import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import FlowGauge from "../components/FlowGauge";
import { Body, Chip, NoData, Num, Panel } from "../components/ui";
import { useMarketData } from "../hooks/useMarketData";
import { fetchJSON } from "../lib/api";
import { fmt, fmtCompact, isNum, signCls } from "../lib/format";
import { istSession } from "../lib/schedule";
import type { CallLine, ChainRow, FnoDesk, MarketAnalysisData } from "../lib/types";

const KEYS = ["NIFTY", "BANKNIFTY", "SENSEX"] as const;
type Key = (typeof KEYS)[number];
const LABEL: Record<Key, string> = { NIFTY: "NIFTY 50", BANKNIFTY: "BANK NIFTY", SENSEX: "SENSEX" };
const TAB_KEY = "nova.fnoTab";
const th = "px-1.5 py-1 font-normal";

interface Slot { data: FnoDesk | null; loading: boolean; error: string | null }

/** One desk per index; each fetch is independent so a slow exchange never blocks the others. */
function useDesks(expiry: Record<Key, string | undefined>) {
  const [slots, setSlots] = useState<Record<Key, Slot>>(() =>
    Object.fromEntries(KEYS.map((k) => [k, { data: null, loading: true, error: null }])) as Record<Key, Slot>);
  const seq = useRef<Record<string, number>>({});
  const load = useCallback((k: Key, exp?: string) => {
    const id = (seq.current[k] = (seq.current[k] ?? 0) + 1);
    setSlots((s) => ({ ...s, [k]: { ...s[k], loading: true } }));
    fetchJSON<FnoDesk>(`/fno/${k}${exp ? `?expiry=${encodeURIComponent(exp)}` : ""}`)
      .then((d) => { if (id === seq.current[k]) setSlots((s) => ({ ...s, [k]: { data: d, loading: false, error: null } })); })
      .catch((e: Error) => { if (id === seq.current[k]) setSlots((s) => ({ ...s, [k]: { ...s[k], loading: false, error: e.message } })); });
  }, []);
  const loadAll = useCallback(() => KEYS.forEach((k) => load(k, expiry[k])), [load, expiry]);
  useEffect(() => { loadAll(); }, [loadAll]);
  // live during market hours: chains refresh every minute (the API caches for 60 s)
  useEffect(() => {
    const t = setInterval(() => { if (istSession().session === "Open") loadAll(); }, 60_000);
    return () => clearInterval(t);
  }, [loadAll]);
  return { slots, load, loadAll };
}

/* ------------------------------------------------------------------ pieces */

function IndexTab({ k, s, active, onClick }: { k: Key; s: Slot; active: boolean; onClick: () => void }) {
  const d = s.data, m = d?.metrics, t = d?.technicals;
  const chg = t?.change_pct;
  return (
    <button onClick={onClick} role="tab" aria-selected={active}
      className={`min-w-0 flex-1 rounded-md border px-3 py-2 text-left transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60 ${active ? "border-accent/60 bg-accent/[0.07]" : "border-line/40 bg-panel hover:border-line"}`}>
      <div className="flex items-baseline justify-between gap-2">
        <span className={`text-[13px] font-semibold ${active ? "text-accent" : "text-fg"}`}>{LABEL[k]}</span>
        <span className="text-[10.5px] text-muted">{d?.exchange ?? ""}{d?.expiry ? ` · ${d.expiry}` : ""}</span>
      </div>
      {s.loading && !d ? <div className="mt-2 h-5 w-32 animate-pulse rounded bg-raised" /> : (
        <>
          <div className="mt-1 flex items-baseline gap-2">
            <Num v={d?.spot} className="text-xl font-semibold" />
            <Num v={chg} signed suffix="%" className="text-[12px]" />
          </div>
          <div className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted">
            <span>PCR <Num v={m?.pcr_oi} className="text-secondary" /></span>
            <span>Max pain <Num v={m?.max_pain} d={0} className="text-secondary" /></span>
            <span>IV <Num v={m?.atm_iv} d={1} className="text-secondary" /></span>
            <span>Move ±<Num v={m?.expected_move_pct} className="text-secondary" />%</span>
          </div>
        </>
      )}
      {s.error && !d && <div className="mt-1 text-[11px] text-negative">{s.error}</div>}
    </button>
  );
}

function Metric({ k, children, sub, title }: { k: string; children: ReactNode; sub?: ReactNode; title?: string }) {
  return (
    <div className="min-w-[7.5rem] flex-1 border-l border-line/25 px-3 py-1.5 first:border-l-0" title={title}>
      <div className="text-[11px] text-muted">{k}</div>
      <div className="text-[15px] font-semibold leading-tight">{children}</div>
      {sub && <div className="text-[11px] text-muted">{sub}</div>}
    </div>
  );
}

function MetricStrip({ d, onExpiry }: { d: FnoDesk; onExpiry: (e: string) => void }) {
  const m = d.metrics, t = d.technicals;
  const ivRv = m?.atm_iv != null && t ? m.atm_iv - t.rv20 : null;
  const mpGap = m?.max_pain != null && d.spot ? (m.max_pain / d.spot - 1) * 100 : null;
  return (
    <div className="flex flex-wrap items-stretch rounded-md border border-line/40 bg-panel py-1">
      <Metric k="Expiry" sub={m?.days_to_expiry != null ? `${m.days_to_expiry} day${m.days_to_expiry === 1 ? "" : "s"} left` : undefined}>
        {d.expiries.length > 1 ? (
          <select value={d.expiry ?? ""} onChange={(e) => onExpiry(e.target.value)} aria-label="Expiry"
            className="-ml-1 rounded bg-transparent px-1 font-mono text-[14px] font-semibold text-fg outline-none hover:bg-raised focus-visible:ring-1 focus-visible:ring-accent">
            {d.expiries.map((e) => <option key={e} value={e} className="bg-panel">{e}</option>)}
          </select>
        ) : <span className="font-mono">{d.expiry ?? "N/A"}</span>}
      </Metric>
      <Metric k="ATM strike"><Num v={m?.atm} d={0} /></Metric>
      <Metric k="PCR (OI)" sub={<>Vol <Num v={m?.pcr_volume} /> · ΔOI <Num v={m?.pcr_change_oi} /></>} title="Put OI ÷ call OI across the expiry">
        <span className={m?.pcr_oi == null ? "" : m.pcr_oi >= 1.2 ? "text-positive" : m.pcr_oi <= 0.7 ? "text-negative" : ""}><Num v={m?.pcr_oi} /></span>
      </Metric>
      <Metric k="Max pain" sub={<><Num v={mpGap} d={2} signed suffix="%" /> vs spot</>}><Num v={m?.max_pain} d={0} /></Metric>
      <Metric k="ATM IV" sub={<>C <Num v={m?.atm_call_iv} d={1} /> · P <Num v={m?.atm_put_iv} d={1} /></>}><Num v={m?.atm_iv} d={2} suffix="%" /></Metric>
      <Metric k="IV − RV20" sub={<>RV20 <Num v={t?.rv20} d={1} />%</>} title="ATM implied vol minus 20-day realized vol of the index">
        <Num v={ivRv} d={1} signed suffix=" pts" />
      </Metric>
      <Metric k="Skew (3% OTM)" title="3% OTM put IV minus 3% OTM call IV" sub="put − call IV"><Num v={m?.skew} d={1} signed suffix=" pts" /></Metric>
      <Metric k="ATM straddle" sub={<>±<Num v={m?.expected_move_pct} />% by expiry</>}><Num v={m?.straddle} /></Metric>
    </div>
  );
}

function DeskRead({ lines }: { lines: CallLine[] }) {
  const dot = { positive: "bg-positive", negative: "bg-negative", neutral: "bg-muted" };
  if (lines.length === 0) return <NoData text="Not enough data for a desk read." />;
  return (
    <ul className="space-y-1.5">
      {lines.map((l, i) => (
        <li key={i} className="flex items-baseline gap-2 text-[13px] leading-snug">
          <span className={`h-2 w-2 shrink-0 translate-y-[-1px] rounded-full ${dot[l.tone]}`} />
          <span className="w-[5.5rem] shrink-0 text-[11.5px] text-muted">{l.topic}</span>
          <span className="text-fg/90">{l.text}</span>
        </li>
      ))}
    </ul>
  );
}

/** Every level a desk quotes, sorted by price, with spot slotted in. */
function Ladder({ d }: { d: FnoDesk }) {
  const m = d.metrics, p = d.technicals?.pivots, spot = d.spot;
  const rows: { k: string; v: number; cls: string; hint?: string }[] = [];
  const add = (k: string, v: unknown, cls: string, hint?: string) => { if (isNum(v)) rows.push({ k, v, cls, hint }); };
  m?.resistance.forEach((r, i) => add(`Call OI ${i + 1}`, r.strike, "text-negative", `Call OI ${fmtCompact(r.oi)}, change ${fmtCompact(r.change_oi)}`));
  m?.support.forEach((r, i) => add(`Put OI ${i + 1}`, r.strike, "text-positive", `Put OI ${fmtCompact(r.oi)}, change ${fmtCompact(r.change_oi)}`));
  add("Max pain", m?.max_pain, "text-info");
  add("Straddle BE high", m?.breakeven_high, "text-warning", "ATM strike + straddle premium");
  add("Straddle BE low", m?.breakeven_low, "text-warning", "ATM strike − straddle premium");
  if (p) { add("R2", p.r2, "text-secondary", `Pivot from ${p.from}`); add("R1", p.r1, "text-secondary"); add("Pivot", p.pp, "text-secondary"); add("S1", p.s1, "text-secondary"); add("S2", p.s2, "text-secondary"); }
  rows.sort((a, b) => b.v - a.v);
  const at = isNum(spot) ? rows.findIndex((r) => r.v < spot) : -1;
  const Spot = () => (
    <div className="my-0.5 flex items-center gap-2 rounded bg-accent/10 px-2 py-1 text-[12px]">
      <span className="font-medium text-accent">Spot</span><span className="h-px flex-1 bg-accent/40" /><Num v={spot} className="font-semibold text-accent" />
    </div>
  );
  return (
    <div>
      {rows.map((r, i) => (
        <div key={r.k + r.v}>
          {i === at && <Spot />}
          <div className="flex items-center gap-2 px-2 py-[3px] text-[12px]" title={r.hint}>
            <span className={`w-28 shrink-0 ${r.cls}`}>{r.k}</span><span className="h-px flex-1 bg-line/20" />
            <Num v={r.v} d={0} />
            <Num v={isNum(spot) ? (r.v / spot - 1) * 100 : null} d={2} signed suffix="%" className="w-16 text-right text-[11px] text-muted" />
          </div>
        </div>
      ))}
      {(at === -1 && rows.length > 0) && <Spot />}
    </div>
  );
}

/** Put OI grows left, call OI grows right, strikes down the spine. The desk's main picture. */
function OiProfile({ rows, spot, atm, maxPain }: { rows: ChainRow[]; spot: number | null; atm?: number; maxPain?: number | null }) {
  const [mode, setMode] = useState<"oi" | "chg">("oi");
  const val = (r: ChainRow, leg: "call" | "put") => (mode === "oi" ? r[`${leg}_oi`] : r[`${leg}_change_oi`]) ?? 0;
  const max = Math.max(1, ...rows.flatMap((r) => [Math.abs(val(r, "call")), Math.abs(val(r, "put"))]));
  const desc = [...rows].sort((a, b) => b.strike - a.strike);
  const spotAt = isNum(spot) ? desc.findIndex((r) => r.strike < spot) : -1;
  const Bar = ({ v, side }: { v: number; side: "call" | "put" }) => (
    <div className={`flex h-3.5 flex-1 ${side === "put" ? "justify-end" : ""}`}>
      <div className={`h-full rounded-sm ${side === "call" ? (v >= 0 ? "bg-negative/75" : "bg-negative/25 outline outline-1 outline-negative/60") : (v >= 0 ? "bg-positive/75" : "bg-positive/25 outline outline-1 outline-positive/60")}`}
        style={{ width: `${(Math.abs(v) / max) * 100}%` }} />
    </div>
  );
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2 text-[11.5px]">
        <div className="flex gap-1" role="tablist">
          {(["oi", "chg"] as const).map((k) => (
            <button key={k} role="tab" aria-selected={mode === k} onClick={() => setMode(k)}
              className={`rounded-full border px-2.5 py-0.5 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent ${mode === k ? "border-accent/60 bg-accent/10 text-accent" : "border-line/40 text-secondary hover:text-fg"}`}>
              {k === "oi" ? "Open interest" : "Change in OI"}
            </button>
          ))}
        </div>
        <div className="flex gap-3 text-muted">
          <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-positive/75" />Puts</span>
          <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm bg-negative/75" />Calls</span>
          {mode === "chg" && <span className="flex items-center gap-1"><span className="h-2 w-3 rounded-sm outline outline-1 outline-muted" />Unwinding</span>}
        </div>
      </div>
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-x-2 text-[11px]">
        <div className="pb-1 text-right text-muted">Put {mode === "oi" ? "OI" : "ΔOI"}</div><div className="pb-1 text-center text-muted">Strike</div><div className="pb-1 text-muted">Call {mode === "oi" ? "OI" : "ΔOI"}</div>
        {desc.map((r, i) => {
          const isAtm = r.strike === atm, isMp = r.strike === maxPain;
          return (
            <div key={r.strike} className="contents">
              {i === spotAt && <div className="col-span-3 my-0.5 flex items-center gap-2 text-[10.5px] text-accent"><span className="h-px flex-1 bg-accent/60" />spot <Num v={spot} /><span className="h-px flex-1 bg-accent/60" /></div>}
              <div className="flex items-center gap-1.5" title={`Put ${mode === "oi" ? "OI" : "ΔOI"} ${fmt(val(r, "put"), 0)}`}>
                <span className="w-12 text-right font-mono tabular-nums text-muted">{fmtCompact(val(r, "put"))}</span><Bar v={val(r, "put")} side="put" />
              </div>
              <div className={`w-[4.5rem] rounded px-1 text-center font-mono tabular-nums ${isAtm ? "bg-accent/15 font-semibold text-accent" : isMp ? "text-info" : "text-secondary"}`}
                title={isAtm ? "ATM strike" : isMp ? "Max pain" : undefined}>
                {fmt(r.strike, 0)}{isMp && !isAtm ? " ◆" : ""}
              </div>
              <div className="flex items-center gap-1.5" title={`Call ${mode === "oi" ? "OI" : "ΔOI"} ${fmt(val(r, "call"), 0)}`}>
                <Bar v={val(r, "call")} side="call" /><span className="w-12 font-mono tabular-nums text-muted">{fmtCompact(val(r, "call"))}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div className="text-[11px] text-muted">◆ max pain · highlighted strike is ATM · {desc.length} strikes around spot</div>
    </div>
  );
}

function Chain({ rows, spot, atm }: { rows: ChainRow[]; spot: number | null; atm?: number }) {
  const maxC = Math.max(1, ...rows.map((r) => r.call_oi ?? 0)), maxP = Math.max(1, ...rows.map((r) => r.put_oi ?? 0));
  const heat = (v: number | null, max: number, rgb: string) => (isNum(v) ? { background: `linear-gradient(to left, rgba(${rgb},0.28) ${(v / max) * 100}%, transparent 0)` } : undefined);
  const heatR = (v: number | null, max: number, rgb: string) => (isNum(v) ? { background: `linear-gradient(to right, rgba(${rgb},0.28) ${(v / max) * 100}%, transparent 0)` } : undefined);
  const iv = (v: number | null) => (isNum(v) && v > 0 ? fmt(v, 1) : "–");
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[44rem] text-[11.5px]">
        <thead className="sticky top-0 z-10 bg-panel text-[10.5px] text-muted">
          <tr><th colSpan={5} className="py-1 text-center font-medium text-negative">Calls</th><th /><th colSpan={5} className="py-1 text-center font-medium text-positive">Puts</th></tr>
          <tr className="border-b border-line/25">
            <th className={`${th} text-right`}>OI</th><th className={`${th} text-right`}>ΔOI</th><th className={`${th} text-right`}>Volume</th><th className={`${th} text-right`}>IV</th><th className={`${th} text-right`}>LTP</th>
            <th className={`${th} text-center`}>Strike</th>
            <th className={`${th} text-left`}>LTP</th><th className={`${th} text-left`}>IV</th><th className={`${th} text-left`}>Volume</th><th className={`${th} text-left`}>ΔOI</th><th className={`${th} text-left`}>OI</th>
          </tr>
        </thead>
        <tbody className="font-mono tabular-nums">
          {rows.map((r) => {
            const callItm = isNum(spot) && r.strike < spot, putItm = isNum(spot) && r.strike > spot;
            const isAtm = r.strike === atm;
            return (
              <tr key={r.strike} className={`border-t border-line/10 hover:bg-raised/70 ${isAtm ? "outline outline-1 -outline-offset-1 outline-accent/50" : ""}`}>
                <td className={`px-1.5 py-[3px] text-right ${callItm ? "bg-warning/[0.04]" : ""}`} style={heat(r.call_oi, maxC, "240,84,79")}>{fmtCompact(r.call_oi)}</td>
                <td className={`px-1.5 text-right ${signCls(r.call_change_oi)} ${callItm ? "bg-warning/[0.04]" : ""}`}>{fmtCompact(r.call_change_oi)}</td>
                <td className={`px-1.5 text-right text-secondary ${callItm ? "bg-warning/[0.04]" : ""}`}>{fmtCompact(r.call_volume)}</td>
                <td className={`px-1.5 text-right text-secondary ${callItm ? "bg-warning/[0.04]" : ""}`}>{iv(r.call_iv)}</td>
                <td className={`px-1.5 text-right ${callItm ? "bg-warning/[0.04]" : ""}`}>{fmt(r.call_ltp)}</td>
                <td className={`px-2 text-center font-semibold ${isAtm ? "bg-accent/15 text-accent" : "bg-raised/60 text-fg"}`}>{fmt(r.strike, 0)}</td>
                <td className={`px-1.5 ${putItm ? "bg-warning/[0.04]" : ""}`}>{fmt(r.put_ltp)}</td>
                <td className={`px-1.5 text-secondary ${putItm ? "bg-warning/[0.04]" : ""}`}>{iv(r.put_iv)}</td>
                <td className={`px-1.5 text-secondary ${putItm ? "bg-warning/[0.04]" : ""}`}>{fmtCompact(r.put_volume)}</td>
                <td className={`px-1.5 ${signCls(r.put_change_oi)} ${putItm ? "bg-warning/[0.04]" : ""}`}>{fmtCompact(r.put_change_oi)}</td>
                <td className={`px-1.5 ${putItm ? "bg-warning/[0.04]" : ""}`} style={heatR(r.put_oi, maxP, "46,189,133")}>{fmtCompact(r.put_oi)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="mt-1 px-1 text-[11px] text-muted">Shaded cells are in the money. Bar shading shows OI relative to the largest strike on each side.</div>
    </div>
  );
}

/** Call and put IV across strikes; the shape shows where the market pays up for protection. */
function IvSmile({ rows, atm }: { rows: ChainRow[]; atm?: number }) {
  const pts = (leg: "call" | "put") => rows.filter((r) => isNum(r[`${leg}_iv`]) && (r[`${leg}_iv`] as number) > 0).map((r) => [r.strike, r[`${leg}_iv`] as number] as const);
  const c = pts("call"), p = pts("put"), all = [...c, ...p];
  if (all.length < 3) return <NoData text="Not enough IV quotes to draw the smile." />;
  const xs = rows.map((r) => r.strike), x0 = Math.min(...xs), x1 = Math.max(...xs);
  const ys = all.map(([, y]) => y), y0 = Math.floor(Math.min(...ys) - 1), y1 = Math.ceil(Math.max(...ys) + 1);
  const W = 560, H = 200, L = 34, B = 22, R = 8, T = 8;
  const sx = (x: number) => L + ((x - x0) / Math.max(1, x1 - x0)) * (W - L - R), sy = (y: number) => T + (1 - (y - y0) / Math.max(1, y1 - y0)) * (H - T - B);
  const path = (s: readonly (readonly [number, number])[]) => s.map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`).join("");
  const ticks = Array.from({ length: 4 }, (_, i) => y0 + ((y1 - y0) * i) / 3);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Implied volatility by strike for calls and puts">
        {ticks.map((t) => <g key={t}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} stroke="currentColor" className="text-line/30" /><text x={L - 4} y={sy(t) + 3} textAnchor="end" className="fill-muted text-[10px]">{t.toFixed(0)}</text></g>)}
        {isNum(atm) && <><line x1={sx(atm)} x2={sx(atm)} y1={T} y2={H - B} className="stroke-accent/60" strokeDasharray="3 3" /><text x={sx(atm)} y={H - 6} textAnchor="middle" className="fill-accent text-[10px]">ATM {fmt(atm, 0)}</text></>}
        <text x={L} y={H - 6} className="fill-muted text-[10px]">{fmt(x0, 0)}</text>
        <text x={W - R} y={H - 6} textAnchor="end" className="fill-muted text-[10px]">{fmt(x1, 0)}</text>
        <path d={path(p)} fill="none" strokeWidth="2" className="stroke-positive" />
        <path d={path(c)} fill="none" strokeWidth="2" className="stroke-negative" />
      </svg>
      <div className="flex gap-4 text-[11px] text-muted"><span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-positive" />Put IV</span><span className="flex items-center gap-1"><span className="h-0.5 w-4 bg-negative" />Call IV</span><span>Implied volatility, % annualized</span></div>
    </div>
  );
}

function Technicals({ t, spot }: { t: NonNullable<FnoDesk["technicals"]>; spot: number | null }) {
  const px = spot ?? t.last;
  const pos = t.high_52w > t.low_52w ? Math.min(100, Math.max(0, ((px - t.low_52w) / (t.high_52w - t.low_52w)) * 100)) : null;
  const Row = ({ k, children }: { k: string; children: ReactNode }) =>
    <div className="flex h-6 items-center justify-between gap-2 border-t border-line/15 text-[12px] first:border-t-0"><span className="text-secondary">{k}</span><span className="flex items-center gap-2">{children}</span></div>;
  return (
    <div className="space-y-2">
      <div>
        {Object.entries(t.ema).map(([n, v]) => (
          <Row key={n} k={`EMA ${n}`}><Num v={v} /><Num v={(px / v - 1) * 100} d={2} signed suffix="%" className="w-16 text-right" /><Chip text={px >= v ? "ABOVE" : "BELOW"} /></Row>
        ))}
        <Row k="RSI (14)"><Num v={t.rsi} d={1} /><Chip text={t.rsi >= 70 ? "OVERBOUGHT" : t.rsi <= 30 ? "OVERSOLD" : "NEUTRAL"} /></Row>
        <Row k="ATR (14)"><Num v={t.atr} d={0} /><span className="text-[11px] text-muted"><Num v={t.atr_pct} />%</span></Row>
        <Row k="Realized vol 20D"><Num v={t.rv20} d={1} suffix="%" /></Row>
        <Row k="Day range"><Num v={t.day_low} d={0} /><span className="text-muted">–</span><Num v={t.day_high} d={0} /></Row>
        <Row k="Returns 5D / 20D / 60D">{(["5d", "20d", "60d"] as const).map((w) => <Num key={w} v={t.returns[w]} d={1} signed suffix="%" />)}</Row>
      </div>
      <div className="flex items-center gap-2 text-[11px]" title={pos === null ? undefined : `${pos.toFixed(0)}% of the 52-week range`}>
        <span className="text-muted">52W</span><Num v={t.low_52w} d={0} className="text-secondary" />
        <span className="relative h-1.5 flex-1 rounded-full bg-gradient-to-r from-negative/40 via-line/40 to-positive/40">
          {pos !== null && <span className="absolute -top-1 h-3.5 w-1 rounded-sm bg-fg" style={{ left: `calc(${pos}% - 2px)` }} />}
        </span>
        <Num v={t.high_52w} d={0} className="text-secondary" />
      </div>
      <div className="text-[11px] text-muted">Daily data to {t.as_of}, Yahoo Finance. Pivots use the {t.pivots.from} session.</div>
    </div>
  );
}

function Events({ e }: { e: MarketAnalysisData["events"] }) {
  const evs = (e?.upcoming_events ?? []).slice(0, 6);
  if (!e) return <NoData />;
  return (
    <div className="space-y-1">
      {e.source_fresh === false && <div className="rounded border border-warning/30 bg-warning/5 px-2 py-1 text-[11px] text-warning">Calendar source is stale; verify dates independently.</div>}
      {evs.length === 0 ? <NoData text="No upcoming events in the calendar." /> : evs.map((v, i) => (
        <div key={i} className="flex items-baseline gap-2 border-t border-line/15 py-1 text-[12px] first:border-t-0">
          <span className="w-20 shrink-0 font-mono text-[11px] text-muted">{v.datetime_utc ? new Date(v.datetime_utc).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) : "N/A"}</span>
          <span className="min-w-0 flex-1 truncate" title={v.impact_note}>{v.name ?? "N/A"}</span>
          <Chip text={v.risk_level ?? v.severity} />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export default function MarketAnalysis() {
  const [tab, setTab] = useState<Key>(() => {
    try { const v = localStorage.getItem(TAB_KEY); return (KEYS as readonly string[]).includes(v ?? "") ? (v as Key) : "NIFTY"; } catch { return "NIFTY"; }
  });
  const [expiry, setExpiry] = useState<Record<Key, string | undefined>>({ NIFTY: undefined, BANKNIFTY: undefined, SENSEX: undefined });
  const { slots, load } = useDesks(expiry);
  const ctx = useMarketData<MarketAnalysisData>("/market-analysis");
  const pick = (k: Key) => { setTab(k); try { localStorage.setItem(TAB_KEY, k); } catch { /* storage unavailable */ } };
  const s = slots[tab], d = s.data, m = d?.metrics;
  const rows = useMemo(() => m?.profile ?? [], [m]);
  const r = ctx.data?.regime;

  return (
    <div className="mx-auto max-w-[1800px] space-y-2">
      <div className="flex flex-col gap-2 sm:flex-row" role="tablist" aria-label="Index">
        {KEYS.map((k) => <IndexTab key={k} k={k} s={slots[k]} active={k === tab} onClick={() => pick(k)} />)}
      </div>

      <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted">
        <span>{d?.source ?? "Option chain"}{d && ` · updated ${new Date(d.generated).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`}</span>
        {s.loading && <span className="text-accent">Loading {LABEL[tab]} chain…</span>}
        {s.error && d && <span className="text-warning">Reload failed ({s.error}); showing last chain.</span>}
        <span className="ml-auto">Auto-refreshes every minute while the market is open</span>
        <button onClick={() => load(tab, expiry[tab])} className="rounded border border-line/50 px-2 py-0.5 text-secondary hover:border-accent/60 hover:text-accent focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">Reload chain</button>
      </div>

      {!d ? (
        <Panel title={LABEL[tab]}><Body loading={s.loading} error={s.error} lines={8}>{null}</Body></Panel>
      ) : (
        <>
          {d.errors.chain && <div className="rounded-md border border-warning/30 bg-warning/5 px-3 py-2 text-[12px] text-warning">{d.errors.chain}. Spot technicals below still use daily history.</div>}
          <MetricStrip d={d} onExpiry={(e) => { setExpiry((x) => ({ ...x, [tab]: e })); load(tab, e); }} />

          <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Panel title="Desk read" right={`${LABEL[tab]} · ${d.expiry ?? "no expiry"}`}>
              <DeskRead lines={d.read} />
              <div className="mt-3 border-t border-line/20 pt-2 text-[11px] text-muted">Describes current positioning from the chain and daily history. Not a forecast or a trade recommendation.</div>
            </Panel>
            <Panel title="Levels">
              <Ladder d={d} />
            </Panel>
          </div>

          {m && (
            <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.35fr)]">
              <Panel title="OI profile" right={<span>Total put <span className="font-mono text-positive">{fmtCompact(m.put_oi)}</span> · call <span className="font-mono text-negative">{fmtCompact(m.call_oi)}</span></span>}>
                <OiProfile rows={rows} spot={d.spot} atm={m.atm} maxPain={m.max_pain} />
              </Panel>
              <Panel title="Option chain" right={`${rows.length} strikes around ATM`} bodyClass="max-h-[40rem] overflow-auto p-0">
                <Chain rows={[...rows].sort((a, b) => a.strike - b.strike)} spot={d.spot} atm={m.atm} />
              </Panel>
            </div>
          )}

          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2 2xl:grid-cols-3">
            <Panel title="Volatility smile" right={m && <span>Fresh writing: call <span className="font-mono text-negative">{m.fresh_call_writing[0] ? fmt(m.fresh_call_writing[0].strike, 0) : "N/A"}</span> · put <span className="font-mono text-positive">{m.fresh_put_writing[0] ? fmt(m.fresh_put_writing[0].strike, 0) : "N/A"}</span></span>}>
              {m ? <IvSmile rows={rows} atm={m.atm} /> : <NoData text="Option chain unavailable." />}
            </Panel>
            <Panel title="Spot technicals">
              <Body loading={false} error={d.technicals ? null : d.errors.technicals ?? "Unavailable"}>{d.technicals && <Technicals t={d.technicals} spot={d.spot} />}</Body>
            </Panel>
            <Panel title="Volatility regime · India VIX" right={r && <Chip text={r.vix_regime} />} className="lg:col-span-2 2xl:col-span-1">
              <Body loading={ctx.loading && !ctx.data} error={ctx.data && !r ? "No saved report: run a refresh." : null}>
                {r && (
                  <div className="space-y-2">
                    <div className="flex items-baseline gap-3">
                      <Num v={r.india_vix} className="text-2xl font-semibold" />
                      <Num v={r.vix_change_percent} signed suffix="%" className="text-[13px]" />
                      <span className={`text-[12px] ${/RIS/.test(r.vix_direction ?? "") ? "text-negative" : "text-secondary"}`}>{(r.vix_direction ?? "").toLowerCase()}</span>
                    </div>
                    <div className="flex items-center gap-2 text-[11px]">
                      <span className="w-24 text-muted">1Y percentile</span>
                      <div className="h-1.5 flex-1 rounded-full bg-raised">{isNum(r.vix_percentile_1y) && <div className="h-1.5 rounded-full bg-warning/70" style={{ width: `${Math.min(100, r.vix_percentile_1y)}%` }} />}</div>
                      <Num v={r.vix_percentile_1y} d={0} className="w-8 text-right" />
                    </div>
                    <div className="flex items-center gap-2 text-[12px]"><span className="text-muted">Market regime</span><Chip text={r.market_regime} /></div>
                    <div className="text-[11px] text-muted">VIX is NIFTY's 30-day implied vol. Compare it with the ATM IV above to see whether near-dated options are priced above or below the index-wide reading.</div>
                  </div>
                )}
              </Body>
            </Panel>
          </div>

          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            <FlowGauge flows={ctx.data?.flows ?? null} />
            <Panel title="Event risk" right={ctx.data?.events?.overall_risk && <span className="flex items-center gap-1.5">Overall <Chip text={ctx.data.events.overall_risk} /></span>}>
              <Events e={ctx.data?.events ?? null} />
            </Panel>
          </div>
        </>
      )}
    </div>
  );
}
