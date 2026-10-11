"""
Offline tests for market_lab/stock_adapter.py (per-stock analysis adapter).

Symbol resolution, candle building (+ real MA overlays), KPI extraction,
data-quality status and market context — all with `search_symbols`,
`get_price_history` stubbed so no network/MCP is touched. The MA math uses the
real `technical_engine.calculate_sma`.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_lab import stock_adapter
from market_lab import view_model as vm

N_A = vm.N_A


def _ohlcv_frame(n=30):
    idx = pd.date_range("2026-08-01", periods=n, freq="B")
    closes = [100.0 + (i % 7) * 0.5 + i * 0.1 for i in range(n)]
    return pd.DataFrame(
        {"Open": [c - 0.3 for c in closes], "High": [c + 0.6 for c in closes],
         "Low": [c - 0.6 for c in closes], "Close": closes,
         "Volume": [100000 + i for i in range(n)]},
        index=idx,
    )


class TestResolveSymbol(unittest.TestCase):

    def test_resolves_known(self):
        frame = pd.DataFrame([{"symbol": "RELIANCE",
                               "company_name": "Reliance Industries"}])
        with mock.patch("analysis.data.symbol_master.search_symbols",
                        return_value=frame):
            res = stock_adapter.resolve_symbol("reliance")
        self.assertEqual(res["symbol"], "RELIANCE")
        self.assertEqual(res["company_name"], "Reliance Industries")

    def test_unknown_returns_none(self):
        with mock.patch("analysis.data.symbol_master.search_symbols",
                        return_value=pd.DataFrame()):
            self.assertIsNone(stock_adapter.resolve_symbol("NOPE"))
        with mock.patch("analysis.data.symbol_master.search_symbols",
                        side_effect=RuntimeError("no master")):
            self.assertIsNone(stock_adapter.resolve_symbol("RELIANCE"))
        self.assertIsNone(stock_adapter.resolve_symbol(""))


class TestStockCandles(unittest.TestCase):

    def test_builds_candles_with_mas(self):
        with mock.patch("analysis.data.market_universe.get_price_history",
                        return_value=_ohlcv_frame(30)):
            candles = stock_adapter.stock_candles("RELIANCE", period="6mo")
        self.assertEqual(len(candles), 30)
        # ma20 populated; ma50/ma200 absent with only 30 rows.
        self.assertIsNotNone(candles[-1].get("ma20"))
        self.assertNotIn("ma50", candles[-1])
        self.assertNotIn("ma200", candles[-1])

    def test_empty_history(self):
        with mock.patch("analysis.data.market_universe.get_price_history",
                        return_value=pd.DataFrame()):
            self.assertEqual(stock_adapter.stock_candles("RELIANCE"), [])
        with mock.patch("analysis.data.market_universe.get_price_history",
                        side_effect=RuntimeError("down")):
            self.assertEqual(stock_adapter.stock_candles("RELIANCE"), [])


class TestOscillators(unittest.TestCase):

    def test_computes_real_rsi_macd_from_candles(self):
        candles = [
            {"t": f"d{i}", "o": 100, "h": 105, "l": 99,
             "c": 100.0 + (i % 5) + i * 0.1, "v": 1}
            for i in range(40)
        ]
        osc = stock_adapter.stock_oscillators(candles)
        self.assertEqual(len(osc["rsi"]), 40)
        self.assertEqual(len(osc["macd"]), 40)
        self.assertEqual(len(osc["signal"]), 40)

    def test_short_history_returns_empty(self):
        candles = [{"t": "d0", "o": 1, "h": 1, "l": 1, "c": 1, "v": 1}
                   for _ in range(5)]
        osc = stock_adapter.stock_oscillators(candles)
        self.assertEqual(osc["rsi"], [])
        self.assertEqual(osc["macd"], [])

    def test_none_history_is_safe(self):
        self.assertEqual(stock_adapter.stock_oscillators(None)["rsi"], [])


class TestKpiAndQuality(unittest.TestCase):

    def test_kpi_tiles(self):
        metrics = {"trend": "STRONG_UPTREND", "momentum_score": 92.0,
                   "rsi_14": 61.2, "macd": 12.3, "atr_14": 20.0,
                   "relative_volume": 1.4}
        k = stock_adapter.kpi_tiles(metrics)
        self.assertEqual(k["trend"], "STRONG_UPTREND")
        self.assertEqual(k["rsi"], 61.2)

    def test_kpi_tiles_empty(self):
        self.assertEqual(stock_adapter.kpi_tiles(None), {})

    def test_data_quality_marks_unavailable(self):
        dq = stock_adapter.data_quality({"price": 100.0}, [{"c": 1}])
        self.assertEqual(dq["Price quote"], "AVAILABLE")
        self.assertEqual(dq["Fundamentals"], "UNAVAILABLE")
        self.assertEqual(dq["Derivatives (stock-level)"], "UNAVAILABLE")

    def test_data_quality_partial_indicators(self):
        dq = stock_adapter.data_quality({"price": 100.0, "rsi_14": 50,
                                         "macd": 1.0}, [{"c": 1}])
        self.assertEqual(dq["RSI/MACD/ATR"], "AVAILABLE")

    def test_market_context_secondary(self):
        report = {"market_regime": "BEARISH",
                  "volatility": {"india_vix": {"value": 14.38}},
                  "institutional_flow": {"available": True,
                                         "metrics": {"fii_20d": -10.0}}}
        ctx = stock_adapter.market_context(report)
        self.assertEqual(ctx["market_regime"], "BEARISH")
        self.assertEqual(ctx["india_vix"], 14.38)


if __name__ == "__main__":
    unittest.main(verbosity=2)
