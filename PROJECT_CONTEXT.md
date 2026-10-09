# Project Context

Last audited: 2026-10-09, Asia/Calcutta.

## Goal Of This Context Layer

The user wants Nova to move from copy-paste coding into an AI coding-agent
workflow. Any capable model should be able to open this folder, read the
context files, inspect the current code, and safely continue work without
needing the old chats.

## Current Repository State

- Path: `C:\Users\Anirudh\nova`
- Git status: local Git repository on branch `main`; private GitHub remote
  `origin` = `https://github.com/benalanirudh-pixel/nova.git`. Initial commit
  `e6ff588` pushed on 2026-10-09.
- Runtime: local Windows Python project.
- Package manifest: no `requirements.txt`, `pyproject.toml`, or similar
  manifest was found during the audit.
- Virtual environments: both `venv/` and `.venv/` exist. The populated runtime
  used for dependency inspection is `venv/`.
- Large local assets:
  - `stt_models/` contains local Faster-Whisper model files.
  - `voices/` contains Piper voice assets.
  - `analysis/data/cache/` contains generated market data caches.
  - `*.wav`, `*.zip`, and `market_lab_debug.log` are runtime/archive artifacts.

## Product Shape

Nova combines:

- A desktop personal assistant UI.
- A local Ollama chat brain with tool calling.
- Voice input and TTS output.
- A 3D visual core.
- Web/app helper tools.
- Market data and Indian-market intelligence engines.
- A separate Market Lab UI for integrated market reports and AI interpretation.

## Current Main Entry Points

- `main.py`: starts `NovaWindow` from `ui.py`.
- `ui.py`: main PySide6 assistant interface.
- `brain.py`: Ollama chat loop and tool-calling orchestration.
- `tools.py`: tool registry and safe tool execution.
- `market_lab_ui.py`: standalone Market Lab UI.
- `market_lab/market_lab_data.py`: cache-first Market Lab report generator.
- `market_lab/market_lab_brain.py`: Ollama interpretation layer for reports.
- `voice.py`: local Faster-Whisper voice session system.
- `tts.py`: Piper TTS through the active Python interpreter.
- `nova3dcore.py`: PyOpenGL visual core used by the UI.

## Current Data And Analysis Engines

Under `analysis/data/`:

- `nse_feed.py`: Indian Market MCP adapter.
- `symbol_master.py`: local NSE equity security master cache.
- `market_universe.py`: NSE-first quote/history layer with Yahoo fallback.
- `market_data.py`: direct yfinance helpers for index data.
- `market_scanner.py`: full NSE equity scanner and factor ranking.
- `technical_engine.py`: technical indicators.
- `volatility_engine.py`: volatility and VIX-style context.
- `derivatives_engine.py`: NIFTY/BANKNIFTY options analysis.
- `institutional_flow_engine.py`: FII/FPI and DII flow history and validation.
- `sector_classification.py`: sector classification cache builder.
- `sector_engine.py`: sector and macro-sector intelligence.
- `risk_engine.py`: risk-budget and position-risk calculations.
- `event_risk_engine.py`: event-risk context from supplied event data.

Under `analysis/regime/` and `analysis/sectors/`:

- Additional regime and sector engines used for research/analysis workflows.

## Safety Boundary

The code repeatedly states that Nova is analysis-only. Maintain these
invariants:

- No broker connection.
- No order placement.
- No automatic orders.
- No BUY/SELL authorization.
- No invented market values.
- No claims of institutional activity unless supported by verified engine
  output.

## Known Project Risks

- Git history exists now, but the only off-machine copy is the private GitHub
  repo; keep commits small so rollback stays usable.
- No dependency manifest means environment reproduction currently depends on
  the existing `venv/`.
- Market-data code touches live public endpoints and local caches. Network
  failures and stale caches must be expected.
- Some code paths can be expensive, especially a forced full NSE scan.
- The assistant depends on local services: Ollama, SearXNG, Indian Market MCP,
  audio devices, Piper voice files, and Faster-Whisper model files.
- There are backup/inspection files from previous copy-paste work. Preserve
  them unless the user explicitly asks for cleanup.
