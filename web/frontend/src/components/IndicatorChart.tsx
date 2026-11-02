import { useEffect, useRef } from "react";
import {
  ColorType, HistogramSeries, LineSeries, createChart, type IChartApi, type ISeriesApi, type Time,
} from "lightweight-charts";
import { isNum } from "../lib/format";
import { COLORS } from "../lib/theme";
import { Panel } from "./ui";

export interface IndPoint { time: string; value?: number | null; macd?: number | null; signal?: number | null; histogram?: number | null }

interface S { a: ISeriesApi<"Line">; b?: ISeriesApi<"Line">; h?: ISeriesApi<"Histogram"> }

// gaps stay as whitespace points so bar indices line up with a synced price chart
const pts = (d: IndPoint[], k: "value" | "macd" | "signal") =>
  d.map((p) => (isNum(p[k]) ? { time: p.time as Time, value: p[k] as number } : { time: p.time as Time }));

export interface ChartProps { className?: string; fill?: boolean; onChart?: (c: IChartApi | null) => void }

/** kind "rsi": line + 30/70 reference lines (data in `value`). kind "macd": histogram + macd + signal. */
export default function IndicatorChart({ kind, data, title, className = "", fill, onChart }:
  { kind: "rsi" | "macd"; data: IndPoint[]; title: string } & ChartProps) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const sRef = useRef<S | null>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: COLORS.bgPanel }, textColor: COLORS.textSecondary, fontSize: 11 },
      grid: { vertLines: { color: "rgba(11,100,120,0.1)" }, horzLines: { color: "rgba(11,100,120,0.1)" } },
      rightPriceScale: { borderColor: COLORS.border, minimumWidth: 64 },
      timeScale: { borderColor: COLORS.border, lockVisibleTimeRangeOnResize: true },
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
    onChart?.(chart);
    return () => { onChart?.(null); chart.remove(); chartRef.current = null; sRef.current = null; };
  }, [kind]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const s = sRef.current;
    if (!s) return;
    if (kind === "rsi") s.a.setData(pts(data, "value"));
    else {
      s.a.setData(pts(data, "macd"));
      s.b?.setData(pts(data, "signal"));
      s.h?.setData(data.map((p) => isNum(p.histogram)
        ? { time: p.time as Time, value: p.histogram, color: p.histogram >= 0 ? COLORS.positive : COLORS.negative } : { time: p.time as Time }));
    }
    chartRef.current?.timeScale().fitContent();
  }, [data, kind]);

  return (
    <Panel title={title} bodyClass="p-0" className={className} fill={fill}>
      <div ref={ref} className={fill ? "absolute inset-0" : "h-36 w-full"} />
    </Panel>
  );
}
