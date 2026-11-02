import asyncio
import math

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import JSONResponse

import time

from analysis.data import stock_profile, symbol_master
from market_lab import view_model as vm
from analysis.data.nse_feed import get_stock_history_dataframe
from analysis.data.technical_engine import analyze_stock, calculate_indicators

router = APIRouter()


def _num(v):
    return None if v is None or pd.isna(v) else float(v)


def _jsonable(v):
    """numpy scalars -> python; NaN/inf -> None (Starlette JSON rejects NaN)."""
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        v = v.item()
    if isinstance(v, float) and not math.isfinite(v):
        return None
    return v


def _chart(symbol: str) -> dict:
    """OHLC + indicator series from NSE history; empty chart if history unavailable."""
    empty = {"candles": [], "ema20": [], "ema50": [], "ema200": [], "rsi": [], "macd": []}
    try:
        df = calculate_indicators(get_stock_history_dataframe(symbol))
    except Exception:
        return empty

    def series(col):
        return [{"time": str(t)[:10], "value": _num(v)} for t, v in df[col].items() if _num(v) is not None]

    return {
        "candles": [
            {"time": str(t)[:10], "open": _num(r["Open"]), "high": _num(r["High"]),
             "low": _num(r["Low"]), "close": _num(r["Close"]), "volume": _num(r["Volume"])}
            for t, r in df.iterrows()
        ],
        "ema20": series("EMA_20"), "ema50": series("EMA_50"), "ema200": series("EMA_200"),
        "rsi": series("RSI_14"),
        "macd": [{"time": str(t)[:10], "macd": _num(r["MACD"]), "signal": _num(r["MACD_SIGNAL"]),
                  "histogram": _num(r["MACD_HISTOGRAM"])} for t, r in df.iterrows()],
    }


def _build(symbol: str) -> dict:
    a = analyze_stock(symbol)  # raises ValueError for unknown symbol
    return {
        "info": {"name": a.get("company_name"), "symbol": a["symbol"], "sector": None,
                 "price": a["price"], "change": a.get("return_1d")},
        "chart": _chart(a["symbol"]),
        "score": {"overall": a.get("momentum_score"), "components": []},
        # No S/R engine in analyze_stock; 52w extremes are the only sourced levels.
        "levels": {"support": [a["low_52w"]] if a.get("low_52w") else [],
                   "resistance": [a["high_52w"]] if a.get("high_52w") else []},
        "volatility": {"atr": a.get("atr_14"), "adx": None},
        "research_factors": [],
        "risk": {"position_size": None, "stop_loss": None},
        "analysis": a,
        "guardrails": vm.guardrails({}),
    }


@router.get("/stock/{symbol}")
async def stock(symbol: str):
    try:
        return _jsonable(await asyncio.to_thread(_build, symbol))
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": f"Analysis failed: {e}"}, status_code=502)


# profile pulls news/fundamentals over the network; keep each symbol for 15 min
_PROFILE_TTL = 900
_profile_cache: dict[str, tuple[float, dict]] = {}


@router.get("/stock/{symbol}/profile")
async def stock_profile_route(symbol: str):
    key = symbol.strip().upper()
    if not key.replace("-", "").replace("&", "").isalnum() or len(key) > 20:
        return JSONResponse({"error": f"Invalid symbol: {symbol}"}, status_code=400)
    hit = _profile_cache.get(key)
    if hit and time.monotonic() - hit[0] < _PROFILE_TTL:
        return hit[1]
    try:
        data = _jsonable(await asyncio.to_thread(stock_profile.build_stock_profile, key))
    except Exception as e:
        return JSONResponse({"error": f"Profile failed: {e}"}, status_code=502)
    data["guardrails"] = vm.guardrails({})
    _profile_cache[key] = (time.monotonic(), data)
    return data


@router.get("/symbols")
def symbols():
    """Cache-only: never downloads the NSE master on GET."""
    try:
        if not symbol_master.MASTER_FILE.exists():
            return []
        df = symbol_master.load_master(auto_update=False)
        name_col = next((c for c in ("company_name", "name") if c in df.columns), None)
        if "symbol" not in df.columns:
            return []
        return [{"symbol": r["symbol"], "name": r[name_col] if name_col else ""}
                for _, r in df.iterrows()]
    except Exception:
        return []
