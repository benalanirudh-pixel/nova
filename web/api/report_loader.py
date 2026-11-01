import json
import time
from datetime import datetime
from pathlib import Path

from market_lab.market_lab_data import CACHE_DIR


def load_cached_report():
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
