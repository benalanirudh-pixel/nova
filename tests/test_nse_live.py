import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import nse_live

ALL = {"timestamp": "03-Nov-2026 10:57", "advances": 6946, "declines": 2613, "unchanged": 27, "data": [
    {"key": "INDICES ELIGIBLE IN DERIVATIVES", "index": "NIFTY 50", "last": 23661.45, "variation": 220.65,
     "percentChange": 0.94, "open": 23582.25, "high": 23675.3, "low": 23482.8, "previousClose": 23440.8, "advances": "35"},
    {"key": "BROAD MARKET INDICES", "index": "INDIA VIX", "last": 15.97, "variation": 0.47, "percentChange": 3.03},
    {"key": "SECTORAL INDICES", "index": "NIFTY IT", "last": 32480.2, "percentChange": 0.12},
]}


class TestParsers(unittest.TestCase):
    def test_indices(self):
        d = nse_live.parse_indices(ALL)
        self.assertEqual(d["nifty"]["price"], 23661.45)
        self.assertEqual(d["nifty"]["advances"], 35.0)
        self.assertEqual(d["vix"]["change_percent"], 3.03)
        self.assertNotIn("banknifty", d)  # missing stays missing
        self.assertEqual([x["name"] for x in d["sectors"]], ["NIFTY IT"])
        self.assertEqual(d["breadth"], {"advances": 6946.0, "declines": 2613.0, "unchanged": 27.0})

    def test_gift(self):
        g = nse_live.parse_gift({"giftnifty": {"LASTPRICE": 23696.5, "DAYCHANGE": 456.5, "PERCHANGE": 1.96, "EXPIRYDATE": "23-Nov-2026"}})
        self.assertEqual((g["price"], g["change_pct"]), (23696.5, 1.96))
        self.assertIsNone(nse_live.parse_gift({}))

    def test_fii_dii(self):
        rows = nse_live.parse_fii_dii([{"buyValue": "14,988.48", "category": "DII", "date": "02-Nov-2026", "netValue": "-392.2", "sellValue": "15380.68"}])
        self.assertEqual(rows[0]["net_cr"], -392.2)
        self.assertEqual(rows[0]["buy_cr"], 14988.48)
        with self.assertRaises(ValueError):
            nse_live.parse_fii_dii({"error": "x"})

    def test_movers(self):
        p = {"NIFTY": {"data": [{"symbol": "ONGC", "ltp": 230.7, "perChange": -1.76, "turnover": "97.44 Cr"}]}}
        self.assertEqual(nse_live.parse_movers(p, "NIFTY")[0]["change_pct"], -1.76)
        self.assertEqual(nse_live.parse_movers(p, "BANKNIFTY"), [])

    def test_get_retries_with_fresh_session(self):
        good = mock.Mock(content=b'[{"a": 1}]', raise_for_status=mock.Mock())
        bad = mock.Mock(get=mock.Mock(side_effect=RuntimeError("expired")))
        fresh = mock.Mock(get=mock.Mock(return_value=good))
        nse_live._session = bad
        with mock.patch.object(nse_live.de, "create_nse_session", return_value=fresh), \
             mock.patch.object(nse_live.de, "warm_nse_session"):
            self.assertEqual(nse_live.get("x"), [{"a": 1}])
        nse_live._session = None


class TestOverlay(unittest.TestCase):
    def test_live_prices_replace_report_values_but_not_scan_breadth(self):
        from web.api.routes.market import apply_live
        live = {"error": None, "data": {**nse_live.parse_indices(ALL), "status": {"state": "Open"}, "gift_nifty": None}}
        live["data"]["breadth"].update(new_52w_highs=46.0, new_52w_lows=58.0)
        body = {"kpis": {"macro": {"nifty_price": 1.0}, "nifty": {"price": 1.0, "series": [1]}, "vix": {"value": 1.0}},
                "breadth": {"advancing": 1, "declining": 1, "above_ema20_percent": 40.0}, "regime": {"india_vix": 1.0}}
        out = apply_live(body, live)
        self.assertEqual(out["kpis"]["nifty"]["price"], 23661.45)
        self.assertEqual(out["kpis"]["nifty"]["series"], [1])          # history kept
        self.assertTrue(out["kpis"]["nifty"]["source_label"].startswith("NSE · "))
        self.assertEqual(out["kpis"]["vix"]["value"], 15.97)
        self.assertEqual(out["kpis"]["macro"]["nifty_price"], 23661.45)
        self.assertEqual(out["regime"]["india_vix"], 15.97)
        self.assertEqual(out["breadth"]["advancing"], 1)  # NSE's figure sums every index, the scan's does not
        self.assertEqual(out["breadth"]["new_52w_highs"], 46.0)
        self.assertEqual(out["breadth"]["above_ema20_percent"], 40.0)  # scan-based field untouched
        self.assertNotIn("ad_ratio", out["breadth"])
        self.assertEqual(out["live"]["sectors"][0]["name"], "NIFTY IT")

    def test_failure_keeps_report_and_reports_error(self):
        from web.api.routes.market import apply_live
        body = apply_live({"kpis": {"nifty": {"price": 1.0}}}, {"data": None, "error": "NSE live data unavailable: blocked"})
        self.assertEqual(body["kpis"]["nifty"]["price"], 1.0)
        self.assertIn("blocked", body["live"]["error"])


if __name__ == "__main__":
    unittest.main()
