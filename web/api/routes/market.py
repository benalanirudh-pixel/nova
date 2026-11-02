import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.data import morning_brief

from market_lab import view_model as vm
from web.api.report_loader import load_cached_report

router = APIRouter()


@router.get("/market-overview")
def market_overview():
    saved = load_cached_report()
    if not saved:
        return {
            "kpis": None, "breadth": None, "flows": None,
            "sectors": None, "derivatives": None, "freshness": None,
            "guardrails": vm.guardrails({}),
        }
    r = saved["report"]
    return {
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
    }


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
