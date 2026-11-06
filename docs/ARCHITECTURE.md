# Architecture

Last updated: 2026-11-03.

## Surfaces

Nova has three user-facing entry points:

| Entry point         | Surface                                     |
|---------------------|---------------------------------------------|
| `main.py`           | Nova Assistant — personal AI desktop UI     |
| `market_lab_ui.py`  | Market Lab — standalone analysis terminal   |
| `terminal_main.py`  | Nova Terminal — unified Bloomberg-style UI  |

All three are PySide6 desktop applications. The original two remain functional;
Nova Terminal merges them into one window.

## Call Graph

```
main.py -> ui.py (NovaWindow)
  -> brain.py           Ollama chat + tool calling (qwen3.5:4b)
  -> tools.py           Tool registry, run_tool dispatcher
     -> analysis/data/* Market data engines
  -> voice.py           Faster-Whisper STT + wake phrase
  -> tts.py             Piper TTS (Windows winsound)
  -> nova3dcore.py      PyOpenGL 3D visual core

market_lab_ui.py -> MarketLabWindow
  -> market_lab/market_lab_data.py    Cache-first report generator
     -> analysis/data/*               All market engines
  -> market_lab/market_lab_brain.py   Ollama AI interpretation
  -> market_lab/view_model.py         Pure report -> UI adapter
  -> market_lab/widgets.py            Themed component library
  -> market_lab/stock_adapter.py      Per-stock analysis adapter
  -> market_lab/report_parser.py      AI report section parser
  -> market_lab/icons.py              Inline SVG icon set
  -> market_lab/theme.py              QSS theme loader

terminal_main.py -> terminal/main_window.py (NovaTerminal)
  -> terminal/pages/market_overview.py   Dashboard (wires market_lab_data + view_model)
  -> terminal/pages/stock_analysis.py    Single-stock (wires stock_adapter + brain)
  -> terminal/pages/nova_ai.py           Chat (wires brain.think)
  -> terminal/pages/institutional.py     FII/DII flows (wires view_model)
  -> terminal/pages/market_lab.py        JSON report + AI narrative
  -> terminal/style.py                   Terminal-specific styling
```

## Analysis Engines (`analysis/data/`)

| Module                          | Responsibility                                    |
|---------------------------------|---------------------------------------------------|
| `nse_feed.py`                   | Indian Market MCP adapter (stdio_client)          |
| `symbol_master.py`              | NSE equity security master cache                  |
| `market_universe.py`            | NSE-first quote/history with Yahoo fallback       |
| `market_data.py`                | Direct yfinance index helpers                     |
| `market_scanner.py`             | Full NSE equity scanner + factor ranking          |
| `technical_engine.py`           | RSI, MACD, ATR, EMA, trend, momentum             |
| `volatility_engine.py`          | VIX context, realized vol, ATR, regime            |
| `derivatives_engine.py`         | NIFTY/BANKNIFTY option chain analysis             |
| `institutional_flow_engine.py`  | FII/DII flow history + primary-source validation  |
| `sector_classification.py`      | Sector classification cache builder               |
| `sector_engine.py`              | Sector + macro-sector intelligence                |
| `risk_engine.py`                | Risk-budget and position-risk calculations        |
| `event_risk_engine.py`          | Event-risk from `event_calendar.json`             |
| `research_factor_engine.py`     | Multi-factor scoring                              |
| `watchlist_engine.py`           | Per-symbol live snapshot                          |
| `dhan_feed.py`                  | Optional Dhan market-data adapter (read-only)     |

Additional engines: `analysis/regime/regime_engine.py`,
`analysis/sectors/sector_engine.py`, `analysis/backtest_harness.py`.

## Nova Desk Live Path

Nova Desk is the main terminal. Its screens live in `web/frontend/src/desk/`.

`web_main.py` serves the FastAPI app (`web/api/main.py`) and the built React
frontend, rebuilding it when the source is newer than `dist`. The lifespan starts the refresh scheduler and the live quote loop.

```
web/api/live_feed.py  (asyncio task, 09:15-15:30 IST Mon-Fri; no holiday calendar)
  -> dhan_feed.get_index_quote          NIFTY, BANKNIFTY, INDIAVIX every 5 s (only if configured)
  -> nse_feed.get_normalized_stock_quote watched stocks every 15 s (max 25, 120 s TTL)
  -> scheduler._broadcast               changed ticks + feed_status heartbeat (10 s)
     -> GET /api/events (SSE)
        -> hooks/useSSE.ts              tick/feed_status -> lib/live.ts store (per-frame batch)
                                        refresh_* -> page refetch
           -> hooks/useLive.ts          useLiveQuote, useFeedStatus, useLiveWatch
              -> App Tape, desk/Equity
POST /api/live/watch    client registers symbols (origin-checked, re-posted every 60 s)
GET  /api/live/snapshot last tick per symbol + status (loaded on every SSE reconnect)
```

Tick shape: `{type:"tick", symbol, ltp, change, change_pct, volume, source,
as_of, max_age_s}`. Missing prices are skipped; failing sources back off up to
300 s and surface in `feed_status`. The live loop never runs the full NSE scan.
Env: `NOVA_LIVE_INDEX_S` (5), `NOVA_LIVE_STOCK_S` (15).

## Data Sources

| Source                | Adapter                     | Notes                                  |
|-----------------------|-----------------------------|----------------------------------------|
| Indian Market MCP     | `nse_feed.py`               | Primary; `indian-market-mcp.exe`       |
| Yahoo Finance         | `market_data.py`, `market_universe.py` | Fallback for history            |
| NSE archives          | `symbol_master.py`, `derivatives_engine.py` | Equity master, option chains |
| NSE FII/DII endpoints | `institutional_flow_engine.py` | Plus Groww secondary mirror         |
| Dhan (optional)       | `dhan_feed.py`              | Candles + live quotes; off by default  |
| Event calendar        | `event_risk_engine.py`      | Local `event_calendar.json`            |
| Sector classification | `sector_engine.py`          | theannexure.com                        |
| Local SearXNG         | `tools.py`                  | `http://localhost:8080`                |
| Local Ollama          | `brain.py`, `market_lab_brain.py` | `qwen3.5:4b`                    |

## Report Pipeline

`market_lab/market_lab_data.py::get_market_lab_data()` is the central gateway:

1. Loads cached NSE equity scan (or runs full scan if `--refresh` / no cache).
2. Aggregates: scanner, regime, breadth, technical, volatility, sector,
   derivatives, institutional flow, event risk, research factors.
3. Optionally applies Dhan live overrides (NIFTY, BANK NIFTY, VIX).
4. Saves JSON to `analysis/data/cache/market_lab/`.
5. Returns the report dict consumed by all three UIs.

**Modes:** `CACHE_FIRST` (default), `FORCED_REFRESH` (`--refresh`),
`LIVE_ONLY` (`--live-only`; updates live layers without a full scan).

## Design System

`styles/design_tokens.py` is the single source of truth for colors, typography,
spacing, z-index, freshness tiers, and the guardrail text. The unified QSS
lives in `styles/nova_theme.qss`; loaders in `market_lab/theme.py` and
`ui/theme.py`.

## Cache Layout

| Path                                      | Contents                        |
|-------------------------------------------|---------------------------------|
| `analysis/data/cache/scanner/`            | NSE equity scan CSVs            |
| `analysis/data/cache/institutional_flow/` | FII/DII flow cache              |
| `analysis/data/cache/derivatives/`        | Option chain cache              |
| `analysis/data/cache/sector/`             | Sector classification cache     |
| `analysis/data/cache/market_lab/`         | Saved Market Lab JSON reports   |
| `analysis/data/cache/dhan/`               | Dhan candles + security map     |
| `analysis/data/data/cache/`               | NSE equity master files         |

Caches are working state. Do not delete during agent work.

## Voice and Audio

- `voice.py` — Faster-Whisper STT, wake phrase, active conversation mode.
- `tts.py` — Piper TTS, `voices/` assets, Windows `winsound` playback.
- `stt_models/` — local Faster-Whisper model files.

## Visual Core

`nova3dcore.py` — PyOpenGL `QOpenGLWidget` with particles and visual states.
Used only by `ui.py` (main assistant).

## Test Suite

`tests/` — 394+ stdlib `unittest` tests (no pytest). All offline.
Run: `.\venv\Scripts\python.exe -m unittest discover -s tests -v`

CI (`.github/workflows/ci.yml`) is dependency-free: ast-parse all sources +
stdlib-only suites. Full suite runs locally only (heavy Windows stack).

## Safety Invariants

Enforced across all market modules:

- **Analysis only.** No broker connection, no order placement, no trade
  execution, no BUY/SELL authorization.
- **No invented data.** Missing/stale/conflicting data is flagged, never
  fabricated.
- **Cache-first by default.** The expensive full NSE scan (2,333 stocks) runs
  only on explicit `--refresh` or when no cache exists.
- **Guardrails visible.** `GuardrailsBar` is always shown in the UI.
