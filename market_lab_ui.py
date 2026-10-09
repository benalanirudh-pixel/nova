from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from market_lab.market_lab_data import (
    CACHE_DIR,
    get_market_lab_data,
    save_json_report,
)
from market_lab.market_lab_brain import analyze_market_lab


# ============================================================
# NOVA MARKET LAB
# ============================================================

APP_NAME = "NOVA MARKET LAB"

BG = "#05090D"
SIDEBAR = "#080F15"
PANEL = "#0B151D"
PANEL_ALT = "#10212B"
BORDER = "#1A3542"

TEXT = "#E8F3F7"
MUTED = "#8198A3"

GREEN = "#39F0B2"
CYAN = "#35DFFF"
PURPLE = "#B49AFF"
AMBER = "#FFC857"
RED = "#FF647C"

FONT = "Segoe UI"


# ============================================================
# HELPERS
# ============================================================

def pretty_json(data: Any) -> str:
    try:
        return json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
            default=str,
        )
    except (TypeError, ValueError):
        return str(data)


def load_latest_saved_report():
    report_dir = Path(CACHE_DIR) / "market_lab"

    if not report_dir.is_dir():
        return None

    try:
        files = sorted(
            report_dir.glob("market_lab_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return None

    for path in files:
        try:
            with path.open("r", encoding="utf-8") as f:
                report = json.load(f)

            if isinstance(report, dict) and report:
                modified = path.stat().st_mtime
                return {
                    "report": report,
                    "saved_at": datetime.fromtimestamp(
                        modified
                    ).isoformat(timespec="seconds"),
                    "age_seconds": max(0, time.time() - modified),
                }
        except (OSError, ValueError, json.JSONDecodeError):
            continue

    return None


def find_value(data, candidates, depth=0):
    if depth > 7:
        return None

    if isinstance(data, dict):
        for key, value in data.items():
            normalized = (
                str(key).lower().strip()
                .replace("-", "_").replace(" ", "_")
            )

            if normalized in candidates and not isinstance(
                value, (dict, list)
            ):
                if value is not None:
                    return value

        for value in data.values():
            result = find_value(value, candidates, depth + 1)
            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data[:40]:
            result = find_value(item, candidates, depth + 1)
            if result is not None:
                return result

    return None


def find_section(data, candidates, depth=0):
    if depth > 7:
        return None

    if isinstance(data, dict):
        for key, value in data.items():
            normalized = str(key).lower().strip().replace("-", "_")
            if normalized in candidates and isinstance(
                value, (dict, list)
            ):
                return value

        for value in data.values():
            result = find_section(value, candidates, depth + 1)
            if result is not None:
                return result

    elif isinstance(data, list):
        for item in data[:30]:
            result = find_section(item, candidates, depth + 1)
            if result is not None:
                return result

    return None


def display_age(seconds):
    if seconds < 60:
        return f"{int(seconds)} seconds old"
    if seconds < 3600:
        return f"{int(seconds // 60)} minutes old"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} hours old"
    return f"{seconds / 86400:.1f} days old"


# Auto-refresh cadence: fast clock, slow data. The live-only report costs
# ~8 s of network-bound fetching, so polling it every second would stack
# workers, saturate the connection, and invite NSE throttling. The 1 s
# timer only repaints cheap local state (clock, ages, countdowns).
AUTO_CLOCK_MS = 1000
AUTO_POLL_OPEN_S = 60
AUTO_POLL_CLOSED_S = 300


def nse_market_open_now(now=None):
    """Return True when NSE equity is normally open (Mon-Fri 09:15-15:30 IST).

    Holidays are not modelled here; a holiday simply yields an empty
    live update, which the worker already surfaces honestly.
    """
    from datetime import timezone as _tz, timedelta as _td

    ist = _tz(_td(hours=5, minutes=30))
    now = now if now is not None else datetime.now(ist)
    if now.tzinfo is None:
        now = now.replace(tzinfo=ist)
    else:
        now = now.astimezone(ist)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 15 <= minutes < 15 * 60 + 30


def make_label(text="", size=10, color=TEXT, bold=False):
    label = QLabel(str(text))
    label.setWordWrap(True)
    label.setFont(
        QFont(
            FONT,
            size,
            QFont.Weight.Bold if bold else QFont.Weight.Normal,
        )
    )
    label.setStyleSheet(
        f"color:{color}; background:transparent; border:none;"
    )
    return label


def make_button(text, primary=False):
    button = QPushButton(text)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    button.setMinimumHeight(39)
    button.setStyleSheet(f"""
        QPushButton {{
            background:{GREEN if primary else PANEL_ALT};
            color:{BG if primary else TEXT};
            border:1px solid {GREEN if primary else BORDER};
            border-radius:8px;
            padding:8px 13px;
            font-weight:600;
        }}
        QPushButton:hover {{ border-color:{CYAN}; }}
        QPushButton:disabled {{
            background:{PANEL};
            color:{MUTED};
            border-color:{BORDER};
        }}
    """)
    return button


def make_panel(title, subtitle=None):
    frame = QFrame()
    frame.setObjectName("panel")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(15, 13, 15, 13)
    layout.setSpacing(9)
    layout.addWidget(make_label(title.upper(), 9, CYAN, True))

    if subtitle:
        layout.addWidget(make_label(subtitle, 9, MUTED))

    return frame, layout


# ============================================================
# BACKGROUND WORKER
# ============================================================

class Worker(QThread):
    succeeded = Signal(str, object, float)
    failed = Signal(str, str, float)

    def __init__(self, task_name, function, *args, **kwargs):
        super().__init__()
        self.task_name = task_name
        self.function = function
        self.args = args
        self.kwargs = kwargs

    def run(self):
        started = time.perf_counter()

        try:
            result = self.function(*self.args, **self.kwargs)

            if (
                self.task_name == "report"
                and isinstance(result, dict)
                and result
            ):
                # Persist in the worker thread so the next launch can
                # show a saved report without blocking the UI.
                try:
                    save_json_report(result)
                except Exception:
                    print(
                        "WARNING: failed to save Market Lab JSON report:"
                    )
                    traceback.print_exc()

            self.succeeded.emit(
                self.task_name,
                result,
                time.perf_counter() - started,
            )
        except Exception:
            self.failed.emit(
                self.task_name,
                traceback.format_exc(),
                time.perf_counter() - started,
            )


# ============================================================
# MAIN WINDOW
# ============================================================

class MarketLabWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.report = None
        self.workers = {}
        self.cache_is_displayed = False
        self.auto_enabled = False
        self.last_update_at = None
        self.next_poll_at = None
        self.auto_timer = None

        self.setWindowTitle(APP_NAME)
        self.resize(1500, 920)
        self.setMinimumSize(1050, 680)

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background:{BG};
                color:{TEXT};
                font-family:'{FONT}';
            }}
            QLabel {{ background:transparent; border:none; }}
            QFrame#panel {{
                background:{PANEL};
                border:1px solid {BORDER};
                border-radius:11px;
            }}
            QFrame#sidebar {{
                background:{SIDEBAR};
                border:1px solid {BORDER};
                border-radius:12px;
            }}
            QPlainTextEdit, QLineEdit {{
                background:#070D12;
                color:{TEXT};
                border:1px solid {BORDER};
                border-radius:8px;
                padding:10px;
                selection-background-color:#174B58;
            }}
            QPlainTextEdit {{
                font-family:Consolas;
                font-size:10pt;
            }}
            QScrollBar:vertical {{
                background:{BG};
                width:8px;
                margin:0;
            }}
            QScrollBar::handle:vertical {{
                background:{BORDER};
                border-radius:4px;
                min-height:28px;
            }}
        """)

        self.build_ui()
        QTimer.singleShot(150, self.load_initial_report)

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(18, 14, 18, 14)
        outer.setSpacing(12)

        header = QHBoxLayout()

        brand = QVBoxLayout()
        brand.addWidget(make_label("NOVA", 22, GREEN, True))
        brand.addWidget(
            make_label("MARKET INTELLIGENCE TERMINAL", 9, MUTED, True)
        )
        header.addLayout(brand)
        header.addStretch()

        self.connection_label = make_label("INITIALIZING", 9, AMBER, True)
        header.addWidget(self.connection_label)

        self.refresh_btn = make_button("↻  FULL REFRESH", True)
        self.refresh_btn.clicked.connect(self.refresh_report)
        header.addWidget(self.refresh_btn)

        self.live_btn = make_button("⚡ LIVE UPDATE", False)
        self.live_btn.clicked.connect(self.live_update_report)
        header.addWidget(self.live_btn)

        self.auto_btn = make_button("AUTO: OFF", False)
        self.auto_btn.setCheckable(True)
        self.auto_btn.clicked.connect(self.toggle_auto_refresh)
        header.addWidget(self.auto_btn)

        self.clock_label = make_label("--:--:--", 9, MUTED, True)
        header.addWidget(self.clock_label)

        outer.addLayout(header)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(3)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setStyleSheet(f"""
            QProgressBar {{ background:{PANEL_ALT}; border:none; }}
            QProgressBar::chunk {{ background:{GREEN}; }}
        """)
        outer.addWidget(self.progress)

        status_row = QHBoxLayout()
        self.status_data = self.add_status(
            status_row, "DATA PIPELINE", "STARTING", AMBER
        )
        self.status_event = self.add_status(
            status_row, "EVENT RISK", "UNKNOWN", AMBER
        )
        self.status_flow = self.add_status(
            status_row, "INSTITUTIONAL FLOW", "UNVERIFIED", AMBER
        )
        self.status_execution = self.add_status(
            status_row, "EXECUTION", "DISABLED", GREEN
        )
        outer.addLayout(status_row)

        workspace = QHBoxLayout()
        workspace.setSpacing(13)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)

        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 16, 12, 16)
        side.addWidget(make_label("WORKSPACE", 9, MUTED, True))

        self.pages = QStackedWidget()
        self.nav_buttons = []

        specs = [
            ("Overview", self.build_overview),
            ("Market Report", self.build_report_page),
            ("Nova Analysis", self.build_analysis_page),
        ]

        for index, (title, builder) in enumerate(specs):
            nav = make_button(f"{index + 1:02d}   {title}", index == 0)
            nav.clicked.connect(
                lambda checked=False, i=index: self.switch_page(i)
            )
            side.addWidget(nav)
            self.nav_buttons.append(nav)
            self.pages.addWidget(builder())

        side.addStretch()
        side.addWidget(make_label("SYSTEM MODE", 9, MUTED, True))
        side.addWidget(make_label("READ-ONLY", 12, GREEN, True))
        side.addWidget(make_label(
            "No broker connection\n"
            "No order placement\n"
            "No automatic execution",
            9, MUTED,
        ))

        workspace.addWidget(sidebar)
        workspace.addWidget(self.pages, 1)
        outer.addLayout(workspace, 1)

        self.footer = make_label("Initializing terminal…", 9, MUTED)
        outer.addWidget(self.footer)

    def add_status(self, row, title, value, color):
        frame, layout = make_panel(title)
        label = make_label(value, 12, color, True)
        layout.addWidget(label)
        row.addWidget(frame, 1)
        return label

    def add_metric(self, row, title, value):
        frame, layout = make_panel(title)
        label = make_label(value, 13, TEXT, True)
        label.setMinimumHeight(38)
        layout.addWidget(label)
        layout.addWidget(make_label("Backend-reported value", 8, MUTED))
        row.addWidget(frame, 1)
        return label

    # --------------------------------------------------------
    # PAGES
    # --------------------------------------------------------

    def build_overview(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        intro, intro_layout = make_panel(
            "Market overview",
            "Powered by your existing Market Lab data and analysis engines.",
        )
        intro_layout.addWidget(make_label(
            "Review market conditions, source quality and analysis "
            "availability in one workspace.",
            10, MUTED,
        ))
        layout.addWidget(intro)

        metrics = QHBoxLayout()
        self.metric_market = self.add_metric(metrics, "MARKET", "Waiting…")
        self.metric_time = self.add_metric(metrics, "REPORT TIME", "Waiting…")
        self.metric_event = self.add_metric(metrics, "EVENT RISK", "UNKNOWN")
        self.metric_flow = self.add_metric(
            metrics, "FLOW ELIGIBILITY", "Unverified"
        )
        layout.addLayout(metrics)

        integrity, integrity_layout = make_panel(
            "Data integrity",
            "Cached reports are labelled. Missing evidence is not treated as zero.",
        )
        self.integrity_view = QPlainTextEdit()
        self.integrity_view.setReadOnly(True)
        self.integrity_view.setPlainText(
            "Nova Market Lab is starting.\n\n"
            "The interface remains responsive while the report loads."
        )
        integrity_layout.addWidget(self.integrity_view, 1)
        layout.addWidget(integrity, 1)

        return page

    def build_report_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        frame, frame_layout = make_panel(
            "Market Lab report",
            "Raw report returned by get_market_lab_data().",
        )
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Waiting for market report…")
        frame_layout.addWidget(self.report_view, 1)
        layout.addWidget(frame)

        return page

    def build_analysis_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        controls, controls_layout = make_panel(
            "Nova AI analysis",
            "Uses your existing market_lab_brain.py and Ollama model.",
        )

        self.question = QLineEdit()
        self.question.setMinimumHeight(40)
        self.question.setPlaceholderText(
            "Ask about NIFTY, BANK NIFTY, breadth, flows or risk…"
        )
        controls_layout.addWidget(self.question)

        actions = QHBoxLayout()
        self.analyze_btn = make_button("RUN ANALYSIS", True)
        self.analyze_btn.clicked.connect(self.run_analysis)
        actions.addWidget(self.analyze_btn)

        clear_btn = make_button("CLEAR")
        clear_btn.clicked.connect(self.question.clear)
        actions.addWidget(clear_btn)
        actions.addStretch()
        controls_layout.addLayout(actions)
        layout.addWidget(controls)

        output, output_layout = make_panel(
            "Analysis output",
            "AI interpretation, not a validated prediction or instruction to trade.",
        )
        self.analysis_view = QPlainTextEdit()
        self.analysis_view.setReadOnly(True)
        self.analysis_view.setPlaceholderText(
            "Run analysis to see Nova's interpretation."
        )
        output_layout.addWidget(self.analysis_view, 1)
        layout.addWidget(output, 1)

        return page

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)

        for i, button in enumerate(self.nav_buttons):
            active = i == index
            button.setStyleSheet(f"""
                QPushButton {{
                    background:{GREEN if active else PANEL_ALT};
                    color:{BG if active else TEXT};
                    border:1px solid {GREEN if active else BORDER};
                    border-radius:8px;
                    padding:9px 12px;
                    text-align:left;
                    font-weight:600;
                }}
            """)

    # --------------------------------------------------------
    # STARTUP
    # --------------------------------------------------------

    def load_initial_report(self):
        cached = load_latest_saved_report()

        if cached:
            self.cache_is_displayed = True
            self.display_report(
                cached["report"],
                0,
                cached=True,
                saved_at=cached["saved_at"],
                age_seconds=cached["age_seconds"],
            )
            self.connection_label.setText("SAVED REPORT")
            self.connection_label.setStyleSheet(f"color:{AMBER};")
            self.footer.setText(
                f"Showing saved report ({display_age(cached['age_seconds'])}). "
                "Updating data in background…"
            )

            # Reuse backend caches where possible.
            self.start_task(
                "report",
                get_market_lab_data,
                force_refresh=False,
            )
        else:
            self.cache_is_displayed = False
            self.status_data.setText("INITIALIZING")
            self.connection_label.setText("LOADING DATA")
            self.connection_label.setStyleSheet(f"color:{AMBER};")
            self.footer.setText(
                "No saved report found. Building the first report in "
                "the background. Initial scanning may take time."
            )

            # First report: do not force a full refresh.
            self.start_task(
                "report",
                get_market_lab_data,
                force_refresh=False,
            )

    # --------------------------------------------------------
    # BACKGROUND TASKS
    # --------------------------------------------------------

    def start_task(self, name, function, *args, **kwargs):
        if name in self.workers:
            self.footer.setText(f"{name.title()} is already running.")
            return

        worker = Worker(name, function, *args, **kwargs)
        self.workers[name] = worker

        worker.succeeded.connect(self.task_succeeded)
        worker.failed.connect(self.task_failed)
        worker.finished.connect(
            lambda task_name=name, task_worker=worker:
            self.task_finished(task_name, task_worker)
        )

        if name == "report":
            self.refresh_btn.setEnabled(False)
            self.live_btn.setEnabled(False)
            self.progress.setRange(0, 0)
            self.status_data.setText(
                "CACHED • UPDATING" if self.cache_is_displayed else "LOADING…"
            )
            self.status_data.setStyleSheet(f"color:{AMBER};")
            self.footer.setText(
                "Market data task running in the background…"
            )

        elif name == "analysis":
            self.analyze_btn.setEnabled(False)
            self.footer.setText("Nova AI is analyzing the market report…")

        worker.start()

    def task_finished(self, name, worker):
        self.workers.pop(name, None)

        if name == "report":
            self.refresh_btn.setEnabled(True)
            self.live_btn.setEnabled(True)
            self.progress.setRange(0, 100)

        elif name == "analysis":
            self.analyze_btn.setEnabled(True)

        worker.deleteLater()

    def task_succeeded(self, name, result, elapsed):
        if name == "report":
            if not isinstance(result, dict) or not result:
                self.task_failed(
                    "report",
                    "The data engine returned an empty or invalid report.",
                    elapsed,
                )
                return

            self.cache_is_displayed = False
            self.display_report(result, elapsed, cached=False)
            self.last_update_at = time.time()
            self.schedule_next_poll()

        elif name == "analysis":
            self.analysis_view.setPlainText(
                result if isinstance(result, str) else pretty_json(result)
            )
            self.switch_page(2)
            self.footer.setText(
                f"AI analysis returned in {elapsed:.2f}s. "
                "Validate conclusions against the report evidence."
            )

    def task_failed(self, name, error, elapsed):
        if name == "report":
            # A failed poll must not kill auto mode; the next tick retries.
            self.schedule_next_poll()
        if name == "report" and self.cache_is_displayed:
            self.status_data.setText("CACHED • UPDATE FAILED")
            self.status_data.setStyleSheet(f"color:{AMBER};")
            self.footer.setText(
                "Update failed. The saved report remains visible. "
                "Check its timestamp before relying on it."
            )
        else:
            self.status_data.setText("ERROR" if name == "report" else "ANALYSIS ERROR")
            self.status_data.setStyleSheet(f"color:{RED};")
            self.footer.setText(
                f"{name.title()} failed after {elapsed:.1f}s. "
                "See the terminal output for details."
            )

        print(f"\n[{name.upper()} ERROR after {elapsed:.2f}s]\n{error}")

        QMessageBox.warning(
            self,
            f"Nova Market Lab — {name.title()}",
            f"The task failed after {elapsed:.1f} seconds.\n\n"
            "The detailed error has been printed to the terminal.",
        )

    # --------------------------------------------------------
    # DISPLAY REPORT
    # --------------------------------------------------------

    def display_report(
        self,
        report,
        elapsed,
        cached=False,
        saved_at=None,
        age_seconds=None,
    ):
        self.report = report
        self.report_view.setPlainText(pretty_json(report))

        market = find_value(report, ("market", "market_name"))
        generated = find_value(
            report,
            ("generated", "generated_at", "report_time", "timestamp"),
        )

        event_risk = find_value(
            report,
            ("overall_risk", "event_risk_level", "event_risk_status"),
        )

        flow_eligible = find_value(
            report,
            (
                "primary_source_verified_for_target_window",
                "signal_eligibility",
                "institutional_flow_eligible",
            ),
        )

        event_context = find_section(
            report,
            ("event_risk_context", "event_risk", "event_risk_engine"),
        )

        flow_context = find_section(
            report,
            ("institutional_flow", "institutional_flow_intelligence"),
        )

        if event_risk is None and event_context is not None:
            event_risk = find_value(
                event_context, ("overall_risk", "status", "risk_level")
            )

        if flow_eligible is None and flow_context is not None:
            flow_eligible = find_value(
                flow_context,
                (
                    "primary_source_verified_for_target_window",
                    "signal_eligibility",
                    "signal_allowed",
                    "eligible",
                ),
            )

        self.metric_market.setText(
            str(market) if market is not None else "Not reported"
        )
        self.metric_time.setText(
            str(generated) if generated is not None else "Not reported"
        )
        self.metric_event.setText(
            str(event_risk) if event_risk is not None else "UNKNOWN"
        )
        self.metric_flow.setText(
            str(flow_eligible) if flow_eligible is not None else "Not reported"
        )

        self.status_data.setText("CACHED REPORT" if cached else "REPORT LOADED")
        self.status_data.setStyleSheet(
            f"color:{AMBER if cached else GREEN};"
        )

        risk_text = str(event_risk).upper() if event_risk is not None else "UNKNOWN"
        self.status_event.setText(risk_text)
        self.status_event.setStyleSheet(
            f"color:{RED if risk_text in ('HIGH', 'CRITICAL') else AMBER};"
        )

        # Only an explicit True can qualify as eligible.
        if flow_eligible is True:
            flow_text, flow_color = "ELIGIBLE", GREEN
        elif flow_eligible is None:
            flow_text, flow_color = "NOT VERIFIED", AMBER
        else:
            flow_text, flow_color = "NOT ELIGIBLE", AMBER

        self.status_flow.setText(flow_text)
        self.status_flow.setStyleSheet(f"color:{flow_color};")

        self.status_execution.setText("DISABLED")
        self.status_execution.setStyleSheet(f"color:{GREEN};")

        availability = find_section(
            report,
            ("data_availability", "data_quality", "source_quality"),
        )
        warnings = find_value(
            report,
            ("warnings", "data_warnings", "quality_warnings"),
        )

        if cached:
            age = (
                display_age(age_seconds)
                if age_seconds is not None else "unknown age"
            )
            origin = (
                f"Saved report timestamp: {saved_at}\n"
                f"Saved report age: {age}\n"
                "STATUS: CACHED — may not reflect current market conditions."
            )
        else:
            origin = (
                f"Refresh completed: {datetime.now().isoformat(timespec='seconds')}\n"
                f"Duration: {elapsed:.2f} seconds\n"
                "Inspect source timestamps before relying on the report."
            )

        details = [
            origin,
            "",
            f"Market: {market if market is not None else 'Not reported'}",
            f"Report timestamp: {generated if generated is not None else 'Not reported'}",
            f"Event risk: {risk_text}",
            f"Institutional-flow eligibility: "
            f"{flow_eligible if flow_eligible is not None else 'Not reported'}",
            "",
            "DATA AVAILABILITY",
            pretty_json(availability) if availability is not None
            else "See the full report for data availability fields.",
            "",
            "WARNINGS",
            pretty_json(warnings) if warnings is not None
            else "No top-level warnings field found; inspect the full report.",
            "",
            "SAFETY",
            "- UNKNOWN event risk is not an all-clear.",
            "- Cached data may be stale.",
            "- Missing fields are not assumed to be zero.",
            "- Institutional-flow eligibility follows backend verification.",
            "- Trading execution remains disabled.",
        ]

        self.integrity_view.setPlainText("\n".join(details))
        self.progress.setValue(100)

        if cached:
            self.connection_label.setText("SAVED REPORT")
            self.connection_label.setStyleSheet(f"color:{AMBER};")
            self.footer.setText(
                f"Showing saved report ({display_age(age_seconds or 0)})."
            )
        else:
            self.connection_label.setText(
                f"UPDATED {datetime.now().strftime('%H:%M:%S')}"
            )
            self.connection_label.setStyleSheet(f"color:{GREEN};")
            self.footer.setText(
                f"Report returned in {elapsed:.2f}s. "
                "Review source quality and warnings."
            )

    # --------------------------------------------------------
    # MANUAL REFRESH AND AI
    # --------------------------------------------------------

    def refresh_report(self):
        # A forced full scan is only triggered by this button.
        self.start_task(
            "report",
            get_market_lab_data,
            force_refresh=True,
        )

    def live_update_report(self):
        # Refresh only cheap live layers over the cached equity scan.
        # Never runs the full NSE scan.
        self.start_task(
            "report",
            get_market_lab_data,
            live_only=True,
        )
        # A manual update resets the auto countdown.
        self.schedule_next_poll()

    # --------------------------------------------------------
    # STAGGERED AUTO-REFRESH
    # --------------------------------------------------------
    # Tier 1 (1 s): clock/age/countdown repaint only, no network.
    # Tier 2 (60 s open / 300 s closed): live-only worker poll.
    # Single-flight: a tick never starts a second worker; manual
    # actions reset the countdown via schedule_next_poll().

    def auto_interval_seconds(self):
        if nse_market_open_now():
            return AUTO_POLL_OPEN_S
        return AUTO_POLL_CLOSED_S

    def schedule_next_poll(self):
        if not self.auto_enabled:
            self.next_poll_at = None
            return
        self.next_poll_at = time.time() + self.auto_interval_seconds()

    def toggle_auto_refresh(self):
        self.auto_enabled = bool(self.auto_btn.isChecked())
        self.auto_btn.setText(
            "AUTO: ON" if self.auto_enabled else "AUTO: OFF"
        )
        if self.auto_enabled:
            self.ensure_auto_timer()
            # First poll fires after one interval, not immediately,
            # so enabling AUTO never surprises a running task.
            self.schedule_next_poll()
            self.tick_auto_clock()
        else:
            self.next_poll_at = None
            self.tick_auto_clock()

    def ensure_auto_timer(self):
        if self.auto_timer is None:
            self.auto_timer = QTimer(self)
            self.auto_timer.setInterval(AUTO_CLOCK_MS)
            self.auto_timer.timeout.connect(self.tick_auto_clock)
        if not self.auto_timer.isActive():
            self.auto_timer.start()

    def tick_auto_clock(self):
        from datetime import timezone as _tz, timedelta as _td

        ist = _tz(_td(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        session = (
            "NSE OPEN" if nse_market_open_now(now_ist) else "NSE CLOSED"
        )
        parts = [now_ist.strftime("%H:%M:%S"), session]

        if self.last_update_at is not None:
            age = max(0, time.time() - self.last_update_at)
            parts.append(f"data {display_age(age)}")

        if self.auto_enabled and self.next_poll_at is not None:
            remaining = int(self.next_poll_at - time.time())
            if remaining <= 0 and "report" not in self.workers:
                self.live_update_report()
                return
            if remaining > 0:
                parts.append(f"next update in {remaining}s")

        if hasattr(self, "clock_label"):
            self.clock_label.setText("  •  ".join(parts))

    def run_analysis(self):
        if not self.report:
            QMessageBox.information(
                self,
                APP_NAME,
                "Wait for a market report to load before running analysis.",
            )
            return

        query = self.question.text().strip()
        self.start_task(
            "analysis",
            analyze_market_lab,
            query,
            False,
        )

    # --------------------------------------------------------
    # SAFE WINDOW CLOSE
    # --------------------------------------------------------

    def closeEvent(self, event):
        running = [
            worker for worker in self.workers.values()
            if worker.isRunning()
        ]

        if running:
            QMessageBox.information(
                self,
                APP_NAME,
                "A background task is still running. Wait for it to finish "
                "before closing the terminal.",
            )
            event.ignore()
            return

        event.accept()


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setFont(QFont(FONT, 10))

    window = MarketLabWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())