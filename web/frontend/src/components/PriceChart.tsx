import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, createChart,
  type IChartApi, type ISeriesApi, type MouseEventParams, type Time,
} from "lightweight-charts";
import type { StockData, TV } from "../hooks/useStockAnalysis";
import { fmt, fmtCompact, isNum } from "../lib/format";
import { COLORS } from "../lib/theme";
import { btn } from "./ui";

type Chart = StockData["chart"];
const EMAS = [
  { key: "ema20", label: "EMA 20", color: COLORS.accent },
  { key: "ema50", label: "EMA 50", color: COLORS.info },
  { key: "ema200", label: "EMA 200", color: COLORS.purple },
] as const;
type EmaKey = (typeof EMAS)[number]["key"];
const RANGES = { "1M": 1, "3M": 3, "6M": 6, "1Y": 12, All: 0 } as const;
type Range = keyof typeof RANGES;
interface Bar { t: string; o: number; h: number; l: number; c: number; v: number | null }

const toLine = (s: TV[]) => s.filter((p) => isNum(p.value)).map((p) => ({ time: p.time as Time, value: p.value as number }));

function applyRange(chart: IChartApi, bars: Bar[], r: Range) {
  if (!bars.length) return;
  if (r === "All") { chart.timeScale().fitContent(); return; }
  const last = bars[bars.length - 1].t;
  const from = new Date(`${last}T00:00:00Z`);
  from.setUTCMonth(from.getUTCMonth() - RANGES[r]);
  const f = from.toISOString().slice(0, 10);
  chart.timeScale().setVisibleRange({ from: (f < bars[0].t ? bars[0].t : f) as Time, to: last as Time });
}

/** Daily candles + volume + engine EMAs. Scroll to zoom, drag to pan, crosshair shows OHLC. */
export default function PriceChart({ chart }: { chart: Chart }) {
  const el = useRef<HTMLDivElement>(null);
  const api = useRef<{ chart: IChartApi; candle: ISeriesApi<"Candlestick">; vol: ISeriesApi<"Histogram">; ema: Record<EmaKey, ISeriesApi<"Line">> } | null>(null);
  const [range, setRange] = useState<Range>("6M");
  const [on, setOn] = useState<Record<EmaKey | "vol", boolean>>({ ema20: true, ema50: true, ema200: false, vol: true });
  const [hover, setHover] = useState<Bar | null>(null);

  const bars: Bar[] = chart.candles.flatMap((c) =>
    isNum(c.open) && isNum(c.high) && isNum(c.low) && isNum(c.close) ? [{ t: c.time, o: c.open, h: c.high, l: c.low, c: c.close, v: c.volume }] : []);
  const byTime = useRef(new Map<string, Bar>());
  byTime.current = new Map(bars.map((b) => [b.t, b]));

  useEffect(() => {
    if (!el.current) return;
    const c = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: COLORS.bgPanel }, textColor: COLORS.textSecondary, fontSize: 11, fontFamily: "IBM Plex Mono, Consolas, monospace" },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border },
    });
    const candle = c.addSeries(CandlestickSeries, {
      upColor: COLORS.positive, downColor: COLORS.negative, borderVisible: false,
      wickUpColor: COLORS.positive, wickDownColor: COLORS.negative,
    });
    // own scale pinned to the bottom 20% so volume never squashes candles
    const vol = c.addSeries(HistogramSeries, { color: COLORS.volume, priceFormat: { type: "volume" }, priceScaleId: "vol", priceLineVisible: false, lastValueVisible: false });
    c.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    const ema = Object.fromEntries(EMAS.map((e) => [e.key, c.addSeries(LineSeries, {
      color: e.color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    })])) as Record<EmaKey, ISeriesApi<"Line">>;
    const onMove = (p: MouseEventParams) => setHover(p.time !== undefined ? byTime.current.get(String(p.time)) ?? null : null);
    c.subscribeCrosshairMove(onMove);
    api.current = { chart: c, candle, vol, ema };
    return () => { c.unsubscribeCrosshairMove(onMove); c.remove(); api.current = null; };
  }, []);

  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.candle.setData(bars.map((b) => ({ time: b.t as Time, open: b.o, high: b.h, low: b.l, close: b.c })));
    a.vol.setData(bars.filter((b) => isNum(b.v)).map((b) => ({
      time: b.t as Time, value: b.v as number, color: b.c >= b.o ? `${COLORS.positive}55` : `${COLORS.negative}55`,
    })));
    for (const e of EMAS) a.ema[e.key].setData(toLine(chart[e.key]));
    applyRange(a.chart, bars, range);
  }, [chart]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (api.current) applyRange(api.current.chart, bars, range); }, [range]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    for (const e of EMAS) a.ema[e.key].applyOptions({ visible: on[e.key] });
    a.vol.applyOptions({ visible: on.vol });
  }, [on]);

  const L = hover ?? bars[bars.length - 1];
  const tog = (k: EmaKey | "vol") => setOn((s) => ({ ...s, [k]: !s[k] }));
  const cls = (active: boolean) => `${btn} ${active ? "border-accent/70 text-accent" : "border-line/50 text-muted hover:text-secondary"}`;

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-wrap items-center gap-1.5 border-b border-line/30 px-2 py-1 text-[11px]">
        <span className={`${btn} border-accent/70 text-accent`} title="Daily bars only; intraday history isn't available from the backend">1D</span>
        <span className="mx-1 h-3.5 w-px bg-line/40" />
        {(Object.keys(RANGES) as Range[]).map((r) => <button key={r} className={cls(range === r)} onClick={() => setRange(r)} aria-pressed={range === r}>{r}</button>)}
        <span className="mx-1 h-3.5 w-px bg-line/40" />
        {EMAS.map((e) => (
          <button key={e.key} className={cls(on[e.key])} onClick={() => tog(e.key)} aria-pressed={on[e.key]} title={`${e.label} from the technical engine`}>
            <span className="mr-1 inline-block h-0.5 w-2.5 align-middle" style={{ background: e.color }} />{e.label}
          </button>
        ))}
        <button className={cls(on.vol)} onClick={() => tog("vol")} aria-pressed={on.vol}>Volume</button>
        {L && (
          <span className="ml-auto font-mono tabular-nums text-secondary">
            <span className="text-muted">{L.t} </span>
            O <span className={L.c >= L.o ? "text-positive" : "text-negative"}>{fmt(L.o)}</span>{" "}
            H <span className="text-fg">{fmt(L.h)}</span> L <span className="text-fg">{fmt(L.l)}</span>{" "}
            C <span className={L.c >= L.o ? "text-positive" : "text-negative"}>{fmt(L.c)}</span>{" "}
            V <span className="text-fg">{fmtCompact(L.v)}</span>
          </span>
        )}
      </div>
      <div className="relative min-h-0 flex-1">
        <div ref={el} className="absolute inset-0" />
        {!bars.length && <div className="absolute inset-0 grid place-items-center text-[12px] text-muted">No price history from the NSE feed for this symbol.</div>}
      </div>
    </div>
  );
}
