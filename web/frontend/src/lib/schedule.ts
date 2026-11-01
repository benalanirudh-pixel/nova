// Fixed IST schedule (minutes since midnight): 09:15, 13:30, 15:15, 18:00
const SCHEDULE = [555, 810, 915, 1080];

export function nextRefreshLabel(now = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(now);
  const h = Number(parts.find((p) => p.type === "hour")!.value) % 24;
  const m = Number(parts.find((p) => p.type === "minute")!.value);
  const cur = h * 60 + m;
  const next = SCHEDULE.find((s) => s > cur);
  const diff = next === undefined ? SCHEDULE[0] + 1440 - cur : next - cur;
  return `${Math.floor(diff / 60)}h ${String(diff % 60).padStart(2, "0")}m`;
}
