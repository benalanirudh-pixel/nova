"""
Tests for the Nova Market Lab brain's single-stock focus path (in
market_lab/market_lab_brain.py).

Offline: focus-symbol detection uses the cached symbol master (stubbed here),
the per-stock snapshot uses the watchlist engine (stubbed), and the Ollama
call is stubbed so no provider or GPU is touched.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_lab.market_lab_brain as mlb


def report_fixture(**overrides):
    report = {
        "generated": "2026-10-10T13:00:00+00:00",
        "market": "NSE",
        "stocks_analyzed": 1999,
        "market_regime": "BEARISH",
        "nifty_snapshot": {"price": 22520.45, "change_percent": 1.3},
        "breadth": {"advancing": 1169, "declining": 807},
        "data_availability": {"market_scanner": "AVAILABLE"},
        "decision_policy": {"buy_sell_authorized": False},
        "ai_context": {},
        "top_technical_stocks": [
            {"symbol": "AAA", "technical_score": 100.0, "trend": "STRONG_UPTREND"},
        ],
        "research_factors": {
            "status": "AVAILABLE",
            "method": "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT",
            "universe_size": 1999,
            "top_ranked": [
                {"rank": 1, "symbol": "UEL", "composite_z": 1.448},
                {"rank": 2, "symbol": "RELIANCE", "composite_z": 0.92},
            ],
            "bottom_ranked": [
                {"rank": 1, "symbol": "ATALREAL", "composite_z": -1.35},
            ],
        },
    }
    report.update(overrides)
    return report


class TestExtractFocusSymbol(unittest.TestCase):

    def test_named_stock_uppercase(self):
        with mock.patch.object(mlb, "_known_symbols",
                               return_value={"RELIANCE", "TCS", "INFY"}):
            self.assertEqual(mlb._extract_focus_symbol("tell me about RELIANCE"),
                             "RELIANCE")

    def test_named_stock_lowercase(self):
        with mock.patch.object(mlb, "_known_symbols",
                               return_value={"RELIANCE", "TCS", "INFY"}):
            self.assertEqual(mlb._extract_focus_symbol("how is reliance doing"),
                             "RELIANCE")

    def test_benchmarks_and_broad_words_are_not_stocks(self):
        with mock.patch.object(mlb, "_known_symbols",
                               return_value={"RELIANCE", "TCS"}):
            self.assertEqual(mlb._extract_focus_symbol("what about bank nifty"), "")
            self.assertEqual(mlb._extract_focus_symbol("market overview"), "")
            self.assertEqual(mlb._extract_focus_symbol("show market breadth"), "")
            self.assertEqual(mlb._extract_focus_symbol("explain the trend"), "")

    def test_no_named_stock_with_master(self):
        with mock.patch.object(mlb, "_known_symbols", return_value={"RELIANCE"}):
            self.assertEqual(
                mlb._extract_focus_symbol("what is the outlook for india"), ""
            )

    def test_fallback_without_master_uses_uppercase_token(self):
        with mock.patch.object(mlb, "_known_symbols", return_value=None):
            self.assertEqual(mlb._extract_focus_symbol("check TCS please"), "TCS")
            # lowercase only, no master to validate -> stay broad
            self.assertEqual(mlb._extract_focus_symbol("tell me about reliance"), "")


class TestFocusPayload(unittest.TestCase):

    def test_includes_live_snapshot_and_factor_membership(self):
        live = {"status": "AVAILABLE", "symbol": "RELIANCE", "price": 2900.0,
                "rsi_14": 55.0, "trend": "STRONG_UPTREND"}
        with mock.patch("analysis.data.watchlist_engine.refresh_watch_symbol",
                        return_value=live), \
             mock.patch("analysis.data.symbol_master.get_security",
                        return_value={"company_name": "Reliance Industries"}):
            focus = mlb._focus_payload("RELIANCE", report_fixture())
        self.assertEqual(focus["requested_symbol"], "RELIANCE")
        self.assertEqual(focus["company_name"], "Reliance Industries")
        self.assertEqual(focus["live_snapshot"]["price"], 2900.0)
        self.assertTrue(focus["factor_membership"]["in_stored_extremes"])
        self.assertEqual(focus["factor_membership"]["side"], "top")
        self.assertEqual(focus["factor_membership"]["rank"], 2)

    def test_symbol_not_in_extremes(self):
        live = {"status": "AVAILABLE", "symbol": "IDEA", "price": 12.0}
        with mock.patch("analysis.data.watchlist_engine.refresh_watch_symbol",
                        return_value=live), \
             mock.patch("analysis.data.symbol_master.get_security",
                        return_value={"name": "Vodafone Idea"}):
            focus = mlb._focus_payload("IDEA", report_fixture())
        self.assertFalse(focus["factor_membership"]["in_stored_extremes"])

    def test_live_unavailable_is_honest(self):
        with mock.patch("analysis.data.watchlist_engine.refresh_watch_symbol",
                        return_value={"status": "UNAVAILABLE",
                                      "reason": "no data",
                                      "symbol": "RELIANCE"}), \
             mock.patch("analysis.data.symbol_master.get_security",
                        side_effect=Exception("no master")):
            focus = mlb._focus_payload("RELIANCE", report_fixture())
        self.assertEqual(focus["live_snapshot"]["status"], "UNAVAILABLE")
        self.assertNotIn("company_name", focus)

    def test_watchlist_engine_exception_is_caught(self):
        with mock.patch("analysis.data.watchlist_engine.refresh_watch_symbol",
                        side_effect=RuntimeError("nse down")), \
             mock.patch("analysis.data.symbol_master.get_security",
                        return_value=None):
            focus = mlb._focus_payload("RELIANCE", report_fixture())
        self.assertEqual(focus["live_snapshot"]["status"], "UNAVAILABLE")
        self.assertIn("nse down", focus["live_snapshot"]["reason"].lower())

    def test_json_safe(self):
        with mock.patch("analysis.data.watchlist_engine.refresh_watch_symbol",
                        return_value={"status": "AVAILABLE", "symbol": "RELIANCE",
                                      "price": float("nan")}), \
             mock.patch("analysis.data.symbol_master.get_security",
                        return_value=None):
            focus = mlb._focus_payload("RELIANCE", report_fixture())
        self.assertIsNone(focus["live_snapshot"]["price"])


class TestBuildPayload(unittest.TestCase):

    def test_focus_and_factors_added(self):
        payload = mlb._build_analysis_payload(
            report_fixture(),
            focus={"requested_symbol": "RELIANCE"},
        )
        self.assertIn("focus_symbol", payload)
        self.assertEqual(payload["focus_symbol"]["requested_symbol"], "RELIANCE")
        self.assertIn("research_factors", payload)
        self.assertEqual(payload["research_factors"]["method"],
                         "CROSS_SECTIONAL_ZSCORE_EQUAL_WEIGHT")

    def test_broad_payload_has_no_focus(self):
        payload = mlb._build_analysis_payload(report_fixture())
        self.assertNotIn("focus_symbol", payload)


class TestAnalyzeBranchesPrompt(unittest.TestCase):

    def _stub_ollama(self):
        captured = {}

        def fake_chat(**kwargs):
            captured["messages"] = kwargs["messages"]
            return SimpleNamespace(message=SimpleNamespace(content="ok"))

        return fake_chat, captured

    def test_single_stock_prompt(self):
        fake, captured = self._stub_ollama()
        with mock.patch.object(mlb, "get_market_lab_data",
                               return_value=report_fixture()), \
             mock.patch.object(mlb, "_extract_focus_symbol",
                               return_value="RELIANCE"), \
             mock.patch.object(mlb, "_focus_payload",
                               return_value={"requested_symbol": "RELIANCE"}), \
             mock.patch.object(mlb.ollama, "chat", side_effect=fake):
            out = mlb.analyze_market_lab("tell me about RELIANCE")
        user_msg = captured["messages"][1]["content"]
        self.assertIn("FOCUS STOCK JSON", user_msg)
        self.assertIn("Answer about the requested stock", user_msg)
        self.assertNotIn("Cover both benchmarks", user_msg)
        self.assertIn("Focus: RELIANCE", out)

    def test_broad_prompt_unchanged(self):
        fake, captured = self._stub_ollama()
        with mock.patch.object(mlb, "get_market_lab_data",
                               return_value=report_fixture()), \
             mock.patch.object(mlb, "_extract_focus_symbol", return_value=""), \
             mock.patch.object(mlb.ollama, "chat", side_effect=fake):
            out = mlb.analyze_market_lab("")
        user_msg = captured["messages"][1]["content"]
        self.assertIn("MARKET LAB REPORT JSON", user_msg)
        self.assertIn("IMPORTANT DATA RULES", user_msg)
        self.assertIn("Cover both benchmarks", user_msg)
        self.assertNotIn("FOCUS STOCK JSON", user_msg)
        self.assertIn("NOVA MARKET LAB ANALYSIS", out)

    def test_data_error_returns_message(self):
        with mock.patch.object(mlb, "get_market_lab_data",
                               side_effect=RuntimeError("boom")):
            out = mlb.analyze_market_lab("reliance")
        self.assertIn("MARKET LAB DATA ERROR", out)


class TestAnalyzeStockReport(unittest.TestCase):

    def _metrics(self):
        return {"symbol": "RELIANCE", "company_name": "Reliance Industries",
                "exchange": "NSE", "price": 2850.0, "change_percent": 0.8,
                "rsi_14": 55.0, "macd": 5.0, "trend": "STRONG_UPTREND"}

    def test_returns_focused_report_with_disclaimer(self):
        captured = {}

        def fake_chat(**kwargs):
            captured["messages"] = kwargs["messages"]
            from types import SimpleNamespace
            return SimpleNamespace(message=SimpleNamespace(
                content="**Conclusion:** neutral — mixed evidence."))

        with mock.patch.dict("os.environ", {}), \
             mock.patch.object(mlb.ollama, "chat", side_effect=fake_chat):
            out = mlb.analyze_stock_report(
                "RELIANCE", self._metrics(), [], {}, "full")

        self.assertIn("NOVA STOCK ANALYSIS — RELIANCE", out)
        self.assertIn("Not a validated prediction or instruction to trade", out)
        self.assertIn("informational and educational purposes only", out)
        # prompt is stock-scoped and carries the identity + data JSON.
        user_msg = captured["messages"][1]["content"]
        self.assertIn("ANALYZE THIS ONE STOCK: RELIANCE", user_msg)
        self.assertIn("MODE: FULL", user_msg)
        self.assertIn("Reliance Industries", user_msg)

    def test_mode_changes_prompt(self):
        captured = {}

        def fake_chat(**kwargs):
            captured["messages"] = kwargs["messages"]
            from types import SimpleNamespace
            return SimpleNamespace(message=SimpleNamespace(content="ok"))

        with mock.patch.object(mlb.ollama, "chat", side_effect=fake_chat):
            mlb.analyze_stock_report("TCS", {}, [], {}, "quick")
        self.assertIn("MODE: QUICK", captured["messages"][1]["content"])
        self.assertIn("QUICK SCAN", captured["messages"][1]["content"])

    def test_empty_model_response_is_error(self):
        from types import SimpleNamespace
        with mock.patch.object(mlb.ollama, "chat",
                               return_value=SimpleNamespace(
                                   message=SimpleNamespace(content=""))):
            out = mlb.analyze_stock_report("TCS", {}, [], {}, "full")
        self.assertIn("STOCK ANALYSIS AI ERROR", out)

    def test_model_not_found_404(self):
        err = mlb.ollama.ResponseError("not found")
        err.status_code = 404
        with mock.patch.object(mlb.ollama, "chat", side_effect=err):
            out = mlb.analyze_stock_report("TCS", {}, [], {}, "full")
        self.assertIn("ollama pull", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
