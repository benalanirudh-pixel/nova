"""
Market Overview page — Bloomberg-style market dashboard.

Shows NIFTY 50, BANK NIFTY, India VIX cards with candlestick charts,
market breadth, sector intelligence, derivatives, institutional flows,
risk context, and event risk. All data from the real Market Lab pipeline.
"""

from __future__ import annotations

import time
import traceback
from datetime import datetime, timezone, timedelta

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from market_lab.market_lab_data import get_market_lab_data, save_json_report, CACHE_DIR
from market_lab import view_model as vm
from market_lab import widgets as W

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SIDEBAR, HEADER,
    BORDER, BORDER_BRIGHT, BORDER_DIM,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, BLUE, CYAN, PURPLE,
    BG_SUCCESS, BG_WARNING, BG_ERROR, BG_INFO,
    FONT_UI, FONT_MONO,
    FONT_SIZE_CAPTION, FONT_SIZE_SMALL, FONT_SIZE_REGULAR,
    FONT_SIZE_MEDIUM, FONT_SIZE_LARGE, FONT_SIZE_XLARGE,
    SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG,
    BORDER_RADIUS_SM, BORDER_RADIUS_MD,
    GUARDRAIL_TEXT,
    freshness_level, freshness_color,
)

IST = timezone(timedelta(hours=5, minutes=30))

N_A = vm.N_A


def _lbl(text="", size=10, color=TEXT, bold=False, mono=False):
    label = QLabel("" if text is None else str(text))
    family = FONT_MONO if mono else FONT_UI
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    label.setFont(QFont(family, size, weight))
    label.setStyleSheet(f"color:{color}; background:transparent; border:none;")
    return label


def _sign_color(value):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return MUTED
    return GREEN if v >= 0 else RED


def _fmt_price(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:,.2f}"


def _fmt_pct(v, signed=True):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _fmt_num(v, places=2):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:,.{places}f}"


def _fmt_crore(v):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:+,.2f} Cr"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class _DataWorker(QThread):
    succeeded = Signal(object, float)
    failed = Signal(str, float)

    def __init__(self, force_refresh=False):
        super().__init__()
        self._refresh = force_refresh

    def run(self):
        t0 = time.perf_counter()
        try:
            report = get_market_lab_data(force_refresh=self._refresh)
            if isinstance(report, dict) and report:
                try:
                    save_json_report(report)
                except Exception:
                    traceback.print_exc()
            self.succeeded.emit(report, time.perf_counter() - t0)
        except Exception:
            self.failed.emit(traceback.format_exc(), time.perf_counter() - t0)


# ---------------------------------------------------------------------------
# Compact index card
# ---------------------------------------------------------------------------

class IndexCard(QFrame):
    """Compact card for an index (NIFTY / BANK NIFTY / VIX)."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._title = title
        self.setObjectName("indexCard")
        self.setStyleSheet(f"""
            QFrame#indexCard {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # Title row
        top = QHBoxLayout()
        top.setSpacing(8)
        self._title_label = _lbl(title, 9, MUTED, bold=True)
        top.addWidget(self._title_label)
        top.addStretch(1)
        self._source_label = _lbl("", 7, MUTED2, mono=True)
        top.addWidget(self._source_label)
        layout.addLayout(top)

        # Price row
        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        self._price = _lbl("—", 20, TEXT, bold=True, mono=True)
        price_row.addWidget(self._price)
        self._change = _lbl("", 11, MUTED, mono=True)
        price_row.addWidget(self._change)
        self._pct = _lbl("", 11, MUTED, mono=True)
        price_row.addWidget(self._pct)
        price_row.addStretch(1)
        layout.addLayout(price_row)

        # Metrics row
        self._metrics_row = QHBoxLayout()
        self._metrics_row.setSpacing(16)
        layout.addLayout(self._metrics_row)

        # Chart placeholder
        self._chart_frame = QFrame()
        self._chart_frame.setFixedHeight(100)
        self._chart_frame.setStyleSheet(
            f"background: {BG}; border: 1px solid {BORDER_DIM}; border-radius: 4px;"
        )
        layout.addWidget(self._chart_frame)

        self._chart_layout = QVBoxLayout(self._chart_frame)
        self._chart_layout.setContentsMargins(0, 0, 0, 0)

    def set_data(self, price, change, pct_change, source=None, metrics=None):
        self._price.setText(_fmt_price(price))
        color = _sign_color(change)

        if isinstance(change, (int, float)) and not isinstance(change, bool):
            self._change.setText(f"{change:+,.2f}")
            self._change.setStyleSheet(
                f"color:{color}; background:transparent; border:none;"
            )
        else:
            self._change.setText("")

        if isinstance(pct_change, (int, float)) and not isinstance(pct_change, bool):
            self._pct.setText(f"({pct_change:+.2f}%)")
            self._pct.setStyleSheet(
                f"color:{color}; background:transparent; border:none;"
            )
        else:
            self._pct.setText("")

        if source:
            self._source_label.setText(source)

        if metrics:
            while self._metrics_row.count():
                item = self._metrics_row.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            for key, val, clr in metrics:
                chip = _lbl(f"{key}: {val}", 8, clr or SECONDARY, mono=True)
                self._metrics_row.addWidget(chip)
            self._metrics_row.addStretch(1)

    def set_chart(self, widget):
        while self._chart_layout.count():
            item = self._chart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._chart_layout.addWidget(widget)


# ---------------------------------------------------------------------------
# Breadth bar
# ---------------------------------------------------------------------------

class BreadthBar(QWidget):
    """Visual advances/declines bar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(32)
        self._adv = 0
        self._dec = 0
        self._unch = 0

    def set_data(self, adv, dec, unch):
        self._adv = adv or 0
        self._dec = dec or 0
        self._unch = unch or 0
        self.update()

    def paintEvent(self, event):
        total = self._adv + self._dec + self._unch
        if total == 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        r = 4

        adv_w = max(1, int(w * self._adv / total))
        dec_w = max(1, int(w * self._dec / total))
        unch_w = w - adv_w - dec_w

        p.setBrush(QColor(GREEN))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, adv_w, h, r, r)

        p.setBrush(QColor(AMBER))
        p.drawRect(adv_w, 0, unch_w, h)

        p.setBrush(QColor(RED))
        p.drawRoundedRect(adv_w + unch_w, 0, dec_w, h, r, r)

        # Labels
        p.setPen(QColor("#000000"))
        font = QFont(FONT_MONO, 8, QFont.Weight.Bold)
        p.setFont(font)
        if adv_w > 30:
            p.drawText(4, 0, adv_w - 8, h, Qt.AlignmentFlag.AlignVCenter, str(self._adv))
        if dec_w > 30:
            p.drawText(
                adv_w + unch_w + 4, 0, dec_w - 8, h,
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                str(self._dec),
            )
        p.end()


# ---------------------------------------------------------------------------
# Section panel
# ---------------------------------------------------------------------------

def _section(title, subtitle=None):
    frame = QFrame()
    frame.setObjectName("sectionPanel")
    frame.setStyleSheet(f"""
        QFrame#sectionPanel {{
            background: {SURFACE};
            border: 1px solid {BORDER};
            border-radius: 8px;
        }}
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 10, 14, 12)
    layout.setSpacing(8)
    layout.addWidget(_lbl(title.upper(), 9, CYAN, bold=True))
    if subtitle:
        layout.addWidget(_lbl(subtitle, 8, MUTED))
    return frame, layout


def _kv_row(key, value, color=SECONDARY):
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_lbl(key, 9, MUTED))
    row.addStretch(1)
    row.addWidget(_lbl(str(value), 9, color, mono=True))
    return row


# ---------------------------------------------------------------------------
# Market Overview page
# ---------------------------------------------------------------------------

class MarketOverviewPage(QWidget):
    regime_changed = Signal(str, str)
    scanner_age_changed = Signal(str, str)
    report_loaded = Signal(object)  # emits the report dict

    def __init__(self, terminal, parent=None):
        super().__init__(parent)
        self.terminal = terminal
        self.report = None
        self._worker = None

        self._build_ui()
        QTimer.singleShot(100, self._load_cached_report)

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"background: {BG}; border: none;")

        self._content = QWidget()
        self._content.setStyleSheet(f"background: {BG};")
        self._layout = QVBoxLayout(self._content)
        self._layout.setContentsMargins(16, 12, 16, 16)
        self._layout.setSpacing(12)

        # Top bar: regime + refresh + freshness
        top = QHBoxLayout()
        top.setSpacing(12)
        self._regime_label = _lbl("MARKET REGIME: —", 11, AMBER, bold=True)
        top.addWidget(self._regime_label)
        top.addStretch(1)

        self._freshness_badge = W.FreshnessBadge()
        top.addWidget(self._freshness_badge)

        self._refresh_btn = QPushButton("REFRESH")
        self._refresh_btn.setFixedHeight(30)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {SURFACE};
                color: {CYAN};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0 16px;
            }}
            QPushButton:hover {{
                border-color: {CYAN};
                background: {SURFACE_ALT};
            }}
            QPushButton:disabled {{
                color: {MUTED2};
                border-color: {BORDER_DIM};
            }}
        """)
        self._refresh_btn.clicked.connect(self._do_refresh)
        top.addWidget(self._refresh_btn)

        self._layout.addLayout(top)

        # Index cards row
        cards_row = QHBoxLayout()
        cards_row.setSpacing(12)

        self._nifty_card = IndexCard("NIFTY 50")
        self._banknifty_card = IndexCard("BANK NIFTY")
        self._vix_card = IndexCard("INDIA VIX")
        cards_row.addWidget(self._nifty_card, 1)
        cards_row.addWidget(self._banknifty_card, 1)
        cards_row.addWidget(self._vix_card, 1)
        self._layout.addLayout(cards_row)

        # Range selector
        range_row = QHBoxLayout()
        range_row.setSpacing(4)
        range_row.addStretch(1)
        self._range_buttons = {}
        for rng in ["1W", "1M", "3M", "6M"]:
            btn = QPushButton(rng)
            btn.setCheckable(True)
            btn.setChecked(rng == "3M")
            btn.setFixedSize(48, 24)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(FONT_MONO, 8))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {SURFACE};
                    color: {SECONDARY};
                    border: 1px solid {BORDER};
                    border-radius: 4px;
                }}
                QPushButton:checked {{
                    background: {SURFACE_ALT};
                    color: {CYAN};
                    border-color: {CYAN};
                }}
                QPushButton:hover {{
                    border-color: {BORDER_BRIGHT};
                }}
            """)
            btn.clicked.connect(lambda _, r=rng: self._set_range(r))
            range_row.addWidget(btn)
            self._range_buttons[rng] = btn
        self._chart_range = "3M"
        self._layout.addLayout(range_row)

        # Breadth section
        breadth_frame, breadth_lay = _section("MARKET BREADTH")
        self._breadth_bar = BreadthBar()
        breadth_lay.addWidget(self._breadth_bar)

        breadth_stats = QHBoxLayout()
        breadth_stats.setSpacing(16)
        self._breadth_adv = _lbl("ADV: —", 9, GREEN, mono=True)
        self._breadth_dec = _lbl("DEC: —", 9, RED, mono=True)
        self._breadth_unch = _lbl("UNCH: —", 9, AMBER, mono=True)
        self._breadth_ema20 = _lbl("EMA20: —", 9, CYAN, mono=True)
        self._breadth_ema50 = _lbl("EMA50: —", 9, PURPLE, mono=True)
        breadth_stats.addWidget(self._breadth_adv)
        breadth_stats.addWidget(self._breadth_dec)
        breadth_stats.addWidget(self._breadth_unch)
        breadth_stats.addWidget(self._breadth_ema20)
        breadth_stats.addWidget(self._breadth_ema50)
        breadth_stats.addStretch(1)
        breadth_lay.addLayout(breadth_stats)
        self._layout.addWidget(breadth_frame)

        # Two-column: Sectors + Volatility
        mid_row = QHBoxLayout()
        mid_row.setSpacing(12)

        # Sectors
        self._sector_frame, self._sector_lay = _section("SECTOR INTELLIGENCE")
        mid_row.addWidget(self._sector_frame, 1)

        # Volatility
        self._vol_frame, self._vol_lay = _section("VOLATILITY")
        mid_row.addWidget(self._vol_frame, 1)
        self._layout.addLayout(mid_row)

        # Two-column: Derivatives + Institutional Flow
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        self._deriv_frame, self._deriv_lay = _section("DERIVATIVES")
        bottom_row.addWidget(self._deriv_frame, 1)

        self._flow_frame, self._flow_lay = _section("INSTITUTIONAL FLOWS")
        bottom_row.addWidget(self._flow_frame, 1)
        self._layout.addLayout(bottom_row)

        # Risk + Event risk row
        risk_row = QHBoxLayout()
        risk_row.setSpacing(12)

        self._risk_frame, self._risk_lay = _section("RISK CONTEXT")
        risk_row.addWidget(self._risk_frame, 1)

        self._event_frame, self._event_lay = _section("EVENT RISK")
        risk_row.addWidget(self._event_frame, 1)
        self._layout.addLayout(risk_row)

        # Factor rankings
        self._factor_frame, self._factor_lay = _section("FACTOR RANKINGS", "Cross-sectional composite")
        self._layout.addWidget(self._factor_frame)

        # Data availability
        self._avail_frame, self._avail_lay = _section("DATA AVAILABILITY")
        self._layout.addWidget(self._avail_frame)

        self._layout.addStretch(1)

        scroll.setWidget(self._content)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_cached_report(self):
        from pathlib import Path
        import json as _json

        report_dir = Path(CACHE_DIR) / "market_lab"
        if not report_dir.is_dir():
            self._do_refresh()
            return

        try:
            files = sorted(
                report_dir.glob("market_lab_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
        except OSError:
            self._do_refresh()
            return

        for path in files:
            try:
                with path.open("r", encoding="utf-8") as f:
                    report = _json.load(f)
                if isinstance(report, dict) and report:
                    self.report = report
                    self._populate(report)
                    self.report_loaded.emit(report)
                    return
            except (OSError, ValueError, _json.JSONDecodeError):
                continue

        self._do_refresh()

    def _do_refresh(self, force=False):
        if self._worker is not None and self._worker.isRunning():
            return
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.setText("LOADING...")
        self._worker = _DataWorker(force_refresh=force)
        self._worker.succeeded.connect(self._on_data)
        self._worker.failed.connect(self._on_error)
        self._worker.start()

    def _on_data(self, report, elapsed):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("REFRESH")
        if not isinstance(report, dict) or not report:
            return
        self.report = report
        self._populate(report)
        self.report_loaded.emit(report)

    def _on_error(self, tb, elapsed):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("REFRESH")
        print(f"Market data error ({elapsed:.1f}s):\n{tb}")

    # ------------------------------------------------------------------
    # Populate dashboard
    # ------------------------------------------------------------------

    def _populate(self, report):
        # Regime
        macro = vm.macro(report)
        regime_text = str(macro.get("market_regime", "UNKNOWN")).upper()
        regime_color = self._regime_color(regime_text)
        self._regime_label.setText(f"MARKET REGIME: {regime_text}")
        self._regime_label.setStyleSheet(
            f"color: {regime_color}; background: transparent; border: none;"
        )
        self.regime_changed.emit(regime_text, regime_color)

        # Freshness
        age_info = vm.data_age(report)
        age_sec = age_info.get("age_seconds")
        if age_sec is not None:
            level = freshness_level(int(age_sec))
            color = freshness_color(level)
            self._freshness_badge.set_age(level, age_info.get("label", "—"))
            self.scanner_age_changed.emit(age_info.get("label", "—"), color)

        # Index cards
        self._populate_nifty(report)
        self._populate_banknifty(report)
        self._populate_vix(report)

        # Breadth
        self._populate_breadth(report)

        # Sections
        self._populate_sectors(report)
        self._populate_volatility(report)
        self._populate_derivatives(report)
        self._populate_flows(report)
        self._populate_risk(report)
        self._populate_event_risk(report)
        self._populate_factors(report)
        self._populate_availability(report)

    def _regime_color(self, label):
        label = label.upper()
        if "BULLISH" in label and "MILDLY" not in label:
            return GREEN
        if "MILDLY_BULLISH" in label or "MILDLY BULLISH" in label:
            return "#66CC88"
        if "BEARISH" in label and "MILDLY" not in label:
            return RED
        if "MILDLY_BEARISH" in label or "MILDLY BEARISH" in label:
            return AMBER
        return AMBER

    def _populate_nifty(self, report):
        card = vm.index_card(report, "nifty")
        price = card.get("price")
        change = card.get("change_abs")
        pct = card.get("change_percent")
        source = card.get("source_label", "")

        metrics = []
        for period, key in [("5D", "return_5d"), ("20D", "return_20d"), ("60D", "return_60d")]:
            val = card.get(key)
            if isinstance(val, (int, float)):
                metrics.append((period, _fmt_pct(val), _sign_color(val)))

        self._nifty_card.set_data(price, change, pct, source=source, metrics=metrics)

        candles = self._slice_candles(card.get("candles", []))
        if candles:
            try:
                chart = W.PgCandleChart(candles, title="")
                chart.setFixedHeight(96)
                self._nifty_card.set_chart(chart)
            except Exception:
                pass

    def _populate_banknifty(self, report):
        card = vm.index_card(report, "bank_nifty")
        price = card.get("price")
        change = card.get("change_abs")
        pct = card.get("change_percent")

        metrics = []
        for period, key in [("5D", "return_5d"), ("20D", "return_20d"), ("60D", "return_60d")]:
            val = card.get(key)
            if isinstance(val, (int, float)):
                metrics.append((period, _fmt_pct(val), _sign_color(val)))

        self._banknifty_card.set_data(price, change, pct, metrics=metrics)

        candles = self._slice_candles(card.get("candles", []))
        if candles:
            try:
                chart = W.PgCandleChart(candles, title="")
                chart.setFixedHeight(96)
                self._banknifty_card.set_chart(chart)
            except Exception:
                pass

    def _populate_vix(self, report):
        vix = vm.vix_card(report)
        value = vix.get("value")
        change_pct = vix.get("change_percent")
        regime = vix.get("regime", "")

        metrics = []
        if regime and regime != N_A:
            color_map = {"LOW": GREEN, "MODERATE": AMBER, "HIGH": RED, "EXTREME": RED}
            metrics.append(("REGIME", str(regime), color_map.get(str(regime).upper(), AMBER)))

        self._vix_card.set_data(value, vix.get("change_abs"), change_pct, metrics=metrics)

        candles = self._slice_candles(vix.get("candles", []))
        if candles:
            try:
                chart = W.PgCandleChart(candles, title="")
                chart.setFixedHeight(96)
                self._vix_card.set_chart(chart)
            except Exception:
                pass

    def _slice_candles(self, candles):
        if not candles:
            return candles
        range_map = {"1W": 5, "1M": 22, "3M": 66, "6M": 132}
        n = range_map.get(self._chart_range, 66)
        return candles[-n:]

    def _populate_breadth(self, report):
        breadth = vm.breadth_block(report)
        adv = breadth.get("advancing", 0)
        dec = breadth.get("declining", 0)
        unch = breadth.get("unchanged", 0)
        ema20 = breadth.get("above_ema20_percent")
        ema50 = breadth.get("above_ema50_percent")

        self._breadth_bar.set_data(adv, dec, unch)
        self._breadth_adv.setText(f"ADV: {adv}")
        self._breadth_dec.setText(f"DEC: {dec}")
        self._breadth_unch.setText(f"UNCH: {unch}")

        if isinstance(ema20, (int, float)):
            self._breadth_ema20.setText(f"EMA20: {ema20:.1f}%")
        if isinstance(ema50, (int, float)):
            self._breadth_ema50.setText(f"EMA50: {ema50:.1f}%")

    def _populate_sectors(self, report):
        self._clear_layout(self._sector_lay, keep=1)
        sectors = vm.sector_rows(report, limit=10)
        if not sectors:
            self._sector_lay.addWidget(_lbl("No sector data available", 9, MUTED))
            return

        for s in sectors:
            name = s.get("name", "?")
            ret = s.get("return_20d")
            regime = s.get("regime", "")
            color = _sign_color(ret)
            row = QHBoxLayout()
            row.addWidget(_lbl(name, 9, TEXT))
            row.addStretch(1)
            if regime:
                row.addWidget(_lbl(regime, 8, MUTED))
            row.addWidget(_lbl(_fmt_pct(ret), 9, color, mono=True))
            self._sector_lay.addLayout(row)

    def _populate_volatility(self, report):
        self._clear_layout(self._vol_lay, keep=1)
        nifty_ind = vm.indicator_cards(report, "nifty")
        bnifty_ind = vm.indicator_cards(report, "bank_nifty")

        atr = nifty_ind.get("ATR", {})
        vol = nifty_ind.get("VOL", {})

        for label, val in [
            ("NIFTY ATR", atr.get("value")),
            ("NIFTY ATR %", atr.get("percent")),
            ("NIFTY RV 20D", vol.get("value")),
        ]:
            self._vol_lay.addLayout(_kv_row(label, _fmt_num(val), SECONDARY))

        bn_atr = bnifty_ind.get("ATR", {})
        self._vol_lay.addLayout(_kv_row("BNIFTY ATR", _fmt_num(bn_atr.get("value")), SECONDARY))

        macro = vm.macro(report)
        regime = macro.get("vix_regime", "")
        direction = macro.get("vix_direction", "")
        if regime and regime != N_A:
            color_map = {"LOW": GREEN, "MODERATE": AMBER, "HIGH": RED, "EXTREME": RED}
            self._vol_lay.addLayout(
                _kv_row("VIX REGIME", str(regime), color_map.get(str(regime).upper(), AMBER))
            )
        if direction and direction != N_A:
            self._vol_lay.addLayout(_kv_row("DIRECTION", str(direction), SECONDARY))

    def _populate_derivatives(self, report):
        self._clear_layout(self._deriv_lay, keep=1)

        for index_name in ["nifty", "banknifty"]:
            d = vm.derivatives_block(report, index_name)
            if not d.get("available"):
                continue
            self._deriv_lay.addWidget(_lbl(d.get("instrument", index_name.upper()), 9, CYAN, bold=True))
            for key, label in [
                ("oi_pcr", "PCR (OI)"),
                ("volume_pcr", "PCR (Vol)"),
                ("max_pain", "Max Pain"),
                ("atm_iv", "ATM IV"),
            ]:
                val = d.get(key)
                if val is not None:
                    self._deriv_lay.addLayout(_kv_row(f"  {label}", _fmt_num(val), SECONDARY))

            interp = d.get("interpretation", N_A)
            if interp and interp != N_A:
                self._deriv_lay.addWidget(_lbl(f"  {interp}", 8, MUTED))

        if self._deriv_lay.count() <= 1:
            self._deriv_lay.addWidget(_lbl("No derivatives data", 9, MUTED))

    def _populate_flows(self, report):
        self._clear_layout(self._flow_lay, keep=1)
        flow = vm.flow_block(report)
        if not flow.get("available"):
            self._flow_lay.addWidget(_lbl("No flow data available", 9, MUTED))
            return

        for key, label in [
            ("fii_5d", "FII Net 5D"),
            ("fii_10d", "FII Net 10D"),
            ("dii_5d", "DII Net 5D"),
            ("dii_10d", "DII Net 10D"),
        ]:
            val = flow.get(key)
            color = _sign_color(val)
            self._flow_lay.addLayout(_kv_row(label, _fmt_crore(val), color))

        regime = flow.get("flow_regime")
        if regime and regime != N_A:
            self._flow_lay.addLayout(_kv_row("FLOW REGIME", str(regime), AMBER))

    def _populate_risk(self, report):
        self._clear_layout(self._risk_lay, keep=1)
        risk = vm.risk_cards(report)

        color_map = {
            "HIGH": RED, "CRITICAL": RED, "SEVERE": RED,
            "MODERATE": AMBER, "ELEVATED": AMBER,
            "LOW": GREEN, "MINIMAL": GREEN,
        }

        vol_regime = risk.get("vol_regime", N_A)
        c = color_map.get(str(vol_regime).upper(), AMBER) if vol_regime != N_A else MUTED
        self._risk_lay.addLayout(_kv_row("Vol Regime", str(vol_regime), c))

        for key, label in [
            ("realized_vol_20d", "RV 20D"),
            ("atr_pct", "ATR %"),
            ("vol_percentile", "Vol Percentile"),
            ("expected_daily_move", "Exp Daily Move %"),
        ]:
            val = risk.get(key)
            self._risk_lay.addLayout(_kv_row(label, _fmt_num(val), SECONDARY))

        note = risk.get("note", "")
        if note:
            self._risk_lay.addWidget(_lbl(note, 7, MUTED2))

    def _populate_event_risk(self, report):
        self._clear_layout(self._event_lay, keep=1)
        ctx = report.get("event_risk_context")
        if not isinstance(ctx, dict) or not ctx:
            self._event_lay.addWidget(_lbl("No event-risk context", 9, MUTED))
            return

        overall = ctx.get("overall_risk", "UNKNOWN")
        color_map = {"HIGH": RED, "MODERATE": AMBER, "LOW": GREEN}
        c = color_map.get(overall.upper(), AMBER)
        self._event_lay.addLayout(_kv_row("Overall Event Risk", overall, c))

        events = ctx.get("upcoming_events", [])
        if isinstance(events, list):
            for ev in events[:5]:
                if not isinstance(ev, dict):
                    continue
                name = ev.get("name", "?")
                severity = str(ev.get("severity", "")).upper()
                sc = color_map.get(severity, AMBER)
                self._event_lay.addLayout(_kv_row(f"  {name}", severity, sc))

    def _populate_factors(self, report):
        self._clear_layout(self._factor_lay, keep=2)
        fb = vm.factor_block(report)
        if fb.get("status") != "AVAILABLE":
            self._factor_lay.addWidget(_lbl("No factor data", 9, MUTED))
            return

        top = fb.get("top", [])
        bottom = fb.get("bottom", [])

        if top:
            self._factor_lay.addWidget(_lbl("TOP RANKED", 8, GREEN, bold=True))
            for stock in top[:5]:
                sym = stock.get("symbol", "?")
                z = stock.get("composite_z")
                self._factor_lay.addLayout(
                    _kv_row(f"  {sym}", _fmt_num(z), GREEN)
                )

        if bottom:
            self._factor_lay.addWidget(_lbl("BOTTOM RANKED", 8, RED, bold=True))
            for stock in bottom[:5]:
                sym = stock.get("symbol", "?")
                z = stock.get("composite_z")
                self._factor_lay.addLayout(
                    _kv_row(f"  {sym}", _fmt_num(z), RED)
                )

    def _populate_availability(self, report):
        self._clear_layout(self._avail_lay, keep=1)
        avail = report.get("data_availability")
        if not isinstance(avail, dict):
            return

        for key, val in avail.items():
            is_ok = str(val).upper() == "AVAILABLE"
            color = GREEN if is_ok else RED
            self._avail_lay.addLayout(_kv_row(key.replace("_", " ").title(), str(val), color))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _clear_layout(self, layout, keep=0):
        while layout.count() > keep:
            item = layout.takeAt(keep)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sub_layout(item.layout())

    def _clear_sub_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                self._clear_sub_layout(item.layout())

    def _set_range(self, rng):
        self._chart_range = rng
        for r, btn in self._range_buttons.items():
            btn.setChecked(r == rng)
        if self.report:
            self._populate_nifty(self.report)
            self._populate_banknifty(self.report)
            self._populate_vix(self.report)

    def shutdown(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(3000)
