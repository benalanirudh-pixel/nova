import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import fno_desk as fd


def chain(strikes, call_oi, put_oi, **extra):
    n = len(strikes)
    df = pd.DataFrame({"strike": strikes, "call_oi": call_oi, "put_oi": put_oi,
                       "call_change_oi": [0] * n, "put_change_oi": [0] * n,
                       "call_volume": [10] * n, "put_volume": [10] * n,
                       "call_iv": [15.0] * n, "put_iv": [18.0] * n,
                       "call_ltp": [50.0] * n, "put_ltp": [40.0] * n})
    for k, v in extra.items():
        df[k] = v
    return df


class TestChain(unittest.TestCase):
    def test_max_pain_minimizes_payout(self):
        # all OI at 100: settling at 100 pays nothing
        df = chain([90, 100, 110], [0, 500, 0], [0, 500, 0])
        self.assertEqual(fd.max_pain(df), 100.0)
        self.assertIsNone(fd.max_pain(chain([100], [0], [0])))

    def test_metrics(self):
        df = chain([90, 95, 100, 105, 110], [10, 20, 30, 80, 40], [50, 90, 30, 10, 5],
                   call_change_oi=[0, 0, 5, 40, 0], put_change_oi=[0, 60, 5, 0, 0])
        m = fd.chain_metrics(df, spot=101.0, expiry="05-Nov-2026", today=date(2026, 11, 2))
        self.assertEqual(m["atm"], 100.0)
        self.assertEqual(m["days_to_expiry"], 3)
        self.assertAlmostEqual(m["pcr_oi"], 185 / 180)
        self.assertAlmostEqual(m["pcr_change_oi"], 65 / 45)
        self.assertEqual(m["straddle"], 90.0)
        self.assertAlmostEqual(m["expected_move_pct"], 90 / 101 * 100)
        self.assertEqual(m["resistance"][0]["strike"], 105.0)  # largest call OI above spot
        self.assertEqual(m["support"][0]["strike"], 95.0)      # largest put OI below spot
        self.assertEqual(m["fresh_call_writing"][0], {"strike": 105.0, "oi": 80.0, "change_oi": 40.0})
        self.assertEqual(m["fresh_put_writing"][0]["strike"], 95.0)
        self.assertAlmostEqual(m["atm_iv"], 16.5)
        self.assertAlmostEqual(m["skew"], 3.0)

    def test_zero_iv_is_missing(self):
        df = chain([100], [1], [1], call_iv=[0.0], put_iv=[0.0])
        m = fd.chain_metrics(df, spot=100.0, expiry="bad")
        self.assertIsNone(m["atm_iv"])
        self.assertIsNone(m["days_to_expiry"])

    def test_empty_chain_raises(self):
        with self.assertRaises(ValueError):
            fd.chain_metrics(chain([], [], []), spot=100.0, expiry="05 Nov 2026")

    def test_bse_rows_map_call_and_put_legs(self):
        df = fd.parse_bse_chain([{"Strike_Price1": "73300.00", "C_Open_Interest": "1,011", "C_IV": "0.0", "C_Last_Trd_Price": "2217.80",
                                  "Open_Interest": "10838", "IV": "23.85", "Last_Trd_Price": "46.25", "Absolute_Change_OI": "-5"},
                                 {"Strike_Price1": ""}])
        self.assertEqual(len(df), 1)
        r = df.iloc[0]
        self.assertEqual((r["strike"], r["call_oi"], r["put_oi"], r["put_change_oi"]), (73300.0, 1011.0, 10838.0, -5.0))
        self.assertAlmostEqual(r["put_iv"], 23.85)


class TestTechnicals(unittest.TestCase):
    def hist(self, last_day):
        idx = pd.date_range(end=last_day, periods=300, freq="D")
        c = pd.Series(np.linspace(100, 130, 300), index=idx)
        return pd.DataFrame({"Close": c, "High": c + 2, "Low": c - 2})

    def test_pivots_skip_partial_session(self):
        h = self.hist("2026-11-02")
        live = fd.spot_technicals(h, now=datetime(2026, 11, 2, 5, 0, tzinfo=timezone.utc))    # 10:30 IST
        closed = fd.spot_technicals(h, now=datetime(2026, 11, 2, 11, 0, tzinfo=timezone.utc))  # 16:30 IST
        self.assertEqual(live["pivots"]["from"], "2026-11-01")
        self.assertEqual(closed["pivots"]["from"], "2026-11-02")
        self.assertAlmostEqual(closed["pivots"]["pp"], 130.0)
        self.assertGreater(closed["rsi"], 70)
        self.assertEqual(set(closed["ema"]), {20, 50, 200})

    def test_short_history_raises(self):
        with self.assertRaises(ValueError):
            fd.spot_technicals(self.hist("2026-11-02").tail(10))


class TestCandles(unittest.TestCase):
    def test_tail_and_missing_rows_dropped(self):
        idx = pd.date_range(end="2026-11-03", periods=5, freq="D")  # 10-30 .. 11-03
        h = pd.DataFrame({"Open": [1, 2, None, 4, 5], "High": [2, 3, 4, 5, 6], "Low": [0, 1, 2, 3, 4], "Close": [1.5, 2.5, 3.5, 4.5, 5.5]}, index=idx)
        self.assertEqual([x["t"] for x in fd.daily_candles(h, n=3)], ["2026-10-31", "2026-11-02", "2026-11-03"])  # 11-01 has no open
        self.assertEqual(fd.daily_candles(h)[0], {"t": "2026-10-30", "o": 1.0, "h": 2.0, "l": 0.0, "c": 1.5})
        self.assertEqual(fd.daily_candles(pd.DataFrame({"Close": [1]})), [])


class TestRead(unittest.TestCase):
    def test_tones(self):
        m = {"pcr_oi": 1.5, "call_change_oi": 10, "put_change_oi": 100, "resistance": [{"strike": 105.0}],
             "support": [{"strike": 95.0}], "max_pain": 99.0, "days_to_expiry": 2, "straddle": 3.0,
             "expected_move_pct": 3.0, "breakeven_low": 97.0, "breakeven_high": 103.0, "skew": 5.0, "atm_iv": 20.0}
        t = {"rv20": 12.0, "ema": {20: 90.0, 50: 95.0}, "rsi": 60.0}
        by = {l["topic"]: l for l in fd.desk_read(100.0, m, t)}
        self.assertEqual(by["PCR"]["tone"], "positive")
        self.assertEqual(by["Fresh OI"]["tone"], "positive")
        self.assertEqual(by["Skew"]["tone"], "negative")
        self.assertIn("rich", by["Vol"]["text"])
        self.assertEqual(by["Trend"]["tone"], "positive")
        text = " ".join(l["text"].lower() for l in by.values())
        self.assertNotIn("buy", text)
        self.assertNotIn("sell", text)

    def test_nothing(self):
        self.assertEqual(fd.desk_read(100.0, None, None), [])


class TestBuild(unittest.TestCase):
    def test_unsupported(self):
        with self.assertRaises(ValueError):
            fd.build_fno("FINNIFTY")

    def test_chain_failure_keeps_technicals(self):
        with mock.patch.object(fd, "fetch_nse_chain", side_effect=RuntimeError("blocked")), \
             mock.patch.object(fd, "fetch_spot_history", return_value=TestTechnicals().hist("2026-10-30")):
            d = fd.build_fno("nifty")
        self.assertIsNone(d["metrics"])
        self.assertIn("blocked", d["errors"]["chain"])
        self.assertIsNotNone(d["technicals"])
        self.assertEqual(d["spot"], d["technicals"]["last"])

    def test_sensex_uses_bse(self):
        fake = {"spot": 100.0, "expiry": "05 Nov 2026", "expiries": ["05 Nov 2026"], "source": "BSE",
                "rows": chain([95, 100, 105], [1, 2, 3], [3, 2, 1])}
        with mock.patch.object(fd, "fetch_bse_chain", return_value=fake) as b, \
             mock.patch.object(fd, "fetch_spot_history", side_effect=RuntimeError("no yahoo")):
            d = fd.build_fno("SENSEX", "05 Nov 2026")
        b.assert_called_once_with("05 Nov 2026")
        self.assertEqual(d["metrics"]["atm"], 100.0)
        self.assertIn("technicals", d["errors"])


class TestRoute(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from web.api.main import create_app
        from web.api.routes import analysis
        analysis._fno_cache.clear()
        self.client = TestClient(create_app())

    def test_validation(self):
        self.assertEqual(self.client.get("/api/fno/FINNIFTY").status_code, 404)
        self.assertEqual(self.client.get("/api/fno/NIFTY", params={"expiry": "x;drop"}).status_code, 400)

    def test_cached_with_guardrails(self):
        with mock.patch("web.api.routes.analysis.fno_desk.build_fno", return_value={"instrument": "NIFTY"}) as b:
            r = self.client.get("/api/fno/nifty")
            self.client.get("/api/fno/NIFTY")
        self.assertEqual(r.status_code, 200)
        self.assertIn("guardrails", r.json())
        self.assertEqual(b.call_count, 1)


if __name__ == "__main__":
    unittest.main()
