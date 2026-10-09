"""
Reference-value tests for Nova's analysis math engines.

Small hand-computed fixtures only: no network, no caches, no live market
data. Run from the project root:

    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data.technical_engine import (
    MACD_SLOW,
    RSI_PERIOD,
    calculate_atr as technical_atr,
    calculate_ema,
    calculate_macd,
    calculate_relative_volume,
    calculate_roc,
    calculate_rsi,
    calculate_sma,
    calculate_true_range as technical_true_range,
    calculate_vwap,
)
from analysis.data.volatility_engine import (
    calculate_atr as volatility_atr,
    calculate_realized_volatility,
    calculate_true_range as volatility_true_range,
    calculate_volatility_percentile,
    classify_volatility_direction,
    classify_volatility_regime,
)
from analysis.data.risk_engine import calculate_position_risk
from analysis.data.event_risk_engine import build_event_risk_context


# ---------------------------------------------------------------------------
# FIXTURES
# ---------------------------------------------------------------------------

def ohlc_frame(close, high=None, low=None, volume=100.0):
    """Build a minimal OHLCV frame from a close series."""
    close = pd.Series(close, dtype=float)
    if high is None:
        high = close + 1.0
    if low is None:
        low = close - 1.0
    return pd.DataFrame(
        {
            "High": pd.Series(high, dtype=float),
            "Low": pd.Series(low, dtype=float),
            "Close": close,
            "Volume": float(volume),
        }
    )


def tr_frame(tr_values):
    """
    Build OHLC rows engineered so True Range equals each given value.

    Each bar opens at the previous close (no gaps), so the only
    contribution to True Range is the bar's own high-low span.
    """
    previous_close = 100.0
    records = []
    for tr in tr_values:
        low = previous_close
        high = previous_close + tr
        records.append(
            {"High": high, "Low": low, "Close": high, "Volume": 100.0}
        )
        previous_close = high
    return pd.DataFrame(records)


# ---------------------------------------------------------------------------
# TECHNICAL ENGINE
# ---------------------------------------------------------------------------

class TestTechnicalEngineMath(unittest.TestCase):

    def test_sma_known_window(self):
        sma = calculate_sma(pd.Series([float(i) for i in range(1, 11)]), 5)
        self.assertTrue(pd.isna(sma.iloc[3]))
        self.assertEqual(sma.iloc[-1], 8.0)  # mean(6,7,8,9,10)

    def test_ema_constant_series(self):
        ema = calculate_ema(pd.Series([42.0] * 30), 14)
        self.assertFalse(pd.isna(ema.iloc[-1]))
        self.assertAlmostEqual(ema.iloc[-1], 42.0, places=9)

    def test_rsi_only_gains_is_100(self):
        close = pd.Series([100.0 + i for i in range(30)])
        rsi = calculate_rsi(close)
        self.assertTrue(pd.isna(rsi.iloc[RSI_PERIOD - 1]))  # warm-up
        self.assertAlmostEqual(rsi.iloc[-1], 100.0)

    def test_rsi_only_losses_is_0(self):
        close = pd.Series([200.0 - i for i in range(30)])
        rsi = calculate_rsi(close)
        self.assertAlmostEqual(rsi.iloc[-1], 0.0)

    def test_rsi_mixed_series_stays_bounded(self):
        close = pd.Series(
            [100, 103, 99, 104, 98, 105, 97, 106, 96, 107, 95,
             108, 94, 109, 93, 110, 92, 111, 91, 112, 90, 113],
            dtype=float,
        )
        last = calculate_rsi(close).iloc[-1]
        self.assertFalse(pd.isna(last))
        self.assertTrue(0.0 <= last <= 100.0)

    def test_macd_constant_series_is_zero(self):
        macd, signal, histogram = calculate_macd(
            pd.Series([50.0] * (MACD_SLOW + 20))
        )
        self.assertAlmostEqual(macd.iloc[-1], 0.0, places=9)
        self.assertAlmostEqual(signal.iloc[-1], 0.0, places=9)
        self.assertAlmostEqual(histogram.iloc[-1], 0.0, places=9)

    def test_true_range_gap_up(self):
        frame = pd.DataFrame(
            {
                "High": [102.0, 110.0],
                "Low": [100.0, 105.0],
                "Close": [101.0, 109.0],
            }
        )
        true_range = technical_true_range(frame)
        self.assertAlmostEqual(true_range.iloc[0], 2.0)  # high - low
        # max(110-105, |110-101|, |105-101|) = 9
        self.assertAlmostEqual(true_range.iloc[1], 9.0)

    def test_true_range_engines_agree(self):
        frame = tr_frame([2.0, 4.0, 6.0, 3.0, 8.0])
        pd.testing.assert_series_equal(
            technical_true_range(frame),
            volatility_true_range(frame),
            check_names=False,
        )

    def test_atr_wilder_constant_range(self):
        atr = technical_atr(tr_frame([4.0] * 30))
        self.assertAlmostEqual(atr.iloc[-1], 4.0, places=9)

    def test_roc_known_percent(self):
        roc = calculate_roc(pd.Series([100.0, 110.0]), period=1)
        self.assertAlmostEqual(roc.iloc[-1], 10.0)

    def test_relative_volume_constant_is_one(self):
        rvol = calculate_relative_volume(pd.Series([1000.0] * 25), period=20)
        self.assertAlmostEqual(rvol.iloc[-1], 1.0)

    def test_vwap_flat_prices(self):
        flat = [10.0] * 25
        frame = ohlc_frame(flat, high=flat, low=flat, volume=100.0)
        vwap = calculate_vwap(frame, period=20)
        self.assertAlmostEqual(vwap.iloc[-1], 10.0)


# ---------------------------------------------------------------------------
# VOLATILITY ENGINE
# ---------------------------------------------------------------------------

class TestVolatilityEngineMath(unittest.TestCase):

    def test_atr_rolling_mean_known_values(self):
        atr = volatility_atr(tr_frame([2.0, 4.0, 6.0]), period=3)
        self.assertTrue(pd.isna(atr.iloc[1]))  # window not full
        self.assertAlmostEqual(atr.iloc[-1], 4.0)  # (2 + 4 + 6) / 3

    def test_realized_vol_constant_prices_is_zero(self):
        vol = calculate_realized_volatility(ohlc_frame([100.0] * 40), 20)
        self.assertAlmostEqual(vol.iloc[-1], 0.0)

    def test_realized_vol_constant_growth_is_near_zero(self):
        close = pd.Series([100.0 * (1.01 ** i) for i in range(40)])
        vol = calculate_realized_volatility(ohlc_frame(close), 20)
        self.assertLess(abs(vol.iloc[-1]), 1e-9)

    def test_percentile_ascending_series_is_100(self):
        series = pd.Series([float(i) for i in range(1, 26)])
        pct = calculate_volatility_percentile(series, lookback=25)
        self.assertAlmostEqual(pct.iloc[-1], 100.0)

    def test_percentile_lowest_value_is_four_percent(self):
        # Descending 25..1: current value 1 is <= exactly 1 of 25 values.
        series = pd.Series([float(i) for i in range(25, 0, -1)])
        pct = calculate_volatility_percentile(series, lookback=25)
        self.assertAlmostEqual(pct.iloc[-1], 4.0)

    def test_percentile_requires_twenty_points(self):
        series = pd.Series([float(i) for i in range(1, 20)])
        pct = calculate_volatility_percentile(series, lookback=25)
        self.assertTrue(pct.dropna().empty)

    def test_regime_thresholds_percentile_path(self):
        self.assertEqual(classify_volatility_regime(None, None), "UNKNOWN")
        self.assertEqual(classify_volatility_regime(0.20, 90), "EXTREME")
        self.assertEqual(classify_volatility_regime(0.20, 75), "ELEVATED")
        self.assertEqual(classify_volatility_regime(0.20, 40), "MODERATE")
        self.assertEqual(classify_volatility_regime(0.20, 39.9), "LOW")

    def test_regime_thresholds_absolute_fallback(self):
        self.assertEqual(classify_volatility_regime(0.36, None), "EXTREME")
        self.assertEqual(classify_volatility_regime(0.25, None), "ELEVATED")
        self.assertEqual(classify_volatility_regime(0.15, None), "MODERATE")
        self.assertEqual(classify_volatility_regime(0.14, None), "LOW")

    def test_direction_classification_rules(self):
        expanding = pd.Series([0.10] * 5 + [0.20] * 5)
        contracting = pd.Series([0.20] * 5 + [0.10] * 5)
        stable = pd.Series([0.15] * 12)
        too_short = pd.Series([0.10] * 9)
        with_zero = pd.Series([0.0] * 5 + [0.05] * 5)

        self.assertEqual(
            classify_volatility_direction(expanding), "EXPANDING"
        )
        self.assertEqual(
            classify_volatility_direction(contracting), "CONTRACTING"
        )
        self.assertEqual(classify_volatility_direction(stable), "STABLE")
        self.assertEqual(classify_volatility_direction(too_short), "UNKNOWN")
        self.assertEqual(classify_volatility_direction(with_zero), "UNKNOWN")


# ---------------------------------------------------------------------------
# RISK ENGINE
# ---------------------------------------------------------------------------

class TestRiskEngineMath(unittest.TestCase):

    def test_position_sizing_known_values(self):
        result = calculate_position_risk(
            entry_price=100.0,
            stop_price=95.0,
            target_price=110.0,
            account_equity=100_000.0,
            risk_pct=0.5,
        )
        self.assertTrue(result["available"])
        self.assertEqual(result["risk_budget"], 500.0)  # 0.5% of 100k
        self.assertEqual(result["risk_per_unit"], 5.0)
        self.assertEqual(result["quantity"], 100)  # 500 // 5
        self.assertEqual(result["position_value"], 10_000.0)
        self.assertEqual(result["estimated_stop_loss"], 500.0)
        self.assertEqual(result["estimated_target_profit"], 1_000.0)
        self.assertAlmostEqual(result["risk_reward_ratio"], 2.0)  # 10 / 5
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["buy_sell_authorization"])

    def test_invalid_inputs_are_rejected(self):
        no_entry = calculate_position_risk(0, 95, 110, 100_000)
        self.assertFalse(no_entry["available"])
        self.assertIn("Entry price", no_entry["reason"])

        same_stop = calculate_position_risk(100, 100, 110, 100_000)
        self.assertFalse(same_stop["available"])

        zero_pct = calculate_position_risk(
            100, 95, 110, 100_000, risk_pct=0
        )
        self.assertFalse(zero_pct["available"])

    def test_budget_too_small_warns_but_succeeds(self):
        result = calculate_position_risk(
            100, 99, 110, 100, risk_pct=0.5
        )
        # Budget 0.5 < risk per unit 1.0 -> quantity 0 with a warning.
        self.assertTrue(result["available"])
        self.assertEqual(result["quantity"], 0)
        self.assertTrue(
            any("smaller than" in w for w in result["warnings"])
        )


# ---------------------------------------------------------------------------
# EVENT RISK ENGINE
# ---------------------------------------------------------------------------

class TestEventRiskMath(unittest.TestCase):

    NOW = "2026-10-10T12:00:00+05:30"

    @staticmethod
    def event(hours, severity="HIGH", verified=True):
        when = datetime.fromisoformat(
            TestEventRiskMath.NOW
        ) + timedelta(hours=hours)
        return {
            "name": f"Fixture event in {hours}h",
            "datetime": when.isoformat(),
            "category": "TEST",
            "severity": severity,
            "instruments": ["NIFTY"],
            "source": "UNIT_TEST_FIXTURE",
            "verified": verified,
            "impact_note": "",
        }

    def build(self, events, checked_at=None, complete=True):
        return build_event_risk_context(
            events=events,
            source_checked_at=checked_at or self.NOW,
            calendar_complete=complete,
            now=self.NOW,
        )

    def test_fresh_complete_empty_calendar_is_low_all_clear(self):
        context = self.build([])
        self.assertEqual(context["status"], "AVAILABLE")
        self.assertEqual(context["overall_risk"], "LOW")

    def test_stale_source_is_unknown(self):
        context = self.build(
            [], checked_at="2026-10-08T12:00:00+05:30"
        )
        self.assertEqual(context["status"], "NOT_AVAILABLE")
        self.assertEqual(context["overall_risk"], "UNKNOWN")

    def test_incomplete_calendar_is_unknown(self):
        context = self.build([], complete=False)
        self.assertEqual(context["status"], "NOT_AVAILABLE")
        self.assertEqual(context["overall_risk"], "UNKNOWN")

    def test_score_escalates_with_proximity(self):
        near = self.build([self.event(5)])
        # HIGH(3) within 6 h -> +2 -> 5 -> CRITICAL
        self.assertEqual(near["overall_risk"], "CRITICAL")
        self.assertEqual(near["upcoming_event_count"], 1)

        far = self.build([self.event(48)])
        # HIGH(3), more than 24 h away -> 3 -> MODERATE
        self.assertEqual(far["overall_risk"], "MODERATE")

    def test_unverified_event_is_rejected(self):
        context = self.build([self.event(5, verified=False)])
        self.assertEqual(context["upcoming_event_count"], 0)
        self.assertTrue(
            any("rejected" in w for w in context["warnings"])
        )

    def test_naive_timestamp_is_rejected(self):
        event = self.event(5)
        event["datetime"] = "2026-10-11T10:00:00"  # no timezone
        context = self.build([event])
        self.assertEqual(context["upcoming_event_count"], 0)

    def test_past_and_beyond_horizon_events_are_ignored(self):
        context = self.build([self.event(-5), self.event(24 * 8)])
        self.assertEqual(context["upcoming_event_count"], 0)

    def test_guardrails_always_disabled(self):
        context = self.build([])
        policy = context["decision_policy"]
        self.assertFalse(policy["trading_execution"])
        self.assertFalse(policy["buy_sell_authorization"])
        self.assertFalse(policy["event_risk_is_a_buy_sell_signal"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


