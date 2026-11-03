<div align="center">

# ✦ Nova

### Your own Indian stock market research terminal. It runs on your PC and it's free.

**NSE stocks · F&O option chains · FII/DII flows · live quotes · market regime**, all in one dark trading-desk dashboard on `localhost`.

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-strict-3178C6?logo=typescript&logoColor=white)
![Tailwind](https://img.shields.io/badge/Tailwind-4-06B6D4?logo=tailwindcss&logoColor=white)
![Tests](https://img.shields.io/badge/tests-476%20passing-26C281)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-FF9933)

<img src="docs/screenshots/overview.png" alt="Nova overview: morning call, NIFTY levels, index cards, global cues, pre-open session" width="100%">

</div>

> [!IMPORTANT]
> **Nova is for analysis only.** It has no broker connection, it never places orders, and it never tells you to buy or sell. Every number shows where it came from and how old it is. Missing or stale data is flagged, not invented.

---

## Why Nova?

Most free market sites give you one piece at a time: a chart here, an option chain there, FII data in a PDF somewhere else. Nova pulls it **all into one screen** and does the maths for you:

- 🧭 **Morning call.** One plain-English line per factor: NIFTY, US/Asia, crude, rupee, pre-open breadth, flows, regime, VIX. Each line is coloured supportive, neutral or cautious.
- 📈 **Real charts.** Daily candlesticks with EMA 20/50/200 and volume. Scroll to zoom, drag to pan, and the crosshair shows OHLC.
- 🧮 **F&O desk.** PCR, max pain, OI walls, ATM IV vs realized vol, skew, straddle-implied move and the full option chain for **NIFTY, BANK NIFTY and SENSEX**.
- 🏦 **FII / DII flows.** Daily, weekly and monthly bars with a sortable history and running totals.
- ⚡ **Live prices.** During market hours, prices stream into the page. A pill always tells you if data is *Live*, *Delayed*, *Saved* or *Stale*.
- 🔍 **Stock research.** Valuation, ratios, quarterly results, results calendar, ownership, peers, news and a technical snapshot for any NSE stock.
- 🔒 **100% local.** Everything runs on `127.0.0.1`. No account, no cloud and no tracking.

---

## 📸 What it looks like

### Stock research: chart, technicals, fundamentals, news
<img src="docs/screenshots/stock.png" alt="Stock page for RELIANCE: price chart with EMAs, technical snapshot, company, results calendar, news" width="100%">

The **key takeaways** row turns raw numbers into plain sentences: *"Revenue up 29.8% year on year"*, *"Return on equity 8.8% (below 10%)"*, *"Ranked 3 of 7 listed peers by 20-day return"*. The technical snapshot scores momentum from 0 to 100 and labels trend, structure, RSI, MACD and VWAP.

### F&O desk: option chain analytics for NIFTY, BANK NIFTY, SENSEX
<img src="docs/screenshots/fno.png" alt="F&O desk: index switcher, PCR, max pain, IV, desk read, levels ladder, OI profile, option chain" width="100%">

The **desk read** explains positioning in words, for example *"OI PCR 1.77: put-heavy, writers are defending lower strikes"*. The **levels** ladder sorts call/put OI walls, max pain, straddle breakevens and pivots around spot.

### FII / DII flows: who's buying, who's selling
<img src="docs/screenshots/flows.png" alt="Flows page: institutional activity stats, daily net flow bars, daily history table" width="100%">

Every row shows its **source** (NSE primary or a mirror) and provisional days carry a `*`. Combined NSE+BSE+MSEI data and NSE-only data are **never mixed**.

---

## 🚀 Get it running (about 10 minutes)

### 1. Install these first

| Tool | Version | Get it |
|------|---------|--------|
| **Windows** | 10 or 11 | |
| **Python** | 3.14 | [python.org/downloads](https://www.python.org/downloads/). Tick **"Add python.exe to PATH"** |
| **Node.js** | 20 or newer (LTS) | [nodejs.org](https://nodejs.org/). Only needed to build the dashboard once |
| **Git** | any | [git-scm.com](https://git-scm.com/download/win) |

### 2. Clone and install

Open **PowerShell** and run:

```powershell
git clone https://github.com/benalanirudh-pixel/nova.git
cd nova
python -m venv venv
.\venv\Scripts\pip.exe install -r requirements.txt
```

> The install is big (about 100 packages) because the same repo also ships a desktop AI assistant. It's a one-time step.

### 3. Build your first market report

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py
```

On a fresh clone there is no cache yet, so this scans **all ~2,300 NSE stocks** once. It takes **2 to 3 minutes**. Later runs reuse the cache and finish in seconds.

### 4. Launch the dashboard

```powershell
.\venv\Scripts\python.exe web_main.py
```

The first launch installs and builds the frontend automatically (about a minute). Then your browser opens **http://127.0.0.1:8501**. 🎉

Next time, just run step 4.

### Keyboard shortcuts

| Key | Action |
|-----|--------|
| `Ctrl+K` or `/` | Search any NSE symbol or company |
| `1` `2` `3` `4` | Overview · Stock · F&O desk · Flows |
| `g` then `o` / `s` / `a` / `f` | Same pages, Vim-style |
| `Esc` | Leave the search box |

---

## 🛠 Troubleshooting

<details>
<summary><b>The dashboard opens but panels are empty</b></summary>

You skipped step 3. Run `.\venv\Scripts\python.exe market_lab\market_lab_data.py` once, then press **Refresh data** in the top-right corner.
</details>

<details>
<summary><b><code>npm not found on PATH</code></b></summary>

Install Node.js LTS from [nodejs.org](https://nodejs.org/), close and reopen PowerShell, then run `web_main.py` again.
</details>

<details>
<summary><b>The feed pill says "Delayed" or "Feed closed"</b></summary>

That's expected. Live polling only runs during the NSE session (**09:15–15:30 IST, Mon–Fri**). Outside it, Nova shows the last saved values tagged **Saved**. Fast index ticks (every 5 s) need the optional Dhan data API (see below). Without it, index prices are delayed and stock prices still update every 15 s.
</details>

<details>
<summary><b>Port 8501 is already in use</b></summary>

```powershell
.\venv\Scripts\python.exe web_main.py --port 8502
```
</details>

<details>
<summary><b>Force a completely fresh scan</b></summary>

```powershell
.\venv\Scripts\python.exe market_lab\market_lab_data.py --refresh
```

This re-downloads everything (2 to 3 minutes). Use it sparingly, because the normal run is cache-first on purpose.
</details>

<details>
<summary><b>Check that all services are healthy</b></summary>

```powershell
.\venv\Scripts\python.exe start_nova.py --check
```
</details>

---

## ⚙️ Optional extras

| Extra | What it adds | How |
|-------|--------------|-----|
| **Dhan data API** | 5-second live NIFTY / BANK NIFTY / VIX ticks and Dhan candles | Put your *read-only data* token in a `.env` or `dhan_config.json` (both git-ignored). Off by default. Nova never uses order APIs. |
| **Ollama** | AI interpretation in the desktop apps | Install [Ollama](https://ollama.com) and `ollama pull qwen3.5:4b`. The web dashboard doesn't need it. |
| **Desktop apps** | PySide6 terminal, Market Lab and a voice assistant | `terminal_main.py`, `market_lab_ui.py`, `main.py` |

---

## 🧠 How it works

```
 NSE · BSE · Yahoo · Dhan (optional)
            │  read-only adapters
            ▼
  ┌──────────────────────────┐      ┌───────────────────────┐
  │ 11 Python analysis       │      │ live_feed.py          │
  │ engines (analysis/data/) │      │ polls quotes in market│
  │ technical · volatility   │      │ hours, change-only    │
  │ derivatives · flows ·    │      └──────────┬────────────┘
  │ sectors · risk · events  │                 │ ticks
  └────────────┬─────────────┘                 │
               │ cache-first JSON report        │
               ▼                                ▼
  ┌──────────────────────────────────────────────────────┐
  │ FastAPI (127.0.0.1:8501): REST + Server-Sent Events  │
  └──────────────────────────┬───────────────────────────┘
                             ▼
  ┌──────────────────────────────────────────────────────┐
  │ React 19 + TypeScript + Tailwind + lightweight-charts│
  └──────────────────────────────────────────────────────┘
```

| Engine | What it computes |
|--------|-----------------|
| `technical_engine.py` | RSI, MACD, ATR, EMA, ADX, trend and momentum scoring |
| `volatility_engine.py` | VIX regime, realized vol, IV, ATR regime |
| `derivatives_engine.py` | PCR, max pain, OI walls, unusual activity |
| `institutional_flow_engine.py` | FII/DII history with primary-source validation |
| `sector_engine.py` | Sector and macro-sector strength |
| `risk_engine.py` | Risk-budget and position-risk maths |
| `event_risk_engine.py` | Earnings, expiry and policy-date risk |
| `research_factor_engine.py` | Multi-factor scoring |
| `market_scanner.py` | Full NSE scan (~2,300 stocks) and factor ranking |
| `nse_feed.py` | Indian Market MCP adapter (primary data) |
| `dhan_feed.py` | Optional Dhan adapter (read-only, off by default) |

More detail is in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

<details>
<summary><b>API endpoints</b></summary>

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/health` | Service health and guardrail text |
| GET | `/api/market-overview` | Regime, breadth, flows, sectors, derivatives |
| GET | `/api/morning-brief` | Morning call, pre-open, global cues, news, stocks in focus |
| GET | `/api/stock/:symbol` | Per-stock technicals and chart data |
| GET | `/api/stock/:symbol/profile` | Company, ratios, results, ownership, peers, news |
| GET | `/api/symbols?q=` | Symbol search |
| GET | `/api/market-analysis` | VIX regime, flows, events for the F&O desk |
| GET | `/api/fno/:instrument?expiry=` | Live F&O desk for NIFTY, BANKNIFTY or SENSEX |
| GET | `/api/flows/history` | FII/DII history rows, each with its own scope |
| GET | `/api/events` | SSE stream: refresh events, live ticks, feed status |
| GET | `/api/live/snapshot` | Latest live ticks |
| POST | `/api/live/watch` | Ask the server to poll these symbols (origin-checked) |
| POST | `/api/refresh` | Trigger a data refresh (origin-checked) |

</details>

<details>
<summary><b>Developer mode (hot reload)</b></summary>

```powershell
.\venv\Scripts\python.exe web_main.py --dev     # API only
cd web\frontend; npm run dev                    # Vite on http://localhost:5173
```

Run the tests (offline, no services needed):

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests
```
</details>

---

## 🛡 Guardrails

- **Analysis only.** No broker integration, no order placement and no BUY/SELL signals. `buy_sell_authorized` is hard-wired to `False`.
- **No invented data.** Every price shows its source and time. Stale or missing values are labelled.
- **Cache-first.** The expensive full scan only runs on `--refresh` or when no cache exists.
- **Local only.** The server binds to `127.0.0.1`. Write endpoints reject cross-origin requests.
- **No secrets in git.** Tokens live in git-ignored files.

> Nova is a research tool, not investment advice. Markets carry risk. Do your own research and make your own decisions.

---

## 📄 License

[MIT](LICENSE) © 2026 Anirudh. Fork it, run it, share it.

<div align="center">

**If Nova helps you read the market, give it a ⭐**

</div>
