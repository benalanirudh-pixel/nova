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





