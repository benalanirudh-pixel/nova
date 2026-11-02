import type { ReactNode } from "react";
import { fmt, isNum, label, signCls } from "../lib/format";

/** Dense panel: compact uppercase header bar + body. */
/** `fill`: flex column whose body takes the remaining height (for fixed-height layouts). */
export function Panel({ title, right, children, className = "", bodyClass = "p-2", fill }: {
  title: ReactNode; right?: ReactNode; children: ReactNode; className?: string; bodyClass?: string; fill?: boolean;
}) {
  return (
    <section className={`min-w-0 rounded-sm border border-line/50 bg-panel ${fill ? "flex min-h-0 flex-col" : ""} ${className}`}>
      <header className="flex shrink-0 items-center gap-2 border-b border-line/40 bg-deep/50 px-2 py-1">
        <h2 className="text-[10px] font-semibold uppercase tracking-[0.12em] text-secondary">{title}</h2>
        {right && <div className="ml-auto flex items-center gap-2 text-[10px] text-muted">{right}</div>}
      </header>
      <div className={fill ? `relative min-h-0 flex-1 ${bodyClass}` : bodyClass}>{children}</div>
    </section>
  );
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
  if (/BEAR|WEAK|SELL|BELOW|NEGATIVE|LOWER|HIGH_RISK/.test(u)) return "border-negative/60 text-negative";
  if (/BULL|STRONG|BUY|ABOVE|POSITIVE|HIGHER/.test(u)) return "border-positive/60 text-positive";
  if (!u || u === "N/A" || u === "UNKNOWN") return "border-line text-muted";
  return "border-warning/60 text-warning";
}

/** Small uppercase status chip, tone derived from the API string. */
export function Chip({ text, tone, title }: { text: unknown; tone?: string; title?: string }) {
  return (
    <span title={title} className={`inline-block whitespace-nowrap rounded-sm border px-1.5 py-px text-[10px] font-semibold uppercase tracking-wide ${tone ?? toneOf(text)}`}>
      {label(text)}
    </span>
  );
}

/** Label/value cell for stat grids. */
export function Stat({ k, children, title }: { k: string; children: ReactNode; title?: string }) {
  return (
    <div className="min-w-0 border border-line/30 bg-deep/40 px-2 py-1" title={title}>
      <div className="truncate text-[10px] uppercase tracking-wide text-muted">{k}</div>
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

export const btn = "rounded-sm border px-1.5 py-px text-[10px] font-semibold focus:outline-none focus-visible:ring-1 focus-visible:ring-accent";
