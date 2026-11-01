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
