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
- No automated test suite is currently configured.
- Existing `test_nse_*` scripts are manual smoke scripts, not a formal test

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
  suite.
