

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

)

from market_lab.market_lab_brain import analyze_market_lab





# ============================================================

# NOVA MARKET LAB — CONFIG

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

# REPORT CACHE

# ============================================================



def load_latest_saved_report() -> dict[str, Any] | None:

    """

    Load the latest saved Market Lab JSON report.



    This only reads an existing report. It does not fetch market

    data or mark cached data as live.

    """

    report_dir = Path(CACHE_DIR) / "market_lab"



    if not report_dir.is_dir():

        return None



    try:

        files = sorted(

            report_dir.glob("market_lab_*.json"),

            key=lambda path: path.stat().st_mtime,

            reverse=True,

        )

    except OSError:

        return None



    for path in files:

        try:

            with path.open("r", encoding="utf-8") as file:

                report = json.load(file)



            if isinstance(report, dict) and report:

                modified = datetime.fromtimestamp(path.stat().st_mtime)



                return {

                    "report": report,

                    "path": str(path),

                    "saved_at": modified.isoformat(timespec="seconds"),

                    "age_seconds": max(

                        0.0,

                        time.time() - path.stat().st_mtime,

                    ),

                }



        except (OSError, json.JSONDecodeError, ValueError):

            continue



    return None





# ============================================================

# UI HELPERS

# ============================================================



def make_label(

    text: str = "",

    size: int = 10,

    color: str = TEXT,

    bold: bool = False,

) -> QLabel:

    widget = QLabel(str(text))

    widget.setWordWrap(True)

    widget.setFont(

        QFont(

            FONT,

            size,

            QFont.Weight.Bold if bold else QFont.Weight.Normal,

        )

    )

    widget.setStyleSheet(

        f"color: {color}; background: transparent; border: none;"

    )

    return widget





def make_button(text: str, primary: bool = False) -> QPushButton:

    widget = QPushButton(text)

    widget.setCursor(Qt.CursorShape.PointingHandCursor)

    widget.setMinimumHeight(39)

    widget.setStyleSheet(f"""

        QPushButton {{

            background: {GREEN if primary else PANEL_ALT};

            color: {BG if primary else TEXT};

            border: 1px solid {GREEN if primary else BORDER};

            border-radius: 8px;

            padding: 8px 13px;

            font-weight: 600;

        }}

        QPushButton:hover {{

            border-color: {CYAN};

        }}

        QPushButton:disabled {{

            background: {PANEL};

            color: {MUTED};

            border-color: {BORDER};

        }}

    """)

    return widget





def make_panel(title: str, subtitle: str | None = None):

    frame = QFrame()

    frame.setObjectName("panel")



    layout = QVBoxLayout(frame)

    layout.setContentsMargins(15, 13, 15, 13)

    layout.setSpacing(9)



    layout.addWidget(make_label(title.upper(), 9, CYAN, True))



    if subtitle:

        layout.addWidget(make_label(subtitle, 9, MUTED))



    return frame, layout





def pretty_json(data: Any) -> str:

    try:

        return json.dumps(

            data,

            indent=2,

            ensure_ascii=False,

            allow_nan=False,

            default=str,

        )

    except (TypeError, ValueError):

        return str(data)





def find_value(

    data: Any,

    candidates: tuple[str, ...],

    depth: int = 0,

):

    """Find a field without calculating or inventing a value."""

    if depth > 7:

        return None



    if isinstance(data, dict):

        for key, value in data.items():

            normalized = (

                str(key)

                .lower()

                .strip()

                .replace("-", "_")

                .replace(" ", "_")

            )



            if normalized in candidates and value is not None:

                if not isinstance(value, (dict, list)):

                    return value



        for value in data.values():

            found = find_value(value, candidates, depth + 1)

            if found is not None:

                return found



    elif isinstance(data, list):

        for item in data[:40]:

            found = find_value(item, candidates, depth + 1)

            if found is not None:

                return found



    return None





def find_section(

    data: Any,

    candidates: tuple[str, ...],

    depth: int = 0,

):

    if depth > 7:

        return None



    if isinstance(data, dict):

        for key, value in data.items():

            normalized = (

                str(key).lower().strip().replace("-", "_")

            )



            if normalized in candidates and isinstance(value, (dict, list)):

                return value



        for value in data.values():

            found = find_section(value, candidates, depth + 1)

            if found is not None:

                return found



    elif isinstance(data, list):

        for item in data[:30]:

            found = find_section(item, candidates, depth + 1)

            if found is not None:

                return found



    return None





def display_age(seconds: float) -> str:

    if seconds < 60:

        return f"{int(seconds)} seconds old"

    if seconds < 3600:

        return f"{int(seconds // 60)} minutes old"

    if seconds < 86400:

        return f"{seconds / 3600:.1f} hours old"

    return f"{seconds / 86400:.1f} days old"





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

            elapsed = time.perf_counter() - started

            self.succeeded.emit(self.task_name, result, elapsed)

        except Exception:

            elapsed = time.perf_counter() - started

            self.failed.emit(

                self.task_name,

                traceback.format_exc(),

                elapsed,

            )





# ============================================================

# MAIN WINDOW

# ============================================================



class MarketLabWindow(QMainWindow):

    def __init__(self):

        super().__init__()



        self.report: dict[str, Any] | None = None

        self.workers: dict[str, Worker] = {}

        self.cache_is_displayed = False

        self.last_report_time: datetime | None = None



        self.setWindowTitle(APP_NAME)

        self.resize(1500, 920)

        self.setMinimumSize(1050, 680)



        self.setStyleSheet(f"""

            QMainWindow, QWidget {{

                background: {BG};

                color: {TEXT};

                font-family: '{FONT}';

            }}

            QLabel {{

                background: transparent;

                border: none;

            }}

            QFrame#panel {{

                background: {PANEL};

                border: 1px solid {BORDER};

                border-radius: 11px;

            }}

            QFrame#sidebar {{

                background: {SIDEBAR};

                border: 1px solid {BORDER};

                border-radius: 12px;

            }}

            QPlainTextEdit, QLineEdit {{

                background: #070D12;

                color: {TEXT};

                border: 1px solid {BORDER};

                border-radius: 8px;

                padding: 10px;

                selection-background-color: #174B58;

            }}

            QPlainTextEdit {{

                font-family: Consolas;

                font-size: 10pt;

            }}

            QScrollBar:vertical {{

                background: {BG};

                width: 8px;

                margin: 0;

            }}

            QScrollBar::handle:vertical {{

                background: {BORDER};

                border-radius: 4px;

                min-height: 28px;

            }}

            QScrollBar::handle:vertical:hover {{

                background: {CYAN};

            }}

        """)



        self.build_ui()



        # Paint the window before doing report-cache or network work.

        QTimer.singleShot(100, self.load_initial_report)



    # --------------------------------------------------------

    # BUILD UI

    # --------------------------------------------------------



    def build_ui(self):

        root = QWidget()

        self.setCentralWidget(root)



        outer = QVBoxLayout(root)

        outer.setContentsMargins(18, 14, 18, 14)

        outer.setSpacing(12)



        # Header

        header = QHBoxLayout()

        header.setSpacing(12)



        brand = QVBoxLayout()

        brand.setSpacing(3)

        brand.addWidget(make_label("NOVA", 22, GREEN, True))

        brand.addWidget(

            make_label("MARKET INTELLIGENCE TERMINAL", 9, MUTED, True)

        )



        header.addLayout(brand)

        header.addStretch()



        self.connection_label = make_label("STARTING", 9, AMBER, True)

        header.addWidget(self.connection_label)



        self.refresh_btn = make_button("↻  FULL REFRESH", True)

        self.refresh_btn.clicked.connect(self.refresh_report)

        header.addWidget(self.refresh_btn)



        outer.addLayout(header)



        # Progress indicator

        self.progress = QProgressBar()

        self.progress.setTextVisible(False)

        self.progress.setFixedHeight(3)

        self.progress.setRange(0, 100)

        self.progress.setValue(0)

        self.progress.setStyleSheet(f"""

            QProgressBar {{

                background: {PANEL_ALT};

                border: none;

                border-radius: 1px;

            }}

            QProgressBar::chunk {{

                background: {GREEN};

                border-radius: 1px;

            }}

        """)

        outer.addWidget(self.progress)



        # Status cards

        status_row = QHBoxLayout()

        status_row.setSpacing(10)



        self.status_data = self.make_status_card(

            status_row, "DATA PIPELINE", "WAITING", AMBER

        )

        self.status_event = self.make_status_card(

            status_row, "EVENT RISK", "UNKNOWN", AMBER

        )

        self.status_flow = self.make_status_card(

            status_row, "INSTITUTIONAL FLOW", "UNVERIFIED", AMBER

        )

        self.status_execution = self.make_status_card(

            status_row, "EXECUTION", "DISABLED", GREEN

        )



        outer.addLayout(status_row)



        # Main workspace

        workspace = QHBoxLayout()

        workspace.setSpacing(13)



        sidebar = QFrame()

        sidebar.setObjectName("sidebar")

        sidebar.setFixedWidth(205)



        side = QVBoxLayout(sidebar)

        side.setContentsMargins(12, 16, 12, 16)

        side.setSpacing(9)



        side.addWidget(make_label("WORKSPACE", 9, MUTED, True))



        self.pages = QStackedWidget()

        self.nav_buttons = []



        page_specs = [

            ("Overview", self.build_overview),

            ("Market Report", self.build_report_page),

            ("Nova Analysis", self.build_analysis_page),

        ]



        for index, (title, builder) in enumerate(page_specs):

            nav = make_button(f"{index + 1:02d}   {title}", index == 0)

            nav.setMinimumHeight(43)

            nav.clicked.connect(

                lambda checked=False, i=index: self.switch_page(i)

            )

            side.addWidget(nav)

            self.nav_buttons.append(nav)

            self.pages.addWidget(builder())



        side.addStretch()

        side.addWidget(make_label("SYSTEM MODE", 9, MUTED, True))

        side.addWidget(make_label("READ-ONLY", 12, GREEN, True))

        side.addWidget(

            make_label(

                "No broker connection\n"

                "No order placement\n"

                "No automatic execution",

                9,

                MUTED,

            )

        )



        workspace.addWidget(sidebar)

        workspace.addWidget(self.pages, 1)

        outer.addLayout(workspace, 1)



        self.footer = make_label(

            "Opening terminal…", 9, MUTED

        )

        outer.addWidget(self.footer)



    def make_status_card(self, row, title, value, color):

        frame, layout = make_panel(title)

        value_label = make_label(value, 12, color, True)

        layout.addWidget(value_label)

        row.addWidget(frame, 1)

        return value_label



    # --------------------------------------------------------

    # OVERVIEW PAGE

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

        intro_layout.addWidget(

            make_label(

                "Review market conditions, source quality and analysis "

                "availability in one workspace.",

                10,

                MUTED,

            )

        )

        layout.addWidget(intro)



        metrics = QHBoxLayout()

        metrics.setSpacing(10)



        self.metric_market = self.make_metric(

            metrics, "MARKET", "Waiting…"

        )

        self.metric_time = self.make_metric(

            metrics, "REPORT TIME", "Waiting…"

        )

        self.metric_event = self.make_metric(

            metrics, "EVENT RISK", "UNKNOWN"

        )

        self.metric_flow = self.make_metric(

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

            "The interface will open before report retrieval finishes."

        )

        integrity_layout.addWidget(self.integrity_view, 1)

        layout.addWidget(integrity, 1)



        return page



    def make_metric(self, row, title, value):

        frame, layout = make_panel(title)

        value_label = make_label(value, 13, TEXT, True)

        value_label.setMinimumHeight(38)

        layout.addWidget(value_label)

        layout.addWidget(make_label("Backend-reported value", 8, MUTED))

        row.addWidget(frame, 1)

        return value_label



    # --------------------------------------------------------

    # REPORT PAGE

    # --------------------------------------------------------



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

        self.report_view.setPlaceholderText(

            "The report will appear here when available."

        )

        frame_layout.addWidget(self.report_view, 1)

        layout.addWidget(frame)



        return page



    # --------------------------------------------------------

    # AI ANALYSIS PAGE

    # --------------------------------------------------------



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

            "Optional question about NIFTY, BANK NIFTY, breadth, flows or risk…"

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



    # --------------------------------------------------------

    # NAVIGATION

    # --------------------------------------------------------



    def switch_page(self, index):

        self.pages.setCurrentIndex(index)



        for i, nav in enumerate(self.nav_buttons):

            active = i == index

            nav.setStyleSheet(f"""

                QPushButton {{

                    background: {GREEN if active else PANEL_ALT};

                    color: {BG if active else TEXT};

                    border: 1px solid {GREEN if active else BORDER};

                    border-radius: 8px;

                    padding: 9px 12px;

                    text-align: left;

                    font-weight: 600;

                }}

                QPushButton:hover {{

                    border-color: {CYAN};

                }}

            """)



    # --------------------------------------------------------

    # CACHE-FIRST STARTUP

    # --------------------------------------------------------



    def load_initial_report(self):
        """
        Cache-first startup: show the last saved report without starting
        network requests or the full stock scanner automatically.
        A full refresh is user-triggered with the Refresh Data button.
        """
        try:
            cached = load_latest_saved_report()
        except Exception:
            cached = None

        if cached:
            self.cache_is_displayed = True
            self.display_report(
                cached["report"],
                elapsed=0.0,
                cached=True,
                saved_at=cached["saved_at"],
                age_seconds=cached["age_seconds"],
            )
            self.connection_label.setText("SAVED REPORT")
            self.connection_label.setStyleSheet(f"color: {AMBER};")
            self.footer.setText(
                f"Showing saved report ({display_age(cached['age_seconds'])}). "
                "Press REFRESH DATA to run a full market scan."
            )
        else:
            self.cache_is_displayed = False
            self.status_data.setText("NO SAVED REPORT")
            self.status_data.setStyleSheet(f"color: {AMBER};")
            self.connection_label.setText("STANDBY")
            self.connection_label.setStyleSheet(f"color: {AMBER};")
            self.footer.setText(
                "No saved report found. Press REFRESH DATA to fetch market data."
            )

        self.progress.setRange(0, 100)
        self.progress.setValue(0)


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

            self.progress.setRange(0, 0)



            if self.cache_is_displayed:

                self.status_data.setText("CACHED • REFRESHING")

                self.status_data.setStyleSheet(f"color: {AMBER};")

            else:

                self.status_data.setText("LOADING…")

                self.status_data.setStyleSheet(f"color: {AMBER};")



        elif name == "analysis":

            self.analyze_btn.setEnabled(False)

            self.footer.setText("Nova AI is analyzing the market report…")



        worker.start()



    def task_finished(self, name, worker):

        self.workers.pop(name, None)



        if name == "report":

            self.refresh_btn.setEnabled(True)

            self.progress.setRange(0, 100)



        elif name == "analysis":

            self.analyze_btn.setEnabled(True)



        worker.deleteLater()



    def task_succeeded(self, name, result, elapsed):

        if name == "report":

            self.cache_is_displayed = False

            self.display_report(

                result,

                elapsed=elapsed,

                cached=False,

            )



        elif name == "analysis":

            self.display_analysis(result, elapsed)



    def task_failed(self, name, error, elapsed):

        if name == "report" and self.cache_is_displayed:

            self.status_data.setText("CACHED • REFRESH FAILED")

            self.status_data.setStyleSheet(f"color: {AMBER};")

            self.footer.setText(

                "Refresh failed. The saved report remains visible; "

                "check its timestamp before relying on it."

            )

        else:

            self.footer.setText(

                f"{name.title()} failed after {elapsed:.1f}s."

            )



        QMessageBox.critical(

            self,

            f"Nova Market Lab — {name.title()} error",

            error[-5000:],

        )



    # --------------------------------------------------------

    # REPORT REFRESH

    # --------------------------------------------------------



    def refresh_report(self):

        self.start_task(

            "report",

            get_market_lab_data,

            force_refresh=True,

        )



    def display_report(

        self,

        report,

        elapsed: float,

        cached: bool = False,

        saved_at: str | None = None,

        age_seconds: float | None = None,

    ):

        if not isinstance(report, dict) or not report:

            self.status_data.setText("NO REPORT")

            self.status_data.setStyleSheet(f"color: {RED};")

            self.footer.setText("The data engine returned no usable report.")

            return



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

                event_context,

                ("overall_risk", "status", "risk_level"),

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



        if cached:

            self.status_data.setText("CACHED REPORT")

            self.status_data.setStyleSheet(f"color: {AMBER};")

        else:

            self.status_data.setText("REPORT LOADED")

            self.status_data.setStyleSheet(f"color: {GREEN};")



        risk_text = str(event_risk).upper() if event_risk is not None else "UNKNOWN"

        self.status_event.setText(risk_text)

        self.status_event.setStyleSheet(

            f"color: {RED if risk_text in ('HIGH', 'CRITICAL') else AMBER};"

        )



        # Eligibility must be explicitly True; other values remain ineligible.

        if flow_eligible is True:

            flow_text = "ELIGIBLE"

            flow_color = GREEN

        elif flow_eligible is None:

            flow_text = "NOT VERIFIED"

            flow_color = AMBER

        else:

            flow_text = "NOT ELIGIBLE"

            flow_color = AMBER



        self.status_flow.setText(flow_text)

        self.status_flow.setStyleSheet(f"color: {flow_color};")



        # This interface never enables order execution.

        self.status_execution.setText("DISABLED")

        self.status_execution.setStyleSheet(f"color: {GREEN};")



        availability = find_section(

            report,

            ("data_availability", "data_quality", "source_quality"),

        )

        warnings = find_value(

            report,

            ("warnings", "data_warnings", "quality_warnings"),

        )



        if cached:

            report_age = (

                display_age(age_seconds)

                if age_seconds is not None

                else "unknown age"

            )

            report_origin = (

                f"Saved report timestamp: {saved_at}\n"

                f"Saved report age: {report_age}\n"

                "STATUS: CACHED — not guaranteed to reflect current market conditions."

            )

        else:

            report_origin = (

                f"Refresh completed at: "

                f"{datetime.now().isoformat(timespec='seconds')}\n"

                f"Refresh duration: {elapsed:.2f} seconds\n"

                "STATUS: Returned by the data engine; inspect source timestamps."

            )



        details = [

            report_origin,

            "",

            f"Market: {market if market is not None else 'Not reported'}",

            f"Report timestamp: {generated if generated is not None else 'Not reported'}",

            f"Event risk: {event_risk if event_risk is not None else 'UNKNOWN'}",

            f"Institutional-flow eligibility: {flow_eligible if flow_eligible is not None else 'Not reported'}",

            "",

            "DATA AVAILABILITY",

            pretty_json(availability)

            if availability is not None

            else "See the full report for data availability fields.",

            "",

            "WARNINGS",

            pretty_json(warnings)

            if warnings is not None

            else "No top-level warnings field found; inspect the full report.",

            "",

            "SAFETY",

            "- UNKNOWN event risk is not an all-clear.",

            "- Cached data may be stale.",

            "- Missing fields are not assumed to be zero.",

            "- Institutional-flow eligibility must follow backend verification rules.",

            "- Trading execution remains disabled.",

        ]



        self.integrity_view.setPlainText("\n".join(details))



        if cached:

            self.connection_label.setText("SAVED REPORT")

            self.connection_label.setStyleSheet(f"color: {AMBER};")

            self.footer.setText(

                f"Showing saved report ({display_age(age_seconds or 0)}). "

                "Background refresh is starting."

            )

        else:

            self.connection_label.setText(

                f"UPDATED {datetime.now().strftime('%H:%M:%S')}"

            )

            self.connection_label.setStyleSheet(f"color: {GREEN};")

            self.footer.setText(

                f"Report returned in {elapsed:.2f}s. "

                "Review source quality and warnings."

            )



        self.progress.setValue(100)



    # --------------------------------------------------------

    # AI ANALYSIS

    # --------------------------------------------------------



    def run_analysis(self):

        query = self.question.text().strip()



        self.start_task(

            "analysis",

            analyze_market_lab,

            query,

            False,

        )



    def display_analysis(self, result, elapsed):

        self.analysis_view.setPlainText(

            result if isinstance(result, str) else pretty_json(result)

        )

        self.switch_page(2)

        self.footer.setText(

            f"AI analysis returned in {elapsed:.2f}s. "

            "Validate conclusions against the report evidence."

        )



    # --------------------------------------------------------

    # WINDOW CLOSE

    # --------------------------------------------------------



    def closeEvent(self, event):

        running = [

            worker for worker in self.workers.values()

            if worker.isRunning()

        ]



        if running:

            QMessageBox.information(

                self,

                "Nova Market Lab",

                "A background task is still running. "

                "Wait for it to finish before closing the terminal.",

            )

            event.ignore()

            return



        event.accept()





# ============================================================

# ENTRY POINT

# ============================================================



def main() -> int:

    app = QApplication(sys.argv)

    app.setApplicationName(APP_NAME)

    app.setFont(QFont(FONT, 10))



    window = MarketLabWindow()

    window.show()



    return app.exec()





if __name__ == "__main__":

    raise SystemExit(main())
