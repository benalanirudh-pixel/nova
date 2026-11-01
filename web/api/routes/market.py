import json
import time
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter

from market_lab import view_model as vm
from market_lab.market_lab_data import CACHE_DIR

router = APIRouter()


def load_latest_saved_report():
    """Cache-only read of newest saved Market Lab report (mirrors market_lab_ui, no Qt import)."""
    report_dir = Path(CACHE_DIR) / "market_lab"
    if not report_dir.is_dir():
        return None
    try:
        files = sorted(report_dir.glob("market_lab_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                report = json.load(f)
            if isinstance(report, dict) and report:
                modified = path.stat().st_mtime
                return {
                    "report": report,
                    "saved_at": datetime.fromtimestamp(modified).isoformat(timespec="seconds"),
                    "age_seconds": max(0, time.time() - modified),
                }
        except (OSError, ValueError):
            continue
    return None


@router.get("/market-overview")
def market_overview():
    saved = load_latest_saved_report()
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
