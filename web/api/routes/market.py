from fastapi import APIRouter

from market_lab import view_model as vm
from web.api.report_loader import load_cached_report

router = APIRouter()


@router.get("/market-overview")
def market_overview():
    saved = load_cached_report()
    if not saved:
        return {
            "kpis": None, "chart": None, "breadth": None, "flows": None,
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
        "chart": {"candles": r.get("nifty_candles", [])},
        "breadth": vm.breadth_block(r),
        "flows": vm.flow_block(r),
        "sectors": vm.sector_rows(r, limit=25),
        "derivatives": vm.derivatives_block(r, "nifty"),
        "freshness": {**vm.data_age(r), "saved_at": saved["saved_at"],
                      "file_age_seconds": saved["age_seconds"]},
        "guardrails": vm.guardrails(r),
    }
