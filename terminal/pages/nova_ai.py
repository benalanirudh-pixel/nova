"""Terminal Nova AI workspace page — wraps brain.think() in a QThread."""
from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QFrame, QScrollArea, QTextEdit, QSizePolicy, QPushButton,
)

from styles.design_tokens import (
    BG, SURFACE, SURFACE_ALT, CYAN, GREEN, RED, AMBER, MUTED, MUTED2, TEXT, BORDER, BORDER_BRIGHT, SECONDARY,
)

try:
    from brain import think, reset, MODEL, BrainError
    _BRAIN_AVAILABLE = True
except Exception:
    _BRAIN_AVAILABLE = False
    MODEL = "unavailable"
    BrainError = Exception

    def think(text: str) -> str:  # type: ignore[misc]
        raise RuntimeError("brain module not available")

    def reset() -> None:  # type: ignore[misc]
        pass


def _lbl(text, size=10, color=TEXT, bold=False):
    lbl = QLabel(str(text))
    lbl.setStyleSheet(
        f"color:{color}; font-size:{size}px;"
        f" font-weight:{'bold' if bold else 'normal'};"
        f" background:transparent;"
    )
    return lbl


class _BrainWorker(QThread):
    answered = Signal(str)
    errored = Signal(str)

    def __init__(self, prompt: str):
        super().__init__()
        self._prompt = prompt

    def run(self):
        try:
            response = think(self._prompt)
            self.answered.emit(response)
        except BrainError as exc:
            self.errored.emit(f"Brain error: {exc}")
        except Exception as exc:
            self.errored.emit(f"Error: {exc}")


class _MessageBubble(QFrame):
    """Single chat message."""

    def __init__(self, role: str, text: str, parent=None):
        super().__init__(parent)
        is_user = role == "user"
        bg = BG if is_user else SURFACE
        border = BORDER if is_user else CYAN
        self.setStyleSheet(
            f"QFrame {{ background:{bg}; border:1px solid {border};"
            f" border-radius:4px; }}"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)

        role_lbl = _lbl("YOU" if is_user else f"NOVA  ·  {MODEL}", 8,
                         MUTED if is_user else CYAN, bold=True)
        lay.addWidget(role_lbl)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setStyleSheet(
            f"color:{TEXT}; font-size:11px; background:transparent;"
        )
        lay.addWidget(body)


class NovaAIPage(QWidget):
    """Chat workspace powered by brain.think() (Ollama)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker: _BrainWorker | None = None
        self._setup_ui()

    # ------------------------------------------------------------------

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Header bar
        bar = QFrame()
        bar.setObjectName("AIBar")
        bar.setFixedHeight(44)
        bar.setStyleSheet(
            f"QFrame#AIBar {{ background:{SURFACE}; border-bottom:1px solid {BORDER}; }}"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(14, 6, 14, 6)
        bl.setSpacing(10)
        bl.addWidget(_lbl("NOVA AI", 12, CYAN, bold=True))
        bl.addWidget(_lbl(f"model: {MODEL}", 9, MUTED))
        bl.addStretch()

        self._status_lbl = _lbl("Ready" if _BRAIN_AVAILABLE else "Ollama unavailable", 9,
                                  GREEN if _BRAIN_AVAILABLE else AMBER)
        bl.addWidget(self._status_lbl)

        reset_btn = QPushButton("RESET")
        reset_btn.setFixedHeight(28)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background:transparent; color:{MUTED}; border:1px solid {BORDER};
                border-radius:3px; font-size:9px; font-weight:600; padding:0 10px;
            }}
            QPushButton:hover {{ color:{TEXT}; border-color:{BORDER_BRIGHT}; background:{SURFACE_ALT}; }}
            QPushButton:pressed {{ background:{BORDER}; }}
        """)
        reset_btn.clicked.connect(self._reset_chat)
        bl.addWidget(reset_btn)
        outer.addWidget(bar)

        # Chat scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"QScrollArea {{ background:{BG}; border:none; }}")

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet(f"background:{BG};")
        self._chat_lay = QVBoxLayout(self._chat_container)
        self._chat_lay.setContentsMargins(16, 16, 16, 8)
        self._chat_lay.setSpacing(10)
        self._chat_lay.setAlignment(Qt.AlignmentFlag.AlignTop)

        # Welcome message
        self._add_bubble("assistant",
            "Nova AI is ready. Ask me about market conditions, technical analysis, "
            "or anything about the Indian equity market. Analysis-only — no buy/sell calls.")

        self._scroll.setWidget(self._chat_container)
        outer.addWidget(self._scroll, 1)

        # Typing indicator (hidden by default)
        self._typing_lbl = _lbl("Nova is thinking…", 10, CYAN)
        self._typing_lbl.setContentsMargins(16, 4, 16, 4)
        self._typing_lbl.setVisible(False)
        outer.addWidget(self._typing_lbl)

        # Input bar
        input_bar = QFrame()
        input_bar.setObjectName("InputBar")
        input_bar.setStyleSheet(
            f"QFrame#InputBar {{ background:{SURFACE}; border-top:1px solid {BORDER}; }}"
        )
        il = QHBoxLayout(input_bar)
        il.setContentsMargins(14, 8, 14, 8)
        il.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Nova something…")
        self._input.setStyleSheet(
            f"QLineEdit {{ background:{BG}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:3px; padding:6px 10px; font-size:12px; }}"
        )
        self._input.returnPressed.connect(self._send)
        il.addWidget(self._input, 1)

        send_btn = QPushButton("SEND")
        send_btn.setFixedHeight(36)
        send_btn.setMinimumWidth(70)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background:{CYAN}; color:#000; border:none;
                border-radius:3px; font-size:11px; font-weight:700;
                padding:0 18px; letter-spacing:1px;
            }}
            QPushButton:hover {{ background:#33E8FF; }}
            QPushButton:pressed {{ background:#00B8D4; }}
        """)
        send_btn.clicked.connect(self._send)
        il.addWidget(send_btn)
        outer.addWidget(input_bar)

    # ------------------------------------------------------------------

    def _add_bubble(self, role: str, text: str):
        bubble = _MessageBubble(role, text)
        self._chat_lay.addWidget(bubble)
        # scroll to bottom
        self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        )

    def _send(self):
        text = self._input.text().strip()
        if not text:
            return
        if not _BRAIN_AVAILABLE:
            self._add_bubble("user", text)
            self._add_bubble("assistant",
                "Ollama is not running. Start Ollama and restart Nova to use AI features.")
            self._input.clear()
            return

        self._input.clear()
        self._add_bubble("user", text)
        self._typing_lbl.setVisible(True)
        self._status_lbl.setText("Thinking…")
        self._status_lbl.setStyleSheet(f"color:{CYAN};")

        if self._worker and self._worker.isRunning():
            return  # ignore if already thinking

        self._worker = _BrainWorker(text)
        self._worker.answered.connect(self._on_answer)
        self._worker.errored.connect(self._on_error)
        self._worker.start()

    def _on_answer(self, text: str):
        self._typing_lbl.setVisible(False)
        self._status_lbl.setText("Ready")
        self._status_lbl.setStyleSheet(f"color:{GREEN};")
        self._add_bubble("assistant", text)

    def _on_error(self, err: str):
        self._typing_lbl.setVisible(False)
        self._status_lbl.setText("Error")
        self._status_lbl.setStyleSheet(f"color:{RED};")
        self._add_bubble("assistant", f"[Error] {err}")

    def submit_query(self, text: str):
        """Called from main window search bar (/AI <text>)."""
        self._input.setText(text)
        self._send()

    def _reset_chat(self):
        try:
            reset()
        except Exception:
            pass
        # Clear bubbles
        while self._chat_lay.count():
            item = self._chat_lay.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        self._add_bubble("assistant", "Conversation reset.")
        self._status_lbl.setText("Ready")
        self._status_lbl.setStyleSheet(f"color:{GREEN};")
