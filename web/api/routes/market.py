import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.data import morning_brief, nse_live

from market_lab import view_model as vm
from web.api.report_loader import load_cached_report

router = APIRouter()


# NSE live quotes, shared by every route that shows prices; 30 s keeps NSE from rate-limiting us
_LIVE_TTL = 30
_live_cache: dict = {}


def live_market() -> dict:
    """{"data": nse_live.market() | None, "error": str | None}; failures are reported, never filled."""
    hit = _live_cache.get("v")
    if hit and time.monotonic() - hit[0] < _LIVE_TTL:
        return hit[1]
    try:
        out = {"data": nse_live.market(), "error": None}
    except Exception as e:
        out = {"data": None, "error": f"NSE live data unavailable: {e}"}
    _live_cache["v"] = (time.monotonic(), out)
    return out


def apply_live(body: dict, live: dict) -> dict:
    """Overlay live NSE prices/breadth onto report-based blocks; adds body["live"]."""
    d = live["data"]
    body["live"] = {"as_of": d and d["as_of"], "error": live["error"],
                    "status": d and d["status"], "gift_nifty": d and d["gift_nifty"],
                    "sectors": d["sectors"] if d else None}
    if not d:
        return body
    k = body.get("kpis") or {}
    if body.get("kpis") is None and any(d.get(x) for x in ("nifty", "banknifty", "vix")):
        body["kpis"] = k  # no saved report: live quotes alone still fill the index cards
    for key in ("nifty", "banknifty", "vix"):
        q = d.get(key)
        if not q or q["price"] is None:
            continue
        card = k.get(key) or {}
        card.update({f: q[f] for f in ("change_abs", "change_percent", "open", "high", "low", "prev_close")},
                    source_label=f"NSE live · {d['as_of']}")
        card["value" if key == "vix" else "price"] = q["price"]
        card.setdefault("name", q["name"])
        k[key] = card
    for macro in (k.get("macro"), body.get("regime")):  # Overview's macro / F&O desk's regime
        if macro is None:
            continue
        if d.get("nifty"):
            macro["nifty_price"] = d["nifty"]["price"]
        if d.get("vix"):
            macro.update(india_vix=d["vix"]["price"], vix_change_percent=d["vix"]["change_percent"])
    b = body.get("breadth")
    if b is not None:
        lb = d["breadth"]
        # report key <- live key (market-wide counts from NSE)
        for dst, src in (("advancing", "advances"), ("declining", "declines"), ("unchanged", "unchanged"),
                         ("new_52w_highs", "new_52w_highs"), ("new_52w_lows", "new_52w_lows")):
            if lb.get(src) is not None:
                b[dst] = lb[src]
        if lb.get("advances") is not None and lb.get("declines"):
            b["ad_ratio"] = lb["advances"] / lb["declines"]
    return body


@router.get("/market-overview")
def market_overview():
    saved = load_cached_report()
    if not saved:
        return apply_live({
            "kpis": None, "breadth": {}, "flows": None,
            "sectors": None, "derivatives": None, "freshness": None,
            "guardrails": vm.guardrails({}),
        }, live_market())
    r = saved["report"]
    return apply_live({
        "kpis": {
            "macro": vm.macro(r),
            "nifty": vm.index_card(r, "nifty"),
            "banknifty": vm.index_card(r, "bank_nifty"),
            "vix": vm.vix_card(r),
            "indicators": vm.indicator_cards(r),
        },
        "breadth": vm.breadth_block(r),
        "flows": vm.flow_block(r),
        "sectors": vm.sector_rows(r, limit=25),
        "derivatives": vm.derivatives_block(r, "nifty"),
        "freshness": {**vm.data_age(r), "saved_at": saved["saved_at"],
                      "file_age_seconds": saved["age_seconds"]},
        "guardrails": vm.guardrails(r),
    }, live_market())


# live sources (news, pre-open, global cues); 5 min keeps the page snappy without going stale
_BRIEF_TTL = 300
_brief_cache: dict = {}


@router.get("/morning-brief")
async def morning_brief_route():
    hit = _brief_cache.get("v")
    if hit and time.monotonic() - hit[0] < _BRIEF_TTL:
        return hit[1]
    saved = load_cached_report()
    try:
        data = await asyncio.to_thread(morning_brief.build_morning_brief, saved["report"] if saved else None)
    except Exception as e:
        return JSONResponse({"error": f"Morning brief failed: {e}"}, status_code=502)
    data["report_saved_at"] = saved["saved_at"] if saved else None
    data["guardrails"] = vm.guardrails(saved["report"] if saved else {})
    _brief_cache["v"] = (time.monotonic(), data)
    return data
