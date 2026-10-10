"""
Tests for the assistant morning market brief in tools.py.

Offline only: _build_market_brief is pure (report dict -> text), so these
tests feed it fixtures and never touch the network, Ollama, or caches.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import (
    _brief_age_hours,
    _brief_crore,
    _build_market_brief,
)


def _iso_hours_ago(hours):
    stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=hours
    )
    return stamp.isoformat()


def full_report(**overrides):
    """A saved Market Lab report fixture using the real nested keys."""
    report = {
        "generated": _iso_hours_ago(1),
        "market": "NSE",
        "stocks_analyzed": 1999,
        "mode": "CACHED_OR_REFRESH",
        "market_regime": "BEARISH",
        "breadth": {
            "advancing": 1169,
            "declining": 809,
            "advance_decline_ratio": 1.44,
            "above_ema20_percent": 20.66,
            "above_ema50_percent": 22.91,
            "above_ema200_percent": 32.72,
        },
        "volatility": {
            "india_vix": {
                "available": True,
                "value": 15.28,
                "direction": "RISING",
                "change_percent": 10.01,
                "percentile_1y": 73,
                "regime": "MODERATE",
            }
        },
        "institutional_flow": {
            "available": True,
            "signal_allowed": False,
            "signal_reason": "not fully primary-verified",
            "metrics": {
                "flow_regime": "FII_SELLING_DII_ABSORPTION",
                "latest_date": "2026-10-09",
                "latest_session_age_calendar_days": 1,
                "fii_5d": -41330.14,
                "dii_5d": 37629.94,
                "combined_5d": -3700.20,
                "fii_10d": -52335.00,
                "dii_10d": 54807.67,
                "combined_10d": 2472.67,
                "fii_20d": -57910.10,
                "dii_20d": 84541.97,
                "combined_20d": 26631.87,
                "primary_source_sessions_in_target_window": 2,
                "target_sessions": 20,
                "source_quality": "MIXED_SOURCE_TARGET_WINDOW",
            },
        },
        "event_risk_context": {
            "overall_risk": "MODERATE",
            "upcoming_event_count": 5,
            "source_fresh": True,
            "upcoming_events": [
                {"name": "India CPI (Sep 2026)", "severity": "HIGH", "hours_until": 62},
                {"name": "India WPI (Sep 2026)", "severity": "MODERATE", "hours_until": 106},
                {"name": "US CPI (Sep 2026)", "severity": "HIGH", "hours_until": 112},
                {"name": "4th (should be dropped)", "severity": "LOW", "hours_until": 200},
            ],
        },
        "top_technical_stocks": [
            {"symbol": "CPPLUS", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
            {"symbol": "ZIMLAB", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
            {"symbol": "BLUSPRING", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
        ],
        "research_factors": {
            "status": "AVAILABLE",
            "top_ranked": [
                {"rank": 1, "symbol": "UEL", "price": 214.94, "composite_z": 1.448},
                {"rank": 2, "symbol": "STLNETWORK", "price": 46.35, "composite_z": 1.382},
            ],
        },
        "data_availability": {
            "market_scanner": "AVAILABLE",
            "institutional_flow": "READY",
            "research_factor_engine": "AVAILABLE",
        },
    }
    report.update(overrides)
    return report


class TestBriefHelpers(unittest.TestCase):

    def test_age_hours_none_for_bad_input(self):
        self.assertIsNone(_brief_age_hours(None))
        self.assertIsNone(_brief_age_hours(""))
        self.assertIsNone(_brief_age_hours("not-a-date"))

    def test_age_hours_recent(self):
        age = _brief_age_hours(_iso_hours_ago(3))
        self.assertIsNotNone(age)
        self.assertGreater(age, 2.9)
        self.assertLess(age, 3.1)

    def test_age_hours_naive_treated_as_utc(self):
        naive = (
            datetime.datetime.now(datetime.timezone.utc)
            - datetime.timedelta(hours=2)
        ).replace(tzinfo=None)
        self.assertIsNotNone(_brief_age_hours(naive.isoformat()))

    def test_crore_signed_and_na(self):
        self.assertEqual(_brief_crore(-3700.2), "-3,700.20")
        self.assertEqual(_brief_crore(2472.67), "+2,472.67")
        self.assertEqual(_brief_crore(None), "N/A")
        self.assertEqual(_brief_crore("junk"), "N/A")


class TestBuildMarketBrief(unittest.TestCase):

    def test_header_and_sections(self):
        text = _build_market_brief(full_report())
        self.assertIn("NOVA MORNING MARKET BRIEF", text)
        self.assertIn("MARKET REGIME", text)
        self.assertIn("BEARISH", text)
        self.assertIn("BREADTH", text)
        self.assertIn("VOLATILITY", text)
        self.assertIn("India VIX: 15.28", text)
        self.assertIn("INSTITUTIONAL FLOW", text)
        self.assertIn("FII_SELLING_DII_ABSORPTION", text)
        self.assertIn("EVENT RISK", text)
        self.assertIn("TOP TECHNICAL STOCKS", text)
        self.assertIn("TOP FACTOR-RANKED", text)
        self.assertIn("DATA GAPS", text)
        self.assertIn("GUARDRAILS", text)

    def test_stocks_analyzed_and_mode(self):
        text = _build_market_brief(full_report())
        self.assertIn("Stocks analyzed: 1999", text)
        self.assertIn("Mode: CACHED_OR_REFRESH", text)

    def test_flow_numbers_and_signal_honesty(self):
        text = _build_market_brief(full_report())
        self.assertIn("FII -41,330.14", text)
        self.assertIn("DII +37,629.94", text)
        self.assertIn("Primary-verified sessions: 2/20", text)
        self.assertIn("Signal-eligible: NO", text)
        self.assertIn("not fully primary-verified", text)

    def test_events_limited_to_three(self):
        text = _build_market_brief(full_report())
        self.assertIn("India CPI (Sep 2026)", text)
        self.assertIn("US CPI (Sep 2026)", text)
        self.assertNotIn("4th (should be dropped)", text)

    def test_stale_report_warns(self):
        text = _build_market_brief(full_report(generated=_iso_hours_ago(30)))
        self.assertIn("WARNING", text)
        self.assertIn("30.0h old", text)

    def test_fresh_report_has_no_warning(self):
        text = _build_market_brief(full_report(generated=_iso_hours_ago(1)))
        self.assertNotIn("WARNING", text)

    def test_invalid_report(self):
        self.assertIn("MARKET BRIEF ERROR", _build_market_brief(None))
        self.assertIn("MARKET BRIEF ERROR", _build_market_brief("not a dict"))

    def test_missing_sections_are_omitted_gracefully(self):
        text = _build_market_brief({"generated": _iso_hours_ago(1)})
        self.assertIn("NOVA MORNING MARKET BRIEF", text)
        self.assertIn("GUARDRAILS", text)
        self.assertNotIn("BREADTH", text)
        self.assertNotIn("INSTITUTIONAL FLOW", text)

    def test_missing_values_render_na_not_zero(self):
        report = full_report()
        report["institutional_flow"]["metrics"]["fii_5d"] = None
        self.assertIn("FII N/A", _build_market_brief(report))

    def test_data_gap_listed(self):
        report = full_report()
        report["data_availability"]["derivatives"] = "NOT AVAILABLE"
        text = _build_market_brief(report)
        self.assertIn("derivatives", text)
        self.assertNotIn("None reported", text)

    def test_factor_ranking_only_when_available(self):
        report = full_report()
        report["research_factors"]["status"] = "NOT_AVAILABLE"
        self.assertNotIn("TOP FACTOR-RANKED", _build_market_brief(report))

    def test_vix_not_available(self):
        report = full_report()
        report["volatility"]["india_vix"]["available"] = False
        self.assertIn("India VIX: not available", _build_market_brief(report))


if __name__ == "__main__":
    unittest.main(verbosity=2)

