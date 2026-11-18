"""
Single-day movers from the cached scanner CSV: biggest stock moves, 1-day
sector moves, and headline matching for the movers. No network here.

Movers are measured price changes, not predictions or buy/sell signals.
A headline is shown as context only; it is not proof of why a stock moved.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from analysis.data.stock_profile import CLASSIFICATION_FILE, SCANNER_DIR

MIN_PRICE = 20.0           # below this, % moves are mostly tick noise
MIN_TURNOVER_CR = 5.0      # 20-day average traded value; keeps illiquid stocks off the list
MIN_SECTOR_STOCKS = 10  # the classification mixes two taxonomies; small leftover groups are noise
HEADLINE_MAX_AGE_H = 36    # covers results posted after the previous close


def load_latest(scanner_dir: Path = SCANNER_DIR, classification_file: Path = CLASSIFICATION_FILE) -> Optional[pd.DataFrame]:
    """Latest scan joined with company name and sector. None when no scan is cached."""
    files = sorted(Path(scanner_dir).glob("market_scan_*.csv"), key=lambda p: p.stat().st_mtime)
    if not files:
        return None
    scan = pd.read_csv(files[-1])
    try:
        classes = pd.read_csv(classification_file, usecols=["symbol", "company_name", "sector"])
        classes["sector"] = classes["sector"].replace({"—": None, "-": None, "": None})  # placeholder, not a sector
        scan = scan.merge(classes, on="symbol", how="left")
    except (OSError, ValueError):
        scan["company_name"], scan["sector"] = None, None
    scan.attrs["file"] = files[-1].name
    return scan


def _row(r) -> dict:
    def val(k):
        v = r.get(k)
        return None if v is None or (isinstance(v, float) and pd.isna(v)) else v
    return {"symbol": r["symbol"], "company": val("company_name"), "sector": val("sector"),
            "change_pct": float(r["return_1d"]), "price": float(r["price"]), "rel_volume": val("relative_volume")}


def top_movers(scan: pd.DataFrame, n: int = 5, min_price: float = MIN_PRICE,
               min_turnover_cr: float = MIN_TURNOVER_CR) -> dict:
    d = scan.dropna(subset=["return_1d", "price", "volume_average_20"])
    d = d[(d["price"] >= min_price) & (d["price"] * d["volume_average_20"] / 1e7 >= min_turnover_cr)]
    return {"gainers": [_row(r) for _, r in d.nlargest(n, "return_1d").iterrows() if r["return_1d"] > 0],
            "losers": [_row(r) for _, r in d.nsmallest(n, "return_1d").iterrows() if r["return_1d"] < 0]}


def sector_moves(scan: pd.DataFrame, n: int = 3, min_stocks: int = MIN_SECTOR_STOCKS) -> dict:
    """Median 1-day move per sector, so one runaway stock cannot carry a sector."""
    d = scan.dropna(subset=["return_1d", "sector"])
    g = d.groupby("sector")["return_1d"].agg(["median", "count"])
    g = g[g["count"] >= min_stocks].sort_values("median")
    rows = [{"sector": s, "median_pct": float(m), "stocks": int(c)} for s, (m, c) in g.iterrows()]
    return {"up": [r for r in reversed(rows[-n:]) if r["median_pct"] > 0],
            "down": [r for r in rows[:n] if r["median_pct"] < 0]}


def match_headline(news: list[dict], symbol: str, company: Optional[str],
                   now: Optional[datetime] = None, max_age_h: int = HEADLINE_MAX_AGE_H) -> Optional[dict]:
    """Newest recent headline naming the stock (symbol or first word of its company name)."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=max_age_h)).isoformat()
    keys = {symbol.lower()}
    first = str(company or "").split()[0].lower() if company else ""
    if len(first) >= 4:
        keys.add(first)
    hits = [n for n in news if n.get("published") and n["published"] >= cutoff
            and any(k in str(n.get("title", "")).lower() for k in keys)]
    return max(hits, key=lambda n: n["published"]) if hits else None
