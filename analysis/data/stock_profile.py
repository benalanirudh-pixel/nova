"""
Single-stock profile for the web Stock page: company, valuation, quarterly
results, next results date, ownership, competitors, news, corporate actions
and a rule-based list of highlights.

Sources (each section independent; a failed source gives None + a reason,
never a made-up value):
- Indian Market MCP (nse_feed.call_tools): profile, key ratios, quarterly
  income statement, stock news, corporate actions, NSE shareholding pattern,
  NSE board meetings.
- Yahoo Finance via yfinance: next earnings date/estimates and holder
  percentages (NSE shareholding/board-meeting endpoints are often blocked).
- Local caches: NSE sector classification + latest scanner CSV for peers.

Analysis only: nothing here is a buy/sell signal.
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from analysis.data import nse_feed

CACHE_DIR = Path(__file__).resolve().parent / "cache"
CLASSIFICATION_FILE = CACHE_DIR / "sector" / "nse_sector_classification.csv"
SCANNER_DIR = CACHE_DIR / "scanner"

CRORE = 1e7


def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _error_of(v: Any) -> Optional[str]:
    """Reason a source result is unusable, or None when it is usable."""
    if isinstance(v, Exception):
        return str(v)
    if isinstance(v, dict) and v.get("error"):
        return str(v["error"])
    if isinstance(v, str):
        return v[:200]
    if v is None or v == [] or v == {}:
        return "No data returned"
    return None


# ---------------------------------------------------------------- sections

def parse_profile(p: dict) -> dict:
    return {
        "company": p.get("company"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "website": p.get("website") if str(p.get("website", "")).startswith("http") else None,
        "description": p.get("description"),
        "employees": _num(p.get("employees")),
    }


def parse_ratios(r: dict, price: Any = None) -> dict:
    out = {k: _num(r.get(k)) for k in (
        "market_cap_cr", "enterprise_value_cr", "pe_trailing", "pe_forward", "pb", "ps", "peg",
        "ev_ebitda", "roe", "roa", "current_ratio", "eps_trailing", "eps_forward",
        "dividend_per_share", "payout_ratio", "revenue_growth", "earnings_growth",
        "profit_margin", "operating_margin", "gross_margin", "beta", "book_value",
    )}
    # Yahoo reports debt/equity as a percent (44.3 = 0.44x).
    de = _num(r.get("debt_to_equity"))
    out["debt_to_equity_x"] = de / 100 if de is not None else None
    # The feed's dividend_yield is scaled inconsistently, so derive it from DPS / price.
    dps, price = _num(r.get("dividend_per_share")), _num(r.get("price", price))
    out["dividend_yield_pct"] = dps / price * 100 if dps is not None and price else None
    return out


def parse_quarters(stmt: dict, limit: int = 5) -> list[dict]:
    rows = [d for d in (stmt.get("data") or []) if isinstance(d, dict) and d.get("period")]
    rows.sort(key=lambda d: str(d["period"]), reverse=True)

    def cr(d, k):
        v = _num(d.get(k))
        return v / CRORE if v is not None else None

    q = [{
        "period": str(d["period"])[:10],
        "revenue_cr": cr(d, "Total Revenue"),
        "ebitda_cr": cr(d, "EBITDA"),
        "operating_income_cr": cr(d, "Operating Income"),
        "net_income_cr": cr(d, "Net Income"),
        "eps": _num(d.get("Diluted EPS")),
    } for d in rows]

    def growth(cur, prev):
        return (cur - prev) / abs(prev) * 100 if cur is not None and prev else None

    for i, row in enumerate(q):
        rev, op = row["revenue_cr"], row["operating_income_cr"]
        row["operating_margin"] = op / rev * 100 if rev and op is not None else None
        row["revenue_qoq"] = growth(rev, q[i + 1]["revenue_cr"]) if i + 1 < len(q) else None
        row["net_income_qoq"] = growth(row["net_income_cr"], q[i + 1]["net_income_cr"]) if i + 1 < len(q) else None
        row["revenue_yoy"] = growth(rev, q[i + 4]["revenue_cr"]) if i + 4 < len(q) else None
    return q[:limit]


def parse_news(items: list, limit: int = 12) -> list[dict]:
    out = []
    for n in items:
        if not isinstance(n, dict):
            continue
        link, title, source = str(n.get("link") or ""), str(n.get("title") or "").strip(), n.get("source")
        if not title or not link.startswith("https://"):  # href goes into the page: https only
            continue
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            published = parsedate_to_datetime(str(n.get("published"))).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            published = None
        out.append({"title": title, "link": link, "source": source, "published": published})
    return out[:limit]


def parse_actions(items: list, limit: int = 8) -> list[dict]:
    return [{"ex_date": a.get("exDate"), "subject": a.get("subject")}
            for a in items if isinstance(a, dict) and a.get("subject")][:limit]


def _pick(d: dict, *needles: str) -> Optional[float]:
    for k, v in d.items():
        if any(n in str(k).lower() for n in needles) and _num(v) is not None:
            return _num(v)
    return None


def parse_nse_shareholding(d: dict) -> dict:
    return {
        "promoter_pct": _pick(d, "promoter"),
        "fii_pct": _pick(d, "fii", "foreign", "fpi"),
        "dii_pct": _pick(d, "dii", "domestic", "mutual"),
        "public_pct": _pick(d, "public", "retail"),
    }


def parse_board_meetings(items: Any, limit: int = 5) -> list[dict]:
    rows = items.get("data", []) if isinstance(items, dict) else items
    out = []
    for m in rows or []:
        if not isinstance(m, dict):
            continue
        when = next((v for k, v in m.items() if "date" in k.lower() and v), None)
        what = next((v for k, v in m.items() if any(w in k.lower() for w in ("purpose", "subject", "desc")) and v), None)
        if when:
            out.append({"date": str(when), "purpose": str(what) if what else None})
    return out[:limit]


def yahoo_sections(symbol: str) -> dict:
    """Earnings calendar + holder percentages from Yahoo; each part None on failure."""
    out: dict = {"calendar": None, "holders": None, "errors": {}}
    try:
        import yfinance as yf
        t = yf.Ticker(f"{symbol}.NS")
    except Exception as exc:
        out["errors"]["yahoo"] = f"yfinance unavailable: {exc}"
        return out

    try:
        c = t.calendar or {}
        dates = c.get("Earnings Date") or []
        ex_div = c.get("Ex-Dividend Date")
        out["calendar"] = {
            "earnings_dates": [str(d) for d in dates],
            "eps_estimate": _num(c.get("Earnings Average")),
            "revenue_estimate_cr": (_num(c.get("Revenue Average")) or 0) / CRORE or None,
            "ex_dividend_date": str(ex_div) if ex_div else None,
        }
    except Exception as exc:
        out["errors"]["calendar"] = f"Yahoo calendar failed: {exc}"

    try:
        mh = t.major_holders
        v = mh["Value"].to_dict() if mh is not None and "Value" in mh else {}
        pct = lambda k: _num(v.get(k)) * 100 if _num(v.get(k)) is not None else None  # noqa: E731
        holders = {
            "insiders_pct": pct("insidersPercentHeld"),
            "institutions_pct": pct("institutionsPercentHeld"),
            "institutions_float_pct": pct("institutionsFloatPercentHeld"),
            "institutions_count": _num(v.get("institutionsCount")),
        }
        out["holders"] = holders if any(x is not None for x in holders.values()) else None
        if out["holders"] is None:
            out["errors"]["holders"] = "Yahoo returned no holder breakdown"
    except Exception as exc:
        out["errors"]["holders"] = f"Yahoo holders failed: {exc}"
    return out


def local_peers(symbol: str, limit: int = 8,
                classification_file: Path = CLASSIFICATION_FILE, scanner_dir: Path = SCANNER_DIR) -> Optional[dict]:
    """Same-industry stocks from the NSE classification cache, ranked by traded value from the latest scan."""
    if not classification_file.exists():
        return None
    cls = pd.read_csv(classification_file)
    me = cls[cls["symbol"] == symbol]
    if me.empty:
        return None
    me = me.iloc[0]
    basis, group = "basic_industry", cls[cls["basic_industry"] == me["basic_industry"]]
    if len(group) < 4:  # too narrow to compare against: widen one level
        basis, group = "industry", cls[cls["industry"] == me["industry"]]

    scans = sorted((p for p in scanner_dir.glob("market_scan_*.csv")), key=lambda p: p.stat().st_mtime)
    if not scans:
        return {"basis": basis, "group": me[basis], "as_of": None, "rows": []}
    scan = pd.read_csv(scans[-1])
    cols = ["symbol", "price", "return_20d", "return_60d", "relative_strength_20d", "rsi_14",
            "trend", "momentum_score", "volume_average_20", "distance_52w_high"]
    df = group[["symbol", "company_name"]].merge(scan[[c for c in cols if c in scan.columns]], on="symbol")
    df["traded_value_cr"] = df["price"] * df["volume_average_20"] / CRORE
    df = df.sort_values("traded_value_cr", ascending=False)
    top = df.head(limit)
    if symbol not in set(top["symbol"]):
        top = pd.concat([top.head(limit - 1), df[df["symbol"] == symbol]])
    rows = [{k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in r.items()}
            for r in top.drop(columns=["volume_average_20"]).to_dict("records")]
    for r in rows:
        r["is_self"] = r["symbol"] == symbol
    return {"basis": basis, "group": me[basis], "peer_count": int(len(df)),
            "as_of": datetime.fromtimestamp(scans[-1].stat().st_mtime).isoformat(timespec="minutes"), "rows": rows}


# ---------------------------------------------------------------- highlights

def build_highlights(ratios: Optional[dict], analysis: Optional[dict], holders: Optional[dict],
                     next_results: Optional[str], peers: Optional[dict], today: Optional[date] = None) -> list[dict]:
    """Plain statements read off the numbers above. tone: positive | negative | neutral. Not advice."""
    out: list[dict] = []
    r, a, today = ratios or {}, analysis or {}, today or date.today()

    def add(tone, text):
        out.append({"tone": tone, "text": text})

    g = r.get("revenue_growth")
    if g is not None and (g >= 15 or g < 0):
        add("positive" if g >= 15 else "negative", f"Revenue {'up' if g >= 0 else 'down'} {abs(g):.1f}% year on year")
    e = r.get("earnings_growth")
    if e is not None and (e >= 15 or e < 0):
        add("positive" if e >= 15 else "negative", f"Earnings {'up' if e >= 0 else 'down'} {abs(e):.1f}% year on year")
    roe = r.get("roe")
    if roe is not None and (roe >= 15 or roe < 10):
        add("positive" if roe >= 15 else "negative", f"Return on equity {roe:.1f}% ({'strong' if roe >= 15 else 'below 10%'})")
    de = r.get("debt_to_equity_x")
    if de is not None and (de < 0.3 or de > 1):
        add("positive" if de < 0.3 else "negative", f"Debt to equity {de:.2f}x ({'low' if de < 0.3 else 'above 1x'})")
    peg = r.get("peg")
    if peg is not None and peg > 0 and (peg < 1 or peg > 2):
        add("positive" if peg < 1 else "negative", f"PEG {peg:.2f} ({'below 1' if peg < 1 else 'above 2'})")

    dh = _num(a.get("distance_from_52w_high"))
    if dh is not None:
        if dh >= -5:
            add("neutral", f"Within {abs(dh):.1f}% of its 52-week high")
        elif dh <= -30:
            add("negative", f"{abs(dh):.1f}% below its 52-week high")
    rs = _num(a.get("relative_strength_20d"))
    if rs is not None and abs(rs) >= 3:
        add("positive" if rs > 0 else "negative", f"{'Outperformed' if rs > 0 else 'Underperformed'} NIFTY by {abs(rs):.1f} pts over 20 days")

    rows = (peers or {}).get("rows") or []
    ranked = sorted((p for p in rows if _num(p.get("return_20d")) is not None), key=lambda p: -p["return_20d"])
    pos = next((i for i, p in enumerate(ranked) if p.get("is_self")), None)
    if pos is not None and len(ranked) >= 3:
        add("positive" if pos == 0 else "negative" if pos == len(ranked) - 1 else "neutral",
            f"Ranked {pos + 1} of {len(ranked)} listed peers by 20-day return")

    inst = (holders or {}).get("institutions_pct")
    if inst is not None:
        add("neutral", f"Institutions hold {inst:.1f}% of shares")

    if next_results:
        try:
            days = (date.fromisoformat(next_results[:10]) - today).days
            if 0 <= days <= 14:
                add("negative", f"Results due in {days} day{'s' if days != 1 else ''}: expect event volatility")
        except ValueError:
            pass
    return out


# ---------------------------------------------------------------- assembly

def build_stock_profile(symbol: str, analysis: Optional[dict] = None) -> dict:
    symbol = nse_feed.normalize_symbol(symbol)
    raw = nse_feed.call_tools({
        "profile": ("get_company_profile", {"symbol": symbol}),
        "ratios": ("get_key_ratios", {"symbol": symbol}),
        "income": ("get_income_statement", {"symbol": symbol, "quarterly": True}),
        "news": ("get_stock_news", {"symbol": symbol, "limit": 15}),
        "actions": ("get_corporate_actions", {"symbol": symbol}),
        "shareholding": ("get_shareholding_pattern", {"symbol": symbol}),
        "board": ("get_board_meetings", {"symbol": symbol}),
    })
    errors: dict = {}

    def section(key, parse):
        v = raw.get(key)
        err = _error_of(v)
        if err:
            errors[key] = err
            return None
        try:
            return parse(v)
        except Exception as exc:
            errors[key] = f"Could not parse: {exc}"
            return None

    yahoo = yahoo_sections(symbol)
    errors.update(yahoo["errors"])
    try:
        peers = local_peers(symbol)
        if peers is None:
            errors["peers"] = "Symbol not in NSE classification cache"
    except Exception as exc:
        peers, errors["peers"] = None, f"Peer lookup failed: {exc}"

    profile_price = raw.get("profile").get("price") if isinstance(raw.get("profile"), dict) else None
    ratios = section("ratios", lambda r: parse_ratios(r, profile_price))
    if analysis is None:
        # latest scanner row for this symbol; scanner distance is % below the high (positive)
        me = next((r for r in (peers or {}).get("rows", []) if r.get("is_self")), {})
        dist = _num(me.get("distance_52w_high"))
        analysis = {"distance_from_52w_high": -dist if dist is not None else None,
                    "relative_strength_20d": me.get("relative_strength_20d")}
    cal = yahoo["calendar"]
    upcoming = sorted(d for d in (cal or {}).get("earnings_dates", []) if d >= date.today().isoformat())
    nse_holding = section("shareholding", parse_nse_shareholding)
    board = section("board", parse_board_meetings) or []

    return {
        "symbol": symbol,
        "profile": section("profile", parse_profile),
        "ratios": ratios,
        "quarters": section("income", parse_quarters),
        "results": {
            "next_date": upcoming[0] if upcoming else None,
            "eps_estimate": (cal or {}).get("eps_estimate"),
            "revenue_estimate_cr": (cal or {}).get("revenue_estimate_cr"),
            "ex_dividend_date": (cal or {}).get("ex_dividend_date"),
            "board_meetings": board,
            "source": "Yahoo Finance calendar; NSE board meetings when available",
        } if cal or board else None,
        "ownership": {
            "nse": nse_holding if nse_holding and any(v is not None for v in nse_holding.values()) else None,
            "yahoo": yahoo["holders"],
        } if nse_holding or yahoo["holders"] else None,
        "peers": peers,
        "news": section("news", parse_news),
        "corporate_actions": section("actions", parse_actions),
        "highlights": build_highlights(ratios, analysis, yahoo["holders"], upcoming[0] if upcoming else None, peers),
        "errors": errors,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
