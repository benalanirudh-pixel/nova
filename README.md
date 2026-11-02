# Nova

**Real-time Indian market analysis dashboard — runs locally, no broker, no cloud.**

Nova is a web-based NSE analysis terminal built with FastAPI and React. It pulls live data from the National Stock Exchange, runs technical, derivatives, institutional flow, and regime analysis through Python engines, and renders everything in a professional trading dashboard at `http://127.0.0.1:8501`. AI interpretation is powered by a local Ollama instance. All data stays on your machine.

> **Analysis only.** Nova does not connect to any broker, place trades, or generate buy/sell signals.

---

## Dashboard

<p align="center">
  <img src="screenshots/kilo_marketlab_full.png" alt="Nova Dashboard — Market Overview" width="100%">
</p>

<details>
<summary>More views</summary>

| Stock Analysis | Market Analysis (Nifty Deep Dive) |
|:---:|:---:|
| <img src="screenshots/stock.png" alt="Stock Analysis" width="480"> | <img src="screenshots/report.png" alt="Market Analysis" width="480"> |

| Desktop Terminal (PySide6) | Market Dashboard |
|:---:|:---:|
| <img src="screenshots/terminal_v2_final.png" alt="Nova Terminal" width="480"> | <img src="screenshots/dashboard.png" alt="Market Dashboard" width="480"> |

</details>

---

## Pages

### Market Overview
- **Ticker tape** — Nifty 50, Bank Nifty, India VIX, sector leaders with live prices and change
- **Index cards** — Candlestick charts with OHLC, multi-period returns (5D/20D/60D), 52-week range bar
- **KPI strip** — 7 indicators with sparklines: Nifty, Bank Nifty, VIX, Advance/Decline, FII, DII, PCR
- **Market breadth** — Advances vs. declines vs. unchanged with percent bars
- **Institutional flows** — FII and DII net activity gauges (daily and cumulative)
- **Sector heatmap** — NSE sector performance grid
- **Derivatives strip** — ATM IV, PCR, max pain, OI walls

### Stock Analysis
- **Symbol search** — Search across 2,333 NSE equities with recent history
- **Candlestick chart** — Price action with volume, synced indicator chart (RSI/MACD/ADX)
- **Momentum gauge** — Composite 0–100 score with red/amber/green threshold zones
- **Technical table** — RSI, MACD, ADX, ATR, EMA/SMA signals, trend structure
- **52-week range** — Current price positioning with high/low
- **Multi-period returns** — 1D, 5D, 20D, 60D
- **AI research report** — LLM-generated executive summary, bullish/bearish factors, key levels

### Market Analysis (Nifty Deep Dive)
- **Regime assessment** — VIX regime, VIX percentile (1Y), breadth regime, composite market state
- **Derivatives desk** — PCR, max pain, ATM IV, put/call walls, unusual OI activity
- **Institutional positioning** — FII/DII flow summary with directional bias
- **Sector performance** — Returns across NSE sectors with regime context
- **Breadth analysis** — Advance/decline ratios, breadth thrust indicators
- **AI narrative** — LLM interpretation with evidence citations

### Real-Time Updates
- **SSE (Server-Sent Events)** — Dashboard auto-updates on data refresh
- **Scheduled refresh** — Automatic data refresh on weekdays during market hours
- **Manual refresh** — One-click refresh button with POST endpoint (origin-checked)

---

## Quick Start

**Requirements:** Windows 10/11, Python 3.14, Node.js (for frontend build), Git

```powershell
git clone https://github.com/benalanirudh-pixel/nova.git
cd nova

python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
```

### Launch the Dashboard

```powershell
# Build frontend (first time only)
.\venv\Scripts\python.exe web_main.py --build

# Start the dashboard — opens at http://127.0.0.1:8501
.\venv\Scripts\python.exe web_main.py
```

### Development Mode

```powershell
# API only (run Vite dev server separately for hot reload)
.\venv\Scripts\python.exe web_main.py --dev

# In another terminal:
cd web/frontend && npm run dev
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

### Desktop Surfaces (Alternative)

Nova also ships PySide6 desktop UIs for offline use without a browser:

```powershell
.\venv\Scripts\python.exe terminal_main.py      # Unified Bloomberg-style terminal
.\venv\Scripts\python.exe market_lab_ui.py       # Market Lab standalone
.\venv\Scripts\python.exe main.py                # Nova Assistant (AI chat + voice)
```

---

## Architecture

```
nova/
├── web_main.py                       # Dashboard launcher (build / serve / dev)
├── web/
│   ├── api/
│   │   ├── main.py                   # FastAPI app: health, SSE, static serving
│   │   ├── report_loader.py          # Shared report cache loader
│   │   ├── scheduler.py              # APScheduler auto-refresh (weekday)
│   │   └── routes/
│   │       ├── market.py             # GET /api/market-overview
│   │       ├── stock.py              # GET /api/stock/:symbol, /api/symbols
│   │       ├── analysis.py           # GET /api/market-analysis
│   │       └── events.py             # GET /api/events (SSE stream)
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx               # Shell: header, ticker tape, sidebar, routes
│       │   ├── pages/
│       │   │   ├── MarketOverview.tsx # Dashboard with all panels
│       │   │   ├── StockAnalysis.tsx  # Per-stock deep dive
│       │   │   └── MarketAnalysis.tsx # Nifty regime + derivatives analysis
│       │   ├── components/           # CandlestickChart, FlowGauge, SectorHeatmap, ...
│       │   ├── hooks/                # useSSE, useMarketData, useStockAnalysis
│       │   └── lib/                  # API client, formatters, types, theme tokens
│       ├── package.json              # React 19, TypeScript, Vite, Recharts
│       └── vite.config.ts
├── market_lab/
│   └── market_lab_data.py            # Central report gateway (all engines)
├── analysis/
│   └── data/                         # Python analysis engines (see below)
└── tests/                            # 423 offline tests
```

### Analysis Engines

The backend runs 11 Python analysis engines under `analysis/data/`:

| Engine | What it computes |
|--------|-----------------|
| `technical_engine.py` | RSI, MACD, ATR, EMA, ADX, trend, momentum scoring |
| `volatility_engine.py` | VIX context, realized volatility, IV, ATR regime |
| `derivatives_engine.py` | Nifty/Bank Nifty option chain: PCR, max pain, OI walls, unusual activity |
| `institutional_flow_engine.py` | FII/DII flow history with primary-source validation |
| `sector_engine.py` | Sector and macro-sector performance intelligence |
| `risk_engine.py` | Risk-budget and position-risk calculations |
| `event_risk_engine.py` | Event-risk context (earnings, expiry, policy dates) |
| `research_factor_engine.py` | Multi-factor scoring |
| `market_scanner.py` | Full NSE equity scanner (2,333 stocks) + factor ranking |
| `nse_feed.py` | Indian Market MCP adapter (primary data source) |
| `dhan_feed.py` | Optional Dhan market-data adapter (read-only, off by default) |

### Report Pipeline

`market_lab_data.py::get_market_lab_data()` aggregates all engines into a single JSON report:

1. Load cached NSE equity scan (or full scan with `--refresh`)
2. Aggregate: scanner → regime → breadth → technical → volatility → sector → derivatives → institutional → event risk → research factors
3. Optionally overlay Dhan live quotes (Nifty, Bank Nifty, VIX)
4. Cache to `analysis/data/cache/market_lab/`
5. Serve to the dashboard via FastAPI endpoints

Modes: **CACHE_FIRST** (default), **FORCED_REFRESH** (`--refresh`), **LIVE_ONLY** (`--live-only`).

### Data Sources

| Source | Adapter | Coverage |
|--------|---------|----------|
| NSE via Indian Market MCP | `nse_feed.py` | Live quotes, history, option chains, equity master |
| Yahoo Finance | `market_data.py` | Fallback for historical candles |
| NSE FII/DII endpoints | `institutional_flow_engine.py` | Daily institutional flow + Groww mirror |
| NSE archives | `derivatives_engine.py` | Option chain snapshots |
| Dhan (optional) | `dhan_feed.py` | Historical candles + live quotes; off by default |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.14, FastAPI, Uvicorn, APScheduler, SSE-Starlette |
| **Frontend** | React 19, TypeScript, Vite, Recharts, Lightweight Charts, Tailwind CSS |
| **Analysis** | 11 Python engines: technicals, derivatives, volatility, institutional flow, sectors, risk, regime |
| **AI** | Ollama (qwen3.5:4b) for market interpretation and stock research |
| **Data** | Indian Market MCP, Yahoo Finance, NSE, Dhan (optional) |
| **Desktop** | PySide6, QPainter (alternative offline UI) |

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health + guardrail text |
| GET | `/api/market-overview` | Full market dashboard data |
| GET | `/api/stock/:symbol` | Per-stock analysis (technicals, AI report) |
| GET | `/api/symbols?q=` | Symbol search across NSE equities |
| GET | `/api/market-analysis` | Nifty deep dive (regime, derivatives, flows) |
| GET | `/api/events` | SSE stream (refresh events) |
| POST | `/api/refresh` | Trigger data refresh (origin-checked) |

All endpoints return JSON. The dashboard is localhost-only (`127.0.0.1`).

---

## External Services

All services run locally. No data leaves your machine.

| Service | Default URL | Purpose |
|---------|-------------|---------|
| Ollama | `http://localhost:11434` | Local LLM inference (qwen3.5:4b) |
| Indian Market MCP | stdio | NSE market data |
| SearXNG | `http://localhost:8080` | Web research (assistant only) |

---

## Tests

```powershell
# Run all 423 tests (offline, no external services needed)
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

CI (`.github/workflows/ci.yml`) runs a dependency-free gate: AST-parse every `.py` file plus stdlib-only tests. Full suite runs locally (heavy Windows stack).

---

## Safety

- **Analysis only** — No broker integration, no order placement, no trade execution, no BUY/SELL
- **No invented data** — Missing or stale data is flagged, never fabricated
- **Cache-first** — Full NSE scans only on explicit `--refresh` or empty cache
- **Guardrails** — Every surface (web and desktop) shows the analysis-only disclaimer
- **Localhost-only** — Web dashboard binds to `127.0.0.1`, POST `/refresh` is origin-checked
- **No credentials in code** — Optional Dhan token via git-ignored `.env` or `dhan_config.json`

---

## License

Private repository. All rights reserved.
