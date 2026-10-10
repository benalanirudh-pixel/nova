"""
Tests for the cache-first get_market_analysis() behaviour in tools.py.

Offline only. These exercise the pure helper functions
`_build_market_analysis_from_report` and `_build_market_analysis_from_scanner`
and the cache-first dispatch in `get_market_analysis` itself, using fixtures and
a stubbed report loader. No network, no Ollama, no NSE scanner run.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import tools


def report_fixture(**overrides):
    """A saved Market Lab report fixture using the real nested report keys.

    Note the report uses short return keys (1D/5D/20D/60D), unlike the scanner
    summary (return_1d/...), so the report-based builder must handle both.
    """
    report = {
        "generated": "2026-10-10T18:25:33+05:30",
        "stocks_analyzed": 1999,
        "mode": "LIVE_ONLY",
        "market": "NSE",
        "scanner_file": "market_scan_20261010_123734.csv",
        "market_regime": "BEARISH",
        "nifty_returns": {"1D": 1.30, "5D": 0.44, "20D": -3.89, "60D": -6.47},
        "bank_nifty_returns": {"1D": 1.36, "5D": 1.48, "20D": -1.85, "60D": -4.33},
        "breadth": {
            "total": 1999,
            "advancing": 523,
            "declining": 1466,
            "unchanged": 10,
            "advance_decline_ratio": 0.36,
            "above_ema20_percent": 17.61,
            "above_ema50_percent": 22.71,
            "above_ema200_percent": 31.92,
            "strong_uptrend_percent": 10.06,
            "strong_downtrend_percent": 48.22,
        },
        "volatility": {
            "india_vix": {
                "available": True,
                "value": 14.375,
                "direction": "FALLING",
                "change_percent": -5.92,
                "percentile_1y": 70.3,
                "regime": "MODERATE",
            }
        },
        "derivatives": {
            "available": True,
            "nifty": {
                "underlying": {"spot": 22520.45},
                "pcr": {"oi_pcr": 1.1181, "volume_pcr": 0.8749},
                "max_pain": {"strike": 22500},
            },
            "bank_nifty": {
                "underlying": {"spot": 55256.65},
                "pcr": {"oi_pcr": 0.9255, "volume_pcr": 0.8347},
                "max_pain": {"strike": 55700},
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
                "fii_10d": -52335.00,
                "fii_20d": -57910.10,
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
            {"symbol": "CPPLUS", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
            {"symbol": "BLUSPRING", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
        ],
        "research_factors": {
            "status": "AVAILABLE",
            "top_ranked": [
                {"rank": 1, "symbol": "UEL", "price": 214.94, "composite_z": 1.535},
            ],
        },
        "data_availability": {
            "market_scanner": "AVAILABLE",
            "india_vix": "AVAILABLE",
            "volatility_engine": "AVAILABLE",
            "sector_engine": "AVAILABLE",
            "derivatives_engine": "AVAILABLE",
            "institutional_flow": "READY",
            "event_risk_engine": "AVAILABLE",
            "risk_engine": "AVAILABLE",
        },
    }
    report.update(overrides)
    return report


class TestReportReturn(unittest.TestCase):
    """The report return reader must support both report and scanner keys."""

    def test_report_short_keys(self):
        self.assertEqual(tools._report_return({"1D": 1.3}, "return_1d"), 1.3)
        self.assertEqual(tools._report_return({"20D": -3.9}, "return_20d"), -3.9)

    def test_scanner_style_keys(self):
        self.assertEqual(
            tools._report_return({"return_1d": 0.5}, "return_1d"), 0.5
        )

    def test_missing_and_bad_input_is_none(self):
        self.assertIsNone(tools._report_return({}, "return_5d"))
        self.assertIsNone(tools._report_return(None, "return_5d"))
        self.assertIsNone(tools._report_return("nope", "return_5d"))


class TestBuildFromReport(unittest.TestCase):
    """The cache-first (report-backed) analysis builder."""

    def test_header_and_cache_source(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("NOVA EVIDENCE-GROUNDED NSE MARKET ANALYSIS", text)
        self.assertIn("DATA_SOURCE=LATEST_SAVED_MARKET_LAB_REPORT", text)
        self.assertIn("CACHE-FIRST", text)
        self.assertIn("MARKET_REGIME=BEARISH", text)

    def test_nifty_and_banknifty_returns(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("NIFTY_RETURN_1D=1.30%", text)
        self.assertIn("NIFTY_RETURN_20D=-3.89%", text)
        self.assertIn("BANKNIFTY_RETURN_5D=1.48%", text)

    def test_breadth_from_report(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("ADVANCING=523", text)
        self.assertIn("DECLINING=1466", text)
        self.assertIn("ADVANCE_DECLINE_RATIO=0.36", text)

    def test_vix_rendered_as_scalars(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("INDIA_VIX=14.38", text)
        self.assertIn("VOLATILITY_REGIME=MODERATE", text)

    def test_derivatives_rendered_as_scalars_not_raw_dicts(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("NIFTY_SPOT=22520.45", text)
        self.assertIn("NIFTY_OI_PCR=1.12", text)
        self.assertIn("NIFTY_MAX_PAIN_STRIKE=22500", text)
        self.assertIn("BANKNIFTY_OI_PCR=0.93", text)
        # The report stores nested dicts; they must never leak as raw dicts.
        self.assertNotIn("{'call_oi'", text)
        self.assertNotIn("{'strike'", text)

    def test_institutional_flow_and_signal_honesty(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("FII_SELLING_DII_ABSORPTION", text)
        self.assertIn("FII_20D=-57910.10", text)
        self.assertIn("PRIMARY_VERIFIED_SESSIONS=2/20", text)
        self.assertIn("SIGNAL_ELIGIBLE=NO", text)

    def test_event_risk(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("OVERALL_RISK=MODERATE", text)
        self.assertIn("UPCOMING_EVENTS=5", text)

    def test_top_technical_and_factor_ranked(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("CPPLUS", text)
        self.assertIn("TOP TECHNICAL STOCKS", text)
        self.assertIn("TOP FACTOR-RANKED", text)
        self.assertIn("UEL", text)

    def test_availability_matrix_merges_report_flags(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("INDIA_VIX=AVAILABLE", text)
        self.assertIn("SECTOR_STRENGTH=AVAILABLE", text)
        self.assertIn("DERIVATIVES_OI=AVAILABLE", text)
        self.assertIn("INSTITUTIONAL_FLOW=AVAILABLE", text)
        self.assertIn("EVENT_RISK=AVAILABLE", text)

    def test_full_dataframe_rankings_are_honestly_unavailable(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("MOMENTUM_RANKING=NOT_AVAILABLE", text)
        self.assertIn("RELATIVE_STRENGTH=NOT_AVAILABLE", text)
        self.assertIn("RELATIVE_VOLUME=NOT_AVAILABLE", text)

    def test_guardrails_and_decision_boundary(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        self.assertIn("REASONING GUARDRAILS", text)
        self.assertIn("BUY_SELL_AUTHORIZATION=DISABLED", text)
        self.assertIn("TRADING_EXECUTION=DISABLED", text)
        self.assertIn("CURRENT_STATUS=ANALYSIS_ONLY", text)
        self.assertIn("RULE_1=Never claim data marked NOT_AVAILABLE.", text)

    def test_missing_layers_only_models_without_risk(self):
        text = tools._build_market_analysis_from_report(report_fixture())
        # risk_engine is AVAILABLE in the fixture, so it must NOT be listed.
        self.assertNotIn("RISK_MODEL", text)
        self.assertIn("MISSING_CRITICAL_LAYERS=TRANSACTION_COST_MODEL, "
                      "COVARIANCE_PORTFOLIO_MODEL", text)

    def test_risk_missing_listed_when_unavailable(self):
        report = report_fixture()
        report["data_availability"]["risk_engine"] = "NOT_AVAILABLE"
        text = tools._build_market_analysis_from_report(report)
        self.assertIn("RISK_MODEL", text)

    def test_minimal_report_does_not_crash(self):
        text = tools._build_market_analysis_from_report({"generated": "x"})
        self.assertIn("MARKET_REGIME=UNKNOWN", text)
        # No top technical stocks -> section still present but honest.
        self.assertIn("TOP TECHNICAL STOCKS", text)

    def test_invalid_report_returns_error_text(self):
        self.assertIn(
            "MARKET ANALYSIS ERROR", tools._build_market_analysis_from_report(None)
        )
        self.assertIn(
            "MARKET ANALYSIS ERROR",
            tools._build_market_analysis_from_report("not a dict"),
        )

    def test_factor_ranked_hidden_when_not_available(self):
        report = report_fixture()
        report["research_factors"]["status"] = "NOT_AVAILABLE"
        text = tools._build_market_analysis_from_report(report)
        self.assertNotIn("TOP FACTOR-RANKED", text)


class TestBuildFromScanner(unittest.TestCase):
    """The scanner-backed builder must reproduce the original sections."""

    def _summary(self):
        return {
            "market_regime": "BEARISH",
            "nifty_returns": {
                "return_1d": 1.30,
                "return_5d": 0.44,
                "return_20d": -3.89,
                "return_60d": -6.47,
            },
            "breadth": {"total": 2000, "advancing": 523, "declining": 1466},
            "stocks_in_universe": 2000,
            "stocks_analyzed": 1999,
            "timestamp": "2026-10-10T18:25:33",
        }

    def _df(self):
        import pandas as pd

        return pd.DataFrame(
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
                },
                {
                    "symbol": "BBB",
                    "price": 50.0,
                    "score": 40.0,
                    "trend": "STRONG_DOWNTREND",
                    "rsi_14": 35.0,
                    "relative_volume": 1.1,
                    "return_1d": -0.5,
                    "return_20d": -5.0,
                    "return_60d": -10.0,
                    "relative_strength_20d": -3.0,
                    "relative_strength_60d": -4.0,
                    "macd_condition": "BEARISH",
                    "volume_condition": "CONTRACTION",
                },
            ]
        )

    def test_full_ranking_sections_present(self):
        text = tools._build_market_analysis_from_scanner(
            self._df(), self._summary(), lab_report=None
        )
        for section in (
            "TOP TECHNICAL RANKINGS",
            "TOP MOMENTUM",
            "TOP RELATIVE STRENGTH",
            "TOP VOLUME EXPANSION",
            "STRONG UPTRENDS",
        ):
            self.assertIn(section, text)
        self.assertIn("NIFTY_RETURN_1D=1.30%", text)
        self.assertIn("AAA", text)

    def test_scanner_only_source_when_no_report(self):
        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=None
        ):
            text = tools._build_market_analysis_from_scanner(
                self._df(), self._summary(), lab_report=None
            )
        self.assertIn("AVAILABILITY_SOURCE=SCANNER_ONLY", text)

    def test_scanner_merges_report_when_present(self):
        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=report_fixture()
        ):
            text = tools._build_market_analysis_from_scanner(
                self._df(), self._summary(), lab_report=None
            )
        self.assertIn(
            "AVAILABILITY_SOURCE=SCANNER+LATEST_SAVED_MARKET_LAB_REPORT", text
        )
        self.assertIn("INDIA_VIX=AVAILABLE", text)


class TestCacheFirstDispatch(unittest.TestCase):
    """get_market_analysis() must be cache-first and never scan on a hit."""

    def test_uses_report_and_never_scans_when_report_exists(self):
        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=report_fixture()
        ), mock.patch.object(tools, "scan_market") as scanner:
            out = tools.get_market_analysis()
        scanner.assert_not_called()
        self.assertIn("DATA_SOURCE=LATEST_SAVED_MARKET_LAB_REPORT", out)

    def test_falls_back_to_scanner_when_no_report(self):
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
            "market_regime": "BEARISH",
            "nifty_returns": {"return_1d": 1.0},
            "breadth": {"total": 2000},
            "stocks_in_universe": 2000,
            "stocks_analyzed": 1999,
            "timestamp": "2026-10-10T18:25:33",
        }
        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=None
        ), mock.patch.object(tools, "scan_market", return_value=(df, summary)) as scanner:
            out = tools.get_market_analysis()
        scanner.assert_called_once()
        self.assertIn("TOP TECHNICAL RANKINGS", out)
        self.assertIn("DATA_TIMESTAMP=2026-10-10T18:25:33", out)

    def test_empty_scanner_result_is_reported(self):
        import pandas as pd

        with mock.patch.object(
            tools, "_load_latest_market_lab_report", return_value=None
        ), mock.patch.object(
            tools, "scan_market", return_value=(pd.DataFrame(), {})
        ):
            out = tools.get_market_analysis()
        self.assertIn("MARKET ANALYSIS ERROR", out)
        self.assertIn("no usable stock data", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
