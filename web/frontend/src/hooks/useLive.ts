import { useEffect, useState, useSyncExternalStore } from "react";
import { fetchJSON } from "../lib/api";
import { getStatus, getTicks, isStale, statusLost, subscribe } from "../lib/live";

/** Re-render on a clock so staleness flips without a new tick. */
function useNow(ms = 5000) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}

export function useLiveQuote(symbol: string | null | undefined) {
  const tick = useSyncExternalStore(subscribe, () => (symbol ? getTicks()[symbol.toUpperCase()] : undefined));
  const now = useNow();
  return tick ? { ...tick, stale: isStale(tick, now) } : null;
}

export function useFeedStatus() {
  const status = useSyncExternalStore(subscribe, getStatus);
  const now = useNow();
  return { status, lost: statusLost(status, now) };
}

const WATCH_RENEW_MS = 60_000; // server drops a symbol after 120 s

/** Ask the server to poll these symbols while this component is mounted. */
export function useLiveWatch(symbols: (string | null | undefined)[]) {
  const key = symbols.filter(Boolean).map((s) => s!.toUpperCase()).sort().join(",");
  useEffect(() => {
    if (!key) return;
    const post = () => fetchJSON("/live/watch", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ symbols: key.split(",") }),
    }).catch(() => {});
    post();
    const t = setInterval(post, WATCH_RENEW_MS);
    return () => clearInterval(t);
  }, [key]);
}
