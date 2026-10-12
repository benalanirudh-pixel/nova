# CHANGES.md

This file tracks context, workflow, and behavior changes important for future
coding agents.

## 2026-10-12 - Stock Analysis page rebuilt (two-column, no chart)

The Stock Analysis page now has only three areas: the controls panel, a Stock
Overview column, and an AI Research Report column.

- Removed from this page: the price/volume/RSI/MACD chart, the interactive
  report tabs, the standalone data-quality table and market-wide panel (no
  oversized empty panels, no giant raw-text box).
- Left column ("Stock Overview"): company identity (name, symbol, exchange,
  sector tag when resolvable), prominent last price + change with the
  last-session timestamp, four KPI cards (Trend, Momentum Score, RSI 14, MACD)
  and a "Key observations" card derived from real metrics.
- Right column ("AI Research Report"): header with AI icon + compact
  disclaimer + status + Copy; Executive Summary with an Overall Bias card;
  side-by-side Bullish/Bearish factors; a slim Key Price Levels table (R2/R1/
  current/S1/S2, "support/resistance not calculated" when absent); and a
  compact collapsed "Show full report" so the full AI text is preserved.
- Empty state before analysis: "Ready to analyze a stock" with the required
  subtitle; a loading indicator replaces it while analyzing.
- The two columns use a responsive layout (side-by-side when wide, stacked when
  narrow); controls (symbol, mode, range, Analyze, Enter-to-run) and the
  analysis/Ollama pipeline are unchanged.

New adapter helpers (pure): `stock_observations(metrics)` and
`stock_sector(symbol)`. Analysis-only guardrails and honesty preserved; no
fabricated metrics, levels, fundamentals or market data.

Files changed: `market_lab_ui.py` (Stock Analysis page only),
`market_lab/stock_adapter.py` (`stock_observations`, `stock_sector`),
`tests/test_gui_smoke.py`, `tests/test_stock_adapter.py`.

Validation: `ast.parse` on `market_lab_ui.py`/`stock_adapter.py`; offscreen
render shows the empty state, then the two columns with Stock overview / Key
observations / AI Research Report / Executive Summary / Overall Bias / Bullish /
Bearish / Key price levels, Copy + collapsed raw report, and no chart;
`tests.test_gui_smoke.TestStockAnalysisPage` + `tests.test_stock_adapter` -> OK;
full suite `Ran 371 tests ... OK` (366 -> 371).

## 2026-10-12 - AI Research Report redesigned (structured, tabbed)

Replaced the large plain-text report box and the row of oversized UNAVAILABLE
cards in the Stock Analysis page with a structured report (only the AI Research
Report section and its widgets changed; search/button/nav/chart untouched).

New `market_lab/report_parser.py` (pure, stdlib): parses the AI report into
sections/bias/key-levels and always preserves the raw text; detects the
explicit bias (INSUFFICIENT EVIDENCE/BULLISH/BEARISH/NEUTRAL/MIXED) without
inventing a stance.

`market_lab_ui.py` (`render_stock_result` -> new `_render_ai_report`):
- Header: AI icon, "AI Research Report" + subtitle, "Success - generated just
  now", compact disclaimer, working Copy and Re-run actions.
- Executive Summary: bias side card (colored) + KPI strip (trend, momentum
  score, RSI 14, MACD) from real metrics.
- Bullish / Bearish evidence panels derived from the report's own sections
  (green/red bullets; honest empty state).
- Interactive tabs: Technical Analysis / Fundamental Context / Business
  Overview / Risks & Outlook (QTabWidget, content swaps in place).
- Compact Key Price Levels table (R2/R1/current/S1/S2; absent levels explained,
  never treated as zero).
- Full raw report kept in a scrollable fallback so nothing is dropped; a failed
  AI run still preserves the previous good report.
- Fund/institutional/derivatives/S-R "oversized unavailable" cards removed;
  limitations now shown as compact notes inside the relevant section.

Unavailable-data honesty, analysis-only guardrails and all backend/AI data
sources are unchanged.

Files changed: `market_lab_ui.py`, `market_lab/report_parser.py` (new),
`tests/test_report_parser.py` (new, 10), `tests/test_gui_smoke.py`
(+`test_report_is_structured_with_tabs`, `test_copy_report_action_exists`).

Validation: `ast.parse` on `market_lab_ui.py`/`report_parser.py`; offscreen
render shows the 4 tabs, preserved raw report, bias card, and no oversized
UNAVAILABLE card; `tests.test_report_parser` -> 10 OK,
`tests.test_gui_smoke.TestStockAnalysisPage` -> OK; full suite
`Ran 366 tests ... OK` (354 -> 366).

## 2026-10-12 - Premium ANALYZE button (Stock Analysis only)

Replaced the plain Analyze button with a dedicated `AnalyzeButton`
(`market_lab_ui.py`): cyan gradient `#00D9F5 -> #00E6C8`, 12px radius, bold
uppercase `ANALYZE` in dark navy `#031018`, left lightning icon, Enter-key hint
chip inside the right edge (hidden when the button is narrow), and QSS
`hover`/`pressed`/`focus`/`disabled` states. `set_busy()` toggles the
`ANALYZING …` + disabled state and restores `ANALYZE` on completion/failure.
The existing `.clicked -> run_stock_analysis` handler and all backend behavior
are unchanged; no second button or duplicate handler. Only the button and its
styling changed — search, mode, range, result rendering are untouched.

Validation: `ast.parse` ok; offscreen build confirms objectName
`analyzePrimaryButton`, gradient/`#00D9F5`/12px radius/hover-pressed-focus-
disabled in the QSS, lightning icon present, and `set_busy` toggling label +
enabled; `tests.test_gui_smoke` -> 52 OK (incl. the new button test); full
suite `Ran 354 tests ... OK`.

## 2026-10-11 - Fix corrupted stock chart (non-finite + future-date validation)

Root cause of the corrupted chart: the plot received **NaN warm-up values**
from `calculate_rsi`/`calculate_macd` (first 14/26 bars) and used a **fallback
epoch** for unparsed dates, so pyqtgraph rendered vertical spikes and the
auto-ranging viewboxes exploded (RSI \u00b150000, huge green candles, MACD
lines). The source data itself was clean (RELIANCE RSI 28-85, MACD -29..6, no
bad OHLC, no future dates), so this was a rendering/validation gap.

Fixes:
- `market_lab/stock_adapter.py`: new `to_epoch()` and `validate_candles()`
  which return the candles sorted chronologically with future-dated (> now +
  1 day), unparseable, duplicate, and non-finite/inconsistent-OHLC rows
  dropped, while preserving original indices so RSI/MACD stay aligned. A
  diagnostic `report` counts each drop.
- `market_lab/widgets.py` (`PgCandleChart`): `set_data()` now runs
  `validate_candles`, plots **only finite points** for candles/MAs/RSI/MACD
  (histogram warm-up -> 0), and **pins the shared time axis** to the validated
  min/max range so nothing extends into the future; RSI Y is locked to 0-100;
  volume/MACD keep independent Y axes.

Regression tests: `tests/test_stock_adapter.py` (+`TestValidateCandles`:
sorting, dedupe, alignment, future/bad-date/bad-OHLC drop) and
`tests/test_gui_smoke.py` (+`test_pg_skips_nonfinite_and_future`: NaN warm-up
and a future candle must not raise or blow up the axes).

Verified with real RELIANCE data: shared axis 2026-04-09 -> 2026-10-09, price
~1134-1500, volume own axis 0-46M, RSI -2..102, MACD -32.7..9.1; a suspicious
input (`[CHART DATA] dropped rows: future=1`) is logged.

Root cause of the broken chart: `GraphicsLayoutWidget.addPlot()` called with no
row/col added the four panels as **4 columns in 1 row** (narrow horizontal
strips) instead of a vertical stack, and the ViewBoxes were never auto-ranged,
so x stuck at the default `[0, 1]`.

Fixes in `market_lab/widgets.py` (`PgCandleChart`):
- Panels are now added as **4 rows x 1 column** with row stretch factors (price
  dominant ~6, volume/RSI/MACD ~2 each) and an Expanding size policy, so the
  price chart occupies the full chart-column width.
- **Shared datetime axis**: the price plot uses a `DateAxisItem`; volume/RSI/MACD
  are `setXLink`-ed to it and the price plot is `autoRange`-ed, so all four share
  one epoch time range (verified identical x-range across panels).
- BarGraphItem widths and the candlestick body width are expressed in real time
  units (seconds), so volume/MACD bars align to the time axis.

Fixes in `market_lab_ui.py` (Stock Analysis page):
- AI report panel now wraps lines, and `_set_stock_ai()` preserves the previous
  successful report for the same symbol when a new AI call fails (instead of
  replacing it with only an error/disclaimer).
- Unavailable panels now state precise reasons (fundamentals source missing,
  stock-level holdings unavailable, stock option chain unavailable, S/R not
  calculated).

Verified: offscreen render -> 4 rows x 1 col, all panels full width (622px),
identical x-range (shared time axis), price 218px tall; AI panel holds the full
report (~4.2k chars). `tests.test_gui_smoke.TestPyQtGraphAndIcons` -> 4 OK incl.
a new `test_pg_panels_are_stacked_and_share_time_axis`. Full offline suite:
`Ran 345 tests ... OK`.

## 2026-10-11 - PyQtGraph stock chart + Lucide-style icons (Stock Analysis)

Uses the newly installed `pyqtgraph` for the Stock Analysis technical chart and
ships a small inline Lucide-style SVG icon set (no new dependency; QTsvg-based).

- `market_lab/widgets.py`: `PgCandleChart` — a pyqtgraph panel with **price
  candles + MA20/50/200 overlays, volume, RSI (14) with 30/70 guide lines, and
  MACD + signal + histogram**, real series only (short/missing series are simply
  not drawn). Ships a minimal `_CandlestickItem`. `PG_AVAILABLE` flag lets the
  UI fall back to the existing QPainter `CandleChart` if pyqtgraph is absent.
- `market_lab/icons.py` (new): 16 inline Lucide-style SVG icons rendered via
  QtSvg (`icon_pixmap`/`make_icon`/`svg_markup`); `icon_available` falls back to
  text-only when QtSvg is missing.
- `market_lab/stock_adapter.py`: `stock_oscillators(candles)` — real RSI/MACD
  series from the same candles via `technical_engine.calculate_rsi/calculate_macd`
  (no new math).
- `market_lab_ui.py`: the Stock Analysis page renders `PgCandleChart` with the
  RSI/MACD series when pyqtgraph is available (else the lightweight chart), the
  worker now returns oscillators, and the controls gain Lucide icons (search +
  analyze).

Deliberately NOT applied: qt-material — it forces its own palette and is
incompatible with Nova's existing NOVA theme tokens, so the custom QSS theme is
kept (as instructed: only if compatible).

Files changed: `market_lab_ui.py`, `market_lab/widgets.py`,
`market_lab/stock_adapter.py`, `market_lab/icons.py` (new),
`tests/test_gui_smoke.py` (+`TestPyQtGraphAndIcons`), `tests/test_stock_adapter.py`
(+`TestOscillators`).

Validation: `ast.parse` ok; offscreen render of `PgCandleChart` (price/volume/RSI/
MACD) and the full Stock Analysis page (uses `PgCandleChart`, PNG proxy saved);
`tests.test_gui_smoke` -> 46 OK incl. chart+icon tests; `tests.test_stock_adapter`
-> oscillator tests OK. Full offline suite: `Ran 345 tests ... OK` (339 -> 345; +6).

No backend/Ollama/cache/data change; no mock data introduced anywhere.

## 2026-10-11 - Added pyqtgraph + qt-material (deps)

Installed into the local venv for richer charting/theming (available to the
Stock Analysis charts and general UI):

- `pyqtgraph==0.14.0` — verified: `pyqtgraph.PlotWidget()` constructs offscreen
  (intended for candlestick/RSI/MACD panels).
- `qt-material==2.17` — verified: `qt_material.build_stylesheet("dark_teal.xml")`
  returns a ~30k-char QSS and applies to a QApplication (API is
  `build_stylesheet` in v2.x, not `load_stylesheet`).

Regenerated `requirements.txt` (109 pkgs, plain UTF-8, no BOM) and mirrored it in
`pyproject.toml`; `tests/test_packaging.py` confirms the two stay in sync.
No application code changed yet — the packages are available but not yet wired
into widgets (charts remain the existing lightweight QPainter components).
Full offline suite: `Ran 339 tests ... OK`.

## 2026-10-11 - AI Stock Analysis terminal (per-stock; any symbol)

Added a stock-specific analysis mode: enter ANY supported NSE symbol and get a
comprehensive report for THAT stock only (RELIANCE is just an example). Reuses
the existing technical engine, candles, and Ollama client; no new backend.

New files:
- `market_lab/stock_adapter.py` — read-only per-stock adapter:
  `resolve_symbol` (symbol_master), `stock_metrics` (technical_engine.analyze_stock:
  price/RSI/MACD/ATR/EMAs/returns/52w/trend/momentum), `stock_candles`
  (get_price_history daily OHLCV + real MA20/MA50/MA200 via technical_engine),
  `kpi_tiles`, `data_quality` (honest AVAILABLE/PARTIAL/UNAVAILABLE),
  `market_context` (clearly-labeled market-wide secondary only). It never
  computes fundamentals/stock-level institutional/stock options/VaR and marks
  them UNAVAILABLE (never fabricated).
- `tests/test_stock_adapter.py` (10 tests; search_symbols/get_price_history
  stubbed; MA math uses the real engine).

`market_lab/market_lab_brain.py`: added `analyze_stock_report(symbol, metrics,
candles, report, mode)` — a focused per-stock prompt reusing the SAME Ollama
client/model/options (not a second engine). Mode quick/full/institutional
changes the task. Returns the required disclaimer: "AI-generated analysis based
on available market data. For informational and educational purposes only. Not a
validated prediction or instruction to trade." STOCK_SYSTEM_PROMPT enforces
stock-only scope, no fabricated values, and INSUFFICIENT EVIDENCE when warranted.

`market_lab/market_lab_ui.py`:
- New sidebar page **Stock Analysis** (index 1). Nav reordered: Markets,
  Stock Analysis, Market Report, Nova Analysis, Factor Backtest, Event Risk.
  Updated the off-page switch targets accordingly (analysis->3, backtest->4,
  watchlist/search->3).
- `build_stock_page`: SYMBOL input (Enter submits), MODE selector
  (Quick/Full/Institutional, Full default), RANGE (3M/6M/1Y), ANALYZE button,
  live status line; body rebuilt per run.
- Analysis runs OFF the UI thread via a `stock_analysis` Worker (no overlap with
  the report worker); on symbol change the body is rebuilt so no stale stock
  data can persist.
- Renders: stock identity (company/symbol/exchange, last price + change, H/L,
  volume, 52W H/L, last-session timestamp), KPI cards (trend, momentum score,
  RSI, MACD, ATR, relative volume), a real candlestick chart with MA20/50/200
  overlays (crosshair + OHLC hover), the AI research report, honest
  `UNAVAILABLE` cards for fundamentals/institutional/derivatives/support-
  resistance, a data-quality table, and a clearly-labeled market-wide context
  panel (secondary).
- `CandleChart` gained `set_overlays` for MA lines; `QComboBox` import added.

Files changed: `market_lab_ui.py`, `market_lab_brain.py`, `market_lab/widgets.py`,
`tests/test_gui_smoke.py` (nav indices 5->6 / backtest page 4; +TestStockAnalysisPage),
`tests/test_market_lab_brain.py` (+TestAnalyzeStockReport).

Validation:
- Real adapter run for RELIANCE: resolve -> "Reliance Industries Limited (NSE)";
  metrics price 1170.30, RSI 35.42, MACD -26.80, ATR 22.22, trend
  STRONG_DOWNTREND; 126 daily candles with MA20/MA50 overlays (NSE-MCP live
  path; child cleaned up).
- `tests.test_stock_adapter` -> 10 OK; `TestAnalyzeStockReport` -> 4 OK;
  `tests.test_gui_smoke` -> 46 OK (incl. new Stock Analysis page tests).
- Full offline suite: `Ran 339 tests ... OK` (324 -> 339; +15).

Analysis-only preserved: no broker/orders, no fabricated data, symbol-only
analysis, market-wide context clearly secondary.

## 2026-10-11 - Terminal alignment pass (uniform grid, no ragged cards)

Visual-consistency pass so the terminal reads as one aligned grid (presentation
only; all tests/data unchanged):

- Uniform KPI card height (96px) and stat/summary card height (78px); indicator
  cards fixed 116px; index cards share a minimum height (330px) and a taller
  chart area, so the Dashboard top row aligns.
- Card value/sub/note labels set to no-wrap (clip + tooltip) so long values
  can't stretch a row and break the grid.
- Uniform compact table rows (`defaultSectionSize(26)`) and consistent panel
  padding/spacing in `widgets.panel`; numeric columns stay right-aligned.

Files changed: `market_lab_ui.py`, `market_lab/widgets.py`.

Validation: `ast.parse` on both files; offscreen render confirms uniform card
heights (KPI 96, indicators 116, index min 330). Full offline suite ->
`Ran 324 tests ... OK` (unchanged).

## 2026-10-11 - Institutional UI upgrade for Sections 03-08

Upgraded the six remaining Market Report sections into a cohesive, dense,
institutional terminal (presentation only; real data + honest N/A preserved).

Reusable components (market_lab/widgets.py + market_lab_ui.py): `GroupedBarChart`
(grouped categorical bars, zero baseline, legend), reuse of `PerfBar`/`FillBar`
as inline table bars, shared `_stat_card`/`_cards_row` summary strips, and
view-model summaries (`sector_summary`, `uptrend_summary`, `flow_series`,
`risk_cards`, `factor_summary`).

- 03 Sector: summary strip (Strongest 20D / Weakest 20D / Sectors tracked) +
  ranked table (#, Sector, 20D %, Perf, RS 20D, Regime) with a real centered
  performance bar per row; no fake sparkline.
- 04 Technical: summary cards (Stocks analyzed / Strong uptrends / Strong
  downtrends) + Rank/Symbol/Score/Meter/Trend table with a real score meter
  + indicator-availability chips (RSI/MACD/S-R NOT_AVAILABLE) + "score is not a
  probability" note.
- 05 Derivatives: summary strip (Spot/Expiry/OI PCR/Max pain) + Metric | NIFTY |
  BANK NIFTY table + the engine's real `positioning_interpretation` insight card
  + "Unusual OI activity" table + note (no per-strike OI chart in the report; OI
  levels are not labeled guaranteed support/resistance).
- 06 Institutional Flow: summary cards (FII 20D / DII 20D / Regime / Latest date)
  + real FII-vs-DII grouped bar across 5D/10D/20D (₹ crore, zero baseline) +
  metrics/coverage/signal table + EOD-flow note.
- 07 Risk: cards for the real market-risk context (realized vol 20D/60D, ATR %,
  vol percentile, regime/direction, expected daily move) + honest N/A cards for
  VaR/Sharpe/drawdown (not computed) with an amber limitation note.
- 08 Factor Rankings: summary strip (Factors evaluated / Stocks covered / Best
  composite / Rank date) + factor-coverage table (QUALITY/VALUE NOT_AVAILABLE) +
  top/bottom composite-z tables (z colored) + equal-weight method note.

Files changed: market_lab_ui.py, market_lab/widgets.py, market_lab/view_model.py,
tests/test_gui_smoke.py (updated column counts for new columns).

Validation: ast.parse on all files; offscreen render of the real report shows
03 (5 perf bars), 04 (10 score meters), 05 (summary+interpretation+unusual
tables), 06 (GroupedBarChart FII/DII), 07 (vol cards + N/A), 08 (coverage+top+
bottom); footer/guardrails pinned with no overlap at 1600x900. Full offline
suite -> Ran 324 tests ... OK.

Honest limitations: no per-strike OI-distribution chart and no per-date FII/DII
history exist in the saved report, so those are notes/N-A rather than synthetic
charts. Pixel verification is manual (offscreen render + PNG proxy only).

## 2026-10-11 - Replace factor panel with an honest "Top Uptrend Stocks" screen

Requested: remove the factor-ranking panel and show the most-uptrend stocks.
Because Nova is analysis-only and its engine explicitly does NOT compute
long-run growth fundamentals (value/quality/growth), the new panel is labeled a
**technical uptrend screen**, not a growth forecast or signal.

- Removed the right-side factor-ranking panel (`build_factor_panel`,
  `render_factor`, `factor_*` widgets, splitter column) and its `display_report`
  call.
- Added `build_uptrend_panel` / `render_uptrend`: a `#, Symbol, Score, Trend`
  table ranked by the report's real `top_technical_stocks` technical score
  (strongest first, top 15), trend colored via the existing trend palette, with
  a note stating it's the current trend/score, that fundamentals are not
  computed, and that it's not a buy/sell signal.
- Section 08 (Factor Rankings) remains in the 10-section report unchanged
  (still real composite z, QUALITY/VALUE honestly NOT_AVAILABLE) — only the
  duplicate side panel was replaced.

Files changed: `market_lab_ui.py`, `tests/test_gui_smoke.py`
(factor-panel assertion replaced with an uptrend empty-state assertion).

Validation: `ast.parse` ok; real cached report -> uptrend table lists top
STRONG_UPTREND symbols (e.g. BLUSPRING/ZIMLAB/CPPLUS 100.0, PLASTIBLEN 98.0);
empty report -> honest "No technical top-list" + a single "—" row.
`tests.test_gui_smoke(44 OK)`; full offline suite -> `Ran 324 tests ... OK`.

## 2026-10-11 - Market Report sections 03-08 redesigned (aligned/colorized, dense)

Applied the same premium treatment used for Sections 01/02 to the remaining
Market Report sections (presentation only; real data + honesty preserved):

- 03 Sector Intelligence: ranked table `#, Sector, 20D %, RS 20D, Regime`;
  right-aligned numerics, centered rank/regime, 20D % and RS 20D colored by sign,
  regime as a centered colored badge (POSITIVE green / NEGATIVE red / else muted).
  New `_paint_cell` / `_regime_color` helpers. No per-sector sparkline column
  (no genuine per-sector series) - honest, per the reference rule.
- 04 Technical Analysis: `Rank, Symbol, Score, Trend` with colored trend
  (uptrend/bullish green, downtrend/bearish red) and cyan score emphasis; the
  RSI/MACD/support-resistance note carries a tooltip explaining the honest N/A.
- 05 Derivatives Intelligence: compact `Metric | NIFTY | BANK NIFTY` table (spot,
  expiry, OI PCR, volume PCR, max pain, put/call wall, ATM IV) with an honest note
  that per-stock OI-build lists are not in the saved report.
- 06 Institutional Flow: `Metric | INR crore` with FII/DII 20D/5D colored by sign
  and the signal-eligibility cell green/amber.
- 08 Factor Rankings: TOP 10 and BOTTOM 10 composite-z tables, z colored by sign,
  QUALITY/VALUE shown honestly as NOT_AVAILABLE.
- 07 Risk and 09/10 unchanged (07 note colorized amber).

Files changed: `market_lab_ui.py`, `tests/test_gui_smoke.py`
(+`test_remaining_sections_render_tables`).

Validation: `ast.parse` ok; real cached report renders 03 (5x5), 04 (10x4),
05 (7x3), 06 (7x2), 08 (10x10 x2 tables) with no errors;
`tests.test_gui_smoke.TestRedesign` -> 5 OK; full offline suite ->
`Ran 324 tests ... OK` (323 -> 324; +1).

## 2026-10-11 - Sidebar: remove disabled "Unavailable" nav items

`market_lab_ui.py`: removed the disabled Indices/Sectors/Stocks/Screeners/
Watchlist/News/Tools entries (and the "UNAVAILABLE" label) the master-redesign
commit had added to the left rail. The sidebar now shows only the five real,
working destinations (Markets, Market Report, Nova Analysis, Factor Backtest,
Event Risk) plus the NOVA identity mark. Guardrails/guardrail footer unchanged.

Validation: `ast.parse` ok; full offline suite `Ran 323 tests ... OK`.

## 2026-10-11 - Master UI redesign: theme tokens, KPI strip, macro cards, breadth panel, expanded sidebar

A large presentation refresh of `market_lab_ui.py` / `market_lab/widgets.py`
toward the institutional-terminal reference. No backend, engine, cache, or
refresh logic changed; every value still comes from the real report.

- Centralized the exact theme palette in both modules (BG `#050B10`, sidebar
  `#061019`, panel `#091620`, card `#0D1B26`, alt row `#0F202B`, border
  `#183746`/`#102936`, text `#F2F6FA`/secondary `#91A9BE`/muted `#617A91`,
  cyan `#00D9F5`, green `#00E6A0`, red `#FF4058`, amber `#FFBD4A`). Table
  typography bumped (header 9px, data 10pt).
- **KPI strip** on the Dashboard: five cards — NIFTY 50 (price + change),
  INDIA VIX (value + change), ADVANCES (count + green fill bar + % of movers),
  DECLINES (count + red fill bar + %), A/D RATIO. New `W.FillBar` and
  `W.StackBar` widgets. All real; missing -> `N/A`.
- **Section 01 – Macro Overview** redesigned into three horizontal cards:
  dominant colored **Market Regime** (red/bearish, green/bullish, cyan/else),
  **NIFTY 50 Level** (value + real sparkline from candles), **India VIX**
  (value + 1D change + regime).
- **Section 02 – Market Breadth** redesigned into a visual internals panel:
  green/red **stacked advances-vs-declines bar** (proportions from real counts),
  big advances/declines counts + % of movers, and an A/D ratio block. Added
  `view_model.breadth_block` A/D ratio fallback = advances/declines.
- **Sidebar** expanded: working nav styled dark-blue active + cyan indicator
  (`NAV_QSS`, `switch_page` now uses `setChecked`); first tab renamed
  "Markets"; unsupported destinations (Indices, Sectors, Stocks, Screeners,
  News, Tools) are **disabled and honestly labeled** (no fake pages); Watchlist
  is a working shortcut to the Nova Analysis page; added a NOVA identity mark
  at the rail bottom.
- Header search placeholder -> `Search symbol, sector, or insight...` (still the
  real watchlist-pin behavior).

Guardrails unchanged (analysis-only, no broker/orders, honest N/A).

Files changed:
- `market_lab_ui.py`, `market_lab/widgets.py`, `market_lab/view_model.py`
- `tests/test_gui_smoke.py` (+`TestRedesign`: KPI, missing-KPI N/A, macro
  regime card, breadth stack bar)

Validation:

- `ast.parse` on all changed files; offscreen `MarketLabWindow` build passes;
  real `load_initial_report` -> KPI/macro/breadth populate with genuine values
  (NIFTY 22,520.45 +1.30%, VIX 14.38, Advances 1,169 / Declines 807, A/D 1.45,
  regime BEARISH, stacked bar 2 segments, RSI 36.49, MACD -28.76).
- `tests.test_gui_smoke` -> 43 OK; full offline suite -> `Ran 323 tests ... OK`
  (319 -> 323; +4). `tests.test_view_model` (breadth A/D fallback) still OK.

Visual verification (honest): the window was rendered headless (offscreen) and
a PNG proxy saved, but this environment cannot display/compare pixels, so the
side-by-side match to the reference screenshot still needs your eyes. Known
deviation: the left rail is a wider column (~230-260px) because the sector
panel is stacked beneath it (the reference uses a ~160-180px slim rail); I kept
it wider so sector names don't clip. Desktop native window controls are used
(no custom title bar).

## 2026-10-11 - Real RSI + MACD on the dashboard indicator cards

The RSI/MACD indicator cards were empty because the saved report carries only
ATR/volatility, not index-level RSI/MACD. Now they are computed from the index's
real daily candles.

- `market_lab/view_model.py`: `indicator_cards(report, which)` now computes
  RSI(14) and MACD(line/signal/histogram) from the `nifty_candles` /
  `bank_nifty_candles` closes using `technical_engine.calculate_rsi` /
  `calculate_macd` — Nova's EXISTING indicator math, no new calculation. RSI
  interpretation uses the SAME thresholds as `technical_engine.analyze_stock`
  (>=70 OVERBOUGHT, <=30 OVERSOLD, >=55 BULLISH, <=45 BEARISH); MACD is
  BULLISH/BEARISH on macd vs signal. ATR/VOL still come from the volatility
  engine. Honest N/A when there is too little real history (<20 closes -> RSI
  N/A; <45 -> MACD N/A; <30 -> both N/A) or on any engine error.

No data-source or engine change; the report carries the candles already used by
the candlestick chart. Analysis-only unchanged.

Files changed:
- `market_lab/view_model.py`
- `tests/test_view_model.py` (+RSI/MACD computed test, short-history N/A test)

Validation:
- Real cached report (125 NIFTY candles): RSI 36.49 BEARISH, MACD -28.76
  (histogram) BEARISH, ATR 263.48 pts, VOL 13.74% — all genuine.
- `tests.test_view_model` -> 27 OK (incl. RSI/MACD computed from candles,
  short-history stays N/A).
- Full offline suite: `Ran 319 tests ... OK` (317 -> 319; 2 new).

## 2026-10-11 - TradingView-style candlestick charts for NIFTY / BANK NIFTY

Upgraded the index cards from a line/snapshot to a real candlestick chart.

- `market_lab/market_lab_data.py`: added `build_index_candles(symbol, period,
  limit)` — guarded daily OHLC(+volume) candles from the same `^NSEI` /
  `^NSEBANK` index history (dates from the frame index); `get_market_lab_data`
  now records `nifty_candles` / `bank_nifty_candles` (~125 daily bars). Never
  synthesizes candles; `[]` on failure.
- `market_lab/view_model.py`: `index_card(...)` exposes `candles` and derives
  BANK NIFTY OHLC from its last candle (so BANK NIFTY OHLC is now real too).
- `market_lab/widgets.py`: added `CandleChart` — TradingView-style: restrained
  grid, green/red OHLC candles, bottom volume bars, right price axis with a
  live last-price tag, time axis, a dashed last-price line, and a mouse
  crosshair with an OHLC/change/date read-out. Empty/absent series renders an
  explicit "no series in report".
- `market_lab_ui.py`: index cards use `CandleChart`; `render_dashboard` feeds
  real candles and updates the last candle's close to the live price (so the
  chart tracks between refreshes) with hi/low widened; added a `1M / 3M / 6M`
  range selector (`set_chart_range`) that slices the stored real candles
  client-side (no refetch).

Files changed:
- `market_lab/market_lab_data.py`, `market_lab/view_model.py`,
  `market_lab/widgets.py`, `market_lab_ui.py`
- `tests/test_market_lab_data.py` (+`build_index_candles`),
  `tests/test_view_model.py` (+candles/OHLC), `tests/test_gui_smoke.py`
  (+candle render + range selector)

Validation:

- Live fetch: `build_index_candles("^NSEI")` / `^NSEBANK` each returned 125 real
  daily OHLCV candles (e.g. NIFTY 2026-10-09 O 22,314.95 H 22,580.75 L 22,294.75
  C 22,520.45 vol 296,200).
- `tests` for `build_index_candles` (parse/index-dates, empty/error),
  `index_card` OHLC-from-candle, and dashboard candle wiring + `1M` slice -> OK.
- NSE-MCP stdio smoke: `test_nse_mcp.py` -> MCP SESSION CONNECTED, 68 tools, no
  orphan.
- Full offline suite: `Ran 317 tests ... OK` (314 -> 317; 3 new).

Scope note (honest): these are real DAILY candles (the free NSE/Yahoo sources
provide daily OHLC, not tick data), so the chart updates on refresh and tracks
the live price on the last bar rather than ticking tick-by-tick. True sub-minute
intraday candles require a live feed and are left for the Dhan intraday path
(when a token/plan is configured); the widget is ready to accept them.

## 2026-10-11 - Real NIFTY / BANK NIFTY charts on the dashboard

Previously the index cards only had a tiny OHLC snapshot bar (and BANK NIFTY
showed an "unavailable" placeholder) because the report carried no price
series. Now the dashboard renders a genuine daily-close line chart.

- `market_lab/market_lab_data.py`: added `extract_close_series(dataframe,
  limit)` (compact `[{date, close}]` from an index-history frame, no
  synthesis) and `build_index_series(symbol, period, limit)` (guarded; `[]` on
  any failure). `get_market_lab_data` now records `nifty_series` and
  `bank_nifty_series` (from the SAME `^NSEI` / `^NSEBANK` daily history the
  report already fetches).
- `market_lab/view_model.py`: `index_card(...)` now exposes `series`.
- `market_lab/widgets.py`: added `LineChart` (free hand stretch point series;
  restrained grid + last-price marker + min/max price labels + first/last date
  labels; green/red by overall direction; explicit "no series in report" empty
  state). Index cards use it (they were previously using only the snapshot bar).
- `market_lab_ui.py`: `render_dashboard` feeds the report series into the
  charts; a missing series renders the honest "no series" state.

Files changed:
- `market_lab/market_lab_data.py`, `market_lab/view_model.py`,
  `market_lab/widgets.py`, `market_lab_ui.py`
- `tests/test_gui_smoke.py` (+1), `tests/test_market_lab_data.py`
  (+`extract_close_series`), `tests/test_view_model.py` (+series)

Validation:
- `ast.parse` + offscreen build/render passed; a live fetch of
  `build_index_series("^NSEI")` returned 21 real daily closes
  (23,431.5 -> 22,520.45).
- `tests.test_market_lab_data` -> `extract_close_series` cases (values+dates,
  last-N limit, empty/None, missing Close column) OK.
- `tests.test_gui_smoke.TestTerminalLayout` -> index chart renders the report
  series (NIFTY 7 points; BANK NIFTY empty -> "no series").
- NSE-MCP stdio smoke: `test_nse_mcp.py` -> "MCP SESSION: CONNECTED", 68 tools,
  no orphan.
- Full offline suite: `Ran 314 tests ... OK` (303 -> 314; 11 new).

Note: charts, like every other panel, use real backend data only; when the
index-history fetch fails (e.g. provider outage) the chart shows an explicit
"no series in report" state rather than fabricated candles.

## 2026-10-11 - Dhan Step 4: opt-in BANK NIFTY + India VIX live override

Extends the Dhan live-snapshot wiring to the volatility section, same guarded/
opt-in pattern (read-only, analysis-only; unchanged when Dhan is off).

- `market_lab/market_lab_data.py`: added `_apply_dhan_volatility_overrides()` and
  applied it as `volatility = _apply_dhan_volatility_overrides(load_volatility_snapshot())`.
  - BANK NIFTY: sets `volatility.bank_nifty.price` (+ `source: DHAN_LIVE`,
    `last_trade_time`); the engine's ATR / realized-vol / regime fields are
    preserved.
  - India VIX: sets `volatility.india_vix.value` and `change_percent`
    (+ `source: DHAN_LIVE`, `last_trade_time`, and a `note` recording the split);
    the engine's `percentile_1y` / `regime` / `direction` are preserved (Dhan has
    none). Missing legs are created on demand.
  - Unconfigured / unavailable / any error returns the original volatility dict
    unchanged (identity preserved).

Files changed:
- `market_lab/market_lab_data.py`
- `tests/test_market_lab_data.py` (+7)

Validation:
- `ast.parse` on `market_lab/market_lab_data.py`: passed.
- `tests.test_market_lab_data` -> 12 OK (NIFTY override + BANK/VIX volatility
  override, engine-field preservation, no-mutation, identity on no-override /
  unavailable / error / non-dict, missing-leg creation).
- Full offline suite: `Ran 308 tests ... OK` (301 -> 308; 7 new).

Not run here: a live Dhan call (no token/plan). BANK NIFTY/VIX Dhan values land
in the report only when configured; percentile/regime continue to come from the
volatility engine.

## 2026-10-11 - Dhan Step 3: opt-in NIFTY/BANK NIFTY/VIX live snapshot

Wires the Dhan market-feed quote into the report generator as an OPTIONAL,
guarded source for the index snapshot — still read-only/analysis-only; NSE MCP
and Yahoo fallbacks are byte-identical when Dhan is unconfigured.

- `analysis/data/dhan_feed.py`: added `_index_entry_to_snapshot(entry)` (pure:
  converts one quote entry into a report-compatible NIFTY snapshot, deriving
  change_percent/previous_close from last_price + net_change, labeled
  `source: DHAN_LIVE`; unavailable entry -> `{"available": False}`) and
  `get_report_index_snapshot()` (keys `nifty`/`bank_nifty`/`india_vix`; `{}` when
  Dhan is unconfigured or the quote fails).
- `market_lab/market_lab_data.py`: added `_dhan_index_overrides()` (guarded
  wrapper; `{}` when unconfigured/on any error) and `_apply_dhan_override()`
  (returns the Dhan NIFTY snapshot only when it is `available`, else the original
  snapshot unchanged). `nifty_snapshot = _apply_dhan_override(get_nifty_snapshot())`.
  Default (Dhan off) behavior is unchanged.

BANK NIFTY and India VIX snapshots are produced by the same converter and are
ready to wire into their report sections as a follow-up; NIFTY is wired now
(the single, lowest-risk injection point the UI + Section 01 consume).

Files changed:
- `analysis/data/dhan_feed.py`, `market_lab/market_lab_data.py`
- `tests/test_dhan_feed.py` (+6), `tests/test_market_lab_data.py` (new, 5)

Validation:
- `ast.parse` + imports for both modules: passed.
- `tests.test_dhan_feed tests.test_market_lab_data` -> 44 OK.
- NSE-MCP stdio smoke: `test_nse_mcp.py` -> MCP SESSION CONNECTED, 68 tools,
  no orphaned `indian-market-mcp.exe`; NSE path unchanged.
- Full offline suite: `Ran 301 tests ... OK` (290 -> 301; 11 new).

Not run here: any live Dhan call (no token/plan). BANK NIFTY/VIX wiring and a
real end-to-end Dhan snapshot require a configured token to verify.

## 2026-10-11 - Dhan Step 2: auto security-id map + live index/equity quotes

Extends `analysis/data/dhan_feed.py` (still read-only, analysis-only — no
order/position/trade/funds endpoints):

- **Auto security-id map** from Dhan's PUBLIC instrument master CSV
  (`https://images.dhan.co/api-data/api-scrip-master.csv`, no token needed):
  `build_security_map()` parses NSE EQUITY symbol -> securityId (tolerant to the
  CSV's header spellings) and caches it in `analysis/data/cache/dhan/
  security_map.json` with the same 16h freshness gate. `resolve_security_id`
  now falls back to this cached map, and `get_price_history_dhan` builds it
  automatically (best-effort, guarded) on a miss — so symbols no longer need
  manual `dhan_config.json` mapping. Config `equity` overrides still win.
- **Live quotes** via `POST /v2/marketfeed/quote` (IDX_I) and
  `POST /v2/marketfeed/ltp` (NSE_EQ): `get_index_quote(["NIFTY","BANKNIFTY",
  "INDIAVIX"])` returns live last_price/net_change/OHLC with `available` flags
  (missing data is `available: False`, never invented); `get_last_price(symbols)`
  returns LTP for equities. Index IDs default to common Dhan IDs
  (NIFTY 13, BANKNIFTY 25, INDIAVIX 26) and are overridable via
  `dhan_config.json {"index": {...}}`. `_post` now sends an optional `client-id`
  header from env `DHAN_CLIENT_ID` (required by some quote calls).

Endpoints verified against Dhan docs (not invented). No market-feed/LTP is
wired into report generation yet — they are exposed as adapter functions the
engines can call; wiring into the Market Lab snapshot is a separate, guarded
step.

Files changed:
- `analysis/data/dhan_feed.py` (master map + quote functions + client-id)
- `tests/test_dhan_feed.py` (12 new: master parse/filter/zero-rows/cache-gate,
  resolve fallback + config override, index/ltp quote parsing, unconfigured,
  config index override, auto-build-on-miss)

Validation:
- `ast.parse` + import: passed.
- `tests.test_dhan_feed` -> 33 OK (was 21; +12).
- Full offline suite: `Ran 290 tests ... OK` (278 -> 290; 12 new).

Not run here: any live Dhan call (no token/plan in this environment); the quote
and instrument-master paths are verified only with stubbed HTTP offline.

## 2026-10-11 - Dhan market-data adapter (Step 1 data layer, read-only)

Adds Dhan as an optional, cache-first source of historical daily candles that
feeds Nova's EXISTING technical engine (which already computes RSI/MACD/ATR/
momentum locally). It fixes the recurring "[NSE FALLBACK] <SYMBOL>: no usable
historical data" gap for indicators.

- New `analysis/data/dhan_feed.py` — read-only market-data adapter.
  - Analysis-only by design: uses ONLY Dhan data endpoints
    (`POST /v2/charts/historical`). It NEVER calls order/position/trade/funds
    endpoints and places no orders; no broker or execution behavior.
  - `get_price_history_dhan(symbol, period)`: cache-first; caches daily candles
    under `analysis/data/cache/dhan` (git-ignored) and reuses them only while
    younger than `MAX_AGE_HOURS` (16h, matching Nova's scanner freshness gate),
    else one live fetch.
  - `resolve_security_id(symbol)`: maps NSE symbol -> Dhan securityId from a
    git-ignored `dhan_config.json` `{"equity": {SYMBOL: id}}`. Never invents an
    id and never auto-downloads the instrument master.
  - `is_configured()`/`get_access_token()`: token from env `DHAN_ACCESS_TOKEN`
    or `dhan_config.json {"access_token": ...}`; base URL from `DHAN_BASE_URL`
    (default `https://api.dhan.co/v2`). Credentials/config are git-ignored.
  - `_to_dataframe(...)`: converts Dhan parallel arrays (open/high/low/close/
    volume/timestamp epoch) into the exact OHLCV DataFrame Nova's technical
    engine already expects.
- `analysis/data/market_universe.py`: `get_price_history` now tries Dhan FIRST
  when `ENABLE_DHAN and dhan_configured()`; any Dhan failure falls through to
  the existing NSE MCP -> Yahoo chain. With Dhan unset (the default) behavior is
  byte-for-byte unchanged.

Files changed:
- `analysis/data/dhan_feed.py` (new)
- `analysis/data/market_universe.py` (`ENABLE_DHAN` flag + opt-in Dhan attempt)
- `tests/test_dhan_feed.py` (new, 21 offline tests; requests/HTTP/config/cache
  stubbed)
- `.gitignore` (ignore `.env`, `dhan_config.json`)

Validation:
- `ast.parse` + imports for the new module and the wired market_universe: passed.
- `tests.test_dhan_feed` -> 21 OK (parsing, error codes, network propagation,
  cache round-trip + 16h staleness gate + miss, config/token, unmapped symbol,
  and get_price_history prefer / skip / fall-back-to-NSE wiring).
- Full offline suite: `Ran 278 tests ... OK` (257 -> 278; 21 new).

To enable (never commit the file): create `dhan_config.json` in the project root
with `{"access_token": "<dhan-jwt>", "equity": {"RELIANCE": "<id>", ...}}`
(or set env `DHAN_ACCESS_TOKEN`), restart Market Lab. Not-run here: a live Dhan
fetch (no token/plan in this environment) and the live NSE MCP smoke — the
existing MCP path is unchanged and preserved by the offline fall-back test.

## 2026-10-11 - Nova Analysis answers about the specific stock asked

Bug: asking about a single stock in the Nova Analysis question box (or via
`get_market_lab_analysis("...")`) produced a generic whole-market template and
ignored the stock. Fixed in `market_lab/market_lab_brain.py`:

- `_extract_focus_symbol(query)` detects the one NSE stock named, offline, by
  validating candidate tokens against the cached symbol master
  (`analysis/data/symbol_master.load_master`). Benchmarks/instructions
  (NIFTY, BANK NIFTY, market, breadth, ...) and unknown words never trigger it,
  so a broad question still yields the full assessment.
- `_focus_payload(symbol, report)` gathers verifiable per-stock evidence: a
  live snapshot from the existing watchlist engine
  (`refresh_watch_symbol`; returns status UNAVAILABLE with a reason on any
  failure — never demo values), company name from the cached master, and the
  stock's factor/technical membership from the report (only the stored
  top/bottom extremes and top-technical list are checked; "not in extremes"
  is stated plainly). All values are preserved as-reported; nothing invented.
- `_build_analysis_payload(report, focus=...)` now includes a `focus_symbol`
  block and a compact `research_factors` summary (top/bottom 5) so the model
  can place the stock without the whole report.
- `analyze_market_lab` branches the prompt: when a stock is named it uses a
  focused directive ("answer about the requested stock; do not emit the broad
  market template; say when a field is missing instead of substituting
  market-wide numbers") and prepends `FOCUS STOCK JSON`; otherwise the
  previous broad prompt/system behavior is unchanged. The returned header now
  shows `Focus: <SYMBOL>`. A SYSTEM_PROMPT "SINGLE-STOCK QUESTIONS" section
  was added.
- Analysis-only invariants unchanged: read-only, no broker/orders, no
  fabricated data.

Known limitation: detection matches ticker tokens, not company names, so
"infosys" does not resolve to `INFY` (type the ticker). If the week's live
snapshot is unavailable, the answer says so honestly.

Validation:

- `tests/test_market_lab_brain.py` (new, 15 offline tests; symbol master,
  watchlist engine and ollama stubbed) covers detection, focus payload,
  payload shaping, prompt branching and data-error handling.
- Real (un-stubbed) checks against the cached master: "tell me about
  RELIANCE" -> RELIANCE; "bank nifty"/"market overview" -> "" (broad);
  `_focus_payload("RELIANCE", <cached report>)` returned a real snapshot
  (price present, RSI, trend) + company name + honest factor/technical
  membership.
- Full offline suite: `Ran 257 tests ... OK` (242 -> 257; 15 new).

## 2026-10-10 - Market Lab terminal visual refinement (Step 5)

Visual polish of the new terminal. No backend, engine, data-source, or
`market_lab_data.py`/`market_lab_brain.py` logic changed; honesty preserved
(all N/A states unchanged).

- Unified dark theme to the reference palette (BG `#050B10`, panels
  `#09141D`/`#0D1D28`, border `#1B3443`, text `#E6F0F7`/muted `#8298AA`,
  green `#20E69A`, red `#FF465B`, amber `#FFC45B`, blue `#3198FF`, cyan
  `#36DDF2`) in both `market_lab_ui.py` and `market_lab/widgets.py`.
- `market_lab/widgets.py`: added `SnapshotBar` (real single-session OHLC
  high-low + open/close ticks, honest "chart unavailable" when absent) and
  `PerfBar` (thin centered green/red performance bar scaled across the shown
  rows); `GuardrailsBar` gained a shield-accent strip + divider; `restyle_chip`.
- `market_lab_ui.py`:
  - Index cards dominant (28px value, 15px change) with a real OHLC snapshot
    visual for NIFTY and an honest unavailable state for BANK NIFTY; clearer
    hierarchy.
  - Sector panel rebuilt as compact terminal rows (name + proportional
    PerfBar + colored % + regime) in a horizontal-scroll-disabled QScrollArea.
  - Factor panel: numeric columns right-aligned, availability color-coded.
  - Consistent panel radius; footer + guardrails remain pinned and
    non-overlapping.
- Fixed: removed a duplicate stale `render_sector` (referenced a removed
  `sector_table`) that had shadowed the new sector renderer.

Validation:

- Widget geom/non-overlap checks at 1920x1080, 1366x768 and 1280x720: header
  fixed 56px, footer + guardrails pinned to the bottom with no overlap.
- Offscreen render of the real report: header badges, index cards (NIFTY with
  OHLC, BANK NIFTY chart N/A), 5 sector rows with bars, factor top-10 + 7
  availability rows.
- Full offline suite: `Ran 242 tests ... OK` (unchanged).
- Real `market_lab_ui.py` launched (pid, running) with live-only refresh over
  the cached scan; no traceback.

Manual-only remaining: human pixel review at 1920x1080 vs the reference
(screenshot not captureable in this environment); FULL REFRESH not triggered.

## 2026-10-10 - Market Lab terminal UI redesign

Redesigned `market_lab_ui.py` into a native Bloomberg/TradingView-style
terminal while preserving the working backend, worker/refresh orchestration,
cache-first behavior, existing pages (Analysis, Backtest, Event Risk), and all
guardrails. No backend, engine, cache, data-source, or `market_lab_data.py` /
`market_lab_brain.py` logic changed.

New supporting modules:
- `market_lab/view_model.py` — pure, stdlib-only adapter that maps the real
  saved report into UI-friendly structures and marks anything the backend does
  not actually provide as an explicit `N/A` (never a fabricated value).
- `market_lab/widgets.py` — self-contained PySide6 component library (palette,
  `CollapsibleSection`, index/indicator cards, `Sparkline`, tables,
  `FreshnessBadge`, `GuardrailsBar`, `stat_chip`/`restyle_chip`). No new deps.

Layout now: fixed header (branding, symbol search that pins into the existing
watchlist, data-age + scanner-freshness badges, MODE: CACHE-FIRST chip, live
session badge OPEN/CLOSED/PRE-OPEN/WEEKEND, India VIX chip, connection, refresh
controls, clock) -> status chips -> a `QSplitter` of
[left nav rail + sector overview | center pages | factor rankings] -> footer
status line -> a persistent `GuardrailsBar` (always visible, not removable).

Center pages: Dashboard (NIFTY/BANK NIFTY index cards with price/change/OHLC/
derived prev-close/returns and an honest chart-N/A, four indicator cards, and a
market-breadth table), Market Report (the ten collapsible report sections in
order 01-10, plus a utility raw-JSON collapsible), Nova Analysis, Factor
Backtest, Event Risk.

Refresh behavior unchanged and preserved: AUTO toggles the 1 s UI timer only;
FULL REFRESH and LIVE UPDATE invoke the existing `get_market_lab_data`
(`force_refresh=True` / `live_only=True`) through the existing single-flight
worker; displays update in place (no widget rebuild per tick); header clock/age/
session repaint every second from memory; cache-first startup shows the saved
report first.

Honesty by design (see VALIDATION for exact limits): QUALITY/VALUE factor
rankings are explicitly NOT_AVAILABLE (the factor engine does not compute
fundamentals); per-index RSI/MACD/volume and intraday chart series are N/A (not
in the saved report); portfolio VaR/Sharpe/drawdown are N/A (risk engine is
market-risk-context only); earnings calendar is NOT_AVAILABLE (no source);
52w highs/lows and McClellan summation are N/A. Derived index absolute change
and previous close are labeled as arithmetic on backend values.

Files changed:
- `market_lab_ui.py` (build_ui/build_header/dashboard/report-workspace/sector/
  factor/renderers wired into display_report + cheap header tick)
- `market_lab/view_model.py` (new), `market_lab/widgets.py` (new)
- `tests/test_view_model.py` (new, 23), `tests/test_gui_smoke.py`
  (+`TestTerminalLayout`, 6; 5 nav pages)

Validation:

- `ast.parse` on all changed files; offscreen `MarketLabWindow` builds and
  renders the real saved report (header WEEKEND / VIX 14.38, index cards,
  breadth, sectors, factor top-10 rank order, all ten sections with
  availability chips).
- Full offline suite: `Ran 242 tests ... OK` (213 -> 242; +29).
- Real `market_lab_ui.py` launched and performed a live-only refresh over the
  cached 1,999-stock scan, fetching real NIFTY/BANKNIFTY option chains, no
  traceback; stopped afterward with no orphaned market-MCP subprocess.

## 2026-10-10 - Market Lab Event Risk panel (upcoming-events UI)

First UI addition driven by a real gap: event risk was fresh and available in
the report's `event_risk_context`, but only surfaced as a status chip with no
dedicated view. Added an Event Risk page to `market_lab_ui.py`.

- New nav page "Event Risk" (index 4, appended so the existing page indices
  are unchanged): a risk banner, a meta line and a read-only list.
- `display_report()` now populates it (reusing the already-parsed
  `event_risk_context`): banner = `OVERALL EVENT RISK: <level>` colored by
  level (HIGH/CRITICAL red, MODERATE/ELEVATED amber, LOW green, UNKNOWN/other
  amber - never a false all-clear); meta line shows upcoming count, lookahead
  and calendar-source freshness (FRESH / STALE / unknown).
- New pure, offline helpers (unit-testable, no widgets): `format_event_risk`
  renders the upcoming-events list with severity tag, IST datetime and a
  countdown **recomputed from each event's datetime** (not the report's frozen
  `hours_until`), so a cached report still shows an accurate time-until;
  `_risk_color`, `_parse_iso`, `_eta`. Closes with the guardrail: descriptive
  context only, not a buy/sell signal.
- Honesty preserved: missing/empty context -> "NOT AVAILABLE"; stale source
  flagged; an event without a usable timestamp still lists its name.

Files changed:

- `market_lab_ui.py` (event helpers + `build_event_page` + `render_event_risk`
  + nav spec + `display_report` wiring)
- `tests/test_gui_smoke.py` (12 new tests: pure `format_event_risk`/color +
  widget `TestEventRiskPanel`; updated nav-index test 4 -> 5 pages)
- `AGENTS.md`, `.github/workflows/ci.yml` (offline-suite count 201 -> 213)

Validation:

- `ast.parse` + `import market_lab_ui` passed; `MarketLabWindow` builds with
  the three event widgets and 5 nav pages.
- Headless render of the real saved report: banner MODERATE, meta
  "5 | 7 days | FRESH (within 24h)", and the full upcoming-events list with
  IST times and live countdowns (e.g. India CPI "in 43.9 h").
- Full suite (QT available): `Ran 213 tests ... OK` (201 -> 213; 12 new);
  also green with Qt absent (Qt-guarded tests skip).

## 2026-10-10 - Re-checked and re-stamped the event calendar

Web-verified every upcoming calendar entry against authoritative sources, then
re-stamped `source_checked_at` (resetting the 24h freshness window) — no event
entries changed, only the timestamp.

Re-check results (all matched, no edits needed):

- US (BLS bls.gov/schedule/2026): CPI Sep -> Wed Oct 14 08:30 ET; PPI Sep ->
  Thu Oct 15; Import/Export Sep -> Fri Oct 16. (No shutdown delay listed.)
- India CPI (MoSPI advance release calendar + PIB): Sep -> Mon Oct 12, 4 pm
  IST (or next working day if a holiday).
- India WPI (DPIIT via IndiaInflation.com): Sep -> Wed Oct 14, 12:00 IST.
- RBI MPC (IndiaInflation.com): next decision Fri Dec 4, 2026.
- NSE/BSE 2026 holidays (NSE circular CM-TR71775 / BSE / Nifty Indices):
  Dussehra Tue Oct 20; Diwali-Balipratipada Tue Nov 10; Prakash Gurpurb Sri
  Guru Nanak Dev Tue Nov 24; Christmas Fri Dec 25; Diwali Muhurat Sun Nov 8
  (timings TBA), all as already recorded.

`source_checked_at`: 2026-10-10T00:11:37+05:30 -> 2026-10-10T19:51:49+05:30.
Only that one line changed (kept the file's original compact formatting rather
than the re-serialized array expansion `touch_event_calendar.py` writes).
`check_event_calendar.py` -> RESULT: OK, 11 valid / 0 invalid, 0.0h -> FRESH.
Offline suite unchanged: `Ran 201 tests ... OK`.

## 2026-10-10 - Sector engine unit tests (closes coverage gap)

Added `tests/test_sector_engine.py` (19 offline tests) for the sector engine's
pure math, which previously had no coverage (technical, volatility,
institutional-flow, event-risk and research-factor engines were tested; sector
was not):

- `safe_float`: None/NaN/NA/inf/junk -> None; numbers and numeric strings
  coerce.
- `pct_mean`: mean of a numeric series; non-numeric/NaN entries are coerced
  then dropped; empty/all-invalid -> None.
- `safe_ratio`: normal ratio; zero and negative denominators -> None.
- `determine_sector_regime`: table-driven coverage of the descriptive regime
  score — `INSUFFICIENT_DATA` when there is no evidence, and the STRONG /
  POSITIVE / NEUTRAL / NEGATIVE / WEAK boundaries at scores 5 / 2 / -2 / -5,
  plus the single-evidence case. Confirms it stays descriptive (no signal).

The index-classification / scan path (which downloads NSE HTML and reads the
scanner output) is intentionally not exercised.

Files changed:

- `tests/test_sector_engine.py` (new)
- `AGENTS.md`, `.github/workflows/ci.yml` (offline-suite count 182 -> 201)

Validation:

- `.\venv\Scripts\python.exe -m unittest tests.test_sector_engine -v` -> 19 OK.
- `import analysis.data.sector_engine` offline: passed.
- Full suite: `Ran 201 tests ... OK` (182 -> 201; 19 new).

## 2026-10-10 - pyproject.toml metadata + dependency-free CI gate

- Added `pyproject.toml`: canonical project metadata (name/version/
  `requires-python >=3.11`) with `dependencies` mirroring `requirements.txt`
  exactly (107 pinned packages). Metadata-only — no build-system / not a
  publishing manifest; `pip install .` is not part of Nova's workflow and app
  runtime is unchanged (still the local venv).
- Added `tests/test_packaging.py` (3 tests, stdlib `tomllib`): asserts the
  metadata is present and that `pyproject` dependencies == `requirements.txt`
  so the two manifests cannot drift.
- Added `.github/workflows/ci.yml`: a **dependency-free** gate that runs on
  push/PR to main. The full runtime (PySide6, torch, pywin32, numpy,
  yfinance, ...) is heavy and Windows-specific and lives in the local venv, so
  CI instead (1) `ast`-parses every `.py` source (excluding venv/caches/model
  dirs) to catch syntax regressions tree-wide, and (2) runs the stdlib-only
  suites `tests.test_start_nova` and `tests.test_packaging`.

Why not a full-suite CI job: Nova pins Python 3.14 with large Windows-only
packages; installing them on a GitHub runner would be very heavy and fragile.
The complete offline suite (182 tests) is run locally via
`.\venv\Scripts\python.exe -m unittest discover -s tests`.

Files added:

- `pyproject.toml`
- `tests/test_packaging.py`
- `.github/workflows/ci.yml`
- `AGENTS.md` (notes the manifests and CI)

Validation:

- `pyproject.toml` parses via `tomllib`; 107 deps == requirements.txt.
- Full suite: `Ran 182 tests ... OK` (179 -> 182; 3 new).
- CI steps executed locally and passing: 57 `.py` sources parse clean; the
  stdlib-only suites run 12 tests OK.

## 2026-10-10 - Add start_nova.py launcher with local-service preflight

New file `start_nova.py`: a launcher that preflight-checks the two local
services Nova depends on, then starts one of the existing entry points.

- `check_service(url, timeout)` / `check_all()` probe Ollama
  (`http://localhost:11434/api/tags`) and SearXNG (`http://localhost:8080`) via
  `urllib` and return `(ok, detail)`; they never raise and never block a launch.
- `print_report(...)` prints a clear UP/DOWN table with what each service is
  used for, and returns overall health.
- `launch("main"|"market")` starts `main.py` or `market_lab_ui.py` with the same
  interpreter (`subprocess.Popen`); CLI: `start_nova.py [main|market]`,
  `--check` (check only, exit 0 if all up else 1), or no args for an interactive
  menu.
- The check is advisory only: Nova still launches when a service is DOWN, just
  with a warning. No new broker/order/trading behavior; no app logic changed.

Files added:

- `start_nova.py`
- `tests/test_start_nova.py` (new: 9 offline tests, `urlopen` patched)
- `AGENTS.md` (Common Commands now lists the launcher)

Validation:

- `ast.parse` on `start_nova.py` and the new test file: passed.
- `.\venv\Scripts\python.exe -m unittest tests.test_start_nova -v` -> 9 tests OK.
- Full suite: `Ran 179 tests ... OK` (170 -> 179; 9 new).
- Live `.\venv\Scripts\python.exe start_nova.py --check` -> Ollama UP (HTTP 200),
  SearXNG UP (HTTP 200), "All services are up."

## 2026-10-10 - Market Lab clean shutdown on window close

`market_lab_ui.py`: replaced the old `closeEvent` that refused to close while
any worker ran (showing "A background task is still running…" and ignoring the
event). That refusal pushed users to force-close the window, which orphaned the
`indian-market-mcp.exe` subprocess the worker had spawned via
`analysis/data/nse_feed.py` (stdio_client) — the "background task running"
symptom after closing.

New behavior:

- On close, `_shutting_down` is set, `auto_enabled` is cleared and both the
  auto-refresh clock and the 1s display ticker are stopped, so nothing new can
  be scheduled.
- `start_task` now returns immediately when `_shutting_down` is set, which also
  breaks the watchlist self-chaining (it restarts a worker off `task_succeeded`).
- Each still-running worker is waited on (`worker.wait`, up to
  `CLOSE_WORKER_WAIT_MS` = 10s). When `Worker.run()` returns, the `stdio_client`
  context in nse_feed exits and terminates the `indian-market-mcp.exe`
  subprocess, so closing leaves no orphan. Only a worker that overstays the
  grace period is force-`terminate()`d as a last resort so the window can always
  close.
- The close is then accepted unconditionally.

Files changed:

- `market_lab_ui.py` (closeEvent rewrite, `_shutting_down` flag, `start_task`
  guard, `CLOSE_WORKER_WAIT_MS` constant).
- `tests/test_gui_smoke.py` (new `TestCleanShutdown`: 3 tests).

Validation:

- `ast.parse` on both changed files passed; `import market_lab_ui` ok.
- `.\venv\Scripts\python.exe -m unittest tests.test_gui_smoke -v` -> 20 tests OK.
- Full suite: `Ran 170 tests ... OK` (167 -> 170; 3 new).
- Live: `nse_feed.get_market_status()` spawned and then exited its
  `indian-market-mcp.exe` on its own (no persistent orphan after the call).
  Process sweep confirms 0 real MCP servers / 0 Nova UI processes.

Note: real MCP/MCP-shim processes must be counted excluding one's own probe
process (a `Get-CimInstance ... '*indian-market-mcp*'` PowerShell query matches
itself).

## 2026-10-10 - Live end-to-end check (terminal-integrated)

No code change. On-machine live verification of the integrated stack
(services, Market Lab CLI, Ollama tool call, both GUIs) — see
`docs/VALIDATION.md` "2026-10-10 - Live end-to-end check". Result: the whole
pipeline works in the terminal — Ollama `qwen3.5:4b` UP, SearXNG UP, cache-first
Market Lab report clean (1,999 stocks, no full scan, guardrails intact), a real
Ollama turn called `get_market_brief` and produced a grounded summary, and both
`MarketLabWindow` and `NovaWindow` construct/run headless and fetch live NSE
data. Reminder logged: event calendar needs re-check ~12:11 IST 2026-10-11.

## 2026-10-10 - Assistant tool-registry + run_tool contract tests

Added `tests/test_tool_contract.py` (15 offline tests) protecting the
invariants the Ollama tool-calling loop relies on:

- Registry/schema lock-step: every callable in `TOOLS` is advertised in
  `TOOL_SCHEMA`, every schema function name resolves to a real tool, no
  duplicate schema names, and each entry is a well-formed function schema
  (name, description, object parameters, required keys exist in properties).
- `run_tool` never raises: unknown tool -> text; args as JSON string are
  parsed; malformed JSON and non-dict args are normalized to `{}`; bad
  arguments become a "Bad arguments" message. Only side-effect-free paths are
  executed (`get_time`; a missing-arg `open_website` call raises `TypeError`
  before any browser opens).
- `get_market_brief` dispatches correctly through `run_tool` (loader stubbed,
  so it is hermetic and read-only).
- Brain coupling: `brain.TOOL_SCHEMA` is `tools.TOOL_SCHEMA`, `MAX_TOOL_ROUNDS`
  is sane, and every schema name is dispatchable by `run_tool`.

No production code changed.

Validation:

- Full suite: `Ran 167 tests ... OK` (152 -> 167; 15 new).
- `ast.parse` on the new test file passed; `import brain` succeeds offline.

## 2026-10-10 - Cache-first pipeline integration tests + shared report loader

Added `tests/test_pipeline_integration.py` (19 offline tests) covering the
end-to-end cache-first pipeline without network, Ollama, real scan, or writes
to the real cache:

- Save/load round-trip: `save_json_report` -> `load_latest_saved_report`
  returns an equivalent report; guardrails (`analysis_only`,
  `buy_sell_authorized: false`) survive the round-trip; newest file wins;
  empty cache loads nothing.
- `get_market_brief` and `get_market_analysis` read a redirectable temp cache;
  `get_market_analysis` never calls `scan_market` when a saved report exists,
  and falls back to the scanner only when the cache is empty.
- Consumer agreement: the brief and the analysis snapshot, which parse the
  same report independently, must report identical measured facts (regime,
  India VIX, breadth, FII/DII flow regime, signal-eligibility honesty, top
  symbols).
- Stale/missing handling is consistent across both consumers.

Code change: `tools.get_market_brief` now reuses the shared
`_load_latest_market_lab_report()` loader instead of duplicating the
cache-globbing logic. Behavior is preserved (newest valid saved report ->
brief; none -> the "open Market Lab first" message) and the corpus is now
readable from a single cache path. Minor behavior improvement: a corrupt
newest file now falls back to an older valid report instead of erroring.

Removed approved scratch/debug files from the repo root: `run_test.py`,
`test_fix.py`, `test_verify.py`, `test_output.txt` (never committed; two were
UTF-16 throwaway scripts, one a 109-byte import stub, one a captured
test-output log).

Validation:

- `ast.parse` on `tools.py` and the new test file passed.
- `import tools`; live read-only `get_market_brief()` against the real cache
  still returns a valid brief (0.0h fresh).
- Full suite: `Ran 152 tests ... OK` (133 -> 152; 19 new).

## 2026-10-10 - requirements.txt generated from venv + full verification

- Generated `requirements.txt` from `.\venv\Scripts\pip.exe freeze` (58 packages).
- Verified Python syntax across 54 source files with `utf-8-sig` decoding.
- Confirmed main assistant imports: `import main, brain, tools, ui` ok.
- Confirmed market lab imports: `import market_lab_ui; from market_lab.market_lab_data import get_market_lab_data; from market_lab.market_lab_brain import analyze_market_lab` ok.
- Ran full test suite: `.\venv\Scripts\python.exe -m unittest discover -s tests` → 108 tests in 0.200s, OK.

## 2026-10-10 - get_market_analysis made cache-first

`tools.py:get_market_analysis()` used to call `scan_market()` unconditionally
(the expensive full NSE scan) on every assistant call. It is now cache-first,
matching Market Lab behavior:

- New `_build_market_analysis_from_report(report)` builds the snapshot purely
  from the latest saved Market Lab report (regime, NIFTY/BANKNIFTY returns,
  breadth, India VIX, sector strength, derivatives OI/PCR/max-pain, FII/DII
  institutional flow, event risk, top technical + factor-ranked stocks).
  It never runs a scan and never fetches live prices.
- New `_build_market_analysis_from_scanner(dataframe, summary, lab_report=None)`
  holds the original scanner logic, now only used as a fall-back when no saved
  report exists. Still merges the latest saved report into the availability
  matrix exactly as before.
- `get_market_analysis()` dispatches: report present → report builder (no
  scan); no report → `scan_market()` → scanner builder. Removed a duplicate
  `except` block that an earlier partial edit had left behind.
- Full-dataframe rankings (momentum / relative strength / volume expansion) are
  not stored in a saved report, so the cache-first path reports them honestly as
  NOT_AVAILABLE and tells the user to run FULL REFRESH in Market Lab for those.
- Derivatives context now renders measured scalars (`SPOT`, `OI_PCR`,
  `VOLUME_PCR`, `MAX_PAIN_STRIKE`) instead of leaking the report's raw nested
  dicts.
- `TOOL_SCHEMA` description for `get_market_analysis` updated to document the
  cache-first behavior and which layers need a full scan.

Analysis-only invariants unchanged: no broker/order/execution, missing data is
flagged, measured values are not invented.

Files changed:

- `tools.py` (cache-first dispatch + two builders + `_report_return` helper +
  schema description)
- `tests/test_cached_market_analysis.py` (new: 25 offline tests)

Validation:

- `ast.parse` on `tools.py` and the new test file passed.
- `import main, brain, tools, ui` passed.
- Full suite: `Ran 133 tests ... OK` (108 → 133; 25 new).
- Live cache-first call of `get_market_analysis()` returned in well under a
  second from the saved report (no scan); scanner fall-back exercised with a
  stubbed dataframe in tests.

## 2026-10-10 - GUI smoke test: skip cleanly when PySide6 is missing

`tests/test_gui_smoke.py` now guards its PySide6 / Market Lab imports with
`try/except ImportError` and decorates the test case with
`@unittest.skipIf(not QT_AVAILABLE, ...)`. Without Qt the module still imports
and the case reports 17 skips instead of an import error, so
`unittest discover -s tests` stays green on a machine that has no PySide6.
Behavior with Qt installed is unchanged (`QT_QPA_PLATFORM=offscreen`, one
`QApplication`, real `MarketLabWindow` built with no event loop).

## 2026-10-10 - Headless GUI smoke tests for Market Lab

Added `tests/test_gui_smoke.py`: the first automated coverage of the Market Lab
GUI itself, run fully headless and offline so it can live in the normal
`unittest discover -s tests` run.

- Forces `QT_QPA_PLATFORM=offscreen` before importing PySide6, creates exactly
  one `QApplication` for the module, and constructs the real `MarketLabWindow`
  without ever running an event loop. The deferred
  `QTimer.singleShot(150, load_initial_report)` therefore never fires, so the
  test proves construction spawns no worker, no network call, and no NSE scan.
- Locks in the watchlist fix: `task_succeeded("watchlist", ...)` must store the
  refresh payload in `watch_data` and re-render `watch_view` (the old code
  dropped the result, so the panel never populated). Also covers the
  `NOT_AVAILABLE` branch, the empty-pin reset, `format_watchlist_line` dashes
  for missing numbers, PIN dedupe/`MAX_SYMBOLS` cap, and the round-robin poll.
- Locks in the backtest arg-wiring fix: `window.start_task` is stubbed with a
  recorder so `run_backtest_task` is exercised with no real `QThread` and no
  network. The captured args/kwargs are bound against the real
  `inspect.signature(run_backtest)`, which is exactly the `TypeError` the UI's
  blank-input path used to raise; `symbols` must keep its `None` default.
- Covers `render_backtest` (real report keys, decile hit-rate labels, trend
  mix, top-ranked list, "not a buy/sell signal" guardrail), the invalid-result
  path, `task_succeeded` page switch (index 3 = Factor Backtest, asserted
  against its nav label), `task_failed` surfacing the error in the result view
  (`QMessageBox` mocked), and `task_finished` restoring the controls.
- No production code changed; these tests only assert existing behavior.

## 2026-10-10 - Institutional flow primary-coverage progress note (Option C)

Made the runway to a fully NSE-primary FII/DII history window legible instead
of a bare "2/22". This is documentation of *progress*, not a way to fake
coverage: the `signal_allowed` gate is unchanged and still requires every
target session to be primary-verified.

Context (verified by a live probe of `fetch_nse_rows()`): NSE's combined
endpoint returns only the latest trading day, and there is no NSE historical
FII/DII API. Older sessions can only come from the Groww mirror. Promotion is
sticky (`upsert_rows` keeps the highest-priority source per date), and ~1 NSE
session is promoted per trading day, so full-primary needs ~18 trading days.

- New pure helper `_primary_coverage_summary(metrics)` in the flow engine
  returns a coverage note dict (verified fraction, remaining sessions, and an
  honest "estimated more trading day(s)" runway) and is surfaced as
  `primary_coverage_note` on the metrics.
- `print_report` now prints a `Primary coverage:` line when the window is not
  fully primary-verified.
- The assistant `get_market_brief` flow section prints a matching
  `Coverage:` line under Primary-verified sessions, plus the existing
  honest `Signal-eligible: NO` reason.
- Added `tests/test_institutional_flow_coverage.py` (offline) for the helper.

## 2026-10-10 - Assistant morning market brief tool (`get_market_brief`)

Added a new voice/chat-callable tool, `get_market_brief()`, so the Nova
assistant can read out a concise morning market brief on request. It is
**cache-first**: it loads the latest saved Market Lab JSON report and never
triggers a full NSE scan, so it is cheap and respects the "prefer cache-first"
rule.

- Composed from measured values only, taken straight from the saved report:
  header + report age (staleness), market regime, breadth, India VIX +
  volatility regime, institutional FII/DII flow (5D/10D/20D with the
  `signal_allowed` honesty line), event risk + top upcoming events, top
  technical stocks, top factor-ranked names, and any data-availability gaps.
- Ends with an explicit guardrails footer: analysis-only, measured vs.
  interpreted kept separate, not a buy/sell signal, no broker/orders.
- Split into a pure `_build_market_brief(report)` (dict -> str, unit-testable
  offline) and a thin `get_market_brief()` that loads the cache and calls it.
- Registered in `TOOLS` and `TOOL_SCHEMA` so the Ollama brain can invoke it.

## 2026-10-10 - Factor backtest harness fixed and wired into Market Lab UI

The factor backtest harness (`analysis/backtest_harness.py`) was committed but
never actually ran: `_safe_float` was used in `trend_component`,
`strength_component`, and `score_symbol` but was never defined or imported, so
`run_backtest` raised `NameError` on the first symbol. It is now functional and
surfaced as a new "Factor Backtest" panel in Market Lab.

Evidence-integrity fixes (analysis-only rules):

- Added a numeric `_safe_float()` helper (missing / non-numeric -> `None`).
- `trend` is read as the raw `TREND` classification string, not coerced through
  the numeric helper. Routing it through `_safe_float` previously yielded
  `None`, so `trend_counts` and the trend column were always empty.
- `_success_rate` actually computes the fraction of up days (a hit-rate), not an
  average return. It was stored/printed as `avg_20d_return` / "avg 20D return",
  which would misrepresent measured data. Renamed to `up_day_fraction` across
  the per-symbol entry, the decile stats keys, and the console output. Missing
  values stay `None` (never treated as zero).

Market Lab UI wiring (reuses the existing Worker / page / nav pattern):

- New "Factor Backtest" nav page: optional symbol list, "RUN BACKTEST" button,
  and a read-only result view. Blank input runs the 20-symbol quick sample.
- `run_backtest` is invoked lazily in a `"backtest"` background worker so the
  heavy scanner / Yahoo imports never block UI startup.
- `start_task` / `task_finished` / `task_succeeded` / `task_failed` now handle
  the `"backtest"` task. The result panel labels the metric as an up-day
  fraction (hit-rate), not a return, and repeats that this is not a signal.

Runtime call-path fixes (found after the panel was wired, covered by
regression tests that stub the network layer):

- `run_backtest(symbols, ...)` had `symbols` as a required positional with no
  default, but the UI's blank-input path calls `run_backtest(sample=20,
  quiet=True)`, which raised `TypeError: missing 1 required positional
  argument` on every "RUN BACKTEST" click. `symbols` now defaults to `None`.
- The universe-vs-explicit guard used `if symbols is None:`, but the CLI
  (`main()`) passes `args.symbols` = `[]` from `nargs="*"`. An empty list is
  not `None`, so `--quick` and any no-arg run took the explicit branch and
  backtested an empty pool (silently 0 symbols). The guard is now
  `if not symbols:` so both `None` and `[]` mean "use the universe".

Files changed:

- `analysis/backtest_harness.py` (fix `_safe_float`, trend string, rename
  `up_day_fraction`, `symbols=None` default + `if not symbols` guard)
- `market_lab_ui.py` (Factor Backtest page + backtest task handling)
- `tests/test_backtest_harness.py` (new: offline helper tests plus a
  network-stubbed `run_backtest` regression test)

## 2026-10-10 - Watchlist refresh results wired into the UI

The stock watchlist (added in `a383f45`) started a `"watchlist"` worker but
`task_succeeded` had no branch for it, so every refresh result was silently
dropped and the panel stayed on "waiting for first refresh…" forever. The
row renderer also formatted numbers with `+.2f` / `.1f`, which raised
`TypeError` on any `None` reading once data did arrive.

Behavior now:

- `task_succeeded` stores each `refresh_watch_symbol` result into
  `self.watch_data` and re-renders the panel.
- Watchlist state (`watch_symbols`, `watch_index`, `watch_data`) is
  initialized in `MarketLabWindow.__init__` so an early result cannot hit an
  `AttributeError`.
- Row rendering moved to a new pure, Qt-free `format_watchlist_line()` in
  `analysis/data/watchlist_engine.py`. Missing or `NaN` readings render as
  `--` instead of a fabricated number; analysis-only behavior is unchanged.

Files changed:

- `analysis/data/watchlist_engine.py` (added `_fmt`, `format_watchlist_line`)
- `market_lab_ui.py` (watchlist result handling, simplified render, init state)
- `tests/test_watchlist_engine.py` (new: 10 offline tests)

Validation:

- `.\venv\Scripts\python.exe -m unittest discover -s tests -v` → 51 passed.
- `py_compile` + BOM-aware `ast.parse` passed on the edited files.
- Formatter output spot-checked for AVAILABLE / waiting / NOT AVAILABLE /
  missing-value cases.

## 2026-10-09 - Agent Context Bootstrap

Added a model-agnostic context layer so Nova can be opened by another coding
agent and resumed safely.

Files added:

- `AGENTS.md`
- `README.md`
- `PROJECT_CONTEXT.md`
- `USER_CONTEXT.md`
- `docs/ARCHITECTURE.md`
- `docs/DEPENDENCIES.md`
- `docs/VALIDATION.md`
- `docs/WORKFLOW.md`
- `docs/MODEL_HANDOFF.md`

Repository facts recorded:

- Actual project folder is `C:\Users\Anirudh\nova`.
- The folder is not currently a Git repository.
- No dependency manifest was found before this pass.
- Existing runtime dependencies were inspected from `venv/`.
- Main assistant entry point is `main.py`.
- Market Lab entry point is `market_lab_ui.py`.
- Market behavior is analysis-only and must remain non-executing.

Code changes:

- Added a small entry-point docstring to `main.py`.

Validation:

- Initial read-only inventory and dependency inspection completed.
- Python syntax check passed across 39 source files using BOM-aware decoding.
- Main assistant import smoke check passed.
- Market Lab import smoke check passed.

## 2026-10-09 - Git And GitHub Initialization

- Initialized a local Git repository on branch `main`.
- Confirmed the existing `.gitignore` excludes all generated state
  (`venv/`, `.venv/`, `stt_models/`, `voices/`, `analysis/data/cache/`,
  `analysis/data/data/cache/`, `*.wav`, `*.zip`, `*.log`).
- Root commit `e6ff588` contains 55 source, doc, and context files (~1.1 MB).
- Created the private GitHub repository `benalanirudh-pixel/nova` and pushed
  `main`; first push authenticated through Git Credential Manager.
- Set repo-local git identity: Anirudh <benalanirudh@gmail.com>.
- Updated stale "not a Git repository" statements in `AGENTS.md`, `README.md`,
  `PROJECT_CONTEXT.md`, and `docs/MODEL_HANDOFF.md`.


## 2026-10-09 - Market Lab UI Report Persistence

- Fixed: `market_lab_ui.py` never saved successful reports to JSON, so
  `load_latest_saved_report()` had nothing to show on the next launch and
  `analysis/data/cache/market_lab/` did not exist at all.
- `Worker.run()` now calls `save_json_report()` in the background thread for
  every successful `"report"` result; save failures print a warning but never
  fail the task.
- Verified with a cache-first engine run: 18 s end-to-end using the cached
  1,999-stock scan; first saved report written (62 KB) and loaded back
  through the UI loader with safety guardrails intact.


## 2026-10-10 - Event Risk Engine Wired Via Verified Calendar

- Created `analysis/data/event_calendar.json` — the missing file that was the
  sole reason `event_risk_engine` reported NOT AVAILABLE and `overall_risk`
  stayed UNKNOWN. No Python source was changed; the wiring in
  `load_event_risk_context()` already existed.
- Populated with 11 source-verified events: India CPI/WPI releases (Oct 12,
  Oct 14), US BLS CPI/PPI/import-export releases (Oct 14-16), NSE 2026
  holidays (Dussehra Oct 20, Muhurat Nov 8, Diwali-Balipratipada Nov 10,
  Guru Nanak Nov 24, Christmas Dec 25), and the next RBI MPC decision
  (Dec 4).
- Sources cross-checked on 2026-10-10: Zerodha/Livemint/HDFC Sky (NSE
  holidays), MoSPI and DPIIT advance release calendars via IndiaInflation.com
  and Finostat, bls.gov (US releases), RBI 2026-27 MPC schedule.
- Result: report flag `event_risk_engine` = AVAILABLE, `overall_risk` =
  MODERATE with 5 events inside the 7-day window.
- Maintenance rule: `source_checked_at` must be re-verified within 24 hours
  or the engine deliberately reverts to NOT_AVAILABLE/UNKNOWN.


## 2026-10-10 - Assistant Availability Matrix + Event Calendar Checker

- `tools.py`: `get_market_analysis()` no longer underreports the system.
  Its availability matrix now merges the latest saved Market Lab report
  (cache-first, no network) into rows the scanner cannot measure: INDIA_VIX,
  volatility regime, SECTOR_STRENGTH, derivatives OI/IV/PCR/max-pain,
  INSTITUTIONAL_FLOW, EVENT_RISK. The report timestamp is printed as
  `MARKET_LAB_REPORT_TIMESTAMP` so staleness stays visible, and
  `MISSING_CRITICAL_LAYERS` is computed dynamically. Transaction-cost and
  covariance models remain honestly NOT_AVAILABLE. No-report path behaves
  exactly as before.
- New `check_event_calendar.py`: offline validator + 24 h staleness alarm +
  re-check checklist for `analysis/data/event_calendar.json`. Exit 0 =
  valid and fresh; exit 1 = stale, invalid, or missing. It never writes to
  the calendar and never fakes a source check.
- Registered `check_event_calendar.py` in `AGENTS.md` common commands.
- Preserved behavior note: `get_market_analysis()` still runs a live full
  NSE scan per call (pre-existing; unchanged).


## 2026-10-10 - Engine Math Test Suite

- New `tests/test_engine_math.py`: 32 reference-value tests using stdlib
  `unittest` (pytest is not installed; no new dependency added).
- Coverage: technical engine (SMA, EMA, RSI bounds/warm-up, MACD on constant
  series, True Range gap logic, Wilder ATR, ROC, relative volume, VWAP),
  volatility engine (rolling ATR known mean, realized-vol edge cases,
  percentile rank, regime thresholds, direction rules), risk engine
  (position sizing known values, input rejection, guardrail flags), event
  risk engine (freshness/completeness gates, proximity score escalation,
  rejection of unverified/naive-timestamp events, guardrails).
- Fixtures are hand-computed; no network, caches, or live market data.
- Result: 32/32 passing in ~0.02 s.
- Test command registered in `AGENTS.md`.


## 2026-10-10 - Research Factor Engine Built And Wired

- New `analysis/data/research_factor_engine.py`: cross-sectional factor
  ranking over the cached NSE scanner universe. Five transparent,
  equal-weighted z-score factors: MOMENTUM_60D, RELATIVE_STRENGTH,
  LOW_VOLATILITY (ATR% sign-flipped), TREND_STRUCTURE (EMA alignment
  0-3), PROXIMITY_52W_HIGH. Minimum universe 30, minimum factors per
  stock 3. No fundamental factors — Nova has no verified fundamentals
  source, so none are invented.
- Wired into `market_lab/market_lab_data.py` import block and report
  assembly; `data_availability.research_factor_engine` reflects status.
- New `tests/test_research_factor_engine.py`: 8 reference-value tests
  (availability, sign-flip, extreme winner/loser rank, missing columns,
  small universe, NaN exclusion, guardrails, z-score bounds).
- Full suite: 40 tests / 0.08 s, all passing.
- Live cache-first report now shows `research_factor_engine: AVAILABLE`
  (1,999-stock universe). Guardrails intact: `factor_rank_is_a_buy_sell_signal:
  false`, `buy_sell_authorization: false`, `trading_execution: false`.


## 2026-10-10 - Live-Only Report Mode + Calendar Re-Check Helper

- New `--live-only` mode in `market_lab/market_lab_data.py`:
  `get_market_lab_data(live_only=True)` reuses the newest cached equity
  scan at any age via `load_latest_market_scan_any_age()`, then refreshes
  only the cheap live layers (index returns, NIFTY snapshot, volatility,
  derivatives, institutional flow, risk, event risk). Report carries
  `mode: LIVE_ONLY` with scanner file + age labelled. `--live-only` and
  `--refresh` are mutually exclusive (CLI exits 2, function raises
  `ValueError`). Verified live: 1,999-stock reuse in seconds, report
  `market_lab_20261010_012258.json`, all availability flags AVAILABLE,
  guardrails all false.
- New `touch_event_calendar.py`: interactive re-check confirmer for
  `analysis/data/event_calendar.json`. Prints the 4 source groups + event
  consistency as 5 checks; only a literal `yes` stamps
  `source_checked_at` to now, anything else leaves the file untouched.
  Never touches the network, never edits events. Registered below.
- Deleted the half-built `analysis/tools/check_daily_calendar.py` stub
  (bad import of a nonexistent engine constant, broken source URL,
  untested scraping parsers). It was untracked and never committed.
- `market_lab_ui.py`: new `LIVE UPDATE` button beside `FULL REFRESH`
  calls `get_market_lab_data(live_only=True)` in the background worker
  (auto-saved to JSON like every report); both buttons disable while a
  report task runs. Import smoke confirms both handlers exist.
- `market_lab_ui.py`: staggered auto-refresh — `AUTO: OFF/ON` toggle +
  1 s header clock (`HH:MM:SS • NSE OPEN/CLOSED • data age • next update
  in Ns`). Live-only worker polls every 60 s in market hours, 30 s when
  closed; single-flight guard (never stacks workers), manual actions
  reset the countdown, failed polls retry next tick without killing
  auto mode. Session logic verified: weekday 10:00 IST open, Saturday
  and pre-open closed.
- `market_lab_ui.py`: 1-second live display tier — an always-on display
  ticker repaints the header clock, the Overview `Live` strip (clock,
  session badge, data age, countdown), and the REPORT TIME metric every
  second from memory only; zero network. The auto tick now only
  schedules polls.

