import { useState } from "react";
import BreadthBars from "../components/BreadthBars";
import DerivativesPanel from "../components/DerivativesPanel";
import FlowGauge from "../components/FlowGauge";
import IndicatorStrip from "../components/IndicatorStrip";
import { Chip, NoData, Num, Panel, Stat, btn } from "../components/ui";
import { useMarketData } from "../hooks/useMarketData";
import { isNum, label, signCls } from "../lib/format";
import type { MarketAnalysisData, Sector } from "../lib/types";

function RegimeSection({ r }: { r: MarketAnalysisData["regime"] }) {
  return (
    <Panel title="Regime analysis" right={r && <Chip text={r.market_regime} />}>
      {!r ? <NoData /> : (
        <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-6">
          <Stat k="NIFTY"><Num v={r.nifty_price} /></Stat>
          <Stat k="India VIX"><Num v={r.india_vix} /></Stat>
          <Stat k="VIX change"><Num v={r.vix_change_percent} signed suffix="%" /></Stat>
          <Stat k="VIX regime"><Chip text={r.vix_regime} /></Stat>
          <Stat k="VIX 1Y percentile">
            <div className="flex items-center gap-1.5">
              <Num v={r.vix_percentile_1y} d={1} />
              <div className="h-1.5 flex-1 rounded-full bg-line/30">
                {isNum(r.vix_percentile_1y) && <div className="h-1.5 rounded-full bg-warning/70" style={{ width: `${Math.min(100, Math.max(0, r.vix_percentile_1y))}%` }} />}
              </div>
            </div>
          </Stat>
          <Stat k="VIX direction"><span className="text-secondary">{label(r.vix_direction)}</span></Stat>
        </div>
      )}
    </Panel>
  );
}

type SortKey = "name" | "return_20d" | "relative_strength_20d" | "regime";
function SectorTable({ sectors }: { sectors: Sector[] | null }) {
  const [key, setKey] = useState<SortKey>("return_20d");
  const [asc, setAsc] = useState(false);
  if (!sectors || sectors.length === 0) return <Panel title="Sector performance"><NoData /></Panel>;
  const rows = [...sectors].sort((a, b) => {
    const x = a[key], y = b[key];
    if (typeof x === "string" && typeof y === "string") return asc ? x.localeCompare(y) : y.localeCompare(x);
    if (!isNum(x)) return 1; // non-numeric always last
    if (!isNum(y)) return -1;
    return asc ? x - y : y - x;
  });
  const max = Math.max(1, ...sectors.map((s) => s.return_20d).filter(isNum).map(Math.abs));
  const th = (k: SortKey, t: string, right = true) => (
    <th className={`px-1.5 py-0.5 font-normal ${right ? "text-right" : "text-left"}`}
      aria-sort={k === key ? (asc ? "ascending" : "descending") : "none"}>
      <button className={`${btn} border-transparent uppercase ${k === key ? "text-accent" : "text-muted hover:text-secondary"}`}
        onClick={() => { if (k === key) setAsc(!asc); else { setKey(k); setAsc(k === "name" || k === "regime"); } }}>
        {t}{k === key ? (asc ? " ▲" : " ▼") : ""}
      </button>
    </th>
  );
  return (
    <Panel title="Sector performance" bodyClass="p-0">
      <table className="w-full text-xs">
        <thead className="text-[10px] text-muted">
          <tr>{th("name", "Sector", false)}{th("return_20d", "20D return")}<th className="w-1/3 px-1.5 font-normal" aria-label="20D return bar" />{th("relative_strength_20d", "RS 20D")}{th("regime", "Regime", false)}</tr>
        </thead>
        <tbody>
          {rows.map((s) => (
            <tr key={s.name} className="border-t border-line/20 hover:bg-line/15">
              <td className="px-1.5 py-0.5">{s.name}</td>
              <td className="px-1.5 text-right"><Num v={s.return_20d} signed suffix="%" /></td>
              <td className="px-1.5">
                <div className="flex h-2">
                  <div className="flex w-1/2 justify-end border-r border-line/40">
                    {isNum(s.return_20d) && s.return_20d < 0 && <div className="bg-negative/80" style={{ width: `${(-s.return_20d / max) * 100}%` }} />}
                  </div>
                  <div className="flex w-1/2">
                    {isNum(s.return_20d) && s.return_20d > 0 && <div className="bg-positive/80" style={{ width: `${(s.return_20d / max) * 100}%` }} />}
                  </div>
                </div>
              </td>
              <td className={`px-1.5 text-right ${signCls(s.relative_strength_20d)}`}><Num v={s.relative_strength_20d} signed /></td>
              <td className="px-1.5"><Chip text={s.regime} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </Panel>
  );
}

function EventSection({ e }: { e: MarketAnalysisData["events"] }) {
  const evs = e?.upcoming_events ?? [];
  return (
    <Panel title="Event risk calendar"
      right={e && <><Chip text={e.status} /><span>Overall risk</span><Chip text={e.overall_risk} /></>} bodyClass="p-0">
      {!e ? <NoData /> : (
        <>
          {e.source_fresh === false && (
            <div className="border-b border-warning/30 bg-warning/5 px-2 py-1 text-[11px] text-warning">
              Calendar source stale{e.source_checked_at_utc ? ` (last checked ${e.source_checked_at_utc.slice(0, 10)})` : ""}; verify events independently.
            </div>
          )}
          {evs.length === 0 ? <NoData text="No upcoming events in source" /> : (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-[10px] uppercase text-muted">
                  <tr><th className="px-1.5 py-0.5 text-left font-normal">Date (UTC)</th><th className="px-1.5 text-left font-normal">Event</th><th className="px-1.5 text-left font-normal">Risk</th><th className="px-1.5 text-left font-normal">Note</th></tr>
                </thead>
                <tbody>
                  {evs.map((v, i) => (
                    <tr key={i} className="border-t border-line/20 align-top hover:bg-line/15">
                      <td className="whitespace-nowrap px-1.5 py-0.5 font-mono tabular-nums">{v.datetime_utc ? v.datetime_utc.slice(0, 16).replace("T", " ") : "N/A"}</td>
                      <td className="px-1.5">{v.name ?? "N/A"}</td>
                      <td className="px-1.5"><Chip text={v.risk_level ?? v.severity} /></td>
                      <td className="px-1.5 text-[11px] text-secondary">{v.impact_note ?? ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}

export default function MarketAnalysis() {
  const { data, loading, error } = useMarketData<MarketAnalysisData>("/market-analysis");

  if (loading && !data) {
    return (
      <div className="animate-pulse space-y-2" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => <div key={i} className="h-28 rounded-sm bg-panel" />)}
      </div>
    );
  }
  if (!data) return <div className="text-negative">Failed to load: {error ?? "No data"}</div>;

  return (
    <div className="space-y-2">
      {error && <div className="text-xs text-warning">Refresh failed ({error}); showing last data.</div>}
      <RegimeSection r={data.regime} />
      <IndicatorStrip ind={data.indicators} />
      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        <BreadthBars breadth={data.breadth} detail />
        <FlowGauge flows={data.flows} />
      </div>
      <SectorTable sectors={data.sectors} />
      {data.derivatives ? (
        <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
          <DerivativesPanel title="NIFTY" d={data.derivatives.nifty} />
          <DerivativesPanel title="BANK NIFTY" d={data.derivatives.bank_nifty} />
        </div>
      ) : <Panel title="Derivatives"><NoData /></Panel>}
      <EventSection e={data.events} />
    </div>
  );
}
