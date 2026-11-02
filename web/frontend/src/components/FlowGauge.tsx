import { isNum, label } from "../lib/format";
import type { Flows, Streak } from "../lib/types";
import { Chip, Num, Panel } from "./ui";

const streak = (s?: Streak) =>
  Array.isArray(s) && s.length === 2 ? <><Chip text={s[0]} /> <span className="font-mono tabular-nums text-secondary">{s[1]}d</span></> : <span className="text-muted">N/A</span>;

export default function FlowGauge({ flows }: { flows: Flows | null }) {
  const rows = flows?.available
    ? (["5d", "10d", "20d"] as const).flatMap((w) => [
        { label: `FII ${w}`, v: flows[`fii_${w}`] },
        { label: `DII ${w}`, v: flows[`dii_${w}`] },
      ])
    : [];
  const max = Math.max(1, ...rows.map((r) => r.v).filter(isNum).map(Math.abs));
  return (
    <Panel title={`Institutional flows${flows?.unit ? ` · ${flows.unit}` : ""}`}
      right={flows?.latest_date && <span>as of <span className="text-secondary">{flows.latest_date}</span></span>}>
      {rows.length === 0 ? (
        <div className="text-xs text-muted">Flow data unavailable{flows?.signal_reason ? `: ${flows.signal_reason}` : ""}</div>
      ) : (
        <div className="space-y-1.5">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px]">
            <Chip text={flows?.flow_regime} tone="border-info/60 text-info" />
            <span className="flex items-center gap-1"><span className="text-muted">FII</span>{streak(flows?.fii_streak)}</span>
            <span className="flex items-center gap-1"><span className="text-muted">DII</span>{streak(flows?.dii_streak)}</span>
          </div>
          <div>
            {rows.map((r) => (
              <div key={r.label} className="flex items-center gap-2 py-px text-[11px] hover:bg-line/15">
                <span className="w-12 text-secondary">{r.label}</span>
                <div className="flex h-2 flex-1">
                  <div className="flex w-1/2 justify-end border-r border-line/40">
                    {isNum(r.v) && r.v < 0 && <div className="bg-negative" style={{ width: `${(-r.v / max) * 100}%` }} />}
                  </div>
                  <div className="flex w-1/2">
                    {isNum(r.v) && r.v > 0 && <div className="bg-positive" style={{ width: `${(r.v / max) * 100}%` }} />}
                  </div>
                </div>
                <Num v={r.v} d={0} signed className="w-20 text-right" />
              </div>
            ))}
          </div>
          <div className="text-[10px] text-muted">
            Source quality: <span className="text-secondary">{label(flows?.source_quality)}</span>
            {flows?.signal_allowed === false && flows.signal_reason && <div title={flows.signal_reason} className="truncate">{flows.signal_reason}</div>}
          </div>
        </div>
      )}
    </Panel>
  );
}
