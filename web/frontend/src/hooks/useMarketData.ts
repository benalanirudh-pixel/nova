import { useCallback, useEffect, useRef, useState } from "react";
import { fetchJSON } from "../lib/api";
import { useSSEContext } from "./SSEContext";

export function useMarketData<T>(path: string) {
  const { last, reconnects } = useSSEContext();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0); // only the latest request may set state

  const refresh = useCallback(() => {
    const id = ++seq.current;
    fetchJSON<T>(path)
      .then((d) => { if (id === seq.current) { setData(d); setError(null); } })
      .catch((e: Error) => { if (id === seq.current) setError(e.message); })
      .finally(() => { if (id === seq.current) setLoading(false); });
  }, [path]);

  // refetch on mount, SSE event, and SSE (re)connect
  useEffect(() => { refresh(); }, [refresh, last, reconnects]);
  // invalidate in-flight requests on unmount
  useEffect(() => () => { seq.current++; }, []);
  return { data, loading, error, refresh };
}
