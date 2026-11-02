import { isNum } from "../lib/format";
import { COLORS } from "../lib/theme";

export default function MomentumGauge({ score, label }: { score: number | null; label: string }) {
  const ok = isNum(score);
  const v = ok ? Math.min(100, Math.max(0, score)) : 0; // 0 only drives the empty arc, never displayed
  const color = v < 30 ? COLORS.negative : v < 60 ? COLORS.warning : COLORS.positive;
  const r = 52, c = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 140 140" className="h-32 w-32" role="img" aria-label={`${label} ${ok ? v.toFixed(1) : "N/A"}`}>
        <circle cx="70" cy="70" r={r} fill="none" stroke={COLORS.border} strokeOpacity="0.3" strokeWidth="12" />
        {ok && (
          <circle cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="12" strokeLinecap="round"
            strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 70 70)" />
        )}
        <text x="70" y="78" textAnchor="middle" fontSize="26" fontWeight="600" fill={ok ? color : COLORS.textMuted}>
          {ok ? v.toFixed(1) : "N/A"}
        </text>
      </svg>
      <div className="text-xs text-secondary">{label}</div>
    </div>
  );
}
