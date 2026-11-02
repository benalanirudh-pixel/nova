import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import BreadthBars from "../components/BreadthBars";
import DerivativesPanel from "../components/DerivativesPanel";
import FlowGauge from "../components/FlowGauge";
import IndicatorStrip from "../components/IndicatorStrip";
import NewsList from "../components/NewsList";
import SectorHeatmap from "../components/SectorHeatmap";
import { Body, Change, Chip, Num, Panel, RangeBar, Sparkline } from "../components/ui";
import { useMarketData } from "../hooks/useMarketData";
import { fmt, isNum, label, signCls } from "../lib/format";
import type { CallLine, MarketOverviewData, MorningBrief, PreopenRow, Quote } from "../lib/types";

const time = (iso?: string | null) => (iso ? new Date(iso).toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" }) : "");
const th = "px-2 py-1 font-normal";

function Returns({ q }: { q?: Quote }) {
  return (
    <div className="grid grid-cols-3 gap-1 text-[11px]">
      {(["5d", "20d", "60d"] as const).map((w) => (
        <div key={w} className="flex justify-between rounded border border-line/25 bg-raised/60 px-1.5 py-0.5">
          <span className="text-muted">{w}</span><Num v={q?.[`return_${w}`]} signed suffix="%" />
        </div>
      ))}
    </div>
  );
}

function IndexCard({ q, fallback, live }: { q?: Quote; fallback: string; live?: MorningBrief["session"] }) {
  const closes = (q?.series ?? []).map((p) => p.close);
  // the live NSE print beats the saved report when we have it
  const price = live?.nifty_last ?? q?.price;
  return (
    <Panel title={q?.name ?? fallback} right={live ? <span title={`NSE market status, ${live.trade_date}`}>NSE {live.trade_date}</span> : q?.source_label && <span className="truncate" title={q.source_label}>{q.source_label}</span>}>
      <div className="space-y-1.5">
        <div className="flex items-end justify-between gap-2">
          <div>
            <Num v={price} className="text-2xl font-semibold leading-none" />
            <div className="mt-1 text-xs">{live ? <Change abs={live.nifty_change} pct={live.nifty_change_pct} /> : <Change abs={q?.change_abs} pct={q?.change_percent} />}</div>
          </div>
          <Sparkline values={closes} className="h-10 w-28" title={`Last ${closes.filter(isNum).length} closes`} />
        </div>
        {!live && <RangeBar low={q?.low} high={q?.high} value={q?.price} lowLabel="Day L" highLabel="H" />}
        <Returns q={q} />
      </div>
    </Panel>
  );
}

function VixCard({ q, pctile }: { q?: Quote; pctile: unknown }) {
  const dir = q?.direction ?? "";
  return (
    <Panel title={q?.name ?? "INDIA VIX"} right={<Chip text={q?.regime} />}>
      <div className="space-y-1.5">
        <div className="flex items-end justify-between gap-2">
          <div>
            <Num v={q?.value} className="text-2xl font-semibold leading-none" />
            <div className="mt-1 text-xs"><Change abs={q?.change_abs} pct={q?.change_percent} /></div>
          </div>
          {/* rising VIX = rising fear, so tone is inverted on purpose */}
          <div className={`text-right text-[12px] ${/RIS/.test(dir) ? "text-negative" : /FALL|DECL/.test(dir) ? "text-positive" : "text-secondary"}`}>
            {/RIS/.test(dir) ? "▲ " : /FALL|DECL/.test(dir) ? "▼ " : ""}{label(dir)}
          </div>
        </div>
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

/** The opening read: one line per factor, colour = how it leans for Indian equities. */
function MorningCall({ lines }: { lines: CallLine[] }) {
  const dot = { positive: "bg-positive", negative: "bg-negative", neutral: "bg-muted" };
  const pos = lines.filter((l) => l.tone === "positive").length, neg = lines.filter((l) => l.tone === "negative").length;
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3">
        <div className="flex h-2 flex-1 overflow-hidden rounded-full bg-raised" title="Share of factors leaning supportive / neutral / cautious">
          <div className="bg-positive" style={{ width: `${(pos / Math.max(1, lines.length)) * 100}%` }} />
          <div className="bg-muted/60" style={{ width: `${((lines.length - pos - neg) / Math.max(1, lines.length)) * 100}%` }} />
          <div className="bg-negative" style={{ width: `${(neg / Math.max(1, lines.length)) * 100}%` }} />
        </div>
        <span className="shrink-0 font-mono text-[12px] tabular-nums"><span className="text-positive">{pos} supportive</span> · <span className="text-negative">{neg} cautious</span></span>
      </div>
      <ul className="grid gap-x-6 gap-y-1.5 md:grid-cols-2">
        {lines.map((l, i) => (
          <li key={i} className="flex items-baseline gap-2 text-[13px] leading-snug">
            <span className={`mt-1.5 h-2 w-2 shrink-0 self-start rounded-full ${dot[l.tone]}`} />
            <span className="w-[4.5rem] shrink-0 text-[11.5px] text-muted">{l.topic}</span>
            <span className="text-fg/90">{l.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Price ladder: expected day range and option-OI levels around the latest NIFTY print. */
function Levels({ b, d }: { b: MorningBrief; d: MarketOverviewData["derivatives"] }) {
  const base = b.range?.base ?? b.session?.nifty_last ?? null;
  const rows: { k: string; v: number; tone: string; hint: string }[] = [];
  const push = (k: string, v: unknown, tone: string, hint: string) => { if (isNum(v)) rows.push({ k, v, tone, hint }); };
  push("Call wall", d?.call_wall?.strike, "text-negative", "Strike with the most call open interest; often acts as resistance");
  push("Range high", b.range?.high, "text-secondary", "Latest NIFTY + typical daily range (ATR)");
  push("Max pain", d?.max_pain, "text-info", "Strike where option buyers lose the most at expiry");
  push("Range low", b.range?.low, "text-secondary", "Latest NIFTY − typical daily range (ATR)");
  push("Put wall", d?.put_wall?.strike, "text-positive", "Strike with the most put open interest; often acts as support");
  rows.sort((x, y) => y.v - x.v);
  const at = base === null ? -1 : rows.findIndex((r) => r.v < base);
  const Now = () => (
    <div className="flex items-center gap-2 rounded bg-accent/10 px-2 py-1 text-[12px]">
      <span className="font-medium text-accent">NIFTY now</span><span className="h-px flex-1 bg-accent/40" /><Num v={base} className="font-semibold text-accent" />
    </div>
  );
  return (
    <div className="space-y-2">
      <div className="space-y-0.5">
        {rows.map((r, i) => (
          <div key={r.k}>
            {i === at && <Now />}
            <div className="flex items-center gap-2 px-2 py-1 text-[12px]" title={r.hint}>
              <span className={r.tone}>{r.k}</span><span className="h-px flex-1 bg-line/30" />
              <Num v={r.v} d={0} />
              <Num v={base ? ((r.v - base) / base) * 100 : null} d={1} signed suffix="%" className="w-14 text-right text-[11px] text-muted" />
            </div>
          </div>
        ))}
        {(at === -1 || rows.length === 0) && base !== null && <Now />}
      </div>
      <div className="text-[11px] leading-relaxed text-muted">
        {b.range && <>Typical day ±{fmt(b.range.points, 0)} pts ({fmt(b.range.pct, 2)}%). </>}
        {d?.expiry && <>Option levels for the {d.expiry} expiry, from the saved report.</>}
      </div>
    </div>
  );
}

function Pct({ v }: { v: unknown }) {
  return <Num v={v} d={2} signed suffix="%" />;
}

function GlobalCues({ g }: { g: MorningBrief["global"] }) {
  const Line = ({ k, sub, v, c }: { k: string; sub?: ReactNode; v: ReactNode; c: unknown }) => (
    <div className="flex items-baseline justify-between gap-2 border-t border-line/15 py-1 text-[12px] first:border-t-0">
      <span className="text-secondary">{k}{sub && <span className="ml-1.5 text-[10.5px] text-muted">{sub}</span>}</span>
      <span className="flex items-baseline gap-3">{v}<span className="w-16 text-right"><Pct v={c} /></span></span>
    </div>
  );
  return (
    <div className="grid gap-x-6 sm:grid-cols-2">
      <div>
        <div className="mb-1 text-[11.5px] text-muted">World indices · last close</div>
        {g.indices?.length ? g.indices.map((i) => <Line key={i.name} k={i.name} sub={i.date.slice(5)} v={<Num v={i.last} />} c={i.change_pct} />) : <div className="text-[12px] text-muted">N/A</div>}
      </div>
      <div>
        <div className="mb-1 mt-3 text-[11.5px] text-muted sm:mt-0">Commodities and rupee</div>
        {g.commodities?.map((c) => <Line key={c.name} k={c.name} sub={c.currency} v={<Num v={c.price} />} c={c.change_pct} />)}
        {g.fx?.filter((f) => f.pair === "USDINR" || f.pair === "EURINR").map((f) => <Line key={f.pair} k={f.pair.replace("INR", "/INR")} v={<Num v={f.rate} />} c={f.change_pct} />)}
        {!g.commodities && !g.fx && <div className="text-[12px] text-muted">N/A</div>}
      </div>
    </div>
  );
}

function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { k: T; label: string }[]; value: T; onChange: (k: T) => void }) {
  return (
    <div className="flex flex-wrap gap-1" role="tablist">
      {tabs.map((t) => (
        <button key={t.k} role="tab" aria-selected={t.k === value} onClick={() => onChange(t.k)}
          className={`rounded-full border px-2.5 py-0.5 text-[11.5px] focus:outline-none focus-visible:ring-1 focus-visible:ring-accent ${t.k === value ? "border-accent/60 bg-accent/10 text-accent" : "border-line/40 text-secondary hover:text-fg"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

function Preopen({ p }: { p: NonNullable<MorningBrief["preopen"]> }) {
  const [tab, setTab] = useState<"gainers" | "losers" | "most_active">("gainers");
  const nav = useNavigate();
  const a = p.advances ?? 0, d = p.declines ?? 0, u = p.unchanged ?? 0, t = Math.max(1, a + d + u);
  const rows: PreopenRow[] = p[tab];
  return (
    <div className="space-y-2">
      {!p.is_today && <div className="rounded border border-warning/30 bg-warning/5 px-2 py-1 text-[11.5px] text-warning">This snapshot is from {p.timestamp}. Today's pre-open runs 09:00–09:08 IST.</div>}
      <div>
        <div className="flex h-2 overflow-hidden rounded-full">
          <div className="bg-positive" style={{ width: `${(a / t) * 100}%` }} /><div className="bg-muted" style={{ width: `${(u / t) * 100}%` }} /><div className="bg-negative" style={{ width: `${(d / t) * 100}%` }} />
        </div>
        <div className="mt-1 flex justify-between font-mono text-[11px] tabular-nums"><span className="text-positive">▲ {fmt(a, 0)} up</span><span className="text-muted">{fmt(u, 0)} flat</span><span className="text-negative">▼ {fmt(d, 0)} down</span></div>
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ k: "gainers", label: "Top gainers" }, { k: "losers", label: "Top losers" }, { k: "most_active", label: "Most traded" }]} />
      <table className="w-full text-[12px]">
        <thead className="text-[11px] text-muted"><tr><th className={`${th} text-left`}>Symbol</th><th className={`${th} text-right`}>Indicative open</th><th className={`${th} text-right`}>vs prev close</th><th className={`${th} text-right`}>Value (Cr)</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.symbol} className="cursor-pointer border-t border-line/15 hover:bg-raised/60" onClick={() => nav(`/stock?s=${encodeURIComponent(r.symbol)}`)}>
              <td className="px-2 py-1 font-mono text-fg">{r.symbol}</td>
              <td className="px-2 text-right"><Num v={r.iep} /></td>
              <td className="px-2 text-right"><Pct v={r.change_pct} /></td>
              <td className="px-2 text-right"><Num v={r.turnover_cr} d={1} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      {tab !== "most_active" && <div className="text-[11px] text-muted">Only stocks with at least ₹{p.min_turnover_cr} Cr traded in pre-open.</div>}
    </div>
  );
}

function Focus({ f }: { f: NonNullable<MorningBrief["focus"]> }) {
  const [key, setKey] = useState(f.screens[0]?.key ?? "");
  const nav = useNavigate();
  const s = f.screens.find((x) => x.key === key) ?? f.screens[0];
  if (!s) return null;
  return (
    <div className="space-y-2">
      <Tabs value={s.key} onChange={setKey} tabs={f.screens.map((x) => ({ k: x.key, label: `${x.title} (${x.rows.length})` }))} />
      <div className="text-[11.5px] text-muted">{s.rule}. Liquid stocks only, from the scan at {f.as_of.replace("T", " ")}.</div>
      {s.rows.length === 0 ? <div className="p-1 text-[12px] text-muted">No stock meets this screen in the latest scan.</div> : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="text-[11px] text-muted"><tr className="border-b border-line/25"><th className={`${th} text-left`}>Stock</th><th className={`${th} text-right`}>Price</th><th className={`${th} text-right`}>1D</th><th className={`${th} text-right`}>20D</th><th className={`${th} text-right`}>RSI</th><th className={`${th} text-right`}>Rel. vol</th><th className={`${th} text-right`}>Off high</th><th className={`${th} text-right`}>Trend</th></tr></thead>
            <tbody>
              {s.rows.map((r) => (
                <tr key={r.symbol} className="cursor-pointer border-t border-line/15 hover:bg-raised/60" onClick={() => nav(`/stock?s=${encodeURIComponent(r.symbol)}`)}>
                  <td className="max-w-[13rem] px-2 py-1"><div className="font-mono text-fg">{r.symbol}</div><div className="truncate text-[11px] text-muted">{r.sector ?? r.company_name ?? ""}</div></td>
                  <td className="px-2 text-right"><Num v={r.price} /></td>
                  <td className="px-2 text-right"><Num v={r.return_1d} d={1} signed suffix="%" /></td>
                  <td className="px-2 text-right"><Num v={r.return_20d} d={1} signed suffix="%" /></td>
                  <td className="px-2 text-right"><Num v={r.rsi_14} d={0} /></td>
                  <td className="px-2 text-right"><Num v={r.relative_volume} d={1} suffix={isNum(r.relative_volume) ? "x" : ""} /></td>
                  <td className="px-2 text-right" title="% below the 52-week high">{isNum(r.distance_52w_high) && r.distance_52w_high < 0.05 ? <span className="text-positive">At high</span> : <Num v={isNum(r.distance_52w_high) ? -r.distance_52w_high : null} d={1} suffix={isNum(r.distance_52w_high) ? "%" : ""} />}</td>
                  <td className="px-2 text-right"><Chip text={r.trend} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="text-[11px] text-muted">Screens of measured data, not predictions or buy signals. Click a row for the full stock research page.</div>
    </div>
  );
}

function Institutional({ b, cached }: { b: MorningBrief; cached: MarketOverviewData["flows"] }) {
  if (!b.fii_dii) return <FlowGauge flows={cached} />;
  const max = Math.max(1, ...b.fii_dii.map((r) => Math.abs(r.net_cr ?? 0)));
  return (
    <Panel title="FII / DII cash activity · ₹ crore" right={b.fii_dii[0]?.date}>
      <div className="space-y-2">
        {b.fii_dii.map((r) => (
          <div key={r.category} className="space-y-1">
            <div className="flex items-baseline justify-between text-[12px]"><span className="font-medium">{r.category}</span><span className={`font-mono tabular-nums ${signCls(r.net_cr)}`}>{isNum(r.net_cr) ? `${r.net_cr > 0 ? "+" : ""}${fmt(r.net_cr, 0)}` : "N/A"}</span></div>
            <div className="h-1.5 rounded-full bg-raised"><div className={`h-1.5 rounded-full ${(r.net_cr ?? 0) >= 0 ? "bg-positive" : "bg-negative"}`} style={{ width: `${(Math.abs(r.net_cr ?? 0) / max) * 100}%` }} /></div>
            <div className="flex gap-4 text-[11px] text-muted"><span>Bought <Num v={r.buy_cr} d={0} className="text-secondary" /></span><span>Sold <Num v={r.sell_cr} d={0} className="text-secondary" /></span></div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Movers({ m }: { m: MorningBrief["movers"] }) {
  const nav = useNavigate();
  const List = ({ title, rows }: { title: string; rows: MorningBrief["movers"]["gainers"] }) => (
    <div>
      <div className="mb-1 text-[11.5px] text-muted">{title}</div>
      {rows.length === 0 ? <div className="text-[12px] text-muted">None reported</div> : rows.map((r) => (
        <button key={r.symbol} onClick={() => nav(`/stock?s=${encodeURIComponent(r.symbol)}`)}
          className="flex w-full items-baseline justify-between gap-2 border-t border-line/15 py-1 text-left text-[12px] first:border-t-0 hover:bg-raised/60 focus:outline-none focus-visible:bg-raised">
          <span className="font-mono">{r.symbol}</span><span className="flex gap-3"><Num v={r.ltp} /><span className="w-14 text-right"><Pct v={r.change_pct} /></span></span>
        </button>
      ))}
    </div>
  );
  return <div className="grid gap-x-6 sm:grid-cols-2"><List title="Top gainers" rows={m.gainers} /><List title="Top losers" rows={m.losers} /></div>;
}

export default function MarketOverview() {
  const { data, loading, error } = useMarketData<MarketOverviewData>("/market-overview");
  const brief = useMarketData<MorningBrief>("/morning-brief");
  const b = brief.data;
  const bl = brief.loading && !b;
  const bErr = (v: unknown, key: string) => (brief.error && !b ? brief.error : v == null ? b?.errors[key] ?? "Source returned nothing." : null);

  if (loading && !data) {
    return (
      <div className="animate-pulse space-y-2" aria-busy="true">
        <div className="h-48 rounded-md bg-panel" />
        <div className="grid grid-cols-3 gap-2">{Array.from({ length: 3 }, (_, i) => <div key={i} className="h-36 rounded-md bg-panel" />)}</div>
      </div>
    );
  }
  if (!data) return <div className="text-negative">Failed to load: {error ?? "No data"}</div>;
  const { kpis } = data;

  return (
    <div className="mx-auto max-w-[1800px] space-y-2">
      {error && <div className="text-xs text-warning">Refresh failed ({error}); showing last data.</div>}
      {!kpis && <div className="text-xs text-warning">No saved report: run a refresh to load regime, breadth and flows.</div>}

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,2.2fr)_minmax(0,1fr)]">
        <Panel title="Morning call" right={b && <span>{b.session?.message ?? ""}{b.session?.message && " · "}updated {time(b.generated)}</span>}>
          <Body loading={bl} error={brief.error && !b ? brief.error : null} lines={6}>
            {b && (b.morning_call.length ? <MorningCall lines={b.morning_call} /> : <div className="text-[12px] text-muted">Not enough data for a morning call yet.</div>)}
          </Body>
          <div className="mt-3 border-t border-line/20 pt-2 text-[11px] text-muted">A plain reading of the inputs below, not a forecast or a buy/sell call.</div>
        </Panel>
        <Panel title="NIFTY levels to watch">
          <Body loading={bl} error={brief.error && !b ? brief.error : null} lines={6}>{b && <Levels b={b} d={data.derivatives} />}</Body>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <IndexCard q={kpis?.nifty} fallback="NIFTY 50" live={b?.session} />
        <IndexCard q={kpis?.banknifty} fallback="BANK NIFTY" />
        <VixCard q={kpis?.vix} pctile={kpis?.macro?.vix_percentile_1y} />
      </div>
      <IndicatorStrip ind={kpis?.indicators} />

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        <Panel title="Global cues" right="Yahoo Finance and NSE feed">
          <Body loading={bl} error={b && !b.global.indices && !b.global.commodities ? b.errors.global ?? "Unavailable" : brief.error && !b ? brief.error : null} lines={6}>{b && <GlobalCues g={b.global} />}</Body>
        </Panel>
        <Panel title="Pre-open session" right={b?.preopen?.timestamp && `NSE snapshot ${b.preopen.timestamp}`}>
          <Body loading={bl} error={bErr(b?.preopen, "preopen")} lines={6}>{b?.preopen && <Preopen p={b.preopen} />}</Body>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel title="Stocks in focus" right={b?.focus && `${b.focus.universe} liquid stocks screened`}>
          <Body loading={bl} error={bErr(b?.focus, "focus")} lines={8}>{b?.focus && <Focus f={b.focus} />}</Body>
        </Panel>
        <Panel title="Market news" right={b?.news && `${b.news.length} headlines · Google News`} bodyClass="max-h-[32rem] overflow-auto px-2 py-0">
          <Body loading={bl} error={bErr(b?.news, "news")} lines={8}>{b?.news && <NewsList items={b.news} />}</Body>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-2 lg:grid-cols-3">
        <Institutional b={b ?? ({ fii_dii: null } as MorningBrief)} cached={data.flows} />
        <Panel title="Last session movers" right={b?.session?.trade_date}>
          <Body loading={bl} error={brief.error && !b ? brief.error : null}>{b && <Movers m={b.movers} />}</Body>
        </Panel>
        <BreadthBars breadth={data.breadth} />
      </div>

      <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
        <SectorHeatmap sectors={data.sectors} />
        <DerivativesPanel title={data.derivatives?.instrument ?? "NIFTY"} d={data.derivatives} />
      </div>
    </div>
  );
}
