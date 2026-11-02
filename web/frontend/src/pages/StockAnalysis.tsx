import { useEffect, useMemo, useState, type ReactNode } from "react";
import CandlestickChart from "../components/CandlestickChart";
import IndicatorChart from "../components/IndicatorChart";
import MomentumGauge from "../components/MomentumGauge";
import SymbolSearch, { type SymbolItem } from "../components/SymbolSearch";
import { useStockAnalysis } from "../hooks/useStockAnalysis";
import { fetchJSON } from "../lib/api";
import { Change, Chip, Num, Panel, RangeBar } from "../components/ui";
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

function Row({ k, v }: { k: string; v: ReactNode }) {
  return <div className="flex justify-between gap-3 py-px text-xs"><span className="text-secondary">{k}</span><span className="text-right">{v}</span></div>;
}
const NotAvail = () => <span className="text-muted">N/A</span>;

/** Price vs moving average: value, % gap (from API numbers), above/below marker. */
function MaRow({ k, ma, price }: { k: string; ma: unknown; price: unknown }) {
  const gap = isNum(ma) && isNum(price) && ma !== 0 ? ((price - ma) / ma) * 100 : null;
  return (
    <tr className="border-t border-line/20 hover:bg-line/15">
      <td className="px-1.5 py-0.5 text-secondary">{k}</td>
      <td className="px-1.5 text-right"><Num v={ma} /></td>
      <td className="px-1.5 text-right"><Num v={gap} signed suffix="%" /></td>
      <td className="px-1.5 text-right">{gap === null ? <NotAvail /> : <Chip text={gap >= 0 ? "ABOVE" : "BELOW"} />}</td>
    </tr>
  );
}
function IndRow({ k, v, s }: { k: string; v: ReactNode; s?: unknown }) {
  return (
    <tr className="border-t border-line/20 hover:bg-line/15">
      <td className="px-1.5 py-0.5 text-secondary">{k}</td>
      <td colSpan={2} className="px-1.5 text-right">{v}</td>
      <td className="px-1.5 text-right">{s !== undefined && <Chip text={s} />}</td>
    </tr>
  );
}
const flag = (v: unknown, t: string) => (v === true ? t : null);

export default function StockAnalysis() {
  const { data, loading, error, analyze } = useStockAnalysis();
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [recent, setRecent] = useState<string[]>(loadRecent);
  const [current, setCurrent] = useState<string | null>(null);

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

  const candles: Candle[] = useMemo(
    () => (data?.chart.candles ?? []).map((c) => ({ t: c.time, o: c.open as number, h: c.high as number, l: c.low as number, c: c.close as number, v: c.volume as number })),
    [data],
  );
  const a = data?.analysis ?? {};
  const info = data?.info;
  const support = (data?.levels.support ?? []).filter(isNum);
  const resistance = (data?.levels.resistance ?? []).filter(isNum);
  const comps = data?.score.components ?? [];
  const factors = data?.research_factors ?? [];
  const risk = data?.risk;
  const price = info?.price ?? a.price;
  const structure = [flag(a.higher_high, "HH"), flag(a.higher_low, "HL"), flag(a.lower_high, "LH"), flag(a.lower_low, "LL")].filter(Boolean).join(" · ");

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <SymbolSearch onSelect={run} symbols={symbols} />
        {recent.map((s) => (
          <button key={s} onClick={() => run(s)} className="rounded-sm border border-line/50 bg-panel px-2 py-0.5 font-mono text-[11px] text-secondary hover:border-accent/60 hover:text-accent focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">{s}</button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-xs text-accent" role="status" aria-busy="true">
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          Analyzing {current}... this can take up to 20 seconds.
        </div>
      )}
      {error && <div className="text-xs text-negative">{error}</div>}
      {!data && !loading && !error && <div className="text-xs text-muted">Search a symbol to analyze it.</div>}

      {data && (
        <div className={`space-y-2 ${loading ? "opacity-50" : ""}`}>
          <Panel title={<>{info?.symbol ?? current}{typeof a.exchange === "string" && <span className="ml-1 text-muted">· {a.exchange}</span>}</>}
            right={<>{typeof a.source === "string" && <span>{a.source}</span>}{typeof a.timestamp === "string" && <span className="font-mono">{a.timestamp.slice(0, 10)}</span>}</>}>
            <div className="grid grid-cols-1 gap-x-4 gap-y-2 lg:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]">
              <div>
                <div className="truncate text-xs text-secondary">{info?.name ?? "N/A"}{info?.sector && <span className="text-muted"> · {info.sector}</span>}</div>
                <div className="flex items-baseline gap-2">
                  <Num v={price} className="text-2xl font-semibold" />
                  <Change pct={info?.change} className="text-sm" />
                </div>
              </div>
              <div className="space-y-1">
                <div className="flex flex-wrap gap-x-3 text-[11px]">
                  {([["O", a.open], ["H", a.high], ["L", a.low]] as const).map(([k, v]) => (
                    <span key={k}><span className="text-muted">{k} </span><Num v={v} className="text-secondary" /></span>
                  ))}
                  <span><span className="text-muted">VOL </span><span className="font-mono tabular-nums text-secondary">{fmtCompact(a.volume)}</span></span>
                  <span title={`20D avg volume ${fmtCompact(a.volume_average_20)}`}><span className="text-muted">RVOL </span><Num v={a.relative_volume} suffix={isNum(a.relative_volume) ? "x" : ""} className="text-secondary" /></span>
                </div>
                <RangeBar low={a.low} high={a.high} value={price} lowLabel="Day L" highLabel="H" />
              </div>
              <div className="space-y-1">
                <RangeBar low={a.low_52w} high={a.high_52w} value={price} lowLabel="52W L" highLabel="H" />
                <div className="flex flex-wrap gap-x-3 text-[11px]">
                  <span><span className="text-muted">From 52W H </span><Num v={a.distance_from_52w_high} signed suffix="%" /></span>
                  <span><span className="text-muted">From 52W L </span><Num v={a.distance_from_52w_low} signed suffix="%" /></span>
                </div>
              </div>
            </div>
            <div className="mt-2 grid grid-cols-4 gap-1 text-[11px]">
              {(["1d", "5d", "20d", "60d"] as const).map((w) => (
                <div key={w} className="flex justify-between border border-line/30 bg-deep/40 px-1.5 py-0.5">
                  <span className="uppercase text-muted">{w}</span><Num v={a[`return_${w}`]} signed suffix="%" />
                </div>
              ))}
            </div>
          </Panel>

          <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,62fr)_minmax(0,38fr)]">
            <div className="min-w-0 space-y-2">
              <CandlestickChart key={info?.symbol} candles={candles} title={`${info?.symbol ?? current} · Daily`} />
              <IndicatorChart kind="rsi" title="RSI (14) · ref 30 / 70" data={data.chart.rsi} />
              <IndicatorChart kind="macd" title="MACD" data={data.chart.macd} />
            </div>

            <div className="min-w-0 space-y-2">
              <Panel title="Technical summary" bodyClass="p-0">
                <table className="w-full text-xs">
                  <thead className="text-[10px] uppercase text-muted">
                    <tr><th className="px-1.5 py-0.5 text-left font-normal">Indicator</th><th colSpan={2} className="px-1.5 text-right font-normal">Value</th><th className="px-1.5 text-right font-normal">State</th></tr>
                  </thead>
                  <tbody>
                    <IndRow k="RSI (14)" v={<Num v={a.rsi_14} />} s={a.rsi_condition} />
                    <IndRow k="MACD" v={<span className="text-[11px]"><Num v={a.macd} /> <span className="text-muted">sig</span> <Num v={a.macd_signal} /> <span className="text-muted">hist</span> <Num v={a.macd_histogram} signed /></span>} s={a.macd_condition} />
                    <IndRow k="VWAP 20D" v={<Num v={a.vwap_20d} />} s={a.vwap_condition} />
                    <IndRow k="Volume" v={<span><span className="font-mono tabular-nums">{fmtCompact(a.volume)}</span> <span className="text-muted">avg</span> <span className="font-mono tabular-nums">{fmtCompact(a.volume_average_20)}</span></span>} s={a.volume_condition} />
                    <IndRow k="Trend" v="" s={a.trend} />
                    <IndRow k="Structure" v={structure ? <span className="font-mono text-secondary">{structure}</span> : <NotAvail />} s={a.market_structure} />
                    <IndRow k="ROC (12)" v={<Num v={a.roc_12} signed suffix="%" />} />
                    <IndRow k="ATR (14)" v={<Num v={a.atr_14} />} />
                  </tbody>
                  <thead className="text-[10px] uppercase text-muted">
                    <tr className="border-t border-line/40"><th className="px-1.5 py-0.5 text-left font-normal">Average</th><th className="px-1.5 text-right font-normal">Value</th><th className="px-1.5 text-right font-normal">Price vs</th><th className="px-1.5 text-right font-normal">Side</th></tr>
                  </thead>
                  <tbody>
                    {(["ema_9", "ema_20", "ema_50", "ema_200", "sma_20", "sma_50", "sma_200"] as const).map((m) => (
                      <MaRow key={m} k={m.replace("_", " ").toUpperCase()} ma={a[m]} price={price} />
                    ))}
                  </tbody>
                </table>
              </Panel>
              <Panel title="Momentum score">
                <MomentumGauge score={data.score.overall} label="Overall (0-100)" />
                {comps.length === 0 && <Row k="Components" v={<NotAvail />} />}
              </Panel>
              <Panel title="Key levels · volatility">
                <Row k="Support (52W low)" v={support.length ? <span className="font-mono tabular-nums">{support.map((n) => fmt(n)).join(", ")}</span> : <NotAvail />} />
                <Row k="Resistance (52W high)" v={resistance.length ? <span className="font-mono tabular-nums">{resistance.map((n) => fmt(n)).join(", ")}</span> : <NotAvail />} />
                <Row k="ATR" v={<Num v={data.volatility.atr} />} />
                <Row k="ADX" v={<Num v={data.volatility.adx} />} />
              </Panel>
              <Panel title="Research factors">
                {factors.length === 0 ? <NotAvail /> : factors.map((f, i) => <div key={i} className="text-xs">{typeof f === "string" ? f : JSON.stringify(f)}</div>)}
              </Panel>
              <Panel title="Risk context">
                <Row k="Position size" v={<Num v={risk?.position_size} />} />
                <Row k="Stop loss" v={<Num v={risk?.stop_loss} />} />
              </Panel>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
