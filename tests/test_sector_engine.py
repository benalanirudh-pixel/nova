"""
Tests for the sector engine's pure math in analysis/data/sector_engine.py.

Offline only: safe_float / pct_mean / safe_ratio / determine_sector_regime are
pure (no network, no files), so these feed them fixtures and known inputs
instead of running the sector scan. The index classification / scan path (which
downloads NSE HTML and reads the scanner output) is intentionally not exercised.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from analysis.data.sector_engine import (
    determine_sector_regime,
    pct_mean,
    safe_float,
    safe_ratio,
)


class TestSafeFloat(unittest.TestCase):

    def test_none_and_nan_are_none(self):
        self.assertIsNone(safe_float(None))
        self.assertIsNone(safe_float(float("nan")))
        self.assertIsNone(safe_float(pd.NA))

    def test_non_finite_is_none(self):
        self.assertIsNone(safe_float(float("inf")))
        self.assertIsNone(safe_float(-math.inf))

    def test_numbers_coerce(self):
        self.assertEqual(safe_float(7), 7.0)
        self.assertEqual(safe_float("3.5"), 3.5)

    def test_junk_is_none(self):
        self.assertIsNone(safe_float("abc"))
        self.assertIsNone(safe_float(object()))


class TestPctMean(unittest.TestCase):

    def test_mean_of_numeric_series(self):
        self.assertEqual(pct_mean(pd.Series([1.0, 2.0, 3.0])), 2.0)

    def test_non_numeric_coerced_then_dropped(self):
        self.assertEqual(pct_mean(pd.Series([1, 2, "x", None])), 1.5)

    def test_all_invalid_is_none(self):
        self.assertIsNone(pct_mean(pd.Series([None, "x", float("nan")])))
        self.assertIsNone(pct_mean(pd.Series([], dtype="float64")))


class TestSafeRatio(unittest.TestCase):

    def test_normal_ratio(self):
        self.assertEqual(safe_ratio(5, 10), 0.5)

    def test_zero_and_negative_denominator_are_none(self):
        self.assertIsNone(safe_ratio(5, 0))
        self.assertIsNone(safe_ratio(5, -2))


class TestDetermineSectorRegime(unittest.TestCase):
    """Score model: return_20d / relative_strength_20d each +-2/+-1 on the
    +/-5 boundaries; EMA50 breadth +-2/+-1 on the 40/50/60 boundaries. Then
    score>=5 STRONG, >=2 POSITIVE, <=-5 WEAK, <=-2 NEGATIVE, else NEUTRAL; no
    evidence -> INSUFFICIENT_DATA. Descriptive only, never a signal."""

    def test_no_evidence_is_insufficient(self):
        self.assertEqual(
            determine_sector_regime(None, None, None),
            "INSUFFICIENT_DATA",
        )

    def test_strong_at_boundary_score_five(self):
        # +2 (ret>5) +2 (rs>5) +1 (ema>=50) = 5
        self.assertEqual(
            determine_sector_regime(6.0, 6.0, 55.0), "STRONG"
        )

    def test_strong(self):
        self.assertEqual(
            determine_sector_regime(10.0, 10.0, 70.0), "STRONG"
        )

    def test_positive_at_boundary_score_two(self):
        # +1 (ret>0) +1 (rs>0), no breadth evidence = 2
        self.assertEqual(
            determine_sector_regime(2.0, 2.0, None), "POSITIVE"
        )

    def test_positive(self):
        self.assertEqual(
            determine_sector_regime(2.0, 2.0, 70.0), "POSITIVE"
        )

    def test_neutral(self):
        # ret 0 -> -1 ; rs 0 -> -1 ; ema 50 -> +1  = -1
        self.assertEqual(
            determine_sector_regime(0.0, 0.0, 50.0), "NEUTRAL"
        )

    def test_negative_at_boundary_score_negative_two(self):
        # ret 0 -> -1 ; ema 45 (40..50) -> -1  = -2
        self.assertEqual(
            determine_sector_regime(0.0, None, 45.0), "NEGATIVE"
        )

    def test_weak_at_boundary_score_negative_five(self):
        # ret -10 -> -2 ; rs -10 -> -2 ; ema 45 -> -1  = -5
        self.assertEqual(
            determine_sector_regime(-10.0, -10.0, 45.0), "WEAK"
        )

    def test_weak(self):
        self.assertEqual(
            determine_sector_regime(-10.0, -10.0, 30.0), "WEAK"
        )

    def test_single_evidence_still_classifies(self):
        # Only breadth: ema 70 -> +2  = 2 -> POSITIVE
        self.assertEqual(
            determine_sector_regime(None, None, 70.0), "POSITIVE"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
