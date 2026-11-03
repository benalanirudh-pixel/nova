import { useEffect, useState } from "react";
import { useFeedStatus, useLiveQuote } from "../hooks/useLive";
import { istTime } from "../lib/live";
import { istSession } from "../lib/schedule";
import type { MarketOverviewData, Quote } from "../lib/types";
import { Change, Chip, Flash, Num } from "./ui";

// Mirrors styles/design_tokens.py freshness_level / freshness_color
function level(s: number | null | undefined): { name: string; cls: string } {
  if (typeof s !== "number") return { name: "unknown", cls: "bg-muted" };
  if (s < 600) return { name: "fresh", cls: "bg-positive" };
  if (s < 7200) return { name: "aging", cls: "bg-warning" };
  return { name: "stale", cls: "bg-negative" };
}

function SessionClock() {
  const [now, setNow] = useState(istSession);
  useEffect(() => {
    const t = setInterval(() => setNow(istSession()), 1000);
    return () => clearInterval(t);
  }, []);
  const tone = now.session === "Open" ? "border-positive/40 bg-positive/10 text-positive" : now.session === "Pre-open" ? "border-warning/40 bg-warning/10 text-warning" : "border-line/60 text-muted";
  return (
    <div className="ml-auto flex shrink-0 items-center gap-2 bg-deep pl-3 sm:sticky sm:right-0 sm:shadow-[-12px_0_12px_var(--color-deep)]">
      <span className="font-mono tabular-nums text-secondary">{now.clock}</span>
      <FeedPill />
      <span title="By time and weekday only; holiday calendar not checked"
        className={`flex items-center gap-1.5 rounded-full border px-2 py-px text-[11px] font-medium ${tone}`}>{now.session === "Open" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-positive" />}Market {now.session.toLowerCase()}</span>
    </div>
  );
}

const FEED: Record<string, { text: string; cls: string }> = {
  live: { text: "Live", cls: "border-positive/40 bg-positive/10 text-positive" },
  delayed: { text: "Delayed", cls: "border-warning/40 bg-warning/10 text-warning" },
  closed: { text: "Feed closed", cls: "border-line/60 text-muted" },
  error: { text: "Feed error", cls: "border-negative/40 bg-negative/10 text-negative" },
  lost: { text: "Feed lost", cls: "border-negative/40 bg-negative/10 text-negative" },
};

function FeedPill() {
  const { status, lost } = useFeedStatus();
  const key = lost ? "lost" : status!.state;
  const f = FEED[key] ?? FEED.error;
  const why = lost ? "No feed heartbeat in 30 s" : status!.reason || "Quotes streaming";
  return (
    <span title={`${why}. Last status ${istTime(status?.as_of)}.`}
      className={`flex items-center gap-1.5 rounded-full border px-2 py-px text-[11px] font-medium ${f.cls}`}>
      {key === "live" && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-positive" />}{f.text}
    </span>
  );
}

/** Live tick when the feed has one; otherwise the saved report's value, labelled as such. */
function Item({ name, sym, q, v }: { name: string; sym: string; q?: Quote; v: unknown }) {
  const t = useLiveQuote(sym);
  const title = t ? `${t.source} ${istTime(t.as_of)}${t.stale ? " (stale)" : ""}` : `${q?.source_label ?? "Saved report"} (not live)`;
  return (
    <span className={`flex shrink-0 items-center gap-1.5 ${!t || t.stale ? "opacity-60" : ""}`} title={title}>
      <span className="font-medium text-secondary">{name}</span>
      <Flash v={t?.ltp}><Num v={t ? t.ltp : v} className="text-fg" /></Flash>
      {t ? <Change abs={t.change} pct={t.change_pct} /> : <Change abs={q?.change_abs} pct={q?.change_percent} />}
      {(!t || t.stale) && <span className="rounded-sm border border-line/50 px-1 text-[9.5px] font-medium uppercase tracking-wide text-muted">{t ? "Stale" : "Saved"}</span>}
    </span>
  );
}

const Sep = () => <span className="h-3.5 w-px shrink-0 bg-line/40" />;

export default function TickerTape({ data }: { data: MarketOverviewData | null }) {
  const k = data?.kpis;
  const freshness = data?.freshness;
  const lv = level(freshness?.age_seconds);
  return (
    <div className="flex h-8 shrink-0 items-center gap-4 overflow-x-auto [scrollbar-width:none] whitespace-nowrap border-b border-line/30 bg-deep px-3 text-[12px]">
      <Item name="NIFTY" sym="NIFTY" q={k?.nifty} v={k?.nifty?.price} />
      <Sep />
      <Item name="BANK NIFTY" sym="BANKNIFTY" q={k?.banknifty} v={k?.banknifty?.price} />
      <Sep />
      <Item name="INDIA VIX" sym="INDIAVIX" q={k?.vix} v={k?.vix?.value} />
      <Sep />
      <span className="flex shrink-0 items-center gap-1.5"><span className="text-muted">Regime</span><Chip text={k?.macro?.market_regime} /></span>
      <span className="flex shrink-0 items-center gap-1.5"><span className="text-muted">Flows</span><Chip text={data?.flows?.flow_regime} /></span>
      <Sep />
      <span className="flex shrink-0 items-center gap-1.5" title={freshness?.generated ? `Generated ${freshness.generated}` : "No cache"}>
        <span className={`inline-block h-1.5 w-1.5 rounded-full ${lv.cls}`} />
        <span className="text-muted">Report</span>
        <span className="text-secondary">{freshness?.label ?? "No cache"}</span>
      </span>
      <SessionClock />
    </div>
  );
}
