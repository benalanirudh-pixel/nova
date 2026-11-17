"""Read-only live quote loop for the web dashboard.

Polls existing adapters during the NSE session and pushes changed quotes over
the scheduler's SSE channel. Analysis only: no orders, no broker execution.
Never triggers the full NSE equity scan.

Indices: Dhan when configured, else NSE's website API. Stocks, tried in order per symbol:
Yahoo Finance (1-3 s) -> NSE MCP (15-20 s a call, so only a fallback) -> Stooq, several symbols at once.
Indices and stocks run in separate loops, so a slow stock round never makes index ticks stale.
Yahoo/Stooq are rate-limited; don't poll thousands of symbols every few seconds.
"""
import asyncio
import csv
import io
import os
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from analysis.data import dhan_feed, nse_feed, nse_live
from web.api import scheduler

IST = ZoneInfo("Asia/Kolkata")
INDEX_POLL_S = float(os.getenv("NOVA_LIVE_INDEX_S", "5"))
# without Dhan, indices come from NSE's website API; poll gently so NSE does not block the session
NSE_INDEX_POLL_S = float(os.getenv("NOVA_LIVE_NSE_INDEX_S", "15"))
STOCK_POLL_S = float(os.getenv("NOVA_LIVE_STOCK_S", "15"))
HEARTBEAT_S = 10.0
WATCH_TTL_S = 120.0  # clients re-post their symbols; closed tabs drop off
MAX_WATCH = 25
MAX_BACKOFF_S = 300.0
STOCK_WORKERS = 6           # parallel quote requests; 25 watched symbols take one or two Yahoo round trips
INDICES = ("NIFTY", "BANKNIFTY", "INDIAVIX")
SESSION_OPEN, SESSION_CLOSE = dtime(9, 15), dtime(15, 30)
_SYMBOL_RE = re.compile(r"^[A-Z0-9&\-]{1,20}$")

_last: dict[str, dict] = {}            # symbol -> last tick
_watch: dict[str, float] = {}          # symbol -> monotonic expiry
_fails: dict[str, int] = {}            # source -> consecutive failures
_next_at: dict[str, float] = {}        # source -> monotonic time of next poll
_errors: dict[str, str] = {}           # source -> last error
_status: dict = {"type": "feed_status", "state": "closed", "reason": "Not started", "as_of": None}
_holidays: dict = {"day": None, "dates": set()}  # NSE trading holidays, fetched once per IST day
STATUS_CHECK_S = 300.0                               # off the clock, ask NSE whether a special session is open
SPECIAL_WINDOW = (dtime(8, 45), dtime(20, 0))        # muhurat runs in the evening; never ask overnight
_nse_state: dict = {"at": None, "open": False}


def reset() -> None:
    for d in (_last, _watch, _fails, _next_at, _errors):
        d.clear()
    _status.update(state="closed", reason="Not started", as_of=None)
    _holidays.update(day=None, dates=set())
    _nse_state.update(at=None, open=False)


def in_session(now: datetime, holidays=frozenset()) -> bool:
    now = now.astimezone(IST)
    return now.weekday() < 5 and now.date().isoformat() not in holidays and SESSION_OPEN <= now.time() <= SESSION_CLOSE


async def _load_holidays(now: datetime) -> None:
    day = now.astimezone(IST).date()
    if _holidays["day"] == day:
        return
    try:
        _holidays["dates"] = await asyncio.to_thread(nse_live.trading_holidays)
    except Exception:
        pass  # keep the last list; without one the feed falls back to weekday hours
    _holidays["day"] = day


async def _nse_says_open(mono: float, now: datetime) -> bool:
    """NSE's Capital Market status, asked at most every STATUS_CHECK_S and only inside SPECIAL_WINDOW."""
    t = now.astimezone(IST).time()
    if not SPECIAL_WINDOW[0] <= t <= SPECIAL_WINDOW[1]:
        return False
    if _nse_state["at"] is None or mono - _nse_state["at"] >= STATUS_CHECK_S:
        _nse_state["at"] = mono
        try:
            status = await asyncio.to_thread(nse_live.get, "marketStatus")
            cm = next((m for m in (status or {}).get("marketState", []) if m.get("market") == "Capital Market"), {})
            _nse_state["open"] = str(cm.get("marketStatus", "")).strip().lower() == "open"
        except Exception:
            _nse_state["open"] = False
    return _nse_state["open"]


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


def _index_interval() -> float:
    return INDEX_POLL_S if dhan_feed.is_configured() else NSE_INDEX_POLL_S


def _interval(symbol: str) -> float:
    return _index_interval() if symbol in INDICES else STOCK_POLL_S


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


def fetch_nse_indices(as_of: str) -> list[dict]:
    q = nse_live.parse_indices(nse_live.get("allIndices"))
    names = {"nifty": "NIFTY", "banknifty": "BANKNIFTY", "vix": "INDIAVIX"}
    return [{"type": "tick", "symbol": sym, "ltp": q[k]["price"], "change": q[k]["change_abs"],
             "change_pct": q[k]["change_percent"], "volume": None, "source": "NSE", "as_of": as_of,
             "max_age_s": 2 * NSE_INDEX_POLL_S}
            for k, sym in names.items() if q.get(k) and q[k]["price"] is not None]


# ------------------------------------------------------------------
# Yahoo Finance fallback (free, rate-limited)
# ------------------------------------------------------------------

def _yahoo_symbol(symbol: str) -> str:
    return f"{symbol}.NS"


def fetch_yahoo_quote(symbol: str, as_of: str) -> dict | None:
    """Return a normalized tick dict for one symbol via Yahoo Finance, or None."""
    try:
        import yfinance as yf
    except Exception:
        return None
    try:
        t = yf.Ticker(_yahoo_symbol(symbol))
        info = t.fast_info or {}
        price = info.get("last_price") or info.get("lastPrice") or info.get("regular_market_price")
        if price is None:
            hist = t.history(period="1d", interval="1m", prepost=False, actions=False)
            if hist is None or hist.empty:
                return None
            price = float(hist["Close"].iloc[-1])
        prev = info.get("previous_close") or info.get("regular_market_previous_close")
        change = None
        change_pct = None
        if prev and price is not None:
            change = float(price) - float(prev)
            change_pct = round(change / float(prev) * 100, 2)
        return {"type": "tick", "symbol": symbol, "ltp": float(price), "change": change,
                "change_pct": change_pct, "volume": None, "source": "Yahoo",
                "as_of": as_of, "max_age_s": 60}
    except Exception:
        return None


# ------------------------------------------------------------------
# Stooq fallback (free CSV, delayed, rate-limited)
# ------------------------------------------------------------------

def fetch_stooq_quote(symbol: str, as_of: str) -> dict | None:
    """Return a normalized tick dict for one symbol via Stooq, or None."""
    url = f"https://stooq.com/q/l/?s={symbol.lower()}.ns&f=sd2t2chv&h&e=csv"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None
    reader = csv.DictReader(io.StringIO(data))
    for row in reader:
        close = (row.get("Close") or "").strip()
        if not close or close == "N/D":
            continue
        try:
            price = float(close)
        except ValueError:
            continue
        chg = (row.get("Chg") or "").strip()
        change = None
        change_pct = None
        try:
            change = float(chg)
        except ValueError:
            change = None
        if change is not None and price:
            change_pct = round(change / (price - change) * 100, 2) if (price - change) else None
        vol = None
        try:
            vol = int((row.get("Volume") or "0").strip() or 0)
        except ValueError:
            vol = None
        return {"type": "tick", "symbol": symbol, "ltp": price, "change": change,
                "change_pct": change_pct, "volume": vol, "source": "Stooq",
                "as_of": as_of, "max_age_s": 300}
    return None


def _mcp_quote(symbol: str, as_of: str) -> dict | None:
    q = nse_feed.get_normalized_stock_quote(symbol)
    if q.get("price") is None:
        return None
    return {"type": "tick", "symbol": symbol, "ltp": q["price"], "change": q.get("change"),
            "change_pct": q.get("change_percent"), "volume": q.get("volume"),
            "source": q.get("source", "NSE MCP"), "as_of": as_of, "max_age_s": 2 * STOCK_POLL_S}


def fetch_stock_quote_free(symbol: str, as_of: str) -> dict | None:
    """Yahoo, then NSE MCP, then Stooq. One source failing never hides the next.
    Raises when no source had a quote and at least one failed, so the round is reported and backed off."""
    errors = []
    for name, fetch in (("Yahoo", fetch_yahoo_quote), ("NSE MCP", _mcp_quote), ("Stooq", fetch_stooq_quote)):
        try:
            tick = fetch(symbol, as_of)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            continue
        if tick:
            return tick
    if errors:
        raise RuntimeError("; ".join(errors))
    return None


def fetch_indices(as_of: str) -> list[dict]:
    if not dhan_feed.is_configured():
        return fetch_nse_indices(as_of)
    ticks = []
    for name, q in dhan_feed.get_index_quote(INDICES).items():
        if not q.get("available") or q.get("last_price") is None:
            continue  # missing stays missing
        ticks.append({"type": "tick", "symbol": name, "ltp": q["last_price"],
                      "change": q.get("net_change"), "change_pct": _pct(q.get("net_change"), q["last_price"]),
                      "volume": None, "source": "Dhan", "as_of": as_of, "max_age_s": 2 * INDEX_POLL_S})
    return ticks


def fetch_stocks(symbols, as_of: str) -> list[dict]:
    """Quotes for every watched symbol, several at a time. Raises when no symbol could be quoted at all."""
    symbols = list(symbols)
    if not symbols:
        return []
    ticks, errors = [], []
    with ThreadPoolExecutor(max_workers=min(STOCK_WORKERS, len(symbols))) as pool:
        for sym, fut in [(s, pool.submit(fetch_stock_quote_free, s, as_of)) for s in symbols]:
            try:
                tick = fut.result()
            except Exception as exc:
                errors.append(f"{sym}: {exc}")
                continue
            if tick:
                ticks.append(tick)
    if errors and not ticks:
        raise RuntimeError(errors[0])
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


async def poll_once(mono: float, now: datetime, only: set | None = None) -> int:
    """One pass over the due sources (all, or just `only`). Returns the number of ticks broadcast."""
    as_of = now.astimezone(IST).isoformat()
    await _load_holidays(now)
    holiday = now.astimezone(IST).date().isoformat() in _holidays["dates"]
    if (holiday or not in_session(now)) and not await _nse_says_open(mono, now):
        _set_status("closed", "NSE trading holiday" if holiday else "Outside NSE session (09:15-15:30 IST, Mon-Fri)", as_of)
        return 0

    for sym, exp in list(_watch.items()):
        if exp <= mono:
            del _watch[sym]

    sources = {"indices": (_index_interval(), lambda: fetch_indices(as_of))}
    if _watch:
        syms = sorted(_watch)
        sources["stocks"] = (STOCK_POLL_S, lambda: fetch_stocks(syms, as_of))
    active = set(sources)  # the status covers every source, whichever loop is calling
    if only is not None:
        sources = {k: v for k, v in sources.items() if k in only}

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

    errs = {k: v for k, v in _errors.items() if k in active}
    if errs and len(errs) == len(active):
        _set_status("error", "; ".join(errs.values()), as_of)
    elif errs:
        _set_status("delayed", "; ".join(errs.values()), as_of)
    else:
        _set_status("live", "", as_of)
    return sent


async def _poll_loop(names: set, pause: float) -> None:
    while True:
        try:
            await poll_once(time.monotonic(), datetime.now(IST), only=names)
        except Exception as exc:  # one bad pass must not end the feed
            print(f"[LIVE FEED] {sorted(names)}: {exc}")
        await asyncio.sleep(pause)


async def _heartbeat() -> None:
    while True:
        scheduler._broadcast(dict(_status))
        await asyncio.sleep(HEARTBEAT_S)


async def run() -> None:
    # separate loops: a stock round can take seconds, and index ticks must not wait for it
    await asyncio.gather(_poll_loop({"indices"}, min(INDEX_POLL_S, HEARTBEAT_S)), _poll_loop({"stocks"}, 1.0), _heartbeat())


def start(app) -> None:
    app.state.live_task = asyncio.get_running_loop().create_task(run())


def stop(app) -> None:
    task = getattr(app.state, "live_task", None)
    if task:
        task.cancel()
