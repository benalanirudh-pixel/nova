"""
Nova Terminal — unified Bloomberg-style main window.

Merges Nova Assistant and Market Lab into a single professional terminal.
All backend modules (brain, tools, market_lab_data, analysis engines) are
preserved and wired into their respective workspace pages.
"""

from __future__ import annotations

import time
import json
import traceback
import urllib.request
from datetime import datetime, timezone, timedelta

import psutil

from PySide6.QtCore import Qt, QTimer, Signal, QSize
from PySide6.QtGui import QFont, QColor, QIcon
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

TAB_DEFS = [
    ("MARKET",       "Market Overview"),
    ("STOCKS",       "Stock Analysis"),
    ("FLOWS",        "Institutional Flows"),
    ("LAB",          "Market Lab"),
    ("AI",           "Nova AI"),
]


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


class NovaTerminal(QMainWindow):
    """Unified Bloomberg-style terminal window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("NOVA TERMINAL")
        self.resize(1600, 960)
        self.setMinimumSize(1100, 700)

        self._active_tab = 0
        self._tab_buttons: list[QPushButton] = []
        self._ollama_ok = False
        self._searxng_ok = False

        self._apply_base_style()
        self._build_ui()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick)
        self._clock_timer.start(1000)

        QTimer.singleShot(200, self._check_services)
        QTimer.singleShot(300, self._load_initial_page)

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _apply_base_style(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: {BG};
            }}
            QScrollArea {{
                background: {BG};
                border: none;
            }}
            QScrollBar:vertical {{
                background: {BG};
                width: 8px;
                margin: 0;
            }}
            QScrollBar::handle:vertical {{
                background: {BORDER};
                min-height: 28px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {BORDER_BRIGHT};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar:horizontal {{
                background: {BG};
                height: 8px;
            }}
            QScrollBar::handle:horizontal {{
                background: {BORDER};
                min-width: 28px;
                border-radius: 4px;
            }}
            QScrollBar::handle:horizontal:hover {{
                background: {BORDER_BRIGHT};
            }}
            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0;
            }}
            QToolTip {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                padding: 4px 8px;
                font-family: {FONT_UI};
                font-size: 10pt;
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

        outer.addWidget(self._build_header())

        self._pages = QStackedWidget()
        self._pages.setStyleSheet(f"background: {BG};")
        outer.addWidget(self._pages, 1)

        outer.addWidget(self._build_statusbar())

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):
        header = QFrame()
        header.setFixedHeight(52)
        header.setStyleSheet(f"""
            QFrame {{
                background: {HEADER};
                border-bottom: 1px solid {BORDER_DIM};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(0)

        # --- Branding ---
        brand = QLabel("NOVA")
        brand.setFont(QFont(FONT_UI, 16, QFont.Weight.Bold))
        brand.setStyleSheet(f"color: {CYAN}; background: transparent; border: none;")
        layout.addWidget(brand)

        # Regime badge
        self._regime_badge = QLabel("—")
        self._regime_badge.setFont(QFont(FONT_MONO, 9, QFont.Weight.Bold))
        self._regime_badge.setStyleSheet(f"""
            color: {AMBER};
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 4px;
            padding: 2px 10px;
            margin-left: 12px;
        """)
        layout.addWidget(self._regime_badge)

        layout.addSpacing(32)

        # --- Tab bar ---
        tab_bar = QWidget()
        tab_bar.setStyleSheet("background: transparent; border: none;")
        tab_layout = QHBoxLayout(tab_bar)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(2)

        for idx, (label, tooltip) in enumerate(TAB_DEFS):
            btn = QPushButton(label)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setChecked(idx == 0)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(FONT_UI, 10, QFont.Weight.DemiBold))
            btn.setFixedHeight(36)
            btn.setStyleSheet(self._tab_qss())
            btn.clicked.connect(lambda checked, i=idx: self._switch_tab(i))
            tab_layout.addWidget(btn)
            self._tab_buttons.append(btn)

        layout.addWidget(tab_bar)
        layout.addStretch(1)

        # --- Search ---
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search symbol or command...")
        self._search.setFixedSize(220, 32)
        self._search.setFont(QFont(FONT_UI, 10))
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: {SURFACE};
                color: {TEXT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0 10px;
            }}
            QLineEdit:focus {{
                border-color: {CYAN};
            }}
        """)
        self._search.returnPressed.connect(self._on_search)
        layout.addWidget(self._search)

        layout.addSpacing(16)

        # --- Service indicators ---
        self._ollama_dot = self._make_dot("LLM", MUTED)
        self._searxng_dot = self._make_dot("WEB", MUTED)
        layout.addWidget(self._ollama_dot)
        layout.addSpacing(8)
        layout.addWidget(self._searxng_dot)

        layout.addSpacing(16)

        # --- Clock ---
        self._clock_label = QLabel("--:--")
        self._clock_label.setFont(QFont(FONT_MONO, 11, QFont.Weight.Bold))
        self._clock_label.setStyleSheet(
            f"color: {TEXT}; background: transparent; border: none;"
        )
        layout.addWidget(self._clock_label)

        return header

    def _tab_qss(self):
        return f"""
            QPushButton {{
                color: {SECONDARY};
                background: transparent;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 4px 14px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                color: {TEXT};
                background: rgba(255, 255, 255, 0.03);
            }}
            QPushButton:checked {{
                color: {CYAN};
                border-bottom: 2px solid {CYAN};
            }}
        """

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
    # Status bar
    # ------------------------------------------------------------------

    def _build_statusbar(self):
        bar = QFrame()
        bar.setFixedHeight(28)
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
    # Page management
    # ------------------------------------------------------------------

    def _load_initial_page(self):
        self._ensure_page(0)
        self._pages.setCurrentIndex(0)

    def _switch_tab(self, index):
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == index)
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
            border-radius: 4px;
            padding: 2px 10px;
            margin-left: 12px;
        """)

    def _on_scanner_age(self, text, color):
        self._scanner_age_label.setText(f"Scanner: {text}")
        self._scanner_age_label.setStyleSheet(
            f"color: {color}; background: transparent; border: none;"
        )

    def _on_report_loaded(self, report):
        """Push report to flows and market-lab pages if already created."""
        flows = self._pages.widget(2)
        if hasattr(flows, "set_report"):
            flows.set_report(report)
        lab = self._pages.widget(3)
        if hasattr(lab, "set_report"):
            lab.set_report(report)
        stocks = self._pages.widget(1)
        if hasattr(stocks, "set_market_report"):
            stocks.set_market_report(report)

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

    def get_current_report(self):
        page = self._pages.widget(0)
        if hasattr(page, "report"):
            return page.report
        return None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        for i in range(self._pages.count()):
            page = self._pages.widget(i)
            if hasattr(page, "shutdown"):
                page.shutdown()
        event.accept()
