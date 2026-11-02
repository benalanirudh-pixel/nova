import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJSON } from "../lib/api";
import type { MarketOverviewData } from "../lib/types";
import { useSSEContext } from "./SSEContext";

export function useMarketData() {
  const { last, reconnects } = useSSEContext();
  const [data, setData] = useState<MarketOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0); // only the latest request may set state

  const refresh = useCallback(() => {
    const id = ++seq.current;
    fetchJSON<MarketOverviewData>("/market-overview")
      .then((d) => { if (id === seq.current) { setData(d); setError(null); } })
      .catch((e: Error) => { if (id === seq.current) setError(e.message); })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, []);

  // refetch on mount, SSE event, and SSE (re)connect
  useEffect(() => { refresh(); }, [refresh, last, reconnects]);
  // invalidate in-flight requests on unmount
  useEffect(() => () => { seq.current++; }, []);
  return { data, loading, error, refresh };
}
