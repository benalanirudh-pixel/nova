import type { ReactNode } from "react";
import { isNum } from "../lib/format";
import type { Breadth } from "../lib/types";

function Box({ children }: { children: ReactNode }) {
  return (
    <div className="rounded border border-line/50 bg-panel p-3">
      <div className="mb-2 text-xs text-secondary">Market breadth</div>
      {children}
    </div>
  );
}

export default function BreadthBars({ breadth }: { breadth: Breadth | null }) {
  const { advancing: a, declining: d, unchanged: u } = breadth ?? {};
  if (!isNum(a) || !isNum(d) || !isNum(u) || a + d + u === 0) {
    return <Box><div className="text-sm text-muted">N/A</div></Box>;
  }
  const total = a + d + u;
  const seg = (n: number, cls: string) => <div className={cls} style={{ width: `${(n / total) * 100}%` }} />;
  return (
    <Box>
      <div className="flex h-4 overflow-hidden rounded">
        {seg(a, "bg-positive")}{seg(u, "bg-muted")}{seg(d, "bg-negative")}
      </div>
      <div className="mt-2 flex justify-between text-xs">
        <span className="text-positive">Advancing {a}</span>
        <span className="text-muted">Unch {u}</span>
        <span className="text-negative">Declining {d}</span>
      </div>
    </Box>
  );
}
