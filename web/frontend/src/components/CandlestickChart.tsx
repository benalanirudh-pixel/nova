import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart,
  type CandlestickData, type IChartApi, type ISeriesApi, type MouseEventParams, type Time,
} from "lightweight-charts";
import { fmt, fmtCompact, isNum } from "../lib/format";
import { COLORS } from "../lib/theme";
import type { Candle } from "../lib/types";
import { Panel, btn } from "./ui";

function ema(closes: number[], period: number): (number | null)[] {
  const k = 2 / (period + 1);
  let prev: number | null = null;
  return closes.map((c, i) => {
    if (i < period - 1) return null;
    prev = prev === null ? closes.slice(0, period).reduce((a, b) => a + b, 0) / period : c * k + prev * (1 - k);
    return prev;
  });
}

interface Series {
  candle: ISeriesApi<"Candlestick">;
  ema: ISeriesApi<"Line">;
  vol: ISeriesApi<"Histogram">;
}
interface Legend { t: string; o: number; h: number; l: number; c: number; v?: number; e?: number }

const RANGES = { "1M": 1, "3M": 3, "6M": 6, ALL: 0 } as const;
type Range = keyof typeof RANGES;

const timeStr = (t: Time) =>
  typeof t === "string" ? t : typeof t === "number" ? new Date(t * 1000).toISOString().slice(0, 10)
    : `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`;

function applyRange(chart: IChartApi | null, ok: Candle[], r: Range) {
  if (!chart || ok.length === 0) return;
  if (r === "ALL") { chart.timeScale().fitContent(); return; }
  const last = ok[ok.length - 1].t;
  const from = new Date(`${last}T00:00:00Z`);
  from.setUTCMonth(from.getUTCMonth() - RANGES[r]);
  const f = from.toISOString().slice(0, 10);
  chart.timeScale().setVisibleRange({ from: (f < ok[0].t ? ok[0].t : f) as Time, to: last as Time });
}

/** Daily candles + client-side EMA 20 + volume, with range buttons, toggles and a crosshair OHLC legend. */
export default function CandlestickChart({ candles, title, right }: { candles: Candle[]; title: string; right?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Series | null>(null);
  const okRef = useRef<Candle[]>([]);
  const fitted = useRef(false);
  const [range, setRange] = useState<Range>("ALL");
  const [showEma, setShowEma] = useState(true);
  const [showVol, setShowVol] = useState(true);
  const [hover, setHover] = useState<Legend | null>(null);
  const [lastBar, setLastBar] = useState<Legend | null>(null);

  // create chart once
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: COLORS.bgPanel }, textColor: COLORS.textSecondary, fontSize: 11 },
      grid: { vertLines: { color: "rgba(11,100,120,0.12)" }, horzLines: { color: "rgba(11,100,120,0.12)" } },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border, lockVisibleTimeRangeOnResize: true },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: COLORS.positive, downColor: COLORS.negative, borderVisible: false,
      wickUpColor: COLORS.positive, wickDownColor: COLORS.negative,
    });
    const line = chart.addSeries(LineSeries, { color: COLORS.accent, lineWidth: 1, priceLineVisible: false, lastValueVisible: false });
    // own price scale pinned to the bottom 20% so volume never squashes candles
    const vol = chart.addSeries(HistogramSeries, {
      color: "rgba(0,229,255,0.25)", priceFormat: { type: "volume" }, priceScaleId: "vol",
      priceLineVisible: false, lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    const onMove = (p: MouseEventParams) => {
      const b = (p.time !== undefined ? p.seriesData.get(candle) : undefined) as CandlestickData<Time> | undefined;
      if (!b || !isNum(b.open)) { setHover(null); return; }
      const e = p.seriesData.get(line), v = p.seriesData.get(vol);
      setHover({
        t: timeStr(b.time), o: b.open, h: b.high, l: b.low, c: b.close,
        e: e && "value" in e ? e.value : undefined, v: v && "value" in v ? v.value : undefined,
      });
    };
    chart.subscribeCrosshairMove(onMove);
    chartRef.current = chart;
    seriesRef.current = { candle, ema: line, vol };
    fitted.current = false;
    return () => { chart.unsubscribeCrosshairMove(onMove); chart.remove(); chartRef.current = null; seriesRef.current = null; };
  }, []);

  // update data in place; fit only on first non-empty load
  useEffect(() => {
    const s = seriesRef.current;
    if (!s) return;
    const ok = candles.filter((c) => isNum(c.o) && isNum(c.h) && isNum(c.l) && isNum(c.c));
    okRef.current = ok;
    s.candle.setData(ok.map((c) => ({ time: c.t as Time, open: c.o, high: c.h, low: c.l, close: c.c })));
    const e = ema(ok.map((c) => c.c), 20);
    s.ema.setData(ok.flatMap((c, i) => (e[i] === null ? [] : [{ time: c.t as Time, value: e[i]! }])));
    s.vol.setData(ok.filter((c) => isNum(c.v)).map((c) => ({ time: c.t as Time, value: c.v })));
    const last = ok[ok.length - 1];
    setLastBar(last ? { t: last.t, o: last.o, h: last.h, l: last.l, c: last.c, v: isNum(last.v) ? last.v : undefined, e: e[ok.length - 1] ?? undefined } : null);
    if (!fitted.current && ok.length > 0) { applyRange(chartRef.current, ok, range); fitted.current = true; }
  }, [candles]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { applyRange(chartRef.current, okRef.current, range); }, [range]);
  useEffect(() => { seriesRef.current?.ema.applyOptions({ visible: showEma }); }, [showEma]);
  useEffect(() => { seriesRef.current?.vol.applyOptions({ visible: showVol }); }, [showVol]);

  const L = hover ?? lastBar;
  const up = L ? L.c >= L.o : true;
  const toggle = (on: boolean) => `${btn} ${on ? "border-accent/70 text-accent" : "border-line/50 text-muted hover:text-secondary"}`;

  return (
    <Panel title={title} bodyClass="p-0" right={<>
      {right}
      <div className="flex gap-0.5" role="group" aria-label="Visible range">
        {(Object.keys(RANGES) as Range[]).map((r) => (
          <button key={r} onClick={() => setRange(r)} aria-pressed={range === r} className={toggle(range === r)}>{r}</button>
        ))}
      </div>
      <button onClick={() => setShowEma(!showEma)} aria-pressed={showEma} className={toggle(showEma)}>EMA20</button>
      <button onClick={() => setShowVol(!showVol)} aria-pressed={showVol} className={toggle(showVol)}>VOL</button>
    </>}>
      <div className="relative h-[22rem] w-full">
        <div ref={ref} className="absolute inset-0" />
        {L && (
          <div className="pointer-events-none absolute left-2 top-1 z-10 flex flex-wrap gap-x-2 font-mono text-[11px] tabular-nums">
            <span className="text-secondary">{L.t}</span>
            {(["o", "h", "l", "c"] as const).map((k) => (
              <span key={k}><span className="text-muted">{k.toUpperCase()}</span> <span className={up ? "text-positive" : "text-negative"}>{fmt(L[k])}</span></span>
            ))}
            {showVol && <span><span className="text-muted">V</span> <span className="text-secondary">{fmtCompact(L.v)}</span></span>}
            {showEma && <span><span className="text-muted">EMA20</span> <span className="text-accent">{fmt(L.e)}</span></span>}
          </div>
        )}
        {candles.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">No chart data</div>}
      </div>
    </Panel>
  );
}
