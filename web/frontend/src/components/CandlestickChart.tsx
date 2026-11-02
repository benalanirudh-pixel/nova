import { useEffect, useRef } from "react";
import {
  CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart, type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import { isNum } from "../lib/format";
import type { Candle } from "../lib/types";

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

export default function CandlestickChart({ candles }: { candles: Candle[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Series | null>(null);
  const fitted = useRef(false);

  // create chart once
  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#071923" }, textColor: "#91A9BE" },
      grid: { vertLines: { color: "rgba(11,100,120,0.1)" }, horzLines: { color: "rgba(11,100,120,0.1)" } },
      rightPriceScale: { borderColor: "#0B6478" },
      timeScale: { borderColor: "#0B6478", lockVisibleTimeRangeOnResize: true },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: "#00E6A8", downColor: "#FF405A", borderVisible: false,
      wickUpColor: "#00E6A8", wickDownColor: "#FF405A",
    });
    const line = chart.addSeries(LineSeries, { color: "#00E5FF", lineWidth: 2, title: "EMA 20", priceLineVisible: false });
    // own price scale pinned to the bottom 20% so volume never squashes candles
    const vol = chart.addSeries(HistogramSeries, {
      color: "rgba(0,229,255,0.3)", priceFormat: { type: "volume" }, priceScaleId: "vol",
      priceLineVisible: false, lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    chartRef.current = chart;
    seriesRef.current = { candle, ema: line, vol };
    fitted.current = false;
    return () => { chart.remove(); chartRef.current = null; seriesRef.current = null; };
  }, []);

  // update data in place; fit only on first non-empty load
  useEffect(() => {
    const s = seriesRef.current;
    if (!s) return;
    const ok = candles.filter((c) => isNum(c.o) && isNum(c.h) && isNum(c.l) && isNum(c.c));
    s.candle.setData(ok.map((c) => ({ time: c.t as Time, open: c.o, high: c.h, low: c.l, close: c.c })));
    const e = ema(ok.map((c) => c.c), 20);
    s.ema.setData(ok.flatMap((c, i) => (e[i] === null ? [] : [{ time: c.t as Time, value: e[i]! }])));
    s.vol.setData(ok.filter((c) => isNum(c.v)).map((c) => ({ time: c.t as Time, value: c.v })));
    if (!fitted.current && ok.length > 0) { chartRef.current?.timeScale().fitContent(); fitted.current = true; }
  }, [candles]);

  return (
    <div className="relative h-full min-h-[20rem] w-full">
      <div ref={ref} className="absolute inset-0" />
      {candles.length === 0 && <div className="absolute inset-0 flex items-center justify-center text-muted">No chart data</div>}
    </div>
  );
}
