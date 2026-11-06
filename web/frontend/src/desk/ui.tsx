import { useState, type CSSProperties, type ReactNode } from "react";
import { fmt, isNum } from "../lib/format";

export const n = (v: unknown, d = 2) => (isNum(v) ? fmt(v, d) : "n/a");
export const sg = (v: unknown, d = 2) => (isNum(v) ? `${v > 0 ? "+" : v < 0 ? "−" : ""}${fmt(Math.abs(v), d)}` : "n/a");
export const pc = (v: unknown, d = 2) => (isNum(v) ? `${sg(v, d)}%` : "n/a");
const tone = (v: unknown) => (!isNum(v) || v === 0 ? "" : v > 0 ? "up" : "dn");
export const big = (v: unknown) => (!isNum(v) || !v ? "n/a" : v >= 1e7 ? `${fmt(v / 1e7, 2)} Cr` : v >= 1e5 ? `${fmt(v / 1e5, 2)} L` : fmt(v, 0));
export const dayMonth = (t: unknown) => {
  const p = String(t ?? "").slice(0, 10).split("-");
  return p.length < 3 ? String(t ?? "") : `${+p[2]} ${"Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(" ")[+p[1] - 1]}`;
};

export const Pct = ({ v, d }: { v: unknown; d?: number }) => <span className={tone(v)}>{pc(v, d)}</span>;
export const Sgn = ({ v, d = 0 }: { v: unknown; d?: number }) => <span className={tone(v)}>{sg(v, d)}</span>;
export const Flag = ({ children }: { children: ReactNode }) => <span className="flag">{children}</span>;

export function Pane({ area, title, sub, flag, pad, children }: { area: string; title: ReactNode; sub?: ReactNode; flag?: ReactNode; pad?: boolean; children: ReactNode }) {
  return (
    <section className="pane" style={{ gridArea: area }}>
      <div className="ph"><h2>{title}</h2><span className="s">{sub}</span>{flag && <Flag>{flag}</Flag>}</div>
      <div className={`body${pad ? " pad" : ""}`}>{children}</div>
    </section>
  );
}

export const Block = ({ title, sub, wide, children }: { title: ReactNode; sub?: ReactNode; wide?: boolean; children: ReactNode }) => (
  <section className={`blk${wide ? " wide" : ""}`}>
    <div className="bh"><h3>{title}</h3><span>{sub}</span></div>
    {children}
  </section>
);

export const Kv = ({ rows }: { rows: [ReactNode, ReactNode][] }) => (
  <div className="kv">{rows.map(([k, v], i) => <div key={i}><u>{k}</u><b>{v}</b></div>)}</div>
);

export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>;

export interface Col<R> {
  h: ReactNode;
  v: (r: R) => ReactNode;
  /** Value used for sorting; sortable tables only. */
  sort?: (r: R) => number | string | null | undefined;
  text?: boolean;
  bold?: boolean;
  heat?: { max: number; of: (r: R) => number | null | undefined };
}

const heatStyle = (v: number | null | undefined, max: number): CSSProperties | undefined =>
  isNum(v) ? { backgroundImage: `linear-gradient(rgba(${v > 0 ? "var(--hp)" : "var(--hn)"},${Math.min(0.3, (Math.abs(v) / max) * 0.3).toFixed(3)}) 0 0)` } : undefined;

export function Table<R>({ cols, rows, groups, sortable, limit, onRow, isOn }: {
  cols: Col<R>[]; rows: R[]; groups?: [string, number][]; sortable?: boolean; limit?: number;
  onRow?: (r: R) => void; isOn?: (r: R) => boolean;
}) {
  const [sort, setSort] = useState<{ i: number; dir: number } | null>(null);
  let list = rows;
  if (sort) {
    const key = cols[sort.i].sort;
    if (key) {
      list = [...rows].sort((a, b) => {
        const x = key(a), y = key(b);
        if (x == null) return 1;
        if (y == null) return -1;
        return (typeof x === "string" ? x.localeCompare(String(y)) : (y as number) - x) * sort.dir;
      });
    }
  }
  const pick = (i: number) => setSort((s) => (s?.i === i ? { i, dir: -s.dir } : { i, dir: 1 }));
  return (
    <table>
      <thead>
        {groups && <tr>{groups.map(([t, w], i) => <th key={i} className="grp" colSpan={w}>{t}</th>)}</tr>}
        <tr>
          {cols.map((c, i) => {
            const can = sortable && !!c.sort;
            return (
              <th key={i} className={`${c.text ? "x" : ""}${can ? " so" : ""}`} aria-sort={sort?.i === i ? (sort.dir > 0 ? "descending" : "ascending") : undefined}>
                {can ? <button type="button" onClick={() => pick(i)}>{c.h}{sort?.i === i ? (sort.dir > 0 ? " ↓" : " ↑") : ""}</button> : c.h}
              </th>
            );
          })}
        </tr>
      </thead>
      <tbody>
        {(limit ? list.slice(0, limit) : list).map((r, i) => (
          <tr key={i} className={`${isOn?.(r) ? "on" : ""}${onRow ? " link" : ""}`} onClick={onRow && (() => onRow(r))}>
            {cols.map((c, j) => (
              <td key={j} className={`${c.text ? "x" : ""}${c.bold ? " b" : ""}`} style={c.heat ? heatStyle(c.heat.of(r), c.heat.max) : undefined}>
                {j === 0 && onRow ? <button type="button" className="rowbtn" onClick={(e) => { e.stopPropagation(); onRow(r); }}>{c.v(r)}</button> : c.v(r)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
