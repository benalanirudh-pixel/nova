import { useEffect, useRef, useState } from "react";
import {
  CandlestickSeries, ColorType, CrosshairMode, LineStyle, createChart,
  type IChartApi, type IPriceLine, type ISeriesApi, type MouseEventParams, type Time,
} from "lightweight-charts";
import { fmt, isNum } from "../lib/format";
import { COLORS } from "../lib/theme";
import { cn } from "@/lib/utils";

export interface Candle { t: string; o: number; h: number; l: number; c: number }
export interface Level { label: string; price: number | null | undefined; color: string; dashed?: boolean }

const RANGES = { "1M": 1, "3M": 3, "6M": 6 } as const;
type Range = keyof typeof RANGES;

function fit(chart: IChartApi, bars: Candle[], r: Range) {
  if (!bars.length) return;
  const last = bars[bars.length - 1].t, from = new Date(`${last}T00:00:00Z`);
  from.setUTCMonth(from.getUTCMonth() - RANGES[r]);
  const f = from.toISOString().slice(0, 10);
  chart.timeScale().setVisibleRange({ from: (f < bars[0].t ? bars[0].t : f) as Time, to: last as Time });
}

/** Index daily candles with the desk's option levels drawn as labelled price lines. */
export default function LevelsChart({ candles, levels, className = "" }: { candles: Candle[]; levels: Level[]; className?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const api = useRef<{ chart: IChartApi; series: ISeriesApi<"Candlestick">; lines: IPriceLine[] } | null>(null);
  const [range, setRange] = useState<Range>("3M");
  const [hover, setHover] = useState<Candle | null>(null);
  const byTime = useRef(new Map<string, Candle>());
  byTime.current = new Map(candles.map((c) => [c.t, c]));

  useEffect(() => {
    if (!el.current) return;
    const chart = createChart(el.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: COLORS.bgPanel }, textColor: COLORS.textSecondary, fontSize: 11, fontFamily: "IBM Plex Mono, Consolas, monospace" },
      grid: { vertLines: { color: COLORS.grid }, horzLines: { color: COLORS.grid } },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: COLORS.border, scaleMargins: { top: 0.08, bottom: 0.08 } },
      timeScale: { borderColor: COLORS.border },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.positive, downColor: COLORS.negative, borderVisible: false,
      wickUpColor: COLORS.positive, wickDownColor: COLORS.negative,
    });
    const onMove = (p: MouseEventParams) => setHover(p.time ? byTime.current.get(String(p.time)) ?? null : null);
    chart.subscribeCrosshairMove(onMove);
    api.current = { chart, series, lines: [] };
    return () => { chart.unsubscribeCrosshairMove(onMove); chart.remove(); api.current = null; };
  }, []);

  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.series.setData(candles.map((c) => ({ time: c.t as Time, open: c.o, high: c.h, low: c.l, close: c.c })));
    fit(a.chart, candles, range);
  }, [candles]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (api.current) fit(api.current.chart, candles, range); }, [range]); // eslint-disable-line react-hooks/exhaustive-deps

  // price lines are cheap: rebuild them whenever the levels change
  const key = levels.map((l) => `${l.label}:${l.price}`).join("|");
  useEffect(() => {
    const a = api.current;
    if (!a) return;
    a.lines.forEach((l) => a.series.removePriceLine(l));
    a.lines = levels.filter((l) => isNum(l.price)).map((l) => a.series.createPriceLine({
      price: l.price as number, color: l.color, lineWidth: 1, lineStyle: l.dashed ? LineStyle.Dashed : LineStyle.Solid,
      axisLabelVisible: true, title: l.label,
    }));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps

  const bar = hover ?? candles[candles.length - 1];
  const up = bar ? bar.c >= bar.o : true;
  return (
    <div className={cn("relative h-full min-h-[18rem]", className)}>
      <div ref={el} className="absolute inset-0" />
      <div className="pointer-events-none absolute left-2 top-1.5 z-10 flex flex-wrap gap-x-2.5 font-mono text-[11px] tabular-nums">
        {bar && <>
          <span className="text-secondary">{bar.t}</span>
          {(["o", "h", "l", "c"] as const).map((k) => <span key={k}><span className="text-muted">{k.toUpperCase()} </span><span className={up ? "text-positive" : "text-negative"}>{fmt(bar[k])}</span></span>)}
        </>}
      </div>
      <div className="absolute right-[4.5rem] top-1.5 z-10 flex gap-0.5" role="group" aria-label="Visible range">
        {(Object.keys(RANGES) as Range[]).map((r) => (
          <button key={r} onClick={() => setRange(r)} aria-pressed={range === r}
            className={cn("rounded border px-1.5 py-px text-[10.5px] font-semibold focus:outline-none focus-visible:ring-1 focus-visible:ring-accent",
              range === r ? "border-accent/70 bg-panel text-accent" : "border-line/50 bg-panel/80 text-muted hover:text-secondary")}>{r}</button>
        ))}
      </div>
      {candles.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-[12px] text-muted">No daily history for this index.</div>}
    </div>
  );
}
