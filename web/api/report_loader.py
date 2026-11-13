import json
import time
from datetime import datetime
from pathlib import Path

from market_lab.market_lab_data import CACHE_DIR

_cache: dict = {}  # (dir, dir mtime) -> parsed newest report; a new save changes the directory's mtime


def load_cached_report():
    """Cache-only read of newest saved Market Lab report (mirrors market_lab_ui, no Qt import)."""
    report_dir = Path(CACHE_DIR) / "market_lab"
    if not report_dir.is_dir():
        return None
    try:
        dir_mtime = (str(report_dir), report_dir.stat().st_mtime)
        if _cache.get("key") == dir_mtime:
            saved = _cache["value"]
            return saved and {**saved, "age_seconds": max(0, time.time() - saved["mtime"])}
        files = sorted(report_dir.glob("market_lab_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return None
    saved = None
    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                # NaN/Infinity (e.g. a partial candle) are not valid JSON for the API: read them as missing
                report = json.load(f, parse_constant=lambda _: None)
            if isinstance(report, dict) and report:
                modified = path.stat().st_mtime
                saved = {"report": report, "mtime": modified,
                         "saved_at": datetime.fromtimestamp(modified).isoformat(timespec="seconds")}
                break
        except (OSError, ValueError):
            continue
    _cache.update(key=dir_mtime, value=saved)
    return saved and {**saved, "age_seconds": max(0, time.time() - saved["mtime"])}
