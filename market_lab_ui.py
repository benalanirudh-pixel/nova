from __future__ import annotations

import json
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QColor, QFont
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
    QScrollArea,
    QSizePolicy,
    QSplitter,
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
from market_lab import view_model as vm
from market_lab import widgets as W


# ============================================================
# NOVA MARKET LAB
# ============================================================

APP_NAME = "NOVA MARKET LAB"

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
            ("Dashboard", self.build_overview),
            ("Market Report", self.build_report_page),
            ("Nova Analysis", self.build_analysis_page),
            ("Factor Backtest", self.build_backtest_page),
            ("Event Risk", self.build_event_page),
        ]

        for index, (title, builder) in enumerate(specs):
            nav = make_button(f"{index + 1:02d}   {title}", index == 0)
            nav.clicked.connect(
                lambda checked=False, i=index: self.switch_page(i)
            )
            rail_layout.addWidget(nav)
            self.nav_buttons.append(nav)
            self.pages.addWidget(builder())

        rail_layout.addStretch()
        rail_layout.addWidget(make_label("SYSTEM MODE", 9, MUTED, True))
        rail_layout.addWidget(make_label("READ-ONLY", 12, GREEN, True))
        rail_layout.addWidget(make_label(
            "No broker connection\n"
            "No order placement\n"
            "No automatic execution",
            9, MUTED,
        ))
        left_layout.addWidget(rail)

        # Sector overview beneath the rail (real sector data only).
        self.sector_panel = self.build_sector_panel()
        left_layout.addWidget(self.sector_panel, 1)

        body.addWidget(left)
        body.addWidget(self.pages)

        self.factor_panel = self.build_factor_panel()
        body.addWidget(self.factor_panel)

        body.setStretchFactor(0, 0)
        body.setStretchFactor(1, 1)
        body.setStretchFactor(2, 0)
        body.setSizes([260, 1160, 380])
        left.setMinimumWidth(230)
        left.setMaximumWidth(280)
        self.factor_panel.setMinimumWidth(320)
        self.factor_panel.setMaximumWidth(420)
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
        self.symbol_search.setPlaceholderText("Symbol search (e.g. RELIANCE)")
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
        self.switch_page(2)
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
        self_price_row = QHBoxLayout()
        price = W.make_label("—", 28, TEXT, bold=True, mono=True)
        change = W.make_label("—", 15, MUTED, bold=True, mono=True)
        self_price_row.addWidget(price)
        self_price_row.addWidget(change)
        self_price_row.addStretch()
        layout.addLayout(self_price_row)
        meta = W.make_label("—", 9, MUTED)
        layout.addWidget(meta)
        snapshot = W.SnapshotBar()
        layout.addWidget(snapshot)
        ohlc = W.make_label("O —  H —  L —  C —", 10, TEXT, mono=True)
        layout.addWidget(ohlc)
        returns = W.make_label("5d —  |  20d —  |  60d —", 9, MUTED, mono=True)
        layout.addWidget(returns)
        return {
            "frame": frame, "price": price, "change": change, "meta": meta,
            "snapshot": snapshot, "ohlc": ohlc, "returns": returns,
        }

    def _indicator_card(self, name):
        frame, layout = W.panel(name, "")
        value = W.make_label("—", 18, TEXT, bold=True, mono=True)
        interp = W.make_label("—", 9, MUTED)
        layout.addWidget(value)
        layout.addWidget(interp)
        return {"frame": frame, "value": value, "interp": interp}

    # --------------------------------------------------------
    # PAGES
    # --------------------------------------------------------

    def build_overview(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(12)

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
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

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

    def build_factor_panel(self):
        frame, layout = W.panel(
            "Factor rankings",
            "Cross-sectional equal-weight z-score (research_factor_engine). "
            "Ranks are analysis inputs, not buy/sell signals.",
        )
        self.factor_meta = W.make_label("Loading factor rankings…", 9, MUTED)
        layout.addWidget(self.factor_meta)

        self.factor_avail = W.make_table(["Factor", "Availability"], stretch_column=0)
        layout.addWidget(self.factor_avail)

        layout.addWidget(W.make_label("TOP 10 (composite z)", 9, MUTED, True))
        self.factor_top_table = W.make_table(
            ["Rank", "Symbol", "Composite Z", "Price"],
            stretch_column=1,
        )
        layout.addWidget(self.factor_top_table)
        layout.addStretch()
        return frame

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
            # Real OHLC snapshot (NIFTY); BANK NIFTY has no OHLC -> honest
            # "chart unavailable" state (never synthetic candles).
            if all(isinstance(x, (int, float))
                   for x in (card["open"], card["high"], card["low"], card["price"])):
                c["snapshot"].set_snapshot(
                    card["open"], card["high"], card["low"], card["price"]
                )
            else:
                c["snapshot"].set_unavailable()
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

    def render_factor(self, report):
        fb = vm.factor_block(report)
        self.factor_meta.setText(
            f"method: {fb['method']}  •  universe: {fb['universe_size']}  •  "
            f"as of: {fb['as_of']}"
        )
        # Factor availability (QUALITY/VALUE genuinely not computed).
        avail_rows = []
        for factor in fb["factors_available"]:
            avail_rows.append([factor, "AVAILABLE (z populated: "
                              + ("yes" if fb["per_factor_z_available"] else "no") + ")"] )
        for factor, reason in fb["factors_unavailable"].items():
            avail_rows.append([factor, "NOT_AVAILABLE"])
        W.fill_table(self.factor_avail, avail_rows)
        # Color availability: green available, muted unavailable (text carries it).
        for r in range(self.factor_avail.rowCount()):
            cell = self.factor_avail.item(r, 1)
            if cell is None:
                continue
            if cell.text().startswith("NOT_AVAILABLE"):
                cell.setForeground(QColor(MUTED))
            else:
                cell.setForeground(QColor(GREEN))

        # Top 10 by composite z (the real ranking output).
        top_rows = []
        for r in fb["top"]:
            top_rows.append([
                r["rank"], r["symbol"], fmt_num(r["composite_z"], 3),
                fmt_price(r["price"]),
            ])
        if not top_rows:
            top_rows = []
        W.fill_table(self.factor_top_table, top_rows)
        # Right-align the numeric columns for a quant-terminal feel.
        for r in range(self.factor_top_table.rowCount()):
            for col in (0, 2, 3):
                cell = self.factor_top_table.item(r, col)
                if cell is not None:
                    cell.setTextAlignment(
                        Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
                    )

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
        # --- 01 Macro ---
        macro = vm.macro(report)
        self._fill_section("01", "AVAILABLE", lambda s: s.add(self._kv_table([
            ["Market regime", macro["market_regime"]],
            ["NIFTY level", fmt_price(macro["nifty_price"])],
            ["India VIX", fmt_num(macro["india_vix"])],
            ["VIX regime", macro["vix_regime"]],
            ["VIX change %", fmt_pct(macro["vix_change_percent"])],
            ["VIX 1y percentile", fmt_num(macro["vix_percentile_1y"], 1)],
        ])))

        # --- 02 Breadth ---
        b = vm.breadth_block(report)
        self._fill_section("02", "AVAILABLE", lambda s: s.add(self._kv_table([
            ["Advances", b["advancing"]],
            ["Declines", b["declining"]],
            ["A/D ratio", fmt_num(b["ad_ratio"])],
            ["% above EMA200", fmt_pct(b["above_ema200_percent"], signed=False)],
            ["New 52w highs", b["new_52w_highs"]],
            ["New 52w lows", b["new_52w_lows"]],
            ["McClellan Summation", b["mcclellan_summation"]],
        ])))

        # --- 03 Sector ---
        sectors = vm.sector_rows(report, limit=20)
        self._fill_section("03", "AVAILABLE" if sectors else "NOT_AVAILABLE",
            lambda s: s.add(self._list_table(
                ["Sector", "20D %", "RS 20D", "Regime"],
                [[r["name"], fmt_pct(r["return_20d"]),
                  fmt_num(r["relative_strength_20d"], 1), r["regime"]] for r in sectors],
                stretch=0)))

        # --- 04 Technical ---
        t = vm.technical_block(report)
        def _technical(sec):
            sec.add(self._list_table(
                ["Rank", "Symbol", "Score", "Trend"],
                [[r["rank"], r["symbol"], fmt_num(r["technical_score"], 1), r["trend"]]
                 for r in t["top_stocks"]]))
            sec.add(W.make_label(
                f"RSI oversold {t['rsi_oversold']} • RSI overbought {t['rsi_overbought']} • "
                f"MACD crossovers {t['macd_crossovers']} • support/resistance {t['support_resistance']}",
                9, MUTED))
        self._fill_section("04", "PARTIAL", _technical)

        # --- 05 Derivatives ---
        def _deriv(sec):
            for which, label in (("nifty", "NIFTY"), ("bank_nifty", "BANK NIFTY")):
                d = vm.derivatives_block(report, which)
                if not d.get("available"):
                    sec.add(W.make_label(f"{label}: derivatives N/A", 10, MUTED))
                    continue
                sec.add(self._kv_table([
                    [f"{label} spot", fmt_price(d["spot"])],
                    [f"{label} expiry", d["expiry"]],
                    [f"{label} OI PCR", fmt_num(d["oi_pcr"], 3)],
                    [f"{label} volume PCR", fmt_num(d["volume_pcr"], 3)],
                    [f"{label} max pain", fmt_points(d["max_pain"])],
                    [f"{label} put/call wall", f"{d['put_wall']} / {d['call_wall']}"],
                    [f"{label} ATM IV", fmt_num(d["atm_iv"])],
                    [f"{label} top OI-build stocks", d["stock_oi_buildup_list"]],
                ], value_field="Value"))
        self._fill_section("05", "AVAILABLE", _deriv)

        # --- 06 Institutional flow ---
        f = vm.flow_block(report)
        def _flow(sec):
            coverage = (f"{f['primary_verified']}/{f['target_sessions']} sessions verified"
                        if f.get("primary_verified") is not None else vm.N_A)
            sec.add(self._kv_table([
                ["Flow regime", f["flow_regime"]],
                ["FII net 20D (cr)", fmt_crore(f["fii_20d"])],
                ["DII net 20D (cr)", fmt_crore(f["dii_20d"])],
                ["FII net 5D (cr)", fmt_crore(f["fii_5d"])],
                ["DII net 5D (cr)", fmt_crore(f["dii_5d"])],
                ["Primary coverage", coverage],
                ["Signal eligible", ("YES" if f["signal_allowed"] else f"NO — {f['signal_reason']}")],
            ]))
        self._fill_section("06", "AVAILABLE" if f["available"] else "NOT_AVAILABLE", _flow)

        # --- 07 Risk metrics ---
        rk = vm.risk_block(report)
        def _risk(sec):
            provided = rk["provided"]
            sec.add(self._kv_table([
                ["1-day VaR 95%", rk["var_95"]],
                ["Sharpe ratio", rk["sharpe"]],
                ["Max drawdown 52w", rk["max_drawdown_52w"]],
                ["Current drawdown", rk["current_drawdown"]],
                ["NIFTY ATR %", fmt_num(provided["atr_pct"])],
                ["NIFTY realized vol 20D", fmt_num(provided["realized_volatility_20d"]) + "%"],
                ["Volatility percentile", fmt_num(provided["volatility_percentile"], 1)],
                ["Volatility regime", provided["volatility_regime"]],
            ]))
            sec.add(W.make_label(rk["note"], 9, MUTED))
        self._fill_section("07", "CONTEXT_ONLY", _risk)

        # --- 08 Factor rankings ---
        fb2 = vm.factor_block(report)
        def _factor(sec):
            sec.add(W.make_label(
                f"method: {fb2['method']} • universe: {fb2['universe_size']} • "
                f"as of: {fb2['as_of']}", 9, MUTED))
            sec.add(self._list_table(
                ["Rank", "Symbol", "Composite Z", "Price"],
                [[r["rank"], r["symbol"], fmt_num(r["composite_z"], 3), fmt_price(r["price"])]
                 for r in fb2["top"]]))
            for factor, reason in fb2["factors_unavailable"].items():
                sec.add(W.make_label(f"{factor}: NOT_AVAILABLE — {reason}", 9, MUTED))
        self._fill_section("08", "AVAILABLE" if fb2["status"] == "AVAILABLE" else "NOT_AVAILABLE", _factor)

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
            self.switch_page(2)
            self.footer.setText(
                f"AI analysis returned in {elapsed:.2f}s. "
                "Validate conclusions against the report evidence."
            )

        elif name == "watchlist":
            if isinstance(result, dict):
                symbol = str(result.get("symbol") or "").upper()
                if symbol:
                    self.watch_data[symbol] = result
                    self.render_watchlist()

        elif name == "backtest":
            self.render_backtest(result)
            self.switch_page(3)
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
            self.render_factor(report)
        except Exception as exc:
            self._render_failure("factors", exc)

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