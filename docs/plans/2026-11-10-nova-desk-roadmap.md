# Nova Desk roadmap: better terminal, then a supply-chain page

Status: plan only, not started. Written 10 Nov 2026 after the bug sweep in
`CHANGES.md` (holiday-aware feed, stock option chains, scheduler fixes).

Ground rules stay the same: analysis only, no orders, no buy or sell calls,
every number shows its source and age, and missing or conflicting data is
flagged instead of filled.

## Part 1. Make the terminal better (data first, then screens)

Ordered by value to a trader per hour of work.

| # | Change | Data source already in Nova | Effort |
|---|--------|-----------------------------|--------|
| 1 | **Futures and basis per stock**: lot size, futures price, basis, OI build-up (long build-up, short covering and so on) | NSE session in `derivatives_engine` (MCP `get_futures_data` is blocked by NSE) | M |
| 2 | **Option chain expiry picker** on the F&O desk, for indices and stocks | `/api/fno/{symbol}?expiry=` already works; UI only | S |
| 3 | **OI change history**: compare today's chain with the previous saved chain to show where writers moved | Save each chain snapshot to `analysis/data/cache/derivatives/` | M |
| 4 | **Delivery percentage and bulk or block deals** on the stock sheet | MCP `get_bulk_deals`; NSE security-wise delivery file | M |
| 5 | **Results and events calendar** fed by the NSE holiday list plus board meetings | `nse_live.trading_holidays()` (new); board meetings currently blocked, keep flagged | S |
| 6 | **Sector rotation table**: 1W, 1M and 3M relative strength against Nifty per sector, ranked | `/api/scan` sector table already has the inputs | S |
| 7 | **Watchlists you save** (several named lists, kept in the browser) | none needed | S |
| 8 | **Alerts panel**: price, % move or level crossed, shown in the desk only (no orders) | live ticks over SSE | M |
| 9 | **Fix the remaining blocked sources**: shareholding, board meetings and announcements fail from both the MCP and Nova's NSE session (non-JSON reply). Try BSE's API as a fallback, as SENSEX already does | `fno_desk.fetch_bse_chain` pattern | M |
| 10 | **Faster first load of a stock sheet** (about 10 to 20 seconds today): cache `/api/stock/{s}` history for the session day | `web/api/routes/stock.py` | S |

Known data limits to keep visible on screen:

- NSE blocks several endpoints for automated clients; they are flagged, not faked.
- Stock option chains exist only for F&O stocks; others say so.
- Greeks, probabilities and gamma are model estimates and are labelled that way.

## Part 2. Supply-chain page ("who supplies Reliance, who buys from it")

### What the page shows

New route `/chain?s=RELIANCE`, reachable from the stock sheet.

- **Suppliers** (upstream): listed companies that sell inputs to the
  company, with what they supply.
- **Customers** (downstream): listed companies that buy its products.
- **Peers** (same layer): already available from the profile peers table.
- For every listed link: live price, 1D, 20D and relative strength from the
  scan, so you can see whether the chain is moving together.
- Each link carries its **evidence**: the document, page and date it came
  from, plus a confidence tag. Links without evidence are not shown.

### The hard part: there is no free structured feed for this

NSE, BSE, Yahoo and the MCP server do not publish supplier or customer lists.
The honest sources are:

1. **Related-party transactions** in annual reports and the half-yearly
   related-party disclosures filed on NSE and BSE. These name group companies
   that buy from or sell to each other, with rupee values. Strongest evidence,
   but limited to related parties.
2. **Annual reports and investor presentations**, which often name major
   raw materials, suppliers and customer segments in words.
3. **Industry structure**: for a refiner, crude suppliers are mostly foreign and
   unlisted, while customers include oil marketing companies, airlines, paint
   and plastics makers. This gives *likely* links, which must be labelled as
   inferred, never shown as fact.

### Proposed build

1. **Store**: `analysis/data/supply_chain/links.json`, one record per link:
   `{from, to, relation: supplier|customer, product, evidence: {doc, url, page, date}, confidence: filed|stated|inferred, checked_at}`.
2. **Extractor** (offline, run by hand): download the company's annual report
   PDF and related-party filing, let the local Ollama model extract candidate
   links with page citations, then check each candidate against the NSE master
   so only real listed symbols survive. A person approves the list before it
   is saved. Nothing is generated on the fly in the page.
3. **API**: `GET /api/supply-chain/{symbol}` reads the store, joins scan prices,
   and returns links grouped by relation, with the evidence attached.
4. **Page**: three tables (suppliers, company, customers), each row linking to
   its own stock sheet, plus a "Not covered yet" message for symbols with no
   approved links.
5. **Start small**: seed the 20 most-traded names (RELIANCE, HDFCBANK, TCS,
   LT, MARUTI and so on), then grow.

### Open questions before building

- Is related-party plus annual-report evidence enough, or do you want inferred
  industry links shown too (clearly tagged)?
- Who approves extracted links: you by hand, or accept only `filed` evidence
  automatically?
- How often to refresh: once a year after annual reports, plus quarterly for
  related-party filings, is the natural rhythm.
