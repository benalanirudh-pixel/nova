"""
Nova Research Factor Engine

Version: 1.0.0

Purpose:
- Cross-sectional factor ranking over the cached NSE scanner universe.
- Transparent, equal-weighted z-score factors computed only from measured
  scanner columns. No data fetching.

This module does not predict prices, authorize buy/sell signals, or
execute trades.

Fundamental factors (value, quality, growth) are deliberately NOT computed
because Nova has no verified fundamentals source. No values are invented.

Timestamps: engine is offline; the scanner dataframe provides as-of data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ENGINE_NAME = "Nova Research Factor Engine"
ENGINE_VERSION = "1.0.0"

MIN_UNIVERSE_SIZE = 30
MIN_FACTORS_PER_STOCK = 3
TOP_N_DEFAULT = 10
MAX_ABS_Z = 3.0

EXECUTION_ENABLED = False
BUY_SELL_AUTHORIZATION = False

FACTOR_DEFINITIONS = {
    "MOMENTUM_60D": {
        "source_column": "return_60d",
        "direction": 1,
        "description": "60-day price return, cross-sectional z-score.",
    },
    "RELATIVE_STRENGTH": {
        "source_column": "relative_strength_60d",
        "direction": 1,
        "description": (
            "60-day return relative to NIFTY, cross-sectional z-score."
        ),
    },
    "LOW_VOLATILITY": {
        "source_column": "atr_percent",
        "direction": -1,
        "description": (
            "ATR percent of price, sign-flipped so lower volatility "
            "scores higher."
        ),
    },
    "TREND_STRUCTURE": {
        "source_column": "_ema_alignment",
        "direction": 1,
        "description": (
            "Count of close levels above EMA20/EMA50/EMA200 (0-3), "
            "cross-sectional z-score."
        ),
    },
    "PROXIMITY_52W_HIGH": {
        "source_column": "distance_52w_high",
        "direction": 1,
        "description": (
            "Distance from 52-week high, cross-sectional z-score."
        ),
    },
}

REQUIRED_COLUMNS = [
    "symbol",
    "price",
    "return_60d",
    "relative_strength_60d",
    "atr_percent",
    "distance_52w_high",
    "ema_20",
    "ema_50",
    "ema_200",
]

STATIC_WARNINGS = [
    "Fundamental factors (value, quality, growth) are NOT computed: "
    "Nova has no verified fundamentals source.",
    "Factor ranks are cross-sectional analysis inputs, not forecasts "
    "and not buy/sell signals.",
    "Universe and prices come from the cached scanner output; check "
    "data_availability and scanner_file for freshness.",
]


def _unavailable(reason: str) -> dict:
    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "status": "NOT_AVAILABLE",
        "reason": reason,
        "warnings": list(STATIC_WARNINGS),
        "decision_policy": {
            "factor_rank_is_a_buy_sell_signal": False,
            "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
            "trading_execution": EXECUTION_ENABLED,
        },
    }


def _zscore(series: pd.Series) -> pd.Series:
    """Cross-sectional z-score, clipped at +/- MAX_ABS_Z."""
    clean = pd.to_numeric(series, errors="coerce")
    std = clean.std()

    if pd.isna(std) or std == 0:
        return pd.Series(np.nan, index=clean.index, dtype=float)

    z = (clean - clean.mean()) / std
    return z.clip(-MAX_ABS_Z, MAX_ABS_Z)


def _ema_alignment(row: pd.Series) -> float:
    """Count of price levels above EMA20/50/200 (0-3), NaN if unusable."""
    price = row.get("price")

    if price is None or pd.isna(price):
        return np.nan

    above = 0
    for column in ("ema_20", "ema_50", "ema_200"):
        value = row.get(column)
        if value is None or pd.isna(value):
            return np.nan
        if float(price) > float(value):
            above += 1

    return float(above)


def build_research_factors(
    dataframe: pd.DataFrame | None,
    top_n: int = TOP_N_DEFAULT,
) -> dict:
    """
    Build cross-sectional factor ranks from the scanner universe.

    Returns an AVAILABLE context with top/bottom rankings, or an
    UNAVAILABLE context explaining exactly what is missing.
    """
    if dataframe is None or not isinstance(dataframe, pd.DataFrame):
        return _unavailable("Scanner dataframe is missing.")

    if dataframe.empty:
        return _unavailable("Scanner dataframe is empty.")

    if len(dataframe) < MIN_UNIVERSE_SIZE:
        return _unavailable(
            f"Universe size {len(dataframe)} is below the minimum "
            f"of {MIN_UNIVERSE_SIZE} stocks for cross-sectional ranking."
        )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in dataframe.columns
    ]
    if missing:
        return _unavailable(
            "Scanner dataframe is missing required columns: "
            + ", ".join(missing)
        )

    if not isinstance(top_n, int) or not 1 <= top_n <= 100:
        top_n = TOP_N_DEFAULT

    frame = dataframe.copy()
    frame["_ema_alignment"] = frame.apply(_ema_alignment, axis=1)

    # ------------------------------------------------------------
    # FACTOR Z-SCORES
    # ------------------------------------------------------------

    factor_columns: dict[str, pd.Series] = {}

    for name, definition in FACTOR_DEFINITIONS.items():
        z = _zscore(frame[definition["source_column"]])
        if definition["direction"] == -1:
            z = -z
        factor_columns[name] = z

    factor_z = pd.DataFrame(factor_columns, index=frame.index)

    # ------------------------------------------------------------
    # COMPOSITE (equal weight, minimum factor coverage)
    # ------------------------------------------------------------

    valid_count = factor_z.notna().sum(axis=1)
    composite = factor_z.mean(axis=1).where(
        valid_count >= MIN_FACTORS_PER_STOCK
    )

    frame["_composite"] = composite.round(4)
    frame["_valid_factors"] = valid_count

    included = frame.dropna(subset=["_composite"])
    excluded_count = int(len(frame) - len(included))

    # ------------------------------------------------------------
    # FACTOR METADATA
    # ------------------------------------------------------------

    factors_meta = {}
    for name, series in factor_z.items():
        factors_meta[name] = {
            "source_column": FACTOR_DEFINITIONS[name]["source_column"],
            "direction": (
                "HIGHER_IS_BETTER"
                if FACTOR_DEFINITIONS[name]["direction"] == 1
                else "LOWER_IS_BETTER"
            ),
            "description": FACTOR_DEFINITIONS[name]["description"],
            "coverage": round(float(series.notna().mean()), 4),
        }

    # ------------------------------------------------------------
    # RANKINGS
    # ------------------------------------------------------------

    def _entry(row: pd.Series) -> dict:
        return {
            "symbol": str(row.get("symbol")),
            "price": (
                None
                if pd.isna(row.get("price"))
                else round(float(row["price"]), 4)
            ),
            "composite_z": float(row["_composite"]),
            "factor_z": {
                name: (
                    None
                    if pd.isna(row.get(name))
                    else round(float(row[name]), 4)
                )
                for name in FACTOR_DEFINITIONS
            },
        }

    ranked = included.sort_values("_composite", ascending=False)
    top = ranked.head(top_n)
    bottom = ranked.tail(top_n).sort_values("_composite")

    as_of = None
    if "timestamp" in frame.columns:
        try:
            as_of = str(frame["timestamp"].dropna().max())
        except Exception:
            as_of = None

    return {
        "engine": ENGINE_NAME,
        "version": ENGINE_VERSION,
        "status": "AVAILABLE",
        "method": "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT",
        "as_of": as_of,
        "universe_size": int(len(frame)),
        "ranked_count": int(len(included)),
        "excluded_below_min_factors": excluded_count,
        "min_factors_per_stock": MIN_FACTORS_PER_STOCK,
        "max_abs_z": MAX_ABS_Z,
        "factors": factors_meta,
        "top_ranked": [
            {"rank": rank, **_entry(row)}
            for rank, (_, row) in enumerate(top.iterrows(), start=1)
        ],
        "bottom_ranked": [
            {"rank": rank, **_entry(row)}
            for rank, (_, row) in enumerate(bottom.iterrows(), start=1)
        ],
        "warnings": list(STATIC_WARNINGS),
        "decision_policy": {
            "factor_rank_is_a_buy_sell_signal": False,
            "buy_sell_authorization": BUY_SELL_AUTHORIZATION,
            "trading_execution": EXECUTION_ENABLED,
        },
    }


if __name__ == "__main__":
    # Self-test with fictional offline data. Never a real market claim.
    rng = np.random.default_rng(42)
    sample_size = 60
    sample = pd.DataFrame(
        {
            "symbol": [f"TEST{i:03d}" for i in range(sample_size)],
            "price": rng.uniform(10, 1000, sample_size),
            "return_60d": rng.normal(0, 15, sample_size),
            "relative_strength_60d": rng.normal(0, 10, sample_size),
            "atr_percent": rng.uniform(1, 8, sample_size),
            "distance_52w_high": rng.uniform(-40, 0, sample_size),
            "ema_20": rng.uniform(10, 1000, sample_size),
            "ema_50": rng.uniform(10, 1000, sample_size),
            "ema_200": rng.uniform(10, 1000, sample_size),
            "timestamp": ["2026-01-01T00:00:00+05:30"] * sample_size,
        }
    )

    result = build_research_factors(sample)

    assert result["status"] == "AVAILABLE"
    assert result["universe_size"] == sample_size
    assert len(result["top_ranked"]) == 10
    assert result["decision_policy"]["trading_execution"] is False

    print("NOVA RESEARCH FACTOR ENGINE SELF-TEST")
    print("Status:", result["status"])
    print("Universe:", result["universe_size"])
    print("Top symbol:", result["top_ranked"][0]["symbol"])
    print(
        "Execution enabled:",
        result["decision_policy"]["trading_execution"],
    )
    print("Self-test passed.")


