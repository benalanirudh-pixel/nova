"""
Lock-step test: styles/nova_theme.qss must carry the same design tokens as
the palette constants in market_lab_ui.py, and must stay loadable from the
project root regardless of the shell's working directory.

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

from market_lab import theme


class TestThemeFile(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.qss = theme.load_theme()

    def test_theme_file_exists_at_project_root(self):
        path = theme.theme_path()
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
        # Every colour used by the app shell must appear in the QSS so the file
        # and the code palette cannot drift apart.
        try:
            import market_lab_ui
        except ImportError:  # pragma: no cover - depends on PySide6
            self.skipTest("PySide6 not installed")
        tokens = {
            "BG": market_lab_ui.BG,
            "PANEL": market_lab_ui.PANEL,
            "SIDEBAR": market_lab_ui.SIDEBAR,
            "BORDER": market_lab_ui.BORDER,
            "TEXT": market_lab_ui.TEXT,
        }
        for name, value in tokens.items():
            self.assertIn(value, self.qss, f"token {name}={value} missing")

    def test_load_theme_resolves_outside_cwd(self):
        # Simulate launching from an unrelated working directory.
        import os
        import tempfile

        original = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                try:
                    loaded = theme.load_theme()
                finally:
                    # Windows cannot remove a directory that is the cwd, so
                    # leave it before the temp dir is cleaned up.
                    os.chdir(original)
        finally:
            os.chdir(original)
        self.assertTrue(loaded.strip())

    def test_missing_theme_file_returns_empty_string(self):
        self.assertEqual(theme.load_theme(path=Path("no_such_theme.qss")), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
