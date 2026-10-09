# AGENTS.md

This file is the first handoff point for any coding agent working on Nova.

## Project Identity

Nova is a local Windows Python assistant and Indian-market analysis workbench.
It has two primary user-facing surfaces:

- `main.py` launches the main Nova desktop assistant UI.
- `market_lab_ui.py` launches Nova Market Lab.

The project is a local Git repository on branch `main` with a private GitHub
remote (`origin`: https://github.com/benalanirudh-pixel/nova.git). Make small
commits as part of completed work; do not push to the remote unless the user
asks.

## Required Reading Order

Before changing code, read these files:

1. `README.md`
2. `PROJECT_CONTEXT.md`
3. `USER_CONTEXT.md`
4. `docs/ARCHITECTURE.md`
5. `docs/VALIDATION.md`
6. `docs/WORKFLOW.md`
7. `CHANGES.md`

Then inspect the exact files related to the requested change.

## Agent Rules

- Inspect current files before editing. Do not rely only on previous chat
  context.
- Preserve working behavior. This project was assembled through iterative
  copy-paste coding, so avoid broad refactors unless explicitly requested.
- Keep edits small, reversible, and tied to the current task.
- Do not edit generated/runtime folders unless the user explicitly asks:
  `venv/`, `.venv/`, `__pycache__/`, `stt_models/`, `voices/`,
  `analysis/data/cache/`.
- Do not delete cached market reports, audio files, model files, backups, or
  inspection notes unless the user explicitly asks.
- Never add trading execution, broker integration, order placement, or
  automatic BUY/SELL behavior. Nova is analysis-only.
- For current market data, preserve the existing evidence rules: use the data
  engines, keep measured data separate from interpretation, and flag stale,
  missing, or conflicting data instead of guessing.
- Do not run the expensive full NSE scan unless needed for the task or
  explicitly requested. Prefer cache-first checks first.
- Add comments only where they explain non-obvious behavior. Avoid decorative
  comments and speculative documentation.
- Update `CHANGES.md` when you add or meaningfully change project context,
  workflow, validation, or behavior.

## Common Commands

Use the existing virtual environment unless the user asks otherwise:

```powershell
.\venv\Scripts\python.exe main.py
.\venv\Scripts\python.exe market_lab_ui.py
.\venv\Scripts\python.exe market_lab\market_lab_data.py
.\venv\Scripts\python.exe market_lab\market_lab_data.py --json
.\venv\Scripts\python.exe test_nse_mcp.py
.\venv\Scripts\python.exe test_nse_tools.py
.\venv\Scripts\python.exe check_event_calendar.py
```

The full refresh command is intentionally heavier:

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh
```

## External Services

- Ollama must be running for `brain.py` and `market_lab/market_lab_brain.py`.
- Both brains currently use `qwen3.5:4b`.
- Local SearXNG is expected at `http://localhost:8080` for `web_research`.
- Indian market MCP is launched from the active virtual environment as
  `indian-market-mcp.exe`.

## Verification Baseline

Before calling work complete, run checks that match the risk of the change.
At minimum, use syntax/import checks for code edits and update
`docs/VALIDATION.md` with what was actually verified.
