"""Offline tests for analysis/data/quant_engine.py on synthetic data with known answers."""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import quant_engine as q


def history(returns, start=100.0, volume=1_000_000, spread=0.01):
    close = start * np.cumprod(1 + np.asarray(returns, dtype=float))
    idx = pd.bdate_range("2025-11-03", periods=len(close))
    return pd.DataFrame({"Open": close, "High": close * (1 + spread), "Low": close * (1 - spread), "Close": close, "Volume": volume}, index=idx)


def universe(n=400, seed=7):
    rng = np.random.default_rng(seed)
    price = rng.uniform(50, 2000, n)
    return pd.DataFrame({
        "symbol": [f"S{i:03d}" for i in range(n)], "price": price,
        "return_1d": rng.normal(0, 2, n), "return_5d": rng.normal(0, 4, n), "return_20d": rng.normal(0, 8, n), "return_60d": rng.normal(0, 15, n),
        "relative_strength_20d": rng.normal(0, 8, n), "relative_strength_60d": rng.normal(0, 15, n),
        "ema_20": price * rng.uniform(0.9, 1.1, n), "ema_50": price * rng.uniform(0.85, 1.15, n), "ema_200": price * rng.uniform(0.7, 1.3, n),
        "rsi_14": rng.uniform(20, 80, n), "atr_percent": rng.uniform(1, 6, n), "volume": rng.uniform(1e4, 1e7, n),
        "volume_average_20": rng.uniform(1e4, 1e7, n), "relative_volume": rng.uniform(0.3, 3, n),
        "distance_52w_high": rng.uniform(0, 50, n), "distance_52w_low": rng.uniform(0, 80, n), "score": rng.uniform(0, 100, n),
        "sector": [f"Sector {i % 10}" for i in range(n)],
    })


class TestRiskProfile(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(1)
        self.rb = rng.normal(0.0004, 0.01, 250)
        self.bench = history(self.rb, start=20000)["Close"]

    def test_beta_and_correlation_of_a_levered_benchmark(self):
        out = q.risk_profile(history(1.5 * self.rb), self.bench)
        b = out["benchmark"]
        self.assertEqual(out["status"], "AVAILABLE")
        self.assertAlmostEqual(b["beta"], 1.5, places=2)
        self.assertAlmostEqual(b["correlation"], 1.0, places=2)
        self.assertAlmostEqual(b["alpha_annual_pct"], 0.0, places=1)
        self.assertGreater(b["up_capture_pct"], 140)

    def test_volatility_var_and_ratios(self):
        r = np.tile([0.01, -0.01], 125)  # known daily stdev ~1%
        out = q.risk_profile(history(r))
        self.assertAlmostEqual(out["volatility"]["vol_full_pct"], 0.01 * np.sqrt(252) * 100, delta=0.2)
        self.assertAlmostEqual(out["tail"]["var_95_pct"], 1.0, places=2)
        self.assertAlmostEqual(out["tail"]["cvar_95_pct"], 1.0, places=2)
        self.assertEqual(out["benchmark"]["status"], "NOT_AVAILABLE")  # no benchmark passed: flagged, not invented

    def test_drawdown_dates_and_depth(self):
        r = [0.0] * 60 + [-0.05] * 4 + [0.01] * 10  # 100 -> 81.45 -> 89.97: still under the peak
        d = q.risk_profile(history(r))["drawdown"]
        self.assertAlmostEqual(d["max_pct"], (0.95 ** 4 - 1) * 100, places=1)
        self.assertAlmostEqual(d["current_pct"], (0.95 ** 4 * 1.01 ** 10 - 1) * 100, places=1)
        self.assertEqual(d["sessions_underwater"], 14)
        self.assertEqual(d["longest_underwater"], 14)

    def test_liquidity_and_days_to_exit(self):
        out = q.risk_profile(history([0.0] * 100, start=100, volume=1_000_000))  # Rs 10 Cr a day
        liq = out["liquidity"]
        self.assertAlmostEqual(liq["adv_20d_cr"], 10.0, places=2)
        self.assertEqual(liq["days_to_exit"][0], {"notional_cr": 10, "days": 10.0})  # 10 Cr at 10% of 10 Cr a day
        self.assertEqual(liq["days_to_exit"][2]["days"], 250.0)

    def test_trend_fit_of_a_straight_line(self):
        out = q.risk_profile(history([0.002] * 150))
        fit = out["trend_quality"]["fit_60d"]
        self.assertAlmostEqual(fit["r_squared"], 1.0, places=2)
        self.assertAlmostEqual(fit["slope_annual_pct"], ((1.002 ** 252) - 1) * 100, delta=0.5)
        self.assertAlmostEqual(out["trend_quality"]["efficiency_20d"], 1.0, places=2)

    def test_volume_profile_poc_sits_where_volume_traded(self):
        h = history([0.0] * 100, spread=0.001)
        h.iloc[-30:, h.columns.get_loc("Volume")] = 50_000_000  # heavy volume after a jump to 120
        for c in ("Open", "High", "Low", "Close"):
            h.iloc[-30:, h.columns.get_loc(c)] *= 1.2
        vp = q.risk_profile(h)["volume_profile"]
        self.assertGreater(vp["poc"], 115)
        self.assertLessEqual(vp["value_area_low"], vp["poc"])
        self.assertGreaterEqual(vp["value_area_high"], vp["poc"])
        self.assertAlmostEqual(sum(b["share_pct"] for b in vp["bins"]), 100, delta=0.5)

    def test_short_or_missing_history_is_flagged(self):
        self.assertEqual(q.risk_profile(history([0.01] * 20))["status"], "NOT_AVAILABLE")
        self.assertEqual(q.risk_profile(pd.DataFrame({"Close": [1, 2]}))["status"], "NOT_AVAILABLE")

    def test_timezone_aware_benchmark_aligns(self):
        bench = self.bench.copy()
        bench.index = bench.index.tz_localize("Asia/Kolkata")
        self.assertEqual(q.risk_profile(history(self.rb), bench)["benchmark"]["sessions"], 249)


class TestCrossSection(unittest.TestCase):
    def setUp(self):
        self.d = q.prepare(universe())

    def test_internals_counts_and_tiers(self):
        m = q.market_internals(self.d)
        b = m["breadth"]
        self.assertEqual(b["advancing"] + b["declining"] + b["unchanged"], 400)
        self.assertEqual([t["stocks"] for t in m["tiers"]], [100, 300])  # 400 names: top 100, next 300, no rest
        self.assertLessEqual(m["concentration"]["top10_share_pct"], 100)
        self.assertIn("%", m["regime"]["rule"])

    def test_52w_distance_is_a_magnitude(self):
        d = self.d.copy()
        d["below_high"] = 20.0
        d.loc[:4, "below_high"] = 0.0  # five stocks sitting on their high
        b = q.market_internals(d)["breadth"]
        self.assertEqual(b["new_highs"], 5)
        self.assertAlmostEqual(b["within_5pct_of_high_pct"], 5 / 400 * 100, delta=0.1)

    def test_small_universe_is_refused(self):
        self.assertEqual(q.market_internals(self.d.head(50))["status"], "NOT_AVAILABLE")

    def test_rotation_quadrants(self):
        d = self.d.copy()
        d[["return_60d", "return_20d"]] = 0.0  # the median stock is flat, so sector medians are the excess
        d.loc[d["sector"] == "Sector 0", ["return_60d", "return_20d"]] = [12.0, 9.0]   # y = 9 - 4 = +5
        d.loc[d["sector"] == "Sector 1", ["return_60d", "return_20d"]] = [12.0, 1.0]   # y = 1 - 4 = -3
        d.loc[d["sector"] == "Sector 2", ["return_60d", "return_20d"]] = [-9.0, 2.0]   # y = 2 + 3 = +5
        d.loc[d["sector"] == "Sector 3", ["return_60d", "return_20d"]] = [-9.0, -8.0]  # y = -8 + 3 = -5
        got = {r["sector"]: r["quadrant"] for r in q.sector_rotation(d)["sectors"]}
        self.assertEqual([got[f"Sector {i}"] for i in range(4)], ["Leading", "Weakening", "Improving", "Lagging"])

    def test_factor_spread_recovers_a_planted_effect(self):
        base = self.d.copy()
        now = base[["symbol", "price"]].copy()
        now["price"] = base["price"] * (1 + base["return_60d"] / 1000)  # forward return rises with 60D momentum
        now.loc[0, "price"] = base.loc[0, "price"] * 5                    # a 5-for-1 "split" must be dropped
        s = q.factor_spreads(base, now)
        mom = next(f for f in s["factors"] if f["factor"] == "Momentum 60D")
        self.assertEqual(s["dropped_corporate_action_suspects"], 1)
        self.assertGreater(mom["spread_pct"], 0)
        self.assertGreater(mom["ic"], 0.95)
        self.assertTrue(mom["monotonic"])

    def test_scorecard_ranks_the_best_stock_at_the_top(self):
        d = self.d.copy()
        best = {"vs_ema200": 99.0, "vs_ema50": 99.0, "return_60d": 99.0, "return_20d": 99.0, "below_high": 0.0, "atr_percent": 0.5}
        for k, v in best.items():
            d.loc[0, k] = v
        c = q.scorecard(d, "s000")
        self.assertGreaterEqual(c["composite"], 99)
        self.assertEqual(c["stance"], "Top quartile")
        self.assertEqual(len(c["pillars"]), 4)
        self.assertIsNotNone(c["pillars"][0]["sector_pct"])
        self.assertFalse(c["buy_sell_authorization"])
        self.assertEqual(q.scorecard(d, "NOPE")["status"], "NOT_AVAILABLE")

    def test_conflicts_name_the_contradiction(self):
        d = self.d.copy()
        d.loc[0, ["return_60d", "return_20d", "rsi_14"]] = [99.0, 99.0, 82.0]
        self.assertTrue(any("RSI 82" in t for t in q.scorecard(d, "S000")["conflicts"]))

    def test_read_lines_never_issue_a_trade_call(self):
        m, rot = q.market_internals(self.d), q.sector_rotation(self.d)
        text = " ".join(l["text"] for l in q.internals_read(m, rot, None)).lower()
        self.assertTrue(text)
        for word in ("buy", "sell", "target", "should"):
            self.assertNotIn(word, text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
