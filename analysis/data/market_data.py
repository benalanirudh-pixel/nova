"""
Nova Analysis Lab
Step 1 — Yahoo Finance market data layer
"""

from __future__ import annotations

import yfinance as yf
import pandas as pd


INSTRUMENTS = {
    "NIFTY": "^NSEI",
    "BANK_NIFTY": "^NSEBANK",
    "INDIA_VIX": "^INDIAVIX",
}


def get_history(
    symbol: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:

    ticker = yf.Ticker(symbol)

    data = ticker.history(
        period=period,
        interval=interval,
        auto_adjust=False,
    )

    if data.empty:
        raise RuntimeError(
            f"No market data returned for Yahoo symbol: {symbol}"
        )

    columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    available = [
        column for column in columns
        if column in data.columns
    ]

    data = data[available].copy()
    data = data.dropna(subset=["Close"])

    return data


def get_instrument(
    name: str,
    period: str = "1y",
    interval: str = "1d",
) -> pd.DataFrame:

    name = name.upper()

    if name not in INSTRUMENTS:
        available = ", ".join(INSTRUMENTS.keys())

        raise ValueError(
            f"Unknown instrument '{name}'. "
            f"Available: {available}"
        )

    return get_history(
        INSTRUMENTS[name],
        period=period,
        interval=interval,
    )


def get_market_snapshot() -> dict:

    snapshot = {}

    for name, symbol in INSTRUMENTS.items():

        data = get_history(
            symbol,
            period="5d",
            interval="1d",
        )

        latest = data.iloc[-1]

        snapshot[name] = {
            "symbol": symbol,
            "timestamp": data.index[-1].isoformat(),
            "open": float(latest["Open"]),
            "high": float(latest["High"]),
            "low": float(latest["Low"]),
            "close": float(latest["Close"]),
            "volume": float(latest["Volume"]),
        }

    return snapshot


if __name__ == "__main__":

    print()
    print("NOVA MARKET DATA TEST")
    print("=" * 60)

    snapshot = get_market_snapshot()

    for name, data in snapshot.items():

        print()
        print(name)
        print("-" * 60)

        print(f"Symbol : {data['symbol']}")
        print(f"Time   : {data['timestamp']}")
        print(f"Open   : {data['open']:.2f}")
        print(f"High   : {data['high']:.2f}")
        print(f"Low    : {data['low']:.2f}")
        print(f"Close  : {data['close']:.2f}")
        print(f"Volume : {data['volume']:,.0f}")

    print()
    print("Market data test completed.")