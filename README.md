# Nova

Nova is a local Windows Python project for a personal AI command assistant and
an Indian-market analysis workbench.

It has two main entry points:

- `main.py` - launches the main Nova assistant desktop UI.
- `market_lab_ui.py` - launches Nova Market Lab.

The project is designed around local tools:

- PySide6 desktop interfaces.
- Ollama for local LLM calls.
- Piper TTS and Faster-Whisper for voice.
- Indian market data engines backed by NSE sources, Yahoo Finance fallbacks,
  cached scans, derivatives analysis, sector analysis, and institutional-flow
  checks.

Nova is analysis-only. It does not connect to a broker, place trades, execute
orders, or authorize automatic BUY/SELL actions.

## Quick Start

From `C:\Users\Anirudh\nova`:

```powershell
.\venv\Scripts\python.exe main.py
```

To open Market Lab:

```powershell
.\venv\Scripts\python.exe market_lab_ui.py
```

To run the cache-first Market Lab report in the terminal:

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py
```

To save a JSON Market Lab report:

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py --json
```

To force a full NSE equity scan:

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh
```

Use `--refresh` carefully. The source code says normal mode is cache-first and
does not run the expensive 2,333-stock scan unless refresh is forced or no
cached scan is available.

## Local Runtime Expectations

- Windows is assumed. `tts.py` uses `winsound`.
- Use `.\venv\Scripts\python.exe` unless the user intentionally switches
  environments.
- Ollama should be running locally for assistant responses and Market Lab AI
  interpretation.
- The current configured model is `qwen3.5:4b` in both `brain.py` and
  `market_lab/market_lab_brain.py`.
- Local web research expects SearXNG at `http://localhost:8080`.
- Voice assets live under `voices/`.
- Faster-Whisper assets live under `stt_models/`.

## Important Files

- `AGENTS.md` - instructions for coding agents.
- `PROJECT_CONTEXT.md` - current repository map and project status.
- `USER_CONTEXT.md` - user preferences and handoff expectations.
- `docs/ARCHITECTURE.md` - architecture and data-flow map.
- `docs/DEPENDENCIES.md` - dependency evidence from imports and the venv.
- `docs/VALIDATION.md` - checks performed and known gaps.
- `docs/WORKFLOW.md` - safe change workflow.
- `docs/MODEL_HANDOFF.md` - how to resume work in another coding model.
- `CHANGES.md` - context and workflow change log.

## Current Caveats

- This folder is a Git repository (branch `main`) with a private GitHub remote
  (`benalanirudh-pixel/nova`). Generated state is excluded via `.gitignore`.
- There is no `requirements.txt` or `pyproject.toml` yet.
- There are two virtual environments: `venv/` and `.venv/`. The populated one
  used during inspection was `venv/`.
- Generated assets and caches are large. Agents should ignore them unless the
  task specifically concerns voice models, audio, or cached market data.
