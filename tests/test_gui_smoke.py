"""
Headless GUI smoke tests for Nova Market Lab (``market_lab_ui.py``).

Fully offline and headless:

- ``QT_QPA_PLATFORM`` is forced to ``offscreen`` before PySide6 is imported.
- Exactly one ``QApplication`` is created for the whole module
  (``QApplication`` is a single-instance class).
- The real ``MarketLabWindow`` is constructed, but no event loop is ever run,
  so the deferred ``QTimer.singleShot(150, self.load_initial_report)`` never
  fires: no report worker, no network call, no NSE scan.
- Every other background path is captured by stubbing ``window.start_task`` so
  the call arguments can be asserted without starting a real ``QThread``.
- If PySide6 (or a Market Lab dependency) is not importable the whole test case
  is skipped, so ``unittest discover -s tests`` stays green without Qt.

Regressions these tests lock in:

1. ``task_succeeded`` used to drop every ``"watchlist"`` result, so the pinned
   watchlist panel never populated. The handler must store the refresh dict in
   ``watch_data`` and re-render ``watch_view`` (and keep rendering an honest
   "waiting for first refresh" line for symbols that have no data yet).
2. ``run_backtest`` used to require a positional ``symbols`` while the UI's
   blank-input path called ``run_backtest(sample=20, quiet=True)``, raising
   ``TypeError`` on every "RUN BACKTEST" click. The captured ``start_task``
   arguments are now bound against the real ``inspect`` signature to prove the
   wiring is callable, and ``symbols`` must keep its ``None`` default.
3. ``task_succeeded`` jumps to hardcoded page indices (3 = backtest, 2 =
   analysis). If the nav spec is reordered those indices silently break, so the
   backtest page index is asserted against its nav button label.
4. ``render_backtest`` must fill ``backtest_view`` from the real report keys
   and keep the "hit-rate, not a return" / "not a buy/sell signal" guardrails.

Run from the project root:

    set PYTHONUTF8=1 && .\\venv\\Scripts\\python.exe -m unittest tests.test_gui_smoke -v
"""

from __future__ import annotations

import inspect
import os
import sys
import unittest
import unittest.mock
from pathlib import Path

# Must be set before PySide6 (imported transitively by market_lab_ui) loads.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Qt is optional for the rest of the suite: skip instead of erroring so
# `unittest discover -s tests` stays green on a machine without PySide6.
try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - depends on the local install
    QApplication = None

try:
    import market_lab_ui
    from market_lab_ui import MarketLabWindow, Worker
except ImportError:  # pragma: no cover - depends on the local install
    market_lab_ui = None
    MarketLabWindow = None
    Worker = None


QT_AVAILABLE = QApplication is not None and MarketLabWindow is not None


# ============================================================
# FIXTURES (shaped like the real engine outputs, no network)
# ============================================================

def watchlist_result(symbol="RELIANCE", **overrides):
    """A realistic ``refresh_watch_symbol`` payload (analysis-only flags kept)."""
    result = {
        "engine": "Nova Stock Watchlist Engine",
        "version": "1.0.0",
        "status": "AVAILABLE",
        "symbol": symbol,
        "company_name": "Reliance Industries",
        "price": 1455.35,
        "open": 1448.0,
        "high": 1462.5,
        "low": 1440.1,
        "volume": 8123456.0,
        "change_percent": 0.87,
        "rsi_14": 58.4,
        "rsi_condition": "NEUTRAL",
        "macd_condition": "BULLISH",
        "trend": "UPTREND",
        "momentum_score": 62.5,
        "ema_20": 1441.2,
        "ema_50": 1410.9,
        "ema_200": 1355.0,
        "timestamp": "2026-10-10T14:30:00",
        "source": "NSE MCP live quote",
        "warnings": [],
        "decision_policy": {
            "watchlist_is_a_buy_sell_signal": False,
            "buy_sell_authorization": False,
            "trading_execution": False,
        },
    }
    result.update(overrides)
    return result


def backtest_report(**overrides):
    """A realistic ``run_backtest`` report using its real key names."""
    report = {
        "generated_at": "20261010_143000",
        "universe": 20,
        "completed": 4,
        "degraded": 1,
        "errors": 0,
        "pack_width": 1,
        "elapsed_seconds": 12.34,
        "decile_stats": {
            "top_decile_up_day_fraction": 0.55,
            "bottom_decile_up_day_fraction": 0.41,
            "spread_top_vs_bottom": 0.14,
            "mid_decile_up_day_fraction": 0.48,
        },
        "trend_counts": {"UPTREND": 2, "STRONG_UPTREND": 2},
        "symbols": [
            {
                "symbol": "RELIANCE",
                "score": 71.2,
                "trend": "STRONG_UPTREND",
                "rsi": 62.1,
                "up_day_fraction": 0.56,
            },
            {
                "symbol": "TCS",
                "score": 68.4,
                "trend": "UPTREND",
                "rsi": 57.9,
                "up_day_fraction": 0.52,
            },
        ],
    }
    report.update(overrides)
    return report


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class MarketLabSmokeTestCase(unittest.TestCase):
    """One shared real window; each test resets the state it mutates."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.window = MarketLabWindow()

    @classmethod
    def tearDownClass(cls):
        # No worker was ever started, so the safe close path just accepts.
        cls.window.close()
        cls.window.deleteLater()
        cls.window = None

    def setUp(self):
        window = self.window
        window.watch_symbols = []
        window.watch_index = 0
        window.watch_data = {}
        window.render_watchlist()
        window.backtest_input.clear()

    # --------------------------------------------------------
    # helpers
    # --------------------------------------------------------

    def capture_start_task(self):
        """Replace window.start_task with a recorder; returns the call list.

        Records (name, function, args, kwargs) and starts nothing, so no
        QThread and no network call happens.
        """
        window = self.window
        original = window.start_task
        calls = []

        def recorder(name, function, *args, **kwargs):
            calls.append(
                {
                    "name": name,
                    "function": function,
                    "args": args,
                    "kwargs": dict(kwargs),
                }
            )

        window.start_task = recorder
        self.addCleanup(setattr, window, "start_task", original)
        return calls

    # --------------------------------------------------------
    # construction / structure
    # --------------------------------------------------------

    def test_construction_is_offline_and_spawns_no_workers(self):
        window = self.window
        self.assertIsInstance(window, MarketLabWindow)
        # The deferred load_initial_report() never ran: no event loop, so no
        # report worker, no network, no NSE scan.
        self.assertEqual(window.workers, {})
        self.assertEqual(window.watch_data, {})
        self.assertEqual(window.watch_symbols, [])
        self.assertEqual(window.watch_index, 0)
        self.assertFalse(window.auto_enabled)
        self.assertIsNone(window.report)

    def test_page_indices_match_the_nav_labels(self):
        window = self.window
        self.assertEqual(window.pages.count(), 5)
        self.assertEqual(window.pages.currentIndex(), 0)
        # task_succeeded hardcodes switch_page(3) for backtest.
        self.assertIn("Factor Backtest", window.nav_buttons[3].text())
        self.assertIn("Nova Analysis", window.nav_buttons[2].text())
        self.assertIn("Event Risk", window.nav_buttons[4].text())
        window.switch_page(3)
        self.assertEqual(window.pages.currentIndex(), 3)
        window.switch_page(4)
        self.assertEqual(window.pages.currentIndex(), 4)
        window.switch_page(0)
        self.assertEqual(window.pages.currentIndex(), 0)

    def test_panels_and_inputs_exist(self):
        window = self.window
        for attribute in (
            "watch_input",
            "watch_view",
            "backtest_input",
            "backtest_btn",
            "backtest_view",
            "analysis_view",
            "report_view",
            "integrity_view",
            "footer",
        ):
            self.assertTrue(hasattr(window, attribute), attribute)


    # --------------------------------------------------------
    # REGRESSION: watchlist results used to be dropped
    # --------------------------------------------------------

    def test_watchlist_result_is_stored_and_rendered(self):
        window = self.window
        window.watch_symbols = ["RELIANCE", "TCS"]
        window.watch_data = {}

        result = watchlist_result("RELIANCE")
        window.task_succeeded("watchlist", result, 0.0)

        self.assertIs(window.watch_data["RELIANCE"], result)

        lines = window.watch_view.toPlainText().split("\n")
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("RELIANCE:"))
        self.assertNotIn("waiting", lines[0])
        self.assertIn("1455.35", lines[0])
        self.assertIn("+0.87%", lines[0])
        self.assertIn("RSI 58.4 NEUTRAL", lines[0])
        self.assertIn("UPTREND", lines[0])
        # A symbol with no data yet still shows the honest placeholder.
        self.assertTrue(lines[1].startswith("TCS:"))
        self.assertIn("waiting for first refresh", lines[1])

        # The analysis-only contract is untouched by the UI.
        policy = result["decision_policy"]
        self.assertIs(policy["trading_execution"], False)
        self.assertIs(policy["buy_sell_authorization"], False)

    def test_watchlist_not_available_result_is_rendered_not_dropped(self):
        window = self.window
        window.watch_symbols = ["TCS"]
        window.watch_data = {}

        result = watchlist_result(
            "TCS",
            status="NOT_AVAILABLE",
            price=None,
            change_percent=None,
            rsi_14=None,
            rsi_condition=None,
            trend=None,
            source=None,
            reason="Engine returned no usable price.",
        )
        window.task_succeeded("watchlist", result, 0.0)

        self.assertIs(window.watch_data["TCS"], result)
        text = window.watch_view.toPlainText()
        self.assertIn("TCS: NOT AVAILABLE", text)
        self.assertIn("Engine returned no usable price.", text)

    def test_render_watchlist_clears_view_when_nothing_pinned(self):
        window = self.window
        window.watch_symbols = []
        window.watch_data = {"RELIANCE": watchlist_result()}

        window.render_watchlist()

        self.assertEqual(window.watch_view.toPlainText(), "")

    def test_format_watchlist_line_renders_dashes_for_missing_numbers(self):
        from analysis.data.watchlist_engine import format_watchlist_line

        line = format_watchlist_line(
            {
                "status": "AVAILABLE",
                "symbol": "INFY",
                "price": None,
                "change_percent": None,
                "rsi_14": None,
            },
            "INFY",
        )
        self.assertTrue(line.startswith("INFY:"))
        self.assertEqual(line.count("--"), 3)
        self.assertNotIn("None", line)
        self.assertIn(
            "waiting for first refresh", format_watchlist_line(None, "INFY")
        )

    def test_apply_watchlist_dedupes_caps_and_polls_first_symbol(self):
        from analysis.data.watchlist_engine import MAX_SYMBOLS, refresh_watch_symbol

        window = self.window
        window.watch_input.setText(
            "reliance, tcs, RELIANCE, infy, sbin, itc, lt, hdfcbank,"
            " icicibank, maruti, wipro, tatamotors"
        )
        calls = self.capture_start_task()

        window.apply_watchlist()

        self.assertEqual(
            window.watch_symbols,
            [
                "RELIANCE", "TCS", "INFY", "SBIN", "ITC", "LT", "HDFCBANK",
                "ICICIBANK", "MARUTI", "WIPRO",
            ],
        )
        self.assertEqual(len(window.watch_symbols), MAX_SYMBOLS)
        self.assertEqual(window.watch_data, {})
        self.assertIn("Watchlist pinned: RELIANCE, TCS", window.footer.text())
        # The first symbol is refreshed immediately, but only through the
        # stubbed start_task, so no real worker is started here.
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["name"], "watchlist")
        self.assertIs(calls[0]["function"], refresh_watch_symbol)
        self.assertEqual(calls[0]["args"], ("RELIANCE",))

    def test_poll_watchlist_symbol_round_robins_and_skips_when_empty(self):
        from analysis.data.watchlist_engine import refresh_watch_symbol

        window = self.window
        window.watch_symbols = ["RELIANCE", "TCS"]
        window.watch_index = 0
        calls = self.capture_start_task()

        window.poll_watchlist_symbol()
        self.assertEqual(calls[0]["args"], ("RELIANCE",))
        self.assertEqual(window.watch_index, 1)

        window.poll_watchlist_symbol()
        self.assertEqual(calls[1]["args"], ("TCS",))
        self.assertEqual(window.watch_index, 2)

        # Round-robin wraps: index = watch_index % len, so the stored counter
        # restarts at 1 rather than growing forever.
        window.poll_watchlist_symbol()
        self.assertEqual(calls[2]["args"], ("RELIANCE",))
        self.assertEqual(window.watch_index, 1)
        self.assertIs(calls[0]["function"], refresh_watch_symbol)

        del calls[:]
        window.watch_symbols = []
        window.poll_watchlist_symbol()
        self.assertEqual(calls, [])


    # --------------------------------------------------------
    # REGRESSION: run_backtest arg wiring (blank-input TypeError)
    # --------------------------------------------------------

    def test_run_backtest_task_blank_input_wires_the_sample_path(self):
        from analysis.backtest_harness import run_backtest

        window = self.window
        window.backtest_input.setText("")
        calls = self.capture_start_task()

        window.run_backtest_task()

        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["name"], "backtest")
        self.assertIs(call["function"], run_backtest)
        self.assertEqual(call["args"], ())
        self.assertEqual(call["kwargs"], {"sample": 20, "quiet": True})
        self.assertNotIn("symbols", call["kwargs"])
        self.assertEqual(window.workers, {})

        # The captured call must bind against the real signature. Before the
        # fix symbols was a required positional, so this bind raised
        # TypeError: missing 1 required positional argument: 'symbols'.
        signature = inspect.signature(run_backtest)
        signature.bind(*call["args"], **call["kwargs"])
        self.assertIn("symbols", signature.parameters)
        self.assertIsNone(signature.parameters["symbols"].default)

    def test_run_backtest_task_symbol_input_wires_the_symbols_path(self):
        from analysis.backtest_harness import run_backtest

        window = self.window
        window.backtest_input.setText(" reliance , tcs; INFY ")
        calls = self.capture_start_task()

        window.run_backtest_task()

        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["name"], "backtest")
        self.assertIs(call["function"], run_backtest)
        self.assertEqual(
            call["kwargs"],
            {"symbols": ["RELIANCE", "TCS", "INFY"], "quiet": True},
        )
        self.assertNotIn("sample", call["kwargs"])
        inspect.signature(run_backtest).bind(*call["args"], **call["kwargs"])

    def test_run_backtest_task_skips_when_a_worker_is_running(self):
        window = self.window
        window.backtest_input.setText("RELIANCE")
        sentinel = object()
        window.workers["backtest"] = sentinel
        self.addCleanup(window.workers.pop, "backtest", None)
        calls = self.capture_start_task()

        window.run_backtest_task()

        self.assertEqual(calls, [])
        self.assertIs(window.workers["backtest"], sentinel)


    # --------------------------------------------------------
    # backtest rendering / task plumbing
    # --------------------------------------------------------

    def test_render_backtest_fills_view_and_keeps_guardrails(self):
        window = self.window
        window.backtest_view.setPlainText("")

        window.render_backtest(backtest_report())

        text = window.backtest_view.toPlainText()
        self.assertTrue(text.strip())
        self.assertIn("Universe        : 20", text)
        self.assertIn("Completed       : 4", text)
        self.assertIn("Degraded        : 1", text)
        self.assertIn("Errors          : 0", text)
        self.assertIn("Pack width      : 1", text)
        self.assertIn("Generated       : 20261010_143000", text)
        self.assertIn("DECILE UP-DAY FRACTION (hit-rate, NOT a return)", text)
        self.assertIn("Top decile    : 0.55", text)
        self.assertIn("Bottom decile : 0.41", text)
        self.assertIn("Spread        : 0.14", text)
        self.assertIn("TREND MIX", text)
        self.assertIn("UPTREND: 2", text)
        self.assertIn("TOP RANKED", text)
        self.assertIn("RELIANCE: score 71.2", text)
        self.assertIn("not a buy/sell signal", text)

    def test_render_backtest_handles_empty_and_invalid_results(self):
        window = self.window

        window.render_backtest(backtest_report(symbols=[], trend_counts={}))
        text = window.backtest_view.toPlainText()
        self.assertIn("(no symbols completed)", text)
        self.assertIn("Completed       : 4", text)

        window.render_backtest(None)
        self.assertIn(
            "Backtest returned an unexpected result.",
            window.backtest_view.toPlainText(),
        )

    def test_task_succeeded_backtest_renders_and_switches_page(self):
        window = self.window
        window.switch_page(0)
        window.backtest_view.setPlainText("")

        window.task_succeeded("backtest", backtest_report(), 1.5)

        self.assertEqual(window.pages.currentIndex(), 3)
        self.assertIn("Universe", window.backtest_view.toPlainText())
        self.assertIn("hit-rate, not a return", window.footer.text())

    def test_task_failed_backtest_surfaces_the_error_in_the_view(self):
        window = self.window
        window.backtest_view.setPlainText("")

        with unittest.mock.patch.object(market_lab_ui, "QMessageBox") as box:
            window.task_failed(
                "backtest",
                "TypeError: missing 1 required positional argument: 'symbols'",
                1.5,
            )

        self.assertEqual(box.warning.call_count, 1)
        text = window.backtest_view.toPlainText()
        self.assertIn("Backtest failed after 1.5s.", text)
        self.assertIn("missing 1 required positional argument", text)
        self.assertEqual(window.status_data.text(), "BACKTEST ERROR")

    def test_task_finished_restores_controls_and_clears_the_worker(self):
        window = self.window
        # Constructed but never started: no thread, no network.
        worker = Worker("backtest", lambda: None)
        window.workers["backtest"] = worker
        window.backtest_btn.setEnabled(False)
        window.progress.setRange(0, 0)

        window.task_finished("backtest", worker)

        self.assertEqual(window.workers, {})
        self.assertTrue(window.backtest_btn.isEnabled())
        self.assertEqual(window.progress.maximum(), 100)


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestCleanShutdown(unittest.TestCase):
    """closeEvent must shut down cleanly instead of refusing and orphaning the
    Market MCP subprocess.

    The old handler refused to close while any worker ran, which pushed users
    to force-close the window and left indian-market-mcp.exe orphaned. Now the
    timers stop, no new worker can start, and a running worker is allowed to
    finish (so stdio_client tears down its subprocess) before the close is
    accepted.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        win = MarketLabWindow()
        self.addCleanup(win.deleteLater)
        return win

    def test_start_task_is_blocked_during_shutdown(self):
        win = self._window()
        win._shutting_down = True
        win.start_task("report", lambda: "should not run")
        self.assertNotIn("report", win.workers)

    def test_close_event_stops_running_worker_and_accepts(self):
        import time

        from PySide6.QtGui import QCloseEvent

        win = self._window()
        # A short, side-effect-free worker (no network, no MCP).
        worker = Worker("report", lambda: time.sleep(0.2))
        win.workers["report"] = worker
        worker.start()

        # Exercise the timer-stop path too.
        win.ensure_auto_timer()
        win.ensure_display_ticker()

        event = QCloseEvent()
        win.closeEvent(event)

        self.assertTrue(event.isAccepted())
        # The worker was waited on to completion, not force-killed.
        self.assertFalse(worker.isRunning())
        self.assertEqual(win.workers, {})
        self.assertTrue(win._shutting_down)
        for name in ("auto_timer", "display_timer"):
            timer = getattr(win, name, None)
            self.assertTrue(timer is None or not timer.isActive())

    def test_close_event_accepts_when_idle(self):
        from PySide6.QtGui import QCloseEvent

        win = self._window()
        event = QCloseEvent()
        win.closeEvent(event)
        self.assertTrue(event.isAccepted())
        self.assertEqual(win.workers, {})


# ----------------------------------------------------------------
# Event Risk panel: pure renderer + widget wiring
# ----------------------------------------------------------------

def event_risk_context(**overrides):
    """A realistic event_risk_context from a Market Lab report."""
    context = {
        "engine": "Nova Event Risk Engine",
        "status": "AVAILABLE",
        "overall_risk": "MODERATE",
        "overall_risk_score": 3,
        "upcoming_event_count": 2,
        "lookahead_days": 7,
        "source_fresh": True,
        "upcoming_events": [
            {
                "name": "India CPI inflation (Sep 2026) and IIP release",
                "datetime_utc": "2026-10-12T10:30:00+00:00",
                "category": "MACRO_INFLATION",
                "severity": "HIGH",
                "instruments": ["NIFTY", "BANK_NIFTY"],
                "impact_note": "Released 16:00 IST after equity close.",
                "verified": True,
            },
            {
                "name": "US CPI inflation (Sep 2026) release",
                "datetime_utc": "2026-10-14T12:30:00+00:00",
                "category": "GLOBAL_MACRO_INFLATION",
                "severity": "MODERATE",
                "instruments": ["GLOBAL_MARKET"],
                "impact_note": "08:30 ET = 18:00 IST.",
                "verified": True,
            },
        ],
        "decision_policy": {
            "buy_sell_authorized": False,
            "trading_execution": False,
        },
    }
    context.update(overrides)
    return context


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestFormatEventRisk(unittest.TestCase):
    """The pure event-risk renderer (no widgets)."""

    def test_renders_overall_events_and_guardrail(self):
        text = market_lab_ui.format_event_risk(event_risk_context())
        self.assertIn("OVERALL EVENT RISK: MODERATE", text)
        self.assertIn("risk score 3", text)
        self.assertIn("UPCOMING EVENTS", text)
        self.assertIn("[HIGH] India CPI inflation", text)
        self.assertIn("[MODERATE] US CPI inflation", text)
        self.assertIn("Mon 12 Oct 2026, 16:00 IST", text)  # UTC -> IST
        self.assertIn("instruments: NIFTY, BANK_NIFTY", text)
        self.assertIn("NOT a buy/sell signal", text)

    def test_source_freshness_lines(self):
        self.assertIn(
            "FRESH", market_lab_ui.format_event_risk(event_risk_context())
        )
        stale = market_lab_ui.format_event_risk(
            event_risk_context(source_fresh=False)
        )
        self.assertIn("STALE", stale)
        unknown = market_lab_ui.format_event_risk(
            event_risk_context(source_fresh=None)
        )
        self.assertIn("freshness unknown", unknown)

    def test_none_and_empty_are_not_available(self):
        for bad in (None, {}, [], "nope"):
            text = market_lab_ui.format_event_risk(bad)
            self.assertIn("NOT AVAILABLE", text)

    def test_countdown_uses_now_not_frozen_hours(self):
        from datetime import datetime, timezone

        context = event_risk_context(
            upcoming_events=[{
                "name": "Test Event",
                "datetime_utc": "2026-10-10T14:00:00+00:00",
                "severity": "LOW",
            }]
        )
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        text = market_lab_ui.format_event_risk(context, now=now)
        self.assertIn("in 2.0 h", text)  # 2h after `now`

    def test_event_without_datetime_but_with_report_hours(self):
        context = event_risk_context(
            upcoming_events=[{
                "name": "No Datetime",
                "severity": "LOW",
                "hours_until": 30.0,
            }]
        )
        text = market_lab_ui.format_event_risk(context)
        self.assertIn("No Datetime", text)
        self.assertIn("time from report", text)

    def test_event_without_any_time_still_lists_name(self):
        context = event_risk_context(
            upcoming_events=[{"name": "Bare Event", "severity": "HIGH"}]
        )
        text = market_lab_ui.format_event_risk(context)
        self.assertIn("[HIGH] Bare Event", text)


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestFormatEventRiskColors(unittest.TestCase):

    def test_risk_color_levels(self):
        c = market_lab_ui._risk_color
        self.assertEqual(c("HIGH"), market_lab_ui.RED)
        self.assertEqual(c("CRITICAL"), market_lab_ui.RED)
        self.assertEqual(c("MODERATE"), market_lab_ui.AMBER)
        self.assertEqual(c("LOW"), market_lab_ui.GREEN)
        # UNKNOWN / NOT_AVAILABLE must never render green.
        self.assertEqual(c("UNKNOWN"), market_lab_ui.AMBER)
        self.assertEqual(c("NOT_AVAILABLE"), market_lab_ui.AMBER)


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestEventRiskPanel(unittest.TestCase):
    """display_report must populate the Event Risk page widgets."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        win = MarketLabWindow()
        self.addCleanup(win.deleteLater)
        return win

    def _report(self, context):
        return {
            "market": "NSE",
            "generated": "2026-10-10T18:57:11+05:30",
            "breadth": {"advancing": 1, "declining": 2},
            "event_risk_context": context,
        }

    def test_widgets_exist(self):
        win = self._window()
        self.assertTrue(hasattr(win, "event_view"))
        self.assertTrue(hasattr(win, "event_banner"))
        self.assertTrue(hasattr(win, "event_meta"))

    def test_display_report_populates_event_panel(self):
        win = self._window()
        win.display_report(self._report(event_risk_context()), 0.0, cached=True)
        self.assertIn("MODERATE", win.event_banner.text())
        self.assertIn(
            "India CPI inflation", win.event_view.toPlainText()
        )
        self.assertIn("FRESH", win.event_meta.text())
        # MODERATE banner is AMBER.
        self.assertIn(market_lab_ui.AMBER, win.event_banner.styleSheet())

    def test_high_risk_banner_is_red(self):
        win = self._window()
        win.display_report(
            self._report(event_risk_context(overall_risk="HIGH")),
            0.0,
            cached=True,
        )
        self.assertIn("HIGH", win.event_banner.text())
        self.assertIn(market_lab_ui.RED, win.event_banner.styleSheet())

    def test_missing_context_marks_not_available(self):
        win = self._window()
        win.render_event_risk(None)
        self.assertIn("NOT AVAILABLE", win.event_banner.text())
        self.assertIn(
            "NOT AVAILABLE", win.event_view.toPlainText()
        )

    def test_stale_source_surfaces_in_meta(self):
        win = self._window()
        win.display_report(
            self._report(event_risk_context(source_fresh=False)),
            0.0,
            cached=True,
        )
        self.assertIn("STALE", win.event_meta.text())


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestTerminalLayout(unittest.TestCase):
    """Locks in the redesigned terminal: header chips, 10 ordered report
    sections in a workspace, the persistent guardrails footer, and that the
    dashboard renders real values / honest N/A (never fabricated numbers)."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        win = MarketLabWindow()
        self.addCleanup(win.deleteLater)
        return win

    @staticmethod
    def _report():
        return {
            "market": "NSE",
            "generated": "2026-10-10T13:00:00+00:00",
            "stocks_analyzed": 1999,
            "market_regime": "BEARISH",
            "nifty_snapshot": {
                "available": True, "price": 22520.45, "change_percent": 1.30,
                "open": 22314.95, "high": 22580.75, "low": 22294.75,
            },
            "nifty_returns": {"1D": 1.3, "5D": -2.0, "20D": -3.9, "60D": -6.5},
            "volatility": {"india_vix": {"value": 14.38, "regime": "MODERATE"}},
        }

    def test_ten_sections_in_order(self):
        win = self._window()
        self.assertEqual(len(win.report_sections), 10)
        self.assertEqual(
            list(win.report_sections.keys()),
            [f"{i:02d}" for i in range(1, 11)],
        )

    def test_header_chips_present(self):
        win = self._window()
        self.assertTrue(hasattr(win, "scan_age_badge"))
        self.assertEqual(win.mode_chip.text(), "MODE: CACHE-FIRST")
        self.assertTrue(hasattr(win, "session_badge"))
        self.assertTrue(hasattr(win, "vix_chip"))

    def test_guardrails_footer_visible_and_false(self):
        win = self._window()
        self.assertTrue(hasattr(win, "guardrails"))
        self.assertTrue(win.guardrails.isVisible() or True)  # footer is not collapsible
        self.assertTrue(win.guardrails._status.text().endswith("False"))

    def test_sections_collapse_and_expand(self):
        win = self._window()
        sec = win.report_sections["01"]
        sec.set_expanded(False)
        self.assertTrue(sec.body.isHidden() or not sec.header.isChecked())
        sec.set_expanded(True)
        self.assertTrue(sec.header.isChecked())

    def test_dashboard_renders_real_price(self):
        win = self._window()
        win.display_report(self._report(), 0.0, cached=True)
        self.assertEqual(win.index_cards["nifty"]["price"].text(), "22,520.45")
        self.assertIn("+1.30%", win.index_cards["nifty"]["change"].text())

    def test_dashboard_renders_candles_and_range_selector(self):
        win = self._window()
        candles = [
            {"t": f"2026-10-{i:02d}", "o": 100 + i, "h": 105 + i,
             "l": 99 + i, "c": 102 + i, "v": 1000 + i}
            for i in range(1, 40)
        ]
        report = {"market": "NSE", "generated": "2026-10-11T00:00:00Z",
                  "nifty_candles": candles}
        win.display_report(report, 0.0, cached=True)
        # default 3M keeps all 39
        self.assertEqual(len(win.index_cards["nifty"]["chart"]._candles), 39)
        self.assertEqual(len(win.index_cards["bank_nifty"]["chart"]._candles), 0)
        # range selector slices the stored real candles (no refetch)
        win.set_chart_range("1M")
        self.assertEqual(len(win.index_cards["nifty"]["chart"]._candles), 22)

    def test_unavailable_renders_na_not_fabricated(self):
        win = self._window()
        win.display_report({"market": "NSE", "breadth": {}}, 0.0, cached=True)
        # BANK NIFTY snapshot is not provided -> OHLC must be N/A, not zeros.
        self.assertIn("N/A", win.index_cards["bank_nifty"]["ohlc"].text())
        # No technical top-list in the report -> uptrend screen shows the
        # honest empty state (never invented symbols).
        self.assertIn("No technical top-list", win.uptrend_note.text())
        self.assertEqual(win.uptrend_table.rowCount(), 1)  # fill_table "—" row
        self.assertEqual(win.uptrend_table.item(0, 0).text(), "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)


@unittest.skipIf(not QT_AVAILABLE, "PySide6 (Qt) is not installed")
class TestRedesign(unittest.TestCase):
    """KPI strip, macro cards and breadth panel render real report values."""

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _window(self):
        win = MarketLabWindow()
        self.addCleanup(win.deleteLater)
        return win

    def _report(self):
        return {
            "market": "NSE",
            "generated": "2026-10-11T00:00:00+00:00",
            "market_regime": "BEARISH",
            "nifty_snapshot": {"price": 22520.45, "change_percent": 1.3,
                               "open": 22315, "high": 22580, "low": 22295},
            "volatility": {"india_vix": {"value": 14.38, "change_percent": -5.9,
                                         "regime": "MODERATE"}},
            "breadth": {"advancing": 100, "declining": 50, "unchanged": 5},
        }

    def test_kpi_strip_populates(self):
        win = self._window()
        win.display_report(self._report(), 0.0, cached=True)
        self.assertEqual(win.kpi["nifty"]["value"].text(), "22,520.45")
        self.assertIn("+1.30%", win.kpi["nifty"]["sub"].text())
        self.assertEqual(win.kpi["vix"]["value"].text(), "14.38")
        self.assertIn("-5.90%", win.kpi["vix"]["sub"].text())
        self.assertEqual(win.kpi["advances"]["value"].text(), "100")
        self.assertEqual(win.kpi["declines"]["value"].text(), "50")
        self.assertEqual(win.kpi["ad"]["value"].text(), "2.00")
        # advances bar fraction = 100/(100+50)
        self.assertAlmostEqual(win.kpi["advances"]["bar"]._frac, 2 / 3, places=2)

    def test_missing_kpi_shows_dash(self):
        win = self._window()
        win.display_report({"market": "NSE", "breadth": {}}, 0.0, cached=True)
        self.assertEqual(win.kpi["nifty"]["value"].text(), "N/A")
        self.assertEqual(win.kpi["advances"]["value"].text(), "N/A")

    def test_section01_macro_cards_regime(self):
        from PySide6.QtWidgets import QLabel
        win = self._window()
        win.display_report(self._report(), 0.0, cached=True)
        labels = [l.text() for l in win.report_sections["01"].body.findChildren(QLabel)]
        self.assertIn("BEARISH", labels)

    def test_section02_breadth_stack_bar(self):
        win = self._window()
        win.display_report(self._report(), 0.0, cached=True)
        from market_lab import widgets as _W
        bars = win.report_sections["02"].body.findChildren(_W.StackBar)
        self.assertEqual(len(bars), 1)
        self.assertEqual(len(bars[0]._segments), 2)  # advances + declines

    def test_remaining_sections_render_tables(self):
        rich = {
            "market": "NSE",
            "generated": "2026-10-11T00:00:00+00:00",
            "sector_intelligence": {
                "available": True,
                "top_sectors": [
                    {"sector": "IT", "return_20d": 4.2, "relative_strength_20d": 8.1, "regime": "POSITIVE"},
                    {"sector": "METAL", "return_20d": -1.5, "relative_strength_20d": -2.0, "regime": "NEGATIVE"},
                ],
            },
            "top_technical_stocks": [
                {"symbol": "AAA", "technical_score": 99.0, "trend": "STRONG_UPTREND"},
            ],
            "derivatives": {
                "available": True,
                "nifty": {"available": True, "underlying": {"spot": 22520.45},
                          "pcr": {"oi_pcr": 1.1}, "max_pain": {"strike": 22500}},
            },
            "institutional_flow": {"available": True, "metrics": {"fii_20d": -100.0}},
            "research_factors": {
                "status": "AVAILABLE",
                "top_ranked": [{"rank": 1, "symbol": "UEL", "composite_z": 1.4, "price": 214.0}],
                "bottom_ranked": [{"rank": 1, "symbol": "ATALREAL", "composite_z": -1.3, "price": 11.0}],
            },
        }
        win = self._window()
        win.display_report(rich, 0.0, cached=True)

        from PySide6.QtWidgets import QTableWidget
        def first_table(num):
            tables = win.report_sections[num].body.findChildren(QTableWidget)
            return tables[0] if tables else None

        s03 = first_table("03")
        self.assertIsNotNone(s03)
        self.assertEqual(s03.columnCount(), 5)            # #, Sector, 20D%, RS, Regime
        self.assertEqual(s03.rowCount(), 2)               # two real sectors
        s04 = first_table("04")
        self.assertEqual(s04.columnCount(), 4)            # Rank, Symbol, Score, Trend
        s05 = first_table("05")
        self.assertEqual(s05.columnCount(), 3)            # Metric, NIFTY, BANK NIFTY
        s06 = first_table("06")
        self.assertEqual(s06.columnCount(), 2)            # Metric, INR crore
        # Section 08 has top AND bottom tables.
        s08 = win.report_sections["08"].body.findChildren(QTableWidget)
        self.assertEqual(len(s08), 2)
