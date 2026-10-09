"""
Tests for the research factor engine. Offline fixtures only:
no network, no caches, no live market data.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data.research_factor_engine import (
    MIN_UNIVERSE_SIZE,
    build_research_factors,
)


def make_frame(n=40, seed=7):
    rng = np.random.default_rng(seed)
    price = rng.uniform(10, 500, n)
    return pd.DataFrame(
        {
            "symbol": [f"S{i:03d}" for i in range(n)],
            "price": price,
            "return_60d": rng.normal(0, 10, n),
            "relative_strength_60d": rng.normal(0, 5, n),
            "atr_percent": rng.uniform(1, 6, n),
            "distance_52w_high": rng.uniform(-30, 0, n),
            "ema_20": price * rng.uniform(0.97, 1.03, n),
            "ema_50": price * rng.uniform(0.95, 1.05, n),
            "ema_200": price * rng.uniform(0.90, 1.10, n),
            "timestamp": ["2026-01-01T00:00:00+05:30"] * n,
        }
    )


def all_entries(result):
    return result["top_ranked"] + result["bottom_ranked"]


class TestResearchFactorEngine(unittest.TestCase):

    def test_available_on_valid_frame(self):
        result = build_research_factors(make_frame())
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["universe_size"], 40)
        self.assertEqual(result["ranked_count"], 40)
        self.assertEqual(len(result["top_ranked"]), 10)
        self.assertEqual(len(result["bottom_ranked"]), 10)
        self.assertIsNotNone(result["as_of"])
        self.assertEqual(
            result["method"], "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT"
        )

    def test_low_volatility_is_sign_flipped(self):
        # atr_percent identical to return_60d => LOW_VOL z must be the
        # exact negation of MOMENTUM z for every ranked stock.
        frame = make_frame()
        frame["atr_percent"] = frame["return_60d"] = (
            frame["return_60d"]
        )
        result = build_research_factors(frame)
        self.assertEqual(result["status"], "AVAILABLE")
        for entry in all_entries(result):
            momentum = entry["factor_z"]["MOMENTUM_60D"]
            low_vol = entry["factor_z"]["LOW_VOLATILITY"]
            if momentum is not None and low_vol is not None:
                self.assertAlmostEqual(
                    low_vol, -momentum, places=3
                )

    def test_extreme_winner_ranks_first(self):
        frame = make_frame()
        best = frame["return_60d"].idxmax()
        worst = frame["return_60d"].idxmin()
        frame.loc[best, "symbol"] = "MOM_MAX"
        frame.loc[worst, "symbol"] = "MOM_MIN"

        # Make the extremes dominate every factor by using values that
        # produce z-scores far beyond what the other 38 random stocks can
        # reach (random frame uses normal(0,10), normal(0,5), uniform(1,6), etc.).
        # 1e6 ensures ~1e5 sigma separation; clipped at MAX_ABS_Z=3.0, but
        # both extremes will still be at opposite clips, guaranteeing rank 1/N.
        frame.loc[best, [
            "return_60d",
            "relative_strength_60d",
            "distance_52w_high",
        ]] = [1_000_000.0, 1_000_000.0, 0.0]
        frame.loc[best, "atr_percent"] = 0.0001
        frame.loc[best, ["ema_20", "ema_50", "ema_200"]] = [
            frame.loc[best, "price"] * 0.5,
            frame.loc[best, "price"] * 0.4,
            frame.loc[best, "price"] * 0.3,
        ]

        frame.loc[worst, [
            "return_60d",
            "relative_strength_60d",
            "distance_52w_high",
        ]] = [-1_000_000.0, -1_000_000.0, -1_000_000.0]
        frame.loc[worst, "atr_percent"] = 1_000_000.0
        frame.loc[worst, ["ema_20", "ema_50", "ema_200"]] = [
            frame.loc[worst, "price"] * 2.0,
            frame.loc[worst, "price"] * 3.0,
            frame.loc[worst, "price"] * 4.0,
        ]

        result = build_research_factors(frame)
        self.assertEqual(result["top_ranked"][0]["symbol"], "MOM_MAX")
        # bottom_ranked is sorted ascending (worst first), so index 0 is the absolute worst
        self.assertEqual(
            result["bottom_ranked"][0]["symbol"], "MOM_MIN"
        )

    def test_missing_column_is_unavailable(self):
        frame = make_frame().drop(columns=["atr_percent"])
        result = build_research_factors(frame)
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertIn("atr_percent", result["reason"])

    def test_small_universe_is_unavailable(self):
        result = build_research_factors(make_frame(n=MIN_UNIVERSE_SIZE - 1))
        self.assertEqual(result["status"], "NOT_AVAILABLE")
        self.assertIn("below the minimum", result["reason"])

    def test_none_and_empty_inputs(self):
        self.assertEqual(
            build_research_factors(None)["status"], "NOT_AVAILABLE"
        )
        self.assertEqual(
            build_research_factors(pd.DataFrame())["status"],
            "NOT_AVAILABLE",
        )

    def test_nan_heavy_row_is_excluded(self):
        frame = make_frame()
        frame.loc[0, [
            "return_60d",
            "relative_strength_60d",
            "distance_52w_high",
        ]] = np.nan
        result = build_research_factors(frame)
        self.assertEqual(result["status"], "AVAILABLE")
        self.assertEqual(result["excluded_below_min_factors"], 1)
        self.assertEqual(result["ranked_count"], 39)

    def test_guardrails_and_warnings(self):
        result = build_research_factors(make_frame())
        policy = result["decision_policy"]
        self.assertFalse(policy["factor_rank_is_a_buy_sell_signal"])
        self.assertFalse(policy["buy_sell_authorization"])
        self.assertFalse(policy["trading_execution"])
        self.assertTrue(
            any("NOT computed" in w for w in result["warnings"])
        )
        for entry in all_entries(result):
            self.assertLessEqual(abs(entry["composite_z"]), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
