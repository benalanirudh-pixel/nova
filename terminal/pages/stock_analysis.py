"""Terminal Stock Analysis page — wraps existing stock_adapter + analyze_stock_report."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QComboBox, QFrame, QScrollArea, QSizePolicy, QPlainTextEdit,
)

from market_lab import stock_adapter, report_parser
from market_lab import widgets as W
from market_lab.market_lab_brain import analyze_stock_report
from styles.design_tokens import (
    BG, SURFACE, CYAN, GREEN, RED, AMBER, MUTED, MUTED2, TEXT,
    BORDER, SECONDARY,
)

N_A = "N/A"


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
    family = "Consolas" if mono else "Segoe UI"
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


class StockAnalysisPage(QWidget):
    """Single-stock deep-dive: overview card + AI report."""

    _MODE_KEYS = {
        "Quick Scan": "quick",
        "Full Analysis": "full",
        "Institutional Analysis": "institutional",
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
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- toolbar ---
        bar = QFrame()
        bar.setObjectName("StockToolbar")
        bar.setFixedHeight(52)
        bar.setStyleSheet(
            f"QFrame#StockToolbar {{ background:{SURFACE};"
            f" border-bottom:1px solid {BORDER}; }}"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 6, 14, 6)
        bl.setSpacing(10)

        bl.addWidget(_lbl("SYMBOL", 9, MUTED, bold=True))
        self._sym_input = QLineEdit()
        self._sym_input.setFixedWidth(200)
        self._sym_input.setPlaceholderText("e.g. RELIANCE")
        self._sym_input.setStyleSheet(
            f"QLineEdit {{ background:{BG}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:4px 8px; font-size:12px; }}"
        )
        self._sym_input.returnPressed.connect(self._run_analysis)
        bl.addWidget(self._sym_input)

        bl.addWidget(_lbl("MODE", 9, MUTED, bold=True))
        self._mode_cb = QComboBox()
        self._mode_cb.addItems(["Quick Scan", "Full Analysis", "Institutional Analysis"])
        self._mode_cb.setCurrentIndex(1)
        self._mode_cb.setStyleSheet(
            f"QComboBox {{ background:{BG}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:4px 8px; font-size:11px; }}"
        )
        bl.addWidget(self._mode_cb)

        bl.addWidget(_lbl("RANGE", 9, MUTED, bold=True))
        self._range_cb = QComboBox()
        self._range_cb.addItems(["3M", "6M", "1Y"])
        self._range_cb.setCurrentIndex(1)
        self._range_cb.setStyleSheet(self._mode_cb.styleSheet())
        bl.addWidget(self._range_cb)

        self._analyze_btn = QLabel("ANALYZE")
        self._analyze_btn.setFixedSize(90, 30)
        self._analyze_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._analyze_btn.setStyleSheet(
            f"QLabel {{ background:{CYAN}; color:#000; font-size:11px;"
            f" font-weight:bold; border-radius:3px; }}"
        )
        self._analyze_btn.mousePressEvent = lambda _: self._run_analysis()
        bl.addWidget(self._analyze_btn)

        bl.addStretch(1)

        self._status_lbl = _lbl("Enter a symbol and press ANALYZE", 9, MUTED)
        bl.addWidget(self._status_lbl)

        outer.addWidget(bar)

        # --- scroll body ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:none; }}")

        self._body = QWidget()
        self._body.setStyleSheet(f"background:{BG};")
        self._body_lay = QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(16, 16, 16, 16)
        self._body_lay.setSpacing(14)
        self._body_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        scroll.setWidget(self._body)
        outer.addWidget(scroll, 1)

        self._show_empty()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_market_report(self, report: dict):
        self._market_report = report

    def analyze_symbol(self, symbol: str):
        self._sym_input.setText(symbol.upper())
        self._run_analysis()

    def set_symbol(self, symbol: str):
        """Called from main window search bar."""
        self.analyze_symbol(symbol)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _clear_body(self):
        while self._body_lay.count():
            item = self._body_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def _show_empty(self):
        self._clear_body()
        msg = _lbl("Enter an NSE symbol above and press ANALYZE", 13, MUTED)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_lay.addWidget(msg, alignment=Qt.AlignmentFlag.AlignCenter)

    def _show_loading(self, symbol: str):
        self._clear_body()
        msg = _lbl(f"Analyzing {symbol}…", 13, CYAN)
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._body_lay.addWidget(msg, alignment=Qt.AlignmentFlag.AlignCenter)

    def _run_analysis(self):
        query = self._sym_input.text().strip().upper()
        if not query:
            self._status_lbl.setText("Enter a symbol first.")
            self._status_lbl.setStyleSheet(f"color:{AMBER};")
            return

        resolved = stock_adapter.resolve_symbol(query)
        if not resolved:
            self._status_lbl.setText(f"Symbol '{query}' not found on NSE.")
            self._status_lbl.setStyleSheet(f"color:{RED};")
            return

        symbol = resolved["symbol"]
        mode_key = self._MODE_KEYS.get(self._mode_cb.currentText(), "full")
        period = self._RANGE_PERIODS.get(self._range_cb.currentText(), "6mo")

        self._status_lbl.setText(f"Fetching {symbol}…")
        self._status_lbl.setStyleSheet(f"color:{CYAN};")
        self._show_loading(symbol)

        if self._worker and self._worker.isRunning():
            self._worker.quit()

        self._worker = _StockWorker(symbol, mode_key, period, self._market_report)
        self._worker.succeeded.connect(self._on_result)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_result(self, result: dict):
        symbol = result.get("symbol", "?")
        metrics = result.get("metrics") or {}
        candles = result.get("candles") or []
        ai_text = result.get("ai") or ""

        self._status_lbl.setText(f"{symbol} — done")
        self._status_lbl.setStyleSheet(f"color:{GREEN};")

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

        # Two-column layout
        cols = QHBoxLayout()
        cols.setSpacing(14)
        cols.addWidget(self._build_overview(symbol, metrics, candles), 1)
        cols.addWidget(self._build_ai_panel(symbol, ai_text), 1)
        container = QWidget()
        container.setLayout(cols)
        self._body_lay.addWidget(container)

    def _on_error(self, err: str):
        self._status_lbl.setText(f"Error: {err[:80]}")
        self._status_lbl.setStyleSheet(f"color:{RED};")
        self._clear_body()
        self._body_lay.addWidget(_lbl(f"Analysis failed: {err}", 10, RED))

    # ------------------------------------------------------------------
    # Overview card
    # ------------------------------------------------------------------

    def _build_overview(self, symbol: str, metrics: dict, candles: list) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # Identity row
        id_row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(2)
        company = metrics.get("company_name") or symbol
        left.addWidget(_lbl(company, 16, TEXT, bold=True))
        tags = [symbol, metrics.get("exchange", "NSE")]
        sector = stock_adapter.stock_sector(symbol)
        if sector:
            tags.append(sector)
        ts = metrics.get("timestamp", "")
        meta = " · ".join(tags)
        if ts:
            meta += f" · as of {ts}"
        left.addWidget(_lbl(meta, 9, MUTED))
        id_row.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(2)
        price_lbl = _lbl(_fmt_price(metrics.get("price")), 22, TEXT, bold=True, mono=True)
        price_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(price_lbl)
        chg = metrics.get("change_percent")
        chg_lbl = _lbl(_fmt_pct(chg), 13, _sign_color(chg), bold=True, mono=True)
        chg_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        right.addWidget(chg_lbl)
        id_row.addLayout(right)
        lay.addLayout(id_row)

        # KPI tiles row
        kt = stock_adapter.kpi_tiles(metrics)
        tiles_row = QHBoxLayout()
        tiles_row.setSpacing(8)
        for label, val, color, note in [
            ("TREND", kt.get("trend", N_A), self._trend_color(kt.get("trend")), ""),
            ("MOMENTUM", _fmt_num(kt.get("momentum_score"), 1), CYAN, "scanner score"),
            ("RSI 14", _fmt_num(kt.get("rsi"), 1), None, str(kt.get("rsi_condition", ""))),
            ("MACD", _fmt_num(kt.get("macd"), 2), None, str(kt.get("macd_condition", ""))),
        ]:
            tile = self._stat_tile(label, val, color, note)
            tiles_row.addWidget(tile)
        lay.addLayout(tiles_row)

        # Sparkline from candles
        closes = [c.get("c") for c in candles if isinstance(c, dict) and c.get("c") is not None]
        dates = [c.get("t", "") for c in candles if isinstance(c, dict) and c.get("c") is not None]
        if closes:
            chart = W.LineChart()
            chart.setMinimumHeight(80)
            chart.set_series(closes, dates)
            lay.addWidget(chart)
        else:
            lay.addWidget(_lbl("No price history available.", 9, MUTED))

        # Key observations
        obs = stock_adapter.stock_observations(metrics)
        if obs:
            lay.addWidget(_lbl("KEY OBSERVATIONS", 9, MUTED, bold=True))
            for o in obs[:6]:
                lay.addWidget(_lbl(f"• {o}", 9, TEXT))

        # Key metrics grid
        lay.addWidget(_lbl("METRICS", 9, MUTED, bold=True))
        for key, label in [
            ("volume", "Volume"),
            ("avg_volume_20d", "Avg Vol 20D"),
            ("week_52_high", "52W High"),
            ("week_52_low", "52W Low"),
            ("market_cap", "Market Cap"),
            ("pe_ratio", "P/E"),
            ("eps", "EPS"),
        ]:
            val = metrics.get(key)
            if val is not None:
                lay.addLayout(_kv_row(label, val))

        lay.addStretch()
        return frame

    def _stat_tile(self, label, value, color=None, note="") -> QFrame:
        tile = QFrame()
        tile.setStyleSheet(
            f"QFrame {{ background:{BG}; border:1px solid {BORDER};"
            f" border-radius:3px; }}"
        )
        tl = QVBoxLayout(tile)
        tl.setContentsMargins(8, 6, 8, 6)
        tl.setSpacing(2)
        tl.addWidget(_lbl(label, 8, MUTED, bold=True))
        tl.addWidget(_lbl(str(value), 14, color or TEXT, bold=True, mono=True))
        if note:
            tl.addWidget(_lbl(note, 8, MUTED))
        return tile

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

    # ------------------------------------------------------------------
    # AI report panel
    # ------------------------------------------------------------------

    def _build_ai_panel(self, symbol: str, ai_text: str) -> QFrame:
        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER};"
            f" border-radius:4px; }}"
        )
        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        # Header
        hdr = QHBoxLayout()
        hdr.addWidget(_lbl("AI RESEARCH REPORT", 12, CYAN, bold=True))
        hdr.addStretch()
        hdr.addWidget(_lbl("Analysis-only · no buy/sell recommendation", 8, MUTED))
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

        # Bias chip
        bias_chip = _lbl(f"  {bias}  ", 11, bias_color, bold=True)
        bias_chip.setStyleSheet(
            f"color:{bias_color}; font-size:11px; font-weight:bold;"
            f" background:{BG}; border:1px solid {bias_color}; border-radius:3px;"
            f" padding:2px 6px;"
        )
        lay.addWidget(bias_chip)

        # Executive summary bullets
        summary_items = report_parser.collect_bullets(
            report_parser.sections_matching(parsed, "executive", "conclusion", "summary", "overall")
        )
        if summary_items:
            lay.addWidget(_lbl("EXECUTIVE SUMMARY", 9, MUTED, bold=True))
            for item in summary_items[:5]:
                lbl = _lbl(f"• {item}", 10, TEXT)
                lbl.setWordWrap(True)
                lay.addWidget(lbl)

        # Full report text (scrollable)
        text_edit = QPlainTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        text_edit.setPlainText(ai_text)
        text_edit.setStyleSheet(
            f"QPlainTextEdit {{ background:{BG}; color:{SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-size:10px; font-family:Consolas; padding:8px; }}"
        )
        text_edit.setMinimumHeight(200)
        lay.addWidget(text_edit, 1)

        return frame
