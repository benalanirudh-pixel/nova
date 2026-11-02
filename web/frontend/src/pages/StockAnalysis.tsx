import { useEffect, useMemo, useState, type ReactNode } from "react";
import CandlestickChart from "../components/CandlestickChart";
import IndicatorChart from "../components/IndicatorChart";
import MomentumGauge from "../components/MomentumGauge";
import SymbolSearch, { type SymbolItem } from "../components/SymbolSearch";
import { useStockAnalysis } from "../hooks/useStockAnalysis";
import { fetchJSON } from "../lib/api";
import { fmt, isNum } from "../lib/format";
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

const label = (v: unknown) => (typeof v === "string" && v ? v.replaceAll("_", " ") : "N/A");

function Card({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded border border-line/50 bg-panel p-3">
      <div className="mb-2 text-xs font-semibold uppercase text-secondary">{title}</div>
      <div className="space-y-1 text-sm">{children}</div>
    </div>
  );
}
function Row({ k, v }: { k: string; v: ReactNode }) {
  return <div className="flex justify-between gap-3"><span className="text-secondary">{k}</span><span>{v}</span></div>;
}
const NotAvail = () => <span className="text-muted">Not available</span>;

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
  const change = info?.change;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <SymbolSearch onSelect={run} symbols={symbols} />
        {recent.map((s) => (
          <button key={s} onClick={() => run(s)} className="rounded border border-line/50 bg-panel px-2 py-1 text-xs text-secondary hover:text-accent">{s}</button>
        ))}
      </div>

      {loading && (
        <div className="flex items-center gap-2 text-sm text-accent" role="status" aria-busy="true">
          <span className="inline-block h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          Analyzing {current}... this can take up to 20 seconds.
        </div>
      )}
      {error && <div className="text-negative">{error}</div>}
      {!data && !loading && !error && <div className="text-muted">Search a symbol to analyze it.</div>}

      {data && (
        <div className={`grid grid-cols-1 gap-3 lg:grid-cols-[60fr_40fr] ${loading ? "opacity-50" : ""}`}>
          <div className="min-w-0 space-y-3">
            <div className="flex flex-wrap items-baseline gap-3">
              <h1 className="text-xl text-accent">{info?.symbol ?? current}</h1>
              <span className="text-secondary">{info?.name ?? "N/A"}</span>
              <span className="text-lg font-semibold">{fmt(info?.price)}</span>
              {isNum(change) && (
                <span className={change >= 0 ? "text-positive" : "text-negative"}>
                  {change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(2)}%
                </span>
              )}
            </div>
            <div className="rounded border border-line/50 bg-panel p-2">
              <div className="mb-1 text-xs text-secondary">Daily, EMA 20</div>
              <div className="h-96"><CandlestickChart candles={candles} /></div>
            </div>
            <IndicatorChart kind="rsi" title="RSI (14), reference 30 / 70" data={data.chart.rsi} />
            <IndicatorChart kind="macd" title="MACD" data={data.chart.macd} />
          </div>

          <div className="min-w-0 space-y-3">
            <Card title="Momentum score">
              <MomentumGauge score={data.score.overall} label="Overall (0-100)" />
              {comps.length === 0 && <Row k="Components" v={<NotAvail />} />}
            </Card>
            <Card title="Trend and indicators">
              <Row k="Trend" v={label(a.trend)} />
              <Row k="Market structure" v={label(a.market_structure)} />
              <Row k="MACD condition" v={label(a.macd_condition)} />
              <Row k="RSI (14)" v={`${fmt(a.rsi_14)}${typeof a.rsi_condition === "string" ? ` (${label(a.rsi_condition)})` : ""}`} />
              <Row k="EMA 50" v={fmt(a.ema_50)} />
              <Row k="EMA 200" v={fmt(a.ema_200)} />
              <Row k="Sector" v={info?.sector ? info.sector : <NotAvail />} />
            </Card>
            <Card title="Key levels">
              <Row k="52W low (support)" v={support.length ? support.map((n) => fmt(n)).join(", ") : <NotAvail />} />
              <Row k="52W high (resistance)" v={resistance.length ? resistance.map((n) => fmt(n)).join(", ") : <NotAvail />} />
            </Card>
            <Card title="Volatility">
              <Row k="ATR" v={isNum(data.volatility.atr) ? fmt(data.volatility.atr) : <NotAvail />} />
              <Row k="ADX" v={isNum(data.volatility.adx) ? fmt(data.volatility.adx) : <NotAvail />} />
            </Card>
            <Card title="Research factors">
              {factors.length === 0 ? <NotAvail /> : factors.map((f, i) => <div key={i}>{typeof f === "string" ? f : JSON.stringify(f)}</div>)}
            </Card>
            <Card title="Risk context">
              <Row k="Position size" v={isNum(risk?.position_size) ? fmt(risk.position_size) : <NotAvail />} />
              <Row k="Stop loss" v={isNum(risk?.stop_loss) ? fmt(risk.stop_loss) : <NotAvail />} />
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
