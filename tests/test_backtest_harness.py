"""
Tests for the factor backtest harness. Offline fixtures only: these cover
the pure scoring helpers, no network, no scanner cache, no live history.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.backtest_harness import (
    _safe_float,
    _up_day_fraction,
    score_symbol,
    strength_component,
    trend_component,
)


def make_indicators(trend="STRONG_UPTREND", rel_vol=1.4):
    return pd.DataFrame(
        {
            "TREND": [trend],
            "RELATIVE_VOLUME": [rel_vol],
            "Close": [100.0],
            "EMA_20": [98.0],
            "EMA_50": [95.0],
            "EMA_200": [90.0],
            "RSI_14": [58.0],
            "MACD": [1.2],
            "MACD_SIGNAL": [0.8],
            "ROC_12": [3.0],
        }
    )


class TestSafeFloat(unittest.TestCase):
    def test_none_and_nan(self):
        self.assertIsNone(_safe_float(None))
        self.assertIsNone(_safe_float(float("nan")))

    def test_non_numeric_string_is_none(self):
        # TREND is a classification string; the numeric helper must reject it.
        self.assertIsNone(_safe_float("UPTREND"))

    def test_numeric_string_coerces(self):
        self.assertEqual(_safe_float("3.5"), 3.5)


class TestTrendComponent(unittest.TestCase):
    def test_known_classifications(self):
        cases = {
            "STRONG_UPTREND": 30.0,
            "UPTREND": 20.0,
            "SIDEWAYS": 5.0,
            "DOWNTREND": -20.0,
            "STRONG_DOWNTREND": -30.0,
        }
        for trend, points in cases.items():
            with self.subTest(trend=trend):
                self.assertEqual(
                    trend_component(make_indicators(trend=trend)), points
                )

    def test_unknown_classification_is_neutral(self):
        self.assertEqual(
            trend_component(make_indicators(trend="WEIRD")), 0.0
        )

    def test_missing_trend_is_neutral(self):
        frame = make_indicators()
        frame.loc[0, "TREND"] = None
        self.assertEqual(trend_component(frame), 0.0)


class TestStrengthComponent(unittest.TestCase):
    def test_above_average_volume_is_positive(self):
        self.assertAlmostEqual(
            strength_component(make_indicators(rel_vol=1.4)), 0.4, places=3
        )

    def test_missing_volume_is_neutral(self):
        frame = make_indicators()
        frame.loc[0, "RELATIVE_VOLUME"] = None
        self.assertEqual(strength_component(frame), 0.0)


class TestScoreSymbol(unittest.TestCase):
    def test_trend_is_a_string_not_coerced_none(self):
        # Regression: routing the TREND string through _safe_float used to
        # yield None, wiping out the trend field and trend_counts.
        result = score_symbol(make_indicators(trend="UPTREND"))
        self.assertEqual(result["trend"], "UPTREND")
        self.assertEqual(result["trend_pts"], 20.0)

    def test_score_fields_present_and_typed(self):
        result = score_symbol(make_indicators())
        self.assertIsInstance(result["score"], float)
        self.assertIsInstance(result["momentum"], float)
        self.assertEqual(result["rsi"], 58.0)
        self.assertEqual(result["price"], 100.0)

    def test_missing_trend_field_is_none(self):
        frame = make_indicators()
        frame.loc[0, "TREND"] = None
        result = score_symbol(frame)
        self.assertIsNone(result["trend"])
        self.assertIn("trend", result)


class TestUpDayFraction(unittest.TestCase):
    def test_known_fraction(self):
        # Close [1,2,1,2,3,4,5,2]: 5 up moves out of 7 deltas = 0.7143.
        frame = pd.DataFrame({"Close": [1, 2, 1, 2, 3, 4, 5, 2]})
        self.assertAlmostEqual(_up_day_fraction(frame), 0.7143, places=4)

    def test_monotonic_rise_is_one(self):
        frame = pd.DataFrame({"Close": [1, 2, 3, 4, 5]})
        self.assertEqual(_up_day_fraction(frame), 1.0)

    def test_monotonic_fall_is_zero(self):
        frame = pd.DataFrame({"Close": [5, 4, 3, 2, 1]})
        self.assertEqual(_up_day_fraction(frame), 0.0)

    def test_single_bar_is_zero(self):
        self.assertEqual(_up_day_fraction(pd.DataFrame({"Close": [100]})), 0.0)

    def test_result_stays_within_zero_one(self):
        frame = pd.DataFrame({"Close": [10, 11, 10, 12, 9, 13, 8]})
        value = _up_day_fraction(frame)
        self.assertGreaterEqual(value, 0.0)
        self.assertLessEqual(value, 1.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
