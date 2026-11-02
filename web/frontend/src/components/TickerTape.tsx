import { useEffect, useState } from "react";
import { istSession } from "../lib/schedule";
import type { MarketOverviewData, Quote } from "../lib/types";
import { Change, Chip, Num } from "./ui";

// Mirrors styles/design_tokens.py freshness_level / freshness_color
function level(s: number | null | undefined): { name: string; cls: string } {
  if (typeof s !== "number") return { name: "unknown", cls: "bg-muted" };
  if (s < 600) return { name: "fresh", cls: "bg-positive" };
  if (s < 7200) return { name: "aging", cls: "bg-warning" };
  return { name: "stale", cls: "bg-negative" };
}

function SessionClock() {
  const [now, setNow] = useState(istSession);
  useEffect(() => {
    const t = setInterval(() => setNow(istSession()), 1000);
    return () => clearInterval(t);
  }, []);
  const tone = now.session === "Open" ? "border-positive/60 text-positive" : now.session === "Pre-open" ? "border-warning/60 text-warning" : "border-line text-muted";
  return (
    <div className="ml-auto flex shrink-0 items-center gap-2 pl-3">
      <span className="font-mono tabular-nums text-secondary">{now.clock}</span>
      <span title="By time and weekday only; holiday calendar not checked"
        className={`rounded-sm border px-1.5 py-px text-[10px] font-semibold uppercase ${tone}`}>{now.session}</span>
    </div>
  );
}

function Item({ name, q, v }: { name: string; q?: Quote; v: unknown }) {
  return (
    <span className="flex shrink-0 items-center gap-1.5" title={q?.source_label}>
      <span className="font-semibold text-secondary">{name}</span>
      <Num v={v} className="text-fg" />
      <Change abs={q?.change_abs} pct={q?.change_percent} />
    </span>
  );
}

const Sep = () => <span className="h-3 w-px shrink-0 bg-line/50" />;

export default function TickerTape({ data }: { data: MarketOverviewData | null }) {
  const k = data?.kpis;
  const freshness = data?.freshness;
  const lv = level(freshness?.age_seconds);
  return (
    <div className="flex items-center gap-3 overflow-x-auto [scrollbar-width:none] whitespace-nowrap border-b border-line/50 bg-deep px-3 py-1 text-xs">
      <Item name="NIFTY" q={k?.nifty} v={k?.nifty?.price} />
      <Sep />
      <Item name="BANK NIFTY" q={k?.banknifty} v={k?.banknifty?.price} />
      <Sep />
      <Item name="INDIA VIX" q={k?.vix} v={k?.vix?.value} />
      <Sep />
      <span className="flex shrink-0 items-center gap-1.5"><span className="text-muted">REGIME</span><Chip text={k?.macro?.market_regime} /></span>
      <span className="flex shrink-0 items-center gap-1.5"><span className="text-muted">FLOWS</span><Chip text={data?.flows?.flow_regime} /></span>
      <Sep />
      <span className="flex shrink-0 items-center gap-1.5" title={freshness?.generated ? `Generated ${freshness.generated}` : "No cache"}>
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${lv.cls}`} />
        <span className="text-muted">DATA</span>
        <span className="text-secondary">{freshness?.label ?? "No cache"}</span>
      </span>
      <SessionClock />
    </div>
  );
}
