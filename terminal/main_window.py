"""
Nova Terminal — unified professional trading analysis terminal.

Professional layout: wide sidebar nav, command bar, live ticker strip,
and dense single-screen pages. All backend modules preserved.
"""

from __future__ import annotations

import time
import json
import traceback
import urllib.request
from datetime import datetime, timezone, timedelta

import psutil

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SURFACE_RAISED, SIDEBAR, HEADER,
    BORDER, BORDER_BRIGHT, BORDER_DIM,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, BLUE, CYAN, PURPLE,
    BG_SUCCESS, BG_WARNING, BG_ERROR, BG_INFO,
    FONT_UI, FONT_MONO,
    FONT_SIZE_CAPTION, FONT_SIZE_SMALL, FONT_SIZE_REGULAR,
    FONT_SIZE_MEDIUM, FONT_SIZE_LARGE, FONT_SIZE_XLARGE,
    SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL, SPACE_XXL,
    BORDER_RADIUS_SM, BORDER_RADIUS_MD, BORDER_RADIUS_LG,
    HEADER_HEIGHT,
    GUARDRAIL_TEXT,
    freshness_level, freshness_color, freshness_label,
)

IST = timezone(timedelta(hours=5, minutes=30))

OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
SEARXNG_URL = "http://127.0.0.1:8080/"

# Sidebar navigation: (key, icon_char, label, tooltip, page_index)
NAV_ITEMS = [
    ("market",    "⌂", "Market",          "Market Dashboard",    0),
    ("stocks",    "☆", "Stock Analysis",  "Stock Analysis",      1),
    ("analysis",  "⇄", "Market Analysis", "Nifty Deep Dive",     2),
]

# Keep old TAB_DEFS for page creation compatibility
TAB_DEFS = [(item[2], item[3]) for item in NAV_ITEMS]


def _check_url(url, timeout=1.5):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Nova/1.0"})
        with urllib.request.urlopen(req, timeout=timeout):
            return True
    except Exception:
        return False


def _nse_market_open(now=None):
    ist = IST
    now = now or datetime.now(ist)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ist)
    else:
        now = now.astimezone(ist)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes < 15 * 60 + 30


# =====================================================================
# Sidebar nav button (wide, icon + text)
# =====================================================================

class _NavButton(QPushButton):
    """Wide sidebar navigation button: icon + label."""

    def __init__(self, icon_char, label, tooltip, parent=None):
        super().__init__(parent)
        self._icon_char = icon_char
        self._label = label
        self.setToolTip(tooltip)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(38)
        self.setMouseTracking(True)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        is_active = self.isChecked()
        is_hover = self.underMouse()

        # Active indicator bar (left edge)
        if is_active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(CYAN))
            p.drawRoundedRect(0, 6, 3, h - 12, 1, 1)
            p.setBrush(QColor(SURFACE_ALT))
            p.drawRoundedRect(4, 2, w - 8, h - 4, 6, 6)
        elif is_hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(SURFACE))
            p.drawRoundedRect(4, 2, w - 8, h - 4, 6, 6)

        # Icon
        icon_color = QColor(CYAN) if is_active else QColor(MUTED)
        if is_hover and not is_active:
            icon_color = QColor(TEXT)
        p.setPen(icon_color)
        p.setFont(QFont(FONT_UI, 13))
        p.drawText(14, 0, 24, h, Qt.AlignmentFlag.AlignCenter, self._icon_char)

        # Label
        label_color = QColor(TEXT) if is_active else QColor(SECONDARY)
        if is_hover and not is_active:
            label_color = QColor(TEXT)
        p.setPen(label_color)
        weight = QFont.Weight.DemiBold if is_active else QFont.Weight.Normal
        p.setFont(QFont(FONT_UI, 10, weight))
        p.drawText(44, 0, w - 52, h, Qt.AlignmentFlag.AlignVCenter, self._label)

        p.end()


# =====================================================================
# Ticker item widget
# =====================================================================

class _TickerItem(QWidget):
    """Single index ticker chip: NAME  PRICE  CHANGE%"""

    def __init__(self, name, parent=None):
        super().__init__(parent)
        self._name = name
        self.setFixedHeight(28)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 0, 12, 0)
        lay.setSpacing(6)

        self._name_lbl = QLabel(name)
        self._name_lbl.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._name_lbl.setStyleSheet(f"color: {SECONDARY}; background: transparent;")
        lay.addWidget(self._name_lbl)

        self._price_lbl = QLabel("—")
        self._price_lbl.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        self._price_lbl.setStyleSheet(f"color: {TEXT}; background: transparent;")
        lay.addWidget(self._price_lbl)

        self._change_lbl = QLabel("")
        self._change_lbl.setFont(QFont(FONT_MONO, 8))
        self._change_lbl.setStyleSheet(f"color: {MUTED}; background: transparent;")
        lay.addWidget(self._change_lbl)

    def set_data(self, price, change_pct):
        try:
            self._price_lbl.setText(f"{float(price):,.2f}")
        except (TypeError, ValueError):
            self._price_lbl.setText("—")
            return

        try:
            pct = float(change_pct)
            sign = "+" if pct >= 0 else ""
            color = GREEN if pct >= 0 else RED
            self._change_lbl.setText(f"{sign}{pct:.2f}%")
            self._change_lbl.setStyleSheet(f"color: {color}; background: transparent;")
            self._price_lbl.setStyleSheet(f"color: {color}; background: transparent;")
        except (TypeError, ValueError):
            pass


# =====================================================================
# Main terminal window
# =====================================================================

class NovaTerminal(QMainWindow):
    """Unified professional trading analysis terminal."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOVA MARKET LAB Pro")
        self.resize(1600, 960)
        self.setMinimumSize(1100, 700)

        self._active_tab = 0
        self._nav_buttons: list[_NavButton] = []
        self._ollama_ok = False
        self._searxng_ok = False

        self._apply_base_style()
        self._build_ui()
        self._load_initial_page()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

        self._service_timer = QTimer(self)
        self._service_timer.timeout.connect(self._check_services)
        self._service_timer.start(15_000)

        QTimer.singleShot(500, self._check_services)

    # ------------------------------------------------------------------
    # Base stylesheet
    # ------------------------------------------------------------------

    def _apply_base_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{ background: {BG}; }}
            QScrollBar:vertical {{
                background: {BG}; width: 8px; margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER}; min-height: 28px; border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {BORDER_BRIGHT}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{
                background: {BG}; height: 8px; margin: 0;
            }}
            QScrollBar::handle:horizontal {{
                background: {BORDER}; min-width: 28px; border-radius: 3px;
            }}
            QScrollBar::handle:horizontal:hover {{ background: {BORDER_BRIGHT}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 3px;
                padding: 5px 9px;
                font-size: 11px;
                selection-background-color: {CYAN};
                selection-color: #000;
            }}
            QLineEdit:focus {{ border-color: {CYAN}; }}
            QComboBox {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 3px;
                padding: 4px 8px 4px 8px;
                font-size: 11px;
                min-width: 80px;
            }}
            QComboBox:hover {{ border-color: {BORDER_BRIGHT}; }}
            QComboBox::drop-down {{ border: none; width: 16px; }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 5px solid {MUTED};
                margin-right: 6px;
            }}
            QComboBox QAbstractItemView {{
                background: {SURFACE_ALT};
                color: {TEXT};
                border: 1px solid {BORDER};
                selection-background-color: {BORDER};
                selection-color: {CYAN};
                outline: none;
                padding: 2px;
            }}
            QPushButton {{
                background: transparent;
                color: {SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 3px;
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
            QPushButton:pressed {{ background: {BORDER}; }}
            QPushButton:disabled {{ color: {MUTED2}; }}
            QPlainTextEdit, QTextEdit {{
                background: {SURFACE};
                color: {SECONDARY};
                border: 1px solid {BORDER};
                border-radius: 3px;
                padding: 6px;
                font-family: '{FONT_MONO}';
                font-size: 10px;
                selection-background-color: {CYAN};
            }}
            QSplitter::handle {{ background: {BORDER}; }}
            QToolTip {{
                background: {SURFACE_ALT};
                color: {TEXT};
                border: 1px solid {BORDER};
                padding: 4px 8px;
                font-size: 10px;
            }}
        """)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        root.setStyleSheet(f"background: {BG};")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_command_bar())

        # Ticker strip below command bar
        outer.addWidget(self._build_ticker_strip())

        # Body: sidebar + content
        body = QWidget()
        body.setStyleSheet(f"background: {BG};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        # Content: pages
        self._pages = QStackedWidget()
        self._pages.setStyleSheet(f"background: {BG};")
        body_layout.addWidget(self._pages, 1)

        outer.addWidget(body, 1)
        outer.addWidget(self._build_statusbar())

    # ------------------------------------------------------------------
    # Command bar (top header)
    # ------------------------------------------------------------------

    def _build_command_bar(self):
        bar = QFrame()
        bar.setFixedHeight(48)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {HEADER};
                border-bottom: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # Brand
        brand = QLabel("NOVA MARKET LAB")
        brand.setFont(QFont(FONT_MONO, 13, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {CYAN}; background: transparent; border: none;")
        layout.addWidget(brand)

        pro = QLabel("Pro")
        pro.setFont(QFont(FONT_UI, 11, QFont.Weight.DemiBold))
        pro.setStyleSheet(
            f"color: {GREEN}; background: transparent; border: none;"
            " margin-left: 4px; padding-top: 2px;"
        )
        layout.addWidget(pro)

        layout.addSpacing(8)

        sub = QLabel("Markets · Analysis · Research · Strategy")
        sub.setFont(QFont(FONT_UI, 8))
        sub.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
            " padding-top: 2px;"
        )
        layout.addWidget(sub)

        layout.addSpacing(32)

        # Top nav tabs
        for idx, (key, icon, label, tooltip, page_idx) in enumerate(NAV_ITEMS):
            btn = QPushButton(label)
            btn.setFixedHeight(32)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(FONT_UI, 9, QFont.Weight.DemiBold))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent;
                    color: {SECONDARY};
                    border: none;
                    padding: 0 12px;
                    border-radius: 6px;
                }}
                QPushButton:hover {{
                    background: {SURFACE};
                    color: {TEXT};
                }}
            """)
            btn.clicked.connect(lambda _, i=page_idx: self._switch_tab(i))
            layout.addWidget(btn)

        layout.addStretch(1)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Ctrl + K")
        self._search.setFixedHeight(30)
        self._search.setFixedWidth(160)
        self._search.setFont(QFont(FONT_MONO, 9))
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0 12px;
            }}
            QLineEdit:focus {{
                border-color: {CYAN};
                background: {SURFACE_ALT};
            }}
        """)
        self._search.returnPressed.connect(self._on_search)
        layout.addWidget(self._search)

        layout.addSpacing(16)

        # Service dots
        self._ollama_dot = self._make_dot("LLM", MUTED)
        self._searxng_dot = self._make_dot("WEB", MUTED)
        layout.addWidget(self._ollama_dot)
        layout.addSpacing(8)
        layout.addWidget(self._searxng_dot)

        layout.addSpacing(16)

        # Clock
        self._clock_label = QLabel("--:--")
        self._clock_label.setFont(QFont(FONT_MONO, 13, QFont.Weight.Bold))
        self._clock_label.setStyleSheet(
            f"color: {TEXT}; background: transparent; border: none;"
        )
        layout.addWidget(self._clock_label)

        return bar

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------

    def _build_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(170)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {SIDEBAR};
                border-right: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        for idx, (key, icon, label, tooltip, page_idx) in enumerate(NAV_ITEMS):
            btn = _NavButton(icon, label, tooltip)
            btn.setChecked(idx == 0)
            btn.clicked.connect(lambda checked, i=page_idx: self._switch_tab(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addSpacing(16)

        # Workspaces section
        ws_header = QHBoxLayout()
        ws_label = QLabel("WORKSPACES")
        ws_label.setFont(QFont(FONT_UI, 7, QFont.Weight.Bold))
        ws_label.setStyleSheet(f"color: {MUTED2}; background: transparent; border: none; padding-left: 14px;")
        ws_header.addWidget(ws_label)
        ws_header.addStretch(1)
        ws_plus = QLabel("+")
        ws_plus.setFont(QFont(FONT_UI, 11))
        ws_plus.setStyleSheet(f"color: {MUTED}; background: transparent; border: none; padding-right: 14px;")
        ws_header.addWidget(ws_plus)
        layout.addLayout(ws_header)

        layout.addSpacing(4)

        # Workspace items (cosmetic)
        for name, active in [("Market Lab", True), ("Options Desk", False),
                              ("Swing Lab", False), ("Portfolio", False)]:
            ws = QLabel(f"  {'●' if active else '○'}  {name}")
            ws.setFont(QFont(FONT_UI, 9))
            color = GREEN if active else MUTED
            ws.setStyleSheet(f"color: {color}; background: transparent; border: none; padding: 3px 14px;")
            layout.addWidget(ws)

        layout.addStretch(1)

        # Data Pipeline status
        pipe_frame = QFrame()
        pipe_frame.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border: 1px solid {BORDER_DIM};
                border-radius: 6px;
                margin: 4px 8px;
            }}
        """)
        pipe_lay = QVBoxLayout(pipe_frame)
        pipe_lay.setContentsMargins(10, 8, 10, 8)
        pipe_lay.setSpacing(2)

        pipe_title = QLabel("Data Pipeline")
        pipe_title.setFont(QFont(FONT_UI, 9, QFont.Weight.DemiBold))
        pipe_title.setStyleSheet(f"color: {TEXT}; background: transparent; border: none;")
        pipe_lay.addWidget(pipe_title)

        self._pipeline_status = QLabel("● Connected")
        self._pipeline_status.setFont(QFont(FONT_UI, 8))
        self._pipeline_status.setStyleSheet(f"color: {GREEN}; background: transparent; border: none;")
        pipe_lay.addWidget(self._pipeline_status)

        self._pipeline_sync = QLabel("↻ Last Sync: --:--:--")
        self._pipeline_sync.setFont(QFont(FONT_MONO, 7))
        self._pipeline_sync.setStyleSheet(f"color: {MUTED}; background: transparent; border: none;")
        pipe_lay.addWidget(self._pipeline_sync)

        layout.addWidget(pipe_frame)

        return sidebar

    # ------------------------------------------------------------------
    # Ticker strip
    # ------------------------------------------------------------------

    def _build_ticker_strip(self):
        strip = QFrame()
        strip.setFixedHeight(30)
        strip.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border-bottom: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QHBoxLayout(strip)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # LIVE badge
        live = QLabel(" ● LIVE ")
        live.setFont(QFont(FONT_MONO, 7, QFont.Weight.Bold))
        live.setStyleSheet(f"""
            color: {TEXT};
            background: {RED};
            border-radius: 3px;
            padding: 1px 6px;
            margin: 4px 8px 4px 12px;
        """)
        layout.addWidget(live)

        self._ticker_nifty = _TickerItem("NIFTY 50")
        self._ticker_banknifty = _TickerItem("BANKNIFTY")
        self._ticker_vix = _TickerItem("INDIA VIX")

        layout.addWidget(self._ticker_nifty)
        layout.addWidget(self._ticker_sep())
        layout.addWidget(self._ticker_banknifty)
        layout.addWidget(self._ticker_sep())
        layout.addWidget(self._ticker_vix)
        layout.addStretch(1)

        # Freshness badge
        self._freshness_badge_ticker = QLabel("")
        self._freshness_badge_ticker.setFont(QFont(FONT_MONO, 7, QFont.Weight.Bold))
        self._freshness_badge_ticker.setStyleSheet(
            f"color: {MUTED2}; background: transparent; padding-right: 8px;"
        )
        layout.addWidget(self._freshness_badge_ticker)

        # Date label
        self._date_label = QLabel("")
        self._date_label.setFont(QFont(FONT_MONO, 8))
        self._date_label.setStyleSheet(f"color: {MUTED}; background: transparent; padding-right: 12px;")
        layout.addWidget(self._date_label)

        return strip

    def _ticker_sep(self):
        sep = QFrame()
        sep.setFixedSize(1, 16)
        sep.setStyleSheet(f"background: {BORDER_DIM};")
        return sep

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_statusbar(self):
        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {HEADER};
                border-top: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(0)

        # Market status
        self._market_status = QLabel("NSE: —")
        self._market_status.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._market_status.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._market_status)

        self._add_separator(layout)

        # Regime badge
        self._regime_badge = QLabel("—")
        self._regime_badge.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._regime_badge.setStyleSheet(
            f"color: {AMBER}; background: transparent; border: none;"
        )
        layout.addWidget(self._regime_badge)

        self._add_separator(layout)

        # Scanner age
        self._scanner_age_label = QLabel("Scanner: —")
        self._scanner_age_label.setFont(QFont(FONT_MONO, 8))
        self._scanner_age_label.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._scanner_age_label)

        layout.addStretch(1)

        # Guardrail
        guardrail = QLabel(GUARDRAIL_TEXT.upper())
        guardrail.setFont(QFont(FONT_MONO, 7))
        guardrail.setStyleSheet(
            f"color: {MUTED2}; background: transparent; border: none;"
        )
        layout.addWidget(guardrail)

        layout.addStretch(1)

        # System metrics
        self._cpu_label = QLabel("CPU —")
        self._cpu_label.setFont(QFont(FONT_MONO, 8))
        self._cpu_label.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._cpu_label)

        self._add_separator(layout)

        self._ram_label = QLabel("RAM —")
        self._ram_label.setFont(QFont(FONT_MONO, 8))
        self._ram_label.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
        )
        layout.addWidget(self._ram_label)

        self._add_separator(layout)

        # IST clock
        self._ist_clock = QLabel("IST --:--:--")
        self._ist_clock.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._ist_clock.setStyleSheet(
            f"color: {SECONDARY}; background: transparent; border: none;"
        )
        layout.addWidget(self._ist_clock)

        return bar

    def _add_separator(self, layout):
        sep = QLabel("|")
        sep.setFont(QFont(FONT_MONO, 8))
        sep.setStyleSheet(
            f"color: {BORDER}; background: transparent; border: none;"
            " padding: 0 6px;"
        )
        layout.addWidget(sep)

    # ------------------------------------------------------------------
    # Service indicator dots
    # ------------------------------------------------------------------

    def _make_dot(self, label, color):
        w = QWidget()
        w.setStyleSheet("background: transparent; border: none;")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(
            f"background: {color}; border-radius: 4px; border: none;"
        )
        lay.addWidget(dot)
        lbl = QLabel(label)
        lbl.setFont(QFont(FONT_MONO, 8))
        lbl.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
        )
        lay.addWidget(lbl)
        w._dot = dot
        w._lbl = lbl
        return w

    def _update_dot(self, widget, ok):
        color = GREEN if ok else RED
        widget._dot.setStyleSheet(
            f"background: {color}; border-radius: 4px; border: none;"
        )

    # ------------------------------------------------------------------
    # Page management
    # ------------------------------------------------------------------

    def _load_initial_page(self):
        self._ensure_page(0)
        self._pages.setCurrentIndex(0)

    def _switch_tab(self, index):
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == index)
            btn.update()
        self._active_tab = index
        self._ensure_page(index)
        self._pages.setCurrentIndex(index)

    def _ensure_page(self, index):
        if index < self._pages.count():
            return
        while self._pages.count() <= index:
            placeholder = QLabel(f"Loading {TAB_DEFS[self._pages.count()][1]}...")
            placeholder.setFont(QFont(FONT_UI, 14))
            placeholder.setStyleSheet(
                f"color: {MUTED}; background: {BG}; border: none;"
            )
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._pages.addWidget(placeholder)

        current_widget = self._pages.widget(index)
        if isinstance(current_widget, QLabel):
            page = self._create_page(index)
            if page is not None:
                self._pages.removeWidget(current_widget)
                current_widget.deleteLater()
                self._pages.insertWidget(index, page)
                self._pages.setCurrentIndex(index)

    def _create_page(self, index):
        try:
            if index == 0:
                from terminal.pages.market_overview import MarketOverviewPage
                page = MarketOverviewPage(self)
                page.regime_changed.connect(self._on_regime_changed)
                page.scanner_age_changed.connect(self._on_scanner_age)
                page.report_loaded.connect(self._on_report_loaded)
                return page
            elif index == 1:
                from terminal.pages.stock_analysis import StockAnalysisPage
                return StockAnalysisPage(self)
            elif index == 2:
                from terminal.pages.market_analysis import MarketAnalysisPage
                page = MarketAnalysisPage(self)
                page.regime_changed.connect(self._on_regime_changed)
                return page
        except Exception:
            traceback.print_exc()
            err = QLabel(f"Failed to load {TAB_DEFS[index][1]}")
            err.setFont(QFont(FONT_UI, 12))
            err.setStyleSheet(f"color: {RED}; background: {BG}; border: none;")
            err.setAlignment(Qt.AlignmentFlag.AlignCenter)
            return err
        return None

    # ------------------------------------------------------------------
    # Signals from pages
    # ------------------------------------------------------------------

    def _on_regime_changed(self, regime_text, color):
        self._regime_badge.setText(regime_text)
        self._regime_badge.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    def _on_scanner_age(self, text, color):
        self._scanner_age_label.setText(f"Scanner: {text}")
        self._scanner_age_label.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    def _on_report_loaded(self, report):
        """Push report to analysis/stocks pages + update ticker strip."""
        analysis = self._pages.widget(2)
        if hasattr(analysis, "set_report"):
            analysis.set_report(report)
        stocks = self._pages.widget(1)
        if hasattr(stocks, "set_market_report"):
            stocks.set_market_report(report)

        self._update_ticker(report)

    def _update_ticker(self, report):
        if not isinstance(report, dict):
            return

        snap = report.get("nifty_snapshot") or {}
        self._ticker_nifty.set_data(snap.get("price"), snap.get("change_percent"))

        bn = (report.get("volatility") or {}).get("bank_nifty") or {}
        bn_pct = (report.get("bank_nifty_returns") or {}).get("1D")
        self._ticker_banknifty.set_data(bn.get("price"), bn_pct)

        vix = (report.get("volatility") or {}).get("india_vix") or {}
        self._ticker_vix.set_data(vix.get("value"), vix.get("change_percent"))

        # Freshness
        age = report.get("scanner_age_seconds")
        if age is not None:
            level = freshness_level(int(age))
            color = freshness_color(level)
            label = freshness_label(level)
            self._freshness_badge_ticker.setText(f"DATA: {label}")
            self._freshness_badge_ticker.setStyleSheet(
                f"color: {color}; background: transparent; padding-right: 8px;"
            )

        # Update pipeline sync time
        self._pipeline_sync.setText(
            f"↻ Last Sync: {datetime.now(IST).strftime('%H:%M:%S')}"
        )

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def _on_search(self):
        query = self._search.text().strip()
        if not query:
            return
        self._search.clear()
        upper = query.upper()
        self._switch_tab(1)
        page = self._pages.widget(1)
        if hasattr(page, "set_symbol"):
            page.set_symbol(upper)

    # ------------------------------------------------------------------
    # Timers
    # ------------------------------------------------------------------

    def _tick(self):
        now = datetime.now(IST)
        self._clock_label.setText(now.strftime("%H:%M"))
        self._ist_clock.setText(f"IST {now.strftime('%H:%M:%S')}")

        # Date in ticker
        self._date_label.setText(now.strftime("%a, %b %d, %Y  %H:%M:%S IST"))

        is_open = _nse_market_open(now)
        status = "OPEN" if is_open else "CLOSED"
        color = GREEN if is_open else RED
        self._market_status.setText(f"NSE: {status}")
        self._market_status.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

        # Pipeline status
        services_ok = self._ollama_ok or self._searxng_ok
        self._pipeline_status.setText(
            f"● {'Connected' if services_ok else 'Offline'}"
        )
        self._pipeline_status.setStyleSheet(
            f"color: {GREEN if services_ok else RED}; background: transparent; border: none;"
        )

        try:
            cpu = psutil.cpu_percent(interval=0)
            self._cpu_label.setText(f"CPU {cpu:.0f}%")
            ram = psutil.virtual_memory().percent
            self._ram_label.setText(f"RAM {ram:.0f}%")
        except Exception:
            pass

    def _check_services(self):
        self._ollama_ok = _check_url(OLLAMA_URL)
        self._searxng_ok = _check_url(SEARXNG_URL)
        self._update_dot(self._ollama_dot, self._ollama_ok)
        self._update_dot(self._searxng_dot, self._searxng_ok)

    # ------------------------------------------------------------------
    # Accessors for pages
    # ------------------------------------------------------------------

    @property
    def ollama_ok(self):
        return self._ollama_ok

    @property
    def searxng_ok(self):
        return self._searxng_ok
