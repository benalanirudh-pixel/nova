"""Read-only data for the Nova Desk screener, sector tables and audit screen. Never starts a scan."""
import csv
import glob
import os
import re
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter

from analysis.data import symbol_master
from market_lab import view_model as vm
from market_lab.market_lab_data import CACHE_DIR
from web.api.report_loader import load_cached_report

router = APIRouter()

MIN_COMPLETE_ROWS = 1500  # a throttled scan can save a few hundred stocks; do not treat that as the market
MIN_SECTOR_STOCKS = 5
TRENDS = {"STRONG_UPTREND": "Strong up", "UPTREND": "Up", "SIDEWAYS": "Sideways",
          "DOWNTREND": "Down", "STRONG_DOWNTREND": "Strong down"}
COLUMNS = ("s", "n", "x", "p", "r1", "r5", "r20", "r60", "rs20", "e20", "e50", "e200",
           "rsi", "atr", "val", "rv", "h52", "l52", "dh", "t", "sc")
_cache: dict = {}


def _f(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return round(x, 2) if x == x else None


def _rows(path: str) -> list[dict]:
    with open(path, encoding="utf8", newline="") as f:
        return list(csv.DictReader(f))


def latest_complete_scan(scanner_dir: str, newest_first: list[str] | None = None) -> tuple[str | None, list[dict], int]:
    """Newest scan with enough rows, its rows, and how many stocks the very newest scan covered."""
    paths = newest_first if newest_first is not None else sorted(
        glob.glob(os.path.join(scanner_dir, "market_scan_*.csv")), key=os.path.getmtime, reverse=True)
    newest = None
    for p in paths:
        rows = _rows(p)
        newest = len(rows) if newest is None else newest
        if len(rows) >= MIN_COMPLETE_ROWS:
            return p, rows, newest
    return None, [], newest or 0


def build_stocks(rows: list[dict], sectors: dict[str, str], names: dict[str, str]) -> list[dict]:
    out = []
    for r in rows:
        p = _f(r.get("price"))
        if not p:
            continue
        vs = lambda k: round((p / e - 1) * 100, 2) if (e := _f(r.get(k))) else None
        out.append({
            "s": r["symbol"], "n": names.get(r["symbol"]) or r["symbol"], "x": sectors.get(r["symbol"], ""), "p": p,
            "r1": _f(r.get("return_1d")), "r5": _f(r.get("return_5d")), "r20": _f(r.get("return_20d")),
            "r60": _f(r.get("return_60d")), "rs20": _f(r.get("relative_strength_20d")),
            "e20": vs("ema_20"), "e50": vs("ema_50"), "e200": vs("ema_200"), "rsi": _f(r.get("rsi_14")),
            "atr": _f(r.get("atr_percent")), "val": round(p * (_f(r.get("volume")) or 0) / 1e7, 2),
            "rv": _f(r.get("relative_volume")), "h52": _f(r.get("high_52w")), "l52": _f(r.get("low_52w")),
            "dh": _f(r.get("distance_52w_high")), "t": TRENDS.get(r.get("trend"), r.get("trend")), "sc": _f(r.get("score")),
        })
    return out


def _mean(rows: list[dict], key: str):
    vals = [r[key] for r in rows if r[key] is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def build_sectors(stocks: list[dict]) -> list[dict]:
    """Equal-weight sector table from today's stock rows, so it cannot go stale with the sector scan."""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in stocks:
        if r["x"]:
            groups[r["x"]].append(r)
    out = []
    for name, g in groups.items():
        if len(g) < MIN_SECTOR_STOCKS:
            continue
        by5 = sorted(g, key=lambda r: r["r5"] if r["r5"] is not None else 0)
        out.append({"n": name, "c": len(g), "r1": _mean(g, "r1"), "r5": _mean(g, "r5"), "r20": _mean(g, "r20"),
                    "r60": _mean(g, "r60"), "a200": round(sum(1 for r in g if (r["e200"] or 0) > 0) / len(g) * 100, 1),
                    "rsi": _mean(g, "rsi"), "val": round(sum(r["val"] for r in g), 1),
                    "best": by5[-1]["s"], "worst": by5[0]["s"]})
    return sorted(out, key=lambda r: -(r["r5"] if r["r5"] is not None else -1e9))


def _names() -> dict[str, str]:
    try:
        if not symbol_master.MASTER_FILE.exists():
            return {}
        df = symbol_master.load_master(auto_update=False)
        col = next((c for c in ("company_name", "name") if c in df.columns), None)
        return {r["symbol"]: r[col] for _, r in df.iterrows()} if col else {}
    except Exception:
        return {}


def _date(path: str | None) -> str | None:
    m = re.search(r"_(\d{4})(\d{2})(\d{2})_", os.path.basename(path or ""))
    return "-".join(m.groups()) if m else None


@router.get("/scan")
def scan():
    root = Path(CACHE_DIR)
    path, rows, newest = latest_complete_scan(str(root / "scanner"))
    if not path:
        return {"available": False, "columns": COLUMNS, "rows": [], "sectors": [], "newest_stocks": newest}
    enriched = sorted(glob.glob(str(root / "sector" / "sector_enriched*")))
    key = (path, enriched[-1] if enriched else None)
    if _cache.get("key") != key:
        sectors = {r["symbol"]: r.get("sector") or "" for r in _rows(enriched[-1])} if enriched else {}
        stocks = build_stocks(rows, sectors, _names())
        _cache.update(key=key, stocks=stocks, table=build_sectors(stocks))
    return {
        "available": True, "as_of": _date(path), "stock_count": len(_cache["stocks"]), "newest_stocks": newest,
        "sector_map_as_of": _date(enriched[-1]) if enriched else None, "columns": COLUMNS,
        "rows": [[r[c] for c in COLUMNS] for r in _cache["stocks"]], "sectors": _cache["table"],
        "guardrails": vm.guardrails({}),
    }


@router.get("/audit")
def audit():
    saved = load_cached_report()
    r = saved["report"] if saved else {}
    factors = r.get("research_factors") or {}
    ranked = (factors.get("top_ranked") or []) + (factors.get("bottom_ranked") or [])
    return {
        "report_saved_at": saved["saved_at"] if saved else None, "stocks_analyzed": r.get("stocks_analyzed"),
        "data_availability": r.get("data_availability") or {}, "decision_policy": r.get("decision_policy") or {},
        "sector_file_as_of": _date(r.get("sector_file")), "scanner_file_as_of": _date(r.get("scanner_file")),
        "factor_rows": len(ranked), "factor_rows_empty": sum(1 for x in ranked if not any((x.get("factor_z") or {}).values())),
        "guardrails": vm.guardrails(r),
    }
