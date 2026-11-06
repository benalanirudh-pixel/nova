import { useSearchParams } from "react-router-dom";
import { isNum } from "../lib/format";
import type { FnoDesk } from "../lib/types";
import { type FnoRow } from "./analytics";
import { useDesk } from "./data";
import { Empty, Flag, Kv, n, Pane, Pct, pc, sg, Sgn, Table, type Col } from "./ui";

const LIST = ["NIFTY", "BANKNIFTY", "SENSEX"];
const blank = (v: number | null | undefined, d = 2) => ((v ?? 0) > 0 ? n(v, d) : "");

export default function Fno() {
  const { chains, models, analysis } = useDesk();
  const [params, setParams] = useSearchParams();
  const inst = LIST.includes((params.get("i") ?? "").toUpperCase()) ? params.get("i")!.toUpperCase() : "NIFTY";
  const C = chains[inst], A = models[inst], M = C?.metrics, T = C?.technicals;
  if (!C) return <div className="pane full"><Empty>Loading option chain.</Empty></div>;
  if (!M || !T || !A) return <div className="pane full"><Empty>Option chain unavailable. {Object.values(C.errors ?? {})[0]}</Empty></div>;
  const R = inst === "NIFTY" ? analysis?.derivatives?.nifty : inst === "BANKNIFTY" ? analysis?.derivatives?.bank_nifty : null;
  const rows = [...A.rows].reverse(), spot = C.spot!;
  const mv = Math.max(...rows.flatMap((r) => [Math.abs(r.call_change_oi ?? 0), Math.abs(r.put_change_oi ?? 0)]), 1), mo = Math.max(...rows.flatMap((r) => [r.call_oi ?? 0, r.put_oi ?? 0]), 1);
  const cross: Col<FnoDesk>[] = [
    { h: "Index", v: (c) => c.name, text: true, bold: true }, { h: "Spot", v: (c) => n(c.spot) }, { h: "Expiry", v: (c) => c.expiry }, { h: "Days", v: (c) => c.metrics?.days_to_expiry },
    { h: "OI PCR", v: (c) => n(c.metrics?.pcr_oi) }, { h: "Vol PCR", v: (c) => n(c.metrics?.pcr_volume) }, { h: "ATM IV", v: (c) => n(c.metrics?.atm_iv, 1) }, { h: "RV 20D", v: (c) => n(c.technicals?.rv20, 1) },
    { h: "IV − RV", v: (c) => (isNum(c.metrics?.atm_iv) && isNum(c.technicals?.rv20) ? <Sgn v={c.metrics!.atm_iv! - c.technicals!.rv20} d={1} /> : "n/a") }, { h: "Skew", v: (c) => sg(c.metrics?.skew, 1) },
    { h: "Straddle %", v: (c) => (isNum(c.metrics?.straddle) && isNum(c.spot) ? n((c.metrics!.straddle! / c.spot) * 100) : "n/a") }, { h: "Max pain vs spot", v: (c) => (isNum(c.metrics?.max_pain) && isNum(c.spot) ? <Pct v={(c.metrics!.max_pain! / c.spot - 1) * 100} d={1} /> : "n/a") },
    { h: "Call wall", v: (c) => n(c.metrics?.resistance[0]?.strike, 0) }, { h: "Put wall", v: (c) => n(c.metrics?.support[0]?.strike, 0) },
  ];
  const chain: Col<FnoRow>[] = [
    { h: "OI chg", v: (r) => <Sgn v={r.call_change_oi} />, heat: { max: mv, of: (r) => r.call_change_oi } }, { h: "OI", v: (r) => n(r.call_oi, 0), heat: { max: mo, of: (r) => -(r.call_oi ?? 0) } }, { h: "Volume", v: (r) => n(r.call_volume, 0) },
    { h: "IV", v: (r) => blank(r.call_iv, 1) }, { h: "Delta", v: (r) => ((r.call_iv ?? 0) > 0 ? n(r.dc) : "") }, { h: "LTP", v: (r) => blank(r.call_ltp) },
    { h: "Strike", v: (r) => n(r.strike, 0), bold: true },
    { h: "LTP", v: (r) => blank(r.put_ltp) }, { h: "Delta", v: (r) => ((r.put_iv ?? 0) > 0 ? n(r.dp) : "") }, { h: "IV", v: (r) => blank(r.put_iv, 1) }, { h: "Volume", v: (r) => n(r.put_volume, 0) },
    { h: "OI", v: (r) => n(r.put_oi, 0), heat: { max: mo, of: (r) => r.put_oi ?? 0 } }, { h: "OI chg", v: (r) => <Sgn v={r.put_change_oi} />, heat: { max: mv, of: (r) => r.put_change_oi } },
    { h: "PCR", v: (r) => (r.call_oi ? n((r.put_oi ?? 0) / r.call_oi) : "") }, { h: "Net γ %", v: (r) => sg(r.gp, 1) },
  ];
  type Lv = [string, number];
  const levels = ([["Call wall", M.resistance[0]?.strike], ["Range high", M.breakeven_high], ["Spot", spot], ["Forward", A.fwd], ["Max pain", M.max_pain], ["Range low", M.breakeven_low], ["Put wall", M.support[0]?.strike], ["Gamma flip", A.flip], ["+1σ", A.fwd + A.sigmaMove], ["−1σ", A.fwd - A.sigmaMove]] as [string, number | null | undefined][])
    .filter((y): y is Lv => isNum(y[1])).sort((a, b) => b[1] - a[1]);
  const lag = Math.abs(A.basis) / spot > 0.001;
  const iv = M.atm_iv!, rv = T.rv20;
  const wallShare = (oi: number | null | undefined, total: number) => (isNum(oi) && total ? n((oi / total) * 100, 1) : "n/a");
  const read = [
    isNum(M.max_pain) ? `Spot sits ${pc((spot / M.max_pain - 1) * 100, 1)} from max pain with ${M.days_to_expiry} days left.` : null,
    `Implied vol ${iv >= rv ? "above" : "below"} realized by ${n(Math.abs(iv - rv), 1)} pts.`,
    M.support[0] && M.resistance[0] ? `Heaviest walls ${n(M.support[0].strike, 0)} and ${n(M.resistance[0].strike, 0)} hold ${wallShare(M.support[0].oi, M.put_oi)}% and ${wallShare(M.resistance[0].oi, M.call_oi)}% of side OI.` : null,
    `OI-gamma is net ${A.callHeavy ? "call" : "put"}-weighted in the fetched strikes.`,
  ].filter(Boolean) as string[];
  const unusual = (R?.unusual_activity ?? []) as { option_type?: string; strike?: number; change_oi?: number; volume_oi_ratio?: number; premium_change?: number }[];
  return (
    <div className="grid-fno">
      <section className="pane" style={{ gridArea: "hd" }}>
        <div className="qh">
          <div><h1>{C.name}</h1><div className="sub">{C.source}, expiry {C.expiry}, {M.days_to_expiry} days</div></div>
          <div className="px">{n(spot)}</div>
          <span className="seg" role="group" aria-label="Instrument">{LIST.map((i) => <button key={i} type="button" aria-pressed={i === inst} onClick={() => setParams({ i })}>{chains[i]?.name ?? i}</button>)}</span>
          <div className="q">{[["Forward", n(A.fwd, 0)], ["Basis", sg(A.basis, 1)], ["ATM IV", `${n(iv, 1)}%`], ["IV less RV", sg(iv - rv, 1)], ["Straddle", n(M.straddle, 0)], ["1σ to expiry", `±${n(A.sigmaMove, 0)}`], ["Max pain", n(M.max_pain, 0)]].map(([k, v]) => <div key={k}><u>{k}</u><b>{v}</b></div>)}</div>
        </div>
      </section>
      <Pane area="cx" title="Index comparison" sub="Near-month chain per index"><Table cols={cross} rows={LIST.map((i) => chains[i]).filter((c): c is FnoDesk => !!c)} isOn={(c) => c === C} /></Pane>
      <Pane area="ch" title="Option chain with delta and net gamma" sub={`${rows.length} strikes. Delta from each strike’s IV`}><Table cols={chain} rows={rows} groups={[["Calls", 6], ["", 1], ["Puts", 6], ["", 2]]} isOn={(r) => r.strike === M.atm} /></Pane>
      <section className="pane" style={{ gridArea: "rg" }} aria-label="Positioning">
        <div className="body">
          <div className="view tight"><div className="who">Nova read</div><ul className="reads">{read.map((t) => <li key={t}>{t}</li>)}</ul></div>
          {lag && <div className="pad"><Flag>Parity gap</Flag><p className="note-t">Forward from ATM parity is {sg(A.basis, 0)} pts from spot. Option last trades may lag the index, so probabilities use the forward.</p></div>}
          <div className="bh pd"><h3>Implied probabilities</h3><span>Close above level at expiry. ATM IV {n(iv, 1)}%</span></div>
          <Table cols={[{ h: "Level", v: (y: Lv) => y[0], text: true, bold: true }, { h: "Price", v: (y) => n(y[1], 0) }, { h: "Dist", v: (y) => <Pct v={(y[1] / spot - 1) * 100} d={1} /> }, { h: "σ", v: (y) => sg(A.zOf(y[1])) }, { h: "P(above)", v: (y) => `${n(A.above(y[1]), 0)}%` }]} rows={levels} isOn={(y) => y[0] === "Spot"} />
          <div className="bh pd"><h3>Skew by moneyness</h3><span>OTM side vs ATM</span></div>
          <Table cols={[{ h: "Moneyness", v: (y) => `${y.m > 0 ? "+" : y.m < 0 ? "−" : ""}${Math.abs(y.m)}%`, text: true, bold: true }, { h: "Strike", v: (y) => n(y.k, 0) }, { h: "IV", v: (y) => blank(y.iv, 1) }, { h: "vs ATM", v: (y) => (y.spread == null ? "" : sg(y.spread, 1)) }]} rows={A.smile} />
          <div className="bh pd"><h3>OI concentration</h3><span>Share of side OI, fetched strikes</span></div>
          <Table cols={[{ h: "Call strike", v: (i: number) => n(A.topC[i].strike, 0), text: true, bold: true }, { h: "Share", v: (i) => `${wallShare(A.topC[i].call_oi, M.call_oi)}%` }, { h: "Added", v: (i) => <Sgn v={A.topC[i].call_change_oi} /> }, { h: "Put strike", v: (i) => n(A.topP[i].strike, 0), bold: true }, { h: "Share", v: (i) => `${wallShare(A.topP[i].put_oi, M.put_oi)}%` }, { h: "Added", v: (i) => <Sgn v={A.topP[i].put_change_oi} /> }]} rows={A.topC.map((_, i) => i)} />
          <div className="bh pd"><h3>PCR by distance from spot</h3><span>Fetched strikes only</span></div>
          <Table cols={[{ h: "Band", v: (y: [string, ReturnType<typeof A.band>]) => y[0], text: true, bold: true }, { h: "Call OI", v: (y) => n(y[1].c, 0) }, { h: "Put OI", v: (y) => n(y[1].u, 0) }, { h: "PCR", v: (y) => n(y[1].pcr) }]} rows={[["Within 1%", A.band(0, 1)], ["1% to 2%", A.band(1, 2)], ["2% to 3%", A.band(2, 3.5)]]} />
          <div className="bh pd"><h3>Gamma</h3><span>Model, not a dealer position</span></div>
          <div className="pad" style={{ paddingTop: 4 }}>
            <Kv rows={[["Gamma flip", A.flip ? n(A.flip, 0) : "none in window"], ["Net OI-gamma", `${sg(A.netPct, 1)}%`], ["Implied daily move", `±${n(A.dayMove, 0)}`], ["Annualized basis", pc(A.carry, 1)]]} />
            <div style={{ marginTop: 6 }}><Flag>Assumes dealers long calls, short puts</Flag></div>
          </div>
          {R && <div className="pad" style={{ paddingTop: 0 }}><Flag>PCR disagrees</Flag><p className="note-t">{n(M.pcr_oi)} here, {n(R.oi_pcr)} in the saved report.</p></div>}
          {unusual.length > 0 && <><div className="bh pd"><h3>Unusual activity</h3><span>Saved report</span></div>
            <Table cols={[{ h: "Strike", v: (r) => `${r.option_type === "CALL" ? "C" : "P"} ${n(r.strike, 0)}`, text: true, bold: true }, { h: "OI chg", v: (r) => sg(r.change_oi, 0) }, { h: "Vol/OI", v: (r) => `${n(r.volume_oi_ratio, 1)}x` }, { h: "Prem", v: (r) => <Pct v={r.premium_change} d={0} /> }]} rows={unusual} /></>}
        </div>
      </section>
    </div>
  );
}
