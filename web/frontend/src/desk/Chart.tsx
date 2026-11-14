import { useMemo, useRef, useState, type ReactNode } from "react";
import { isNum } from "../lib/format";
import { dayMonth, n } from "./ui";

export interface Series { name: string; color: string; values: (number | null | undefined)[]; width?: number }
interface Props {
  x: string[];
  series: Series[];
  /** Drawn in their own strip under the plot, on their own scale: never a second axis on the plot. */
  bars?: (number | null | undefined)[];
  barsLabel?: string;
  band?: { lo: number; hi: number; label: string };
  marks?: { y: number; label: string }[];
  domain?: [number, number];
  fmt?: (v: number) => string;
  barFmt?: (v: number) => string;
  height?: number;
  label: string;
}

const W = 900, PAD_L = 6, PAD_R = 58, TOP = 8, AXIS = 16, STRIP = 44;

function step(span: number) {
  const raw = span / 4, mag = 10 ** Math.floor(Math.log10(raw)), f = raw / mag;
  return (f >= 5 ? 5 : f >= 2 ? 2 : 1) * mag;
}

/** Line chart with a hover crosshair. One y-axis; optional volume strip, value band and level marks. */
export default function LineChart({ x, series, bars, barsLabel, band, marks, domain, fmt = (v) => n(v), barFmt = (v) => n(v, 0), height = 280, label }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const ref = useRef<SVGSVGElement>(null);
  const count = x.length, H = height, plotB = H - AXIS - (bars ? STRIP + 6 : 0), plotW = W - PAD_L - PAD_R;

  const g = useMemo(() => {
    const all = series.flatMap((s) => s.values.filter(isNum));
    if (count < 2 || !all.length) return null;
    let lo = domain ? domain[0] : Math.min(...all), hi = domain ? domain[1] : Math.max(...all);
    if (!domain) { const pad = (hi - lo || Math.abs(hi) || 1) * 0.05; lo -= pad; hi += pad; }
    const X = (i: number) => PAD_L + (i * plotW) / (count - 1);
    const Y = (v: number) => TOP + ((hi - v) / (hi - lo)) * (plotB - TOP);
    const st = step(hi - lo), ticks: number[] = [];
    for (let t = Math.ceil(lo / st) * st; t <= hi + 1e-9; t += st) ticks.push(t);
    const paths = series.map((s) => {
      let d = "", pen = false;
      s.values.forEach((v, i) => { if (isNum(v)) { d += `${pen ? "L" : "M"}${X(i).toFixed(1)} ${Y(v).toFixed(1)}`; pen = true; } else pen = false; });
      return d;
    });
    const barMax = bars ? Math.max(...bars.filter(isNum), 0) : 0;
    return { lo, hi, X, Y, ticks, paths, barMax };
  }, [series, bars, count, domain, plotB, plotW]);

  if (!g) return <div className="empty">Not enough history to draw {label}.</div>;
  const { X, Y, lo, hi } = g;
  const inside = (v: number) => v >= lo && v <= hi;
  const move = (e: React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect(), px = ((e.clientX - r.left) / r.width) * W;
    setHover(Math.max(0, Math.min(count - 1, Math.round(((px - PAD_L) / plotW) * (count - 1)))));
  };
  const xt = [0, 1, 2, 3, 4, 5].map((k) => Math.round((k * (count - 1)) / 5));
  const lastIdx = (v: Series["values"]) => { for (let i = v.length - 1; i >= 0; i--) if (isNum(v[i])) return i; return -1; };
  const ends = series.map((s) => { const i = lastIdx(s.values); return i < 0 ? null : { i, y: Y(s.values[i] as number), v: s.values[i] as number }; });
  // end labels in series order, skipping any that would collide; the legend and the tooltip carry the rest
  const placed: number[] = [];
  const labelled = ends.map((e) => { if (!e || placed.some((y) => Math.abs(y - e.y) < 11)) return false; placed.push(e.y); return true; });
  const barW = Math.max(1, plotW / count - 1);
  const tip: ReactNode = hover != null && (
    <div className="ctip" style={hover > count * 0.6 ? { right: `${100 - (X(hover) / W) * 100 + 1.5}%` } : { left: `${(X(hover) / W) * 100 + 1.5}%` }}>
      <b>{dayMonth(x[hover])} {x[hover].slice(0, 4)}</b>
      {series.map((s) => <div key={s.name}><i style={{ background: s.color }} /><u>{s.name}</u><span>{isNum(s.values[hover]) ? fmt(s.values[hover] as number) : "n/a"}</span></div>)}
      {bars && <div><i style={{ background: "var(--faint)" }} /><u>{barsLabel}</u><span>{isNum(bars[hover]) ? barFmt(bars[hover] as number) : "n/a"}</span></div>}
    </div>
  );
  return (
    <div className="chart">
      {series.length > 1 && <div className="clegend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}{band && <span><i className="vband" />{band.label}</span>}</div>}
      <div className="cwrap">
        <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} onMouseMove={move} onMouseLeave={() => setHover(null)}>
          {g.ticks.map((t) => <g key={t}><line x1={PAD_L} x2={W - PAD_R} y1={Y(t)} y2={Y(t)} className="cgrid" /><text x={W - PAD_R + 5} y={Y(t) + 3} className="ctick">{fmt(t)}</text></g>)}
          {band && inside(band.lo) && inside(band.hi) && <rect x={PAD_L} width={plotW} y={Y(band.hi)} height={Y(band.lo) - Y(band.hi)} className="cband" />}
          {marks?.filter((m) => inside(m.y)).map((m) => <g key={m.label}><line x1={PAD_L} x2={W - PAD_R} y1={Y(m.y)} y2={Y(m.y)} className="cmark" /><text x={PAD_L + 3} y={Y(m.y) - 3} className="ctick">{m.label} {fmt(m.y)}</text></g>)}
          {g.paths.map((d, i) => <path key={series[i].name} d={d} fill="none" stroke={series[i].color} strokeWidth={series[i].width ?? 2} strokeLinejoin="round" strokeLinecap="round" />)}
          {ends.map((e, i) => e && labelled[i] && <g key={series[i].name}><circle cx={X(e.i)} cy={e.y} r={4} fill={series[i].color} className="cdot" /><text x={W - PAD_R + 5} y={e.y + 3} className="cend">{fmt(e.v)}</text></g>)}
          {bars && g.barMax > 0 && <>
            <line x1={PAD_L} x2={W - PAD_R} y1={H - AXIS} y2={H - AXIS} className="cgrid" />
            {bars.map((v, i) => isNum(v) && v > 0 && <rect key={i} x={X(i) - barW / 2} width={barW} y={H - AXIS - (v / g.barMax) * STRIP} height={(v / g.barMax) * STRIP} className="cbar" />)}
            <text x={W - PAD_R + 5} y={H - AXIS - STRIP + 8} className="ctick">{barsLabel}</text>
          </>}
          {xt.map((i) => <text key={i} x={X(i)} y={H - 4} textAnchor={i === 0 ? "start" : i === count - 1 ? "end" : "middle"} className="ctick">{dayMonth(x[i])}{i === 0 || i === count - 1 ? ` ${x[i].slice(2, 4)}` : ""}</text>)}
          {hover != null && <>
            <line x1={X(hover)} x2={X(hover)} y1={TOP} y2={H - AXIS} className="ccross" />
            {series.map((s) => isNum(s.values[hover]) && <circle key={s.name} cx={X(hover)} cy={Y(s.values[hover] as number)} r={4} fill={s.color} className="cdot" />)}
          </>}
        </svg>
        {tip}
      </div>
    </div>
  );
}

interface Dot { name: string; x: number; y: number; note: string }

/** Quadrant scatter: position carries the meaning, so every dot wears one colour. */
export function Quadrants({ dots, xLabel, yLabel, corners, label }: { dots: Dot[]; xLabel: string; yLabel: string; corners: [string, string, string, string]; label: string }) {
  const [hover, setHover] = useState<number | null>(null);
  if (dots.length < 2) return <div className="empty">Not enough sectors to map.</div>;
  const S = 420, P = 26, mx = Math.max(...dots.map((d) => Math.abs(d.x)), 1) * 1.12, my = Math.max(...dots.map((d) => Math.abs(d.y)), 1) * 1.12;
  const X = (v: number) => P + ((v + mx) / (2 * mx)) * (S - 2 * P), Y = (v: number) => P + ((my - v) / (2 * my)) * (S - 2 * P);
  // label only the dots furthest from the centre; the table beside the chart names every sector
  const far = [...dots.keys()].sort((a, b) => Math.hypot(dots[b].x / mx, dots[b].y / my) - Math.hypot(dots[a].x / mx, dots[a].y / my)).slice(0, 8);
  const h = hover != null ? dots[hover] : null;
  return (
    <div className="chart">
      <div className="cwrap">
        <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label={label} onMouseLeave={() => setHover(null)}>
          <line x1={X(0)} x2={X(0)} y1={P} y2={S - P} className="caxis" /><line x1={P} x2={S - P} y1={Y(0)} y2={Y(0)} className="caxis" />
          {[[S - P - 2, P + 10, "end", corners[0]], [P + 2, P + 10, "start", corners[1]], [P + 2, S - P - 5, "start", corners[2]], [S - P - 2, S - P - 5, "end", corners[3]]].map(([cx, cy, a, t]) =>
            <text key={t as string} x={cx as number} y={cy as number} textAnchor={a as "end"} className="cquad">{t}</text>)}
          <text x={S / 2} y={S - 6} textAnchor="middle" className="ctick">{xLabel}</text>
          <text x={10} y={S / 2} textAnchor="middle" className="ctick" transform={`rotate(-90 10 ${S / 2})`}>{yLabel}</text>
          {dots.map((d, i) => <circle key={d.name} cx={X(d.x)} cy={Y(d.y)} r={hover === i ? 6 : 4.5} fill="var(--s1)" className="cdot" />)}
          {far.map((i) => <text key={dots[i].name} x={X(dots[i].x) + (dots[i].x >= 0 ? -7 : 7)} y={Y(dots[i].y) - 7} textAnchor={dots[i].x >= 0 ? "end" : "start"} className="cend">{dots[i].name.slice(0, 22)}</text>)}
          {dots.map((d, i) => <circle key={d.name} cx={X(d.x)} cy={Y(d.y)} r={11} fill="transparent" onMouseEnter={() => setHover(i)} />)}
        </svg>
        {h && <div className="ctip" style={h.x > 0 ? { right: `${100 - (X(h.x) / S) * 100 + 3}%`, top: `${(Y(h.y) / S) * 100}%` } : { left: `${(X(h.x) / S) * 100 + 3}%`, top: `${(Y(h.y) / S) * 100}%` }}>
          <b>{h.name}</b><div><u>{xLabel}</u><span>{n(h.x)}</span></div><div><u>{yLabel}</u><span>{n(h.y)}</span></div><div><u>{h.note}</u></div>
        </div>}
      </div>
    </div>
  );
}
