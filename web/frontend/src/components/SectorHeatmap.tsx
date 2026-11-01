import { fmt, isNum } from "../lib/format";
import type { Sector } from "../lib/types";

const SCALE = 10; // real 20D returns reach +-15, so +-10 keeps cells from all saturating
const NEUTRAL = [7, 25, 35];
const GREEN = [0, 140, 100];
const RED = [190, 30, 55];

function cellColor(v: unknown): string {
  if (!isNum(v)) return "#071923";
  const t = Math.min(1, Math.abs(v) / SCALE);
  const end = v >= 0 ? GREEN : RED;
  return `rgb(${NEUTRAL.map((n, i) => Math.round(n + (end[i] - n) * t)).join(",")})`;
}

export default function SectorHeatmap({ sectors }: { sectors: Sector[] | null }) {
  return (
    <div className="rounded border border-line/50 bg-panel p-3">
      <div className="mb-2 text-xs text-secondary">Sectors, 20D return</div>
      {!sectors || sectors.length === 0 ? <div className="text-sm text-muted">N/A</div> : (
        <div className="grid grid-cols-2 gap-1">
          {sectors.map((s) => (
            <div key={s.name} className="rounded p-2 text-xs text-white" style={{ background: cellColor(s.return_20d) }}
              title={s.regime ? `Regime: ${s.regime}` : undefined}>
              <div className="truncate">{s.name}</div>
              <div className="font-semibold">{isNum(s.return_20d) ? `${s.return_20d >= 0 ? "+" : ""}${fmt(s.return_20d)}%` : "N/A"}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
