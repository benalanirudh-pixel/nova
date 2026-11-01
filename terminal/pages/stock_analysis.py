"""Terminal Stock Analysis page — spacious data layout with momentum gauge.

Big fonts, generous spacing, momentum circle as the verdict.
All data from stock_adapter — nothing fabricated.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QThread, Signal, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QFrame, QSizePolicy, QPushButton,
)

from market_lab import stock_adapter, report_parser
from market_lab.market_lab_brain import analyze_stock_report
from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SURFACE_INSET,
    CYAN, GREEN, RED, AMBER, PURPLE, MUTED, MUTED2, TEXT,
    BORDER, BORDER_DIM, SECONDARY,
    FONT_UI, FONT_MONO, GUARDRAIL_TEXT,
)

N_A = "—"


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


def _fmt_vol(v):
    if v is None:
        return N_A
    try:
        n = float(v)
        if n >= 1e7:
            return f"{n/1e7:.2f} Cr"
        if n >= 1e5:
            return f"{n/1e5:.2f} L"
        return f"{int(n):,}"
    except (TypeError, ValueError):
        return str(v)


def _sign_color(v):
    try:
        return GREEN if float(v) >= 0 else RED
    except (TypeError, ValueError):
        return MUTED


def _lbl(text, size=11, color=TEXT, bold=False, mono=False):
    lbl = QLabel(str(text))
    family = FONT_MONO if mono else FONT_UI
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}px;"
        f" font-weight:{'bold' if bold else 'normal'};"
        f" font-family:'{family}'; background:transparent;"
    )
    return lbl


def _pill(text, color=CYAN):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color:{color}; font-size:9px; font-weight:bold;"
        f" background:{SURFACE_ALT}; border:1px solid {color}; border-radius:10px;"
        f" padding:2px 10px; font-family:'{FONT_UI}';"
    )
    return lbl


def _divider():
    line = QFrame()
    line.setFixedHeight(1)
    line.setStyleSheet(f"background:{BORDER_DIM};")
    return line


def _metric_row(key, value, color=TEXT):
    """Spacious key-value row with big value font."""
    row = QHBoxLayout()
    row.setSpacing(12)
    row.setContentsMargins(0, 3, 0, 3)
    row.addWidget(_lbl(key, 11, MUTED))
    row.addStretch(1)
    v = _lbl(str(value) if value is not None else N_A, 13, color, bold=True, mono=True)
    v.setAlignment(Qt.AlignmentFlag.AlignRight)
    row.addWidget(v)
    return row


# ---------------------------------------------------------------------------
# Sparkline — tiny price line for header corner
# ---------------------------------------------------------------------------

class _Sparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(110, 44)
        self._prices = []

    def set_prices(self, candles):
        self._prices = []
        for c in (candles or []):
            p = c.get("close")
            if p is not None:
                try:
                    self._prices.append(float(p))
                except (TypeError, ValueError):
                    pass
        self.update()

    def paintEvent(self, event):
        if len(self._prices) < 2:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(2, 6, -2, -6)

        mn, mx = min(self._prices), max(self._prices)
        rng = mx - mn if mx != mn else 1.0
        n = len(self._prices)

        color = GREEN if self._prices[-1] >= self._prices[0] else RED
        painter.setPen(QPen(QColor(color), 1.5))

        pts = []
        for i, p in enumerate(self._prices):
            x = r.left() + (i / (n - 1)) * r.width()
            y = r.bottom() - ((p - mn) / rng) * r.height()
            pts.append(QRectF(x, y, 0, 0).center())
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        painter.end()


# ---------------------------------------------------------------------------
# Momentum gauge — big arc widget, the verdict
# ---------------------------------------------------------------------------

class _MomentumGauge(QWidget):
    """Large arc gauge 0-100. This IS the verdict."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._value = None
        self._label = "MOMENTUM SCORE"
        self._zone = ""

    def set_value(self, value, label=None):
        try:
            self._value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            self._value = None
        if label:
            self._label = str(label)
        if self._value is not None:
            if self._value >= 70:
                self._zone = "STRONG"
            elif self._value >= 50:
                self._zone = "MODERATE"
            elif self._value >= 30:
                self._zone = "WEAK"
            else:
                self._zone = "VERY WEAK"
        else:
            self._zone = ""
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        size = min(r.width(), r.height())
        cx, cy = r.center().x(), r.center().y()
        radius = size / 2 - 16
        arc_width = 12
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

            # big center number
            painter.setPen(QPen(color))
            painter.setFont(QFont(FONT_MONO, 36, QFont.Weight.Bold))
            num_rect = QRectF(r.left(), cy - 30, r.width(), 50)
            painter.drawText(num_rect, Qt.AlignmentFlag.AlignCenter, f"{self._value:.0f}")

            # zone label below number
            if self._zone:
                painter.setFont(QFont(FONT_UI, 11, QFont.Weight.Bold))
                zone_rect = QRectF(r.left(), cy + 18, r.width(), 20)
                painter.drawText(zone_rect, Qt.AlignmentFlag.AlignCenter, self._zone)
        else:
            painter.setPen(QPen(QColor(MUTED)))
            painter.setFont(QFont(FONT_MONO, 28, QFont.Weight.Bold))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, N_A)

        # title below arc
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        title_rect = QRectF(r.left(), cy + radius * 0.55, r.width(), 20)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                         self._label)

        # tick labels: 0, 25, 50, 75, 100
        painter.setFont(QFont(FONT_MONO, 8))
        painter.setPen(QPen(QColor(MUTED2)))
        tick_r = radius + 12
        for val, angle_deg in ((0, 225), (25, 157.5), (50, 90), (75, 22.5), (100, -45)):
            rad = math.radians(angle_deg)
            tx = cx + tick_r * math.cos(rad)
            ty = cy - tick_r * math.sin(rad)
            painter.drawText(QRectF(tx - 14, ty - 7, 28, 14),
                             Qt.AlignmentFlag.AlignCenter, str(val))

        painter.end()


# ---------------------------------------------------------------------------
# Worker thread
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
    """Spacious stock analysis — big fonts, momentum gauge as verdict."""

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

    def set_market_report(self, report: dict):
        self._market_report = report

    def analyze_symbol(self, symbol: str):
        self._sym_input.setText(symbol.upper())
        self._run_analysis()

    def set_symbol(self, symbol: str):
        self.analyze_symbol(symbol)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(self._build_toolbar())

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{BG};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 12, 16, 12)
        self._body_lay.setSpacing(10)
        outer.addWidget(self._body, 1)

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
        bl.setContentsMargins(16, 0, 16, 0)
        bl.setSpacing(10)

        self._sym_input = QLineEdit()
        self._sym_input.setFixedWidth(180)
        self._sym_input.setPlaceholderText("Symbol (e.g. RELIANCE)")
        self._sym_input.setStyleSheet(
            f"QLineEdit {{ background:{SURFACE_INSET}; color:{TEXT}; border:1px solid {BORDER_DIM};"
            f" border-radius:4px; padding:6px 12px; font-size:13px;"
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
            f" border-radius:4px; padding:4px 10px; font-size:11px; }}"
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
        self._analyze_btn.setFixedHeight(32)
        self._analyze_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._analyze_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CYAN}; color:#000; border:none;
                border-radius:4px; font-size:11px; font-weight:700;
                padding:0 18px; letter-spacing:1px; font-family:'{FONT_UI}';
            }}
            QPushButton:hover {{ background:#33E8FF; }}
            QPushButton:pressed {{ background:#00B8D4; }}
            QPushButton:disabled {{ background:{BORDER_DIM}; color:{MUTED}; }}
        """)
        self._analyze_btn.clicked.connect(self._run_analysis)
        bl.addWidget(self._analyze_btn)

        bl.addStretch(1)
        self._status_lbl = _lbl("Enter a symbol", 10, MUTED)
        bl.addWidget(self._status_lbl)
        bl.addWidget(_lbl("ANALYSIS ONLY", 9, MUTED2, bold=True))
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
        c = QWidget()
        cl = QVBoxLayout(c)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.setSpacing(8)
        cl.addWidget(_lbl("Enter an NSE symbol and press ANALYZE", 16, MUTED))
        sub = _lbl("Supports all NSE-listed equities", 11, MUTED2)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(sub)
        self._body_lay.addWidget(c, 1)

    def _show_loading(self, symbol: str):
        self._clear_body()
        c = QWidget()
        cl = QVBoxLayout(c)
        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cl.addWidget(_lbl(f"Analyzing {symbol}…", 18, CYAN, bold=True))
        cl.addWidget(_lbl("Fetching data + running technical analysis", 11, MUTED))
        self._body_lay.addWidget(c, 1)

    # ------------------------------------------------------------------
    # Analysis
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
    # Result
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
                _lbl(f"No data for {symbol}. Nothing fabricated.", 13, AMBER)
            )
            return

        # === HEADER: company + price + sparkline ===
        self._body_lay.addWidget(self._build_header(symbol, metrics, candles))

        # === MAIN: left data panels | right momentum gauge ===
        main_row = QHBoxLayout()
        main_row.setSpacing(12)

        # Left: two data columns
        left = QVBoxLayout()
        left.setSpacing(10)

        # Top data row: Price & Returns | Technicals
        data_row = QHBoxLayout()
        data_row.setSpacing(10)
        data_row.addWidget(self._build_price_panel(metrics), 1)
        data_row.addWidget(self._build_technicals_panel(metrics, osc), 1)
        data_w = QWidget()
        data_w.setLayout(data_row)
        left.addWidget(data_w)

        # Bottom: Trend + EMA signals + AI points
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(10)
        bottom_row.addWidget(self._build_trend_panel(metrics), 1)
        ai_panel = self._build_ai_panel(ai_text)
        if ai_panel:
            bottom_row.addWidget(ai_panel, 1)
        bottom_w = QWidget()
        bottom_w.setLayout(bottom_row)
        left.addWidget(bottom_w)

        main_row.addLayout(left, 3)

        # Right: big momentum gauge
        gauge_frame = QFrame()
        gauge_frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        gauge_lay = QVBoxLayout(gauge_frame)
        gauge_lay.setContentsMargins(12, 12, 12, 12)
        gauge_lay.setSpacing(4)

        gauge = _MomentumGauge()
        gauge.set_value(metrics.get("momentum_score"), "MOMENTUM SCORE")
        gauge_lay.addWidget(gauge, 1)

        # RSI mini-summary under gauge
        rsi = metrics.get("rsi_14")
        if rsi is not None:
            try:
                r = float(rsi)
                rc = GREEN if r < 30 else (RED if r > 70 else SECONDARY)
                zone = "Oversold" if r < 30 else ("Overbought" if r > 70 else "Neutral")
                rsi_lbl = _lbl(f"RSI {r:.1f} · {zone}", 11, rc, bold=True)
                rsi_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                gauge_lay.addWidget(rsi_lbl)
            except (TypeError, ValueError):
                pass

        macd_cond = metrics.get("macd_condition", "")
        if macd_cond:
            mc = _sign_color(metrics.get("macd"))
            macd_lbl = _lbl(f"MACD · {macd_cond}", 10, mc)
            macd_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            gauge_lay.addWidget(macd_lbl)

        main_row.addWidget(gauge_frame, 2)

        main_w = QWidget()
        main_w.setLayout(main_row)
        self._body_lay.addWidget(main_w, 1)

        # === GUARDRAIL ===
        guard = QLabel(GUARDRAIL_TEXT)
        guard.setStyleSheet(f"color:{MUTED2}; font-size:8px; background:transparent; padding:2px 0;")
        guard.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_lay.addWidget(guard)

    def _on_error(self, err: str):
        self._analyze_btn.setEnabled(True)
        self._status_lbl.setText(f"Error: {err[:60]}")
        self._status_lbl.setStyleSheet(f"color:{RED}; background:transparent;")
        self._clear_body()
        self._body_lay.addWidget(_lbl(f"Analysis failed: {err}", 12, RED))

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self, symbol, metrics, candles):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QHBoxLayout(frame)
        lay.setContentsMargins(16, 10, 16, 10)
        lay.setSpacing(12)

        # Left: company + pills
        left = QVBoxLayout()
        left.setSpacing(4)
        company = metrics.get("company_name") or symbol
        left.addWidget(_lbl(company, 18, TEXT, bold=True))
        tags = QHBoxLayout()
        tags.setSpacing(6)
        tags.addWidget(_pill(symbol, CYAN))
        sector = stock_adapter.stock_sector(symbol)
        if sector:
            tags.addWidget(_pill(sector, PURPLE))
        trend = metrics.get("trend", "")
        if trend:
            tags.addWidget(_pill(str(trend).upper(), self._trend_color(trend)))
        tags.addStretch()
        left.addLayout(tags)
        lay.addLayout(left, 1)

        # Right: price + change + sparkline
        right = QHBoxLayout()
        right.setSpacing(16)
        right.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        price_col = QVBoxLayout()
        price_col.setSpacing(0)
        price_col.setAlignment(Qt.AlignmentFlag.AlignRight)
        price_col.addWidget(_lbl(_fmt_price(metrics.get("price")), 22, TEXT, bold=True, mono=True))
        chg = metrics.get("change_percent")
        chg_lbl = _lbl(_fmt_pct(chg), 14, _sign_color(chg), bold=True, mono=True)
        chg_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        price_col.addWidget(chg_lbl)
        right.addLayout(price_col)

        spark = _Sparkline()
        spark.set_prices(candles)
        right.addWidget(spark)

        lay.addLayout(right)
        return frame

    # ------------------------------------------------------------------
    # Data panels
    # ------------------------------------------------------------------

    def _build_price_panel(self, metrics):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        lay.addWidget(_lbl("PRICE & VOLUME", 10, CYAN, bold=True))
        lay.addWidget(_divider())

        h52 = metrics.get("week_52_high") or metrics.get("high_52w")
        l52 = metrics.get("week_52_low") or metrics.get("low_52w")
        lay.addLayout(_metric_row("52W High", _fmt_price(h52), GREEN))
        lay.addLayout(_metric_row("52W Low", _fmt_price(l52), RED))

        price = metrics.get("price")
        if price and h52 and l52:
            try:
                p, h, l = float(price), float(h52), float(l52)
                if h != l:
                    pct = (p - l) / (h - l) * 100
                    lay.addLayout(_metric_row("52W Position", f"{pct:.0f}%", CYAN))
            except (TypeError, ValueError):
                pass

        lay.addLayout(_metric_row("Volume", _fmt_vol(metrics.get("volume")), SECONDARY))
        rel_vol = metrics.get("relative_volume")
        if rel_vol is not None:
            lay.addLayout(_metric_row("Rel Volume", _fmt_num(rel_vol, 1), SECONDARY))

        lay.addWidget(_divider())
        lay.addWidget(_lbl("RETURNS", 10, CYAN, bold=True))

        for key, label in [("return_1d", "1 Day"), ("return_5d", "5 Day"),
                           ("return_20d", "20 Day"), ("return_60d", "60 Day")]:
            val = metrics.get(key)
            if val is not None:
                lay.addLayout(_metric_row(label, _fmt_pct(val), _sign_color(val)))

        lay.addStretch(1)
        return frame

    def _build_technicals_panel(self, metrics, osc):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        lay.addWidget(_lbl("TECHNICALS", 10, CYAN, bold=True))
        lay.addWidget(_divider())

        rsi = metrics.get("rsi_14")
        if rsi is not None:
            try:
                r = float(rsi)
                rc = GREEN if r < 30 else (RED if r > 70 else SECONDARY)
                lay.addLayout(_metric_row("RSI (14)", f"{r:.1f}", rc))
            except (TypeError, ValueError):
                lay.addLayout(_metric_row("RSI (14)", N_A, MUTED))
        else:
            lay.addLayout(_metric_row("RSI (14)", N_A, MUTED))

        macd = metrics.get("macd")
        lay.addLayout(_metric_row("MACD", _fmt_num(macd), _sign_color(macd)))
        lay.addLayout(_metric_row("Signal", _fmt_num(metrics.get("macd_signal")), MUTED))

        lay.addLayout(_metric_row("ADX", _fmt_num(metrics.get("adx"), 1), SECONDARY))
        lay.addLayout(_metric_row("ATR (14)", _fmt_num(metrics.get("atr_14")), SECONDARY))

        lay.addWidget(_divider())
        lay.addWidget(_lbl("MOVING AVERAGES", 10, CYAN, bold=True))

        price = metrics.get("price")
        for key, label in [("ema_20", "EMA 20"), ("ema_50", "EMA 50"), ("ema_200", "EMA 200")]:
            ema = metrics.get(key)
            if ema is not None and price is not None:
                try:
                    above = float(price) >= float(ema)
                    signal = "Above" if above else "Below"
                    lay.addLayout(_metric_row(label, f"{signal}  {_fmt_price(ema)}",
                                             GREEN if above else RED))
                except (TypeError, ValueError):
                    lay.addLayout(_metric_row(label, _fmt_price(ema), MUTED))

        lay.addStretch(1)
        return frame

    def _build_trend_panel(self, metrics):
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(2)

        lay.addWidget(_lbl("TREND & STRUCTURE", 10, CYAN, bold=True))
        lay.addWidget(_divider())

        trend = metrics.get("trend", "")
        if trend:
            lay.addLayout(_metric_row("Trend", str(trend).title(), self._trend_color(trend)))

        structure = metrics.get("structure", "")
        if structure:
            lay.addLayout(_metric_row("Structure", str(structure).title(), SECONDARY))

        rsi_cond = metrics.get("rsi_condition", "")
        if rsi_cond:
            lay.addLayout(_metric_row("RSI Zone", str(rsi_cond), SECONDARY))

        macd_cond = metrics.get("macd_condition", "")
        if macd_cond:
            lay.addLayout(_metric_row("MACD Signal", str(macd_cond), _sign_color(metrics.get("macd"))))

        # Key observations
        obs = stock_adapter.stock_observations(metrics)
        if obs:
            lay.addWidget(_divider())
            lay.addWidget(_lbl("KEY OBSERVATIONS", 10, CYAN, bold=True))
            for o in (obs or [])[:3]:
                ol = _lbl(f"• {o}", 10, SECONDARY)
                ol.setWordWrap(True)
                lay.addWidget(ol)

        lay.addStretch(1)
        return frame

    def _build_ai_panel(self, ai_text):
        if not ai_text or ai_text.startswith(("STOCK ANALYSIS AI ERROR", "MARKET LAB AI ERROR")):
            return None

        parsed = report_parser.parse_report(ai_text)
        bullets = report_parser.collect_bullets(
            report_parser.sections_matching(parsed, "executive", "conclusion", "summary", "overall")
        )
        if not bullets:
            return None

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER_DIM};"
            f" border-radius:6px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(4)

        lay.addWidget(_lbl("AI KEY POINTS", 10, CYAN, bold=True))
        lay.addWidget(_divider())
        for item in bullets[:4]:
            lbl = _lbl(f"• {item}", 10, SECONDARY)
            lbl.setWordWrap(True)
            lay.addWidget(lbl)

        lay.addStretch(1)
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
