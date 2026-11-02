import BreadthBars from "../components/BreadthBars";
import CandlestickChart from "../components/CandlestickChart";
import DerivativesStrip from "../components/DerivativesStrip";
import FlowGauge from "../components/FlowGauge";
import KPICard from "../components/KPICard";
import SectorHeatmap from "../components/SectorHeatmap";
import StatusBar from "../components/StatusBar";
import { useMarketData } from "../hooks/useMarketData";
import { fmt, isNum } from "../lib/format";
import type { MarketOverviewData } from "../lib/types";

const pct = (v: unknown) => (isNum(v) ? v : null);

export default function MarketOverview() {
  const { data, loading, error } = useMarketData<MarketOverviewData>("/market-overview");

  if (loading && !data) {
    return (
      <div className="animate-pulse space-y-4" aria-busy="true">
        <div className="flex gap-3">{Array.from({ length: 7 }, (_, i) => <div key={i} className="h-20 flex-1 rounded bg-panel" />)}</div>
        <div className="h-96 rounded bg-panel" />
      </div>
    );
  }
  if (!data) return <div className="text-negative">Failed to load: {error ?? "No data"}</div>;

  const { kpis, breadth, derivatives } = data;
  const candles = data.chart?.candles ?? [];
  const regime = kpis?.macro?.market_regime;

  return (
    <div className="space-y-4">
      {error && <div className="text-xs text-warning">Refresh failed ({error}); showing last data.</div>}
      {!kpis && <div className="text-sm text-warning">No cache: run a refresh to load market data.</div>}
      <div className="flex flex-wrap gap-3">
        <KPICard title="NIFTY 50" value={fmt(kpis?.nifty?.price)} change={pct(kpis?.nifty?.change_percent)} />
        <KPICard title="BANK NIFTY" value={fmt(kpis?.banknifty?.price)} change={pct(kpis?.banknifty?.change_percent)} />
        <KPICard title="INDIA VIX" value={fmt(kpis?.vix?.value)} change={pct(kpis?.vix?.change_percent)} />
        <KPICard title="A/D ratio" value={fmt(breadth?.ad_ratio)} />
        <KPICard title="PCR (OI)" value={fmt(derivatives?.oi_pcr)} />
        <KPICard title="Max Pain" value={fmt(derivatives?.max_pain, 0)} />
        <KPICard title="Regime" value={typeof regime === "string" && regime ? regime.replaceAll("_", " ") : "N/A"} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[50fr_26fr_24fr]">
        <div className="rounded border border-line/50 bg-panel p-2">
          <div className="mb-1 text-xs text-secondary">NIFTY 50 daily, EMA 20</div>
          <CandlestickChart candles={candles} />
        </div>
        <div className="space-y-3">
          <BreadthBars breadth={breadth} />
          <FlowGauge flows={data.flows} />
        </div>
        <SectorHeatmap sectors={data.sectors} />
      </div>
      <DerivativesStrip d={derivatives} />
      <StatusBar freshness={data.freshness} />
    </div>
  );
}
