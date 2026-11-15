import asyncio
import math

import pandas as pd
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from analysis.data import price_store, research_engine, stock_profile, symbol_master
from web.api import ttl_cache
from market_lab import view_model as vm
from analysis.data.market_universe import get_price_history, resolve_symbol
from analysis.data.technical_engine import analyze_stock, calculate_indicators
from web.api.routes.quant import stock_quant

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


def _chart(history: pd.DataFrame) -> dict:
    """OHLC + indicator series from the daily history; empty chart if indicators cannot be built."""
    empty = {"candles": [], "ema20": [], "ema50": [], "ema200": [], "rsi": [], "macd": []}
    try:
        df = calculate_indicators(history)
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


def _quant(symbol: str, history: pd.DataFrame) -> dict:
    try:
        return stock_quant(symbol, history)
    except Exception as e:  # analytics must never take the sheet down
        failed = {"status": "NOT_AVAILABLE", "reason": f"Quant engine failed: {e}"}
        return {"risk": failed, "scorecard": failed}


STORE_SESSIONS = 750      # about three years: enough for a fully seeded 200-day average on the chart
RISK_SESSIONS = 253       # one year of returns for the risk profile
# the store holds every session since 2021, so a shorter stored history is the stock's whole life since listing:
# the feed cannot offer more. Below this there is too little for any engine.
STORE_MIN_SESSIONS = 20
STORE_MAX_LAG_DAYS = 7    # a symbol whose last stored bar is older than this has stopped trading or the store is stale


def _history(symbol: str):
    """(daily history, store rows or None). The local price store first: instant, corporate-action adjusted,
    with delivery. One download from the feed only when the store cannot serve the symbol."""
    try:
        stored = price_store.history(symbol, sessions=STORE_SESSIONS)
        last = price_store.version()[0]
        if len(stored) >= STORE_MIN_SESSIONS and last and (pd.Timestamp(last) - stored.index[-1]).days <= STORE_MAX_LAG_DAYS:
            return stored[["Open", "High", "Low", "Close", "Volume"]], stored
    except Exception:
        pass  # a broken or locked store must not take the sheet down; fall through to the feed
    return get_price_history(symbol, period="1y", interval="1d"), None


def _actions(symbol: str) -> list:
    try:
        return price_store.corporate_actions(symbol)
    except Exception:
        return []


def _build(symbol: str) -> dict:
    security = resolve_symbol(symbol)
    if security is None:
        raise ValueError(f"Stock not found in NSE master: {symbol}")
    history, stored = _history(security["symbol"])
    a = analyze_stock(security["symbol"], data=history)
    return {
        "info": {"name": a.get("company_name"), "symbol": a["symbol"], "sector": None,
                 "price": a["price"], "change": a.get("return_1d")},
        "chart": _chart(history),
        "quant": _quant(a["symbol"], history.tail(RISK_SESSIONS)),
        "history_source": "NSE bhavcopy (local price store)" if stored is not None else "Feed download, 1 year",
        "delivery": research_engine.delivery_profile(stored),
        "corporate_actions": [] if stored is None else _actions(a["symbol"]),
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


# history + indicators take ~15 s per symbol; a session-length cache makes revisits instant
_STOCK_TTL = 900
_stock_cache: dict[str, tuple[float, dict]] = {}


def _bad_symbol(key: str) -> bool:
    return not key.replace("-", "").replace("&", "").isalnum() or len(key) > 20


@router.get("/stock/{symbol}")
async def stock(symbol: str):
    key = symbol.strip().upper()
    if _bad_symbol(key):
        return JSONResponse({"error": f"Invalid symbol: {symbol}"}, status_code=400)
    if hit := ttl_cache.get(_stock_cache, key, _STOCK_TTL):
        return hit
    try:
        data = _jsonable(await asyncio.to_thread(_build, key))
        ttl_cache.put(_stock_cache, key, data, _STOCK_TTL)
        return data
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
    if _bad_symbol(key):
        return JSONResponse({"error": f"Invalid symbol: {symbol}"}, status_code=400)
    if hit := ttl_cache.get(_profile_cache, key, _PROFILE_TTL):
        return hit
    try:
        data = _jsonable(await asyncio.to_thread(stock_profile.build_stock_profile, key))
    except Exception as e:
        return JSONResponse({"error": f"Profile failed: {e}"}, status_code=502)
    data["guardrails"] = vm.guardrails({})
    ttl_cache.put(_profile_cache, key, data, _PROFILE_TTL)
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
