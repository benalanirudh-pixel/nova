import { useEffect, useState } from "react";
import { loadSnapshot, pushTick, setStatus } from "../lib/live";

export interface SSEEvent {
  type: "refresh_complete" | "refresh_failed";
  timestamp: string;
}

/** Last server refresh event. `reconnects` bumps on every (re)open so pages can refetch current state.
 *  Live ticks and feed status go to lib/live so they never trigger page refetches. */
export function useSSE() {
  const [last, setLast] = useState<SSEEvent | null>(null);
  const [reconnects, setReconnects] = useState(0);

  useEffect(() => {
    // EventSource auto-reconnects on error; onopen fires on each reconnect.
    const es = new EventSource("/api/events");
    es.onopen = () => { setReconnects((n) => n + 1); loadSnapshot(); };
    es.onmessage = (m) => {
      let ev;
      try { ev = JSON.parse(m.data); } catch { return; /* ignore malformed */ }
      if (ev?.type === "tick") pushTick(ev);
      else if (ev?.type === "feed_status") setStatus(ev);
      else if (ev?.type === "refresh_complete" || ev?.type === "refresh_failed") setLast(ev);
      else if (ev && typeof ev === "object" && ev.symbol && ev.ltp !== undefined) pushTick(ev);
    };
    return () => es.close();
  }, []);

  return { last, reconnects };
}
