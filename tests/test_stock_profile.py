import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data import stock_profile as sp


class TestParsers(unittest.TestCase):
    def test_quarters_sorted_newest_first_with_growth_in_crore(self):
        rows = [{"period": f"2026-0{m}-30", "Total Revenue": rev * 1e7, "Operating Income": rev * 1e6,
                 "Net Income": 10 * 1e7, "Diluted EPS": 1.0}
                for m, rev in [(1, 100), (6, 120), (3, 110), (2, 105), (5, 115)]]
        q = sp.parse_quarters({"data": rows})
        self.assertEqual([r["period"] for r in q], ["2026-06-30", "2026-05-30", "2026-03-30", "2026-02-30", "2026-01-30"])
        self.assertAlmostEqual(q[0]["revenue_cr"], 120)
        self.assertAlmostEqual(q[0]["revenue_qoq"], (120 - 115) / 115 * 100)
        self.assertAlmostEqual(q[0]["revenue_yoy"], 20.0)  # 4 quarters back = 100
        self.assertAlmostEqual(q[0]["operating_margin"], 10.0)
        self.assertIsNone(q[-1]["revenue_qoq"])

    def test_quarters_missing_values_stay_none(self):
        q = sp.parse_quarters({"data": [{"period": "2026-06-30", "Total Revenue": float("nan")}]})
        self.assertIsNone(q[0]["revenue_cr"])
        self.assertIsNone(q[0]["operating_margin"])

    def test_news_keeps_https_only_and_strips_source_suffix(self):
        items = [
            {"title": "Big move - Reuters", "link": "https://x.test/a", "source": "Reuters", "published": "Mon, 02 Nov 2026 03:50:00 GMT"},
            {"title": "Bad link", "link": "javascript:alert(1)", "source": "Evil"},
            {"title": "", "link": "https://x.test/b"},
        ]
        n = sp.parse_news(items)
        self.assertEqual(len(n), 1)
        self.assertEqual(n[0]["title"], "Big move")
        self.assertEqual(n[0]["published"], "2026-11-02T03:50:00+00:00")

    def test_ratios_scale_debt_equity_and_derive_yield(self):
        r = sp.parse_ratios({"debt_to_equity": 44.3, "dividend_per_share": 6, "dividend_yield": 52.0}, price=1200)
        self.assertAlmostEqual(r["debt_to_equity_x"], 0.443)
        self.assertAlmostEqual(r["dividend_yield_pct"], 0.5)
        self.assertNotIn("dividend_yield", r)

    def test_error_of(self):
        self.assertEqual(sp._error_of({"error": "blocked"}), "blocked")
        self.assertIsNotNone(sp._error_of([]))
        self.assertIsNotNone(sp._error_of(RuntimeError("x")))
        self.assertIsNone(sp._error_of({"a": 1}))


class TestHighlights(unittest.TestCase):
    def test_tones_follow_thresholds(self):
        h = sp.build_highlights(
            {"revenue_growth": 20.0, "earnings_growth": -5.0, "roe": 8.0, "debt_to_equity_x": 0.1, "peg": 0.8},
            {"distance_from_52w_high": -2.0, "relative_strength_20d": -4.0},
            {"institutions_pct": 30.0}, "2026-11-10", None, today=date(2026, 11, 2))
        tones = {x["text"].split(" ")[0]: x["tone"] for x in h}
        self.assertEqual(tones["Revenue"], "positive")
        self.assertEqual(tones["Earnings"], "negative")
        self.assertEqual(tones["Return"], "negative")
        self.assertEqual(tones["Debt"], "positive")
        self.assertEqual(tones["Underperformed"], "negative")
        self.assertTrue(any("Results due in 8 days" in x["text"] for x in h))

    def test_no_data_no_highlights(self):
        self.assertEqual(sp.build_highlights(None, None, None, None, None), [])

    def test_never_says_buy_or_sell(self):
        h = sp.build_highlights({"revenue_growth": 50, "peg": 0.2, "roe": 40}, None, None, None, None)
        self.assertFalse(any(w in x["text"].lower() for x in h for w in ("buy", "sell")))


class TestLocalPeers(unittest.TestCase):
    def test_same_industry_ranked_by_traded_value_self_included(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            cls = d / "cls.csv"
            cls.write_text(
                "symbol,company_name,macro_sector,sector,industry,basic_industry,classification_source\n"
                + "".join(f"S{i},Co {i},M,S,Ind,Basic,x\n" for i in range(10))
                + "OTHER,Other,M,S,Ind2,Basic2,x\n")
            scan = d / "market_scan_20261102_000000.csv"
            scan.write_text("symbol,price,return_20d,volume_average_20\n"
                            + "".join(f"S{i},{10 + i},{i},{1000 * (i + 1)}\n" for i in range(10)) + "OTHER,1,1,1\n")
            p = sp.local_peers("S0", limit=4, classification_file=cls, scanner_dir=d)
        self.assertEqual(p["group"], "Basic")
        self.assertEqual(p["peer_count"], 10)
        syms = [r["symbol"] for r in p["rows"]]
        self.assertEqual(syms, ["S9", "S8", "S7", "S0"])  # S0 is smallest but always kept
        self.assertTrue(p["rows"][-1]["is_self"])
        self.assertNotIn("OTHER", syms)

    def test_unknown_symbol(self):
        with tempfile.TemporaryDirectory() as d:
            cls = Path(d) / "cls.csv"
            cls.write_text("symbol,company_name,macro_sector,sector,industry,basic_industry,classification_source\n")
            self.assertIsNone(sp.local_peers("NOPE", classification_file=cls, scanner_dir=Path(d)))


class TestBuildProfile(unittest.TestCase):
    def test_failed_sources_become_none_with_reason(self):
        raw = {"profile": {"company": "X Ltd", "price": 100, "website": "javascript:x"},
               "ratios": {"error": "down"}, "income": RuntimeError("boom"), "news": [],
               "actions": [], "shareholding": {"error": "blocked"}, "board": {"error": "blocked"}}
        with mock.patch.object(sp.nse_feed, "call_tools", return_value=raw), \
             mock.patch.object(sp, "yahoo_sections", return_value={"calendar": None, "holders": None, "errors": {}}), \
             mock.patch.object(sp, "local_peers", return_value=None):
            p = sp.build_stock_profile("x")
        self.assertEqual(p["symbol"], "X")
        self.assertEqual(p["profile"]["company"], "X Ltd")
        self.assertIsNone(p["profile"]["website"])
        for k in ("ratios", "quarters", "news", "ownership", "results", "peers"):
            self.assertIsNone(p[k], k)
        self.assertEqual(p["errors"]["ratios"], "down")
        self.assertIn("boom", p["errors"]["income"])


class TestProfileRoute(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        from web.api.main import create_app
        from web.api.routes import stock
        stock._profile_cache.clear()
        self.client = TestClient(create_app())

    def test_rejects_bad_symbol(self):
        r = self.client.get("/api/stock/..%2Fetc/profile")
        self.assertIn(r.status_code, (400, 404))

    def test_returns_guardrails_and_caches(self):
        fake = {"symbol": "X", "errors": {}, "highlights": []}
        with mock.patch("web.api.routes.stock.stock_profile.build_stock_profile", return_value=fake) as b:
            r1 = self.client.get("/api/stock/X/profile")
            r2 = self.client.get("/api/stock/x/profile")
        self.assertEqual(r1.status_code, 200)
        self.assertIn("guardrails", r1.json())
        self.assertEqual(r2.json()["symbol"], "X")
        self.assertEqual(b.call_count, 1)


if __name__ == "__main__":
    unittest.main()
