"""Terminal Stock Analysis page — professional trading-terminal layout.

Three-column top (stock info + candlestick chart + momentum gauge),
technicals grid, AI report panel, and data-quality footer.
All data from stock_adapter / report_parser — nothing fabricated.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QFrame, QScrollArea, QSizePolicy, QPlainTextEdit,
    QPushButton,
)

from market_lab import stock_adapter, report_parser
from market_lab import widgets as W
from market_lab.market_lab_brain import analyze_stock_report
from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SURFACE_INSET,
    CYAN, GREEN, RED, AMBER, PURPLE, MUTED, MUTED2, TEXT,
    BORDER, BORDER_DIM, SECONDARY,
    FONT_UI, FONT_MONO, GUARDRAIL_TEXT,
)

N_A = "N/A"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_price(v):
    if v is None:
        return N_A
    try:
        return f"₹{float(v):,.2f}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_pct(v):
    if v is None:
        return N_A
    try:
        sign = "+" if float(v) >= 0 else ""
        return f"{sign}{float(v):.2f}%"
    except (TypeError, ValueError):
        return str(v)


def _fmt_num(v, decimals=2):
    if v is None:
        return N_A
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def _sign_color(v):
    try:
        return GREEN if float(v) >= 0 else RED
    except (TypeError, ValueError):
        return MUTED


def _lbl(text, size=10, color=TEXT, bold=False, mono=False):
    lbl = QLabel(str(text))
    weight = "bold" if bold else "normal"
    family = FONT_MONO if mono else FONT_UI
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}px; font-weight:{weight};"
        f" font-family:'{family}'; background:transparent;"
    )
    return lbl


def _kv_row(key, value, color=SECONDARY):
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_lbl(key, 9, MUTED))
    row.addStretch(1)
    row.addWidget(_lbl(str(value) if value is not None else N_A, 9, color, mono=True))
    return row


def _pill(text, color=CYAN, bg=SURFACE_ALT):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color:{color}; font-size:9px; font-weight:bold;"
        f" background:{bg}; border:1px solid {color}; border-radius:9px;"
        f" padding:2px 10px; font-family:'{FONT_UI}';"
    )
    return lbl


def _divider():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{BORDER_DIM};")
    return line


# ---------------------------------------------------------------------------
# Momentum gauge — QPainter arc widget
# ---------------------------------------------------------------------------

class _MomentumGauge(QWidget):
    """Arc gauge 0-100 with color gradient and center readout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(180, 180)
        self._value = None
        self._label = "MOMENTUM"

    def set_value(self, value, label=None):
        try:
            self._value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self._value = None
        if label:
            self._label = str(label)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        radius = min(r.width(), r.height()) / 2 - 12
        arc_width = 10
        start_angle = 225
        total_sweep = -270

        # background arc
        painter.setPen(QPen(QColor(BORDER_DIM), arc_width, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap))
        arc_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)
        painter.drawArc(arc_rect, int(start_angle * 16), int(total_sweep * 16))

        if self._value is not None:
            frac = self._value / 100.0
            sweep = total_sweep * frac
            if frac < 0.3:
                color = QColor(RED)
            elif frac < 0.5:
                color = QColor(AMBER)
            elif frac < 0.7:
                color = QColor(CYAN)
            else:
                color = QColor(GREEN)
            painter.setPen(QPen(color, arc_width, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap))
            painter.drawArc(arc_rect, int(start_angle * 16), int(sweep * 16))

            # center value
            painter.setPen(QPen(color))
            painter.setFont(QFont(FONT_MONO, 28, QFont.Weight.Bold))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, f"{self._value:.0f}")
        else:
            painter.setPen(QPen(QColor(MUTED)))
            painter.setFont(QFont(FONT_MONO, 20, QFont.Weight.Bold))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, N_A)

        # label below
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        label_rect = QRectF(r.left(), cy + radius * 0.45, r.width(), 20)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         self._label)

        # ticks: 0, 50, 100
        painter.setFont(QFont(FONT_MONO, 7))
        painter.setPen(QPen(QColor(MUTED2)))
        tick_r = radius + 8
        for val, angle_deg in ((0, 225), (50, 90), (100, -45)):
            rad = math.radians(angle_deg)
            tx = cx + tick_r * math.cos(rad)
            ty = cy - tick_r * math.sin(rad)
            painter.drawText(QRectF(tx - 12, ty - 6, 24, 12),
                             Qt.AlignmentFlag.AlignCenter, str(val))

        painter.end()


# ---------------------------------------------------------------------------
# RSI mini gauge — horizontal bar with zones
# ---------------------------------------------------------------------------

class _RSIBar(QWidget):
    """Horizontal RSI bar with oversold/neutral/overbought zones."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self.setMinimumWidth(120)
        self._value = None

    def set_value(self, value):
        try:
            self._value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self._value = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        bar_h = 6
        bar_y = r.center().y() - bar_h // 2
        bar_left = r.left() + 4
        bar_right = r.right() - 4
        bar_w = bar_right - bar_left

        # zones: 0-30 oversold (green), 30-70 neutral (muted), 70-100 overbought (red)
        zones = [(0.30, GREEN), (0.40, BORDER_DIM), (0.30, RED)]
        x = bar_left
        for frac, col in zones:
            w = int(bar_w * frac)
            painter.fillRect(QRectF(x, bar_y, w, bar_h), QColor(col).darker(200))
            x += w

        if self._value is not None:
            pos = bar_left + (self._value / 100.0) * bar_w
            if self._value < 30:
                color = QColor(GREEN)
            elif self._value > 70:
                color = QColor(RED)
            else:
                color = QColor(CYAN)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(pos, r.center().y()), 5, 5)
            painter.setPen(QPen(color))
            painter.setFont(QFont(FONT_MONO, 8, QFont.Weight.Bold))
            painter.drawText(QRectF(pos - 16, bar_y - 12, 32, 12),
                             Qt.AlignmentFlag.AlignCenter, f"{self._value:.1f}")

        # labels
        painter.setPen(QPen(QColor(MUTED2)))
        painter.setFont(QFont(FONT_MONO, 7))
        painter.drawText(QRectF(bar_left, bar_y + bar_h + 1, 20, 10),
                         Qt.AlignmentFlag.AlignLeft, "0")
        painter.drawText(QRectF(bar_right - 20, bar_y + bar_h + 1, 20, 10),
                         Qt.AlignmentFlag.AlignRight, "100")
        painter.end()


# ---------------------------------------------------------------------------
# Worker thread (unchanged contract)
# ---------------------------------------------------------------------------

class _StockWorker(QThread):
    succeeded = Signal(dict)
    failed = Signal(str)

    def __init__(self, symbol, mode_key, period, market_report):
        super().__init__()
        self._symbol = symbol
        self._mode_key = mode_key
        self._period = period
        self._market_report = market_report or {}

    def run(self):
        try:
            metrics = stock_adapter.stock_metrics(self._symbol)
            candles = stock_adapter.stock_candles(self._symbol, period=self._period)
            osc = stock_adapter.stock_oscillators(candles)
            ai = analyze_stock_report(
                self._symbol, metrics or {}, candles,
                self._market_report, self._mode_key,
            )
            self.succeeded.emit({
                "symbol": self._symbol,
                "metrics": metrics or {},
                "candles": candles or [],
                "osc": osc or {},
                "ai": ai or "",
            })
        except Exception as exc:
            self.failed.emit(str(exc))


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

class StockAnalysisPage(QWidget):
    """Professional single-stock deep-dive: chart + technicals + AI report."""

    _MODE_KEYS = {
        "Quick Scan": "quick",
        "Full Analysis": "full",
        "Institutional": "institutional",
    }
    _RANGE_PERIODS = {
        "3M": "3mo",
        "6M": "6mo",
        "1Y": "1y",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._market_report = None
        self._worker = None
        self._last_report: dict | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API (contract with main_window)
    # ------------------------------------------------------------------

    def set_market_report(self, report: dict):
        self._market_report = report

    def analyze_symbol(self, symbol: str):
        self._sym_input.setText(symbol.upper())
        self._run_analysis()

    def set_symbol(self, symbol: str):
        self.analyze_symbol(symbol)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_toolbar())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{BG}; border:none; }}"
            f"QScrollBar:vertical {{ background:{BG}; width:8px; border:none; }}"
            f"QScrollBar::handle:vertical {{ background:{BORDER_DIM}; border-radius:4px; min-height:28px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        )

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{BG};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 12, 16, 16)
        self._body_lay.setSpacing(12)
        self._body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)

        self._show_empty()

    def _build_toolbar(self):
        bar = QFrame()
        bar.setObjectName("StockToolbar")
        bar.setFixedHeight(48)
        bar.setStyleSheet(
            f"QFrame#StockToolbar {{ background:{SURFACE};"
            f" border-bottom:1px solid {BORDER_DIM}; }}"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 0, 14, 0)
        bl.setSpacing(8)

        self._sym_input = QLineEdit()
        self._sym_input.setFixedWidth(180)
        self._sym_input.setPlaceholderText("Symbol (e.g. RELIANCE)")
        self._sym_input.setStyleSheet(
            f"QLineEdit {{ background:{SURFACE_INSET}; color:{TEXT}; border:1px solid {BORDER_DIM};"
            f" border-radius:3px; padding:4px 10px; font-size:12px;"
            f" font-family:'{FONT_MONO}'; font-weight:bold; }}"
            f"QLineEdit:focus {{ border-color:{CYAN}; }}"
        )
        self._sym_input.returnPressed.connect(self._run_analysis)
        bl.addWidget(self._sym_input)

        self._mode_cb = QComboBox()
        self._mode_cb.addItems(["Quick Scan", "Full Analysis", "Institutional"])
        self._mode_cb.setCurrentIndex(1)
        cb_style = (
            f"QComboBox {{ background:{SURFACE_INSET}; color:{TEXT}; border:1px solid {BORDER_DIM};"
            f" border-radius:3px; padding:3px 8px; font-size:10px; }}"
            f"QComboBox::drop-down {{ border:none; }}"
            f"QComboBox QAbstractItemView {{ background:{SURFACE}; color:{TEXT};"
            f" border:1px solid {BORDER_DIM}; selection-background-color:{SURFACE_ALT}; }}"
        )
        self._mode_cb.setStyleSheet(cb_style)
        bl.addWidget(self._mode_cb)

        self._range_cb = QComboBox()
        self._range_cb.addItems(["3M", "6M", "1Y"])
        self._range_cb.setCurrentIndex(1)
        self._range_cb.setStyleSheet(cb_style)
        bl.addWidget(self._range_cb)

        self._analyze_btn = QPushButton("ANALYZE")
        self._analyze_btn.setFixedHeight(30)
        self._analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._analyze_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CYAN}; color:#000; border:none;
                border-radius:3px; font-size:10px; font-weight:700;
                padding:0 16px; letter-spacing:1px;
                font-family:'{FONT_UI}';
            }}
            QPushButton:hover {{ background:#33E8FF; }}
            QPushButton:pressed {{ background:#00B8D4; }}
            QPushButton:disabled {{ background:{BORDER_DIM}; color:{MUTED}; }}
        """)
        self._analyze_btn.clicked.connect(self._run_analysis)
        bl.addWidget(self._analyze_btn)

        bl.addStretch(1)

        self._status_lbl = _lbl("Enter a symbol", 9, MUTED)
        bl.addWidget(self._status_lbl)

        bl.addWidget(_lbl("ANALYSIS ONLY", 8, MUTED2, bold=True))

        return bar

    # ------------------------------------------------------------------
    # States
    # ------------------------------------------------------------------

    def _clear_body(self):
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def _show_empty(self):
        self._clear_body()
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(8)
        msg = _lbl("Enter an NSE symbol and press ANALYZE", 13, MUTED)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(msg)
        sub = _lbl("Supports all NSE-listed equities", 9, MUTED2)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        self._body_lay.addWidget(container, 1)

    def _show_loading(self, symbol: str):
        self._clear_body()
        container = QWidget()
        cl = QVBoxLayout(container)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(6)
        cl.addWidget(_lbl(f"Analyzing {symbol}…", 14, CYAN, bold=True))
        cl.addWidget(_lbl("Fetching data from NSE + running technical analysis", 9, MUTED))
        self._body_lay.addWidget(container, 1)

    # ------------------------------------------------------------------
    # Analysis trigger
    # ------------------------------------------------------------------

    def _run_analysis(self):
        query = self._sym_input.text().strip().upper()
        if not query:
            self._status_lbl.setText("Enter a symbol first")
            self._status_lbl.setStyleSheet(f"color:{AMBER}; background:transparent;")
            return

        resolved = stock_adapter.resolve_symbol(query)
        if not resolved:
            self._status_lbl.setText(f"'{query}' not found on NSE")
            self._status_lbl.setStyleSheet(f"color:{RED}; background:transparent;")
            return

        symbol = resolved["symbol"]
        mode_key = self._MODE_KEYS.get(self._mode_cb.currentText(), "full")
        period = self._RANGE_PERIODS.get(self._range_cb.currentText(), "6mo")

        self._status_lbl.setText(f"Fetching {symbol}…")
        self._status_lbl.setStyleSheet(f"color:{CYAN}; background:transparent;")
        self._analyze_btn.setEnabled(False)
        self._show_loading(symbol)

        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = _StockWorker(symbol, mode_key, period, self._market_report)
        self._worker.succeeded.connect(self._on_result)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    # ------------------------------------------------------------------
    # Result rendering
    # ------------------------------------------------------------------

    def _on_result(self, result: dict):
        self._analyze_btn.setEnabled(True)
        symbol = result.get("symbol", "?")
        metrics = result.get("metrics") or {}
        candles = result.get("candles") or []
        osc = result.get("osc") or {}
        ai_text = result.get("ai") or ""

        self._status_lbl.setText(f"{symbol} — done")
        self._status_lbl.setStyleSheet(f"color:{GREEN}; background:transparent;")

        if result.get("symbol"):
            self._last_report = {"symbol": symbol, "text": ai_text}

        self._clear_body()

        if not metrics.get("price"):
            self._body_lay.addWidget(
                _lbl(f"No live/history data for {symbol}. Nothing fabricated.", 11, AMBER)
            )
            if ai_text:
                self._body_lay.addWidget(self._build_ai_panel(symbol, ai_text))
            return

        # ROW 1: Stock header
        self._body_lay.addWidget(self._build_stock_header(symbol, metrics))

        # ROW 2: Three-column top (info | chart | momentum)
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._build_info_column(symbol, metrics), 0)
        top_row.addWidget(self._build_chart_column(candles), 1)
        top_row.addWidget(self._build_momentum_column(metrics, osc), 0)
        top_container = QWidget()
        top_container.setLayout(top_row)
        self._body_lay.addWidget(top_container)

        # ROW 3: Technicals grid (3 columns)
        self._body_lay.addWidget(self._build_technicals_grid(metrics, osc))

        # ROW 4: AI report
        if ai_text:
            self._body_lay.addWidget(self._build_ai_panel(symbol, ai_text))

        # ROW 5: Data quality footer
        self._body_lay.addWidget(self._build_data_quality(metrics, candles))

    def _on_error(self, err: str):
        self._analyze_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {err[:60]}")
        self._status_lbl.setStyleSheet(f"color:{RED}; background:transparent;")
        self._clear_body()
        self._body_lay.addWidget(_lbl(f"Analysis failed: {err}", 10, RED))

    # ------------------------------------------------------------------
    # Stock header row
    # ------------------------------------------------------------------

    def _build_stock_header(self, symbol, metrics):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(2)
        company = metrics.get("company_name") or symbol
        left.addWidget(_lbl(company, 16, TEXT, bold=True))

        tags = QHBoxLayout()
        tags.setSpacing(6)
        tags.addWidget(_pill(symbol, CYAN))
        tags.addWidget(_pill("NSE", MUTED))
        sector = stock_adapter.stock_sector(symbol)
        if sector:
            tags.addWidget(_pill(sector, PURPLE))
        trend = metrics.get("trend", "")
        if trend:
            tc = self._trend_color(trend)
            tags.addWidget(_pill(str(trend).upper(), tc))
        tags.addStretch()
        left.addLayout(tags)
        lay.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(0)
        right.setAlignment(Qt.AlignmentFlag.AlignRight)
        price_lbl = _lbl(_fmt_price(metrics.get("price")), 24, TEXT, bold=True, mono=True)
        price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(price_lbl)

        chg = metrics.get("change_percent")
        chg_lbl = _lbl(_fmt_pct(chg), 14, _sign_color(chg), bold=True, mono=True)
        chg_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(chg_lbl)

        ts = metrics.get("timestamp", "")
        if ts:
            ts_lbl = _lbl(f"as of {ts}", 8, MUTED2)
            ts_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            right.addWidget(ts_lbl)
        lay.addLayout(right)

        return frame

    # ------------------------------------------------------------------
    # Three-column top
    # ------------------------------------------------------------------

    def _build_info_column(self, symbol, metrics):
        frame = QFrame()
        frame.setFixedWidth(260)
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)

        lay.addWidget(_lbl("KEY STATISTICS", 9, MUTED, bold=True))
        lay.addWidget(_divider())

        for key, label in [
            ("volume", "Volume"),
            ("avg_volume_20d", "Avg Vol 20D"),
            ("relative_volume", "Rel Volume"),
            ("week_52_high", "52W High"),
            ("week_52_low", "52W Low"),
            ("high_52w", "52W High"),
            ("low_52w", "52W Low"),
            ("market_cap", "Market Cap"),
            ("pe_ratio", "P/E"),
            ("eps", "EPS"),
        ]:
            val = metrics.get(key)
            if val is not None:
                lay.addLayout(_kv_row(label, val))

        lay.addWidget(_divider())
        lay.addWidget(_lbl("KEY OBSERVATIONS", 9, MUTED, bold=True))
        obs = stock_adapter.stock_observations(metrics)
        for o in (obs or [])[:4]:
            ol = _lbl(f"• {o}", 9, SECONDARY)
            ol.setWordWrap(True)
            lay.addWidget(ol)

        lay.addStretch()
        return frame

    def _build_chart_column(self, candles):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        header = QHBoxLayout()
        header.addWidget(_lbl("PRICE", 9, MUTED, bold=True))
        header.addStretch()
        for label, color in [("MA20", CYAN), ("MA50", AMBER), ("MA200", PURPLE)]:
            header.addWidget(_lbl("●", 8, color))
            header.addWidget(_lbl(label, 8, MUTED))
        lay.addLayout(header)

        chart = W.CandleChart()
        chart.setMinimumHeight(260)
        chart.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        chart.set_candles(candles)

        overlays = []
        for key, color in [("ma20", CYAN), ("ma50", AMBER), ("ma200", PURPLE)]:
            values = [c.get(key) for c in candles]
            if any(v is not None for v in values):
                overlays.append({"values": values, "color": color})
        if overlays:
            chart.set_overlays(overlays)

        lay.addWidget(chart, 1)
        return frame

    def _build_momentum_column(self, metrics, osc):
        frame = QFrame()
        frame.setFixedWidth(200)
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)
        lay.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)

        gauge = _MomentumGauge()
        gauge.set_value(metrics.get("momentum_score"), "MOMENTUM SCORE")
        lay.addWidget(gauge, 0, Qt.AlignmentFlag.AlignHCenter)

        lay.addWidget(_divider())

        lay.addWidget(_lbl("RSI (14)", 9, MUTED, bold=True))
        rsi_bar = _RSIBar()
        rsi_bar.set_value(metrics.get("rsi_14"))
        lay.addWidget(rsi_bar)
        cond = metrics.get("rsi_condition", "")
        if cond:
            lay.addWidget(_lbl(str(cond), 8, MUTED2))

        lay.addWidget(_divider())

        lay.addWidget(_lbl("MACD", 9, MUTED, bold=True))
        macd_val = metrics.get("macd")
        macd_sig = metrics.get("macd_signal")
        macd_cond = metrics.get("macd_condition", "")
        mc = _sign_color(macd_val) if macd_val is not None else MUTED
        lay.addLayout(_kv_row("Line", _fmt_num(macd_val), mc))
        lay.addLayout(_kv_row("Signal", _fmt_num(macd_sig), MUTED))
        if macd_cond:
            lay.addWidget(_pill(str(macd_cond), mc, SURFACE_ALT))

        lay.addStretch()
        return frame

    # ------------------------------------------------------------------
    # Technicals grid
    # ------------------------------------------------------------------

    def _build_technicals_grid(self, metrics, osc):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        grid_outer = QVBoxLayout(frame)
        grid_outer.setContentsMargins(14, 10, 14, 10)
        grid_outer.setSpacing(8)

        grid_outer.addWidget(_lbl("TECHNICAL INDICATORS", 10, MUTED, bold=True))

        cols = QHBoxLayout()
        cols.setSpacing(14)

        # Column 1: Oscillators
        c1 = QVBoxLayout()
        c1.setSpacing(3)
        c1.addWidget(_lbl("OSCILLATORS", 9, CYAN, bold=True))
        c1.addWidget(_divider())
        for key, label in [
            ("rsi_14", "RSI (14)"),
            ("macd", "MACD"),
            ("macd_signal", "Signal"),
            ("atr_14", "ATR (14)"),
        ]:
            val = metrics.get(key)
            c1.addLayout(_kv_row(label, _fmt_num(val), _sign_color(val) if key == "macd" else SECONDARY))
        c1.addStretch()
        cols.addLayout(c1, 1)

        # Column 2: Moving Averages
        c2 = QVBoxLayout()
        c2.setSpacing(3)
        c2.addWidget(_lbl("MOVING AVERAGES", 9, CYAN, bold=True))
        c2.addWidget(_divider())
        price = metrics.get("price")
        for key, label in [
            ("ema_20", "EMA 20"),
            ("ema_50", "EMA 50"),
            ("ema_200", "EMA 200"),
            ("sma_20", "SMA 20"),
            ("sma_50", "SMA 50"),
            ("sma_200", "SMA 200"),
        ]:
            val = metrics.get(key)
            if val is not None:
                try:
                    color = GREEN if float(price) >= float(val) else RED
                except (TypeError, ValueError):
                    color = MUTED
                c2.addLayout(_kv_row(label, _fmt_price(val), color))
        c2.addStretch()
        cols.addLayout(c2, 1)

        # Column 3: Structure & Returns
        c3 = QVBoxLayout()
        c3.setSpacing(3)
        c3.addWidget(_lbl("STRUCTURE & RETURNS", 9, CYAN, bold=True))
        c3.addWidget(_divider())
        for key, label in [
            ("trend", "Trend"),
            ("structure", "Structure"),
        ]:
            val = metrics.get(key)
            if val is not None:
                c3.addLayout(_kv_row(label, str(val).title(), SECONDARY))
        c3.addWidget(_divider())
        for key, label in [
            ("return_1d", "Return 1D"),
            ("return_5d", "Return 5D"),
            ("return_20d", "Return 20D"),
            ("return_60d", "Return 60D"),
        ]:
            val = metrics.get(key)
            if val is not None:
                c3.addLayout(_kv_row(label, _fmt_pct(val), _sign_color(val)))
        c3.addStretch()
        cols.addLayout(c3, 1)

        grid_outer.addLayout(cols)
        return frame

    # ------------------------------------------------------------------
    # AI report panel
    # ------------------------------------------------------------------

    def _build_ai_panel(self, symbol: str, ai_text: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        hdr = QHBoxLayout()
        hdr.addWidget(_lbl("AI RESEARCH REPORT", 11, CYAN, bold=True))
        hdr.addStretch()
        hdr.addWidget(_lbl("analysis-only · no buy/sell recommendation", 8, MUTED2))
        lay.addLayout(hdr)

        if not ai_text or ai_text.startswith(("STOCK ANALYSIS AI ERROR", "MARKET LAB AI ERROR")):
            if ai_text:
                err = _lbl(ai_text[:200], 9, RED)
                err.setWordWrap(True)
                lay.addWidget(err)
            else:
                lay.addWidget(_lbl("No AI report generated.", 10, MUTED))
            lay.addStretch()
            return frame

        parsed = report_parser.parse_report(ai_text)
        bias = parsed.get("bias", "UNAVAILABLE")
        bias_color = {
            "BULLISH": GREEN, "BEARISH": RED, "NEUTRAL": MUTED,
            "MIXED": AMBER, "INSUFFICIENT EVIDENCE": AMBER,
        }.get(bias, MUTED)

        bias_row = QHBoxLayout()
        bias_row.addWidget(_pill(bias, bias_color))
        bias_row.addStretch()
        lay.addLayout(bias_row)

        summary_items = report_parser.collect_bullets(
            report_parser.sections_matching(parsed, "executive", "conclusion", "summary", "overall")
        )
        if summary_items:
            lay.addWidget(_lbl("EXECUTIVE SUMMARY", 9, MUTED, bold=True))
            for item in summary_items[:5]:
                lbl = _lbl(f"• {item}", 10, SECONDARY)
                lbl.setWordWrap(True)
                lay.addWidget(lbl)

        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        text_edit.setPlainText(ai_text)
        text_edit.setStyleSheet(
            f"QPlainTextEdit {{ background:{SURFACE_INSET}; color:{SECONDARY};"
            f" border:1px solid {BORDER_DIM}; border-radius:4px;"
            f" font-size:10px; font-family:'{FONT_MONO}'; padding:8px; }}"
        )
        text_edit.setMinimumHeight(180)
        lay.addWidget(text_edit, 1)

        return frame

    # ------------------------------------------------------------------
    # Data quality footer
    # ------------------------------------------------------------------

    def _build_data_quality(self, metrics, candles):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:4px; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(16)

        lay.addWidget(_lbl("DATA QUALITY", 8, MUTED2, bold=True))

        dq = stock_adapter.data_quality(metrics, candles)
        for component, status in dq.items():
            color = GREEN if status == "AVAILABLE" else (AMBER if status == "PARTIAL" else MUTED2)
            lay.addWidget(_lbl(f"{component}: {status}", 8, color))

        lay.addStretch()
        lay.addWidget(_lbl(GUARDRAIL_TEXT, 8, MUTED2))

        return frame

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _trend_color(self, trend):
        if not trend:
            return MUTED
        t = str(trend).upper()
        if "STRONG_UP" in t or "STRONG UP" in t:
            return GREEN
        if "UP" in t:
            return "#66CC88"
        if "STRONG_DOWN" in t or "STRONG DOWN" in t:
            return RED
        if "DOWN" in t:
            return AMBER
        return MUTED
