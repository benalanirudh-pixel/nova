import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.data import fno_desk

from market_lab import view_model as vm
from web.api.report_loader import load_cached_report

router = APIRouter()


@router.get("/market-analysis")
def market_analysis():
    saved = load_cached_report()
    if not saved:
        return {k: None for k in ("regime", "breadth", "sectors", "flows", "derivatives",
                                  "indicators", "events", "risk", "freshness")} | {"guardrails": vm.guardrails({})}
    r = saved["report"]
    return {
        "regime": vm.macro(r),
        "breadth": vm.breadth_block(r),
        "sectors": vm.sector_rows(r, limit=25),
        "flows": {**vm.flow_block(r), "series": vm.flow_series(r)},
        "derivatives": {"nifty": vm.derivatives_block(r, "nifty"),
                        "bank_nifty": vm.derivatives_block(r, "bank_nifty")},
        "indicators": vm.indicator_cards(r, "nifty"),
        "events": r.get("event_risk_context", {}),
        "risk": vm.risk_block(r),
        "freshness": {**vm.data_age(r), "saved_at": saved["saved_at"],
                      "file_age_seconds": saved["age_seconds"]},
        "guardrails": vm.guardrails(r),
    }


# option chains move every few seconds intraday; 60 s keeps the exchanges from being hammered
_FNO_TTL = 60
_fno_cache: dict = {}


@router.get("/fno/{instrument}")
async def fno(instrument: str, expiry: str | None = None):
    key = instrument.strip().upper()
    if key not in fno_desk.INSTRUMENTS:
        return JSONResponse({"error": f"Unsupported instrument: {instrument}. Use NIFTY, BANKNIFTY or SENSEX."}, status_code=404)
    if expiry is not None and (len(expiry) > 20 or not all(ch.isalnum() or ch in " -" for ch in expiry)):
        return JSONResponse({"error": f"Invalid expiry: {expiry}"}, status_code=400)
    hit = _fno_cache.get((key, expiry))
    if hit and time.monotonic() - hit[0] < _FNO_TTL:
        return hit[1]
    try:
        data = await asyncio.to_thread(fno_desk.build_fno, key, expiry)
    except Exception as e:
        return JSONResponse({"error": f"F&O desk failed: {e}"}, status_code=502)
    data["guardrails"] = vm.guardrails({})
    _fno_cache[(key, expiry)] = (time.monotonic(), data)
    return data
