"""
Tests for the stock watchlist formatting. Offline only: no network, no
Qt, no live market data. Exercises the pure render helper used by the
Market Lab UI watchlist panel.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.data.watchlist_engine import (
    BUY_SELL_AUTHORIZATION,
    EXECUTION_ENABLED,
    MAX_SYMBOLS,
    format_watchlist_line,
)


def available_entry(**overrides):
    entry = {
        "engine": "Nova Stock Watchlist Engine",
        "status": "AVAILABLE",
        "symbol": "RELIANCE",
        "company_name": "Reliance Industries",
        "price": 2950.5,
        "change_percent": 1.234,
        "rsi_14": 62.5,
        "rsi_condition": "NEUTRAL",
        "trend": "UPTREND",
        "source": "NSE_MCP",
    }
    entry.update(overrides)
    return entry


class TestFormatWatchlistLine(unittest.TestCase):

    def test_waiting_when_no_entry(self):
        line = format_watchlist_line(None, "INFY")
        self.assertIn("INFY", line)
        self.assertIn("waiting", line)

    def test_available_line_formats_numbers(self):
        line = format_watchlist_line(available_entry(), "RELIANCE")
        self.assertIn("RELIANCE", line)
        self.assertIn("2950.50", line)
        self.assertIn("+1.23%", line)
        self.assertIn("62.5", line)
        self.assertIn("UPTREND", line)
        self.assertIn("NSE_MCP", line)

    def test_negative_change_is_signed(self):
        line = format_watchlist_line(
            available_entry(change_percent=-2.5), "RELIANCE"
        )
        self.assertIn("-2.50%", line)

    def test_not_available_shows_reason(self):
        entry = {
            "status": "NOT_AVAILABLE",
            "reason": "Engine returned no usable price.",
        }
        line = format_watchlist_line(entry, "TCS")
        self.assertIn("NOT AVAILABLE", line)
        self.assertIn("Engine returned no usable price.", line)

    def test_missing_numbers_render_as_dashes(self):
        # None readings must never crash the formatter or be fabricated.
        entry = available_entry(
            price=None,
            change_percent=None,
            rsi_14=None,
            rsi_condition=None,
            trend=None,
            source=None,
        )
        line = format_watchlist_line(entry, "RELIANCE")
        self.assertIn("--", line)
        self.assertNotIn("None", line)
        self.assertNotIn("nan", line.lower())

    def test_nan_reading_renders_as_dash(self):
        line = format_watchlist_line(
            available_entry(rsi_14=float("nan")), "RELIANCE"
        )
        self.assertIn("RSI --", line)

    def test_string_number_is_coerced(self):
        line = format_watchlist_line(
            available_entry(price="1234.5"), "RELIANCE"
        )
        self.assertIn("1234.50", line)

    def test_non_numeric_price_renders_as_dash(self):
        line = format_watchlist_line(
            available_entry(price="not-a-number"), "RELIANCE"
        )
        self.assertIn("₹--", line)

    def test_symbol_falls_back_to_requested(self):
        entry = available_entry(symbol=None)
        line = format_watchlist_line(entry, "SBIN")
        self.assertTrue(line.startswith("SBIN:"))


class TestGuardrails(unittest.TestCase):

    def test_execution_disabled(self):
        self.assertFalse(EXECUTION_ENABLED)
        self.assertFalse(BUY_SELL_AUTHORIZATION)

    def test_symbol_cap_is_sane(self):
        self.assertGreaterEqual(MAX_SYMBOLS, 1)
        self.assertLessEqual(MAX_SYMBOLS, 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
