from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, QSize, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from market_lab.market_lab_data import (
    CACHE_DIR,
    get_market_lab_data,
    save_json_report,
)
from market_lab.market_lab_brain import analyze_market_lab, analyze_stock_report
from market_lab import view_model as vm
from market_lab import widgets as W
from market_lab import stock_adapter
from market_lab import report_parser
from market_lab import icons as icons_module


# ============================================================
# NOVA MARKET LAB
# ============================================================

APP_NAME = "NOVA MARKET LAB"

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

# Left-rail navigation styling: dark-blue active + cyan indicator; disabled dim.
NAV_QSS = """
QPushButton {
    text-align:left; padding:9px 12px; background:transparent;
    border:none; border-left:3px solid transparent;
    color:%s; font-size:10pt; font-weight:600;
}
QPushButton:hover { background:%s; color:%s; }
QPushButton:checked { background:%s; color:%s; border-left:3px solid %s; }
QPushButton:disabled { color:%s; }
""" % (SECONDARY, PANEL_ALT, TEXT, "#0A2230", CYAN, CYAN, MUTED2)

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
AUTO_POLL_CLOSED_S = 30

# How long closeEvent waits for a running worker to finish so its Market MCP
# subprocess is torn down cleanly, before force-terminating it as a last
# resort. Market-closed cached/live-only polls finish in a few seconds; this
# is a generous safety ceiling so the window still always closes.
CLOSE_WORKER_WAIT_MS = 10000


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


IST = timezone(timedelta(hours=5, minutes=30))


def _parse_iso(value):
    """Parse an ISO-8601 stamp to an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _eta(hours):
    """Human time-until from a float number of hours (may be negative)."""
    if hours is None:
        return ""
    if hours < 0:
        return "started"
    if hours < 1:
        return f"in {int(hours * 60)}m"
    if hours < 48:
        return f"in {hours:.1f} h"
    return f"in {hours / 24:.1f} d"


def _risk_color(level):
    """Banner color for an overall risk level. UNKNOWN is never green."""
    level = str(level).upper()
    if level in ("HIGH", "CRITICAL", "SEVERE"):
        return RED
    if level in ("MODERATE", "ELEVATED", "WATCH"):
        return AMBER
    if level in ("LOW", "MINIMAL", "CALM"):
        return GREEN
    return AMBER


def format_event_risk(context, now=None):
    """Render the event-risk panel body from the report's event_risk_context.

    Pure and offline (no widgets, no network) so it can be unit-tested.
    Times are shown in IST; the countdown is recomputed from each event's
    datetime (not the report's frozen hours_until), so a cached report still
    shows an accurate 'time until' and clearly labels the source freshness.
    Descriptive context only — never a buy/sell signal.
    """
    if not isinstance(context, dict) or not context:
        return (
            "EVENT RISK: NOT AVAILABLE\n"
            "No event-risk context in this report."
        )

    overall = context.get("overall_risk", "UNKNOWN")
    status = context.get("status")
    score = context.get("overall_risk_score")
    count = context.get("upcoming_event_count")
    lookahead = context.get("lookahead_days")
    source_fresh = context.get("source_fresh")
    events = context.get("upcoming_events")
    now_utc = now or datetime.now(timezone.utc)

    lines = []
    header = f"OVERALL EVENT RISK: {overall}"
    if score is not None:
        header += f"   (risk score {score})"
    lines.append(header)

    meta = []
    if count is not None:
        meta.append(f"upcoming events: {count}")
    if lookahead is not None:
        meta.append(f"lookahead: {lookahead} days")
    if meta:
        lines.append("  |  ".join(meta))

    if source_fresh is True:
        lines.append("Calendar source: FRESH (re-verified within 24h).")
    elif source_fresh is False:
        lines.append(
            "Calendar source: STALE - not re-verified within 24h; "
            "event risk may be outdated."
        )
    else:
        lines.append("Calendar source: freshness unknown.")
    lines.append("")

    if status == "NOT_AVAILABLE" or not isinstance(events, list) or not events:
        lines.append(
            "No upcoming events in the lookahead window, or the event-risk "
            "engine returned no events."
        )
    else:
        lines.append("UPCOMING EVENTS (times in IST)")
        for event in events:
            if not isinstance(event, dict):
                continue
            name = event.get("name", "(unnamed event)")
            severity = str(
                event.get("severity") or event.get("risk_level") or "UNKNOWN"
            ).upper()

            parsed = _parse_iso(
                event.get("datetime_utc") or event.get("datetime")
            )
            if parsed is not None:
                ist_time = parsed.astimezone(IST).strftime(
                    "%a %d %b %Y, %H:%M IST"
                )
                hours = (parsed - now_utc).total_seconds() / 3600.0
                tail = f" - {ist_time}  |  {_eta(hours)}"
            elif isinstance(event.get("hours_until"), (int, float)):
                tail = f" - {_eta(event['hours_until'])} (time from report)"
            else:
                tail = ""
            lines.append(f"[{severity}] {name}{tail}")

            detail = []
            if event.get("category"):
                detail.append(f"category: {event['category']}")
            instruments = event.get("instruments")
            if isinstance(instruments, list) and instruments:
                detail.append(
                    "instruments: " + ", ".join(str(x) for x in instruments)
                )
            if detail:
                lines.append("      " + "  |  ".join(detail))
            if event.get("impact_note"):
                lines.append(f"      {event['impact_note']}")
            lines.append("")

    lines.append(
        "Descriptive context only. This is NOT a buy/sell signal. "
        "No broker, no orders, no execution."
    )
    return "\n".join(lines)


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


# ---------------------------------------------------------------------------
# Number formatting for the terminal (monospace-friendly). Never invents a
# value: vm.N_A (or any non-number) is passed through unchanged.
# ---------------------------------------------------------------------------

def fmt_price(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return vm.N_A
    return f"{value:,.2f}"


def fmt_points(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return vm.N_A
    return f"{value:,.0f}"


def fmt_pct(value, signed=True):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return vm.N_A
    return f"{value:+.2f}%" if signed else f"{value:.2f}%"


def fmt_num(value, places=2):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return vm.N_A
    return f"{value:,.{places}f}"


def fmt_crore(value):
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return vm.N_A
    return f"{value:+,.2f}"


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


# Premium cyan "ANALYZE" button (Stock Analysis page only). Gradient QSS with
# distinct hover/pressed/focus/disabled states plus an inline Enter-key hint.
ANALYZE_BUTTON_QSS = """
QPushButton#analyzePrimaryButton {
    color: #031018;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #00D9F5, stop:1 #00E6C8);
    border: 1px solid #00D9F5;
    border-radius: 12px;
    padding: 6px 38px 6px 16px;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 1px;
}
QPushButton#analyzePrimaryButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #2FE6FF, stop:1 #2BF0D6);
    border: 1px solid #7BEEFF;
}
QPushButton#analyzePrimaryButton:pressed {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                                stop:0 #00B8D0, stop:1 #00C9AE);
    padding: 7px 38px 5px 16px;
}
QPushButton#analyzePrimaryButton:focus {
    border: 2px solid #7BEEFF;
}
QPushButton#analyzePrimaryButton:disabled {
    background: #17313e;
    color: #5d707b;
    border: 1px solid #1f3b48;
}
"""


class AnalyzeButton(QPushButton):
    """Premium cyan ANALYZE button with an inline Enter-key hint.

    Only styling/hint; the caller wires `.clicked` to the existing analysis.
    """

    def __init__(self, text="ANALYZE", parent=None):
        super().__init__(text, parent)
        self.setObjectName("analyzePrimaryButton")
        self.setMinimumSize(150, 50)
        self.setMaximumHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(ANALYZE_BUTTON_QSS)
        try:
            from market_lab.icons import make_icon

            icon = make_icon("zap", "#031018", 16)
            if icon and not icon.isNull():
                self.setIcon(icon)
                self.setIconSize(QSize(16, 16))
        except Exception:
            pass
        self._hint = QLabel("\u23CE", self)  # return symbol
        self._hint.setObjectName("analyzeEnterHint")
        self._hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._hint.setStyleSheet(
            "QLabel#analyzeEnterHint { color:#031018;"
            " background: rgba(3,16,24,0.14); border-radius:4px;"
            " padding:1px 5px; font-size:11px; }"
        )
        self._hint.hide()

    def set_busy(self, busy):
        """Reflect the running state; restores the normal label when done."""
        self.setEnabled(not busy)
        self.setText("ANALYZING \u2026" if busy else "ANALYZE")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if not hasattr(self, "_hint") or self._hint is None:
            return
        self._hint.adjustSize()
        x = self.width() - self._hint.width() - 14
        # Keep room for the label; only show the hint when the button is wide.
        if self.isEnabled() and self.width() >= (self._hint.width() + 90):
            self._hint.move(x, (self.height() - self._hint.height()) // 2)
            self._hint.show()
        else:
            self._hint.hide()


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
        self._shutting_down = False
        self.cache_is_displayed = False
        self.chart_range = "3M"
        self._range_buttons = {}
        self.auto_enabled = False
        self.last_update_at = None
        self.next_poll_at = None
        self.auto_timer = None
        self.report_generated_at = None

        # Watchlist state; populated as each pinned symbol refreshes.
        self.watch_symbols = []
        self.watch_index = 0
        self.watch_data = {}

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
                border-radius:8px;
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
        # The display ticker always runs: it repaints only in-memory
        # labels every second and never touches the network.
        self.ensure_display_ticker()

    # --------------------------------------------------------
    # UI
    # --------------------------------------------------------

    def _make_nav(self, text, active, enabled=True):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(active)
        button.setEnabled(enabled)
        button.setCursor(
            Qt.CursorShape.PointingHandCursor if enabled
            else Qt.CursorShape.ArrowCursor
        )
        button.setStyleSheet(NAV_QSS)
        return button

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Fixed terminal header ---
        outer.addWidget(self.build_header())

        # --- Thin progress line ---
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

        # --- Status chips row ---
        status_row = QHBoxLayout()
        status_row.setContentsMargins(12, 8, 12, 4)
        status_row.setSpacing(10)
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

        # --- Body: left rail + sector | center pages | factor rankings ---
        body = QSplitter(Qt.Orientation.Horizontal)
        body.setHandleWidth(1)
        body.setStyleSheet(f"QSplitter::handle {{ background:{BORDER}; }}")

        left = QWidget()
        left.setObjectName("rail")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(10)

        rail = QFrame()
        rail.setObjectName("sidebar")
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(10, 12, 10, 12)
        rail_layout.setSpacing(6)
        rail_layout.addWidget(make_label("WORKSPACE", 9, MUTED, True))

        self.pages = QStackedWidget()
        self.nav_buttons = []

        specs = [
            ("Markets", self.build_overview),
            ("Stock Analysis", self.build_stock_page),
            ("Market Report", self.build_report_page),
            ("Nova Analysis", self.build_analysis_page),
            ("Factor Backtest", self.build_backtest_page),
            ("Event Risk", self.build_event_page),
        ]

        for index, (title, builder) in enumerate(specs):
            nav = self._make_nav(f"{index + 1:02d}  {title}", index == 0)
            nav.clicked.connect(
                lambda checked=False, i=index: self.switch_page(i)
            )
            rail_layout.addWidget(nav)
            self.nav_buttons.append(nav)
            self.pages.addWidget(builder())

        rail_layout.addStretch()

        # NOVA identity mark at the bottom of the rail.
        identity = QHBoxLayout()
        identity.setSpacing(8)
        mark = QLabel("N")
        mark.setFixedSize(28, 28)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setStyleSheet(
            f"QLabel {{ background:{PANEL_ALT}; color:{CYAN};"
            f" border:1px solid {CYAN}; border-radius:14px;"
            f" font-weight:bold; }}"
        )
        identity.addWidget(mark)
        idcol = QVBoxLayout()
        idcol.setSpacing(0)
        idcol.addWidget(make_label("NOVA", 11, TEXT, True))
        idcol.addWidget(make_label("MARKET LAB · read-only", 8, MUTED2))
        identity.addLayout(idcol)
        identity.addStretch()
        rail_layout.addLayout(identity)

        left_layout.addWidget(rail)

        # Sector overview beneath the rail (real sector data only).
        self.sector_panel = self.build_sector_panel()
        left_layout.addWidget(self.sector_panel, 1)

        body.addWidget(left)
        body.addWidget(self.pages)

        self.uptrend_panel = self.build_uptrend_panel()
        body.addWidget(self.uptrend_panel)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([260, 1160, 380])
        left.setMinimumWidth(230)
        left.setMaximumWidth(280)
        self.uptrend_panel.setMinimumWidth(320)
        self.uptrend_panel.setMaximumWidth(420)
        outer.addWidget(body, 1)

        # --- Footer status line (operational text) ---
        self.footer = make_label("Initializing terminal…", 9, MUTED)
        self.footer.setContentsMargins(12, 4, 12, 4)
        outer.addWidget(self.footer)

        # --- Persistent guardrails bar (never hidden by ordinary UI actions) ---
        self.guardrails = W.GuardrailsBar()
        self.guardrails.set_authorized(
            bool(vm.guardrails({})["buy_sell_authorization"])
        )
        outer.addWidget(self.guardrails)

    def build_header(self):
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(56)
        header.setStyleSheet(f"""
            QFrame#header {{
                background:{SIDEBAR};
                border-bottom:1px solid {BORDER};
            }}
        """)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(14, 6, 14, 6)
        hl.setSpacing(12)

        brand = QVBoxLayout()
        brand.setSpacing(0)
        brand.addWidget(W.make_label("NOVA MARKET LAB", 15, GREEN, True))
        brand.addWidget(W.make_label("INDIAN MARKET INTELLIGENCE", 8, MUTED, True))
        hl.addLayout(brand)
        hl.addSpacing(14)

        # Symbol search pins a symbol into the existing watchlist engine.
        self.symbol_search = QLineEdit()
        self.symbol_search.setFixedWidth(230)
        self.symbol_search.setPlaceholderText("Search symbol, sector, or insight...")
        self.symbol_search.returnPressed.connect(self._search_symbol)
        hl.addWidget(self.symbol_search)

        hl.addStretch()

        # Data-age + scanner freshness (measured from backend timestamps).
        self.data_age_label = W.make_label("data age —", 9, MUTED, True)
        hl.addWidget(self.data_age_label)
        self.scan_age_badge = W.FreshnessBadge()
        hl.addWidget(self.scan_age_badge)

        self.mode_chip = W.stat_chip("MODE: CACHE-FIRST", CYAN)
        hl.addWidget(self.mode_chip)
        self.session_badge = W.stat_chip("SESSION —", AMBER)
        hl.addWidget(self.session_badge)
        self.vix_chip = W.stat_chip("VIX —", MUTED)
        hl.addWidget(self.vix_chip)

        self.connection_label = W.make_label("INITIALIZING", 9, AMBER, True)
        hl.addWidget(self.connection_label)

        self.refresh_btn = make_button("↻  FULL REFRESH", True)
        self.refresh_btn.clicked.connect(self.refresh_report)
        hl.addWidget(self.refresh_btn)

        self.live_btn = make_button("⚡ LIVE UPDATE", False)
        self.live_btn.clicked.connect(self.live_update_report)
        hl.addWidget(self.live_btn)

        self.auto_btn = make_button("AUTO: OFF", False)
        self.auto_btn.setCheckable(True)
        self.auto_btn.clicked.connect(self.toggle_auto_refresh)
        hl.addWidget(self.auto_btn)

        self.clock_label = W.make_label("--:--:--", 10, MUTED, True)
        hl.addWidget(self.clock_label)
        return header

    def _search_symbol(self):
        """Pin the typed symbol(s) into the existing watchlist and jump to
        the Nova Analysis page. Uses the real watchlist refresh path only."""
        text = self.symbol_search.text().strip().upper()
        if not text:
            return
        symbols = [s.strip() for s in text.replace(" ", ",").split(",") if s.strip()]
        existing = [s for s in self.watch_input.text().split(",") if s.strip()]
        self.watch_input.setText(", ".join(existing + symbols))
        self.symbol_search.clear()
        self.switch_page(3)  # Nova Analysis (watchlist lives there)
        self.apply_watchlist()

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

    # --------------------------------------------------------
    # Reusable dashboard pieces
    # --------------------------------------------------------

    def _index_card(self, name):
        frame, layout = W.panel(name, "Backend index snapshot")
        frame.setMinimumHeight(330)
        self_price_row = QHBoxLayout()
        price = W.make_label("—", 28, TEXT, bold=True, mono=True)
        change = W.make_label("—", 15, MUTED, bold=True, mono=True)
        change.setWordWrap(False)
        self_price_row.addWidget(price)
        self_price_row.addWidget(change)
        self_price_row.addStretch()
        layout.addLayout(self_price_row)
        meta = W.make_label("—", 9, MUTED)
        meta.setWordWrap(False)
        layout.addWidget(meta)
        chart = W.CandleChart()
        chart.setMinimumHeight(160)
        layout.addWidget(chart, 1)
        ohlc = W.make_label("O —  H —  L —  C —", 10, TEXT, mono=True)
        ohlc.setWordWrap(False)
        layout.addWidget(ohlc)
        returns = W.make_label("5d —  |  20d —  |  60d —", 9, MUTED, mono=True)
        layout.addWidget(returns)
        return {
            "frame": frame, "price": price, "change": change, "meta": meta,
            "chart": chart, "ohlc": ohlc, "returns": returns,
        }

    def _indicator_card(self, name):
        frame, layout = W.panel(name, "")
        frame.setFixedHeight(116)
        value = W.make_label("—", 18, TEXT, bold=True, mono=True)
        value.setWordWrap(False)
        interp = W.make_label("—", 9, MUTED)
        interp.setWordWrap(False)
        interp.setToolTip(name)
        layout.addWidget(value)
        layout.addWidget(interp)
        layout.addStretch()
        return {"frame": frame, "value": value, "interp": interp}

    # --------------------------------------------------------
    # PAGES
    # --------------------------------------------------------

    _RANGE_BARS = {"1M": 22, "3M": 63, "6M": 126}

    def _slice_candles(self, candles, rng):
        limit = self._RANGE_BARS.get(rng, 63)
        return candles[-limit:] if candles else []

    def set_chart_range(self, rng):
        """Switch the index chart range (client-side slice of real candles;
        no refetch)."""
        self.chart_range = rng
        for label, button in getattr(self, "_range_buttons", {}).items():
            button.setChecked(label == rng)
        if getattr(self, "report", None):
            for which in ("nifty", "bank_nifty"):
                card = vm.index_card(self.report, which)
                c = self.index_cards[which]
                candles = [dict(row) for row in (card.get("candles") or [])
                           if isinstance(row, dict)]
                if candles and isinstance(card["price"], (int, float)):
                    candles[-1]["c"] = float(card["price"])
                    if isinstance(card["high"], (int, float)):
                        candles[-1]["h"] = max(candles[-1]["h"], float(card["high"]))
                    if isinstance(card["low"], (int, float)):
                        candles[-1]["l"] = min(candles[-1]["l"], float(card["low"]))
                c["chart"].set_candles(self._slice_candles(candles, rng))

    # --------------------------------------------------------
    # KPI strip (real values only)
    # --------------------------------------------------------

    _KPI_TITLES = (
        ("nifty", "NIFTY 50"),
        ("vix", "INDIA VIX"),
        ("advances", "ADVANCES"),
        ("declines", "DECLINES"),
        ("ad", "A/D RATIO"),
    )

    def _kpi_card(self, title):
        frame, layout = W.panel(title)
        frame.setFixedHeight(96)
        layout.setSpacing(4)
        value = W.make_label("—", 22, TEXT, bold=True, mono=True)
        value.setWordWrap(False)
        layout.addWidget(value)
        sub = W.make_label("—", 10, MUTED, mono=True)
        sub.setWordWrap(False)
        sub.setToolTip(title)
        layout.addWidget(sub)
        bar = W.FillBar()
        bar.setVisible(False)
        layout.addWidget(bar)
        layout.addStretch()
        return {"frame": frame, "value": value, "sub": sub, "bar": bar}

    def build_kpi_strip(self):
        strip = QHBoxLayout()
        strip.setSpacing(10)
        self.kpi = {}
        for key, title in self._KPI_TITLES:
            card = self._kpi_card(title)
            strip.addWidget(card["frame"], 1)
            self.kpi[key] = card
        return strip

    def render_kpi(self, report):
        try:
            card = vm.index_card(report, "nifty")
            macro = vm.macro(report)
            breadth = vm.breadth_block(report)

            def set_change(cell, value):
                if isinstance(value, (int, float)):
                    cell.setText(fmt_pct(value))
                    cell.setStyleSheet(
                        f"color:{W.sign_color(value)};"
                        "background:transparent;border:none;"
                    )
                else:
                    cell.setText(vm.N_A)
                    cell.setStyleSheet(
                        f"color:{MUTED};background:transparent;border:none;"
                    )

            c = self.kpi["nifty"]
            c["value"].setText(fmt_price(card["price"]))
            set_change(c["sub"], card["change_percent"])
            c["bar"].setVisible(False)

            c = self.kpi["vix"]
            c["value"].setText(fmt_num(macro["india_vix"]))
            set_change(c["sub"], macro["vix_change_percent"])
            c["bar"].setVisible(False)

            advances = breadth["advancing"]
            declines = breadth["declining"]
            total = None
            if (isinstance(advances, (int, float))
                    and isinstance(declines, (int, float))
                    and (advances + declines) > 0):
                total = advances + declines

            c = self.kpi["advances"]
            c["value"].setText(f"{advances:,}" if isinstance(advances, (int, float)) else vm.N_A)
            if total:
                frac = advances / total
                c["bar"].set_fraction(frac, GREEN)
                c["bar"].setVisible(True)
                c["sub"].setText(f"{frac * 100:.1f}% of movers")
            else:
                c["bar"].setVisible(False)
                c["sub"].setText(vm.N_A)

            c = self.kpi["declines"]
            c["value"].setText(f"{declines:,}" if isinstance(declines, (int, float)) else vm.N_A)
            if total:
                frac = declines / total
                c["bar"].set_fraction(frac, RED)
                c["bar"].setVisible(True)
                c["sub"].setText(f"{frac * 100:.1f}% of movers")
            else:
                c["bar"].setVisible(False)
                c["sub"].setText(vm.N_A)

            c = self.kpi["ad"]
            c["value"].setText(fmt_num(breadth["ad_ratio"]))
            c["sub"].setText("advance / decline")
            c["bar"].setVisible(False)
        except Exception:
            self._render_failure("kpi", sys.exc_info()[1])

    # --------------------------------------------------------
    # Section renderers: Macro cards (01) + Breadth panel (02)
    # --------------------------------------------------------

    def _macro_cards(self, report):
        m = vm.macro(report)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setSpacing(12)
        h.setContentsMargins(0, 0, 0, 0)

        # Card A — Market Regime (dominant, tinted by regime)
        regime = str(m["market_regime"]).upper()
        accent = RED if regime == "BEARISH" else (
            GREEN if regime == "BULLISH" else CYAN
        )
        card_a, la = W.panel("Market Regime")
        card_a.setStyleSheet(
            f"QFrame#novaPanel {{ background:{PANEL};"
            f" border:1px solid {accent}; border-radius:8px; }}"
        )
        la.addWidget(W.make_label(regime, 30, accent, bold=True))
        la.addWidget(W.make_label("scanner classification (not a signal)", 9, MUTED))
        la.addStretch()
        h.addWidget(card_a, 30)

        # Card B — NIFTY 50 Level (+ real sparkline from candles)
        card_b, lb = W.panel("NIFTY 50 Level")
        lb.addWidget(W.make_label(fmt_price(m["nifty_price"]), 26, TEXT,
                                  bold=True, mono=True))
        closes = [c["c"] for c in (report.get("nifty_candles") or [])
                  if isinstance(c, dict)]
        spark = W.Sparkline(width=220, height=40)
        spark.set_series(closes[-40:])
        lb.addWidget(spark)
        h.addWidget(card_b, 35)

        # Card C — India VIX (Dhan/engine value + 1D change; no series -> no sparkline)
        card_c, lc = W.panel("India VIX")
        lc.addWidget(W.make_label(fmt_num(m["india_vix"]), 26, TEXT,
                                  bold=True, mono=True))
        lc.addWidget(W.make_label(f"{fmt_pct(m['vix_change_percent'])} 1D", 11,
                                  W.sign_color(m["vix_change_percent"]), mono=True))
        lc.addWidget(W.make_label(f"regime: {m['vix_regime']}", 9, MUTED))
        h.addWidget(card_c, 35)
        return row

    def _breadth_panel(self, report):
        b = vm.breadth_block(report)
        row = QWidget()
        h = QHBoxLayout(row)
        h.setSpacing(14)
        h.setContentsMargins(0, 0, 0, 0)

        advances = b["advancing"]
        declines = b["declining"]
        total = None
        if (isinstance(advances, (int, float))
                and isinstance(declines, (int, float))
                and (advances + declines) > 0):
            total = advances + declines

        # Advances (left)
        left = QVBoxLayout()
        left.addWidget(W.make_label("ADVANCES", 10, MUTED, True))
        left.addWidget(W.make_label(
            f"{advances:,}" if isinstance(advances, (int, float)) else vm.N_A,
            24, GREEN, bold=True, mono=True))
        left.addWidget(W.make_label(
            f"{advances / total * 100:.1f}% of movers" if total else vm.N_A,
            9, MUTED))
        h.addLayout(left)

        # Stacked bar (center)
        bar = W.StackBar(height=18)
        if total:
            bar.set_segments([(advances / total, GREEN),
                              (declines / total, RED)])
        h.addWidget(bar, 1)

        # Declines (right of bar)
        right = QVBoxLayout()
        right.addWidget(W.make_label("DECLINES", 10, MUTED, True))
        right.addWidget(W.make_label(
            f"{declines:,}" if isinstance(declines, (int, float)) else vm.N_A,
            24, RED, bold=True, mono=True))
        right.addWidget(W.make_label(
            f"{declines / total * 100:.1f}% of movers" if total else vm.N_A,
            9, MUTED))
        h.addLayout(right)

        # A/D ratio (far right, separated)
        h.addWidget(self._vsep())
        ad = QVBoxLayout()
        ad.addWidget(W.make_label("A/D RATIO", 10, MUTED, True))
        ad.addWidget(W.make_label(fmt_num(b["ad_ratio"]), 22, TEXT,
                                  bold=True, mono=True))
        ad.addWidget(W.make_label("advance / decline", 9, MUTED))
        h.addLayout(ad)
        return row

    @staticmethod
    def _macro_availability(report):
        return "AVAILABLE" if vm.macro(report).get("market_regime") else vm.N_A

    # ---- table cell painting helpers (color + alignment) ----

    @staticmethod
    def _paint_cell(table, row, col, color, center=False):
        item = table.item(row, col)
        if item is None:
            return
        item.setForeground(QColor(color))
        if center:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
            )
        else:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            )

    @staticmethod
    def _regime_color(regime):
        r = str(regime).upper()
        if r in ("POSITIVE", "STRONG", "BULLISH", "UPTREND", "STRONG_UPTREND"):
            return GREEN
        if r in ("NEGATIVE", "WEAK", "BEARISH", "DOWNTREND", "STRONG_DOWNTREND"):
            return RED
        return MUTED

    @staticmethod
    def _trend_color(trend):
        t = str(trend).upper()
        if "UPTREND" in t or "BULL" in t:
            return GREEN
        if "DOWNTREND" in t or "BEAR" in t:
            return RED
        return MUTED

    def _box(self, widgets):
        from PySide6.QtWidgets import QWidget as _QW
        box = _QW()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        for w in widgets:
            lay.addWidget(w)
        return box

    # ---- Section widgets (03 Sector, 04 Technical, 05 Derivatives,
    #      06 Flow, 08 Factor Rankings) ----

    def _sector_table(self, report):
        rows = vm.sector_rows(report, limit=25)
        if not rows:
            return W.make_label(
                "Sector data unavailable in this report.", 10, MUTED)

        summ = vm.sector_summary(report)
        strongest, weakest = summ["strongest"], summ["weakest"]
        cards = [
            self._stat_card("STRONGEST (20D)",
                            f"{strongest['name']}  {fmt_pct(strongest['return_20d'])}"
                            if strongest else vm.N_A,
                            GREEN if strongest else None),
            self._stat_card("WEAKEST (20D)",
                            f"{weakest['name']}  {fmt_pct(weakest['return_20d'])}"
                            if weakest else vm.N_A,
                            RED if weakest else None),
            self._stat_card("SECTORS TRACKED", summ["count"]),
        ]

        table = W.make_table(["#", "Sector", "20D %", "Perf", "RS 20D", "Regime"],
                             stretch_column=1)
        W.fill_table(table, [
            [i, r["name"], fmt_pct(r["return_20d"]), "",
             fmt_num(r["relative_strength_20d"], 1), r["regime"]]
            for i, r in enumerate(rows, 1)])
        scale = max([abs(r["return_20d"]) for r in rows
                     if isinstance(r["return_20d"], (int, float))] or [1.0]) or 1.0
        for i, r in enumerate(rows):
            self._paint_cell(table, i, 0, MUTED, center=True)
            self._paint_cell(table, i, 2, W.sign_color(r["return_20d"]))
            self._paint_cell(table, i, 4, W.sign_color(r["relative_strength_20d"]))
            self._paint_cell(table, i, 5, self._regime_color(r["regime"]), center=True)
            bar = W.PerfBar()
            bar.set_value(r["return_20d"], scale)
            table.setCellWidget(i, 3, bar)
        return self._box([self._cards_row(cards), table])

    def _technical_widget(self, report):
        t = vm.technical_block(report)
        summ = vm.uptrend_summary(report)
        rows = t["top_stocks"]

        cards = [
            self._stat_card("STOCKS ANALYZED", f"{summ['analyzed']:,}"),
            self._stat_card("STRONG UPTRENDS", summ["strong_uptrends"], GREEN,
                            f"of {summ['shorted']} shown"),
            self._stat_card("STRONG DOWNTRENDS", summ["strong_downtrends"], RED,
                            f"of {summ['shorted']} shown"),
        ]

        table = W.make_table(["Rank", "Symbol", "Score", "Meter", "Trend"],
                             stretch_column=1)
        W.fill_table(table, [
            [r["rank"], r["symbol"], fmt_num(r["technical_score"], 1), "",
             r["trend"]]
            for r in rows])
        for i, r in enumerate(rows):
            score = r.get("technical_score")
            self._paint_cell(table, i, 0, MUTED, center=True)
            self._paint_cell(table, i, 2, CYAN if isinstance(score, (int, float)) else MUTED)
            self._paint_cell(table, i, 4, self._trend_color(r["trend"]))
            meter = W.FillBar()
            meter.set_fraction((score / 100.0) if isinstance(score, (int, float)) else 0.0,
                               CYAN)
            table.setCellWidget(i, 3, meter)

        # Indicator availability (honest; per-stock lists are not in the report).
        avail = QWidget()
        avail_row = QHBoxLayout(avail)
        avail_row.setContentsMargins(0, 0, 0, 0)
        avail_row.setSpacing(8)
        for name, state in (("RSI (oversold/overbought)", t["rsi_oversold"]),
                            ("MACD crossovers", t["macd_crossovers"]),
                            ("Support/Resistance", t["support_resistance"])):
            ok = str(state).upper() != "N/A"
            avail_row.addWidget(W.stat_chip(f"{name}: {'AVAILABLE' if ok else state}",
                                            GREEN if ok else AMBER))
        avail_row.addStretch()
        note = W.make_label(
            "Per-stock RSI/MACD/support-resistance lists are not stored in the "
            "saved report and are shown as N/A. A score of 100 is a scanner "
            "score, not a probability of gain.", 9, MUTED)
        note.setWordWrap(True)
        note.setToolTip("These indicator lists are not part of the saved report; "
                        "an honest N/A is shown instead of fabricated signals.")
        return self._box([self._cards_row(cards), table, avail, note])

    def _derivatives_widget(self, report):
        n = vm.derivatives_block(report, "nifty")
        b = vm.derivatives_block(report, "bank_nifty")
        if not (n.get("available") or b.get("available")):
            return W.make_label(
                "Derivatives data unavailable in this report.", 10, MUTED)

        cards = [
            self._stat_card("NIFTY SPOT", fmt_price(n.get("spot")) if n.get("available") else vm.N_A),
            self._stat_card("EXPIRY", n.get("expiry", vm.N_A) if n.get("available") else vm.N_A),
            self._stat_card("NIFTY OI PCR", fmt_num(n.get("oi_pcr"), 3) if n.get("available") else vm.N_A,
                            CYAN, "OI PCR = put OI / call OI"),
            self._stat_card("NIFTY MAX PAIN", fmt_points(n.get("max_pain")) if n.get("available") else vm.N_A),
        ]

        def cell(d, key, formatter):
            return formatter(d.get(key)) if d.get("available") else vm.N_A

        table = W.make_table(["Metric", "NIFTY", "BANK NIFTY"], stretch_column=0)
        W.fill_table(table, [
            ["Spot", cell(n, "spot", fmt_price), cell(b, "spot", fmt_price)],
            ["Expiry", cell(n, "expiry", lambda v: v), cell(b, "expiry", lambda v: v)],
            ["OI PCR", cell(n, "oi_pcr", lambda v: fmt_num(v, 3)),
                       cell(b, "oi_pcr", lambda v: fmt_num(v, 3))],
            ["Volume PCR", cell(n, "volume_pcr", lambda v: fmt_num(v, 3)),
                            cell(b, "volume_pcr", lambda v: fmt_num(v, 3))],
            ["Max Pain", cell(n, "max_pain", fmt_points),
                          cell(b, "max_pain", fmt_points)],
            ["ATM IV", cell(n, "atm_iv", lambda v: fmt_num(v)),
                        cell(b, "atm_iv", lambda v: fmt_num(v))],
            ["Put / Call wall",
             f"{n.get('put_wall', vm.N_A)} / {n.get('call_wall', vm.N_A)}" if n.get("available") else vm.N_A,
             f"{b.get('put_wall', vm.N_A)} / {b.get('call_wall', vm.N_A)}" if b.get("available") else vm.N_A],
        ])

        pieces = [self._cards_row(cards), table]

        # Backend-generated options interpretation (real engine output).
        interp = n.get("interpretation") or b.get("interpretation")
        if isinstance(interp, str) and interp and interp != vm.N_A:
            inner_frame, inner_layout = W.panel("Positioning interpretation")
            inner_layout.addWidget(W.make_label(interp, 9, TEXT))
            inner_layout.addWidget(W.make_label(
                f"Engine output • {n.get('timestamp', vm.N_A)}", 8, MUTED))
            pieces.append(inner_frame)

        # Unusual open-interest activity (real strikes).
        unusual = n.get("unusual_activity") or []
        if unusual:
            ut = W.make_table(["Type", "Strike", "OI", "Vol", "State"],
                              stretch_column=4)
            W.fill_table(ut, [
                [u.get("type", vm.N_A), fmt_points(u.get("strike")),
                 f"{int(u['oi']):,}" if isinstance(u.get("oi"), (int, float)) else vm.N_A,
                 f"{int(u['vol']):,}" if isinstance(u.get("vol"), (int, float)) else vm.N_A,
                 u.get("state", vm.N_A)]
                for u in unusual[:8]])
            pieces.append(W.make_label("UNUSUAL OI ACTIVITY (strike-level)", 9, MUTED, True))
            pieces.append(ut)

        note = W.make_label(
            "OI concentrations/depth are not labeled guaranteed support or "
            "resistance. A per-strike OI-distribution chart is not stored in the "
            "saved report, so it is not drawn.", 9, AMBER)
        note.setWordWrap(True)
        pieces.append(note)
        return self._box(pieces)

    def _flow_widget(self, report):
        f = vm.flow_block(report)
        if not f["available"]:
            return W.make_label(
                "Institutional flow unavailable in this report.", 10, MUTED)
        series = vm.flow_series(report)
        unit = series["unit"]
        cards = [
            self._stat_card("FII NET 20D", f"{fmt_crore(f['fii_20d'])} cr",
                            W.sign_color(f["fii_20d"])),
            self._stat_card("DII NET 20D", f"{fmt_crore(f['dii_20d'])} cr",
                            W.sign_color(f["dii_20d"])),
            self._stat_card("FLOW REGIME", f["flow_regime"], CYAN),
            self._stat_card("LATEST DATE", f["latest_date"]),
        ]

        chart = W.GroupedBarChart(height=150)
        chart.set_data(series["categories"], [
            {"label": "FII", "color": CYAN, "values": series["fii"]},
            {"label": "DII", "color": GREEN, "values": series["dii"]},
        ])

        table = self._kv_table([
            ["Flow regime", f["flow_regime"]],
            ["FII net 5D (₹ cr)", fmt_crore(f["fii_5d"])],
            ["DII net 5D (₹ cr)", fmt_crore(f["dii_5d"])],
            ["FII net 10D (₹ cr)", fmt_crore(f["fii_10d"])],
            ["DII net 10D (₹ cr)", fmt_crore(f["dii_10d"])],
            ["FII net 20D (₹ cr)", fmt_crore(f["fii_20d"])],
            ["DII net 20D (₹ cr)", fmt_crore(f["dii_20d"])],
            ["Latest date", f["latest_date"]],
            ["Primary coverage",
             (f"{f['primary_verified']}/{f['target_sessions']} sessions verified"
              if f.get("primary_verified") is not None else vm.N_A)],
            ["Signal eligible",
             ("YES" if f["signal_allowed"] else f"NO — {f['signal_reason']}")],
        ], value_field="INR crore")
        for i, key in enumerate(["x", "fii_5d", "dii_5d", "fii_10d", "dii_10d",
                                 "fii_20d", "dii_20d"], start=1):
            if key in f:
                self._paint_cell(table, i, 1, W.sign_color(f[key]))

        fii_streak = f.get("fii_streak") or [None, None]
        dii_streak = f.get("dii_streak") or [None, None]
        note = W.make_label(
            f"FII {fii_streak[0]} for {fii_streak[1]}d • DII {dii_streak[0]} for "
            f"{dii_streak[1]}d • unit: {unit}. Cash-market participant flows "
            f"(end-of-day), not proprietary order-book data. Net flow across "
            f"5D/10D/20D horizons (₹ crore), zero baseline at the center.",
            9, MUTED)
        note.setWordWrap(True)
        note.setToolTip("Delayed end-of-day participant activity; not real-time "
                        "institutional transactions.")
        return self._box([self._cards_row(cards), chart, table, note])

    def _factor_widget(self, report):
        summ = vm.factor_summary(report)
        cards = [
            self._stat_card("FACTORS EVALUATED", summ["factors_evaluated"]),
            self._stat_card("STOCKS COVERED", f"{summ['stocks']:,}"
                            if isinstance(summ["stocks"], (int, float)) else vm.N_A),
            self._stat_card("BEST (COMPOSITE Z)", summ["best_symbol"], GREEN),
            self._stat_card("RANK DATE", summ["as_of"]),
        ]
        pieces = [self._cards_row(cards)]

        avail = W.make_table(["Factor", "Availability"], stretch_column=0)
        W.fill_table(avail, [[f, "EVALUATED (z shown: "
                                + ("yes" if summ["per_factor_z_available"] else "no") + ")"]
                             for f in summ["factors_available"]] +
                             [[f, "NOT_AVAILABLE"]
                              for f in summ["factors_unavailable"]])
        for r in range(avail.rowCount()):
            cell = avail.item(r, 1)
            if cell is not None:
                cell.setForeground(QColor(
                    MUTED if cell.text().startswith("NOT_AVAILABLE") else GREEN))
        pieces.append(W.make_label("FACTOR COVERAGE", 9, MUTED, True))
        pieces.append(avail)

        for title, data in (("TOP 10 (composite z)", summ["top"]),
                            ("BOTTOM 10 (composite z)", summ["bottom"])):
            if not data:
                continue
            table = W.make_table(["Rank", "Symbol", "Composite Z", "Price"],
                                 stretch_column=1)
            W.fill_table(table, [
                [r["rank"], r["symbol"], fmt_num(r["composite_z"], 3),
                 fmt_price(r["price"])] for r in data])
            for i, r in enumerate(data):
                self._paint_cell(table, i, 0, MUTED, center=True)
                self._paint_cell(table, i, 2, W.sign_color(r["composite_z"]))
            pieces.append(W.make_label(title, 9, MUTED, True))
            pieces.append(table)

        pieces.append(W.make_label(
            f"Method: {summ['method']}. Per-factor z is not populated in this "
            "report, so per-factor score bars are not shown; only the "
            "equal-weight composite z (real) is displayed. QUALITY/VALUE "
            "fundamentals are NOT computed by Nova.", 9, AMBER))
        return self._box(pieces)

    # ---- reusable summary cards for section panels ----

    def _stat_card(self, title, value, color=None, note=None):
        frame, layout = W.panel(title)
        frame.setFixedHeight(78)
        layout.setSpacing(2)
        value_label = W.make_label(str(value), 18, color or TEXT,
                                   bold=True, mono=True)
        value_label.setWordWrap(False)
        value_label.setToolTip(str(value))
        layout.addWidget(value_label)
        if note:
            note_label = W.make_label(note, 8, MUTED)
            note_label.setWordWrap(False)
            layout.addWidget(note_label)
        layout.addStretch()
        return frame

    def _cards_row(self, cards, spacing=10):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(spacing)
        for card in cards:
            h.addWidget(card, 1)
        return row

    def _bullets(self, items, color, empty="No points recorded in the analysis."):
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)
        if not items:
            note = W.make_label(empty, 9, MUTED)
            note.setWordWrap(True)
            lay.addWidget(note)
        else:
            for item in items:
                label = W.make_label(f"\u2022  {item}", 9, color)
                label.setWordWrap(True)
                lay.addWidget(label)
        return box

    def _evidence_panel(self, title, items, color, icon_name):
        """An evidence panel with an icon + bold title header row, bullet list,
        and a trailing stretch so paired panels align to the same top and fill
        equal height."""
        frame, layout = W.panel()
        header = QHBoxLayout()
        header.setSpacing(8)
        pm = icons_module.icon_pixmap(icon_name, color, 16)
        if pm is not None:
            icon_label = QLabel()
            icon_label.setPixmap(pm)
            header.addWidget(icon_label)
        header.addWidget(W.make_label(title, 10, color, bold=True))
        header.addStretch()
        layout.addLayout(header)
        layout.addWidget(self._bullets(items, color))
        layout.addStretch()
        return frame

    # --------------------------------------------------------
    # Stock Analysis terminal (per-stock; real data + AI report)
    # --------------------------------------------------------

    _STOCK_MODE_KEYS = {
        "Quick Scan": "quick",
        "Full Analysis": "full",
        "Institutional Analysis": "institutional",
    }
    _STOCK_RANGE_PERIOD = {"3M": "3mo", "6M": "6mo", "1Y": "1y"}

    def build_stock_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # Controls
        controls, cl = W.panel(
            "Stock analysis",
            "Enter any supported NSE symbol. Metrics, chart and the AI report "
            "are stock-specific. Analysis-only — no broker/orders.",
        )
        row = QHBoxLayout()
        row.setSpacing(10)
        search_icon_pm = icons_module.icon_pixmap("search", MUTED, 16)
        if search_icon_pm is not None:
            icon_label = QLabel()
            icon_label.setPixmap(search_icon_pm)
            row.addWidget(icon_label)
        row.addWidget(W.make_label("SYMBOL", 9, MUTED, True))
        self.stock_symbol_input = QLineEdit()
        self.stock_symbol_input.setFixedWidth(220)
        self.stock_symbol_input.setPlaceholderText("Enter symbol (e.g. RELIANCE)")
        self.stock_symbol_input.returnPressed.connect(self.run_stock_analysis)
        row.addWidget(self.stock_symbol_input)
        row.addWidget(W.make_label("MODE", 9, MUTED, True))
        self.stock_mode = QComboBox()
        self.stock_mode.addItems(["Quick Scan", "Full Analysis",
                                  "Institutional Analysis"])
        self.stock_mode.setCurrentIndex(1)
        row.addWidget(self.stock_mode)
        row.addWidget(W.make_label("RANGE", 9, MUTED, True))
        self.stock_range = QComboBox()
        self.stock_range.addItems(["3M", "6M", "1Y"])
        self.stock_range.setCurrentIndex(1)
        self.stock_range.currentIndexChanged.connect(self._stock_range_changed)
        row.addWidget(self.stock_range)
        self.stock_analyze_btn = AnalyzeButton("ANALYZE")
        self.stock_analyze_btn.clicked.connect(self.run_stock_analysis)
        row.addWidget(self.stock_analyze_btn)
        row.addStretch()
        cl.addLayout(row)
        self.stock_status = W.make_label(
            "Ready. Enter a symbol and press Analyze.", 9, MUTED)
        cl.addWidget(self.stock_status)
        layout.addWidget(controls)

        # Body (rebuilt per analysis) holder
        self.stock_page_layout = layout
        self._stock_clear()
        scroll.setWidget(page)
        return scroll

    def _reset_stock_body(self):
        """Rebuild a fresh stock-body container (avoids stale widget/layout
        lifetime across analyses)."""
        old = getattr(self, "stock_body", None)
        if old is not None and self.stock_page_layout is not None:
            self.stock_page_layout.removeWidget(old)
            old.setParent(None)
        self.stock_body = QWidget()
        self.stock_body_layout = QVBoxLayout(self.stock_body)
        self.stock_body_layout.setContentsMargins(0, 0, 0, 0)
        self.stock_body_layout.setSpacing(12)
        if self.stock_page_layout is not None:
            self.stock_page_layout.addWidget(self.stock_body, 1)

    def _stock_clear(self):
        self._reset_stock_body()
        placeholder = W.make_label(
            "No stock analyzed yet. Enter a symbol above and press Analyze.",
            10, MUTED)
        self.stock_body_layout.addWidget(placeholder)

    def _stock_range_changed(self):
        # Re-run with the new range only if a symbol is present.
        if self.stock_symbol_input.text().strip():
            self.run_stock_analysis()

    def run_stock_analysis(self):
        query = self.stock_symbol_input.text().strip()
        if not query:
            self.stock_status.setText("Enter a symbol first.")
            self.stock_status.setStyleSheet(f"color:{AMBER};")
            return

        self._stock_clear()
        self.stock_report_placeholder()

        resolved = stock_adapter.resolve_symbol(query)
        if not resolved:
            self.stock_status.setText(
                f"No NSE security found for '{query}'. Try a symbol like RELIANCE.")
            self.stock_status.setStyleSheet(f"color:{RED};")
            self._stock_append_label(
                f"Unresolved symbol '{query}' — nothing to analyze.", RED)
            return

        symbol = resolved["symbol"]
        mode_key = self._STOCK_MODE_KEYS.get(
            self.stock_mode.currentText(), "full")
        period = self._STOCK_RANGE_PERIOD.get(
            self.stock_range.currentText(), "6mo")
        self.stock_status.setText(f"Analyzing {symbol} ({mode_key})…")
        self.stock_status.setStyleSheet(f"color:{CYAN};")
        self.start_task(
            "stock_analysis", self._stock_worker,
            symbol, mode_key, period, self.report,
        )

    def _stock_worker(self, symbol, mode_key, period, report):
        metrics = stock_adapter.stock_metrics(symbol)
        candles = stock_adapter.stock_candles(symbol, period=period)
        osc = stock_adapter.stock_oscillators(candles)
        ai = analyze_stock_report(symbol, metrics or {}, candles,
                                  report or {}, mode_key)
        return {"ok": bool(isinstance(metrics, dict) and metrics.get("price") is not None),
                "symbol": symbol, "metrics": metrics, "candles": candles,
                "osc": osc, "ai": ai}

    def stock_report_placeholder(self):
        layout = getattr(self, "stock_body_layout", None)
        if layout is None:
            return
        self.stock_report = QPlainTextEdit()
        self.stock_report.setReadOnly(True)
        self.stock_report.setPlaceholderText("Waiting for analysis…")
        self.stock_report.setMinimumHeight(180)
        layout.addWidget(self.stock_report)

    def _stock_append_label(self, text, color):
        layout = getattr(self, "stock_body_layout", None)
        if layout is not None:
            layout.addWidget(W.make_label(text, 10, color))

    def render_stock_result(self, result):
        self._reset_stock_body()
        layout = getattr(self, "stock_body_layout", None)
        if layout is None:
            return

        metrics = result.get("metrics") if isinstance(result, dict) else None
        metrics = metrics if isinstance(metrics, dict) else {}
        candles = result.get("candles") or []
        symbol = result.get("symbol") or metrics.get("symbol") or "?"

        if not metrics.get("price"):
            self._stock_append_label(
                f"No usable live/history data for {symbol} right now "
                f"(provider unavailable or market closed). Nothing was "
                f"fabricated.", AMBER)
            self.stock_report = QPlainTextEdit()
            self.stock_report.setReadOnly(True)
            self.stock_report.setPlainText(
                result.get("ai", "") or "No analysis generated.")
            layout.addWidget(self.stock_report)
            return

        # Identity strip
        holder = self._stock_identity_panel(metrics)
        layout.addWidget(holder)

        # KPI cards (real metrics only)
        ktiles = stock_adapter.kpi_tiles(metrics)
        cards = [
            self._stat_card("TREND", ktiles["trend"], self._trend_color(ktiles["trend"])),
            self._stat_card("MOMENTUM SCORE",
                            fmt_num(ktiles["momentum_score"], 1), CYAN,
                            "scanner score, not a probability"),
            self._stat_card("RSI 14", fmt_num(ktiles["rsi"]), None,
                            str(ktiles["rsi_condition"])),
            self._stat_card("MACD", fmt_num(ktiles["macd"]), None,
                            str(ktiles["macd_condition"])),
            self._stat_card("ATR 14", fmt_num(ktiles["atr"]), None, "INR"),
            self._stat_card("REL VOLUME", fmt_num(ktiles["relative_volume"], 2)),
        ]
        layout.addWidget(self._cards_row(cards))

        # Chart (real candles + MA overlays; PyQtGraph price/volume/RSI/MACD
        # when available, otherwise the lightweight QPainter candle chart).
        chart_frame, chart_layout = W.panel(
            "Price (daily OHLC)",
            "Candles + volume + RSI/MACD from real history. Hover the price "
            "panel for OHLC/change. Not a forecast.")
        if getattr(W, "PG_AVAILABLE", False):
            chart = W.PgCandleChart()
            chart.setMinimumHeight(420)
            osc = result.get("osc") or {}
            chart.set_data(candles, osc.get("rsi"), osc.get("macd"),
                           osc.get("signal"), osc.get("hist"))
        else:
            chart = W.CandleChart()
            chart.setMinimumHeight(320)
            chart.set_candles(candles)
            overlays = []
            for key, color in (("ma20", CYAN), ("ma50", AMBER), ("ma200", PURPLE)):
                overlays.append({"values": [c.get(key) for c in candles],
                                 "color": color})
            chart.set_overlays(overlays)
        chart_layout.addWidget(chart, 1)
        layout.addWidget(chart_frame, 1)

        # ---------------- AI Research Report (structured) ----------------
        self._render_ai_report(layout, result, symbol, metrics, candles)

        # Data quality (compact)
        dq = stock_adapter.data_quality(metrics, candles)
        table = W.make_table(["Component", "Status"], stretch_column=0)
        W.fill_table(table, [[k, v] for k, v in dq.items()])
        for r in range(table.rowCount()):
            state = table.item(r, 1).text()
            color = GREEN if state == "AVAILABLE" else (
                AMBER if state == "PARTIAL" else MUTED)
            self._paint_cell(table, r, 1, color, center=True)
        layout.addWidget(W.make_label("DATA QUALITY", 9, MUTED, True))
        layout.addWidget(table)

        # Secondary market-wide context (clearly labeled)
        ctx = stock_adapter.market_context(self.report or {})
        ctx_frame, ctx_layout = W.panel("Market-wide context (secondary)")
        ctx_layout.addWidget(W.make_label(
            f"Regime: {ctx['market_regime']}  \u2022  India VIX: {ctx['india_vix']}  "
            f"\u2022  FII 20D: {fmt_num(ctx['fii_20d'])}  "
            f"\u2022  DII 20D: {fmt_num(ctx['dii_20d'])}",
            9, MUTED))
        ctx_layout.addWidget(W.make_label(
            "These are MARKET-WIDE figures, not this stock's own activity.",
            8, AMBER))
        layout.addWidget(ctx_frame)

    def _render_ai_report(self, layout, result, symbol, metrics, candles):
        """Structured AI Research Report: header, executive summary with bias,
        bullish/bearish evidence, interactive tabs, key levels, risk, and a
        raw fallback. Compact 'not available' notes replace oversized cards.
        """
        parsed = report_parser.parse_report(result.get("ai", "") or "")
        bias = parsed["bias"]
        bias_color = {
            "BULLISH": GREEN, "BEARISH": RED, "NEUTRAL": MUTED,
            "MIXED": AMBER, "INSUFFICIENT EVIDENCE": AMBER, "UNAVAILABLE": MUTED,
        }.get(bias, MUTED)

        report_frame, report_layout = W.panel()

        # Header
        hdr = QHBoxLayout()
        ai_pm = icons_module.icon_pixmap("zap", CYAN, 24)
        if ai_pm is not None:
            icon_lbl = QLabel()
            icon_lbl.setPixmap(ai_pm)
            hdr.addWidget(icon_lbl)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        titles.addWidget(W.make_label("AI Research Report", 16, TEXT, True))
        sub = W.make_label(
            "Stock-specific research based on available market data. "
            "Observations are separated from AI interpretation.", 9, MUTED)
        sub.setWordWrap(True)
        titles.addWidget(sub)
        hdr.addLayout(titles)
        hdr.addStretch()
        hdr.addWidget(W.make_label("Success  \u2022  generated just now",
                                   9, GREEN))
        copy_btn = make_button("Copy", False)
        copy_btn.clicked.connect(self._copy_stock_report)
        hdr.addWidget(copy_btn)
        refresh_btn = make_button("Re-run", False)
        refresh_btn.clicked.connect(self.run_stock_analysis)
        hdr.addWidget(refresh_btn)
        report_layout.addLayout(hdr)
        disclaimer = W.make_label(
            "AI-generated analysis \u2014 informational and educational only; "
            "not a validated prediction or instruction to trade.", 8, AMBER)
        disclaimer.setWordWrap(True)
        report_layout.addWidget(disclaimer)

        # Executive summary: bias card + indicator KPIs
        exec_row = QHBoxLayout()
        bias_card, bias_layout = W.panel("Analytical bias")
        bias_layout.addWidget(
            W.make_label(bias, 22, bias_color, bold=True))
        bias_layout.addWidget(W.make_label(
            "From the report's own conclusion; not a forecast.", 8, MUTED))
        exec_row.addWidget(bias_card)
        kpi_strip = self._cards_row([
            self._stat_card("TREND", metrics.get("trend", vm.N_A),
                            self._trend_color(metrics.get("trend"))),
            self._stat_card("MOMENTUM", fmt_num(metrics.get("momentum_score"), 1),
                            CYAN, "scanner score, not a probability"),
            self._stat_card("RSI 14", fmt_num(metrics.get("rsi_14")), None,
                            str(metrics.get("rsi_condition", vm.N_A))),
            self._stat_card("MACD", fmt_num(metrics.get("macd")), None,
                            str(metrics.get("macd_condition", vm.N_A))),
        ])
        exec_row.addWidget(kpi_strip, 1)
        report_layout.addLayout(exec_row)

        # Bullish / Bearish evidence
        bull_items = report_parser.collect_bullets(
            report_parser.sections_matching(parsed, "bullish", "positive"))
        bear_items = report_parser.collect_bullets(
            report_parser.sections_matching(
                parsed, "bearish", "negative", "risk", "limitation"))
        bull_frame = self._evidence_panel(
            "Bullish factors", bull_items, GREEN, "trending-up")
        bear_frame = self._evidence_panel(
            "Bearish factors", bear_items, RED, "trending-down")
        bb = QHBoxLayout()
        bb.setSpacing(12)
        bb.addWidget(bull_frame, 1)
        bb.addWidget(bear_frame, 1)
        report_layout.addLayout(bb)

        # Interactive tabs
        tabs = QTabWidget()
        tabs.setObjectName("reportTabs")
        tabs.setStyleSheet(
            f"QTabWidget#reportTabs::pane {{ border:1px solid {BORDER};"
            f" border-radius:8px; top:-1px; }}"
            f"QTabBar::tab {{ background:{PANEL}; color:{MUTED};"
            " padding:6px 12px; border:1px solid transparent; }"
            f"QTabBar::tab:selected {{ background:{PANEL_ALT}; color:{TEXT};"
            f" border:1px solid {BORDER}; border-bottom:2px solid {CYAN}; }}"
        )
        tech_items = report_parser.collect_bullets(
            report_parser.sections_matching(
                parsed, "technical", "momentum", "trend")) or \
            report_parser.collect_bullets(parsed.get("sections", {}))
        tech_page = QWidget()
        tech_layout = QVBoxLayout(tech_page)
        tech_layout.addWidget(self._bullets(
            tech_items, TEXT, "No technical observations were recorded."))
        tech_scroll = QScrollArea()
        tech_scroll.setWidgetResizable(True)
        tech_scroll.setWidget(tech_page)
        tabs.addTab(tech_scroll, "Technical Analysis")

        fund_page = QWidget()
        fund_layout = QVBoxLayout(fund_page)
        fund_layout.addWidget(W.make_label(
            "Fundamentals are not available: Nova has no fundamentals data "
            "source, so no revenue, earnings, valuation or peer metrics are "
            "shown. This is a data limitation, not a zero reading.",
            10, AMBER))
        tabs.addTab(fund_page, "Fundamental Context")

        biz_page = QWidget()
        biz_layout = QVBoxLayout(biz_page)
        name = metrics.get("company_name") or symbol
        biz_layout.addWidget(W.make_label(f"{name}  \u2022  {symbol}  \u2022  NSE",
                                          12, TEXT, True))
        biz_layout.addWidget(W.make_label(
            "Business-segment and company-profile data are not provided by the "
            "current Nova data sources; only identity from the exchange symbol "
            "master is available.", 9, MUTED))
        biz_layout.addStretch()
        tabs.addTab(biz_page, "Business Overview")

        risk_items = report_parser.collect_bullets(
            report_parser.sections_matching(
                parsed, "risk", "outlook", "limitation", "invalidat", "summary"))
        risk_page = QWidget()
        risk_layout = QVBoxLayout(risk_page)
        risk_layout.addWidget(W.make_label("Risks & Outlook", 11, AMBER, True))
        risk_layout.addWidget(self._bullets(
            risk_items, TEXT, "No explicit risks were recorded in the report."))
        risk_scroll = QScrollArea()
        risk_scroll.setWidgetResizable(True)
        risk_scroll.setWidget(risk_page)
        tabs.addTab(risk_scroll, "Risks & Outlook")
        report_layout.addWidget(tabs)

        # Key price levels (compact; support/resistance not calculated)
        level_rows = [
            ("Resistance 2", parsed["levels"].get("r2")),
            ("Resistance 1", parsed["levels"].get("r1")),
            ("Current price", metrics.get("price")),
            ("Support 1", parsed["levels"].get("s1")),
            ("Support 2", parsed["levels"].get("s2")),
        ]
        level_table = W.make_table(["Level", "Value"], stretch_column=0)
        W.fill_table(level_table, [[label, fmt_price(value)]
                                   for label, value in level_rows])
        levels_frame, levels_layout = W.panel("Key price levels")
        levels_layout.addWidget(level_table)
        levels_layout.addWidget(W.make_label(
            "Support/resistance are not calculated by Nova's engine; values "
            "shown only when the AI report states them. Absent \u2260 zero.",
            8, MUTED))
        report_layout.addWidget(levels_frame)

        # Full AI report (raw) fallback so nothing is dropped.
        raw_frame, raw_layout = W.panel("Full AI report (raw)")
        self.stock_report = QPlainTextEdit()
        self.stock_report.setReadOnly(True)
        self.stock_report.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._set_stock_ai(result.get("ai", "") or "", symbol)
        raw_layout.addWidget(self.stock_report, 1)
        raw_frame.setVisible(bool(parsed["raw"]))
        report_layout.addWidget(raw_frame)

        layout.addWidget(report_frame, 1)

    def _copy_stock_report(self):
        clipboard = QApplication.clipboard()
        text = ""
        if hasattr(self, "stock_report"):
            text = self.stock_report.toPlainText()
        if not text:
            self.stock_status.setText("No report text to copy.")
            return
        clipboard.setText(text)
        self.stock_status.setText("Report copied to clipboard.")
        self.stock_status.setStyleSheet(f"color:{GREEN};")

    def _set_stock_ai(self, text, symbol=None):
        """Show the AI report; on an AI error, preserve the previous successful
        report for the same symbol (with its original content) instead of
        replacing it with only an error/disclaimer."""
        text = text or ""
        is_error = (
            text.startswith("STOCK ANALYSIS AI ERROR")
            or text.startswith("MARKET LAB AI ERROR")
        )
        prev = getattr(self, "_last_stock_report", None)
        if is_error and prev and prev.get("symbol") == symbol and prev.get("text"):
            self.stock_report.setPlainText(prev["text"])
            self.stock_status.setText(
                f"AI report failed; showing the previous good report "
                f"for {symbol}.")
            self.stock_status.setStyleSheet(f"color:{AMBER};")
            return
        self.stock_report.setPlainText(text)
        if not is_error and text:
            self._last_stock_report = {"symbol": symbol, "text": text}

    def _stock_identity_panel(self, metrics):
        frame, layout = W.panel("Selected security")
        layout.addWidget(W.make_label(
            f"{metrics.get('company_name') or metrics.get('symbol')}  •  "
            f"{metrics.get('symbol')}  •  {metrics.get('exchange', 'NSE')}",
            15, TEXT, True))
        layout.addWidget(W.make_label(
            f"Last {fmt_price(metrics.get('price'))}  "
            f"({fmt_pct(metrics.get('change_percent'))})   "
            f"H {fmt_points(metrics.get('high'))}  L {fmt_points(metrics.get('low'))}",
            11, W.sign_color(metrics.get("change_percent")), mono=True))
        layout.addWidget(W.make_label(
            f"52W H {fmt_points(metrics.get('high_52w'))}  "
            f"L {fmt_points(metrics.get('low_52w'))}  •  volume "
            f"{metrics.get('volume') if isinstance(metrics.get('volume'), (int, float)) else vm.N_A}"
            f"  •  as of {metrics.get('timestamp', vm.N_A)} (last session)",
            9, MUTED))
        return frame

    def build_overview(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

        # --- Market KPI strip ---
        layout.addLayout(self.build_kpi_strip())

        # --- Chart range selector (slices the stored real candles) ---
        range_row = QHBoxLayout()
        range_row.setSpacing(6)
        range_row.addWidget(W.make_label("INDEX CHART RANGE", 9, MUTED, True))
        for label in ("1M", "3M", "6M"):
            button = make_button(f" {label} ", self.chart_range == label)
            button.setCheckable(True)
            button.setChecked(self.chart_range == label)
            button.clicked.connect(
                lambda checked=False, r=label: self.set_chart_range(r)
            )
            self._range_buttons[label] = button
            range_row.addWidget(button)
        range_row.addStretch()
        layout.addLayout(range_row)

        # --- Index cards ---
        indices = QHBoxLayout()
        indices.setSpacing(12)
        self.index_cards = {}
        for which in ("nifty", "bank_nifty"):
            self.index_cards[which] = self._index_card(
                "NIFTY 50" if which == "nifty" else "BANK NIFTY"
            )
            indices.addWidget(self.index_cards[which]["frame"], 1)
        layout.addLayout(indices)

        # --- Technical indicator cards ---
        indicators = QHBoxLayout()
        indicators.setSpacing(12)
        self.ind_cards = {}
        for label in ("RSI", "MACD", "ATR", "VOL"):
            self.ind_cards[label] = self._indicator_card(label)
            indicators.addWidget(self.ind_cards[label]["frame"], 1)
        layout.addLayout(indicators)

        # --- Metric chips (kept for compatibility + header context) ---
        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        self.metric_market = self.add_metric(metrics, "MARKET", "Waiting…")
        self.metric_time = self.add_metric(metrics, "REPORT TIME", "Waiting…")
        self.metric_event = self.add_metric(metrics, "EVENT RISK", "UNKNOWN")
        self.metric_flow = self.add_metric(
            metrics, "FLOW ELIGIBILITY", "Unverified"
        )
        layout.addLayout(metrics)

        # --- Breadth table ---
        bframe, blayout = W.panel(
            "Market breadth",
            "Scanner breadth. Metrics the backend does not compute are N/A.",
        )
        self.breadth_table = W.make_table(["Metric", "Value"], stretch_column=1)
        blayout.addWidget(self.breadth_table)
        layout.addWidget(bframe)

        # --- Live 1 s strip (pure in-memory repaint, no network) ---
        live_strip, live_strip_layout = make_panel(
            "Live",
            "1-second display • data polls every 60 s open / 30 s closed.",
        )
        self.live_clock_value = W.make_label("--:--:--", 13, TEXT, True, mono=True)
        live_strip_layout.addWidget(self.live_clock_value)
        self.live_session_value = W.make_label("NSE …", 10, MUTED, True)
        live_strip_layout.addWidget(self.live_session_value)
        self.live_age_value = W.make_label("data age …", 10, MUTED)
        live_strip_layout.addWidget(self.live_age_value)
        self.live_next_value = W.make_label("next update …", 10, MUTED)
        live_strip_layout.addWidget(self.live_next_value)
        layout.addWidget(live_strip)

        # --- Data integrity ---
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

        scroll.setWidget(page)
        return scroll

    # --------------------------------------------------------
    # Ten-section report workspace
    # --------------------------------------------------------

    _REPORT_SECTIONS = [
        ("01", "Macro Overview"),
        ("02", "Market Breadth"),
        ("03", "Sector Intelligence"),
        ("04", "Technical Analysis"),
        ("05", "Derivatives Intelligence"),
        ("06", "Institutional Flow"),
        ("07", "Risk Metrics"),
        ("08", "Factor Rankings"),
        ("09", "Earnings Calendar"),
        ("10", "Guardrails"),
    ]

    def build_report_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 12)
        layout.setSpacing(10)

        self.report_sections = {}
        for number, title in self._REPORT_SECTIONS:
            section = W.CollapsibleSection(int(number), title, vm.N_A)
            self.report_sections[number] = section
            layout.addWidget(section)

        # Raw report kept as a utility collapsible (NOT one of the 10 sections).
        raw = W.CollapsibleSection("+", "Raw report (JSON)")
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setPlaceholderText("Waiting for market report…")
        raw.add(self.report_view)
        raw.set_expanded(False)
        layout.addWidget(raw)

        layout.addStretch()
        scroll.setWidget(page)
        return scroll

    # --------------------------------------------------------
    # Left sector panel + right factor panel
    # --------------------------------------------------------

    def build_sector_panel(self):
        frame, layout = W.panel(
            "Sector overview",
            "Top sectors by 20D performance. Real data only — never synthesized.",
        )
        self.sector_scroll = QScrollArea()
        self.sector_scroll.setWidgetResizable(True)
        self.sector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.sector_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.sector_container = QWidget()
        self.sector_rows_layout = QVBoxLayout(self.sector_container)
        self.sector_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.sector_rows_layout.setSpacing(5)
        self.sector_scroll.setWidget(self.sector_container)
        layout.addWidget(self.sector_scroll, 1)
        self.sector_note = W.make_label("Loading sector data…", 9, MUTED)
        layout.addWidget(self.sector_note)
        return frame

    @staticmethod
    def _clear_layout(layout):
        try:
            while layout.count():
                item = layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.setParent(None)
        except RuntimeError:
            pass

    def _sector_row(self, name, return_20d, relative_strength, regime, scale):
        row = QFrame()
        row.setStyleSheet(
            f"QFrame {{ background:transparent; border-bottom:1px solid {BORDER}; }}"
        )
        rh = QHBoxLayout(row)
        rh.setContentsMargins(2, 3, 2, 3)
        rh.setSpacing(8)
        name_lbl = W.make_label(str(name), 9, TEXT)
        name_lbl.setToolTip(str(name))
        rh.addWidget(name_lbl, 3)
        bar = W.PerfBar()
        bar.set_value(return_20d, scale)
        bar.setFixedWidth(64)
        rh.addWidget(bar, 0)
        pct = W.make_label(fmt_pct(return_20d), 9, W.sign_color(return_20d),
                           bold=True, mono=True)
        pct.setFixedWidth(58)
        pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        rh.addWidget(pct, 0)
        reg = W.make_label(str(regime), 8, MUTED)
        reg.setFixedWidth(60)
        reg.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        rh.addWidget(reg, 0)
        return row

    def render_sector(self, report):
        rows = vm.sector_rows(report, limit=10)
        self._clear_layout(self.sector_rows_layout)
        if rows:
            scale = max(abs(r["return_20d"]) for r in rows if r["return_20d"] is not None)
            for r in rows:
                self.sector_rows_layout.addWidget(
                    self._sector_row(
                        r["name"], r["return_20d"],
                        r["relative_strength_20d"], r["regime"], scale or 1.0,
                    )
                )
            self.sector_rows_layout.addStretch()
            self.sector_note.setText(
                f"{len(rows)} sectors • source: scanner sector engine"
            )
        else:
            self.sector_rows_layout.addWidget(
                W.make_label("Sector data unavailable in this report.", 9, MUTED)
            )
            self.sector_note.setText("Sector data unavailable.")

    def build_uptrend_panel(self):
        frame, layout = W.panel(
            "Top Uptrend Stocks",
            "Current technical trend/score ranking from the report "
            "(top_technical_stocks). Nova does not compute long-run growth "
            "fundamentals — this is a trend screen, not a growth forecast "
            "and not a buy/sell signal.",
        )
        self.uptrend_table = W.make_table(
            ["#", "Symbol", "Score", "Trend"], stretch_column=1
        )
        layout.addWidget(self.uptrend_table)
        self.uptrend_note = W.make_label("Loading uptrend screen…", 9, MUTED)
        self.uptrend_note.setWordWrap(True)
        layout.addWidget(self.uptrend_note)
        layout.addStretch()
        return frame

    def render_uptrend(self, report):
        rows = []
        for item in (report.get("top_technical_stocks") or []):
            if isinstance(item, dict):
                rows.append(item)
        # Rank by technical score (strongest first); real values only.
        rows.sort(key=lambda r: r.get("technical_score") or 0, reverse=True)
        rows = rows[:15]

        W.fill_table(self.uptrend_table, [
            [i, r.get("symbol", vm.N_A), fmt_num(r.get("technical_score"), 1),
             r.get("trend", vm.N_A)]
            for i, r in enumerate(rows, 1)
        ])
        for i, r in enumerate(rows):
            self._paint_cell(self.uptrend_table, i, 0, MUTED, center=True)
            self._paint_cell(self.uptrend_table, i, 3,
                             self._trend_color(r.get("trend")))

        if rows:
            self.uptrend_note.setText(
                "Strongest current uptrend by score/trend from the existing "
                "scanner. Not a long-range growth prediction; fundamentals "
                "(value/quality/growth) are not computed by Nova."
            )
        else:
            self.uptrend_note.setText(
                "No technical top-list in this report."
            )

    # --------------------------------------------------------
    # Small table builders for report sections
    # --------------------------------------------------------

    @staticmethod
    def _kv_table(rows, title_field="Field", value_field="Value"):
        table = W.make_table([title_field, value_field], stretch_column=1)
        W.fill_table(table, rows)
        return table

    @staticmethod
    def _list_table(headers, rows, stretch=1):
        table = W.make_table(headers, stretch_column=stretch)
        W.fill_table(table, rows)
        return table

    @staticmethod
    def _vsep():
        from PySide6.QtWidgets import QFrame as _QF
        line = _QF()
        line.setFixedWidth(1)
        line.setStyleSheet(f"background:{BORDER}; border:none;")
        return line

    def _fill_section(self, number, availability, add_func):
        section = self.report_sections[number]
        section.set_availability(availability)
        section.clear_body()
        add_func(section)

    # --------------------------------------------------------
    # Renderers (all read-only; populate existing widgets in place)
    # --------------------------------------------------------

    def update_header(self, report, now=None):
        try:
            age = vm.data_age(report, now=now)
            self.data_age_label.setText(f"data age {age['label']}")
            if hasattr(self, "live_age_value"):
                self.live_age_value.setText(f"data age: {age['label']}")
        except Exception:
            pass

        try:
            scan = vm.scanner_info(report, now=now)
            if scan["count"] is not None:
                self.scan_age_badge.set_age(
                    scan["level"], f"{scan['count']:,} stocks • {scan['label']}"
                )
            else:
                self.scan_age_badge.set_age(None, "scan age —")
        except Exception:
            pass

        try:
            session = vm.session_status(now=now)
            label = session["label"]
            color = GREEN if session["open"] else MUTED
            W.restyle_chip(self.session_badge, f"SESSION {label}", color)
            if hasattr(self, "live_session_value"):
                self.live_session_value.setText(f"NSE {label}")
        except Exception:
            pass

        try:
            macro = vm.macro(report)
            vix = macro["india_vix"]
            if vix is None:
                W.restyle_chip(self.vix_chip, "VIX N/A", MUTED)
            else:
                W.restyle_chip(self.vix_chip, f"VIX {vix:.2f}", CYAN)  # type: ignore
        except Exception:
            pass

        try:
            g = vm.guardrails(report)
            if hasattr(self, "guardrails"):
                self.guardrails.set_authorized(g["buy_sell_authorization"])
        except Exception:
            pass

    def render_dashboard(self, report):
        # --- Index cards ---
        self.render_kpi(report)
        for which in ("nifty", "bank_nifty"):
            card = vm.index_card(report, which)
            c = self.index_cards[which]
            c["price"].setText(fmt_price(card["price"]))
            if isinstance(card["change_percent"], (int, float)):
                c["change"].setText(
                    f"{fmt_pct(card['change_percent'])}"
                    f"  ({fmt_points(card['change_abs'])})"
                )
                c["change"].setStyleSheet(
                    f"color:{W.sign_color(card['change_percent'])};"
                    f"background:transparent;border:none;"
                )
            else:
                c["change"].setText(vm.N_A)
                c["change"].setStyleSheet(
                    f"color:{MUTED};background:transparent;border:none;"
                )
            c["ohlc"].setText(
                f"O {fmt_points(card['open'])}  H {fmt_points(card['high'])}  "
                f"L {fmt_points(card['low'])}  C {fmt_points(card['price'])}"
            )
            # Real daily OHLC candles; last candle tracks the live price so the
            # chart feels live between refreshes. Sliced by the range selector.
            candles = [dict(row) for row in (card.get("candles") or [])
                       if isinstance(row, dict)]
            if candles and isinstance(card["price"], (int, float)):
                candles[-1]["c"] = float(card["price"])
                if isinstance(card["high"], (int, float)):
                    candles[-1]["h"] = max(candles[-1]["h"], float(card["high"]))
                if isinstance(card["low"], (int, float)):
                    candles[-1]["l"] = min(candles[-1]["l"], float(card["low"]))
            c["chart"].set_candles(self._slice_candles(candles, self.chart_range))
            c["returns"].setText(
                f"5d {fmt_pct(card['return_5d'])}  |  "
                f"20d {fmt_pct(card['return_20d'])}  |  "
                f"60d {fmt_pct(card['return_60d'])}"
            )

        # --- Indicator cards ---
        ind = vm.indicator_cards(report, "nifty")
        for label in ("RSI", "MACD", "ATR", "VOL"):
            card = self.ind_cards[label]
            data = ind[label]
            value = data["value"]
            if isinstance(value, (int, float)):
                unit = data.get("unit")
                text = fmt_num(value) + (f" {unit}" if unit else "")
                card["value"].setText(text)
                card["value"].setStyleSheet(
                    f"color:{TEXT};background:transparent;border:none;"
                )
            else:
                card["value"].setText(vm.N_A)
                card["value"].setStyleSheet(
                    f"color:{MUTED};background:transparent;border:none;"
                )
            card["interp"].setText(str(data.get("interpretation", vm.N_A)))

        # --- Breadth ---
        b = vm.breadth_block(report)
        rows = [
            ["Advances", b["advancing"]],
            ["Declines", b["declining"]],
            ["Unchanged", b["unchanged"]],
            ["A/D Ratio", fmt_num(b["ad_ratio"])],
            ["% above EMA20", fmt_pct(b["above_ema20_percent"], signed=False)],
            ["% above EMA50", fmt_pct(b["above_ema50_percent"], signed=False)],
            ["% above EMA200", fmt_pct(b["above_ema200_percent"], signed=False)],
            ["Strong uptrend %", fmt_pct(b["strong_uptrend_percent"], signed=False)],
            ["Strong downtrend %", fmt_pct(b["strong_downtrend_percent"], signed=False)],
            ["New 52w highs", b["new_52w_highs"]],
            ["New 52w lows", b["new_52w_lows"]],
            ["McClellan Summation", b["mcclellan_summation"]],
        ]
        W.fill_table(self.breadth_table, rows)

        self.update_header(report)

    def _render_failure(self, panel, exc):
        """Record that one panel failed to render without crashing the rest
        of the dashboard; the failure is surfaced in the footer/integrity view
        rather than substituting fabricated data."""
        message = f"{panel} panel render failed: {type(exc).__name__}: {exc}"
        try:
            self.footer.setText(message)
        except Exception:
            pass
        try:
            self.integrity_view.appendPlainText("\n" + message)
        except Exception:
            pass

    def render_report_sections(self, report):
        # --- 01 Macro Overview (premium 3-card row) ---
        macro = vm.macro(report)
        self._fill_section(
            "01",
            "AVAILABLE" if macro.get("market_regime") else vm.N_A,
            lambda s: s.add(self._macro_cards(report)),
        )

        # --- 02 Market Breadth (visual stacked advances/declines panel) ---
        self._fill_section(
            "02", "AVAILABLE", lambda s: s.add(self._breadth_panel(report))
        )

        # --- 03 Sector intelligence (ranked, colorized table) ---
        sectors = vm.sector_rows(report, limit=25)
        self._fill_section(
            "03", "AVAILABLE" if sectors else "NOT_AVAILABLE",
            lambda s: s.add(self._sector_table(report)))

        # --- 04 Technical analysis (ranked table, colored score/trend) ---
        self._fill_section(
            "04", "PARTIAL",
            lambda s: s.add(self._technical_widget(report)))

        # --- 05 Derivatives intelligence (compact NIFTY vs BANK NIFTY) ---
        self._fill_section(
            "05", "AVAILABLE",
            lambda s: s.add(self._derivatives_widget(report)))

        # --- 06 Institutional flow (colorized FII/DII) ---
        f = vm.flow_block(report)
        self._fill_section(
            "06", "AVAILABLE" if f["available"] else "NOT_AVAILABLE",
            lambda s: s.add(self._flow_widget(report)))

        # --- 07 Risk metrics (market-risk context; portfolio stats not computed) ---
        rk = vm.risk_block(report)
        rc = vm.risk_cards(report)
        def _risk(sec):
            cards = [
                self._stat_card("REALIZED VOL 20D",
                                f"{fmt_num(rc['realized_vol_20d'])}%" if rc["realized_vol_20d"] is not None else vm.N_A),
                self._stat_card("REALIZED VOL 60D",
                                f"{fmt_num(rc['realized_vol_60d'])}%" if rc["realized_vol_60d"] is not None else vm.N_A),
                self._stat_card("ATR %", fmt_num(rc["atr_pct"])),
                self._stat_card("VOL PERCENTILE", fmt_num(rc["vol_percentile"], 1),
                                None, "1y percentile of realized volatility"),
                self._stat_card("VOL REGIME", rc["vol_regime"],
                                AMBER if str(rc["vol_regime"]).upper() in ("HIGH", "ELEVATED") else None,
                                f"direction: {rc['vol_direction']}"),
                self._stat_card("EXP DAILY MOVE", f"{fmt_num(rc['expected_daily_move'])}%"),
            ]
            sec.add(self._cards_row(cards))
            sec.add(self._kv_table([
                ["1-day VaR 95%", rc["var_95"]],
                ["Sharpe ratio", rc["sharpe"]],
                ["Max drawdown 52w", rc["max_drawdown_52w"]],
            ]))
            sec.add(W.make_label(rk["note"], 9, AMBER))
        self._fill_section("07", "CONTEXT_ONLY", _risk)

        # --- 08 Factor rankings (summary + availability + top/bottom composite) ---
        self._fill_section(
            "08", "AVAILABLE" if vm.factor_block(report)["status"] == "AVAILABLE" else "NOT_AVAILABLE",
            lambda s: s.add(self._factor_widget(report)))

        # --- 09 Earnings calendar ---
        e = vm.earnings_block(report)
        def _earnings(sec):
            sec.add(W.make_label(
                f"Earnings calendar NOT_AVAILABLE — {e['reason']}. "
                "Nova has no earnings source; no dates are shown.", 9, MUTED))
        self._fill_section("09", "NOT_AVAILABLE", _earnings)

        # --- 10 Guardrails ---
        g = vm.guardrails(report)
        def _guard(sec):
            sec.add(W.make_label(g["text"], 10, AMBER, True))
            sec.add(W.make_label(f"buy_sell_authorization: {g['buy_sell_authorization']}",
                                 10, GREEN, True, mono=True))
        self._fill_section("10", "ACTIVE", _guard)

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

        watch_row = QHBoxLayout()
        watch_row.addWidget(make_label("WATCHLIST", 9, MUTED, True))
        self.watch_input = QLineEdit()
        self.watch_input.setMinimumHeight(36)
        self.watch_input.setPlaceholderText(
            "RELIANCE, HDFCBANK, INFY … (comma-separated, max 10)"
        )
        watch_row.addWidget(self.watch_input, 1)
        self.watch_apply_btn = make_button("PIN", False)
        self.watch_apply_btn.clicked.connect(self.apply_watchlist)
        watch_row.addWidget(self.watch_apply_btn)
        controls_layout.addLayout(watch_row)

        self.watch_view = QPlainTextEdit()
        self.watch_view.setReadOnly(True)
        self.watch_view.setMinimumHeight(120)
        self.watch_view.setPlaceholderText(
            "Pinned symbols appear here with live price, RSI and trend. "
            "Refreshes on the auto cadence."
        )
        controls_layout.addWidget(self.watch_view)

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

    def build_backtest_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        controls, controls_layout = make_panel(
            "Factor backtest",
            "Ranks the universe by the existing technical composite score "
            "and compares the top vs bottom deciles. Analysis only.",
        )

        symbol_row = QHBoxLayout()
        symbol_row.addWidget(make_label("SYMBOLS", 9, MUTED, True))
        self.backtest_input = QLineEdit()
        self.backtest_input.setMinimumHeight(36)
        self.backtest_input.setPlaceholderText(
            "blank = 20-symbol quick sample • or RELIANCE, TCS …"
        )
        symbol_row.addWidget(self.backtest_input, 1)
        self.backtest_btn = make_button("RUN BACKTEST", True)
        self.backtest_btn.clicked.connect(self.run_backtest_task)
        symbol_row.addWidget(self.backtest_btn)
        controls_layout.addLayout(symbol_row)
        layout.addWidget(controls)

        output, output_layout = make_panel(
            "Backtest result",
            "Up-day fraction is a hit-rate, not a return. Missing data is "
            "flagged, never treated as zero.",
        )
        self.backtest_view = QPlainTextEdit()
        self.backtest_view.setReadOnly(True)
        self.backtest_view.setPlaceholderText(
            "Run a backtest to see the decile spread."
        )
        output_layout.addWidget(self.backtest_view, 1)
        layout.addWidget(output, 1)

        return page

    def build_event_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        banner, banner_layout = make_panel(
            "Event risk",
            "Upcoming macro, holiday and policy events from the event-risk "
            "engine. Descriptive context only, not a signal.",
        )
        banner_row = QHBoxLayout()
        self.event_banner = make_label("UNKNOWN", 15, AMBER, True)
        banner_row.addWidget(self.event_banner)
        banner_row.addStretch()
        banner_layout.addLayout(banner_row)
        self.event_meta = make_label("No event-risk data yet.", 10, MUTED)
        banner_layout.addWidget(self.event_meta)
        layout.addWidget(banner)

        listing, listing_layout = make_panel(
            "Upcoming events",
            "Times in IST; countdown recomputed from each event's datetime.",
        )
        self.event_view = QPlainTextEdit()
        self.event_view.setReadOnly(True)
        self.event_view.setPlaceholderText(
            "Waiting for a market report with event-risk data…"
        )
        listing_layout.addWidget(self.event_view, 1)
        layout.addWidget(listing, 1)

        return page

    def render_event_risk(self, context):
        """Update the Event Risk page widgets from the report's context."""
        if not isinstance(context, dict) or not context:
            if hasattr(self, "event_banner"):
                self.event_banner.setText("EVENT RISK: NOT AVAILABLE")
                self.event_banner.setStyleSheet(
                    f"color:{MUTED}; background:transparent; border:none;"
                )
            if hasattr(self, "event_meta"):
                self.event_meta.setText(
                    "No event-risk context in this report."
                )
            if hasattr(self, "event_view"):
                self.event_view.setPlainText(format_event_risk(None))
            return

        overall = context.get("overall_risk", "UNKNOWN")
        if hasattr(self, "event_banner"):
            self.event_banner.setText(f"OVERALL EVENT RISK: {overall}")
            self.event_banner.setStyleSheet(
                f"color:{_risk_color(overall)};"
                "background:transparent; border:none;"
            )

        if hasattr(self, "event_meta"):
            count = context.get("upcoming_event_count")
            lookahead = context.get("lookahead_days")
            fresh = context.get("source_fresh")
            if fresh is True:
                source = "FRESH (within 24h)"
            elif fresh is False:
                source = "STALE (not re-verified within 24h)"
            else:
                source = "freshness unknown"
            meta = []
            if count is not None:
                meta.append(f"upcoming events: {count}")
            if lookahead is not None:
                meta.append(f"lookahead: {lookahead} days")
            meta.append(f"calendar source: {source}")
            self.event_meta.setText("  |  ".join(meta))

        if hasattr(self, "event_view"):
            self.event_view.setPlainText(format_event_risk(context))

    def run_backtest_task(self):
        if "backtest" in self.workers:
            return

        raw = self.backtest_input.text().strip().upper()
        symbols = [
            part.strip()
            for part in raw.replace(";", ",").split(",")
            if part.strip()
        ]

        # Import lazily so the heavy scanner/Yahoo dependencies never
        # block UI startup when the panel is unused.
        from analysis.backtest_harness import run_backtest

        if symbols:
            self.start_task(
                "backtest",
                run_backtest,
                symbols=symbols,
                quiet=True,
            )
        else:
            self.start_task(
                "backtest",
                run_backtest,
                sample=20,
                quiet=True,
            )

    def render_backtest(self, result):
        if not hasattr(self, "backtest_view"):
            return

        if not isinstance(result, dict):
            self.backtest_view.setPlainText(
                "Backtest returned an unexpected result."
            )
            return

        stats = result.get("decile_stats") or {}
        trend_counts = result.get("trend_counts") or {}

        lines = [
            f"Universe        : {result.get('universe')}",
            f"Completed       : {result.get('completed')}",
            f"Degraded        : {result.get('degraded')}",
            f"Errors          : {result.get('errors')}",
            f"Pack width      : {result.get('pack_width')}",
            f"Elapsed         : {result.get('elapsed_seconds')}s",
            f"Generated       : {result.get('generated_at')}",
            "",
            "DECILE UP-DAY FRACTION (hit-rate, NOT a return)",
            f"  Top decile    : {stats.get('top_decile_up_day_fraction')}",
            f"  Bottom decile : {stats.get('bottom_decile_up_day_fraction')}",
            f"  Spread        : {stats.get('spread_top_vs_bottom')}",
            f"  Mid decile    : {stats.get('mid_decile_up_day_fraction')}",
            "",
            "TREND MIX",
        ]

        if trend_counts:
            for key, count in trend_counts.items():
                lines.append(f"  {key}: {count}")
        else:
            lines.append("  (no symbols completed)")

        lines += ["", "TOP RANKED"]
        for entry in (result.get("symbols") or [])[:10]:
            lines.append(
                f"  {entry.get('symbol')}: score {entry.get('score')} "
                f"| trend {entry.get('trend')} "
                f"| rsi {entry.get('rsi')} "
                f"| up {entry.get('up_day_fraction')}"
            )

        lines += [
            "",
            "Analysis only: up-day fraction measures how often prices closed",
            "higher, not average return. This is not a buy/sell signal.",
        ]

        self.backtest_view.setPlainText("\n".join(lines))

    def switch_page(self, index):
        self.pages.setCurrentIndex(index)

        for i, button in enumerate(self.nav_buttons):
            button.setChecked(i == index)

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
        if self._shutting_down:
            return

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

        elif name == "backtest":
            self.backtest_btn.setEnabled(False)
            self.progress.setRange(0, 0)
            self.footer.setText("Factor backtest running in the background…")

        elif name == "stock_analysis":
            self.stock_analyze_btn.set_busy(True)
            self.footer.setText("Stock analysis running in the background…")

        worker.start()

    def task_finished(self, name, worker):
        self.workers.pop(name, None)

        if name == "report":
            self.refresh_btn.setEnabled(True)
            self.live_btn.setEnabled(True)
            self.progress.setRange(0, 100)

        elif name == "watchlist":
            self.watch_apply_btn.setEnabled(True)
            # Rotate to the next symbol on the following poll.
            self.poll_watchlist_symbol()

        elif name == "analysis":
            self.analyze_btn.setEnabled(True)

        elif name == "backtest":
            self.backtest_btn.setEnabled(True)
            self.progress.setRange(0, 100)

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
            self.switch_page(3)  # Nova Analysis
            self.footer.setText(
                f"AI analysis returned in {elapsed:.2f}s. "
                "Validate conclusions against the report evidence."
            )

        elif name == "stock_analysis":
            self.render_stock_result(result if isinstance(result, dict) else {})
            self.stock_analyze_btn.set_busy(False)
            self.stock_status.setText(
                f"Analysis complete in {elapsed:.2f}s.")
            self.stock_status.setStyleSheet(f"color:{GREEN};")
            self.footer.setText(
                "Stock analysis complete. Validate against the evidence shown.")

        elif name == "watchlist":
            if isinstance(result, dict):
                symbol = str(result.get("symbol") or "").upper()
                if symbol:
                    self.watch_data[symbol] = result
                    self.render_watchlist()

        elif name == "backtest":
            self.render_backtest(result)
            self.switch_page(4)  # Factor Backtest
            self.footer.setText(
                f"Backtest completed in {elapsed:.2f}s. "
                "Up-day fraction is a hit-rate, not a return."
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
        elif name == "backtest":
            self.status_data.setText("BACKTEST ERROR")
            self.status_data.setStyleSheet(f"color:{RED};")
            self.backtest_view.setPlainText(
                f"Backtest failed after {elapsed:.1f}s.\n\n{error}"
            )
            self.footer.setText(
                f"Backtest failed after {elapsed:.1f}s. "
                "See the terminal output for details."
            )
        elif name == "stock_analysis":
            self.stock_analyze_btn.set_busy(False)
            self.stock_status.setText(
                f"Stock analysis failed after {elapsed:.1f}s: {error}")
            self.stock_status.setStyleSheet(f"color:{RED};")
            self.footer.setText(
                "Stock analysis failed. No conclusion produced; nothing fabricated.")
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
        generated = find_value(
            report,
            ("generated", "generated_at", "report_time", "timestamp"),
        )
        self.report_generated_at = generated
        self.last_display_at = time.time()

        market = find_value(report, ("market", "market_name"))

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

        # Dedicated Event Risk page + overview banner.
        self.render_event_risk(event_context)

        # --- Terminal panels: dashboard, 10-section workspace, sector, factors ---
        try:
            self.render_dashboard(report)
        except Exception as exc:
            self._render_failure("dashboard", exc)
        try:
            self.render_report_sections(report)
        except Exception as exc:
            self._render_failure("report", exc)
        try:
            self.render_sector(report)
        except Exception as exc:
            self._render_failure("sector", exc)
        try:
            self.render_uptrend(report)
        except Exception as exc:
            self._render_failure("uptrend", exc)

        if hasattr(self, "guardrails"):
            dmc = report.get("decision_policy") or {}
            self.guardrails.set_authorized(
                bool(dmc.get("buy_sell_authorized") is True)
            )
            self.guardrails.set_ops(
                f"scanner: {report.get('stocks_analyzed', 'N/A')} • "
                f"mode: cache-first • updated {datetime.now().strftime('%H:%M:%S')}"
            )

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
    # Tier 2 (60 s open / 30 s closed): live-only worker poll.
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

    def ensure_display_ticker(self):
        if getattr(self, "display_timer", None) is None:
            self.display_timer = QTimer(self)
            self.display_timer.setInterval(AUTO_CLOCK_MS)
            self.display_timer.timeout.connect(self.tick_display)
        if not self.display_timer.isActive():
            self.display_timer.start()
        self.tick_display()

    def tick_display(self):
        """Repaint every visible time-derived label from memory (1 s)."""
        from datetime import timezone as _tz, timedelta as _td

        ist = _tz(_td(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        clock = now_ist.strftime("%H:%M:%S")
        session_open = nse_market_open_now(now_ist)
        session = "NSE OPEN" if session_open else "NSE CLOSED"

        if self.last_update_at is not None:
            data_age = display_age(max(0, time.time() - self.last_update_at))
        elif self.report_generated_at is not None:
            data_age = f"report {self.report_generated_at}"
        else:
            data_age = "waiting for first report…"

        if self.auto_enabled and self.next_poll_at is not None:
            remaining = int(self.next_poll_at - time.time())
            if "report" in self.workers:
                poll = "updating now…"
            elif remaining > 0:
                poll = f"next update in {remaining}s"
            else:
                poll = "poll due…"
        elif "report" in self.workers:
            poll = "updating now…"
        else:
            poll = "AUTO OFF • data polls paused"

        if hasattr(self, "clock_label"):
            self.clock_label.setText(
                f"{clock}  •  {session}  •  {data_age}  •  {poll}"
            )
        if hasattr(self, "live_clock_value"):
            self.live_clock_value.setText(clock)
            self.live_session_value.setText(session)
            self.live_session_value.setStyleSheet(
                f"color:{GREEN if session_open else AMBER};"
                "background:transparent;border:none;"
            )
            self.live_age_value.setText(data_age)
            self.live_next_value.setText(poll)

        if hasattr(self, "metric_time") and self.metric_time is not None:
            if self.report_generated_at is not None:
                self.metric_time.setText(str(self.report_generated_at))

        # Keep the header session badge + data-age live (uses the report's own
        # backend timestamp; no network, reuses the last report in memory).
        if getattr(self, "report", None) is not None and hasattr(self, "scan_age_badge"):
            try:
                self.update_header(self.report)
            except Exception:
                pass

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
        # The 1 s display ticker owns label repaints; keep the auto
        # tick to poll scheduling only.
        self.tick_display()

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
    # STOCK WATCHLIST (same auto cadence, one symbol per poll)
    # --------------------------------------------------------

    def apply_watchlist(self):
        from analysis.data.watchlist_engine import MAX_SYMBOLS

        raw = self.watch_input.text().strip().upper()
        symbols = [
            part.strip()
            for part in raw.replace(";", ",").split(",")
            if part.strip()
        ]
        seen = []
        for symbol in symbols:
            if symbol not in seen:
                seen.append(symbol)
        self.watch_symbols = seen[:MAX_SYMBOLS]
        self.watch_index = 0
        self.watch_data = {}
        self.render_watchlist()
        if self.watch_symbols:
            self.footer.setText(
                f"Watchlist pinned: {', '.join(self.watch_symbols)}. "
                "Refreshes one symbol per auto poll."
            )
            # Refresh the first symbol immediately in the worker.
            self.poll_watchlist_symbol()

    def poll_watchlist_symbol(self):
        symbols = getattr(self, "watch_symbols", [])
        if not symbols or "watchlist" in self.workers:
            return
        from analysis.data.watchlist_engine import refresh_watch_symbol

        index = getattr(self, "watch_index", 0) % len(symbols)
        symbol = symbols[index]
        self.watch_index = index + 1
        self.start_task("watchlist", refresh_watch_symbol, symbol)

    def render_watchlist(self):
        if not hasattr(self, "watch_view"):
            return
        symbols = getattr(self, "watch_symbols", [])
        if not symbols:
            self.watch_view.setPlainText("")
            return
        from analysis.data.watchlist_engine import format_watchlist_line

        data = getattr(self, "watch_data", {})
        lines = [
            format_watchlist_line(data.get(symbol), symbol)
            for symbol in symbols
        ]
        self.watch_view.setPlainText("\n".join(lines))

    # --------------------------------------------------------
    # SAFE WINDOW CLOSE
    # --------------------------------------------------------

    def closeEvent(self, event):
        # ------------------------------------------------------------------
        # Clean shutdown.
        #
        # Workers run the market/MCP calls synchronously inside a QThread.
        # When Worker.run() returns, the nse_feed stdio_client context exits
        # and terminates the indian-market-mcp.exe subprocess it spawned, so
        # letting a running worker finish prevents orphaned MCP servers.
        # Blocking here (briefly) replaces the old "a background task is
        # running" refusal that could leave the MCP server orphaned when the
        # user force-closed the window.
        # ------------------------------------------------------------------

        self._shutting_down = True
        self.auto_enabled = False
        self.next_poll_at = None

        # Stop the auto-refresh clock and the 1s display ticker so nothing
        # new can be scheduled (the watchlist chains itself off task_succeeded
        # via start_task, which the _shutting_down guard now also blocks).
        for timer_attr in ("auto_timer", "display_timer"):
            timer = getattr(self, timer_attr, None)
            if timer is not None:
                timer.stop()

        running = [w for w in self.workers.values() if w.isRunning()]

        for worker in running:
            # Wait for the live MCP/network call to finish and its subprocess
            # to be torn down. Only if it overstays the grace period do we
            # force-terminate as a last resort so the window can always close.
            if not worker.wait(CLOSE_WORKER_WAIT_MS):
                worker.terminate()
                worker.wait(3000)

        self.workers.clear()
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