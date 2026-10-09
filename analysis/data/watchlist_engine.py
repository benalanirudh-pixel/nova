"""
Nova stock watchlist fetcher (analysis-only, read-only).

Refreshes one pinned symbol per call through the existing
technical engine: live quote first (NSE MCP), Yahoo history fallback,
full indicator set. Never invents values, never trades.

Intended caller: the Market Lab UI background worker on the same
60 s open / 30 s closed cadence as the live-only report poll.
One symbol per worker run keeps each poll cheap and avoids stacking.

Usage (manual single check):
    .\\venv\\Scripts\\python.exe analysis\\data\\watchlist_engine.py RELIANCE
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ENGINE_NAME = "Nova Stock Watchlist Engine"
ENGINE_VERSION = "1.0.0"

EXECUTION_ENABLED = False
BUY_SELL_AUTHORIZATION = False

# Symbols refresh one per poll round-robin; keep the default list small
# so a full rotation fits inside one poll interval.
DEFAULT_SYMBOLS = ["RELIANCE", "HDFCBANK", "INFY", "TCS", "SBIN"]
MAX_SYMBOLS = 10


def _unavailable(symbol: str, reason: str) -> dict[str, Any]:
    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "status": "NOT_AVAILABLE",
        "symbol": symbol,
        "reason": reason,
        "warnings": [],
        "decision_policy": {
            "watchlist_is_a_buy_sell_signal": False,
            "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
            "trading_execution": EXECUTION_ENABLED,
        },
    }


def refresh_watch_symbol(symbol: str) -> dict[str, Any]:
    """Refresh one watchlist symbol through the technical engine."""
    from analysis.data.technical_engine import analyze_stock

    name = str(symbol or "").strip().upper()
    if not name:
        return _unavailable(str(symbol), "Empty symbol.")

    try:
        result = analyze_stock(name)
    except Exception as exc:
        return _unavailable(
            name, f"{type(exc).__name__}: {exc}"
        )

    if not isinstance(result, dict) or result.get("price") is None:
        return _unavailable(name, "Engine returned no usable price.")

    def num(key):
        try:
            value = result.get(key)
            return None if value is None else float(value)
        except (TypeError, ValueError):
            return None

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "status": "AVAILABLE",
        "symbol": result.get("symbol", name),
        "company_name": result.get("company_name", ""),
        "price": num("price"),
        "open": num("open"),
        "high": num("high"),
        "low": num("low"),
        "volume": num("volume"),
        "change_percent": num("return_1d"),
        "rsi_14": num("rsi_14"),
        "rsi_condition": result.get("rsi_condition"),
        "macd_condition": result.get("macd_condition"),
        "trend": result.get("trend"),
        "momentum_score": num("momentum_score"),
        "ema_20": num("ema_20"),
        "ema_50": num("ema_50"),
        "ema_200": num("ema_200"),
        "timestamp": result.get("timestamp"),
        "source": result.get("source"),
        "warnings": [],
        "decision_policy": {
            "watchlist_is_a_buy_sell_signal": False,
            "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
            "trading_execution": EXECUTION_ENABLED,
        },
    }


if __name__ == "__main__":
    symbol = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SYMBOLS[0]
    print(json.dumps(refresh_watch_symbol(symbol), indent=2, default=str))
