# Master Prompt — Nova Web Terminal: Professional UI + Live Data Feed

Paste everything below the line into a fresh agent session opened at the repo root.

---

You are working in the Nova repo (`C:\Users\Anirudh\nova`). Read `AGENTS.md`, `CLAUDE.md`,
`docs/ARCHITECTURE.md` and `docs/UI_UX_GUIDE.md` (if present) before touching code.

## Goal

Turn the web dashboard (`web/api` FastAPI + `web/frontend` React 19 / Vite 8 / Tailwind 4)
into a professional, dense, dark trading-terminal UI (Bloomberg / TradingView class) driven by a
**live, read-only market data feed** pushed over the existing SSE channel. Analysis only.

## Non-negotiable rules

1. **Analysis only.** No orders, no broker execution, no BUY/SELL labels. `GuardrailsBar` stays
   visible on every page; `buy_sell_authorized: False` survives every response that has it.
2. **No invented data.** Every live value carries `source` and `as_of`. Stale (> 2 × poll
   interval), missing or failed values render as stale/`—` with a reason — never a guess,
   never a frozen number shown as live.
3. **Cache-first.** Never trigger the full NSE equity scan from the live loop. The 2333-stock
   scan stays on `/api/refresh` and the scheduler cron only.
4. **Read-only feeds.** Use only existing adapters: `analysis/data/nse_feed.py`
   (`get_normalized_stock_quote`, Indian Market MCP over stdio) and the optional
   `analysis/data/dhan_feed.py` (`get_index_quote`, `get_last_price`; off unless
   `is_configured()`). No new data vendors, no API keys in code or chat.
5. **Small reversible steps.** One phase per commit. Do not touch `venv/`,
   `analysis/data/cache/`, backups, or `*.wav`.

## Current state (verify, don't assume)

- SSE: `web/api/routes/events.py` `GET /api/events` streams queue messages from
  `web/api/scheduler.py` (`subscribe` / `_broadcast`). Today only `refresh_complete` /
  `refresh_failed` are sent.
- Frontend: `src/hooks/useSSE.ts` (single `EventSource`), `SSEContext.tsx`,
  `useMarketData.ts`, `useStockAnalysis.ts`; pages `MarketOverview`, `MarketAnalysis`,
  `StockAnalysis`; components `TickerTape`, `SectorHeatmap`, `BreadthBars`, `FlowGauge`,
  `DerivativesPanel`, `IndicatorStrip`, `MomentumGauge`, `ui.tsx` (`Panel`).
- Tokens: `src/lib/theme.ts` (`COLORS`, `CHART_FONT`), `src/index.css`; desktop tokens in
  `styles/design_tokens.py` — keep both palettes in step.
- Schedule helpers: `src/lib/schedule.ts` (`istSession`, `nextRefreshLabel`).

## Phase 1 — Live feed backend

- Add `web/api/live_feed.py`: an asyncio task started in the app `lifespan` that, **only
  during the NSE session (09:15–15:30 IST, Mon–Fri, excluding holidays already known to the
  codebase)**, polls a bounded watchlist every N seconds (default 5s indices, 15s stocks,
  configurable via env) using `asyncio.to_thread` around the existing adapters.
- Watchlist = NIFTY, BANKNIFTY, INDIAVIX + symbols currently open in any client (clients send
  them via `POST /api/live/watch` with the same origin check as `/api/refresh`), capped at 25.
- Broadcast through the existing `_broadcast` as
  `{"type":"tick","symbol","ltp","change","change_pct","volume","source","as_of"}` and a
  `{"type":"feed_status","state":"live|delayed|closed|error","reason","as_of"}` heartbeat
  every 10s. Only send ticks whose value changed.
- Per-adapter failures: exponential backoff, emit `feed_status` with the error, keep the app up.
  Out-of-session: emit `closed` and stop polling.
- Add `GET /api/live/snapshot` returning the last known tick per symbol (with `as_of`) so a
  reconnecting client can paint immediately.
- Tests (stdlib `unittest`, offline, adapters mocked) in `tests/test_web_api.py` or a new
  `tests/test_live_feed.py`: session gating, change-only emission, stale flagging, backoff,
  watchlist cap, origin rejection.

## Phase 2 — Frontend live layer

- Extend `SSEEvent` in `useSSE.ts` with `tick` and `feed_status`. Keep one `EventSource` for
  the whole app (via `SSEContext`); on reconnect fetch `/api/live/snapshot`.
- Add `useLiveQuote(symbol)` returning `{ltp, change_pct, as_of, stale}`; staleness computed
  client-side against `as_of`, not arrival time.
- Batch tick updates per animation frame so 25 symbols × 5s never re-renders whole pages.
- Header status pill: LIVE (green pulse) / DELAYED / MARKET CLOSED / FEED ERROR + last
  update time in IST. Every live number shows a tiny source tag on hover.

## Phase 3 — Professional UI

- Layout: fixed top bar (brand, `SymbolSearch` with ⌘K / Ctrl+K, session clock IST, feed
  pill), `TickerTape` below fed by live ticks, resizable grid of `Panel`s, `GuardrailsBar`
  pinned bottom. Single screen at 1920×1080 and 2560×1440, no page scroll on desktop;
  stacks cleanly at 1280 and tablet widths.
- Visual system: near-black background, 1px hairline panel borders, tabular-nums monospace
  for every number, 2 accent colours max plus up/down green/red that also pass for
  colour-blind users (add ▲▼ glyphs, never colour alone). WCAG AA contrast on all text.
- Motion: price cells flash up/down for 600 ms on change; respect `prefers-reduced-motion`.
- Charts: one chart library only. Prefer the already-installed stack; if a candlestick
  library is needed, use `lightweight-charts` (exact pinned version) and append live ticks to
  the last candle — do not re-fetch history per tick.
- Every panel has loading skeleton, empty state, stale state and error state. No spinners
  over stale data that hide it.
- Keyboard: `/` focuses search, `g o` / `g a` / `g s` switch pages, `Esc` closes overlays.

## Phase 4 — Verify and document

1. `.\venv\Scripts\python.exe -m unittest discover -s tests -v` — all green.
2. `npm run build` in `web/frontend` — zero TS errors.
3. Run the dashboard, open it in the browser preview, confirm: feed pill state matches the
   clock, ticks update during session, closed state outside it, stale flag appears when the
   adapter is stopped, `GuardrailsBar` visible on every page. Screenshot at 2560 and 1280 into
   `screenshots/`.
4. Update `CHANGES.md`, `docs/VALIDATION.md`, `docs/ARCHITECTURE.md` (live feed path), README
   API section (`/api/live/*`, new SSE event types).

## Done when

Live ticks flow end-to-end during market hours, every number is sourced and timestamped,
stale/closed/error states are honest, the full test suite and frontend build pass, and no
trading capability exists anywhere in the diff.
