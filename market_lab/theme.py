"""
Nova Market Lab centralized theme loader.

The visual theme lives in `styles/nova_theme.qss` at the project root. This
module resolves that path from the file's own location (not the shell's
current working directory) so the same stylesheet loads no matter where Nova
is launched from.

Per-widget styling that must react to state (hover/pressed/active/disabled and
custom-painted charts) stays next to the widget in code; this file holds the
shared application shell theme only.
"""

from __future__ import annotations

from pathlib import Path

# market_lab/theme.py -> project root is one directory up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
THEME_PATH = PROJECT_ROOT / "styles" / "nova_theme.qss"


def theme_path() -> Path:
    """Absolute path to the theme stylesheet."""
    return THEME_PATH


def load_theme(path=None) -> str:
    """Return the stylesheet text, or an empty string if it is unavailable.

    Never raises: a missing or unreadable theme falls back to the hardcoded
    appearance of the individual widgets rather than breaking startup.
    """
    target = Path(path) if path is not None else THEME_PATH
    try:
        return target.read_text(encoding="utf-8-sig")
    except OSError:
        return ""
