"""
Tests for the institutional flow primary-coverage helper.

Offline and pure: no network, no cache, no live market data. The helper
turns the measured primary-session count into an honest coverage ratio and
a clearly-labelled runway estimate.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data.institutional_flow_engine import (
    DEFAULT_TARGET_SESSIONS,
    _primary_coverage_summary,
)


class TestPrimaryCoverageSummary(unittest.TestCase):

    def test_full_primary_window(self):
        result = _primary_coverage_summary(
            DEFAULT_TARGET_SESSIONS, DEFAULT_TARGET_SESSIONS
        )
        self.assertEqual(result["primary_coverage_ratio"], 1.0)
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"], 0
        )
        self.assertIn("fully NSE-primary", result["primary_coverage_note"])

    def test_no_primary_yet(self):
        result = _primary_coverage_summary(0, DEFAULT_TARGET_SESSIONS)
        self.assertEqual(result["primary_coverage_ratio"], 0.0)
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"],
            DEFAULT_TARGET_SESSIONS,
        )
        self.assertIn("No NSE-primary", result["primary_coverage_note"])

    def test_partial_coverage_estimate(self):
        result = _primary_coverage_summary(2, 22)
        self.assertAlmostEqual(
            result["primary_coverage_ratio"], 0.0909, places=3
        )
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"], 20
        )
        self.assertIn("2/22", result["primary_coverage_note"])
        self.assertIn("20 more trading day", result["primary_coverage_note"])

    def test_over_count_clamps_ratio_to_one(self):
        result = _primary_coverage_summary(30, 20)
        self.assertEqual(result["primary_coverage_ratio"], 1.0)
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"], 0
        )
        self.assertIn("fully NSE-primary", result["primary_coverage_note"])

    def test_zero_target_is_unknown(self):
        result = _primary_coverage_summary(0, 0)
        self.assertIsNone(result["primary_coverage_ratio"])
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"], 0
        )
        self.assertIn("unknown", result["primary_coverage_note"])

    def test_negative_inputs_clamp(self):
        result = _primary_coverage_summary(-5, -1)
        self.assertIsNone(result["primary_coverage_ratio"])
        self.assertEqual(
            result["trading_days_to_full_primary_estimate"], 0
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
