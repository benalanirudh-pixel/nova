"""
Nova Market Lab presentation adapter (view-model).

Pure, offline, dependency-free (stdlib only). It translates the real saved
Market Lab report dict into small UI-friendly structures WITHOUT changing any
backend logic, and marks anything the backend does not actually provide as an
explicit ``N/A`` sentinel rather than inventing a value.

Nothing here formats numbers for pixels; that is the widgets' job. This module
only extracts and classifies what is genuinely in the report.

Field names mirror the real report (nifty_snapshot, volatility, breadth,
sector_intelligence, derivatives, institutional_flow.metrics,
event_risk_context, research_factors, risk_context, top_technical_stocks) —
see market_lab_data.py for the producer.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any

# Honest sentinel used everywhere a real value is absent. Never a number.
N_A = "N/A"

_IST = _dt.timezone(_dt.timedelta(hours=5, minutes=30))


def _num(value):
    """Coerce to float if finite, else None. Never returns a fabricated value."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _get(report, *path):
    """Safe nested dict access; returns None if any level is missing/wrong."""
    current = report
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


# ---------------------------------------------------------------------------
# Time / freshness / session
# ---------------------------------------------------------------------------

def freshness(age_seconds):
    """Scanner-age colour level. green <1h, amber 1-8h, red >8h, critical >16h."""
    age = _num(age_seconds)
    if age is None:
        return (N_A, "unknown age")
    hours = age / 3600.0
    if hours < 1:
        return ("green", "fresh")
    if hours <= 8:
        return ("amber", "aging")
    if hours <= 16:
        return ("red", "stale")
    return ("critical", "CRITICAL: SCAN DATA IS OVER 16 HOURS OLD")


def parse_iso(value):
    """Parse an ISO-8601 timestamp to an aware datetime, else None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = _dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def data_age(report, now=None):
    """Report age from its own `generated` timestamp."""
    generated = report.get("generated")
    parsed = parse_iso(generated)
    if parsed is None:
        return {"generated": generated, "age_seconds": None, "label": N_A}
    now = now or _dt.datetime.now(_dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_dt.timezone.utc)
    age = max(0.0, (now - parsed).total_seconds())
    return {"generated": generated, "age_seconds": age, "label": _age_label(age)}


def scanner_info(report, now=None, scanner_mtime=None):
    """Count + file path + age for the underlying NSE scan (from report)."""
    count = report.get("stocks_analyzed")
    if count is None:
        count = _get(report, "breadth", "total")
    path = report.get("scanner_file")
    if scanner_mtime is None and path:
        try:
            import os

            scanner_mtime = os.path.getmtime(path)
        except OSError:
            scanner_mtime = None
    age_seconds = None
    if scanner_mtime is not None:
        now = now or _dt.datetime.now(_dt.timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=_dt.timezone.utc)
        age_seconds = max(0.0, now.timestamp() - float(scanner_mtime))
    level, note = freshness(age_seconds)
    return {
        "count": count,
        "path": path,
        "age_seconds": age_seconds,
        "level": level,
        "note": note,
        "label": _age_label(age_seconds),
    }


def session_status(now=None):
    """Session label: OPEN / CLOSED / PRE-OPEN / WEEKEND, from IST wall clock."""
    now = now or _dt.datetime.now(_IST)
    if now.tzinfo is None:
        now = now.replace(tzinfo=_IST)
    else:
        now = now.astimezone(_IST)
    if now.weekday() >= 5:
        return {"label": "WEEKEND", "open": False}
    minutes = now.hour * 60 + now.minute
    if minutes < 9 * 60 + 15:
        return {"label": "PRE-OPEN" if minutes >= 8 * 60 else "CLOSED", "open": False}
    if minutes < 15 * 60 + 30:
        return {"label": "OPEN", "open": True}
    return {"label": "CLOSED", "open": False}


def _age_label(age_seconds):
    age = _num(age_seconds)
    if age is None:
        return N_A
    if age < 60:
        return f"{int(age)}s old"
    if age < 3600:
        return f"{int(age // 60)}m old"
    if age < 86400:
        return f"{age / 3600:.1f}h old"
    return f"{age / 86400:.1f}d old"


# ---------------------------------------------------------------------------
# Index cards (NIFTY / BANKNIFTY)
# ---------------------------------------------------------------------------

def index_card(report, which, r5=None):
    """Card data for 'nifty' or 'bank_nifty'. Honest N/A for missing fields.

    Absolute change and previous close are derived from price + change_percent
    (labeled DERIVED by the caller); that is arithmetic on backend values, not
    a fabricated number.
    """
    which = which.lower()
    candles = report.get("nifty_candles" if which == "nifty"
                         else "bank_nifty_candles") or []
    last = candles[-1] if candles else None
    if which == "nifty":
        name = "NIFTY 50"
        snap = report.get("nifty_snapshot") or {}
        price = _num(snap.get("price"))
        change_pct = _num(snap.get("change_percent"))
        open_ = snap.get("open")
        high = snap.get("high")
        low = snap.get("low")
        returns = report.get("nifty_returns") or {}
    else:
        name = "BANK NIFTY"
        vol = _get(report, "volatility", "bank_nifty") or {}
        price = _num(vol.get("price"))
        change_pct = _num((report.get("bank_nifty_returns") or {}).get("1D"))
        open_ = _num(last.get("o")) if last else None
        high = _num(last.get("h")) if last else None
        low = _num(last.get("l")) if last else None
        returns = report.get("bank_nifty_returns") or {}

    # Fall back to the last candle's OHLC when a live snapshot is absent.
    if last is not None:
        open_ = open_ if open_ is not None else _num(last.get("o"))
        high = high if high is not None else _num(last.get("h"))
        low = low if low is not None else _num(last.get("l"))

    change_abs = None
    prev_close = None
    if price is not None and change_pct is not None:
        prev_close = price / (1.0 + change_pct / 100.0)
        change_abs = price - prev_close

    return {
        "name": name,
        "price": price if price is not None else N_A,
        "change_percent": change_pct if change_pct is not None else N_A,
        "change_abs": change_abs,
        "prev_close": prev_close,
        "open": open_ if open_ is not None else N_A,
        "high": high if high is not None else N_A,
        "low": low if low is not None else N_A,
        "return_5d": _num(returns.get("5D")),
        "return_20d": _num(returns.get("20D")),
        "return_60d": _num(returns.get("60D")),
        "chart": N_A,
        "series": (report.get("nifty_series") if which == "nifty"
                   else report.get("bank_nifty_series")) or [],
        "candles": candles,
        "derived_abs_change": change_abs is not None,
    }


def _last(series):
    """Last non-null value of a pandas Series as float, else None."""
    try:
        cleaned = series.dropna()
        return float(cleaned.iloc[-1]) if len(cleaned) else None
    except Exception:
        return None


def _rsi_condition(value):
    """RSI interpretation using the SAME thresholds as technical_engine's
    analyze_stock (>=70 overbought, <=30 oversold, >=55 bullish, <=45 bearish).
    This is the engine's existing convention applied to a real computed value,
    not a newly invented rule."""
    if value >= 70:
        return "OVERBOUGHT"
    if value <= 30:
        return "OVERSOLD"
    if value >= 55:
        return "BULLISH"
    if value <= 45:
        return "BEARISH"
    return "NEUTRAL"


def indicator_cards(report, which="nifty"):
    """RSI/MACD/ATR/VOL for an index. ATR/VOL come from the report's volatility
    engine; RSI/MACD are computed from the index's REAL daily candles using
    technical_engine's own calculate_rsi/calculate_macd (no new math). If there
    is not enough real history, they stay honest N/A."""
    vol = _get(report, "volatility", which) or {}
    cards = {
        "RSI": {"value": N_A, "interpretation": N_A},
        "MACD": {"value": N_A, "interpretation": N_A},
        "ATR": {"value": _num(vol.get("atr14")), "unit": "pts",
                "percent": _num(vol.get("atr_percent")),
                "interpretation": vol.get("volatility_regime", N_A)},
        "VOL": {"value": _num(vol.get("realized_volatility_20d")),
                "unit": "%", "interpretation": "realized vol 20d"},
    }

    candles = report.get("nifty_candles" if which == "nifty"
                         else "bank_nifty_candles") or []
    closes = [float(c["c"]) for c in candles
              if isinstance(c, dict) and _num(c.get("c")) is not None]

    if len(closes) >= 30:
        try:
            import pandas as pd
            from analysis.data.technical_engine import calculate_macd, calculate_rsi

            series = pd.Series(closes)

            if len(closes) >= 20:
                rsi_val = _last(calculate_rsi(series, 14))
                if rsi_val is not None:
                    cards["RSI"] = {"value": rsi_val, "unit": "",
                                    "interpretation": _rsi_condition(rsi_val)}

            if len(closes) >= 45:
                macd, signal, histogram = calculate_macd(series)
                macd_val = _last(macd)
                sig_val = _last(signal)
                hist_val = _last(histogram)
                if macd_val is not None and sig_val is not None:
                    cards["MACD"] = {
                        "value": hist_val, "unit": "",
                        "macd": macd_val, "signal": sig_val,
                        "histogram": hist_val,
                        "interpretation": "BULLISH" if macd_val > sig_val else "BEARISH",
                    }
        except Exception:
            pass

    return cards


# ---------------------------------------------------------------------------
# Sector overview + Section 03
# ---------------------------------------------------------------------------

def sector_rows(report, limit=5):
    sector = report.get("sector_intelligence") or {}
    if not sector.get("available"):
        return []
    rows = []
    for item in (sector.get("top_sectors") or [])[:limit]:
        rows.append({
            "name": item.get("sector", N_A),
            "return_20d": _num(item.get("return_20d")),
            "relative_strength_20d": _num(item.get("relative_strength_20d")),
            "regime": item.get("regime", N_A),
        })
    return rows


# ---------------------------------------------------------------------------
# Factor rankings (right panel + Section 08)
# ---------------------------------------------------------------------------

# The backend's equal-weight composite factors (research_factor_engine). The
# reference asks for QUALITY/VALUE too, but the engine explicitly does NOT
# compute fundamentals, so those are declared unavailable rather than faked.
FACTOR_UNAVAILABLE = {
    "QUALITY": "Fundamental quality factors are NOT computed "
               "(no verified fundamentals source).",
    "VALUE": "Fundamental value factors are NOT computed "
             "(no verified fundamentals source).",
}


def _rank_rows(rows):
    out = []
    for item in rows or []:
        factor_z = item.get("factor_z") or {}
        out.append({
            "rank": item.get("rank", N_A),
            "symbol": item.get("symbol", N_A),
            "price": _num(item.get("price")),
            "composite_z": _num(item.get("composite_z")),
            "factor_z": factor_z,
        })
    return out


def factor_block(report):
    factors = report.get("research_factors") or {}
    available = factors.get("status") == "AVAILABLE"
    listed = list((factors.get("factors") or {}).keys())
    top = _rank_rows(factors.get("top_ranked"))
    bottom = _rank_rows(factors.get("bottom_ranked"))
    # per-factor z is populated only when at least one real factor z exists;
    # in a composite-only report every factor_z is null.
    per_factor_z_available = any(
        value is not None
        for row in top
        for value in (row["factor_z"] or {}).values()
    )
    return {
        "status": "AVAILABLE" if available else "NOT_AVAILABLE",
        "method": factors.get("method", N_A),
        "as_of": factors.get("as_of", N_A),
        "universe_size": factors.get("universe_size", N_A),
        "factors_available": listed,
        "factors_unavailable": dict(FACTOR_UNAVAILABLE),
        "per_factor_z_available": per_factor_z_available,
        "top": top,
        "bottom": bottom,
        "warnings": factors.get("warnings", []),
    }


# ---------------------------------------------------------------------------
# Section 01 — macro
# ---------------------------------------------------------------------------

def macro(report):
    vix = _get(report, "volatility", "india_vix") or {}
    nifty = report.get("nifty_snapshot") or {}
    return {
        "market_regime": report.get("market_regime", N_A),
        "nifty_price": _num(nifty.get("price")),
        "india_vix": _num(vix.get("value")),
        "vix_regime": vix.get("regime", N_A),
        "vix_change_percent": _num(vix.get("change_percent")),
        "vix_percentile_1y": _num(vix.get("percentile_1y")),
        "vix_direction": vix.get("direction", N_A),
    }


# ---------------------------------------------------------------------------
# Section 02 — breadth
# ---------------------------------------------------------------------------

def breadth_block(report):
    b = report.get("breadth") or {}
    ad_ratio = _num(b.get("advance_decline_ratio", b.get("ad_ratio")))
    if ad_ratio is None:
        advances = _num(b.get("advancing"))
        declines = _num(b.get("declining"))
        if advances is not None and declines not in (None, 0):
            ad_ratio = advances / declines
    return {
        "advancing": b.get("advancing", N_A),
        "declining": b.get("declining", N_A),
        "unchanged": b.get("unchanged", N_A),
        "ad_ratio": ad_ratio,
        "above_ema20_percent": _num(b.get("above_ema20_percent")),
        "above_ema50_percent": _num(b.get("above_ema50_percent")),
        "above_ema200_percent": _num(b.get("above_ema200_percent")),
        "strong_uptrend_percent": _num(b.get("strong_uptrend_percent")),
        "strong_downtrend_percent": _num(b.get("strong_downtrend_percent")),
        # Not computed by the scanner in the saved report:
        "new_52w_highs": N_A,
        "new_52w_lows": N_A,
        "mcclellan_summation": N_A,
    }


# ---------------------------------------------------------------------------
# Section 04 — technical analysis
# ---------------------------------------------------------------------------

def technical_block(report, limit=10):
    rows = []
    for i, item in enumerate((report.get("top_technical_stocks") or [])[:limit], 1):
        rows.append({
            "rank": i,
            "symbol": item.get("symbol", N_A),
            "technical_score": _num(item.get("technical_score")),
            "trend": item.get("trend", N_A),
        })
    return {
        "top_stocks": rows,
        # Per-stock RSI/MACD lists and index S/R are not stored in the report:
        "rsi_oversold": N_A,
        "rsi_overbought": N_A,
        "macd_crossovers": N_A,
        "support_resistance": N_A,
    }


# ---------------------------------------------------------------------------
# Section 05 — derivatives
# ---------------------------------------------------------------------------

def derivatives_block(report, which="nifty"):
    leg = _get(report, "derivatives", which) or {}
    if not leg:
        return {"available": False}
    pcr = leg.get("pcr") or {}
    max_pain = leg.get("max_pain") or {}
    walls = leg.get("oi_walls") or {}
    iv = leg.get("iv_structure") or {}
    unusual = []
    for item in (leg.get("unusual_activity") or [])[:8]:
        unusual.append(item)
    return {
        "available": True,
        "instrument": leg.get("instrument", which.upper()),
        "spot": _num((leg.get("underlying") or {}).get("spot")),
        "expiry": (leg.get("expiry") or {}).get("selected", N_A),
        "oi_pcr": _num(pcr.get("oi_pcr")),
        "volume_pcr": _num(pcr.get("volume_pcr")),
        "max_pain": _num(max_pain.get("strike")),
        "put_wall": walls.get("put_wall", N_A),
        "call_wall": walls.get("call_wall", N_A),
        "support": (leg.get("support_resistance") or {}).get("support", N_A),
        "resistance": (leg.get("support_resistance") or {}).get("resistance", N_A),
        "atm_iv": _num(iv.get("atm_iv")),
        "unusual_activity": unusual,
        "timestamp": leg.get("timestamp", N_A),
        "stock_oi_buildup_list": N_A,  # per-stock OI build list not in report
    }


# ---------------------------------------------------------------------------
# Section 06 — institutional flow
# ---------------------------------------------------------------------------

def flow_block(report):
    flow = report.get("institutional_flow") or {}
    m = flow.get("metrics") or {}
    counts = m.get("source_counts") or {}
    primary = m.get("primary_combined_sessions")
    target = m.get("target_sessions")
    return {
        "available": bool(flow.get("available")),
        "flow_regime": m.get("flow_regime", N_A),
        "fii_5d": _num(m.get("fii_5d")),
        "dii_5d": _num(m.get("dii_5d")),
        "fii_10d": _num(m.get("fii_10d")),
        "dii_10d": _num(m.get("dii_10d")),
        "fii_20d": _num(m.get("fii_20d")),
        "dii_20d": _num(m.get("dii_20d")),
        "fii_streak": [m.get("fii_streak_direction"), m.get("fii_streak_days")],
        "dii_streak": [m.get("dii_streak_direction"), m.get("dii_streak_days")],
        "primary_verified": primary,
        "target_sessions": target,
        "source_quality": flow.get("source_quality") or _compact_quality(counts),
        "signal_allowed": flow.get("signal_allowed"),
        "signal_reason": flow.get("signal_reason", ""),
        "latest_date": m.get("latest_date", N_A),
        "unit": m.get("flow_unit", "INR crore"),
    }


def _compact_quality(counts):
    if not counts:
        return N_A
    total = sum(counts.values())
    secondary = sum(v for k, v in counts.items() if k.startswith("SECONDARY"))
    if total:
        return f"{total - secondary}/{total} primary-verified"
    return N_A


# ---------------------------------------------------------------------------
# Section 07 — risk metrics
# ---------------------------------------------------------------------------

def risk_block(report):
    risk = report.get("risk_context") or {}
    nifty = _get(risk, "instruments", "nifty") or {}
    return {
        # Portfolio risk statistics are NOT computed by the risk engine
        # (it is MARKET_RISK_CONTEXT_ONLY); the computed context IS shown.
        "var_95": N_A,
        "sharpe": N_A,
        "max_drawdown_52w": N_A,
        "current_drawdown": N_A,
        "provided": {
            "atr_pct": _num(nifty.get("atr_pct")),
            "realized_volatility_20d": _num(nifty.get("realized_volatility_20d")),
            "volatility_percentile": _num(nifty.get("volatility_percentile")),
            "volatility_regime": nifty.get("volatility_regime", N_A),
            "expected_daily_move_percent": _num(
                nifty.get("expected_daily_move_percent")
            ),
        },
        "note": "Market-risk context only; no portfolio VaR/Sharpe/drawdown.",
        "execution_enabled": risk.get("execution_enabled"),
        "buy_sell_authorization": risk.get("buy_sell_authorization"),
    }


# ---------------------------------------------------------------------------
# Section 09 — earnings calendar
# ---------------------------------------------------------------------------

def earnings_block(report):
    # Nova has no earnings source; never invent dates or surprise percentages.
    return {"available": False, "events": [], "reason": "no earnings source"}


# ---------------------------------------------------------------------------
# Section 10 — guardrails + data quality
# ---------------------------------------------------------------------------

def guardrails(report):
    policy = report.get("decision_policy") or {}
    return {
        "text": "analysis-only, not a buy/sell signal, no broker/orders",
        "buy_sell_authorization": bool(policy.get("buy_sell_authorized") is True),
    }


def data_quality(report):
    return report.get("data_availability") or {}
