# CHANGES.md

This file tracks context, workflow, and behavior changes important for future
coding agents.

## 2026-10-10 - Live end-to-end check (terminal-integrated)

No code change. On-machine live verification of the integrated stack
(services, Market Lab CLI, Ollama tool call, both GUIs) — see
`docs/VALIDATION.md` "2026-10-10 - Live end-to-end check". Result: the whole
pipeline works in the terminal — Ollama `qwen3.5:4b` UP, SearXNG UP, cache-first
Market Lab report clean (1,999 stocks, no full scan, guardrails intact), a real
Ollama turn called `get_market_brief` and produced a grounded summary, and both
`MarketLabWindow` and `NovaWindow` construct/run headless and fetch live NSE
data. Reminder logged: event calendar needs re-check ~12:11 IST 2026-10-11.

## 2026-10-10 - Assistant tool-registry + run_tool contract tests

Added `tests/test_tool_contract.py` (15 offline tests) protecting the
invariants the Ollama tool-calling loop relies on:

- Registry/schema lock-step: every callable in `TOOLS` is advertised in
  `TOOL_SCHEMA`, every schema function name resolves to a real tool, no
  duplicate schema names, and each entry is a well-formed function schema
  (name, description, object parameters, required keys exist in properties).
- `run_tool` never raises: unknown tool -> text; args as JSON string are
  parsed; malformed JSON and non-dict args are normalized to `{}`; bad
  arguments become a "Bad arguments" message. Only side-effect-free paths are
  executed (`get_time`; a missing-arg `open_website` call raises `TypeError`
  before any browser opens).
- `get_market_brief` dispatches correctly through `run_tool` (loader stubbed,
  so it is hermetic and read-only).
- Brain coupling: `brain.TOOL_SCHEMA` is `tools.TOOL_SCHEMA`, `MAX_TOOL_ROUNDS`
  is sane, and every schema name is dispatchable by `run_tool`.

No production code changed.

Validation:

- Full suite: `Ran 167 tests ... OK` (152 -> 167; 15 new).
- `ast.parse` on the new test file passed; `import brain` succeeds offline.

## 2026-10-10 - Cache-first pipeline integration tests + shared report loader

Added `tests/test_pipeline_integration.py` (19 offline tests) covering the
end-to-end cache-first pipeline without network, Ollama, real scan, or writes
to the real cache:

- Save/load round-trip: `save_json_report` -> `load_latest_saved_report`
  returns an equivalent report; guardrails (`analysis_only`,
  `buy_sell_authorized: false`) survive the round-trip; newest file wins;
  empty cache loads nothing.
- `get_market_brief` and `get_market_analysis` read a redirectable temp cache;
  `get_market_analysis` never calls `scan_market` when a saved report exists,
  and falls back to the scanner only when the cache is empty.
- Consumer agreement: the brief and the analysis snapshot, which parse the
  same report independently, must report identical measured facts (regime,
  India VIX, breadth, FII/DII flow regime, signal-eligibility honesty, top
  symbols).
- Stale/missing handling is consistent across both consumers.

Code change: `tools.get_market_brief` now reuses the shared
`_load_latest_market_lab_report()` loader instead of duplicating the
cache-globbing logic. Behavior is preserved (newest valid saved report ->
brief; none -> the "open Market Lab first" message) and the corpus is now
readable from a single cache path. Minor behavior improvement: a corrupt
newest file now falls back to an older valid report instead of erroring.

Removed approved scratch/debug files from the repo root: `run_test.py`,
`test_fix.py`, `test_verify.py`, `test_output.txt` (never committed; two were
UTF-16 throwaway scripts, one a 109-byte import stub, one a captured
test-output log).

Validation:

- `ast.parse` on `tools.py` and the new test file passed.
- `import tools`; live read-only `get_market_brief()` against the real cache
  still returns a valid brief (0.0h fresh).
- Full suite: `Ran 152 tests ... OK` (133 -> 152; 19 new).

## 2026-10-10 - requirements.txt generated from venv + full verification

- Generated `requirements.txt` from `.\venv\Scripts\pip.exe freeze` (58 packages).
- Verified Python syntax across 54 source files with `utf-8-sig` decoding.
- Confirmed main assistant imports: `import main, brain, tools, ui` ok.
- Confirmed market lab imports: `import market_lab_ui; from market_lab.market_lab_data import get_market_lab_data; from market_lab.market_lab_brain import analyze_market_lab` ok.
- Ran full test suite: `.\venv\Scripts\python.exe -m unittest discover -s tests` → 108 tests in 0.200s, OK.

## 2026-10-10 - get_market_analysis made cache-first

`tools.py:get_market_analysis()` used to call `scan_market()` unconditionally
(the expensive full NSE scan) on every assistant call. It is now cache-first,
matching Market Lab behavior:

- New `_build_market_analysis_from_report(report)` builds the snapshot purely
  from the latest saved Market Lab report (regime, NIFTY/BANKNIFTY returns,
  breadth, India VIX, sector strength, derivatives OI/PCR/max-pain, FII/DII
  institutional flow, event risk, top technical + factor-ranked stocks).
  It never runs a scan and never fetches live prices.
- New `_build_market_analysis_from_scanner(dataframe, summary, lab_report=None)`
  holds the original scanner logic, now only used as a fall-back when no saved
  report exists. Still merges the latest saved report into the availability
  matrix exactly as before.
- `get_market_analysis()` dispatches: report present → report builder (no
  scan); no report → `scan_market()` → scanner builder. Removed a duplicate
  `except` block that an earlier partial edit had left behind.
- Full-dataframe rankings (momentum / relative strength / volume expansion) are
  not stored in a saved report, so the cache-first path reports them honestly as
  NOT_AVAILABLE and tells the user to run FULL REFRESH in Market Lab for those.
- Derivatives context now renders measured scalars (`SPOT`, `OI_PCR`,
  `VOLUME_PCR`, `MAX_PAIN_STRIKE`) instead of leaking the report's raw nested
  dicts.
- `TOOL_SCHEMA` description for `get_market_analysis` updated to document the
  cache-first behavior and which layers need a full scan.

Analysis-only invariants unchanged: no broker/order/execution, missing data is
flagged, measured values are not invented.

Files changed:

- `tools.py` (cache-first dispatch + two builders + `_report_return` helper +
  schema description)
- `tests/test_cached_market_analysis.py` (new: 25 offline tests)

Validation:

- `ast.parse` on `tools.py` and the new test file passed.
- `import main, brain, tools, ui` passed.
- Full suite: `Ran 133 tests ... OK` (108 → 133; 25 new).
- Live cache-first call of `get_market_analysis()` returned in well under a
  second from the saved report (no scan); scanner fall-back exercised with a
  stubbed dataframe in tests.

## 2026-10-10 - GUI smoke test: skip cleanly when PySide6 is missing

`tests/test_gui_smoke.py` now guards its PySide6 / Market Lab imports with
`try/except ImportError` and decorates the test case with
`@unittest.skipIf(not QT_AVAILABLE, ...)`. Without Qt the module still imports
and the case reports 17 skips instead of an import error, so
`unittest discover -s tests` stays green on a machine that has no PySide6.
Behavior with Qt installed is unchanged (`QT_QPA_PLATFORM=offscreen`, one
`QApplication`, real `MarketLabWindow` built with no event loop).

## 2026-10-10 - Headless GUI smoke tests for Market Lab

Added `tests/test_gui_smoke.py`: the first automated coverage of the Market Lab
GUI itself, run fully headless and offline so it can live in the normal
`unittest discover -s tests` run.

- Forces `QT_QPA_PLATFORM=offscreen` before importing PySide6, creates exactly
  one `QApplication` for the module, and constructs the real `MarketLabWindow`
  without ever running an event loop. The deferred
  `QTimer.singleShot(150, load_initial_report)` therefore never fires, so the
  test proves construction spawns no worker, no network call, and no NSE scan.
- Locks in the watchlist fix: `task_succeeded("watchlist", ...)` must store the
  refresh payload in `watch_data` and re-render `watch_view` (the old code
  dropped the result, so the panel never populated). Also covers the
  `NOT_AVAILABLE` branch, the empty-pin reset, `format_watchlist_line` dashes
  for missing numbers, PIN dedupe/`MAX_SYMBOLS` cap, and the round-robin poll.
- Locks in the backtest arg-wiring fix: `window.start_task` is stubbed with a
  recorder so `run_backtest_task` is exercised with no real `QThread` and no
  network. The captured args/kwargs are bound against the real
  `inspect.signature(run_backtest)`, which is exactly the `TypeError` the UI's
  blank-input path used to raise; `symbols` must keep its `None` default.
- Covers `render_backtest` (real report keys, decile hit-rate labels, trend
  mix, top-ranked list, "not a buy/sell signal" guardrail), the invalid-result
  path, `task_succeeded` page switch (index 3 = Factor Backtest, asserted
  against its nav label), `task_failed` surfacing the error in the result view
  (`QMessageBox` mocked), and `task_finished` restoring the controls.
- No production code changed; these tests only assert existing behavior.

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

