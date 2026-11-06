import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.api.main import create_app
from unittest import mock as _mock

_offline = _mock.patch("analysis.data.nse_live.market", side_effect=RuntimeError("offline test"))
_no_save = _mock.patch("web.api.scheduler.save_json_report")  # never write real reports from tests


def setUpModule():
    # routes overlay live NSE quotes; keep these tests offline and deterministic
    _offline.start()
    _no_save.start()
    from web.api.routes import market
    market._live_cache.clear()


def tearDownModule():
    _offline.stop()
    _no_save.stop()


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
        for key in ("kpis", "breadth", "flows", "sectors",
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
        self.assertIn("guardrails", body)

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
            r = self.client.post("/api/refresh")
        self.assertEqual(r.status_code, 200)
        self.assertIn(r.json()["status"], ("refreshing", "already_running"))

    def test_refresh_get_not_allowed(self):
        # 405 from the router; 404 when the SPA catch-all (built dist) answers GET /api/*
        self.assertIn(self.client.get("/api/refresh").status_code, (404, 405))

    def test_refresh_foreign_origin_rejected(self):
        from unittest import mock
        with mock.patch("web.api.scheduler.get_market_lab_data") as m:
            r = self.client.post("/api/refresh", headers={"Origin": "https://evil.example"})
            r2 = self.client.post("/api/refresh", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(r.status_code, 403)
        self.assertIn("error", r.json())
        self.assertEqual(r2.status_code, 403)
        m.assert_not_called()

    def test_refresh_allowed_origin_ok(self):
        from unittest import mock
        with mock.patch("web.api.scheduler.get_market_lab_data"):
            r = self.client.post("/api/refresh", headers={
                "Origin": "http://localhost:5173", "Sec-Fetch-Site": "same-origin"})
        self.assertEqual(r.status_code, 200)

    def test_concurrent_refresh_blocked(self):
        from unittest import mock
        from web.api import scheduler
        with mock.patch.object(scheduler, "_running", True):
            r = self.client.post("/api/refresh")
        self.assertEqual(r.json()["status"], "already_running")

    def test_refresh_timeout_broadcasts_failure_and_resets(self):
        import asyncio, time
        from unittest import mock
        from web.api import scheduler
        q = scheduler.subscribe()
        try:
            with mock.patch.object(scheduler, "REFRESH_TIMEOUT_S", 0.05),                  mock.patch.object(scheduler, "get_market_lab_data", side_effect=lambda **k: time.sleep(0.3)),                  mock.patch.object(scheduler, "_running", True):
                asyncio.run(scheduler._run_refresh())
                self.assertFalse(scheduler._running)
            self.assertIn("refresh_failed", q.get_nowait())
        finally:
            scheduler.unsubscribe(q)

    def test_lifespan_starts_and_stops_scheduler(self):
        from starlette.testclient import TestClient
        from unittest import mock
        app = create_app()
        with mock.patch("web.api.scheduler.get_market_lab_data"),              mock.patch("analysis.data.nse_live.get", side_effect=RuntimeError("offline test")),              TestClient(app):
            jobs = app.state.scheduler.get_jobs()
            self.assertEqual(len(jobs), 4)
            for j in jobs:
                self.assertIn("day_of_week='mon-fri'", str(j.trigger))


    def test_missed_refresh_catch_up(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from web.api import scheduler
        tue_1100 = datetime(2026, 11, 3, 11, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
        self.assertEqual(scheduler.last_slot(tue_1100).strftime("%a %H:%M"), "Tue 09:15")
        mon_0800 = tue_1100.replace(day=2, hour=8)
        self.assertEqual(scheduler.last_slot(mon_0800).strftime("%a %d %H:%M"), "Fri 30 18:00")  # skips weekend
        self.assertTrue(scheduler.missed_refresh("2026-11-01T20:10:43", tue_1100))   # Sunday report
        self.assertFalse(scheduler.missed_refresh("2026-11-03T09:20:00", tue_1100))
        self.assertTrue(scheduler.missed_refresh(None, tue_1100))


class TestRefreshSaves(unittest.TestCase):
    def test_refresh_saves_the_report(self):
        import asyncio
        from unittest import mock
        from web.api import scheduler
        with mock.patch.object(scheduler, "get_market_lab_data", return_value={"generated": "x"}) as g,              mock.patch.object(scheduler, "save_json_report") as save,              mock.patch.object(scheduler, "_running", True):
            asyncio.run(scheduler._run_refresh())
        g.assert_called_once_with(force_refresh=True)
        save.assert_called_once_with({"generated": "x"})


class TestReportLoader(unittest.TestCase):
    def test_nan_in_saved_report_reads_as_null(self):
        import json, tempfile
        from pathlib import Path
        from unittest import mock
        from web.api import report_loader
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "market_lab").mkdir()
            (Path(d) / "market_lab" / "market_lab_20261104_010618.json").write_text('{"nifty_candles": [{"c": NaN}], "x": Infinity}')
            with mock.patch.object(report_loader, "CACHE_DIR", d):
                r = report_loader.load_cached_report()["report"]
        self.assertIsNone(r["nifty_candles"][0]["c"])
        self.assertIsNone(r["x"])
        json.dumps(r, allow_nan=False)  # the API encoder's rule


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
        self.assertEqual(r.headers["cache-control"], "no-cache")  # a new build must show at once
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


class TestFlowsHistoryEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_rows_keep_scope_and_nan_becomes_null(self):
        import pandas as pd
        from unittest import mock
        df = pd.DataFrame([
            {"date": "2026-10-29", "fii_net": float("nan"), "dii_net": 5.0, "combined_net": None,
             "market_scope": "NSE_ONLY", "source": "x", "provisional": False},
            {"date": "2026-10-28", "fii_net": -10.0, "dii_net": 20.0, "combined_net": 10.0,
             "market_scope": "NSE_BSE_MSEI_COMBINED", "source": "y", "provisional": True},
        ])
        with mock.patch("web.api.routes.analysis.flow_engine.load_history", return_value=df):
            body = self.client.get("/api/flows/history").json()
        self.assertEqual([r["date"] for r in body["rows"]], ["2026-10-28", "2026-10-29"])
        self.assertEqual(body["rows"][1]["market_scope"], "NSE_ONLY")
        self.assertIsNone(body["rows"][1]["fii_net"])
        self.assertIn("target_scope", body)

    def test_store_failure_returns_502(self):
        from unittest import mock
        with mock.patch("web.api.routes.analysis.flow_engine.load_history", side_effect=RuntimeError("bad csv")):
            r = self.client.get("/api/flows/history")
        self.assertEqual(r.status_code, 502)
        self.assertIn("bad csv", r.json()["error"])


class TestDeskEndpoints(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_scan_shape_and_guardrail(self):
        r = self.client.get("/api/scan")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("rows", body)
        if body["available"]:
            self.assertEqual(len(body["rows"][0]), len(body["columns"]))
            self.assertFalse(body["guardrails"]["buy_sell_authorization"])

    def test_audit_exposes_policy(self):
        r = self.client.get("/api/audit")
        self.assertEqual(r.status_code, 200)
        self.assertIn("decision_policy", r.json())

    def test_partial_scan_is_skipped(self):
        import csv, tempfile, os
        from web.api.routes import desk
        with tempfile.TemporaryDirectory() as d:
            partial, full = os.path.join(d, "market_scan_b.csv"), os.path.join(d, "market_scan_a.csv")
            for path, count in ((partial, 3), (full, desk.MIN_COMPLETE_ROWS)):
                with open(path, "w", newline="", encoding="utf8") as f:
                    w = csv.DictWriter(f, ["symbol", "price"])
                    w.writeheader()
                    w.writerows({"symbol": f"S{i}", "price": 10} for i in range(count))
            path, rows, newest = desk.latest_complete_scan(d, [partial, full])
        self.assertEqual(path, full)
        self.assertEqual(len(rows), desk.MIN_COMPLETE_ROWS)
        self.assertEqual(newest, 3)

    def test_sector_table_skips_thin_groups_and_counts_above_200d(self):
        from web.api.routes import desk
        row = dict.fromkeys(("price", "volume", "return_1d", "return_5d", "return_20d", "return_60d", "relative_strength_20d", "ema_20", "ema_50", "ema_200", "rsi_14", "atr_percent", "relative_volume", "high_52w", "low_52w", "distance_52w_high", "score"), 100)
        rows = [{**row, "symbol": f"A{i}", "trend": "UPTREND", "price": 110 if i else 90} for i in range(5)] + [{**row, "symbol": "B", "trend": "UPTREND"}]
        stocks = desk.build_stocks(rows, {**{f"A{i}": "Big" for i in range(5)}, "B": "Thin"}, {})
        table = desk.build_sectors(stocks)
        self.assertEqual([s["n"] for s in table], ["Big"])
        self.assertEqual(table[0]["a200"], 80.0)
        self.assertEqual(stocks[0]["t"], "Up")


class TestLiveBreadth(unittest.TestCase):
    def test_index_summed_advances_never_replace_scan_breadth(self):
        from web.api.routes.market import apply_live
        live = {"data": {"as_of": "t", "status": None, "gift_nifty": None, "sectors": [], "breadth": {"advances": 4761, "declines": 4752, "new_52w_highs": 40}}, "error": None}
        body = apply_live({"kpis": {}, "breadth": {"advancing": 660, "declining": 1326, "ad_ratio": 0.5}}, live)
        self.assertEqual(body["breadth"]["advancing"], 660)
        self.assertEqual(body["breadth"]["ad_ratio"], 0.5)
        self.assertEqual(body["breadth"]["new_52w_highs"], 40)


class TestLauncherBuild(unittest.TestCase):
    def test_rebuilds_when_missing_or_older_than_source(self):
        import os, tempfile
        import web_main
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src").mkdir()
            source = root / "src" / "a.tsx"
            source.write_text("x", encoding="utf-8")
            dist = root / "dist" / "index.html"
            with _mock.patch.multiple(web_main, FRONTEND=root, DIST_INDEX=dist):
                self.assertTrue(web_main.needs_build())
                dist.parent.mkdir()
                dist.write_text("built", encoding="utf-8")
                os.utime(dist, (2_000_000_000, 2_000_000_000))
                self.assertFalse(web_main.needs_build())
                os.utime(source, (2_000_000_100, 2_000_000_100))
                self.assertTrue(web_main.needs_build())
