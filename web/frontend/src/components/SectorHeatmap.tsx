import { fmt, fmtPct, isNum, label } from "../lib/format";
import type { Sector } from "../lib/types";
import { Panel } from "./ui";

const SCALE = 10; // real 20D returns reach +-15, so +-10 keeps cells from all saturating
const NEUTRAL = [27, 34, 43];
const GREEN = [22, 130, 90];
const RED = [190, 30, 55];

function cellColor(v: unknown): string {
  if (!isNum(v)) return "#141920";
  const t = Math.min(1, Math.abs(v) / SCALE);
  const end = v >= 0 ? GREEN : RED;
  return `rgb(${NEUTRAL.map((n, i) => Math.round(n + (end[i] - n) * t)).join(",")})`;
}

export default function SectorHeatmap({ sectors }: { sectors: Sector[] | null }) {
  return (
    <Panel title="Sectors · 20D return" right="RS = relative strength 20D">
      {!sectors || sectors.length === 0 ? <div className="text-xs text-muted">N/A</div> : (
        <div className="grid grid-cols-2 gap-px sm:grid-cols-3">
          {sectors.map((s) => (
            <div key={s.name} className="min-w-0 p-1.5 text-white" style={{ background: cellColor(s.return_20d) }}
              title={`${s.name} · 20D ${fmtPct(s.return_20d)} · RS ${fmt(s.relative_strength_20d)} · ${label(s.regime)}`}>
              <div className="truncate text-[11px] font-semibold">{s.name}</div>
              <div className="font-mono text-sm font-semibold tabular-nums">{fmtPct(s.return_20d)}</div>
              <div className="flex justify-between gap-1 text-[10px] text-white/75">
                <span className="font-mono tabular-nums">RS {fmt(s.relative_strength_20d, 1)}</span>
                <span className="truncate">{label(s.regime)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
