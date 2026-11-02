# Nova

**Local AI-powered Indian market analysis workbench.**

Nova is a desktop and web analysis terminal built for Indian equity markets. It runs entirely on your machine — NSE data, technical analysis, derivatives intelligence, institutional flow tracking, and local AI interpretation — with no cloud dependency and no broker connection.

> **Analysis only.** Nova does not connect to any broker, place trades, or generate buy/sell signals. Every output surface carries this disclaimer.

---

## Screenshots

<p align="center">
  <img src="screenshots/terminal_v2_final.png" alt="Nova Terminal — unified dashboard" width="100%">
</p>

<details>
<summary>More screenshots</summary>

| Market Dashboard | Stock Analysis |
|:---:|:---:|
| <img src="screenshots/dashboard.png" alt="Market Dashboard" width="480"> | <img src="screenshots/stock.png" alt="Stock Analysis" width="480"> |

| Market Lab (Full Report) | Web Dashboard |
|:---:|:---:|
| <img src="screenshots/report.png" alt="Market Lab Report" width="480"> | <img src="screenshots/kilo_marketlab_full.png" alt="Web Dashboard" width="480"> |

</details>

---

## What It Does

### Market Dashboard
- **Index tracking** — Nifty 50, Bank Nifty, India VIX with candlestick charts and range selectors
- **KPI strip** — 7 live indicators with sparklines (Nifty, Bank Nifty, VIX, Advance/Decline, FII, DII, PCR)
- **Market breadth** — Advances vs. declines vs. unchanged with visual bar and EMA-breadth cards
- **Institutional flows** — FII and DII net activity gauges, daily and cumulative
- **Sector heatmap** — Performance grid across NSE sectors
- **Derivatives strip** — ATM IV, PCR, max pain, OI walls at a glance

### Stock Analysis
- **Technical indicators** — RSI, MACD, ADX, ATR, EMA/SMA crossovers
- **Momentum gauge** — Composite 0–100 score with threshold zones (red/amber/green)
- **52-week positioning** — Current price relative to high/low range
- **Multi-period returns** — 1D, 5D, 20D, 60D performance
- **AI research report** — Local LLM generates executive summary, bullish/bearish factors, key price levels, and market context
- **Trend structure** — Higher highs/lows analysis with support/resistance levels

### Market Analysis (Nifty Deep Dive)
- **Derivatives desk** — PCR, max pain, ATM IV, put/call walls, unusual OI activity
- **OI wall visualization** — Strike-level open interest with directional bias
- **Regime assessment** — VIX regime, breadth regime, composite market state
- **Positioning intelligence** — Institutional positioning and flow summary
- **AI narrative** — LLM-generated market interpretation with evidence citations

### Nova Assistant
- Local AI chat powered by Ollama (qwen3.5:4b)
- Voice input (Faster-Whisper STT) and output (Piper TTS)
- Web research via local SearXNG
- Tool-augmented conversations with market data access

### Web Dashboard
- Browser-based interface at `http://127.0.0.1:8501`
- Market Overview, Stock Analysis, and Market Analysis pages
- Real-time SSE updates, TradingView-style charts
- Localhost-only — does not bind to external interfaces

---

## Quick Start

**Requirements:** Windows 10/11, Python 3.14, Git

```powershell
git clone https://github.com/benalanirudh-pixel/nova.git
cd nova

python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
```

### Launch

```powershell
# Nova Terminal (recommended — unified Bloomberg-style interface)
.\venv\Scripts\python.exe terminal_main.py

# Nova Assistant (personal AI desktop)
.\venv\Scripts\python.exe main.py

# Market Lab (standalone analysis terminal)
.\venv\Scripts\python.exe market_lab_ui.py

# Web Dashboard (browser-based, localhost only)
.\venv\Scripts\python.exe web_main.py

# Launcher with service preflight check
.\venv\Scripts\python.exe start_nova.py
```

### Market Data

```powershell
# Cache-first report (fast, uses existing data)
.\venv\Scripts\python.exe market_lab\market_lab_data.py

# JSON export
.\venv\Scripts\python.exe market_lab\market_lab_data.py --json

# Full NSE scan (2,333 stocks, ~2-3 min — use sparingly)
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh

# Service health check
.\venv\Scripts\python.exe start_nova.py --check
```

---

## Architecture

```
nova/
├── terminal_main.py              # Nova Terminal (unified UI)
├── terminal/
│   ├── main_window.py            # Shell: header, sidebar, ticker strip
│   └── pages/                    # Dashboard, stock, market analysis, AI, flows
├── main.py                       # Nova Assistant
├── ui.py                         # Assistant UI
├── brain.py                      # Ollama chat + tool calling
├── tools.py                      # Tool registry and dispatch
├── market_lab_ui.py              # Market Lab standalone
├── market_lab/
│   ├── market_lab_data.py        # Central report gateway
│   ├── market_lab_brain.py       # AI interpretation layer
│   ├── stock_adapter.py          # Per-stock analysis
│   ├── view_model.py             # Report → UI adapter
│   └── widgets.py                # Charts, gauges, heatmaps
├── web_main.py                   # Web dashboard launcher
├── web/
│   ├── api/                      # FastAPI backend + SSE
│   └── frontend/                 # React + TypeScript SPA
├── analysis/
│   └── data/                     # Analysis engines (see below)
├── styles/
│   ├── design_tokens.py          # Unified design system
│   └── nova_theme.qss            # QSS stylesheet
└── tests/                        # 423 offline tests
```

### Analysis Engines (`analysis/data/`)

| Engine | What it does |
|--------|-------------|
| `technical_engine.py` | RSI, MACD, ATR, EMA, ADX, trend, momentum scoring |
| `volatility_engine.py` | VIX context, realized volatility, IV, ATR regime |
| `derivatives_engine.py` | Nifty/Bank Nifty option chain: PCR, max pain, OI walls, unusual activity |
| `institutional_flow_engine.py` | FII/DII flow history with primary-source validation |
| `sector_engine.py` | Sector and macro-sector performance intelligence |
| `risk_engine.py` | Risk-budget and position-risk calculations |
| `event_risk_engine.py` | Event-risk context from `event_calendar.json` |
| `research_factor_engine.py` | Multi-factor scoring |
| `market_scanner.py` | Full NSE equity scanner (2,333 stocks) + factor ranking |
| `nse_feed.py` | Indian Market MCP adapter |
| `dhan_feed.py` | Optional Dhan market-data adapter (read-only, off by default) |

### Data Sources

| Source | Adapter | Notes |
|--------|---------|-------|
| NSE (Indian Market MCP) | `nse_feed.py` | Primary — live quotes, history, option chains |
| Yahoo Finance | `market_data.py`, `market_universe.py` | Fallback for historical candles |
| NSE archives | `symbol_master.py`, `derivatives_engine.py` | Equity master, option chain data |
| NSE FII/DII endpoints | `institutional_flow_engine.py` | Plus Groww secondary mirror |
| Dhan (optional) | `dhan_feed.py` | Historical candles + live quotes; disabled until configured |
| Local SearXNG | `tools.py` | Web research for AI assistant |
| Local Ollama | `brain.py`, `market_lab_brain.py` | qwen3.5:4b for AI interpretation |

### Report Pipeline

`market_lab_data.py::get_market_lab_data()` is the central gateway:

1. Load cached NSE equity scan (or run full scan with `--refresh`)
2. Aggregate: scanner → regime → breadth → technical → volatility → sector → derivatives → institutional → event risk → research factors
3. Optionally apply Dhan live overrides (Nifty, Bank Nifty, VIX)
4. Save JSON to `analysis/data/cache/market_lab/`
5. Return the report dict consumed by all UI surfaces

Modes: `CACHE_FIRST` (default), `FORCED_REFRESH` (`--refresh`), `LIVE_ONLY` (`--live-only`).

---

## External Services

All services run locally. No data leaves your machine.

| Service | Default URL | Purpose |
|---------|-------------|---------|
| Ollama | `http://localhost:11434` | Local LLM inference (qwen3.5:4b) |
| SearXNG | `http://localhost:8080` | Web research |
| Indian Market MCP | stdio | NSE market data |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Runtime | Python 3.14 |
| Desktop UI | PySide6, QPainter (custom charts, gauges, heatmaps) |
| Web UI | FastAPI, React 19, TypeScript, Vite, Recharts |
| AI | Ollama (qwen3.5:4b), Faster-Whisper STT, Piper TTS |
| 3D | PyOpenGL (assistant visual core) |
| Data | Indian Market MCP, Yahoo Finance, NSE archives, Dhan (optional) |

---

## Tests

```powershell
# Run all 423 tests (offline, no external services needed)
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

CI (`.github/workflows/ci.yml`) runs a dependency-free gate: AST-parse every `.py` file plus stdlib-only test suites. The full suite runs locally (heavy Windows-specific stack).

---

## Safety

- **Analysis only** — No broker integration, no order placement, no trade execution, no BUY/SELL
- **No invented data** — Missing or stale data is flagged, never fabricated
- **Cache-first** — Full NSE scans only on explicit `--refresh` or empty cache
- **Guardrails** — Every UI surface shows the analysis-only disclaimer
- **Localhost-only** — Web dashboard binds to `127.0.0.1`, refuses cross-origin refresh requests

---

## License

Private repository. All rights reserved.
