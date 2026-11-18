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

    def test_stale_stock_is_not_todays_mover(self):
        d = scan()
        d["timestamp"] = "2026-11-18T00:00:00+05:30"
        d.loc[d.symbol == "ODD", "timestamp"] = "2026-11-16T00:00:00+05:30"
        self.assertNotIn("ODD", [r["symbol"] for r in day_movers.top_movers(d)["gainers"]])

    def test_sector_short_names(self):
        self.assertEqual(mu.short_sector("Fast Moving Consumer Goods", 12), "FMCG")
        self.assertEqual(mu.short_sector(None, 12), "n/a")

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
    def test_pulse_table_hourly_change_and_na(self):
        text = mu.pulse_text(QUOTES, {"nifty": {"price": 25300.0}}, now=datetime(2026, 11, 18, 11, 15, tzinfo=IST))
        self.assertIn("<b>NOVA · INDEX PULSE</b>", text)
        self.assertIn("Wed 18 Nov 2026 · 11:15 IST", text)
        self.assertRegex(text, r"NIFTY 50\s+25,387.4\s+\+0.38\s+\+0.35\s+51")  # RNG: position in day range
        self.assertRegex(text, r"BANKNIFTY\s+n/a\s+n/a")
        self.assertRegex(text, r"INDIA VIX\s+15.52\s+-1.02")
        self.assertIn(mu.DISCLAIMER, text)

    def test_tables_fit_a_phone(self):
        text = mu.pulse_text(QUOTES, {"nifty": {"price": 25300.0}})
        body = text.split("<pre>")[1].split("</pre>")[0]
        self.assertLessEqual(max(len(l) for l in body.splitlines()), 36)

    def test_premarket_tables_and_desk_view(self):
        brief = {"gift_nifty": {"price": 25450.0, "change_pct": 0.25},
                 "global": {"indices": [{"name": "S&P 500", "last": 6800.0, "change_pct": -1.0}],
                            "fx": [{"pair": "USD/INR", "rate": 93.5, "change_pct": 0.06}]},
                 "fii_dii": [{"category": "FII/FPI", "date": "17-Nov-2026", "buy_cr": 10000, "sell_cr": 5805, "net_cr": 4195}],
                 "morning_call": [{"topic": "GIFT Nifty", "tone": "positive", "text": "dup of table"},
                                  {"topic": "Trend", "tone": "negative", "text": "Regime <BEAR> & weak"}],
                 "range": {"low": 25100, "high": 25600, "points": 250, "pct": 1.0}, "news": []}
        text = mu.premarket_text(brief)
        self.assertRegex(text, r"GIFT NIFTY\s+25,450\s+\+0.25")
        self.assertIn("S&amp;P 500", text)                       # escaped for Telegram HTML
        self.assertIn("FII +4,195 cr (17-Nov-2026)", text)
        self.assertIn("<b>25,100 – 25,600</b>", text)
        self.assertNotIn("dup of table", text)                   # short: no desk-view essay
        self.assertLess(len(text), 700)
        self.assertIn("not yet posted", mu.premarket_text({}))

    def test_postmarket_sections(self):
        movers = day_movers.top_movers(scan(), n=5)
        heads = {"ODD": {"title": "ODD wins order", "source": "ET"}}
        text = mu.postmarket_text(REPORT, QUOTES, movers, day_movers.sector_moves(scan(), min_stocks=5), heads,
                                  [{"title": "Sensex ends higher", "source": "BS"}],
                                  [{"category": "FII/FPI", "date": "18-Nov-2026", "net_cr": -1234.5}],
                                  ai="Banks led the gains.")
        for part in ("POST-MARKET WRAP", "<b>Top gainers</b>", "<b>Top losers</b>", "<b>Sector moves</b>",
                     "▲ <b>ODD</b> +30.00%\n   ODD wins order <i>(ET)</i>", "<i>No NSE filing or news in 48h</i>",
                     "945 / 1,084 (A/D 0.87)", "<i>Unverified, qwen3.5:4b:</i> Banks led the gains."):
            self.assertIn(part, text)
        self.assertRegex(text, r"BIG\s+\+9.00\s+4.2x\s+Banks")
        self.assertRegex(text, r"FII/FPI\s+n/a\s+n/a\s+-1,234")

    def test_postmarket_without_data(self):
        text = mu.postmarket_text({}, {}, None, None, {}, [], None)
        self.assertIn("n/a (no scan cached)", text)
        self.assertIn("Not yet posted", text)
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


class TestNewsQuality(unittest.TestCase):
    NOW = datetime(2026, 11, 18, 18, 5, tzinfo=IST)

    def test_market_headlines_trusted_fresh_deduped(self):
        utc = lambda h: (self.NOW - timedelta(hours=h)).astimezone(timezone.utc).isoformat()
        items = [{"title": "Sensex falls 700 points as IT drags", "source": "The Economic Times", "published": utc(1)},
                 {"title": "Sensex falls 700 points as IT drags, check details", "source": "Mint", "published": utc(2)},
                 {"title": "Top 5 stocks to buy now", "source": "Kalkine Media", "published": utc(1)},
                 {"title": "Old RBI story", "source": "Reuters", "published": utc(30)}]
        got = mu.market_headlines(items, now=self.NOW)
        self.assertEqual([i["source"] for i in got], ["The Economic Times"])

    def test_untrusted_used_only_when_nothing_trusted(self):
        utc = (self.NOW - timedelta(hours=1)).astimezone(timezone.utc).isoformat()
        got = mu.market_headlines([{"title": "Markets end lower", "source": "Local Wire", "published": utc}], now=self.NOW)
        self.assertEqual(len(got), 1)

    def test_nse_context_prefers_ex_date_and_material_filing(self):
        def fake(endpoint, params):
            if endpoint == "corporates-corporateActions":
                return [{"exDate": "17-Nov-2026", "subject": "Bonus 3:2"}]
            return [{"an_dt": "18-Nov-2026 10:00:00", "desc": "Copy of Newspaper Publication", "attchmntText": "x"},
                    {"an_dt": "17-Nov-2026 21:00:00", "desc": "Updates", "attchmntText": "routine"},
                    {"an_dt": "18-Nov-2026 09:30:00", "desc": "Bagging/Receiving of orders/contracts",
                     "attchmntText": "ABC Limited has informed the Exchange about receipt of order worth Rs 500 crore"},
                    {"an_dt": "10-Nov-2026 09:30:00", "desc": "Financial Results", "attchmntText": "too old"}]
        with mock.patch.object(mu.nse_live, "get", side_effect=fake):
            got = mu.nse_context("ABC", now=self.NOW)
        self.assertEqual(got[0]["title"], "Ex-date 17-Nov-2026: Bonus 3:2 (price adjusts)")
        self.assertEqual(got[1]["title"], "Bagging/Receiving of orders/contracts: receipt of order worth Rs 500 crore")
        self.assertEqual(got[1]["source"], "NSE filing 18-Nov 09:30")

    def test_nse_failure_gives_empty_context(self):
        with mock.patch.object(mu.nse_live, "get", side_effect=RuntimeError("NSE down")), mock.patch("builtins.print"):
            self.assertEqual(mu.nse_context("ABC", now=self.NOW), [])


class TestTelegramSend(unittest.TestCase):
    def test_send_is_noop_when_unconfigured(self):
        with mock.patch.object(telegram, "_config", return_value=("", "")), \
             mock.patch.object(telegram.requests, "post") as post:
            self.assertFalse(telegram.send("hi"))
        post.assert_not_called()

    def test_html_rejected_falls_back_to_plain(self):
        bad, ok = mock.Mock(ok=False, status_code=400, text="can't parse entities"), mock.Mock(ok=True)
        with mock.patch.object(telegram, "_config", return_value=("t", "c")),              mock.patch.object(telegram.requests, "post", side_effect=[bad, ok]) as post,              mock.patch("builtins.print"):
            self.assertTrue(telegram.send("<b>A &amp; B</b>"))
        self.assertEqual(post.call_args_list[0].kwargs["json"]["parse_mode"], "HTML")
        self.assertEqual(post.call_args_list[1].kwargs["json"]["text"], "A & B")
        self.assertNotIn("parse_mode", post.call_args_list[1].kwargs["json"])

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
        self.assertIn("SCAN FAILED", send.call_args[0][0])
        self.assertIn("scanner down", send.call_args[0][0])

    def test_pulse_remembers_last_hour(self):
        scheduler._last_pulse.clear()
        with mock.patch.object(scheduler.telegram, "is_configured", return_value=True), \
             mock.patch.object(scheduler, "_is_holiday", mock.AsyncMock(return_value=False)), \
             mock.patch.object(scheduler.market_updates, "index_quotes", return_value=QUOTES), \
             mock.patch.object(scheduler.telegram, "send") as send:
            asyncio.run(scheduler.hourly_pulse())
            asyncio.run(scheduler.hourly_pulse())
        self.assertRegex(send.call_args_list[0][0][0], r"NIFTY 50\s+25,387.4\s+\+0.38\s+n/a")
        self.assertRegex(send.call_args_list[1][0][0], r"NIFTY 50\s+25,387.4\s+\+0.38\s+\+0.00")
        scheduler._last_pulse.clear()


class TestRescanNote(unittest.TestCase):
    def test_counts_fresh_and_stale_stocks(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as d:
            f = os.path.join(d, "scan.csv")
            pd.DataFrame({"timestamp": ["2026-11-18T00:00:00"] * 3 + ["2026-11-16T00:00:00"]}).to_csv(f, index=False)
            text = mu.rescan_text({"scanner_file": f, "market_regime": "NEUTRAL"},
                                  now=datetime(2026, 11, 18, 12, 21, tzinfo=IST))
        self.assertIn("3 / 4 stocks on today's prices (75.0%) · 1 stale", text)
        self.assertIn("NOVA · RESCAN", text)

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
