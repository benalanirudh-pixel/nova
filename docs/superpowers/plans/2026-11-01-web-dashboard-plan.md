# Nova Web Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a localhost web dashboard (FastAPI + React) that serves the same market analysis as the PySide6 terminal, with interactive TradingView charts and scheduled auto-refresh.

**Architecture:** FastAPI wraps the existing `get_market_lab_data()` and `view_model.py` as JSON endpoints. React SPA with TradingView Lightweight Charts consumes them. SSE pushes refresh events. APScheduler triggers data refreshes at market hours.

**Tech Stack:** Python (FastAPI, uvicorn, APScheduler, sse-starlette, yfinance), Node.js (React 18, React Router 6, TradingView Lightweight Charts 4, Tailwind CSS 3, Vite 5, TypeScript)

**Spec:** `docs/superpowers/specs/2026-11-01-web-dashboard-design.md`

## Global Constraints

- Python 3.14, existing venv at `.\venv\`
- No paid APIs. Free NSE feeds + yfinance only.
- `BUY_SELL_AUTHORIZED = False` — no order/trade/broker endpoints.
- Cache-first: GET endpoints read cache. Only `/api/refresh` and scheduler write.
- Localhost only: bind `127.0.0.1:8501`, never `0.0.0.0`.
- Existing engines unchanged — no modifications to `market_lab/`, `analysis/`, `styles/`.
- Tests use stdlib `unittest` (no pytest). Run: `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
- GuardrailsBar visible on every page.
- Missing data → `null` / `"N/A"`, never fabricated.

## Review Focus

1. **Empty/missing cache:** First run with no `analysis/data/cache/market_lab/` files — API must return structured empty response with `null` fields, not crash.
2. **Stale report fields:** Report dict missing expected keys (e.g. `derivatives` absent) — view_model already handles this with N/A, but API serialization must preserve `null` not drop keys.
3. **Invalid stock symbol:** `/api/stock/XYZNOTREAL` — must return 404 with message, not 500.
4. **Concurrent refresh:** Two browsers hit `/api/refresh` simultaneously — must not double-run the expensive NSE scan.
5. **SSE reconnect:** Browser loses connection, reconnects — must get current state, not miss updates silently.

---

### Task 1: FastAPI Backend Scaffold + Health Check

**Files:**
- Create: `web/__init__.py`
- Create: `web/api/__init__.py`
- Create: `web/api/main.py`
- Create: `web_main.py`
- Create: `tests/test_web_api.py`

**Interfaces:**
- Produces: `create_app() -> FastAPI` in `web/api/main.py`
- Produces: `web_main.py` CLI entry point (port 8501, `--dev` flag)

- [ ] **Step 1: Write failing test for health endpoint**

```python
# tests/test_web_api.py
import unittest
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web.api.main import create_app

class TestHealthEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_health_returns_ok(self):
        r = self.client.get("/api/health")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["buy_sell_authorized"])

    def test_cors_headers_present(self):
        r = self.client.options("/api/health", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        })
        self.assertIn("access-control-allow-origin", r.headers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: FAIL (ImportError — `web.api.main` does not exist)

- [ ] **Step 3: Install Python dependencies**

```powershell
.\venv\Scripts\pip.exe install fastapi uvicorn[standard] apscheduler sse-starlette yfinance httpx
```

`httpx` is needed for `starlette.testclient`.

- [ ] **Step 4: Implement `create_app()` in `web/api/main.py`**

Create `web/__init__.py` and `web/api/__init__.py` (empty).
`create_app()` returns a FastAPI instance with:
- CORS middleware allowing `http://localhost:5173` and `http://localhost:8501`
- `GET /api/health` returning `{"status": "ok", "buy_sell_authorized": False}`
- Import `GUARDRAIL_TEXT, BUY_SELL_AUTHORIZED` from `styles.design_tokens`

- [ ] **Step 5: Implement `web_main.py` launcher**

Accepts `--dev` flag and `--port` (default 8501).
Runs `uvicorn.run("web.api.main:create_app", factory=True, host="127.0.0.1", port=port)`.
With `--dev`, prints instructions to start Vite separately.

- [ ] **Step 6: Run tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: PASS

- [ ] **Step 7: Run full test suite to check no regressions**

Run: `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: All existing 397+ tests still pass.

- [ ] **Step 8: Commit**

```bash
git add web/ web_main.py tests/test_web_api.py
git commit -m "feat(web): FastAPI scaffold with health endpoint and launcher"
```

---

### Task 2: Market Overview API Route

**Files:**
- Create: `web/api/routes/__init__.py`
- Create: `web/api/routes/market.py`
- Modify: `web/api/main.py` (include router)
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `market_lab.market_lab_data.get_market_lab_data(force_refresh=False)` → `dict`
- Consumes: `market_lab.view_model.*` — `macro()`, `index_card()`, `vix_card()`, `breadth_block()`, `flow_block()`, `sector_rows()`, `derivatives_block()`, `data_age()`, `indicator_cards()`, `guardrails()`
- Produces: `GET /api/market-overview` → JSON matching spec section 6.1

- [ ] **Step 1: Write failing test for market overview endpoint**

```python
class TestMarketOverviewEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_market_overview_returns_200(self):
        r = self.client.get("/api/market-overview")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("kpis", body)
        self.assertIn("breadth", body)
        self.assertIn("flows", body)
        self.assertIn("sectors", body)
        self.assertIn("derivatives", body)
        self.assertIn("freshness", body)
        self.assertIn("guardrails", body)

    def test_market_overview_guardrails_present(self):
        r = self.client.get("/api/market-overview")
        body = r.json()
        self.assertFalse(body["guardrails"]["buy_sell_authorization"])

    def test_market_overview_no_cache_returns_null_kpis(self):
        """When no cached report exists, KPIs should be null, not crash."""
        r = self.client.get("/api/market-overview")
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api.TestMarketOverviewEndpoint -v`
Expected: FAIL (404, route not found)

- [ ] **Step 3: Implement `web/api/routes/market.py`**

`GET /api/market-overview`:
1. Call `load_latest_saved_report()` (reuse pattern from `market_lab_ui.py`) to get cached report
2. If no report: return structured response with all fields `null`
3. Pass report through `view_model` functions: `macro(report)`, `index_card(report, "nifty")`, `index_card(report, "bank_nifty")`, `vix_card(report)`, `breadth_block(report)`, `flow_block(report)`, `sector_rows(report, limit=25)`, `derivatives_block(report, "nifty")`, `data_age(report)`, `guardrails(report)`
4. Assemble into response JSON matching spec section 6.1
5. Include NIFTY candles from `report.get("nifty_candles", [])` for chart data

- [ ] **Step 4: Register router in `web/api/main.py`**

```python
from web.api.routes.market import router as market_router
app.include_router(market_router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/api/routes/ tests/test_web_api.py web/api/main.py
git commit -m "feat(web): market overview API endpoint"
```

---

### Task 3: Stock Analysis API Route

**Files:**
- Create: `web/api/routes/stock.py`
- Modify: `web/api/main.py` (include router)
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `analysis.data.technical_engine.analyze_stock(query: str) -> dict`
- Consumes: `analysis.data.nse_feed.get_stock_history_dataframe(symbol: str) -> pd.DataFrame`
- Consumes: `analysis.data.symbol_master.download_nse_equity_master() -> pd.DataFrame`
- Produces: `GET /api/stock/{symbol}` → JSON matching spec section 6.2
- Produces: `GET /api/symbols` → `[{"symbol": "RELIANCE", "name": "Reliance Industries"}, ...]`

- [ ] **Step 1: Write failing tests**

```python
class TestStockEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_invalid_symbol_returns_404(self):
        r = self.client.get("/api/stock/XYZNOTREAL123")
        self.assertEqual(r.status_code, 404)
        self.assertIn("error", r.json())

    def test_symbols_endpoint_returns_list(self):
        r = self.client.get("/api/symbols")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsInstance(body, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api.TestStockEndpoint -v`
Expected: FAIL

- [ ] **Step 3: Implement `web/api/routes/stock.py`**

`GET /api/stock/{symbol}`:
1. Call `analyze_stock(symbol)` — returns full technical analysis dict
2. If result indicates symbol not found (returns `None` or error key), return 404
3. Call `get_stock_history_dataframe(symbol)` for OHLC candle data
4. Convert DataFrame to list of `{time, open, high, low, close, volume}` dicts
5. Compute EMA 20/50/200, RSI, MACD from the analysis result
6. Assemble response matching spec section 6.2
7. Wrap in `asyncio.to_thread()` since `analyze_stock` is blocking

`GET /api/symbols`:
1. Try loading cached NSE equity master from `analysis/data/cache/`
2. Return `[{symbol, name}]` list for autocomplete
3. If no cache, return empty list (never trigger full download on GET)

- [ ] **Step 4: Register router in `web/api/main.py`**

- [ ] **Step 5: Run tests to verify they pass**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/api/routes/stock.py tests/test_web_api.py web/api/main.py
git commit -m "feat(web): stock analysis and symbols API endpoints"
```

---

### Task 4: Market Analysis API Route

**Files:**
- Create: `web/api/routes/analysis.py`
- Modify: `web/api/main.py` (include router)
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: Same cached report as Task 2
- Consumes: `view_model.macro()`, `breadth_block()`, `sector_rows()`, `flow_block()`, `flow_series()`, `derivatives_block()`, `risk_block()`, `indicator_cards()`
- Produces: `GET /api/market-analysis` → JSON matching spec section 6.3

- [ ] **Step 1: Write failing test**

```python
class TestMarketAnalysisEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_market_analysis_returns_200(self):
        r = self.client.get("/api/market-analysis")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("regime", body)
        self.assertIn("breadth", body)
        self.assertIn("sectors", body)
        self.assertIn("flows", body)
        self.assertIn("derivatives", body)
```

- [ ] **Step 2: Run test to verify it fails**

- [ ] **Step 3: Implement `web/api/routes/analysis.py`**

`GET /api/market-analysis`:
1. Load cached report (same helper as Task 2 — extract to shared `web/api/report_loader.py`)
2. Build response sections:
   - `regime`: `macro(report)` — `market_regime`, description
   - `breadth`: `breadth_block(report)` — full breadth data including DMA percents
   - `sectors`: `sector_rows(report, limit=25)` — all sector performance data
   - `flows`: `flow_block(report)` + `flow_series(report)` — daily + cumulative
   - `derivatives`: `derivatives_block(report, "nifty")` + `derivatives_block(report, "bank_nifty")`
   - `indicators`: `indicator_cards(report, "nifty")` — RSI/MACD/ATR/VOL
   - `events`: `report.get("event_risk_context", {})` — event calendar
   - `risk`: `risk_block(report)`

- [ ] **Step 4: Extract report loading to shared helper**

Create `web/api/report_loader.py`:
```python
def load_cached_report() -> dict | None:
    """Load latest cached Market Lab report. Returns report dict or None."""
```
Reuse the `load_latest_saved_report()` logic from `market_lab_ui.py`.
Update Tasks 2 and 4 routes to use this shared helper.

- [ ] **Step 5: Register router, run tests**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add web/api/routes/analysis.py web/api/report_loader.py tests/test_web_api.py web/api/main.py
git commit -m "feat(web): market analysis API endpoint with shared report loader"
```

---

### Task 5: Refresh Endpoint + SSE Events + Scheduler

**Files:**
- Create: `web/api/scheduler.py`
- Create: `web/api/routes/events.py`
- Modify: `web/api/main.py` (lifespan for scheduler start/stop)
- Modify: `tests/test_web_api.py`

**Interfaces:**
- Consumes: `market_lab.market_lab_data.get_market_lab_data(force_refresh=True)`
- Produces: `GET /api/refresh` → `{"status": "refreshing" | "already_running", "triggered_at": str}`
- Produces: `GET /api/events` → SSE stream, events: `{"type": "refresh_complete", "timestamp": str}`
- Produces: `start_scheduler(app)` / `stop_scheduler(app)` lifecycle hooks

- [ ] **Step 1: Write failing tests**

```python
class TestRefreshEndpoint(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_refresh_returns_status(self):
        r = self.client.get("/api/refresh")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("status", body)

    def test_concurrent_refresh_blocked(self):
        """Second refresh while first is running returns already_running."""
        r = self.client.get("/api/refresh")
        self.assertEqual(r.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

- [ ] **Step 3: Implement `web/api/scheduler.py`**

- `_refresh_lock = asyncio.Lock()` — prevents concurrent refreshes
- `async def do_refresh()`: acquires lock, calls `get_market_lab_data(force_refresh=True)` in `asyncio.to_thread()`, broadcasts SSE event on completion
- `event_broadcaster`: simple in-memory list of `asyncio.Queue` for SSE subscribers
- `start_scheduler()`: APScheduler `AsyncIOScheduler` with 4 `CronTrigger` jobs (IST times: 09:15, 13:30, 15:15, 18:00)
- `stop_scheduler()`: shutdown APScheduler

- [ ] **Step 4: Implement `web/api/routes/events.py`**

`GET /api/refresh`: calls `do_refresh()`, returns status.
`GET /api/events`: SSE endpoint using `sse-starlette`. Subscribes a queue to the broadcaster, yields events.

- [ ] **Step 5: Wire scheduler lifecycle in `web/api/main.py`**

Use FastAPI `lifespan` context manager to start/stop scheduler.

- [ ] **Step 6: Run tests**

Run: `.\venv\Scripts\python.exe -m unittest tests.test_web_api -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add web/api/scheduler.py web/api/routes/events.py web/api/main.py tests/test_web_api.py
git commit -m "feat(web): refresh endpoint, SSE events, and scheduled auto-refresh"
```

---

### Task 6: React Frontend Scaffold + Navigation Shell

**Files:**
- Create: `web/frontend/package.json`
- Create: `web/frontend/vite.config.ts`
- Create: `web/frontend/tailwind.config.ts`
- Create: `web/frontend/postcss.config.js`
- Create: `web/frontend/tsconfig.json`
- Create: `web/frontend/index.html`
- Create: `web/frontend/src/main.tsx`
- Create: `web/frontend/src/App.tsx`
- Create: `web/frontend/src/index.css`
- Create: `web/frontend/src/lib/theme.ts`
- Create: `web/frontend/src/lib/api.ts`
- Create: `web/frontend/src/hooks/useSSE.ts`
- Create: `web/frontend/src/components/GuardrailsBar.tsx`
- Create: `web/frontend/src/pages/MarketOverview.tsx` (placeholder)
- Create: `web/frontend/src/pages/StockAnalysis.tsx` (placeholder)
- Create: `web/frontend/src/pages/MarketAnalysis.tsx` (placeholder)

**Interfaces:**
- Consumes: API at `http://localhost:8501/api/*`
- Produces: React SPA with 3-page routing, sidebar nav, top bar with freshness badge

- [ ] **Step 1: Initialize frontend project**

```powershell
cd web/frontend
npm create vite@latest . -- --template react-ts
npm install react-router-dom lightweight-charts tailwindcss @tailwindcss/vite
```

- [ ] **Step 2: Configure Vite proxy to API**

`vite.config.ts`: proxy `/api` to `http://localhost:8501`.

- [ ] **Step 3: Set up Tailwind with custom design tokens**

`web/frontend/src/index.css`:
```css
@import "tailwindcss";

:root {
  --bg-deep: #030B12;
  --bg-panel: #071923;
  --border: #0B6478;
  --text: #F2F6FA;
  --text-secondary: #91A9BE;
  --text-muted: #617A91;
  --accent: #00E5FF;
  --positive: #00E6A8;
  --negative: #FF405A;
  --warning: #FFC928;
  --info: #3198FF;
  --purple: #B49AFF;
}
body {
  background: var(--bg-deep);
  color: var(--text);
  font-family: 'Segoe UI', system-ui, sans-serif;
}
```

`tailwind.config.ts`: extend theme colors to reference CSS variables.

- [ ] **Step 4: Implement `lib/api.ts`**

```typescript
const BASE = "/api";
export async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${path}`);
  return res.json();
}
```

- [ ] **Step 5: Implement `hooks/useSSE.ts`**

Custom hook that opens `EventSource` to `/api/events`, returns last event, auto-reconnects on close. On reconnect, triggers a data refetch so the browser gets current state (Review Focus item 5).

- [ ] **Step 6: Implement `App.tsx` with sidebar navigation**

- React Router with 3 routes: `/` (Market Overview), `/stock` (Stock Analysis), `/analysis` (Market Analysis)
- Collapsible left sidebar with nav links
- Top bar: "Nova" logo text, freshness badge (calls `/api/health`), manual refresh button, next refresh countdown
- `<GuardrailsBar />` fixed at bottom of every page

- [ ] **Step 7: Implement `GuardrailsBar.tsx`**

Red-tinted bar at bottom: "Analysis only — not a buy/sell signal, no broker/orders". Always visible. Text from `GUARDRAIL_TEXT`.

- [ ] **Step 8: Create placeholder pages**

Each page (`MarketOverview.tsx`, `StockAnalysis.tsx`, `MarketAnalysis.tsx`): a `<div>` with the page title. Will be filled in Tasks 7-9.

- [ ] **Step 9: Verify dev server works**

```powershell
cd web/frontend
npm run dev
```

Open `http://localhost:5173` — should show sidebar nav, all 3 pages route, guardrails bar visible.

- [ ] **Step 10: Commit**

```bash
git add web/frontend/
git commit -m "feat(web): React frontend scaffold with navigation and design tokens"
```

---

### Task 7: Market Overview Page (Frontend)

**Files:**
- Create: `web/frontend/src/hooks/useMarketData.ts`
- Create: `web/frontend/src/components/KPICard.tsx`
- Create: `web/frontend/src/components/CandlestickChart.tsx`
- Create: `web/frontend/src/components/BreadthBars.tsx`
- Create: `web/frontend/src/components/FlowGauge.tsx`
- Create: `web/frontend/src/components/SectorHeatmap.tsx`
- Create: `web/frontend/src/components/DerivativesStrip.tsx`
- Create: `web/frontend/src/components/StatusBar.tsx`
- Modify: `web/frontend/src/pages/MarketOverview.tsx`

**Interfaces:**
- Consumes: `GET /api/market-overview` response (Task 2)
- Consumes: SSE events via `useSSE` hook (Task 6)
- Produces: Complete Market Overview page matching spec section 5.1

- [ ] **Step 1: Implement `useMarketData` hook**

Calls `fetchJSON("/market-overview")` on mount and on SSE refresh event. Returns `{data, loading, error, refresh}`.

- [ ] **Step 2: Implement `KPICard` component**

Props: `{title: string, value: string|number|null, change?: number, arrow?: boolean, color?: string}`.
Renders: panel-colored card with title, large value, change % with up/down arrow, colored by positive/negative.

- [ ] **Step 3: Implement `CandlestickChart` component**

Props: `{candles: {time, open, high, low, close}[], ema?: {time, value}[], volume?: {time, value}[]}`.
Uses `lightweight-charts` `createChart()`:
- Dark theme: background `#071923`, text `#91A9BE`, grid `#0B6478` at 0.1 opacity
- Candlestick series: up `#00E6A8`, down `#FF405A`
- Line series for EMA overlay: `#00E5FF`
- Histogram series for volume: `#00E5FF` at 0.3 opacity
- Crosshair, time scale, price scale configured
- `autoSize: true` for responsive

- [ ] **Step 4: Implement `BreadthBars` component**

Props: `{advancing: number, declining: number, unchanged: number}`.
Horizontal stacked bar using CSS flexbox. Green/red/gray segments with labels.

- [ ] **Step 5: Implement `FlowGauge` component**

Props: `{fii_5d, fii_10d, fii_20d, dii_5d, dii_10d, dii_20d, unit}`.
Horizontal bars for FII/DII flows. Green for positive, red for negative. Labels with values.

- [ ] **Step 6: Implement `SectorHeatmap` component**

Props: `{sectors: {name, change_pct}[]}`.
CSS Grid of cells. Background color interpolated: deep red (-3%) → neutral (#071923, 0%) → deep green (+3%). White text with sector name and % value.

- [ ] **Step 7: Implement `DerivativesStrip` component**

Props: derivatives object from API.
Horizontal row of cards: OI PCR, Volume PCR, Max Pain, ATM IV, unusual count. Each with icon, label, value.

- [ ] **Step 8: Implement `StatusBar` component**

Props: `{freshness: {age_seconds, level, next_refresh}}`.
Shows data age with freshness color (green/amber/red/critical), next refresh countdown.

- [ ] **Step 9: Assemble `MarketOverview.tsx`**

Layout:
- Top: 7 `<KPICard>` in flex row (NIFTY, Bank NIFTY, VIX, A/D ratio, PCR, Max Pain, Regime)
- Three columns (`grid grid-cols-[50%_26%_24%]`):
  - Left: `<CandlestickChart>` with NIFTY candles + EMA
  - Center: `<BreadthBars>` + `<FlowGauge>`
  - Right: `<SectorHeatmap>`
- Bottom: `<DerivativesStrip>`
- Footer: `<StatusBar>`

Uses `useMarketData` hook. Shows loading skeleton while fetching.

- [ ] **Step 10: Verify in browser**

Start API (`python web_main.py`) and frontend (`npm run dev`). Navigate to Market Overview. Verify:
- KPI cards render with data (or "N/A" if no cache)
- Chart renders candles with crosshair interaction
- Breadth bars, flows, sectors, derivatives all populated
- SSE reconnects after refresh

- [ ] **Step 11: Commit**

```bash
git add web/frontend/src/
git commit -m "feat(web): Market Overview page with TradingView chart and all panels"
```

---

### Task 8: Stock Analysis Page (Frontend)

**Files:**
- Create: `web/frontend/src/hooks/useStockAnalysis.ts`
- Create: `web/frontend/src/components/SymbolSearch.tsx`
- Create: `web/frontend/src/components/MomentumGauge.tsx`
- Modify: `web/frontend/src/pages/StockAnalysis.tsx`

**Interfaces:**
- Consumes: `GET /api/stock/{symbol}` response (Task 3)
- Consumes: `GET /api/symbols` for autocomplete (Task 3)
- Consumes: `CandlestickChart` component (Task 7)
- Produces: Complete Stock Analysis page matching spec section 5.2

- [ ] **Step 1: Implement `useStockAnalysis` hook**

```typescript
function useStockAnalysis(): {
  data: StockData | null;
  loading: boolean;
  error: string | null;
  analyze: (symbol: string) => void;
}
```
Calls `fetchJSON(`/stock/${symbol}`)` when `analyze()` is called.

- [ ] **Step 2: Implement `SymbolSearch` component**

Props: `{onSelect: (symbol: string) => void, symbols: {symbol, name}[]}`.
Text input with dropdown autocomplete filtered by typed text. Recent searches stored in localStorage (try/catch wrapped). Debounce 300ms.

- [ ] **Step 3: Implement `MomentumGauge` component**

Props: `{score: number, label: string}`.
Circular SVG gauge (0-100). Color gradient: red (0-30) → amber (30-60) → green (60-100). Score number in center, label below.

- [ ] **Step 4: Assemble `StockAnalysis.tsx`**

Layout:
- Top: `<SymbolSearch>` + recent search chips
- Two columns (`grid grid-cols-[60%_40%]`):
  - Left: `<CandlestickChart>` (reuse from Task 7) with EMA overlays
    - Below: RSI line chart (separate `createChart` instance, 30/70 reference lines)
    - Below: MACD chart (histogram + signal line)
  - Right panel (scrollable):
    - `<MomentumGauge>` with overall score
    - Key levels table (support/resistance)
    - Volatility card (ATR, ADX)
    - Research factors list
    - Risk context card

- [ ] **Step 5: Verify in browser**

Start both servers. Navigate to Stock Analysis. Search "RELIANCE". Verify:
- Chart renders with candles + EMA overlays
- RSI/MACD subplots render below
- Right panel shows score gauge, levels, volatility
- Invalid symbol shows error message
- Recent searches persist across page navigations

- [ ] **Step 6: Commit**

```bash
git add web/frontend/src/
git commit -m "feat(web): Stock Analysis page with search, charts, and analysis panels"
```

---

### Task 9: Market Analysis Page (Frontend)

**Files:**
- Modify: `web/frontend/src/pages/MarketAnalysis.tsx`

**Interfaces:**
- Consumes: `GET /api/market-analysis` response (Task 4)
- Consumes: `CandlestickChart` (Task 7, reused as line/area chart)
- Consumes: SSE events via `useSSE` hook (Task 6)
- Produces: Complete Market Analysis page matching spec section 5.3

- [ ] **Step 1: Implement Market Analysis page sections**

Single-column scrollable layout with 6 sections, each in a panel card:

1. **Regime Analysis**: regime badge (colored by bull/bear/sideways), description text
2. **Breadth Deep-Dive**: breadth data cards (advancing/declining/unchanged, A/D ratio, % above EMAs), horizontal bars for DMA percentages
3. **Sector Performance**: table with sector name, 1D/1W/1M columns (from `sector_rows` data). Sortable by column click. Color values by positive/negative.
4. **Institutional Flow**: FII/DII flow bars (5D/10D/20D) using CSS bars. Flow regime badge. Streak indicators.
5. **Derivatives Intelligence**: NIFTY + Bank NIFTY derivatives cards side by side. OI PCR, Max Pain, IV, unusual activity table.
6. **Event Risk Calendar**: Table of upcoming events with date, event name, impact rating (if available from `event_risk_context`).

Each section uses a `<section>` with panel styling (`bg-[--bg-panel] border border-[--border] rounded-lg p-4`).

- [ ] **Step 2: Add data fetching**

Hook: `useMarketAnalysis()` — calls `fetchJSON("/market-analysis")` on mount and SSE refresh. Returns `{data, loading, error}`.

- [ ] **Step 3: Verify in browser**

Navigate to Market Analysis. Verify all 6 sections render with data or graceful "N/A" for missing fields. Scroll through all sections.

- [ ] **Step 4: Commit**

```bash
git add web/frontend/src/
git commit -m "feat(web): Market Analysis page with all 6 analysis sections"
```

---

### Task 10: Production Build + Static Serving + Final Integration

**Files:**
- Modify: `web/api/main.py` (mount static files)
- Modify: `web_main.py` (build step, prod serving)
- Modify: `tests/test_web_api.py` (add integration tests)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Single-command launcher: `python web_main.py` serves everything on port 8501

- [ ] **Step 1: Add static file serving to FastAPI**

In `create_app()`: if `web/frontend/dist/` exists, mount it as static files at `/` with `html=True` (SPA fallback). API routes take precedence (they are registered first).

- [ ] **Step 2: Add build command to `web_main.py`**

`python web_main.py --build`: runs `npm run build` in `web/frontend/`, outputs to `web/frontend/dist/`.
`python web_main.py`: starts uvicorn, serves both API and built frontend.
`python web_main.py --dev`: API only, frontend via Vite dev server.

- [ ] **Step 3: Write integration test**

```python
class TestFullIntegration(unittest.TestCase):
    def setUp(self):
        from starlette.testclient import TestClient
        self.client = TestClient(create_app())

    def test_all_api_endpoints_return_200(self):
        for path in ["/api/health", "/api/market-overview", "/api/market-analysis", "/api/symbols"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, 200, f"{path} returned {r.status_code}")

    def test_guardrails_in_all_market_responses(self):
        for path in ["/api/market-overview", "/api/market-analysis"]:
            with self.subTest(path=path):
                r = self.client.get(path)
                body = r.json()
                self.assertIn("guardrails", body)
```

- [ ] **Step 4: Build frontend and test prod mode**

```powershell
python web_main.py --build
python web_main.py
```
Open `http://localhost:8501`. All 3 pages should work without Vite dev server.

- [ ] **Step 5: Run full test suite**

Run: `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
Expected: All tests pass (existing 397+ plus new web API tests).

- [ ] **Step 6: Commit**

```bash
git add web/ web_main.py tests/test_web_api.py
git commit -m "feat(web): production build, static serving, and integration tests"
```

---

## File Map Summary

| File | Responsibility |
|------|---------------|
| `web_main.py` | CLI launcher: uvicorn + build |
| `web/api/main.py` | FastAPI app factory, CORS, router registration, lifespan |
| `web/api/report_loader.py` | Shared cached report loading |
| `web/api/scheduler.py` | APScheduler + SSE broadcast + refresh lock |
| `web/api/routes/market.py` | `/api/market-overview` |
| `web/api/routes/stock.py` | `/api/stock/{symbol}`, `/api/symbols` |
| `web/api/routes/analysis.py` | `/api/market-analysis` |
| `web/api/routes/events.py` | `/api/refresh`, `/api/events` (SSE) |
| `web/frontend/src/App.tsx` | Router, sidebar nav, top bar |
| `web/frontend/src/pages/MarketOverview.tsx` | 3-column dashboard |
| `web/frontend/src/pages/StockAnalysis.tsx` | Search + chart + analysis panels |
| `web/frontend/src/pages/MarketAnalysis.tsx` | 6-section scrollable analysis |
| `web/frontend/src/components/*.tsx` | Reusable UI components |
| `web/frontend/src/hooks/*.ts` | Data fetching + SSE hooks |
| `web/frontend/src/lib/api.ts` | Fetch wrappers |
| `web/frontend/src/lib/theme.ts` | Design token constants |
| `tests/test_web_api.py` | API endpoint tests |
