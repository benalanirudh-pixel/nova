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
        with mock.patch("web.api.routes.market.load_cached_report", return_value=None):
            r = self.client.get("/api/market-overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["kpis"])
        self.assertFalse(body["guardrails"]["buy_sell_authorization"])


class TestStockEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_invalid_symbol_returns_404(self):
        from unittest import mock
        with mock.patch("web.api.routes.stock.analyze_stock", side_effect=ValueError("Stock not found")):
            r = self.client.get("/api/stock/XYZNOTREAL123")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.json())

    def test_numpy_and_nan_values_serialize(self):
        import numpy as np
        from unittest import mock
        fake = {"symbol": "X", "price": np.float64(10.5), "above_ema": np.bool_(True),
                "atr_14": float("nan"), "momentum_score": np.int64(70)}
        with mock.patch("web.api.routes.stock.analyze_stock", return_value=fake), \
             mock.patch("web.api.routes.stock._chart", return_value={}):
            r = self.client.get("/api/stock/X")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIs(body["analysis"]["above_ema"], True)
        self.assertIsNone(body["volatility"]["atr"])
        self.assertEqual(body["score"]["overall"], 70)

    def test_symbols_endpoint_returns_list(self):
        r = self.client.get("/api/symbols")
        self.assertEqual(r.status_code, 200)
        self.assertIsInstance(r.json(), list)

    def test_symbols_no_cache_returns_empty_without_download(self):
        from unittest import mock
        with mock.patch("web.api.routes.stock.symbol_master.MASTER_FILE") as mf, \
             mock.patch("web.api.routes.stock.symbol_master.load_master") as lm:
            mf.exists.return_value = False
            r = self.client.get("/api/symbols")
        self.assertEqual(r.json(), [])
        lm.assert_not_called()


class TestMarketAnalysisEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_market_analysis_returns_200(self):
        r = self.client.get("/api/market-analysis")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in ("regime", "breadth", "sectors", "flows", "derivatives"):
            self.assertIn(key, body)

    def test_market_analysis_no_cache(self):
        from unittest import mock
        with mock.patch("web.api.routes.analysis.load_cached_report", return_value=None):
            r = self.client.get("/api/market-analysis")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["regime"])


class TestRefreshEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_refresh_returns_status(self):
        from unittest import mock
        with mock.patch("web.api.scheduler.get_market_lab_data"):
            r = self.client.get("/api/refresh")
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["status"], ("refreshing", "already_running"))

    def test_concurrent_refresh_blocked(self):
        from unittest import mock
        from web.api import scheduler
        with mock.patch.object(scheduler, "_running", True):
            r = self.client.get("/api/refresh")
        self.assertEqual(r.json()["status"], "already_running")

    def test_lifespan_starts_and_stops_scheduler(self):
        from starlette.testclient import TestClient
        app = create_app()
        with TestClient(app):
            self.assertEqual(len(app.state.scheduler.get_jobs()), 4)


class TestFullIntegration(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_all_api_endpoints_return_200(self):
        for path in ["/api/health", "/api/market-overview", "/api/market-analysis", "/api/symbols"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, f"{path} returned {r.status_code}")

    def test_guardrails_in_all_market_responses(self):
        for path in ["/api/market-overview", "/api/market-analysis"]:
            with self.subTest(path=path):
                self.assertIn("guardrails", self.client.get(path).json())


class TestStaticServing(unittest.TestCase):
    def setUp(self):
        import tempfile
        from starlette.testclient import TestClient
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        dist = Path(self._tmp.name) / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<html>SPA</html>", encoding="utf-8")
        (dist / "assets" / "a.js").write_text("console.log(1)", encoding="utf-8")
        (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
        (Path(self._tmp.name) / "secret.txt").write_text("SECRET", encoding="utf-8")
        self.client = TestClient(create_app(dist))

    def test_deep_link_serves_index(self):
        r = self.client.get("/stock")
        self.assertEqual(r.status_code, 200)
        self.assertIn("SPA", r.text)
        self.assertIn("text/html", r.headers["content-type"])

    def test_assets_and_top_level_files(self):
        self.assertEqual(self.client.get("/assets/a.js").text, "console.log(1)")
        self.assertEqual(self.client.get("/favicon.svg").text, "<svg/>")

    def test_unknown_api_path_is_json_404(self):
        r = self.client.get("/api/nope")
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.json(), {"detail": "Not Found"})

    def test_real_api_still_wins(self):
        self.assertEqual(self.client.get("/api/health").json()["status"], "ok")

    def test_traversal_does_not_leak(self):
        for path in ["/..%2fsecret.txt", "/..%2f..%2fweb_main.py", "/%2e%2e/secret.txt", "/../secret.txt"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertNotIn("SECRET", r.text)
                self.assertNotIn("uvicorn", r.text)

    def test_no_dist_means_no_static(self):
        from starlette.testclient import TestClient
        c = TestClient(create_app(Path(self._tmp.name) / "missing"))
        self.assertEqual(c.get("/stock").status_code, 404)
        self.assertEqual(c.get("/api/health").status_code, 200)
