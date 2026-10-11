"""
Offline tests for the opt-in Dhan NIFTY-snapshot override in Market Lab's
report generator (market_lab/market_lab_data.py).

Only the small, pure `_dhan_index_overrides` / `_apply_dhan_override` helpers
are tested (with the Dhan adapter stubbed), so the heavy report pipeline and
network are never invoked. Default behavior (Dhan unconfigured) must leave the
snapshot unchanged.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_lab.market_lab_data as mld


class TestApplyDhanOverride(unittest.TestCase):

    def test_overrides_when_dhan_available(self):
        original = {"available": True, "price": 999.0, "source": "YAHOO"}
        dhan_nifty = {"available": True, "price": 22520.4,
                      "change_percent": 1.3, "source": "DHAN_LIVE"}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value={"nifty": dhan_nifty}):
            out = mld._apply_dhan_override(original)
        self.assertEqual(out, dhan_nifty)

    def test_keeps_original_when_overrides_empty(self):
        original = {"available": True, "price": 999.0}
        with mock.patch.object(mld, "_dhan_index_overrides", return_value={}):
            self.assertEqual(mld._apply_dhan_override(original), original)

    def test_keeps_original_when_dhan_unavailable(self):
        original = {"available": True, "price": 999.0}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value={"nifty": {"available": False}}):
            self.assertEqual(mld._apply_dhan_override(original), original)

    def test_keeps_original_on_override_error(self):
        original = {"available": True, "price": 999.0}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               side_effect=RuntimeError("boom")):
            self.assertEqual(mld._apply_dhan_override(original), original)

    def test_dhan_index_overrides_unconfigured_is_empty(self):
        # No token/env in test env -> adapter reports unconfigured -> {}.
        with mock.patch("analysis.data.dhan_feed.is_configured",
                        return_value=False):
            self.assertEqual(mld._dhan_index_overrides(), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
