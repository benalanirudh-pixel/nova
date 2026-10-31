"""Shared visual helpers for Nova Terminal pages."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, BORDER, BORDER_BRIGHT,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, CYAN,
    FONT_UI, FONT_MONO,
)

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

def lbl(text, size=10, color=TEXT, bold=False, mono=False, wrap=False) -> QLabel:
    w = QLabel(str(text) if text is not None else "—")
    family = FONT_MONO if mono else FONT_UI
    weight = "600" if bold else "400"
    w.setStyleSheet(
        f"color:{color}; font-size:{size}px; font-weight:{weight};"
        f" font-family:'{family}'; background:transparent; border:none;"
    )
    if wrap:
        w.setWordWrap(True)
    return w


def sign_color(v) -> str:
    try:
        return GREEN if float(v) >= 0 else RED
    except (TypeError, ValueError):
        return MUTED


# ---------------------------------------------------------------------------
# Buttons
# ---------------------------------------------------------------------------

_BTN_BASE = f"""
    QPushButton {{
        background: transparent;
        color: {SECONDARY};
        border: 1px solid {BORDER};
        border-radius: 3px;
        font-family: '{FONT_UI}';
        font-size: 10px;
        font-weight: 600;
        padding: 4px 12px;
        letter-spacing: 0.5px;
    }}
    QPushButton:hover {{
        background: {SURFACE_ALT};
        color: {TEXT};
        border-color: {BORDER_BRIGHT};
    }}
    QPushButton:pressed {{
        background: {BORDER};
    }}
    QPushButton:disabled {{
        color: {MUTED2};
        border-color: {BORDER};
    }}
"""

_BTN_PRIMARY = f"""
    QPushButton {{
        background: {CYAN};
        color: #000;
        border: none;
        border-radius: 3px;
        font-family: '{FONT_UI}';
        font-size: 10px;
        font-weight: 700;
        padding: 5px 16px;
        letter-spacing: 0.8px;
    }}
    QPushButton:hover {{
        background: #33E8FF;
    }}
    QPushButton:pressed {{
        background: #00B8D4;
    }}
    QPushButton:disabled {{
        background: {MUTED2};
        color: #000;
    }}
"""

_BTN_DANGER = f"""
    QPushButton {{
        background: transparent;
        color: {RED};
        border: 1px solid {RED};
        border-radius: 3px;
        font-family: '{FONT_UI}';
        font-size: 10px;
        font-weight: 600;
        padding: 4px 12px;
    }}
    QPushButton:hover {{
        background: rgba(255,64,88,0.15);
    }}
"""


def btn(text: str, primary=False, danger=False) -> QPushButton:
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        b.setStyleSheet(_BTN_PRIMARY)
    elif danger:
        b.setStyleSheet(_BTN_DANGER)
    else:
        b.setStyleSheet(_BTN_BASE)
    return b


# ---------------------------------------------------------------------------
# Panels / cards
# ---------------------------------------------------------------------------

_PANEL_QSS = f"""
    QFrame#novaCard {{
        background: {SURFACE};
        border: 1px solid {BORDER};
        border-radius: 6px;
    }}
"""

_PANEL_ACCENT_QSS = f"""
    QFrame#novaCardAccent {{
        background: {SURFACE};
        border: 1px solid {CYAN};
        border-radius: 6px;
    }}
"""


def card(title: str = "", accent=False) -> tuple[QFrame, QVBoxLayout]:
    """Bordered panel card. Returns (frame, inner_layout)."""
    frame = QFrame()
    frame.setObjectName("novaCardAccent" if accent else "novaCard")
    frame.setStyleSheet(_PANEL_ACCENT_QSS if accent else _PANEL_QSS)
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(12, 10, 12, 12)
    lay.setSpacing(6)
    if title:
        lay.addWidget(lbl(title.upper(), 8, MUTED, bold=True))
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background:{BORDER}; border:none;")
        lay.addWidget(sep)
    return frame, lay


def kv_row(key: str, value, color=SECONDARY) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(lbl(key, 9, MUTED))
    row.addStretch()
    row.addWidget(lbl(str(value) if value is not None else "—", 9, color, mono=True))
    return row


# ---------------------------------------------------------------------------
# Input styling QSS (apply to individual widgets)
# ---------------------------------------------------------------------------

INPUT_QSS = f"""
    QLineEdit {{
        background: {BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 3px;
        padding: 5px 9px;
        font-family: '{FONT_UI}';
        font-size: 11px;
        selection-background-color: {CYAN};
        selection-color: #000;
    }}
    QLineEdit:focus {{
        border-color: {CYAN};
    }}
    QLineEdit::placeholder {{
        color: {MUTED2};
    }}
"""

COMBO_QSS = f"""
    QComboBox {{
        background: {BG};
        color: {TEXT};
        border: 1px solid {BORDER};
        border-radius: 3px;
        padding: 4px 8px;
        font-family: '{FONT_UI}';
        font-size: 11px;
        min-width: 90px;
    }}
    QComboBox:hover {{
        border-color: {BORDER_BRIGHT};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 18px;
    }}
    QComboBox QAbstractItemView {{
        background: {SURFACE};
        color: {TEXT};
        border: 1px solid {BORDER};
        selection-background-color: {SURFACE_ALT};
        selection-color: {CYAN};
        outline: none;
    }}
"""

TOOLBAR_QSS = f"""
    QFrame#Toolbar {{
        background: {SURFACE};
        border-bottom: 1px solid {BORDER};
    }}
"""
