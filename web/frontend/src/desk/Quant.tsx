import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMarketData } from "../hooks/useMarketData";
import { isNum } from "../lib/format";
import type { QBreadth, BreadthPoint, FactorRow, QuantInternals, QuantRisk, QuantScorecard, RotationRow, StockQuant } from "../lib/types";
import LineChart, { Quadrants } from "./Chart";
import { Block, dayMonth, Empty, Flag, Kv, n, Pane, Pct, pc, sg, Table } from "./ui";

type Point = { time: string; value: number | null };
type Candle = { time: string; close: number; volume: number };
const pct = (v: unknown, d = 1) => (isNum(v) ? `${n(v, d)}%` : "n/a");
const RANGES: [string, number][] = [["3M", 63], ["6M", 126], ["1Y", 252], ["3Y", 0]];

/** Close with the 50 and 200-day averages, volume underneath, and the value area the stock has traded in. */
export function PriceChart({ sym, candles, ema50, ema200, risk }: { sym: string; candles: Candle[]; ema50: Point[]; ema200: Point[]; risk?: QuantRisk }) {
  const [range, setRange] = useState(2);
  const view = useMemo(() => {
    const keep = RANGES[range][1], c = keep ? candles.slice(-keep) : candles;
    const by = (p: Point[]) => { const m = new Map(p.map((x) => [x.time, x.value])); return c.map((b) => m.get(b.time) ?? null); };
    return { x: c.map((b) => b.time), close: c.map((b) => b.close), e50: by(ema50), e200: by(ema200), vol: c.map((b) => b.volume) };
  }, [candles, ema50, ema200, range]);
  const vp = risk?.status === "AVAILABLE" ? risk.volume_profile : null;
  if (candles.length < 2) return null;
  return (
    <Block wide title="Price" sub={`${sym} daily close, ${view.x.length} sessions to ${dayMonth(view.x[view.x.length - 1])}`}>
      <div className="tool"><div className="seg">{RANGES.map(([t], i) => <button key={t} type="button" aria-pressed={range === i} onClick={() => setRange(i)}>{t}</button>)}</div></div>
      <LineChart label={`${sym} price chart`} x={view.x} bars={view.vol} barsLabel="Volume" barFmt={(v) => v.toLocaleString("en-IN", { notation: "compact", maximumFractionDigits: 1 })}
        series={[{ name: "Close", color: "var(--s1)", values: view.close }, { name: "EMA 50", color: "var(--s2)", values: view.e50, width: 1.5 }, { name: "EMA 200", color: "var(--s3)", values: view.e200, width: 1.5 }]}
        band={vp ? { lo: vp.value_area_low, hi: vp.value_area_high, label: `Value area, ${vp.sessions} sessions` } : undefined}
        marks={vp ? [{ y: vp.poc, label: "POC" }] : undefined} />
    </Block>
  );
}

function Scorecard({ c }: { c: QuantScorecard }) {
  if (c.status !== "AVAILABLE") return <Block title="Scorecard"><div className="pad"><Flag>Not rated</Flag><p className="note-t">{c.reason}</p></div></Block>;
  return (
    <Block title="Scorecard" sub={`Percentile in ${n(c.universe, 0)} stocks, ${c.universe_source === "Saved scan" ? "saved scan" : "every listed stock"}, ${dayMonth(c.scan_as_of)}`}>
      <div className="pad">
        <div className="score"><b>{n(c.composite, 0)}</b><span>{c.stance}</span><small>Rank against other stocks, not a view on direction</small></div>
        <div className="meters" role="table" aria-label="Pillar percentiles">
          <div className="mh" role="row"><span>Pillar</span><span>Universe</span><span /><span>{c.sector_peers ? `Sector (${c.sector_peers})` : "Sector"}</span></div>
          {c.pillars!.map((p) => (
            <div key={p.pillar} role="row"><u>{p.pillar}</u><div className="meter" aria-hidden><i style={{ width: `${p.universe_pct ?? 0}%` }} /></div><b>{n(p.universe_pct, 0)}</b><b>{isNum(p.sector_pct) ? n(p.sector_pct, 0) : "n/a"}</b></div>
          ))}
          <div role="row" className="cap"><u>Liquidity</u><div className="meter" aria-hidden><i style={{ width: `${c.liquidity_pct ?? 0}%` }} /></div><b>{n(c.liquidity_pct, 0)}</b><b /></div>
        </div>
        {c.conflicts!.length > 0 && <ul className="reads conf">{c.conflicts!.map((t) => <li key={t}><em>Conflict</em>{t}</li>)}</ul>}
        <p className="note-t">{c.method} Liquidity is capacity and sits outside the composite.</p>
      </div>
    </Block>
  );
}

/** Institutional blocks for one stock: scorecard, risk, benchmark, liquidity and structure. */
export function StockQuantBlocks({ q, px }: { q?: StockQuant; px: number | null }) {
  if (!q) return null;
  const r = q.risk;
  if (r.status !== "AVAILABLE") return <><Scorecard c={q.scorecard} /><Block title="Risk profile"><div className="pad"><Flag>Unavailable</Flag><p className="note-t">{r.reason}</p></div></Block></>;
  const { volatility: v, tail: t, drawdown: d, ratios: ra, benchmark: b, liquidity: l, trend_quality: tq } = r;
  const fit = (f: typeof tq.fit_60d) => (f ? `${pc(f.slope_annual_pct, 0)} a year, R² ${n(f.r_squared)}` : "n/a");
  const vs = (level: number) => (isNum(px) ? pc((px / level - 1) * 100, 1) : "");
  return (
    <>
      <Scorecard c={q.scorecard} />
      <Block title="Risk profile" sub={`${r.sessions} sessions from ${dayMonth(r.from)}`}>
        <div className="pad"><Kv rows={[
          ["Volatility 20D", pct(v.vol_20d_pct)], ["Volatility 60D", pct(v.vol_60d_pct)], ["Volatility, window", pct(v.vol_full_pct)], ["20D vol percentile", n(v.vol_20d_percentile, 0)],
          ["Downside deviation", pct(v.downside_dev_pct)], ["VaR 95%, 1 day", pct(t.var_95_pct, 2)], ["CVaR 95%, 1 day", pct(t.cvar_95_pct, 2)], ["VaR 99%, 1 day", pct(t.var_99_pct, 2)],
          ["Worst day", `${pc(t.worst_day_pct)} ${dayMonth(t.worst_day_date)}`], ["Best day", `${pc(t.best_day_pct)} ${dayMonth(t.best_day_date)}`], ["Skew", sg(t.skew)], ["Excess kurtosis", sg(t.excess_kurtosis)],
          ["Max drawdown", pc(d.max_pct, 1)], ["Peak to trough", `${dayMonth(d.peak_date)} to ${dayMonth(d.trough_date)}`], ["Drawdown now", pc(d.current_pct, 1)], ["Sessions under water", d.sessions_underwater],
          ["Return per unit vol", sg(ra.sharpe_rf0)], ["Sortino", sg(ra.sortino_rf0)], ["Calmar", sg(ra.calmar)], ["Annualised return", pc(ra.return_annual_pct, 1)],
        ]} /><p className="note-t">{r.conventions}</p></div>
      </Block>
      <Block title={`Against ${b.name}`} sub={b.status === "AVAILABLE" ? `${b.sessions} shared sessions` : ""}>
        <div className="pad">{b.status === "AVAILABLE" ? <Kv rows={[
          ["Beta", n(b.beta)], ["Beta 60D", n(b.beta_60d)], ["Correlation", n(b.correlation)], ["R²", n(b.r_squared)],
          ["Alpha, annualised", pc(b.alpha_annual_pct, 1)], ["Excess return", pc(b.excess_return_pct, 1)], ["Tracking error", pct(b.tracking_error_pct)], ["Information ratio", sg(b.information_ratio)],
          ["Up capture", pct(b.up_capture_pct, 0)], ["Down capture", pct(b.down_capture_pct, 0)],
        ]} /> : <><Flag>Benchmark unavailable</Flag><p className="note-t">{b.reason}</p></>}</div>
      </Block>
      <div className="stack">
        <Block title="Liquidity and capacity" sub={`Exit at ${n(l.participation_pct, 0)}% of daily value`}>
          <div className="pad"><Kv rows={[["Average value 20D", `${n(l.adv_20d_cr, 1)} Cr`], ["Average value 60D", `${n(l.adv_60d_cr, 1)} Cr`], ["Median value 60D", `${n(l.median_60d_cr, 1)} Cr`], ["20D vs 60D", `${n(l.adv_20d_vs_60d)}x`], ["Price impact", `${n(l.amihud_bps_per_cr, 2)} bp per Cr`]]} /></div>
          <Table cols={[{ h: "Position", v: (y) => `₹${n(y.notional_cr, 0)} Cr`, text: true, bold: true }, { h: "Sessions to exit", v: (y) => (!isNum(y.days) ? "n/a" : y.days < 0.1 ? "under 0.1" : n(y.days, 1)) }]} rows={l.days_to_exit} />
        </Block>
        <Block title="Structure" sub="Trend fit, volume at price, anchored VWAP">
          <div className="pad"><Kv rows={[
            ["Trend 60D", fit(tq.fit_60d)], ["Trend 120D", fit(tq.fit_120d)], ["Efficiency 20D", n(tq.efficiency_20d)],
            ...(r.volume_profile ? [["Point of control", `${n(r.volume_profile.poc)} ${vs(r.volume_profile.poc)}`], ["Value area", `${n(r.volume_profile.value_area_low, 0)} to ${n(r.volume_profile.value_area_high, 0)}`]] as [string, string][] : []),
            ...r.anchored_vwap.map((a) => [`VWAP from ${a.anchor.toLowerCase()}`, `${n(a.vwap)} ${vs(a.vwap)}`] as [string, string]),
          ]} /></div>
        </Block>
      </div>
    </>
  );
}

const QUAD: Record<string, string> = { Leading: "Strong and accelerating", Improving: "Weak but accelerating", Weakening: "Strong but fading", Lagging: "Weak and fading" };

function breadthRows(b: QBreadth): [string, string][] {
  return [
    ["Advancing", n(b.advancing, 0)], ["Declining", n(b.declining, 0)], ["A/D ratio", n(b.ad_ratio)], ["Value in advancers", pct(b.up_value_share_pct)],
    ["Above EMA 20", pct(b.above_ema20_pct)], ["Above EMA 50", pct(b.above_ema50_pct)], ["Above EMA 200", pct(b.above_ema200_pct)], ["Within 5% of high", pct(b.within_5pct_of_high_pct)],
    ["New 52W highs", n(b.new_highs, 0)], ["New 52W lows", n(b.new_lows, 0)], ["RSI 70+", pct(b.rsi_over_70_pct)], ["RSI under 30", pct(b.rsi_under_30_pct)],
    ["Median 1D", pc(b.median_1d_pct)], ["Median 5D", pc(b.median_5d_pct)], ["Median 20D", pc(b.median_20d_pct)], ["Median 60D", pc(b.median_60d_pct)],
    ["Dispersion 1D", pct(b.dispersion_1d_pct, 2)], ["Dispersion 20D", pct(b.dispersion_20d_pct, 2)],
  ];
}

export function Internals() {
  const { data, error } = useMarketData<QuantInternals>("/quant/internals");
  const nav = useNavigate();
  if (!data) return <div className="pane full"><Empty>{error ?? "Loading market internals."}</Empty></div>;
  if (!data.available || !data.internals || data.internals.status !== "AVAILABLE") return <div className="pane full"><Empty>{data.reason ?? "The saved scan is too small for cross-sectional work."}</Empty></div>;
  const I = data.internals, rot = data.rotation!, hist = [...(data.breadth_history ?? [])].reverse();
  const open = (r: RotationRow) => { try { sessionStorage.setItem("nova.sector", r.sector); } catch { /* storage unavailable */ } nav("/screener"); };
  return (
    <div className="grid-quant">
      <Pane area="a" title="Market internals" sub={`${n(data.stocks, 0)} stocks, session of ${dayMonth(data.as_of)}. ${data.source ?? ""}`}>
        <div className="view"><div className="who">Nova read</div><h1>{I.regime.label}</h1><p>{I.regime.rule}</p></div>
        <ul className="reads pad">{(data.read ?? []).slice(1).map((c) => <li key={c.topic}><em>{c.topic}</em>{c.text}</li>)}</ul>
        <Block title="Breadth" sub="Whole scan"><div className="pad"><Kv rows={breadthRows(I.breadth)} /></div></Block>
        <Block title="Participation by liquidity" sub="Ranked on 20-day traded value">
          <Table rows={I.tiers} cols={[
            { h: "Tier", v: (r) => r.tier, text: true, bold: true }, { h: "Stocks", v: (r) => r.stocks }, { h: "Adv", v: (r) => r.advancing }, { h: "Dec", v: (r) => r.declining },
            { h: "> 50D", v: (r) => pct(r.above_ema50_pct, 0), heat: { max: 50, of: (r) => (r.above_ema50_pct ?? 50) - 50 } }, { h: "> 200D", v: (r) => pct(r.above_ema200_pct, 0), heat: { max: 50, of: (r) => (r.above_ema200_pct ?? 50) - 50 } },
            { h: "Med 20D", v: (r) => <Pct v={r.median_20d_pct} d={1} /> }, { h: "Med 60D", v: (r) => <Pct v={r.median_60d_pct} d={1} /> }, { h: "Value Cr", v: (r) => n(r.value_cr, 0) },
          ]} />
        </Block>
        <Block title="Turnover concentration" sub={`Top 10 hold ${pct(I.concentration.top10_share_pct)} of ₹${n(I.concentration.total_value_cr, 0)} Cr. HHI ${n(I.concentration.hhi, 0)}`}>
          <Table rows={I.concentration.top10} onRow={(r) => nav(`/?s=${encodeURIComponent(r.symbol)}`)} cols={[{ h: "Symbol", v: (r) => r.symbol, text: true, bold: true }, { h: "Value Cr", v: (r) => n(r.value_cr, 0) }, { h: "1D", v: (r) => <Pct v={r.return_1d} />, heat: { max: 6, of: (r) => r.return_1d } }]} />
        </Block>
      </Pane>
      <Pane area="b" title="Breadth trend and factors" sub={`${hist.length} saved sessions`}>
        <Block title="Share above moving averages" sub="Percent of the scan, one point per saved session">
          {hist.length >= 2 ? <LineChart label="Breadth trend" height={230} x={hist.map((h) => h.date)} domain={[0, 100]} fmt={(v) => `${n(v, 0)}%`}
            series={[{ name: "Above EMA 20", color: "var(--s1)", values: hist.map((h) => h.above_ema20_pct) }, { name: "Above EMA 50", color: "var(--s2)", values: hist.map((h) => h.above_ema50_pct) }, { name: "Above EMA 200", color: "var(--s3)", values: hist.map((h) => h.above_ema200_pct) }]} />
            : <Empty>One saved session so far. The trend builds as scans accumulate.</Empty>}
        </Block>
        <Block title="Session ledger" sub="Newest first. Sessions without a saved scan are absent, not interpolated">
          <Table rows={data.breadth_history ?? []} cols={[
            { h: "Session", v: (r: BreadthPoint) => dayMonth(r.date), text: true, bold: true }, { h: "Stocks", v: (r) => r.stocks }, { h: "Adv", v: (r) => r.advancing }, { h: "Dec", v: (r) => r.declining },
            { h: "> 20D", v: (r) => pct(r.above_ema20_pct, 0), heat: { max: 50, of: (r) => (r.above_ema20_pct ?? 50) - 50 } }, { h: "> 50D", v: (r) => pct(r.above_ema50_pct, 0), heat: { max: 50, of: (r) => (r.above_ema50_pct ?? 50) - 50 } },
            { h: "> 200D", v: (r) => pct(r.above_ema200_pct, 0), heat: { max: 50, of: (r) => (r.above_ema200_pct ?? 50) - 50 } }, { h: "Highs", v: (r) => r.new_highs }, { h: "Lows", v: (r) => r.new_lows }, { h: "Med 20D", v: (r) => <Pct v={r.median_20d_pct} d={1} /> },
          ]} />
        </Block>
        {(data.factor_windows ?? []).map((w) => (
          <Block key={w.base_date} title={`Factor returns, ${w.calendar_days} days`} sub={`Ranked ${dayMonth(w.base_date)}, measured to ${dayMonth(w.to_date)}. ${n(w.names, 0)} stocks, median ${pc(w.universe_median_pct)}`}>
            <Table rows={w.factors.filter((f) => f.status === "AVAILABLE")} cols={[
              { h: "Factor", v: (f: FactorRow) => f.factor, text: true, bold: true }, { h: "Top fifth", v: (f) => <Pct v={f.top_pct} /> }, { h: "Bottom fifth", v: (f) => <Pct v={f.bottom_pct} /> },
              { h: "Spread", v: (f) => `${sg(f.spread_pct)} pt`, heat: { max: 5, of: (f) => f.spread_pct } }, { h: "Rank IC", v: (f) => sg(f.ic, 3) }, { h: "Ordered", v: (f) => (f.monotonic ? "yes" : "no"), text: true },
            ]} />
            <p className="note-t pad">Out of sample: ranks use only the older scan. One window is one observation, not a backtest.{w.dropped_corporate_action_suspects > 0 && ` ${w.dropped_corporate_action_suspects} stocks dropped as suspected splits or bonuses.`}</p>
          </Block>
        ))}
        {!(data.factor_windows ?? []).length && <div className="pad"><Flag>No factor window</Flag><p className="note-t">Needs a saved scan at least three days older than the newest one.</p></div>}
      </Pane>
      <Pane area="c" title="Sector rotation" sub={`${rot.sectors.length} sectors against the median stock`} flag={data.sector_map ? undefined : "No sector map"}>
        {rot.sectors.length ? <>
          <Quadrants label="Sector rotation map" xLabel="Strength, 60D excess %" yLabel="Momentum, 20D pace %" corners={["Leading", "Improving", "Lagging", "Weakening"]}
            dots={rot.sectors.map((s) => ({ name: s.sector, x: s.rs_60d, y: s.rs_momentum, note: `${s.quadrant}: ${QUAD[s.quadrant].toLowerCase()}` }))} />
          <Table sortable onRow={open} rows={rot.sectors} cols={[
            { h: "Sector", v: (r: RotationRow) => r.sector.slice(0, 26), sort: (r) => r.sector, text: true, bold: true }, { h: "Quadrant", v: (r) => r.quadrant, sort: (r) => r.quadrant, text: true },
            { h: "Strength", v: (r) => sg(r.rs_60d, 1), sort: (r) => r.rs_60d, heat: { max: 15, of: (r) => r.rs_60d } }, { h: "Pace", v: (r) => sg(r.rs_momentum, 1), sort: (r) => r.rs_momentum, heat: { max: 8, of: (r) => r.rs_momentum } },
            { h: "5D", v: (r) => <Pct v={r.median_5d} d={1} />, sort: (r) => r.median_5d }, { h: "> 50D", v: (r) => pct(r.above_ema50_pct, 0), sort: (r) => r.above_ema50_pct }, { h: "Stocks", v: (r) => r.stocks, sort: (r) => r.stocks }, { h: "Leader", v: (r) => r.leader ?? "", text: true },
          ]} />
          <p className="note-t pad">{rot.method} Median stock: {pc(rot.universe_median_60d, 1)} over 60D, {pc(rot.universe_median_20d, 1)} over 20D.</p>
        </> : <Empty>No sector classification on disk. A refresh builds it.</Empty>}
      </Pane>
    </div>
  );
}
