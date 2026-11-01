"""
Market Overview page — premium trading terminal dashboard.

Layout: header → 7-KPI strip → 3-column (chart 50% | breadth+flows 26% | sectors 24%)
        → derivatives strip → status bar.
All custom widgets use QPainter for professional rendering.
"""

from __future__ import annotations

import math
import time
import traceback
from datetime import datetime, timezone, timedelta

from PySide6.QtCore import Qt, QThread, QTimer, Signal, QRectF, QPointF
from PySide6.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QLinearGradient,
    QPainterPath, QFontMetrics,
)
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from market_lab.market_lab_data import get_market_lab_data, save_json_report, CACHE_DIR
from market_lab import view_model as vm
from market_lab import widgets as W

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, SURFACE_RAISED, SIDEBAR, HEADER,
    BORDER, BORDER_BRIGHT, BORDER_DIM,
    TEXT, SECONDARY, MUTED, MUTED2,
    GREEN, RED, AMBER, BLUE, CYAN, PURPLE,
    BG_SUCCESS, BG_WARNING, BG_ERROR, BG_INFO,
    FONT_UI, FONT_MONO,
    GUARDRAIL_TEXT,
    freshness_level, freshness_color,
)

IST = timezone(timedelta(hours=5, minutes=30))
N_A = vm.N_A

# Premium palette overrides (matching reference image)
_BG_DEEP = "#030B12"
_PANEL = "#071923"
_PANEL_BORDER = "#0B6478"
_ACCENT = "#00E5FF"
_POS = "#00E6A8"
_NEG = "#FF405A"
_WARN = "#FFC928"


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
    return _POS if v >= 0 else _NEG


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
    return f"{v:+,.0f} Cr"


def _clear_layout(layout):
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()
        elif item.layout():
            _clear_layout(item.layout())


# =====================================================================
# Worker
# =====================================================================

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


# =====================================================================
# Sparkline widget (QPainter)
# =====================================================================

class _Sparkline(QWidget):
    def __init__(self, parent=None, color=_ACCENT):
        super().__init__(parent)
        self._data: list[float] = []
        self._color = color
        self.setFixedHeight(24)
        self.setMinimumWidth(60)

    def set_data(self, values: list):
        self._data = []
        for v in (values or []):
            try:
                self._data.append(float(v))
            except (TypeError, ValueError):
                continue
        self.update()

    def paintEvent(self, event):
        if len(self._data) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        pad = 2
        lo = min(self._data)
        hi = max(self._data)
        rng = hi - lo if hi != lo else 1.0
        n = len(self._data)
        step = (w - 2 * pad) / max(n - 1, 1)

        path = QPainterPath()
        for i, v in enumerate(self._data):
            x = pad + i * step
            y = h - pad - ((v - lo) / rng) * (h - 2 * pad)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        pen = QPen(QColor(self._color), 1.5)
        p.setPen(pen)
        p.drawPath(path)

        fill = QPainterPath(path)
        fill.lineTo(pad + (n - 1) * step, h)
        fill.lineTo(pad, h)
        fill.closeSubpath()
        grad = QLinearGradient(0, 0, 0, h)
        c = QColor(self._color)
        c.setAlpha(40)
        grad.setColorAt(0, c)
        c.setAlpha(0)
        grad.setColorAt(1, c)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill)

        last_v = self._data[-1]
        first_v = self._data[0]
        dot_color = _POS if last_v >= first_v else _NEG
        lx = pad + (n - 1) * step
        ly = h - pad - ((last_v - lo) / rng) * (h - 2 * pad)
        p.setBrush(QBrush(QColor(dot_color)))
        p.drawEllipse(QPointF(lx, ly), 2.5, 2.5)
        p.end()


# =====================================================================
# KPI card with sparkline
# =====================================================================

class _KPICard(QFrame):
    def __init__(self, title, spark_color=_ACCENT, parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL};
                border: 1px solid {_PANEL_BORDER};
                border-radius: 6px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(78)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 4)
        lay.setSpacing(1)

        top = QHBoxLayout()
        top.setSpacing(4)
        self._arrow_lbl = _lbl("", 9, MUTED)
        top.addWidget(self._arrow_lbl)
        self._title_lbl = _lbl(title, 7, MUTED, bold=True)
        top.addWidget(self._title_lbl)
        top.addStretch(1)
        self._change_lbl = _lbl("", 9, MUTED, mono=True, bold=True)
        top.addWidget(self._change_lbl)
        lay.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(6)
        self._value_lbl = _lbl("—", 16, TEXT, bold=True, mono=True)
        mid.addWidget(self._value_lbl)
        mid.addStretch(1)
        self._spark = _Sparkline(color=spark_color)
        mid.addWidget(self._spark)
        lay.addLayout(mid)

    def set_data(self, value, change_pct=None, suffix="", sparkline=None):
        try:
            self._value_lbl.setText(f"{float(value):,.2f}{suffix}")
        except (TypeError, ValueError):
            self._value_lbl.setText("—")
            self._value_lbl.setStyleSheet(f"color:{MUTED}; background:transparent; border:none;")
            self._arrow_lbl.setText("")
            return

        if change_pct is not None:
            try:
                pct = float(change_pct)
                color = _POS if pct >= 0 else _NEG
                arrow = "▲" if pct >= 0 else "▼"
                self._arrow_lbl.setText(arrow)
                self._arrow_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
                self._change_lbl.setText(f"{pct:+.2f}%")
                self._change_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
                self._value_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
            except (TypeError, ValueError):
                self._arrow_lbl.setText("")
        if sparkline:
            self._spark.set_data(sparkline)

    def set_raw(self, text, color=TEXT, sparkline=None):
        self._value_lbl.setText(text)
        self._value_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
        self._change_lbl.setText("")
        self._arrow_lbl.setText("")
        if sparkline:
            self._spark.set_data(sparkline)


# =====================================================================
# Candlestick chart (QPainter) — compact premium style
# =====================================================================

class _CandlestickChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._candles: list[dict] = []
        self._title = ""
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet(f"background: {_PANEL};")

    def set_data(self, candles: list[dict], title=""):
        self._candles = candles or []
        self._title = title
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(_PANEL))

        if not self._candles:
            p.setPen(QColor(MUTED))
            p.setFont(QFont(FONT_MONO, 10))
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "No candle data")
            p.end()
            return

        pad_l, pad_r, pad_t, pad_b = 50, 10, 14, 40
        vol_h = 30
        chart_h = h - pad_t - pad_b - vol_h - 4
        chart_w = w - pad_l - pad_r

        candles = self._candles
        n = len(candles)
        if n == 0:
            p.end()
            return

        highs = [c.get("high", 0) for c in candles]
        lows = [c.get("low", 0) for c in candles]
        vols = [c.get("volume", 0) or 0 for c in candles]
        price_hi = max(highs) if highs else 1
        price_lo = min(lows) if lows else 0
        price_rng = price_hi - price_lo if price_hi != price_lo else 1
        vol_max = max(vols) if vols else 1

        bar_w = max(chart_w / n, 1)
        body_w = max(bar_w * 0.6, 2)

        self._draw_grid(p, pad_l, pad_t, chart_w, chart_h, price_lo, price_hi, price_rng)

        # Draw area fill under closes
        closes_path = QPainterPath()
        for i, c in enumerate(candles):
            cl = c.get("close", 0)
            cx = pad_l + i * bar_w + bar_w / 2
            y = pad_t + (1 - (cl - price_lo) / price_rng) * chart_h
            if i == 0:
                closes_path.moveTo(cx, y)
            else:
                closes_path.lineTo(cx, y)

        fill_path = QPainterPath(closes_path)
        last_cx = pad_l + (n - 1) * bar_w + bar_w / 2
        first_cx = pad_l + bar_w / 2
        fill_path.lineTo(last_cx, pad_t + chart_h)
        fill_path.lineTo(first_cx, pad_t + chart_h)
        fill_path.closeSubpath()
        grad = QLinearGradient(0, pad_t, 0, pad_t + chart_h)
        gc = QColor(_POS)
        gc.setAlpha(25)
        grad.setColorAt(0, gc)
        gc.setAlpha(0)
        grad.setColorAt(1, gc)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(grad))
        p.drawPath(fill_path)

        for i, c in enumerate(candles):
            o = c.get("open", 0)
            cl = c.get("close", 0)
            hi = c.get("high", 0)
            lo = c.get("low", 0)
            vol = c.get("volume", 0) or 0

            bullish = cl >= o
            color = QColor(_POS) if bullish else QColor(_NEG)
            cx = pad_l + i * bar_w + bar_w / 2

            def py(price):
                return pad_t + (1 - (price - price_lo) / price_rng) * chart_h

            wick_x = int(cx)
            p.setPen(QPen(color, 1))
            p.drawLine(wick_x, int(py(hi)), wick_x, int(py(lo)))

            body_top = py(max(o, cl))
            body_bot = py(min(o, cl))
            body_height = max(body_bot - body_top, 1)
            body_rect = QRectF(cx - body_w / 2, body_top, body_w, body_height)
            p.setBrush(QBrush(color))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(body_rect)

            vol_y_base = h - pad_b
            vol_bar_h = (vol / vol_max) * vol_h if vol_max else 0
            vol_color = QColor(_POS if bullish else _NEG)
            vol_color.setAlpha(60)
            p.setBrush(QBrush(vol_color))
            p.drawRect(QRectF(cx - body_w / 2, vol_y_base - vol_bar_h, body_w, vol_bar_h))

        # Draw a dashed EMA-style line (20-period simple average of closes)
        closes = [c.get("close", 0) for c in candles]
        if len(closes) >= 20:
            ema_path = QPainterPath()
            started = False
            for i in range(19, len(closes)):
                avg = sum(closes[i - 19:i + 1]) / 20
                cx = pad_l + i * bar_w + bar_w / 2
                y = pad_t + (1 - (avg - price_lo) / price_rng) * chart_h
                if not started:
                    ema_path.moveTo(cx, y)
                    started = True
                else:
                    ema_path.lineTo(cx, y)
            p.setPen(QPen(QColor(_ACCENT), 1, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(ema_path)

        # Last close dot
        if candles:
            last_c = candles[-1].get("close", 0)
            lx = pad_l + (n - 1) * bar_w + bar_w / 2
            ly = pad_t + (1 - (last_c - price_lo) / price_rng) * chart_h
            glow = QColor(_POS)
            glow.setAlpha(60)
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(lx, ly), 5, 5)
            p.setBrush(QBrush(QColor(_POS)))
            p.drawEllipse(QPointF(lx, ly), 3, 3)

        self._draw_labels(p, candles, pad_l, pad_t, chart_w, chart_h, h, pad_b, bar_w, n)

        if self._title:
            p.setPen(QColor(SECONDARY))
            p.setFont(QFont(FONT_UI, 9, QFont.Weight.Bold))
            p.drawText(pad_l + 4, pad_t - 2, self._title)

        p.end()

    def _draw_grid(self, p, pl, pt, cw, ch, lo, hi, rng):
        p.setPen(QPen(QColor(BORDER_DIM), 1, Qt.PenStyle.DotLine))
        font = QFont(FONT_MONO, 7)
        p.setFont(font)
        for i in range(5):
            frac = i / 4
            y = int(pt + frac * ch)
            price = hi - frac * rng
            p.setPen(QPen(QColor(BORDER_DIM), 1, Qt.PenStyle.DotLine))
            p.drawLine(pl, y, pl + cw, y)
            p.setPen(QColor(MUTED2))
            p.drawText(2, y + 4, f"{price:,.0f}")

    def _draw_labels(self, p, candles, pl, pt, cw, ch, h, pb, bar_w, n):
        p.setFont(QFont(FONT_MONO, 7))
        p.setPen(QColor(MUTED2))
        step = max(n // 6, 1)
        for i in range(0, n, step):
            c = candles[i]
            date_str = c.get("date", "")
            if isinstance(date_str, str) and len(date_str) >= 5:
                x = pl + i * bar_w + bar_w / 2
                p.drawText(int(x) - 15, int(h - pb + 14), date_str[-5:])


# =====================================================================
# Panel frame with icon
# =====================================================================

class _Panel(QFrame):
    def __init__(self, title, icon="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL};
                border: 1px solid {_PANEL_BORDER};
                border-radius: 6px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._outer = QVBoxLayout(self)
        self._outer.setContentsMargins(10, 8, 10, 8)
        self._outer.setSpacing(4)

        header = QHBoxLayout()
        header.setSpacing(6)
        if icon:
            icon_lbl = _lbl(icon, 10, _ACCENT)
            header.addWidget(icon_lbl)
        self._title_lbl = _lbl(title, 9, _ACCENT, bold=True)
        header.addWidget(self._title_lbl)
        header.addStretch(1)
        self._outer.addLayout(header)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {_PANEL_BORDER}; border:none;")
        self._outer.addWidget(sep)

        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 4, 0, 0)
        self._content_layout.setSpacing(2)
        self._outer.addLayout(self._content_layout, 1)

    @property
    def content(self):
        return self._content_layout

    def clear_content(self):
        _clear_layout(self._content_layout)


# =====================================================================
# Breadth bar (painted)
# =====================================================================

class BreadthBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._adv = 0
        self._dec = 0
        self._unch = 0
        self.setFixedHeight(14)

    def set_data(self, adv, dec, unch):
        self._adv = adv or 0
        self._dec = dec or 0
        self._unch = unch or 0
        self.update()

    def paintEvent(self, event):
        total = self._adv + self._dec + self._unch
        if total <= 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        adv_w = int(w * self._adv / total)
        dec_w = int(w * self._dec / total)
        unch_w = w - adv_w - dec_w

        x = 0
        for width, color in [(adv_w, _POS), (unch_w, _WARN), (dec_w, _NEG)]:
            if width > 0:
                p.setBrush(QBrush(QColor(color)))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(x, 0, width, h, 4, 4)
                x += width
        p.end()


# =====================================================================
# Flow gauge bar (horizontal painted bar for FII/DII)
# =====================================================================

class _FlowGauge(QWidget):
    def __init__(self, label="", parent=None):
        super().__init__(parent)
        self._label = label
        self._value = 0.0
        self._max_abs = 1.0
        self._text = ""
        self.setFixedHeight(24)
        self.setMinimumWidth(100)

    def set_data(self, value, max_abs, text=""):
        self._value = value or 0.0
        self._max_abs = max(abs(max_abs), 1) if max_abs else 1.0
        self._text = text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        label_font = QFont(FONT_MONO, 8, QFont.Weight.Bold)
        p.setFont(label_font)
        label_w = QFontMetrics(label_font).horizontalAdvance(self._label) + 6

        p.setPen(QColor(MUTED))
        p.drawText(0, int(h / 2 + 4), self._label)

        bar_x = max(label_w, 50)
        val_font = QFont(FONT_MONO, 8)
        val_w = QFontMetrics(val_font).horizontalAdvance(self._text) + 8
        bar_w = w - bar_x - val_w - 4
        bar_h = 10
        bar_y = int((h - bar_h) / 2)

        p.setPen(Qt.PenStyle.NoPen)
        bg_color = QColor(BORDER_DIM)
        bg_color.setAlpha(120)
        p.setBrush(QBrush(bg_color))
        p.drawRoundedRect(bar_x, bar_y, bar_w, bar_h, 3, 3)

        mid = bar_x + bar_w / 2
        frac = min(abs(self._value) / self._max_abs, 1.0)
        fill_w = frac * (bar_w / 2)

        color = QColor(_POS if self._value >= 0 else _NEG)
        p.setBrush(QBrush(color))
        if self._value >= 0:
            p.drawRoundedRect(int(mid), bar_y, int(fill_w), bar_h, 2, 2)
        else:
            p.drawRoundedRect(int(mid - fill_w), bar_y, int(fill_w), bar_h, 2, 2)

        p.setPen(QPen(QColor(_PANEL_BORDER), 1))
        p.drawLine(int(mid), bar_y - 1, int(mid), bar_y + bar_h + 1)

        if self._text:
            val_color = _POS if self._value >= 0 else _NEG
            p.setPen(QColor(val_color))
            p.setFont(val_font)
            p.drawText(int(w - val_w), int(h / 2 + 4), self._text)

        p.end()


# =====================================================================
# Sector heatmap cell
# =====================================================================

class _SectorCell(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(0)
        self._name_lbl = _lbl("", 8, TEXT, bold=True)
        self._name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ret_lbl = _lbl("", 9, TEXT, mono=True, bold=True)
        self._ret_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(self._name_lbl)
        lay.addWidget(self._ret_lbl)

    def set_data(self, name, ret_pct):
        short = name[:10] if name else "—"
        self._name_lbl.setText(short)
        if isinstance(ret_pct, (int, float)):
            color = _POS if ret_pct >= 0 else _NEG
            self._ret_lbl.setText(f"{ret_pct:+.1f}%")
            self._ret_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
            intensity = min(abs(ret_pct) / 5.0, 1.0)
            bg = QColor(_POS if ret_pct >= 0 else _NEG)
            bg.setAlpha(int(25 + intensity * 45))
            self.setStyleSheet(
                f"QFrame {{ background: rgba({bg.red()},{bg.green()},{bg.blue()},{bg.alpha()});"
                f" border: 1px solid {BORDER_DIM}; border-radius: 6px; }}"
            )
        else:
            self._ret_lbl.setText("—")
            self.setStyleSheet(
                f"QFrame {{ background: {_PANEL}; border: 1px solid {BORDER_DIM}; border-radius: 6px; }}"
            )


# =====================================================================
# Derivatives strip cell
# =====================================================================

class _DerivCell(QFrame):
    def __init__(self, title, icon="", parent=None):
        super().__init__(parent)
        self.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL};
                border: 1px solid {BORDER_DIM};
                border-radius: 6px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(54)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 5, 10, 5)
        lay.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(4)
        if icon:
            icon_lbl = _lbl(icon, 9, _ACCENT)
            top.addWidget(icon_lbl)
        top.addWidget(_lbl(title, 7, MUTED, bold=True))
        top.addStretch(1)
        lay.addLayout(top)

        self._value_lbl = _lbl("—", 13, TEXT, mono=True, bold=True)
        lay.addWidget(self._value_lbl)

    def set_value(self, text, color=TEXT):
        self._value_lbl.setText(str(text))
        self._value_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")


# =====================================================================
# IndexCard (retained for API compat with main_window)
# =====================================================================

class IndexCard(QFrame):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self._title = title
        self.setObjectName("indexCard")
        self.setStyleSheet(f"""
            QFrame#indexCard {{
                background: qlineargradient(
                    x1:0, y1:0, x2:0, y2:1,
                    stop:0 {SURFACE_ALT}, stop:1 {SURFACE}
                );
                border: 1px solid {BORDER};
                border-top: 2px solid {CYAN};
                border-radius: 6px;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top = QHBoxLayout()
        top.setSpacing(8)
        self._title_lbl = _lbl(title, 10, CYAN, bold=True)
        top.addWidget(self._title_lbl)
        top.addStretch(1)
        self._source_lbl = _lbl("", 7, MUTED)
        top.addWidget(self._source_lbl)
        layout.addLayout(top)

        price_row = QHBoxLayout()
        price_row.setSpacing(8)
        self._price_lbl = _lbl("—", 18, TEXT, bold=True, mono=True)
        price_row.addWidget(self._price_lbl)
        self._change_lbl = _lbl("", 10, MUTED, mono=True)
        price_row.addWidget(self._change_lbl)
        price_row.addStretch(1)
        layout.addLayout(price_row)

    def set_data(self, price, change_pct=None, source=""):
        try:
            self._price_lbl.setText(f"{float(price):,.2f}")
        except (TypeError, ValueError):
            self._price_lbl.setText("—")
        if change_pct is not None:
            try:
                pct = float(change_pct)
                color = _POS if pct >= 0 else _NEG
                self._change_lbl.setText(f"{pct:+.2f}%")
                self._change_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
                self._price_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
            except (TypeError, ValueError):
                pass
        if source:
            self._source_lbl.setText(source)


# =====================================================================
# Main page
# =====================================================================

class MarketOverviewPage(QWidget):
    regime_changed = Signal(str, str)
    scanner_age_changed = Signal(str, str)
    report_loaded = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.report: dict | None = None
        self._worker: _DataWorker | None = None
        self._chart_range = "3M"
        self._chart_index = "NIFTY 50"
        self._build_ui()
        QTimer.singleShot(100, self._load_cached_report)

    def set_report(self, report: dict):
        if isinstance(report, dict) and report:
            self.report = report
            self._populate(report)

    # ------------------------------------------------------------------
    # UI build
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ background:{_BG_DEEP}; border:none; }}"
            f" QScrollBar:vertical {{ background:{_BG_DEEP}; width:6px; }}"
            f" QScrollBar::handle:vertical {{ background:{_PANEL_BORDER}; border-radius:3px; }}"
            f" QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}"
        )

        container = QWidget()
        container.setStyleSheet(f"background: {_BG_DEEP};")
        main_lay = QVBoxLayout(container)
        main_lay.setContentsMargins(12, 8, 12, 8)
        main_lay.setSpacing(8)

        main_lay.addLayout(self._build_header())
        main_lay.addLayout(self._build_kpi_strip())
        main_lay.addLayout(self._build_main_area(), 1)
        main_lay.addLayout(self._build_deriv_strip())
        main_lay.addWidget(self._build_status_bar())

        scroll.setWidget(container)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self):
        row = QHBoxLayout()
        row.setSpacing(10)

        icon = _lbl("📊", 11, _ACCENT)
        row.addWidget(icon)

        self._regime_label = _lbl("MARKET REGIME:", 10, SECONDARY, bold=True, mono=True)
        row.addWidget(self._regime_label)

        self._regime_badge = _lbl("—", 10, "#000", bold=True, mono=True)
        self._regime_badge.setFixedHeight(24)
        self._regime_badge.setContentsMargins(8, 2, 8, 2)
        self._regime_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._regime_badge.setStyleSheet(
            f"background:{_WARN}; color:#000; border-radius:4px;"
            f" padding: 2px 10px; font-weight:700;"
        )
        row.addWidget(self._regime_badge)

        row.addStretch(1)

        self._freshness_lbl = _lbl("", 9, MUTED, mono=True)
        row.addWidget(self._freshness_lbl)

        self._refresh_btn = QPushButton("🔄  REFRESH")
        self._refresh_btn.setFixedSize(100, 28)
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: {_ACCENT}; color: #000; border: none;
                border-radius: 4px; font-size: 10px; font-weight: 700;
                letter-spacing: 0.5px;
            }}
            QPushButton:hover {{ background: #33E8FF; }}
            QPushButton:disabled {{ background: {BORDER}; color: {MUTED}; }}
        """)
        self._refresh_btn.clicked.connect(lambda: self._do_refresh(force=True))
        row.addWidget(self._refresh_btn)

        return row

    # ------------------------------------------------------------------
    # 7-KPI strip
    # ------------------------------------------------------------------

    def _build_kpi_strip(self):
        row = QHBoxLayout()
        row.setSpacing(6)

        self._kpi_nifty = _KPICard("NIFTY 50", _ACCENT)
        self._kpi_banknifty = _KPICard("BANK NIFTY", BLUE)
        self._kpi_vix = _KPICard("INDIA VIX", AMBER)
        self._kpi_ad = _KPICard("ADV / DEC", _POS)
        self._kpi_fii = _KPICard("FII NET", PURPLE)
        self._kpi_dii = _KPICard("DII NET", _ACCENT)
        self._kpi_pcr = _KPICard("PCR (OI)", AMBER)

        for card in [
            self._kpi_nifty, self._kpi_banknifty, self._kpi_vix,
            self._kpi_ad, self._kpi_fii, self._kpi_dii, self._kpi_pcr,
        ]:
            row.addWidget(card)

        return row

    # ------------------------------------------------------------------
    # Main area: chart (50%) + breadth/flows (26%) + sectors (24%)
    # ------------------------------------------------------------------

    def _build_main_area(self):
        row = QHBoxLayout()
        row.setSpacing(8)

        # LEFT — Chart (~50%)
        chart_frame = QFrame()
        chart_frame.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL};
                border: 1px solid {_PANEL_BORDER};
                border-radius: 6px;
            }}
        """)
        chart_lay = QVBoxLayout(chart_frame)
        chart_lay.setContentsMargins(8, 6, 8, 6)
        chart_lay.setSpacing(4)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(4)

        self._chart_tabs = {}
        for name in ["NIFTY 50", "BANK NIFTY", "VIX"]:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(name == "NIFTY 50")
            btn.setFixedHeight(22)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {MUTED};
                    border: 1px solid {_PANEL_BORDER}; border-radius: 3px;
                    font-size: 8px; font-weight: 600; padding: 0 10px;
                }}
                QPushButton:checked {{
                    background: {_ACCENT}; color: #000; border-color: {_ACCENT};
                }}
                QPushButton:hover {{ border-color: {_ACCENT}; color: {TEXT}; }}
            """)
            btn.clicked.connect(lambda checked, n=name: self._switch_chart_tab(n))
            toolbar.addWidget(btn)
            self._chart_tabs[name] = btn

        toolbar.addStretch(1)

        self._ohlc_labels = {}
        for field in ["O", "H", "L", "C"]:
            lbl = _lbl(f"{field}: —", 8, SECONDARY, mono=True)
            toolbar.addWidget(lbl)
            self._ohlc_labels[field] = lbl

        toolbar.addWidget(_lbl("│", 8, BORDER_DIM))

        self._range_buttons = {}
        for rng in ["1W", "1M", "3M", "6M"]:
            btn = QPushButton(rng)
            btn.setCheckable(True)
            btn.setChecked(rng == "3M")
            btn.setFixedSize(32, 20)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {MUTED};
                    border: none; font-size: 8px; font-weight: 600;
                    border-radius: 2px;
                }}
                QPushButton:checked {{ background: {_PANEL_BORDER}; color: {TEXT}; }}
                QPushButton:hover {{ color: {TEXT}; }}
            """)
            btn.clicked.connect(lambda checked, r=rng: self._set_range(r))
            toolbar.addWidget(btn)
            self._range_buttons[rng] = btn

        chart_lay.addLayout(toolbar)

        self._candle_chart = _CandlestickChart()
        chart_lay.addWidget(self._candle_chart, 1)

        row.addWidget(chart_frame, 5)

        # CENTER — Breadth + Flows (~26%)
        center_col = QVBoxLayout()
        center_col.setSpacing(6)

        self._breadth_panel = _Panel("MARKET BREADTH", "📊")
        bp = self._breadth_panel.content
        self._breadth_bar = BreadthBar()
        bp.addWidget(self._breadth_bar)
        bp.addSpacing(2)
        stats = QHBoxLayout()
        stats.setSpacing(4)
        self._breadth_adv = _lbl("ADV: —", 9, _POS, mono=True, bold=True)
        self._breadth_unch = _lbl("UNCH: —", 9, _WARN, mono=True, bold=True)
        self._breadth_dec = _lbl("DEC: —", 9, _NEG, mono=True, bold=True)
        stats.addWidget(self._breadth_adv)
        stats.addStretch(1)
        stats.addWidget(self._breadth_unch)
        stats.addStretch(1)
        stats.addWidget(self._breadth_dec)
        bp.addLayout(stats)
        bp.addSpacing(2)
        self._breadth_ema_row = QHBoxLayout()
        self._breadth_ema_row.setSpacing(4)
        self._ema20_lbl = _lbl(">EMA20: —", 8, _ACCENT, mono=True)
        self._ema50_lbl = _lbl(">EMA50: —", 8, PURPLE, mono=True)
        self._breadth_ema_row.addWidget(self._ema20_lbl)
        self._breadth_ema_row.addStretch(1)
        self._breadth_ema_row.addWidget(self._ema50_lbl)
        bp.addLayout(self._breadth_ema_row)
        center_col.addWidget(self._breadth_panel)

        self._flow_panel = _Panel("INSTITUTIONAL FLOWS", "🏛")
        fl = self._flow_panel.content
        self._fii_gauge = _FlowGauge("FII 5D")
        self._dii_gauge = _FlowGauge("DII 5D")
        self._fii10_gauge = _FlowGauge("FII 10D")
        self._dii10_gauge = _FlowGauge("DII 10D")
        fl.addWidget(self._fii_gauge)
        fl.addWidget(self._dii_gauge)
        fl.addWidget(self._fii10_gauge)
        fl.addWidget(self._dii10_gauge)
        fl.addSpacing(2)
        self._flow_regime_lbl = _lbl("", 8, _WARN, mono=True, bold=True)
        fl.addWidget(self._flow_regime_lbl)
        center_col.addWidget(self._flow_panel)

        center_col.addStretch(1)
        row.addLayout(center_col, 3)

        # RIGHT — Sector Heatmap (~24%)
        right_col = QVBoxLayout()
        right_col.setSpacing(6)

        self._sector_panel = _Panel("SECTOR HEATMAP", "▦")
        self._sector_grid = QGridLayout()
        self._sector_grid.setSpacing(4)
        self._sector_cells = []
        for i in range(8):
            cell = _SectorCell()
            r, c = divmod(i, 2)
            self._sector_grid.addWidget(cell, r, c)
            self._sector_cells.append(cell)
        self._sector_panel.content.addLayout(self._sector_grid)
        right_col.addWidget(self._sector_panel)

        right_col.addStretch(1)
        row.addLayout(right_col, 2)

        return row

    # ------------------------------------------------------------------
    # Derivatives strip
    # ------------------------------------------------------------------

    def _build_deriv_strip(self):
        row = QHBoxLayout()
        row.setSpacing(6)

        self._deriv_atm = _DerivCell("ATM STRIKE", "⚙")
        self._deriv_pcr = _DerivCell("PCR (OI)", "≋")
        self._deriv_maxpain = _DerivCell("MAX PAIN", "⚡")
        self._deriv_iv = _DerivCell("ATM IV", "〰")
        self._deriv_oi_ce = _DerivCell("OI WALL CE", "▐▌")
        self._deriv_oi_pe = _DerivCell("OI WALL PE", "▐▌")

        for cell in [
            self._deriv_atm, self._deriv_pcr, self._deriv_maxpain,
            self._deriv_iv, self._deriv_oi_ce, self._deriv_oi_pe,
        ]:
            row.addWidget(cell)

        return row

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _build_status_bar(self):
        bar = QFrame()
        bar.setFixedHeight(26)
        bar.setStyleSheet(f"""
            QFrame {{
                background: {_PANEL};
                border-top: 1px solid {_PANEL_BORDER};
                border-radius: 0;
            }}
        """)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(16)

        self._status_regime = _lbl("Regime: —", 8, _WARN, mono=True, bold=True)
        self._status_vix = _lbl("VIX: —", 8, SECONDARY, mono=True)
        self._status_breadth = _lbl("A/D: —", 8, SECONDARY, mono=True)
        self._status_flow = _lbl("FII 5D: —", 8, SECONDARY, mono=True)
        lay.addWidget(self._status_regime)
        lay.addWidget(self._status_vix)
        lay.addWidget(self._status_breadth)
        lay.addWidget(self._status_flow)
        lay.addStretch(1)

        self._guardrail_lbl = _lbl(GUARDRAIL_TEXT, 7, MUTED2)
        lay.addWidget(self._guardrail_lbl)

        self._status_time = _lbl("", 8, _ACCENT, mono=True)
        self._status_time.setStyleSheet(
            f"color:{_ACCENT}; background:rgba(0,229,255,15);"
            f" border:1px solid {_PANEL_BORDER}; border-radius:3px;"
            f" padding: 1px 6px;"
        )
        lay.addWidget(self._status_time)

        return bar

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
        self._refresh_btn.setText("🔄  REFRESH")
        if not isinstance(report, dict) or not report:
            return
        self.report = report
        self._populate(report)
        self.report_loaded.emit(report)

    def _on_error(self, tb, elapsed):
        self._refresh_btn.setEnabled(True)
        self._refresh_btn.setText("🔄  REFRESH")
        print(f"Market data error ({elapsed:.1f}s):\n{tb}")

    # ------------------------------------------------------------------
    # Populate
    # ------------------------------------------------------------------

    def _populate(self, report):
        macro = vm.macro(report)
        regime_text = str(macro.get("market_regime", "UNKNOWN")).upper()
        regime_color = self._regime_color(regime_text)
        self._regime_badge.setText(regime_text)
        self._regime_badge.setStyleSheet(
            f"background:{regime_color}; color:#000; border-radius:4px;"
            f" padding: 2px 10px; font-weight:700;"
        )
        self.regime_changed.emit(regime_text, regime_color)

        age_info = vm.data_age(report)
        age_sec = age_info.get("age_seconds")
        if age_sec is not None:
            level = freshness_level(int(age_sec))
            color = freshness_color(level)
            self._freshness_lbl.setText(f"Data: {age_info.get('label', '—')}")
            self._freshness_lbl.setStyleSheet(f"color:{color}; background:transparent; border:none;")
            self.scanner_age_changed.emit(age_info.get("label", "—"), color)

        self._populate_kpis(report)
        self._populate_chart(report)
        self._populate_breadth(report)
        self._populate_flows(report)
        self._populate_sectors(report)
        self._populate_derivatives(report)
        self._populate_status(report, macro)

    def _regime_color(self, label):
        label = label.upper()
        if "BULLISH" in label and "MILDLY" not in label:
            return _POS
        if "MILDLY_BULLISH" in label or "MILDLY BULLISH" in label:
            return "#66CC88"
        if "BEARISH" in label and "MILDLY" not in label:
            return _NEG
        if "MILDLY_BEARISH" in label or "MILDLY BEARISH" in label:
            return _WARN
        return _WARN

    # ------------------------------------------------------------------
    # KPI population
    # ------------------------------------------------------------------

    def _populate_kpis(self, report):
        nifty = vm.index_card(report, "nifty")
        candles_n = nifty.get("candles", [])
        closes_n = [c.get("close") for c in candles_n[-20:] if c.get("close") is not None]
        self._kpi_nifty.set_data(nifty.get("price"), nifty.get("change_percent"), sparkline=closes_n)

        bnifty = vm.index_card(report, "bank_nifty")
        candles_bn = bnifty.get("candles", [])
        closes_bn = [c.get("close") for c in candles_bn[-20:] if c.get("close") is not None]
        self._kpi_banknifty.set_data(bnifty.get("price"), bnifty.get("change_percent"), sparkline=closes_bn)

        vix = vm.vix_card(report)
        vix_candles = vix.get("candles", [])
        vix_closes = [c.get("close") for c in vix_candles[-20:] if c.get("close") is not None]
        self._kpi_vix.set_data(vix.get("value"), vix.get("change_percent"), sparkline=vix_closes)

        breadth = vm.breadth_block(report)
        adv = breadth.get("advancing", 0)
        dec = breadth.get("declining", 0)
        total = adv + dec
        if total > 0:
            ratio = adv / total
            color = _POS if ratio > 0.55 else _NEG if ratio < 0.45 else _WARN
            self._kpi_ad.set_raw(f"{adv} / {dec}", color)
        else:
            self._kpi_ad.set_raw(N_A, MUTED)

        flow = vm.flow_block(report)
        fii_5d = flow.get("fii_5d")
        dii_5d = flow.get("dii_5d")
        if isinstance(fii_5d, (int, float)):
            self._kpi_fii.set_raw(_fmt_crore(fii_5d), _sign_color(fii_5d))
        else:
            self._kpi_fii.set_raw(N_A, MUTED)

        if isinstance(dii_5d, (int, float)):
            self._kpi_dii.set_raw(_fmt_crore(dii_5d), _sign_color(dii_5d))
        else:
            self._kpi_dii.set_raw(N_A, MUTED)

        d = vm.derivatives_block(report, "nifty")
        pcr = d.get("oi_pcr")
        if pcr is not None:
            pcr_color = _POS if pcr > 1.0 else _NEG if pcr < 0.7 else _WARN
            self._kpi_pcr.set_raw(f"{pcr:.2f}", pcr_color)
        else:
            self._kpi_pcr.set_raw(N_A, MUTED)

    # ------------------------------------------------------------------
    # Chart
    # ------------------------------------------------------------------

    def _populate_chart(self, report):
        active = self._chart_index
        if active == "VIX":
            card = vm.vix_card(report)
        elif active == "BANK NIFTY":
            card = vm.index_card(report, "bank_nifty")
        else:
            card = vm.index_card(report, "nifty")

        candles = card.get("candles", [])
        self._set_ohlc(candles)
        candles = self._slice_candles(candles)
        self._candle_chart.set_data(candles, title=active)

    def _set_ohlc(self, candles):
        if candles:
            last = candles[-1]
            for field, key in [("O", "open"), ("H", "high"), ("L", "low"), ("C", "close")]:
                val = last.get(key)
                self._ohlc_labels[field].setText(
                    f"{field}: {_fmt_price(val)}" if isinstance(val, (int, float)) else f"{field}: —"
                )
        else:
            for field in ["O", "H", "L", "C"]:
                self._ohlc_labels[field].setText(f"{field}: —")

    def _slice_candles(self, candles):
        if not candles:
            return candles
        range_map = {"1W": 5, "1M": 22, "3M": 66, "6M": 132}
        n = range_map.get(self._chart_range, 66)
        return candles[-n:]

    # ------------------------------------------------------------------
    # Breadth
    # ------------------------------------------------------------------

    def _populate_breadth(self, report):
        breadth = vm.breadth_block(report)
        adv = breadth.get("advancing", 0)
        dec = breadth.get("declining", 0)
        unch = breadth.get("unchanged", 0)

        self._breadth_bar.set_data(adv, dec, unch)
        self._breadth_adv.setText(f"ADV: {adv}")
        self._breadth_dec.setText(f"DEC: {dec}")
        self._breadth_unch.setText(f"UNCH: {unch}")

        ema20 = breadth.get("above_ema20_percent")
        ema50 = breadth.get("above_ema50_percent")
        self._ema20_lbl.setText(f">EMA20: {ema20:.1f}%" if isinstance(ema20, (int, float)) else ">EMA20: —")
        self._ema50_lbl.setText(f">EMA50: {ema50:.1f}%" if isinstance(ema50, (int, float)) else ">EMA50: —")

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------

    def _populate_flows(self, report):
        flow = vm.flow_block(report)
        if not flow.get("available"):
            return

        vals = {}
        for key in ["fii_5d", "dii_5d", "fii_10d", "dii_10d"]:
            v = flow.get(key)
            vals[key] = float(v) if isinstance(v, (int, float)) else 0.0

        max_abs = max(abs(v) for v in vals.values()) if vals else 1

        self._fii_gauge.set_data(vals.get("fii_5d", 0), max_abs, _fmt_crore(vals.get("fii_5d", 0)))
        self._dii_gauge.set_data(vals.get("dii_5d", 0), max_abs, _fmt_crore(vals.get("dii_5d", 0)))
        self._fii10_gauge.set_data(vals.get("fii_10d", 0), max_abs, _fmt_crore(vals.get("fii_10d", 0)))
        self._dii10_gauge.set_data(vals.get("dii_10d", 0), max_abs, _fmt_crore(vals.get("dii_10d", 0)))

        regime = flow.get("flow_regime")
        if regime and regime != N_A:
            self._flow_regime_lbl.setText(f"Flow regime: {regime}")
        else:
            self._flow_regime_lbl.setText("")

    # ------------------------------------------------------------------
    # Sectors
    # ------------------------------------------------------------------

    def _populate_sectors(self, report):
        sectors = vm.sector_rows(report, limit=8)
        for i, cell in enumerate(self._sector_cells):
            if i < len(sectors):
                s = sectors[i]
                cell.set_data(s.get("name", "?"), s.get("return_20d"))
            else:
                cell.set_data("—", None)

    # ------------------------------------------------------------------
    # Derivatives strip
    # ------------------------------------------------------------------

    def _populate_derivatives(self, report):
        d = vm.derivatives_block(report, "nifty")
        if not d.get("available"):
            return

        atm = d.get("atm_strike")
        self._deriv_atm.set_value(_fmt_num(atm, 0) if isinstance(atm, (int, float)) else "—", _ACCENT)

        pcr = d.get("oi_pcr")
        if pcr is not None:
            pcr_color = _POS if pcr > 1.0 else _NEG if pcr < 0.7 else _WARN
            self._deriv_pcr.set_value(f"{pcr:.2f}", pcr_color)

        mp = d.get("max_pain")
        self._deriv_maxpain.set_value(_fmt_num(mp, 0) if isinstance(mp, (int, float)) else "—", _WARN)

        iv = d.get("atm_iv")
        self._deriv_iv.set_value(f"{iv:.1f}%" if isinstance(iv, (int, float)) else "—", SECONDARY)

        oi_ce = d.get("highest_oi_ce_strike") or d.get("oi_wall_ce")
        self._deriv_oi_ce.set_value(_fmt_num(oi_ce, 0) if isinstance(oi_ce, (int, float)) else "—", _NEG)

        oi_pe = d.get("highest_oi_pe_strike") or d.get("oi_wall_pe")
        self._deriv_oi_pe.set_value(_fmt_num(oi_pe, 0) if isinstance(oi_pe, (int, float)) else "—", _POS)

    # ------------------------------------------------------------------
    # Status bar
    # ------------------------------------------------------------------

    def _populate_status(self, report, macro):
        regime = str(macro.get("market_regime", "—")).upper()
        self._status_regime.setText(f"Regime: {regime}")
        self._status_regime.setStyleSheet(
            f"color:{self._regime_color(regime)}; background:transparent; border:none;"
        )

        vix = vm.vix_card(report)
        vix_val = vix.get("value")
        self._status_vix.setText(f"VIX: {_fmt_num(vix_val)}" if isinstance(vix_val, (int, float)) else "VIX: —")

        breadth = vm.breadth_block(report)
        adv = breadth.get("advancing", 0)
        dec = breadth.get("declining", 0)
        total = adv + dec
        self._status_breadth.setText(f"A/D: {adv / total:.2f}" if total > 0 else "A/D: —")

        flow = vm.flow_block(report)
        fii = flow.get("fii_5d")
        self._status_flow.setText(
            f"FII 5D: {_fmt_crore(fii)}" if isinstance(fii, (int, float)) else "FII 5D: —"
        )

        self._status_time.setText(f"Updated: {datetime.now(IST).strftime('%H:%M:%S IST')}")

    # ------------------------------------------------------------------
    # Chart controls
    # ------------------------------------------------------------------

    def _switch_chart_tab(self, name):
        self._chart_index = name
        for n, btn in self._chart_tabs.items():
            btn.setChecked(n == name)
        if self.report:
            self._populate_chart(self.report)

    def _set_range(self, rng):
        self._chart_range = rng
        for r, btn in self._range_buttons.items():
            btn.setChecked(r == rng)
        if self.report:
            self._populate_chart(self.report)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def shutdown(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(3000)
