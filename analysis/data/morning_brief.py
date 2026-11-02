"""
Pre-market morning brief for the web Overview page.

Live (one Indian Market MCP session + Yahoo): NSE session status with the
latest NIFTY print, the NSE pre-open snapshot (served by the MCP's
`get_bulk_deals` tool), FII/DII cash activity, previous-session movers,
market news, commodities, INR rates and overnight global indices.
Cached (no network): the saved Market Lab report (regime, VIX, risk range,
events, flows) and the latest scanner CSV for "stocks in focus".

Every section is independent: a failed source gives None plus a reason in
`errors`. Stocks in focus are screens of measured data, not predictions or
buy/sell signals.
"""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from analysis.data import nse_feed
from analysis.data.stock_profile import CLASSIFICATION_FILE, SCANNER_DIR, _error_of, _num, parse_news

JUNK_NEWS = re.compile(r"live updates|top (gainers|losers) today|stock market today live|share price - live|stock price & chart", re.I)
IST = timezone(timedelta(hours=5, minutes=30))
CRORE = 1e7

GLOBAL_INDICES = [
    ("^GSPC", "S&P 500", "US"), ("^IXIC", "Nasdaq", "US"), ("^DJI", "Dow Jones", "US"),
    ("^FTSE", "FTSE 100", "Europe"), ("^N225", "Nikkei 225", "Asia"), ("^HSI", "Hang Seng", "Asia"),
]
COMMODITIES = {"CRUDE_OIL": "Crude oil", "GOLD": "Gold", "SILVER": "Silver", "NATURAL_GAS": "Natural gas", "COPPER": "Copper"}


# ---------------------------------------------------------------- live parsers

def parse_session(status: dict) -> dict:
    row = next((m for m in status.get("marketState", []) if m.get("market") == "Capital Market"), None)
    if not row:
        raise ValueError("no Capital Market row")
    return {
        "status": row.get("marketStatus"),
        "message": row.get("marketStatusMessage"),
        "trade_date": row.get("tradeDate"),
        "nifty_last": _num(row.get("last")),
        "nifty_change": _num(row.get("variation")),
        "nifty_change_pct": _num(row.get("percentChange")),
    }


def _ist_date(stamp: str) -> Optional[str]:
    try:
        return datetime.strptime(stamp[:11], "%d-%b-%Y").date().isoformat()
    except (TypeError, ValueError):
        return None


def parse_preopen(d: dict, now: Optional[datetime] = None, n: int = 8, min_turnover_cr: float = 1.0) -> dict:
    """NSE pre-open snapshot: breadth plus top movers among stocks with real pre-open turnover."""
    rows = []
    for x in d.get("data", []):
        m = x.get("metadata", {}) if isinstance(x, dict) else {}
        t = _num(m.get("totalTurnover"))
        if m.get("symbol") and _num(m.get("pChange")) is not None and t is not None:
            rows.append({"symbol": m["symbol"], "iep": _num(m.get("iep")) or _num(m.get("lastPrice")),
                         "change_pct": _num(m.get("pChange")), "prev_close": _num(m.get("previousClose")),
                         "turnover_cr": t / CRORE})
    liquid = [r for r in rows if r["turnover_cr"] >= min_turnover_cr]
    stamp = d.get("timestamp")
    today = (now or datetime.now(IST)).astimezone(IST).date().isoformat()
    return {
        "timestamp": stamp,
        "is_today": _ist_date(stamp or "") == today,
        "advances": _num(d.get("advances")), "declines": _num(d.get("declines")), "unchanged": _num(d.get("unchanged")),
        "gainers": sorted(liquid, key=lambda r: -r["change_pct"])[:n],
        "losers": sorted(liquid, key=lambda r: r["change_pct"])[:n],
        "most_active": sorted(rows, key=lambda r: -r["turnover_cr"])[:n],
        "min_turnover_cr": min_turnover_cr,
    }


def parse_fii_dii(d: Any) -> list[dict]:
    rows = d.get("data", d) if isinstance(d, dict) else d
    out = []
    for r in rows if isinstance(rows, list) else []:
        num = lambda k: _num(str(r.get(k, "")).replace(",", ""))  # noqa: E731
        if isinstance(r, dict) and r.get("category"):
            out.append({"category": str(r["category"]).replace("*", "").strip(), "date": r.get("date"),
                        "buy_cr": num("buyValue"), "sell_cr": num("sellValue"), "net_cr": num("netValue")})
    if not out:
        raise ValueError("no FII/DII rows")
    return out


def parse_movers(rows: list, n: int = 8) -> list[dict]:
    return [{"symbol": r.get("symbol"), "ltp": _num(r.get("ltp")), "change_pct": _num(r.get("perChange")),
             "turnover": r.get("turnover")} for r in rows if isinstance(r, dict) and r.get("symbol")][:n]


def parse_commodities(rows: list) -> list[dict]:
    by = {r.get("commodity"): r for r in rows if isinstance(r, dict)}
    return [{"name": label, "price": _num(by[k].get("price")), "change_pct": _num(by[k].get("change_percent")),
             "currency": by[k].get("currency")} for k, label in COMMODITIES.items() if k in by]


def parse_fx(rows: list) -> list[dict]:
    return [{"pair": r.get("pair"), "rate": _num(r.get("rate")), "change_pct": _num(r.get("change_percent"))}
            for r in rows if isinstance(r, dict) and r.get("pair")]


def global_indices() -> list[dict]:
    """Last close vs previous close per index; markets not yet open today keep yesterday's close."""
    import yfinance as yf
    closes = yf.download([t for t, _, _ in GLOBAL_INDICES], period="7d", progress=False, auto_adjust=False)["Close"]
    out = []
    for t, name, region in GLOBAL_INDICES:
        s = closes[t].dropna() if t in closes else pd.Series(dtype=float)
        if len(s) < 2:
            continue
        last, prev = float(s.iloc[-1]), float(s.iloc[-2])
        out.append({"name": name, "region": region, "last": last, "change_pct": (last - prev) / prev * 100,
                    "date": str(s.index[-1])[:10]})
    if not out:
        raise ValueError("Yahoo returned no index closes")
    return out


def fresh_news(items: list[dict], now: Optional[datetime] = None, max_days: int = 7, n: int = 15) -> list[dict]:
    """Newest first; Google News mixes in months-old pages, so drop undated and stale items."""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(days=max_days)).isoformat()
    return sorted((i for i in items if i.get("published") and i["published"] >= cutoff),
                  key=lambda i: i["published"], reverse=True)[:n]


# ---------------------------------------------------------------- cached screens

def stocks_in_focus(scanner_dir: Path = SCANNER_DIR, classification_file: Path = CLASSIFICATION_FILE,
                    n: int = 8, min_value_cr: float = 5.0) -> Optional[dict]:
    """Screens over the latest scan, liquid names only (20D avg traded value >= min_value_cr)."""
    scans = sorted(scanner_dir.glob("market_scan_*.csv"), key=lambda p: p.stat().st_mtime)
    if not scans:
        return None
    df = pd.read_csv(scans[-1])
    df["value_cr"] = df["price"] * df["volume_average_20"] / CRORE
    df = df[df["value_cr"] >= min_value_cr]
    if classification_file.exists():
        cls = pd.read_csv(classification_file, usecols=["symbol", "company_name", "sector"])
        df = df.merge(cls, on="symbol", how="left")

    cols = [c for c in ("symbol", "company_name", "sector", "price", "return_1d", "return_20d", "rsi_14",
                        "relative_volume", "distance_52w_high", "trend", "score") if c in df.columns]

    def rows(frame):
        return [{k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in r.items()}
                for r in frame[cols].head(n).to_dict("records")]

    near_high = df[df["near_52w_high"].astype(str).str.lower() == "true"] if "near_52w_high" in df else df.iloc[0:0]
    return {
        "as_of": datetime.fromtimestamp(scans[-1].stat().st_mtime).isoformat(timespec="minutes"),
        "universe": int(len(df)),
        "screens": [
            {"key": "breakouts", "title": "Near 52-week high on volume",
             "rule": "Within reach of the 52-week high, relative volume 1.5x or more",
             "rows": rows(near_high[near_high["relative_volume"] >= 1.5].sort_values("relative_volume", ascending=False))},
            {"key": "momentum", "title": "Strongest momentum",
             "rule": "Highest scanner score among stocks in an uptrend",
             "rows": rows(df[df["trend"].astype(str).str.contains("UPTREND")].sort_values("score", ascending=False))},
            {"key": "volume", "title": "Unusual volume",
             "rule": "Highest volume versus the 20-day average",
             "rows": rows(df.sort_values("relative_volume", ascending=False))},
            {"key": "oversold", "title": "Oversold",
             "rule": "RSI (14) below 30, lowest first",
             "rows": rows(df[df["rsi_14"] < 30].sort_values("rsi_14"))},
        ],
    }


# ---------------------------------------------------------------- morning call

def build_morning_call(report: Optional[dict], session: Optional[dict], preopen: Optional[dict],
                       indices: Optional[list], commodities: Optional[list], fx: Optional[list],
                       fii_dii: Optional[list], now: Optional[datetime] = None) -> list[dict]:
    """Plain sentences read off the data. tone: positive | negative | neutral. Never a buy/sell call."""
    out: list[dict] = []
    r = report or {}
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    def add(tone, topic, text):
        out.append({"tone": tone, "topic": topic, "text": text})

    def sign(v):
        return "positive" if v > 0 else "negative" if v < 0 else "neutral"

    if session and session.get("nifty_change_pct") is not None:
        p = session["nifty_change_pct"]
        add(sign(p), "NIFTY", f"NIFTY last at {session['nifty_last']:,.2f} ({p:+.2f}%), session {str(session.get('status', '')).lower()} ({session.get('trade_date')})")

    us = [i for i in indices or [] if i["region"] == "US"]
    asia = [i for i in indices or [] if i["region"] == "Asia"]
    for group, label in ((us, "US markets"), (asia, "Asian markets")):
        if group:
            ch = [i["change_pct"] for i in group]
            word, tone = ("higher", "positive") if min(ch) > 0 else ("lower", "negative") if max(ch) < 0 else ("mixed", "neutral")
            detail = ", ".join(f"{i['name']} {i['change_pct']:+.1f}%" for i in group)
            add(tone, "Global", f"{label} {word} ({detail}, last close {group[0]['date']})")

    crude = next((c for c in commodities or [] if c["name"] == "Crude oil" and c["change_pct"] is not None), None)
    if crude and abs(crude["change_pct"]) >= 1:
        # costlier crude is a headwind for India (net importer)
        add("negative" if crude["change_pct"] > 0 else "positive", "Crude",
            f"Crude oil {crude['change_pct']:+.1f}% at ${crude['price']:,.2f}")
    usd = next((f for f in fx or [] if f["pair"] == "USDINR" and f["change_pct"] is not None), None)
    if usd:
        add("negative" if usd["change_pct"] > 0.1 else "positive" if usd["change_pct"] < -0.1 else "neutral", "Rupee",
            f"USD/INR {usd['rate']:.2f} ({usd['change_pct']:+.2f}%, rupee {'weaker' if usd['change_pct'] > 0.1 else 'firmer' if usd['change_pct'] < -0.1 else 'steady'})")

    if preopen and preopen.get("is_today") and preopen.get("advances") is not None and preopen.get("declines"):
        a, d = preopen["advances"], preopen["declines"]
        add("positive" if a > d * 1.2 else "negative" if d > a * 1.2 else "neutral", "Pre-open",
            f"Pre-open breadth {a:.0f} up / {d:.0f} down (snapshot {preopen['timestamp']})")

    if fii_dii:
        for row in fii_dii:
            if row["net_cr"] is not None:
                add(sign(row["net_cr"]), "Flows", f"{row['category']} net {'bought' if row['net_cr'] > 0 else 'sold'} ₹{abs(row['net_cr']):,.0f} Cr ({row.get('date')})")
    else:
        flow = r.get("institutional_flow") or {}
        if flow.get("flow_regime"):
            add("neutral", "Flows", f"Institutional flow regime: {str(flow['flow_regime']).replace('_', ' ').lower()} (saved report)")

    regime = r.get("market_regime")
    if regime:
        add("positive" if "BULL" in regime else "negative" if "BEAR" in regime else "neutral", "Trend",
            f"Market regime {regime.replace('_', ' ').lower()} (saved report)")
    vix = ((r.get("volatility") or {}).get("india_vix") or {})
    if vix.get("value") is not None:
        add("negative" if "RIS" in str(vix.get("direction")) else "neutral", "Volatility",
            f"India VIX {vix['value']:.2f}, {str(vix.get('direction', 'N/A')).lower()}, {vix.get('regime', 'N/A')} regime")
    nifty_risk = ((r.get("risk_context") or {}).get("instruments") or {}).get("nifty") or {}
    if nifty_risk.get("expected_daily_range") is not None:
        add("neutral", "Range", f"Typical NIFTY day: about ±{nifty_risk['expected_daily_range']:,.0f} pts ({nifty_risk.get('expected_daily_move_percent', 0):.2f}%), from ATR")

    for e in (r.get("event_risk_context") or {}).get("upcoming_events") or []:
        try:
            hours = (datetime.fromisoformat(e["datetime_utc"]) - now).total_seconds() / 3600
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= hours <= 48:
            add("negative" if e.get("risk_level") in ("HIGH", "MEDIUM") else "neutral", "Event",
                f"{e.get('name')} in {hours:.0f}h ({str(e.get('risk_level', 'N/A')).lower()} risk)")
    return out


# ---------------------------------------------------------------- assembly

def build_morning_brief(report: Optional[dict] = None) -> dict:
    raw = nse_feed.call_tools({
        "status": ("get_market_status", {}),
        "preopen": ("get_bulk_deals", {}),  # MCP serves NSE's pre-open snapshot under this name
        "fii_dii": ("get_fii_dii_data", {}),
        "gainers": ("get_top_gainers", {}),
        "losers": ("get_top_losers", {}),
        "news": ("get_market_news", {"limit": 40}),
        "nifty_news": ("get_stock_news", {"symbol": "NIFTY", "limit": 30}),
        "commodities": ("get_all_commodity_prices", {}),
        "fx": ("get_all_currency_rates", {}),
    })
    errors: dict = {}

    def section(key, parse, value=None):
        v = raw.get(key) if value is None else value
        err = _error_of(v)
        if err:
            errors[key] = err
            return None
        try:
            return parse(v)
        except Exception as exc:
            errors[key] = f"Could not parse: {exc}"
            return None

    session = section("status", parse_session)
    # Google News also returns site landing pages ("... Live Updates"); they carry no news
    merged = [n for k in ("news", "nifty_news") if isinstance(raw.get(k), list) for n in raw[k]]
    seen: set = set()
    raw["news"] = [n for n in merged if not JUNK_NEWS.search(str(n.get("title", "")))
                   and not (str(n.get("title", "")).lower() in seen or seen.add(str(n.get("title", "")).lower()))] or raw.get("news")
    preopen = section("preopen", parse_preopen)
    fii = section("fii_dii", parse_fii_dii)
    commodities = section("commodities", parse_commodities)
    fx = section("fx", parse_fx)
    try:
        indices = global_indices()
    except Exception as exc:
        indices, errors["global"] = None, f"Global indices failed: {exc}"
    try:
        focus = stocks_in_focus()
        if focus is None:
            errors["focus"] = "No scanner cache yet: run a full refresh"
    except Exception as exc:
        focus, errors["focus"] = None, f"Screens failed: {exc}"

    nr = (((report or {}).get("risk_context") or {}).get("instruments") or {}).get("nifty") or {}
    base = (session or {}).get("nifty_last") or _num(nr.get("price"))
    pts = _num(nr.get("expected_daily_range"))
    day_range = {"base": base, "points": pts, "pct": _num(nr.get("expected_daily_move_percent")),
                 "low": base - pts, "high": base + pts} if base and pts else None

    return {
        "session": session,
        "range": day_range,
        "preopen": preopen,
        "fii_dii": fii,
        "movers": {"gainers": section("gainers", parse_movers) or [], "losers": section("losers", parse_movers) or []},
        "news": section("news", lambda v: fresh_news(parse_news(v, limit=80))),
        "global": {"indices": indices, "commodities": commodities, "fx": fx},
        "focus": focus,
        "morning_call": build_morning_call(report, session, preopen, indices, commodities, fx, fii),
        "errors": errors,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
