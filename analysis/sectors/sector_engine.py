"""
Nova Sector Rotation Engine

Purpose
-------
Analyze Indian equity sector leadership relative to NIFTY.

This module is an ANALYSIS layer.
It does NOT generate BUY/SELL orders.

Research principles incorporated:
- Multi-horizon momentum
- Relative strength versus benchmark
- Volatility-aware analysis
- No look-ahead
- Market-regime context
- Ranking rather than unconditional prediction

Research basis:
- Moskowitz, Ooi & Pedersen:
  time-series momentum and volatility scaling
- Gu, Kelly & Xiu:
  high-dimensional prediction requires validation
  and should not be treated as economic truth
- Indian factor research:
  factor performance requires out-of-sample validation

Important:
Sector scores below are engineering/ranking scores.
They are NOT empirically validated predictive probabilities.
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf


# ============================================================
# CONFIGURATION
# ============================================================

BENCHMARK = "^NSEI"

PERIOD = "1y"
INTERVAL = "1d"

# Core NSE/Nifty sectoral benchmarks available through Yahoo Finance.
SECTORS: Dict[str, str] = {
    "AUTO": "^CNXAUTO",
    "BANK": "^NSEBANK",
    "FINANCIAL_SERVICES": "^CNXFINANCE",
    "FMCG": "^CNXFMCG",
    "IT": "^CNXIT",
    "MEDIA": "^CNXMEDIA",
    "METAL": "^CNXMETAL",
    "PHARMA": "^CNXPHARMA",
    "PRIVATE_BANK": "^CNXPVTBANK",
    "PSU_BANK": "^CNXPSUBANK",
    "REALTY": "^CNXREALTY",
    "OIL_GAS": "^CNXOILGAS",
    "HEALTHCARE": "^CNXHEALTHCARE",
}


# ============================================================
# DATA STRUCTURE
# ============================================================

@dataclass
class SectorResult:
    sector: str
    yahoo_symbol: str

    price: float

    ema20: float
    ema50: float
    ema200: float

    trend: str

    return_1d: float
    return_5d: float
    return_20d: float
    return_60d: float

    benchmark_return_20d: float
    benchmark_return_60d: float

    relative_strength_20d: float
    relative_strength_60d: float

    volatility_20d: float
    volatility_60d: float

    volatility_ratio: float

    score: float
    classification: str


# ============================================================
# DATA DOWNLOAD
# ============================================================

def download_history(symbol: str) -> pd.DataFrame:
    """
    Download historical daily OHLCV data.

    Only historical observations are used.
    No future observations are introduced into calculations.
    """

    df = yf.download(
        symbol,
        period=PERIOD,
        interval=INTERVAL,
        auto_adjust=False,
        progress=False,
        threads=False,
    )

    if df is None or df.empty:
        raise RuntimeError(f"No data returned for {symbol}")

    # yfinance can return MultiIndex columns.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required = ["Close"]

    for column in required:
        if column not in df.columns:
            raise RuntimeError(
                f"Missing {column} column for {symbol}"
            )

    df = df.copy()

    for column in ["Open", "High", "Low", "Close", "Volume"]:
        if column in df.columns:
            df[column] = pd.to_numeric(
                df[column],
                errors="coerce"
            )

    df = df.dropna(subset=["Close"])

    return df


# ============================================================
# BASIC CALCULATIONS
# ============================================================

def calculate_returns(
    close: pd.Series,
) -> Dict[str, float]:
    """
    Multi-horizon returns.

    Horizons:
    1D
    5D
    20D
    60D
    """

    result = {}

    for name, periods in {
        "1d": 1,
        "5d": 5,
        "20d": 20,
        "60d": 60,
    }.items():

        if len(close) <= periods:
            result[name] = np.nan
            continue

        current = float(close.iloc[-1])
        previous = float(close.iloc[-periods - 1])

        if previous == 0:
            result[name] = np.nan
        else:
            result[name] = (
                current / previous - 1.0
            ) * 100.0

    return result


def calculate_ema(
    close: pd.Series,
    period: int,
) -> float:

    if len(close) < period:
        return np.nan

    ema = close.ewm(
        span=period,
        adjust=False
    ).mean()

    return float(ema.iloc[-1])


def calculate_realized_volatility(
    close: pd.Series,
    window: int,
) -> float:
    """
    Annualized realized volatility.

    Uses lagged historical returns only.
    """

    returns = close.pct_change().dropna()

    if len(returns) < window:
        return np.nan

    recent = returns.iloc[-window:]

    volatility = recent.std(ddof=1)

    if pd.isna(volatility):
        return np.nan

    return float(
        volatility * math.sqrt(252) * 100.0
    )


# ============================================================
# TREND
# ============================================================

def determine_trend(
    price: float,
    ema20: float,
    ema50: float,
    ema200: float,
) -> str:

    if any(
        pd.isna(value)
        for value in [
            price,
            ema20,
            ema50,
            ema200,
        ]
    ):
        return "UNKNOWN"

    if (
        price > ema20
        and ema20 > ema50
        and ema50 > ema200
    ):
        return "STRONG_UPTREND"

    if (
        price > ema50
        and ema50 > ema200
    ):
        return "UPTREND"

    if (
        price < ema20
        and ema20 < ema50
        and ema50 < ema200
    ):
        return "STRONG_DOWNTREND"

    if (
        price < ema50
        and ema50 < ema200
    ):
        return "DOWNTREND"

    return "MIXED"


# ============================================================
# RELATIVE STRENGTH
# ============================================================

def calculate_relative_strength(
    sector_return: float,
    benchmark_return: float,
) -> float:

    if pd.isna(sector_return) or pd.isna(
        benchmark_return
    ):
        return np.nan

    return sector_return - benchmark_return


# ============================================================
# SCORE COMPONENTS
# ============================================================

def score_trend(
    trend: str,
) -> float:

    mapping = {
        "STRONG_UPTREND": 100.0,
        "UPTREND": 80.0,
        "MIXED": 50.0,
        "DOWNTREND": 20.0,
        "STRONG_DOWNTREND": 0.0,
        "UNKNOWN": 50.0,
    }

    return mapping.get(trend, 50.0)


def score_momentum(
    return_20d: float,
    return_60d: float,
) -> float:

    if pd.isna(return_20d):
        return 50.0

    if pd.isna(return_60d):
        return 50.0

    # Engineering ranking score.
    #
    # This is deliberately not interpreted as
    # a probability of future returns.

    short_score = np.clip(
        50.0 + return_20d * 5.0,
        0.0,
        100.0,
    )

    medium_score = np.clip(
        50.0 + return_60d * 2.5,
        0.0,
        100.0,
    )

    return float(
        0.60 * short_score
        + 0.40 * medium_score
    )


def score_relative_strength(
    rs20: float,
    rs60: float,
) -> float:

    if pd.isna(rs20) or pd.isna(rs60):
        return 50.0

    short_score = np.clip(
        50.0 + rs20 * 5.0,
        0.0,
        100.0,
    )

    medium_score = np.clip(
        50.0 + rs60 * 2.5,
        0.0,
        100.0,
    )

    return float(
        0.60 * short_score
        + 0.40 * medium_score
    )


def score_medium_term(
    return_60d: float,
) -> float:

    if pd.isna(return_60d):
        return 50.0

    return float(
        np.clip(
            50.0 + return_60d * 2.5,
            0.0,
            100.0,
        )
    )


def score_volatility_quality(
    volatility_20d: float,
    volatility_60d: float,
    relative_strength_20d: float,
) -> float:

    if (
        pd.isna(volatility_20d)
        or pd.isna(volatility_60d)
    ):
        return 50.0

    if volatility_60d <= 0:
        return 50.0

    vol_ratio = (
        volatility_20d
        / volatility_60d
    )

    # Moderate volatility expansion combined
    # with positive relative strength can indicate
    # active leadership.
    #
    # Extreme volatility is penalized.

    score = 60.0

    if relative_strength_20d > 0:
        score += 15.0

    if 0.85 <= vol_ratio <= 1.20:
        score += 15.0

    elif vol_ratio > 1.50:
        score -= 20.0

    elif vol_ratio < 0.60:
        score -= 5.0

    return float(
        np.clip(score, 0.0, 100.0)
    )


# ============================================================
# SECTOR ANALYSIS
# ============================================================

def analyze_sector(
    sector: str,
    symbol: str,
    benchmark: pd.DataFrame,
) -> SectorResult:

    df = download_history(symbol)

    close = df["Close"].dropna()

    benchmark_close = benchmark[
        "Close"
    ].dropna()

    if len(close) < 200:
        raise RuntimeError(
            f"Insufficient history for {sector}"
        )

    price = float(close.iloc[-1])

    ema20 = calculate_ema(close, 20)
    ema50 = calculate_ema(close, 50)
    ema200 = calculate_ema(close, 200)

    trend = determine_trend(
        price,
        ema20,
        ema50,
        ema200,
    )

    returns = calculate_returns(close)

    benchmark_returns = calculate_returns(
        benchmark_close
    )

    rs20 = calculate_relative_strength(
        returns["20d"],
        benchmark_returns["20d"],
    )

    rs60 = calculate_relative_strength(
        returns["60d"],
        benchmark_returns["60d"],
    )

    volatility20 = (
        calculate_realized_volatility(
            close,
            20,
        )
    )

    volatility60 = (
        calculate_realized_volatility(
            close,
            60,
        )
    )

    if (
        pd.isna(volatility60)
        or volatility60 == 0
    ):
        volatility_ratio = np.nan

    else:
        volatility_ratio = (
            volatility20
            / volatility60
        )

    # --------------------------------------------------------
    # COMPONENT SCORES
    # --------------------------------------------------------

    trend_score = score_trend(trend)

    momentum_score = score_momentum(
        returns["20d"],
        returns["60d"],
    )

    relative_strength_score = (
        score_relative_strength(
            rs20,
            rs60,
        )
    )

    medium_term_score = (
        score_medium_term(
            returns["60d"]
        )
    )

    volatility_quality_score = (
        score_volatility_quality(
            volatility20,
            volatility60,
            rs20,
        )
    )

    # --------------------------------------------------------
    # FINAL SECTOR SCORE
    # --------------------------------------------------------

    score = (
        trend_score * 0.25
        + momentum_score * 0.25
        + relative_strength_score * 0.25
        + medium_term_score * 0.15
        + volatility_quality_score * 0.10
    )

    score = float(
        np.clip(score, 0.0, 100.0)
    )

    if score >= 80:
        classification = "LEADING"

    elif score >= 65:
        classification = "STRONG"

    elif score >= 50:
        classification = "NEUTRAL"

    elif score >= 35:
        classification = "WEAK"

    else:
        classification = "LAGGING"

    return SectorResult(
        sector=sector,
        yahoo_symbol=symbol,
        price=price,
        ema20=ema20,
        ema50=ema50,
        ema200=ema200,
        trend=trend,
        return_1d=returns["1d"],
        return_5d=returns["5d"],
        return_20d=returns["20d"],
        return_60d=returns["60d"],
        benchmark_return_20d=benchmark_returns["20d"],
        benchmark_return_60d=benchmark_returns["60d"],
        relative_strength_20d=rs20,
        relative_strength_60d=rs60,
        volatility_20d=volatility20,
        volatility_60d=volatility60,
        volatility_ratio=volatility_ratio,
        score=score,
        classification=classification,
    )


# ============================================================
# MARKET-WIDE ROTATION
# ============================================================

def classify_rotation_environment(
    results: List[SectorResult],
) -> str:

    if not results:
        return "UNKNOWN"

    strong_count = sum(
        result.classification in {
            "LEADING",
            "STRONG",
        }
        for result in results
    )

    ratio = (
        strong_count
        / len(results)
    )

    if ratio >= 0.60:
        return "BROAD_SECTOR_RISK_ON"

    if ratio >= 0.40:
        return "SELECTIVE_SECTOR_ROTATION"

    if ratio >= 0.20:
        return "DEFENSIVE_NARROW_LEADERSHIP"

    return "BROAD_SECTOR_RISK_OFF"


# ============================================================
# REPORT
# ============================================================

def print_report(
    results: List[SectorResult],
    benchmark_return_20d: float,
    benchmark_return_60d: float,
):

    results = sorted(
        results,
        key=lambda x: x.score,
        reverse=True,
    )

    environment = (
        classify_rotation_environment(
            results
        )
    )

    print()
    print("=" * 95)
    print("NOVA SECTOR ROTATION ENGINE")
    print("=" * 95)

    print()
    print("BENCHMARK")
    print("-" * 95)

    print(
        f"NIFTY 20D Return : "
        f"{benchmark_return_20d:>8.2f}%"
    )

    print(
        f"NIFTY 60D Return : "
        f"{benchmark_return_60d:>8.2f}%"
    )

    print()
    print("SECTOR ENVIRONMENT")
    print("-" * 95)

    print(
        f"Environment       : "
        f"{environment}"
    )

    print()
    print("SECTOR RANKING")
    print("-" * 95)

    header = (
        f"{'Rank':<5}"
        f"{'Sector':<22}"
        f"{'Score':>8}"
        f"{'Class':<12}"
        f"{'20D':>9}"
        f"{'60D':>9}"
        f"{'RS20':>9}"
        f"{'RS60':>9}"
        f"{'Trend':<20}"
    )

    print(header)
    print("-" * 95)

    for rank, result in enumerate(
        results,
        start=1,
    ):

        print(
            f"{rank:<5}"
            f"{result.sector:<22}"
            f"{result.score:>8.2f}"
            f"{result.classification:<12}"
            f"{result.return_20d:>8.2f}%"
            f"{result.return_60d:>8.2f}%"
            f"{result.relative_strength_20d:>8.2f}%"
            f"{result.relative_strength_60d:>8.2f}%"
            f"{result.trend:<20}"
        )

    leaders = [
        result
        for result in results
        if result.classification
        in {"LEADING", "STRONG"}
    ]

    laggards = [
        result
        for result in results
        if result.classification
        in {"WEAK", "LAGGING"}
    ]

    print()
    print("SECTOR LEADERS")
    print("-" * 95)

    if leaders:
        for result in leaders[:5]:
            print(
                f"{result.sector:<25}"
                f"score={result.score:>6.2f}  "
                f"RS20={result.relative_strength_20d:>6.2f}%  "
                f"RS60={result.relative_strength_60d:>6.2f}%"
            )

    else:
        print("No strong sector leaders.")

    print()
    print("SECTOR LAGGARDS")
    print("-" * 95)

    if laggards:
        for result in laggards[:5]:
            print(
                f"{result.sector:<25}"
                f"score={result.score:>6.2f}  "
                f"RS20={result.relative_strength_20d:>6.2f}%  "
                f"RS60={result.relative_strength_60d:>6.2f}%"
            )

    else:
        print("No significant sector laggards.")

    print()
    print("=" * 95)
    print("IMPORTANT")
    print("=" * 95)

    print(
        "Sector score is a ranking metric, "
        "NOT a BUY/SELL signal."
    )

    print(
        "Relative strength does not prove future "
        "outperformance."
    )

    print(
        "Thresholds are Nova engineering decisions "
        "and require historical/OOS validation."
    )

    print(
        "Sector analysis must eventually be combined "
        "with market regime, flows, derivatives, "
        "stock factors and risk."
    )

    print("=" * 95)


# ============================================================
# ENGINE ENTRY POINT
# ============================================================

def run_sector_engine() -> List[SectorResult]:

    print(
        "Downloading NIFTY benchmark..."
    )

    benchmark = download_history(
        BENCHMARK
    )

    benchmark_returns = calculate_returns(
        benchmark["Close"].dropna()
    )

    results: List[SectorResult] = []

    for sector, symbol in SECTORS.items():

        print(
            f"Analyzing {sector:<22} "
            f"{symbol}"
        )

        try:

            result = analyze_sector(
                sector,
                symbol,
                benchmark,
            )

            results.append(result)

        except Exception as exc:

            print(
                f"WARNING: {sector} failed: "
                f"{exc}"
            )

    print_report(
        results,
        benchmark_returns["20d"],
        benchmark_returns["60d"],
    )

    return results


def main():

    parser = argparse.ArgumentParser(
        description=(
            "Nova Sector Rotation Engine"
        )
    )

    parser.parse_args()

    run_sector_engine()


if __name__ == "__main__":
    main()