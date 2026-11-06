"""
Offline tests for start_nova.py (Nova launcher + preflight health check).

check_service/check_all are pure-ish (one urlopen call each), so these patch
urllib to simulate services being UP or DOWN and never touch the network, the
GUI, or any service. main()'s --check path is exercised without launching.

Run from the project root:
    .\\venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

from __future__ import annotations

import io
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import start_nova


class _FakeResp:
    def __init__(self, status=200):
        self.status = status

    def getcode(self):
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class TestCheckService(unittest.TestCase):

    def test_up_returns_true_and_status(self):
        with mock.patch(
            "urllib.request.urlopen", return_value=_FakeResp(200)
        ):
            ok, detail = start_nova.check_service("http://x")
        self.assertTrue(ok)
        self.assertIn("200", detail)

    def test_down_returns_false_and_never_raises(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=ConnectionRefusedError("refused")
        ):
            ok, detail = start_nova.check_service("http://x")
        self.assertFalse(ok)
        self.assertIn("ConnectionRefusedError", detail)

    def test_timeout_is_reported_not_raised(self):
        with mock.patch(
            "urllib.request.urlopen", side_effect=TimeoutError("slow")
        ):
            ok, detail = start_nova.check_service("http://x")
        self.assertFalse(ok)
        self.assertTrue(detail)


class TestCheckAll(unittest.TestCase):

    def test_all_services_probed(self):
        with mock.patch(
            "urllib.request.urlopen", return_value=_FakeResp(200)
        ):
            results = start_nova.check_all()
        self.assertEqual(len(results), len(start_nova.SERVICES))
        self.assertTrue(all(r["ok"] for r in results))

    def test_down_service_marked_not_ok(self):
        def fake(url, timeout=None):
            if "8080" in url:  # SearXNG down
                raise ConnectionRefusedError("refused")
            return _FakeResp(200)

        with mock.patch("urllib.request.urlopen", side_effect=fake):
            results = start_nova.check_all()
        by_name = {r["name"]: r for r in results}
        self.assertTrue(by_name["Ollama"]["ok"])
        self.assertFalse(by_name["SearXNG"]["ok"])


class TestPrintReport(unittest.TestCase):

    def test_report_returns_true_only_when_all_up(self):
        up = [{"name": "A", "url": "u", "why": "w", "ok": True, "detail": "HTTP 200"}]
        mixed = up + [
            {"name": "B", "url": "u", "why": "w", "ok": False, "detail": "err"}
        ]
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertTrue(start_nova.print_report(up))
            self.assertFalse(start_nova.print_report(mixed))
        self.assertIn("NOVA PREFLIGHT CHECK", buf.getvalue())
        self.assertIn("DOWN", buf.getvalue())


class TestMain(unittest.TestCase):

    def test_check_only_exit_code(self):
        with mock.patch.object(
            start_nova, "check_all", return_value=[
                {"name": "A", "url": "u", "why": "w", "ok": True, "detail": "d"},
            ]
        ), mock.patch.object(start_nova, "launch") as launcher:
            with redirect_stdout(io.StringIO()):
                rc_ok = start_nova.main(["--check"])
            launcher.assert_not_called()
        self.assertEqual(rc_ok, 0)

    def test_check_returns_1_when_a_service_is_down(self):
        with mock.patch.object(
            start_nova, "check_all", return_value=[
                {"name": "A", "url": "u", "why": "w", "ok": False, "detail": "d"},
            ]
        ), mock.patch.object(start_nova, "launch"):
            with redirect_stdout(io.StringIO()):
                rc = start_nova.main(["--check"])
        self.assertEqual(rc, 1)

    def _run(self, argv):
        with mock.patch.object(
            start_nova, "check_all", return_value=[
                {"name": "A", "url": "u", "why": "w", "ok": True, "detail": "d"},
            ]
        ), mock.patch.object(start_nova, "launch", return_value=1234) as launcher:
            with redirect_stdout(io.StringIO()):
                start_nova.main(argv)
        return launcher

    def test_launch_called_for_app_arg(self):
        self._run(["market"]).assert_called_once_with("market")

    def test_no_arg_opens_nova_desk(self):
        self._run([]).assert_called_once_with("desk")


if __name__ == "__main__":
    unittest.main(verbosity=2)
