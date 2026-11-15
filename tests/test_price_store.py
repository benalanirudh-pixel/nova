"""Offline tests for the price store and the research engine. No network: the archive is faked."""
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import price_store as ps
from analysis.data import research_engine as re_

HEAD = "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"


def day_csv(d: date, rows) -> bytes:
    """rows: (symbol, series, prev_close, close, volume, deliv_pct or '-')."""
    stamp = d.strftime("%d-%b-%Y")
    body = "".join(f"{s}, {ser}, {stamp}, {pc}, {c}, {c}, {c}, {c}, {c}, {c}, {v}, {c * v / 1e5:.2f}, 10, {'-' if dp == '-' else int(v * dp / 100)}, {dp}\n"
                   for s, ser, pc, c, v, dp in rows)
    return (HEAD + body).encode()


class FakeArchive:
    """Answers the archive and corporate-action URLs from memory; everything else is a 404."""

    def __init__(self, days, changes=b"NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\n", actions=()):
        self.days, self.changes, self.actions, self.calls = days, changes, list(actions), []

    def get(self, url, params=None, **_):
        self.calls.append(url)
        if url == ps.ACTIONS_API:
            year = params["from_date"][-4:]
            return SimpleNamespace(status_code=200, json=lambda: [a for a in self.actions if a["exDate"].endswith(year)])
        if url == ps.SYMBOL_CHANGES:
            return SimpleNamespace(status_code=200, content=self.changes)
        for d, raw in self.days.items():
            if url == ps.ARCHIVE.format(d):
                return SimpleNamespace(status_code=200, content=raw)
        return SimpleNamespace(status_code=404, content=b"<html>not found</html>")


def action(symbol, ex, subject, face="10"):
    return {"symbol": symbol, "series": "EQ", "exDate": ex, "subject": subject, "faceVal": face}


class StoreCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.con = ps.connect(Path(self.tmp.name) / "p.sqlite")
        self.addCleanup(self.con.close)

    def load(self, days, start, end, **kw):
        fake = FakeArchive(days, **kw)
        out = ps.update(start=start, end=end, con=self.con, session=fake, log=lambda *_: None, pause=0)
        return fake, out

    def three_days(self, closes, **kw):
        """AAA over 2-4 March 2026 with the given raw closes."""
        ds = [date(2026, 3, 2), date(2026, 3, 3), date(2026, 3, 4)]
        prev = [closes[0]] + list(closes[:-1])
        self.load({d: day_csv(d, [("AAA", "EQ", pc, c, 1000, 50)]) for d, pc, c in zip(ds, prev, closes)}, ds[0], date(2026, 3, 20), **kw)


class TestIngest(StoreCase):
    def test_parse_keeps_equity_series_and_reads_dashes_as_missing(self):
        d = date(2026, 11, 13)
        f = ps.parse_bhavcopy(day_csv(d, [("AAA", "EQ", 100, 101, 1000, 55.5), ("BOND", "GS", 100, 100, 10, 100), ("BBB", "BE", 50, 49, 200, "-")]))
        self.assertEqual(list(f["symbol"]), ["AAA", "BBB"])
        self.assertEqual(f["date"].iloc[0], "2026-11-13")
        self.assertTrue(np.isnan(f["deliv_pct"].iloc[1]))
        with self.assertRaises(ValueError):
            ps.parse_bhavcopy(b"<html>blocked</html>")

    def test_holidays_are_remembered_and_recent_gaps_are_retried(self):
        mon, tue, wed = date(2026, 11, 9), date(2026, 11, 10), date(2026, 11, 11)
        days = {mon: day_csv(mon, [("AAA", "EQ", 100, 101, 1000, 50)]), wed: day_csv(wed, [("AAA", "EQ", 101, 102, 1000, 50)])}
        fake, out = self.load(days, mon, date(2026, 11, 20))
        self.assertEqual((out["stored"], out["sessions"], out["last"]), (2, 2, "2026-11-11"))
        self.assertEqual(self.con.execute("SELECT status FROM days WHERE date=?", (tue.isoformat(),)).fetchone()[0], "none")  # old gap: a holiday
        self.assertIsNone(self.con.execute("SELECT 1 FROM days WHERE date='2026-11-19'").fetchone())  # recent gap: may not be published yet
        fake2, _ = self.load(days, mon, date(2026, 11, 20))
        asked = [u for u in fake2.calls if u not in (ps.SYMBOL_CHANGES, ps.ACTIONS_API)]
        self.assertNotIn(ps.ARCHIVE.format(tue), asked)   # never asks for a known holiday again
        self.assertIn(ps.ARCHIVE.format(date(2026, 11, 19)), asked)

    def test_weekend_special_sessions_are_stored(self):
        sat = date(2026, 1, 31)  # NSE trades on some Saturdays and Sundays: budget day, Diwali muhurat
        _, out = self.load({sat: day_csv(sat, [("AAA", "EQ", 100, 101, 1000, 50)])}, date(2026, 1, 30), date(2026, 2, 20))
        self.assertEqual((out["stored"], out["last"]), (1, "2026-01-31"))


    def test_file_for_another_session_is_not_stored_under_the_asked_date(self):
        fri, sun = date(2021, 1, 1), date(2021, 1, 3)
        same = day_csv(fri, [("AAA", "EQ", 100, 101, 1000, 50)])  # the archive serves Friday's file for the Sunday too
        _, out = self.load({fri: same, sun: same}, fri, date(2021, 1, 20))
        self.assertEqual((out["sessions"], out["last"], out["rows"]), (1, "2021-01-01", 1))
        self.assertEqual(self.con.execute("SELECT status FROM days WHERE date='2021-01-03'").fetchone()[0], "none")


class TestActionParsing(unittest.TestCase):
    def test_nse_subjects(self):
        self.assertEqual(ps.parse_action("Face Value Split (Sub-Division) - From Rs10/- Per Share To Re 1/- Per Share"), [("split", 10.0, 1.0, None)])
        self.assertEqual(ps.parse_action("Bonus 3:1"), [("bonus", 3.0, 1.0, None)])
        self.assertEqual(ps.parse_action("Rights 6:179 @ Premium Rs 1810/-", face_value=2), [("rights", 6.0, 179.0, 1812.0)])
        self.assertEqual(ps.parse_action("Interim Dividend - Rs 6 Per Share And Special Dividend - Rs 4.50 Per Share"), [("dividend", 10.5, None, None)])
        self.assertEqual(ps.parse_action("Annual General Meeting"), [])
        self.assertEqual(ps.parse_action("Dividend - 50%"), [])  # no rupee amount: nothing is guessed

    def test_factors(self):
        self.assertAlmostEqual(ps.price_factor("split", 10, 1, None, 27000), 0.1)
        self.assertAlmostEqual(ps.price_factor("bonus", 3, 1, None, 100), 0.25)
        self.assertAlmostEqual(ps.price_factor("rights", 1, 4, 50, 100), (4 * 100 + 50) / 500)  # theoretical ex-rights price
        self.assertEqual(ps.price_factor("rights", 1, 4, 150, 100), 1.0)                          # priced above market: no discount
        self.assertIsNone(ps.price_factor("rights", 1, 4, None, 100))

    def test_only_equity_series_rows_are_kept(self):
        rows = ps.parse_actions([action("AAA", "03-Mar-2026", "Bonus 1:1"), {**action("GSEC", "03-Mar-2026", "Bonus 1:1"), "series": "GS"}, {"symbol": "X"}])
        self.assertEqual(rows, [("AAA", "2026-03-03", "bonus", 1.0, 1.0, None, "Bonus 1:1")])


class TestAdjustment(StoreCase):
    def test_bonus_does_not_show_as_a_crash(self):
        # 1:1 bonus on 3 March. NSE does not restate prev_close, so the raw series halves overnight.
        self.three_days([200, 102, 103], actions=[action("AAA", "03-Mar-2026", "Bonus 1:1")])
        h = ps.history("aaa", con=self.con)
        self.assertEqual(list(h["RawClose"]), [200, 102, 103])
        self.assertAlmostEqual(h["Close"].iloc[0], 100.0)              # pre-bonus bar restated to today's terms
        self.assertAlmostEqual(h["Volume"].iloc[0], 2000.0)            # and its volume doubled
        self.assertAlmostEqual(h["Close"].pct_change().iloc[1], 0.02)  # the real move that day, not -49%
        acts = ps.corporate_actions("AAA", con=self.con)
        self.assertEqual([(a["date"], a["kind"], a["factor"], a["applied"]) for a in acts], [("2026-03-03", "bonus", 0.5, True)])
        p = ps.panels(con=self.con)
        self.assertAlmostEqual(p["ret"]["AAA"].iloc[1], 0.02)
        self.assertEqual(p["meta"]["splits_bonuses_rights_applied"], 1)

    def test_action_that_does_not_match_the_price_gap_is_not_applied(self):
        # NSE lists a 1:1 bonus but the price never halves: wrong date or wrong terms. Leave prices alone and say so.
        self.three_days([200, 198, 199], actions=[action("AAA", "03-Mar-2026", "Bonus 1:1")])
        h = ps.history("AAA", con=self.con)
        self.assertEqual(list(h["Close"]), [200, 198, 199])
        act = ps.corporate_actions("AAA", con=self.con)[0]
        self.assertFalse(act["applied"])
        self.assertIn("does not match", act["note"])
        self.assertEqual(ps.panels(con=self.con)["meta"]["splits_bonuses_rights_unverified"], 1)

    def test_dividend_is_added_to_the_return_not_to_the_chart(self):
        self.three_days([100, 96, 97], actions=[action("AAA", "03-Mar-2026", "Dividend - Rs 5 Per Share")])
        p = ps.panels(con=self.con)
        self.assertAlmostEqual(p["ret"]["AAA"].iloc[1], (96 + 5) / 100 - 1)  # +1% total return, not -4%
        self.assertEqual(list(ps.history("AAA", con=self.con)["Close"]), [100, 96, 97])  # price chart untouched
        self.assertEqual(ps.history("AAA", con=self.con)["Dividend"].iloc[1], 5.0)

    def test_unexplained_collapse_is_unknown_not_performance(self):
        self.three_days([100, 40, 41])  # a demerger with nothing on file
        p = ps.panels(con=self.con)
        self.assertTrue(np.isnan(p["ret"]["AAA"].iloc[1]))
        self.assertAlmostEqual(p["adj"]["AAA"].iloc[2], 41 / 40)  # the index carries on from the far side of the gap
        self.assertEqual(p["meta"]["unexplained_moves_dropped"], 1)

    def test_rename_joins_the_two_histories(self):
        d1, d2 = date(2026, 3, 2), date(2026, 3, 3)
        changes = b"NAME OF THE COMPANY,OLD SYMBOL,NEW SYMBOL,EFFECTIVE DATE\nAcme,OLDCO,NEWCO,03-MAR-2026\n"
        self.load({d1: day_csv(d1, [("OLDCO", "EQ", 99, 100, 1000, 50)]), d2: day_csv(d2, [("NEWCO", "EQ", 100, 105, 1000, 50)])}, d1, date(2026, 3, 20), changes=changes)
        for name in ("NEWCO", "OLDCO"):
            self.assertEqual(list(ps.history(name, con=self.con)["Close"]), [100, 105])
        self.assertAlmostEqual(ps.panels(con=self.con)["ret"]["NEWCO"].iloc[1], 0.05)  # the return runs across the rename
        self.assertEqual(list(ps.panels(con=self.con)["ret"].columns), ["NEWCO"])

    def test_unknown_symbol_is_an_empty_frame(self):
        self.assertTrue(ps.history("NOPE", con=self.con).empty)
        self.assertEqual(ps.panels(con=self.con), {})


def synthetic_panels(days=700, names=300, seed=5, drift_spread=0.0015):
    """Stocks with persistent, different drifts: past winners keep winning, so momentum must pay."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2023-01-02", periods=days)
    cols = [f"S{i:03d}" for i in range(names)]
    drift = np.linspace(-drift_spread, drift_spread, names)
    ret = pd.DataFrame(rng.normal(0, 0.01, (days, names)) + drift, index=idx, columns=cols)
    traded = ret.notna()
    return {"ret": ret, "adj": (1 + ret).cumprod(), "traded": traded,
            "turnover_cr": pd.DataFrame(rng.uniform(1, 100, (days, names)), index=idx, columns=cols),
            "deliv_pct": pd.DataFrame(rng.uniform(20, 80, (days, names)), index=idx, columns=cols)}


class TestRecentHistories(StoreCase):
    def test_bulk_read_matches_single_history_across_a_bonus(self):
        self.three_days([200, 102, 103], actions=[action("AAA", "03-Mar-2026", "Bonus 1:1")])
        as_of, h = ps.recent_histories(sessions=10, con=self.con)
        self.assertEqual(as_of, "2026-03-04")
        self.assertEqual(list(h["AAA"]["Close"]), list(ps.history("AAA", con=self.con)["Close"]))
        self.assertAlmostEqual(h["AAA"]["Volume"].iloc[0], 2000.0)
        self.assertEqual(ps.version(self.con), ("2026-03-04", 3, 1))


class TestStoreScan(unittest.TestCase):
    def frame(self, n, end="2026-11-13", start=100.0, step=0.003):
        idx = pd.bdate_range(end=end, periods=n)
        close = start * np.cumprod(np.full(n, 1 + step))
        return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1e5}, index=idx)

    def test_every_listed_trading_stock_gets_a_row(self):
        from analysis.data import store_scan
        nifty = pd.Series(np.linspace(20000, 21000, 300), index=pd.bdate_range(end="2026-11-20", periods=300))  # feed runs past the store
        hist = {"OLD": self.frame(260), "NEW": self.frame(40), "TINY": self.frame(10), "GONE": self.frame(260, end="2026-09-01"), "UNLISTED": self.frame(260)}
        out = store_scan.build(hist, "2026-11-13", {"OLD", "NEW", "TINY", "GONE", "MISSING"}, nifty,
                               pd.DataFrame({"symbol": ["OLD", "NEW"], "sector": ["Banks", "IT"], "company_name": ["Old Ltd", "New Ltd"]}))
        self.assertEqual(sorted(out["symbol"]), ["NEW", "OLD"])
        old, new = out.set_index("symbol").loc["OLD"], out.set_index("symbol").loc["NEW"]
        self.assertFalse(old["short_history"])
        self.assertIn(old["trend"], ("UPTREND", "STRONG_UPTREND"))   # the scanner's own labels
        self.assertTrue(new["short_history"])
        self.assertTrue(pd.isna(new["high_52w"]) and pd.isna(new["ema_200"]) and pd.isna(new["trend"]))
        self.assertAlmostEqual(new["return_20d"], ((1.003 ** 20) - 1) * 100, places=4)
        self.assertEqual(new["sector"], "IT")
        nr = store_scan.nifty_returns(nifty, "2026-11-13")
        trimmed = nifty[nifty.index <= "2026-11-13"]
        self.assertAlmostEqual(nr["return_20d"], (trimmed.iloc[-1] / trimmed.iloc[-21] - 1) * 100)  # same end date as the store
        self.assertAlmostEqual(new["relative_strength_20d"], new["return_20d"] - nr["return_20d"])


class TestBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = synthetic_panels()
        cls.bt = re_.factor_backtest(cls.p, top_n=200, cost_bps=30)
        cls.by = {f["factor"]: f for f in cls.bt["factors"]}

    def test_planted_momentum_is_found_and_noise_is_not(self):
        mom, dlv = self.by["Momentum 12-1"], self.by["Delivery %"]
        self.assertEqual(self.bt["status"], "AVAILABLE")
        self.assertGreater(mom["spread_annual_pct"], 20)
        self.assertGreater(mom["spread_t"], 3)
        self.assertGreater(mom["ic_mean"], 0.1)
        self.assertTrue(mom["monotonic"])
        self.assertLess(abs(dlv["spread_t"]), 3)  # delivery is random here

    def test_no_lookahead_signals_ignore_the_future(self):
        pos, names = 400, self.p["adj"].columns[:50]
        before = re_.signals(self.p, pos, names)
        future = {k: v.copy() for k, v in self.p.items()}
        for k in ("ret", "adj", "deliv_pct"):
            future[k].iloc[pos + 1:] = 999.0
        pd.testing.assert_frame_equal(before, re_.signals(future, pos, names))

    def test_universe_is_the_most_liquid_names(self):
        p = synthetic_panels(days=400, names=120)
        p["turnover_cr"].iloc[:, :10] = 10_000.0
        self.assertEqual(set(re_.liquid_universe(p["turnover_cr"], p["traded"], p["adj"], 300, 10)), set(p["adj"].columns[:10]))

    def test_costs_reduce_the_long_only_figure_and_curves_line_up(self):
        mom = self.by["Momentum 12-1"]
        self.assertLess(mom["long_only_net_pct"], mom["long_only_excess_pct"])
        self.assertEqual(len(mom["curve"]["dates"]), mom["months"])
        self.assertEqual(len(mom["curve"]["long_short"]), mom["months"])
        self.assertFalse(self.bt["buy_sell_authorization"])
        self.assertTrue(any("dividends" in c for c in self.bt["caveats"]))

    def test_short_store_is_refused(self):
        self.assertEqual(re_.factor_backtest(synthetic_panels(days=200))["status"], "NOT_AVAILABLE")
        self.assertEqual(re_.factor_backtest({})["status"], "NOT_AVAILABLE")


class TestBreadthAndDelivery(unittest.TestCase):
    def test_breadth_of_a_rising_market(self):
        idx = pd.bdate_range("2024-01-01", periods=320)
        ret = pd.DataFrame(0.002, index=idx, columns=["A", "B", "C", "D"])
        ret["D"] = -0.002
        p = {"ret": ret, "adj": (1 + ret).cumprod(), "traded": ret.notna(), "turnover_cr": ret * 0 + 5}
        b = re_.breadth_series(p).iloc[-1]
        self.assertEqual((b["advancing"], b["declining"], b["stocks"]), (3, 1, 4))
        self.assertAlmostEqual(b["above_200_pct"], 75.0)
        self.assertEqual((b["new_highs"], b["new_lows"]), (3, 1))

    def test_delivery_trend_and_missing_data(self):
        idx = pd.bdate_range("2025-01-01", periods=120)
        h = pd.DataFrame({"DelivPct": [40.0] * 115 + [70.0] * 5, "TurnoverCr": 10.0}, index=idx)
        d = re_.delivery_profile(h)
        self.assertEqual((d["trend"], d["avg_5d_pct"], d["last_pct"]), ("Rising", 70.0, 70.0))
        self.assertAlmostEqual(d["delivered_value_20d_cr"], (15 * 4 + 5 * 7) / 20, places=2)
        self.assertEqual(re_.delivery_profile(h.head(30))["status"], "NOT_AVAILABLE")


if __name__ == "__main__":
    unittest.main(verbosity=2)
