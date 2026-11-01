import { useEffect, useState } from "react";
import { nextRefreshLabel } from "../lib/schedule";
import type { Freshness } from "../lib/types";

// Mirrors styles/design_tokens.py freshness_level / freshness_color
function level(s: number | null | undefined): { name: string; color: string } {
  if (typeof s !== "number") return { name: "unknown", color: "#617A91" };
  if (s < 600) return { name: "green", color: "#00E6A0" };
  if (s < 7200) return { name: "amber", color: "#FFBD4A" };
  if (s < 43200) return { name: "red", color: "#FF4058" };
  return { name: "critical", color: "#FF1A3A" };
}

export default function StatusBar({ freshness }: { freshness: Freshness | null }) {
  const [next, setNext] = useState(nextRefreshLabel());
  useEffect(() => {
    const t = setInterval(() => setNext(nextRefreshLabel()), 30_000);
    return () => clearInterval(t);
  }, []);
  const lv = level(freshness?.age_seconds);
  return (
    <div className="flex items-center gap-4 text-xs text-secondary">
      <span className="flex items-center gap-1">
        <span className="inline-block h-2 w-2 rounded-full" style={{ background: lv.color }} />
        Data: {freshness?.label ?? "No cache"} ({lv.name})
      </span>
      <span className="text-muted">Next refresh in {next}</span>
    </div>
  );
}
