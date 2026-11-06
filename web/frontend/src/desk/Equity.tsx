import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useMarketData } from "../hooks/useMarketData";
import { useLiveQuote, useLiveWatch } from "../hooks/useLive";
import { isNum } from "../lib/format";
import type { StockProfile } from "../lib/types";
import { risk, withQuote, type Bar, type Risk } from "./analytics";
import { headline, INDEX_NAMES, INDICES, useDesk } from "./data";
import { big, Block, dayMonth, Empty, Flag, Kv, n, Pct, pc, sg, Table, type Col } from "./ui";

const DEFAULT_WATCH = ["RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN", "TCS", "INFY", "LT", "ITC", "BHARTIARTL", "AXISBANK", "MARUTI", "BAJFINANCE"];
const MAX_MONITOR = 22; // the live feed polls 25 symbols at most; three go to the index feed's own names
const tickSym = (s: string) => (s === "VIX" ? "INDIAVIX" : s);

interface MonitorRow { sym: string; px: unknown; p: unknown }
interface StockData {
  chart: { candles: { time: string; open: number; high: number; low: number; close: number; volume: number }[] };
  analysis: { company_name?: string; price: number; open: number; high: number; low: number; volume: number; return_1d: number; rsi_14: number; ema_200: number; vwap_20d: number; high_52w: number; low_52w: number };
}
interface Instrument {
  sym: string; name: string; sub: string; px: number | null; ch: number | null; p: number | null; o: unknown; h: unknown; l: unknown; v?: number | null;
  bars: Bar[]; rsi: number | null | undefined; hi52: number | null | undefined; lo52: number | null | undefined; ema200: number | null | undefined; vwap?: number | null;
}

const LiveLast = ({ r }: { r: MonitorRow }) => { const t = useLiveQuote(tickSym(r.sym)); return <>{n(t?.ltp ?? r.px)}</>; };
const LiveChg = ({ r }: { r: MonitorRow }) => { const t = useLiveQuote(tickSym(r.sym)); return <Pct v={t?.change_pct ?? r.p} />; };

function Monitor({ sym, go }: { sym: string; go: (s: string) => void }) {
  const { overview, stocks, bySymbol, chains, brief } = useDesk();
  const [group, setGroup] = useState(0);
  const k = overview?.kpis, sx = chains.SENSEX;
  const groups = useMemo(() => {
    const stock = (s: string): MonitorRow => ({ sym: s, px: bySymbol[s]?.p, p: bySymbol[s]?.r1 });
    const sxPrev = sx?.technicals?.prev_close;
    const indices: MonitorRow[] = [
      { sym: "NIFTY", px: k?.nifty?.price, p: k?.nifty?.change_percent }, { sym: "BANKNIFTY", px: k?.banknifty?.price, p: k?.banknifty?.change_percent },
      { sym: "SENSEX", px: sx?.spot, p: isNum(sx?.spot) && isNum(sxPrev) ? (sx!.spot! / sxPrev - 1) * 100 : null }, { sym: "VIX", px: k?.vix?.value, p: k?.vix?.change_percent },
    ];
    const active = [...stocks].sort((a, b) => b.val - a.val).map((r) => r.s).filter((s) => !DEFAULT_WATCH.includes(s));
    const movers = (a?: { symbol: string; ltp: unknown; change_pct: unknown }[]) => (a ?? []).map((m) => ({ sym: m.symbol, px: m.ltp, p: m.change_pct }));
    return [
      ["Watchlist", [...indices, ...[...DEFAULT_WATCH, ...active].slice(0, MAX_MONITOR).map(stock)]],
      ["Gainers", movers(brief?.movers.gainers)], ["Losers", movers(brief?.movers.losers)],
      ["Near high", (brief?.focus?.screens[0]?.rows ?? []).map((r) => ({ sym: r.symbol, px: r.price, p: r.return_1d }))],
    ] as [string, MonitorRow[]][];
  }, [k, sx, stocks, bySymbol, brief]);
  const rows = groups[group][1];
  useLiveWatch(rows.filter((r) => !(INDICES as readonly string[]).includes(r.sym)).slice(0, 24).map((r) => r.sym));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLElement && /INPUT|SELECT|TEXTAREA/.test(e.target.tagName)) return;
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const i = rows.findIndex((r) => r.sym === sym), next = rows[(i + (e.key === "ArrowDown" ? 1 : -1) + rows.length) % rows.length];
      if (next) go(next.sym);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [rows, sym, go]);

  const cols: Col<MonitorRow>[] = [
    { h: "Symbol", v: (r) => INDEX_NAMES[r.sym] ?? r.sym, text: true, bold: true },
    { h: "Last", v: (r) => <LiveLast r={r} /> }, { h: "Chg", v: (r) => <LiveChg r={r} /> },
  ];
  return (
    <section className="pane" style={{ gridArea: "wl" }} aria-label="Monitor">
      <div className="ph"><h2>Monitor</h2><span className="s">↑ ↓ moves. Click loads the sheet</span></div>
      <div className="sub-tabs">{groups.map(([t], i) => <button key={t} type="button" aria-pressed={group === i} onClick={() => setGroup(i)}>{t}</button>)}</div>
      <div className="body"><Table cols={cols} rows={rows} onRow={(r) => go(r.sym)} isOn={(r) => r.sym === sym} /></div>
    </section>
  );
}

function assess(q: Instrument, x: Risk, base: Risk | null, rel: boolean, stock: boolean) {
  const out: [string, string, string][] = [], px = q.px!, all = [x.e20, x.e50, q.ema200].filter(isNum), ex = (px - x.e20) / x.atr;
  out.push(["Trend", all.every((v) => px > v) ? (x.e20 > x.e50 ? "Aligned up" : "Above averages, not yet aligned") : all.every((v) => px < v) ? "Aligned down" : "Mixed", `EMA 20 ${x.slope20 >= 0 ? "rising" : "falling"} ${pc(x.slope20)} in 5D`]);
  const r = q.rsi;
  if (isNum(r)) out.push(["Momentum", r >= 70 ? "Stretched" : r <= 30 ? "Washed out" : r >= 55 ? "Firm" : r <= 45 ? "Soft" : "Neutral", `RSI ${n(r, 1)}, MACD hist ${sg(x.hist)}`]);
  out.push(["Extension", Math.abs(ex) >= 3 ? "Extended" : Math.abs(ex) >= 1.5 ? "Elevated" : "Normal", `${sg(ex, 1)} ATR from EMA 20`]);
  out.push(["Volatility", x.rv20 > x.rv60 * 1.15 ? "Expanding" : x.rv20 < x.rv60 * 0.85 ? "Contracting" : "Stable", `RV 20D ${n(x.rv20, 1)}% vs 60D ${n(x.rv60, 1)}%`]);
  const a = x.ret(20), b = base?.ret(20);
  if (rel && isNum(a) && isNum(b)) out.push(["Relative", a - b >= 2 ? "Leading" : a - b <= -2 ? "Lagging" : "In line", `${pc(a - b, 1)} vs Nifty over 20D`]);
  if (stock && x.upDown) out.push(["Accumulation", x.upDown >= 1.25 ? "Volume on up days" : x.upDown <= 0.8 ? "Volume on down days" : "Balanced", `Up/down volume ${n(x.upDown)}x over 20D`]);
  return out;
}

function Sheet({ q, wide, read, sideExtra }: { q: Instrument; wide?: ReactNode; read?: (a: [string, string, string][]) => ReactNode; sideExtra?: ReactNode }) {
  const { niftyRisk, niftyBars, flags } = useDesk();
  const isNifty = q.sym === "NIFTY";
  const x = useMemo(() => risk(q.bars, q.px, isNifty ? null : niftyBars), [q.bars, q.px, isNifty, niftyBars]);
  const px = q.px ?? 0;
  const head = (
    <div className="qh">
      <div><h1>{q.name}</h1><div className="sub">{q.sub}</div></div>
      <div><div className="px">{n(q.px)}</div><div className="chg"><Pct v={q.p} /> <span className="fa">({sg(q.ch)})</span></div></div>
      <div className="q">
        {([["Open", n(q.o)], ["High", n(q.h)], ["Low", n(q.l)], ...(x ? [["Gap", <Pct v={x.gap} />], ["ATR", `${n(x.atrPct)}%`], ["RV 20D", `${n(x.rv20, 1)}%`]] : []), ["RSI", n(q.rsi, 1)]] as [string, ReactNode][]).map(([k, v]) => <div key={k}><u>{k}</u><b>{v}</b></div>)}
      </div>
    </div>
  );
  let cards: ReactNode = <Empty>Not enough daily history for this symbol yet.</Empty>;
  if (x) {
    const ages = Math.min(q.bars.length - 1, 122);
    const rr = ([["1D", q.p, 1], ["5D", x.ret(5), 5], ["20D", x.ret(20), 20], ["60D", x.ret(60), 60], ["6M", x.ret(ages), ages]] as [string, number | null, number][])
      .map(([t, v, k]) => ({ t, v, b: niftyRisk?.ret(k) }));
    type Avg = [string, number | null | undefined, number?];
    const mas: Avg[] = [["EMA 9", x.e9], ["EMA 20", x.e20, x.slope20], ["EMA 50", x.e50, x.slope50], ["EMA 200", q.ema200], ...(isNum(q.vwap) ? [["VWAP 20D", q.vwap] as Avg] : [])];
    const lv = ([["52W high", q.hi52], ["High 60D", x.hi(60)], ["High 20D", x.hi(20)], ["Prior high", x.prevHigh], ["Pivot R2", x.r2], ["Pivot R1", x.r1], ["Pivot", x.pp], ["Pivot S1", x.s1], ["Pivot S2", x.s2], ["Prior low", x.prevLow], ["Low 20D", x.lo(20)], ["Low 60D", x.lo(60)], ["52W low", q.lo52], ["+1 ATR", px + x.atr], ["−1 ATR", px - x.atr], ["+2 ATR", px + 2 * x.atr], ["−2 ATR", px - 2 * x.atr]] as [string, number | null | undefined][])
      .filter((y): y is [string, number] => isNum(y[1])).concat([["Last", px]]).sort((a, b) => b[1] - a[1]);
    const m5 = (px * x.rv20) / 100 * Math.sqrt(5 / 252);
    cards = (
      <div className="sheet">
        <Block title="Performance" sub={isNifty ? "Absolute" : "Against Nifty 50"}>
          <Table cols={[{ h: "Period", v: (r) => r.t, text: true, bold: true }, { h: q.sym, v: (r) => <Pct v={r.v} /> }, ...(isNifty ? [] : [{ h: "Nifty", v: (r: typeof rr[number]) => <Pct v={r.b} /> }, { h: "Excess", v: (r: typeof rr[number]) => (isNum(r.v) && isNum(r.b) ? <Pct v={r.v - r.b} /> : "") }])]} rows={rr} />
        </Block>
        <Block title="Trend structure" sub={`Above EMA 20 for ${x.streak} sessions. MACD hist ${sg(x.hist)}`}>
          <Table cols={[{ h: "Average", v: (y: Avg) => y[0], text: true, bold: true }, { h: "Level", v: (y) => n(y[1]) }, { h: "Price vs", v: (y) => (isNum(y[1]) ? <Pct v={(px / y[1] - 1) * 100} d={1} /> : "") }, { h: "ATRs", v: (y) => (isNum(y[1]) ? sg((px - y[1]) / x.atr, 1) : "") }, { h: "5D slope", v: (y) => (y[2] != null ? <Pct v={y[2]} /> : "") }]} rows={mas} />
        </Block>
        <Block title="Level map" sub="Sorted by price. Distance in % and ATR">
          <Table cols={[{ h: "Level", v: (y: [string, number]) => y[0], text: true }, { h: "Price", v: (y) => n(y[1]) }, { h: "Dist", v: (y) => (y[0] === "Last" ? "" : <Pct v={(y[1] / px - 1) * 100} d={1} />) }, { h: "ATRs", v: (y) => (y[0] === "Last" ? "" : sg((y[1] - px) / x.atr, 1)) }]} rows={lv} isOn={(y) => y[0] === "Last"} />
        </Block>
        <div className="stack">
          <Block title="Risk and volatility" sub={x.beta != null ? `Beta on ${x.pairs} sessions` : ""}>
            <div className="pad"><Kv rows={[["Realized vol 20D", `${n(x.rv20, 1)}%`], ["Realized vol 60D", `${n(x.rv60, 1)}%`], ["ATR 14", `${n(x.atr)} (${n(x.atrPct)}%)`], ["1σ 5-day", `${n(px - m5, 0)} to ${n(px + m5, 0)}`], ["Max drawdown 6M", pc(x.maxDrawdown, 1)], ["From 6M high", pc(x.fromHigh, 1)], ["Sessions since high", x.sinceHigh], ["Best day 60D", pc(x.best)], ["Worst day 60D", pc(x.worst)], ["Up days 60D", `${n(x.upDays, 0)}%`], ...(x.beta != null ? [["Beta to Nifty 60D", n(x.beta)], ["Correlation 60D", n(x.corr)], ["Alpha 60D", pc(x.alpha, 1)]] as [string, string][] : [])]} /></div>
          </Block>
          {x.vol20 > 0 && <Block title="Volume"><div className="pad"><Kv rows={[...(q.v ? [["Volume today", big(q.v)]] as [string, string][] : []), ["Average 20D", big(x.vol20)], ["Average 5D", big(x.vol5)], ["5D vs 20D", `${n(x.vol5 / x.vol20)}x`], ["Up/down volume 20D", x.upDown ? `${n(x.upDown)}x` : "n/a"]]} /></div></Block>}
        </div>
        {wide}
      </div>
    );
  }
  const asm = x ? assess(q, x, niftyRisk, !isNifty, !!q.v) : [];
  return (
    <>
      <section className="pane" style={{ gridArea: "main" }} aria-label={q.name}>{head}<div className="body">{cards}</div></section>
      <section className="pane" style={{ gridArea: "side" }} aria-label="Assessment">
        <div className="body">
          {read?.(asm)}
          <div className="sigs">{asm.map(([k, v, s]) => <div className="sig" key={k}><u>{k}</u><div><b>{v}</b><small>{s}</small></div></div>)}</div>
          {sideExtra}
          <div className="ph bt"><h2>Data flags</h2><span className="s">{flags.length} open</span></div>
          <div className="pad flags">{flags.map(([t, d]) => <div key={t}><Flag>{t}</Flag><p>{d}</p></div>)}</div>
        </div>
      </section>
    </>
  );
}

function IndexSheet({ sym }: { sym: string }) {
  const { overview, chains, indexBars, niftyRisk } = useDesk();
  const tick = useLiveQuote(tickSym(sym));
  const k = overview?.kpis, ch = chains[sym], t = ch?.technicals, b = overview?.breadth;
  const card = sym === "NIFTY" ? k?.nifty : sym === "BANKNIFTY" ? k?.banknifty : sym === "VIX" ? k?.vix : null;
  const base = (card?.price ?? card?.value ?? ch?.spot ?? null) as number | null;
  const px = tick?.ltp ?? base;
  const prev = (card?.prev_close as number | undefined) ?? t?.prev_close;
  const p = tick?.change_pct ?? (card?.change_percent as number | null | undefined) ?? (isNum(px) && isNum(prev) ? (px / prev - 1) * 100 : null);
  const bars = useMemo(() => indexBars(sym), [overview, ch, sym]); // eslint-disable-line
  if (!k && !ch) return <div className="pane" style={{ gridColumn: "2 / 4" }}><Empty>{overview ? "No saved report yet. Run a refresh to build one." : "Loading market data."}</Empty></div>;
  const q: Instrument = {
    sym, name: INDEX_NAMES[sym], sub: sym === "VIX" ? "NSE volatility index" : "NSE index", px, ch: tick?.change ?? (card?.change_abs as number | null | undefined) ?? (isNum(px) && isNum(prev) ? px - prev : null), p,
    o: card?.open, h: card?.high ?? t?.day_high, l: card?.low ?? t?.day_low, bars, rsi: t?.rsi, hi52: t?.high_52w, lo52: t?.low_52w, ema200: t?.ema["200"],
  };
  const m = ch?.metrics, below = b?.above_ema200_percent as number | undefined;
  return (
    <Sheet q={q}
      read={() => (
        <div className="view"><div className="who">Nova read</div><h1>{headline(niftyRisk?.ret(5), below)}</h1>
          <p>Nifty {pc(k?.nifty?.change_percent)} on the day. {n(b?.declining, 0)} stocks fell against {n(b?.advancing, 0)} that rose, and {n(below, 0)}% hold above their 200-day average.</p></div>
      )}
      sideExtra={m && <><div className="ph bt"><h2>Option snapshot</h2><span className="s">Expiry {ch?.expiry}</span></div><div className="pad"><Kv rows={[["Priced range", `${n(m.breakeven_low, 0)} to ${n(m.breakeven_high, 0)}`], ["OI PCR", n(m.pcr_oi)], ["ATM IV", `${n(m.atm_iv, 1)}%`], ["Max pain", n(m.max_pain, 0)]]} /></div></>}
      wide={sym === "NIFTY" && b && <Block wide title="Market internals" sub="Saved report scan"><div className="pad"><Kv rows={[["Advancing", n(b.advancing, 0)], ["Declining", n(b.declining, 0)], ["A/D", n(b.ad_ratio)], ["Above EMA 20", `${n(b.above_ema20_percent, 1)}%`], ["Above EMA 50", `${n(b.above_ema50_percent, 1)}%`], ["Above EMA 200", `${n(b.above_ema200_percent, 1)}%`], ["Strong uptrend", `${n(b.strong_uptrend_percent, 1)}%`], ["Strong downtrend", `${n(b.strong_downtrend_percent, 1)}%`], ["New 52W highs", n(b.new_52w_highs, 0)], ["New 52W lows", n(b.new_52w_lows, 0)]]} /></div></Block>} />
  );
}

function StockSheet({ sym, go }: { sym: string; go: (s: string) => void }) {
  const { bySymbol, tradeDate } = useDesk();
  const stock = useMarketData<StockData>(`/stock/${encodeURIComponent(sym)}`);
  const prof = useMarketData<StockProfile>(`/stock/${encodeURIComponent(sym)}/profile`);
  const tick = useLiveQuote(sym);
  useLiveWatch([sym]);
  const scan = bySymbol[sym], a = stock.data?.analysis, P = prof.data, px = tick?.ltp ?? a?.price ?? scan?.p ?? null, r1 = tick?.change_pct ?? a?.return_1d ?? scan?.r1 ?? null;
  const bars = useMemo(() => withQuote((stock.data?.chart.candles ?? []).map((c): Bar => [c.time, c.open, c.high, c.low, c.close, c.volume ?? 0]), tradeDate, { px, o: a?.open, h: a?.high, l: a?.low }), [stock.data, tradeDate, px, a]);
  const q: Instrument = {
    sym, name: a?.company_name ?? P?.profile?.company ?? scan?.n ?? sym, sub: [sym, P?.profile?.sector ?? scan?.x, P?.profile?.industry].filter(Boolean).join(", "), px, p: r1, ch: tick?.change ?? (isNum(px) && isNum(r1) ? px - px / (1 + r1 / 100) : null),
    o: a?.open, h: a?.high, l: a?.low, v: tick?.volume ?? a?.volume, bars, rsi: a?.rsi_14 ?? scan?.rsi, hi52: a?.high_52w ?? scan?.h52, lo52: a?.low_52w ?? scan?.l52, ema200: a?.ema_200, vwap: a?.vwap_20d,
  };
  const R = P?.ratios ?? {}, res = P?.results;
  const wide = P && (
    <>
      {P.ratios && <Block title="Valuation and quality" sub="Yahoo Finance"><div className="pad"><Kv rows={[["Market cap", isNum(R.market_cap_cr) ? `${n(R.market_cap_cr / 1e5, 2)} L Cr` : "n/a"], ["P/E trailing", n(R.pe_trailing, 1)], ["P/E forward", n(R.pe_forward, 1)], ["P/B", n(R.pb)], ["EV/EBITDA", n(R.ev_ebitda, 1)], ["PEG", n(R.peg)], ["ROE", `${n(R.roe, 1)}%`], ["ROA", `${n(R.roa, 1)}%`], ["Gross margin", `${n(R.gross_margin, 1)}%`], ["Operating margin", `${n(R.operating_margin, 1)}%`], ["Net margin", `${n(R.profit_margin, 1)}%`], ["Revenue growth", pc(R.revenue_growth, 1)], ["Earnings growth", pc(R.earnings_growth, 1)], ["Debt/equity", n(R.debt_to_equity_x)], ["Dividend yield", `${n(R.dividend_yield_pct)}%`], ["Next results", res?.next_date ? dayMonth(res.next_date) : "n/a"], ["EPS estimate", n(res?.eps_estimate)]]} /></div></Block>}
      {P.ownership && <Block title="Ownership" sub={P.ownership.nse ? "NSE" : "Yahoo Finance"}><div className="pad"><Kv rows={P.ownership.nse ? [["Promoter", `${n(P.ownership.nse.promoter_pct, 1)}%`], ["FII", `${n(P.ownership.nse.fii_pct, 1)}%`], ["DII", `${n(P.ownership.nse.dii_pct, 1)}%`], ["Public", `${n(P.ownership.nse.public_pct, 1)}%`]] : [["Insiders", `${n(P.ownership.yahoo?.insiders_pct, 1)}%`], ["Institutions", `${n(P.ownership.yahoo?.institutions_pct, 1)}%`]]} />{!P.ownership.nse && <div style={{ marginTop: 6 }}><Flag>NSE shareholding unavailable</Flag></div>}</div></Block>}
      {P.quarters && <Block wide title="Quarterly results" sub="₹ Cr"><Table cols={[{ h: "Quarter", v: (y) => y.period.slice(0, 7), text: true, bold: true }, { h: "Revenue", v: (y) => n(y.revenue_cr, 0) }, { h: "YoY", v: (y) => <Pct v={y.revenue_yoy} d={1} /> }, { h: "EBITDA", v: (y) => n(y.ebitda_cr, 0) }, { h: "Net inc", v: (y) => n(y.net_income_cr, 0) }, { h: "QoQ", v: (y) => <Pct v={y.net_income_qoq} d={1} /> }, { h: "Op mgn", v: (y) => `${n(y.operating_margin, 1)}%` }, { h: "EPS", v: (y) => n(y.eps) }]} rows={P.quarters} /></Block>}
      {P.peers && <Block wide title={P.peers.group || "Peers"} sub={`${P.peers.peer_count ?? P.peers.rows.length} listed peers`}><Table cols={[{ h: "Symbol", v: (y) => y.symbol, text: true, bold: true }, { h: "Last", v: (y) => n(y.price) }, { h: "20D", v: (y) => <Pct v={y.return_20d} d={1} /> }, { h: "60D", v: (y) => <Pct v={y.return_60d} d={1} /> }, { h: "RS 20D", v: (y) => sg(y.relative_strength_20d, 1) }, { h: "RSI", v: (y) => n(y.rsi_14, 0) }, { h: "Value Cr", v: (y) => n(y.traded_value_cr, 0) }]} rows={P.peers.rows} onRow={(y) => go(y.symbol)} isOn={(y) => y.symbol === sym} /></Block>}
      {P.news && P.news.length > 0 && <Block wide title="News"><Table cols={[{ h: "Headline", v: (y) => y.title, text: true }, { h: "Source", v: (y) => y.source ?? "", text: true }]} rows={P.news.slice(0, 6)} /></Block>}
    </>
  );
  return (
    <Sheet q={q} wide={wide}
      read={(asm) => <div className="view"><div className="who">Nova read</div><h1>{asm.length ? `Trend ${asm[0][1].toLowerCase()}. Momentum ${(asm[1]?.[1] ?? "n/a").toLowerCase()}.` : stock.error ? "History unavailable." : "Building the sheet."}</h1></div>}
      sideExtra={
        <>
          {stock.error && <div className="pad"><Flag>History failed</Flag><p className="note-t">{stock.error}</p></div>}
          {(P?.highlights ?? []).length > 0 && <ul className="reads pad">{P!.highlights.slice(0, 4).map((h) => <li key={h.text}>{h.text}</li>)}</ul>}
          <div className="pad bt1"><Flag>No stock option data</Flag><p className="note-t">Nova’s option feed covers NIFTY, BANKNIFTY and SENSEX only.</p></div>
        </>
      } />
  );
}

export default function Equity() {
  const [params, setParams] = useSearchParams();
  const sym = (params.get("s") ?? "NIFTY").toUpperCase();
  const go = (s: string) => setParams({ s });
  const isIndex = (INDICES as readonly string[]).includes(sym);
  return (
    <div className="grid-eq">
      <Monitor sym={sym} go={go} />
      {isIndex ? <IndexSheet key={sym} sym={sym} /> : <StockSheet key={sym} sym={sym} go={go} />}
    </div>
  );
}
