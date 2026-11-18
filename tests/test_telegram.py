import asyncio
import unittest
from unittest import mock

from web.api import scheduler, telegram


REPORT = {
    "generated": "2026-11-17T18:01:45+05:30",
    "market_regime": "NEUTRAL",
    "nifty_snapshot": {"available": True, "price": 25387.4, "change_percent": 0.38},
    "bank_nifty_returns": {"1D": -0.2},
    "volatility": {"india_vix": {"available": True, "value": 15.52, "change_percent": -1.02, "regime": "MODERATE"}},
    "breadth": {"total": 2052.0, "advancing": 945, "declining": 1084},
    "sector_intelligence": {"top_sectors": [{"sector": "Capital Markets", "return_20d": 11.0}]},
    "top_technical_stocks": [{"symbol": "AMANTA", "technical_score": 97.0}],
    "event_risk_context": {"status": "NOT_AVAILABLE", "source_fresh": False},
}


class TestTelegramSummary(unittest.TestCase):
    def test_digest_has_key_numbers_and_guardrail(self):
        text = telegram.summary(REPORT)
        for part in ("NEUTRAL", "25,387.4 (+0.38%)", "VIX 15.52", "945 up / 1084 down of 2052",
                     "Capital Markets +11.00%", "AMANTA 97", "event calendar stale", "Not a buy/sell signal"):
            self.assertIn(part, text)

    def test_missing_data_shows_na_not_invented(self):
        text = telegram.summary({})
        self.assertIn("NIFTY: n/a", text)
        self.assertIn("VIX: n/a", text)
        self.assertIn("Breadth: n/a", text)

    def test_send_is_noop_when_unconfigured(self):
        with mock.patch.object(telegram, "_config", return_value=("", "")), \
             mock.patch.object(telegram.requests, "post") as post:
            self.assertFalse(telegram.send("hi"))
        post.assert_not_called()

    def test_send_swallows_network_errors(self):
        with mock.patch.object(telegram, "_config", return_value=("t", "c")), \
             mock.patch.object(telegram.requests, "post", side_effect=telegram.requests.ConnectionError("down")):
            self.assertFalse(telegram.send("hi"))


class TestSchedulerNotifies(unittest.TestCase):
    def _run(self, **data_kw):
        with mock.patch.object(scheduler, "get_market_lab_data", **data_kw), \
             mock.patch.object(scheduler, "save_json_report", return_value="x/market_lab_1.json"), \
             mock.patch.object(scheduler, "prune_reports"), \
             mock.patch.object(scheduler, "_running", True), \
             mock.patch.object(scheduler.telegram, "is_configured", return_value=True), \
             mock.patch.object(scheduler.telegram, "send") as send:
            asyncio.run(scheduler._run_refresh())
        return send

    def test_digest_sent_after_scan(self):
        send = self._run(return_value=REPORT)
        self.assertIn("NEUTRAL", send.call_args[0][0])

    def test_failure_sent_when_scan_breaks(self):
        send = self._run(side_effect=RuntimeError("scanner down"))
        self.assertIn("scan failed: scanner down", send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
