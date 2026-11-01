import { fmt, isNum } from "../lib/format";
import type { Derivatives } from "../lib/types";

export default function DerivativesStrip({ d }: { d: Derivatives | null }) {
  const items = d?.available ? [
    { icon: "⚖", label: "OI PCR", value: fmt(d.oi_pcr) },
    { icon: "📊", label: "Volume PCR", value: fmt(d.volume_pcr) },
    { icon: "🎯", label: "Max Pain", value: fmt(d.max_pain, 0) },
    { icon: "〰", label: "ATM IV", value: isNum(d.atm_iv) ? `${fmt(d.atm_iv)}%` : "N/A" },
    { icon: "⚡", label: "Unusual activity", value: fmt(d.unusual_count, 0) },
  ] : [];
  return (
    <div className="flex flex-wrap gap-3">
      {items.length === 0 ? <div className="text-sm text-muted">Derivatives: N/A</div> : items.map((i) => (
        <div key={i.label} className="flex min-w-[9rem] flex-1 items-center gap-2 rounded border border-line/50 bg-panel p-3">
          <span aria-hidden>{i.icon}</span>
          <div><div className="text-xs text-secondary">{i.label}</div><div className="font-semibold">{i.value}</div></div>
        </div>
      ))}
    </div>
  );
}
