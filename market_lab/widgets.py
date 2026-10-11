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
SIDEBAR = "#070F16"
PANEL = "#09141D"
PANEL_ALT = "#0D1D28"
BORDER = "#1B3443"

TEXT = "#E6F0F7"
MUTED = "#8298AA"

GREEN = "#20E69A"
CYAN = "#36DDF2"
PURPLE = "#B49AFF"
AMBER = "#FFC45B"
RED = "#FF465B"
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
            alternate-background-color:{PANEL};
            color:{TEXT};
            gridline-color:{BORDER};
            border:1px solid {BORDER};
            border-radius:6px;
        }}
        QHeaderView::section {{
            background:{PANEL};
            color:{MUTED};
            border:none;
            border-bottom:1px solid {BORDER};
            padding:4px 6px;
            font-size:8pt;
        }}
        QTableWidget::item {{ padding:3px 6px; font-size:9pt; }}
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
