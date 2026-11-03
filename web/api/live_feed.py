"""Read-only live quote loop for the web dashboard.

Polls existing adapters during the NSE session and pushes changed quotes over
the scheduler's SSE channel. Analysis only: no orders, no broker execution.
Never triggers the full NSE equity scan.
"""
import asyncio
import os
import re
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from analysis.data import dhan_feed, nse_feed
from web.api import scheduler

IST = ZoneInfo("Asia/Kolkata")
INDEX_POLL_S = float(os.getenv("NOVA_LIVE_INDEX_S", "5"))
STOCK_POLL_S = float(os.getenv("NOVA_LIVE_STOCK_S", "15"))
HEARTBEAT_S = 10.0
WATCH_TTL_S = 120.0  # clients re-post their symbols; closed tabs drop off
MAX_WATCH = 25
MAX_BACKOFF_S = 300.0
INDICES = ("NIFTY", "BANKNIFTY", "INDIAVIX")
SESSION_OPEN, SESSION_CLOSE = dtime(9, 15), dtime(15, 30)
_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")

_last: dict[str, dict] = {}            # symbol -> last tick
_watch: dict[str, float] = {}          # symbol -> monotonic expiry
_fails: dict[str, int] = {}            # source -> consecutive failures
_next_at: dict[str, float] = {}        # source -> monotonic time of next poll
_errors: dict[str, str] = {}           # source -> last error
_status: dict = {"type": "feed_status", "state": "closed", "reason": "Not started", "as_of": None}


def reset() -> None:
    for d in (_last, _watch, _fails, _next_at, _errors):
        d.clear()
    _status.update(state="closed", reason="Not started", as_of=None)


def in_session(now: datetime) -> bool:
    # shortcut: weekday + hours only, no NSE holiday calendar; add one when the codebase has it.
    now = now.astimezone(IST)
    return now.weekday() < 5 and SESSION_OPEN <= now.time() <= SESSION_CLOSE


def watch(symbols, mono: float | None = None) -> dict:
    """Register symbols for polling. Returns accepted / rejected lists."""
    mono = time.monotonic() if mono is None else mono
    for sym, exp in list(_watch.items()):
        if exp <= mono:
            del _watch[sym]
    accepted, rejected = [], []
    for raw in symbols or []:
        sym = str(raw).strip().upper()
        if not _SYMBOL_RE.match(sym) or sym in INDICES:
            rejected.append(str(raw))
        elif sym in _watch or len(_watch) < MAX_WATCH:
            _watch[sym] = mono + WATCH_TTL_S
            accepted.append(sym)
        else:
            rejected.append(sym)
    return {"accepted": accepted, "rejected": rejected, "max": MAX_WATCH}


def _interval(symbol: str) -> float:
    return INDEX_POLL_S if symbol in INDICES else STOCK_POLL_S


def snapshot(now: datetime | None = None) -> dict:
    """Last known tick per symbol, flagged stale when older than 2x its poll interval."""
    now = now or datetime.now(IST)
    ticks = {}
    for sym, tick in _last.items():
        age = (now - datetime.fromisoformat(tick["as_of"])).total_seconds()
        ticks[sym] = {**tick, "stale": age > 2 * _interval(sym)}
    return {"ticks": ticks, "status": dict(_status), "buy_sell_authorized": False}


def _pct(change, ltp):
    base = ltp - change if ltp is not None and change is not None else None
    return round(change / base * 100, 2) if base else None


def fetch_indices(as_of: str) -> list[dict]:
    if not dhan_feed.is_configured():
        return []
    ticks = []
    for name, q in dhan_feed.get_index_quote(INDICES).items():
        if not q.get("available") or q.get("last_price") is None:
            continue  # missing stays missing
        ticks.append({"type": "tick", "symbol": name, "ltp": q["last_price"],
                      "change": q.get("net_change"), "change_pct": _pct(q.get("net_change"), q["last_price"]),
                      "volume": None, "source": "Dhan", "as_of": as_of, "max_age_s": 2 * INDEX_POLL_S})
    return ticks


def fetch_stocks(symbols, as_of: str) -> list[dict]:
    ticks = []
    for sym in symbols:
        q = nse_feed.get_normalized_stock_quote(sym)
        if q.get("price") is None:
            continue
        ticks.append({"type": "tick", "symbol": sym, "ltp": q["price"], "change": q.get("change"),
                      "change_pct": q.get("change_percent"), "volume": q.get("volume"),
                      "source": q.get("source", "NSE MCP"), "as_of": as_of,
                      "max_age_s": 2 * STOCK_POLL_S})
    return ticks


def _emit(tick: dict) -> bool:
    """Broadcast only when price, change or volume moved."""
    prev = _last.get(tick["symbol"])
    _last[tick["symbol"]] = tick
    key = ("ltp", "change", "volume")
    if prev and all(prev.get(k) == tick.get(k) for k in key):
        return False
    scheduler._broadcast(tick)
    return True


def _set_status(state: str, reason: str, as_of: str) -> None:
    _status.update(state=state, reason=reason, as_of=as_of)


async def poll_once(mono: float, now: datetime) -> int:
    """One loop iteration. Returns number of ticks broadcast."""
    as_of = now.astimezone(IST).isoformat()
    if not in_session(now):
        _set_status("closed", "Outside NSE session (09:15-15:30 IST, Mon-Fri)", as_of)
        return 0

    for sym, exp in list(_watch.items()):
        if exp <= mono:
            del _watch[sym]

    sources = {"indices": (INDEX_POLL_S, lambda: fetch_indices(as_of))}
    if _watch:
        syms = sorted(_watch)
        sources["stocks"] = (STOCK_POLL_S, lambda: fetch_stocks(syms, as_of))

    sent = 0
    for name, (interval, fetch) in sources.items():
        if mono < _next_at.get(name, 0):
            continue
        try:
            ticks = await asyncio.to_thread(fetch)
        except Exception as exc:  # keep the loop alive; report via feed_status
            n = _fails[name] = _fails.get(name, 0) + 1
            _next_at[name] = mono + min(interval * 2 ** n, MAX_BACKOFF_S)
            _errors[name] = f"{name}: {exc}"
            continue
        _fails[name] = 0
        _errors.pop(name, None)
        _next_at[name] = mono + interval
        sent += sum(_emit(t) for t in ticks)

    if _errors and len(_errors) == len(sources):
        _set_status("error", "; ".join(_errors.values()), as_of)
    elif _errors:
        _set_status("delayed", "; ".join(_errors.values()), as_of)
    elif not dhan_feed.is_configured():
        _set_status("delayed", "Dhan not configured: index quotes unavailable", as_of)
    else:
        _set_status("live", "", as_of)
    return sent


async def run() -> None:
    last_beat = 0.0
    while True:
        mono = time.monotonic()
        await poll_once(mono, datetime.now(IST))
        if mono - last_beat >= HEARTBEAT_S:
            scheduler._broadcast(dict(_status))
            last_beat = mono
        await asyncio.sleep(min(INDEX_POLL_S, HEARTBEAT_S))


def start(app) -> None:
    app.state.live_task = asyncio.get_running_loop().create_task(run())


def stop(app) -> None:
    task = getattr(app.state, "live_task", None)
    if task:
        task.cancel()
