import { useCallback, useEffect, useState } from "react";
import { fetchJSON } from "../lib/api";
import type { MarketOverviewData } from "../lib/types";
import { useSSEContext } from "./SSEContext";

export function useMarketData() {
  const { last, reconnects } = useSSEContext();
  const [data, setData] = useState<MarketOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    fetchJSON<MarketOverviewData>("/market-overview")
      .then((d) => { setData(d); setError(null); })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  // refetch on mount, SSE event, and SSE (re)connect
  useEffect(() => { refresh(); }, [refresh, last, reconnects]);
  return { data, loading, error, refresh };
}
