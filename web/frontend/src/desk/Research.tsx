import { useMemo, useState } from "react";
import { useMarketData } from "../hooks/useMarketData";
import { isNum } from "../lib/format";
import LineChart from "./Chart";
import { Block, dayMonth, Empty, Flag, Kv, n, Pane, pc, sg, Table } from "./ui";

type N = number | null;
interface Curve { dates: string[]; long_short: N[]; long_only_excess: N[] }
interface Factor {
  factor: string; description: string; status: string; months: number; from?: string; to?: string; avg_names?: N;
  spread_annual_pct?: N; spread_vol_pct?: N; spread_ir?: N; spread_t?: N; hit_rate_pct?: N; spread_max_drawdown_pct?: N;
  long_only_excess_pct?: N; long_only_t?: N; long_only_net_pct?: N; ic_mean?: N; ic_t?: N; turnover_pct?: N;
  quintiles_annual_pct?: N[]; monotonic?: boolean; curve?: Curve;
}
interface BreadthSeries { dates: string[]; stocks: N[]; above_50_pct: N[]; above_200_pct: N[]; advancing: N[]; declining: N[]; new_highs: N[]; new_lows: N[]; ad_line: N[] }
interface Store { available: boolean; first: string | null; last: string | null; sessions: number; rows: number; symbols: number; actions?: number }
interface Overview {
  available: boolean; reason?: string; store: Store;
  backtest?: {
    status: string; reason?: string | null; sessions: number; store_from: string; store_to: string; top_n: number; cost_bps_one_way: number; rebalance: string;
    factors: Factor[]; caveats: string[]; adjustments?: Record<string, number>;
  };
  breadth?: { all: BreadthSeries; liquid: BreadthSeries; liquid_n: number };
}

const SPANS: [string, number][] = [["1Y", 252], ["3Y", 756], ["All", 0]];
// |t| of 2 is the usual bar for "unlikely to be noise"; shown as a word so nobody has to remember it
const strength = (t: N | undefined) => (!isNum(t) ? "n/a" : Math.abs(t) >= 3 ? "strong" : Math.abs(t) >= 2 ? "moderate" : "not significant");

export function Research() {
  const { data, error } = useMarketData<Overview>("/research/overview");
  const [pick, setPick] = useState<string | null>(null);
  const [span, setSpan] = useState(1);
  const [liquid, setLiquid] = useState(true);
  const B = data?.breadth ? (liquid ? data.breadth.liquid : data.breadth.all) : null;
  const view = useMemo(() => {
    if (!B) return null;
    const k = SPANS[span][1], cut = <T,>(a: T[]) => (k ? a.slice(-k) : a);
    return { x: cut(B.dates), a50: cut(B.above_50_pct), a200: cut(B.above_200_pct), net: cut(B.new_highs).map((h, i) => (isNum(h) && isNum(cut(B.new_lows)[i]) ? h - (cut(B.new_lows)[i] as number) : null)) };
  }, [B, span]);

  if (!data) return <div className="pane full"><Empty>{error ?? "Building research from the price store. The first build reads about three million rows and takes up to a minute."}</Empty></div>;
  if (!data.available) return <div className="pane full"><Empty>{data.reason}</Empty></div>;
  const bt = data.backtest!, ok = bt.factors.filter((f) => f.status === "AVAILABLE");
  const sel = ok.find((f) => f.factor === pick) ?? [...ok].sort((a, b) => (b.long_only_t ?? -9) - (a.long_only_t ?? -9))[0];
  const last = B && B.dates.length ? B.dates.length - 1 : -1;
  const adj = bt.adjustments ?? {};

  return (
    <div className="grid-research">
      <Pane area="a" title="Factor research" sub={bt.status === "AVAILABLE" ? `${ok[0]?.months ?? 0} monthly rebalances, ${dayMonth(ok[0]?.from)} ${ok[0]?.from?.slice(0, 4)} to ${dayMonth(ok[0]?.to)} ${ok[0]?.to?.slice(0, 4)}` : ""}>
        {bt.status !== "AVAILABLE" ? <div className="pad"><Flag>Backtest unavailable</Flag><p className="note-t">{bt.reason}</p></div> : <>
          <div className="view"><div className="who">Nova read</div>
            <h1>{sel.factor}: {isNum(sel.long_only_excess_pct) ? `${sg(sel.long_only_excess_pct, 1)}% a year over the universe` : "n/a"}, {strength(sel.long_only_t)}.</h1>
            <p>The {bt.top_n} most liquid NSE stocks, re-ranked every month-end and held equal weight. {sel.description} After {n(bt.cost_bps_one_way, 0)} bp one-way costs on {n(sel.turnover_pct, 0)}% monthly turnover the excess is {sg(sel.long_only_net_pct, 1)}% a year. A record of the past, not a forecast.</p>
          </div>
          <Table sortable rows={ok} onRow={(f) => setPick(f.factor)} isOn={(f) => f.factor === sel.factor} cols={[
            { h: "Factor", v: (f: Factor) => f.factor, sort: (f) => f.factor, text: true, bold: true },
            { h: "Top fifth vs universe", v: (f) => `${sg(f.long_only_excess_pct, 1)}%`, sort: (f) => f.long_only_excess_pct, heat: { max: 15, of: (f) => f.long_only_excess_pct } },
            { h: "Net of cost", v: (f) => `${sg(f.long_only_net_pct, 1)}%`, sort: (f) => f.long_only_net_pct },
            { h: "t", v: (f) => sg(f.long_only_t, 1), sort: (f) => f.long_only_t },
            { h: "Top minus bottom", v: (f) => `${sg(f.spread_annual_pct, 1)}%`, sort: (f) => f.spread_annual_pct, heat: { max: 30, of: (f) => f.spread_annual_pct } },
            { h: "t", v: (f) => sg(f.spread_t, 1), sort: (f) => f.spread_t },
            { h: "Rank IC", v: (f) => sg(f.ic_mean, 3), sort: (f) => f.ic_mean }, { h: "IC t", v: (f) => sg(f.ic_t, 1), sort: (f) => f.ic_t },
            { h: "Hit", v: (f) => `${n(f.hit_rate_pct, 0)}%`, sort: (f) => f.hit_rate_pct }, { h: "Turnover", v: (f) => `${n(f.turnover_pct, 0)}%`, sort: (f) => f.turnover_pct },
            { h: "Worst fall", v: (f) => pc(f.spread_max_drawdown_pct, 0), sort: (f) => f.spread_max_drawdown_pct },
          ]} />
          <Block title={`${sel.factor}: growth of 1`} sub="Top fifth against the universe, and top fifth against bottom fifth">
            <LineChart label={`${sel.factor} cumulative`} height={240} x={sel.curve!.dates} fmt={(v) => n(v)}
              series={[{ name: "Top fifth vs universe", color: "var(--s1)", values: sel.curve!.long_only_excess }, { name: "Top fifth vs bottom fifth", color: "var(--s2)", values: sel.curve!.long_short, width: 1.5 }]}
              marks={[{ y: 1, label: "Start" }]} />
          </Block>
          <Block title="Return by fifth" sub="Annualised, lowest-ranked fifth first">
            <Table rows={[sel]} cols={[...[0, 1, 2, 3, 4].map((i) => ({ h: i === 0 ? "Bottom" : i === 4 ? "Top" : `${i + 1}`, v: (f: Factor) => pc(f.quintiles_annual_pct?.[i], 1), heat: { max: 40, of: (f: Factor) => f.quintiles_annual_pct?.[i] } })), { h: "In order", v: (f: Factor) => (f.monotonic ? "yes" : "no"), text: true }]} />
          </Block>
          <Block title="What this test does and does not show">
            <ul className="reads pad">{bt.caveats.map((c) => <li key={c}>{c}</li>)}</ul>
          </Block>
        </>}
      </Pane>
      <Pane area="b" title="Market breadth, daily" sub={B && last >= 0 ? `${n(B.stocks[last], 0)} stocks on ${dayMonth(B.dates[last])}` : ""}>
        {view && view.x.length > 1 ? <>
          <div className="tool">
            <div className="seg">{SPANS.map(([t], i) => <button key={t} type="button" aria-pressed={span === i} onClick={() => setSpan(i)}>{t}</button>)}</div>
            <div className="seg"><button type="button" aria-pressed={liquid} onClick={() => setLiquid(true)}>Liquid {data.breadth!.liquid_n}</button><button type="button" aria-pressed={!liquid} onClick={() => setLiquid(false)}>All NSE</button></div>
          </div>
          <Block title="Share above moving averages" sub="Percent of stocks trading that day">
            <LineChart label="Daily breadth" height={230} x={view.x} domain={[0, 100]} fmt={(v) => `${n(v, 0)}%`}
              series={[{ name: "Above 50-day", color: "var(--s1)", values: view.a50, width: 1.5 }, { name: "Above 200-day", color: "var(--s2)", values: view.a200, width: 1.5 }]} />
          </Block>
          <Block title="New highs minus new lows" sub="252-session highs less lows, per day">
            <LineChart label="Net new highs" height={190} x={view.x} fmt={(v) => n(v, 0)} series={[{ name: "Net new highs", color: "var(--s1)", values: view.net, width: 1.5 }]} marks={[{ y: 0, label: "" }]} />
          </Block>
          <Block title="Latest session">
            <div className="pad"><Kv rows={[["Above 50-day", `${n(B!.above_50_pct[last], 1)}%`], ["Above 200-day", `${n(B!.above_200_pct[last], 1)}%`], ["Advancing", n(B!.advancing[last], 0)], ["Declining", n(B!.declining[last], 0)], ["New highs", n(B!.new_highs[last], 0)], ["New lows", n(B!.new_lows[last], 0)]]} /></div>
          </Block>
        </> : <Empty>The price store needs about a year of sessions before breadth can be drawn.</Empty>}
        <Block title="Price store" sub="NSE bhavcopy and corporate actions, held locally">
          <div className="pad"><Kv rows={[
            ["Sessions", n(data.store.sessions, 0)], ["From", `${dayMonth(data.store.first)} ${data.store.first?.slice(0, 4)}`], ["To", `${dayMonth(data.store.last)} ${data.store.last?.slice(0, 4)}`],
            ["Symbols ever traded", n(data.store.symbols, 0)], ["Daily bars", n(data.store.rows, 0)],
            ["Splits, bonuses, rights applied", n(adj.splits_bonuses_rights_applied, 0)], ["Listed but not matching price", n(adj.splits_bonuses_rights_unverified, 0)],
            ["Dividends added", n(adj.dividends_applied, 0)], ["Unexplained moves dropped", n(adj.unexplained_moves_dropped, 0)],
          ]} /></div>
        </Block>
      </Pane>
    </div>
  );
}

export interface Delivery {
  status: string; reason?: string; as_of?: string; last_pct?: N; avg_5d_pct?: N; avg_20d_pct?: N; avg_60d_pct?: N; avg_20d_percentile?: N;
  delivered_value_20d_cr?: N; delivered_value_60d_cr?: N; trend?: string; trend_rule?: string;
}
export interface CorpAction { date: string; kind: string; subject: string; factor: number; dividend: number; applied: boolean; note: string }

/** Delivery and corporate-action blocks for one stock, from the local price store. */
export function StoreBlocks({ delivery, actions, source }: { delivery?: Delivery; actions?: CorpAction[]; source?: string }) {
  if (!delivery) return null;
  const acts = [...(actions ?? [])].reverse();
  return (
    <div className="stack">
      <Block title="Delivery" sub={delivery.status === "AVAILABLE" ? `Share of volume taken into delivery, to ${dayMonth(delivery.as_of)}` : ""}>
        <div className="pad">{delivery.status === "AVAILABLE" ? <>
          <Kv rows={[["Last session", `${n(delivery.last_pct, 1)}%`], ["Average 5D", `${n(delivery.avg_5d_pct, 1)}%`], ["Average 20D", `${n(delivery.avg_20d_pct, 1)}%`], ["Average 60D", `${n(delivery.avg_60d_pct, 1)}%`],
            ["20D against own year", isNum(delivery.avg_20d_percentile) ? `${n(delivery.avg_20d_percentile, 0)}th percentile` : "n/a"], ["Delivered value 20D", `${n(delivery.delivered_value_20d_cr, 1)} Cr`], ["Delivered value 60D", `${n(delivery.delivered_value_60d_cr, 1)} Cr`], ["Trend", delivery.trend ?? "n/a"]]} />
          <p className="note-t">{delivery.trend_rule}</p>
        </> : <><Flag>No delivery data</Flag><p className="note-t">{delivery.reason}</p></>}</div>
      </Block>
      <Block title="Corporate actions" sub={source}>
        {acts.length ? <Table rows={acts.slice(0, 12)} cols={[
          { h: "Ex-date", v: (a: CorpAction) => `${dayMonth(a.date)} ${a.date.slice(2, 4)}`, text: true, bold: true }, { h: "Action", v: (a) => a.subject.slice(0, 46), text: true },
          { h: "Effect", v: (a) => (a.kind === "dividend" ? `₹${n(a.dividend)}` : a.applied ? `x${n(a.factor, 4)}` : "") },
          { h: "Status", v: (a) => (a.applied ? "Applied" : <Flag>Not applied</Flag>), text: true },
        ]} /> : <div className="pad note-t">None on file inside the stored window.</div>}
      </Block>
    </div>
  );
}
