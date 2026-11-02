import BreadthBars from "../components/BreadthBars";
import CandlestickChart from "../components/CandlestickChart";
import DerivativesPanel from "../components/DerivativesPanel";
import FlowGauge from "../components/FlowGauge";
import IndicatorStrip from "../components/IndicatorStrip";
import SectorHeatmap from "../components/SectorHeatmap";
import { Change, Chip, Num, Panel, RangeBar, Sparkline } from "../components/ui";
import { useMarketData } from "../hooks/useMarketData";
import { isNum, label } from "../lib/format";
import type { MarketOverviewData, Quote } from "../lib/types";

function Returns({ q }: { q?: Quote }) {
  return (
    <div className="grid grid-cols-3 gap-1 text-[11px]">
      {(["5d", "20d", "60d"] as const).map((w) => (
        <div key={w} className="flex justify-between border border-line/30 bg-deep/40 px-1.5 py-0.5">
          <span className="uppercase text-muted">{w}</span><Num v={q?.[`return_${w}`]} signed suffix="%" />
        </div>
      ))}
    </div>
  );
}

function Ohlc({ items }: { items: [string, unknown][] }) {
  return (
    <div className="flex flex-wrap gap-x-3 text-[11px]">
      {items.map(([k, v]) => <span key={k}><span className="text-muted">{k} </span><Num v={v} className="text-secondary" /></span>)}
    </div>
  );
}

function IndexCard({ q, fallback }: { q?: Quote; fallback: string }) {
  const closes = (q?.series ?? []).map((p) => p.close);
  return (
    <Panel title={q?.name ?? fallback} right={q?.source_label && <span className="truncate" title={q.source_label}>{q.source_label}</span>}>
      <div className="space-y-1.5">
        <div className="flex items-end justify-between gap-2">
          <div>
            <Num v={q?.price} className="text-2xl font-semibold leading-none" />
            <div className="mt-1 text-xs"><Change abs={q?.change_abs} pct={q?.change_percent} /></div>
          </div>
          <Sparkline values={closes} className="h-10 w-28" title={`Last ${closes.filter(isNum).length} closes`} />
        </div>
        <Ohlc items={[["O", q?.open], ["H", q?.high], ["L", q?.low], ["PC", q?.prev_close]]} />
        <RangeBar low={q?.low} high={q?.high} value={q?.price} lowLabel="Day L" highLabel="H" />
        <Returns q={q} />
      </div>
    </Panel>
  );
}

function VixCard({ q, pctile }: { q?: Quote; pctile: unknown }) {
  const dir = q?.direction;
  return (
    <Panel title={q?.name ?? "INDIA VIX"} right={<Chip text={q?.regime} />}>
      <div className="space-y-1.5">
        <div className="flex items-end justify-between gap-2">
          <div>
            <Num v={q?.value} className="text-2xl font-semibold leading-none" />
            <div className="mt-1 text-xs"><Change abs={q?.change_abs} pct={q?.change_percent} /></div>
          </div>
          <div className="text-right text-[11px]">
            <div className="text-muted">Direction</div>
            {/* rising VIX = rising fear, so tone is inverted on purpose */}
            <div className={/RIS/.test(dir ?? "") ? "text-negative" : /FALL|DECL/.test(dir ?? "") ? "text-positive" : "text-secondary"}>
              {/RIS/.test(dir ?? "") ? "▲ " : /FALL|DECL/.test(dir ?? "") ? "▼ " : ""}{label(dir)}
            </div>
          </div>
        </div>
        <Ohlc items={[["O", q?.open], ["H", q?.high], ["L", q?.low]]} />
        <div className="flex items-center gap-2 text-[11px]">
          <span className="w-16 text-muted">1Y pctile</span>
          <div className="relative h-1.5 flex-1 rounded-full bg-line/30">
            {isNum(pctile) && <div className="absolute inset-y-0 left-0 rounded-full bg-warning/70" style={{ width: `${Math.min(100, Math.max(0, pctile))}%` }} />}
          </div>
          <Num v={pctile} d={1} className="w-10 text-right" />
        </div>
        <Returns q={q} />
      </div>
    </Panel>
  );
}

export default function MarketOverview() {
  const { data, loading, error } = useMarketData<MarketOverviewData>("/market-overview");

  if (loading && !data) {
    return (
      <div className="animate-pulse space-y-2" aria-busy="true">
        <div className="grid grid-cols-3 gap-2">{Array.from({ length: 3 }, (_, i) => <div key={i} className="h-40 rounded-sm bg-panel" />)}</div>
        <div className="h-96 rounded-sm bg-panel" />
      </div>
    );
  }
  if (!data) return <div className="text-negative">Failed to load: {error ?? "No data"}</div>;

  const { kpis } = data;
  const candles = data.chart?.candles ?? [];

  return (
    <div className="space-y-2">
      {error && <div className="text-xs text-warning">Refresh failed ({error}); showing last data.</div>}
      {!kpis && <div className="text-xs text-warning">No cache: run a refresh to load market data.</div>}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <IndexCard q={kpis?.nifty} fallback="NIFTY 50" />
        <IndexCard q={kpis?.banknifty} fallback="BANK NIFTY" />
        <VixCard q={kpis?.vix} pctile={kpis?.macro?.vix_percentile_1y} />
      </div>
      <IndicatorStrip ind={kpis?.indicators} />
      <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <CandlestickChart candles={candles} title="NIFTY 50 · Daily" right={<Chip text={kpis?.macro?.market_regime} />} />
        <div className="space-y-2">
          <BreadthBars breadth={data.breadth} />
          <FlowGauge flows={data.flows} />
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        <DerivativesPanel title={data.derivatives?.instrument ?? "NIFTY"} d={data.derivatives} />
        <SectorHeatmap sectors={data.sectors} />
      </div>
    </div>
  );
}
