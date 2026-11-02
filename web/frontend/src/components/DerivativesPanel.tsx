import { fmt, fmtCompact, isNum, label, signCls } from "../lib/format";
import type { Derivatives, Wall } from "../lib/types";
import { Chip, Num, Panel, Stat } from "./ui";

function WallCell({ k, w }: { k: string; w?: Wall }) {
  return (
    <Stat k={k} title={w && isNum(w.change_oi) ? `Change in OI ${fmt(w.change_oi, 0)}` : undefined}>
      <Num v={w?.strike} d={0} />
      {w && isNum(w.oi) && <span className="ml-1 text-[10px] text-muted">OI {fmtCompact(w.oi)}</span>}
      {w && isNum(w.change_oi) && <span className={`ml-1 text-[10px] ${signCls(w.change_oi)}`}>Δ{fmtCompact(w.change_oi)}</span>}
    </Stat>
  );
}

/** Options positioning for one instrument: PCR, max pain, IV, walls, top-5 unusual activity. */
export default function DerivativesPanel({ title, d }: { title: string; d?: Derivatives | null }) {
  const it = d?.interpretation;
  const top = (d?.unusual_activity ?? []).slice(0, 5);
  return (
    <Panel title={`Derivatives · ${title}`}
      right={<>{d?.expiry && <span>EXP <span className="text-secondary">{d.expiry}</span></span>}{it?.classification && <Chip text={it.classification} tone="border-info/60 text-info" />}</>}>
      {!d?.available ? <div className="text-xs text-muted">Not available</div> : (
        <div className="space-y-2">
          <div className="grid grid-cols-2 gap-1 sm:grid-cols-4">
            <Stat k="OI PCR"><Num v={d.oi_pcr} /></Stat>
            <Stat k="Vol PCR"><Num v={d.volume_pcr} /></Stat>
            <Stat k="ATM IV"><Num v={d.atm_iv} suffix={isNum(d.atm_iv) ? "%" : ""} /></Stat>
            <Stat k="Spot"><Num v={d.spot} /></Stat>
            <Stat k="Max pain"><Num v={d.max_pain} d={0} /></Stat>
            <Stat k="Max pain vs spot" title="Max-pain distance from spot, % (from API)"><Num v={it?.max_pain_distance_percent} signed suffix="%" /></Stat>
            <WallCell k="Put wall" w={d.put_wall} />
            <WallCell k="Call wall" w={d.call_wall} />
          </div>
          <div>
            <div className="mb-0.5 text-[10px] text-muted">
              Unusual activity {isNum(d.unusual_count) && `(top ${top.length} of ${d.unusual_count})`}
            </div>
            {top.length === 0 ? <div className="text-xs text-muted">None reported</div> : (
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead className="text-[10px] text-muted">
                    <tr><th className="px-1 text-left font-normal">Type</th><th className="px-1 text-right font-normal">Strike</th><th className="px-1 text-right font-normal">OI</th><th className="px-1 text-right font-normal">ΔOI</th><th className="px-1 text-right font-normal">Vol/OI</th><th className="px-1 text-left font-normal">Activity</th></tr>
                  </thead>
                  <tbody className="font-mono tabular-nums">
                    {top.map((u, i) => (
                      <tr key={i} className="border-t border-line/20 hover:bg-line/15" title={u.premium_state ? label(u.premium_state) : undefined}>
                        <td className={`px-1 font-sans ${u.option_type === "CALL" ? "text-positive" : u.option_type === "PUT" ? "text-negative" : "text-muted"}`}>{u.option_type ?? "N/A"}</td>
                        <td className="px-1 text-right">{fmt(u.strike, 0)}</td>
                        <td className="px-1 text-right">{fmtCompact(u.oi)}</td>
                        <td className={`px-1 text-right ${signCls(u.change_oi)}`}>{fmtCompact(u.change_oi)}</td>
                        <td className="px-1 text-right">{fmt(u.volume_oi_ratio, 1)}</td>
                        <td className="px-1 font-sans text-secondary">{u.oi_activity ?? "N/A"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          {it?.warning && <div className="text-[10px] text-muted">{it.warning}</div>}
        </div>
      )}
    </Panel>
  );
}
