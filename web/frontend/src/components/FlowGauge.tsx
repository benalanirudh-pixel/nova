import { fmt, isNum } from "../lib/format";
import type { Flows } from "../lib/types";

export default function FlowGauge({ flows }: { flows: Flows | null }) {
  const rows = flows?.available
    ? (["5d", "10d", "20d"] as const).flatMap((w) => [
        { label: `FII ${w}`, v: flows[`fii_${w}`] },
        { label: `DII ${w}`, v: flows[`dii_${w}`] },
      ])
    : [];
  const max = Math.max(1, ...rows.map((r) => r.v).filter(isNum).map(Math.abs));
  return (
    <div className="rounded border border-line/50 bg-panel p-3">
      <div className="mb-2 text-xs text-secondary">Institutional flows{flows?.unit ? ` (${flows.unit})` : ""}</div>
      {rows.length === 0 ? <div className="text-sm text-muted">N/A</div> : rows.map((r) => (
        <div key={r.label} className="mb-1 flex items-center gap-2 text-xs">
          <span className="w-14 text-secondary">{r.label}</span>
          <div className="flex h-3 flex-1">
            <div className="flex w-1/2 justify-end">
              {isNum(r.v) && r.v < 0 && <div className="bg-negative" style={{ width: `${(-r.v / max) * 100}%` }} />}
            </div>
            <div className="flex w-1/2">
              {isNum(r.v) && r.v > 0 && <div className="bg-positive" style={{ width: `${(r.v / max) * 100}%` }} />}
            </div>
          </div>
          <span className={`w-20 text-right ${!isNum(r.v) ? "text-muted" : r.v >= 0 ? "text-positive" : "text-negative"}`}>{fmt(r.v, 0)}</span>
        </div>
      ))}
      {flows?.signal_allowed === false && flows.signal_reason && (
        <div className="mt-2 text-xs text-muted">{flows.signal_reason}</div>
      )}
    </div>
  );
}
