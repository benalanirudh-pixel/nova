"""Read-only data for the Nova Desk screener, sector tables and audit screen. Never starts a scan."""
import csv
import glob
import json
import os
import re
from collections import defaultdict
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

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


LINKS_FILE = Path(__file__).resolve().parents[3] / "analysis" / "data" / "supply_chain" / "links.json"
RELATIONS = ("supplier", "customer")
EVIDENCE_LEVELS = ("filed", "stated", "inferred")
_SYMBOL = re.compile(r"^[A-Z0-9&-]{1,20}$")


def load_links(path: Path = LINKS_FILE) -> dict:
    with open(path, encoding="utf8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def validate_links(links: dict) -> list[str]:
    """Problems that would put an unsupported link on screen; empty means the store is usable."""
    out = []
    for company, entry in links.items():
        for i, l in enumerate(entry.get("links", [])):
            where = f"{company}[{i}] {l.get('symbol')}"
            if not _SYMBOL.match(str(l.get("symbol", ""))) or l.get("symbol") == company:
                out.append(f"{where}: bad counterparty symbol")
            if l.get("relation") not in RELATIONS:
                out.append(f"{where}: relation must be one of {RELATIONS}")
            if l.get("confidence") not in EVIDENCE_LEVELS:
                out.append(f"{where}: confidence must be one of {EVIDENCE_LEVELS}")
            if l.get("confidence") in ("filed", "stated") and not str((l.get("evidence") or {}).get("url", "")).startswith("https://"):
                out.append(f"{where}: {l.get('confidence')} link needs an https evidence url")
    return out


def chain_view(symbol: str, links: dict, stocks: dict) -> dict:
    entry = links.get(symbol)
    if not entry:
        return {"symbol": symbol, "covered": False, "covered_symbols": sorted(links)}
    rows = []
    for l in entry["links"]:
        r = stocks.get(l["symbol"]) or {}
        rows.append({**l, "name": r.get("n") or l["symbol"], "sector": r.get("x"), "p": r.get("p"), "r1": r.get("r1"),
                     "r20": r.get("r20"), "rs20": r.get("rs20"), "in_scan": bool(r)})
    return {"symbol": symbol, "covered": True, "checked_at": entry.get("checked_at"), "company": stocks.get(symbol),
            "links": rows, "covered_symbols": sorted(links)}


@router.get("/supply-chain/{symbol}")
def supply_chain(symbol: str):
    key = symbol.strip().upper()
    if not _SYMBOL.match(key):
        return JSONResponse({"error": f"Invalid symbol: {symbol}"}, status_code=400)
    try:
        links = load_links()
    except (OSError, ValueError) as e:
        return JSONResponse({"error": f"Supply-chain store unreadable: {e}"}, status_code=502)
    s = scan()  # fills the scan cache used for live-ish prices; empty when no complete scan exists
    stocks = {r["s"]: r for r in _cache.get("stocks", [])} if s.get("available") else {}
    return {**chain_view(key, links, stocks), "scan_as_of": s.get("as_of"), "guardrails": vm.guardrails({})}
