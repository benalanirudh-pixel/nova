import { useEffect, useRef } from "react";
import {
  ColorType, HistogramSeries, LineSeries, createChart, type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import { isNum } from "../lib/format";
import { COLORS } from "../lib/theme";

export interface IndPoint { time: string; value?: number | null; macd?: number | null; signal?: number | null; histogram?: number | null }

interface S { a: ISeriesApi<"Line">; b?: ISeriesApi<"Line">; h?: ISeriesApi<"Histogram"> }

const pts = (d: IndPoint[], k: "value" | "macd" | "signal") =>
  d.flatMap((p) => (isNum(p[k]) ? [{ time: p.time as Time, value: p[k] as number }] : []));

/** kind "rsi": line + 30/70 reference lines (data in `value`). kind "macd": histogram + macd + signal. */
export default function IndicatorChart({ kind, data, title }: { kind: "rsi" | "macd"; data: IndPoint[]; title: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const sRef = useRef<S | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: COLORS.bgPanel }, textColor: COLORS.textSecondary },
      grid: { vertLines: { color: "rgba(11,100,120,0.1)" }, horzLines: { color: "rgba(11,100,120,0.1)" } },
      rightPriceScale: { borderColor: COLORS.border },
      timeScale: { borderColor: COLORS.border },
    });
    if (kind === "rsi") {
      const a = chart.addSeries(LineSeries, { color: COLORS.purple, lineWidth: 2, priceLineVisible: false });
      for (const price of [30, 70]) {
        a.createPriceLine({ price, color: COLORS.textMuted, lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: "" });
      }
      sRef.current = { a };
    } else {
      const h = chart.addSeries(HistogramSeries, { color: COLORS.info, priceLineVisible: false, lastValueVisible: false });
      const a = chart.addSeries(LineSeries, { color: COLORS.accent, lineWidth: 2, priceLineVisible: false });
      const b = chart.addSeries(LineSeries, { color: COLORS.warning, lineWidth: 1, priceLineVisible: false });
      sRef.current = { a, b, h };
    }
    chartRef.current = chart;
    return () => { chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [kind]);

  useEffect(() => {
    const s = sRef.current;
    if (!s) return;
    if (kind === "rsi") s.a.setData(pts(data, "value"));
    else {
      s.a.setData(pts(data, "macd"));
      s.b?.setData(pts(data, "signal"));
      s.h?.setData(data.flatMap((p) => isNum(p.histogram)
        ? [{ time: p.time as Time, value: p.histogram, color: p.histogram >= 0 ? COLORS.positive : COLORS.negative }] : []));
    }
    chartRef.current?.timeScale().fitContent();
  }, [data, kind]);

  return (
    <div className="rounded border border-line/50 bg-panel p-2">
      <div className="mb-1 text-xs text-secondary">{title}</div>
      <div ref={ref} className="h-40 w-full" />
    </div>
  );
}
