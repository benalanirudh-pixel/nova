"""
Offline tests for the Dhan market-data adapter (analysis/data/dhan_feed.py)
and its opt-in wiring in analysis/data/market_universe.get_price_history.

No network: requests.post is stubbed, and config/cache paths point at temp
dirs. The adapter is read-only market-data only (no trading endpoints), and
get_price_history must keep working when Dhan is disabled.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

import analysis.data.dhan_feed as dhan
import analysis.data.market_universe as mu


def _payload(n=3, start=1_700_000_000):
    """A Dhan /charts/historical style response: parallel arrays."""
    return {
        "open": [100.0 + i for i in range(n)],
        "high": [105.0 + i for i in range(n)],
        "low": [99.0 + i for i in range(n)],
        "close": [102.0 + i for i in range(n)],
        "volume": [1000 * (i + 1) for i in range(n)],
        "timestamp": [start + 86400 * i for i in range(n)],
    }


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _DhanTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name)
        self.cache_dir = base / "cache_dhan"
        self.cache_dir.mkdir()
        self.config_path = base / "dhan_config.json"
        self._patches = [
            mock.patch.object(dhan, "CACHE_DIR", self.cache_dir),
            mock.patch.object(dhan, "CONFIG_PATH", self.config_path),
        ]
        for p in self._patches:
            p.start()
        self.addCleanup(self._tmp.cleanup)

    def _write_config(self, equity=None, token=None):
        data = {}
        if equity is not None:
            data["equity"] = equity
        if token is not None:
            data["access_token"] = token
        self.config_path.write_text(json.dumps(data), encoding="utf-8")


class TestConfig(_DhanTestBase):

    def test_not_configured_without_token(self):
        with mock.patch.dict("os.environ", {}, clear=False):
            import os

            os.environ.pop("DHAN_ACCESS_TOKEN", None)
            self.assertFalse(dhan.is_configured())

    def test_configured_via_env(self):
        with mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "jwt-123"}):
            self.assertTrue(dhan.is_configured())
            self.assertEqual(dhan.get_access_token(), "jwt-123")

    def test_configured_via_config_token(self):
        import os

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("DHAN_ACCESS_TOKEN", None)
            self._write_config(token="cfg-token")
            self.assertTrue(dhan.is_configured())
            self.assertEqual(dhan.get_access_token(), "cfg-token")

    def test_resolve_security_id(self):
        self._write_config(equity={"RELIANCE": "500285"})
        self.assertEqual(dhan.resolve_security_id("reliance"), "500285")
        self.assertEqual(dhan.resolve_security_id("TCS"), None)


class TestToDataFrame(_DhanTestBase):

    def test_parse_arrays(self):
        df = dhan._to_dataframe(_payload(n=3))
        self.assertEqual(list(df.columns), ["Open", "High", "Low", "Close", "Volume"])
        self.assertEqual(len(df), 3)
        self.assertEqual(float(df.iloc[0]["Open"]), 100.0)
        self.assertEqual(int(df.iloc[0]["Volume"]), 1000)
        self.assertIsInstance(df.index, pd.DatetimeIndex)
        self.assertEqual(str(df.index.tz), "Asia/Kolkata")

    def test_mismatched_lengths_raises(self):
        payload = _payload(n=3)
        payload["high"] = payload["high"][:2]
        with self.assertRaises(RuntimeError):
            dhan._to_dataframe(payload)

    def test_missing_keys_raises(self):
        with self.assertRaises(RuntimeError):
            dhan._to_dataframe({"open": [1]})

    def test_empty_rows_raises(self):
        payload = _payload(n=0)  # all empty lists
        with self.assertRaises(RuntimeError):
            dhan._to_dataframe(payload)


class TestPost(_DhanTestBase):

    def test_dhan_error_code_raises(self):
        resp = _FakeResponse(
            status_code=400,
            payload={"errorType": "Input_Exception",
                     "errorCode": "DH-905",
                     "errorMessage": "bad params"},
        )
        with mock.patch("requests.post", return_value=resp), \
             mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "t"}):
            with self.assertRaises(RuntimeError) as ctx:
                dhan._post("/charts/historical", {})
        self.assertIn("DH-905", str(ctx.exception))

    def test_network_exception_propagates(self):
        import requests

        with mock.patch("requests.post",
                        side_effect=requests.exceptions.ConnectionError("down")):
            with self.assertRaises(requests.exceptions.ConnectionError):
                dhan._post("/charts/historical", {})

    def test_success_returns_json(self):
        resp = _FakeResponse(200, payload=_payload(n=1))
        with mock.patch("requests.post", return_value=resp), \
             mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "t"}):
            data = dhan._post("/charts/historical", {})
        self.assertIn("open", data)


class TestCacheGate(_DhanTestBase):

    def test_roundtrip_and_fresh(self):
        df = dhan._to_dataframe(_payload(n=3))
        dhan._save_cache("RELIANCE", df)
        loaded = dhan._load_cache("RELIANCE", "1d", dhan.MAX_AGE_HOURS)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded), 3)

    def test_stale_returns_none(self):
        df = dhan._to_dataframe(_payload(n=3))
        dhan._save_cache("RELIANCE", df)
        path = dhan._cache_file("RELIANCE")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["fetched_at"] = time.time() - 17 * 3600  # older than 16h gate
        path.write_text(json.dumps(data), encoding="utf-8")
        self.assertIsNone(dhan._load_cache("RELIANCE", "1d", dhan.MAX_AGE_HOURS))

    def test_miss_returns_none(self):
        self.assertIsNone(dhan._load_cache("NOPE", "1d", dhan.MAX_AGE_HOURS))

    def test_get_history_uses_fresh_cache_without_http(self):
        self._write_config(equity={"RELIANCE": "500285"})
        df = dhan._to_dataframe(_payload(n=3))
        dhan._save_cache("RELIANCE", df)
        with mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "t"}), \
             mock.patch.object(dhan, "fetch_daily_candles",
                               side_effect=AssertionError("should not fetch")):
            out = dhan.get_price_history_dhan("RELIANCE", "5d")
        self.assertEqual(len(out), 3)

    def test_get_history_fetches_on_miss(self):
        self._write_config(equity={"RELIANCE": "500285"})
        with mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "t"}), \
             mock.patch.object(dhan, "fetch_daily_candles",
                               return_value=dhan._to_dataframe(_payload(n=4))) as fetch:
            out = dhan.get_price_history_dhan("RELIANCE", "3mo")
        fetch.assert_called_once()
        self.assertEqual(len(out), 4)
        # wrote a cache file
        self.assertTrue(dhan._cache_file("RELIANCE").is_file())

    def test_unconfigured_raises(self):
        import os

        with mock.patch.dict("os.environ", {}, clear=False):
            os.environ.pop("DHAN_ACCESS_TOKEN", None)
            with self.assertRaises(RuntimeError):
                dhan.get_price_history_dhan("RELIANCE")

    def test_unmapped_symbol_raises(self):
        with mock.patch.dict("os.environ", {"DHAN_ACCESS_TOKEN": "t"}):
            with mock.patch.object(dhan, "fetch_daily_candles",
                                   side_effect=AssertionError("no fetch")):
                with self.assertRaises(RuntimeError):
                    dhan.get_price_history_dhan("UNKNOWNXYZ")


class TestWiring(_DhanTestBase):

    def _nse_stub(self, sentinel):
        df = pd.DataFrame({"Close": [sentinel]})
        return df

    def test_prefers_dhan_when_configured(self):
        dhan_df = pd.DataFrame({"Open": [1.0], "source": ["dhan"]})
        with mock.patch.object(mu, "dhan_configured", return_value=True), \
             mock.patch.object(mu, "get_price_history_dhan",
                               return_value=dhan_df) as d, \
             mock.patch.object(mu, "_get_nse_price_history",
                               side_effect=AssertionError("NSE should be skipped")):
            out = mu.get_price_history("RELIANCE", "5d")
        d.assert_called_once()
        self.assertIs(out, dhan_df)

    def test_skips_dhan_when_not_configured(self):
        nse_df = pd.DataFrame({"Open": [2.0]})
        with mock.patch.object(mu, "dhan_configured", return_value=False), \
             mock.patch.object(mu, "get_price_history_dhan",
                               side_effect=AssertionError("dhan should be skipped")), \
             mock.patch.object(mu, "_get_nse_price_history", return_value=nse_df):
            out = mu.get_price_history("RELIANCE", "5d")
        self.assertIs(out, nse_df)

    def test_dhan_failure_falls_back_to_nse(self):
        nse_df = pd.DataFrame({"Open": [3.0]})
        with mock.patch.object(mu, "dhan_configured", return_value=True), \
             mock.patch.object(mu, "get_price_history_dhan",
                               side_effect=RuntimeError("dhan down")), \
             mock.patch.object(mu, "_get_nse_price_history", return_value=nse_df), \
             mock.patch("builtins.print"):
            out = mu.get_price_history("RELIANCE", "5d")
        self.assertIs(out, nse_df)


if __name__ == "__main__":
    unittest.main(verbosity=2)
