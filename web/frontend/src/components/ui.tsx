import { useEffect, useRef, useState, type ReactNode } from "react";
import { fmt, isNum, label, signCls } from "../lib/format";

/** Dense panel: compact header bar + body. */
/** `fill`: flex column whose body takes the remaining height (for fixed-height layouts). */
export function Panel({ title, right, children, className = "", bodyClass = "p-2", fill }: {
  title: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; fill?: boolean;
}) {
  return (
    <section className={`panel min-w-0 rounded-md border border-line/35 bg-panel transition-colors hover:border-line/60 ${fill ? "flex min-h-0 flex-col" : ""} ${className}`}>
      <header className="flex h-8 shrink-0 items-center gap-2 rounded-t-md border-b border-line/25 bg-raised/35 px-2.5">
        <span className="h-3 w-0.5 shrink-0 rounded-full bg-accent/70" aria-hidden />
        <h2 className="truncate text-[11px] font-semibold uppercase tracking-[0.06em] text-secondary">{title}</h2>
        {right && <div className="ml-auto flex min-w-0 items-center gap-2 text-[11px] text-muted">{right}</div>}
      </header>
      <div className={fill ? `relative min-h-0 flex-1 ${bodyClass}` : bodyClass}>{children}</div>
    </section>
  );
}

/** Brief green/red background when a live number moves; fades out over 600 ms. */
export function Flash({ v, children }: { v: unknown; children: ReactNode }) {
  const prev = useRef(v);
  const [dir, setDir] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    const old = prev.current;
    prev.current = v;
    if (!isNum(v) || !isNum(old) || v === old) return;
    setDir(v > old ? "up" : "down");
    const t = setTimeout(() => setDir(null), 600);
    return () => clearTimeout(t);
  }, [v]);
  const bg = dir === "up" ? "bg-positive/25" : dir === "down" ? "bg-negative/25" : "bg-transparent transition-colors duration-700";
  return <span className={`-mx-0.5 rounded-sm px-0.5 ${bg}`}>{children}</span>;
}

/** Tabular figure; `signed` adds +/- colouring. Missing shows muted N/A. */
export function Num({ v, d = 2, suffix = "", signed, className = "" }: {
  v: unknown; d?: number; suffix?: string; signed?: boolean; className?: string;
}) {
  const tone = signed ? signCls(v) : isNum(v) ? "" : "text-muted";
  const text = isNum(v) ? `${signed && v > 0 ? "+" : ""}${fmt(v, d)}${suffix}` : "N/A";
  return <span className={`font-mono tabular-nums ${tone} ${className}`}>{text}</span>;
}

/** ▲/▼ absolute and percent change. */
export function Change({ abs, pct, className = "" }: { abs?: unknown; pct: unknown; className?: string }) {
  if (!isNum(pct) && !isNum(abs)) return <span className="text-muted">N/A</span>;
  const ref = isNum(pct) ? pct : abs;
  const glyph = !isNum(ref) || ref === 0 ? "" : ref > 0 ? "▲" : "▼";
  return (
    <span className={`whitespace-nowrap font-mono tabular-nums ${signCls(ref)} ${className}`}>
      {glyph} {isNum(abs) && `${fmt(Math.abs(abs))} `}{isNum(pct) && `(${fmt(Math.abs(pct))}%)`}
    </span>
  );
}

export function toneOf(s: unknown) {
  const u = typeof s === "string" ? s.toUpperCase() : "";
  if (/BEAR|WEAK|SELL|BELOW|NEGATIVE|LOWER|HIGH_RISK|DOWN/.test(u)) return "border-negative/40 bg-negative/10 text-negative";
  if (/BULL|STRONG|BUY|ABOVE|POSITIVE|HIGHER|UPTREND/.test(u)) return "border-positive/40 bg-positive/10 text-positive";
  if (!u || u === "N/A" || u === "UNKNOWN") return "border-line/60 text-muted";
  return "border-warning/40 bg-warning/10 text-warning";
}

/** API enum in sentence case ("STRONG BULLISH" -> "Strong bullish"); N/A untouched. */
const sentence = (t: string) => (t === "N/A" ? t : t.charAt(0) + t.slice(1).toLowerCase());

/** Small status chip, tone derived from the API string. */
export function Chip({ text, tone, title }: { text: unknown; tone?: string; title?: string }) {
  return (
    <span title={title} className={`inline-block whitespace-nowrap rounded-full border px-2 py-px text-[10.5px] font-medium ${tone ?? toneOf(text)}`}>
      {sentence(label(text))}
    </span>
  );
}

/** Label/value cell for stat grids. */
export function Stat({ k, children, title }: { k: ReactNode; children: ReactNode; title?: string }) {
  return (
    <div className="min-w-0 rounded border border-line/25 bg-raised/60 px-2 py-1.5" title={title}>
      <div className="truncate text-[11px] text-muted">{k}</div>
      <div className="truncate text-sm">{children}</div>
    </div>
  );
}

/** Inline SVG polyline of real closes; nothing drawn when fewer than 2 points. */
export function Sparkline({ values, className = "h-8 w-24", title }: { values: unknown[]; className?: string; title?: string }) {
  const v = values.filter(isNum);
  if (v.length < 2) return <span className="text-[10px] text-muted">N/A</span>;
  const min = Math.min(...v), max = Math.max(...v), span = max - min || 1;
  const pts = v.map((y, i) => `${(i / (v.length - 1)) * 100},${30 - ((y - min) / span) * 28 - 1}`).join(" ");
  const up = v[v.length - 1] >= v[0];
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={className} role="img" aria-label={title}>
      {title && <title>{title}</title>}
      <polyline points={pts} fill="none" strokeWidth="1.5" vectorEffect="non-scaling-stroke"
        className={up ? "stroke-positive" : "stroke-negative"} />
    </svg>
  );
}

/** Low→high track with a marker at `value`. */
export function RangeBar({ low, high, value, lowLabel = "L", highLabel = "H", d = 2 }: {
  low: unknown; high: unknown; value: unknown; lowLabel?: string; highLabel?: string; d?: number;
}) {
  const ok = isNum(low) && isNum(high) && isNum(value) && high > low;
  const pos = ok ? Math.min(100, Math.max(0, ((value - low) / (high - low)) * 100)) : 0;
  return (
    <div className="flex items-center gap-2 text-[10px]">
      <span className="text-muted">{lowLabel}</span><Num v={low} d={d} className="text-secondary" />
      <div className="relative h-1.5 flex-1 rounded-full bg-line/30" title={ok ? `${pos.toFixed(0)}% of range` : "range N/A"}>
        {ok && <>
          <div className="absolute inset-y-0 left-0 rounded-full bg-gradient-to-r from-negative/50 to-positive/50" style={{ width: `${pos}%` }} />
          <div className="absolute -top-0.5 h-2.5 w-0.5 bg-fg" style={{ left: `calc(${pos}% - 1px)` }} />
        </>}
      </div>
      <Num v={high} d={d} className="text-secondary" /><span className="text-muted">{highLabel}</span>
    </div>
  );
}

/** 0–100 % bar with a label and value. */
export function PctBar({ k, v, bar = "bg-info" }: { k: string; v: unknown; bar?: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-28 shrink-0 truncate text-secondary" title={k}>{k}</span>
      <div className="h-1.5 flex-1 bg-line/20">
        {isNum(v) && <div className={`h-1.5 ${bar}`} style={{ width: `${Math.min(100, Math.max(0, v))}%` }} />}
      </div>
      <Num v={v} d={1} suffix={isNum(v) ? "%" : ""} className="w-14 text-right" />
    </div>
  );
}

export const NoData = ({ text = "No cache: run a refresh to load this section." }: { text?: string }) =>
  <div className="p-1 text-xs text-muted">{text}</div>;

export const btn = "rounded border px-1.5 py-px text-[10.5px] font-semibold focus:outline-none focus-visible:ring-1 focus-visible:ring-accent";

/** Placeholder lines while a section loads; error text when its source failed. */
export function Body({ loading, error, children, lines = 4 }: { loading: boolean; error?: string | null; children: ReactNode; lines?: number }) {
  if (loading) return <div className="animate-pulse space-y-2 p-1">{Array.from({ length: lines }, (_, i) => <div key={i} className="h-3 rounded bg-raised" style={{ width: `${90 - i * 12}%` }} />)}</div>;
  if (error) return <div className="p-1 text-[12px] text-muted">Not available. {error}</div>;
  return <>{children}</>;
}
