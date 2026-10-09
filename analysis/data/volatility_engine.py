"""
Nova Volatility Engine v1

Measures observable market volatility.

Capabilities
------------
- India VIX
- NIFTY realized volatility
- BANK NIFTY realized volatility
- ATR(14)
- ATR %
- 20D / 60D annualized realized volatility
- Historical volatility percentile
- Expected daily move
- Expected daily range
- Volatility regime
- Volatility expansion / contraction

Does NOT provide:
- Option implied volatility
- IV percentile
- Option OI
- PCR
- Max pain
- Options volatility surface

Those belong to the Derivatives Engine.

No trading execution is performed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


TRADING_DAYS = 252

INSTRUMENTS = {
    "NIFTY": "^NSEI",
    "BANK_NIFTY": "^NSEBANK",
    "INDIA_VIX": "^INDIAVIX",
}


class VolatilityEngineError(Exception):
    """Raised when the volatility engine cannot produce valid data."""


@dataclass
class VolatilityResult:
    symbol: str
    price: float | None
    atr_14: float | None
    atr_percent: float | None
    realized_vol_20d: float | None
    realized_vol_60d: float | None
    volatility_percentile: float | None
    expected_daily_move_percent: float | None
    expected_daily_range: float | None
    volatility_regime: str
    volatility_direction: str
    data_timestamp: str | None


def _safe_float(
    value: Any,
    default: float | None = None,
) -> float | None:
    """Safely convert a value to float."""

    try:
        if value is None:
            return default

        if pd.isna(value):
            return default

        result = float(value)

        if not np.isfinite(result):
            return default

        return result

    except (TypeError, ValueError):
        return default


def _clean_downloaded_data(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Normalize yfinance output.

    Handles normal and MultiIndex columns.
    """

    if dataframe is None or dataframe.empty:
        return pd.DataFrame()

    df = dataframe.copy()

    if isinstance(df.columns, pd.MultiIndex):

        flattened = []

        for column in df.columns:

            if isinstance(column, tuple):
                flattened.append(column[0])
            else:
                flattened.append(column)

        df.columns = flattened

        df = df.loc[
            :,
            ~df.columns.duplicated(),
        ]

    required = [
        "Open",
        "High",
        "Low",
        "Close",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    if missing:
        return pd.DataFrame()

    for column in required:

        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "High",
            "Low",
            "Close",
        ]
    )

    return df


def download_history(
    ticker: str,
    period: str = "2y",
) -> pd.DataFrame:
    """Download daily OHLC data from Yahoo Finance."""

    try:

        data = yf.download(
            ticker,
            period=period,
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=False,
        )

    except Exception as exc:

        raise VolatilityEngineError(
            f"Failed to download {ticker}: {exc}"
        ) from exc

    data = _clean_downloaded_data(data)

    if data.empty:

        raise VolatilityEngineError(
            f"No usable historical data returned for {ticker}."
        )

    return data


def calculate_true_range(
    dataframe: pd.DataFrame,
) -> pd.Series:
    """Calculate daily True Range."""

    high = dataframe["High"]
    low = dataframe["Low"]
    close = dataframe["Close"]

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


def calculate_atr(
    dataframe: pd.DataFrame,
    period: int = 14,
) -> pd.Series:
    """Calculate simple rolling ATR."""

    true_range = calculate_true_range(
        dataframe
    )

    return true_range.rolling(
        window=period,
        min_periods=period,
    ).mean()


def calculate_realized_volatility(
    dataframe: pd.DataFrame,
    window: int,
) -> pd.Series:
    """
    Calculate annualized realized volatility.

    Formula:

        std(log returns) × sqrt(252)

    Output is decimal form.

    Example:

        0.20 = 20% annualized volatility
    """

    close = dataframe["Close"]

    log_returns = np.log(
        close / close.shift(1)
    )

    return (
        log_returns
        .rolling(
            window=window,
            min_periods=window,
        )
        .std()
        * np.sqrt(TRADING_DAYS)
    )


def calculate_volatility_percentile(
    series: pd.Series,
    lookback: int = 252,
) -> pd.Series:
    """
    Calculate rolling historical percentile.

    Output:
        0 to 100
    """

    def percentile_rank(
        window: pd.Series,
    ) -> float:

        clean = window.dropna()

        if len(clean) < 20:
            return np.nan

        current = clean.iloc[-1]

        return (
            clean.le(current).sum()
            / len(clean)
            * 100.0
        )

    return series.rolling(
        window=lookback,
        min_periods=20,
    ).apply(
        percentile_rank,
        raw=False,
    )


def classify_volatility_regime(
    realized_vol_20d: float | None,
    volatility_percentile: float | None,
) -> str:
    """
    Classify volatility using:

    1. Historical percentile
    2. Absolute realized volatility as fallback

    This is descriptive only.
    It is NOT a trading signal.
    """

    if realized_vol_20d is None:
        return "UNKNOWN"

    percentile = volatility_percentile

    if percentile is not None:

        if percentile >= 90:
            return "EXTREME"

        if percentile >= 75:
            return "ELEVATED"

        if percentile >= 40:
            return "MODERATE"

        return "LOW"

    # Fallback if percentile unavailable.

    if realized_vol_20d >= 0.35:
        return "EXTREME"

    if realized_vol_20d >= 0.25:
        return "ELEVATED"

    if realized_vol_20d >= 0.15:
        return "MODERATE"

    return "LOW"


def classify_volatility_direction(
    realized_vol_20d_series: pd.Series,
) -> str:
    """
    Classify volatility direction.

    EXPANDING:
        volatility increased by >= 10%

    CONTRACTING:
        volatility decreased by >= 10%

    STABLE:
        otherwise
    """

    clean = (
        realized_vol_20d_series
        .dropna()
    )

    if len(clean) < 10:
        return "UNKNOWN"

    current = float(
        clean.iloc[-1]
    )

    previous = float(
        clean.iloc[-6]
    )

    if previous <= 0:
        return "UNKNOWN"

    change = (
        current - previous
    ) / previous

    if change >= 0.10:
        return "EXPANDING"

    if change <= -0.10:
        return "CONTRACTING"

    return "STABLE"


def analyze_instrument(
    symbol: str,
    ticker: str,
    period: str = "2y",
) -> VolatilityResult:
    """Generate volatility analysis for one instrument."""

    dataframe = download_history(
        ticker,
        period=period,
    )

    if len(dataframe) < 60:

        raise VolatilityEngineError(
            f"Insufficient history for {symbol}: "
            f"{len(dataframe)} rows."
        )

    atr = calculate_atr(
        dataframe,
        period=14,
    )

    realized_20 = (
        calculate_realized_volatility(
            dataframe,
            window=20,
        )
    )

    realized_60 = (
        calculate_realized_volatility(
            dataframe,
            window=60,
        )
    )

    percentile_series = (
        calculate_volatility_percentile(
            realized_20,
            lookback=252,
        )
    )

    current_price = _safe_float(
        dataframe["Close"].iloc[-1]
    )

    current_atr = _safe_float(
        atr.iloc[-1]
    )

    atr_percent = None

    if (
        current_atr is not None
        and current_price is not None
        and current_price != 0
    ):

        atr_percent = (
            current_atr
            / current_price
            * 100.0
        )

    current_realized_20 = (
        _safe_float(
            realized_20.iloc[-1]
        )
    )

    current_realized_60 = (
        _safe_float(
            realized_60.iloc[-1]
        )
    )

    current_percentile = (
        _safe_float(
            percentile_series.iloc[-1]
        )
    )

    expected_daily_move_percent = None

    if current_realized_20 is not None:

        expected_daily_move_percent = (
            current_realized_20
            / np.sqrt(TRADING_DAYS)
            * 100.0
        )

    expected_daily_range = None

    if (
        current_price is not None
        and expected_daily_move_percent is not None
    ):

        expected_daily_range = (
            current_price
            * expected_daily_move_percent
            / 100.0
        )

    regime = classify_volatility_regime(
        current_realized_20,
        current_percentile,
    )

    direction = (
        classify_volatility_direction(
            realized_20
        )
    )

    timestamp = None

    try:

        timestamp = (
            dataframe.index[-1]
            .to_pydatetime()
            .astimezone()
            .isoformat()
        )

    except Exception:

        timestamp = str(
            dataframe.index[-1]
        )

    return VolatilityResult(
        symbol=symbol,
        price=current_price,
        atr_14=current_atr,
        atr_percent=atr_percent,
        realized_vol_20d=current_realized_20,
        realized_vol_60d=current_realized_60,
        volatility_percentile=current_percentile,
        expected_daily_move_percent=(
            expected_daily_move_percent
        ),
        expected_daily_range=(
            expected_daily_range
        ),
        volatility_regime=regime,
        volatility_direction=direction,
        data_timestamp=timestamp,
    )


def get_india_vix(
    period: str = "2y",
) -> dict[str, Any]:
    """Get India VIX and historical positioning."""

    dataframe = download_history(
        INSTRUMENTS["INDIA_VIX"],
        period=period,
    )

    close = dataframe["Close"]

    percentile_series = (
        close.rolling(
            window=252,
            min_periods=20,
        ).apply(
            lambda window: (
                window <= window.iloc[-1]
            ).sum()
            / len(window)
            * 100.0
        )
    )

    current_vix = _safe_float(
        close.iloc[-1]
    )

    previous_vix = None

    if len(close) >= 2:

        previous_vix = _safe_float(
            close.iloc[-2]
        )

    change_percent = None

    if (
        current_vix is not None
        and previous_vix is not None
        and previous_vix != 0
    ):

        change_percent = (
            (
                current_vix
                - previous_vix
            )
            / previous_vix
            * 100.0
        )

    percentile = _safe_float(
        percentile_series.iloc[-1]
    )

    # Absolute VIX classification.

    if current_vix is None:

        absolute_regime = "UNKNOWN"

    elif current_vix >= 25:

        absolute_regime = "EXTREME"

    elif current_vix >= 20:

        absolute_regime = "HIGH"

    elif current_vix >= 15:

        absolute_regime = "MODERATE"

    else:

        absolute_regime = "LOW"

    # Historical positioning.

    if percentile is None:

        historical_position = "UNKNOWN"

    elif percentile >= 90:

        historical_position = "EXTREME"

    elif percentile >= 75:

        historical_position = "ELEVATED"

    elif percentile >= 40:

        historical_position = "MODERATE"

    else:

        historical_position = "LOW"

    # Direction.

    if change_percent is None:

        direction = "UNKNOWN"

    elif change_percent >= 5:

        direction = "RISING"

    elif change_percent <= -5:

        direction = "FALLING"

    else:

        direction = "STABLE"

    timestamp = None

    try:

        timestamp = (
            dataframe.index[-1]
            .to_pydatetime()
            .astimezone()
            .isoformat()
        )

    except Exception:

        timestamp = str(
            dataframe.index[-1]
        )

    return {
        "value": current_vix,
        "previous_value": previous_vix,
        "change_percent": change_percent,
        "percentile_1y": percentile,
        "absolute_regime": absolute_regime,
        "historical_position": historical_position,
        "direction": direction,
        "data_timestamp": timestamp,
        "source": "Yahoo Finance",
    }


def get_market_volatility_snapshot() -> dict[str, Any]:
    """Generate the complete Market Lab volatility snapshot."""

    nifty = analyze_instrument(
        "NIFTY",
        INSTRUMENTS["NIFTY"],
    )

    bank_nifty = analyze_instrument(
        "BANK_NIFTY",
        INSTRUMENTS["BANK_NIFTY"],
    )

    india_vix = get_india_vix()

    return {
        "generated_at": (
            datetime.now()
            .astimezone()
            .isoformat()
        ),

        "source": "Yahoo Finance",

        "instruments": {
            "NIFTY": nifty.__dict__,
            "BANK_NIFTY": bank_nifty.__dict__,
        },

        "india_vix": india_vix,

        "availability": {
            "india_vix": True,
            "realized_volatility": True,
            "atr": True,
            "volatility_percentile": True,
            "expected_daily_move": True,
            "volatility_regime": True,
            "volatility_direction": True,

            "implied_volatility": False,
            "iv_percentile": False,
            "options_volatility_surface": False,
        },

        "decision_policy": {
            "volatility_is_buy_sell_signal": False,
            "automatic_trading": False,
            "broker_connection": False,
        },
    }


def _print_instrument(
    data: dict[str, Any],
) -> None:

    print()
    print(
        data["symbol"]
    )
    print("-" * 70)

    print(
        f"Price: "
        f"{data['price']}"
    )

    print(
        f"ATR(14): "
        f"{data['atr_14']}"
    )

    if data["atr_percent"] is not None:

        print(
            f"ATR %: "
            f"{data['atr_percent']:.2f}%"
        )

    else:

        print("ATR %: N/A")

    if data["realized_vol_20d"] is not None:

        print(
            f"Realized Vol 20D: "
            f"{data['realized_vol_20d'] * 100:.2f}%"
        )

    else:

        print("Realized Vol 20D: N/A")

    if data["realized_vol_60d"] is not None:

        print(
            f"Realized Vol 60D: "
            f"{data['realized_vol_60d'] * 100:.2f}%"
        )

    else:

        print("Realized Vol 60D: N/A")

    if data["volatility_percentile"] is not None:

        print(
            f"Volatility Percentile: "
            f"{data['volatility_percentile']:.2f}%"
        )

    else:

        print(
            "Volatility Percentile: N/A"
        )

    if data["expected_daily_move_percent"] is not None:

        print(
            f"Expected Daily Move: "
            f"{data['expected_daily_move_percent']:.2f}%"
        )

    else:

        print(
            "Expected Daily Move: N/A"
        )

    if data["expected_daily_range"] is not None:

        print(
            f"Expected Daily Range: "
            f"{data['expected_daily_range']:.2f}"
        )

    else:

        print(
            "Expected Daily Range: N/A"
        )

    print(
        f"Volatility Regime: "
        f"{data['volatility_regime']}"
    )

    print(
        f"Volatility Direction: "
        f"{data['volatility_direction']}"
    )

    print(
        f"Data Timestamp: "
        f"{data['data_timestamp']}"
    )


def print_market_volatility_snapshot() -> None:
    """Print a human-readable volatility report."""

    snapshot = (
        get_market_volatility_snapshot()
    )

    print()
    print("=" * 70)
    print("NOVA VOLATILITY ENGINE")
    print("=" * 70)

    print(
        f"Generated: "
        f"{snapshot['generated_at']}"
    )

    print(
        f"Source: "
        f"{snapshot['source']}"
    )

    print()
    print("INDIA VIX")
    print("-" * 70)

    vix = snapshot["india_vix"]

    print(
        f"Current VIX: "
        f"{vix['value']}"
    )

    print(
        f"Previous VIX: "
        f"{vix['previous_value']}"
    )

    if vix["change_percent"] is not None:

        print(
            f"Change: "
            f"{vix['change_percent']:.2f}%"
        )

    else:

        print("Change: N/A")

    if vix["percentile_1y"] is not None:

        print(
            f"1Y Percentile: "
            f"{vix['percentile_1y']:.2f}%"
        )

    else:

        print("1Y Percentile: N/A")

    print(
        f"Absolute VIX Regime: "
        f"{vix['absolute_regime']}"
    )

    print(
        f"Historical Position: "
        f"{vix['historical_position']}"
    )

    print(
        f"VIX Direction: "
        f"{vix['direction']}"
    )

    _print_instrument(
        snapshot["instruments"]["NIFTY"]
    )

    _print_instrument(
        snapshot["instruments"]["BANK_NIFTY"]
    )

    print()
    print("DATA AVAILABILITY")
    print("-" * 70)

    for key, available in (
        snapshot["availability"].items()
    ):

        status = (
            "AVAILABLE"
            if available
            else "NOT BUILT"
        )

        print(
            f"{key:<35}"
            f"{status}"
        )

    print()
    print("DECISION POLICY")
    print("-" * 70)

    print(
        "VOLATILITY_IS_BUY_SELL_SIGNAL=FALSE"
    )

    print(
        "AUTOMATIC_TRADING=FALSE"
    )

    print(
        "BROKER_CONNECTION=FALSE"
    )

    print("=" * 70)


if __name__ == "__main__":

    try:

        print_market_volatility_snapshot()

    except VolatilityEngineError as exc:

        print()
        print(
            f"VOLATILITY ENGINE ERROR: {exc}"
        )

        raise SystemExit(1)

    except Exception as exc:

        print()
        print(
            f"UNEXPECTED VOLATILITY ERROR: {exc}"
        )

        raise SystemExit(1)