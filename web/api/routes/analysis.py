from fastapi import APIRouter

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
