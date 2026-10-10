# Validation Notes

Last updated: 2026-10-09.

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
- This folder is not currently a Git repository.
- No root `requirements.txt`, `pyproject.toml`, or README existed before this
  context pass.
- The project has two visible app entry points:
  - `main.py`
  - `market_lab_ui.py`
- Both `brain.py` and `market_lab/market_lab_brain.py` configure Ollama model
  `qwen3.5:4b`.
- Market Lab normal mode is cache-first unless refresh is forced or no cache is
  available.
- The current code repeatedly marks market functionality as analysis-only and
  not a broker/order system.

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

## Known Validation Gaps

- The GUI was not launched during the documentation audit.
- No full `--refresh` market scan was run during the documentation audit.
- No live trade/broker behavior exists to validate, and none should be added.
- Automated unit tests now exist for engine math:
  `tests/test_engine_math.py` (32 tests, stdlib unittest). Integration and
  backtest coverage still missing.
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


