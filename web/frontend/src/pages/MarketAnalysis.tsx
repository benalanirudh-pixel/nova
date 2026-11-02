import { useState, type ReactNode } from "react";
import FlowGauge from "../components/FlowGauge";
import StatusBar from "../components/StatusBar";
import { useMarketData } from "../hooks/useMarketData";
import { fmt, isNum } from "../lib/format";
import type { DerivativesFull, FlowsFull, MarketAnalysisData, Sector, Streak } from "../lib/types";

const sign = (v: unknown) => (!isNum(v) ? "text-muted" : v >= 0 ? "text-positive" : "text-negative");
const label = (s: unknown) => (typeof s === "string" && s ? s.replaceAll("_", " ") : "N/A");

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded border border-line/50 bg-panel p-4">
      <h2 className="mb-3 text-sm text-accent">{title}</h2>
      {children}
    </section>
  );
}
const NoData = () => <div className="text-sm text-muted">No cache: run a refresh to load this section.</div>;

function Badge({ text, tone }: { text?: string; tone: string }) {
  return <span className={`rounded border px-2 py-0.5 text-xs ${tone}`}>{label(text)}</span>;
}
function regimeTone(r?: string) {
  const u = (r ?? "").toUpperCase();
  return u.includes("BULL") ? "border-positive text-positive" : u.includes("BEAR") ? "border-negative text-negative" : "border-warning text-warning";
}
function Stat({ k, v }: { k: string; v: ReactNode }) {
  return <div className="rounded border border-line/50 p-2"><div className="text-xs text-secondary">{k}</div><div className="text-sm">{v}</div></div>;
}

function RegimeSection({ r }: { r: MarketAnalysisData["regime"] }) {
  if (!r) return <NoData />;
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Badge text={r.market_regime} tone={regimeTone(r.market_regime)} />
      <Stat k="India VIX" v={fmt(r.india_vix)} />
      <Stat k="VIX regime" v={label(r.vix_regime)} />
      <Stat k="VIX 1Y percentile" v={fmt(r.vix_percentile_1y, 1)} />
      <Stat k="VIX direction" v={label(r.vix_direction)} />
    </div>
  );
}

function Pct({ label: l, v }: { label: string; v: unknown }) {
  return (
    <div className="mb-1 flex items-center gap-2 text-xs">
      <span className="w-28 text-secondary">{l}</span>
      <div className="h-3 flex-1 bg-line/20">{isNum(v) && <div className="h-3 bg-info" style={{ width: `${Math.min(100, Math.max(0, v))}%` }} />}</div>
      <span className="w-16 text-right">{isNum(v) ? `${fmt(v, 1)}%` : "N/A"}</span>
    </div>
  );
}
function BreadthSection({ b }: { b: MarketAnalysisData["breadth"] }) {
  if (!b) return <NoData />;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat k="Advancing" v={<span className="text-positive">{fmt(b.advancing, 0)}</span>} />
        <Stat k="Declining" v={<span className="text-negative">{fmt(b.declining, 0)}</span>} />
        <Stat k="Unchanged" v={fmt(b.unchanged, 0)} />
        <Stat k="A/D ratio" v={fmt(b.ad_ratio)} />
        <Stat k="52W highs" v={fmt(b.new_52w_highs, 0)} />
        <Stat k="52W lows" v={fmt(b.new_52w_lows, 0)} />
        <Stat k="McClellan summation" v={fmt(b.mcclellan_summation)} />
      </div>
      <div>
        <Pct label="Above EMA 20" v={b.above_ema20_percent} />
        <Pct label="Above EMA 50" v={b.above_ema50_percent} />
        <Pct label="Above EMA 200" v={b.above_ema200_percent} />
        <Pct label="Strong uptrend" v={b.strong_uptrend_percent} />
        <Pct label="Strong downtrend" v={b.strong_downtrend_percent} />
      </div>
    </div>
  );
}

type SortKey = "name" | "return_20d" | "relative_strength_20d" | "regime";
function SectorTable({ sectors }: { sectors: Sector[] | null }) {
  const [key, setKey] = useState<SortKey>("return_20d");
  const [asc, setAsc] = useState(false);
  if (!sectors || sectors.length === 0) return <NoData />;
  const rows = [...sectors].sort((a, b) => {
    const x = a[key], y = b[key];
    if (typeof x === "string" && typeof y === "string") return asc ? x.localeCompare(y) : y.localeCompare(x);
    if (!isNum(x)) return 1; // non-numeric always last
    if (!isNum(y)) return -1;
    return asc ? x - y : y - x;
  });
  const th = (k: SortKey, t: string, right = true) => (
    <th className={`cursor-pointer select-none p-1 ${right ? "text-right" : "text-left"}`} onClick={() => { if (k === key) setAsc(!asc); else { setKey(k); setAsc(k === "name" || k === "regime"); } }}>
      {t}{k === key ? (asc ? " ▲" : " ▼") : ""}
    </th>
  );
  return (
    <table className="w-full text-sm">
      <thead className="text-xs text-secondary"><tr>{th("name", "Sector", false)}{th("return_20d", "20D return")}{th("relative_strength_20d", "RS 20D")}{th("regime", "Regime", false)}</tr></thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.name} className="border-t border-line/30">
            <td className="p-1">{s.name}</td>
            <td className={`p-1 text-right ${sign(s.return_20d)}`}>{isNum(s.return_20d) ? `${fmt(s.return_20d)}%` : "N/A"}</td>
            <td className={`p-1 text-right ${sign(s.relative_strength_20d)}`}>{fmt(s.relative_strength_20d)}</td>
            <td className="p-1 pl-4">{label(s.regime)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const streak = (s?: Streak) => (Array.isArray(s) && s.length === 2 ? `${s[0]} for ${s[1]} session${s[1] === 1 ? "" : "s"}` : "N/A");
function FlowSection({ f }: { f: FlowsFull | null }) {
  if (!f || !f.available) return <NoData />;
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Badge text={f.flow_regime} tone="border-info text-info" />
        <span className="text-secondary">FII: {streak(f.fii_streak)}</span>
        <span className="text-secondary">DII: {streak(f.dii_streak)}</span>
        {f.latest_date && <span className="text-xs text-muted">as of {f.latest_date}</span>}
      </div>
      <FlowGauge flows={f} />
    </div>
  );
}

function DerivCard({ title, d }: { title: string; d?: DerivativesFull }) {
  const wall = (w?: { strike?: unknown; oi?: unknown }) => (w && isNum(w.strike) ? `${fmt(w.strike, 0)} (OI ${fmt(w.oi, 0)})` : "N/A");
  return (
    <div className="rounded border border-line/50 p-3">
      <div className="mb-2 text-sm">{title}{d?.expiry ? <span className="ml-2 text-xs text-muted">exp {d.expiry}</span> : null}</div>
      {!d || !d.available ? <div className="text-sm text-muted">Not available</div> : (
        <>
          <div className="grid grid-cols-2 gap-2">
            <Stat k="OI PCR" v={fmt(d.oi_pcr)} />
            <Stat k="Volume PCR" v={fmt(d.volume_pcr)} />
            <Stat k="Max pain" v={fmt(d.max_pain, 0)} />
            <Stat k="ATM IV" v={isNum(d.atm_iv) ? `${fmt(d.atm_iv)}%` : "N/A"} />
            <Stat k="Put wall" v={wall(d.put_wall)} />
            <Stat k="Call wall" v={wall(d.call_wall)} />
          </div>
          <div className="mb-1 mt-3 text-xs text-secondary">Unusual activity</div>
          {d.unusual_activity?.length ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead className="text-secondary"><tr><th className="p-1 text-left">Type</th><th className="p-1 text-right">Strike</th><th className="p-1 text-right">OI</th><th className="p-1 text-right">Chg OI</th><th className="p-1 text-right">Vol/OI</th><th className="p-1 text-left">Activity</th></tr></thead>
                <tbody>
                  {d.unusual_activity.map((u, i) => (
                    <tr key={i} className="border-t border-line/30">
                      <td className="p-1">{u.option_type ?? "N/A"}</td>
                      <td className="p-1 text-right">{fmt(u.strike, 0)}</td>
                      <td className="p-1 text-right">{fmt(u.oi, 0)}</td>
                      <td className={`p-1 text-right ${sign(u.change_oi)}`}>{fmt(u.change_oi, 0)}</td>
                      <td className="p-1 text-right">{fmt(u.volume_oi_ratio, 1)}</td>
                      <td className="p-1">{u.oi_activity ?? "N/A"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="text-xs text-muted">None reported</div>}
        </>
      )}
    </div>
  );
}

function EventSection({ e }: { e: MarketAnalysisData["events"] }) {
  if (!e) return <NoData />;
  const evs = e.upcoming_events ?? [];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <Badge text={e.status} tone="border-line text-secondary" />
        <span className="text-secondary">Overall risk: {label(e.overall_risk)}</span>
      </div>
      {e.source_fresh === false && (
        <div className="text-sm text-warning">Calendar source stale{e.source_checked_at_utc ? ` (last checked ${e.source_checked_at_utc.slice(0, 10)})` : ""}; verify events independently.</div>
      )}
      {evs.length === 0 ? <div className="text-sm text-muted">No upcoming events in source</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-xs text-secondary"><tr><th className="p-1 text-left">Date (UTC)</th><th className="p-1 text-left">Event</th><th className="p-1 text-left">Risk</th><th className="p-1 text-left">Note</th></tr></thead>
            <tbody>
              {evs.map((v, i) => (
                <tr key={i} className="border-t border-line/30 align-top">
                  <td className="whitespace-nowrap p-1">{v.datetime_utc ? v.datetime_utc.slice(0, 16).replace("T", " ") : "N/A"}</td>
                  <td className="p-1">{v.name ?? "N/A"}</td>
                  <td className="p-1">{label(v.risk_level ?? v.severity)}</td>
                  <td className="p-1 text-xs text-secondary">{v.impact_note ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function MarketAnalysis() {
  const { data, loading, error } = useMarketData<MarketAnalysisData>("/market-analysis");

  if (loading && !data) {
    return (
      <div className="animate-pulse space-y-4" aria-busy="true">
        {Array.from({ length: 6 }, (_, i) => <div key={i} className="h-32 rounded bg-panel" />)}
      </div>
    );
  }
  if (!data) return <div className="text-negative">Failed to load: {error ?? "No data"}</div>;

  return (
    <div className="space-y-4">
      {error && <div className="text-xs text-warning">Refresh failed ({error}); showing last data.</div>}
      <Section title="Regime Analysis"><RegimeSection r={data.regime} /></Section>
      <Section title="Breadth Deep-Dive"><BreadthSection b={data.breadth} /></Section>
      <Section title="Sector Performance"><SectorTable sectors={data.sectors} /></Section>
      <Section title="Institutional Flow"><FlowSection f={data.flows} /></Section>
      <Section title="Derivatives Intelligence">
        {data.derivatives ? (
          <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
            <DerivCard title="NIFTY" d={data.derivatives.nifty} />
            <DerivCard title="BANK NIFTY" d={data.derivatives.bank_nifty} />
          </div>
        ) : <NoData />}
      </Section>
      <Section title="Event Risk Calendar"><EventSection e={data.events} /></Section>
      <StatusBar freshness={data.freshness} />
    </div>
  );
}
