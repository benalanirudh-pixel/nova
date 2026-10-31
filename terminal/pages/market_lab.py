"""Terminal Market Lab page — full JSON report viewer + AI narrative."""
from __future__ import annotations

import json

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QScrollArea, QPlainTextEdit, QSplitter,
)

from market_lab import view_model as vm
from styles.design_tokens import (
    BG, SURFACE, CYAN, GREEN, RED, AMBER, MUTED, TEXT, BORDER, SECONDARY,
)

try:
    from market_lab.market_lab_brain import analyze_market_lab
    _BRAIN_OK = True
except Exception:
    _BRAIN_OK = False

    def analyze_market_lab(*_a, **_kw):  # type: ignore[misc]
        return "Market Lab brain not available."


def _lbl(text, size=10, color=TEXT, bold=False):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}px;"
        f" font-weight:{'bold' if bold else 'normal'};"
        f" background:transparent;"
    )
    return lbl


class MarketLabPage(QWidget):
    """Shows full report JSON and optional AI narrative."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._report: dict | None = None
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toolbar
        bar = QFrame()
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"QFrame {{ background:{SURFACE}; border-bottom:1px solid {BORDER}; }}"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 6, 14, 6)
        bl.setSpacing(10)
        bl.addWidget(_lbl("MARKET LAB", 12, CYAN, bold=True))
        bl.addWidget(_lbl("Full report data + AI narrative", 9, MUTED))
        bl.addStretch()

        self._status_lbl = _lbl("No report loaded", 9, MUTED)
        bl.addWidget(self._status_lbl)

        narrate_btn = QLabel("  AI NARRATE  ")
        narrate_btn.setFixedHeight(28)
        narrate_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        narrate_btn.setStyleSheet(
            f"QLabel {{ background:{CYAN}; color:#000; font-size:10px;"
            f" font-weight:bold; border-radius:3px; padding:0 6px; }}"
        )
        narrate_btn.mousePressEvent = lambda _: self._narrate()
        bl.addWidget(narrate_btn)
        outer.addWidget(bar)

        # Splitter: JSON (left) | Narrative (right)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.setStyleSheet(f"QSplitter::handle {{ background:{BORDER}; }}")

        # JSON panel
        json_widget = QWidget()
        json_widget.setStyleSheet(f"background:{BG};")
        jl = QVBoxLayout(json_widget)
        jl.setContentsMargins(10, 10, 10, 10)
        jl.setSpacing(6)
        jl.addWidget(_lbl("REPORT JSON", 9, MUTED, bold=True))
        self._json_view = QPlainTextEdit()
        self._json_view.setReadOnly(True)
        self._json_view.setPlaceholderText("Report data will appear here after loading.")
        self._json_view.setStyleSheet(
            f"QPlainTextEdit {{ background:{SURFACE}; color:{SECONDARY};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-family:Consolas; font-size:9px; padding:6px; }}"
        )
        jl.addWidget(self._json_view, 1)
        splitter.addWidget(json_widget)

        # Narrative panel
        narr_widget = QWidget()
        narr_widget.setStyleSheet(f"background:{BG};")
        nl = QVBoxLayout(narr_widget)
        nl.setContentsMargins(10, 10, 10, 10)
        nl.setSpacing(6)
        nl.addWidget(_lbl("AI NARRATIVE", 9, MUTED, bold=True))
        self._narr_view = QPlainTextEdit()
        self._narr_view.setReadOnly(True)
        self._narr_view.setPlaceholderText(
            "Press AI NARRATE to generate a market narrative from the loaded report."
        )
        self._narr_view.setStyleSheet(
            f"QPlainTextEdit {{ background:{SURFACE}; color:{TEXT};"
            f" border:1px solid {BORDER}; border-radius:3px;"
            f" font-size:11px; padding:8px; }}"
        )
        nl.addWidget(self._narr_view, 1)
        splitter.addWidget(narr_widget)

        splitter.setSizes([600, 600])
        outer.addWidget(splitter, 1)

    # ------------------------------------------------------------------

    def set_report(self, report: dict):
        self._report = report
        age = vm.data_age(report)
        self._status_lbl.setText(f"Report loaded · {age.get('label', '')}")
        self._status_lbl.setStyleSheet(f"color:{GREEN};")
        try:
            text = json.dumps(report, indent=2, ensure_ascii=False)
        except Exception as exc:
            text = f"JSON serialization error: {exc}"
        self._json_view.setPlainText(text)

    def _narrate(self):
        if not self._report:
            self._narr_view.setPlainText("No report loaded. Load market data first.")
            return
        self._narr_view.setPlainText("Generating narrative…")
        self._status_lbl.setText("Generating…")
        self._status_lbl.setStyleSheet(f"color:{CYAN};")
        try:
            text = analyze_market_lab(self._report)
        except Exception as exc:
            text = f"Error generating narrative: {exc}"
        self._narr_view.setPlainText(text or "No narrative generated.")
        self._status_lbl.setText("Done")
        self._status_lbl.setStyleSheet(f"color:{GREEN};")
