"""
Offline tests for market_lab/view_model.py (the presentation adapter).

Pure functions over a report-shaped dict; no Qt, no network, no backend. These
lock in the key honesty rule: anything the backend does not really provide is
returned as the N/A sentinel and never a fabricated number.

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

from market_lab import view_model as vm


def report_fixture(**overrides):
    report = {
        "generated": "2026-10-10T13:00:00+00:00",
        "market": "NSE",
        "stocks_analyzed": 1999,
        "market_regime": "BEARISH",
        "scanner_file": "",
        "nifty_snapshot": {
            "available": True,
            "price": 22520.45,
            "change_percent": 1.3,
            "open": 22314.95,
            "high": 22580.75,
            "low": 22294.75,
        },
        "nifty_returns": {"1D": 1.3, "5D": -2.0, "20D": -3.9, "60D": -6.5},
        "bank_nifty_returns": {"1D": 1.36, "5D": 1.48, "20D": -1.85, "60D": -4.33},
        "volatility": {
            "india_vix": {
                "available": True, "value": 14.38, "change_percent": -5.9,
                "percentile_1y": 70.3, "regime": "MODERATE", "direction": "FALLING",
            },
            "nifty": {
                "available": True, "price": 22520.45, "atr14": 263.48,
                "atr_percent": 1.17, "realized_volatility_20d": 13.74,
                "volatility_percentile": 74.0, "volatility_regime": "MODERATE",
            },
            "bank_nifty": {
                "available": True, "price": 55256.65, "atr14": 741.31,
                "atr_percent": 1.34, "realized_volatility_20d": 14.72,
                "volatility_regime": "MODERATE",
            },
        },
        "breadth": {
            "advancing": 523, "declining": 1466, "unchanged": 10,
            "advance_decline_ratio": 0.36, "above_ema20_percent": 17.61,
            "above_ema50_percent": 22.71, "above_ema200_percent": 31.92,
            "strong_uptrend_percent": 10.06, "strong_downtrend_percent": 48.22,
        },
        "sector_intelligence": {
            "available": True, "count": 43,
            "top_sectors": [
                {"sector": "IT", "return_20d": 4.2, "relative_strength_20d": 8.1, "regime": "POSITIVE"},
                {"sector": "METAL", "return_20d": -1.5, "relative_strength_20d": -2.0, "regime": "NEGATIVE"},
            ],
        },
        "top_technical_stocks": [
            {"symbol": "AAA", "company_name": "", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
        ],
        "derivatives": {
            "available": True,
            "nifty": {
                "instrument": "NIFTY",
                "underlying": {"spot": 22520.45},
                "expiry": {"selected": "13-Oct-2026"},
                "pcr": {"oi_pcr": 1.118, "volume_pcr": 0.875},
                "max_pain": {"strike": 22500.0},
                "oi_walls": {"put_wall": 22500, "call_wall": 23000},
                "support_resistance": {"support": 22500, "resistance": 23000},
                "iv_structure": {"atm_iv": 11.10},
                "unusual_activity": [
                    {"type": "CALL", "strike": 22500, "state": "OI UNWINDING"},
                ],
                "timestamp": "2026-10-10T18:57:08+05:30",
            },
        },
        "institutional_flow": {
            "available": True, "signal_allowed": False,
            "source_quality": "MIXED_SOURCE_TARGET_WINDOW",
            "metrics": {
                "fii_5d": -41330.14, "dii_5d": 37629.94,
                "fii_10d": -52335.0, "dii_10d": 54807.67,
                "fii_20d": -57910.1, "dii_20d": 84541.97,
                "fii_streak_direction": "SELLING", "fii_streak_days": 6,
                "dii_streak_direction": "BUYING", "dii_streak_days": 22,
                "flow_regime": "FII_SELLING_DII_ABSORPTION",
                "primary_combined_sessions": 2, "target_sessions": 20,
                "latest_date": "2026-10-09", "flow_unit": "INR crore",
                "source_counts": {
                    "SECONDARY_DAILY_MIRROR:groww": 20,
                    "NSE_PRIMARY_COMBINED_VERIFIED": 2,
                },
            },
        },
        "risk_context": {
            "available": True, "execution_enabled": False,
            "buy_sell_authorization": False,
            "instruments": {
                "nifty": {
                    "price": 22520.45, "atr_pct": 1.17,
                    "realized_volatility_20d": 13.74,
                    "volatility_percentile": 74.0,
                    "volatility_regime": "MODERATE",
                    "expected_daily_move_percent": 0.8658,
                },
            },
        },
        "event_risk_context": {
            "status": "AVAILABLE", "overall_risk": "MODERATE",
            "upcoming_event_count": 5, "source_fresh": True,
            "upcoming_events": [],
        },
        "research_factors": {
            "status": "AVAILABLE",
            "method": "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT",
            "as_of": "2026-10-09T00:00:00+05:30",
            "universe_size": 1999,
            "factors": {
                "MOMENTUM_60D": {}, "RELATIVE_STRENGTH": {},
                "LOW_VOLATILITY": {}, "TREND_STRUCTURE": {},
                "PROXIMITY_52W_HIGH": {},
            },
            "top_ranked": [
                {"rank": 1, "symbol": "UEL", "price": 214.94,
                 "composite_z": 1.448,
                 "factor_z": {"MOMENTUM_60D": None, "RELATIVE_STRENGTH": None,
                              "LOW_VOLATILITY": None, "TREND_STRUCTURE": None,
                              "PROXIMITY_52W_HIGH": None}},
            ],
            "bottom_ranked": [
                {"rank": 1, "symbol": "ATALREAL", "price": 11.34,
                 "composite_z": -1.3508,
                 "factor_z": {"MOMENTUM_60D": None, "RELATIVE_STRENGTH": None,
                              "LOW_VOLATILITY": None, "TREND_STRUCTURE": None,
                              "PROXIMITY_52W_HIGH": None}},
            ],
            "warnings": ["Fundamental factors (value, quality, growth) are NOT computed.",
                         "not buy/sell signals."],
        },
        "data_availability": {"market_scanner": "AVAILABLE", "india_vix": "AVAILABLE"},
        "decision_policy": {"buy_sell_authorized": False, "trading_execution": False},
    }
    report.update(overrides)
    return report


NA = vm.N_A


class TestNum(unittest.TestCase):
    def test_num_rejects_bad(self):
        self.assertIsNone(vm._num(None))
        self.assertIsNone(vm._num("abc"))
        self.assertIsNone(vm._num(float("nan")))
        self.assertIsNone(vm._num(True))
        self.assertEqual(vm._num("3.5"), 3.5)


class TestFreshness(unittest.TestCase):
    def test_thresholds(self):
        self.assertEqual(vm.freshness(600)[0], "green")
        self.assertEqual(vm.freshness(2 * 3600)[0], "amber")
        self.assertEqual(vm.freshness(12 * 3600)[0], "red")
        self.assertEqual(vm.freshness(20 * 3600)[0], "critical")
        self.assertIn("16 HOURS", vm.freshness(20 * 3600)[1])

    def test_unknown(self):
        self.assertEqual(vm.freshness(None)[0], NA)


class TestSession(unittest.TestCase):
    def test_weekend(self):
        sat = datetime.datetime(2026, 10, 10, 12, 0, tzinfo=vm._IST)
        self.assertEqual(vm.session_status(sat)["label"], "WEEKEND")

    def test_open(self):
        mon_open = datetime.datetime(2026, 10, 12, 10, 0, tzinfo=vm._IST)
        self.assertEqual(vm.session_status(mon_open)["label"], "OPEN")

    def test_closed_after_hours(self):
        mon_eve = datetime.datetime(2026, 10, 12, 16, 0, tzinfo=vm._IST)
        self.assertEqual(vm.session_status(mon_eve)["label"], "CLOSED")


class TestDataAge(unittest.TestCase):
    def test_age_from_generated(self):
        now = datetime.datetime(2026, 10, 10, 15, 0, tzinfo=datetime.timezone.utc)
        r = report_fixture(generated="2026-10-10T13:00:00+00:00")  # 2h old
        info = vm.data_age(r, now=now)
        self.assertAlmostEqual(info["age_seconds"], 7200, delta=1)

    def test_missing_generated_is_na(self):
        self.assertEqual(vm.data_age({})["age_seconds"], None)


class TestIndexCard(unittest.TestCase):
    def test_nifty_card_real_and_derived(self):
        card = vm.index_card(report_fixture(), "nifty")
        self.assertEqual(card["price"], 22520.45)
        self.assertEqual(card["change_percent"], 1.3)
        self.assertAlmostEqual(card["prev_close"], 22520.45 / 1.013, places=0)
        self.assertIsNotNone(card["change_abs"])
        self.assertTrue(card["derived_abs_change"])
        self.assertEqual(card["open"], 22314.95)
        self.assertEqual(card["high"], 22580.75)
        self.assertEqual(card["chart"], NA)  # no series -> unavailable

    def test_banknifty_card_ohlc_is_na(self):
        card = vm.index_card(report_fixture(), "bank_nifty")
        self.assertEqual(card["name"], "BANK NIFTY")
        self.assertEqual(card["price"], 55256.65)
        self.assertEqual(card["open"], NA)  # snapshot only for NIFTY
        self.assertEqual(card["high"], NA)

    def test_card_includes_series(self):
        report = report_fixture(
            nifty_series=[{"date": "2026-10-01", "close": 100.0}],
            bank_nifty_series=[{"date": "2026-10-01", "close": 200.0}],
        )
        self.assertEqual(len(vm.index_card(report, "nifty")["series"]), 1)
        self.assertEqual(len(vm.index_card(report, "bank_nifty")["series"]), 1)
        # no series in report -> empty list (chart shows 'no series')
        self.assertEqual(vm.index_card(report_fixture(), "nifty")["series"], [])

    def test_bank_card_ohlc_derived_from_candle(self):
        report = report_fixture(
            bank_nifty_candles=[
                {"t": "2026-10-09", "o": 100.0, "h": 110.0,
                 "l": 95.0, "c": 105.0, "v": 1},
            ]
        )
        card = vm.index_card(report, "bank_nifty")
        self.assertEqual(card["open"], 100.0)
        self.assertEqual(card["high"], 110.0)
        self.assertEqual(card["low"], 95.0)
        self.assertEqual(len(card["candles"]), 1)


class TestIndicatorCards(unittest.TestCase):
    def test_only_atr_is_real(self):
        cards = vm.indicator_cards(report_fixture(), "nifty")
        self.assertEqual(cards["ATR"]["value"], 263.48)
        self.assertEqual(cards["RSI"]["value"], NA)
        self.assertEqual(cards["MACD"]["value"], NA)
        self.assertEqual(cards["VOL"]["value"], 13.74)


class TestSector(unittest.TestCase):
    def test_rows_and_order(self):
        rows = vm.sector_rows(report_fixture(), limit=5)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["name"], "IT")
        self.assertEqual(rows[0]["return_20d"], 4.2)

    def test_unavailable_sector_is_empty(self):
        r = report_fixture(sector_intelligence={"available": False})
        self.assertEqual(vm.sector_rows(r), [])


class TestFactorBlock(unittest.TestCase):
    def test_quality_and_value_declared_unavailable(self):
        fb = vm.factor_block(report_fixture())
        self.assertIn("QUALITY", fb["factors_unavailable"])
        self.assertIn("VALUE", fb["factors_unavailable"])
        self.assertIn("MOMENTUM_60D", fb["factors_available"])
        self.assertEqual(fb["method"], "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT")

    def test_per_factor_z_unavailable_when_null(self):
        fb = vm.factor_block(report_fixture())
        self.assertFalse(fb["per_factor_z_available"])
        self.assertEqual(fb["top"][0]["symbol"], "UEL")
        self.assertEqual(fb["top"][0]["composite_z"], 1.448)

    def test_not_available_status(self):
        r = report_fixture(research_factors={"status": "NOT_AVAILABLE"})
        self.assertEqual(vm.factor_block(r)["status"], "NOT_AVAILABLE")


class TestBreadth(unittest.TestCase):
    def test_real_and_na(self):
        b = vm.breadth_block(report_fixture())
        self.assertEqual(b["advancing"], 523)
        self.assertEqual(b["declining"], 1466)
        self.assertEqual(b["ad_ratio"], 0.36)
        self.assertEqual(b["new_52w_highs"], NA)
        self.assertEqual(b["mcclellan_summation"], NA)


class TestTechnical(unittest.TestCase):
    def test_top_stocks_and_na_lists(self):
        t = vm.technical_block(report_fixture())
        self.assertEqual(t["top_stocks"][0]["symbol"], "AAA")
        self.assertEqual(t["rsi_oversold"], NA)
        self.assertEqual(t["macd_crossovers"], NA)


class TestDerivatives(unittest.TestCase):
    def test_real_fields(self):
        d = vm.derivatives_block(report_fixture(), "nifty")
        self.assertEqual(d["oi_pcr"], 1.118)
        self.assertEqual(d["max_pain"], 22500.0)
        self.assertEqual(d["atm_iv"], 11.10)
        self.assertEqual(d["put_wall"], 22500)
        self.assertEqual(d["stock_oi_buildup_list"], NA)


class TestFlow(unittest.TestCase):
    def test_real_and_coverage(self):
        f = vm.flow_block(report_fixture())
        self.assertEqual(f["fii_20d"], -57910.1)
        self.assertEqual(f["dii_20d"], 84541.97)
        self.assertEqual(f["primary_verified"], 2)
        self.assertEqual(f["target_sessions"], 20)
        self.assertFalse(f["signal_allowed"])


class TestRisk(unittest.TestCase):
    def test_portfolio_metrics_na_context_real(self):
        rk = vm.risk_block(report_fixture())
        self.assertEqual(rk["var_95"], NA)
        self.assertEqual(rk["sharpe"], NA)
        self.assertEqual(rk["provided"]["realized_volatility_20d"], 13.74)


class TestEarningsAndGuardrails(unittest.TestCase):
    def test_earnings_unavailable(self):
        self.assertFalse(vm.earnings_block(report_fixture())["available"])

    def test_guardrails(self):
        g = vm.guardrails(report_fixture())
        self.assertFalse(g["buy_sell_authorization"])
        self.assertIn("not a buy/sell signal", g["text"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
