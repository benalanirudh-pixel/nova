import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { IChartApi, LogicalRange } from "lightweight-charts";
import CandlestickChart from "../components/CandlestickChart";
import IndicatorChart from "../components/IndicatorChart";
import MomentumGauge from "../components/MomentumGauge";
import SymbolSearch, { type SymbolItem } from "../components/SymbolSearch";
import { Change, Chip, Num, Panel } from "../components/ui";
import { useStockAnalysis } from "../hooks/useStockAnalysis";
import { fetchJSON } from "../lib/api";
import { fmt, fmtCompact, isNum } from "../lib/format";
import type { Candle } from "../lib/types";

const KEY = "nova.recentSymbols";

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
const th = "px-1.5 font-normal";

function Row({ k, children }: { k: string; children: ReactNode }) {
  return <div className="flex h-5 items-center justify-between gap-2 text-[11px]"><span className="text-secondary">{k}</span><span className="truncate text-right">{children}</span></div>;
}
function IndRow({ k, v, s }: { k: string; v: ReactNode; s?: unknown }) {
  return (
    <tr className="h-5 border-t border-line/20 hover:bg-line/15">
      <td className="whitespace-nowrap px-1.5 text-secondary">{k}</td>
      <td className="whitespace-nowrap px-1.5 text-right">{v}</td>
      <td className="px-1.5 text-right">{s !== undefined && <Chip text={s} />}</td>
    </tr>
  );
}
/** Price vs moving average: value, % gap (from API numbers), above/below marker. */
function MaRow({ k, ma, price }: { k: string; ma: unknown; price: unknown }) {
  const gap = isNum(ma) && isNum(price) && ma !== 0 ? ((price - ma) / ma) * 100 : null;
  return (
    <tr className="h-5 border-t border-line/20 hover:bg-line/15">
      <td className="whitespace-nowrap px-1.5 text-secondary">{k}</td>
      <td className="px-1.5 text-right"><Num v={ma} /></td>
      <td className="px-1.5 text-right"><Num v={gap} signed suffix="%" /></td>
      <td className="px-1.5 text-right">{gap === null ? <NotAvail /> : <Chip text={gap >= 0 ? "ABOVE" : "BELOW"} />}</td>
    </tr>
  );
}
const Kv = ({ k, children }: { k: string; children: ReactNode }) =>
  <span className="shrink-0"><span className="text-muted">{k} </span>{children}</span>;

/** Single dense line: symbol, name, price, change, OHLC, volume, 52W range, returns. */
function QuoteStrip({ sym, name, price, change, a }: { sym: string; name?: string | null; price: unknown; change: unknown; a: Record<string, unknown> }) {
  const lo = a.low_52w, hi = a.high_52w;
  const pos = isNum(lo) && isNum(hi) && isNum(price) && hi > lo ? Math.min(100, Math.max(0, ((price - lo) / (hi - lo)) * 100)) : null;
  return (
    <div className="flex h-9 shrink-0 items-center gap-2 overflow-hidden whitespace-nowrap rounded-sm border border-line/50 bg-panel px-2 text-[11px]">
      <span className="shrink-0 text-sm font-bold tracking-wide text-accent">{sym}</span>
      <span className="min-w-0 max-w-[14rem] shrink truncate text-secondary" title={name ?? undefined}>{name ?? "—"}</span>
      <Num v={price} className="shrink-0 text-base font-semibold" />
      <Change pct={change} className="shrink-0" />
      <span className="h-4 w-px shrink-0 bg-line/50" />
      <Kv k="O"><Num v={a.open} /></Kv><Kv k="H"><Num v={a.high} /></Kv><Kv k="L"><Num v={a.low} /></Kv>
      <span className="hidden shrink-0 2xl:inline"><span className="text-muted">VOL </span><span className="font-mono tabular-nums">{fmtCompact(a.volume)}</span></span>
      <span className="shrink-0" title={`20D avg volume ${fmtCompact(a.volume_average_20)}`}><span className="text-muted">RVOL </span><Num v={a.relative_volume} suffix={isNum(a.relative_volume) ? "x" : ""} /></span>
      <span className="h-4 w-px shrink-0 bg-line/50" />
      <span className="flex shrink-0 items-center gap-1.5" title={pos === null ? "52W range N/A" : `52W ${fmt(lo)} – ${fmt(hi)} · ${pos.toFixed(0)}% of range`}>
        <span className="text-muted">52W</span>
        <span className="relative h-1.5 w-16 rounded-full bg-line/30">
          {pos !== null && <span className="absolute -top-0.5 h-2.5 w-0.5 bg-fg" style={{ left: `calc(${pos}% - 1px)` }} />}
        </span>
        <Num v={lo} d={0} className="hidden text-secondary 2xl:inline" /><span className="hidden text-muted 2xl:inline">–</span><Num v={hi} d={0} className="hidden text-secondary 2xl:inline" />
      </span>
      <Kv k="vs H"><Num v={a.distance_from_52w_high} d={1} signed suffix="%" /></Kv>
      <Kv k="vs L"><Num v={a.distance_from_52w_low} d={1} signed suffix="%" /></Kv>
      <span className="h-4 w-px shrink-0 bg-line/50" />
      {(["1d", "5d", "20d", "60d"] as const).map((w) => (
        <Kv key={w} k={w.toUpperCase()}><Num v={a[`return_${w}`]} d={1} signed suffix="%" /></Kv>
      ))}
    </div>
  );
}

/** Keep the three charts' visible bar ranges locked together (zoom/pan move all). */
function useSyncedCharts(n: number) {
  const charts = useRef<(IChartApi | null)[]>(Array(n).fill(null));
  const [gen, setGen] = useState(0);
  const reg = useMemo(() => Array.from({ length: n }, (_, i) => (c: IChartApi | null) => { charts.current[i] = c; setGen((g) => g + 1); }), [n]);
  useEffect(() => {
    const cs = charts.current.filter((c): c is IChartApi => c !== null);
    if (cs.length < 2) return;
    const unsubs = cs.map((src) => {
      const h = (r: LogicalRange | null) => { if (r) cs.forEach((c) => { if (c !== src) c.timeScale().setVisibleLogicalRange(r); }); };
      src.timeScale().subscribeVisibleLogicalRangeChange(h);
      return () => { try { src.timeScale().unsubscribeVisibleLogicalRangeChange(h); } catch { /* chart already removed */ } };
    });
    return () => unsubs.forEach((u) => u());
  }, [gen]);
  return reg;
}

export default function StockAnalysis() {
  const { data, loading, error, analyze } = useStockAnalysis();
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const [current, setCurrent] = useState<string | null>(null);
  const reg = useSyncedCharts(3);

  useEffect(() => {
    let alive = true;
    fetchJSON<SymbolItem[]>("/symbols").then((s) => { if (alive && Array.isArray(s)) setSymbols(s); }).catch(() => {});
    return () => { alive = false; };
  }, []);

  const run = (sym: string) => {
    setCurrent(sym);
    analyze(sym);
  };

  // only symbols that analyzed successfully become recent chips
  const okSym = data?.info.symbol;
  useEffect(() => {
    if (!okSym) return;
    setRecent((r) => { const n = [okSym, ...r.filter((x) => x !== okSym)].slice(0, 5); saveRecent(n); return n; });
  }, [okSym]);

  // indicators padded to the price chart's bars so the synced logical ranges line up
  const { candles, rsi, macd } = useMemo(() => {
    const raw = data?.chart.candles ?? [];
    const candles: Candle[] = raw
      .filter((c) => isNum(c.open) && isNum(c.high) && isNum(c.low) && isNum(c.close))
      .map((c) => ({ t: c.time, o: c.open as number, h: c.high as number, l: c.low as number, c: c.close as number, v: c.volume as number }));
    const rsiBy = new Map((data?.chart.rsi ?? []).map((p) => [p.time, p.value]));
    const macdBy = new Map((data?.chart.macd ?? []).map((p) => [p.time, p]));
    return {
      candles,
      rsi: candles.map((c) => ({ time: c.t, value: rsiBy.get(c.t) ?? null })),
      macd: candles.map((c) => ({ ...macdBy.get(c.t), time: c.t })),
    };
  }, [data]);

  const a = data?.analysis ?? {};
  const info = data?.info;
  const support = (data?.levels.support ?? []).filter(isNum);
  const resistance = (data?.levels.resistance ?? []).filter(isNum);
  const price = info?.price ?? a.price;
  const structure = [flag(a.higher_high, "HH"), flag(a.higher_low, "HL"), flag(a.lower_high, "LH"), flag(a.lower_low, "LL")].filter(Boolean).join(" · ");
  const sym = info?.symbol ?? current ?? "—";
  const factors = data?.research_factors ?? [];

  const prompt = loading
    ? <span className="text-accent">Analyzing {current}… (up to ~40s)</span>
    : error ? <span className="text-negative">{error}</span>
      : !data ? "Search a symbol to analyze it" : "No chart data";

  return (
    <div className="flex flex-col gap-1.5 lg:h-full lg:min-h-[34rem]">
      <div className="flex shrink-0 items-center gap-2">
        <SymbolSearch onSelect={run} symbols={symbols} />
        {recent.map((s) => (
          <button key={s} onClick={() => run(s)} className="shrink-0 rounded-sm border border-line/50 bg-panel px-2 py-0.5 font-mono text-[11px] text-secondary hover:border-accent/60 hover:text-accent focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">{s}</button>
        ))}
        <div className="ml-auto min-w-0 truncate text-[11px]" role="status" aria-busy={loading}>
          {loading ? <span className="text-accent">Analyzing {current}… (up to ~40s)</span>
            : error ? <span className="text-negative" title={error}>{error}</span>
              : typeof a.source === "string" && <span className="text-muted">{a.source}{typeof a.timestamp === "string" && ` · ${a.timestamp.slice(0, 10)}`}</span>}
        </div>
      </div>

      <QuoteStrip sym={sym} name={info?.name} price={price} change={info?.change} a={a} />

      <div className={`grid min-h-0 flex-1 grid-cols-1 gap-1.5 lg:grid-cols-[minmax(0,62fr)_minmax(0,38fr)] lg:grid-rows-[minmax(0,1fr)] ${loading && data ? "opacity-60" : ""}`}>
        {/* one frame, thin separators; 3:1:1 */}
        <div className="relative flex h-[40rem] min-h-0 flex-col gap-px overflow-hidden rounded-sm border border-line/50 bg-line/40 lg:h-auto">
          {loading && <div className="absolute inset-x-0 top-0 z-20 h-0.5 animate-pulse bg-accent" />}
          <CandlestickChart key={info?.symbol ?? "empty"} candles={candles} title={`${sym} · Daily`} empty={prompt}
            fill className="flex-[3] rounded-none! border-0!" onChart={reg[0]} />
          <IndicatorChart kind="rsi" title="RSI (14) · ref 30 / 70" data={rsi} fill className="flex-1 rounded-none! border-0!" onChart={reg[1]} />
          <IndicatorChart kind="macd" title="MACD" data={macd} fill className="flex-1 rounded-none! border-0!" onChart={reg[2]} />
        </div>

        <div className="grid h-[36rem] min-h-0 grid-cols-2 grid-rows-[minmax(0,1fr)_minmax(0,1.1fr)_minmax(0,1.25fr)] gap-1.5 lg:h-auto">
          <Panel title="Technical summary" fill bodyClass="overflow-auto p-0" className="col-span-2">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-panel text-[10px] uppercase text-muted">
                <tr className="h-5"><th className={`${th} text-left`}>Indicator</th><th className={`${th} text-right`}>Value</th><th className={`${th} text-right`}>State</th></tr>
              </thead>
              <tbody>
                <IndRow k="RSI (14)" v={<Num v={a.rsi_14} />} s={a.rsi_condition} />
                <IndRow k="MACD" v={<><Num v={a.macd} /> <span className="text-muted">sig</span> <Num v={a.macd_signal} /> <span className="text-muted">hist</span> <Num v={a.macd_histogram} signed /></>} s={a.macd_condition} />
                <IndRow k="VWAP 20D" v={<Num v={a.vwap_20d} />} s={a.vwap_condition} />
                <IndRow k="Volume" v={<><span className="font-mono tabular-nums">{fmtCompact(a.volume)}</span> <span className="text-muted">avg20</span> <span className="font-mono tabular-nums">{fmtCompact(a.volume_average_20)}</span></>} s={a.volume_condition} />
                <IndRow k="ROC (12)" v={<Num v={a.roc_12} signed suffix="%" />} />
                <IndRow k="ATR (14)" v={<Num v={a.atr_14} />} />
              </tbody>
            </table>
          </Panel>

          <Panel title="Momentum score" fill bodyClass="flex flex-col items-center justify-center overflow-auto p-1">
            <MomentumGauge score={data?.score.overall ?? null} label="Overall (0-100)" className="h-[90px] w-[90px]" />
            {data && (data.score.components.length === 0 || factors.length === 0) && (
              <div className="mt-0.5 text-center text-[10px] text-muted">
                {data.score.components.length === 0 && "Components N/A"}{data.score.components.length === 0 && factors.length === 0 && " · "}{factors.length === 0 && "Research factors N/A"}
              </div>
            )}
          </Panel>

          <Panel title="Levels · volatility · trend" fill bodyClass="overflow-auto px-2 py-1">
            <Row k="Support">{support.length ? <span className="font-mono tabular-nums">{support.map((n) => fmt(n)).join(", ")}</span> : <NotAvail />}</Row>
            <Row k="Resistance">{resistance.length ? <span className="font-mono tabular-nums">{resistance.map((n) => fmt(n)).join(", ")}</span> : <NotAvail />}</Row>
            <Row k="52W high"><Num v={a.high_52w} /></Row>
            <Row k="52W low"><Num v={a.low_52w} /></Row>
            <Row k="ATR"><Num v={data?.volatility.atr} /></Row>
            <Row k="ADX"><Num v={data?.volatility.adx} /></Row>
            <Row k="Trend"><Chip text={a.trend} /></Row>
            <Row k="Structure">{structure && <span className="mr-1 font-mono text-[10px] text-secondary">{structure}</span>}<Chip text={a.market_structure} /></Row>
          </Panel>

          <Panel title="Moving averages vs price" fill bodyClass="overflow-auto p-0" className="col-span-2">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-panel text-[10px] uppercase text-muted">
                <tr className="h-5"><th className={`${th} text-left`}>Average</th><th className={`${th} text-right`}>Value</th><th className={`${th} text-right`}>Price vs</th><th className={`${th} text-right`}>Side</th></tr>
              </thead>
              <tbody>
                {(["ema_9", "ema_20", "ema_50", "ema_200", "sma_20", "sma_50", "sma_200"] as const).map((m) => (
                  <MaRow key={m} k={m.replace("_", " ").toUpperCase()} ma={a[m]} price={price} />
                ))}
              </tbody>
            </table>
          </Panel>
        </div>
      </div>
    </div>
  );
}
