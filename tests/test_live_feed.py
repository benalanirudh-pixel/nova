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
