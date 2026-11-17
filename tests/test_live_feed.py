import asyncio
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.api import live_feed

IST = live_feed.IST
MON_11AM = datetime(2026, 11, 2, 11, 0, tzinfo=IST)


def _quote(price, change=1.0, volume=100):
    return {"price": price, "change": change, "change_percent": 0.5, "volume": volume, "source": "NSE MCP"}


class LiveFeedBase(unittest.TestCase):
    def setUp(self):
        live_feed.reset()
        self.sent = []
        patches = [
            mock.patch.object(live_feed.scheduler, "_broadcast", side_effect=self.sent.append),
            mock.patch.object(live_feed.dhan_feed, "is_configured", return_value=False),
            mock.patch.object(live_feed.nse_live, "get", return_value={"data": []}),  # no network in tests
            mock.patch.object(live_feed, "fetch_yahoo_quote", return_value=None),  # no network in tests
            mock.patch.object(live_feed, "fetch_stooq_quote", return_value=None),  # no network in tests
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def poll(self, mono=1000.0, now=MON_11AM):
        return asyncio.run(live_feed.poll_once(mono, now))


class TestSession(LiveFeedBase):
    def test_session_hours(self):
        self.assertTrue(live_feed.in_session(MON_11AM))
        self.assertFalse(live_feed.in_session(MON_11AM.replace(hour=9, minute=14)))
        self.assertFalse(live_feed.in_session(MON_11AM.replace(hour=15, minute=31)))
        self.assertFalse(live_feed.in_session(MON_11AM - timedelta(days=1)))  # Sunday

    def test_closed_outside_session_polls_nothing(self):
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote") as q:
            self.assertEqual(self.poll(now=MON_11AM.replace(hour=20)), 0)
            q.assert_not_called()
        self.assertEqual(live_feed.snapshot()["status"]["state"], "closed")


class TestTicks(LiveFeedBase):
    def test_change_only_emission(self):
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", return_value=_quote(2500.0)):
            self.assertEqual(self.poll(1000.0), 1)
            self.assertEqual(self.poll(1000.0 + live_feed.STOCK_POLL_S), 0)  # unchanged
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", return_value=_quote(2501.0)):
            self.assertEqual(self.poll(1000.0 + 2 * live_feed.STOCK_POLL_S), 1)
        tick = self.sent[-1]
        self.assertEqual((tick["type"], tick["symbol"], tick["ltp"], tick["source"]),
                         ("tick", "RELIANCE", 2501.0, "NSE MCP"))
        self.assertIn("as_of", tick)

    def test_missing_price_is_not_invented(self):
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", return_value=_quote(None)):
            self.assertEqual(self.poll(), 0)
        self.assertEqual(live_feed.snapshot()["ticks"], {})

    def test_snapshot_flags_stale(self):
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", return_value=_quote(2500.0)):
            self.poll()
        fresh = live_feed.snapshot(MON_11AM + timedelta(seconds=1))
        old = live_feed.snapshot(MON_11AM + timedelta(seconds=2 * live_feed.STOCK_POLL_S + 1))
        self.assertFalse(fresh["ticks"]["RELIANCE"]["stale"])
        self.assertTrue(old["ticks"]["RELIANCE"]["stale"])
        self.assertFalse(old["buy_sell_authorized"])

    def test_dhan_index_ticks(self):
        live_feed.dhan_feed.is_configured.return_value = True
        quotes = {"NIFTY": {"available": True, "last_price": 25100.0, "net_change": 100.0},
                  "BANKNIFTY": {"available": False}}
        with mock.patch.object(live_feed.dhan_feed, "get_index_quote", return_value=quotes):
            self.assertEqual(self.poll(), 1)
        self.assertEqual(self.sent[0]["symbol"], "NIFTY")
        self.assertEqual(self.sent[0]["change_pct"], 0.4)
        self.assertEqual(live_feed.snapshot()["status"]["state"], "live")


    def test_nse_index_ticks_without_dhan(self):
        payload = {"data": [{"index": "NIFTY 50", "last": 23661.5, "variation": 220.7, "percentChange": 0.94},
                            {"index": "INDIA VIX", "last": 15.97, "variation": 0.47, "percentChange": 3.03}]}
        with mock.patch.object(live_feed.nse_live, "get", return_value=payload):
            self.assertEqual(self.poll(), 2)
        self.assertEqual({t["symbol"] for t in self.sent}, {"NIFTY", "INDIAVIX"})
        self.assertEqual(self.sent[0]["source"], "NSE")
        self.assertEqual(live_feed.snapshot()["status"]["state"], "live")


class TestBackoff(LiveFeedBase):
    def test_failure_backs_off_and_reports_error(self):
        live_feed.watch(["RELIANCE"], mono=1000.0)
        boom = mock.Mock(side_effect=RuntimeError("MCP down"))
        with mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", boom):
            self.poll(1000.0)
            self.poll(1000.0 + live_feed.STOCK_POLL_S)  # still inside 2x backoff
        self.assertEqual(boom.call_count, 1)
        status = live_feed.snapshot()["status"]
        self.assertIn(status["state"], {"error", "delayed"})
        self.assertIn("MCP down", status["reason"])


class TestStockSources(LiveFeedBase):
    def test_a_failing_source_falls_through_to_the_next(self):
        yahoo = {"type": "tick", "symbol": "RELIANCE", "ltp": 1340.6, "change": -4.2, "change_pct": -0.31, "volume": None, "source": "Yahoo", "as_of": "x", "max_age_s": 60}
        with mock.patch.object(live_feed, "fetch_yahoo_quote", side_effect=RuntimeError("rate limited")), \
             mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", side_effect=RuntimeError("Unexpected stock quote response format.")), \
             mock.patch.object(live_feed, "fetch_stooq_quote", return_value={**yahoo, "source": "Stooq"}):
            self.assertEqual(live_feed.fetch_stock_quote_free("RELIANCE", "x")["source"], "Stooq")

    def test_one_bad_symbol_does_not_sink_the_round(self):
        def quote(sym, as_of):
            if sym == "BAD":
                raise RuntimeError("no data")
            return {"type": "tick", "symbol": sym, "ltp": 1.0, "change": 0, "change_pct": 0, "volume": None, "source": "Yahoo", "as_of": as_of, "max_age_s": 60}
        with mock.patch.object(live_feed, "fetch_stock_quote_free", side_effect=quote):
            ticks = live_feed.fetch_stocks(["BAD", "TCS", "INFY"], "x")
        self.assertEqual(sorted(t["symbol"] for t in ticks), ["INFY", "TCS"])

    def test_indices_update_while_stocks_are_slow(self):
        import time as _time
        payload = {"data": [{"index": "NIFTY 50", "last": 25400.0, "variation": 10.0, "percentChange": 0.04}]}
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_live, "get", return_value=payload), \
             mock.patch.object(live_feed, "fetch_stocks", side_effect=lambda *a: _time.sleep(0.5) or []):
            sent = asyncio.run(live_feed.poll_once(1000.0, MON_11AM, only={"indices"}))
        self.assertEqual(sent, 1)  # the stock source was not touched by the index loop


class TestWatch(LiveFeedBase):
    def test_cap_validation_and_expiry(self):
        res = live_feed.watch(["reliance", "bad symbol!", "NIFTY"], mono=0.0)
        self.assertEqual(res["accepted"], ["RELIANCE"])
        self.assertEqual(len(res["rejected"]), 2)
        live_feed.watch([f"S{i}" for i in range(40)], mono=0.0)
        self.assertEqual(len(live_feed._watch), live_feed.MAX_WATCH)
        live_feed.watch([], mono=live_feed.WATCH_TTL_S + 1)
        self.assertEqual(live_feed._watch, {})


class TestLiveRoutes(LiveFeedBase):
    def setUp(self):
        super().setUp()
        from starlette.testclient import TestClient
        from web.api.main import create_app
        self.client = TestClient(create_app())

    def test_watch_and_snapshot(self):
        r = self.client.post("/api/live/watch", json={"symbols": ["TCS"]})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["accepted"], ["TCS"])
        body = self.client.get("/api/live/snapshot").json()
        self.assertIn("ticks", body)
        self.assertFalse(body["buy_sell_authorized"])

    def test_watch_rejects_cross_origin(self):
        r = self.client.post("/api/live/watch", json={"symbols": ["TCS"]},
                             headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)

    def test_watch_allows_same_origin_any_port(self):
        r = self.client.post("/api/live/watch", json={"symbols": ["TCS"]},
                             headers={"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(r.status_code, 200)

    def test_watch_rejects_bad_body(self):
        r = self.client.post("/api/live/watch", json={"symbols": "TCS"})
        self.assertEqual(r.status_code, 422)


if __name__ == "__main__":
    unittest.main()


class TestSpecialSessions(LiveFeedBase):
    OPEN = {"marketState": [{"market": "Capital Market", "marketStatus": "Open"}]}

    def test_weekend_special_session_streams_when_nse_says_open(self):
        sunday_muhurat = datetime(2026, 11, 8, 18, 15, tzinfo=IST)
        live_feed.watch(["RELIANCE"], mono=1000.0)
        with mock.patch.object(live_feed.nse_live, "get", return_value=self.OPEN), \
             mock.patch.object(live_feed.nse_feed, "get_normalized_stock_quote", return_value=_quote(2500.0)):
            self.assertGreater(self.poll(1000.0, sunday_muhurat), 0)
        self.assertEqual(live_feed._status["state"], "live")

    def test_status_is_asked_rarely_and_never_overnight(self):
        with mock.patch.object(live_feed.nse_live, "get", return_value={"marketState": []}) as get:
            self.poll(1000.0, MON_11AM.replace(hour=17))
            self.poll(1100.0, MON_11AM.replace(hour=17, minute=2))   # inside the 300 s window: no new request
            self.poll(1400.0, MON_11AM.replace(hour=23))             # overnight: never asked
        self.assertEqual([c.args[0] for c in get.call_args_list].count("marketStatus"), 1)
        self.assertEqual(live_feed._status["state"], "closed")


class TestHolidays(LiveFeedBase):
    def test_parse_cm_segment_only(self):
        payload = {"CM": [{"tradingDate": "10-Nov-2026"}], "FO": [{"tradingDate": "11-Nov-2026"}]}
        self.assertEqual(live_feed.nse_live.parse_holidays(payload), {"2026-11-10"})

    def test_holiday_reports_closed_without_polling(self):
        holiday = MON_11AM.replace(day=10)  # Tuesday 10 Nov 2026, Diwali-Balipratipada
        with mock.patch.object(live_feed.nse_live, "trading_holidays", return_value={"2026-11-10"}), \
             mock.patch.object(live_feed, "fetch_indices") as fetch:
            self.assertEqual(self.poll(now=holiday), 0)
        fetch.assert_not_called()
        self.assertEqual(live_feed._status["state"], "closed")
        self.assertIn("holiday", live_feed._status["reason"])

    def test_holiday_list_failure_falls_back_to_hours(self):
        with mock.patch.object(live_feed.nse_live, "trading_holidays", side_effect=RuntimeError("blocked")):
            self.poll()
        self.assertNotIn("holiday", live_feed._status["reason"])
