"""
Nova Market Lab unified theme loader.

Loads the QSS stylesheet from ``styles/nova_theme.qss`` at the project root and
exposes the shared design tokens from ``styles/design_tokens.py`` so both UI
surfaces (Market Lab and Nova Assistant) use a single source of truth for
colors, typography, spacing, and component specs.

Never raises: a missing stylesheet falls back to empty string, and individual
widgets keep their hardcoded appearance as a fallback.
"""

from __future__ import annotations

from pathlib import Path

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SIDEBAR, HEADER,
    BORDER, BORDER_BRIGHT, BORDER_DIM,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, BLUE, CYAN, PURPLE, INK,
    FRESH_GREEN, FRESH_AMBER, FRESH_RED, FRESH_CRITICAL,
    BG_SUCCESS, BG_WARNING, BG_ERROR, BG_INFO,
    FONT_UI, FONT_MONO,
    FONT_SIZE_CAPTION, FONT_SIZE_SMALL, FONT_SIZE_REGULAR,
    FONT_SIZE_MEDIUM, FONT_SIZE_LARGE, FONT_SIZE_XLARGE,
    SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL, SPACE_XXL,
    BORDER_RADIUS_SM, BORDER_RADIUS_MD, BORDER_RADIUS_LG, BORDER_RADIUS_PILL,
    HEADER_HEIGHT, SIDEBAR_WIDTH, SIDEBAR_ITEM_HEIGHT,
    GUARDRAIL_TEXT, BUY_SELL_AUTHORIZED, TRADING_EXECUTION, SIGNAL_ELIGIBLE,
    freshness_level, freshness_color, freshness_label,
)

# market_lab/theme.py -> project root is one directory up.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
THEME_PATH = PROJECT_ROOT / "styles" / "nova_theme.qss"


def theme_path() -> Path:
    """Absolute path to the unified stylesheet."""
    return THEME_PATH


def load_theme(path=None) -> str:
    """Return the unified stylesheet text, or an empty string if unavailable.

    Never raises: a missing or unreadable theme falls back to empty string so
    widgets keep their hardcoded appearance rather than breaking startup.
    """
    target = Path(path) if path is not None else THEME_PATH
    try:
        return target.read_text(encoding="utf-8-sig")
    except OSError:
        return ""


def apply_theme(app) -> None:
    """Apply the unified stylesheet to a QApplication instance.

    Safe to call multiple times; re-applying replaces the stylesheet.
    """
    from PySide6.QtWidgets import QApplication

    qss = load_theme()
    if qss:
        app.setStyleSheet(qss)


__all__ = [
    # Tokens
    "BG", "SURFACE", "SURFACE_ALT", "SIDEBAR", "HEADER",
    "BORDER", "BORDER_BRIGHT", "BORDER_DIM",
    "TEXT", "SECONDARY", "MUTED", "MUTED2",
    "GREEN", "RED", "AMBER", "BLUE", "CYAN", "PURPLE", "INK",
    "FRESH_GREEN", "FRESH_AMBER", "FRESH_RED", "FRESH_CRITICAL",
    "BG_SUCCESS", "BG_WARNING", "BG_ERROR", "BG_INFO",
    "FONT_UI", "FONT_MONO",
    "FONT_SIZE_CAPTION", "FONT_SIZE_SMALL", "FONT_SIZE_REGULAR",
    "FONT_SIZE_MEDIUM", "FONT_SIZE_LARGE", "FONT_SIZE_XLARGE",
    "SPACE_XS", "SPACE_SM", "SPACE_MD", "SPACE_LG", "SPACE_XL", "SPACE_XXL",
    "BORDER_RADIUS_SM", "BORDER_RADIUS_MD", "BORDER_RADIUS_LG",
    "BORDER_RADIUS_PILL",
    "HEADER_HEIGHT", "SIDEBAR_WIDTH", "SIDEBAR_ITEM_HEIGHT",
    "GUARDRAIL_TEXT", "BUY_SELL_AUTHORIZED", "TRADING_EXECUTION",
    "SIGNAL_ELIGIBLE",
    "freshness_level", "freshness_color", "freshness_label",
    # Theme functions
    "theme_path", "load_theme", "apply_theme",
]
