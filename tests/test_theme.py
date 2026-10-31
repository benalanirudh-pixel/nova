"""
Lock-step test: styles/nova_theme.qss carries the same design tokens as
styles/design_tokens.py (the single source of truth for both UI surfaces),
and the palette constants in market_lab_ui.py match those tokens.
Also confirms the QSS loads from the project root regardless of cwd.

Offline: reads files only, no Qt application required.

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

from market_lab import theme as market_lab_theme
from styles import design_tokens as dt
import market_lab_ui


class TestThemeFile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qss = market_lab_theme.load_theme()

    def test_theme_file_exists_at_project_root(self):
        path = market_lab_theme.theme_path()
        self.assertTrue(path.is_file())
        self.assertEqual(path.parent.name, "styles")
        self.assertTrue(path.name.endswith(".qss"))

    def test_theme_loads_non_empty(self):
        self.assertTrue(self.qss.strip())

    def test_theme_carries_shell_selectors(self):
        for selector in (
            "QMainWindow",
            "QWidget",
            "QFrame#panel",
            "QFrame#sidebar",
            "QPlainTextEdit",
            "QScrollBar",
        ):
            self.assertIn(selector, self.qss)

    def test_theme_has_balanced_braces(self):
        self.assertEqual(self.qss.count("{"), self.qss.count("}"))

    def test_theme_tokens_match_python_palette(self):
        # Every colour used by market_lab_ui must appear in the QSS so the
        # file and the code palette cannot drift apart.
        try:
            import market_lab_ui
        except ImportError:  # pragma: no cover - depends on PySide6
            self.skipTest("PySide6 not installed")
        mlui_tokens = {
            "BG": market_lab_ui.BG,
            "PANEL": market_lab_ui.PANEL,
            "SIDEBAR": market_lab_ui.SIDEBAR,
            "BORDER": market_lab_ui.BORDER,
            "TEXT": market_lab_ui.TEXT,
        }
        for name, value in mlui_tokens.items():
            self.assertIn(value, self.qss, f"market_lab_ui token {name}={value} missing")

        # Every design token colour must also appear in the QSS so the
        # unified design system is consistently applied across both UIs.
        dt_tokens = {
            "BG": dt.BG,
            "SURFACE": dt.SURFACE,
            "SIDEBAR": dt.SIDEBAR,
            "BORDER": dt.BORDER,
            "TEXT": dt.TEXT,
            "GREEN": dt.GREEN,
            "RED": dt.RED,
            "AMBER": dt.AMBER,
            "CYAN": dt.CYAN,
            "PURPLE": dt.PURPLE,
            "MUTED": dt.MUTED,
        }
        for name, value in dt_tokens.items():
            self.assertIn(value, self.qss, f"design token {name}={value} missing")

    def test_load_theme_resolves_outside_cwd(self):
        # Simulate launching from an unrelated working directory.
        import os
        import tempfile

        original = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                try:
                    loaded = market_lab_theme.load_theme()
                finally:
                    # Windows cannot remove a directory that is the cwd, so
                    # leave it before the temp dir is cleaned up.
                    os.chdir(original)
        finally:
            os.chdir(original)
        self.assertTrue(loaded.strip())

    def test_missing_theme_file_returns_empty_string(self):
        self.assertEqual(market_lab_theme.load_theme(path=Path("no_such_theme.qss")), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
