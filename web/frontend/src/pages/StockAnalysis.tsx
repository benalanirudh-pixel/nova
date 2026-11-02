import { useEffect, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import MomentumGauge from "../components/MomentumGauge";
import NewsList from "../components/NewsList";
import { SEARCH_ID } from "../components/SymbolSearch";
import { Body, Change, Chip, Num, Panel, Stat, toneOf } from "../components/ui";
import { useStockAnalysis, useStockFetch } from "../hooks/useStockAnalysis";
import { fmt, fmtCompact, isNum } from "../lib/format";
import type { Highlight, StockProfile } from "../lib/types";

const KEY = "nova.recentSymbols";
// starting points for the empty state only; every number shown comes from the API
const QUICK = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "SBIN", "BHARTIARTL", "ITC"];

function loadRecent(): string[] {
  try {
    const v = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(v) ? v.filter((s) => typeof s === "string").slice(0, 5) : [];
  } catch { return []; }
}
function saveRecent(list: string[]) {
  try { localStorage.setItem(KEY, JSON.stringify(list)); } catch { /* storage unavailable */ }
}

const NotAvail = () => <span className="text-muted">N/A</span>;
const flag = (v: unknown, t: string) => (v === true ? t : null);
const th = "px-2 py-1 font-normal";
const MAS = ["ema_9", "ema_20", "ema_50", "ema_200", "sma_20", "sma_50", "sma_200"] as const;

const cr = (v: unknown, d = 0) => (isNum(v) ? `₹${fmt(v, d)} Cr` : "N/A");
const daysUntil = (iso: string) => Math.round((Date.parse(`${iso.slice(0, 10)}T00:00:00Z`) - Date.parse(new Date().toISOString().slice(0, 10))) / 86_400_000);
const longDate = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00Z`).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function Row({ k, children }: { k: string; children: ReactNode }) {
  return <div className="flex h-6 items-center justify-between gap-2 border-t border-line/15 text-[12px] first:border-t-0"><span className="text-secondary">{k}</span><span className="truncate text-right">{children}</span></div>;
}

/** Search-first landing: no empty charts or N/A grids before a symbol is picked. */
function EmptyState({ recent, run }: { recent: string[]; run: (s: string) => void }) {
  const chip = "rounded-full border border-line/40 bg-panel px-3 py-1 font-mono text-[12px] text-secondary hover:border-accent/60 hover:text-fg focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60";
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center px-4 py-16 text-center sm:py-24">
      <svg viewBox="0 0 16 16" className="mb-5 h-7 w-7 text-accent" aria-hidden><path d="M8 0l1.6 6.4L16 8l-6.4 1.6L8 16l-1.6-6.4L0 8l6.4-1.6z" fill="currentColor" /></svg>
      <h1 className="text-2xl font-semibold tracking-tight">Research any NSE stock</h1>
      <p className="mt-2 max-w-md text-[14px] leading-relaxed text-secondary">
        Valuation, quarterly results, the next results date, ownership, competitors, news and technicals on one page.
      </p>
      <button onClick={() => document.getElementById(SEARCH_ID)?.focus()}
        className="mt-6 flex w-full max-w-sm items-center gap-2 rounded-md border border-line/50 bg-panel px-3 py-2.5 text-left text-[13px] text-muted hover:border-accent/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
        <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden><circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" /></svg>
        Search symbol or company
        <kbd className="ml-auto rounded border border-line/50 px-1.5 font-mono text-[11px]">/</kbd>
      </button>
      {recent.length > 0 && (
        <div className="mt-8 w-full">
          <div className="mb-2 text-[12px] text-muted">Recently analyzed</div>
          <div className="flex flex-wrap justify-center gap-2">{recent.map((s) => <button key={s} onClick={() => run(s)} className={chip}>{s}</button>)}</div>
        </div>
      )}
      <div className="mt-6 w-full">
        <div className="mb-2 text-[12px] text-muted">Popular large caps</div>
        <div className="flex flex-wrap justify-center gap-2">{QUICK.map((s) => <button key={s} onClick={() => run(s)} className={chip}>{s}</button>)}</div>
      </div>
    </div>
  );
}

function QuoteStrip({ sym, name, sector, price, change, a }: { sym: string; name?: string | null; sector?: string; price: unknown; change: unknown; a: Record<string, unknown> }) {
  const lo = a.low_52w, hi = a.high_52w;
  const pos = isNum(lo) && isNum(hi) && isNum(price) && hi > lo ? Math.min(100, Math.max(0, ((price - lo) / (hi - lo)) * 100)) : null;
  const Kv = ({ k, children }: { k: string; children: ReactNode }) => <span className="shrink-0"><span className="text-muted">{k} </span>{children}</span>;
  return (
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-md border border-line/40 bg-panel px-4 py-3 text-[12px]">
      <div className="min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="font-mono text-lg font-semibold text-accent">{sym}</span>
          {sector && <span className="text-[11px] text-muted">{sector}</span>}
        </div>
        <div className="max-w-[22rem] truncate text-[12px] text-secondary" title={name ?? undefined}>{name ?? "—"}</div>
      </div>
      <div className="flex items-baseline gap-2">
        <Num v={price} className="text-2xl font-semibold" />
        <Change pct={change} className="text-[13px]" />
      </div>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
        <Kv k="Open"><Num v={a.open} /></Kv><Kv k="High"><Num v={a.high} /></Kv><Kv k="Low"><Num v={a.low} /></Kv>
        <Kv k="Volume"><span className="font-mono tabular-nums">{fmtCompact(a.volume)}</span></Kv>
        <Kv k="Rel. volume"><Num v={a.relative_volume} suffix={isNum(a.relative_volume) ? "x" : ""} /></Kv>
      </div>
      <div className="flex min-w-[14rem] flex-1 items-center gap-2" title={pos === null ? "52-week range N/A" : `${pos.toFixed(0)}% of the 52-week range`}>
        <span className="text-muted">52W</span><Num v={lo} d={0} className="text-secondary" />
        <span className="relative h-1.5 flex-1 rounded-full bg-gradient-to-r from-negative/40 via-line/40 to-positive/40">
          {pos !== null && <span className="absolute -top-1 h-3.5 w-1 rounded-sm bg-fg" style={{ left: `calc(${pos}% - 2px)` }} />}
        </span>
        <Num v={hi} d={0} className="text-secondary" />
      </div>
      <div className="flex gap-3">
        {(["1d", "5d", "20d", "60d"] as const).map((w) => (
          <span key={w} className="flex flex-col items-end leading-tight"><span className="text-[10.5px] text-muted">{w.toUpperCase()}</span><Num v={a[`return_${w}`]} d={1} signed suffix="%" /></span>
        ))}
      </div>
    </div>
  );
}

function Takeaways({ items }: { items: Highlight[] }) {
  const tone = { positive: "border-positive/30 bg-positive/8 text-positive", negative: "border-negative/30 bg-negative/8 text-negative", neutral: "border-line/40 bg-raised text-secondary" };
  const glyph = { positive: "▲", negative: "▼", neutral: "•" };
  return (
    <div className="flex flex-wrap gap-1.5" title="Rule-based reading of the numbers on this page. Descriptive, not a buy/sell signal.">
      {items.map((h, i) => (
        <span key={i} className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-[12px] ${tone[h.tone]}`}>
          <span className="text-[9px]">{glyph[h.tone]}</span><span className="text-fg/90">{h.text}</span>
        </span>
      ))}
    </div>
  );
}

function Ratios({ r }: { r: Record<string, number | null> }) {
  const S = ({ k, v, d = 2, suf = "", title }: { k: string; v: unknown; d?: number; suf?: string; title?: string }) =>
    <Stat k={k} title={title}><Num v={v} d={d} suffix={isNum(v) ? suf : ""} /></Stat>;
  return (
    <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
      <Stat k="Market cap"><span className="font-mono tabular-nums">{cr(r.market_cap_cr)}</span></Stat>
      <S k="P/E (TTM)" v={r.pe_trailing} /><S k="P/E (forward)" v={r.pe_forward} />
      <S k="P/B" v={r.pb} /><S k="PEG" v={r.peg} /><S k="EV / EBITDA" v={r.ev_ebitda} />
      <S k="ROE" v={r.roe} d={1} suf="%" /><S k="ROA" v={r.roa} d={1} suf="%" /><S k="Debt / equity" v={r.debt_to_equity_x} suf="x" />
      <S k="Operating margin" v={r.operating_margin} d={1} suf="%" /><S k="Net margin" v={r.profit_margin} d={1} suf="%" /><S k="Current ratio" v={r.current_ratio} />
      <Stat k="Revenue growth"><Num v={r.revenue_growth} d={1} signed suffix="%" /></Stat>
      <Stat k="Earnings growth"><Num v={r.earnings_growth} d={1} signed suffix="%" /></Stat>
      <S k="EPS (TTM)" v={r.eps_trailing} />
      <S k="Book value / share" v={r.book_value} /><S k="Dividend / share" v={r.dividend_per_share} />
      <S k="Dividend yield" v={r.dividend_yield_pct} suf="%" title="Dividend per share ÷ price" />
    </div>
  );
}

function Quarters({ q }: { q: NonNullable<StockProfile["quarters"]> }) {
  const qLabel = (p: string) => { const d = new Date(`${p}T00:00:00Z`); return d.toLocaleDateString("en-IN", { month: "short", year: "2-digit", timeZone: "UTC" }); };
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="text-[11px] text-muted">
          <tr className="border-b border-line/25"><th className={`${th} text-left`}>Quarter</th><th className={`${th} text-right`}>Revenue (Cr)</th><th className={`${th} text-right`}>QoQ</th><th className={`${th} text-right`}>YoY</th><th className={`${th} text-right`}>Net profit (Cr)</th><th className={`${th} text-right`}>QoQ</th><th className={`${th} text-right`}>Op. margin</th><th className={`${th} text-right`}>EPS</th></tr>
        </thead>
        <tbody>
          {q.map((r) => (
            <tr key={r.period} className="border-t border-line/15 hover:bg-raised/60">
              <td className="whitespace-nowrap px-2 py-1 text-secondary">{qLabel(r.period)}</td>
              <td className="px-2 text-right"><Num v={r.revenue_cr} d={0} /></td>
              <td className="px-2 text-right"><Num v={r.revenue_qoq} d={1} signed suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.revenue_yoy} d={1} signed suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.net_income_cr} d={0} /></td>
              <td className="px-2 text-right"><Num v={r.net_income_qoq} d={1} signed suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.operating_margin} d={1} suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.eps} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Results({ r, last }: { r: NonNullable<StockProfile["results"]>; last?: string }) {
  const d = r.next_date ? daysUntil(r.next_date) : null;
  return (
    <div className="space-y-2">
      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="text-[12px] text-muted">Next results (expected)</div>
          <div className="text-xl font-semibold">{r.next_date ? longDate(r.next_date) : <NotAvail />}</div>
        </div>
        {d !== null && <span className={`rounded-full border px-2.5 py-0.5 text-[12px] font-medium ${d <= 14 ? "border-warning/40 bg-warning/10 text-warning" : "border-line/50 text-secondary"}`}>{d === 0 ? "Today" : `in ${d} day${d === 1 ? "" : "s"}`}</span>}
      </div>
      <div>
        <Row k="EPS estimate"><Num v={r.eps_estimate} /></Row>
        <Row k="Revenue estimate"><span className="font-mono tabular-nums">{cr(r.revenue_estimate_cr)}</span></Row>
        <Row k="Last reported quarter">{last ? longDate(last) : <NotAvail />}</Row>
        <Row k="Last ex-dividend">{r.ex_dividend_date ? longDate(r.ex_dividend_date) : <NotAvail />}</Row>
      </div>
      {r.board_meetings.length > 0 && (
        <div className="space-y-1 border-t border-line/20 pt-2 text-[12px]">
          <div className="text-muted">NSE board meetings</div>
          {r.board_meetings.map((m, i) => <div key={i} className="flex gap-2"><span className="font-mono text-secondary">{m.date}</span><span className="truncate">{m.purpose ?? ""}</span></div>)}
        </div>
      )}
    </div>
  );
}

function Ownership({ o, err }: { o: NonNullable<StockProfile["ownership"]>; err?: string }) {
  const n = o.nse, y = o.yahoo;
  const seg = n
    ? [["Promoters", n.promoter_pct, "bg-accent"], ["FII / FPI", n.fii_pct, "bg-info"], ["DII", n.dii_pct, "bg-purple"], ["Public", n.public_pct, "bg-line"]] as const
    : [["Promoters & insiders", y?.insiders_pct, "bg-accent"], ["Institutions (FII + DII)", y?.institutions_pct, "bg-info"]] as const;
  const known = seg.reduce((t, [, v]) => t + (isNum(v) ? v : 0), 0);
  return (
    <div className="space-y-3">
      <div className="flex h-3 overflow-hidden rounded-full bg-raised">
        {seg.map(([k, v, c]) => isNum(v) && <div key={k} className={c} style={{ width: `${Math.min(100, v)}%` }} title={`${k} ${fmt(v, 1)}%`} />)}
      </div>
      <div className="space-y-1">
        {seg.map(([k, v, c]) => (
          <div key={k} className="flex items-center gap-2 text-[12px]">
            <span className={`h-2.5 w-2.5 rounded-sm ${c}`} /><span className="text-secondary">{k}</span>
            <Num v={v} d={1} suffix={isNum(v) ? "%" : ""} className="ml-auto" />
          </div>
        ))}
        {!n && known > 0 && known < 100 && (
          <div className="flex items-center gap-2 text-[12px]"><span className="h-2.5 w-2.5 rounded-sm bg-raised" /><span className="text-secondary">Public and others</span><Num v={100 - known} d={1} suffix="%" className="ml-auto" /></div>
        )}
      </div>
      {!n && y && (
        <div className="text-[11px] leading-relaxed text-muted">
          {isNum(y.institutions_count) && <>{fmt(y.institutions_count, 0)} institutions hold <Num v={y.institutions_float_pct} d={1} suffix="%" className="text-secondary" /> of free float. </>}
          The FII / DII split comes from NSE's shareholding filing, which isn't available right now{err ? ` (${err.replace(/\.$/, "")})` : ""}. Yahoo Finance reports the combined institutional share.
        </div>
      )}
    </div>
  );
}

function Peers({ p, run }: { p: NonNullable<StockProfile["peers"]>; run: (s: string) => void }) {
  if (p.rows.length === 0) return <div className="p-1 text-[12px] text-muted">No scanner cache to compare against. Run a full refresh to build one.</div>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-[12px]">
        <thead className="text-[11px] text-muted">
          <tr className="border-b border-line/25"><th className={`${th} text-left`}>Company</th><th className={`${th} text-right`}>Price</th><th className={`${th} text-right`}>20D</th><th className={`${th} text-right`}>60D</th><th className={`${th} text-right`} title="Relative strength vs NIFTY, 20 days">RS 20D</th><th className={`${th} text-right`}>RSI</th><th className={`${th} text-right`}>Trend</th></tr>
        </thead>
        <tbody>
          {p.rows.map((r) => (
            <tr key={r.symbol} onClick={() => !r.is_self && run(r.symbol)}
              className={`border-t border-line/15 ${r.is_self ? "bg-accent/8" : "cursor-pointer hover:bg-raised/60"}`}>
              <td className="max-w-[12rem] px-2 py-1">
                {r.is_self ? <span className="font-mono font-medium text-accent">{r.symbol}</span>
                  : <button onClick={(e) => { e.stopPropagation(); run(r.symbol); }} className="font-mono font-medium text-fg hover:text-accent focus:outline-none focus-visible:underline">{r.symbol}</button>}
                <div className="truncate text-[11px] text-muted" title={r.company_name}>{r.company_name}</div>
              </td>
              <td className="px-2 text-right"><Num v={r.price} /></td>
              <td className="px-2 text-right"><Num v={r.return_20d} d={1} signed suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.return_60d} d={1} signed suffix="%" /></td>
              <td className="px-2 text-right"><Num v={r.relative_strength_20d} d={1} signed /></td>
              <td className="px-2 text-right"><Num v={r.rsi_14} d={0} /></td>
              <td className="px-2 text-right"><Chip text={r.trend} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Tally of the API's own condition labels by tone. Descriptive only: not a buy/sell signal. */
function ConditionRead({ labels }: { labels: unknown[] }) {
  const tones = labels.filter((l) => typeof l === "string" && l && l !== "N/A").map((l) => toneOf(l));
  const pos = tones.filter((t) => t.includes("positive")).length, neg = tones.filter((t) => t.includes("negative")).length;
  const mid = tones.length - pos - neg;
  if (tones.length === 0) return <div className="text-[11px] text-muted">Conditions N/A</div>;
  const w = (k: number) => `${(k / tones.length) * 100}%`;
  return (
    <div className="w-full" title="Count of the engine's condition labels by tone (RSI, MACD, VWAP, volume, trend, structure, price vs 7 averages). Descriptive, not a buy/sell signal.">
      <div className="flex h-1.5 overflow-hidden rounded-full bg-line/30">
        <div className="bg-positive" style={{ width: w(pos) }} /><div className="bg-warning/70" style={{ width: w(mid) }} /><div className="bg-negative" style={{ width: w(neg) }} />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[11px] tabular-nums">
        <span className="text-positive">{pos} constructive</span><span className="text-warning">{mid} neutral</span><span className="text-negative">{neg} weak</span>
      </div>
    </div>
  );
}

function Technicals({ a, price, score }: { a: Record<string, unknown>; price: unknown; score: unknown }) {
  const structure = [flag(a.higher_high, "HH"), flag(a.higher_low, "HL"), flag(a.lower_high, "LH"), flag(a.lower_low, "LL")].filter(Boolean).join(" · ");
  const side = (m: string) => (isNum(a[m]) && isNum(price) ? (price >= (a[m] as number) ? "ABOVE" : "BELOW") : undefined);
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <MomentumGauge score={score} label="Momentum" className="h-[72px] w-[72px]" />
        <div className="min-w-0 flex-1 space-y-2">
          <ConditionRead labels={[a.rsi_condition, a.macd_condition, a.vwap_condition, a.volume_condition, a.trend, a.market_structure, ...MAS.map(side)]} />
          <div className="flex flex-wrap items-center gap-1.5 text-[11px]"><span className="text-muted">Trend</span><Chip text={a.trend} /><span className="text-muted">Structure</span>{structure && <span className="font-mono text-secondary">{structure}</span>}<Chip text={a.market_structure} /></div>
        </div>
      </div>
      <div>
        <Row k="RSI (14)"><span className="flex items-center gap-2"><Num v={a.rsi_14} /><Chip text={a.rsi_condition} /></span></Row>
        <Row k="MACD histogram"><span className="flex items-center gap-2"><Num v={a.macd_histogram} signed /><Chip text={a.macd_condition} /></span></Row>
        <Row k="VWAP 20D"><span className="flex items-center gap-2"><Num v={a.vwap_20d} /><Chip text={a.vwap_condition} /></span></Row>
        <Row k="ATR (14)"><Num v={a.atr_14} /></Row>
        <Row k="ROC (12)"><Num v={a.roc_12} signed suffix="%" /></Row>
        <Row k="Volume vs 20D avg"><span className="flex items-center gap-2"><span className="font-mono tabular-nums">{fmtCompact(a.volume)} / {fmtCompact(a.volume_average_20)}</span><Chip text={a.volume_condition} /></span></Row>
      </div>
      <div className="grid grid-cols-2 gap-x-4 sm:grid-cols-1 2xl:grid-cols-2">
        {MAS.map((m) => {
          const ma = a[m], gap = isNum(ma) && isNum(price) && ma !== 0 ? ((price - ma) / ma) * 100 : null;
          return <Row key={m} k={m.replace("_", " ").toUpperCase()}><span className="flex items-center gap-2"><Num v={ma} /><Num v={gap} d={1} signed suffix="%" className="w-14 text-right" /></span></Row>;
        })}
      </div>
    </div>
  );
}

export default function StockAnalysis() {
  const tech = useStockAnalysis();
  const prof = useStockFetch<StockProfile>("/profile");
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const [params, setParams] = useSearchParams();
  const wanted = params.get("s")?.trim().toUpperCase() || null;
  const { analyze: runTech } = tech, { analyze: runProf } = prof;

  // the URL is the source of truth so header search, chips and reloads all land here
  useEffect(() => {
    if (!wanted) return;
    runTech(wanted);
    runProf(wanted);
  }, [wanted, runTech, runProf]);

  const run = (sym: string) => (sym === wanted ? (runTech(sym), runProf(sym)) : setParams({ s: sym }));

  // only symbols that analyzed successfully become recent chips
  const okSym = tech.data?.info.symbol;
  useEffect(() => {
    if (!okSym) return;
    setRecent((r) => { const n = [okSym, ...r.filter((x) => x !== okSym)].slice(0, 5); saveRecent(n); return n; });
  }, [okSym]);

  if (!wanted) return <EmptyState recent={recent} run={run} />;

  const a = tech.data?.analysis ?? {};
  const info = tech.data?.info;
  const price = info?.price ?? a.price;
  const p = prof.data;
  const err = p?.errors ?? {};
  const pl = prof.loading || (!p && !prof.error);
  const tl = tech.loading || (!tech.data && !tech.error);
  const sectionErr = (v: unknown, key: string) => (prof.error ? prof.error : v == null ? err[key] ?? "Source returned nothing." : null);

  return (
    <div className="mx-auto max-w-[1800px] space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        {recent.length > 0 && <span className="text-[11px] text-muted">Recent</span>}
        {recent.map((s) => (
          <button key={s} onClick={() => run(s)} aria-current={s === wanted || undefined}
            className={`shrink-0 rounded-full border px-2.5 py-0.5 font-mono text-[11px] focus:outline-none focus-visible:ring-1 focus-visible:ring-accent ${s === wanted ? "border-accent/60 bg-accent/10 text-accent" : "border-line/40 bg-panel text-secondary hover:border-accent/50 hover:text-fg"}`}>{s}</button>
        ))}
        <div className="ml-auto min-w-0 truncate text-[11px]" role="status" aria-busy={tech.loading || prof.loading}>
          {tech.loading || prof.loading ? <span className="text-accent">Analyzing {wanted}… prices, fundamentals and news can take up to 40s</span>
            : tech.error ? <span className="text-negative" title={tech.error}>{tech.error}</span>
              : <span className="text-muted">{typeof a.source === "string" && `Prices: ${a.source}`}{p && ` · Fundamentals and news: NSE feed and Yahoo Finance, ${new Date(p.generated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" })}`}</span>}
        </div>
      </div>

      {tech.error && !tech.data ? (
        <div className="rounded-md border border-negative/30 bg-negative/5 px-4 py-6 text-center text-[13px]">
          <div className="font-medium text-negative">Couldn't analyze {wanted}</div>
          <div className="mt-1 text-secondary">{tech.error}. Check the symbol in the search bar, or try again.</div>
        </div>
      ) : (
        <QuoteStrip sym={info?.symbol ?? wanted} name={info?.name ?? p?.profile?.company} sector={p?.profile?.sector} price={price} change={info?.change} a={a} />
      )}

      {p && p.highlights.length > 0 && <Takeaways items={p.highlights} />}

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 2xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-2">
          <Panel title="Company" right={p?.profile?.website && <a href={p.profile.website} target="_blank" rel="noopener noreferrer" className="text-secondary hover:text-accent">{p.profile.website.replace(/^https?:\/\/(www\.)?/, "")}</a>}>
            <Body loading={pl} error={sectionErr(p?.profile, "profile")}>
              <p className="line-clamp-4 text-[12.5px] leading-relaxed text-secondary" title={p?.profile?.description}>{p?.profile?.description ?? "No description."}</p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px]">
                <span><span className="text-muted">Industry </span>{p?.profile?.industry ?? "N/A"}</span>
                <span><span className="text-muted">Employees </span><Num v={p?.profile?.employees} d={0} /></span>
                {p?.peers && <span><span className="text-muted">NSE group </span>{p.peers.group}</span>}
              </div>
            </Body>
          </Panel>
          <Panel title="Valuation and financial ratios">
            <Body loading={pl} error={sectionErr(p?.ratios, "ratios")} lines={6}>{p?.ratios && <Ratios r={p.ratios} />}</Body>
          </Panel>
          <Panel title="Quarterly results" right="Consolidated, ₹ crore" bodyClass="p-1">
            <Body loading={pl} error={sectionErr(p?.quarters, "income")} lines={5}>{p?.quarters && <Quarters q={p.quarters} />}</Body>
          </Panel>
        </div>

        <div className="space-y-2">
          <Panel title="Results calendar" right={p?.results && "Yahoo Finance"}>
            <Body loading={pl} error={sectionErr(p?.results, "calendar")}>{p?.results && <Results r={p.results} last={p.quarters?.[0]?.period} />}</Body>
          </Panel>
          <Panel title="Ownership" right={p?.ownership && (p.ownership.nse ? "NSE shareholding" : "Yahoo Finance")}>
            <Body loading={pl} error={sectionErr(p?.ownership, "holders")}>{p?.ownership && <Ownership o={p.ownership} err={err.shareholding} />}</Body>
          </Panel>
          <Panel title="Competitors" bodyClass="p-1"
            right={p?.peers && <span title={`Same NSE ${p.peers.basis.replace("_", " ")}; ranked by 20-day traded value from the scanner cache${p.peers.as_of ? ` (${p.peers.as_of.replace("T", " ")})` : ""}`}>{p.peers.group}{p.peers.peer_count ? ` · ${p.peers.peer_count} listed` : ""}</span>}>
            <Body loading={pl} error={sectionErr(p?.peers, "peers")} lines={6}>{p?.peers && <Peers p={p.peers} run={run} />}</Body>
          </Panel>
        </div>

        <div className="space-y-2 lg:col-span-2 lg:grid lg:grid-cols-2 lg:gap-2 lg:space-y-0 2xl:col-span-1 2xl:block 2xl:space-y-2">
          <Panel title="Latest news" right={p?.news && `${p.news.length} headlines · Google News`} bodyClass="max-h-[30rem] overflow-auto px-2 py-0">
            <Body loading={pl} error={sectionErr(p?.news, "news")} lines={8}>{p?.news && <NewsList items={p.news} />}</Body>
          </Panel>
          <div className="space-y-2">
            <Panel title="Technical snapshot" right={a.timestamp && typeof a.timestamp === "string" ? `as of ${a.timestamp.slice(0, 10)}` : undefined}>
              <Body loading={tl} error={tech.error} lines={6}><Technicals a={a} price={price} score={tech.data?.score.overall ?? null} /></Body>
            </Panel>
            <Panel title="Corporate actions" bodyClass="px-2.5 py-1">
              <Body loading={pl} error={sectionErr(p?.corporate_actions, "actions")}>
                {p?.corporate_actions?.length ? p.corporate_actions.map((c, i) => (
                  <Row key={i} k={c.subject ?? ""}><span className="font-mono text-secondary">{c.ex_date ?? "N/A"}</span></Row>
                )) : <div className="text-[12px] text-muted">None on record.</div>}
              </Body>
            </Panel>
          </div>
        </div>
      </div>
    </div>
  );
}
