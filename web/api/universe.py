"""The whole-market cross-section for Nova Desk: every listed NSE equity, built from the local price store.

Shared by the Screener (/api/scan) and the stock scorecard. Built off the request path (after each price-store
update and at server start) because it takes about 40 seconds; until it is ready, callers use the saved scan.
"""
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.data import price_store, quant_engine as qe, store_scan, symbol_master
from market_lab.market_lab_data import CACHE_DIR

SESSIONS = 300          # enough for the scanner's 200-day average plus a 252-session high
MIN_ROWS = 1500         # a smaller result means the store or the master is broken; keep the saved scan instead
SECTOR_MAP = "nse_sector_classification.csv"

_lock = threading.Lock()
_state: dict = {}


def _sectors() -> pd.DataFrame:
    try:
        return pd.read_csv(Path(CACHE_DIR) / "sector" / SECTOR_MAP)
    except Exception:
        return pd.DataFrame(columns=["symbol"])


def build() -> Optional[dict]:
    """Build (or reuse) the cross-section for the store as it is now. Blocking; call from a worker thread."""
    key = price_store.version()
    if not key[0]:
        return None
    with _lock:
        if _state.get("key") == key:
            return _state.get("value")
        from web.api.routes.quant import benchmark_close  # late: quant imports this module's readers
        as_of, histories = price_store.recent_histories(SESSIONS)
        master = set(symbol_master.load_master(auto_update=False)["symbol"].astype(str)) if symbol_master.MASTER_FILE.exists() else set(histories)
        bench, bench_error = benchmark_close()
        raw = store_scan.build(histories, as_of, master, bench, _sectors())
        value = None
        if len(raw) >= MIN_ROWS:
            value = {"as_of": as_of, "raw": raw, "frame": qe.prepare(raw), "listed": len(master), "built_at": datetime.now().isoformat(timespec="seconds"),
                     "short_history": int(raw["short_history"].sum()), "benchmark_error": bench_error}
        _state.clear()
        _state.update(key=key, value=value)
        return value


def ready() -> Optional[dict]:
    """The cross-section if one is built for the store's current state; never builds. A few milliseconds."""
    value = _state.get("value")
    if value is None:
        return None
    try:
        return value if _state.get("key") == price_store.version() else None
    except Exception:
        return None
