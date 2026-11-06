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
.\venv\Scripts\python.exe touch_event_calendar.py
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

Launcher with a preflight check of Ollama/SearXNG (never blocks the UI, only
warns):

```powershell
.\venv\Scripts\python.exe start_nova.py main
.\venv\Scripts\python.exe start_nova.py market
.\venv\Scripts\python.exe start_nova.py --check
.\venv\Scripts\python.exe start_nova.py        # opens Nova Desk
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

## Market Data Sources (analysis-only)

- History/quotes come from the Indian Market MCP (primary) with a Yahoo fallback.
- `analysis/data/dhan_feed.py` is an OPTIONAL, read-only Dhan market-DATA
  source for historical candles (feeds the existing technical engine). It uses
  only Dhan `charts/historical` data endpoints — **no** order/position/trade/
  funds endpoints; Nova stays analysis-only. It is cache-first
  (`analysis/data/cache/dhan`, 16h freshness gate) and disabled until configured.
- Enable (never commit): a git-ignored `.env` or `dhan_config.json` in the
  project root with `{"access_token": "<dhan-jwt>", "equity": {"RELIANCE":
  "<securityId>", ...}}`, or env `DHAN_ACCESS_TOKEN`; base URL via `DHAN_BASE_URL`
  and quote `client-id` via `DHAN_CLIENT_ID`. A missing token/id degrades
  gracefully and falls back to the MCP. Security IDs are auto-mapped from
  Dhan's public instrument master (cached under `analysis/data/cache/dhan`,
  16h), so explicit `equity` overrides are optional. The adapter also exposes
  read-only live quotes (`get_index_quote`, `get_last_price`) for future use;
  they are not yet wired into report generation.
- When a Dhan token is configured, `market_lab_data._apply_dhan_override()`
  replaces the report's `nifty_snapshot` with the live Dhan quote (labeled
  `source: DHAN_LIVE`); `_apply_dhan_volatility_overrides()` overrides
  `volatility.bank_nifty.price` and `volatility.india_vix.value`/`change_percent`
  (engine ATR/vol/percentile/regime are preserved). Unconfigured/error leaves the
  existing NSE/Yahoo/volatility values unchanged.

## Manifests and CI

- `requirements.txt` is the locked runtime set for the local `venv`
  (Python 3.14).
- `pyproject.toml` mirrors it as metadata only; `tests/test_packaging.py`
  keeps the two in sync. No build-system; `pip install .` is not the workflow.
- `.github/workflows/ci.yml` is a dependency-free gate (parse every `.py` +
  stdlib-only tests). The full offline suite (242 tests) runs locally because
  the heavy Windows-specific stack is too large for CI:

  ```powershell
  .\venv\Scripts\python.exe -m unittest discover -s tests -v
  ```

## Verification Baseline

Before calling work complete, run checks that match the risk of the change.
At minimum, use syntax/import checks for code edits and update
`docs/VALIDATION.md` with what was actually verified.
