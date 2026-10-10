"""
Integration tests for the cache-first Nova market pipeline.

These exercise the report pipeline end-to-end but stay fully offline by
pointing the save and load paths at a temporary cache directory:

    save_json_report -> load_latest_saved_report -> get_market_brief
                    -> get_market_analysis (cache-first, never scans)

and assert that both consumers (brief + analysis snapshot) read the SAME
measured values out of one saved report, flag stale/missing data honestly,
and that get_market_analysis never triggers the expensive scanner when a
saved report exists.

No network, no Ollama, no real NSE scan, no writes to the real cache.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools
import market_lab.market_lab_data as mld
import market_lab_ui as mlui


# ----------------------------------------------------------------------------
# Fixtures and helpers
# ----------------------------------------------------------------------------

def _iso_hours_ago(hours):
    stamp = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(
        hours=hours
    )
    return stamp.isoformat()


def rich_report(**overrides):
    """A saved Market Lab report using the real nested report structure.

    Chosen measured values (regime BEARISH, VIX 15.28, advancing 1169,
    flow regime FII_SELLING_DII_ABSORPTION, signal not eligible) are the
    facts the two consumers must agree on.
    """
    report = {
        "generated": _iso_hours_ago(0.2),
        "market": "NSE",
        "stocks_analyzed": 1999,
        "mode": "CACHED_OR_REFRESH",
        "scanner_file": "market_scan_20261010_123734.csv",
        "market_regime": "BEARISH",
        "nifty_returns": {"1D": 1.30, "5D": 0.44, "20D": -3.89, "60D": -6.47},
        "bank_nifty_returns": {"1D": 1.36, "5D": 1.48, "20D": -1.85},
        "breadth": {
            "total": 1999,
            "advancing": 1169,
            "declining": 809,
            "unchanged": 21,
            "advance_decline_ratio": 1.44,
            "above_ema20_percent": 20.66,
            "above_ema50_percent": 22.91,
            "above_ema200_percent": 32.72,
            "strong_uptrend_percent": 12.06,
            "strong_downtrend_percent": 45.22,
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
        "sector_intelligence": {"available": True},
        "derivatives": {
            "available": True,
            "nifty": {
                "underlying": {"spot": 22520.45},
                "pcr": {"oi_pcr": 1.1181, "volume_pcr": 0.8749},
                "max_pain": {"strike": 22500},
            },
        },
        "institutional_flow": {
            "available": True,
            "signal_allowed": False,
            "signal_reason": "not fully primary-verified",
            "metrics": {
                "flow_regime": "FII_SELLING_DII_ABSORPTION",
                "latest_date": "2026-10-09",
                "fii_5d": -41330.14,
                "dii_5d": 37629.94,
                "fii_10d": -52335.00,
                "dii_10d": 54807.67,
                "fii_20d": -57910.10,
                "dii_20d": 84541.97,
                "primary_source_sessions_in_target_window": 2,
                "target_sessions": 20,
            },
        },
        "event_risk_context": {
            "overall_risk": "MODERATE",
            "upcoming_event_count": 5,
            "source_fresh": True,
        },
        "top_technical_stocks": [
            {"symbol": "CPPLUS", "technical_score": 100.0, "trend": "STRONG_UPTREND"}
        ],
        "research_factors": {
            "status": "AVAILABLE",
            "top_ranked": [
                {"rank": 1, "symbol": "UEL", "price": 214.94, "composite_z": 1.535}
            ],
        },
        "risk_context": {"available": True},
        "data_availability": {
            "market_scanner": "AVAILABLE",
            "india_vix": "AVAILABLE",
            "volatility_engine": "AVAILABLE",
            "sector_engine": "AVAILABLE",
            "derivatives_engine": "AVAILABLE",
            "nifty_options": "AVAILABLE",
            "institutional_flow": "READY",
            "event_risk_engine": "AVAILABLE",
            "risk_engine": "AVAILABLE",
            "research_factor_engine": "AVAILABLE",
        },
        "decision_policy": {
            "buy_sell_authorized": False,
            "trading_execution": False,
            "analysis_only": True,
        },
        "ai_context": {"guardrails": {"buy_sell_authorized": False}},
    }
    report.update(overrides)
    return report


class TempCache:
    """Redirect both the saver and the loaders to a throwaway cache dir.

    Patches three module attributes:
      - market_lab.market_lab_data.CACHE_DIR (save_json_report)
      - market_lab_ui.CACHE_DIR             (load_latest_saved_report)
      - market_lab.market_lab_data.CACHE_DIR is also re-read inside
        tools._load_latest_market_lab_report at call time, so it is covered
        by the same patch.
    """

    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.base = Path(self._tmp.name) / "cache"
        self._patches = [
            mock.patch.object(mld, "CACHE_DIR", self.base),
            mock.patch.object(mlui, "CACHE_DIR", self.base),
        ]
        for patch in self._patches:
            patch.start()
        return self.base

    def __exit__(self, *exc):
        for patch in self._patches:
            patch.stop()
        self._tmp.cleanup()
        return False


# ----------------------------------------------------------------------------
# Save / load round-trip (the pipeline's persistence contract)
# ----------------------------------------------------------------------------

class TestSaveLoadRoundTrip(unittest.TestCase):

    def test_save_then_load_returns_equivalent_report(self):
        with TempCache():
            report = rich_report()
            path = mld.save_json_report(report)
            self.assertTrue(path.exists(), "save_json_report wrote a file")
            wrapper = mlui.load_latest_saved_report()
            self.assertIsNotNone(wrapper)
            loaded = wrapper["report"]
            self.assertEqual(loaded["market_regime"], report["market_regime"])
            self.assertEqual(loaded["stocks_analyzed"], report["stocks_analyzed"])
            self.assertEqual(
                sorted(loaded["data_availability"].keys()),
                sorted(report["data_availability"].keys()),
            )

    def test_report_matches_market_lab_filename_pattern(self):
        with TempCache() as base:
            path = mld.save_json_report(rich_report())
            self.assertTrue(path.name.startswith("market_lab_"))
            self.assertTrue(path.name.endswith(".json"))
            self.assertEqual(path.parent, base / "market_lab")

    def test_guardrails_survive_the_round_trip(self):
        with TempCache():
            mld.save_json_report(rich_report())
            loaded = mlui.load_latest_saved_report()["report"]
            self.assertFalse(loaded["decision_policy"]["buy_sell_authorized"])
            self.assertFalse(loaded["decision_policy"]["trading_execution"])
            self.assertTrue(loaded["decision_policy"]["analysis_only"])
            self.assertFalse(loaded["ai_context"]["guardrails"]["buy_sell_authorized"])

    def test_tools_loader_sees_saved_report(self):
        with TempCache():
            mld.save_json_report(rich_report())
            loaded = tools._load_latest_market_lab_report()
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["market_regime"], "BEARISH")

    def test_newest_saved_report_is_loaded(self):
        with TempCache():
            import time

            mld.save_json_report(rich_report(generated=_iso_hours_ago(5), market_regime="OLD"))
            time.sleep(1.05)  # ensure a distinct mtime for the newer file
            mld.save_json_report(rich_report(generated=_iso_hours_ago(0.1), market_regime="NEW"))
            loaded = tools._load_latest_market_lab_report()
            self.assertEqual(loaded["market_regime"], "NEW")

    def test_empty_cache_loads_nothing(self):
        with TempCache():
            self.assertIsNone(tools._load_latest_market_lab_report())
            self.assertIsNone(mlui.load_latest_saved_report())


# ----------------------------------------------------------------------------
# get_market_brief / get_market_analysis read the shared cache
# ----------------------------------------------------------------------------

class TestCacheFirstTools(unittest.TestCase):

    def test_brief_reads_temp_cache(self):
        with TempCache():
            mld.save_json_report(rich_report())
            brief = tools.get_market_brief()
            self.assertIn("NOVA MORNING MARKET BRIEF", brief)
            self.assertIn("BEARISH", brief)

    def test_brief_reports_missing_when_no_report(self):
        with TempCache():
            brief = tools.get_market_brief()
            self.assertIn("No saved Market Lab report found", brief)

    def test_analysis_is_cache_first_and_never_scans(self):
        with TempCache():
            mld.save_json_report(rich_report())
            with mock.patch.object(tools, "scan_market") as scanner:
                out = tools.get_market_analysis()
        scanner.assert_not_called()
        self.assertIn("DATA_SOURCE=LATEST_SAVED_MARKET_LAB_REPORT", out)

    def test_analysis_falls_back_to_scanner_when_no_report(self):
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "symbol": "AAA",
                    "price": 100.0,
                    "score": 90.0,
                    "trend": "STRONG_UPTREND",
                    "rsi_14": 65.0,
                    "relative_volume": 1.5,
                    "return_1d": 0.5,
                    "return_20d": 5.0,
                    "return_60d": 10.0,
                    "relative_strength_20d": 3.0,
                    "relative_strength_60d": 4.0,
                    "macd_condition": "BULLISH",
                    "volume_condition": "EXPANSION",
                }
            ]
        )
        summary = {
            "market_regime": "BULLISH",
            "nifty_returns": {"return_1d": 1.0},
            "breadth": {"total": 2000},
            "stocks_in_universe": 2000,
            "stocks_analyzed": 1999,
            "timestamp": "2026-10-10T18:25:33",
        }
        with TempCache():
            with mock.patch.object(
                tools, "scan_market", return_value=(df, summary)
            ) as scanner:
                out = tools.get_market_analysis()
            scanner.assert_called_once()
        self.assertIn("TOP TECHNICAL RANKINGS", out)


# ----------------------------------------------------------------------------
# The two consumers must agree on the SAME measured values
# ----------------------------------------------------------------------------

class TestConsumersAgree(unittest.TestCase):
    """brief and analysis parse the same report independently; they must
    report the identical measured facts, not diverge."""

    def setUp(self):
        self.report = rich_report()
        self.brief = tools._build_market_brief(self.report)
        self.analysis = tools._build_market_analysis_from_report(self.report)

    def test_regime_matches(self):
        self.assertIn("BEARISH", self.brief)
        self.assertIn("MARKET_REGIME=BEARISH", self.analysis)

    def test_india_vix_matches(self):
        self.assertIn("15.28", self.brief)
        self.assertIn("INDIA_VIX=15.28", self.analysis)

    def test_breadth_matches(self):
        # brief: "Advancing: 1169"; analysis: "ADVANCING=1169"
        self.assertIn("1169", self.brief)
        self.assertIn("ADVANCING=1169", self.analysis)

    def test_flow_regime_matches(self):
        self.assertIn("FII_SELLING_DII_ABSORPTION", self.brief)
        self.assertIn("FII_SELLING_DII_ABSORPTION", self.analysis)

    def test_signal_eligibility_honesty_matches(self):
        self.assertIn("Signal-eligible: NO", self.brief)
        self.assertIn("SIGNAL_ELIGIBLE=NO", self.analysis)
        self.assertIn("not fully primary-verified", self.brief)
        self.assertIn("not fully primary-verified", self.analysis)

    def test_top_symbols_match(self):
        self.assertIn("CPPLUS", self.brief)
        self.assertIn("CPPLUS", self.analysis)


# ----------------------------------------------------------------------------
# Stale / missing honesty is consistent across the pipeline
# ----------------------------------------------------------------------------

class TestStalenessAcrossPipeline(unittest.TestCase):

    def test_stale_report_flagged_in_brief(self):
        report = rich_report(generated=_iso_hours_ago(30))
        brief = tools._build_market_brief(report)
        self.assertIn("WARNING", brief)

    def test_stale_report_timestamp_visible_in_analysis(self):
        report = rich_report(generated=_iso_hours_ago(30))
        analysis = tools._build_market_analysis_from_report(report)
        self.assertIn("DATA_TIMESTAMP=", analysis)
        self.assertIn("may be stale", analysis)

    def test_brief_and_analysis_handle_minimal_report(self):
        report = {"generated": _iso_hours_ago(1), "market_regime": "UNKNOWN"}
        self.assertIn("NOVA MORNING MARKET BRIEF", tools._build_market_brief(report))
        self.assertIn(
            "MARKET_REGIME=UNKNOWN",
            tools._build_market_analysis_from_report(report),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
