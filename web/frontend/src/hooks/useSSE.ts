import { useEffect, useState } from "react";

export interface SSEEvent {
  type: "refresh_complete" | "refresh_failed";
  timestamp: string;
}

/** Last server event. `reconnects` bumps on every (re)open so pages can refetch current state. */
export function useSSE() {
  const [last, setLast] = useState<SSEEvent | null>(null);
  const [reconnects, setReconnects] = useState(0);

  useEffect(() => {
    // EventSource auto-reconnects on error; onopen fires on each reconnect.
    const es = new EventSource("/api/events");
    es.onopen = () => setReconnects((n) => n + 1);
    es.onmessage = (m) => {
      try { setLast(JSON.parse(m.data)); } catch { /* ignore malformed */ }
    };
    return () => es.close();
  }, []);

  return { last, reconnects };
}
