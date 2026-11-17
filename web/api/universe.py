"""The whole-market cross-section for Nova Desk: every listed NSE equity, built from the local price store.

Shared by the Screener (/api/scan) and the stock scorecard. Built off the request path (after each price-store
update and at server start) because it takes about 40 seconds; until it is ready, callers use the saved scan.
"""
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.data import price_store, quant_engine as qe, store_scan, symbol_master
from market_lab.market_lab_data import CACHE_DIR

SESSIONS = 300          # enough for the scanner's 200-day average plus a 252-session high
MIN_ROWS = 1500         # a smaller result means the store or the master is broken; keep the saved scan instead
SECTOR_MAP = "nse_sector_classification.csv"
MASTER_MAX_AGE_S = 20 * 3600  # NSE adds listings and renames weekly; a stale master hides them everywhere

_lock = threading.Lock()
_state: dict = {}


def _sectors() -> pd.DataFrame:
    try:
        return pd.read_csv(Path(CACHE_DIR) / "sector" / SECTOR_MAP)
    except Exception:
        return pd.DataFrame(columns=["symbol"])


def refresh_master() -> bool:
    """Re-download NSE's equity list when the cached copy is older than MASTER_MAX_AGE_S. True when refreshed."""
    path = symbol_master.MASTER_FILE
    if path.exists() and time.time() - path.stat().st_mtime < MASTER_MAX_AGE_S:
        return False
    symbol_master.update_master()
    _state.clear()  # the universe depends on the master: rebuild on the next build()
    return True


def listed_symbols(final: dict[str, str]) -> tuple[set[str], dict[str, str]]:
    """(symbols in the NSE equity master under the name they trade as now, old master name -> new name)."""
    if not symbol_master.MASTER_FILE.exists():
        return set(), {}
    master = symbol_master.load_master(auto_update=False)["symbol"].astype(str)
    return {final.get(s, s) for s in master}, {s: final[s] for s in master if s in final}


def company_names(final: dict[str, str]) -> dict[str, str]:
    if not symbol_master.MASTER_FILE.exists():
        return {}
    m = symbol_master.load_master(auto_update=False)
    return {final.get(s, s): n for s, n in zip(m["symbol"].astype(str), m["company_name"].astype(str)) if n}


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
        con = price_store.connect()
        try:
            final = price_store.rename_map(con)
        finally:
            con.close()
        master, renamed = listed_symbols(final)
        master = master or set(histories)
        sectors = _sectors()
        if len(sectors) and renamed:  # the sector file is keyed by the old names too
            sectors = sectors.assign(symbol=sectors["symbol"].map(lambda s: final.get(s, s)))
        bench, bench_error = benchmark_close()
        raw = store_scan.build(histories, as_of, master, bench, sectors)
        if len(raw):
            names = company_names(final)
            raw["company_name"] = raw.get("company_name", pd.Series(index=raw.index, dtype=object)).fillna(raw["symbol"].map(names))
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
