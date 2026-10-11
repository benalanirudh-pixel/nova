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


class TestExtractCloseSeries(unittest.TestCase):

    def _df(self):
        import pandas as pd
        return pd.DataFrame({
            "Date": ["2026-10-01", "2026-10-02", "2026-10-05"],
            "Close": [100.0, 102.0, 101.0],
        })

    def test_extracts_close_with_dates(self):
        series = mld.extract_close_series(self._df(), limit=40)
        self.assertEqual(len(series), 3)
        self.assertEqual(series[0]["close"], 100.0)
        self.assertEqual(series[-1]["close"], 101.0)
        self.assertEqual(series[0]["date"], "2026-10-01")

    def test_limit_takes_last_n(self):
        series = mld.extract_close_series(self._df(), limit=2)
        self.assertEqual(len(series), 2)
        self.assertEqual(series[-1]["close"], 101.0)

    def test_empty_frame(self):
        import pandas as pd
        self.assertEqual(mld.extract_close_series(pd.DataFrame(), limit=40), [])
        self.assertEqual(mld.extract_close_series(None), [])

    def test_missing_close_column(self):
        import pandas as pd
        df = pd.DataFrame({"Open": [1.0, 2.0]})
        self.assertEqual(mld.extract_close_series(df), [])


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


def _volatility_fixture():
    return {
        "india_vix": {
            "available": True, "value": 15.0, "change_percent": -5.0,
            "percentile_1y": 70.3, "regime": "MODERATE", "direction": "FALLING",
            "source": "VOL_ENGINE",
        },
        "bank_nifty": {
            "available": True, "price": 55000.0, "atr14": 741.3,
            "realized_volatility_20d": 14.7, "volatility_regime": "MODERATE",
            "source": "VOL_ENGINE",
        },
    }


class TestApplyDhanVolatilityOverrides(unittest.TestCase):

    def test_overrides_bank_and_vix_preserving_engine_fields(self):
        overrides = {
            "nifty": {"available": False},
            "bank_nifty": {"available": True, "price": 55256.65,
                           "last_trade_time": "15:30"},
            "india_vix": {"available": True, "value": 14.38,
                          "change_percent": -5.9},
        }
        vol = _volatility_fixture()
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value=overrides):
            out = mld._apply_dhan_volatility_overrides(vol)
        # BANK NIFTY price overridden; ATR/vol preserved.
        self.assertEqual(out["bank_nifty"]["price"], 55256.65)
        self.assertEqual(out["bank_nifty"]["atr14"], 741.3)
        self.assertEqual(out["bank_nifty"]["source"], "DHAN_LIVE")
        self.assertEqual(out["bank_nifty"]["last_trade_time"], "15:30")
        # VIX value/change overridden; percentile/regime preserved.
        self.assertEqual(out["india_vix"]["value"], 14.38)
        self.assertEqual(out["india_vix"]["change_percent"], -5.9)
        self.assertEqual(out["india_vix"]["percentile_1y"], 70.3)
        self.assertEqual(out["india_vix"]["regime"], "MODERATE")
        self.assertEqual(out["india_vix"]["source"], "DHAN_LIVE")
        # Original not mutated.
        self.assertEqual(vol["bank_nifty"]["price"], 55000.0)

    def test_bank_only_override_leaves_vix(self):
        overrides = {"bank_nifty": {"available": True, "price": 55200.0},
                     "india_vix": {"available": False}}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value=overrides):
            out = mld._apply_dhan_volatility_overrides(_volatility_fixture())
        self.assertEqual(out["bank_nifty"]["price"], 55200.0)
        self.assertEqual(out["india_vix"]["value"], 15000 / 1000.0)  # untouched 15.0

    def test_no_overrides_returns_original_object(self):
        vol = _volatility_fixture()
        with mock.patch.object(mld, "_dhan_index_overrides", return_value={}):
            self.assertIs(mld._apply_dhan_volatility_overrides(vol), vol)

    def test_both_unavailable_returns_original_object(self):
        vol = _volatility_fixture()
        overrides = {"bank_nifty": {"available": False},
                     "india_vix": {"available": False}}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value=overrides):
            self.assertIs(mld._apply_dhan_volatility_overrides(vol), vol)

    def test_non_dict_volatility_unchanged(self):
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value={"india_vix": {"available": True,
                                                           "value": 14.0}}):
            self.assertEqual(mld._apply_dhan_volatility_overrides("nope"), "nope")

    def test_override_error_returns_original(self):
        vol = _volatility_fixture()
        with mock.patch.object(mld, "_dhan_index_overrides",
                               side_effect=RuntimeError("boom")):
            self.assertIs(mld._apply_dhan_volatility_overrides(vol), vol)

    def test_missing_engine_leg_is_created(self):
        overrides = {"bank_nifty": {"available": True, "price": 55256.65},
                     "india_vix": {"available": True, "value": 14.38}}
        with mock.patch.object(mld, "_dhan_index_overrides",
                               return_value=overrides):
            out = mld._apply_dhan_volatility_overrides({"nifty": {"x": 1}})
        self.assertEqual(out["bank_nifty"]["price"], 55256.65)
        self.assertTrue(out["india_vix"]["available"])
        self.assertEqual(out["india_vix"]["value"], 14.38)
        self.assertEqual(out["nifty"], {"x": 1})  # untouched


if __name__ == "__main__":
    unittest.main(verbosity=2)
