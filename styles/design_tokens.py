"""
Nova unified design system tokens.
Single source of truth for colors, typography, spacing, z-index, and component
specs shared by both surfaces (Nova Assistant `ui.py` and Market Lab
`market_lab_ui.py`).

Tokens are intentionally pure Python constants with no external imports so the
theme tests can verify them without importing Qt or starting an event loop.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Palette (dark theme, financial terminal aesthetic)
# ---------------------------------------------------------------------------

# Shell / base surfaces
BG = "#050B10"            # app shell / window background
SURFACE = "#091620"       # elevated panel surface
SURFACE_ALT = "#0D1B26"   # slightly elevated (hovered row / active tab)
SIDEBAR = "#061019"       # navigation rail / left rail
HEADER = "#061019"        # top header bar

# Borders
BORDER = "#183746"        # default panel / input border
BORDER_BRIGHT = "#1B6170" # focused / active border
BORDER_DIM = "#0F202B"    # subtle divider

# Text
TEXT = "#F2F6FA"          # primary text
SECONDARY = "#91A9BE"     # secondary text / labels
MUTED = "#617A91"         # muted / placeholder text
MUTED2 = "#4A6572"        # very muted text

# Semantic colors
GREEN = "#00E6A0"         # positive / bullish / OK
RED = "#FF4058"           # negative / bearish / alert
AMBER = "#FFBD4A"         # warning / caution
BLUE = "#3198FF"          # info / neutral
CYAN = "#00D9F5"          # active / selected accent
PURPLE = "#B49AFF"        # accent / factor / highlight
INK = "#000000"           # text on light accent

# Freshness color coding (age-based)
FRESH_GREEN = "#00E6A0"   # data < 10 minutes old
FRESH_AMBER = "#FFBD4A"   # data 10min-2h old
FRESH_RED = "#FF4058"     # data 2h-12h old
FRESH_CRITICAL = "#FF1A3A"  # data > 12h old / stale

# Background tints (subtle fills behind status chips / badges)
BG_SUCCESS = "#003326"
BG_WARNING = "#2A1B00"
BG_ERROR = "#330A14"
BG_INFO = "#0A1B33"

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

FONT_UI = "Segoe UI"      # interface text
FONT_MONO = "Consolas"    # numbers, data, timestamps
FONT_SIZE_CAPTION = 8.5
FONT_SIZE_SMALL = 9.5
FONT_SIZE_REGULAR = 11
FONT_SIZE_MEDIUM = 13
FONT_SIZE_LARGE = 16
FONT_SIZE_XLARGE = 20

FONT_WEIGHT_REGULAR = 400
FONT_WEIGHT_MEDIUM = 500
FONT_WEIGHT_SEMIBOLD = 600
FONT_WEIGHT_BOLD = 700

# ---------------------------------------------------------------------------
# Spacing
# ---------------------------------------------------------------------------

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 24
SPACE_XXL = 32

BORDER_RADIUS_SM = 4
BORDER_RADIUS_MD = 8
BORDER_RADIUS_LG = 12
BORDER_RADIUS_PILL = 9999

LINE_HEIGHT_TIGHT = 1.2
LINE_HEIGHT_NORMAL = 1.4
LINE_HEIGHT_RELAXED = 1.6

# ---------------------------------------------------------------------------
# Component sizes
# ---------------------------------------------------------------------------

HEADER_HEIGHT = 56
SIDEBAR_WIDTH = 240
SIDEBAR_ITEM_HEIGHT = 40
NAV_ITEM_PADDING_H = 12
PANEL_PADDING = 16
PANEL_GAP = 12
CARD_HEIGHT_SM = 80
CARD_HEIGHT_MD = 120
CARD_HEIGHT_LG = 160

# Scrollbar
SCROLLBAR_WIDTH = 8
SCROLLBAR_HANDLE_MIN = 28

# ---------------------------------------------------------------------------
# Z-index / stacking (logical, applied via raise_ / setWindowFlags / etc.)
# ---------------------------------------------------------------------------

Z_BASE = 0
Z_PANEL = 10
Z_POPOVER = 50
Z_MODAL = 100
Z_TOOLTIP = 150
Z_NOTIFICATION = 200

# ---------------------------------------------------------------------------
# Animation / timing (ms)
# ---------------------------------------------------------------------------

DURATION_FAST = 150
DURATION_NORMAL = 250
DURATION_SLOW = 400

# ---------------------------------------------------------------------------
# Freshness thresholds (seconds)
# ---------------------------------------------------------------------------

FRESHNESS_GREEN_SECONDS = 600      # < 10 min
FRESHNESS_AMBER_SECONDS = 7200     # 10 min - 2 h
FRESHNESS_RED_SECONDS = 43200      # 2 h - 12 h
# > 12 h = critical

FRESHNESS_LABELS = {
    "green": "FRESH",
    "amber": "STALE",
    "red": "STALE",
    "critical": "CRITICAL",
}

# ---------------------------------------------------------------------------
# Guardrails (non-negotiable, shown on every output)
# ---------------------------------------------------------------------------

GUARDRAIL_TEXT = (
    "analysis-only, measured vs. interpreted kept separate, "
    "not a buy/sell signal, no broker/orders"
)
BUY_SELL_AUTHORIZED = False
TRADING_EXECUTION = False
SIGNAL_ELIGIBLE = False

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def freshness_level(seconds: int | None) -> str:
    """Return freshness tier name ('green' | 'amber' | 'red' | 'critical'
    | 'unknown') for a data age in seconds."""
    if seconds is None:
        return "unknown"
    if seconds < FRESHNESS_GREEN_SECONDS:
        return "green"
    if seconds < FRESHNESS_AMBER_SECONDS:
        return "amber"
    if seconds < FRESHNESS_RED_SECONDS:
        return "red"
    return "critical"

def freshness_color(level: str) -> str:
    """Return hex color for a freshness tier."""
    return {
        "green": FRESH_GREEN,
        "amber": FRESH_AMBER,
        "red": FRESH_RED,
        "critical": FRESH_CRITICAL,
        "unknown": MUTED,
    }.get(level, MUTED)

def freshness_label(level: str) -> str:
    """Return human-readable label for a freshness tier."""
    return FRESHNESS_LABELS.get(level, "UNKNOWN")

__all__ = [
    "BG", "SURFACE", "SURFACE_ALT", "SIDEBAR", "HEADER",
    "BORDER", "BORDER_BRIGHT", "BORDER_DIM",
    "TEXT", "SECONDARY", "MUTED", "MUTED2",
    "GREEN", "RED", "AMBER", "BLUE", "CYAN", "PURPLE",
    "INK",
    "FRESH_GREEN", "FRESH_AMBER", "FRESH_RED", "FRESH_CRITICAL",
    "BG_SUCCESS", "BG_WARNING", "BG_ERROR", "BG_INFO",
    "FONT_UI", "FONT_MONO",
    "FONT_SIZE_CAPTION", "FONT_SIZE_SMALL", "FONT_SIZE_REGULAR",
    "FONT_SIZE_MEDIUM", "FONT_SIZE_LARGE", "FONT_SIZE_XLARGE",
    "FONT_WEIGHT_REGULAR", "FONT_WEIGHT_MEDIUM", "FONT_WEIGHT_SEMIBOLD",
    "FONT_WEIGHT_BOLD",
    "SPACE_XS", "SPACE_SM", "SPACE_MD", "SPACE_LG", "SPACE_XL", "SPACE_XXL",
    "BORDER_RADIUS_SM", "BORDER_RADIUS_MD", "BORDER_RADIUS_LG",
    "BORDER_RADIUS_PILL",
    "LINE_HEIGHT_TIGHT", "LINE_HEIGHT_NORMAL", "LINE_HEIGHT_RELAXED",
    "HEADER_HEIGHT", "SIDEBAR_WIDTH", "SIDEBAR_ITEM_HEIGHT",
    "NAV_ITEM_PADDING_H", "PANEL_PADDING", "PANEL_GAP",
    "CARD_HEIGHT_SM", "CARD_HEIGHT_MD", "CARD_HEIGHT_LG",
    "SCROLLBAR_WIDTH", "SCROLLBAR_HANDLE_MIN",
    "Z_BASE", "Z_PANEL", "Z_POPOVER", "Z_MODAL", "Z_TOOLTIP",
    "Z_NOTIFICATION",
    "DURATION_FAST", "DURATION_NORMAL", "DURATION_SLOW",
    "FRESHNESS_GREEN_SECONDS", "FRESHNESS_AMBER_SECONDS",
    "FRESHNESS_RED_SECONDS",
    "FRESHNESS_LABELS",
    "GUARDRAIL_TEXT", "BUY_SELL_AUTHORIZED", "TRADING_EXECUTION",
    "SIGNAL_ELIGIBLE",
    "freshness_level", "freshness_color", "freshness_label",
]
