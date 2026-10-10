# CHANGES.md

This file tracks context, workflow, and behavior changes important for future
coding agents.

## 2026-10-10 - Institutional flow primary-coverage progress note (Option C)

Made the runway to a fully NSE-primary FII/DII history window legible instead
of a bare "2/22". This is documentation of *progress*, not a way to fake
coverage: the `signal_allowed` gate is unchanged and still requires every
target session to be primary-verified.

Context (verified by a live probe of `fetch_nse_rows()`): NSE's combined
endpoint returns only the latest trading day, and there is no NSE historical
FII/DII API. Older sessions can only come from the Groww mirror. Promotion is
sticky (`upsert_rows` keeps the highest-priority source per date), and ~1 NSE
session is promoted per trading day, so full-primary needs ~18 trading days.

- New pure helper `_primary_coverage_summary(metrics)` in the flow engine
  returns a coverage note dict (verified fraction, remaining sessions, and an
  honest "estimated more trading day(s)" runway) and is surfaced as
  `primary_coverage_note` on the metrics.
- `print_report` now prints a `Primary coverage:` line when the window is not
  fully primary-verified.
- The assistant `get_market_brief` flow section prints a matching
  `Coverage:` line under Primary-verified sessions, plus the existing
  honest `Signal-eligible: NO` reason.
- Added `tests/test_institutional_flow_coverage.py` (offline) for the helper.

## 2026-10-10 - Assistant morning market brief tool (`get_market_brief`)

Added a new voice/chat-callable tool, `get_market_brief()`, so the Nova
assistant can read out a concise morning market brief on request. It is
**cache-first**: it loads the latest saved Market Lab JSON report and never
triggers a full NSE scan, so it is cheap and respects the "prefer cache-first"
rule.

- Composed from measured values only, taken straight from the saved report:
  header + report age (staleness), market regime, breadth, India VIX +
  volatility regime, institutional FII/DII flow (5D/10D/20D with the
  `signal_allowed` honesty line), event risk + top upcoming events, top
  technical stocks, top factor-ranked names, and any data-availability gaps.
- Ends with an explicit guardrails footer: analysis-only, measured vs.
  interpreted kept separate, not a buy/sell signal, no broker/orders.
- Split into a pure `_build_market_brief(report)` (dict -> str, unit-testable
  offline) and a thin `get_market_brief()` that loads the cache and calls it.
- Registered in `TOOLS` and `TOOL_SCHEMA` so the Ollama brain can invoke it.

## 2026-10-10 - Factor backtest harness fixed and wired into Market Lab UI

The factor backtest harness (`analysis/backtest_harness.py`) was committed but
never actually ran: `_safe_float` was used in `trend_component`,
`strength_component`, and `score_symbol` but was never defined or imported, so
`run_backtest` raised `NameError` on the first symbol. It is now functional and
surfaced as a new "Factor Backtest" panel in Market Lab.

Evidence-integrity fixes (analysis-only rules):

- Added a numeric `_safe_float()` helper (missing / non-numeric -> `None`).
- `trend` is read as the raw `TREND` classification string, not coerced through
  the numeric helper. Routing it through `_safe_float` previously yielded
  `None`, so `trend_counts` and the trend column were always empty.
- `_success_rate` actually computes the fraction of up days (a hit-rate), not an
  average return. It was stored/printed as `avg_20d_return` / "avg 20D return",
  which would misrepresent measured data. Renamed to `up_day_fraction` across
  the per-symbol entry, the decile stats keys, and the console output. Missing
  values stay `None` (never treated as zero).

Market Lab UI wiring (reuses the existing Worker / page / nav pattern):

- New "Factor Backtest" nav page: optional symbol list, "RUN BACKTEST" button,
  and a read-only result view. Blank input runs the 20-symbol quick sample.
- `run_backtest` is invoked lazily in a `"backtest"` background worker so the
  heavy scanner / Yahoo imports never block UI startup.
- `start_task` / `task_finished` / `task_succeeded` / `task_failed` now handle
  the `"backtest"` task. The result panel labels the metric as an up-day
  fraction (hit-rate), not a return, and repeats that this is not a signal.

Runtime call-path fixes (found after the panel was wired, covered by
regression tests that stub the network layer):

- `run_backtest(symbols, ...)` had `symbols` as a required positional with no
  default, but the UI's blank-input path calls `run_backtest(sample=20,
  quiet=True)`, which raised `TypeError: missing 1 required positional
  argument` on every "RUN BACKTEST" click. `symbols` now defaults to `None`.
- The universe-vs-explicit guard used `if symbols is None:`, but the CLI
  (`main()`) passes `args.symbols` = `[]` from `nargs="*"`. An empty list is
  not `None`, so `--quick` and any no-arg run took the explicit branch and
  backtested an empty pool (silently 0 symbols). The guard is now
  `if not symbols:` so both `None` and `[]` mean "use the universe".

Files changed:

- `analysis/backtest_harness.py` (fix `_safe_float`, trend string, rename
  `up_day_fraction`, `symbols=None` default + `if not symbols` guard)
- `market_lab_ui.py` (Factor Backtest page + backtest task handling)
- `tests/test_backtest_harness.py` (new: offline helper tests plus a
  network-stubbed `run_backtest` regression test)

## 2026-10-10 - Watchlist refresh results wired into the UI

The stock watchlist (added in `a383f45`) started a `"watchlist"` worker but
`task_succeeded` had no branch for it, so every refresh result was silently
dropped and the panel stayed on "waiting for first refresh…" forever. The
row renderer also formatted numbers with `+.2f` / `.1f`, which raised
`TypeError` on any `None` reading once data did arrive.

Behavior now:

- `task_succeeded` stores each `refresh_watch_symbol` result into
  `self.watch_data` and re-renders the panel.
- Watchlist state (`watch_symbols`, `watch_index`, `watch_data`) is
  initialized in `MarketLabWindow.__init__` so an early result cannot hit an
  `AttributeError`.
- Row rendering moved to a new pure, Qt-free `format_watchlist_line()` in
  `analysis/data/watchlist_engine.py`. Missing or `NaN` readings render as
  `--` instead of a fabricated number; analysis-only behavior is unchanged.

Files changed:

- `analysis/data/watchlist_engine.py` (added `_fmt`, `format_watchlist_line`)
- `market_lab_ui.py` (watchlist result handling, simplified render, init state)
- `tests/test_watchlist_engine.py` (new: 10 offline tests)

Validation:

- `.\venv\Scripts\python.exe -m unittest discover -s tests -v` → 51 passed.
- `py_compile` + BOM-aware `ast.parse` passed on the edited files.
- Formatter output spot-checked for AVAILABLE / waiting / NOT AVAILABLE /
  missing-value cases.

## 2026-10-09 - Agent Context Bootstrap

Added a model-agnostic context layer so Nova can be opened by another coding
agent and resumed safely.

Files added:

- `AGENTS.md`
- `README.md`
- `PROJECT_CONTEXT.md`
- `USER_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEPENDENCIES.md`
- `docs/VALIDATION.md`
- `docs/WORKFLOW.md`
- `docs/MODEL_HANDOFF.md`

Repository facts recorded:

- Actual project folder is `C:\Users\Anirudh\nova`.
- The folder is not currently a Git repository.
- No dependency manifest was found before this pass.
- Existing runtime dependencies were inspected from `venv/`.
- Main assistant entry point is `main.py`.
- Market Lab entry point is `market_lab_ui.py`.
- Market behavior is analysis-only and must remain non-executing.

Code changes:

- Added a small entry-point docstring to `main.py`.

Validation:

- Initial read-only inventory and dependency inspection completed.
- Python syntax check passed across 39 source files using BOM-aware decoding.
- Main assistant import smoke check passed.
- Market Lab import smoke check passed.

## 2026-10-09 - Git And GitHub Initialization

- Initialized a local Git repository on branch `main`.
- Confirmed the existing `.gitignore` excludes all generated state
  (`venv/`, `.venv/`, `stt_models/`, `voices/`, `analysis/data/cache/`,
  `analysis/data/data/cache/`, `*.wav`, `*.zip`, `*.log`).
- Root commit `e6ff588` contains 55 source, doc, and context files (~1.1 MB).
- Created the private GitHub repository `benalanirudh-pixel/nova` and pushed
  `main`; first push authenticated through Git Credential Manager.
- Set repo-local git identity: Anirudh <benalanirudh@gmail.com>.
- Updated stale "not a Git repository" statements in `AGENTS.md`, `README.md`,
  `PROJECT_CONTEXT.md`, and `docs/MODEL_HANDOFF.md`.


## 2026-10-09 - Market Lab UI Report Persistence

- Fixed: `market_lab_ui.py` never saved successful reports to JSON, so
  `load_latest_saved_report()` had nothing to show on the next launch and
  `analysis/data/cache/market_lab/` did not exist at all.
- `Worker.run()` now calls `save_json_report()` in the background thread for
  every successful `"report"` result; save failures print a warning but never
  fail the task.
- Verified with a cache-first engine run: 18 s end-to-end using the cached
  1,999-stock scan; first saved report written (62 KB) and loaded back
  through the UI loader with safety guardrails intact.


## 2026-10-10 - Event Risk Engine Wired Via Verified Calendar

- Created `analysis/data/event_calendar.json` — the missing file that was the
  sole reason `event_risk_engine` reported NOT AVAILABLE and `overall_risk`
  stayed UNKNOWN. No Python source was changed; the wiring in
  `load_event_risk_context()` already existed.
- Populated with 11 source-verified events: India CPI/WPI releases (Oct 12,
  Oct 14), US BLS CPI/PPI/import-export releases (Oct 14-16), NSE 2026
  holidays (Dussehra Oct 20, Muhurat Nov 8, Diwali-Balipratipada Nov 10,
  Guru Nanak Nov 24, Christmas Dec 25), and the next RBI MPC decision
  (Dec 4).
- Sources cross-checked on 2026-10-10: Zerodha/Livemint/HDFC Sky (NSE
  holidays), MoSPI and DPIIT advance release calendars via IndiaInflation.com
  and Finostat, bls.gov (US releases), RBI 2026-27 MPC schedule.
- Result: report flag `event_risk_engine` = AVAILABLE, `overall_risk` =
  MODERATE with 5 events inside the 7-day window.
- Maintenance rule: `source_checked_at` must be re-verified within 24 hours
  or the engine deliberately reverts to NOT_AVAILABLE/UNKNOWN.


## 2026-10-10 - Assistant Availability Matrix + Event Calendar Checker

- `tools.py`: `get_market_analysis()` no longer underreports the system.
  Its availability matrix now merges the latest saved Market Lab report
  (cache-first, no network) into rows the scanner cannot measure: INDIA_VIX,
  volatility regime, SECTOR_STRENGTH, derivatives OI/IV/PCR/max-pain,
  INSTITUTIONAL_FLOW, EVENT_RISK. The report timestamp is printed as
  `MARKET_LAB_REPORT_TIMESTAMP` so staleness stays visible, and
  `MISSING_CRITICAL_LAYERS` is computed dynamically. Transaction-cost and
  covariance models remain honestly NOT_AVAILABLE. No-report path behaves
  exactly as before.
- New `check_event_calendar.py`: offline validator + 24 h staleness alarm +
  re-check checklist for `analysis/data/event_calendar.json`. Exit 0 =
  valid and fresh; exit 1 = stale, invalid, or missing. It never writes to
  the calendar and never fakes a source check.
- Registered `check_event_calendar.py` in `AGENTS.md` common commands.
- Preserved behavior note: `get_market_analysis()` still runs a live full
  NSE scan per call (pre-existing; unchanged).


## 2026-10-10 - Engine Math Test Suite

- New `tests/test_engine_math.py`: 32 reference-value tests using stdlib
  `unittest` (pytest is not installed; no new dependency added).
- Coverage: technical engine (SMA, EMA, RSI bounds/warm-up, MACD on constant
  series, True Range gap logic, Wilder ATR, ROC, relative volume, VWAP),
  volatility engine (rolling ATR known mean, realized-vol edge cases,
  percentile rank, regime thresholds, direction rules), risk engine
  (position sizing known values, input rejection, guardrail flags), event
  risk engine (freshness/completeness gates, proximity score escalation,
  rejection of unverified/naive-timestamp events, guardrails).
- Fixtures are hand-computed; no network, caches, or live market data.
- Result: 32/32 passing in ~0.02 s.
- Test command registered in `AGENTS.md`.


## 2026-10-10 - Research Factor Engine Built And Wired

- New `analysis/data/research_factor_engine.py`: cross-sectional factor
  ranking over the cached NSE scanner universe. Five transparent,
  equal-weighted z-score factors: MOMENTUM_60D, RELATIVE_STRENGTH,
  LOW_VOLATILITY (ATR% sign-flipped), TREND_STRUCTURE (EMA alignment
  0-3), PROXIMITY_52W_HIGH. Minimum universe 30, minimum factors per
  stock 3. No fundamental factors — Nova has no verified fundamentals
  source, so none are invented.
- Wired into `market_lab/market_lab_data.py` import block and report
  assembly; `data_availability.research_factor_engine` reflects status.
- New `tests/test_research_factor_engine.py`: 8 reference-value tests
  (availability, sign-flip, extreme winner/loser rank, missing columns,
  small universe, NaN exclusion, guardrails, z-score bounds).
- Full suite: 40 tests / 0.08 s, all passing.
- Live cache-first report now shows `research_factor_engine: AVAILABLE`
  (1,999-stock universe). Guardrails intact: `factor_rank_is_a_buy_sell_signal:
  false`, `buy_sell_authorization: false`, `trading_execution: false`.


## 2026-10-10 - Live-Only Report Mode + Calendar Re-Check Helper

- New `--live-only` mode in `market_lab/market_lab_data.py`:
  `get_market_lab_data(live_only=True)` reuses the newest cached equity
  scan at any age via `load_latest_market_scan_any_age()`, then refreshes
  only the cheap live layers (index returns, NIFTY snapshot, volatility,
  derivatives, institutional flow, risk, event risk). Report carries
  `mode: LIVE_ONLY` with scanner file + age labelled. `--live-only` and
  `--refresh` are mutually exclusive (CLI exits 2, function raises
  `ValueError`). Verified live: 1,999-stock reuse in seconds, report
  `market_lab_20261010_012258.json`, all availability flags AVAILABLE,
  guardrails all false.
- New `touch_event_calendar.py`: interactive re-check confirmer for
  `analysis/data/event_calendar.json`. Prints the 4 source groups + event
  consistency as 5 checks; only a literal `yes` stamps
  `source_checked_at` to now, anything else leaves the file untouched.
  Never touches the network, never edits events. Registered below.
- Deleted the half-built `analysis/tools/check_daily_calendar.py` stub
  (bad import of a nonexistent engine constant, broken source URL,
  untested scraping parsers). It was untracked and never committed.
- `market_lab_ui.py`: new `LIVE UPDATE` button beside `FULL REFRESH`
  calls `get_market_lab_data(live_only=True)` in the background worker
  (auto-saved to JSON like every report); both buttons disable while a
  report task runs. Import smoke confirms both handlers exist.
- `market_lab_ui.py`: staggered auto-refresh — `AUTO: OFF/ON` toggle +
  1 s header clock (`HH:MM:SS • NSE OPEN/CLOSED • data age • next update
  in Ns`). Live-only worker polls every 60 s in market hours, 30 s when
  closed; single-flight guard (never stacks workers), manual actions
  reset the countdown, failed polls retry next tick without killing
  auto mode. Session logic verified: weekday 10:00 IST open, Saturday
  and pre-open closed.
- `market_lab_ui.py`: 1-second live display tier — an always-on display
  ticker repaints the header clock, the Overview `Live` strip (clock,
  session badge, data age, countdown), and the REPORT TIME metric every
  second from memory only; zero network. The auto tick now only
  schedules polls.

