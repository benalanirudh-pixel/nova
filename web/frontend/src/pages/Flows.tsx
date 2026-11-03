import { useMemo, useState } from "react";
import { Body, Chip, Num, Panel, Stat, btn } from "../components/ui";
import { useMarketData } from "../hooks/useMarketData";
import { fmt, isNum, label } from "../lib/format";
import type { Flows } from "../lib/types";

interface FlowRow {
  date: string; fii_buy: number | null; fii_sell: number | null; fii_net: number | null;
  dii_buy: number | null; dii_sell: number | null; dii_net: number | null; combined_net: number | null;
  market_scope: string | null; source: string | null; provisional: boolean | null;
}
interface FlowHistory { rows: FlowRow[]; target_scope: string; summary: (Flows & Record<string, unknown>) | null; unit: string }

const SCOPE_LABEL: Record<string, string> = {
  NSE_BSE_MSEI_COMBINED: "Combined NSE + BSE + MSEI",
  NSE_ONLY: "NSE only",
};
const scopeName = (s: string) => SCOPE_LABEL[s] ?? label(s);

type View = "Daily" | "Weekly" | "Monthly";
interface Bucket { key: string; fii: number | null; dii: number | null; combined: number | null; days: number; provisional: boolean; rows: FlowRow[] }

const sum = (xs: (number | null)[]) => (xs.some(isNum) ? xs.filter(isNum).reduce((a, b) => a + b, 0) : null);

function weekKey(d: string) {
  const t = new Date(`${d}T00:00:00Z`);
  t.setUTCDate(t.getUTCDate() - ((t.getUTCDay() + 6) % 7)); // Monday
  return `wk ${t.toISOString().slice(0, 10)}`;
}

/** One scope at a time: rows from different market scopes are never summed together. */
function bucket(rows: FlowRow[], view: View): Bucket[] {
  const keyOf = view === "Daily" ? (d: string) => d : view === "Weekly" ? weekKey : (d: string) => d.slice(0, 7);
  const m = new Map<string, FlowRow[]>();
  for (const r of rows) m.set(keyOf(r.date), [...(m.get(keyOf(r.date)) ?? []), r]);
  return [...m.entries()].map(([key, rs]) => ({
    key, rows: rs, days: rs.length, provisional: rs.some((r) => r.provisional),
    fii: sum(rs.map((r) => r.fii_net)), dii: sum(rs.map((r) => r.dii_net)), combined: sum(rs.map((r) => r.combined_net)),
  }));
}

function FlowBars({ data }: { data: Bucket[] }) {
  const W = 760, H = 220, T = 12, B = 22, L = 52;
  const vals = data.flatMap((d) => [d.fii, d.dii]).filter(isNum);
  if (!vals.length) return <div className="p-2 text-[12px] text-muted">No rows for this scope.</div>;
  const max = Math.max(...vals.map(Math.abs)) || 1;
  const y = (v: number) => T + ((max - v) / (2 * max)) * (H - T - B);
  const step = (W - L) / data.length, bw = Math.max(2, Math.min(14, step / 2 - 2));
  const every = Math.ceil(data.length / 8);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-56 w-full" role="img" aria-label="FII and DII net flow per period">
      {[max, max / 2, 0, -max / 2, -max].map((v) => (
        <g key={v}>
          <line x1={L} x2={W} y1={y(v)} y2={y(v)} className={v === 0 ? "stroke-line" : "stroke-line/25"} />
          <text x={L - 6} y={y(v) + 3} textAnchor="end" className="fill-muted font-mono text-[10px]">{fmt(v, 0)}</text>
        </g>
      ))}
      {data.map((d, i) => {
        const x = L + i * step + step / 2;
        const bar = (v: number | null, dx: number, cls: string) => isNum(v) &&
          <rect x={x + dx} width={bw} y={Math.min(y(v), y(0))} height={Math.max(1, Math.abs(y(v) - y(0)))} className={cls} />;
        return (
          <g key={d.key}>
            <title>{`${d.key}${d.provisional ? " (provisional)" : ""}\nFII ${fmt(d.fii)} · DII ${fmt(d.dii)} · Combined ${fmt(d.combined)} (₹ cr, ${d.days} session${d.days > 1 ? "s" : ""})`}</title>
            <rect x={x - step / 2} y={T} width={step} height={H - T - B} className="fill-transparent hover:fill-raised/60" />
            {bar(d.fii, -bw - 1, isNum(d.fii) && d.fii < 0 ? "fill-negative" : "fill-positive")}
            {bar(d.dii, 1, isNum(d.dii) && d.dii < 0 ? "fill-negative/50" : "fill-positive/50")}
            {i % every === 0 && <text x={x} y={H - 6} textAnchor="middle" className="fill-muted font-mono text-[10px]">{d.key.replace("wk ", "").slice(5)}</text>}
          </g>
        );
      })}
    </svg>
  );
}

export default function FlowsPage() {
  const { data, loading, error } = useMarketData<FlowHistory>("/flows/history");
  const [scope, setScope] = useState<string | null>(null);
  const [view, setView] = useState<View>("Daily");
  const [desc, setDesc] = useState(true);

  const scopes = useMemo(() => {
    const c = new Map<string, number>();
    for (const r of data?.rows ?? []) c.set(r.market_scope ?? "UNKNOWN", (c.get(r.market_scope ?? "UNKNOWN") ?? 0) + 1);
    return c;
  }, [data]);
  const active = scope ?? data?.target_scope ?? "";
  const rows = useMemo(() => (data?.rows ?? []).filter((r) => (r.market_scope ?? "UNKNOWN") === active), [data, active]);
  const buckets = useMemo(() => bucket(rows, view), [rows, view]);
  const cumulative = useMemo(() => {
    let f = 0, d = 0;
    return new Map(buckets.map((b) => [b.key, { fii: (f += b.fii ?? 0), dii: (d += b.dii ?? 0) }]));
  }, [buckets]);
  const s = data?.summary;
  const last = rows[rows.length - 1];
  const tab = (on: boolean) => `${btn} ${on ? "border-accent/70 text-accent" : "border-line/50 text-muted hover:text-secondary"}`;

  return (
    <div className="mx-auto max-w-[1800px] space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        <span className="text-muted">Scope</span>
        {[...scopes.entries()].map(([k, n]) => (
          <button key={k} className={tab(k === active)} onClick={() => setScope(k)} aria-pressed={k === active}
            title={k === data?.target_scope ? "The engine's target scope" : "Kept separate; never mixed with the target scope"}>
            {scopeName(k)} · {n}{k === data?.target_scope ? "" : " (separate)"}
          </button>
        ))}
        <span className="mx-1 h-3.5 w-px bg-line/40" />
        {(["Daily", "Weekly", "Monthly"] as View[]).map((v) => <button key={v} className={tab(v === view)} onClick={() => setView(v)} aria-pressed={v === view}>{v}</button>)}
        <span className="ml-auto text-muted">{rows.length ? `${rows[0].date} to ${last.date} · ${rows.length} sessions · ₹ crore` : ""}</span>
      </div>

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
        <Panel title="Institutional activity" right={s && <Chip text={s.flow_regime} />}>
          <Body loading={loading && !data} error={error}>
            <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
              <Stat k={`FII net ${last?.date ?? ""}`}><Num v={last?.fii_net} signed /></Stat>
              <Stat k="DII net"><Num v={last?.dii_net} signed /></Stat>
              <Stat k="Combined net"><Num v={last?.combined_net} signed /></Stat>
              {(["5d", "10d", "20d"] as const).map((h) => (
                <Stat key={h} k={`${h.toUpperCase()} FII / DII`} title="Engine sums over the last N verified sessions">
                  <Num v={s?.[`fii_${h}`]} d={0} signed /> <span className="text-muted">/</span> <Num v={s?.[`dii_${h}`]} d={0} signed />
                </Stat>
              ))}
            </div>
            {s && (
              <div className="mt-2 space-y-1 text-[11.5px] text-secondary">
                <div>Streaks: FII {label(s.fii_streak?.[0])} {s.fii_streak?.[1] ?? "N/A"}d · DII {label(s.dii_streak?.[0])} {s.dii_streak?.[1] ?? "N/A"}d</div>
                <div title="Verified combined sessions vs the engine's target window">Coverage: {String(s.primary_verified ?? "N/A")} of {String(s.target_sessions ?? "N/A")} sessions · {label(s.source_quality)}</div>
                {last?.provisional && <div className="text-warning">Latest day is provisional and may be revised.</div>}
                {active !== data?.target_scope && <div className="text-warning">Viewing {scopeName(active)} rows. The summary above covers {scopeName(data?.target_scope ?? "")} only.</div>}
              </div>
            )}
          </Body>
        </Panel>
        <Panel title={`${view} net flow`} right={<span><span className="text-positive">■</span> FII <span className="text-positive/50">■</span> DII · hover a bar for values</span>}>
          <Body loading={loading && !data} error={error}><FlowBars data={buckets} /></Body>
        </Panel>
      </div>

      <Panel title={`${view} history`} right={scopeName(active)} bodyClass="max-h-[28rem] overflow-auto p-0">
        <Body loading={loading && !data} error={error} lines={8}>
          <table className="w-full text-[12px]">
            <thead className="sticky top-0 z-10 bg-panel text-[10.5px] text-muted">
              <tr className="border-b border-line/30 text-right [&>th]:px-2 [&>th]:py-1.5 [&>th]:font-medium">
                <th className="text-left"><button onClick={() => setDesc((d) => !d)} className="hover:text-fg" title="Sort by date">{view === "Daily" ? "Date" : "Period"} {desc ? "▼" : "▲"}</button></th>
                {view === "Daily" && <><th>FII buy</th><th>FII sell</th></>}
                <th>FII net</th>
                {view === "Daily" && <><th>DII buy</th><th>DII sell</th></>}
                <th>DII net</th><th>Combined</th><th title="Running total from the first period shown">Cum. FII</th><th>Cum. DII</th>
                {view === "Daily" ? <th className="text-left">Source</th> : <th>Sessions</th>}
              </tr>
            </thead>
            <tbody>
              {(desc ? [...buckets].reverse() : buckets).map((b) => {
                const r = b.rows[0], c = cumulative.get(b.key);
                return (
                  <tr key={b.key} className="border-b border-line/15 text-right font-mono tabular-nums hover:bg-raised/50 [&>td]:px-2 [&>td]:py-1">
                    <td className="text-left text-secondary">{b.key}{b.provisional && <span className="ml-1 text-warning" title="Provisional">*</span>}</td>
                    {view === "Daily" && <><td><Num v={r.fii_buy} /></td><td><Num v={r.fii_sell} /></td></>}
                    <td><Num v={b.fii} signed /></td>
                    {view === "Daily" && <><td><Num v={r.dii_buy} /></td><td><Num v={r.dii_sell} /></td></>}
                    <td><Num v={b.dii} signed /></td><td><Num v={b.combined} signed /></td>
                    <td><Num v={c?.fii} d={0} signed /></td><td><Num v={c?.dii} d={0} signed /></td>
                    {view === "Daily" ? <td className="max-w-[16rem] truncate text-left font-sans text-[11px] text-muted" title={r.source ?? ""}>{r.source ?? "N/A"}</td> : <td>{b.days}</td>}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Body>
      </Panel>
      <div className="text-[11px] text-muted">Historical exchange-reported flows. Descriptive context only, not a buy/sell signal. * provisional.</div>
    </div>
  );
}
