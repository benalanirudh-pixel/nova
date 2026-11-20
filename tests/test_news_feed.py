import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
from zoneinfo import ZoneInfo

from web.api import market_updates as mu
from web.api import news_feed as nf
from web.api import scheduler

IST = ZoneInfo("Asia/Kolkata")
NOW = datetime(2026, 11, 20, 10, 0, tzinfo=IST)

RSS = b"""<?xml version="1.0"?><rss xmlns:media="http://search.yahoo.com/mrss/"><channel>
<item><title><![CDATA[Infosys Q2 results: net profit rises 8%]]></title>
  <link>https://example.in/infy</link><pubDate>Fri, 20 Nov 2026 09:50:00 +0530</pubDate><media:content url="x"/></item>
<item><title>Sensex live updates: market opens flat</title><link>https://example.in/live</link>
  <pubDate>Fri, 20 Nov 2026 09:40:00 +0530</pubDate></item>
<item><title>Rupee opens at 93.20</title><link>http://example.in/insecure</link><pubDate>Fri, 20 Nov 2026 09:30:00 +0530</pubDate></item>
<item><title>Rupee   opens at 93.20 against dollar</title><link>https://example.in/rupee</link>
  <pubDate>Fri, 20 Nov 2026 09:30:00 +0530</pubDate></item>
</channel></rss>"""

GOOGLE = b"""<rss><channel>
<item><title>RBI keeps repo rate unchanged - Reuters</title><link>https://news.google.com/a</link>
  <pubDate>Fri, 20 Nov 2026 04:20:00 GMT</pubDate><source url="https://reuters.com">Reuters</source></item>
<item><title>Top 5 stocks to watch - Some Blog</title><link>https://news.google.com/b</link>
  <pubDate>Fri, 20 Nov 2026 04:20:00 GMT</pubDate><source url="https://x.substack.com">Some Blog</source></item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>SEBI tightens F&amp;O rules</title>
<link href="https://example.in/sebi"/><updated>2026-11-20T04:00:00Z</updated></entry></feed>"""

FILINGS = [
    {"symbol": "JWL", "desc": "Press Release", "an_dt": "20-Nov-2026 09:01:00",
     "attchmntText": 'Jupiter Wagons Limited has informed the Exchange regarding a press release titled '
                     '"Jupiter Wagons secures repeat order worth over INR 128 crore".',
     "attchmntFile": "https://nsearchives.nseindia.in/a.pdf"},
    {"symbol": "RGL", "desc": "Press Release", "an_dt": "20-Nov-2026 09:08:05",
     "attchmntText": 'has informed the Exchange regarding a press release titled "Opening of new store".',
     "attchmntFile": "https://nsearchives.nseindia.in/b.pdf"},
    {"symbol": "TCS", "desc": "Outcome of Board Meeting", "an_dt": "20-Nov-2026 09:30:00",
     "attchmntText": "TCS has informed the Exchange about outcome of board meeting.",
     "attchmntFile": "https://nsearchives.nseindia.in/c.pdf"},
    {"symbol": "ABC", "desc": "Trading Window", "an_dt": "20-Nov-2026 09:30:00", "attchmntText": "closure",
     "attchmntFile": "https://nsearchives.nseindia.in/d.pdf"},
]


def item(title, minutes_ago=5, high=False, link=None):
    return nf.tag({"title": title, "link": link or f"https://x.in/{abs(hash(title))}", "source": "ET",
                   "published": nf._utc(NOW - timedelta(minutes=minutes_ago)), "high": high})


class ParseTests(unittest.TestCase):
    def test_rss_drops_junk_and_insecure_links_and_tags(self):
        out = nf.parse_feed(RSS, "Mint")
        self.assertEqual([i["link"] for i in out], ["https://example.in/infy", "https://example.in/rupee"])
        infy, rupee = out
        self.assertEqual(infy["published"], "2026-11-20T04:20:00+00:00")
        self.assertIn("RESULTS", infy["tags"])
        self.assertTrue(infy["high"])
        self.assertEqual(rupee["title"], "Rupee opens at 93.20 against dollar")  # whitespace collapsed
        self.assertEqual(rupee["tags"], ["MACRO"])
        self.assertFalse(rupee["high"])

    def test_google_news_keeps_trusted_publishers_and_strips_suffix(self):
        out = nf.parse_feed(GOOGLE, "Google News")
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["source"], "Reuters")
        self.assertEqual(out[0]["title"], "RBI keeps repo rate unchanged")
        self.assertEqual(out[0]["tags"][0], "RBI")

    def test_atom_entry(self):
        (sebi,) = nf.parse_feed(ATOM, "X")
        self.assertEqual((sebi["link"], sebi["published"], sebi["high"]), ("https://example.in/sebi", "2026-11-20T04:00:00+00:00", True))

    def test_filings_skip_routine_and_rank_press_release_by_words(self):
        out = {i["title"].split(":")[0]: i for i in nf.parse_filings(FILINGS)}
        self.assertEqual(set(out), {"JWL", "RGL", "TCS"})
        self.assertTrue(out["JWL"]["high"])  # order words
        self.assertFalse(out["RGL"]["high"])  # store opening press release
        self.assertTrue(out["TCS"]["high"])  # material filing category
        self.assertIn("secures repeat order", out["JWL"]["title"])
        self.assertEqual(out["JWL"]["published"], "2026-11-20T03:31:00+00:00")
        self.assertEqual(nf.parse_filings({"error": "blocked"}), [])


class MergeTests(unittest.TestCase):
    def test_new_items_once_and_same_story_across_outlets_once(self):
        seen = {}
        a = item("Infosys Q2 results net profit rises 8 per cent", 5)
        b = dict(a, link="https://other.in/infy", source="Mint")  # same headline, other outlet
        new, recent = nf.merge([a, b], [], seen, NOW)
        self.assertEqual(len(new), 1)
        new2, recent2 = nf.merge([dict(a), item("Rupee opens weak", 1)], recent, seen, NOW + timedelta(minutes=1))
        self.assertEqual([i["title"] for i in new2], ["Rupee opens weak"])
        self.assertEqual([i["title"] for i in recent2], ["Rupee opens weak", a["title"]])

    def test_restart_shows_known_items_on_desk_without_resending(self):
        a = item("Infosys Q2 results net profit rises 8 per cent", 5)
        seen = {}
        nf.merge([dict(a)], [], seen, NOW)
        new, recent = nf.merge([dict(a)], [], seen, NOW + timedelta(minutes=1))  # fresh process: empty Desk list
        self.assertEqual(new, [])
        self.assertEqual([i["title"] for i in recent], [a["title"]])

    def test_old_items_leave_desk_list_and_seen_store(self):
        seen = {"https://gone": nf._utc(NOW - timedelta(days=4))}
        new, recent = nf.merge([item("Yesterday's story", 60 * 30)], [], seen, NOW)
        self.assertEqual(len(new), 1)  # unseen, so reported as new ...
        self.assertEqual(recent, [])  # ... but older than 24 h, so not on the Desk
        self.assertNotIn("https://gone", seen)

    def test_poll_reports_failed_sources_without_inventing_items(self):
        def boom(*_):
            raise TimeoutError("read timed out")
        with mock.patch.object(nf, "_fetch_feed", boom), \
                mock.patch.object(nf.nse_live, "get", return_value=FILINGS), \
                mock.patch.object(nf, "_load_seen", return_value={}), mock.patch.object(nf, "_save_seen"), \
                mock.patch.object(nf, "_seen", None), mock.patch.object(nf, "_recent", []):
            out = nf.poll(NOW)
            snap = nf.snapshot()
        self.assertEqual(len(out["errors"]), len(nf.FEEDS))
        self.assertTrue(all(i["source"] == nf.NSE_SOURCE for i in out["new"]))
        self.assertEqual(snap["sources"], len(nf.FEEDS) + 1)


class AlertTests(unittest.TestCase):
    def test_only_fresh_high_impact(self):
        new = [item("SEBI bans broker", 2), item("Rupee opens weak", 2), item("RBI hikes repo rate", 90),
               dict(item("TCS Q2 results", 2), published=None)]
        self.assertEqual([i["title"] for i in nf.alerts(new, NOW)], ["SEBI bans broker"])

    def test_text_is_escaped_and_linked(self):
        a = item("M&M <Q2> results beat", 3, link='https://x.in/a?b=1&c="2"')
        text = mu.news_text([a], now=NOW)
        self.assertIn("NOVA · MARKET NEWS", text)
        self.assertIn('<a href="https://x.in/a?b=1&amp;c=&quot;2&quot;">M&amp;M &lt;Q2&gt; results beat</a>', text)
        self.assertIn("<b>RESULTS</b> · 09:57 · ET", text)
        self.assertIn("Not a buy/sell signal", text)

    def test_push_window_weekdays_8_to_20_ist(self):
        self.assertTrue(scheduler.news_push_due(NOW))
        self.assertFalse(scheduler.news_push_due(NOW.replace(hour=7, minute=59)))
        self.assertFalse(scheduler.news_push_due(NOW.replace(hour=20)))
        self.assertFalse(scheduler.news_push_due(NOW + timedelta(days=1)))  # Saturday

    def test_tick_sends_one_message_for_fresh_high_items(self):
        fresh = [item("SEBI bans broker", 1), item("Rupee opens weak", 1)]
        sent, real_alerts = [], nf.alerts

        async def notify(text):
            sent.append(text)
        with mock.patch.object(scheduler.news_feed, "poll", return_value={"new": fresh, "errors": {}}), \
                mock.patch.object(scheduler, "_notify", notify), \
                mock.patch.object(scheduler, "news_push_due", return_value=True), \
                mock.patch.object(scheduler.news_feed, "alerts", side_effect=lambda new, now: real_alerts(new, NOW)):
            asyncio.run(scheduler.news_tick())
        self.assertEqual(len(sent), 1)
        self.assertIn("SEBI bans broker", sent[0])
        self.assertNotIn("Rupee", sent[0])

    def test_tick_survives_poll_failure(self):
        with mock.patch.object(scheduler.news_feed, "poll", side_effect=RuntimeError("no network")), \
                mock.patch.object(scheduler, "_notify") as notify:
            asyncio.run(scheduler.news_tick())
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
