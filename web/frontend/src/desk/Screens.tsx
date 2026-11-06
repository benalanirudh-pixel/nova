import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isNum } from "../lib/format";
import { sd } from "./analytics";
import { headline, useDesk, type FlowRow, type ScanRow, type SectorRow } from "./data";
import { dayMonth, Empty, Flag, Kv, n, Pane, Pct, sg, Sgn, Table, type Col } from "./ui";

const fiiDate = (d: unknown) => String(d ?? "").split("-").slice(0, 2).map((x, i) => (i ? x : +x)).join(" ");

export function Flows() {
  const { flows, brief, niftyBars } = useDesk();
  const F = flows?.metrics;
  if (!flows) return <div className="pane full"><Empty>Loading flow history.</Empty></div>;
  if (!F) return <div className="pane full"><Empty>No flow metrics in the saved report yet.</Empty></div>;
  const closes = Object.fromEntries(niftyBars.map((b, i) => [b[0], [b[4], i ? (b[4] / niftyBars[i - 1][4] - 1) * 100 : null] as const]));
  let cum = 0;
  const rows = [...flows.rows].sort((a, b) => (a.date < b.date ? -1 : 1)).map((r) => {
    const scoped = r.market_scope === flows.target_scope;
    if (scoped) cum += r.fii_net ?? 0;
    return { ...r, scoped, cum: scoped ? cum : null, close: closes[r.date]?.[0], day: closes[r.date]?.[1] ?? null };
  }).reverse();
  const inScope = rows.filter((r) => r.scoped), recent = inScope.slice(0, 20), paired = inScope.filter((r) => isNum(r.day)), xs = paired.map((r) => r.fii_net), ys = paired.map((r) => r.day!);
  const mean = (a: number[]) => a.reduce((p, c) => p + c, 0) / a.length, mx = mean(xs), my = mean(ys);
  const cor = paired.length > 2 ? xs.reduce((p, x, i) => p + (x - mx) * (ys[i] - my), 0) / ((xs.length - 1) * sd(xs) * sd(ys)) : null;
  const sells = paired.filter((r) => r.fii_net < 0);
  const primary = (r: FlowRow) => r.source?.startsWith("NSE_PRIMARY");
  const w: [string, number, number, number, number, number][] = [["5D", F.fii_5d, F.dii_5d, F.combined_5d, F.fii_avg_5d, F.dii_avg_5d], ["10D", F.fii_10d, F.dii_10d, F.combined_10d, F.fii_avg_10d, F.dii_avg_10d], ["20D", F.fii_20d, F.dii_20d, F.combined_20d, F.fii_avg_20d, F.dii_avg_20d]];
  return (
    <div className="grid-flows">
      <Pane area="rl" title="Rolling flow" sub="₹ Cr net, NSE, BSE and MSEI combined">
        <Table cols={[{ h: "Window", v: (r) => r[0], text: true, bold: true }, { h: "FII", v: (r) => <Sgn v={r[1]} /> }, { h: "DII", v: (r) => <Sgn v={r[2]} /> }, { h: "Combined", v: (r) => <Sgn v={r[3]} /> }, { h: "FII per day", v: (r) => <Sgn v={r[4]} /> }, { h: "DII per day", v: (r) => <Sgn v={r[5]} /> }]} rows={w} />
      </Pane>
      <Pane area="tb" title="Daily ledger" sub={`${rows.length} sessions, newest first`}>
        <Table cols={[
          { h: "Date", v: (r) => dayMonth(r.date), text: true, bold: true }, { h: "Nifty", v: (r) => (isNum(r.close) ? n(r.close, 0) : "") }, { h: "1D", v: (r) => (isNum(r.day) ? <Pct v={r.day} /> : "") }, { h: "FII buy", v: (r) => n(r.fii_buy, 0) }, { h: "FII sell", v: (r) => n(r.fii_sell, 0) },
          { h: "FII net", v: (r) => <Sgn v={r.fii_net} />, heat: { max: 12000, of: (r) => r.fii_net } }, { h: "Cum FII", v: (r) => (r.cum == null ? "" : <Sgn v={r.cum} />) }, { h: "DII buy", v: (r) => n(r.dii_buy, 0) }, { h: "DII sell", v: (r) => n(r.dii_sell, 0) },
          { h: "DII net", v: (r) => <Sgn v={r.dii_net} />, heat: { max: 12000, of: (r) => r.dii_net } }, { h: "Net", v: (r) => <Sgn v={r.combined_net} /> }, { h: "Source", v: (r) => (primary(r) ? "NSE primary" : <Flag>{r.source?.split(":").pop()?.slice(0, 16)}</Flag>), text: true },
        ]} rows={rows} />
      </Pane>
      <Pane area="st" title="Assessment" sub={`Latest ${dayMonth(F.latest_date ?? rows[0]?.date)}`}>
        <div className="view"><div className="who">Nova read</div>
          <ul className="reads">
            <li>FIIs have been {F.fii_streak_direction.toLowerCase()} {F.fii_streak_days} sessions running, with {sg(F.fii_20d, 0)} Cr over 20 days.</li>
            <li>DIIs recorded {sg(F.dii_20d, 0)} Cr over the same window.</li>
          </ul></div>
        <div className="pad"><Kv rows={[
          ...(brief?.fii_dii ?? []).map((x) => [`${/FII/.test(x.category) ? "FII" : "DII"} ${fiiDate(x.date)}`, sg(x.net_cr, 0)] as [string, string]),
          ["FII streak", `${F.fii_streak_direction.toLowerCase()} ${F.fii_streak_days}d`], ["DII streak", `${F.dii_streak_direction.toLowerCase()} ${F.dii_streak_days}d`], ["FII buy days 20D", `${recent.filter((r) => r.fii_net > 0).length} of ${recent.length}`], ["DII buy days 20D", `${recent.filter((r) => r.dii_net > 0).length} of ${recent.length}`],
          ["Largest FII buy", sg(Math.max(...inScope.map((r) => r.fii_net)), 0)], ["Largest FII sell", sg(Math.min(...inScope.map((r) => r.fii_net)), 0)], ["FII net vs Nifty 1D", cor == null ? "n/a" : `r = ${sg(cor)}`], ["Nifty up on FII sell days", `${sells.filter((r) => r.day! > 0).length} of ${sells.length}`],
          ["NSE-primary days", `${F.primary_source_sessions_in_target_window} of ${F.target_sessions}`], ["Signal allowed", flows.summary?.signal_allowed ? "yes" : "no"],
        ]} /></div>
      </Pane>
    </div>
  );
}

const PRESETS: Record<string, [string, (r: ScanRow) => boolean]> = {
  all: ["All", () => true], high: ["New 52W high", (r) => r.dh === 0], near: ["Within 5% of high", (r) => isNum(r.dh) && Math.abs(r.dh) <= 5], vol: ["Rel vol 2x+", (r) => (r.rv ?? 0) >= 2], up: ["Strong up", (r) => r.t === "Strong up"],
  rs: ["RS leaders", (r) => (r.rs20 ?? 0) >= 10], hot: ["RSI 70+", (r) => (r.rsi ?? 0) >= 70], cold: ["RSI under 30", (r) => isNum(r.rsi) && r.rsi <= 30], down: ["Strong down", (r) => r.t === "Strong down"],
};

export function Screener() {
  const { stocks, scan } = useDesk();
  const nav = useNavigate();
  const [preset, setPreset] = useState("all");
  const [q, setQ] = useState("");
  const [sector, setSector] = useState(() => { // handed over once by a click on the Sectors screen
    try { const s = sessionStorage.getItem("nova.sector") ?? ""; sessionStorage.removeItem("nova.sector"); return s; } catch { return ""; }
  });
  const sectors = useMemo(() => [...new Set(stocks.map((r) => r.x).filter(Boolean))].sort(), [stocks]);
  const rows = useMemo(() => {
    const t = q.trim().toUpperCase();
    return stocks.filter((r) => PRESETS[preset][1](r) && (!sector || r.x === sector) && (!t || r.s.includes(t) || r.n.toUpperCase().includes(t)));
  }, [stocks, preset, sector, q]);
  const cols: Col<ScanRow>[] = [
    { h: "Symbol", v: (r) => r.s, sort: (r) => r.s, text: true, bold: true }, { h: "Company", v: (r) => r.n.slice(0, 30), sort: (r) => r.n, text: true }, { h: "Sector", v: (r) => r.x.slice(0, 22), sort: (r) => r.x, text: true }, { h: "Last", v: (r) => n(r.p), sort: (r) => r.p },
    { h: "1D", v: (r) => <Pct v={r.r1} />, sort: (r) => r.r1, heat: { max: 8, of: (r) => r.r1 } }, { h: "5D", v: (r) => <Pct v={r.r5} />, sort: (r) => r.r5, heat: { max: 15, of: (r) => r.r5 } }, { h: "20D", v: (r) => <Pct v={r.r20} d={1} />, sort: (r) => r.r20, heat: { max: 30, of: (r) => r.r20 } }, { h: "60D", v: (r) => <Pct v={r.r60} d={1} />, sort: (r) => r.r60, heat: { max: 50, of: (r) => r.r60 } },
    { h: "RS 20D", v: (r) => sg(r.rs20, 1), sort: (r) => r.rs20 }, { h: "vs 200D", v: (r) => <Pct v={r.e200} d={1} />, sort: (r) => r.e200 }, { h: "RSI", v: (r) => n(r.rsi, 0), sort: (r) => r.rsi }, { h: "ATR%", v: (r) => n(r.atr), sort: (r) => r.atr }, { h: "Rel vol", v: (r) => `${n(r.rv, 1)}x`, sort: (r) => r.rv }, { h: "Value Cr", v: (r) => n(r.val, 0), sort: (r) => r.val }, { h: "Trend", v: (r) => r.t, text: true }, { h: "Score", v: (r) => n(r.sc, 0), sort: (r) => r.sc },
  ];
  if (!scan) return <div className="pane full"><Empty>Loading scan.</Empty></div>;
  if (!scan.available) return <div className="pane full"><Empty>No complete scan on disk. Run a refresh to build one.</Empty></div>;
  const partial = scan.newest_stocks < 1500;
  return (
    <section className="pane full" aria-label="Screener">
      <div className="ph"><h2>Screener</h2><span className="s">Complete scan, {dayMonth(scan.as_of)}. A screen is a filter, not a recommendation</span>{partial && <Flag>Newest scan partial, {scan.newest_stocks} stocks</Flag>}</div>
      <div className="bar">
        {Object.entries(PRESETS).map(([k, v]) => <button key={k} type="button" className="chip" aria-pressed={preset === k} onClick={() => setPreset(k)}>{v[0]}</button>)}
        <input value={q} onChange={(e) => setQ(e.target.value)} size={13} aria-label="Filter by symbol or name" placeholder="Filter" />
        <select value={sector} onChange={(e) => setSector(e.target.value)} aria-label="Sector"><option value="">All sectors</option>{sectors.map((s) => <option key={s}>{s}</option>)}</select>
        <span className="cnt">{n(rows.length, 0)} of {n(stocks.length, 0)}, first 300</span>
      </div>
      <div className="body"><Table cols={cols} rows={rows} sortable limit={300} onRow={(r) => nav(`/?s=${encodeURIComponent(r.s)}`)} /></div>
    </section>
  );
}

export function Sectors() {
  const { overview, scan } = useDesk();
  const nav = useNavigate();
  const live = [...(overview?.live?.sectors ?? [])].sort((a, b) => (b.change_percent ?? 0) - (a.change_percent ?? 0)) as (NonNullable<NonNullable<typeof overview>["live"]>["sectors"] & object)[number][];
  const open = (r: SectorRow) => { try { sessionStorage.setItem("nova.sector", r.n); } catch { /* storage unavailable */ } nav("/screener"); };
  type Live = (typeof live)[number] & { advances?: number; declines?: number; year_high?: number };
  return (
    <div className="grid-sec">
      <Pane area="a" title="NSE indices" sub={overview?.live?.as_of ? `Live at ${overview.live.as_of}` : "Live data unavailable"}>
        {live.length ? <Table cols={[{ h: "Index", v: (r: Live) => r.name.replace("NIFTY ", ""), text: true, bold: true }, { h: "Last", v: (r) => n(r.price) }, { h: "Chg", v: (r) => <Pct v={r.change_percent} />, heat: { max: 2.5, of: (r) => r.change_percent } }, { h: "Adv", v: (r) => r.advances ?? "" }, { h: "Dec", v: (r) => r.declines ?? "" }, { h: "52W hi", v: (r) => (r.year_high && isNum(r.price) ? <Pct v={(r.price / r.year_high - 1) * 100} d={1} /> : "") }]} rows={live as Live[]} /> : <Empty>NSE live sectors unavailable. {overview?.live?.error}</Empty>}
      </Pane>
      <Pane area="b" title="Stock sectors" sub={`Equal-weight from the ${dayMonth(scan?.as_of)} scan`} flag={scan?.sector_map_as_of && scan.sector_map_as_of !== scan.as_of ? `Map dated ${dayMonth(scan.sector_map_as_of)}` : undefined}>
        <Table sortable onRow={open} rows={scan?.sectors ?? []} cols={[
          { h: "Sector", v: (r: SectorRow) => r.n, sort: (r) => r.n, text: true, bold: true }, { h: "Stocks", v: (r) => r.c, sort: (r) => r.c }, { h: "1D", v: (r) => <Pct v={r.r1} />, sort: (r) => r.r1, heat: { max: 3, of: (r) => r.r1 } }, { h: "5D", v: (r) => <Pct v={r.r5} />, sort: (r) => r.r5, heat: { max: 10, of: (r) => r.r5 } }, { h: "20D", v: (r) => <Pct v={r.r20} d={1} />, sort: (r) => r.r20, heat: { max: 15, of: (r) => r.r20 } }, { h: "60D", v: (r) => <Pct v={r.r60} d={1} />, sort: (r) => r.r60, heat: { max: 25, of: (r) => r.r60 } },
          { h: "> 200D", v: (r) => `${n(r.a200, 0)}%`, sort: (r) => r.a200, heat: { max: 100, of: (r) => r.a200 - 50 } }, { h: "RSI", v: (r) => n(r.rsi, 0), sort: (r) => r.rsi }, { h: "Value Cr", v: (r) => n(r.val, 0), sort: (r) => r.val }, { h: "Best 5D", v: (r) => r.best, text: true }, { h: "Worst 5D", v: (r) => r.worst, text: true },
        ]} />
      </Pane>
    </div>
  );
}

export function Note() {
  const { brief, niftyRisk, overview } = useDesk();
  if (!brief) return <div className="pane full"><Empty>Loading market note.</Empty></div>;
  const g = brief.global;
  const assets: [string, string, number | null | undefined][] = [
    ...(g.indices ?? []).map((i) => [i.name, n(i.last), i.change_pct] as [string, string, number]),
    ...(g.commodities ?? []).map((i) => [i.name, `$${n(i.price)}`, i.change_pct] as [string, string, number | null]),
    ...(g.fx ?? []).map((i) => [i.pair, n(i.rate, (i.rate ?? 0) < 10 ? 4 : 2), i.change_pct] as [string, string, number | null]),
  ];
  return (
    <div className="grid-note">
      <Pane area="c" title="Market note" sub="Generated from the data on this screen">
        <div className="view bare"><div className="who">Nova read</div><h1>{headline(niftyRisk?.ret(5), overview?.breadth?.above_ema200_percent as number | undefined)}</h1></div>
        <ul className="reads pad">{brief.morning_call.map((c, i) => <li key={i}><em>{c.topic}</em>{c.text}</li>)}</ul>
      </Pane>
      <Pane area="g" title="Cross-asset" sub="Global close, commodities, FX">
        <Table cols={[{ h: "Instrument", v: (r) => r[0], text: true }, { h: "Last", v: (r) => r[1] }, { h: "Chg", v: (r) => <Pct v={r[2]} />, heat: { max: 3, of: (r) => r[2] } }]} rows={assets} />
      </Pane>
      <Pane area="n" title="Headlines" sub={`${brief.news?.length ?? 0} items`}>
        {brief.news ? <Table cols={[{ h: "Headline", v: (r) => r.title, text: true }, { h: "Source", v: (r) => r.source ?? "", text: true }]} rows={brief.news} /> : <Empty>News unavailable. {brief.errors.news}</Empty>}
      </Pane>
    </div>
  );
}

export function AuditScreen() {
  const { audit, flags } = useDesk();
  if (!audit) return <div className="pane full"><Empty>Loading audit.</Empty></div>;
  const engines = Object.entries(audit.data_availability), ready = engines.filter((e) => e[1] !== "NOT AVAILABLE").length;
  return (
    <div className="grid-audit">
      <Pane area="f" title="Data flags" sub={`${flags.length} open`}><Table cols={[{ h: "Item", v: (r) => r[0], text: true, bold: true }, { h: "State", v: (r) => r[1], text: true }]} rows={flags} /></Pane>
      <Pane area="e" title="Engines" sub={`${ready} of ${engines.length} ready. Report ${audit.report_saved_at?.slice(0, 16).replace("T", " ") ?? "n/a"}`}><Table cols={[{ h: "Engine", v: (r) => r[0].replaceAll("_", " "), text: true }, { h: "State", v: (r) => (r[1] === "NOT AVAILABLE" ? <Flag>not available</Flag> : r[1].toLowerCase()), text: true }]} rows={engines} /></Pane>
      <Pane area="p" title="Decision policy" sub="Shown so it can be checked"><Table cols={[{ h: "Rule", v: (r) => r[0].replaceAll("_", " ").toLowerCase(), text: true }, { h: "Value", v: (r) => String(r[1]) }]} rows={Object.entries(audit.decision_policy)} /></Pane>
    </div>
  );
}
