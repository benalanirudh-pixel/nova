from __future__ import annotations

import sys
import time
import json
import urllib.request
import subprocess
import platform

import psutil

from PySide6.QtCore import (
    Qt,
    QThread,
    Signal,
    QTimer,
)

from PySide6.QtGui import (
    QColor,
    QFont,
)

from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from brain import (
    BrainError,
    MODEL,
    reset,
    think,
)

from nova3dcore import Nova3DCore

from tts import (
    TTSError,
    speak,
)

from voice import (
    VoiceError,
    listen_for_session_event,
)


# ============================================================
# CONFIG
# ============================================================

APP_NAME = "NOVA"

OLLAMA_URL = "http://127.0.0.1:11434/api/tags"
SEARXNG_URL = "http://127.0.0.1:8080/"

BG = "#02070B"
PANEL = "#061118"
PANEL_2 = "#081720"
PANEL_3 = "#0A1C25"

BORDER = "#12313D"
BORDER_BRIGHT = "#1B6170"

TEXT = "#EAF7FA"
MUTED = "#64818A"

GREEN = "#39F0B2"
CYAN = "#35DFFF"
PURPLE = "#A77CFF"
RED = "#FF5C70"
AMBER = "#FFC857"


# ============================================================
# HELPERS
# ============================================================

def fetch_json(url, timeout=1.5):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Nova/1.0"
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=timeout,
    ) as response:

        return json.loads(
            response.read().decode("utf-8")
        )


def speed_text(value):

    if value < 1024:
        return f"{value:.0f} B/s"

    if value < 1024 ** 2:
        return f"{value / 1024:.1f} KB/s"

    if value < 1024 ** 3:
        return f"{value / 1024 ** 2:.1f} MB/s"

    return f"{value / 1024 ** 3:.2f} GB/s"


def uptime_text():

    seconds = int(
        time.time() - psutil.boot_time()
    )

    days, remainder = divmod(
        seconds,
        86400,
    )

    hours, remainder = divmod(
        remainder,
        3600,
    )

    minutes, _ = divmod(
        remainder,
        60,
    )

    if days:
        return f"{days}d {hours:02d}h"

    if hours:
        return f"{hours}h {minutes:02d}m"

    return f"{minutes}m"


def gpu_info():

    try:

        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=1.5,
        )

        if result.returncode != 0:
            return None

        line = result.stdout.strip().splitlines()[0]

        parts = [
            item.strip()
            for item in line.split(",")
        ]

        return (
            float(parts[0]),
            float(parts[1]),
            float(parts[2]),
        )

    except Exception:

        return None


# ============================================================
# BRAIN WORKER
# ============================================================

class BrainWorker(QThread):

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, message):

        super().__init__()

        self.message = message

    def run(self):

        try:

            response = think(
                self.message
            )

            self.finished.emit(
                response
                or "Sorry, I didn't get a response."
            )

        except BrainError as exc:

            self.failed.emit(
                str(exc)
            )

        except Exception as exc:

            self.failed.emit(
                f"Unexpected error: {exc}"
            )


# ============================================================
# VOICE WORKER
# ============================================================

class VoiceWorker(QThread):

    status = Signal(str)
    user_message = Signal(str)
    nova_message = Signal(str)
    error = Signal(str)
    stopped = Signal()

    def __init__(self):

        super().__init__()

        self.running = True

    def stop(self):

        self.running = False

        self.requestInterruption()

    def run(self):

        try:

            self.status.emit(
                "Waiting for activation..."
            )

            while (
                self.running
                and not self.isInterruptionRequested()
            ):

                event, text = (
                    listen_for_session_event()
                )

                if not self.running:
                    break

                # ------------------------------------------------
                # ACTIVATION
                # ------------------------------------------------

                if event == "activate":

                    self.status.emit(
                        "Nova active"
                    )

                    greeting = (
                        "Hi Anirudh, how can I help you?"
                    )

                    self.nova_message.emit(
                        greeting
                    )

                    self.status.emit(
                        "Speaking..."
                    )

                    try:

                        speak(
                            greeting
                        )

                    except Exception:

                        pass

                    if self.running:

                        self.status.emit(
                            "Nova active"
                        )

                    continue

                # ------------------------------------------------
                # COMMAND
                # ------------------------------------------------

                if event == "command":

                    command = (
                        text or ""
                    ).strip()

                    if not command:
                        continue

                    self.user_message.emit(
                        command
                    )

                    self.status.emit(
                        "Thinking..."
                    )

                    try:

                        response = think(
                            command
                        )

                    except BrainError as exc:

                        response = str(exc)

                    except Exception as exc:

                        response = (
                            f"Unexpected error: {exc}"
                        )

                    response = (
                        response
                        or "Sorry, I didn't get a response."
                    )

                    self.nova_message.emit(
                        response
                    )

                    if not self.running:
                        break

                    self.status.emit(
                        "Speaking..."
                    )

                    try:

                        speak(
                            response
                        )

                    except TTSError as exc:

                        self.error.emit(
                            str(exc)
                        )

                    except Exception as exc:

                        self.error.emit(
                            f"TTS error: {exc}"
                        )

                    if self.running:

                        self.status.emit(
                            "Nova active"
                        )

                    continue

                # ------------------------------------------------
                # DEACTIVATION
                # ------------------------------------------------

                if event == "deactivate":

                    goodbye = (
                        "Alright, Anirudh. I'll be here."
                    )

                    self.nova_message.emit(
                        goodbye
                    )

                    self.status.emit(
                        "Speaking..."
                    )

                    try:

                        speak(
                            goodbye
                        )

                    except Exception:

                        pass

                    if self.running:

                        self.status.emit(
                            "Waiting for activation..."
                        )

        except VoiceError as exc:

            if self.running:

                self.error.emit(
                    str(exc)
                )

        except Exception as exc:

            if self.running:

                self.error.emit(
                    f"Voice error: {exc}"
                )

        finally:

            self.stopped.emit()


# ============================================================
# SERVICE WORKER
# ============================================================

class ServiceWorker(QThread):

    result = Signal(
        str,
        bool,
        str,
    )

    def run(self):

        # --------------------------------------------------------
        # OLLAMA
        # --------------------------------------------------------

        try:

            data = fetch_json(
                OLLAMA_URL
            )

            models = [
                item.get(
                    "name",
                    "",
                )
                for item in data.get(
                    "models",
                    [],
                )
            ]

            if MODEL in models:

                detail = (
                    "ONLINE • MODEL READY"
                )

            else:

                detail = "ONLINE"

            self.result.emit(
                "OLLAMA",
                True,
                detail,
            )

        except Exception:

            self.result.emit(
                "OLLAMA",
                False,
                "OFFLINE",
            )

        # --------------------------------------------------------
        # SEARXNG
        # --------------------------------------------------------

        try:

            request = urllib.request.Request(
                SEARXNG_URL,
                headers={
                    "User-Agent": "Nova/1.0"
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=1.5,
            ) as response:

                if not (
                    200
                    <= response.status
                    < 400
                ):

                    raise RuntimeError()

            self.result.emit(
                "SEARXNG",
                True,
                "ONLINE",
            )

        except Exception:

            self.result.emit(
                "SEARXNG",
                False,
                "OFFLINE",
            )


# ============================================================
# SERVICE CARD
# ============================================================

class ServiceCard(QFrame):

    def __init__(
        self,
        name,
    ):

        super().__init__()

        self.setObjectName(
            "serviceCard"
        )

        layout = QHBoxLayout(
            self
        )

        layout.setContentsMargins(
            10,
            7,
            10,
            7,
        )

        layout.setSpacing(
            8
        )

        self.dot = QLabel(
            "●"
        )

        self.dot.setObjectName(
            "serviceDot"
        )

        self.name = QLabel(
            name
        )

        self.name.setObjectName(
            "serviceName"
        )

        self.detail = QLabel(
            "CHECKING"
        )

        self.detail.setObjectName(
            "serviceDetail"
        )

        layout.addWidget(
            self.dot
        )

        layout.addWidget(
            self.name
        )

        layout.addStretch()

        layout.addWidget(
            self.detail
        )

    def set_status(
        self,
        online,
        detail,
        color=None,
    ):

        if color is None:

            color = (
                GREEN
                if online
                else RED
            )

        self.dot.setStyleSheet(
            f"""
            color: {color};
            font-size: 9px;
            """
        )

        self.detail.setText(
            detail
        )

        self.detail.setStyleSheet(
            f"""
            color: {color};
            font-family: Consolas;
            font-size: 7px;
            font-weight: bold;
            """
        )


# ============================================================
# TELEMETRY CARD
# ============================================================

class TelemetryCard(QFrame):

    def __init__(
        self,
        title,
    ):

        super().__init__()

        self.setObjectName(
            "telemetryCard"
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            10,
            7,
            10,
            7,
        )

        layout.setSpacing(
            3
        )

        top = QHBoxLayout()

        self.title = QLabel(
            title
        )

        self.title.setObjectName(
            "telemetryTitle"
        )

        self.value = QLabel(
            "0%"
        )

        self.value.setObjectName(
            "telemetryValue"
        )

        top.addWidget(
            self.title
        )

        top.addStretch()

        top.addWidget(
            self.value
        )

        layout.addLayout(
            top
        )

        self.bar = QFrame()

        self.bar.setObjectName(
            "telemetryBar"
        )

        self.bar.setFixedHeight(
            3
        )

        layout.addWidget(
            self.bar
        )

    def update_value(
        self,
        value,
    ):

        value = max(
            0,
            min(
                100,
                float(value),
            ),
        )

        self.value.setText(
            f"{value:.0f}%"
        )

        self.bar.setStyleSheet(
            f"""
            QFrame#telemetryBar {{
                background:
                    qlineargradient(
                        x1:0,
                        y1:0,
                        x2:1,
                        y2:0,
                        stop:0 {GREEN},
                        stop:{value / 100:.3f} {GREEN},
                        stop:{value / 100:.3f} #10252E,
                        stop:1 #10252E
                    );
                border-radius: 2px;
            }}
            """
        )


# ============================================================
# CHAT BUBBLE
# ============================================================

class ChatBubble(QFrame):

    def __init__(
        self,
        speaker,
        message,
        user=False,
    ):

        super().__init__()

        self.setObjectName(
            "userBubble"
            if user
            else "novaBubble"
        )

        layout = QVBoxLayout(
            self
        )

        layout.setContentsMargins(
            11,
            8,
            11,
            8,
        )

        header = QHBoxLayout()

        name = QLabel(
            speaker.upper()
        )

        name.setObjectName(
            "bubbleName"
        )

        timestamp = QLabel(
            time.strftime(
                "%H:%M"
            )
        )

        timestamp.setObjectName(
            "bubbleTime"
        )

        header.addWidget(
            name
        )

        header.addStretch()

        header.addWidget(
            timestamp
        )

        text = QLabel(
            message
        )

        text.setObjectName(
            "bubbleText"
        )

        text.setWordWrap(
            True
        )

        text.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )

        layout.addLayout(
            header
        )

        layout.addWidget(
            text
        )


# ============================================================
# QUICK ACTION
# ============================================================

class QuickAction(QPushButton):

    def __init__(
        self,
        title,
        subtitle,
    ):

        super().__init__()

        self.setText(
            f"{title}\n{subtitle}"
        )

        self.setObjectName(
            "quickAction"
        )

        self.setCursor(
            Qt.PointingHandCursor
        )


# ============================================================
# NOVA WINDOW
# ============================================================

class NovaWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.voice_worker = None
        self.brain_worker = None
        self.service_worker = None

        self.rx_previous = (
            psutil.net_io_counters().bytes_recv
        )

        self.tx_previous = (
            psutil.net_io_counters().bytes_sent
        )

        self.net_time = time.time()

        self.setWindowTitle(
            "NOVA — Personal Intelligence System"
        )

        self.resize(
            1600,
            920,
        )

        self.setMinimumSize(
            1200,
            720,
        )

        self.build_ui()

        self.setup_timers()

        self.append_nova(
            "Nova online. Systems initialized and ready."
        )

    # ========================================================
    # BUILD UI
    # ========================================================

    def build_ui(self):

        central = QWidget()

        central.setObjectName(
            "central"
        )

        self.setCentralWidget(
            central
        )

        root = QVBoxLayout(
            central
        )

        root.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        root.setSpacing(
            8
        )

        # ====================================================
        # HEADER
        # ====================================================

        header = QFrame()

        header.setObjectName(
            "topBar"
        )

        header_layout = QHBoxLayout(
            header
        )

        header_layout.setContentsMargins(
            15,
            8,
            12,
            8,
        )

        logo = QLabel(
            "N O V A"
        )

        logo.setObjectName(
            "logo"
        )

        identity = QVBoxLayout()

        identity_title = QLabel(
            "PERSONAL INTELLIGENCE SYSTEM"
        )

        identity_title.setObjectName(
            "identityTitle"
        )

        identity_subtitle = QLabel(
            "THINK  •  ANALYZE  •  ASSIST  •  EVOLVE"
        )

        identity_subtitle.setObjectName(
            "identitySubtitle"
        )

        identity.addWidget(
            identity_title
        )

        identity.addWidget(
            identity_subtitle
        )

        header_layout.addWidget(
            logo
        )

        header_layout.addLayout(
            identity
        )

        header_layout.addStretch()

        for text in (
            "HOME",
            "SYSTEM",
            "TOOLS",
            "SETTINGS",
        ):

            button = QPushButton(
                text
            )

            button.setObjectName(
                "navButton"
            )

            header_layout.addWidget(
                button
            )

        self.active_indicator = QLabel(
            "● NOVA ACTIVE\n"
            "  READY FOR COMMAND"
        )

        self.active_indicator.setObjectName(
            "activeIndicator"
        )

        header_layout.addWidget(
            self.active_indicator
        )

        self.clock = QLabel(
            "--:--:--"
        )

        self.clock.setObjectName(
            "headerClock"
        )

        header_layout.addWidget(
            self.clock
        )

        root.addWidget(
            header
        )

        # ====================================================
        # THREE COLUMNS
        # ====================================================

        columns = QHBoxLayout()

        columns.setSpacing(
            8
        )

        root.addLayout(
            columns,
            1,
        )

        # ====================================================
        # LEFT
        # ====================================================

        left = QFrame()

        left.setObjectName(
            "panel"
        )

        left.setMinimumWidth(
            260
        )

        left.setMaximumWidth(
            310
        )

        left_layout = QVBoxLayout(
            left
        )

        left_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        left_layout.setSpacing(
            6
        )

        status_title = QLabel(
            "SYSTEM STATUS"
        )

        status_title.setObjectName(
            "sectionTitle"
        )

        left_layout.addWidget(
            status_title
        )

        self.services = {}

        for name in (
            "OLLAMA",
            "WHISPER",
            "PIPER",
            "SEARXNG",
            "GPU",
        ):

            card = ServiceCard(
                name
            )

            self.services[name] = card

            left_layout.addWidget(
                card
            )

        telemetry_title = QLabel(
            "TELEMETRY"
        )

        telemetry_title.setObjectName(
            "sectionTitle"
        )

        left_layout.addWidget(
            telemetry_title
        )

        self.cpu_card = TelemetryCard(
            "CPU"
        )

        self.ram_card = TelemetryCard(
            "RAM"
        )

        self.gpu_card = TelemetryCard(
            "GPU"
        )

        self.disk_card = TelemetryCard(
            "DISK"
        )

        left_layout.addWidget(
            self.cpu_card
        )

        left_layout.addWidget(
            self.ram_card
        )

        left_layout.addWidget(
            self.gpu_card
        )

        left_layout.addWidget(
            self.disk_card
        )

        info_title = QLabel(
            "SYSTEM INFORMATION"
        )

        info_title.setObjectName(
            "sectionTitle"
        )

        left_layout.addWidget(
            info_title
        )

        self.system_info = QLabel(
            "UPTIME       --\n"
            "PLATFORM     --\n"
            "CPU          --\n"
            "MEMORY       --\n"
            "STORAGE      --\n"
            "NETWORK      --"
        )

        self.system_info.setObjectName(
            "systemInfo"
        )

        left_layout.addWidget(
            self.system_info
        )

        left_layout.addStretch()

        columns.addWidget(
            left,
            0,
        )

        # ====================================================
        # CENTER
        # ====================================================

        center = QFrame()

        center.setObjectName(
            "panel"
        )

        center_layout = QVBoxLayout(
            center
        )

        center_layout.setContentsMargins(
            8,
            8,
            8,
            8,
        )

        center_layout.setSpacing(
            5
        )

        core_header = QHBoxLayout()

        core_title = QLabel(
            "NEURAL CORE"
        )

        core_title.setObjectName(
            "sectionTitle"
        )

        self.core_status = QLabel(
            "IDLE"
        )

        self.core_status.setObjectName(
            "coreStatus"
        )

        core_header.addWidget(
            core_title
        )

        core_header.addStretch()

        core_header.addWidget(
            self.core_status
        )

        center_layout.addLayout(
            core_header
        )

        # ====================================================
        # REAL OPENGL 3D CORE
        # ====================================================

        self.core = Nova3DCore()

        self.core.setAttribute(
            Qt.WA_TranslucentBackground,
            True,
        )

        self.core.setAutoFillBackground(
            False
        )

        center_layout.addWidget(
            self.core,
            1,
        )

        self.core_caption = QLabel(
            "N O V A"
        )

        self.core_caption.setObjectName(
            "coreCaption"
        )

        center_layout.addWidget(
            self.core_caption
        )

        self.core_subtitle = QLabel(
            "LISTENING  •  THINKING  •  ASSISTING  •  EVOLVING"
        )

        self.core_subtitle.setObjectName(
            "coreSubtitle"
        )

        center_layout.addWidget(
            self.core_subtitle
        )

        # ====================================================
        # QUICK ACTIONS
        # ====================================================

        quick = QHBoxLayout()

        self.voice_action = QuickAction(
            "◉  VOICE",
            "ACTIVATE    F2",
        )

        self.search_action = QuickAction(
            "◎  SEARCH",
            "WEB          F3",
        )

        self.analyze_action = QuickAction(
            "▥  ANALYZE",
            "DATA         F4",
        )

        self.automate_action = QuickAction(
            "⚙  AUTOMATE",
            "SYSTEM       F5",
        )

        quick.addWidget(
            self.voice_action
        )

        quick.addWidget(
            self.search_action
        )

        quick.addWidget(
            self.analyze_action
        )

        quick.addWidget(
            self.automate_action
        )

        center_layout.addLayout(
            quick
        )

        # ====================================================
        # COMMAND BAR
        # ====================================================

        command_frame = QFrame()

        command_frame.setObjectName(
            "commandFrame"
        )

        command_layout = QHBoxLayout(
            command_frame
        )

        command_layout.setContentsMargins(
            10,
            4,
            4,
            4,
        )

        self.command_input = QLineEdit()

        self.command_input.setObjectName(
            "commandInput"
        )

        self.command_input.setPlaceholderText(
            "Talk to Nova..."
        )

        self.command_input.returnPressed.connect(
            self.send_text
        )

        send = QPushButton(
            "➤"
        )

        send.setObjectName(
            "sendButton"
        )

        send.clicked.connect(
            self.send_text
        )

        command_layout.addWidget(
            self.command_input
        )

        command_layout.addWidget(
            send
        )

        center_layout.addWidget(
            command_frame
        )

        hint = QLabel(
            'Press Enter to send  •  Say "Hi Nova" for voice activation'
        )

        hint.setObjectName(
            "commandHint"
        )

        center_layout.addWidget(
            hint
        )

        columns.addWidget(
            center,
            1,
        )

        # ====================================================
        # RIGHT
        # ====================================================

        right = QFrame()

        right.setObjectName(
            "panel"
        )

        right.setMinimumWidth(
            300
        )

        right.setMaximumWidth(
            380
        )

        right_layout = QVBoxLayout(
            right
        )

        right_layout.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        activity_title = QLabel(
            "ACTIVITY MONITOR"
        )

        activity_title.setObjectName(
            "sectionTitle"
        )

        right_layout.addWidget(
            activity_title
        )

        tabs = QHBoxLayout()

        for text in (
            "ALL",
            "CHAT",
            "SYSTEM",
            "TOOLS",
        ):

            button = QPushButton(
                text
            )

            button.setObjectName(
                "activityTab"
            )

            tabs.addWidget(
                button
            )

        right_layout.addLayout(
            tabs
        )

        self.chat_scroll = QScrollArea()

        self.chat_scroll.setWidgetResizable(
            True
        )

        self.chat_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarAlwaysOff
        )

        self.chat_scroll.setObjectName(
            "chatScroll"
        )

        self.chat_container = QWidget()

        self.chat_layout = QVBoxLayout(
            self.chat_container
        )

        self.chat_layout.setContentsMargins(
            2,
            4,
            2,
            4,
        )

        self.chat_layout.setSpacing(
            7
        )

        self.chat_layout.addStretch()

        self.chat_scroll.setWidget(
            self.chat_container
        )

        right_layout.addWidget(
            self.chat_scroll,
            1,
        )

        connection = QLabel(
            f"● CONNECTED\n"
            f"MODEL  {MODEL}"
        )

        connection.setObjectName(
            "connection"
        )

        right_layout.addWidget(
            connection
        )

        columns.addWidget(
            right,
            0,
        )

        # ====================================================
        # CONNECT ACTIONS
        # ====================================================

        self.voice_action.clicked.connect(
            self.toggle_voice
        )

        self.apply_styles()

    # ========================================================
    # STYLES
    # ========================================================

    def apply_styles(self):

        self.setStyleSheet(
            f"""

            QMainWindow {{
                background: {BG};
            }}

            QWidget#central {{
                background: {BG};
            }}

            QFrame#topBar {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 7px;
            }}

            QFrame#panel {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 7px;
            }}

            QLabel#logo {{
                color: {TEXT};
                font-family: "Segoe UI";
                font-size: 26px;
                font-weight: 800;
                letter-spacing: 5px;
            }}

            QLabel#identityTitle {{
                color: {CYAN};
                font-family: Consolas;
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 2px;
            }}

            QLabel#identitySubtitle {{
                color: {MUTED};
                font-family: Consolas;
                font-size: 7px;
            }}

            QPushButton#navButton {{
                background: transparent;
                color: {MUTED};
                border: none;
                padding: 11px 10px;
                font-family: Consolas;
                font-size: 8px;
                font-weight: bold;
            }}

            QPushButton#navButton:hover {{
                color: {CYAN};
            }}

            QLabel#activeIndicator {{
                background: #061F1B;
                color: {GREEN};
                border: 1px solid #155947;
                border-radius: 5px;
                padding: 6px 10px;
                font-family: Consolas;
                font-size: 7px;
                font-weight: bold;
            }}

            QLabel#headerClock {{
                color: {TEXT};
                font-family: Consolas;
                font-size: 12px;
                font-weight: bold;
                padding: 7px;
            }}

            QLabel#sectionTitle {{
                color: {CYAN};
                font-family: Consolas;
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 2px;
                padding: 3px;
            }}

            QFrame#serviceCard {{
                background: {PANEL_2};
                border: 1px solid #102C37;
                border-radius: 5px;
            }}

            QLabel#serviceName {{
                color: {TEXT};
                font-family: Consolas;
                font-size: 9px;
                font-weight: bold;
            }}

            QLabel#serviceDetail {{
                color: {MUTED};
                font-family: Consolas;
                font-size: 7px;
            }}

            QFrame#telemetryCard {{
                background: {PANEL_2};
                border: 1px solid #102C37;
                border-radius: 5px;
            }}

            QLabel#telemetryTitle {{
                color: {TEXT};
                font-family: Consolas;
                font-size: 8px;
                font-weight: bold;
            }}

            QLabel#telemetryValue {{
                color: {GREEN};
                font-family: Consolas;
                font-size: 9px;
                font-weight: bold;
            }}

            QLabel#systemInfo {{
                color: {MUTED};
                background: {PANEL_2};
                border: 1px solid #102C37;
                border-radius: 5px;
                padding: 8px;
                font-family: Consolas;
                font-size: 7px;
            }}

            QLabel#coreStatus {{
                color: {GREEN};
                font-family: Consolas;
                font-size: 8px;
                font-weight: bold;
                letter-spacing: 2px;
            }}

            QLabel#coreCaption {{
                color: {CYAN};
                font-family: Consolas;
                font-size: 17px;
                font-weight: bold;
                letter-spacing: 7px;
                qproperty-alignment: AlignCenter;
            }}

            QLabel#coreSubtitle {{
                color: {MUTED};
                font-family: Consolas;
                font-size: 7px;
                letter-spacing: 2px;
                qproperty-alignment: AlignCenter;
            }}

            QPushButton#quickAction {{
                background: {PANEL_2};
                color: {CYAN};
                border: 1px solid {BORDER};
                border-radius: 5px;
                padding: 8px;
                min-height: 36px;
                font-family: Consolas;
                font-size: 7px;
                font-weight: bold;
            }}

            QPushButton#quickAction:hover {{
                background: #0C2530;
                border-color: {CYAN};
                color: {TEXT};
            }}

            QFrame#commandFrame {{
                background: #041016;
                border: 1px solid {CYAN};
                border-radius: 6px;
            }}

            QLineEdit#commandInput {{
                background: transparent;
                border: none;
                color: {TEXT};
                padding: 8px;
                font-family: "Segoe UI";
                font-size: 10px;
            }}

            QPushButton#sendButton {{
                background: {CYAN};
                color: #021014;
                border: none;
                border-radius: 5px;
                min-width: 40px;
                min-height: 32px;
                font-size: 17px;
            }}

            QPushButton#sendButton:hover {{
                background: #7CEBFA;
            }}

            QLabel#commandHint {{
                color: {MUTED};
                font-family: Consolas;
                font-size: 7px;
            }}

            QPushButton#activityTab {{
                background: #07161D;
                color: {MUTED};
                border: 1px solid #102C37;
                border-radius: 4px;
                padding: 5px;
                font-family: Consolas;
                font-size: 7px;
                font-weight: bold;
            }}

            QPushButton#activityTab:hover {{
                color: {CYAN};
                border-color: {CYAN};
            }}

            QScrollArea#chatScroll {{
                background: transparent;
                border: none;
            }}

            QFrame#novaBubble {{
                background: #071A22;
                border: 1px solid #15424F;
                border-radius: 6px;
            }}

            QFrame#userBubble {{
                background: #08221C;
                border: 1px solid #1C5748;
                border-radius: 6px;
            }}

            QLabel#bubbleName {{
                color: {GREEN};
                font-family: Consolas;
                font-size: 7px;
                font-weight: bold;
                letter-spacing: 1px;
            }}

            QLabel#bubbleTime {{
                color: {MUTED};
                font-family: Consolas;
                font-size: 7px;
            }}

            QLabel#bubbleText {{
                color: {TEXT};
                font-family: "Segoe UI";
                font-size: 9px;
            }}

            QLabel#connection {{
                color: {GREEN};
                background: #061A15;
                border: 1px solid #154738;
                border-radius: 5px;
                padding: 7px;
                font-family: Consolas;
                font-size: 7px;
                font-weight: bold;
            }}

            QScrollBar:vertical {{
                background: #03090D;
                width: 5px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background: #19404B;
                border-radius: 2px;
                min-height: 30px;
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            """
        )

    # ========================================================
    # TIMERS
    # ========================================================

    def setup_timers(self):

        self.stats_timer = QTimer(
            self
        )

        self.stats_timer.timeout.connect(
            self.update_stats
        )

        self.stats_timer.start(
            1200
        )

        self.clock_timer = QTimer(
            self
        )

        self.clock_timer.timeout.connect(
            self.update_clock
        )

        self.clock_timer.start(
            1000
        )

        self.gpu_timer = QTimer(
            self
        )

        self.gpu_timer.timeout.connect(
            self.update_gpu
        )

        self.gpu_timer.start(
            3000
        )

        self.service_timer = QTimer(
            self
        )

        self.service_timer.timeout.connect(
            self.check_services
        )

        self.service_timer.start(
            10000
        )

        self.update_stats()
        self.update_clock()
        self.update_gpu()
        self.check_services()

    # ========================================================
    # STATS
    # ========================================================

    def update_stats(self):

        cpu = psutil.cpu_percent(
            interval=None
        )

        ram = psutil.virtual_memory().percent

        disk = psutil.disk_usage(
            "/"
        ).percent

        self.cpu_card.update_value(
            cpu
        )

        self.ram_card.update_value(
            ram
        )

        self.disk_card.update_value(
            disk
        )

        gpu = gpu_info()

        gpu_usage = (
            gpu[0]
            if gpu
            else 0
        )

        self.gpu_card.update_value(
            gpu_usage
        )

        net = psutil.net_io_counters()

        now = time.time()

        elapsed = max(
            0.1,
            now - self.net_time,
        )

        rx = (
            net.bytes_recv
            - self.rx_previous
        ) / elapsed

        tx = (
            net.bytes_sent
            - self.tx_previous
        ) / elapsed

        self.rx_previous = (
            net.bytes_recv
        )

        self.tx_previous = (
            net.bytes_sent
        )

        self.net_time = now

        memory = psutil.virtual_memory()

        storage = psutil.disk_usage(
            "/"
        )

        gpu_text = (
            "N/A"
            if gpu is None
            else f"{gpu[0]:.0f}%"
        )

        self.system_info.setText(
            f"UPTIME       {uptime_text()}\n"
            f"PLATFORM     {platform.system()} {platform.release()}\n"
            f"CPU          {psutil.cpu_count()} CORE\n"
            f"MEMORY       {memory.total / 1024**3:.1f} GB\n"
            f"STORAGE      {storage.total / 1024**3:.0f} GB\n"
            f"GPU          {gpu_text}\n"
            f"NETWORK      ↓ {speed_text(rx)}  ↑ {speed_text(tx)}"
        )

    def update_gpu(self):

        gpu = gpu_info()

        if gpu is None:

            self.services[
                "GPU"
            ].set_status(
                False,
                "UNAVAILABLE",
                AMBER,
            )

            return

        usage, used, total = gpu

        self.services[
            "GPU"
        ].set_status(
            True,
            f"{usage:.0f}% • {used:.0f}/{total:.0f} MB",
        )

    # ========================================================
    # CLOCK
    # ========================================================

    def update_clock(self):

        self.clock.setText(
            time.strftime(
                "%H:%M:%S"
            )
        )

    # ========================================================
    # SERVICES
    # ========================================================

    def check_services(self):

        if (
            self.service_worker
            and self.service_worker.isRunning()
        ):

            return

        self.service_worker = (
            ServiceWorker()
        )

        self.service_worker.result.connect(
            self.service_result
        )

        self.service_worker.start()

    def service_result(
        self,
        name,
        online,
        detail,
    ):

        if name not in self.services:
            return

        self.services[
            name
        ].set_status(
            online,
            detail,
        )

    # ========================================================
    # NOVA STATE
    # ========================================================

    def set_status(
        self,
        status,
    ):

        mapping = {

            "Ready": (
                "idle",
                "IDLE",
                "READY FOR COMMAND",
            ),

            "Waiting for activation...": (
                "idle",
                "VOICE STANDBY",
                "WAITING FOR ACTIVATION",
            ),

            "Nova active": (
                "active",
                "NOVA ACTIVE",
                "READY FOR COMMAND",
            ),

            "Listening...": (
                "listening",
                "LISTENING",
                "CAPTURING VOICE",
            ),

            "Thinking...": (
                "thinking",
                "THINKING",
                "OLLAMA PROCESSING",
            ),

            "Searching the web...": (
                "thinking",
                "SEARCHING",
                "WEB SEARCH",
            ),

            "Speaking...": (
                "speaking",
                "SPEAKING",
                "PIPER OUTPUT",
            ),

            "Stopping...": (
                "stopping",
                "STOPPING",
                "VOICE SYSTEM STOPPING",
            ),
        }

        state, core_text, header_text = mapping.get(
            status,
            (
                "idle",
                "IDLE",
                "READY FOR COMMAND",
            ),
        )

        # REAL 3D CORE STATE
        self.core.set_state(
            state
        )

        self.core_status.setText(
            core_text
        )

        if state == "idle":

            self.core_caption.setText(
                "N O V A"
            )

        else:

            self.core_caption.setText(
                "N O V A   A C T I V E"
            )

        self.active_indicator.setText(
            f"● {core_text}\n"
            f"  {header_text}"
        )

        # Voice service state

        if status == "Waiting for activation...":

            self.services[
                "WHISPER"
            ].set_status(
                True,
                "STANDBY",
            )

            self.services[
                "PIPER"
            ].set_status(
                True,
                "READY",
            )

        elif status == "Nova active":

            self.services[
                "WHISPER"
            ].set_status(
                True,
                "ACTIVE",
            )

        elif status == "Listening...":

            self.services[
                "WHISPER"
            ].set_status(
                True,
                "LISTENING",
            )

        elif status == "Thinking...":

            self.services[
                "OLLAMA"
            ].set_status(
                True,
                "PROCESSING",
            )

        elif status == "Speaking...":

            self.services[
                "PIPER"
            ].set_status(
                True,
                "SPEAKING",
            )

    # ========================================================
    # CHAT
    # ========================================================

    def append_user(
        self,
        message,
    ):

        bubble = ChatBubble(
            "YOU",
            message,
            True,
        )

        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1,
            bubble,
        )

        self.scroll_chat()

    def append_nova(
        self,
        message,
    ):

        bubble = ChatBubble(
            "NOVA",
            message,
            False,
        )

        self.chat_layout.insertWidget(
            self.chat_layout.count() - 1,
            bubble,
        )

        self.scroll_chat()

    def scroll_chat(self):

        QTimer.singleShot(
            50,
            lambda:
                self.chat_scroll.verticalScrollBar().setValue(
                    self.chat_scroll.verticalScrollBar().maximum()
                ),
        )

    # ========================================================
    # TEXT
    # ========================================================

    def send_text(self):

        message = (
            self.command_input.text()
            .strip()
        )

        if not message:
            return

        if (
            self.brain_worker
            and self.brain_worker.isRunning()
        ):

            return

        self.command_input.clear()

        self.append_user(
            message
        )

        self.set_status(
            "Thinking..."
        )

        self.brain_worker = BrainWorker(
            message
        )

        self.brain_worker.finished.connect(
            self.brain_finished
        )

        self.brain_worker.failed.connect(
            self.brain_failed
        )

        self.brain_worker.start()

    def brain_finished(
        self,
        response,
    ):

        self.append_nova(
            response
        )

        self.set_status(
            "Ready"
        )

    def brain_failed(
        self,
        error,
    ):

        self.append_nova(
            error
        )

        self.set_status(
            "Ready"
        )

    # ========================================================
    # VOICE
    # ========================================================

    def toggle_voice(self):

        if (
            self.voice_worker
            and self.voice_worker.isRunning()
        ):

            self.stop_voice()

        else:

            self.start_voice()

    def start_voice(self):

        if (
            self.voice_worker
            and self.voice_worker.isRunning()
        ):

            return

        self.voice_worker = (
            VoiceWorker()
        )

        self.voice_worker.status.connect(
            self.set_status
        )

        self.voice_worker.user_message.connect(
            self.append_user
        )

        self.voice_worker.nova_message.connect(
            self.append_nova
        )

        self.voice_worker.error.connect(
            self.voice_error
        )

        self.voice_worker.stopped.connect(
            self.voice_stopped
        )

        self.voice_worker.start()

        self.set_status(
            "Waiting for activation..."
        )

        self.voice_action.setText(
            "◉  VOICE\nACTIVE • F2"
        )

    def stop_voice(self):

        if not self.voice_worker:
            return

        self.set_status(
            "Stopping..."
        )

        self.voice_worker.stop()

        self.voice_action.setText(
            "◉  VOICE\nSTOPPING..."
        )

    def voice_error(
        self,
        error,
    ):

        self.append_nova(
            f"Voice error: {error}"
        )

    def voice_stopped(self):

        self.voice_worker = None

        self.voice_action.setText(
            "◉  VOICE\nACTIVATE • F2"
        )

        self.set_status(
            "Ready"
        )

    # ========================================================
    # CLOSE
    # ========================================================

    def closeEvent(
        self,
        event,
    ):

        if (
            self.voice_worker
            and self.voice_worker.isRunning()
        ):

            self.voice_worker.stop()

            self.voice_worker.wait(
                3000
            )

        event.accept()


# ============================================================
# MAIN
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    app.setApplicationName(
        "Nova"
    )

    app.setStyle(
        "Fusion"
    )

    window = NovaWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()