"""
Nova per-stock analysis adapter (read-only, analysis-only).

Builds a stock-specific dataset for the Stock Analysis terminal by reusing
Nova's EXISTING services:

- symbol resolution  -> analysis.data.symbol_master (search_symbols/get_security)
- per-stock metrics   -> analysis.data.technical_engine.analyze_stock
                         (price, RSI, MACD, ATR, EMAs/SMAs, returns, 52w range,
                          trend, structure, momentum score)
- per-stock history   -> analysis.data.market_universe.get_price_history
                         (cache-first: Dhan -> NSE MCP -> Yahoo)
- moving averages     -> technical_engine.calculate_sma (real, no new math)

It NEVER computes fundamentals, stock-level institutional holdings, stock
options, VaR/beta/drawdown or price targets — those are absent from Nova's
engines and are surfaced as honest UNAVAILABLE states (never fabricated).
Market-wide context (regime, FII/DII, VIX) is secondary only.

Keep heavy calls (analyze_stock, get_price_history, Ollama) off the UI thread.
"""

from __future__ import annotations

from typing import Any

from market_lab import view_model as vm

N_A = vm.N_A


def resolve_symbol(query: str):
    """Resolve a user query to one NSE security, or None if not found."""
    q = str(query or "").strip().upper()
    if not q:
        return None
    try:
        from analysis.data.symbol_master import search_symbols

        frame = search_symbols(q, limit=1)
        if frame is None or frame.empty:
            return None
        row = frame.iloc[0]
        symbol = str(row.get("symbol", "")).strip().upper()
        if not symbol:
            return None
        name = row.get("company_name") or row.get("name") or ""
        return {"symbol": symbol, "company_name": str(name), "exchange": "NSE"}
    except Exception:
        return None


def stock_metrics(symbol: str):
    """Full per-stock technical metrics from the existing engine (or None)."""
    try:
        from analysis.data.technical_engine import analyze_stock

        result = analyze_stock(str(symbol).strip().upper())
        return result if isinstance(result, dict) else None
    except Exception:
        return None


def stock_candles(symbol: str, period: str = "6mo", limit: int = 130):
    """Real daily OHLC candles (+ MA overlays) for a stock, or []."""
    try:
        from analysis.data.market_universe import get_price_history
        from analysis.data.technical_engine import calculate_sma
        import pandas as pd

        frame = get_price_history(str(symbol).strip().upper(),
                                   period=period, interval="1d")
        if frame is None or getattr(frame, "empty", True):
            return []
        rows = []
        closes = []
        close_col = None
        for name in ("Close", "close"):
            if name in getattr(frame, "columns", []):
                close_col = name
                break
        if close_col is None:
            return []
        for idx, r in frame.tail(limit).iterrows():
            def num(col):
                try:
                    return float(r[col]) if r[col] is not None else None
                except (TypeError, ValueError, KeyError):
                    return None
            o, h, l, c = num("Open"), num("High"), num("Low"), num(close_col)
            if None in (o, h, l, c):
                continue
            try:
                v = float(r["Volume"]) if r["Volume"] is not None else None
            except (TypeError, ValueError, KeyError):
                v = None
            rows.append({"t": str(idx)[:10], "o": o, "h": h, "l": l,
                         "c": c, "v": v})
            closes.append(c)
        if not rows:
            return []
        # Real SMA overlays (only where enough history exists).
        close_series = pd.Series(closes)
        for period_days, color in ((20, "ma20"), (50, "ma50"), (200, "ma200")):
            if len(closes) >= period_days:
                ma = calculate_sma(close_series, period_days).tolist()
                for i, value in enumerate(ma):
                    if value is not None and value == value:
                        rows[i][color] = float(value)
        return rows
    except Exception:
        return []


def stock_oscillators(candles, limit=130):
    """Real RSI/MACD series computed from the same candles via technical_engine
    (no new math). Returns {"rsi":[...], "macd":[...], "signal":[...],
    "hist":[...]} aligned to candles; empty lists on any failure."""
    try:
        import pandas as pd
        from analysis.data.technical_engine import calculate_macd, calculate_rsi

        closes = [float(c["c"]) for c in (candles or [])[:limit]
                  if isinstance(c, dict) and c.get("c") is not None]
        if len(closes) < 20:
            return {"rsi": [], "macd": [], "signal": [], "hist": []}
        series = pd.Series(closes)
        rsi = calculate_rsi(series, 14).tolist()
        macd, signal, hist = calculate_macd(series)
        return {
            "rsi": rsi,
            "macd": macd.tolist(),
            "signal": signal.tolist(),
            "hist": hist.tolist(),
        }
    except Exception:
        return {"rsi": [], "macd": [], "signal": [], "hist": []}


def kpi_tiles(metrics: dict):
    """Compact stock KPI values from the metrics (or honest N/A)."""
    if not isinstance(metrics, dict):
        return {}
    return {
        "trend": metrics.get("trend", N_A),
        "momentum_score": metrics.get("momentum_score", N_A),
        "rsi": metrics.get("rsi_14", N_A),
        "rsi_condition": metrics.get("rsi_condition", N_A),
        "macd": metrics.get("macd", N_A),
        "macd_signal": metrics.get("macd_signal", N_A),
        "macd_condition": metrics.get("macd_condition", N_A),
        "atr": metrics.get("atr_14", N_A),
        "volume": metrics.get("volume", N_A),
        "relative_volume": metrics.get("relative_volume", N_A),
        "return_1d": metrics.get("return_1d", N_A),
        "return_20d": metrics.get("return_20d", N_A),
        "return_60d": metrics.get("return_60d", N_A),
    }


def data_quality(metrics, candles):
    """Per-component availability for the selected stock (honest states)."""
    m = metrics if isinstance(metrics, dict) else {}
    have_price = isinstance(m.get("price"), (int, float))
    rsi_ok = isinstance(m.get("rsi_14"), (int, float))
    macd_ok = isinstance(m.get("macd"), (int, float))
    return {
        "Price quote": "AVAILABLE" if have_price else "UNAVAILABLE",
        "Historical series": "AVAILABLE" if candles else "UNAVAILABLE",
        "RSI/MACD/ATR": "AVAILABLE" if (rsi_ok and macd_ok) else "PARTIAL",
        "Support/Resistance": "UNAVAILABLE",
        "Fundamentals": "UNAVAILABLE",
        "Institutional (stock-level)": "UNAVAILABLE",
        "Derivatives (stock-level)": "UNAVAILABLE",
    }


def market_context(report):
    """SECONDARY market-wide context only (clearly labeled as market-wide)."""
    macro = vm.macro(report or {})
    f = vm.flow_block(report or {})
    return {
        "market_regime": macro.get("market_regime", N_A),
        "india_vix": macro.get("india_vix", N_A),
        "fii_20d": f.get("fii_20d", N_A),
        "dii_20d": f.get("dii_20d", N_A),
    }
