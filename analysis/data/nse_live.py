"""
Live NSE market data over the browser-impersonating session that
derivatives_engine already uses for the option chain (the MCP's equivalents
are often blocked or broken). Read-only; analysis only.

- market(): NIFTY / BANK NIFTY / INDIA VIX quotes, sector indices, index-summed
  advances/declines (not stock counts), new 52-week highs/lows, NSE status and GIFT Nifty.
- fii_dii(): latest FII/FPI and DII cash-market activity (₹ crore).
- movers(index): top gainers and losers for an index ("NIFTY", "BANKNIFTY", ...).

Each call raises on failure; callers decide what to show. Values are passed
through as NSE reports them, never filled in.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Optional

from analysis.data import derivatives_engine as de

BASE = "https://www.nseindia.com/api/"
HEADLINE = {"NIFTY 50": "nifty", "NIFTY BANK": "banknifty", "INDIA VIX": "vix"}

_lock = threading.Lock()
_session = None


def _num(v: Any) -> Optional[float]:
    try:
        f = float(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return None
    return f if f == f else None


def get(endpoint: str, params: Optional[dict] = None) -> Any:
    """GET an NSE API endpoint as JSON (dict or list); re-warms the session once on failure."""
    global _session
    with _lock:
        for attempt in range(2):
            try:
                if _session is None:
                    _session = de.create_nse_session()
                    de.warm_nse_session(_session)
                r = _session.get(BASE + endpoint, params=params, timeout=de.REQUEST_TIMEOUT,
                                 headers={**de.HEADERS, "Referer": "https://www.nseindia.com/"})
                r.raise_for_status()
                return json.loads(r.content)
            except Exception:
                _session = None  # cookies expire; start a fresh session
                if attempt:
                    raise


def _quote(r: dict) -> dict:
    return {
        "name": r.get("index"), "price": _num(r.get("last")), "change_abs": _num(r.get("variation")),
        "change_percent": _num(r.get("percentChange")), "open": _num(r.get("open")), "high": _num(r.get("high")),
        "low": _num(r.get("low")), "prev_close": _num(r.get("previousClose")),
        "year_high": _num(r.get("yearHigh")), "year_low": _num(r.get("yearLow")),
        "advances": _num(r.get("advances")), "declines": _num(r.get("declines")),
    }


def parse_indices(payload: dict) -> dict:
    rows = payload.get("data") or []
    out = {key: _quote(r) for r in rows for name, key in HEADLINE.items() if r.get("index") == name}
    out["sectors"] = [_quote(r) for r in rows if r.get("key") == "SECTORAL INDICES"]
    out["breadth"] = {k: _num(payload.get(k)) for k in ("advances", "declines", "unchanged")}
    out["as_of"] = payload.get("timestamp")
    return out


def parse_gift(status: dict) -> Optional[dict]:
    g = status.get("giftnifty") or {}
    price = _num(g.get("LASTPRICE"))
    return None if price is None else {"price": price, "change": _num(g.get("DAYCHANGE")),
                                       "change_pct": _num(g.get("PERCHANGE")), "expiry": g.get("EXPIRYDATE"),
                                       "as_of": g.get("TIMESTMP")}


def market() -> dict:
    out = parse_indices(get("allIndices"))
    hi, lo = get("live-analysis-data-52weekhighstock"), get("live-analysis-data-52weeklowstock")
    out["breadth"].update(new_52w_highs=_num(hi.get("high")), new_52w_lows=_num(lo.get("low")))
    status = get("marketStatus")
    cm = next((m for m in status.get("marketState", []) if m.get("market") == "Capital Market"), {})
    out["status"] = {"state": cm.get("marketStatus"), "message": cm.get("marketStatusMessage"), "trade_date": cm.get("tradeDate")}
    out["gift_nifty"] = parse_gift(status)
    return out


def parse_fii_dii(rows: Any) -> list[dict]:
    out = [{"category": str(r.get("category", "")).replace("*", "").strip(), "date": r.get("date"),
            "buy_cr": _num(r.get("buyValue")), "sell_cr": _num(r.get("sellValue")), "net_cr": _num(r.get("netValue"))}
           for r in rows if isinstance(r, dict) and r.get("category")] if isinstance(rows, list) else []
    if not out:
        raise ValueError("NSE returned no FII/DII rows")
    return out


def fii_dii() -> list[dict]:
    return parse_fii_dii(get("fiidiiTradeReact"))


def parse_movers(payload: dict, index: str, n: int = 8) -> list[dict]:
    rows = ((payload.get(index) or {}).get("data")) or []
    return [{"symbol": r.get("symbol"), "ltp": _num(r.get("ltp")), "change_pct": _num(r.get("perChange")),
             "turnover": r.get("turnover")} for r in rows if r.get("symbol")][:n]


def movers(index: str = "NIFTY", n: int = 8) -> dict:
    return {"gainers": parse_movers(get("live-analysis-variations", {"index": "gainers"}), index, n),
            "losers": parse_movers(get("live-analysis-variations", {"index": "loosers"}), index, n)}
