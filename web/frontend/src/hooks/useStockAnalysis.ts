import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJSON } from "../lib/api";

export interface TV { time: string; value: number | null }
export interface StockData {
  info: { name?: string | null; symbol?: string; sector?: string | null; price?: number | null; change?: number | null };
  chart: {
    candles: { time: string; open: number | null; high: number | null; low: number | null; close: number | null; volume: number | null }[];
    ema20: TV[]; ema50: TV[]; ema200: TV[]; rsi: TV[];
    macd: { time: string; macd: number | null; signal: number | null; histogram: number | null }[];
  };
  score: { overall: number | null; components: unknown[] };
  levels: { support: (number | null)[]; resistance: (number | null)[] };
  volatility: { atr: number | null; adx: number | null };
  research_factors: unknown[];
  risk: { position_size: number | null; stop_loss: number | null };
  analysis: Record<string, unknown>;
}

/** Latest-request-wins fetch of /stock/{symbol}{suffix}. */
export function useStockFetch<T>(suffix = "") {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0); // only the latest request may set state

  const analyze = useCallback((symbol: string) => {
    const id = ++seq.current;
    setLoading(true);
    setError(null);
    fetchJSON<T>(`/stock/${encodeURIComponent(symbol)}${suffix}`)
      .then((d) => { if (id === seq.current) setData(d); })
      .catch((e: Error) => { if (id === seq.current) { setData(null); setError(e.message); } })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, [suffix]);

  useEffect(() => () => { seq.current++; }, []);
  return { data, loading, error, analyze };
}

export const useStockAnalysis = () => useStockFetch<StockData>();
