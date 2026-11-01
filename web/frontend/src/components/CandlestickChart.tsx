import { useEffect, useRef } from "react";
import {
  CandlestickSeries, ColorType, HistogramSeries, LineSeries, createChart, type Time,
} from "lightweight-charts";
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

export default function CandlestickChart({ candles }: { candles: Candle[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const empty = candles.length === 0;

  useEffect(() => {
    if (!ref.current || empty) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "#071923" }, textColor: "#91A9BE" },
      grid: { vertLines: { color: "rgba(11,100,120,0.1)" }, horzLines: { color: "rgba(11,100,120,0.1)" } },
      rightPriceScale: { borderColor: "#0B6478" },
      timeScale: { borderColor: "#0B6478" },
    });
    const cs = chart.addSeries(CandlestickSeries, {
      upColor: "#00E6A8", downColor: "#FF405A", borderVisible: false,
      wickUpColor: "#00E6A8", wickDownColor: "#FF405A",
    });
    cs.setData(candles.map((c) => ({ time: c.t as Time, open: c.o, high: c.h, low: c.l, close: c.c })));

    const line = chart.addSeries(LineSeries, { color: "#00E5FF", lineWidth: 2, title: "EMA 20", priceLineVisible: false });
    const e = ema(candles.map((c) => c.c), 20);
    line.setData(candles.flatMap((c, i) => (e[i] === null ? [] : [{ time: c.t as Time, value: e[i]! }])));

    // own price scale pinned to the bottom 20% so volume never squashes candles
    const vol = chart.addSeries(HistogramSeries, {
      color: "rgba(0,229,255,0.3)", priceFormat: { type: "volume" }, priceScaleId: "vol",
      priceLineVisible: false, lastValueVisible: false,
    });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    vol.setData(candles.map((c) => ({ time: c.t as Time, value: c.v })));

    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [candles, empty]);

  if (empty) return <div className="flex h-full min-h-[20rem] items-center justify-center text-muted">No chart data</div>;
  return <div ref={ref} className="h-full min-h-[20rem] w-full" />;
}
