# Validation Notes

Last updated: 2026-10-10.

## What Was Inspected

Read-only repository inspection covered:

- Root files and directories in `C:\Users\Anirudh\nova`.
- Main entry points: `main.py`, `ui.py`, `market_lab_ui.py`.
- LLM/tool layers: `brain.py`, `tools.py`, `market_lab/market_lab_brain.py`.
- Market Lab data gateway: `market_lab/market_lab_data.py`.
- Market engines under `analysis/data/`.
- Voice/TTS/visual modules: `voice.py`, `tts.py`, `nova3dcore.py`.
- Existing test/helper scripts: `test_nse_mcp.py`, `test_nse_tools.py`,
  `mic_test.py`.
- Existing virtual environment packages through `pip freeze`.
- Existing market cache folders under `analysis/data/cache/`.

## Verified Current Facts

- `C:\Users\Anirudh\nova` is the actual local project folder.
- This folder is not currently a Git repository (initialized on 2026-10-09, `git push origin main` completed).
- Root `requirements.txt` now exists (generated from `venv\pip freeze`, 58 packages).
- No `pyproject.toml` or similar manifest was found before this context pass.
- The project has two visible app entry points:
  - `main.py`
  - `market_lab_ui.py`
- Both `brain.py` and `market_lab/market_lab_brain.py` configure Ollama model `qwen3.5:4b`.
- Market Lab normal mode is cache-first unless refresh is forced or no cache is available.
- The current code repeatedly marks market functionality as analysis-only and not a broker/order system.
- Python syntax verified across 54 source files using BOM-aware decoding (`utf-8-sig`).
- Main assistant import smoke: `import main, brain, tools, ui` passes.
- Market Lab import smoke: `import market_lab_ui; from market_lab.market_lab_data import get_market_lab_data; from market_lab.market_lab_brain import analyze_market_lab` passes.
- Full test suite: `.\venv\Scripts\python.exe -m unittest discover -s tests` → 108 tests in ~0.2s, OK.

## Checks Run During Context Migration

Initial discovery and dependency checks:

```powershell
Get-ChildItem -Force
rg --files -uu -g '!venv/**' -g '!.venv/**' -g '!__pycache__/**' -g '!**/__pycache__/**' -g '!*.pyc' -g '!stt_models/**' -g '!voices/**' -g '!analysis/data/cache/**'
.\venv\Scripts\python.exe -m pip freeze
```

Context migration verification:

```powershell
.\venv\Scripts\python.exe -B -c "import ast,pathlib; skip={'venv','.venv','__pycache__'}; files=[p for p in pathlib.Path('.').rglob('*.py') if not (set(p.parts)&skip)]; [ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in files]; print(f'syntax ok: {len(files)} files')"
```

Result: passed across 39 Python files.

```powershell
.\venv\Scripts\python.exe -B -c "import main, brain, tools, ui; print('main assistant imports ok')"
```

Result: passed.

```powershell
.\venv\Scripts\python.exe -B -c "import market_lab_ui; from market_lab.market_lab_data import get_market_lab_data; from market_lab.market_lab_brain import analyze_market_lab; print('market lab imports ok')"
```

Result: passed.

Note: an earlier syntax scan using plain `utf-8` decoding surfaced an existing
UTF-8 BOM in one source file. The verification scan was rerun with
`utf-8-sig`, which is appropriate for BOM-prefixed Python source text and did
not modify files.

## Recommended Smoke Checks

For documentation-only changes:

```powershell
.\venv\Scripts\python.exe -B -c "import ast, pathlib; [ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p)) for p in pathlib.Path('.').rglob('*.py') if not any(part in {'venv', '.venv', '__pycache__'} for part in p.parts)]; print('syntax ok')"
```

For main assistant import smoke:

```powershell
.\venv\Scripts\python.exe -B -c "import main, brain, tools, ui; print('main assistant imports ok')"
```

For Market Lab import smoke:

```powershell
.\venv\Scripts\python.exe -B -c "import market_lab_ui; from market_lab.market_lab_data import get_market_lab_data; from market_lab.market_lab_brain import analyze_market_lab; print('market lab imports ok')"
```

For Indian Market MCP:

```powershell
.\venv\Scripts\python.exe test_nse_mcp.py
.\venv\Scripts\python.exe test_nse_tools.py
```

For cache-first Market Lab terminal report:

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py
```

Use this only when a terminal report check is needed. It may touch live market
data for lightweight index refreshes.

Verify requirements.txt exists and is readable:

```powershell
Test-Path -LiteralPath "requirements.txt"
```

## Known Validation Gaps

- The GUI was not launched during the documentation audit.
- No full `--refresh` market scan was run during the documentation audit.
- No live trade/broker behavior exists to validate, and none should be added.
- Automated unit tests now exist for engine math:
  `tests/test_engine_math.py` (32 tests, stdlib unittest). Offline
  cache-first pipeline integration coverage now exists too:
  `tests/test_pipeline_integration.py` (save/load round-trip, cache-first
  dispatch, consumer agreement, staleness). Backtest of the full-history
  live path and GUI-layout paint are still not covered.
- Existing `test_nse_*` scripts are manual smoke scripts, not a formal test
  suite.

## 2026-10-09 - Git/GitHub Initialization Session

No source code was changed. Only context docs were updated to replace stale
"not a Git repository" statements.

Checks run:

- `git init -b main` - repository created in `C:\Users\Anirudh\nova`.
- `git add -A` then `git ls-files` - 55 files, about 1.1 MB staged; confirmed
  no `venv/`, `.venv/`, `stt_models/`, `voices/`, cache, `*.wav`, `*.zip`, or
  `*.log` files staged.
- `git commit` - root commit `e6ff588`, 55 files, 52,779 insertions.
- `git ls-remote --heads origin main` - remote hash matches local `e6ff588`.
- `git status` - clean tree; `main` tracks `origin/main`.

Not run: no Python runtime checks were needed because no source code changed.


## 2026-10-09 - Market Lab UI Persistence Fix

Code changed: `market_lab_ui.py` only (import `save_json_report`, save in
`Worker.run()` on successful report).

Checks run:

- Project-wide `ast` syntax check with `utf-8-sig` decoding: passed.
- Import smoke:
  `from market_lab_ui import Worker, load_latest_saved_report; from market_lab.market_lab_data import save_json_report, get_market_lab_data`
  - passed.
- Cache-first engine run:
  `.\venv\Scripts\python.exe -B -u market_lab\market_lab_data.py --json`
  - completed in 18 s (23:45:46 -> 23:46:04);
  - used cached scan `market_scan_20261009_202230.csv` (1,999 stocks, no full scan);
  - live NSE option-chain fetch succeeded (attempt 1/3);
  - wrote `analysis/data/cache/market_lab/market_lab_20261009_234604.json` (62 KB).
- UI loader smoke: `load_latest_saved_report()` returned that report with
  `ai_context.guardrails` intact (`buy_sell_authorized: False`).

Observed data-availability flags from that run (not changed by this fix):

- `event_risk_engine`: NOT AVAILABLE
- `research_factor_engine`: NOT BUILT

Not run: GUI launch (interactive desktop only), forced `--refresh` scan,
Ollama AI analysis path.

## 2026-10-09 - Live GUI Test (market_lab_ui.py)

- Launched the real GUI window; stdout/stderr grepped for
  `ERROR|Traceback|WARNING|failed` after the session: no matches.
- Normal launch used the cached scan ("Using fresh cached market scan,
  1,999 stocks, 3.5 hours old") and displayed the previously saved report.
- Worker auto-save verified live twice without CLI involvement:
  reports written at 23:51:01 (cache-first path) and 23:53:32
  (user-triggered Refresh).
- The user-triggered Refresh completed the full 2,333-stock NSE scan in
  about 2 minutes; new scan `market_scan_20261009_235322.csv` saved and the
  resulting report has `mode: FORCED_REFRESH`.
- Newest-report loader confirmed intact: `generated` 2026-10-09T23:53:32,
  scanner file points at the fresh scan.


## 2026-10-10 - Event Risk Calendar Wiring

Data-only change: new file `analysis/data/event_calendar.json`. No Python
source edits.

Checks run:

- Loader smoke: `load_event_risk_context()` returned `status: AVAILABLE`,
  `overall_risk: MODERATE` (score 3), 5 upcoming events in the 7-day window,
  `source_fresh: True`, zero warnings.
- Engine self-test:
  `.\venv\Scripts\python.exe -B analysis\data\event_risk_engine.py`
  - passed (`Status: AVAILABLE`, `Execution enabled: False`).
- Full cache-first report regeneration (`market_lab_data.py --json`):
  completed in under 20 s; report `market_lab_20261010_001304.json` shows
  `data_availability.event_risk_engine: AVAILABLE`, safety guardrails intact,
  and all other availability flags identical to the previous run.
- Verified web sources (2026-10-10): recorded inside the calendar file
  (`source_name`, per-event `source`).

Not run: forced `--refresh` scan, GUI relaunch, Ollama analysis path.

Known gap carried forward at the time: `tools.py` hardcoded `EVENT_RISK:
NOT_AVAILABLE` in the assistant availability matrix; fixed the same day -
see "Availability Matrix Merge And Calendar Checker" below.


## 2026-10-10 - Availability Matrix Merge And Calendar Checker

Code changed: `tools.py`; new file `check_event_calendar.py`; `AGENTS.md`
command added.

Checks run:

- Project-wide `ast` syntax check with `utf-8-sig` decoding: passed.
- `check_event_calendar.py` executed: RESULT OK, exit code 0; 11/11 events
  valid, 5 events in the 7-day window, source FRESH (0.2 h old).
- Enrichment unit test (scanner NOT executed):
  `_load_latest_market_lab_report()` returned the report generated
  2026-10-10T00:13; `_merge_lab_availability` flipped all 9 mapped matrix
  rows to AVAILABLE with a report present, and left them NOT_AVAILABLE on
  the no-report path.
- Main assistant import smoke `import main, brain, tools, ui`: passed.

Not run: full `get_market_analysis()` end-to-end - it triggers a live full
NSE scan per call (pre-existing behavior), which this change does not need.
GUI, Ollama, and `--refresh` also not run.

Observation for a future task: `get_market_analysis()` calls `scan_market()`
unconditionally; making it cache-first would match Market Lab behavior.

## 2026-10-10 - Engine Math Test Suite

New file: `tests/test_engine_math.py` (stdlib `unittest`; pytest is not
installed and was not added).

Checks run:

- `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
  - Result: `Ran 32 tests in 0.023s - OK`.
- Pure offline: hand-computed fixtures only, no network or cache access.
- Note: unittest writes results to stderr; PowerShell 5.1 garbles native
  stderr redirection. Capture clean logs with
  `cmd /c "...python.exe -m unittest discover -s tests -v > out.txt 2>&1"`.

Not run: network scripts, GUI, forced `--refresh`, Ollama.


## 2026-10-10 - Live-Only Mode + Calendar Re-Check Helper

Code changed: `market_lab/market_lab_data.py`; new file
`touch_event_calendar.py`; `AGENTS.md` + `CHANGES.md` updated; half-built
`analysis/tools/check_daily_calendar.py` stub deleted (untracked, never
committed; failed import on a nonexistent engine constant).

Checks run:

- Project-wide `ast` syntax check with `utf-8-sig` decoding: 44 files OK.
- `touch_event_calendar.py` decline path: piped `no` leaves the calendar
  untouched, exit 1. (The `yes` stamp path was not exercised, to avoid
  mutating the verified `source_checked_at`.)
- Live `--live-only --json` run: completed in seconds reusing cached
  1,999-stock scan `market_scan_20261009_235322.csv`; saved
  `market_lab_20261010_012258.json` with `mode: LIVE_ONLY`,
  `event_risk_engine` + `research_factor_engine` AVAILABLE, risk
  available, all decision-policy flags false.
- Mutual exclusion: `--live-only --refresh` prints the exclusivity error
  and exits 2.
- `market_lab_ui.py` import smoke: `MarketLabWindow` exposes both
  `live_update_report` and `refresh_report`.
- Auto-refresh logic smoke: `nse_market_open_now` true for a weekday
  10:00 IST, false for Saturday and pre-open; cadence constants
  1000 ms / 60 s / 30 s confirmed; auto handlers present.
- Display ticker smoke: `MarketLabWindow` exposes `ensure_display_ticker`
  + `tick_display` alongside the auto handlers; import-only (no Qt
  event loop started).
- Full suite: `Ran 40 tests in 0.079s - OK` (captured via
  `cmd /c "... > file 2>&1"`; PowerShell 5.1 garbles native stderr).

Not run: forced `--refresh`, GUI relaunch, Ollama analysis path.


## 2026-10-10 - Watchlist Refresh Wiring

Code changed: `analysis/data/watchlist_engine.py` (added `_fmt` and
`format_watchlist_line`); `market_lab_ui.py` (handle the `watchlist` result in
`task_succeeded`, simplify `render_watchlist`, initialize watchlist state in
`__init__`); new test `tests/test_watchlist_engine.py`.

Bug fixed: the `"watchlist"` worker (added in `a383f45`) had no
`task_succeeded` branch, so refresh results were dropped and the panel never
updated. The old renderer also formatted with `+.2f`/`.1f`, which raised
`TypeError` on `None` readings.

Checks run:

- Project-wide `ast` syntax check with `utf-8-sig` decoding: passed for the
  two edited files.
- `py_compile` on `market_lab_ui.py`, `analysis/data/watchlist_engine.py`,
  `tests/test_watchlist_engine.py`: passed.
- `.\\venv\\Scripts\\python.exe -m unittest discover -s tests -v`
  - Result: `Ran 51 tests in 0.464s - OK` (10 new watchlist tests).
- Pure formatter smoke (no Qt, no network): AVAILABLE, waiting, NOT
  AVAILABLE, and all-`None` cases render correctly; missing readings show
  `--`. Console output required `PYTHONUTF8=1` because the Windows cp1252
  console cannot encode `₹`/`—` (the Qt text view renders them fine).

Not run: GUI launch (interactive desktop only), forced `--refresh`, live
single-symbol `refresh_watch_symbol` (needs network), Ollama path.

## 2026-10-10 - Factor Backtest Harness Fix + Market Lab Panel

Code changed: `analysis/backtest_harness.py`; `market_lab_ui.py`; new file
`tests/test_backtest_harness.py`.

Checks run:

- Project-wide `ast` syntax check with `utf-8-sig` decoding: passed.
- `py_compile` on `analysis/backtest_harness.py`, `market_lab_ui.py`, and
  `tests/test_backtest_harness.py`: exit code 0.
- Import + helper smoke (offline): `_safe_float`, `trend_component`,
  `strength_component`, `score_symbol`, `_up_day_fraction` import cleanly.
- Unit test suite:
  `.\\venv\\Scripts\\python.exe -m unittest discover -s tests`
  - `Ran 69 tests ... OK` (backtest helper tests plus a network-stubbed
  `run_backtest` regression test; suite was 51 before this work).
- Signature/report-key check: `run_backtest(symbols: list[str] | None = None,
  sample, days, workers, quiet)` and the returned keys (`universe`,
  `completed`, `degraded`, `errors`, `pack_width`, `elapsed_seconds`,
  `generated_at`, `symbols`, `trend_counts`, `decile_stats`) match the UI
  `render_backtest` wiring.

Bug fixes verified by regression tests:

- `_safe_float` was undefined -> `NameError` on the first symbol; now defined.
- `trend` is the raw `TREND` string (not coerced to `None`); regression test
  `test_trend_is_a_string_not_coerced_none` covers it.
- `_success_rate` mislabeled a hit-rate as a return; renamed to
  `up_day_fraction` and relabeled as a hit-rate in the UI and console.
- `run_backtest` required a positional `symbols`, so the UI's blank-input
  path (`run_backtest(sample=20, quiet=True)`) raised `TypeError`; `symbols`
  now defaults to `None`.
- The universe guard `if symbols is None:` let the CLI's empty-list `args`
  take the explicit branch (0 symbols). Now `if not symbols:` so `None` and
  `[]` both use the universe.

Not run: GUI launch (interactive desktop only), a live `run_backtest` (needs
network + NSE symbol list), full `--refresh` scan, Ollama path.

## 2026-10-10 - Assistant morning market brief (`get_market_brief`)

Verified:

- `import tools` succeeds; `get_market_brief` and `_build_market_brief` are
  present and callable (import check).
- `py_compile` passes on `tools.py`; `ast.parse` passes on the test file.
- `tests/test_market_brief.py` added (offline fixture report): covers header +
  staleness line, regime/breadth/VIX lines, institutional-flow honesty
  (`signal_allowed` correctly reported as NO), event-risk section, top
  technical + factor lists, data-gap section, and the guardrails footer.
- Full suite: `Ran 85 tests ... OK` (exit 0).
- Live spot-check against the real cached Market Lab report: the brief renders
  all sections with correct measured values (regime BEARISH, A/D 1.44, VIX
  15.28, FII 20D -57,910.10 Cr, etc.) and the `signal_allowed: NO` line.

Not run: live brain/Ollama tool-call turn (needs Ollama + `qwen3.5:4b`),
`--refresh` scan. The brief itself only reads cached data.

## 2026-10-10 - Institutional flow primary-coverage note (Option C)

Verified:

- `py_compile` passes on `analysis/data/institutional_flow_engine.py`;
  `ast.parse` passes on `tools.py` and the new test file.
- New `tests/test_institutional_flow_coverage.py` (offline): 6 tests covering
  `_primary_coverage_summary` (fully/partially/not verified, remaining-day
  estimate, message text) and its wiring into metrics.
- Full suite: `Ran 91 tests ... OK` (exit 0), up from 85.
- Live `institutional_flow_engine.py --days 20 --save` run exits 0 (READY) and
  `calculate_metrics` -> `_primary_coverage_summary` resolves with no error
  (the call site previously had no helper defined).
- Live `get_market_brief()` renders the new line, e.g. "Coverage: 2/20 target
  sessions are NSE-primary; 18 more trading day(s) estimated to reach full
  primary ...", with `Signal-eligible: NO` and its reason preserved.

Not run: a promotion beyond the cached 2 primary sessions (requires ~18
trading days of the daily schedule), GUI launch, full `--refresh` scan. This
change is display-only; it does not alter the `signal_allowed` gate.


## 2026-10-10 - Headless GUI smoke tests for Market Lab

Added `tests/test_gui_smoke.py` (new file; no production code changed).

Verified:

- `py_compile` passes on `tests/test_gui_smoke.py` and `market_lab_ui.py`;
  `ast.parse` passes on the new test file.
- New suite alone: `.\venv\Scripts\python.exe -B -m unittest
  tests.test_gui_smoke -v` (with `PYTHONUTF8=1`) -> `Ran 17 tests ... OK`
  (exit 0).
- Full suite: `.\venv\Scripts\python.exe -B -m unittest discover -s tests`
  (with `PYTHONUTF8=1`) -> `Ran 108 tests ... OK` (exit 0), up from 91.
- Offline guarantees observed: headless via `QT_QPA_PLATFORM=offscreen`; a single
  `QApplication`; the real `MarketLabWindow` is constructed without running an
  event loop, so the deferred `load_initial_report` never fires and
  `window.workers` is asserted empty; `window.start_task` is replaced by a
  recorder for every task-triggering path and `QMessageBox` is mocked for
  `task_failed`, so no `QThread`, no modal dialog and no network call happens.
  The `[BACKTEST ERROR]` line in the test output is the intentional fixture
  text printed by `task_failed`.
- Regression coverage locked in: watchlist refresh results are stored in
  `watch_data` and rendered into `watch_view` (previously dropped, so the panel
  never populated); the backtest UI call binds against the real
  `run_backtest` signature with `symbols` defaulting to `None` (previously
  `TypeError` on blank input); `render_backtest` renders the real report keys
  plus the hit-rate / not-a-buy-sell-signal guardrails; page index 3 still maps
  to the Factor Backtest nav entry.
- Qt-less guard: with `PySide6` forced unimportable (`sys.modules['PySide6'] =
  None`) the module still imports and the case reports
  `Ran 17 tests ... OK (skipped=17)` with 0 errors, so a machine without Qt
  keeps `unittest discover -s tests` green instead of failing collection.

Not run: a real GUI launch (interactive desktop only), a live `run_backtest`
(needs network + NSE symbol list), the report/analysis workers, a full
`--refresh` scan, the Ollama path. UI paint/layout is not visually inspected;
only widget state and rendered text are asserted.


## 2026-10-10 - get_market_analysis made cache-first

Code changed: `tools.py`; new file `tests/test_cached_market_analysis.py` (`CHANGES.md`
entry added). No engine, cache, or data-source changes.

Checks run:

- `ast.parse` on `tools.py` and `tests/test_cached_market_analysis.py`: passed.
- `import main, brain, tools, ui`: passed.
- Full suite: `.\venv\Scripts\python.exe -m unittest discover -s tests`
  -> `Ran 133 tests in 0.214s - OK` (108 -> 133; 25 new offline tests).
- Live cache-first call `tools.get_market_analysis()` returned instantly from
  the saved Market Lab report (no scan): correct regime/breadth/VIX/
  derivatives/flow/event-risk and honest MOMENTUM/RELATIVE_STRENGTH/
  RELATIVE_VOLUME = NOT_AVAILABLE with a pointer to FULL REFRESH.
- Scanner fall-back exercised in tests with a stubbed `scan_market()` result
  (no network): produces the original full ranking sections.
- `get_market_analysis()` dispatch verified with mocks: report present ->
  `scan_market()` NOT called; no report -> `scan_market()` called once;
  empty scanner frame -> clean MARKET ANALYSIS ERROR.

Not run: a real full `scan_market()` NSE scan, GUI launch, Ollama path. The
assistant `get_market_analysis()` still triggers a scan only when NO saved
Market Lab report exists (the previous always-scan behavior is now the
no-cache fall-back).


## 2026-10-10 - Cache-first pipeline integration tests

Code changed: `tools.py` (`get_market_brief` now reuses the shared
`_load_latest_market_lab_report()` loader instead of duplicating the cache
glob; behavior preserved). New file `tests/test_pipeline_integration.py`.
Removed approved scratch files from the repo root (`run_test.py`,
`test_fix.py`, `test_verify.py`, `test_output.txt`; never committed).

Checks run:

- `ast.parse` on `tools.py` and the new test file: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_pipeline_integration -v`
  -> `Ran 19 tests in 1.224s - OK`.
- Full suite: `Ran 152 tests in 1.398s - OK` (133 -> 152; 19 new).
- Live read-only `get_market_brief()` against the real cache still returns a
  valid brief (source report ~0.0h fresh).

Integration coverage now in place (all offline, cache redirected to a temp
dir so the real cache is never written): save/load round-trip + guardrail
survival + newest-file selection; `get_market_brief`/`get_market_analysis`
read the temp cache; `get_market_analysis` never scans when a report exists
and falls back to the scanner only on an empty cache; brief and analysis
agree on the same measured facts; stale/missing handled consistently.

Not run: GUI launch, a real `scan_market()` run, the Ollama path.


## 2026-10-10 - Assistant tool-registry + run_tool contract tests

No production code changed. New file `tests/test_tool_contract.py`.

Checks run:

- `ast.parse` on `tests/test_tool_contract.py`: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_tool_contract -v`
  -> `Ran 15 tests in 0.164s - OK`.
- Full suite: `Ran 167 tests in 1.395s - OK` (152 -> 167; 15 new).
- `import brain` offline: passed (imports ollama client module only, no server
  connection).

Coverage added (all offline): TOOLS/TOOL_SCHEMA lock-step + schema
well-formedness; `run_tool` never raises (unknown tool, JSON-string args,
malformed/non-dict args, bad-arguments path) using side-effect-free tools
only; `get_market_brief` dispatch through `run_tool` (loader stubbed); brain
coupling (schema identity + dispatchability).

Not run: Ollama tool-calling turn, GUI launch, real NSE scan, live
open_website/open_app/search execution (deliberately avoided side effects).


## 2026-10-10 - Live end-to-end check (terminal-integrated)

Live, terminal-driven verification of the integrated stack on the user machine
(AST Sat 2026-10-10, NSE closed). This closes the live-path validation gap noted
above. Cache-first / live-only paths used; no forced `--refresh` full scan.

Services and environment:

- Ollama: UP, model list `['qwen3.5:4b']` (the exact configured model).
- SearXNG: UP (`http://localhost:8080` -> HTTP 200).
- Entry points present: `main.py`, `market_lab_ui.py`,
  `market_lab/market_lab_data.py`, `tools.py`, `brain.py`.
- Cached NSE scans: 28; newest `market_scan_20261010_123734.csv`.

Checks run and results:

- Cache-first Market Lab terminal report
  `.\venv\Scripts\python.exe -B -u market_lab\market_lab_data.py`: exit 0, 356
  lines, "Using fresh cached market scan (1,999 stocks; 6.2 hours old)",
  `Stocks analyzed: 1,999`, no full scan. Guardrails intact:
  `BUY_SELL_AUTHORIZATION: False`, `TRADING_EXECUTION: False`; event risk
  MODERATE; volatility regime MODERATE. No ERROR/Traceback.
- Live Ollama tool-calling turn (`brain.think('Give me the morning market brief
  please.')`): the model emitted a `get_market_brief({})` tool call, the tool
  returned the full cache-first brief (BEARISH regime, VIX 14.38, FII/DII flow,
  signal-eligible NO, event risk), and the model produced a grounded
  natural-language summary. Full brain -> tool -> cache path confirmed live.
- Live Market Lab GUI (`QT_QPA_PLATFORM=offscreen`): `MarketLabWindow` built and
  shown, `load_initial_report` fired, background worker started, and it fetched
  real NSE option chains (NIFTY spot 22,520.45, OI PCR 1.12; BANKNIFTY spot
  55,256.65, OI PCR 0.93). Report headless-construction check:
  `GUI_OK: ... visible=True, title='NOVA MARKET LAB', workers_started=1`.
- Live main-assistant GUI (`offscreen`):
  `MAIN_GUI_OK: NovaWindow constructed and shown (visible=True, title='NOVA —
  Personal Intelligence System')`, no error.

Findings / notes:

- Both GUIs were verified via headless (offscreen) construction by a temporary
  driver that shows the window, lets startup run ~3 s, then force-exits to avoid
  the non-daemon report worker keeping the process alive; no window flashes on
  the desktop and the real caches are not written.
- The offscreen Market Lab run does perform a live data refresh (option chains,
  index/volatility), so it makes read-only network calls; quantities are the
  normal lightweight live layers, not a full 2,333-stock scan.
- Event calendar was confirmed FRESH earlier today (18.4 h old at check time).
  It crosses the 24 h staleness threshold around 12:11 IST on 2026-10-11 and
  then needs a re-check (`touch_event_calendar.py`), else event risk reverts to
  NOT_AVAILABLE/UNKNOWN the next day. Not re-stamped during this live session.

Not run: forced `--refresh` full scan, a visible (on-desktop) GUI session for the
user to click through, and `open_website/open_app/search_web` side effects.


## 2026-10-10 - Market Lab clean shutdown on window close

Code changed: `market_lab_ui.py`; `tests/test_gui_smoke.py` (`CHANGES.md` entry
added). No engine, cache, or data-source changes.

Context: a user-reported orphan — closing the Market Lab window while a
background worker ran refused to close and, when force-closed, left
`indian-market-mcp.exe` (spawned by `nse_feed.stdio_client`) running.

Checks run:

- `ast.parse` on `market_lab_ui.py` and `tests/test_gui_smoke.py`: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_gui_smoke -v` -> 20 tests OK
  (was 17; +3 new `TestCleanShutdown`).
- Full suite: `Ran 170 tests ... OK` (167 -> 170).
- `import market_lab_ui` offline: passed.
- Live: `nse_feed.get_market_status()` ran one MCP round-trip and its
  `indian-market-mcp.exe` exited on its own; a final Win32_Process sweep
  (excluding the probe's own command line) found 0 MCP servers and 0 Nova UI
  processes — no orphan.

New behavior locked in by tests: close stops the auto/display timers and blocks
`start_task` via `_shutting_down`; a running worker is waited on (up to
`CLOSE_WORKER_WAIT_MS`) so `stdio_client` tears down its subprocess, then the
close is accepted; an idle close accepts immediately.

Not run/verified: a user-initiated, on-desktop close of the real window during
a live refresh (validated headlessly and via the single-call MCP teardown
instead); the `terminate()` last-resort path (only reached if a worker exceeds
the 10s grace window).


## 2026-10-10 - start_nova.py launcher with local-service preflight

Code added: new files `start_nova.py` and `tests/test_start_nova.py` (9 offline
tests). No existing app, engine, cache, or data-source logic changed.

Checks run:

- `ast.parse` on `start_nova.py` and `tests/test_start_nova.py`: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_start_nova -v`
  -> `Ran 9 tests in 0.004s - OK`.
- Full suite: `Ran 179 tests ... OK` (170 -> 179; 9 new).
- Live `.\venv\Scripts\python.exe start_nova.py --check`:
  `[UP] Ollama http://localhost:11434/api/tags (HTTP 200)` and
  `[UP] SearXNG http://localhost:8080 (HTTP 200)` -> "All services are up."

Behavior covered by tests (all offline, `urllib.request.urlopen` patched):
`check_service`/`check_all` return UP/DOWN without raising (connection refused,
timeout); `print_report` returns True only when every service is UP; `main
--check` exits 0 when healthy and 1 when a service is down without launching;
`main market` calls `launch("market")` and never prompts.

Not run: an actual interactive, on-desktop launch of a UI through the launcher
(the Popen path is verified via a mocked `launch()`; the two entry points
themselves were independently live-launched and verified earlier). The preflight
check is advisory only and never blocks a launch.


## 2026-10-10 - pyproject.toml metadata + dependency-free CI gate

Code added: `pyproject.toml` (metadata-only), `tests/test_packaging.py`
(3 tests), `.github/workflows/ci.yml`. No existing app, engine, cache, or
data-source logic changed.

Checks run:

- `pyproject.toml` parses with `tomllib` (Python 3.14); `project.name == nova`,
  `requires-python == ">=3.11"`, 107 dependencies.
- `tests/test_packaging.py`: passes; asserts `pyproject` dependencies ==
  `requirements.txt` (both 107, no drift).
- CI's parse step executed locally: 57 `.py` sources `ast`-parsed with no
  errors (excluding venv/caches/model dirs).
- CI's test step executed locally:
  `python -m unittest tests.test_start_nova tests.test_packaging` -> 12 tests OK.
- Full offline suite: `Ran 182 tests ... OK` (179 -> 182; 3 new).

CI scope (documented in the workflow): dependency-free on `ubuntu-latest` /
Python 3.11 — parse every source + run the two stdlib-only suites. The full
182-test suite is NOT run in CI because the runtime stack (PySide6, torch,
pywin32, numpy, yfinance; Python 3.14) is heavy and Windows-specific; it runs
locally.

Not run here: the GitHub Actions run itself (the workflow's two steps were
executed locally and pass); a full-dependency CI job is intentionally omitted
for the reasons above. `pip install .` is not validated/used (Nova runs from
the local venv).


## 2026-10-10 - Sector engine unit tests (closes coverage gap)

Code added: `tests/test_sector_engine.py` (19 offline tests). No engine, cache,
data-source, or UI code changed.

Checks run:

- `import analysis.data.sector_engine` offline: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_sector_engine -v`
  -> `Ran 19 tests in 0.003s - OK`.
- Full offline suite: `Ran 201 tests ... OK` (182 -> 201; 19 new).

Coverage: the sector engine's pure helpers (`safe_float`, `pct_mean`,
`safe_ratio`) and `determine_sector_regime` — including the STRONG / POSITIVE /
NEUTRAL / NEGATIVE / WEAK boundary scores (5 / 2 / -2 / -5), the
INSUFFICIENT_DATA no-evidence case, and the single-evidence case — are now
locked in. This closes the one engine that had no unit coverage.

Not run: the sector scan/classification path (downloads NSE primary HTML and
reads scanner output) — deliberately out of scope for offline unit tests.
## 2026-10-10 - Event calendar re-check and re-stamp

Data changed: only `analysis/data/event_calendar.json` `source_checked_at`
(2026-10-10T00:11:37+05:30 -> 2026-10-10T19:51:49+05:30). No event entries
altered; the file's original compact formatting preserved (one-line diff).

Checks run:

- Web-verified every upcoming entry against authoritative sources, all
  matching: BLS Oct 2026 schedule (US CPI Sep Oct 14 08:30 ET, PPI Oct 15,
  Import/Export Oct 16); MoSPI/PIB (India CPI Sep Oct 12, 4 pm IST); DPIIT via
  IndiaInflation.com (India WPI Sep Oct 14, 12:00 IST); RBI MPC (Fri Dec 4,
  2026); NSE circular CM-TR71775 / BSE (Dussehra Oct 20, Diwali-Balipratipada
  Nov 10, Guru Nanak Nov 24, Christmas Dec 25, Diwali Muhurat Nov 8).
- `.\venv\Scripts\python.exe check_event_calendar.py` -> RESULT: OK,
  11 valid / 0 invalid, FRESH (0.0h).
- Full offline suite: `Ran 201 tests ... OK` (unchanged; engine tests use
  fixtures, not this data file).

Note: this reset the 24h freshness window that was about to lapse. The next
re-check is due around 19:51 IST on 2026-10-11.

Not run: no event entry was added or edited, so only the timestamp change was
validated.


## 2026-10-10 - Market Lab Event Risk panel (upcoming-events UI)

Code changed: `market_lab_ui.py` (UI-only) + `tests/test_gui_smoke.py`
(12 new tests). No engine, cache, or data-source logic changed; `display_report`
now also populates the new panel but the report itself is untouched.

Checks run:

- `ast.parse` + `import market_lab_ui` offline: passed.
- `MarketLabWindow()` builds with `event_banner`, `event_meta`, `event_view`
  and 5 nav pages (Event Risk appended at index 4, so existing indices unchanged).
- `.\venv\Scripts\python.exe -m unittest tests.test_gui_smoke -v` (with
  `QT_QPA_PLATFORM=offscreen`) -> `Ran 32 tests ... OK` (was 20; +12 new); the
  new tests are: pure `format_event_risk` cases, `_risk_color` levels, and Qt
  `TestEventRiskPanel` (display_report populates banner/meta/list; HIGH banner
  red, MODERATE amber; missing context -> NOT AVAILABLE; stale source shown).
- Live headless render of the real saved report into the panel: banner
  `OVERALL EVENT RISK: MODERATE`, meta `upcoming events: 5 | lookahead: 7 days
  | calendar source: FRESH (within 24h)`, and the full list with IST times and
  live countdowns (e.g. India CPI "in 43.9 h"; countdown recomputed from event
  datetime, not the report's frozen hours_until).
- Full offline suite: `Ran 213 tests ... OK` (201 -> 213; 12 new) both with Qt
  and with Qt absent (Qt-guarded tests skip cleanly).

Not run: an on-desktop click-through of the new page (validated headlessly via
display_report + real widgets, offscreen). No color assertions beyond the
banner; the events list is plaintext (severity shown as [TAG]) consistent with
the other read-only views.


## 2026-10-10 - Market Lab terminal UI redesign

Code changed: `market_lab_ui.py` (layout + renderers), new
`market_lab/view_model.py` (pure adapter), new `market_lab/widgets.py`
(component library); tests `tests/test_view_model.py` (new, 23) and
`tests/test_gui_smoke.py` (+6 `TestTerminalLayout`). No backend, engine, cache,
data-source, `market_lab_data.py` or `market_lab_brain.py` logic changed;
`main.py` (Nova Assistant) untouched.

Architecture:
- `view_model.py` is stdlib-only and reads the real report dict, returning
  UI structures with explicit `N/A` for anything the backend does not provide
  (unit-tested offline).
- `widgets.py` provides the themed, self-contained components; `market_lab_ui`
  wires them to real data in `display_report` and repaints cheap state on the
  existing 1 s ticker. Refresh controls still call the existing
  `get_market_lab_data` through the existing single-flight worker (FULL REFRESH
  = `force_refresh=True`, LIVE UPDATE = `live_only=True`); AUTO toggles the UI
  timer only.

Checks run:

- `ast.parse` on `market_lab_ui.py`, `view_model.py`, `widgets.py`, and both
  test files: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_view_model` -> 23 OK.
- `.\venv\Scripts\python.exe -m unittest tests.test_gui_smoke` (offscreen)
  -> `Ran 38 tests ... OK` (was 32; +6 `TestTerminalLayout` locks the 10 ordered
  sections, header chips, guardrails footer, collapse/expand, real dashboard
  values, and that missing data renders N/A rather than a fabricated number).
- Offscreen render of the real saved report through the rebuilt
  `MarketLabWindow`: header `data age 1.6h`, `1,999 stocks • 1.6h old`,
  `MODE: CACHE-FIRST`, `SESSION WEEKEND`, `VIX 14.38`, `SAVED REPORT`; NIFTY
  22,520.45 +1.30% with OHLC, BANK NIFTY 55,256.65 with OHLC N/A; indicators
  RSI/MACD N/A, ATR 263.48 pts, VOL 13.74 %; breadth; top sectors; factor top-10
  rank order; all ten report sections present in order with availability chips
  (04 PARTIAL, 07 CONTEXT_ONLY, 09 NOT_AVAILABLE, 10 ACTIVE).
- Full offline suite (offscreen): `Ran 242 tests ... OK` (213 -> 242; +29).
- Real entry point launched (`.\venv\Scripts\python.exe -B -u market_lab_ui.py`,
  pid 56200, status running): performed a live-only refresh over the cached
  1,999-stock scan and fetched real NIFTY (spot 22,520.45, expiry 13-Oct) and
  BANKNIFTY (spot 55,256.65, expiry 27-Oct) option chains with no Python
  traceback; stopped cleanly afterward with no orphaned `indian-market-mcp.exe`.

Backend-data limitations surfaced honestly in the UI (not fabricated):
per-index RSI/MACD/volume, intraday chart series, 52w highs/lows, McClellan,
portfolio VaR/Sharpe/drawdown, QUALITY/VALUE factors, and the earnings calendar
are all shown as N/A / NOT_AVAILABLE because the saved report does not provide
them. Derived index absolute change / previous close are labeled as arithmetic
on backend values.

Not run/verified here: an on-desktop visual inspection at 1920x1080 and a
smaller width (layout uses QSplitter + QScrollArea and in-place updates; pixel
review is manual); FULL REFRESH (`--refresh`, ~2-3 min full scan) was not
triggered to avoid the heavy scan — it calls the same existing path and is
unchanged.


## 2026-10-10 - Market Lab terminal visual refinement (Step 5)

Code changed: `market_lab_ui.py` and `market_lab/widgets.py` (presentation
only). No backend, engine, data-source, or report-schema change; honesty
preserved.

Checks run:

- `ast.parse` on both files: passed.
- Non-overlap / pin checks (`win.grab()` + widget geometry, offscreen) at
  1920x1080, 1366x768, 1280x720: header fixed at 56px; footer + guardrails bar
  pinned to the bottom (guardrails_bottom == window height) with
  guardrails_y >= footer_bottom at every size (no overlap).
- Offscreen render of the real report: header badges; index card NIFTY with
  real OHLC snapshot (SnapshotBar) and BANK NIFTY "chart unavailable"; five
  sector rows each with a proportional performance bar; factor top-10 rows with
  right-aligned numerics + 7 availability rows (color-coded).
- Full offline suite (offscreen): `Ran 242 tests ... OK` (unchanged).
- Real entry point launched (`.\venv\Scripts\python.exe -B -u market_lab_ui.py`,
  pid 53256, running) with a live-only refresh over the cached scan; no
  traceback. Launch command for the user: `.\venv\Scripts\python.exe market_lab_ui.py`.

Fixed during refinement: a duplicate stale `render_sector` (referencing the
removed `sector_table`) had shadowed the new sector-rows renderer; removed.

Not verified: human pixel review vs the reference screenshot — this environment
cannot capture/display the rendered window (only geometry + a saved PNG proxy),
so aesthetic judgments (spacing balance, chart aesthetics) remain a manual
step. FULL REFRESH not triggered here.


## 2026-10-11 - Nova Analysis answers about the specific stock asked

Code changed: `market_lab/market_lab_brain.py` (single-stock focus path);
tests `tests/test_market_lab_brain.py` (new, 15). No engine, data-source, or
report-schema change; `market_lab_ui.py` already forwards the question box
text as the `query`, so no UI change was needed.

Checks run:

- `ast.parse` on `market_lab/market_lab_brain.py` and the new test file:
  passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_market_lab_brain -v`
  -> `Ran 15 tests in ... OK` (symbol master, watchlist engine and `ollama.chat`
  stubbed; coverage: focus detection incl. benchmark/unknown tokens and the
  uppercase fallback, focus payload availability/honesty + `_json_safe`, payload
  shaping, focused vs broad prompt branching, data-error path).
- Real, un-stubbed checks against the cached symbol master:
  `_extract_focus_symbol` -> "tell me about RELIANCE" = RELIANCE;
  "what about bank nifty" and "market overview" = "" (broad);
  `_focus_payload("RELIANCE", <latest cached report>)` returned a real
  watchlist snapshot (price present, RSI, trend STRONG_DOWNTREND), company name,
  and honest factor/technical membership (not in stored extremes).
- Full offline suite: `Ran 257 tests ... OK` (242 -> 257; 15 new).

Known limitation (documented): focus detection matches ticker tokens, not
company names, so "infosys" does not resolve to `INFY` — the user types the
ticker. Weekend/live data unavailability is surfaced honestly as an
UNAVAILABLE snapshot rather than demo values.

Not run here: a live Ollama turn through the running app (Ollama inference is
not exercised in this environment); the deterministic prompt-branch + payload
behavior is verified by the stubbed tests, and the launcher path is unchanged.


## 2026-10-11 - Dhan market-data adapter (Step 1 data layer, read-only)

Code added: `analysis/data/dhan_feed.py` (new); `analysis/data/market_universe.py`
(`ENABLE_DHAN` + opt-in Dhan attempt in `get_price_history`); tests
`tests/test_dhan_feed.py` (new, 21). `.gitignore` updated. No change to the NSE
MCP path code (Dhan is attempted only when `ENABLE_DHAN and dhan_configured()`;
any Dhan error falls through to the existing NSE MCP -> Yahoo chain).

Analysis-only boundary: the adapter uses only Dhan market-DATA endpoints
(`POST /v2/charts/historical`); it contains no order/position/trade/funds calls
and no broker/execution behavior. Verified endpoints/fields against Dhan's docs
(access-token header; securityId/exchangeSegment/instrument/fromDate/toDate
body; parallel open/high/low/close/volume/timestamp response) — none invented.

Checks run:

- `ast.parse` on `analysis/data/dhan_feed.py` and `analysis/data/market_universe.py`:
  passed.
- `import analysis.data.market_universe` (which now imports dhan_feed) and
  `import analysis.data.dhan_feed`: passed; `ENABLE_DHAN=True`,
  `is_configured()=False` (no token) -> default behavior unchanged.
- `.\venv\Scripts\python.exe -m unittest tests.test_dhan_feed -v` -> 21 OK.
- Full offline suite (offscreen): `Ran 278 tests ... OK` (257 -> 278; 21 new).

Test coverage (all offline; `requests.post`, config path and cache dir stubbed
to temp dirs): Dhan payload -> OHLCV DataFrame (columns/index/tz), mismatched
arrays and payload-shape errors, Dhan error code (DH-905) -> RuntimeError,
network-exception propagation, cache round-trip + 16h staleness gate + miss,
token via env/config, unmapped-symbol honest error, unconfigured error, and the
`get_price_history` wiring (prefer Dhan when configured; skip when not; fall
back to NSE MCP on Dhan failure).

Not run here (no Dhan token/plan in this environment): a live Dhan historical
fetch; and the live NSE MCP smoke (`test_nse_mcp.py`) intentionally not triggered
because the MCP path is unchanged and additive-Dhan is disabled by default, and
running it spawns a persistent `indian-market-mcp.exe` child.

To enable for real (never commit): create git-ignored `dhan_config.json` in the
project root, e.g. `{"access_token": "<jwt>", "equity": {"RELIANCE": "<id>"}}`
(security IDs from Dhan's instrument/scrip master), or set env
`DHAN_ACCESS_TOKEN`, then restart Market Lab. Cached candles land in
`analysis/data/cache/dhan/` with a 16h freshness gate.


## 2026-10-11 - Dhan Step 2: auto security-id map + live quotes

Code changed: `analysis/data/dhan_feed.py`; tests `tests/test_dhan_feed.py`
(+12 -> 33 total). No report-generation / engine wiring; functions are exposed
as adapter primitives for a later, separate integration.

Endpoints verified against Dhan docs before coding (none invented): market
quote `POST /v2/marketfeed/quote` (segments incl. `IDX_I`; fields last_price,
net_change, ohlc, last_trade_time), LTP `POST /v2/marketfeed/ltp`, and the
public instrument master CSV `https://images.dhan.co/api-data/api-scrip-master.csv`
(compact CSV with Security ID + trading symbol).

Checks run:

- `ast.parse` on `analysis/data/dhan_feed.py` and the test file: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_dhan_feed -v` -> 33 OK
  (was 21; +12): instrument-master parse (NSE equity only), header-spelling
  tolerance, non-NSE/non-equity filtering, zero-rows error, 16h cache gate,
  resolve fallback to cached map + config override, `get_index_quote` parse
  (last_price/net_change/OHLC, config index override, unconfigured -> {},
  missing data -> available False), `get_last_price` LTP parse, and
  `get_price_history_dhan` auto-build-on-miss via a stubbed master CSV.
- Full offline suite (offscreen): `Ran 290 tests ... OK` (278 -> 290; 12 new).

Analysis-only unchanged: adapter uses only Dhan data endpoints; no
order/position/trade/funds/broker/execution calls were added.

Not run here: any live Dhan request (no token/data plan in this environment).
Market-feed/LTP functions are NOT yet consumed by the report engines — enabling
a live NIFTY/BANKNIFTY/VIX snapshot through Dhan in `market_lab_data` is a
separate market-data step (would re-run the NSE-MCP smoke per WORKFLOW). Index
IDs default to common Dhan IDs (13/25/26) and are overridable via config; verify
them against your Dhan scrip master.


## 2026-10-11 - Dhan Step 3: opt-in NIFTY snapshot override

Code changed: `analysis/data/dhan_feed.py` and `market_lab/market_lab_data.py`;
tests `tests/test_dhan_feed.py` (+6) and `tests/test_market_lab_data.py` (new,
+5). No NSE-MCP / Yahoo code touched; the override is guarded and default-off.

Behavior: `_dhan_index_overrides()` returns `{}` when Dhan is unconfigured, so
`_apply_dhan_override()` returns the original snapshot unchanged (byte-identical
default path). When configured and a NIFTY quote is available, `nifty_snapshot`
is replaced by the Dhan-derived snapshot (labeled `source: DHAN_LIVE`); an
unavailable entry or any error keeps the original NSE/Yahoo snapshot.

Checks run:

- `ast.parse` + `import` for both modules: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_dhan_feed tests.test_market_lab_data`
  -> `Ran 44 tests ... OK`.
- NSE-MCP stdio smoke: `.\venv\Scripts\python.exe test_nse_mcp.py` ->
  "MCP SESSION: CONNECTED", 68 tools listed, exit 0; no orphaned
  `indian-market-mcp.exe` process afterward. NSE path verified unchanged.
- Full offline suite (offscreen): `Ran 301 tests ... OK` (290 -> 301; 11 new).

Not run here: a live Dhan call (no token/plan in this environment). BANK NIFTY
and India VIX snapshots are produced by the same converter but are not yet
injected into their report sections — a guarded follow-up; NIFTY is wired now
as the single lowest-risk injection point the UI and Section 01 consume.


## 2026-10-11 - Dhan Step 4: opt-in BANK NIFTY + India VIX live override

Code changed: `market_lab/market_lab_data.py`; tests `tests/test_market_lab_data.py`
(+7). No NSE-MCP / volatility-engine code touched; guarded and default-off.

Behavior: `_apply_dhan_volatility_overrides(volatility)` returns the original
when Dhan is unconfigured / neither BANK NIFTY nor VIX is available / any error
(identity preserved). When configured, it merges into a copy:
- `volatility.bank_nifty.price` = Dhan last price (+ `source: DHAN_LIVE`,
  `last_trade_time`); the engine's ATR / realized-vol / regime are preserved.
- `volatility.india_vix.value` and `change_percent` = Dhan (+ note); the
  engine's `percentile_1y` / `regime` / `direction` are preserved (Dhan has
  no percentile/regime). Missing legs are created on demand.

Checks run:

- `ast.parse` on `market_lab/market_lab_data.py`: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_market_lab_data -v`
  -> `Ran 12 tests ... OK` (NIFTY override + BANK/VIX volatility override,
  engine-field preservation, no-mutation, identity on no-override /
  unavailable / error / non-dict, missing-leg creation).
- Full offline suite (offscreen): `Ran 308 tests ... OK` (301 -> 308; 7 new).

Not run here: a live Dhan call (no token/plan). BANK NIFTY/VIX Dhan values land
in the report only when configured; percentile/regime still come from the
volatility engine.


## 2026-10-11 - Real NIFTY / BANK NIFTY charts on the dashboard

Code changed: `market_lab/market_lab_data.py`, `market_lab/view_model.py`,
`market_lab/widgets.py`, `market_lab_ui.py`; tests in `test_gui_smoke.py`,
`test_market_lab_data.py`, `test_view_model.py`. No NSE-MCP path changed;
series come from the same `^NSEI`/`^NSEBANK` daily history the report already
fetches.

Checks run:

- `ast.parse` + offscreen `MarketLabWindow` build: passed.
- Live series fetch: `market_lab_data.build_index_series("^NSEI")` returned 21
  real daily closes (23,431.5 -> 22,520.45); `^NSEBANK` returned 21 points.
- `tests.test_market_lab_data` -> `extract_close_series` OK (values+dates,
  last-N limit, empty/None, missing Close column).
- `tests.test_gui_smoke.TestTerminalLayout` -> 7 OK, incl.
  `test_dashboard_renders_index_chart_from_series` (report series feeds the
  NIFTY chart; BANK NIFTY with no series renders the "no series" empty state).
- `tests.test_view_model` -> `index_card` exposes `series` ([] when absent).
- NSE-MCP stdio smoke: `test_nse_mcp.py` -> "MCP SESSION: CONNECTED", 68 tools,
  no orphan child.
- Full offline suite (offscreen): `Ran 314 tests ... OK` (303 -> 314; 11 new).

Honesty: charts draw only real backend series; on history-fetch failure the
widget shows an explicit "no series in report" state — never synthetic candles.

Not verified visually here: exact pixel appearance of the chart at 1920x1080
(rendered + saved as a PNG proxy, offscreen); the axis/grid/last-price styling
is a programmatic drawing, reviewed via geometry + the rendered PNG size only.
## 2026-10-11 - TradingView-style candlestick charts

Code changed: `market_lab/market_lab_data.py`, `market_lab/view_model.py`,
`market_lab/widgets.py`, `market_lab_ui.py`; tests in `test_market_lab_data.py`,
`test_view_model.py`, `test_gui_smoke.py`. No NSE-MCP path changed; candles come
from the existing `^NSEI` / `^NSEBANK` daily history.

Checks run:

- Live fetch: `build_index_candles("^NSEI")` and `^NSEBANK` each returned 125
  real daily OHLCV candles (e.g. NIFTY 2026-10-09 O 22314.95 H 22580.75
  L 22294.75 C 22520.45 vol 296200).
- Unit tests: `build_index_candles` (parse + index dates, empty, error),
  `index_card` OHLC-from-candle, and dashboard candle wiring + 1M range slice
  -> OK.
- NSE-MCP stdio smoke: `.\venv\Scripts\python.exe test_nse_mcp.py` ->
  "MCP SESSION: CONNECTED", 68 tools, no orphan.
- Full offline suite (offscreen): `Ran 317 tests ... OK` (314 -> 317).

Widget behavior verified offscreen: `display_report` feeds NIFTY/BANK NIFTY the
3M slice (63 bars) to `CandleChart`; `set_chart_range("1M")` re-slices to 22
without a refetch; BANK NIFTY OHLC now derived from its last candle.

Scope: real DAILY candles (not tick data); the last bar tracks the live price
between refreshes. True intraday needs a live feed (the Dhan intraday path when
configured); `CandleChart` will accept that series too. The exact pixel look was
reviewed via offscreen render + a saved PNG only.

## 2026-10-11 - Replace factor panel with an honest "Top Uptrend Stocks" screen

Code changed: `market_lab_ui.py` + `tests/test_gui_smoke.py`. No backend/engine/data change.

Behavior: the right-side factor-ranking panel is removed and replaced with a
Top Uptrend Stocks table (`#, Symbol, Score, Trend`) ranked by the report's real
`top_technical_stocks` technical score (top 15), trend colored; the panel note
states it is a current technical trend/score screen, that long-run growth
fundamentals (value/quality/growth) are NOT computed by Nova, and that it is not
a buy/sell signal. Section 08 (Factor Rankings) is unchanged within the
10-section report.

Checks run:

- `ast.parse` on `market_lab_ui.py`: passed; no `factor_*` attribute references remain.
- Real cached report (offscreen `load_initial_report`): uptrend table lists top
  STRONG_UPTREND symbols (BLUSPRING/ZIMLAB/CPPLUS 100.0, PLASTIBLEN 98.0, ...);
  Section 08 still has its top+bottom tables.
- Empty report: uptrend shows "No technical top-list in this report" plus a
  single "—" row (never invented symbols).
- `tests.test_gui_smoke` -> 44 OK; full offline suite -> `Ran 324 tests ... OK`.

Guardrails: analysis-only preserved; the panel is explicitly labeled a technical
trend screen, not a growth prediction or recommendation.


## 2026-10-11 - Real RSI + MACD on the dashboard indicator cards

Code changed: `market_lab/view_model.py` (presentation) + `tests/test_view_model.py`.
No data-source or engine change — RSI/MACD are computed from the report's index
candles (already produced by the candlestick-chart step) using
`technical_engine.calculate_rsi` / `calculate_macd`.

Checks run:

- `ast.parse` on `market_lab/view_model.py` and the test: passed.
- Real cached report (125 NIFTY candles), offscreen `render_dashboard`: RSI
  36.49 (BEARISH), MACD -28.76 histogram (BEARISH), ATR 263.48 pts (MODERATE),
  VOL 13.74% — all genuine, none fabricated.
- `tests.test_view_model` -> 27 OK (RSI/MACD computed from candles; short
  history and no-candles cases stay honest N/A).
- Full offline suite (offscreen): `Ran 319 tests ... OK` (317 -> 319; 2 new).

Interpretation labels reuse `technical_engine`'s existing thresholds
(RSI 70/30/55/45; MACD macd vs signal); a failing/short series yields N/A rather
than an invented value. Not re-run here: NSE-MCP smoke (presentation-only change;
the MCP path is untouched and was smoke-tested for the candles step).


## 2026-10-11 - Master UI redesign (theme tokens, KPI strip, macro cards, breadth panel, sidebar)

Code changed: `market_lab_ui.py`, `market_lab/widgets.py`, `market_lab/view_model.py`;
tests in `tests/test_gui_smoke.py` (+`TestRedesign`). No backend/engine/cache/refresh
logic changed; every displayed value still comes from the real report.

Checks run:

- `ast.parse` on all changed files; offscreen `MarketLabWindow` build: passed.
- Real app path (`MarketLabWindow` -> `load_initial_report` on the cached report)
  rendered and populated: header 56px; KPI NIFTY 22520.45 +1.30%, INDIA VIX 14.38
  (-5.89% 1D), ADVANCES 1169 (59.2%), DECLINES 807 (40.8%), A/D 1.45; Section 01
  shows the BEARISH regime card; Section 02 stacked bar has 2 segments; index
  candles 63; RSI 36.49 BEARISH, MACD -28.76 BEARISH, ATR 263.48, VOL 13.74%.
- `tests.test_gui_smoke` -> 43 OK (incl. `TestRedesign`: KPI populate, missing-KPI
  N/A, macro regime label, breadth StackBar 2 segments).
- `tests.test_view_model` (breadth A/D fallback) -> OK.
- Full offline suite (offscreen): `Ran 323 tests ... OK` (319 -> 323; +4).

Guardrails: analysis-only preserved; unsupported nav items (Indices, Sectors, Stocks,
Screeners, News, Tools) are disabled and honestly labeled — no fake pages; Watchlist
is a working shortcut to the Nova Analysis page. Missing KPIs render `N/A`, never a
fabricated number.

Visual verification (honest limitation): the window was rendered headless (offscreen)
and a PNG proxy saved, but this environment cannot display/compare pixels, so the
exact match to the reference screenshot still needs manual review. Deviation: the
left rail is a wider column (~230-260px) because the sector panel is stacked beneath
it; native window controls are used (no custom title bar).


## 2026-10-11 - Institutional UI upgrade for Sections 03-08

Code changed: `market_lab_ui.py`, `market_lab/widgets.py`, `market_lab/view_model.py`,
`tests/test_gui_smoke.py`. No backend/engine/data-source/cache/refresh change; every
value still comes from the real report.

Components added: `GroupedBarChart`; `_stat_card`/`_cards_row`; view-model summaries
(`sector_summary`, `uptrend_summary`, `flow_series`, `risk_cards`, `factor_summary`).

Checks run:

- `ast.parse` on all changed files; offscreen `MarketLabWindow` build passed.
- Real app path (`load_initial_report`) renders: 03 summary + table with 5 real
  Perf bars; 04 summary + 10 real score meters + availability chips; 05 summary +
  NIFTY/BANK NIFTY table + `positioning_interpretation` card + unusual-OI table;
  06 summary + one `GroupedBarChart` (FII vs DII 5D/10D/20D) + table; 07 vol cards
  (realized vol 20D/60D, ATR %, percentile, regime, exp move) + N/A VaR/Sharpe/
  drawdown; 08 coverage + top + bottom tables.
- Geometry at 1600x900: footer ends at y=866, guardrails y=866..900 pinned to the
  bottom, no overlap; PNG proxy saved (`nova_sections_upgrade.png`, ~24 KB).
- `tests.test_gui_smoke` -> passes (updated 03 -> 6 cols w/ Perf, 04 -> 5 cols w/
  Meter, 08 -> >=2 tables); `tests.test_view_model` -> passes.
- Full offline suite (offscreen): `Ran 324 tests ... OK` (unchanged count; existing
  column-count test updated to the new, richer columns — no test removed/skipped).

Data actually connected: sector 20D/RS/regime; technical score+trend + counts;
derivatives spot/expiry/PCR/max-pain/ATM IV/walls/positioning/unusual OI; FII/DII
5D/10D/20D + regime + streaks + coverage; risk realized-vol/ATR/percentile/regime/
expected move; factor method/universe/as-of/top+bottom composite z.

Data honestly NOT shown (backend limits): per-strike OI-distribution chart
(option_chain in the report is only row counts), per-date FII/DII history (only
5D/10D/20D sums + source_counts), portfolio VaR/Sharpe/drawdown, and per-factor z
(null in report) — all rendered as notes/`N/A`, never fabricated.

Manual-only: pixel match vs the reference screenshot (rendered offscreen + PNG
proxy; this environment cannot display the window).


## 2026-10-11 - AI Stock Analysis terminal (per-stock; any symbol)

Code added/changed: `market_lab/stock_adapter.py` (new),
`market_lab/market_lab_brain.py` (+`analyze_stock_report`, `STOCK_SYSTEM_PROMPT`),
`market_lab/market_lab_ui.py` (Stock Analysis page + nav reorder + off-page
targets + `stock_analysis` worker + `CandleChart.set_overlays` + `QComboBox`
import), `market_lab/widgets.py` (MA overlays), tests in
`tests/test_stock_adapter.py`, `tests/test_market_lab_brain.py`,
`tests/test_gui_smoke.py`. No backend/engine/cache/refresh change.

Checks run:

- REAL adapter run for RELIANCE (live NSE-MCP path, child cleaned up): resolve ->
  "Reliance Industries Limited" (NSE); metrics price 1170.30, RSI 35.42, MACD
  -26.80, ATR 22.22, trend STRONG_DOWNTREND, timestamp 2026-10-09 (last session);
  126 daily candles with MA20/MA50 overlays. Confirms the per-stock path works
  for any symbol, not a hardcoded stock.
- `tests.test_stock_adapter` -> 10 OK (resolve, candles+MA, empty/error, kpi,
  data_quality partial/unavailable, market context).
- `tests.test_market_lab_brain` incl. `TestAnalyzeStockReport` -> OK (focused
  report + disclaimer, mode quick/full prompt, empty-response error, 404
  model-not-found).
- `tests.test_gui_smoke` -> 46 OK (nav reorder to 6 pages/backtest page 4,
  Stock Analysis page renders identity/KPIs/chart/report/data-quality and an
  honest no-data state).
- Full offline suite (offscreen): `Ran 339 tests ... OK` (324 -> 339; +15).

Data connected per stock: symbol/company/exchange; price + change (N/A when the
live change is unavailable, e.g. weekend); high/low/volume; 52W H/L; RSI/MACD/
ATR/EMAs/returns/trend/momentum via `technical_engine.analyze_stock`; daily
OHLCV candles + MA20/50/200 via `get_price_history`; an AI report via the
existing Ollama client.

Data honestly UNAVAILABLE (backend limits, never fabricated): fundamentals, stock-
level institutional holdings, stock-level derivatives/options, support/
resistance levels, VaR/Sharpe/drawdown — all rendered as UNAVAILABLE cards /
data-quality states. Market-wide (regime/VIX/FII/DII) is shown only in a small,
clearly-labeled secondary panel.

Not run here: a live Ollama turn through the UI (Ollama available; verified the
focused prompt with a stubbed chat and the disclaimer; a real turn is manual),
and the 1600x900 pixel comparison to the reference (render + PNG proxy only). 
  
## 2026-10-11 - PyQtGraph stock chart + Lucide-style icons
Code changed: market_lab_ui.py, market_lab/widgets.py, market_lab/stock_adapter.py, market_lab/icons.py (new); tests in test_gui_smoke.py (+TestPyQtGraphAndIcons) and test_stock_adapter.py (+TestOscillators). No backend/engine/cache/Ollama/data change.  
  
Code changed: market_lab_ui.py, market_lab/widgets.py, market_lab/stock_adapter.py, market_lab/icons.py (new); tests in test_gui_smoke.py (+TestPyQtGraphAndIcons) and test_stock_adapter.py (+TestOscillators). No backend/engine/cache/Ollama/data change.

Checks run:

- `ast.parse` on all changed files; offscreen `PmoneygCandleChart` build: 4 plots (price, volume, rsi, macd) and a PNG proxy saved (~9 KB); full Stock Analysis page render uses `PgCandleChart` (page PNG ~26 KB).
- `tests.test_gui_smoke` -> 46 OK (incl. `TestPyQtGraphAndIcons`: icons render, PgCandleChart builds, empty-data safe) and `tests.test_stock_adapter` -> oscillator tests OK.
- Full offline suite (offscreen): `Run 345 tests ... OK` (339 -> 345; +6).

Real data connected: candles + MAs from `get_price_history`; RSI/MACD/signal/hist
computed from the same candles via `technical_engine` (no new math). No synthetic
bars are ever drawn; short/missing series are omitted.

Not applied (compatibility): qt-material — its palette conflicts with the existing
NOVA theme tokens, so the custom QSS theme is retained (per the "only if
compatible" instruction).

Manual-only: the 1600x900 visual comparison against the reference screenshot
(rendered headless + PNG proxy; this environment cannot display the window).


## 2026-10-11 - Fix corrupted stock chart (non-finite + future-date validation)

Root cause: NaN warm-up values from `calculate_rsi`/`calculate_macd` and a
fallback epoch for unparsed dates were passed to pyqtgraph, producing vertical
spikes and view-box explosion (RSI ±50000, huge DIY candles, MACD lines). The
source data was clean; the defect was rendering/validation.

Code changed: `market_lab/stock_adapter.py` (`to_epoch`, `validate_candles`),
`market_lab/widgets.py` (`PgCandleChart.set_data` validation + x pinning + RSI
0-100 lock), tests in `tests/test_stock_adapter.py` (+6) and
`tests/test_gui_smoke.py` (+1).

Checks run:

- `tests.test_stock_adapter` -> `TestValidateCandles` OK (sorting, dedupe,
  original-index alignment, future/bad-date/bad-OHLC drops with diagnostics).
- `tests.test_gui_smoke.TestPyQtGraphAndIcons` -> OK incl.
  `test_pg_skips_nonfinite_and_future` (NaN warm-up + future candle must not
  raise; price axis stays finite and pre-2065; RSI axis bounded ~[-5, 105]).
- Real RELIANCE render: shared x-axis 2026-04-09 -> 2026-10-09; price y
  ~1134-1500; volume y 0-46M (own axis); RSI y -2..102; MACD y -32.7..9.1
  (own axis). Suspicious input logged: `[CHART DATA] dropped rows: future=1`.
- Full offline suite (offscreen): `Ran 353 tests ... OK` (all pass).

Guardrails: no synthetic candles/bars; invalid series are dropped with an
explicit diagnostic rather than plotted; the chart never fabricates dates or
prices.


## 2026-10-12 - Premium ANALYZE button (Stock Analysis only)

Code changed: `market_lab_ui.py` (new `AnalyzeButton` + `ANALYZE_BUTTON_QSS`;
creation + enable/disable sites now use `set_busy`). Only this button's styling
and label toggle changed; `run_stock_analysis`, search, mode, range, and result
rendering are untouched. No new dependencies.

Checks run:

- `ast.parse` on `market_lab_ui.py`: passed.
- Offscreen build: objectName `analyzePrimaryButton`; QSS contains the cyan
  gradient + `#00D9F5` + `border-radius: 12px` + `:hover`/`:pressed`/`:focus`/
  `:disabled`; lightning icon present; `set_busy(True)` -> text `ANALYZING …`,
  disabled; `set_busy(False)` -> text `ANALYZE`, enabled.
- `tests.test_gui_smoke` -> 52 OK (incl. `test_analyze_button_is_premium_and_toggles`).
- Full offline suite (offscreen): `Ran 354 tests ... OK` (353 -> 354).

Not verified visually here: the on-screen hover/press/focus pixel rendering and
the Enter-key chip position across widths (logic verified headlessly; the chip
auto-hides below ~90px of free width and is repositioned in `resizeEvent`).


## 2026-10-12 - AI Research Report redesigned (structured, tabbed)

Code changed: `market_lab_ui.py` (report section only), new
`market_lab/report_parser.py`, `tests/test_report_parser.py` (10),
`tests/test_gui_smoke.py` (+2). No engine/data-source/AI-integration change.

Checks run:

- `ast.parse` on `market_lab_ui.py` and `market_lab/report_parser.py`: passed.
- `tests.test_report_parser` -> 10 OK (numbered-heading split, raw preserved,
  bias incl. INSUFFICIENT EVIDENCE, level extraction, plain-text fallback,
  disclaimer/preamble lines skipped).
- `tests.test_gui_smoke.TestStockAnalysisPage` -> OK incl.
  `test_report_is_structured_with_tabs` (4 tabs: Technical Analysis /
  Fundamental Context / Business Overview / Risks & Outlook; raw report kept;
  bias rendered; no oversized "UNAVAILABLE" card) and
  `test_copy_report_action_exists`.
- Offscreen render of the structured report: tabs present with the 4 expected
  labels, bias card shown, raw report preserved, page PNG proxy saved.
- Full offline suite (offscreen): `Ran 366 tests ... OK` (354 -> 366).

Honesty: bias and evidence come only from the AI report's own text; absent
support/resistance and fundamentals are explained as limitations, never
rendered as oversized cards or implied to be zero; the disclaimer stays
compact and the previous successful report is preserved on a failed re-run.

Not verified visually here: the on-screen tab/scroll/animation rendering and
resize behavior at multiple widths (rendered offscreen + PNG proxy only).


## 2026-10-12 - Stock Analysis page rebuilt (two-column, no chart)

Code changed: `market_lab_ui.py` (Stock Analysis page only),
`market_lab/stock_adapter.py` (`stock_observations`, `stock_sector`), tests in
`tests/test_gui_smoke.py` and `tests/test_stock_adapter.py`. No engine,
data-source, Ollama, cache, CLI or guardrail change.

Shape (per the reference): controls panel on top; left "Stock Overview"
(identity, four KPI cards, Key observations); right "AI Research Report"
(header, Executive Summary + Overall Bias, Bullish/Bearish factors, slim Key
Price Levels, collapsed raw report). No chart, no tabs, no oversized
UNAVAILABLE cards, no giant raw-text box. `ResponsiveRow` stacks the two
columns when narrow. Empty state before analysis: "Ready to analyze a stock".

Checks run:

- `ast.parse` on `market_lab_ui.py` and `market_lab/stock_adapter.py`: passed.
- Offscreen render before analysis: empty-state heading + subtitle present.
  After `render_stock_result`: Stock overview / Key observations / AI Research
  Report / Executive Summary / Overall Bias / Bullish factors / Bearish factors
  / Key price levels all present; bias rendered; Copy button present; raw report
  hidden by default but preserving the full text; no chart widget; page PNG
  proxy saved.
- `tests.test_gui_smoke.TestStockAnalysisPage` -> OK (structure, empty state,
  copy action, no-data honesty) and `tests.test_stock_adapter` -> OK
  (observations, sector, kpi, candles, oscillators, validation).
- Full offline suite (offscreen): `Ran 371 tests ... OK` (366 -> 371).

Honesty: Key observations derive only from present metric fields; Key Price
Levels state "support/resistance not calculated" when the engine provides none
and never imply zero; market-wide FII/DII is labeled as market-wide context; the
analysis-only disclaimer is compact. Observations use existing engine
conditions (rsi/macd) — no new indicator math.

Not verified visually here: the on-screen render at 1600x900 and the narrow
(stacked) layout, plus the final pixel match to the reference (rendered
offscreen + PNG proxy only).


## 2026-10-13 - NIFTY 50 + INDIA VIX index cards (Market dashboard)

Code changed: `market_lab/market_lab_data.py` (report now carries
`india_vix_candles` for `^INDIAVIX`), `market_lab/view_model.py` (new
`vix_card()`, `index_card()` gains `source_label`), `market_lab_ui.py`
(index cards with a chart kind + trend marker, shared 1M/3M/6M range selector),
tests in `tests/test_view_model.py` and `tests/test_gui_smoke.py`. Reused the
existing chart widgets (`CandleChart`, `LineChart` from `market_lab/widgets.py`);
no new dependency.

Checks run:

- `ast.parse` on `market_lab_ui.py`, `market_lab/view_model.py`,
  `market_lab/market_lab_data.py` and the two test files: passed.
- `tests.test_view_model` -> OK (NIFTY live-quote vs saved-history label,
  VIX card from live quote, VIX fallback to series, VIX empty -> N/A, VIX
  5/20/60-session changes computed from the VIX series).
- `tests.test_gui_smoke` -> 55 OK (candles + line charts, independent scales,
  range selector updates both cards, missing VIX history -> N/A and an empty
  line series, never synthetic data).
- Fresh report regenerated with `market_lab\market_lab_data.py --json`:
  `india_vix_candles` = 125, `nifty_candles` = 125.
- Live render against that report: NIFTY 22,721.95 (+1.60%, +359 pts), O/H/L/C
  from the snapshot, 5d -0.24% / 20d -2.89% / 60d -6.63%, 63 candles with MA
  overlays, trend marker; INDIA VIX 14.12 (-7.41%), own scale, 63 points,
  5d +3.75% / 20d +14.89% / 60d +7.38%, trend marker. Page PNG proxy saved.
- Full offline suite: `Ran 377 tests ... OK` (371 -> 377).

Honesty: NIFTY and VIX keep independent y-scales; VIX never uses NIFTY prices.
Missing history renders as N/A or an empty chart, never fabricated candles,
volume, or VIX values; the direction of VIX change is coloured without claiming
it is universally bullish or bearish.

Not verified visually here: the on-screen render at 1600x900 and the exact
pixel match to the reference; rendered headless + PNG proxy only.


## 2026-10-13 - Market Breadth panel upgraded to visual layout

Code changed: `market_lab_ui.py` (dashboard breadth panel only; the report's
Section 02 already used this layout), `tests/test_gui_smoke.py` (+2). No
engine, data-source, cache, or guardrail change; no new dependency.

Checks run:

- `ast.parse` on `market_lab_ui.py`: passed.
- `tests.test_gui_smoke` -> 57 OK (incl. `test_market_breadth_visual_panel` and
  `test_market_breadth_missing_data_is_na`).
- Live render against a fresh report: advances 1,251 (63.0% of movers),
  declines 734 (37.0%), A/D ratio 1.70, stacked bar with 2 segments,
  above EMA20 28.01% / EMA50 27.61% / EMA200 34.97%, strong uptrend 13.26% /
  strong downtrend 43.52%, unchanged 14. A note names the metrics the scanner
  does not compute (new 52-week highs/lows, McClellan Summation).
- Missing-data render (`breadth: {}`): all values N/A, empty stacked bar, no
  zeros or fabricated numbers.
- Full offline suite: `Ran 379 tests ... OK` (377 -> 379).

Honesty: sections that show percentages compute movers as
advances/(advances+declines); when counts are missing the panel shows N/A and
an empty bar rather than substituting values.

Not verified visually here: the exact on-screen pixel match at 1600x900
(rendered headless + PNG proxy only).


## 2026-10-13 - Centralized QSS theme (styles/nova_theme.qss + loader)

Code changed: `market_lab_ui.py` (applies the file-based theme). Added:
`styles/nova_theme.qss`, `market_lab/theme.py`, `tests/test_theme.py` (7
tests). No engine, data-source, cache, guardrail, or widget-behaviour change;
the theme file uses the same tokens, so the rendered appearance is unchanged.

Checks run:

- `ast.parse` on `market_lab_ui.py` and `market_lab/theme.py`: passed.
- `tests.test_theme` -> 7 OK.
- Offscreen render from an unrelated cwd: theme loaded from the project root
  path, `win.styleSheet()` equals the file text, `QFrame#panel` present, KPI
  cards = nifty/vix/advances/declines/ad.
- Full offline suite: `Ran 386 tests ... OK` (379 -> 386).

Honesty: the tokens in the QSS match the Python palette (asserted); the theme
loads by project path, not cwd. Not verified visually: exact pixel match
(offscreen + PNG proxy only).

## 2026-10-16 - Market Lab background plane (cyan technical grid)

Code changed: `market_lab/widgets.py` (`GridBackground` custom-painted backdrop)
and `market_lab_ui.py` (`root = W.GridBackground()` as the central widget).
No backend/engine/data/cache/refresh change; `nova3dcore.py` untouched; theme
system unchanged; native window controls/title bar preserved (no custom title
bar).

Rendering method: a single custom-painted `QWidget` behind all foreground
content (correct widget hierarchy/painting order; no CSS z-index relied on).
Layers back to front: near-flat navy base gradient (`#08151D`/`#061019`/`#050B10`),
restrained teal corner illumination, fixed-logical-spacing grid (minor ~38px,
stronger major every 5th interval, sparse major-intersection dots at
`rgba(0,210,235,0.16)`), thin rounded inset frame (8px radius, ~12px inset,
outer `#123847` + inner `#0C2934`), corner crosshairs, faint diagonal guides in
the corners, and a very faint teal edge glow. Fixed logical spacing keeps the
grid pattern consistent on resize (lines are not stretched); nothing animates
and nothing intercepts input. Opaque cards sit on top so the grid reads only in
gaps and uncovered margins.

Checks run:

- `ast.parse` + `import market_lab_ui` offline: passed.
- `tests.test_gui_smoke` -> `test_window_uses_grid_background` and
  `test_grid_background_paints_without_error` OK; full offscreen suite:
  `Ran 388 tests ... OK`.
- Rendered `GridBackground` alone at 2560x1440 (`screenshots/kilo_bg_render.png`):
  subtle, even, restrained cyan grid on a dark navy plane; no banding or
  excessive density.
- Rendered the full `MarketLabWindow` at 2560x1440 (`screenshots/kilo_marketlab_full.png`):
  background sits behind header, four status chips, left rail, sector panel,
  index cards (NIFTY 50 candle + INDIA VIX line), chart range controls, KPI
  strip, macro/breadth cards, tables, uptrend panel and guardrails; foreground
  remains readable and cards stay opaque.
- Live desktop launch: `.\venv\Scripts\python.exe market_lab_ui.py` ran for
  several seconds with zero stdout/stderr output and no traceback; closed cleanly
  with no orphan process.

Not run: a live `--refresh` full NSE scan (unchanged path; intentionally
avoided), a user click-through of every page (layout/structure verified
headlessly instead).


## 2026-10-30 - Unified design system across both Nova surfaces

Code changed: new files `styles/design_tokens.py` (shared color/typography/
spacing/z-index tokens) and `styles/nova_theme.qss` (rewritten unified
stylesheet covering both surfaces); updated `market_lab/theme.py` and
`ui/theme.py` to load the unified theme with token validation; refactored
`market_lab_ui.py` to import palette tokens from `styles.design_tokens`
instead of local redefinitions; refactored `ui.py` (Nova Assistant) to import
from `styles.design_tokens` and apply the unified theme via `apply_theme(app)`
in `main()`. No backend, engine, cache, data-source, or report-schema change;
analysis-only guardrails preserved unchanged.

Design system:
- `styles/design_tokens.py` — single source of truth: BG #050B10, SURFACE
  #091620, SIDEBAR #061019, TEXT #F2F6FA, GREEN #00E6A0, RED #FF4058,
  AMBER #FFBD4A, BLUE #3198FF, CYAN #00D9F5, PURPLE #B49AFF; freshness tiers
  (green <10 min / amber <2 h / red <12 h / critical >12 h); typography
  (Segoe UI / Consolas), spacing, border-radius, z-index, animation durations.
- `styles/nova_theme.qss` — unified QSS covering both UIs: shell, panels,
  sidebar, header, text inputs, buttons (primary/ghost/danger/nav), tables,
  tabs, dropdowns, toggles, progress bars, sliders, scrollbars, status chips,
  freshness indicators, guardrails banner, auto-refresh/live controls.
- `market_lab/theme.py` / `ui/theme.py` — load the QSS, expose all tokens,
  never raise on missing file.
- `tests/test_theme.py` — updated to validate both `market_lab_ui` palette
  tokens AND `design_tokens` tokens appear in the QSS.

Checks run:

- `ast.parse` on all changed files: passed.
- `import market_lab_ui`, `import ui`: passed (PySide6 available via
  `pythonw.exe`).
- `styles.design_tokens` imports standalone (no Qt dependency): passed.
- Full offline suite (offscreen): `Ran 388 tests ... OK` (unchanged count;
  test_theme.py now validates both UIs' token sets).
- `test_theme_tokens_match_python_palette`: verifies both `market_lab_ui`
  palette constants AND `design_tokens` tokens appear in `nova_theme.qss`.
- QSS brace balance, non-empty load, shell selectors present: all pass.

Not run: on-desktop visual inspection at 1920x1080 (same as prior sessions —
geometry + PNG proxy only). Live Dhan data not configured; placeholder mode
shows "DATA UNAVAILABLE" gracefully. UI paint/layout verified headlessly, not
via human pixel review.

## 2026-11-01 - Stock Analysis page redesign (purple/teal trading terminal)

Code changed: `market_lab_ui.py` (redesigned Stock overview + AI research
report panels), `market_lab/widgets.py` (new `MomentumGauge` radial widget and
`StatusPill`), and `tests/test_gui_smoke.py` (+5 new `TestStockAnalysisPage`
tests). No backend, engine, cache, data-source, or report-schema change;
analysis-only guardrails preserved unchanged.

Checks run:

- `ast.parse` on all changed files: passed (74 files).
- `import market_lab_ui`: passed (PySide6 available via `pythonw.exe`).
- Full offline suite (offscreen): `Ran 397 tests ... OK` (+5 new tests on top
  of the prior 394).
- New tests: momentum gauge present, bias badge renders, key levels table
  present, pin button disabled/enabled transitions, pin adds symbol to
  `watch_symbols`. Prior pin/freshness/sparkline tests retained.

Not run: on-desktop visual inspection (headless offscreen render only); live
Dhan data not configured; `MAX_SYMBOLS` cap path not triggered in tests (watch
list starts empty per test).

## 2026-11-02 - Web dashboard production build

Checks run:

- `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v` - 22 tests OK
  (API, integration, static serving, SPA fallback, traversal, no-dist).
- `.\venv\Scripts\python.exe -m unittest discover -s tests` - 419 tests OK.
- `.\venv\Scripts\python.exe web_main.py --build` - Vite build OK.
- `web_main.py --port 8502` smoke: `/`, `/stock`, `/analysis` 200 HTML;
  `/api/health` 200 JSON; `/api/nope` 404 JSON.

Browser-verified in dev and prod mode: all 3 pages with real cached data, deep
links, `/api/nope` JSON 404. Still not verified: live end-to-end refresh,
scheduler firing, no-cache UI.
