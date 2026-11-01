"""
Market Analysis page — Nifty deep-dive with derivatives, technicals, and regime.

Hero bar (price + badges), candlestick chart with OI wall overlays,
technicals grid, derivatives desk, OI wall bars, regime assessment,
unusual options alerts, positioning intelligence, AI narrative.
"""
from __future__ import annotations

import traceback
from datetime import datetime, timezone, timedelta

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont, QColor, QPainter, QPen, QBrush
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from market_lab import view_model as vm
from market_lab import widgets as W

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT,
    BORDER, BORDER_BRIGHT, BORDER_DIM,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, BLUE, CYAN, PURPLE,
    BG_SUCCESS, BG_WARNING, BG_ERROR, BG_INFO,
    FONT_UI, FONT_MONO,
    GUARDRAIL_TEXT,
    freshness_level, freshness_color,
)

try:
    from market_lab.market_lab_brain import analyze_market_lab
    _BRAIN_OK = True
except Exception:
    _BRAIN_OK = False

    def analyze_market_lab(*_a, **_kw):  # type: ignore[misc]
        return "Market Lab brain not available."

IST = timezone(timedelta(hours=5, minutes=30))

N_A = vm.N_A


# =====================================================================
# Helpers
# =====================================================================

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
    return f"₹{v:,.2f}"


def _fmt_pct(v, signed=True):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:+.2f}%" if signed else f"{v:.2f}%"


def _fmt_num(v, places=2):
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return N_A
    return f"{v:,.{places}f}"


def _kv_row(key, value, color=SECONDARY):
    row = QHBoxLayout()
    row.setSpacing(4)
    row.addWidget(_lbl(key, 8, MUTED, mono=True))
    row.addStretch(1)
    row.addWidget(_lbl(value, 9, color, mono=True, bold=True))
    return row


# =====================================================================
# Panel widget (reusable titled panel)
# =====================================================================

class _Panel(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(10, 8, 10, 8)
        self._outer.setSpacing(4)

        self._title_lbl = _lbl(title, 8, CYAN, bold=True)
        self._outer.addWidget(self._title_lbl)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {BORDER_DIM};")
        self._outer.addWidget(sep)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(2)
        self._outer.addLayout(self._content_layout, 1)

    @property
    def content(self):
        return self._content_layout

    def clear_content(self):
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                _clear_sub(item.layout())


def _clear_sub(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_sub(item.layout())


# =====================================================================
# OI Wall bar widget (horizontal bar for put/call walls)
# =====================================================================

class _OIWallBar(QWidget):
    """Horizontal stacked bar showing put and call OI walls relative to spot."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._put_wall = None
        self._call_wall = None
        self._spot = None
        self._max_pain = None
        self.setFixedHeight(28)

    def set_data(self, put_wall, call_wall, spot, max_pain=None):
        self._put_wall = put_wall
        self._call_wall = call_wall
        self._spot = spot
        self._max_pain = max_pain
        self.update()

    def paintEvent(self, event):
        if self._put_wall is None or self._call_wall is None or self._spot is None:
            return
        try:
            put = float(self._put_wall)
            call = float(self._call_wall)
            spot = float(self._spot)
        except (TypeError, ValueError):
            return

        lo = min(put, spot) - 50
        hi = max(call, spot) + 50
        span = hi - lo
        if span <= 0:
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()

        # Background
        p.setBrush(QBrush(QColor(BORDER_DIM)))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(0, 0, w, h, 4, 4)

        def x_pos(val):
            return int((float(val) - lo) / span * w)

        # Put wall zone (green tint)
        put_x = x_pos(put)
        p.setBrush(QBrush(QColor(GREEN)))
        p.setOpacity(0.3)
        p.drawRect(put_x - 2, 0, 4, h)
        p.setOpacity(1.0)

        # Call wall zone (red tint)
        call_x = x_pos(call)
        p.setBrush(QBrush(QColor(RED)))
        p.setOpacity(0.3)
        p.drawRect(call_x - 2, 0, 4, h)
        p.setOpacity(1.0)

        # Spot line
        spot_x = x_pos(spot)
        pen = QPen(QColor(CYAN), 2)
        p.setPen(pen)
        p.drawLine(spot_x, 2, spot_x, h - 2)

        # Max pain marker
        if self._max_pain is not None:
            try:
                mp_x = x_pos(float(self._max_pain))
                pen_mp = QPen(QColor(AMBER), 2, Qt.PenStyle.DashLine)
                p.setPen(pen_mp)
                p.drawLine(mp_x, 2, mp_x, h - 2)
            except (TypeError, ValueError):
                pass

        # Labels
        p.setPen(QPen(QColor(TEXT)))
        font = QFont(FONT_MONO, 7)
        p.setFont(font)
        p.drawText(put_x - 20, h - 3, f"P:{int(put)}")
        p.drawText(call_x + 4, h - 3, f"C:{int(call)}")

        p.end()


# =====================================================================
# Badge widget (regime / trend / volatility)
# =====================================================================

class _Badge(QFrame):
    def __init__(self, text="—", color=MUTED, parent=None):
        super().__init__(parent)
        self._lbl = _lbl(text, 8, color, bold=True, mono=True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lay.addWidget(self._lbl)
        self.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE_ALT};
                border: 1px solid {BORDER};
                border-radius: 10px;
            }}
        """)
        self.setFixedHeight(22)

    def set_text(self, text, color=None):
        self._lbl.setText(str(text))
        if color:
            self._lbl.setStyleSheet(
                f"color:{color}; background:transparent; border:none;"
                f" font-size:8px; font-weight:bold; font-family:'{FONT_MONO}';"
            )


# =====================================================================
# Main page
# =====================================================================

class MarketAnalysisPage(QWidget):
    """Nifty deep-dive: chart, derivatives, technicals, regime, AI."""

    regime_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report = None
        self._chart_range = "3M"
        self._narrating = False
        self.setStyleSheet(f"background: {BG};")
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 4)
        outer.setSpacing(6)

        # Row 0: Hero bar
        outer.addLayout(self._build_hero_bar())

        # Row 1: Main grid (chart + side panels)
        grid = QHBoxLayout()
        grid.setSpacing(6)

        # Left column (~60%): chart + technicals + derivatives
        left = QVBoxLayout()
        left.setSpacing(6)
        left.addLayout(self._build_chart_header())
        left.addWidget(self._build_chart_frame(), 1)
        left.addLayout(self._build_technicals_derivatives())
        grid.addLayout(left, 60)

        # Right column (~40%): OI walls, regime, unusual, positioning, AI
        right = QVBoxLayout()
        right.setSpacing(6)

        self._oi_panel = _Panel("OI WALLS & STRUCTURE")
        right.addWidget(self._oi_panel, 1)

        self._regime_panel = _Panel("REGIME ASSESSMENT")
        right.addWidget(self._regime_panel, 1)

        self._unusual_panel = _Panel("UNUSUAL OPTIONS ACTIVITY")
        right.addWidget(self._unusual_panel, 1)

        self._positioning_panel = _Panel("POSITIONING INTELLIGENCE")
        right.addWidget(self._positioning_panel, 1)

        self._ai_panel = _Panel("AI NARRATIVE")
        right.addWidget(self._ai_panel, 1)

        grid.addLayout(right, 40)
        outer.addLayout(grid, 1)

        # Bottom: guardrails bar
        outer.addWidget(self._build_guardrails_bar())

    # ------------------------------------------------------------------
    # Hero bar
    # ------------------------------------------------------------------

    def _build_hero_bar(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        self._hero_title = _lbl("NIFTY 50", 12, TEXT, bold=True)
        row.addWidget(self._hero_title)

        self._hero_price = _lbl("—", 16, TEXT, bold=True, mono=True)
        row.addWidget(self._hero_price)

        self._hero_change = _lbl("", 10, MUTED, mono=True)
        row.addWidget(self._hero_change)

        row.addSpacing(12)

        self._badge_regime = _Badge("REGIME: —", AMBER)
        row.addWidget(self._badge_regime)

        self._badge_trend = _Badge("TREND: —", MUTED)
        row.addWidget(self._badge_trend)

        self._badge_vol = _Badge("VOL: —", MUTED)
        row.addWidget(self._badge_vol)

        row.addStretch(1)

        # Range buttons
        self._range_buttons = {}
        for rng in ["1M", "3M", "6M"]:
            btn = QPushButton(rng)
            btn.setCheckable(True)
            btn.setChecked(rng == "3M")
            btn.setFixedSize(40, 22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFont(QFont(FONT_MONO, 7))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: {SURFACE};
                    color: {SECONDARY};
                    border: 1px solid {BORDER};
                    border-radius: 3px;
                }}
                QPushButton:checked {{
                    background: {SURFACE_ALT};
                    color: {CYAN};
                    border-color: {CYAN};
                }}
                QPushButton:hover {{ border-color: {BORDER_BRIGHT}; }}
            """)
            btn.clicked.connect(lambda _, r=rng: self._set_range(r))
            row.addWidget(btn)
            self._range_buttons[rng] = btn

        row.addSpacing(8)

        self._freshness_badge = W.FreshnessBadge()
        row.addWidget(self._freshness_badge)

        # AI Narrate button
        self._narrate_btn = QPushButton("AI NARRATE")
        self._narrate_btn.setFixedHeight(26)
        self._narrate_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._narrate_btn.setFont(QFont(FONT_UI, 8, QFont.Weight.Bold))
        self._narrate_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CYAN};
                color: #000;
                border: none;
                border-radius: 4px;
                padding: 0 14px;
                letter-spacing: 0.8px;
            }}
            QPushButton:hover {{ background: #33E8FF; }}
            QPushButton:pressed {{ background: #00B8D4; }}
            QPushButton:disabled {{ background: {BORDER}; color: {MUTED}; }}
        """)
        self._narrate_btn.clicked.connect(self._do_narrate)
        row.addWidget(self._narrate_btn)

        return row

    # ------------------------------------------------------------------
    # Chart header (OHLC + labels)
    # ------------------------------------------------------------------

    def _build_chart_header(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        row.addWidget(_lbl("NIFTY 50 — DAILY", 9, CYAN, bold=True))
        row.addStretch(1)

        self._ohlc_labels = {}
        for field in ["O", "H", "L", "C"]:
            lbl = _lbl(f"{field}: —", 8, SECONDARY, mono=True)
            self._ohlc_labels[field] = lbl
            row.addWidget(lbl)

        return row

    # ------------------------------------------------------------------
    # Chart frame
    # ------------------------------------------------------------------

    def _build_chart_frame(self):
        self._chart_frame = QFrame()
        self._chart_frame.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
        """)
        self._chart_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._chart_layout = QVBoxLayout(self._chart_frame)
        self._chart_layout.setContentsMargins(4, 4, 4, 4)
        self._chart_layout.setSpacing(0)

        self._chart_placeholder = _lbl("Loading chart…", 11, MUTED)
        self._chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._chart_layout.addWidget(self._chart_placeholder)

        return self._chart_frame

    # ------------------------------------------------------------------
    # Technicals + Derivatives (bottom of left column)
    # ------------------------------------------------------------------

    def _build_technicals_derivatives(self):
        row = QHBoxLayout()
        row.setSpacing(6)

        self._tech_panel = _Panel("TECHNICALS")
        row.addWidget(self._tech_panel, 1)

        self._deriv_panel = _Panel("DERIVATIVES DESK")
        row.addWidget(self._deriv_panel, 1)

        return row

    # ------------------------------------------------------------------
    # Guardrails bar
    # ------------------------------------------------------------------

    def _build_guardrails_bar(self):
        bar = QFrame()
        bar.setFixedHeight(22)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {SURFACE};
                border: 1px solid {BORDER};
                border-radius: 4px;
            }}
        """)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(0)

        layout.addWidget(_lbl(
            f"⚠ {GUARDRAIL_TEXT}", 7, AMBER, mono=True
        ))
        layout.addStretch(1)

        self._timestamp_lbl = _lbl("", 7, MUTED, mono=True)
        layout.addWidget(self._timestamp_lbl)

        return bar

    # ------------------------------------------------------------------
    # Public API: set_report()
    # ------------------------------------------------------------------

    def set_report(self, report):
        self._report = report
        self._populate(report)

    # ------------------------------------------------------------------
    # Range switching
    # ------------------------------------------------------------------

    def _set_range(self, rng):
        self._chart_range = rng
        for name, btn in self._range_buttons.items():
            btn.setChecked(name == rng)
        if self._report:
            self._populate_chart(self._report)

    def _slice_candles(self, candles):
        if not candles:
            return candles
        range_map = {"1M": 22, "3M": 66, "6M": 132}
        n = range_map.get(self._chart_range, 66)
        return candles[-n:]

    # ------------------------------------------------------------------
    # Populate everything
    # ------------------------------------------------------------------

    def _populate(self, report):
        self._populate_hero(report)
        self._populate_chart(report)
        self._populate_technicals(report)
        self._populate_derivatives(report)
        self._populate_oi_walls(report)
        self._populate_regime(report)
        self._populate_unusual(report)
        self._populate_positioning(report)
        self._update_freshness(report)

    # ------------------------------------------------------------------
    # Hero bar
    # ------------------------------------------------------------------

    def _populate_hero(self, report):
        card = vm.index_card(report, "nifty")
        price = card.get("price")
        change_pct = card.get("change_percent")

        self._hero_price.setText(_fmt_price(price))
        if change_pct is not None:
            try:
                pct = float(change_pct)
                color = GREEN if pct >= 0 else RED
                sign = "+" if pct >= 0 else ""
                self._hero_change.setText(f"{sign}{pct:.2f}%")
                self._hero_change.setStyleSheet(
                    f"color:{color}; background:transparent; border:none;"
                    f" font-size:10px; font-family:'{FONT_MONO}';"
                )
            except (TypeError, ValueError):
                self._hero_change.setText("")

        # Regime badge
        macro = vm.macro(report)
        regime = str(macro.get("market_regime", "—")).upper()
        regime_color = self._regime_color(regime)
        self._badge_regime.set_text(f"REGIME: {regime}", regime_color)
        self.regime_changed.emit(regime, regime_color)

        # Trend badge from nifty returns
        returns = report.get("nifty_returns") or {}
        r5d = returns.get("5D")
        r20d = returns.get("20D")
        if isinstance(r5d, (int, float)) and isinstance(r20d, (int, float)):
            if r5d > 0 and r20d > 0:
                trend, tc = "UPTREND", GREEN
            elif r5d < 0 and r20d < 0:
                trend, tc = "DOWNTREND", RED
            else:
                trend, tc = "SIDEWAYS", AMBER
            self._badge_trend.set_text(f"TREND: {trend}", tc)
        else:
            self._badge_trend.set_text("TREND: —", MUTED)

        # Vol badge
        vix = macro.get("india_vix")
        if vix is not None:
            try:
                vix_f = float(vix)
                if vix_f > 25:
                    vc = RED
                elif vix_f > 18:
                    vc = AMBER
                else:
                    vc = GREEN
                self._badge_vol.set_text(f"VIX: {vix_f:.1f}", vc)
            except (TypeError, ValueError):
                self._badge_vol.set_text("VIX: —", MUTED)

    # ------------------------------------------------------------------
    # Chart
    # ------------------------------------------------------------------

    def _populate_chart(self, report):
        while self._chart_layout.count():
            item = self._chart_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        card = vm.index_card(report, "nifty")
        candles = card.get("candles", [])

        # Update OHLC
        if candles:
            last = candles[-1]
            for field, key in [("O", "open"), ("H", "high"), ("L", "low"), ("C", "close")]:
                val = last.get(key)
                self._ohlc_labels[field].setText(
                    f"{field}: {_fmt_price(val)}" if isinstance(val, (int, float)) else f"{field}: —"
                )

        sliced = self._slice_candles(candles)
        if sliced:
            try:
                chart = W.PgCandleChart(parent=self._chart_frame)
                # Build indicator series from candles
                closes = [float(c.get("c", c.get("close", 0))) for c in candles
                          if isinstance(c, dict)]
                rsi, macd_line, signal_line, histogram = [], [], [], []

                if len(closes) >= 30:
                    try:
                        import pandas as pd
                        from analysis.data.technical_engine import (
                            calculate_rsi, calculate_macd,
                        )
                        s = pd.Series(closes)
                        if len(closes) >= 20:
                            rsi = calculate_rsi(s, 14).tolist()
                        if len(closes) >= 45:
                            m, sg, h = calculate_macd(s)
                            macd_line = m.tolist()
                            signal_line = sg.tolist()
                            histogram = h.tolist()
                    except Exception:
                        pass

                # Trim indicator series to match sliced candles
                n = len(sliced)
                rsi = rsi[-n:] if rsi else []
                macd_line = macd_line[-n:] if macd_line else []
                signal_line = signal_line[-n:] if signal_line else []
                histogram = histogram[-n:] if histogram else []

                chart.set_data(sliced, rsi, macd_line, signal_line, histogram)
                self._chart_layout.addWidget(chart)
            except Exception:
                traceback.print_exc()
                self._chart_layout.addWidget(
                    _lbl("Chart unavailable", 10, MUTED)
                )
        else:
            self._chart_layout.addWidget(
                _lbl("No candle data", 10, MUTED)
            )

    # ------------------------------------------------------------------
    # Technicals panel
    # ------------------------------------------------------------------

    def _populate_technicals(self, report):
        self._tech_panel.clear_content()
        lay = self._tech_panel.content

        indicators = vm.indicator_cards(report, "nifty")

        rsi = indicators.get("RSI", {})
        macd = indicators.get("MACD", {})
        atr = indicators.get("ATR", {})
        vol = indicators.get("VOL", {})

        rsi_val = rsi.get("value")
        rsi_color = MUTED
        if rsi_val is not None and rsi_val != N_A:
            try:
                rv = float(rsi_val)
                rsi_color = RED if rv > 70 else GREEN if rv < 30 else SECONDARY
            except (TypeError, ValueError):
                pass
        lay.addLayout(_kv_row("RSI 14", _fmt_num(rsi_val), rsi_color))
        if rsi.get("interpretation") and rsi["interpretation"] != N_A:
            lay.addWidget(_lbl(f"  {rsi['interpretation']}", 7, MUTED))

        macd_val = macd.get("value")
        macd_color = _sign_color(macd_val) if macd_val != N_A else MUTED
        lay.addLayout(_kv_row("MACD", _fmt_num(macd_val), macd_color))
        if macd.get("interpretation") and macd["interpretation"] != N_A:
            lay.addWidget(_lbl(f"  {macd['interpretation']}", 7, MUTED))

        lay.addLayout(_kv_row("ATR 14", _fmt_num(atr.get("value")), SECONDARY))
        lay.addLayout(_kv_row("ATR %", _fmt_num(atr.get("percent")), SECONDARY))
        lay.addLayout(_kv_row("RV 20D", _fmt_num(vol.get("value")), SECONDARY))

        # ADX from volatility data
        nifty_vol = (report.get("volatility") or {}).get("nifty") or {}
        adx = nifty_vol.get("adx14")
        if isinstance(adx, (int, float)):
            adx_color = GREEN if adx > 25 else AMBER if adx > 20 else RED
            lay.addLayout(_kv_row("ADX 14", _fmt_num(adx), adx_color))

        # EMA breadth
        breadth = vm.breadth_block(report)
        ema20 = breadth.get("above_ema20_percent")
        ema50 = breadth.get("above_ema50_percent")
        ema200 = breadth.get("above_ema200_percent")
        if isinstance(ema20, (int, float)):
            lay.addLayout(_kv_row(">EMA 20", f"{ema20:.1f}%", CYAN))
        if isinstance(ema50, (int, float)):
            lay.addLayout(_kv_row(">EMA 50", f"{ema50:.1f}%", PURPLE))
        if isinstance(ema200, (int, float)):
            lay.addLayout(_kv_row(">SMA 200", f"{ema200:.1f}%", BLUE))

    # ------------------------------------------------------------------
    # Derivatives desk panel
    # ------------------------------------------------------------------

    def _populate_derivatives(self, report):
        self._deriv_panel.clear_content()
        lay = self._deriv_panel.content

        d = vm.derivatives_block(report, "nifty")
        if not d.get("available"):
            lay.addWidget(_lbl("Derivatives data unavailable", 8, MUTED))
            return

        lay.addLayout(_kv_row("SPOT", _fmt_price(d.get("spot")), TEXT))
        lay.addLayout(_kv_row("EXPIRY", str(d.get("expiry", N_A)), SECONDARY))

        # PCR
        pcr = d.get("oi_pcr")
        pcr_color = MUTED
        if pcr is not None and pcr != N_A:
            try:
                pcr_f = float(pcr)
                pcr_color = GREEN if pcr_f > 1.0 else RED if pcr_f < 0.7 else AMBER
            except (TypeError, ValueError):
                pass
        lay.addLayout(_kv_row("OI PCR", _fmt_num(pcr), pcr_color))
        lay.addLayout(_kv_row("VOL PCR", _fmt_num(d.get("volume_pcr")), SECONDARY))

        # Max Pain
        lay.addLayout(_kv_row("MAX PAIN", _fmt_price(d.get("max_pain")), AMBER))

        # ATM IV
        atm_iv = d.get("atm_iv")
        lay.addLayout(_kv_row("ATM IV", _fmt_num(atm_iv), PURPLE))

        # S/R from derivatives
        lay.addLayout(_kv_row("PUT WALL", str(d.get("put_wall", N_A)), GREEN))
        lay.addLayout(_kv_row("CALL WALL", str(d.get("call_wall", N_A)), RED))
        lay.addLayout(_kv_row("SUPPORT", str(d.get("support", N_A)), GREEN))
        lay.addLayout(_kv_row("RESISTANCE", str(d.get("resistance", N_A)), RED))

    # ------------------------------------------------------------------
    # OI walls panel (right sidebar)
    # ------------------------------------------------------------------

    def _populate_oi_walls(self, report):
        self._oi_panel.clear_content()
        lay = self._oi_panel.content

        d = vm.derivatives_block(report, "nifty")
        if not d.get("available"):
            lay.addWidget(_lbl("No OI data", 8, MUTED))
            return

        # Visual OI wall bar
        wall_bar = _OIWallBar()
        wall_bar.set_data(
            d.get("put_wall"),
            d.get("call_wall"),
            d.get("spot"),
            d.get("max_pain"),
        )
        lay.addWidget(wall_bar)

        # Labels
        lay.addLayout(_kv_row("PUT WALL", str(d.get("put_wall", N_A)), GREEN))
        lay.addLayout(_kv_row("CALL WALL", str(d.get("call_wall", N_A)), RED))
        lay.addLayout(_kv_row("MAX PAIN", _fmt_price(d.get("max_pain")), AMBER))
        lay.addLayout(_kv_row("SPOT", _fmt_price(d.get("spot")), CYAN))

        # Distance from max pain
        spot = d.get("spot")
        mp = d.get("max_pain")
        if isinstance(spot, (int, float)) and isinstance(mp, (int, float)):
            dist = spot - mp
            pct = (dist / mp * 100) if mp else 0
            color = RED if abs(pct) > 1 else GREEN
            lay.addLayout(_kv_row("MP DIST", f"{dist:+,.0f} ({pct:+.1f}%)", color))

        # Bank Nifty derivatives summary
        bd = vm.derivatives_block(report, "bank_nifty")
        if bd.get("available"):
            lay.addWidget(_lbl("BANK NIFTY", 7, PURPLE, bold=True))
            lay.addLayout(_kv_row("PCR", _fmt_num(bd.get("oi_pcr")), SECONDARY))
            lay.addLayout(_kv_row("MAX PAIN", _fmt_price(bd.get("max_pain")), AMBER))

    # ------------------------------------------------------------------
    # Regime assessment panel
    # ------------------------------------------------------------------

    def _populate_regime(self, report):
        self._regime_panel.clear_content()
        lay = self._regime_panel.content

        macro = vm.macro(report)
        regime = str(macro.get("market_regime", "—")).upper()
        regime_color = self._regime_color(regime)

        regime_lbl = _lbl(regime, 11, regime_color, bold=True, mono=True)
        lay.addWidget(regime_lbl)

        # VIX details
        vix = macro.get("india_vix")
        vix_dir = macro.get("vix_direction", N_A)
        vix_regime = macro.get("vix_regime", N_A)
        lay.addLayout(_kv_row("VIX", _fmt_num(vix), SECONDARY))
        lay.addLayout(_kv_row("VIX DIR", str(vix_dir), SECONDARY))
        lay.addLayout(_kv_row("VIX REG", str(vix_regime), SECONDARY))

        vix_pct = macro.get("vix_percentile_1y")
        if isinstance(vix_pct, (int, float)):
            color = RED if vix_pct > 80 else GREEN if vix_pct < 20 else SECONDARY
            lay.addLayout(_kv_row("VIX %ile", f"{vix_pct:.0f}th", color))

        # Breadth summary
        breadth = vm.breadth_block(report)
        lay.addLayout(_kv_row("ADV", str(breadth.get("advancing", N_A)), GREEN))
        lay.addLayout(_kv_row("DEC", str(breadth.get("declining", N_A)), RED))
        ad = breadth.get("ad_ratio")
        if isinstance(ad, (int, float)):
            color = GREEN if ad > 1.2 else RED if ad < 0.8 else AMBER
            lay.addLayout(_kv_row("A/D", f"{ad:.2f}", color))

    # ------------------------------------------------------------------
    # Unusual options activity
    # ------------------------------------------------------------------

    def _populate_unusual(self, report):
        self._unusual_panel.clear_content()
        lay = self._unusual_panel.content

        d = vm.derivatives_block(report, "nifty")
        unusual = d.get("unusual_activity", [])

        if not unusual:
            lay.addWidget(_lbl("No unusual activity detected", 8, MUTED))
            return

        count_lbl = _lbl(f"{len(unusual)} alerts", 8, AMBER, bold=True)
        lay.addWidget(count_lbl)

        for item in unusual[:6]:
            if isinstance(item, dict):
                strike = item.get("strike", "?")
                opt_type = item.get("type", "?")
                action = item.get("action", item.get("signal", "?"))
                oi_chg = item.get("oi_change", item.get("oi_change_pct", ""))

                color = GREEN if "PUT" in str(opt_type).upper() else RED
                text = f"{strike} {opt_type}"
                if action:
                    text += f" · {action}"
                if oi_chg:
                    text += f" · OI:{oi_chg}"

                lay.addWidget(_lbl(text, 7, color, mono=True))
            elif isinstance(item, str):
                lay.addWidget(_lbl(item, 7, SECONDARY, mono=True))

    # ------------------------------------------------------------------
    # Positioning intelligence
    # ------------------------------------------------------------------

    def _populate_positioning(self, report):
        self._positioning_panel.clear_content()
        lay = self._positioning_panel.content

        d = vm.derivatives_block(report, "nifty")
        interp = d.get("interpretation", N_A)

        if interp and interp != N_A:
            text_lbl = _lbl(str(interp), 8, TEXT)
            text_lbl.setWordWrap(True)
            lay.addWidget(text_lbl)
        else:
            lay.addWidget(_lbl("No positioning data", 8, MUTED))

        # Institutional flow summary
        flow = vm.flow_block(report)
        if flow.get("available"):
            lay.addWidget(_lbl("INSTITUTIONAL", 7, CYAN, bold=True))
            for key, label in [("fii_5d", "FII 5D"), ("dii_5d", "DII 5D")]:
                val = flow.get(key)
                if val is not None and val != N_A:
                    try:
                        color = _sign_color(val)
                        lay.addLayout(_kv_row(label, f"{float(val):+,.1f} Cr", color))
                    except (TypeError, ValueError):
                        pass

    # ------------------------------------------------------------------
    # Freshness
    # ------------------------------------------------------------------

    def _update_freshness(self, report):
        age_info = vm.data_age(report)
        age_sec = age_info.get("age_seconds")
        if age_sec is not None:
            level = freshness_level(int(age_sec))
            self._freshness_badge.set_age(level, age_info.get("label", "—"))

        gen = report.get("generated", "")
        self._timestamp_lbl.setText(f"Generated: {gen}" if gen else "")

    # ------------------------------------------------------------------
    # AI Narrative
    # ------------------------------------------------------------------

    def _do_narrate(self):
        if not self._report or self._narrating:
            return
        self._narrating = True
        self._narrate_btn.setEnabled(False)
        self._narrate_btn.setText("GENERATING…")

        self._ai_panel.clear_content()
        self._ai_panel.content.addWidget(_lbl("Generating narrative…", 9, CYAN))

        self._narr_worker = _NarrateWorker(self._report)
        self._narr_worker.succeeded.connect(self._on_narrative)
        self._narr_worker.failed.connect(self._on_narrative_error)
        self._narr_worker.start()

    def _on_narrative(self, text):
        self._narrating = False
        self._narrate_btn.setEnabled(True)
        self._narrate_btn.setText("AI NARRATE")

        self._ai_panel.clear_content()
        lbl = _lbl(text or "No narrative generated.", 9, TEXT)
        lbl.setWordWrap(True)
        self._ai_panel.content.addWidget(lbl)

    def _on_narrative_error(self, error_text):
        self._narrating = False
        self._narrate_btn.setEnabled(True)
        self._narrate_btn.setText("AI NARRATE")

        self._ai_panel.clear_content()
        self._ai_panel.content.addWidget(_lbl(f"Error: {error_text}", 8, RED))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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


# =====================================================================
# AI Narrative worker (off-UI thread)
# =====================================================================

class _NarrateWorker(QThread):
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, report):
        super().__init__()
        self._report = report

    def run(self):
        try:
            text = analyze_market_lab(self._report)
            self.succeeded.emit(text or "")
        except Exception as exc:
            self.failed.emit(str(exc))
