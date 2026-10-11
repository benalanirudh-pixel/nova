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

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QPainter, QPen
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
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
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
        self.setStyleSheet("background:transparent;")

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
