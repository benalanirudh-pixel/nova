# Architecture Map

Last audited: 2026-10-09.

## High-Level Shape

Nova has two primary application surfaces:

```text
main.py
  -> ui.py
     -> brain.py
        -> tools.py
           -> analysis/data/*
     -> voice.py
     -> tts.py
     -> nova3dcore.py

market_lab_ui.py
  -> market_lab/market_lab_data.py
     -> analysis/data/*
  -> market_lab/market_lab_brain.py
     -> Ollama
```

## Main Assistant Flow

`main.py` creates a PySide6 `QApplication`, sets the app name/display name, and
shows `NovaWindow` from `ui.py`.

`ui.py` owns the main desktop experience:

- System/service telemetry using `psutil`, `nvidia-smi`, Ollama tag endpoint,
  and SearXNG health checks.
- Chat UI and worker threads.
- Voice session worker that calls `voice.listen_for_session_event`.
- TTS calls through `tts.speak`.
- Visual core from `nova3dcore.Nova3DCore`.

`brain.py` owns local LLM orchestration:

- Model: `qwen3.5:4b`.
- Provider: local Ollama Python client.
- Tool calling: `TOOL_SCHEMA` and `run_tool` from `tools.py`.
- History trimming: keeps a bounded history after the system prompt.
- Tool rounds: capped by `MAX_TOOL_ROUNDS`.

`tools.py` owns the assistant's callable actions:

- `get_time`
- `get_market_data`
- `get_market_analysis`
- `get_market_lab_analysis`
- `open_website`
- `open_app`
- `search_web`
- `search_youtube`
- `web_research`

Tool safety is centralized in `run_tool`, which normalizes arguments and
returns tool errors as text instead of raising into the chat loop.

## Market Lab Flow

`market_lab_ui.py` is a standalone PySide6 Market Lab terminal.

It uses:

- `get_market_lab_data` from `market_lab/market_lab_data.py`
- `analyze_market_lab` from `market_lab/market_lab_brain.py`

The UI loads the latest saved report if available, supports manual refresh, and
keeps warnings visible for stale/missing data and analysis-only safety.

`market_lab/market_lab_data.py` is the central analysis gateway. Its module
header says normal mode uses the latest cached NSE equity scan and does not run
the expensive full scan unless `--refresh` is used or no usable cache exists.

The report integrates:

- Market scanner.
- Market regime.
- Breadth.
- Technical analysis.
- Volatility.
- Sector intelligence.
- Derivatives intelligence.
- Institutional flow intelligence.
- Event-risk context.

`market_lab/market_lab_brain.py` converts the generated report into a compact
JSON payload and asks Ollama to interpret it. Its prompt requires values,
signs, units, dates, and periods to be preserved exactly.

## Data Sources

Verified from code:

- Yahoo Finance via `yfinance`:
  - `analysis/data/market_data.py`
  - `analysis/data/market_scanner.py`
  - fallback paths in `analysis/data/market_universe.py`
- Indian Market MCP:
  - `analysis/data/nse_feed.py`
  - executable expected as `indian-market-mcp.exe` beside the active Python
    interpreter.
- NSE security master:
  - `analysis/data/symbol_master.py`
  - source URL: `https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv`
- NSE options endpoints:
  - `analysis/data/derivatives_engine.py`
  - option-chain contract and v3 API endpoints.
- NSE FII/DII endpoints plus Groww-labelled secondary mirror:
  - `analysis/data/institutional_flow_engine.py`
- Sector classification:
  - `analysis/data/sector_engine.py`
  - primary source URL in code: `https://theannexure.com/companies`
- Local SearXNG:
  - `tools.py`
  - expected at `http://localhost:8080`.

## Cache Layout

Important cache paths:

- `analysis/data/cache/scanner/`
- `analysis/data/cache/institutional_flow/`
- `analysis/data/cache/derivatives/`
- `analysis/data/cache/sector/`
- `analysis/data/cache/market_lab/` for saved Market Lab JSON reports when
  generated.
- `analysis/data/data/cache/` for NSE equity master files used by
  `symbol_master.py`.

Caches are part of the working local state. Do not delete them during normal
agent work.

## Voice And Audio

`voice.py` implements:

- Local Faster-Whisper STT.
- Adaptive microphone noise detection.
- Wake phrase activation.
- Persistent active conversation mode.
- Deactivation phrases such as "Bye Nova".

`tts.py` implements:

- Piper TTS using `python -m piper`.
- Voice files under `voices/`.
- Windows-only playback through `winsound`.
- A lock to avoid overlapping speech playback.

## Visual Core

`nova3dcore.py` implements a PyOpenGL `QOpenGLWidget` with particles, nodes,
and visual states. It is imported by `ui.py`.

## Safety Invariants

Across market modules, maintain:

- Analysis only.
- No broker connection.
- No order placement.
- No automatic trading.
- No invented market data.
- Explicit handling of missing/stale/conflicting data.
