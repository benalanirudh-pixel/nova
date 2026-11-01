"""
Nova Terminal — unified Bloomberg-style main window.

Professional trading analysis terminal with sidebar navigation, command bar,
live ticker strip, and dense information display. All backend modules
(brain, tools, market_lab_data, analysis engines) are preserved and wired
into their respective workspace pages.
"""

from __future__ import annotations

import time
import json
import traceback
import urllib.request
from datetime import datetime, timezone, timedelta

import psutil

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon, QPainter, QPen
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
    BG, SURFACE, SURFACE_ALT, SIDEBAR, HEADER,
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

# Sidebar navigation definitions: (key, icon_char, label, tooltip)
NAV_ITEMS = [
    ("market",  "M", "MARKET",  "Market Overview"),
    ("stocks",  "S", "STOCKS",  "Stock Analysis"),
    ("flows",   "F", "FLOWS",   "Institutional Flows"),
    ("lab",     "L", "LAB",     "Market Lab"),
    ("ai",      "A", "AI",      "Nova AI"),
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
# Sidebar nav button
# =====================================================================

class _NavButton(QPushButton):
    """Vertical sidebar navigation button with icon letter + label."""

    def __init__(self, icon_char, label, tooltip, parent=None):
        super().__init__(parent)
        self._icon_char = icon_char
        self._label = label
        self.setToolTip(tooltip)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(56, 52)
        self.setStyleSheet("background: transparent; border: none;")

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        is_active = self.isChecked()
        is_hover = self.underMouse()

        # Active indicator bar (left edge)
        if is_active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(CYAN))
            p.drawRoundedRect(0, 8, 3, self.height() - 16, 1, 1)

        # Background on hover
        if is_hover and not is_active:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(SURFACE_ALT))
            p.drawRoundedRect(4, 4, self.width() - 8, self.height() - 8, 4, 4)

        # Icon letter
        icon_color = QColor(CYAN) if is_active else QColor(MUTED)
        if is_hover and not is_active:
            icon_color = QColor(TEXT)
        p.setPen(icon_color)
        p.setFont(QFont(FONT_MONO, 14, QFont.Weight.Bold))
        p.drawText(0, 2, self.width(), 28, Qt.AlignmentFlag.AlignCenter, self._icon_char)

        # Label
        label_color = QColor(SECONDARY) if is_active else QColor(MUTED2)
        if is_hover and not is_active:
            label_color = QColor(SECONDARY)
        p.setPen(label_color)
        p.setFont(QFont(FONT_UI, 7, QFont.Weight.DemiBold))
        p.drawText(0, 28, self.width(), 18, Qt.AlignmentFlag.AlignCenter, self._label)

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
        self._name_lbl.setStyleSheet(f"color: {MUTED}; background: transparent;")
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
        self.setWindowTitle("NOVA TERMINAL")
        self.resize(1600, 960)
        self.setMinimumSize(1100, 700)

        self._active_tab = 0
        self._nav_buttons: list[_NavButton] = []
        self._ollama_ok = False
        self._searxng_ok = False

        self._apply_base_style()
        self._build_ui()
        self._load_initial_page()

        # Clocks and health checks
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

        # Command bar (top)
        outer.addWidget(self._build_command_bar())

        # Body: sidebar + content
        body = QWidget()
        body.setStyleSheet(f"background: {BG};")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        body_layout.addWidget(self._build_sidebar())

        # Content: ticker + pages
        content = QWidget()
        content.setStyleSheet(f"background: {BG};")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        content_layout.addWidget(self._build_ticker_strip())

        self._pages = QStackedWidget()
        self._pages.setStyleSheet(f"background: {BG};")
        content_layout.addWidget(self._pages, 1)

        body_layout.addWidget(content, 1)

        outer.addWidget(body, 1)
        outer.addWidget(self._build_statusbar())

    # ------------------------------------------------------------------
    # Command bar (top header)
    # ------------------------------------------------------------------

    def _build_command_bar(self):
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {HEADER};
                border-bottom: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(0)

        # Brand
        brand = QLabel("NOVA")
        brand.setFont(QFont(FONT_MONO, 14, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {CYAN}; background: transparent; border: none;")
        layout.addWidget(brand)

        sub = QLabel("TERMINAL")
        sub.setFont(QFont(FONT_MONO, 8, QFont.Weight.DemiBold))
        sub.setStyleSheet(
            f"color: {MUTED}; background: transparent; border: none;"
            " margin-left: 4px; padding-top: 4px;"
        )
        layout.addWidget(sub)

        layout.addSpacing(24)

        # Regime badge
        self._regime_badge = QLabel("—")
        self._regime_badge.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
        self._regime_badge.setStyleSheet(f"""
            color: {AMBER};
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 3px;
            padding: 2px 8px;
        """)
        layout.addWidget(self._regime_badge)

        layout.addSpacing(20)

        # Command search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search symbol or /ai command...")
        self._search.setFixedHeight(30)
        self._search.setMinimumWidth(280)
        self._search.setMaximumWidth(480)
        self._search.setFont(QFont(FONT_MONO, 10))
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 4px;
                padding: 0 12px;
                font-family: '{FONT_MONO}';
            }}
            QLineEdit:focus {{
                border-color: {CYAN};
                background: {SURFACE_ALT};
            }}
        """)
        self._search.returnPressed.connect(self._on_search)
        layout.addWidget(self._search, 1)

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
        sidebar.setFixedWidth(56)
        sidebar.setStyleSheet(f"""
            QFrame {{
                background: {SIDEBAR};
                border-right: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        for idx, (key, icon, label, tooltip) in enumerate(NAV_ITEMS):
            btn = _NavButton(icon, label, tooltip)
            btn.setChecked(idx == 0)
            btn.clicked.connect(lambda checked, i=idx: self._switch_tab(i))
            layout.addWidget(btn)
            self._nav_buttons.append(btn)

        layout.addStretch(1)

        # Version tag at bottom of sidebar
        ver = QLabel("v2")
        ver.setFont(QFont(FONT_MONO, 7))
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ver.setStyleSheet(f"color: {MUTED2}; background: transparent; border: none;")
        layout.addWidget(ver)

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

        self._ticker_nifty = _TickerItem("NIFTY")
        self._ticker_banknifty = _TickerItem("BANKNIFTY")
        self._ticker_vix = _TickerItem("VIX")

        # Separators between tickers
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
            f"color: {MUTED2}; background: transparent; padding-right: 12px;"
        )
        layout.addWidget(self._freshness_badge_ticker)

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
                from terminal.pages.institutional import InstitutionalPage
                return InstitutionalPage(self)
            elif index == 3:
                from terminal.pages.market_lab import MarketLabPage
                return MarketLabPage(self)
            elif index == 4:
                from terminal.pages.nova_ai import NovaAIPage
                return NovaAIPage(self)
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
        self._regime_badge.setStyleSheet(f"""
            color: {color};
            background: {SURFACE};
            border: 1px solid {color};
            border-radius: 3px;
            padding: 2px 8px;
        """)

    def _on_scanner_age(self, text, color):
        self._scanner_age_label.setText(f"Scanner: {text}")
        self._scanner_age_label.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    def _on_report_loaded(self, report):
        """Push report to flows/lab/stocks pages + update ticker strip."""
        flows = self._pages.widget(2)
        if hasattr(flows, "set_report"):
            flows.set_report(report)
        lab = self._pages.widget(3)
        if hasattr(lab, "set_report"):
            lab.set_report(report)
        stocks = self._pages.widget(1)
        if hasattr(stocks, "set_market_report"):
            stocks.set_market_report(report)

        # Update ticker strip from report data
        self._update_ticker(report)

    def _update_ticker(self, report):
        if not isinstance(report, dict):
            return

        # NIFTY: flat snapshot dict with price/change_percent
        snap = report.get("nifty_snapshot") or {}
        self._ticker_nifty.set_data(snap.get("price"), snap.get("change_percent"))

        # BANK NIFTY: price in volatility.bank_nifty, pct in bank_nifty_returns.1D
        bn = (report.get("volatility") or {}).get("bank_nifty") or {}
        bn_pct = (report.get("bank_nifty_returns") or {}).get("1D")
        self._ticker_banknifty.set_data(bn.get("price"), bn_pct)

        # VIX: in volatility.india_vix
        vix = (report.get("volatility") or {}).get("india_vix") or {}
        self._ticker_vix.set_data(vix.get("value"), vix.get("change_pct"))

        # Freshness
        age = report.get("scanner_age_seconds")
        if age is not None:
            level = freshness_level(int(age))
            color = freshness_color(level)
            label = freshness_label(level)
            self._freshness_badge_ticker.setText(f"DATA: {label}")
            self._freshness_badge_ticker.setStyleSheet(
                f"color: {color}; background: transparent; padding-right: 12px;"
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
        if upper.startswith("/AI "):
            self._switch_tab(4)
            page = self._pages.widget(4)
            if hasattr(page, "submit_query"):
                page.submit_query(query[4:])
        else:
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

        is_open = _nse_market_open(now)
        status = "OPEN" if is_open else "CLOSED"
        color = GREEN if is_open else RED
        self._market_status.setText(f"NSE: {status}")
        self._market_status.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
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
