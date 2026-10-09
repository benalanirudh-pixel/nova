"""
Nova Institutional Market Regime Engine v1
Analysis only. No trading or order execution.
"""

from __future__ import annotations

import argparse
import math
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from analysis.data.market_scanner import download_nifty, scan_market


BANK_NIFTY = "^NSEBANK"
INDIA_VIX = "^INDIAVIX"


def num(value: Any) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def fmt(value: Any) -> str:
    value = num(value)
    return "N/A" if value is None else f"{value:.2f}"


def load_index(symbol: str) -> pd.DataFrame:
    data = yf.download(
        symbol,
        period="1y",
        interval="1d",
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
    )

    if data is None or data.empty:
        raise RuntimeError(f"No Yahoo Finance data returned for {symbol}.")

    if isinstance(data.columns, pd.MultiIndex):
        if "Close" in data.columns.get_level_values(0):
            close = data["Close"]
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            return pd.DataFrame({"Close": close}).dropna()

        data.columns = [c[0] for c in data.columns]

    if "Close" not in data.columns:
        raise RuntimeError(f"{symbol} data has no Close column.")

    data["Close"] = pd.to_numeric(data["Close"], errors="coerce")
    return data.dropna(subset=["Close"])


def index_stats(data: pd.DataFrame) -> dict:
    close = pd.to_numeric(data["Close"], errors="coerce").dropna()

    def pct(period: int):
        if len(close) <= period:
            return None
        a, b = num(close.iloc[-1]), num(close.iloc[-period - 1])
        if a is None or b in (None, 0):
            return None
        return (a / b - 1) * 100

    e20 = close.ewm(span=20, adjust=False, min_periods=20).mean().iloc[-1]
    e50 = close.ewm(span=50, adjust=False, min_periods=50).mean().iloc[-1]
    e200 = close.ewm(span=200, adjust=False, min_periods=200).mean().iloc[-1]
    price = num(close.iloc[-1])

    e20, e50, e200 = num(e20), num(e50), num(e200)

    if all(v is not None for v in (price, e20, e50, e200)):
        if price > e20 > e50 > e200:
            trend = "STRONG_UPTREND"
        elif price < e20 < e50 < e200:
            trend = "STRONG_DOWNTREND"
        elif price > e50:
            trend = "UPTREND"
        elif price < e50:
            trend = "DOWNTREND"
        else:
            trend = "SIDEWAYS"
    else:
        trend = "INSUFFICIENT_DATA"

    logret = np.log(close / close.shift(1)).dropna()
    rv20 = num(logret.tail(20).std(ddof=1) * np.sqrt(252) * 100) if len(logret) >= 20 else None
    rv60 = num(logret.tail(60).std(ddof=1) * np.sqrt(252) * 100) if len(logret) >= 60 else None

    return {
        "price": price,
        "ema20": e20,
        "ema50": e50,
        "ema200": e200,
        "trend": trend,
        "return_20d": pct(20),
        "return_60d": pct(60),
        "realized_vol_20": rv20,
        "realized_vol_60": rv60,
    }


def breadth_score(breadth: dict) -> tuple[float, dict]:
    e20 = num(breadth.get("above_ema20_percent"))
    e50 = num(breadth.get("above_ema50_percent"))
    e200 = num(breadth.get("above_ema200_percent"))
    ad = num(breadth.get("advance_decline_ratio"))
    up = num(breadth.get("strong_uptrend_percent"))
    down = num(breadth.get("strong_downtrend_percent"))

    score = 0.0

    for value in (e20, e50, e200):
        if value is not None:
            if value >= 60:
                score += 3
            elif value >= 50:
                score += 2
            elif value >= 40:
                score += 1

    if ad is not None:
        if ad >= 2:
            score += 5
        elif ad >= 1.5:
            score += 4
        elif ad >= 1:
            score += 3
        elif ad >= 0.75:
            score += 1

    if up is not None and down is not None:
        spread = up - down
        if spread >= 10:
            score += 8
        elif spread >= 5:
            score += 6
        elif spread >= 0:
            score += 4
        elif spread >= -5:
            score += 2

    return min(score, 25), {
        "above_ema20_percent": e20,
        "above_ema50_percent": e50,
        "above_ema200_percent": e200,
        "advance_decline_ratio": ad,
        "strong_uptrend_percent": up,
        "strong_downtrend_percent": down,
    }


def participation_score(df: pd.DataFrame) -> tuple[float, dict]:
    scores = pd.to_numeric(df.get("score"), errors="coerce").dropna()
    if scores.empty:
        return 0.0, {}

    median = num(scores.median())
    p70 = num((scores >= 70).mean() * 100)
    p80 = num((scores >= 80).mean() * 100)

    score = 0.0
    if median is not None:
        score += 4 if median >= 65 else 3 if median >= 55 else 2 if median >= 45 else 1 if median >= 35 else 0
    if p70 is not None:
        score += 3 if p70 >= 30 else 2 if p70 >= 20 else 1 if p70 >= 10 else 0
    if p80 is not None:
        score += 3 if p80 >= 15 else 2 if p80 >= 8 else 1 if p80 >= 3 else 0

    return min(score, 10), {
        "median_score": median,
        "score_70_plus_percent": p70,
        "score_80_plus_percent": p80,
    }


def classify(score: float) -> str:
    if score >= 80:
        return "BULLISH"
    if score >= 65:
        return "MILDLY_BULLISH"
    if score >= 45:
        return "NEUTRAL"
    if score >= 30:
        return "MILDLY_BEARISH"
    return "BEARISH"


def run(limit: int | None = None) -> dict:
    df, summary = scan_market(limit=limit)

    nifty = index_stats(download_nifty())
    bank = index_stats(load_index(BANK_NIFTY))
    vix = index_stats(load_index(INDIA_VIX))

    # NIFTY structure: 25
    trend_points = 0
    for condition in (
        nifty["price"] is not None and nifty["ema20"] is not None and nifty["price"] > nifty["ema20"],
        nifty["ema20"] is not None and nifty["ema50"] is not None and nifty["ema20"] > nifty["ema50"],
        nifty["ema50"] is not None and nifty["ema200"] is not None and nifty["ema50"] > nifty["ema200"],
        nifty["price"] is not None and nifty["ema200"] is not None and nifty["price"] > nifty["ema200"],
    ):
        trend_points += 6.25 if condition else 0

    breadth_points, breadth = breadth_score(summary["breadth"])

    # Momentum: 15
    r20, r60 = num(nifty["return_20d"]), num(nifty["return_60d"])
    momentum_points = 0
    if r20 is not None:
        momentum_points += 4 if r20 >= 5 else 2 if r20 > 0 else 1 if r20 > -3 else 0
    if r60 is not None:
        momentum_points += 5 if r60 >= 10 else 4 if r60 >= 5 else 2 if r60 > 0 else 1 if r60 > -5 else 0
    if r20 is not None and r60 is not None:
        momentum_points += 3 if r20 > 0 and r60 > 0 else 1 if (r20 > 0 or r60 > 0) else 0

    # Volatility: 15
    rv20, rv60, vix_value = num(nifty["realized_vol_20"]), num(nifty["realized_vol_60"]), num(vix["price"])
    volatility_points = 0
    if rv20 is not None:
        volatility_points += 8 if rv20 < 12 else 6 if rv20 < 16 else 4 if rv20 < 20 else 2 if rv20 < 25 else 0
    if vix_value is not None:
        volatility_points += 7 if vix_value < 14 else 6 if vix_value < 18 else 4 if vix_value < 22 else 2 if vix_value < 28 else 0

    volatility_shock = (
        (rv20 is not None and rv60 not in (None, 0) and rv20 > rv60 * 1.35)
        or (vix_value is not None and vix_value >= 28)
    )
    if volatility_shock:
        volatility_points = min(volatility_points, 4)

    # BANK NIFTY confirmation: 10
    bank_points = 6 if bank["trend"] == "STRONG_UPTREND" else 4 if bank["trend"] == "UPTREND" else 2 if bank["trend"] == "SIDEWAYS" else 0
    br20, br60 = num(bank["return_20d"]), num(bank["return_60d"])
    if br20 is not None and br60 is not None:
        bank_points += 4 if br20 > 0 and br60 > 0 else 2 if br20 > 0 else 0
    bank_points = min(bank_points, 10)

    participation_points, participation = participation_score(df)

    components = {
        "nifty_trend": round(trend_points, 2),
        "breadth": round(breadth_points, 2),
        "momentum": round(min(momentum_points, 15), 2),
        "volatility": round(min(volatility_points, 15), 2),
        "bank_confirmation": round(bank_points, 2),
        "participation": round(participation_points, 2),
    }

    total = round(sum(components.values()), 2)
    regime = classify(total)

    if volatility_shock:
        environment = "DEFENSIVE / HIGH-VOLATILITY"
    elif regime == "BULLISH":
        environment = "RISK-ON"
    elif regime == "MILDLY_BULLISH":
        environment = "SELECTIVE RISK-ON"
    elif regime == "MILDLY_BEARISH":
        environment = "SELECTIVE / DEFENSIVE"
    elif regime == "BEARISH":
        environment = "RISK-OFF"
    else:
        environment = "BALANCED / UNCERTAIN"

    return {
        "regime": regime,
        "score": total,
        "environment": environment,
        "volatility_shock": volatility_shock,
        "components": components,
        "nifty": nifty,
        "bank_nifty": bank,
        "india_vix": vix,
        "breadth": breadth,
        "participation": participation,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Nova Institutional Market Regime Engine"
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    print("=" * 90)
    print("NOVA INSTITUTIONAL MARKET REGIME ENGINE")
    print("=" * 90)

    result = run(limit=args.limit)

    print()
    print(f"MARKET REGIME    : {result['regime']}")
    print(f"REGIME SCORE     : {result['score']:.2f} / 100")
    print(f"ENVIRONMENT      : {result['environment']}")
    print(f"VOLATILITY SHOCK : {'YES' if result['volatility_shock'] else 'NO'}")

    print()
    print("COMPONENT SCORES")
    print("-" * 90)
    for name, value in result["components"].items():
        print(f"{name:<22}: {value:>6.2f}")

    n = result["nifty"]
    b = result["bank_nifty"]
    v = result["india_vix"]

    print()
    print("INDEX STRUCTURE")
    print("-" * 90)
    print(f"NIFTY 50           : {fmt(n['price'])}")
    print(f"NIFTY trend        : {n['trend']}")
    print(f"NIFTY 20D          : {fmt(n['return_20d'])}%")
    print(f"NIFTY 60D          : {fmt(n['return_60d'])}%")
    print(f"BANK NIFTY trend   : {b['trend']}")
    print(f"BANK NIFTY 20D     : {fmt(b['return_20d'])}%")
    print(f"INDIA VIX          : {fmt(v['price'])}")

    br = result["breadth"]
    print()
    print("MARKET BREADTH")
    print("-" * 90)
    print(f"Above EMA20        : {fmt(br['above_ema20_percent'])}%")
    print(f"Above EMA50        : {fmt(br['above_ema50_percent'])}%")
    print(f"Above EMA200       : {fmt(br['above_ema200_percent'])}%")
    print(f"A/D ratio          : {fmt(br['advance_decline_ratio'])}")
    print(f"Strong uptrends    : {fmt(br['strong_uptrend_percent'])}%")
    print(f"Strong downtrends  : {fmt(br['strong_downtrend_percent'])}%")

    p = result["participation"]
    print()
    print("PARTICIPATION")
    print("-" * 90)
    print(f"Median score       : {fmt(p.get('median_score'))}")
    print(f"Score >= 70        : {fmt(p.get('score_70_plus_percent'))}%")
    print(f"Score >= 80        : {fmt(p.get('score_80_plus_percent'))}%")

    print()
    print("This is market-environment analysis, NOT a BUY/SELL signal.")
    print("Thresholds require historical and out-of-sample validation.")


if __name__ == "__main__":
    main()
