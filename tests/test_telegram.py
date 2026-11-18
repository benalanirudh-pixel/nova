import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

import pandas as pd

from analysis.data import day_movers
from web.api import market_updates as mu
from web.api import scheduler, telegram

IST = ZoneInfo("Asia/Kolkata")
REPORT = {"market_regime": "NEUTRAL", "breadth": {"total": 2052.0, "advancing": 945, "declining": 1084}}
QUOTES = {
    "nifty": {"price": 25387.4, "change_pct": 0.38, "high": 25501.3, "low": 25267.3, "source": "NSE"},
    "sensex": {"price": 83100.0, "change_pct": 0.41, "high": 83400.0, "low": 82800.0, "source": "Yahoo"},
    "vix": {"price": 15.52, "change_pct": -1.02, "high": None, "low": None, "source": "NSE"},
}


def scan():
    rows = [  # symbol, price, return_1d, avg volume, rel vol, sector
        ("BIG", 500, 9.0, 200_000, 4.2, "Banks"), ("PENNY", 5, 19.0, 9_000_000, 1, "Banks"),
        ("THIN", 900, 15.0, 100, 1, "Banks"), ("DOWN", 300, -6.0, 500_000, 2.0, "IT"),
    ] + [(f"B{i}", 100, 1.0 + i, 1_000_000, 1, "Banks") for i in range(5)] \
      + [(f"I{i}", 100, -2.0, 1_000_000, 1, "IT") for i in range(5)] + [("ODD", 100, 30.0, 1_000_000, 1, "Tiny")]
    d = pd.DataFrame(rows, columns=["symbol", "price", "return_1d", "volume_average_20", "relative_volume", "sector"])
    d["company_name"] = d["symbol"] + " Ltd"
    return d


class TestDayMovers(unittest.TestCase):
    def test_penny_and_illiquid_stocks_are_filtered(self):
        m = day_movers.top_movers(scan(), n=3)
        syms = [r["symbol"] for r in m["gainers"]]
        self.assertNotIn("PENNY", syms)
        self.assertNotIn("THIN", syms)
        self.assertEqual(syms[0], "ODD")
        self.assertEqual(m["losers"][0]["symbol"], "DOWN")

    def test_sector_median_ignores_small_sectors(self):
        s = day_movers.sector_moves(scan(), min_stocks=5)
        self.assertEqual([r["sector"] for r in s["up"]], ["Banks"])
        self.assertEqual(s["down"][0]["sector"], "IT")
        self.assertEqual(s["down"][0]["median_pct"], -2.0)

    def test_headline_match_needs_name_and_recency(self):
        now = datetime(2026, 11, 18, 13, tzinfo=timezone.utc)
        news = [{"title": "Greaves Cotton Q2 profit jumps", "published": (now - timedelta(hours=5)).isoformat()},
                {"title": "Markets end flat", "published": now.isoformat()},
                {"title": "Greaves old story", "published": (now - timedelta(days=3)).isoformat()}]
        hit = day_movers.match_headline(news, "GREAVESCOT", "Greaves Cotton Ltd", now=now)
        self.assertEqual(hit["title"], "Greaves Cotton Q2 profit jumps")
        self.assertIsNone(day_movers.match_headline(news[1:2], "GREAVESCOT", "Greaves Cotton Ltd", now=now))


class TestMessages(unittest.TestCase):
    def test_pulse_shows_hourly_change_and_na(self):
        text = mu.pulse_text(QUOTES, {"nifty": {"price": 25300.0}}, now=datetime(2026, 11, 18, 11, 15, tzinfo=IST))
        self.assertIn("NOVA hourly 11:15 IST", text)
        self.assertIn("NIFTY 50 25,387.4 (+0.38%), 1h +0.35%, H 25,501 L 25,267", text)
        self.assertIn("SENSEX 83,100.0", text)
        self.assertIn("BANKNIFTY: n/a", text)
        self.assertIn("INDIA VIX 15.52 (-1.02%)", text)
        self.assertIn(mu.FOOTER, text)

    def test_premarket_uses_morning_call(self):
        brief = {"morning_call": [{"text": "GIFT Nifty 25,450 (+0.25%)"}],
                 "range": {"low": 25100, "high": 25600, "points": 250}, "news": []}
        text = mu.premarket_text(brief)
        self.assertIn("- GIFT Nifty 25,450", text)
        self.assertIn("25,100 - 25,600", text)
        self.assertIn("Morning call: n/a", mu.premarket_text({}))

    def test_postmarket_movers_headlines_and_ai_label(self):
        movers = day_movers.top_movers(scan(), n=5)
        heads = {"ODD": {"title": "ODD wins order", "source": "ET"}}
        text = mu.postmarket_text(REPORT, QUOTES, movers, day_movers.sector_moves(scan(), min_stocks=5), heads,
                                  [{"title": "Sensex ends higher", "source": "BS"}],
                                  [{"category": "FII/FPI", "date": "18-Nov-2026", "net_cr": -1234.5}],
                                  ai="Banks led the gains.")
        self.assertIn("Headline: ODD wins order (ET)", text)
        self.assertIn("No news found", text)          # looked up, nothing matched: never a guessed reason
        self.assertIn("4.2x avg vol", text)
        self.assertIn("Sectors up: Banks", text)
        self.assertIn("FII/FPI -1,234 cr", text)
        self.assertIn("AI read (unverified, qwen3.5:4b): Banks led the gains.", text)
        self.assertIn("945 up / 1084 down", text)

    def test_postmarket_without_data(self):
        text = mu.postmarket_text({}, {}, None, None, {}, [], None)
        self.assertIn("Movers: n/a", text)
        self.assertIn("FII/DII: not yet posted", text)
        self.assertNotIn("AI read", text)

    def test_ai_line_dropped_when_it_gives_trade_advice(self):
        fake = mock.Mock()
        fake.chat.return_value = {"message": {"content": "Markets rose. Buy banks now."}}
        with mock.patch("ollama.Client", return_value=fake):
            self.assertIsNone(mu.ai_read("facts"))
        fake.chat.return_value = {"message": {"content": "Banks led;  cause unclear."}}
        with mock.patch("ollama.Client", return_value=fake):
            self.assertEqual(mu.ai_read("facts"), "Banks led; cause unclear.")

    def test_ai_failure_returns_none(self):
        with mock.patch("ollama.Client", side_effect=ConnectionError("ollama down")):
            self.assertIsNone(mu.ai_read("facts"))


class TestTelegramSend(unittest.TestCase):
    def test_send_is_noop_when_unconfigured(self):
        with mock.patch.object(telegram, "_config", return_value=("", "")), \
             mock.patch.object(telegram.requests, "post") as post:
            self.assertFalse(telegram.send("hi"))
        post.assert_not_called()

    def test_send_swallows_network_errors(self):
        with mock.patch.object(telegram, "_config", return_value=("t", "c")), \
             mock.patch.object(telegram.requests, "post", side_effect=telegram.requests.ConnectionError("down")), \
             mock.patch("builtins.print"):
            self.assertFalse(telegram.send("hi"))


class TestSchedule(unittest.TestCase):
    def test_postmarket_due_once_after_1730_on_trading_days(self):
        wed = datetime(2026, 11, 18, 18, 1, tzinfo=IST)
        self.assertTrue(scheduler.postmarket_due(wed, None, holiday=False))
        self.assertFalse(scheduler.postmarket_due(wed, "2026-11-18", holiday=False))
        self.assertFalse(scheduler.postmarket_due(wed, None, holiday=True))
        self.assertFalse(scheduler.postmarket_due(wed.replace(hour=15, minute=20), None, holiday=False))
        self.assertFalse(scheduler.postmarket_due(datetime(2026, 11, 21, 18, 1, tzinfo=IST), None, holiday=False))

    def test_scan_failure_still_notifies(self):
        with mock.patch.object(scheduler, "get_market_lab_data", side_effect=RuntimeError("scanner down")), \
             mock.patch.object(scheduler, "_running", True), \
             mock.patch.object(scheduler.telegram, "is_configured", return_value=True), \
             mock.patch.object(scheduler.telegram, "send") as send:
            asyncio.run(scheduler._run_refresh())
        self.assertIn("scan failed: scanner down", send.call_args[0][0])

    def test_pulse_remembers_last_hour(self):
        scheduler._last_pulse.clear()
        with mock.patch.object(scheduler.telegram, "is_configured", return_value=True), \
             mock.patch.object(scheduler, "_is_holiday", mock.AsyncMock(return_value=False)), \
             mock.patch.object(scheduler.market_updates, "index_quotes", return_value=QUOTES), \
             mock.patch.object(scheduler.telegram, "send") as send:
            asyncio.run(scheduler.hourly_pulse())
            asyncio.run(scheduler.hourly_pulse())
        self.assertNotIn("1h", send.call_args_list[0][0][0])
        self.assertIn("1h +0.00%", send.call_args_list[1][0][0])
        scheduler._last_pulse.clear()


class TestRescanNote(unittest.TestCase):
    def test_counts_fresh_and_stale_stocks(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "scan.csv")
            pd.DataFrame({"timestamp": ["2026-11-18T00:00:00"] * 3 + ["2026-11-16T00:00:00"]}).to_csv(f, index=False)
            text = mu.rescan_text({"scanner_file": f, "market_regime": "NEUTRAL"},
                                  now=datetime(2026, 11, 18, 12, 21, tzinfo=IST))
        self.assertEqual(text, "NOVA rescan 12:21 IST: 3 of 4 stocks with today's prices (1 stale). Regime: NEUTRAL")

    def test_missing_scan_file_falls_back(self):
        self.assertIn("2,052 stocks scanned", mu.rescan_text({"stocks_analyzed": 2052, "scanner_file": "nope.csv"}))

    def test_daytime_scan_sends_note_evening_sends_report(self):
        def run(hour):
            with mock.patch.object(scheduler, "datetime") as dt,                  mock.patch.object(scheduler, "_postmarket_sent", None),                  mock.patch.object(scheduler, "_is_holiday", mock.AsyncMock(return_value=False)),                  mock.patch.object(scheduler.telegram, "is_configured", return_value=True),                  mock.patch.object(scheduler.market_updates, "rescan_text", return_value="note"),                  mock.patch.object(scheduler.market_updates, "build_postmarket", return_value="report"),                  mock.patch.object(scheduler.telegram, "send") as send:
                dt.now.return_value = datetime(2026, 11, 18, hour, 1, tzinfo=IST)
                asyncio.run(scheduler._send_scan_update({}))
            return send.call_args[0][0]
        self.assertEqual(run(12), "note")
        self.assertEqual(run(18), "report")


if __name__ == "__main__":
    unittest.main()
