# Nova Web Dashboard — Design Spec

**Date:** 2026-11-01
**Status:** Draft
**Scope:** Web-based market analysis dashboard reusing existing Python backend

---

## 1. Goal

Build a localhost web dashboard that mirrors the three Nova Terminal pages
(Market Overview, Stock Analysis, Market Analysis) with proper interactive
charts, premium dark UI, and scheduled auto-refresh — while reusing every
existing analysis engine unchanged.

**Non-goals:** Trading execution, broker integration, cloud deployment,
paid API keys, mobile-first design.

## 2. Architecture

```
Browser (React SPA)
    │
    ▼
FastAPI (web/api/main.py)          ← thin JSON wrapper
    │
    ├── GET /api/market-overview   ← view_model.py over cached report
    ├── GET /api/stock/{symbol}    ← score_symbol + get_history
    ├── GET /api/market-analysis   ← regime, breadth, sector, derivatives
    ├── GET /api/refresh           ← trigger manual refresh
    └── SSE /api/events            ← push when scheduler refreshes data
    │
    ▼
Existing engines (unchanged)
    ├── market_lab/market_lab_data.py   (get_market_lab_data)
    ├── market_lab/view_model.py        (presentation adapter)
    ├── analysis/data/*                 (technical, derivatives, sector, etc.)
    └── analysis/data/cache/            (cache files)
```

### 2.1 Directory Layout

```
nova/
├── web/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py              ← FastAPI app, CORS, static mount
│   │   ├── scheduler.py         ← APScheduler refresh triggers
│   │   └── routes/
│   │       ├── __init__.py
│   │       ├── market.py        ← /api/market-overview
│   │       ├── stock.py         ← /api/stock/{symbol}
│   │       └── analysis.py      ← /api/market-analysis
│   └── frontend/
│       ├── package.json
│       ├── vite.config.ts
│       ├── tailwind.config.ts
│       ├── index.html
│       └── src/
│           ├── main.tsx
│           ├── App.tsx
│           ├── pages/
│           │   ├── MarketOverview.tsx
│           │   ├── StockAnalysis.tsx
│           │   └── MarketAnalysis.tsx
│           ├── components/
│           │   ├── KPICard.tsx
│           │   ├── CandlestickChart.tsx
│           │   ├── BreadthBars.tsx
│           │   ├── FlowGauge.tsx
│           │   ├── SectorHeatmap.tsx
│           │   ├── DerivativesStrip.tsx
│           │   ├── StatusBar.tsx
│           │   ├── GuardrailsBar.tsx
│           │   ├── MomentumGauge.tsx
│           │   └── SymbolSearch.tsx
│           ├── hooks/
│           │   ├── useMarketData.ts
│           │   ├── useStockAnalysis.ts
│           │   └── useSSE.ts
│           └── lib/
│               ├── api.ts       ← fetch wrappers
│               └── theme.ts     ← design tokens (CSS vars)
└── web_main.py                  ← launcher: uvicorn + optional Vite dev
```

### 2.2 Launcher

`web_main.py` at project root:
- Starts uvicorn on port 8501
- In dev mode: frontend runs on Vite dev server (port 5173), API proxied
- In prod mode: FastAPI serves built frontend from `web/frontend/dist/`

```
python web_main.py              # prod (serves built frontend)
python web_main.py --dev        # dev (Vite hot-reload + API)
```

## 3. Data Flow

### 3.1 Existing Engines (unchanged)

| Engine | Location | Used by |
|--------|----------|---------|
| Market report | `market_lab/market_lab_data.py` | Market Overview, Market Analysis |
| View model | `market_lab/view_model.py` | All pages (presentation layer) |
| Technical analysis | `analysis/data/technical_analysis.py` | Stock Analysis |
| History download | `analysis/data/nse_history.py` | Stock Analysis charts |
| Sector intelligence | `analysis/data/sectors/` | Market Analysis |
| Derivatives | `analysis/data/derivatives_intel.py` | Market Overview, Analysis |
| Institutional flow | `analysis/data/institutional_flow.py` | Market Overview, Analysis |
| Risk/volatility | `analysis/data/risk.py`, `volatility.py` | Stock Analysis |
| Event risk | `analysis/data/event_risk.py` | Market Analysis |
| Stock analysis | `analysis/data/technical_engine.py` (`analyze_stock`) | Stock Analysis |
| Stock history | `analysis/data/nse_feed.py` (`get_stock_history`) | Stock Analysis charts |
| Stock quote | `analysis/data/nse_feed.py` (`get_stock_quote`) | Stock Analysis |

### 3.2 Cache-First Policy (preserved)

API endpoints read from existing cache by default. The `/api/refresh` endpoint
and scheduled triggers are the only paths that call `get_market_lab_data(refresh=True)`.

### 3.3 Auto-Refresh Schedule (IST)

| Trigger | Time | Action |
|---------|------|--------|
| Market open | 09:15 IST | Full refresh |
| Mid-day | 13:30 IST | Full refresh |
| Near close | 15:15 IST | Full refresh |
| Daily | 18:00 IST | Full refresh (post-market) |

Implemented via APScheduler `CronTrigger` in `web/api/scheduler.py`.
Each refresh fires an SSE event so connected browsers update.

### 3.4 OHLC Chart Data

- Daily candles: existing `download_history()` from `analysis/data/`
- Intraday (if needed): `yfinance` with `^NSEI` / `^NSEBANK` (free, no API key)
- Chart library renders from JSON array of `{time, open, high, low, close, volume}`

## 4. Frontend Design

### 4.1 Tech Stack

| Lib | Version | Purpose |
|-----|---------|---------|
| React | 18.x | UI framework |
| React Router | 6.x | Page routing |
| TradingView Lightweight Charts | 4.x | Candlestick, line, area, histogram charts |
| Tailwind CSS | 3.x | Utility-first styling |
| Vite | 5.x | Build tool, dev server |

No other UI framework (no MUI, no Ant Design). Tailwind + custom components only.

### 4.2 Design Tokens (CSS Variables)

Mapped from `styles/design_tokens.py`:

```css
:root {
  --bg-deep:     #030B12;
  --bg-panel:    #071923;
  --border:      #0B6478;
  --text:        #F2F6FA;
  --text-secondary: #91A9BE;
  --text-muted:  #617A91;
  --accent:      #00E5FF;
  --positive:    #00E6A8;
  --negative:    #FF405A;
  --warning:     #FFC928;
  --info:        #3198FF;
  --purple:      #B49AFF;
  --font-ui:     'Segoe UI', system-ui, sans-serif;
  --font-mono:   'Consolas', 'Fira Code', monospace;
}
```

### 4.3 Navigation

Left sidebar (collapsible):
- Market Overview (default)
- Stock Analysis
- Market Analysis

Top bar: Nova logo, data freshness badge, next refresh countdown, manual refresh button.

## 5. Page Specifications

### 5.1 Market Overview

**Top strip:** 7 KPI cards in a flex row
- NIFTY 50 (price + change % + arrow)
- Bank NIFTY (price + change % + arrow)
- VIX (value + change)
- Advance/Decline ratio
- PCR (put-call ratio)
- Max Pain (NIFTY)
- Market Regime (colored badge)

Data: `view_model.macro()`, `index_card("nifty")`, `index_card("banknifty")`, `vix_card()`

**Three-column layout:**

| Left (50%) | Center (26%) | Right (24%) |
|------------|--------------|-------------|
| Candlestick chart | Breadth bars | Sector heatmap |
| NIFTY OHLC + EMA | Adv/Dec/Unch stacked | Treemap by sector |
| Volume bars below | FII/DII flow gauges | Color by % change |

- Chart: TradingView Lightweight Charts, candlestick series + line overlay (EMA) + volume histogram
- Breadth: horizontal stacked bars (CSS), green/red/gray segments
- Heatmap: CSS Grid cells, background color interpolated from negative (red) to positive (green)

**Bottom strip:** Derivatives row — OI, PCR, Max Pain, IV, unusual activity
**Status bar:** Data age + freshness color + next refresh time

### 5.2 Stock Analysis

**Top:** Search bar (autocomplete from NSE equity list) + recent searches (localStorage)

**Left panel (60%):** TradingView chart stack
- Main: Candlestick + EMA 20/50/200 (toggleable via legend clicks)
- Subplot 1: RSI (14) with 30/70 reference lines
- Subplot 2: MACD (12, 26, 9) with signal line + histogram

Data: `download_history(symbol)` → OHLC JSON, indicators computed by existing `technical_analysis.py`

**Right panel (40%):**
- Score card: overall score (0-100) + circular gauge
- Momentum: gauge component matching PySide6 version
- Key levels: support/resistance table
- Volatility: ATR, ADX values
- Research factors: from `view_model` research block
- Risk context: position sizing suggestion

**Bottom:** Guardrails bar — "Analysis only — not a buy/sell signal" — always visible, red-tinted

### 5.3 Market Analysis

Full-width single-column, scrollable sections:

1. **Regime Analysis**
   - Current regime badge (bull/bear/sideways) with description
   - Regime history timeline (area chart, color-coded periods)

2. **Breadth Deep-Dive**
   - Advance/Decline line chart (cumulative, time series)
   - Breadth thrust indicator
   - % stocks above 20/50/200 DMA (stacked area)

3. **Sector Performance**
   - Grouped bar chart: 1D / 1W / 1M returns per sector
   - Toggle buttons for time period
   - Sort by selected period

4. **Institutional Flow**
   - FII/DII daily net flow (bar chart, green/red)
   - Cumulative flow line overlay
   - Table with recent days

5. **Derivatives Intelligence**
   - OI change chart (calls vs puts, bar)
   - PCR trend (line chart)
   - IV skew visualization
   - Unusual activity table

6. **Event Risk Calendar**
   - Upcoming events from `event_risk_context`
   - Timeline or table view with impact rating

## 6. API Endpoints

### 6.1 Market Overview

```
GET /api/market-overview
Response: {
  kpis: { nifty, banknifty, vix, adv_dec, pcr, max_pain, regime },
  chart: { candles: [...], ema: [...] },
  breadth: { advancing, declining, unchanged },
  flows: { fii: {...}, dii: {...} },
  sectors: [{ name, change_pct, weight }],
  derivatives: { oi, pcr, max_pain, iv, unusual },
  freshness: { age_seconds, level, next_refresh }
}
```

### 6.2 Stock Analysis

```
GET /api/stock/{symbol}
Response: {
  info: { name, symbol, sector, price, change },
  chart: { candles: [...], ema20, ema50, ema200, rsi, macd },
  score: { overall, components: [...] },
  levels: { support: [...], resistance: [...] },
  volatility: { atr, adx },
  research_factors: [...],
  risk: { position_size, stop_loss }
}
```

### 6.3 Market Analysis

```
GET /api/market-analysis
Response: {
  regime: { current, history: [...] },
  breadth: { adv_dec_line: [...], thrust: {...}, dma_pcts: {...} },
  sectors: { returns: { "1d": [...], "1w": [...], "1m": [...] } },
  flows: { daily: [...], cumulative: [...] },
  derivatives: { oi_change: [...], pcr_trend: [...], iv_skew: {...}, unusual: [...] },
  events: [{ date, event, impact }]
}
```

### 6.4 Utility

```
GET /api/refresh          ← triggers manual refresh, returns status
GET /api/events           ← SSE stream, pushes { type: "refresh", timestamp }
GET /api/symbols          ← autocomplete list from NSE equity master
```

## 7. Dependencies (new)

### 7.1 Python (added to venv)

| Package | Purpose |
|---------|---------|
| fastapi | API framework |
| uvicorn | ASGI server |
| apscheduler | Cron-based refresh |
| sse-starlette | Server-Sent Events |
| yfinance | Intraday OHLC (free, no key) |

### 7.2 Node.js (frontend only, separate from Python venv)

| Package | Purpose |
|---------|---------|
| react, react-dom | UI |
| react-router-dom | Routing |
| lightweight-charts | TradingView charts |
| tailwindcss | Styling |
| vite | Build/dev |
| typescript | Type safety |

## 8. Safety & Guardrails

1. **Analysis only.** No `/api/order`, no `/api/trade`, no broker endpoints. Ever.
2. **`BUY_SELL_AUTHORIZED = False`** checked in API layer. Responses include guardrail text.
3. **No invented data.** API returns `null` / `"N/A"` for missing fields, never fabricates.
4. **Cache-first.** All GET endpoints read cache. Only `/api/refresh` and scheduler write.
5. **GuardrailsBar** component rendered on every page, always visible.
6. **No paid APIs.** NSE direct feeds + yfinance only. Zero API keys in config.
7. **Localhost only.** FastAPI binds `127.0.0.1:8501`. No `0.0.0.0`.

## 9. What This Spec Does NOT Cover

- Mobile/responsive design (desktop-first, reasonable tablet support via Tailwind)
- Authentication (localhost, single user)
- Database (reads cache files directly, no DB)
- AI interpretation layer (future: could add market_lab_brain.py summaries)
- Deployment/Docker (localhost only for now)
