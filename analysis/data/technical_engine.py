"""
Nova Market Intelligence
Technical Analysis Engine v1

Purpose:
    Calculate technical indicators for Indian equities.

Design:
    Python calculates all numerical indicators.
    Nova/LLM only interprets the calculated results.

No trading or order execution is performed here.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from analysis.data.market_universe import (
    get_price_history,
    resolve_symbol,
    scan_nse_market,
)


# ============================================================
# CONFIGURATION
# ============================================================

RSI_PERIOD = 14

EMA_FAST = 9
EMA_MID = 20
EMA_SLOW = 50
EMA_LONG = 200

SMA_FAST = 20
SMA_MID = 50
SMA_LONG = 200

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ATR_PERIOD = 14

ROC_PERIOD = 12

VOLUME_PERIOD = 20

VWAP_PERIOD = 20


# ============================================================
# BASIC HELPERS
# ============================================================

def _series(data: pd.DataFrame, column: str) -> pd.Series:

    if column not in data.columns:
        raise ValueError(
            f"Missing required column: {column}"
        )

    return pd.to_numeric(
        data[column],
        errors="coerce",
    )


def _safe_float(value: Any) -> float | None:

    try:

        if value is None or pd.isna(value):
            return None

        return float(value)

    except (TypeError, ValueError):

        return None


# ============================================================
# EMA
# ============================================================

def calculate_ema(
    close: pd.Series,
    period: int,
) -> pd.Series:

    return close.ewm(
        span=period,
        adjust=False,
        min_periods=period,
    ).mean()


# ============================================================
# SMA
# ============================================================

def calculate_sma(
    close: pd.Series,
    period: int,
) -> pd.Series:

    return close.rolling(
        window=period,
        min_periods=period,
    ).mean()


# ============================================================
# RSI
# ============================================================

def calculate_rsi(
    close: pd.Series,
    period: int = RSI_PERIOD,
) -> pd.Series:

    delta = close.diff()

    gain = delta.clip(
        lower=0
    )

    loss = -delta.clip(
        upper=0
    )

    avg_gain = gain.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    avg_loss = loss.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()

    rs = avg_gain / avg_loss.replace(
        0,
        np.nan,
    )

    rsi = 100 - (
        100 / (1 + rs)
    )

    # If losses are zero, RSI should be 100.
    rsi = rsi.where(
        avg_loss != 0,
        100,
    )

    return rsi


# ============================================================
# MACD
# ============================================================

def calculate_macd(
    close: pd.Series,
) -> tuple[
    pd.Series,
    pd.Series,
    pd.Series,
]:

    fast = calculate_ema(
        close,
        MACD_FAST,
    )

    slow = calculate_ema(
        close,
        MACD_SLOW,
    )

    macd = fast - slow

    signal = macd.ewm(
        span=MACD_SIGNAL,
        adjust=False,
        min_periods=MACD_SIGNAL,
    ).mean()

    histogram = macd - signal

    return macd, signal, histogram


# ============================================================
# TRUE RANGE
# ============================================================

def calculate_true_range(
    data: pd.DataFrame,
) -> pd.Series:

    high = _series(
        data,
        "High",
    )

    low = _series(
        data,
        "Low",
    )

    close = _series(
        data,
        "Close",
    )

    previous_close = close.shift(1)

    range_1 = high - low

    range_2 = (
        high - previous_close
    ).abs()

    range_3 = (
        low - previous_close
    ).abs()

    return pd.concat(
        [
            range_1,
            range_2,
            range_3,
        ],
        axis=1,
    ).max(axis=1)


# ============================================================
# ATR
# ============================================================

def calculate_atr(
    data: pd.DataFrame,
    period: int = ATR_PERIOD,
) -> pd.Series:

    true_range = calculate_true_range(
        data
    )

    return true_range.ewm(
        alpha=1 / period,
        adjust=False,
        min_periods=period,
    ).mean()


# ============================================================
# ROC
# ============================================================

def calculate_roc(
    close: pd.Series,
    period: int = ROC_PERIOD,
) -> pd.Series:

    return (
        close.pct_change(periods=period)
        * 100
    )


# ============================================================
# RELATIVE VOLUME
# ============================================================

def calculate_relative_volume(
    volume: pd.Series,
    period: int = VOLUME_PERIOD,
) -> pd.Series:

    average_volume = volume.rolling(
        window=period,
        min_periods=period,
    ).mean()

    return (
        volume / average_volume
    )


# ============================================================
# 20-DAY VOLUME WEIGHTED PRICE
# ============================================================

def calculate_vwap(
    data: pd.DataFrame,
    period: int = VWAP_PERIOD,
) -> pd.Series:

    high = _series(
        data,
        "High",
    )

    low = _series(
        data,
        "Low",
    )

    close = _series(
        data,
        "Close",
    )

    volume = _series(
        data,
        "Volume",
    )

    typical_price = (
        high + low + close
    ) / 3

    price_volume = (
        typical_price * volume
    )

    rolling_pv = price_volume.rolling(
        window=period,
        min_periods=period,
    ).sum()

    rolling_volume = volume.rolling(
        window=period,
        min_periods=period,
    ).sum()

    return (
        rolling_pv / rolling_volume
    )


# ============================================================
# 52-WEEK LEVELS
# ============================================================

def calculate_52_week_levels(
    close: pd.Series,
) -> dict:

    # Approximately 252 trading sessions.
    lookback = min(
        len(close),
        252,
    )

    recent = close.tail(
        lookback
    )

    if recent.empty:

        return {
            "high_52w": None,
            "low_52w": None,
        }

    return {
        "high_52w": _safe_float(
            recent.max()
        ),
        "low_52w": _safe_float(
            recent.min()
        ),
    }


# ============================================================
# MARKET STRUCTURE
# ============================================================

def determine_structure(
    data: pd.DataFrame,
) -> dict:

    high = _series(
        data,
        "High",
    )

    low = _series(
        data,
        "Low",
    )

    if len(data) < 10:

        return {
            "structure": "INSUFFICIENT_DATA",
            "higher_high": False,
            "higher_low": False,
            "lower_high": False,
            "lower_low": False,
        }

    recent_high = high.iloc[-1]
    previous_high = high.iloc[-2]

    recent_low = low.iloc[-1]
    previous_low = low.iloc[-2]

    higher_high = (
        recent_high > previous_high
    )

    higher_low = (
        recent_low > previous_low
    )

    lower_high = (
        recent_high < previous_high
    )

    lower_low = (
        recent_low < previous_low
    )

    if higher_high and higher_low:

        structure = "BULLISH"

    elif lower_high and lower_low:

        structure = "BEARISH"

    elif higher_high or higher_low:

        structure = "IMPROVING"

    elif lower_high or lower_low:

        structure = "WEAKENING"

    else:

        structure = "NEUTRAL"

    return {
        "structure": structure,
        "higher_high": higher_high,
        "higher_low": higher_low,
        "lower_high": lower_high,
        "lower_low": lower_low,
    }


# ============================================================
# TREND CLASSIFICATION
# ============================================================

def determine_trend(
    price: float,
    ema20: float | None,
    ema50: float | None,
    ema200: float | None,
) -> str:

    if (
        ema20 is None
        or ema50 is None
    ):

        return "INSUFFICIENT_DATA"

    if ema200 is not None:

        if (
            price > ema20
            and ema20 > ema50
            and ema50 > ema200
        ):

            return "STRONG_UPTREND"

        if (
            price < ema20
            and ema20 < ema50
            and ema50 < ema200
        ):

            return "STRONG_DOWNTREND"

    if (
        price > ema20
        and ema20 > ema50
    ):

        return "UPTREND"

    if (
        price < ema20
        and ema20 < ema50
    ):

        return "DOWNTREND"

    return "SIDEWAYS"


# ============================================================
# MOMENTUM SCORE
# ============================================================

def calculate_momentum_score(
    price: float,
    ema20: float | None,
    ema50: float | None,
    ema200: float | None,
    rsi: float | None,
    macd: float | None,
    macd_signal: float | None,
    roc: float | None,
) -> float:

    score = 0.0

    # --------------------------------------------------------
    # Price vs EMA20
    # --------------------------------------------------------

    if ema20 is not None:

        if price > ema20:
            score += 12.5

    # --------------------------------------------------------
    # EMA20 vs EMA50
    # --------------------------------------------------------

    if (
        ema20 is not None
        and ema50 is not None
    ):

        if ema20 > ema50:
            score += 12.5

    # --------------------------------------------------------
    # EMA50 vs EMA200
    # --------------------------------------------------------

    if (
        ema50 is not None
        and ema200 is not None
    ):

        if ema50 > ema200:
            score += 12.5

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    if rsi is not None:

        if 50 <= rsi <= 70:
            score += 12.5

        elif 70 < rsi <= 80:
            score += 8

        elif 40 <= rsi < 50:
            score += 5

    # --------------------------------------------------------
    # MACD
    # --------------------------------------------------------

    if (
        macd is not None
        and macd_signal is not None
    ):

        if macd > macd_signal:
            score += 12.5

    # --------------------------------------------------------
    # ROC
    # --------------------------------------------------------

    if roc is not None:

        if roc > 0:
            score += 12.5

    # --------------------------------------------------------
    # Price above EMA50
    # --------------------------------------------------------

    if (
        ema50 is not None
        and price > ema50
    ):

        score += 12.5

    return round(
        min(score, 100),
        2,
    )


# ============================================================
# FULL TECHNICAL CALCULATION
# ============================================================

def calculate_indicators(
    data: pd.DataFrame,
) -> pd.DataFrame:

    if data.empty:

        raise ValueError(
            "Cannot calculate indicators "
            "from empty data."
        )

    data = data.copy()

    close = _series(
        data,
        "Close",
    )

    volume = _series(
        data,
        "Volume",
    )

    # --------------------------------------------------------
    # Moving averages
    # --------------------------------------------------------

    data["EMA_9"] = calculate_ema(
        close,
        EMA_FAST,
    )

    data["EMA_20"] = calculate_ema(
        close,
        EMA_MID,
    )

    data["EMA_50"] = calculate_ema(
        close,
        EMA_SLOW,
    )

    data["EMA_200"] = calculate_ema(
        close,
        EMA_LONG,
    )

    data["SMA_20"] = calculate_sma(
        close,
        SMA_FAST,
    )

    data["SMA_50"] = calculate_sma(
        close,
        SMA_MID,
    )

    data["SMA_200"] = calculate_sma(
        close,
        SMA_LONG,
    )

    # --------------------------------------------------------
    # Momentum
    # --------------------------------------------------------

    data["RSI_14"] = calculate_rsi(
        close,
        RSI_PERIOD,
    )

    (
        data["MACD"],
        data["MACD_SIGNAL"],
        data["MACD_HISTOGRAM"],
    ) = calculate_macd(
        close
    )

    data["ROC_12"] = calculate_roc(
        close,
        ROC_PERIOD,
    )

    # --------------------------------------------------------
    # Volatility
    # --------------------------------------------------------

    data["ATR_14"] = calculate_atr(
        data,
        ATR_PERIOD,
    )

    # --------------------------------------------------------
    # Volume
    # --------------------------------------------------------

    data["VOLUME_AVG_20"] = (
        volume.rolling(
            window=VOLUME_PERIOD,
            min_periods=VOLUME_PERIOD,
        ).mean()
    )

    data["RELATIVE_VOLUME"] = (
        calculate_relative_volume(
            volume,
            VOLUME_PERIOD,
        )
    )

    # --------------------------------------------------------
    # VWAP
    # --------------------------------------------------------

    data["VWAP_20D"] = calculate_vwap(
        data,
        VWAP_PERIOD,
    )

    # --------------------------------------------------------
    # Returns
    # --------------------------------------------------------

    data["RETURN_1D"] = (
        close.pct_change(1) * 100
    )

    data["RETURN_5D"] = (
        close.pct_change(5) * 100
    )

    data["RETURN_20D"] = (
        close.pct_change(20) * 100
    )

    data["RETURN_60D"] = (
        close.pct_change(60) * 100
    )

    return data


# ============================================================
# STOCK ANALYSIS
# ============================================================

def analyze_stock(
    query: str,
) -> dict:

    security = resolve_symbol(
        query
    )

    if security is None:

        raise ValueError(
            f"Stock not found in NSE master: {query}"
        )

    symbol = security["symbol"]

    # 1 year is required for proper 200-day / 52-week analysis.
    data = get_price_history(
        symbol,
        period="1y",
        interval="1d",
    )

    indicators = calculate_indicators(
        data
    )

    latest = indicators.iloc[-1]

    price = _safe_float(
        latest["Close"]
    )

    if price is None:

        raise RuntimeError(
            f"No valid price available for {symbol}"
        )

    ema9 = _safe_float(
        latest["EMA_9"]
    )

    ema20 = _safe_float(
        latest["EMA_20"]
    )

    ema50 = _safe_float(
        latest["EMA_50"]
    )

    ema200 = _safe_float(
        latest["EMA_200"]
    )

    sma20 = _safe_float(
        latest["SMA_20"]
    )

    sma50 = _safe_float(
        latest["SMA_50"]
    )

    sma200 = _safe_float(
        latest["SMA_200"]
    )

    rsi = _safe_float(
        latest["RSI_14"]
    )

    macd = _safe_float(
        latest["MACD"]
    )

    macd_signal = _safe_float(
        latest["MACD_SIGNAL"]
    )

    macd_histogram = _safe_float(
        latest["MACD_HISTOGRAM"]
    )

    atr = _safe_float(
        latest["ATR_14"]
    )

    roc = _safe_float(
        latest["ROC_12"]
    )

    relative_volume = _safe_float(
        latest["RELATIVE_VOLUME"]
    )

    volume_average = _safe_float(
        latest["VOLUME_AVG_20"]
    )

    vwap20 = _safe_float(
        latest["VWAP_20D"]
    )

    return_1d = _safe_float(
        latest["RETURN_1D"]
    )

    return_5d = _safe_float(
        latest["RETURN_5D"]
    )

    return_20d = _safe_float(
        latest["RETURN_20D"]
    )

    return_60d = _safe_float(
        latest["RETURN_60D"]
    )

    # --------------------------------------------------------
    # 52-week levels
    # --------------------------------------------------------

    levels = calculate_52_week_levels(
        indicators["Close"]
    )

    high_52w = levels["high_52w"]
    low_52w = levels["low_52w"]

    if high_52w:

        distance_from_high = (
            (price - high_52w)
            / high_52w
        ) * 100

    else:

        distance_from_high = None

    if low_52w:

        distance_from_low = (
            (price - low_52w)
            / low_52w
        ) * 100

    else:

        distance_from_low = None

    # --------------------------------------------------------
    # Trend
    # --------------------------------------------------------

    trend = determine_trend(
        price,
        ema20,
        ema50,
        ema200,
    )

    structure = determine_structure(
        data
    )

    momentum_score = (
        calculate_momentum_score(
            price,
            ema20,
            ema50,
            ema200,
            rsi,
            macd,
            macd_signal,
            roc,
        )
    )

    # --------------------------------------------------------
    # Volume condition
    # --------------------------------------------------------

    if relative_volume is None:

        volume_condition = (
            "INSUFFICIENT_DATA"
        )

    elif relative_volume >= 2:

        volume_condition = (
            "VERY_HIGH"
        )

    elif relative_volume >= 1.5:

        volume_condition = (
            "HIGH"
        )

    elif relative_volume >= 1:

        volume_condition = (
            "NORMAL"
        )

    else:

        volume_condition = (
            "LOW"
        )

    # --------------------------------------------------------
    # RSI condition
    # --------------------------------------------------------

    if rsi is None:

        rsi_condition = (
            "INSUFFICIENT_DATA"
        )

    elif rsi >= 70:

        rsi_condition = "OVERBOUGHT"

    elif rsi <= 30:

        rsi_condition = "OVERSOLD"

    elif rsi >= 55:

        rsi_condition = "BULLISH"

    elif rsi <= 45:

        rsi_condition = "BEARISH"

    else:

        rsi_condition = "NEUTRAL"

    # --------------------------------------------------------
    # MACD condition
    # --------------------------------------------------------

    if (
        macd is None
        or macd_signal is None
    ):

        macd_condition = (
            "INSUFFICIENT_DATA"
        )

    elif macd > macd_signal:

        macd_condition = "BULLISH"

    else:

        macd_condition = "BEARISH"

    # --------------------------------------------------------
    # VWAP condition
    # --------------------------------------------------------

    if vwap20 is None:

        vwap_condition = (
            "INSUFFICIENT_DATA"
        )

    elif price > vwap20:

        vwap_condition = "ABOVE"

    else:

        vwap_condition = "BELOW"

    # --------------------------------------------------------
    # Timestamp
    # --------------------------------------------------------

    timestamp = pd.Timestamp(
        indicators.index[-1]
    )

    if timestamp.tzinfo is None:

        timestamp = timestamp.tz_localize(
            "Asia/Kolkata"
        )

    else:

        timestamp = timestamp.tz_convert(
            "Asia/Kolkata"
        )

    # --------------------------------------------------------
    # Final result
    # --------------------------------------------------------

    return {
        "symbol": symbol,

        "company_name": security.get(
            "company_name",
            "",
        ),

        "exchange": "NSE",

        "series": security.get(
            "series",
            "",
        ),

        "isin": security.get(
            "isin",
            "",
        ),

        "source": "Yahoo Finance",

        "timestamp": timestamp.isoformat(),

        "price": price,

        "open": _safe_float(
            latest["Open"]
        ),

        "high": _safe_float(
            latest["High"]
        ),

        "low": _safe_float(
            latest["Low"]
        ),

        "volume": _safe_float(
            latest["Volume"]
        ),

        "ema_9": ema9,
        "ema_20": ema20,
        "ema_50": ema50,
        "ema_200": ema200,

        "sma_20": sma20,
        "sma_50": sma50,
        "sma_200": sma200,

        "rsi_14": rsi,

        "rsi_condition": rsi_condition,

        "macd": macd,

        "macd_signal": macd_signal,

        "macd_histogram": macd_histogram,

        "macd_condition": macd_condition,

        "atr_14": atr,

        "roc_12": roc,

        "relative_volume": relative_volume,

        "volume_average_20": volume_average,

        "volume_condition": volume_condition,

        "vwap_20d": vwap20,

        "vwap_condition": vwap_condition,

        "return_1d": return_1d,

        "return_5d": return_5d,

        "return_20d": return_20d,

        "return_60d": return_60d,

        "high_52w": high_52w,

        "low_52w": low_52w,

        "distance_from_52w_high": (
            distance_from_high
        ),

        "distance_from_52w_low": (
            distance_from_low
        ),

        "trend": trend,

        "market_structure": (
            structure["structure"]
        ),

        "higher_high": (
            structure["higher_high"]
        ),

        "higher_low": (
            structure["higher_low"]
        ),

        "lower_high": (
            structure["lower_high"]
        ),

        "lower_low": (
            structure["lower_low"]
        ),

        "momentum_score": momentum_score,
    }


# ============================================================
# FORMAT ANALYSIS FOR NOVA
# ============================================================

def format_analysis(
    analysis: dict,
) -> str:

    def fmt(
        value: Any,
        decimals: int = 2,
    ) -> str:

        if value is None:
            return "N/A"

        try:
            return f"{float(value):.{decimals}f}"
        except (TypeError, ValueError):
            return str(value)

    lines = [
        "VERIFIED TECHNICAL ANALYSIS",
        "========================================",
        f"Stock: {analysis['symbol']}",
        f"Company: {analysis['company_name']}",
        f"Exchange: {analysis['exchange']}",
        f"Timestamp: {analysis['timestamp']}",
        f"Source: {analysis['source']}",
        "",
        "PRICE",
        f"Price: {fmt(analysis['price'])}",
        f"Open: {fmt(analysis['open'])}",
        f"High: {fmt(analysis['high'])}",
        f"Low: {fmt(analysis['low'])}",
        f"Volume: {fmt(analysis['volume'], 0)}",
        "",
        "MOVING AVERAGES",
        f"EMA 9: {fmt(analysis['ema_9'])}",
        f"EMA 20: {fmt(analysis['ema_20'])}",
        f"EMA 50: {fmt(analysis['ema_50'])}",
        f"EMA 200: {fmt(analysis['ema_200'])}",
        f"SMA 20: {fmt(analysis['sma_20'])}",
        f"SMA 50: {fmt(analysis['sma_50'])}",
        f"SMA 200: {fmt(analysis['sma_200'])}",
        "",
        "MOMENTUM",
        f"RSI 14: {fmt(analysis['rsi_14'])}",
        f"RSI Condition: {analysis['rsi_condition']}",
        f"MACD: {fmt(analysis['macd'])}",
        f"MACD Signal: {fmt(analysis['macd_signal'])}",
        f"MACD Histogram: {fmt(analysis['macd_histogram'])}",
        f"MACD Condition: {analysis['macd_condition']}",
        f"ROC 12: {fmt(analysis['roc_12'])}%",
        "",
        "VOLATILITY",
        f"ATR 14: {fmt(analysis['atr_14'])}",
        "",
        "VOLUME",
        f"20D Average Volume: {fmt(analysis['volume_average_20'], 0)}",
        f"Relative Volume: {fmt(analysis['relative_volume'])}x",
        f"Volume Condition: {analysis['volume_condition']}",
        "",
        "VWAP",
        f"20D VWAP: {fmt(analysis['vwap_20d'])}",
        f"Price vs VWAP: {analysis['vwap_condition']}",
        "",
        "RETURNS",
        f"1D: {fmt(analysis['return_1d'])}%",
        f"5D: {fmt(analysis['return_5d'])}%",
        f"20D: {fmt(analysis['return_20d'])}%",
        f"60D: {fmt(analysis['return_60d'])}%",
        "",
        "52 WEEK",
        f"52W High: {fmt(analysis['high_52w'])}",
        f"52W Low: {fmt(analysis['low_52w'])}",
        f"Distance From 52W High: "
        f"{fmt(analysis['distance_from_52w_high'])}%",
        f"Distance From 52W Low: "
        f"{fmt(analysis['distance_from_52w_low'])}%",
        "",
        "MARKET STRUCTURE",
        f"Trend: {analysis['trend']}",
        f"Structure: {analysis['market_structure']}",
        f"Higher High: {analysis['higher_high']}",
        f"Higher Low: {analysis['higher_low']}",
        f"Lower High: {analysis['lower_high']}",
        f"Lower Low: {analysis['lower_low']}",
        "",
        "MOMENTUM SCORE",
        f"{fmt(analysis['momentum_score'])}/100",
        "========================================",
    ]

    return "\n".join(lines)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print()
    print("=" * 70)
    print("NOVA TECHNICAL ANALYSIS ENGINE V1")
    print("=" * 70)

    print()
    print("Analyzing RELIANCE...")

    try:

        result = analyze_stock(
            "RELIANCE"
        )

        print()
        print(
            format_analysis(
                result
            )
        )

    except Exception as exc:

        print()
        print("TECHNICAL ENGINE ERROR")
        print(exc)

    print()
    print("=" * 70)
    print("TECHNICAL ENGINE TEST COMPLETE")
    print("=" * 70)