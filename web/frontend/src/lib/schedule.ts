// Fixed IST schedule (minutes since midnight): 09:15, 13:30, 15:15, 18:00
const SCHEDULE = [555, 810, 915, 1080];

function istParts(now: Date) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", weekday: "short", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(now);
  const get = (t: string) => parts.find((p) => p.type === t)!.value;
  return { h: Number(get("hour")) % 24, m: Number(get("minute")), s: get("second"), wd: get("weekday") };
}

export function nextRefreshLabel(now = new Date()): string {
  const { h, m } = istParts(now);
  const cur = h * 60 + m;
  const next = SCHEDULE.find((s) => s > cur);
  const diff = next === undefined ? SCHEDULE[0] + 1440 - cur : next - cur;
  return `${Math.floor(diff / 60)}h ${String(diff % 60).padStart(2, "0")}m`;
}

/** IST clock text and NSE session by time/weekday only (holidays are not checked). */
export function istSession(now = new Date()) {
  const { h, m, s, wd } = istParts(now);
  const cur = h * 60 + m;
  const weekday = !["Sat", "Sun"].includes(wd);
  const session = !weekday ? "Closed" : cur >= 540 && cur < 555 ? "Pre-open" : cur >= 555 && cur < 930 ? "Open" : "Closed";
  return { clock: `${wd} ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s} IST`, session };
}
