"""Terminal Institutional Flows page — FII/DII flows from cached report."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QScrollArea,
)

from market_lab import view_model as vm
from styles.design_tokens import (
    BG, SURFACE, CYAN, GREEN, RED, AMBER, MUTED, TEXT, BORDER, SECONDARY,
)

N_A = vm.N_A


def _lbl(text, size=10, color=TEXT, bold=False, mono=False):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}px;"
        f" font-weight:{'bold' if bold else 'normal'};"
        f" font-family:{'Consolas' if mono else 'Segoe UI'};"
        f" background:transparent;"
    )
    return lbl


def _kv_row(key, value, color=SECONDARY):
    row = QHBoxLayout()
    row.setSpacing(8)
    row.addWidget(_lbl(key, 9, MUTED))
    row.addStretch()
    row.addWidget(_lbl(str(value) if value is not None else N_A, 9, color, mono=True))
    return row


def _sign_color(v):
    try:
        return GREEN if float(v) >= 0 else RED
    except (TypeError, ValueError):
        return MUTED


def _fmt_crore(v):
    if v is None:
        return N_A
    try:
        f = float(v)
        sign = "+" if f >= 0 else ""
        return f"{sign}₹{abs(f)/1e7:.2f}Cr"
    except (TypeError, ValueError):
        return str(v)


def _section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setStyleSheet(
        f"QFrame {{ background:{SURFACE}; border:1px solid {BORDER}; border-radius:4px; }}"
    )
    lay = QVBoxLayout(frame)
    lay.setContentsMargins(14, 12, 14, 12)
    lay.setSpacing(6)
    if title:
        lay.addWidget(_lbl(title, 10, CYAN, bold=True))
    return frame, lay


class InstitutionalPage(QWidget):
    """FII/DII flows, streaks, and regime from market report."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:none; }}")

        self._content = QWidget()
        self._content.setStyleSheet(f"background:{BG};")
        self._lay = QVBoxLayout(self._content)
        self._lay.setContentsMargins(16, 16, 16, 16)
        self._lay.setSpacing(12)
        self._lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._placeholder = _lbl("Load market data to see institutional flows.", 12, MUTED)
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lay.addWidget(self._placeholder, alignment=Qt.AlignmentFlag.AlignCenter)

        scroll.setWidget(self._content)
        outer.addWidget(scroll, 1)

    def set_report(self, report: dict):
        self._report = report
        self._rebuild()

    def _clear(self):
        while self._lay.count():
            item = self._lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)

    def _rebuild(self):
        self._clear()
        if not self._report:
            self._lay.addWidget(
                _lbl("No report loaded.", 12, MUTED),
                alignment=Qt.AlignmentFlag.AlignCenter,
            )
            return

        flow = vm.flow_block(self._report)

        # --- Flow regime card ---
        fr, fl = _section("FLOW REGIME")
        regime = flow.get("flow_regime", N_A)
        streak = flow.get("fii_streak", N_A)
        fl.addLayout(_kv_row("Overall Regime", str(regime), CYAN))
        fl.addLayout(_kv_row("FII Streak", str(streak), AMBER))
        self._lay.addWidget(fr)

        # --- FII flows ---
        fii_f, fii_l = _section("FII NET FLOWS")
        for key, label in [
            ("fii_5d", "5-Day Net"),
            ("fii_10d", "10-Day Net"),
            ("fii_20d", "20-Day Net"),
        ]:
            val = flow.get(key)
            fii_l.addLayout(_kv_row(label, _fmt_crore(val), _sign_color(val)))
        fii_buy = flow.get("fii_buy_20d")
        fii_sell = flow.get("fii_sell_20d")
        if fii_buy is not None:
            fii_l.addLayout(_kv_row("Gross Buy 20D", _fmt_crore(fii_buy), GREEN))
        if fii_sell is not None:
            fii_l.addLayout(_kv_row("Gross Sell 20D", _fmt_crore(fii_sell), RED))
        self._lay.addWidget(fii_f)

        # --- DII flows ---
        dii_f, dii_l = _section("DII NET FLOWS")
        for key, label in [
            ("dii_5d", "5-Day Net"),
            ("dii_10d", "10-Day Net"),
            ("dii_20d", "20-Day Net"),
        ]:
            val = flow.get(key)
            dii_l.addLayout(_kv_row(label, _fmt_crore(val), _sign_color(val)))
        dii_buy = flow.get("dii_buy_20d")
        dii_sell = flow.get("dii_sell_20d")
        if dii_buy is not None:
            dii_l.addLayout(_kv_row("Gross Buy 20D", _fmt_crore(dii_buy), GREEN))
        if dii_sell is not None:
            dii_l.addLayout(_kv_row("Gross Sell 20D", _fmt_crore(dii_sell), RED))
        self._lay.addWidget(dii_f)

        # --- interpretation ---
        interp = flow.get("interpretation")
        if interp and interp != N_A:
            note_f, note_l = _section("")
            note = _lbl(str(interp), 10, TEXT)
            note.setWordWrap(True)
            note_l.addWidget(note)
            self._lay.addWidget(note_f)

        if not flow.get("available"):
            self._lay.addWidget(_lbl("Flow data not available in current report.", 9, AMBER))

        self._lay.addStretch()
