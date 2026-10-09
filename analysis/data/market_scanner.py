"""
============================================================
NOVA MARKET INTELLIGENCE
FULL NSE MARKET SCANNER
============================================================

Purpose:
    Scan the NSE equity universe and rank stocks using
    multiple quantitative factors.

Factors:

    TREND
        EMA 20
        EMA 50
        EMA 200
        Price vs moving averages

    MOMENTUM
        RSI 14
        MACD
        1D return
        5D return
        20D return
        60D return

    VOLUME
        Relative volume
        20D average volume

    RELATIVE STRENGTH
        Stock vs NIFTY 20D
        Stock vs NIFTY 60D

    PRICE STRUCTURE
        52-week high proximity
        52-week low proximity

    MARKET BREADTH
        Advancing stocks
        Declining stocks
        A/D ratio
        Stocks above EMA20
        Stocks above EMA50
        Stocks above EMA200
        Strong uptrends
        Strong downtrends

    MARKET REGIME
        NIFTY trend/returns
        Market breadth

SCORING:

    Trend              25
    Momentum           25
    Volume             15
    Relative Strength  20
    Structure          15
                       ---
                       100

IMPORTANT:

    This is an analysis/ranking engine.

    It does NOT:
        - place trades
        - send orders
        - guarantee profits
        - generate automatic BUY/SELL orders

    The final institutional checklist will be built
    separately.

DATA SOURCE:

    Yahoo Finance via yfinance
    NSE Security Master for the stock universe.
============================================================
"""

from __future__ import annotations

import argparse
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

from analysis.data.market_universe import (
    get_nse_symbols,
)

from analysis.data.technical_engine import (
    calculate_indicators,
)


# ============================================================
# CONFIGURATION
# ============================================================

CHUNK_SIZE = 150

REQUEST_DELAY = 0.25

HISTORY_PERIOD = "1y"

HISTORY_INTERVAL = "1d"

NIFTY_SYMBOL = "^NSEI"

OUTPUT_DIR = (
    Path(__file__).resolve().parent
    / "cache"
    / "scanner"
)

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(
    value: Any,
) -> float | None:
    """
    Safely convert a value to float.
    """

    try:

        if value is None:
            return None

        if pd.isna(value):
            return None

        value = float(value)

        if not math.isfinite(value):
            return None

        return value

    except (
        TypeError,
        ValueError,
    ):

        return None


def yahoo_symbol(
    symbol: str,
) -> str:
    """
    Convert an NSE symbol to Yahoo Finance format.
    """

    symbol = (
        str(symbol)
        .strip()
        .upper()
    )

    if symbol.endswith(".NS"):
        return symbol

    return f"{symbol}.NS"


def chunked(
    items: list[str],
    size: int,
):
    """
    Split a list into chunks.
    """

    for index in range(
        0,
        len(items),
        size,
    ):

        yield items[
            index:index + size
        ]


# ============================================================
# NIFTY BENCHMARK
# ============================================================

def download_nifty() -> pd.DataFrame:
    """
    Download NIFTY 50 daily history.
    """

    data = yf.download(
        NIFTY_SYMBOL,
        period=HISTORY_PERIOD,
        interval=HISTORY_INTERVAL,
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=False,
        group_by="column",
    )

    if data is None or data.empty:

        raise RuntimeError(
            "Unable to download NIFTY 50 data."
        )

    # yfinance can occasionally return a MultiIndex
    # even for a single ticker.
    if isinstance(
        data.columns,
        pd.MultiIndex,
    ):

        try:

            # Find Close column safely.
            if "Close" in data.columns.get_level_values(0):

                data = data[
                    "Close"
                ]

                if isinstance(
                    data,
                    pd.DataFrame,
                ):

                    data = data.iloc[
                        :,
                        0,
                    ]

                data = pd.DataFrame(
                    {
                        "Close": data
                    }
                )

            else:

                data.columns = [
                    column[0]
                    for column in data.columns
                ]

        except Exception:

            data.columns = [
                column[0]
                for column in data.columns
            ]

    if "Close" not in data.columns:

        raise RuntimeError(
            "NIFTY data does not contain Close prices."
        )

    data["Close"] = pd.to_numeric(
        data["Close"],
        errors="coerce",
    )

    return data.dropna(
        subset=["Close"]
    )


# ============================================================
# NIFTY RETURNS
# ============================================================

def calculate_nifty_returns(
    nifty: pd.DataFrame,
) -> dict:
    """
    Calculate NIFTY benchmark returns.
    """

    close = pd.to_numeric(
        nifty["Close"],
        errors="coerce",
    ).dropna()

    result = {
        "return_1d": None,
        "return_5d": None,
        "return_20d": None,
        "return_60d": None,
    }

    for periods, key in [
        (1, "return_1d"),
        (5, "return_5d"),
        (20, "return_20d"),
        (60, "return_60d"),
    ]:

        if len(close) > periods:

            current = safe_float(
                close.iloc[-1]
            )

            previous = safe_float(
                close.iloc[-periods - 1]
            )

            if (
                current is not None
                and previous not in (
                    None,
                    0,
                )
            ):

                result[key] = (
                    (
                        current
                        / previous
                    )
                    - 1
                ) * 100

    return result


# ============================================================
# DOWNLOAD STOCK CHUNK
# ============================================================

def download_chunk(
    symbols: list[str],
) -> pd.DataFrame:
    """
    Download multiple NSE securities in one batch.

    This is much faster than requesting every stock
    individually.
    """

    yahoo_symbols = [
        yahoo_symbol(symbol)
        for symbol in symbols
    ]

    if not yahoo_symbols:

        return pd.DataFrame()

    try:

        data = yf.download(
            tickers=yahoo_symbols,
            period=HISTORY_PERIOD,
            interval=HISTORY_INTERVAL,
            auto_adjust=False,
            actions=False,
            progress=False,
            threads=True,
            group_by="ticker",
            multi_level_index=True,
        )

    except Exception as exc:

        print(
            f"  Download error: {exc}"
        )

        return pd.DataFrame()

    if data is None or data.empty:

        return pd.DataFrame()

    return data


# ============================================================
# EXTRACT INDIVIDUAL STOCK
# ============================================================

def extract_stock(
    data: pd.DataFrame,
    symbol: str,
) -> pd.DataFrame | None:
    """
    Extract one stock from a yfinance batch response.

    Handles both common MultiIndex orientations.
    """

    yahoo = yahoo_symbol(symbol)

    try:

        if not isinstance(
            data.columns,
            pd.MultiIndex,
        ):

            result = data.copy()

        else:

            level_zero = (
                data.columns
                .get_level_values(0)
                .astype(str)
                .tolist()
            )

            level_one = (
                data.columns
                .get_level_values(1)
                .astype(str)
                .tolist()
            )

            if yahoo in level_zero:

                result = data[
                    yahoo
                ].copy()

            elif yahoo in level_one:

                result = data.xs(
                    yahoo,
                    axis=1,
                    level=1,
                ).copy()

            else:

                return None

        required = [
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]

        available = [
            column
            for column in required
            if column in result.columns
        ]

        if "Close" not in available:

            return None

        result = result[
            available
        ].copy()

        for column in available:

            result[column] = pd.to_numeric(
                result[column],
                errors="coerce",
            )

        result = result.dropna(
            subset=["Close"]
        )

        if result.empty:

            return None

        return result

    except Exception:

        return None


# ============================================================
# STOCK RETURN
# ============================================================

def calculate_return(
    close: pd.Series,
    periods: int,
) -> float | None:
    """
    Calculate percentage return over N trading sessions.
    """

    if len(close) <= periods:

        return None

    current = safe_float(
        close.iloc[-1]
    )

    previous = safe_float(
        close.iloc[-periods - 1]
    )

    if (
        current is None
        or previous in (
            None,
            0,
        )
    ):

        return None

    return (
        (
            current
            / previous
        )
        - 1
    ) * 100


# ============================================================
# TECHNICAL SCORE
# ============================================================

def calculate_score(
    latest: pd.Series,
    stock_return_20d: float | None,
    stock_return_60d: float | None,
    nifty_return_20d: float | None,
    nifty_return_60d: float | None,
) -> tuple[float, dict]:
    """
    Calculate the 0-100 technical ranking score.

    Weighting:

        Trend              25
        Momentum           25
        Volume             15
        Relative Strength  20
        Structure          15
    """

    score = 0.0

    components = {}

    price = safe_float(
        latest.get("Close")
    )

    ema20 = safe_float(
        latest.get("EMA_20")
    )

    ema50 = safe_float(
        latest.get("EMA_50")
    )

    ema200 = safe_float(
        latest.get("EMA_200")
    )

    rsi = safe_float(
        latest.get("RSI_14")
    )

    macd = safe_float(
        latest.get("MACD")
    )

    macd_signal = safe_float(
        latest.get("MACD_SIGNAL")
    )

    relative_volume = safe_float(
        latest.get("RELATIVE_VOLUME")
    )

    high_52w = safe_float(
        latest.get("HIGH_52W")
    )

    # ========================================================
    # TREND — 25 POINTS
    # ========================================================

    trend_score = 0.0

    if (
        price is not None
        and ema20 is not None
        and price > ema20
    ):

        trend_score += 6.25

    if (
        ema20 is not None
        and ema50 is not None
        and ema20 > ema50
    ):

        trend_score += 6.25

    if (
        ema50 is not None
        and ema200 is not None
        and ema50 > ema200
    ):

        trend_score += 6.25

    if (
        price is not None
        and ema50 is not None
        and price > ema50
    ):

        trend_score += 6.25

    components["trend"] = round(
        trend_score,
        2,
    )

    score += trend_score

    # ========================================================
    # MOMENTUM — 25 POINTS
    # ========================================================

    momentum_score = 0.0

    # RSI
    if rsi is not None:

        if 55 <= rsi <= 70:

            momentum_score += 8

        elif 50 <= rsi < 55:

            momentum_score += 5

        elif 70 < rsi <= 80:

            momentum_score += 4

        elif 30 <= rsi < 50:

            momentum_score += 2

    # MACD
    if (
        macd is not None
        and macd_signal is not None
        and macd > macd_signal
    ):

        momentum_score += 9

    # 20D momentum
    if (
        stock_return_20d is not None
        and stock_return_20d > 0
    ):

        momentum_score += 4

    # 60D momentum
    if (
        stock_return_60d is not None
        and stock_return_60d > 0
    ):

        momentum_score += 4

    components["momentum"] = round(
        momentum_score,
        2,
    )

    score += momentum_score

    # ========================================================
    # VOLUME — 15 POINTS
    # ========================================================

    volume_score = 0.0

    if relative_volume is not None:

        if relative_volume >= 2.0:

            volume_score = 15

        elif relative_volume >= 1.5:

            volume_score = 12

        elif relative_volume >= 1.2:

            volume_score = 9

        elif relative_volume >= 1.0:

            volume_score = 6

        else:

            volume_score = 2

    components["volume"] = round(
        volume_score,
        2,
    )

    score += volume_score

    # ========================================================
    # RELATIVE STRENGTH — 20 POINTS
    # ========================================================

    relative_strength_score = 0.0

    if (
        stock_return_20d is not None
        and nifty_return_20d is not None
    ):

        relative_20d = (
            stock_return_20d
            - nifty_return_20d
        )

        if relative_20d >= 10:

            relative_strength_score += 12

        elif relative_20d >= 5:

            relative_strength_score += 10

        elif relative_20d >= 2:

            relative_strength_score += 7

        elif relative_20d >= 0:

            relative_strength_score += 4

    if (
        stock_return_60d is not None
        and nifty_return_60d is not None
    ):

        relative_60d = (
            stock_return_60d
            - nifty_return_60d
        )

        if relative_60d >= 15:

            relative_strength_score += 8

        elif relative_60d >= 7:

            relative_strength_score += 6

        elif relative_60d >= 2:

            relative_strength_score += 4

        elif relative_60d >= 0:

            relative_strength_score += 2

    components[
        "relative_strength"
    ] = round(
        relative_strength_score,
        2,
    )

    score += relative_strength_score

    # ========================================================
    # PRICE STRUCTURE — 15 POINTS
    # ========================================================

    structure_score = 0.0

    if (
        price is not None
        and high_52w is not None
        and high_52w > 0
    ):

        distance = (
            (
                high_52w
                - price
            )
            / high_52w
        ) * 100

        if distance <= 2:

            structure_score = 15

        elif distance <= 5:

            structure_score = 12

        elif distance <= 10:

            structure_score = 8

        elif distance <= 20:

            structure_score = 5

        else:

            structure_score = 2

    components["structure"] = round(
        structure_score,
        2,
    )

    score += structure_score

    return (
        round(
            min(
                score,
                100,
            ),
            2,
        ),
        components,
    )


# ============================================================
# ANALYZE ONE STOCK
# ============================================================

def analyze_stock_dataframe(
    symbol: str,
    data: pd.DataFrame,
    nifty_returns: dict,
) -> dict | None:
    """
    Calculate all scanner features for one stock.
    """

    if data is None or data.empty:

        return None

    try:

        # Need enough data for 200-day EMA.
        if len(data) < 210:

            return None

        indicators = (
            calculate_indicators(
                data
            )
        )

        if indicators.empty:

            return None

        close = pd.to_numeric(
            indicators["Close"],
            errors="coerce",
        ).dropna()

        if len(close) < 210:

            return None

        price = safe_float(
            close.iloc[-1]
        )

        if price is None:

            return None

        # ====================================================
        # 52 WEEK LEVELS
        # ====================================================

        recent_close = close.tail(
            min(
                252,
                len(close),
            )
        )

        high_52w = safe_float(
            recent_close.max()
        )

        low_52w = safe_float(
            recent_close.min()
        )

        indicators["HIGH_52W"] = high_52w
        indicators["LOW_52W"] = low_52w

        latest = indicators.iloc[-1]

        # ====================================================
        # RETURNS
        # ====================================================

        return_1d = calculate_return(
            close,
            1,
        )

        return_5d = calculate_return(
            close,
            5,
        )

        return_20d = calculate_return(
            close,
            20,
        )

        return_60d = calculate_return(
            close,
            60,
        )

        # ====================================================
        # MOVING AVERAGES
        # ====================================================

        ema20 = safe_float(
            latest["EMA_20"]
        )

        ema50 = safe_float(
            latest["EMA_50"]
        )

        ema200 = safe_float(
            latest["EMA_200"]
        )

        # ====================================================
        # MOMENTUM
        # ====================================================

        rsi = safe_float(
            latest["RSI_14"]
        )

        macd = safe_float(
            latest["MACD"]
        )

        macd_signal = safe_float(
            latest["MACD_SIGNAL"]
        )

        # ====================================================
        # VOLUME
        # ====================================================

        relative_volume = safe_float(
            latest["RELATIVE_VOLUME"]
        )

        volume = safe_float(
            latest["Volume"]
        )

        volume_average = safe_float(
            latest["VOLUME_AVG_20"]
        )

        # ====================================================
        # VOLATILITY
        # ====================================================

        atr = safe_float(
            latest["ATR_14"]
        )

        atr_percent = None

        if (
            atr is not None
            and price > 0
        ):

            atr_percent = (
                atr / price
            ) * 100

        # ====================================================
        # TREND
        # ====================================================

        if (
            ema20 is not None
            and ema50 is not None
            and ema200 is not None
        ):

            if (
                price > ema20
                and ema20 > ema50
                and ema50 > ema200
            ):

                trend = "STRONG_UPTREND"

            elif (
                price < ema20
                and ema20 < ema50
                and ema50 < ema200
            ):

                trend = "STRONG_DOWNTREND"

            elif price > ema50:

                trend = "UPTREND"

            elif price < ema50:

                trend = "DOWNTREND"

            else:

                trend = "SIDEWAYS"

        else:

            trend = "INSUFFICIENT_DATA"

        # ====================================================
        # RSI CONDITION
        # ====================================================

        if rsi is None:

            rsi_condition = "N/A"

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

        # ====================================================
        # MACD CONDITION
        # ====================================================

        if (
            macd is not None
            and macd_signal is not None
        ):

            if macd > macd_signal:

                macd_condition = "BULLISH"

            else:

                macd_condition = "BEARISH"

        else:

            macd_condition = "N/A"

        # ====================================================
        # VOLUME CONDITION
        # ====================================================

        if relative_volume is None:

            volume_condition = "N/A"

        elif relative_volume >= 2:

            volume_condition = "VERY_HIGH"

        elif relative_volume >= 1.5:

            volume_condition = "HIGH"

        elif relative_volume >= 1:

            volume_condition = "NORMAL"

        else:

            volume_condition = "LOW"

        # ====================================================
        # RELATIVE STRENGTH
        # ====================================================

        rs20 = None

        rs60 = None

        nifty20 = nifty_returns.get(
            "return_20d"
        )

        nifty60 = nifty_returns.get(
            "return_60d"
        )

        if (
            return_20d is not None
            and nifty20 is not None
        ):

            rs20 = (
                return_20d
                - nifty20
            )

        if (
            return_60d is not None
            and nifty60 is not None
        ):

            rs60 = (
                return_60d
                - nifty60
            )

        # ====================================================
        # 52W POSITION
        # ====================================================

        distance_high = None

        distance_low = None

        if (
            high_52w is not None
            and high_52w > 0
        ):

            distance_high = (
                (
                    high_52w
                    - price
                )
                / high_52w
            ) * 100

        if (
            low_52w is not None
            and low_52w > 0
        ):

            distance_low = (
                (
                    price
                    - low_52w
                )
                / low_52w
            ) * 100

        # ====================================================
        # 52W BREAKOUT / PROXIMITY
        # ====================================================

        near_52w_high = False

        if (
            high_52w is not None
            and price >= high_52w * 0.98
        ):

            near_52w_high = True

        # ====================================================
        # SCORE
        # ====================================================

        score, components = (
            calculate_score(
                latest,
                return_20d,
                return_60d,
                nifty20,
                nifty60,
            )
        )

        # ====================================================
        # TIMESTAMP
        # ====================================================

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

        # ====================================================
        # RESULT
        # ====================================================

        return {
            "symbol": symbol,

            "price": price,

            "return_1d": return_1d,

            "return_5d": return_5d,

            "return_20d": return_20d,

            "return_60d": return_60d,

            "nifty_return_20d": nifty20,

            "nifty_return_60d": nifty60,

            "relative_strength_20d": rs20,

            "relative_strength_60d": rs60,

            "ema_20": ema20,

            "ema_50": ema50,

            "ema_200": ema200,

            "rsi_14": rsi,

            "rsi_condition": rsi_condition,

            "macd": macd,

            "macd_signal": macd_signal,

            "macd_condition": macd_condition,

            "atr_14": atr,

            "atr_percent": atr_percent,

            "volume": volume,

            "volume_average_20": volume_average,

            "relative_volume": relative_volume,

            "volume_condition": volume_condition,

            "high_52w": high_52w,

            "low_52w": low_52w,

            "distance_52w_high": distance_high,

            "distance_52w_low": distance_low,

            "near_52w_high": near_52w_high,

            "trend": trend,

            "score": score,

            "trend_score": components[
                "trend"
            ],

            "momentum_score": components[
                "momentum"
            ],

            "volume_score": components[
                "volume"
            ],

            "relative_strength_score": (
                components[
                    "relative_strength"
                ]
            ),

            "structure_score": components[
                "structure"
            ],

            "timestamp": timestamp.isoformat(),
        }

    except Exception:

        return None


# ============================================================
# MARKET BREADTH
# ============================================================

def calculate_breadth(
    results: pd.DataFrame,
) -> dict:
    """
    Calculate market-wide breadth statistics.
    """

    if results.empty:

        return {
            "total": 0,
            "advancing": 0,
            "declining": 0,
            "unchanged": 0,
            "advance_decline_ratio": None,
            "above_ema20_percent": None,
            "above_ema50_percent": None,
            "above_ema200_percent": None,
            "strong_uptrend_percent": None,
            "strong_downtrend_percent": None,
        }

    total = len(
        results
    )

    advancing = int(
        (
            results["return_1d"]
            > 0
        ).sum()
    )

    declining = int(
        (
            results["return_1d"]
            < 0
        ).sum()
    )

    unchanged = (
        total
        - advancing
        - declining
    )

    if declining > 0:

        ad_ratio = (
            advancing
            / declining
        )

    else:

        ad_ratio = None

    above_ema20 = (
        (
            results["price"]
            > results["ema_20"]
        )
        .mean()
        * 100
    )

    above_ema50 = (
        (
            results["price"]
            > results["ema_50"]
        )
        .mean()
        * 100
    )

    above_ema200 = (
        (
            results["price"]
            > results["ema_200"]
        )
        .mean()
        * 100
    )

    strong_uptrend = (
        (
            results["trend"]
            == "STRONG_UPTREND"
        )
        .mean()
        * 100
    )

    strong_downtrend = (
        (
            results["trend"]
            == "STRONG_DOWNTREND"
        )
        .mean()
        * 100
    )

    return {
        "total": total,
        "advancing": advancing,
        "declining": declining,
        "unchanged": unchanged,
        "advance_decline_ratio": ad_ratio,
        "above_ema20_percent": above_ema20,
        "above_ema50_percent": above_ema50,
        "above_ema200_percent": above_ema200,
        "strong_uptrend_percent": strong_uptrend,
        "strong_downtrend_percent": strong_downtrend,
    }


# ============================================================
# MARKET REGIME
# ============================================================

def determine_market_regime(
    nifty_returns: dict,
    breadth: dict,
) -> str:
    """
    Determine broad market regime.

    This is NOT a trading signal.
    """

    score = 0

    return_20d = nifty_returns.get(
        "return_20d"
    )

    return_60d = nifty_returns.get(
        "return_60d"
    )

    above_ema50 = breadth.get(
        "above_ema50_percent"
    )

    above_ema200 = breadth.get(
        "above_ema200_percent"
    )

    # --------------------------------------------------------
    # NIFTY 20D
    # --------------------------------------------------------

    if return_20d is not None:

        if return_20d > 3:

            score += 2

        elif return_20d > 0:

            score += 1

        elif return_20d < -3:

            score -= 2

        else:

            score -= 1

    # --------------------------------------------------------
    # NIFTY 60D
    # --------------------------------------------------------

    if return_60d is not None:

        if return_60d > 5:

            score += 2

        elif return_60d > 0:

            score += 1

        elif return_60d < -5:

            score -= 2

        else:

            score -= 1

    # --------------------------------------------------------
    # EMA50 BREADTH
    # --------------------------------------------------------

    if above_ema50 is not None:

        if above_ema50 >= 60:

            score += 2

        elif above_ema50 >= 50:

            score += 1

        elif above_ema50 < 40:

            score -= 2

        else:

            score -= 1

    # --------------------------------------------------------
    # EMA200 BREADTH
    # --------------------------------------------------------

    if above_ema200 is not None:

        if above_ema200 >= 60:

            score += 2

        elif above_ema200 >= 50:

            score += 1

        elif above_ema200 < 40:

            score -= 2

        else:

            score -= 1

    # --------------------------------------------------------
    # CLASSIFICATION
    # --------------------------------------------------------

    if score >= 6:

        return "BULLISH"

    if score >= 2:

        return "MILDLY_BULLISH"

    if score <= -6:

        return "BEARISH"

    if score <= -2:

        return "MILDLY_BEARISH"

    return "NEUTRAL"


# ============================================================
# FULL MARKET SCAN
# ============================================================

def scan_market(
    limit: int | None = None,
) -> tuple[pd.DataFrame, dict]:
    """
    Scan the NSE EQ universe.

    limit:
        Used for testing.

        Example:
            --limit 100

        Full market:
            no limit
    """

    print()
    print("=" * 80)
    print("NOVA FULL NSE MARKET SCANNER")
    print("=" * 80)

    # ========================================================
    # LOAD NSE UNIVERSE
    # ========================================================

    symbols = get_nse_symbols(
        series="EQ"
    )

    if not symbols:

        raise RuntimeError(
            "No NSE EQ symbols found."
        )

    if limit is not None:

        symbols = symbols[
            :limit
        ]

    print()
    print(
        f"Universe: "
        f"{len(symbols):,} NSE EQ securities"
    )

    # ========================================================
    # LOAD NIFTY
    # ========================================================

    print()
    print(
        "Loading NIFTY 50 benchmark..."
    )

    nifty = download_nifty()

    nifty_returns = (
        calculate_nifty_returns(
            nifty
        )
    )

    print(
        f"NIFTY 1D : "
        f"{nifty_returns['return_1d']}"
    )

    print(
        f"NIFTY 5D : "
        f"{nifty_returns['return_5d']}"
    )

    print(
        f"NIFTY 20D: "
        f"{nifty_returns['return_20d']}"
    )

    print(
        f"NIFTY 60D: "
        f"{nifty_returns['return_60d']}"
    )

    # ========================================================
    # SCAN STOCKS
    # ========================================================

    results = []

    chunks = list(
        chunked(
            symbols,
            CHUNK_SIZE,
        )
    )

    total_chunks = len(
        chunks
    )

    print()
    print(
        f"Scanning in "
        f"{total_chunks} batches..."
    )

    for batch_number, chunk in enumerate(
        chunks,
        start=1,
    ):

        print(
            f"[{batch_number}/{total_chunks}] "
            f"Scanning "
            f"{len(chunk)} stocks..."
        )

        batch_data = download_chunk(
            chunk
        )

        if batch_data.empty:

            print(
                "    No data returned."
            )

            continue

        successful = 0

        for symbol in chunk:

            stock_data = (
                extract_stock(
                    batch_data,
                    symbol,
                )
            )

            if stock_data is None:

                continue

            result = (
                analyze_stock_dataframe(
                    symbol,
                    stock_data,
                    nifty_returns,
                )
            )

            if result is None:

                continue

            results.append(
                result
            )

            successful += 1

        print(
            f"    Processed: "
            f"{successful}/{len(chunk)}"
        )

        if batch_number < total_chunks:

            time.sleep(
                REQUEST_DELAY
            )

    # ========================================================
    # BUILD DATAFRAME
    # ========================================================

    dataframe = pd.DataFrame(
        results
    )

    if dataframe.empty:

        raise RuntimeError(
            "Scanner returned no usable stocks."
        )

    # ========================================================
    # CLEAN NUMERIC DATA
    # ========================================================

    numeric_columns = [
        "price",
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
        "nifty_return_20d",
        "nifty_return_60d",
        "relative_strength_20d",
        "relative_strength_60d",
        "ema_20",
        "ema_50",
        "ema_200",
        "rsi_14",
        "macd",
        "macd_signal",
        "atr_14",
        "atr_percent",
        "volume",
        "volume_average_20",
        "relative_volume",
        "high_52w",
        "low_52w",
        "distance_52w_high",
        "distance_52w_low",
        "score",
        "trend_score",
        "momentum_score",
        "volume_score",
        "relative_strength_score",
        "structure_score",
    ]

    for column in numeric_columns:

        if column in dataframe.columns:

            dataframe[column] = pd.to_numeric(
                dataframe[column],
                errors="coerce",
            )

    # ========================================================
    # REMOVE INVALID SCORES
    # ========================================================

    dataframe = dataframe[
        dataframe["score"].notna()
    ].copy()

    # ========================================================
    # RANK
    # ========================================================

    dataframe = dataframe.sort_values(
        "score",
        ascending=False,
    ).reset_index(
        drop=True
    )

    dataframe["rank"] = (
        dataframe.index + 1
    )

    # ========================================================
    # MARKET BREADTH
    # ========================================================

    breadth = calculate_breadth(
        dataframe
    )

    # ========================================================
    # MARKET REGIME
    # ========================================================

    market_regime = (
        determine_market_regime(
            nifty_returns,
            breadth,
        )
    )

    # ========================================================
    # MARKET SUMMARY
    # ========================================================

    summary = {
        "market_regime": market_regime,
        "nifty_returns": nifty_returns,
        "breadth": breadth,
        "stocks_in_universe": len(symbols),
        "stocks_analyzed": len(
            dataframe
        ),
        "timestamp": pd.Timestamp.now(
            tz="Asia/Kolkata"
        ).isoformat(),
    }

    # ========================================================
    # SAVE RESULTS
    # ========================================================

    timestamp = pd.Timestamp.now(
        tz="Asia/Kolkata"
    ).strftime(
        "%Y%m%d_%H%M%S"
    )

    output_file = (
        OUTPUT_DIR
        / f"market_scan_{timestamp}.csv"
    )

    dataframe.to_csv(
        output_file,
        index=False,
    )

    print()
    print("=" * 80)
    print("SCAN COMPLETE")
    print("=" * 80)

    print()
    print(
        f"Universe       : "
        f"{len(symbols):,}"
    )

    print(
        f"Stocks analyzed: "
        f"{len(dataframe):,}"
    )

    print(
        f"Market regime  : "
        f"{market_regime}"
    )

    print(
        f"Saved report   : "
        f"{output_file}"
    )

    return (
        dataframe,
        summary,
    )


# ============================================================
# REPORT HELPERS
# ============================================================

def print_table(
    dataframe: pd.DataFrame,
    columns: list[str],
    count: int,
) -> None:
    """
    Print a clean console table.
    """

    available = [
        column
        for column in columns
        if column in dataframe.columns
    ]

    if not available:

        print(
            "No data available."
        )

        return

    display = dataframe[
        available
    ].head(count)

    print(
        display.to_string(
            index=False,
            float_format=lambda value:
            f"{value:.2f}",
        )
    )


# ============================================================
# FULL MARKET REPORT
# ============================================================

def print_market_report(
    dataframe: pd.DataFrame,
    summary: dict,
    top: int = 20,
) -> None:
    """
    Print the complete market intelligence report.
    """

    print()
    print("=" * 100)
    print("NOVA MARKET INTELLIGENCE REPORT")
    print("=" * 100)

    # ========================================================
    # REGIME
    # ========================================================

    print()
    print(
        f"MARKET REGIME: "
        f"{summary['market_regime']}"
    )

    print(
        f"Stocks analyzed: "
        f"{summary['stocks_analyzed']:,}"
    )

    print(
        f"Timestamp: "
        f"{summary['timestamp']}"
    )

    # ========================================================
    # NIFTY
    # ========================================================

    nifty = summary[
        "nifty_returns"
    ]

    print()
    print("NIFTY BENCHMARK")
    print("-" * 100)

    print(
        f"1D : {nifty['return_1d']}"
    )

    print(
        f"5D : {nifty['return_5d']}"
    )

    print(
        f"20D: {nifty['return_20d']}"
    )

    print(
        f"60D: {nifty['return_60d']}"
    )

    # ========================================================
    # BREADTH
    # ========================================================

    breadth = summary[
        "breadth"
    ]

    print()
    print("MARKET BREADTH")
    print("-" * 100)

    print(
        f"Advancing stocks       : "
        f"{breadth['advancing']:,}"
    )

    print(
        f"Declining stocks       : "
        f"{breadth['declining']:,}"
    )

    print(
        f"Unchanged              : "
        f"{breadth['unchanged']:,}"
    )

    if (
        breadth[
            "advance_decline_ratio"
        ]
        is not None
    ):

        print(
            f"Advance/Decline ratio  : "
            f"{breadth['advance_decline_ratio']:.2f}"
        )

    print(
        f"Above EMA20            : "
        f"{breadth['above_ema20_percent']:.2f}%"
    )

    print(
        f"Above EMA50            : "
        f"{breadth['above_ema50_percent']:.2f}%"
    )

    print(
        f"Above EMA200           : "
        f"{breadth['above_ema200_percent']:.2f}%"
    )

    print(
        f"Strong uptrend         : "
        f"{breadth['strong_uptrend_percent']:.2f}%"
    )

    print(
        f"Strong downtrend       : "
        f"{breadth['strong_downtrend_percent']:.2f}%"
    )

    # ========================================================
    # TOP TECHNICAL RANKINGS
    # ========================================================

    print()
    print(
        f"TOP {top} TECHNICAL RANKINGS"
    )

    print("-" * 100)

    print_table(
        dataframe,
        [
            "rank",
            "symbol",
            "price",
            "score",
            "trend",
            "rsi_14",
            "relative_volume",
            "return_20d",
            "return_60d",
            "relative_strength_20d",
            "near_52w_high",
        ],
        top,
    )

    # ========================================================
    # TOP MOMENTUM
    # ========================================================

    print()
    print(
        f"TOP {top} MOMENTUM STOCKS"
    )

    print("-" * 100)

    momentum = dataframe.sort_values(
        [
            "return_20d",
            "return_60d",
            "score",
        ],
        ascending=False,
    )

    print_table(
        momentum,
        [
            "symbol",
            "price",
            "score",
            "return_5d",
            "return_20d",
            "return_60d",
            "rsi_14",
            "macd_condition",
            "trend",
        ],
        top,
    )

    # ========================================================
    # TOP RELATIVE STRENGTH
    # ========================================================

    print()
    print(
        f"TOP {top} RELATIVE STRENGTH"
    )

    print("-" * 100)

    relative_strength = (
        dataframe
        .sort_values(
            [
                "relative_strength_20d",
                "relative_strength_60d",
            ],
            ascending=False,
        )
    )

    print_table(
        relative_strength,
        [
            "symbol",
            "price",
            "score",
            "relative_strength_20d",
            "relative_strength_60d",
            "return_20d",
            "return_60d",
            "trend",
        ],
        top,
    )

    # ========================================================
    # VOLUME EXPANSION
    # ========================================================

    print()
    print(
        f"TOP {top} VOLUME EXPANSION"
    )

    print("-" * 100)

    volume = dataframe.sort_values(
        [
            "relative_volume",
            "score",
        ],
        ascending=False,
    )

    print_table(
        volume,
        [
            "symbol",
            "price",
            "relative_volume",
            "volume_condition",
            "score",
            "return_1d",
            "rsi_14",
            "trend",
        ],
        top,
    )

    # ========================================================
    # 52 WEEK HIGH PROXIMITY
    # ========================================================

    print()
    print(
        f"TOP {top} 52-WEEK HIGH PROXIMITY"
    )

    print("-" * 100)

    near_high = dataframe.sort_values(
        "distance_52w_high",
        ascending=True,
    )

    print_table(
        near_high,
        [
            "symbol",
            "price",
            "high_52w",
            "distance_52w_high",
            "relative_volume",
            "rsi_14",
            "score",
            "trend",
        ],
        top,
    )

    # ========================================================
    # STRONG UPTRENDS
    # ========================================================

    print()
    print(
        f"TOP {top} STRONG UPTRENDS"
    )

    print("-" * 100)

    uptrends = dataframe[
        dataframe["trend"]
        == "STRONG_UPTREND"
    ].sort_values(
        "score",
        ascending=False,
    )

    print_table(
        uptrends,
        [
            "symbol",
            "price",
            "score",
            "ema_20",
            "ema_50",
            "ema_200",
            "rsi_14",
            "relative_volume",
            "return_20d",
        ],
        top,
    )

    # ========================================================
    # HIGH-CONVICTION TECHNICAL CANDIDATES
    # ========================================================

    print()
    print(
        "HIGH-QUALITY TECHNICAL CANDIDATES"
    )

    print("-" * 100)

    candidates = dataframe[
        (
            dataframe["score"]
            >= 80
        )
        &
        (
            dataframe["trend"]
            .isin(
                [
                    "STRONG_UPTREND",
                    "UPTREND",
                ]
            )
        )
        &
        (
            dataframe["rsi_14"]
            >= 50
        )
        &
        (
            dataframe["macd_condition"]
            == "BULLISH"
        )
    ].sort_values(
        "score",
        ascending=False,
    )

    print_table(
        candidates,
        [
            "symbol",
            "price",
            "score",
            "trend",
            "rsi_14",
            "relative_volume",
            "return_20d",
            "return_60d",
            "relative_strength_20d",
            "distance_52w_high",
        ],
        top,
    )

    # ========================================================
    # WARNINGS
    # ========================================================

    print()
    print("=" * 100)
    print("IMPORTANT")
    print("=" * 100)

    print(
        "Technical score is a ranking metric, "
        "NOT a BUY/SELL signal."
    )

    print(
        "The final Nova institutional decision "
        "engine will additionally require:"
    )

    print(
        "Market regime + breadth + volatility + "
        "sector strength + derivatives + risk."
    )

    print()
    print("=" * 100)


# ============================================================
# COMMAND LINE
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description=(
            "Nova Full NSE Market Scanner"
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limit stocks for testing. "
            "Omit for the full NSE universe."
        ),
    )

    parser.add_argument(
        "--top",
        type=int,
        default=20,
        help=(
            "Number of stocks displayed "
            "per ranking section."
        ),
    )

    args = parser.parse_args()

    dataframe, summary = scan_market(
        limit=args.limit
    )

    print_market_report(
        dataframe,
        summary,
        top=args.top,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()