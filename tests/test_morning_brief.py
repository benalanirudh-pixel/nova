import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import morning_brief as mb

NOW = datetime(2026, 11, 2, 4, 0, tzinfo=timezone.utc)  # 09:30 IST


def _pre(sym, pchg, turnover):
    return {"metadata": {"symbol": sym, "pChange": pchg, "totalTurnover": turnover, "iep": 100, "previousClose": 99}}


class TestParsers(unittest.TestCase):
    def test_session_reads_capital_market_row(self):
        s = mb.parse_session({"marketState": [
            {"market": "Currency", "last": ""},
            {"market": "Capital Market", "marketStatus": "Open", "tradeDate": "02-Nov-2026 09:30", "last": 23440.8, "variation": 10, "percentChange": 0.04}]})
        self.assertEqual(s["status"], "Open")
        self.assertEqual(s["nifty_last"], 23440.8)
        with self.assertRaises(ValueError):
            mb.parse_session({"marketState": []})

    def test_preopen_filters_illiquid_movers_and_flags_today(self):
        p = mb.parse_preopen({"timestamp": "02-Nov-2026 09:08:00", "advances": 10, "declines": 5, "unchanged": 1,
                              "data": [_pre("TINY", 19.9, 1e5), _pre("BIG", 3.0, 5e8), _pre("MID", -2.0, 2e7), _pre("BAD", None, 1e9)]},
                             now=NOW)
        self.assertTrue(p["is_today"])
        self.assertEqual([r["symbol"] for r in p["gainers"]], ["BIG", "MID"])  # TINY below ₹1 Cr
        self.assertEqual(p["losers"][0]["symbol"], "MID")
        self.assertEqual(p["most_active"][0]["symbol"], "BIG")
        self.assertAlmostEqual(p["most_active"][0]["turnover_cr"], 50.0)

    def test_preopen_old_snapshot_not_today(self):
        p = mb.parse_preopen({"timestamp": "30-Oct-2026 09:08:00", "data": []}, now=NOW)
        self.assertFalse(p["is_today"])

    def test_fii_dii_strips_commas_and_stars(self):
        rows = mb.parse_fii_dii([{"category": "FII/FPI *", "date": "30-Oct-2026", "buyValue": "12,000.5", "sellValue": "13,000", "netValue": "-999.5"}])
        self.assertEqual(rows[0]["category"], "FII/FPI")
        self.assertEqual(rows[0]["net_cr"], -999.5)
        with self.assertRaises(ValueError):
            mb.parse_fii_dii({"error": "x"})

    def test_fresh_news_sorted_and_stale_dropped(self):
        items = [{"title": "old", "published": "2026-06-01T00:00:00+00:00"},
                 {"title": "a", "published": "2026-11-01T00:00:00+00:00"},
                 {"title": "b", "published": "2026-11-02T01:00:00+00:00"},
                 {"title": "undated", "published": None}]
        self.assertEqual([i["title"] for i in mb.fresh_news(items, now=NOW)], ["b", "a"])


class TestMorningCall(unittest.TestCase):
    def test_lines_and_tones(self):
        report = {"market_regime": "MILDLY_BEARISH",
                  "volatility": {"india_vix": {"value": 15.3, "direction": "RISING", "regime": "MODERATE"}},
                  "risk_context": {"instruments": {"nifty": {"expected_daily_range": 217.0, "expected_daily_move_percent": 0.94}}},
                  "event_risk_context": {"upcoming_events": [
                      {"name": "RBI policy", "datetime_utc": "2026-11-03T04:30:00+00:00", "risk_level": "HIGH"},
                      {"name": "Far away", "datetime_utc": "2026-12-30T00:00:00+00:00", "risk_level": "HIGH"}]}}
        indices = [{"name": "S&P 500", "region": "US", "change_pct": -1.0, "date": "2026-10-30"},
                   {"name": "Nikkei", "region": "Asia", "change_pct": -0.3, "date": "2026-11-02"},
                   {"name": "Hang Seng", "region": "Asia", "change_pct": 0.4, "date": "2026-11-02"}]
        lines = mb.build_morning_call(report, None, None, indices, [{"name": "Crude oil", "price": 98.0, "change_pct": 3.0}],
                                      [{"pair": "USDINR", "rate": 94.9, "change_pct": -0.04}], None, now=NOW)
        by = {l["text"].split(" (")[0]: l for l in lines}
        self.assertEqual(by["US markets lower"]["tone"], "negative")
        self.assertEqual(by["Asian markets mixed"]["tone"], "neutral")
        crude = next(l for l in lines if l["topic"] == "Crude")
        self.assertEqual(crude["tone"], "negative")  # higher crude hurts India
        self.assertIn("steady", next(l for l in lines if l["topic"] == "Rupee")["text"])
        events = [l for l in lines if l["topic"] == "Event"]
        self.assertEqual(len(events), 1)
        self.assertIn("RBI policy", events[0]["text"])
        self.assertTrue(any(l["topic"] == "Range" for l in lines))
        self.assertFalse(any(w in l["text"].lower() for l in lines for w in ("buy ", "sell ")))

    def test_gift_nifty_line(self):
        lines = mb.build_morning_call(None, None, None, None, None, None, None, now=NOW,
                                      gift={"price": 23696.5, "change_pct": 1.96, "expiry": "23-Nov-2026", "as_of": "03-Nov-2026 10:56"})
        self.assertEqual(lines[0]["topic"], "GIFT Nifty")
        self.assertEqual(lines[0]["tone"], "positive")

    def test_live_vix_beats_saved_report(self):
        report = {"volatility": {"india_vix": {"value": 15.3, "direction": "RISING", "regime": "MODERATE"}}}
        lines = mb.build_morning_call(report, None, None, None, None, None, None, now=NOW,
                                      vix_live={"price": 15.67, "change_percent": 1.09})
        vol = next(l for l in lines if l["topic"] == "Volatility")
        self.assertIn("15.67", vol["text"])
        self.assertNotIn("15.30", vol["text"])

    def test_empty_inputs(self):
        self.assertEqual(mb.build_morning_call(None, None, None, None, None, None, None), [])


class TestFocus(unittest.TestCase):
    def test_screens_use_liquid_names(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "market_scan_20261102_000000.csv").write_text(
                "symbol,price,volume_average_20,near_52w_high,relative_volume,trend,score,rsi_14,return_1d,return_20d,distance_52w_high\n"
                "LIQ,100,1000000,True,3.0,STRONG_UPTREND,90,25,1,1,0\n"
                "ILLIQ,1,10,True,9.0,STRONG_UPTREND,99,20,1,1,0\n"
                "DOWN,100,1000000,False,1.0,DOWNTREND,10,50,1,1,20\n")
            f = mb.stocks_in_focus(scanner_dir=d, classification_file=d / "missing.csv")
        screens = {s["key"]: [r["symbol"] for r in s["rows"]] for s in f["screens"]}
        self.assertEqual(f["universe"], 2)
        self.assertEqual(screens["breakouts"], ["LIQ"])
        self.assertEqual(screens["momentum"], ["LIQ"])
        self.assertEqual(screens["oversold"], ["LIQ"])

    def test_no_scan(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(mb.stocks_in_focus(scanner_dir=Path(d)))


class TestBuild(unittest.TestCase):
    def test_failed_sources_are_none_with_reasons(self):
        raw = {k: {"error": f"{k} down"} for k in ("status", "preopen", "fii_dii", "commodities", "fx")}
        raw.update(gainers=[], losers=RuntimeError("boom"), news=[])
        with mock.patch.object(mb.nse_feed, "call_tools", return_value=raw), \
             mock.patch.object(mb, "global_indices", side_effect=RuntimeError("yahoo down")), \
             mock.patch.object(mb, "stocks_in_focus", return_value=None),              mock.patch.object(mb.nse_live, "get", side_effect=RuntimeError("nse blocked")):
            b = mb.build_morning_brief(None)
        for k in ("session", "preopen", "fii_dii", "news", "focus", "range"):
            self.assertIsNone(b[k], k)
        self.assertEqual(b["movers"], {"gainers": [], "losers": []})
        self.assertIn("yahoo down", b["errors"]["global"])
        self.assertIsNone(b["gift_nifty"])
        self.assertIn("nse blocked", b["errors"]["gift_nifty"])
        self.assertEqual(b["morning_call"], [])


class TestRoutes(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from web.api.main import create_app
        from web.api.routes import market
        market._brief_cache.clear()
        market._live_cache.clear()
        p = mock.patch.object(market.nse_live, "market", side_effect=RuntimeError("offline test"))
        p.start()
        self.addCleanup(p.stop)
        self.client = TestClient(create_app())

    def test_brief_cached_with_guardrails(self):
        fake = {"errors": {}, "morning_call": []}
        with mock.patch("web.api.routes.market.morning_brief.build_morning_brief", return_value=fake) as b:
            r1 = self.client.get("/api/morning-brief")
            self.client.get("/api/morning-brief")
        self.assertEqual(r1.status_code, 200)
        self.assertIn("guardrails", r1.json())
        self.assertEqual(b.call_count, 1)

    def test_overview_has_no_chart(self):
        self.assertNotIn("chart", self.client.get("/api/market-overview").json())


if __name__ == "__main__":
    unittest.main()
