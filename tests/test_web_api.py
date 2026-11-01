import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.api.main import create_app


class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_health_returns_ok(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["buy_sell_authorized"])

    def test_cors_headers_present(self):
        r = self.client.options("/api/health", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        })
        self.assertIn("access-control-allow-origin", r.headers)


class TestMarketOverviewEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_market_overview_returns_200(self):
        r = self.client.get("/api/market-overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("kpis", "chart", "breadth", "flows", "sectors",
                    "derivatives", "freshness", "guardrails"):
            self.assertIn(key, body)

    def test_market_overview_guardrails_present(self):
        body = self.client.get("/api/market-overview").json()
        self.assertFalse(body["guardrails"]["buy_sell_authorization"])

    def test_market_overview_no_cache_returns_null_kpis(self):
        from unittest import mock
        with mock.patch("web.api.routes.market.load_latest_saved_report", return_value=None):
            r = self.client.get("/api/market-overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["kpis"])
        self.assertFalse(body["guardrails"]["buy_sell_authorization"])
