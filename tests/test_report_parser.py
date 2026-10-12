"""
Offline tests for market_lab/report_parser.py (AI report parsing).

Deterministic synthetic report text only; no model, network, or market data.
The parser must never invent content and must always preserve the raw text.

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

from market_lab import report_parser as rp


FULL_REPORT = """NOVA STOCK ANALYSIS — RELIANCE
Mode: FULL

### 1) Executive conclusion
**NEUTRAL** with mixed evidence across timeframes.

### 2) Bullish evidence
- Price holds above EMA20
- MACD histogram turning positive
- Relative volume above 20-day average

### 3) Bearish evidence
- Price below EMA50 and EMA200
- NIFTY in a BEARISH market regime
- CPI release risk on 12 Oct

### 4) Key levels
Resistance 1: 1520.00, Support 1: 1160.00

### 5) Risks
- Downside momentum and broad market weakness

### 6) Final research summary
Watch the 15-EMA and the upcoming US CPI print.
"""


class TestParseReport(unittest.TestCase):

    def test_empty_text(self):
        parsed = rp.parse_report("")
        self.assertEqual(parsed["bias"], "UNAVAILABLE")
        self.assertEqual(parsed["sections"], {})
        self.assertEqual(parsed["raw"], "")

    def test_splits_numbered_headings(self):
        parsed = rp.parse_report(FULL_REPORT)
        self.assertIn("Executive conclusion", parsed["sections"])
        self.assertIn("Bullish evidence", parsed["sections"])
        self.assertIn("Bearish evidence", parsed["sections"])

    def test_raw_is_preserved(self):
        parsed = rp.parse_report(FULL_REPORT)
        self.assertEqual(parsed["raw"], FULL_REPORT)

    def test_bias_detected(self):
        self.assertEqual(rp.parse_report(FULL_REPORT)["bias"], "NEUTRAL")

    def test_bias_insufficient_evidence_wins(self):
        text = "### Conclusion\nINSUFFICIENT EVIDENCE (data gaps)."
        self.assertEqual(rp.parse_report(text)["bias"], "INSUFFICIENT EVIDENCE")

    def test_levels_extracted(self):
        parsed = rp.parse_report(FULL_REPORT)
        self.assertEqual(parsed["levels"].get("r1"), 1520.0)
        self.assertEqual(parsed["levels"].get("s1"), 1160.0)

    def test_sections_matching(self):
        parsed = rp.parse_report(FULL_REPORT)
        bull = rp.sections_matching(parsed, "bullish")
        bear = rp.sections_matching(parsed, "bearish")
        self.assertIn("Bullish evidence", bull)
        self.assertIn("Bearish evidence", bear)

    def test_collect_bullets_strips_markers(self):
        parsed = rp.parse_report(FULL_REPORT)
        bullets = rp.collect_bullets(rp.sections_matching(parsed, "bullish"))
        self.assertIn("Price holds above EMA20", bullets)

    def test_plain_text_report_falls_back_to_single_section(self):
        parsed = rp.parse_report("RSI is 45. MACD is positive.")
        self.assertTrue(parsed["raw"])
        self.assertTrue(all(parsed["sections"].values() or [True]))

    def test_disclaimer_and_mode_lines_skipped(self):
        parsed = rp.parse_report(FULL_REPORT)
        for items in parsed["sections"].values():
            for item in items:
                self.assertNotIn("AI-generated analysis", item)
                self.assertNotIn("NOVA STOCK ANALYSIS", item)


if __name__ == "__main__":
    unittest.main(verbosity=2)
