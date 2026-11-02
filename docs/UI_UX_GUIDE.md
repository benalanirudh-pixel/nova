# Nova Terminal — UI/UX Design Guide

Professional trading analysis terminal. PySide6/Qt desktop. Dark theme only.
Indian market focus. Analysis-only — no execution, no orders.

---

## 1. Design Principles

| Principle | Rule |
|-----------|------|
| **Data density** | Every pixel shows actionable data. No decorative whitespace. |
| **Glanceability** | Key numbers (price, change, regime) readable in <1 second. |
| **Color = meaning** | Green/red = direction. Amber = warning. Cyan = active/selected. Never decorative. |
| **Monospace for numbers** | All prices, percentages, timestamps in monospace. Prevents layout shift. |
| **Analysis only** | Guardrail bar always visible. No BUY/SELL affordance anywhere. |
| **Honest data** | Missing/stale data shown as "—" or "N/A", never fabricated. Freshness badge always visible. |

---

## 2. Layout Architecture

```
┌──────────────────────────────────────────────────────┐
│  COMMAND BAR (44px)                                  │
│  Brand · Regime · Search · Service dots · Clock      │
├────┬─────────────────────────────────────────────────┤
│    │  TICKER STRIP (30px)                            │
│ S  │  NIFTY · BANKNIFTY · VIX · Freshness           │
│ I  │─────────────────────────────────────────────────│
│ D  │                                                 │
│ E  │  PAGE CONTENT (QStackedWidget)                  │
│ B  │  Scrollable. Full height. Panels + cards.       │
│ A  │                                                 │
│ R  │                                                 │
│    │                                                 │
│ 56 │                                                 │
│ px │                                                 │
├────┴─────────────────────────────────────────────────┤
│  STATUS BAR (26px)                                   │
│  NSE status · Scanner age · Guardrail · CPU/RAM · IST│
└──────────────────────────────────────────────────────┘
```

### Shell components

| Component | Height | Purpose |
|-----------|--------|---------|
| **Command bar** | 44px | Brand identity, regime badge, symbol/command search, service health, clock |
| **Sidebar** | Full height, 56px wide | 5 navigation items with active indicator. Custom-painted buttons. |
| **Ticker strip** | 30px | Live index prices. Auto-populated from report data. |
| **Status bar** | 26px | Market hours, data freshness, guardrail text, system metrics, IST clock |
| **Page area** | Remaining | QScrollArea with padded content. Each page owns its internal layout. |

### Sidebar navigation

- 56px wide rail, dark (`SIDEBAR` token)
- Each button: 56×52px, custom QPainter rendering
- Active state: 3px cyan bar on left edge, cyan icon color
- Hover state: subtle `SURFACE_ALT` background, white icon
- Inactive: `MUTED` icon, `MUTED2` label
- Order: MARKET → STOCKS → FLOWS → LAB → AI

---

## 3. Color System

All colors from `styles/design_tokens.py`. Never hardcode hex in components.

### Palette

| Token | Hex | Usage |
|-------|-----|-------|
| `BG` | `#050B10` | Window/page background |
| `SURFACE` | `#091620` | Panel/card background |
| `SURFACE_ALT` | `#0D1B26` | Hover state, alt rows |
| `SURFACE_RAISED` | `#0E1F2E` | Elevated cards |
| `SIDEBAR` / `HEADER` | `#061019` | Chrome surfaces |
| `BORDER` | `#183746` | Default borders |
| `BORDER_BRIGHT` | `#1B6170` | Focus/active borders |
| `BORDER_DIM` | `#0F202B` | Subtle dividers |

### Text hierarchy

| Token | Hex | Usage |
|-------|-----|-------|
| `TEXT` | `#F2F6FA` | Primary text, prices, headings |
| `SECONDARY` | `#91A9BE` | Labels, descriptions, data values |
| `MUTED` | `#617A91` | Placeholders, inactive nav |
| `MUTED2` | `#4A6572` | Disabled, de-emphasized |

### Semantic colors (directional)

| Token | Hex | Meaning |
|-------|-----|---------|
| `GREEN` | `#00E6A0` | Positive / bullish / OK / advances |
| `RED` | `#FF4058` | Negative / bearish / alert / declines |
| `AMBER` | `#FFBD4A` | Warning / caution / unchanged |
| `CYAN` | `#00D9F5` | Active / selected / accent / section headers |
| `BLUE` | `#3198FF` | Info / neutral |
| `PURPLE` | `#B49AFF` | Accent / factor highlight |

### Freshness colors

| Age | Color | Label |
|-----|-------|-------|
| < 10 min | `#00E6A0` | FRESH |
| 10 min – 2 h | `#FFBD4A` | STALE |
| 2 h – 12 h | `#FF4058` | STALE |
| > 12 h | `#FF1A3A` | CRITICAL |

### Background tints (for badges/chips)

| Token | Hex | Usage |
|-------|-----|-------|
| `BG_SUCCESS` | `#003326` | Behind green badges |
| `BG_WARNING` | `#2A1B00` | Behind amber badges |
| `BG_ERROR` | `#330A14` | Behind red badges |
| `BG_INFO` | `#0A1B33` | Behind blue badges |

### Rules

1. **Green/red for direction only.** Never use green for "go" or red for "stop" in non-market context.
2. **Cyan for interactive highlights.** Active tab, section header, focus ring.
3. **No color-only meaning.** Always pair with text, icon, or position.
4. **Contrast minimum 4.5:1** for `TEXT` on `SURFACE` (currently ~12:1, well above threshold).
5. **Tinted backgrounds** for badges: use `BG_SUCCESS`/`BG_WARNING`/`BG_ERROR` behind colored text.

---

## 4. Typography

### Font stack

| Role | Font | Fallback |
|------|------|----------|
| UI text (labels, buttons, descriptions) | Segoe UI | sans-serif |
| Data (prices, numbers, timestamps, code) | Consolas | monospace |

### Type scale

| Token | Size | Usage |
|-------|------|-------|
| `FONT_SIZE_CAPTION` | 8.5px | Footnotes, guardrail text |
| `FONT_SIZE_SMALL` | 9.5px | Status bar, ticker labels, chips |
| `FONT_SIZE_REGULAR` | 11px | Body text, inputs, table cells |
| `FONT_SIZE_MEDIUM` | 13px | Section headers, large labels |
| `FONT_SIZE_LARGE` | 16px | Page titles, brand text |
| `FONT_SIZE_XLARGE` | 20px | KPI values (index prices) |
| `FONT_SIZE_KPI` | 28px | Hero numbers (when needed) |
| `FONT_SIZE_TICKER` | 9px | Ticker strip data |

### Weight scale

| Weight | Value | Usage |
|--------|-------|-------|
| Regular | 400 | Body text, descriptions |
| Medium | 500 | Labels |
| Semibold | 600 | Buttons, nav items, sub-headers |
| Bold | 700 | Prices, KPIs, section headers |

### Rules

1. **All numeric data in Consolas.** Tabular alignment requires monospace.
2. **Bold only for prices and headers.** Overuse kills hierarchy.
3. **Letter-spacing: 0.5–1px** on uppercase labels (nav, section headers).
4. **No text below 7px.** Even guardrail text at 7px is the floor.

---

## 5. Spacing System

8dp grid. All spacing from tokens.

| Token | Value | Usage |
|-------|-------|-------|
| `SPACE_XS` | 4px | Between icon and label, tight chip padding |
| `SPACE_SM` | 8px | Between related items, inner card padding (compact) |
| `SPACE_MD` | 12px | Card padding, section gaps (dense pages) |
| `SPACE_LG` | 16px | Page margins, card padding (standard) |
| `SPACE_XL` | 24px | Section separation |
| `SPACE_XXL` | 32px | Page-level separation |

### Dense layout rules

- Page content margins: 16px horizontal, 12px top, 16px bottom
- Card internal padding: 12px sides, 10px top, 12px bottom
- Between cards in a row: 12px gap
- Between sections vertically: 12px gap
- Key-value row spacing: 6–8px vertical
- Ticker strip: 0px margins, 6px between data items

### Border radius

| Token | Value | Usage |
|-------|-------|-------|
| `BORDER_RADIUS_SM` | 4px | Buttons, inputs, small cards |
| `BORDER_RADIUS_MD` | 8px | Standard cards, panels |
| `BORDER_RADIUS_LG` | 12px | Large cards, dialogs |

---

## 6. Component Patterns

### Panel / section card

```
┌─ SECTION TITLE ──────────────────────────┐
│ ▎ Cyan left border (2px)                  │
│ ┄┄┄┄┄┄ dim separator ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄ │
│   Key          Value                      │
│   Key          Value                      │
└───────────────────────────────────────────┘
```

- Background: `SURFACE`
- Border: 1px `BORDER`
- Left accent: 2px `CYAN` (for titled sections)
- Title: uppercase, 8px, `CYAN`, bold
- Separator: 1px `BORDER_DIM`
- Key: 9px, `MUTED`
- Value: 9px, `SECONDARY`, monospace

### Index card (NIFTY / BANKNIFTY)

```
┌─ NIFTY 50 ─────────────── source badge ─┐
│                                          │
│   23,053.10  +116.35 (+0.51%)           │
│                                          │
│   5D: +2.00%  20D: +1.91%  60D: -6.34% │
│  ┌──────────────────────────────────────┐│
│  │  sparkline / mini chart area         ││
│  └──────────────────────────────────────┘│
└──────────────────────────────────────────┘
```

- Top gradient: `SURFACE_ALT` → `SURFACE`
- Top accent: 2px `CYAN` border
- Price: 20px, `TEXT`, bold, monospace
- Change: 11px, `GREEN`/`RED`, monospace
- Metrics row: 8px chips, monospace

### Breadth bar (custom painted)

- Rounded rectangle, 32px height
- Green (advances) → Amber (unchanged) → Red (declines)
- Proportional widths
- Black text labels inside segments

### Key-value row

```
Key label ························· Value
```

- Key: 9px, `MUTED`, left-aligned
- Value: 9px, `SECONDARY` or semantic color, monospace, right-aligned
- Spacing: 8px horizontal gap, addStretch between

### Buttons

| Variant | Background | Text | Border |
|---------|-----------|------|--------|
| Default | transparent | `SECONDARY` | 1px `BORDER` |
| Primary | `CYAN` | `#000` | none |
| Danger | transparent | `RED` | 1px `RED` |
| Disabled | — | `MUTED2` | `BORDER` dimmed |

- Height: 30px standard, 36px for prominent actions
- Padding: 0 12–16px
- Font: 10px, semibold/bold, 0.5–0.8px letter-spacing
- Hover: border-color brightens, subtle background fill
- Cursor: pointer on all interactive elements

---

## 7. Page Layout Guidelines

### Market Overview (tab 0)

**Purpose:** At-a-glance market snapshot. Most data-dense page.

```
┌ Regime label ─────────────── Freshness · Refresh ┐
├──────────────────────┬───────────────────────────┤
│   NIFTY 50 card      │   BANK NIFTY card         │
│   (with sparkline)   │   (with sparkline)        │
├──────────────────────┴───────────────────────────┤
│   MARKET BREADTH bar                              │
│   ADV: 393  DEC: 1592  UNCH: 25                  │
├────────────────────────────┬─────────────────────┤
│ SECTOR INTELLIGENCE        │ VOLATILITY          │
│  (top movers table)        │  ATR, VIX, regime   │
├────────────────────────────┴─────────────────────┤
│ DERIVATIVES                                       │
│  NIFTY PCR, max pain, IV  │ BANKNIFTY same      │
├──────────────────────────────────────────────────┤
│ EVENT RISK  │  INSTITUTIONAL  │  RISK CONTEXT    │
└──────────────────────────────────────────────────┘
```

- Two-column layout for index cards
- Single-column for breadth bar (full width)
- Two-column for sector + volatility
- Flexible multi-column for bottom sections

### Stock Analysis (tab 1)

**Purpose:** Single-stock deep dive.

- Top toolbar: symbol input + timeframe selector + mode combo
- Metrics card: price, change, OHLC, volume
- Oscillators: RSI, MACD, Stochastic in key-value panels
- AI narrative: scrollable text area
- Chart: candle/line chart area (when available)

### Institutional Flows (tab 2)

**Purpose:** FII/DII flow analysis.

- Wait for report data (show placeholder until loaded)
- FII section: net flow, streak, recent history
- DII section: same structure
- Combined view: flow comparison

### Market Lab (tab 3)

**Purpose:** Raw report JSON + AI narrative.

- Horizontal splitter: JSON (left) | Narrative (right)
- JSON: read-only QPlainTextEdit, monospace
- AI Narrate button: primary style, triggers brain analysis
- Status label shows report load state

### Nova AI (tab 4)

**Purpose:** Chat interface to Ollama.

- Chat history: scrollable message bubbles
- User: dark bg, border-only
- Nova: surface bg, cyan border, model label
- Input bar at bottom: text input + send button
- Reset button: danger variant

---

## 8. Interaction Patterns

### Navigation

- Sidebar click: instant tab switch, no animation
- Active state: cyan indicator + icon color change
- Pages lazy-load on first visit (show "Loading..." placeholder)
- Search bar: type symbol → switches to STOCKS tab. `/ai <query>` → switches to AI tab.

### Data loading

- `_DataWorker(QThread)` pattern for all async data
- Show loading state in button (disable + change text)
- On success: populate widgets, emit signals to parent
- On failure: show red error label, keep last good data
- Never block the UI thread

### Refresh

- REFRESH button in Market Overview: triggers full report reload
- Disabled during load, re-enabled on completion
- Freshness badge updates automatically from report age

### Keyboard

- Tab key navigates interactive elements
- Enter in search bar triggers search/command
- Focus indicators: `CYAN` border on inputs

---

## 9. Data Display Rules

### Number formatting

| Data type | Format | Example |
|-----------|--------|---------|
| Price (INR) | `₹{:,.2f}` | ₹23,053.10 |
| Percentage | `{:+.2f}%` | +0.51% |
| Crore value | `₹{:.2f}Cr` | ₹1,234.56Cr |
| Large number | `{:,.0f}` | 1,592 |
| VIX | `{:.2f}` | 15.30 |

### Color coding for values

```python
color = GREEN if value >= 0 else RED
# Exception: VIX (high = bearish, use RED for high VIX)
```

### Missing data

- Numeric: show "—" (em dash)
- Text: show "N/A"
- Never show 0 when data is missing
- Never fabricate a value

### Freshness

- Always show data age
- Color-code by freshness tier
- Include source label where possible ("live NSE quote", "saved daily history")

---

## 10. Chart Guidelines

### Candlestick / OHLC (stock analysis)

- Bullish: `GREEN` filled body
- Bearish: `RED` filled body
- Volume bars: 40% opacity below chart
- Max 500 candles visible at once
- Provide OHLC values in tooltip/label (not color-only)

### Sparklines (index cards)

- Simple line chart, no axes, no labels
- 90px height area
- Background: `BG`
- Line: `CYAN` or directional color
- Area fill: 10–15% opacity

### Breadth bar (market overview)

- Custom QPainter widget
- Green → Amber → Red proportional segments
- Black text labels inside when segment > 30px
- 32px height, 4px corner radius

---

## 11. Status & Health Indicators

### Service dots (command bar)

- 8×8px circle + 3-letter label
- Green: service responding
- Red: service down
- Muted: unchecked / initializing
- Check interval: 15 seconds

### Market status (status bar)

- "NSE: OPEN" in `GREEN` during trading hours (9:15–15:30 IST, Mon–Fri)
- "NSE: CLOSED" in `RED` otherwise
- Monospace, 8px, bold

### Regime badge (command bar)

- Shows market regime from report (e.g., "MILDLY_BEARISH")
- Dynamic border color matches regime severity
- Background: `SURFACE`, border-radius: 3px
- Font: Consolas 8px bold

---

## 12. Guardrails (non-negotiable)

These survive every redesign. Period.

1. **Guardrail text** in status bar, always visible: uppercase, 7px, `MUTED2`
2. **`BUY_SELL_AUTHORIZED = False`** in design_tokens.py — never change
3. **No trade execution UI** — no buy/sell buttons, no order forms, no broker connect
4. **Analysis-only framing** — all language is analytical ("signal", "regime", "bias"), never instructional ("buy", "sell", "enter")

---

## 13. Anti-Patterns to Avoid

| Don't | Why | Do instead |
|-------|-----|------------|
| Decorative gradients | Waste space, distract from data | Flat surfaces, subtle gradient only on index cards |
| Rounded corners > 8px | Looks consumer, not professional | 4px default, 6px for cards |
| Large padding/margins | Reduces data density | 12px card padding, 16px page margins |
| Animated transitions between tabs | Adds latency perception | Instant switch |
| Colored backgrounds for sections | Competes with data colors | `SURFACE` with border accent |
| Multiple font families | Noisy | Segoe UI + Consolas only |
| Icons/emojis for navigation | Ambiguous, inconsistent rendering | Single-letter icons (M, S, F, L, A) |
| Light mode | Not appropriate for trading terminals | Dark only |
| Auto-playing animations | Distracting during analysis | Static display, update on data change |
| Hover-only information | Desktop-only assumption | Always show key data; hover for extras |

---

## 14. Accessibility

### Minimum requirements

- **Contrast:** TEXT on SURFACE = ~12:1 (exceeds 4.5:1 AA)
- **Focus rings:** Cyan border on focused inputs/buttons
- **Keyboard navigation:** Tab order matches visual order
- **No color-only meaning:** Directional colors always paired with +/- sign or label
- **Monospace alignment:** Tabular figures prevent layout shift

### Desktop-specific (PySide6)

- `QWidget.setToolTip()` on all interactive elements
- `QPushButton.setCursor(Qt.PointingHandCursor)` on all clickable
- Text selectable in data labels where useful (`TextSelectableByMouse`)
- Scrollbars always visible (8px, `BORDER` handle)

---

## 15. File Map

| File | Owns |
|------|------|
| `styles/design_tokens.py` | All color, font, spacing, freshness tokens |
| `styles/nova_theme.qss` | Unified QSS stylesheet |
| `terminal/main_window.py` | Shell: command bar, sidebar, ticker, status bar |
| `terminal/style.py` | Shared widget helpers (`lbl`, `btn`, `card`, `kv_row`) — wire pages to use this |
| `terminal/pages/market_overview.py` | Market dashboard page |
| `terminal/pages/stock_analysis.py` | Single-stock analysis page |
| `terminal/pages/institutional.py` | FII/DII flows page |
| `terminal/pages/market_lab.py` | JSON report + AI narrative page |
| `terminal/pages/nova_ai.py` | Chat interface page |
| `market_lab/widgets.py` | Reusable terminal widgets (IndexCard, BreadthBar, etc.) |
| `market_lab/view_model.py` | Report → UI data adapter |
