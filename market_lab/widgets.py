"""
Nova Market Lab reusable terminal widgets.

Self-contained Qt component library (PySide6 only; no new dependencies, no
backend imports) used to rebuild the Market Lab terminal UI. Presentation
only — every value shown by these widgets comes from the real backend via
`market_lab.view_model` and is never fabricated here.

The palette mirrors market_lab_ui's existing theme. Keep these components
generic; the window in market_lab_ui.py wires them to real data.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QTimer
from PySide6.QtGui import (QBrush, QColor, QFont, QLinearGradient, QPainter,
                           QPen, QRadialGradient)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


# ---------------------------------------------------------------------------
# Palette + typography
# ---------------------------------------------------------------------------

BG = "#050B10"
SIDEBAR = "#061019"
PANEL = "#091620"
PANEL_ALT = "#0D1B26"
ALT_ROW = "#0F202B"
BORDER = "#183746"
BORDER_ALT = "#102936"

TEXT = "#F2F6FA"
SECONDARY = "#91A9BE"
MUTED = "#91A9BE"
MUTED2 = "#617A91"

GREEN = "#00E6A0"
CYAN = "#00D9F5"
PURPLE = "#B49AFF"
AMBER = "#FFBD4A"
RED = "#FF4058"
BLUE = "#3198FF"

REGULAR = "Segoe UI"
MONO = "Consolas"

# Map view-model freshness levels to colors (text always accompanies color).
FRESHNESS_COLOR = {
    "green": GREEN,
    "amber": AMBER,
    "red": RED,
    "critical": RED,
}


def font(size=10, mono=False, bold=False):
    family = MONO if mono else REGULAR
    weight = QFont.Weight.Bold if bold else QFont.Weight.Normal
    return QFont(family, size, weight)


def sign_color(value):
    """Green for >=0, red for <0, muted for None/NA."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return MUTED
    return GREEN if v >= 0 else RED


def make_label(text="", size=10, color=TEXT, bold=False, mono=False):
    label = QLabel("" if text is None else str(text))
    label.setFont(font(size, mono=mono, bold=bold))
    label.setStyleSheet(f"color:{color}; background:transparent; border:none;")
    return label


# ---------------------------------------------------------------------------
# Panels / frames
# ---------------------------------------------------------------------------

def panel(title=None, subtitle=None):
    """A bordered rounded panel frame; returns (frame, inner_layout)."""
    frame = QFrame()
    frame.setObjectName("novaPanel")
    frame.setStyleSheet(f"""
        QFrame#novaPanel {{
            background:{PANEL};
            border:1px solid {BORDER};
            border-radius:8px;
        }}
    """)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(6)
    if title is not None:
        layout.addWidget(make_label(title, 9, MUTED, bold=True))
    if subtitle is not None:
        layout.addWidget(make_label(subtitle, 8, MUTED))
    return frame, layout


def stat_chip(text, color=AMBER):
    """A small status chip whose text always carries the meaning."""
    chip = QLabel(str(text))
    chip.setFont(font(8, bold=True))
    _apply_chip_style(chip, color)
    chip.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return chip


def _apply_chip_style(chip, color):
    chip.setStyleSheet(f"""
        QLabel {{
            color:{color};
            background:{PANEL_ALT};
            border:1px solid {color};
            border-radius:8px;
            padding:1px 8px;
        }}
    """)


def restyle_chip(chip, text, color):
    """Update a stat chip's text and color in place (no widget recreation)."""
    chip.setText(str(text))
    _apply_chip_style(chip, color)
    return chip


# ---------------------------------------------------------------------------
# Freshness badge
# ---------------------------------------------------------------------------

class FreshnessBadge(QLabel):
    """Shows scanner/data age; color follows the freshness level, and the text
    always states the age so color is never the only signal."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFont(font(9, bold=True))
        self.set_age(None, "—")

    def set_age(self, level, text):
        color = FRESHNESS_COLOR.get(level, AMBER)
        if level == "critical":
            color = RED
        self.setText(str(text))
        self.setStyleSheet(f"""
            QLabel {{
                color:{color};
                background:{PANEL_ALT};
                border:1px solid {color};
                border-radius:8px;
                padding:2px 8px;
            }}
        """)


# ---------------------------------------------------------------------------
# Collapsible report section
# ---------------------------------------------------------------------------

class CollapsibleSection(QWidget):
    """A report section with a numbered, titled header, an availability chip
    and a collapse toggle. Collapsing hides the body but keeps its data and
    keeps the section in the workspace (never deletes it)."""

    def __init__(self, number, title, availability_text=None, parent=None):
        super().__init__(parent)
        self.setObjectName("section")
        self.setStyleSheet(f"""
            QWidget#section {{
                background:{PANEL};
                border:1px solid {BORDER};
                border-radius:8px;
            }}
        """)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = QPushButton()
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(f"""
            QPushButton {{
                text-align:left;
                background:transparent;
                border:none;
                padding:9px 12px;
            }}
            QPushButton:hover {{ background:{PANEL_ALT}; border-radius:8px; }}
        """)
        head_row = QHBoxLayout(self.header)
        head_row.setContentsMargins(2, 0, 8, 0)
        head_row.setSpacing(8)
        num_text = f"{number:02d}" if isinstance(number, int) else str(number)
        num = make_label(num_text, 11, CYAN, bold=True, mono=True)
        head_row.addWidget(num)
        title_lbl = make_label(title, 11, TEXT, bold=True)
        head_row.addWidget(title_lbl)
        head_row.addStretch()
        self._avail = QLabel()
        if availability_text is not None:
            self.set_availability(availability_text)
        head_row.addWidget(self._avail)
        self.arrow = make_label("▾", 11, MUTED, bold=True)
        head_row.addWidget(self.arrow)
        outer.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 4, 12, 12)
        self.body_layout.setSpacing(8)
        outer.addWidget(self.body)

        self.header.toggled.connect(self._on_toggled)

    def set_availability(self, text):
        color = GREEN if str(text).upper() == "AVAILABLE" else (
            MUTED if str(text).upper() in ("N/A", "UNKNOWN", "NOT_AVAILABLE") else AMBER
        )
        self._avail.setText(str(text))
        self._avail.setFont(font(8, bold=True))
        self._avail.setStyleSheet(
            f"color:{color}; background:transparent; border:none;"
        )

    def add(self, widget):
        self.body_layout.addWidget(widget)

    def add_layout(self, layout):
        self.body_layout.addLayout(layout)

    def set_content(self, widget):
        self.body_layout.addWidget(widget)

    def clear_body(self):
        while self.body_layout.count():
            item = self.body_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

    def _on_toggled(self, expanded):
        self.body.setVisible(expanded)
        self.arrow.setText("▾" if expanded else "▸")

    def set_expanded(self, expanded):
        self.header.setChecked(expanded)


# ---------------------------------------------------------------------------
# Sparkline (honest: only paints a real series)
# ---------------------------------------------------------------------------

class Sparkline(QWidget):
    """A minimal custom-painted sparkline. If given no real series it renders
    an explicit N/A placeholder — it never draws synthetic history."""

    def __init__(self, width=90, height=28, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self._series = []

    def set_series(self, series):
        numeric = []
        for v in series or []:
            try:
                numeric.append(float(v))
            except (TypeError, ValueError):
                numeric = []
                break
        self._series = numeric
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        if len(self._series) < 2:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "n/a")
            return
        lo, hi = min(self._series), max(self._series)
        span = (hi - lo) or 1.0
        pad = 3
        w = max(1, rect.width() - 2 * pad)
        h = max(1, rect.height() - 2 * pad)
        last = self._series[-1]
        color = QColor(GREEN if last >= self._series[0] else RED)
        painter.setPen(QPen(color, 1.4))
        path_points = []
        for i, value in enumerate(self._series):
            x = pad + w * i / (len(self._series) - 1)
            y = pad + h - (value - lo) / span * h
            path_points.append(QPointF(x, y))
        for a, b in zip(path_points, path_points[1:]):
            painter.drawLine(a, b)


# ---------------------------------------------------------------------------
# Snapshot + performance bars (custom-painted, real data only)
# ---------------------------------------------------------------------------

class SnapshotBar(QWidget):
    """A compact single-session OHLC snapshot visualization: a high~low range
    with open/close ticks. If the backend provides no OHLC it renders an
    explicit 'chart unavailable' placeholder — never synthetic candles."""

    def __init__(self, width=150, height=66, parent=None):
        super().__init__(parent)
        self.setMinimumSize(width, height)
        self._ohlc = None

    def set_snapshot(self, open_, high, low, close):
        try:
            self._ohlc = (float(open_), float(high), float(low), float(close))
        except (TypeError, ValueError):
            self._ohlc = None
        self.update()

    def set_unavailable(self):
        self._ohlc = None
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if not self._ohlc:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(
                r, Qt.AlignmentFlag.AlignCenter,
                "intraday chart unavailable (no series in report)",
            )
            return
        o, h, l, c = self._ohlc
        pad = 10
        left = r.left() + pad
        right = r.right() - pad
        top = r.top() + pad
        bot = r.bottom() - pad
        span = (h - l) or 1.0

        def y(value):
            return bot - (value - l) / span * (bot - top)

        color = QColor(GREEN if c >= o else RED)
        # midline reference
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawLine(left, (top + bot) // 2, right, (top + bot) // 2)
        # high-low range
        mid = (left + right) // 2
        painter.setPen(QPen(color, 2))
        painter.drawLine(mid, int(y(h)), mid, int(y(l)))
        # open (left tick) and close (right tick)
        painter.drawLine(left, int(y(o)), mid - 4, int(y(o)))
        painter.drawLine(mid + 4, int(y(c)), right, int(y(c)))
        # current (close) marker
        painter.setBrush(color)
        painter.drawEllipse(mid - 3, int(y(c)) - 3, 6, 6)
        painter.end()


class PerfBar(QWidget):
    """A thin, centered performance bar: right = positive (green), left =
    negative (red); length proportional to the value within a shared scale."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(12)
        self._value = None
        self._scale = 1.0

    def set_value(self, value, scale=None):
        try:
            self._value = float(value)
        except (TypeError, ValueError):
            self._value = None
        if scale:
            try:
                self._scale = abs(float(scale)) or 1.0
            except (TypeError, ValueError):
                self._scale = 1.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        h = r.height()
        radius = (h - 4) // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PANEL_ALT))
        painter.drawRoundedRect(QRectF(r), radius, radius)
        if self._value is None:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "—")
            return
        mid = r.center().x()
        frac = max(-1.0, min(1.0, self._value / (self._scale or 1.0)))
        width = abs(frac) * (r.width() / 2.0)
        painter.setBrush(QColor(GREEN if self._value >= 0 else RED))
        if self._value >= 0:
            box = QRectF(mid, r.top() + 2, width, h - 4)
        else:
            box = QRectF(mid - width, r.top() + 2, width, h - 4)
        painter.drawRoundedRect(box, radius, radius)
        painter.end()


# ---------------------------------------------------------------------------
# Line chart (real series only; never synthetic)
# ---------------------------------------------------------------------------

class LineChart(QWidget):
    """A compact index line chart. Draws only a real series (list of floats,
    optional date labels). Grid + last-price marker + min/max labels. If no
    genuine series is provided it renders an explicit unavailable state.
    """

    def __init__(self, width=300, height=120, parent=None):
        super().__init__(parent)
        self.setMinimumSize(width, height)
        self._values = []
        self._labels = []

    def set_series(self, values, labels=None):
        clean = []
        for v in values or []:
            try:
                clean.append(float(v))
            except (TypeError, ValueError):
                clean = []
                break
        self._values = clean
        self._labels = [str(x) for x in (labels or [])]
        if self._labels and len(self._labels) != len(self._values):
            self._labels = self._labels[-len(self._values):] if self._values else []
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if len(self._values) < 2:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(
                r, Qt.AlignmentFlag.AlignCenter,
                "no series in report",
            )
            painter.end()
            return

        left, right = r.left() + 8, r.right() - 44
        top, bot = r.top() + 8, r.bottom() - 18
        span = (max(self._values) - min(self._values)) or 1.0
        lo, hi = min(self._values), max(self._values)

        def y(value):
            return bot - (value - lo) / span * (bot - top)

        # horizontal grid + right-aligned price labels
        painter.setPen(QPen(QColor(BORDER), 1))
        for frac in (0.0, 0.5, 1.0):
            gy = int(top + (bot - top) * frac)
            painter.drawLine(left, gy, r.right() - 6, gy)
            label = hi - frac * (hi - lo)
            painter.setPen(QPen(QColor(MUTED)))
            painter.setFont(font(7, mono=True))
            painter.drawText(
                r.right() - 42, gy - 6, 40, 12,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{label:,.0f}",
            )
            painter.setPen(QPen(QColor(BORDER)))

        # price line
        rising = self._values[-1] >= self._values[0]
        color = QColor(GREEN if rising else RED)
        painter.setPen(QPen(color, 1.6))
        count = len(self._values)
        points = [
            (int(left + (right - left) * i / (count - 1)), int(y(v)))
            for i, v in enumerate(self._values)
        ]
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            painter.drawLine(x0, y0, x1, y1)

        # last price dot + dashed marker
        last_x, last_y = points[-1]
        painter.setBrush(color)
        painter.drawEllipse(last_x - 3, last_y - 3, 6, 6)
        dash = QPen(color, 1)
        dash.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(dash)
        painter.drawLine(left, last_y, last_x, last_y)

        # x-axis first/last date labels
        if self._labels and self._labels[0]:
            painter.setPen(QPen(QColor(MUTED)))
            painter.setFont(font(7, mono=True))
            painter.drawText(
                left, bot + 2, (right - left) // 2, 16,
                Qt.AlignmentFlag.AlignLeft, self._labels[0][-6:],
            )
            painter.drawText(
                left + (right - left) // 2, bot + 2, (right - left) // 2, 16,
                Qt.AlignmentFlag.AlignRight, self._labels[-1][-6:],
            )
        painter.end()


# ---------------------------------------------------------------------------
# Candlestick chart (real OHLC series only; never synthetic)
# ---------------------------------------------------------------------------

class CandleChart(QWidget):
    """A compact TradingView-style candlestick chart.

    Draws only a real OHLC(+volume) series: grid, candles (green/red), volume
    bars, right price axis with a last-price tag, time axis, and a crosshair
    with an OHLC read-out on hover. If no genuine series is provided it renders
    an explicit "no series" state. It never fabricates candles.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(320, 200)
        self.setMouseTracking(True)
        self._candles = []          # list of {t,o,h,l,c,v}
        self._hover_index = None
        self._overlays = []         # list of {"values":[...], "color":hex}
        self.setStyleSheet("background:transparent;")

    def set_overlays(self, overlays):
        """Set optional line overlays (e.g. MA20/MA50/MA200) aligned by candle
        index. Each overlay is {"values":[...], "color": hex}; None gaps are
        skipped so the line only spans real values."""
        clean = []
        for ov in overlays or []:
            values = []
            for v in ov.get("values", []):
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    values.append(None)
            clean.append({"values": values, "color": ov.get("color", CYAN)})
        self._overlays = clean
        self.update()

    def set_candles(self, candles):
        clean = []
        for row in candles or []:
            if not isinstance(row, dict):
                continue
            try:
                o = float(row["o"]); h = float(row["h"])
                l = float(row["l"]); c = float(row["c"])
            except (KeyError, TypeError, ValueError):
                continue
            if h < l:
                l, h = h, l
            v = row.get("v")
            try:
                v = float(v) if v is not None else None
            except (TypeError, ValueError):
                v = None
            clean.append({"t": str(row.get("t", "")), "o": o,
                          "h": h, "l": l, "c": c, "v": v})
        self._candles = clean
        self._hover_index = None
        self.update()

    def _bounds(self):
        highs = [c["h"] for c in self._candles]
        lows = [c["l"] for c in self._candles]
        hi = max(highs); lo = min(lows)
        pad = (hi - lo) or max(1.0, hi * 0.001)
        return hi + pad * 0.06, lo - pad * 0.06

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if len(self._candles) < 1:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter,
                             "no series in report")
            painter.end()
            return

        right = r.right() - 52
        left = r.left() + 6
        vol_h = max(16, int((r.height() - 12) * 0.18))
        price_top = r.top() + 6
        price_bottom = r.bottom() - 18 - vol_h
        hi, lo = self._bounds()
        span = (hi - lo) or 1.0

        def y(value):
            return price_bottom - (value - lo) / span * (price_bottom - price_top)

        count = len(self._candles)
        usable = max(1, right - left)
        step = usable / count

        # volume scale
        vols = [c["v"] for c in self._candles if c["v"] is not None]
        vmax = max(vols) if vols else 0.0

        # grid + right price labels
        painter.setPen(QPen(QColor(BORDER), 1))
        for frac in (0.0, 0.25, 0.5, 0.75, 1.0):
            gy = int(price_top + (price_bottom - price_top) * frac)
            painter.setPen(QPen(QColor(BORDER)))
            painter.drawLine(left, gy, r.right() - 2, gy)
            label = hi - frac * (hi - lo)
            painter.setPen(QPen(QColor(MUTED)))
            painter.setFont(font(7, mono=True))
            painter.drawText(r.right() - 50, gy - 6, 46, 12,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{label:,.0f}")

        # time axis (a few ticks)
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(font(7, mono=True))
        for i in range(0, count, max(1, count // 4)):
            cx = int(left + step * i + step / 2)
            t = self._candles[i]["t"]
            if t:
                painter.drawText(cx - 20, r.bottom() - 16, 40, 14,
                                 Qt.AlignmentFlag.AlignCenter, t[-6:])

        # candles + volume
        cw = max(1.5, step * 0.62)
        for i, c in enumerate(self._candles):
            cx = int(left + step * i + step / 2)
            color = QColor(GREEN if c["c"] >= c["o"] else RED)
            painter.setPen(QPen(color, 1))
            painter.drawLine(cx, int(y(c["h"])), cx, int(y(c["l"])))
            y_o = int(y(c["o"])); y_c = int(y(c["c"]))
            top = min(y_o, y_c); height = max(1, abs(y_c - y_o))
            painter.fillRect(QRectF(cx - cw / 2, top, cw, height), color)
            # volume
            if vmax and c["v"] is not None:
                vh = (c["v"] / vmax) * (vol_h - 2)
                vtop = price_bottom + 6 + vol_h - 2 - vh
                painter.fillRect(QRectF(cx - cw / 2, vtop, cw, vh),
                                 QColor(GREEN if c["c"] >= c["o"] else RED))

        # moving-average overlays (real series, None gaps skipped)
        for ov in self._overlays:
            if len(ov["values"]) != len(self._candles):
                continue
            painter.setPen(QPen(QColor(ov["color"]), 1.3))
            prev = None
            for i, value in enumerate(ov["values"]):
                if value is None:
                    prev = None
                    continue
                cx = int(left + step * i + step / 2)
                cy = int(y(value))
                if prev is not None:
                    painter.drawLine(prev[0], prev[1], cx, cy)
                prev = (cx, cy)

        # last price tag + dashed line
        last = self._candles[-1]
        last_color = GREEN if last["c"] >= last["o"] else RED
        ly = int(y(last["c"]))
        painter.setPen(QPen(QColor(MUTED), 1))
        painter.drawLine(left, ly, r.right() - 2, ly)
        painter.setBrush(QColor(last_color))
        painter.fillRect(QRectF(r.right() - 50, ly - 7, 46, 14), QColor(last_color))
        painter.setPen(QPen(QColor(BG)))
        painter.setFont(font(7, mono=True, bold=True))
        painter.drawText(r.right() - 50, ly - 7, 46, 14,
                         Qt.AlignmentFlag.AlignCenter, f"{last['c']:,.0f}")

        # crosshair + OHLC read-out
        if self._hover_index is not None:
            i = self._hover_index
            c = self._candles[i]
            cx = int(left + step * i + step / 2)
            painter.setPen(QPen(QColor(MUTED), 1, Qt.PenStyle.DashLine))
            painter.drawLine(cx, price_top, cx, price_bottom + 6)
            chg = (c["c"] - c["o"]) / c["o"] * 100.0 if c["o"] else 0.0
            readout = (f"O {c['o']:,.1f}  H {c['h']:,.1f}  "
                       f"L {c['l']:,.1f}  C {c['c']:,.1f}  "
                       f"{chg:+.2f}%  {c['t']}")
            painter.setPen(QPen(QColor(TEXT)))
            painter.setFont(font(8, mono=True))
            painter.drawText(r.left() + 8, r.top() + 6, readout)
        painter.end()

    def mouseMoveEvent(self, event):
        r = self.rect()
        left = r.left() + 6
        right = r.right() - 52
        count = len(self._candles)
        if count >= 1 and right > left:
            usable = right - left
            x = event.position().x()
            idx = int((x - left) / usable * count)
            idx = max(0, min(count - 1, idx))
            if idx != self._hover_index:
                self._hover_index = idx
                self.update()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_index = None
        self.update()
        super().leaveEvent(event)


# ---------------------------------------------------------------------------
# Fill bar (0..1 horizontal) for KPI strips / breadth
# ---------------------------------------------------------------------------

class FillBar(QWidget):
    """A thin left-to-right progress bar; fraction 0..1, honest color."""

    def __init__(self, color=GREEN, height=8, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._frac = 0.0
        self._color = color

    def set_fraction(self, frac, color=None):
        try:
            self._frac = max(0.0, min(1.0, float(frac)))
        except (TypeError, ValueError):
            self._frac = 0.0
        if color:
            self._color = color
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        h = r.height()
        radius = h // 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PANEL_ALT))
        painter.drawRoundedRect(QRectF(r), radius, radius)
        width = int(r.width() * self._frac)
        if width > 0:
            painter.setBrush(QColor(self._color))
            painter.drawRoundedRect(QRectF(r.left(), r.top(), width, h), radius, radius)
        painter.end()


# ---------------------------------------------------------------------------
# Momentum gauge (radial dial) — single KPI measured against 0-100 scale
# ---------------------------------------------------------------------------

class MomentumGauge(QWidget):
    """A radial momentum gauge showing a single score (0-100) against colored
    threshold zones: red (<40), amber (40-60), green (>60). Never fabricates:
    a missing/non-numeric score renders an explicit N/A placeholder.

    The number and label are drawn beside the gauge (not color-only) so the
    reading stays accessible without relying on hue alone.
    """

    def __init__(self, size=210, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._score = None
        self._label = "Momentum"
        self._sub = ""

    def set_score(self, score, label="Momentum", sub=""):
        try:
            self._score = None if score is None else float(score)
        except (TypeError, ValueError):
            self._score = None
        self._label = str(label or "Momentum")
        self._sub = str(sub or "")
        self.update()

    def _zone_color(self, score):
        if score < 40:
            return RED
        if score < 60:
            return AMBER
        return GREEN

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        radius = min(r.width(), r.height()) // 2 - 14

        if self._score is None:
            painter.setPen(QPen(QColor(MUTED), 1))
            painter.setFont(font(10, bold=True))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "N/A")
            painter.setPen(QPen(QColor(MUTED2), 1))
            painter.setFont(font(8))
            painter.drawText(
                r.adjusted(0, 24, 0, 0),
                Qt.AlignmentFlag.AlignCenter, self._label)
            painter.end()
            return

        score = max(0.0, min(100.0, self._score))
        zone_color = self._zone_color(score)

        # Threshold zone arcs (background track split into red/amber/green).
        zones = [(0.0, 40.0, RED), (40.0, 60.0, AMBER), (60.0, 100.0, GREEN)]
        track_pen_width = 10
        start_angle = 135  # degrees, 0 at 3 o'clock, CCW
        span_per_zone = 270 // 3
        for z_lo, z_hi, z_color in zones:
            frac_lo = (z_lo / 100.0)
            frac_hi = (z_hi / 100.0)
            # Map 0-100 onto the 270-degree arc starting at 135 deg.
            sweep_total = 270
            ang_start = start_angle - frac_lo * sweep_total
            ang_span = (frac_hi - frac_lo) * sweep_total
            pen = QPen(QColor(z_color), track_pen_width)
            pen.setCapStyle(Qt.PenStyle.FlatCap)
            painter.setPen(pen)
            # Qt drawArc uses 1/16th degree, clockwise positive from 3 o'clock.
            painter.drawArc(
                cx - radius, cy - radius, 2 * radius, 2 * radius,
                int(-ang_start * 16), int(-ang_span * 16))

        # Score arc: how far the needle fills the zone track.
        pen = QPen(QColor(zone_color), track_pen_width + 2)
        pen.setCapStyle(Qt.PenStyle.RoundCap)
        painter.setPen(pen)
        ang_start = start_angle
        ang_span = -(score / 100.0) * 270
        painter.drawArc(
            cx - radius, cy - radius, 2 * radius, 2 * radius,
            int(ang_start * 16), int(ang_span * 16))

        # Center needle (small dot + short line pointing to score position).
        import math as _math
        rad = _math.radians(start_angle - (score / 100.0) * 270)
        nx = cx + _math.cos(rad) * (radius - 6)
        ny = cy - _math.sin(rad) * (radius - 6)
        painter.setPen(QPen(QColor(TEXT), 2))
        painter.drawLine(cx, cy, int(nx), int(ny))
        painter.setBrush(QColor(TEXT))
        painter.drawEllipse(cx - 3, cy - 3, 6, 6)

        # Score value + label beneath the dial.
        painter.setPen(QPen(QColor(TEXT), 1))
        painter.setFont(font(22, bold=True, mono=True))
        painter.drawText(
            r.adjusted(0, int(radius * 0.55), 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            f"{score:.0f}")
        painter.setPen(QPen(QColor(SECONDARY), 1))
        painter.setFont(font(8.5, bold=True))
        painter.drawText(
            r.adjusted(0, int(radius * 0.55) + 22, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            self._label.upper())
        if self._sub:
            painter.setPen(QPen(QColor(MUTED), 1))
            painter.setFont(font(7.5))
            painter.drawText(
                r.adjusted(0, int(radius * 0.55) + 34, 0, 0),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                self._sub)

        painter.end()


# ---------------------------------------------------------------------------
# Status pill / badge (rounded, colored; text carries the meaning)
# ---------------------------------------------------------------------------

class StatusPill(QWidget):
    """A rounded status pill whose colored fill + text always carries meaning
    (never color-only)."""

    def __init__(self, text, color=CYAN, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 3, 8, 3)
        lay.setSpacing(0)
        self._label = QLabel(str(text))
        self._label.setFont(font(8.5, bold=True))
        self._label.setStyleSheet(f"color:#041018; background:transparent; border:none;")
        lay.addWidget(self._label)
        self.setStyleSheet(f"""
            StatusPill {{
                background:{color};
                border-radius:999px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)


# ---------------------------------------------------------------------------
# Stacked bar (segments) for breadth internals
# ---------------------------------------------------------------------------

class StackBar(QWidget):
    """A single horizontal stacked bar of (fraction, color) segments.
    Fractions should sum to ~1.0; used for the advances/declines split."""

    def __init__(self, height=16, parent=None):
        super().__init__(parent)
        self.setFixedHeight(height)
        self._segments = []

    def set_segments(self, segments):
        clean = []
        for frac, color in segments or []:
            try:
                clean.append((max(0.0, float(frac)), color))
            except (TypeError, ValueError):
                continue
        self._segments = clean
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if not self._segments:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter, "—")
            painter.end()
            return
        x = float(r.left())
        for frac, color in self._segments:
            w = r.width() * frac
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(color))
            painter.drawRect(QRectF(x, r.top(), w, r.height()))
            x += w
        painter.end()


# ---------------------------------------------------------------------------
# Grouped bar chart (real categorical series; zero baseline + legend)
# ---------------------------------------------------------------------------

class GroupedBarChart(QWidget):
    """Compact grouped bars across categories for one or more series, with a
    zero baseline and a legend. Values are shown only if present; any non-numeric
    or missing value is skipped (bar height 0) rather than fabricated."""

    def __init__(self, height=180, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(height)
        self._categories = []
        self._series = []   # [{label, color, values:[...]}]

    def set_data(self, categories, series):
        self._categories = list(categories or [])
        clean = []
        for s in series or []:
            values = []
            for v in s.get("values", []):
                try:
                    values.append(float(v))
                except (TypeError, ValueError):
                    values.append(0.0)
            clean.append({"label": s.get("label", ""),
                          "color": s.get("color", MUTED), "values": values})
        self._series = clean
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        if not self._categories or not self._series:
            painter.setPen(QPen(QColor(MUTED)))
            painter.drawText(r, Qt.AlignmentFlag.AlignCenter,
                             "no series")
            painter.end()
            return

        legend_h = 16
        plot = r.adjusted(8, 8, -8, -(legend_h + 6))
        values = [v for s in self._series for v in s["values"]]
        hi = max([abs(v) for v in values] or [1.0]) * 1.12
        zero_y = plot.top() + plot.height() / 2

        # zero baseline + gridlines
        painter.setPen(QPen(QColor(SECONDARY), 1))
        painter.drawLine(plot.left(), int(zero_y), plot.right(), int(zero_y))

        n_cat = len(self._categories)
        n_series = len(self._series)
        group_w = plot.width() / n_cat
        bar_w = max(4.0, (group_w * 0.7) / n_series)
        half = plot.height() / 2

        for ci in range(n_cat):
            cx0 = plot.left() + group_w * ci + (group_w - bar_w * n_series) / 2
            for si, s in enumerate(self._series):
                value = s["values"][ci] if ci < len(s["values"]) else 0.0
                frac = max(-1.0, min(1.0, value / hi))
                h = frac * half
                x = cx0 + bar_w * si
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QColor(s["color"]))
                if value >= 0:
                    painter.drawRect(QRectF(x, zero_y - h, bar_w - 1, h))
                else:
                    painter.drawRect(QRectF(x, zero_y, bar_w - 1, -h))
            # category label
            painter.setPen(QPen(QColor(SECONDARY)))
            painter.setFont(font(8))
            painter.drawText(
                int(plot.left() + group_w * ci), int(plot.bottom() + 2),
                int(group_w), 14, Qt.AlignmentFlag.AlignCenter,
                str(self._categories[ci]))

        # legend
        lx = plot.left()
        painter.setFont(font(8))
        for s in self._series:
            painter.setBrush(QColor(s["color"]))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(QRectF(lx, r.bottom() - legend_h, 8, 8))
            painter.setPen(QPen(QColor(SECONDARY)))
            painter.drawText(lx + 12, r.bottom() - legend_h - 2, 140, 14,
                             Qt.AlignmentFlag.AlignVCenter, str(s["label"]))
            lx += 150
        painter.end()


# ---------------------------------------------------------------------------
# Application background: deep navy plane + cyan technical grid + frame
# ---------------------------------------------------------------------------

class GridBackground(QWidget):
    """The terminal backdrop (custom-painted, since QSS cannot express a
    repeating grid or corner accents).

    Layers, back to front:
      1. a near-flat navy base gradient (secondary -> base -> deeper navy),
      2. an extremely faint cyan corner illumination,
      3. a fixed-logical-spacing grid: thin minor lines every ~38px with a
         stronger major line every fifth interval and sparse intersection dots,
      4. a thin rounded inset frame with faint corner crosshairs and diagonal
         guides.

    Opaque panel cards sit on top, so the grid reads as structure in the gaps
    and uncovered margins and never competes with charts, text or tables. The
    grid spacing is fixed in logical pixels so the pattern stays consistent
    when the window is resized (lines are not stretched). Painting happens only
    on resize; nothing here animates or intercepts input.
    """

    MINOR_STEP = 38           # ~36-40px between minor lines
    MAJOR_EVERY = 5            # a stronger major line every fifth interval
    MAJOR_STEP = MINOR_STEP * MAJOR_EVERY

    BASE = QColor(6, 16, 25)            # #061019
    SECONDARY = QColor(8, 21, 29)       # #08151D
    DEEP = QColor(5, 13, 20)
    GRID_MINOR = QColor(0, 210, 235, 14)   # rgba(0,210,235,0.055)
    GRID_MAJOR = QColor(0, 210, 235, 26)   # rgba(0,210,235,0.10)
    GRID_DOT = QColor(0, 210, 235, 41)     # rgba(0,210,235,0.16)
    BORDER_OUTER = QColor(18, 56, 71)      # #123847
    BORDER_INNER = QColor(12, 41, 52)      # #0C2934
    ACCENT = QColor(0, 210, 235, 150)      # corner crosshair accents
    GUIDE = QColor(0, 210, 235, 22)        # faint diagonal guides
    GLOW_TOP = QColor(0, 210, 235, 12)
    GLOW_BOTTOM = QColor(0, 210, 235, 9)

    INSET = 12                 # frame inset from the outer content edges
    CORNER_RADIUS = 8
    _CROSS_ARM = 7
    _CROSS_OFFSET = 12
    _GUIDE_LEN = 30

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        rect = self.rect()
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter = QPainter(self)
        left, right = rect.left(), rect.right()
        top, bottom = rect.top(), rect.bottom()

        # 1. Base plane: a near-flat vertical navy gradient.
        base = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        base.setColorAt(0.0, self.SECONDARY)
        base.setColorAt(0.5, self.BASE)
        base.setColorAt(1.0, self.DEEP)
        painter.fillRect(rect, base)

        # 2. Restrained corner illumination (faint teal, corner-sized only so
        #    the fill stays cheap at large window sizes).
        span = max(rect.width(), rect.height())
        glow_r = span * 0.42
        corner = QRectF(left, top, rect.width() * 0.6, rect.height() * 0.6)
        tl = QRadialGradient(left, top, glow_r)
        tl.setColorAt(0.0, self.GLOW_TOP)
        tl.setColorAt(1.0, QColor(0, 210, 235, 0))
        painter.fillRect(corner, tl)
        br = QRadialGradient(right, bottom, glow_r)
        br.setColorAt(0.0, self.GLOW_BOTTOM)
        br.setColorAt(1.0, QColor(0, 210, 235, 0))
        painter.fillRect(
            QRectF(right - rect.width() * 0.6, bottom - rect.height() * 0.6,
                   rect.width() * 0.6, rect.height() * 0.6),
            br,
        )

        # 3. Grid: fixed logical spacing so resizing keeps the pattern even.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        painter.setPen(QPen(self.GRID_MINOR, 1))
        x = self.MINOR_STEP
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += self.MINOR_STEP
        y = self.MINOR_STEP
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += self.MINOR_STEP

        painter.setPen(QPen(self.GRID_MAJOR, 1))
        x = self.MAJOR_STEP
        while x <= right:
            painter.drawLine(x, top, x, bottom)
            x += self.MAJOR_STEP
        y = self.MAJOR_STEP
        while y <= bottom:
            painter.drawLine(left, y, right, y)
            y += self.MAJOR_STEP

        # 4. Sparse intersection dots at the major intersections only.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.GRID_DOT)
        y = self.MAJOR_STEP
        while y <= bottom:
            x = self.MAJOR_STEP
            while x <= right:
                painter.drawRect(QRectF(x - 1.0, y - 1.0, 2.0, 2.0))
                x += self.MAJOR_STEP
            y += self.MAJOR_STEP

        # 5 + 6. Rounded inset frame with corner accents.
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        frame = rect.adjusted(self.INSET, self.INSET,
                              -self.INSET, -self.INSET)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(self.BORDER_OUTER, 1))
        painter.drawRoundedRect(QRectF(frame), self.CORNER_RADIUS,
                                self.CORNER_RADIUS)
        inner = frame.adjusted(2, 2, -2, -2)
        painter.setPen(QPen(self.BORDER_INNER, 1))
        painter.drawRoundedRect(QRectF(inner), max(1, self.CORNER_RADIUS - 1),
                                max(1, self.CORNER_RADIUS - 1))

        for cx, cy, sx, sy in (
            (frame.left(), frame.top(), 1, -1),
            (frame.right(), frame.top(), -1, -1),
            (frame.left(), frame.bottom(), 1, 1),
            (frame.right(), frame.bottom(), -1, 1),
        ):
            ax, ay = cx + sx * self._CROSS_OFFSET, cy + sy * self._CROSS_OFFSET
            painter.setPen(QPen(self.ACCENT, 1))
            painter.drawLine(ax, ay - self._CROSS_ARM, ax, ay + self._CROSS_ARM)
            painter.drawLine(ax - self._CROSS_ARM, ay, ax + self._CROSS_ARM, ay)
            painter.setPen(QPen(self.GUIDE, 1))
            painter.drawLine(ax, ay, ax + sx * self._GUIDE_LEN,
                             ay + sy * self._GUIDE_LEN)

        painter.end()


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def make_table(headers, stretch_column=1, sortable=False):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(
        QTableWidget.SelectionBehavior.SelectRows
    )
    table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(sortable)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(26)  # uniform compact rows
    header = table.horizontalHeader()
    for i in range(len(headers)):
        mode = (
            QHeaderView.ResizeMode.Stretch
            if i == stretch_column
            else QHeaderView.ResizeMode.ResizeToContents
        )
        header.setSectionResizeMode(i, mode)
    table.setStyleSheet(f"""
        QTableWidget {{
            background:{PANEL_ALT};
            alternate-background-color:{ALT_ROW};
            color:{TEXT};
            gridline-color:{BORDER_ALT};
            border:1px solid {BORDER};
            border-radius:6px;
        }}
        QHeaderView::section {{
            background:{PANEL};
            color:{SECONDARY};
            border:none;
            border-bottom:1px solid {BORDER};
            padding:4px 6px;
            font-size:9pt;
        }}
        QTableWidget::item {{ padding:4px 6px; font-size:10pt; }}
    """)
    table.setMinimumHeight(120)
    return table


def fill_table(table, rows):
    """rows: list of list of cell strings (already formatted). Empty -> a single
    muted '—' row; never fabricates data. If the table is sortable it is left
    sorted by the first column ascending so the logical/rank order is stable."""
    was_sortable = table.isSortingEnabled()
    table.setSortingEnabled(False)
    table.setRowCount(0)
    if not rows:
        table.insertRow(0)
        item = QTableWidgetItem("—")
        item.setForeground(QColor(MUTED))
        table.setItem(0, 0, item)
        table.setSpan(0, 0, 1, table.columnCount())
    else:
        for r in rows:
            row_index = table.rowCount()
            table.insertRow(row_index)
            for c, value in enumerate(r):
                if c >= table.columnCount():
                    break
                item = QTableWidgetItem("" if value is None else str(value))
                item.setFont(font(9, mono=True))
                table.setItem(row_index, c, item)
    if was_sortable:
        table.sortItems(0, Qt.SortOrder.AscendingOrder)
        table.setSortingEnabled(True)


# ---------------------------------------------------------------------------
# Persistent guardrails footer
# ---------------------------------------------------------------------------

class GuardrailsBar(QFrame):
    """Always-visible analysis-only safety footer. Not collapsible/removable
    by ordinary UI actions; it reflects the backend's safety state."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("guardrails")
        self.setFixedHeight(34)
        self.setStyleSheet(f"""
            QFrame#guardrails {{
                background:{SIDEBAR};
                border-top:1px solid {BORDER};
            }}
        """)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(10)

        accent = QLabel()
        accent.setFixedSize(3, 16)
        accent.setStyleSheet(f"background:{AMBER}; border-radius:1px;")
        layout.addWidget(accent)

        text = make_label(
            "GUARDRAILS: analysis-only, not a buy/sell signal, no broker/orders",
            9, AMBER, bold=True,
        )
        layout.addWidget(text)

        divider = QLabel()
        divider.setFixedSize(1, 16)
        divider.setStyleSheet(f"background:{BORDER};")
        layout.addWidget(divider)

        self._status = QLabel("buy_sell_authorization: False")
        self._status.setFont(font(9, mono=True, bold=True))
        self._status.setStyleSheet(f"color:{GREEN}; background:transparent; border:none;")
        layout.addWidget(self._status)

        layout.addStretch()

        self._ops = make_label("", 9, MUTED)
        layout.addWidget(self._ops)

    def set_authorized(self, authorized):
        # Always renders False for a compliant backend; if truly authorized it
        # would render True (never happens in Nova) in red.
        if authorized:
            self._status.setText("buy_sell_authorization: True")
            self._status.setStyleSheet(
                f"color:{RED}; background:transparent; border:none;"
            )
        else:
            self._status.setText("buy_sell_authorization: False")
            self._status.setStyleSheet(
                f"color:{GREEN}; background:transparent; border:none;"
            )

    def set_ops(self, text):
        self._ops.setText(str(text))


# ---------------------------------------------------------------------------
# PyQtGraph chart: price candles + volume + RSI + MACD (real series only)
# ---------------------------------------------------------------------------

try:
    import pyqtgraph as pg
    from pyqtgraph.Qt import QtCore as _PGQtCore
    from pyqtgraph.Qt import QtGui as _PGQtGui
    from PySide6.QtWidgets import QSizePolicy as _PGSizePolicy

    PG_AVAILABLE = True
except Exception:  # pragma: no cover
    PG_AVAILABLE = False


if PG_AVAILABLE:

    def _finite(value):
        return isinstance(value, (int, float)) and math.isfinite(value)

    class _CandlestickItem(pg.GraphicsObject):
        """Minimal candlestick drawn in data coordinates (rises green, falls red).

        Expects finite (x, open, close, low, high) tuples; invalid rows are
        skipped here as a second line of defence.
        """

        def __init__(self, data):
            pg.GraphicsObject.__init__(self)
            self.data = [d for d in data
                         if all(_finite(v) for v in (d[0], d[1], d[2], d[3], d[4]))]
            self._generate_picture()

        def _generate_picture(self):
            self.picture = _PGQtGui.QPicture()
            p = _PGQtGui.QPainter(self.picture)
            xs = sorted({d[0] for d in self.data})
            w = (xs[1] - xs[0]) / 3.0 if len(xs) >= 2 else 3600.0
            for (x, open_, close, low, high) in self.data:
                color = QColor(GREEN if close >= open_ else RED)
                p.setPen(pg.mkPen(color))
                p.drawLine(_PGQtCore.QPointF(x, low), _PGQtCore.QPointF(x, high))
                p.setBrush(pg.mkBrush(color))
                body = abs(close - open_) or max(w * 0.05, 1e-6)
                p.drawRect(_PGQtCore.QRectF(x - w, min(open_, close), 2 * w, body))
            p.end()

        def paint(self, painter, *args):
            painter.drawPicture(0, 0, self.picture)

        def boundingRect(self):
            return _PGQtCore.QRectF(self.picture.boundingRect())

    class PgCandleChart(QWidget):
        """Price candles + MA overlays, volume, RSI and MACD panels stacked
        vertically and sharing one datetime axis.

        `set_data(candles, rsi, macd, signal, hist)` takes only real series;
        missing/short series are simply not drawn. Never fabricates bars.
        """

        _ROWS = ("price", "volume", "rsi", "macd")

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setSizePolicy(_PGSizePolicy.Expanding, _PGSizePolicy.Expanding)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)
            self.win = pg.GraphicsLayoutWidget()
            self.win.setSizePolicy(_PGSizePolicy.Expanding, _PGSizePolicy.Expanding)
            layout.addWidget(self.win)
            self.plots = {}
            self._build()

        def _build(self):
            self.win.clear()
            date_axis = pg.DateAxisItem(orientation="bottom")
            self.plots = {
                "price": self.win.addPlot(row=0, col=0,
                                          axisItems={"bottom": date_axis}),
                "volume": self.win.addPlot(row=1, col=0),
                "rsi": self.win.addPlot(row=2, col=0),
                "macd": self.win.addPlot(row=3, col=0),
            }
            grid = self.win.ci.layout
            grid.setRowStretchFactor(0, 6)   # price dominates
            grid.setRowStretchFactor(1, 2)
            grid.setRowStretchFactor(2, 2)
            grid.setRowStretchFactor(3, 2)

            price = self.plots["price"]
            price.showGrid(x=True, y=True, alpha=0.2)
            price.setLabel("left", "Price")

            for name, label, cap in (("volume", "Volume", 96),
                                      ("rsi", "RSI 14", 96),
                                      ("macd", "MACD", 120)):
                p = self.plots[name]
                p.showGrid(x=False, y=True, alpha=0.2)
                p.setLabel("left", label)
                p.setMaximumHeight(cap)
                p.setXLink(price)
                p.getAxis("bottom").setStyle(showValues=False)

            self.plots["rsi"].setYRange(0, 100, padding=0.02)
            self.plots["rsi"].enableAutoRange(axis=pg.ViewBox.YAxis, enable=False)
            self.plots["rsi"].addLine(
                y=70, pen=pg.mkPen(AMBER, style=_PGQtCore.Qt.DashLine))
            self.plots["rsi"].addLine(
                y=30, pen=pg.mkPen(AMBER, style=_PGQtCore.Qt.DashLine))
            self.plots["macd"].addLine(y=0, pen=pg.mkPen(SECONDARY))

        @staticmethod
        def _finite(value):
            return isinstance(value, (int, float)) and math.isfinite(value)

        def set_data(self, candles, rsi=None, macd=None, signal=None, hist=None):
            candles = list(candles or [])
            rsi = list(rsi or [])
            macd = list(macd or [])
            signal = list(signal or [])
            hist = list(hist or [])
            self._build()
            if not candles:
                return

            # Validate + order the candles (drops non-dict/bad-date/future/
            # duplicate/bad-OHLC rows) and keep original indices so RSI/MACD
            # stay aligned. Never fabricates dates or bars.
            from market_lab import stock_adapter

            kept, report = stock_adapter.validate_candles(candles)
            if report.get("bad_ohlc") or report.get("future") or report.get("bad_date"):
                print(f"[CHART DATA] dropped rows in chart input: {report}")
            if not kept:
                return

            xs = [e for _, e, _ in kept]
            min_x, max_x = xs[0], xs[-1]
            step = (max_x - min_x) / (len(kept) - 1) if len(kept) > 1 else 86400.0
            if step <= 0:
                step = 86400.0

            # Candles
            body_data = [
                (e, float(c["o"]), float(c["c"]), float(c["l"]), float(c["h"]))
                for _, e, c in kept
            ]
            if body_data:
                self.plots["price"].addItem(_CandlestickItem(body_data))

            # Moving averages (only finite, aligned to the candle epoch).
            for key, color in (("ma20", CYAN), ("ma50", AMBER), ("ma200", PURPLE)):
                points = [
                    (e, float(c[key]))
                    for _, e, c in kept
                    if self._finite(c.get(key))
                ]
                if len(points) >= 2:
                    self.plots["price"].plot(
                        [p[0] for p in points], [p[1] for p in points],
                        pen=pg.mkPen(color, width=1.4))

            # Volume (own axis; non-finite -> 0, never plotted on the price axis).
            vol_heights = []
            for i, e, c in kept:
                v = c.get("v")
                vol_heights.append(float(v) if self._finite(v) else 0.0)
            if any(h > 0 for h in vol_heights):
                self.plots["volume"].addItem(pg.BarGraphItem(
                    x=xs, height=vol_heights, width=step * 0.7,
                    brushes=[
                        pg.mkBrush(GREEN if c["c"] >= c["o"] else RED)
                        for _, e, c in kept
                    ]))

            # RSI (only finite points; y is pinned to 0-100 by _build).
            rsi_points = [
                (e, float(rsi[i]))
                for i, e, c in kept
                if i < len(rsi) and self._finite(rsi[i])
            ]
            if len(rsi_points) >= 2:
                self.plots["rsi"].plot(
                    [p[0] for p in rsi_points], [p[1] for p in rsi_points],
                    pen=pg.mkPen(CYAN, width=1.4))

            # MACD line + signal line (own y-axis).
            for values, color in ((macd, CYAN), (signal, AMBER)):
                points = [
                    (e, float(values[i]))
                    for i, e, c in kept
                    if i < len(values) and self._finite(values[i])
                ]
                if len(points) >= 2:
                    self.plots["macd"].plot(
                        [p[0] for p in points], [p[1] for p in points],
                        pen=pg.mkPen(color, width=1.4))

            # MACD histogram (bars from zero; non-finite warm-up -> 0).
            if hist:
                hist_heights = [
                    (float(hist[i]) if i < len(hist) and self._finite(hist[i])
                     else 0.0)
                    for i, e, c in kept
                ]
                self.plots["macd"].addItem(pg.BarGraphItem(
                    x=xs, height=hist_heights, width=step * 0.6,
                    brushes=[pg.mkBrush(GREEN if h >= 0 else RED)
                              for h in hist_heights]))

            # Shared time axis: price owns X, pin it to the validated range so
            # the axis never extends into an unsupported future period.
            price = self.plots["price"]
            price.enableAutoRange(axis=pg.ViewBox.XYAxes)
            price.autoRange()
            price.setXRange(min_x, max_x, padding=0.02)
            for name in ("volume", "macd"):
                self.plots[name].enableAutoRange(axis=pg.ViewBox.YAxis)
                self.plots[name].autoRange()


# ---------------------------------------------------------------------------
# Enhanced components - glass cards, sparklines, trend badges, drill-down
# ---------------------------------------------------------------------------

class GlassCard(QWidget):
    """A glassmorphism card with subtle hover glow. Holds arbitrary content
    in its vertical layout; emits clicked() when the whole card is clicked
    (useful for drill-down navigation)."""

    clicked = Signal()

    def __init__(self, title=None, subtitle=None, parent=None):
        super().__init__(parent)
        self.setObjectName("interactive-card")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(6)
        if title:
            self._layout.addWidget(make_label(title, 9, MUTED, bold=True))
        if subtitle:
            self._layout.addWidget(make_label(subtitle, 12, TEXT, bold=True, mono=True))

    def set_content(self, widget):
        """Add a widget below the title/subtitle."""
        self._layout.addWidget(widget)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self.setStyleSheet(f"""
            QFrame#interactive-card {{
                background:#0A1E2E;
                border:1px solid #00D9F5;
                border-radius:8px;
            }}
        """)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setStyleSheet(f"""
            QFrame#interactive-card {{
                background:#091620;
                border:1px solid #183746;
                border-radius:8px;
            }}
        """)
        super().leaveEvent(event)


class KPIMetricCard(GlassCard):
    """A key-performance-indicator card: big value, small change%, optional
    mini sparkline, and a trend badge. All values are real backend data."""

    def __init__(self, label="", value="—", change=None, sparkline=None,
                 parent=None):
        super().__init__(title=label, parent=None)
        self._value_lbl = make_label(str(value), 26, TEXT, bold=True, mono=True)
        self._layout.addWidget(self._value_lbl)

        row = QHBoxLayout()
        row.setSpacing(8)
        if change is not None:
            self._change_lbl = make_label(str(change), 11,
                                          GREEN if float(change) >= 0 else RED,
                                          bold=True, mono=True)
            row.addWidget(self._change_lbl)
        self._trend = make_label("", 9, CYAN, bold=True, mono=True)
        row.addWidget(self._trend)
        row.addStretch()
        self._layout.addLayout(row)

        if sparkline is not None:
            self._spark = Sparkline(width=120, height=24)
            self._spark.set_series(sparkline)
            self._layout.addWidget(self._spark)

    def set_value(self, value, change=None):
        self._value_lbl.setText(str(value))
        if change is not None and hasattr(self, "_change_lbl"):
            self._change_lbl.setText(str(change))
            self._change_lbl.setStyleSheet(
                f"color:{GREEN if float(change) >= 0 else RED}; "
                f"background:transparent; border:none;"
            )

    def set_trend(self, text, direction="neutral"):
        color = GREEN if direction == "up" else RED if direction == "down" else CYAN
        self._trend.setText(text)
        self._trend.setStyleSheet(f"color:{color}; background:transparent; border:none;")


class TrendBadge(QWidget):
    """A directional trend badge: up/down/neutral with colored text and dot."""

    def __init__(self, text="—", direction="neutral", parent=None):
        super().__init__(parent)
        self.setLayout(QHBoxLayout())
        self.layout().setContentsMargins(6, 2, 6, 2)
        self.layout().setSpacing(4)
        self._dot = QLabel("●")
        self._dot.setFixedSize(6, 6)
        self._dot.setStyleSheet(
            f"color:{GREEN if direction=='up' else RED if direction=='down' else MUTED};"
        )
        self.layout().addWidget(self._dot)
        self._text = make_label(text, 9, GREEN if direction == 'up'
                                else RED if direction == 'down' else MUTED,
                                bold=True)
        self.layout().addWidget(self._text)

    def set_trend(self, text, direction="neutral"):
        self._text.setText(text)
        color = GREEN if direction == 'up' else RED if direction == 'down' else MUTED
        self._text.setStyleSheet(f"color:{color}; background:transparent; border:none;")
        self._dot.setStyleSheet(f"color:{color};")


class DrillDownCard(GlassCard):
    """A GlassCard that emits a symbol string when clicked, for drill-down
    navigation to a detailed stock view."""

    symbolClicked = Signal(str)

    def __init__(self, symbol, price, change, sector, parent=None):
        super().__init__(title=symbol, subtitle=None, parent=None)
        self._symbol = symbol
        self._layout.addWidget(make_label(str(price), 20, TEXT, bold=True, mono=True))
        row = QHBoxLayout()
        row.setSpacing(6)
        change_lbl = make_label(str(change), 10,
                                GREEN if float(change) >= 0 else RED,
                                bold=True, mono=True)
        row.addWidget(change_lbl)
        row.addWidget(make_label(sector, 9, MUTED))
        row.addStretch()
        self._layout.addLayout(row)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.symbolClicked.emit(self._symbol)
        super().mousePressEvent(event)


class LiveTicker(QWidget):
    """A scrolling horizontal ticker showing latest prices and changes.
    Accepts (symbol, price, change) tuples and scrolls them left-to-right."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(28)
        self._items = []
        self._offset = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(40)

    def set_items(self, items):
        self._items = items
        self._offset = 0
        self.update()

    def _tick(self):
        self._offset -= 0.6
        if self._offset < -200:
            self._offset = 0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        painter.setPen(QPen(QColor(MUTED)))
        painter.setFont(font(9, mono=True))
        x = r.right() + self._offset
        for symbol, price, change in self._items:
            color = GREEN if change >= 0 else RED
            text = f"  {symbol}  {price}  {change:+.2f}%  "
            painter.setPen(QPen(QColor(color)))
            painter.drawText(int(x), int(r.center().y() + 4), text)
            x += painter.fontMetrics().horizontalAdvance(text) + 20
        painter.end()


class CollapsiblePanel(QWidget):
    """Enhanced collapsible section with animated toggle, chevron arrow,
    and optional availability badge. Keeps body state when collapsed."""

    def __init__(self, number, title, availability_text=None, parent=None):
        super().__init__(parent)
        self.setObjectName("interactive-card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.header = QPushButton()
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.setStyleSheet(f"""
            QPushButton {{
                text-align:left;
                background:transparent;
                border:none;
                border-bottom:1px solid #0F202B;
                padding:10px 14px;
            }}
            QPushButton:hover {{ background:#0A1E2E; border-radius:8px 8px 0 0; }}
        """)
        head_row = QHBoxLayout(self.header)
        head_row.setContentsMargins(2, 0, 8, 0)
        head_row.setSpacing(8)
        num_text = f"{number:02d}" if isinstance(number, int) else str(number)
        num = make_label(num_text, 11, CYAN, bold=True, mono=True)
        head_row.addWidget(num)
        title_lbl = make_label(title, 11, TEXT, bold=True)
        head_row.addWidget(title_lbl)
        head_row.addStretch()
        self._avail = QLabel()
        if availability_text is not None:
            self.set_availability(availability_text)
        head_row.addWidget(self._avail)
        self.arrow = make_label("▾", 11, MUTED, bold=True)
        head_row.addWidget(self.arrow)
        outer.addWidget(self.header)

        self.body = QWidget()
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 4, 12, 10)
        self.body_layout.setSpacing(6)
        outer.addWidget(self.body)

        self.header.toggled.connect(self._on_toggled)

    def set_availability(self, text):
        color = GREEN if str(text).upper() == "AVAILABLE" else (
            MUTED if str(text).upper() in ("N/A", "UNKNOWN", "NOT_AVAILABLE") else AMBER
        )
        self._avail.setText(str(text))
        self._avail.setFont(font(8, bold=True))
        self._avail.setStyleSheet(
            f"color:{color}; background:transparent; border:none;"
        )

    def add(self, widget):
        self.body_layout.addWidget(widget)

    def _on_toggled(self, expanded):
        self.body.setVisible(expanded)
        self.arrow.setText("▾" if expanded else "▸")


class DashboardGrid(QWidget):
    """Auto-arranging grid of KPIMetricCard widgets. Column count adapts to
    width; cards are evenly sized."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(10)
        self._cards = []

    def add_card(self, card):
        self._cards.append(card)
        self._rebuild()

    def clear(self):
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._cards = []

    def _rebuild(self):
        # Simple 4-column grid; wraps automatically via wrap logic
        from PySide6.QtWidgets import QGridLayout
        # Remove old grid
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        grid = QGridLayout()
        grid.setSpacing(12)
        cols = 4
        for i, card in enumerate(self._cards):
            r, c = divmod(i, cols)
            grid.addWidget(card, r, c)
        # Pad last row
        rem = len(self._cards) % cols
        if rem:
            for c in range(rem, cols):
                placeholder = QWidget()
                placeholder.setFixedHeight(150)
                grid.addWidget(placeholder, len(self._cards) // cols, c)
        self._layout.addLayout(grid)
