interface Props { title: string; value: string | number | null; change?: number | null; color?: string }

export default function KPICard({ title, value, change, color }: Props) {
  const hasChange = typeof change === "number" && Number.isFinite(change);
  const tone = !hasChange ? "text-muted" : change >= 0 ? "text-positive" : "text-negative";
  return (
    <div className="min-w-[8.5rem] flex-1 rounded border border-line/50 bg-panel p-3">
      <div className="text-xs text-secondary">{title}</div>
      <div className="mt-1 text-xl font-semibold" style={color ? { color } : undefined}>{value ?? "N/A"}</div>
      {hasChange && <div className={`text-xs ${tone}`}>{change >= 0 ? "▲" : "▼"} {Math.abs(change).toFixed(2)}%</div>}
    </div>
  );
}
