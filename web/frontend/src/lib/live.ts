import { fetchJSON } from "./api";

/** One read-only quote from /api/live (NSE MCP or Dhan). */
export interface Tick {
  type: "tick"; symbol: string; ltp: number; change: number | null; change_pct: number | null;
  volume: number | null; source: string; as_of: string; max_age_s?: number;
}
export type FeedState = "live" | "delayed" | "closed" | "error";
export interface FeedStatus { type: "feed_status"; state: FeedState; reason: string; as_of: string | null }

const HEARTBEAT_LOST_MS = 30_000; // server beats every 10 s
const DEFAULT_MAX_AGE_S = 30;

let ticks: Record<string, Tick> = {};
let status: FeedStatus | null = null;
let pending: Tick[] = [];
let frame = 0;
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((l) => l());

export function subscribe(l: () => void) {
  listeners.add(l);
  return () => { listeners.delete(l); };
}
export const getTicks = () => ticks;
export const getStatus = () => status;

/** Ticks are applied once per animation frame so a burst re-renders once. */
export function pushTick(t: Tick) {
  pending.push(t);
  if (frame) return;
  frame = requestAnimationFrame(() => {
    frame = 0;
    ticks = { ...ticks, ...Object.fromEntries(pending.map((p) => [p.symbol, p])) };
    pending = [];
    notify();
  });
}

export function setStatus(s: FeedStatus) {
  status = s;
  notify();
}

/** Paint last known values after (re)connect. */
export function loadSnapshot() {
  fetchJSON<{ ticks: Record<string, Tick>; status: FeedStatus }>("/live/snapshot")
    .then((d) => { ticks = { ...ticks, ...d.ticks }; status = d.status; notify(); })
    .catch(() => {});
}

/** Stale by the tick's own as_of, not arrival time. */
export const isStale = (t: Tick, now = Date.now()) =>
  now - Date.parse(t.as_of) > (t.max_age_s ?? DEFAULT_MAX_AGE_S) * 1000;

/** Heartbeat gone quiet -> the last status can't be trusted. */
export const statusLost = (s: FeedStatus | null, now = Date.now()) =>
  !s?.as_of || now - Date.parse(s.as_of) > HEARTBEAT_LOST_MS;

const IST_TIME = new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
export const istTime = (iso: string | null | undefined) => (iso ? `${IST_TIME.format(new Date(iso))} IST` : "unknown time");
