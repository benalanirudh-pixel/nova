# Nova

**Local AI-powered Indian market analysis workbench for Windows.**

Nova is a desktop application built with Python and PySide6 that provides real-time Indian stock market analysis using NSE data. It combines technical analysis engines, institutional flow tracking, derivatives intelligence, and local AI interpretation — all running on your machine with no cloud dependency.

> **Analysis only.** Nova does not connect to any broker, place trades, or generate buy/sell signals.

---

## Screenshots

Nova features a professional dark trading terminal interface with three main sections:

- **Market** — Real-time market pulse with Nifty chart, KPI strip, breadth, institutional flows, sector heatmap, derivatives
- **Stock Analysis** — Per-stock deep dive with technicals, momentum gauge (0–100), trend structure, returns, AI assessment
- **Market Analysis** — Nifty 50 deep analysis with derivatives intelligence, OI walls, regime assessment, positioning

---

## Features

### Market Dashboard
- Live Nifty & Bank Nifty tracking with candlestick charts
- 7-KPI strip with sparklines (Nifty, Bank Nifty, VIX, A/D, FII, DII, PCR)
- Market breadth visualization (advance/decline/unchanged)
- Institutional flow gauges (FII & DII net activity)
- Sector heatmap with performance grid
- Derivatives strip (ATM, PCR, Max Pain, IV, OI walls)

### Stock Analysis
- Technical indicators: RSI, MACD, ADX, ATR, EMA/SMA signals
- Momentum score gauge (0–100) — the central verdict
- 52-week range positioning
- Multi-period returns (1D, 5D, 20D, 60D)
- AI-generated key points and observations
- Trend and structure assessment

### Market Analysis (Nifty Deep Dive)
- Nifty candlestick chart with technical overlays
- Derivatives desk: PCR, max pain, ATM IV, put/call walls
- OI wall visualization
- Market regime assessment (VIX, breadth, A/D ratio)
- Unusual options activity alerts
- Positioning intelligence and flow summary
- AI narrative generation

### Nova Assistant
- Local AI assistant powered by Ollama (qwen3.5:4b)
- Voice input (Faster-Whisper) and output (Piper TTS)
- Web research via local SearXNG instance
- Tool-augmented conversations

---

## Quick Start

**Requirements:** Windows 10/11, Python 3.14, Git

```powershell
# Clone
git clone https://github.com/benalanirudh-pixel/nova.git
cd nova

# Set up virtual environment
python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt

# Launch Nova Terminal (recommended)
.\venv\Scripts\python.exe terminal_main.py

# Or launch individual surfaces
.\venv\Scripts\python.exe main.py            # Nova Assistant
.\venv\Scripts\python.exe market_lab_ui.py   # Market Lab standalone
```

### Market Data Commands

```powershell
# Cache-first market report (fast, uses cached data)
.\venv\Scripts\python.exe market_lab\market_lab_data.py

# JSON export
.\venv\Scripts\python.exe market_lab\market_lab_data.py --json

# Full NSE scan (slow, ~2-3 min, 2333 stocks — use sparingly)
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh

# Service health check
.\venv\Scripts\python.exe start_nova.py --check
```

---

## Architecture

```
nova/
├── terminal_main.py          # Nova Terminal entry point
├── terminal/
│   ├── main_window.py        # Terminal shell: header, sidebar, ticker strip
│   └── pages/
│       ├── market_overview.py   # Market dashboard
│       ├── stock_analysis.py    # Stock analysis
│       └── market_analysis.py   # Nifty deep dive
├── main.py                   # Nova Assistant entry point
├── ui.py                     # Assistant UI
├── brain.py                  # Assistant LLM brain (Ollama)
├── tools.py                  # Assistant tool dispatch
├── market_lab_ui.py          # Market Lab standalone UI
├── market_lab/
│   ├── market_lab_data.py    # Central analysis gateway
│   ├── market_lab_brain.py   # AI interpretation (Ollama)
│   ├── stock_adapter.py      # Per-stock analysis adapter
│   ├── report_parser.py      # AI report parsing
│   └── widgets.py            # Shared chart widgets (CandleChart, etc.)
├── analysis/
│   ├── data/                 # Analysis engines
│   │   ├── technical_engine.py    # RSI, MACD, EMA, ATR, ADX
│   │   ├── volatility_engine.py   # VIX, realized vol, IV
│   │   ├── derivatives_engine.py  # Options OI, PCR, max pain
│   │   ├── institutional_engine.py # FII/DII flow tracking
│   │   ├── sector_engine.py       # Sector performance
│   │   ├── nse_feed.py            # NSE data via MCP
│   │   └── scanner.py             # Full equity scanner
│   └── regime/               # Market regime detection
├── styles/
│   └── design_tokens.py      # Unified design system (colors, typography, spacing)
└── tests/                    # 394+ offline tests (stdlib unittest)
```

---

## External Services

| Service | URL | Purpose |
|---------|-----|---------|
| Ollama | `http://localhost:11434` | Local LLM (qwen3.5:4b) |
| SearXNG | `http://localhost:8080` | Web research |
| Indian Market MCP | stdio | NSE market data |

All services run locally. No data leaves your machine.

---

## Data Sources

- **NSE** — National Stock Exchange of India (via indian-market-mcp)
- **Yahoo Finance** — Fallback for historical candles
- **Cache-first design** — Expensive scans are cached; use `--refresh` only when needed

---

## Tech Stack

- **Python 3.14** — Runtime
- **PySide6** — Desktop UI framework
- **QPainter** — Custom widgets (candlestick charts, gauges, heatmaps, flow bars)
- **Ollama** — Local LLM inference
- **Faster-Whisper** — Speech-to-text
- **Piper TTS** — Text-to-speech

---

## Tests

```powershell
# Run all 394+ tests (offline, no external services needed)
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

---

## Safety

- **Analysis only** — No broker integration, no order placement, no automatic buy/sell
- **No invented data** — Missing or stale data is flagged, never fabricated
- **Cache-first** — Full NSE scans only when explicitly requested
- **Guardrails** — Every output surface shows the analysis-only disclaimer

---

## License

Private repository. All rights reserved.
