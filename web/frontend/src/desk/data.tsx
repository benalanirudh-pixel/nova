import { createContext, useContext, useEffect, useMemo, type ReactNode } from "react";
import { useMarketData } from "../hooks/useMarketData";
import { istSession } from "../lib/schedule";
import type { Candle, FnoDesk, MarketAnalysisData, MarketOverviewData, MorningBrief } from "../lib/types";
import { analyzeChain, risk, withQuote, type Bar, type Fno } from "./analytics";
import { dayMonth, n } from "./ui";

export interface ScanRow {
  s: string; n: string; x: string; p: number; r1: number | null; r5: number | null; r20: number | null; r60: number | null; rs20: number | null;
  e20: number | null; e50: number | null; e200: number | null; rsi: number | null; atr: number | null; val: number; rv: number | null;
  h52: number | null; l52: number | null; dh: number | null; t: string; sc: number | null;
}
export interface SectorRow { n: string; c: number; r1: number | null; r5: number | null; r20: number | null; r60: number | null; a200: number; rsi: number | null; val: number; best: string; worst: string }
interface ScanPayload { available: boolean; as_of?: string; stock_count?: number; newest_stocks: number; sector_map_as_of?: string | null; columns: (keyof ScanRow)[]; rows: unknown[][]; sectors: SectorRow[] }
export interface Audit {
  report_saved_at: string | null; stocks_analyzed: number | null; data_availability: Record<string, string>; decision_policy: Record<string, boolean>;
  sector_file_as_of: string | null; scanner_file_as_of: string | null; factor_rows: number; factor_rows_empty: number;
}
export interface FlowMetrics {
  latest_date?: string; fii_5d: number; dii_5d: number; combined_5d: number; fii_10d: number; dii_10d: number; combined_10d: number; fii_20d: number; dii_20d: number; combined_20d: number;
  fii_avg_5d: number; dii_avg_5d: number; fii_avg_10d: number; dii_avg_10d: number; fii_avg_20d: number; dii_avg_20d: number; fii_streak_direction: string; fii_streak_days: number;
  dii_streak_direction: string; dii_streak_days: number; primary_source_sessions_in_target_window: number; target_sessions: number;
}
export interface FlowRow { date: string; fii_buy: number; fii_sell: number; fii_net: number; dii_buy: number; dii_sell: number; dii_net: number; combined_net: number; market_scope: string; source: string }
interface FlowHistory { rows: FlowRow[]; target_scope: string; summary: { signal_allowed?: boolean } | null; metrics: FlowMetrics | null }

export const INDICES = ["NIFTY", "BANKNIFTY", "SENSEX", "VIX"] as const;
export const INDEX_NAMES: Record<string, string> = { NIFTY: "Nifty 50", BANKNIFTY: "Bank Nifty", SENSEX: "Sensex", VIX: "India VIX" };
const FNO_POLL_MS = 60_000;

const toBars = (c?: { t: string; o: number; h: number; l: number; c: number; v?: number }[] | Candle[]): Bar[] =>
  (c ?? []).map((b) => [b.t, b.o, b.h, b.l, b.c, b.v ?? 0]);

function isoDate(tradeDate: string | undefined) {
  const m = tradeDate?.match(/^(\d{2})-([A-Za-z]{3})-(\d{4})/);
  if (!m) return null;
  const mon = "JanFebMarAprMayJunJulAugSepOctNovDec".indexOf(m[2]) / 3 + 1;
  return `${m[3]}-${String(mon).padStart(2, "0")}-${m[1]}`;
}

function useDeskValue() {
  const overview = useMarketData<MarketOverviewData>("/market-overview");
  const analysis = useMarketData<MarketAnalysisData>("/market-analysis");
  const brief = useMarketData<MorningBrief>("/morning-brief");
  const scan = useMarketData<ScanPayload>("/scan");
  const audit = useMarketData<Audit>("/audit");
  const flows = useMarketData<FlowHistory>("/flows/history");
  const nifty = useMarketData<FnoDesk>("/fno/NIFTY");
  const bank = useMarketData<FnoDesk>("/fno/BANKNIFTY");
  const sensex = useMarketData<FnoDesk>("/fno/SENSEX");

  useEffect(() => {
    const t = setInterval(() => {
      if (istSession().session !== "Open") return;
      overview.refresh(); nifty.refresh(); bank.refresh(); sensex.refresh();
    }, FNO_POLL_MS);
    return () => clearInterval(t);
  }, [overview.refresh, nifty.refresh, bank.refresh, sensex.refresh]);

  const stocks = useMemo(() => (scan.data?.rows ?? []).map((a) => Object.fromEntries(scan.data!.columns.map((k, i) => [k, a[i]])) as unknown as ScanRow), [scan.data]);
  const bySymbol = useMemo(() => Object.fromEntries(stocks.map((r) => [r.s, r])), [stocks]);
  const chains: Record<string, FnoDesk | null> = { NIFTY: nifty.data, BANKNIFTY: bank.data, SENSEX: sensex.data };
  const models: Record<string, Fno | null> = useMemo(() => ({ NIFTY: analyzeChain(nifty.data), BANKNIFTY: analyzeChain(bank.data), SENSEX: analyzeChain(sensex.data) }), [nifty.data, bank.data, sensex.data]);
  const k = overview.data?.kpis;
  const tradeDate = isoDate(overview.data?.live?.status?.trade_date);

  const indexBars = (sym: string): Bar[] => {
    if (sym === "SENSEX") {
      const t = sensex.data?.technicals;
      return withQuote(toBars(t?.candles), tradeDate, { px: sensex.data?.spot, h: t?.day_high, l: t?.day_low });
    }
    const q = sym === "NIFTY" ? k?.nifty : sym === "BANKNIFTY" ? k?.banknifty : k?.vix;
    return withQuote(toBars(q?.candles), tradeDate, { px: (q?.price ?? q?.value) as number | null, o: q?.open as number | null, h: q?.high as number | null, l: q?.low as number | null });
  };
  const niftyBars = indexBars("NIFTY");
  const niftyRisk = risk(niftyBars, (k?.nifty?.price as number | null) ?? null, null);

  const flags = useMemo(() => {
    const out: [string, string][] = [];
    const rep = analysis.data?.derivatives?.nifty?.oi_pcr, live = nifty.data?.metrics?.pcr_oi;
    if (typeof rep === "number" && typeof live === "number" && Math.abs(rep - live) >= 0.05) out.push(["PCR disagrees", `Nifty OI PCR ${n(live)} on the chain, ${n(rep)} in the saved report.`]);
    const a = audit.data;
    if (a?.stocks_analyzed != null && a.stocks_analyzed < 1500) out.push(["Breadth partial", `The saved report covers ${a.stocks_analyzed} stocks. Screener uses the last complete scan, ${dayMonth(scan.data?.as_of)}.`]);
    const m = flows.data?.metrics;
    if (m && m.primary_source_sessions_in_target_window < m.target_sessions) out.push(["Flows part verified", `${m.primary_source_sessions_in_target_window} of ${m.target_sessions} sessions are NSE-primary.`]);
    if (a?.sector_file_as_of && a.sector_file_as_of !== a.scanner_file_as_of) out.push(["Sector scan stale", `Report reads the ${dayMonth(a.sector_file_as_of)} sector file. Sector tables here are recomputed from the stock scan.`]);
    const ev = analysis.data?.events;
    if (ev && ev.status !== "AVAILABLE") out.push(["Event risk unavailable", `Calendar last checked ${dayMonth(ev.source_checked_at_utc)}.`]);
    if (a?.factor_rows && a.factor_rows_empty === a.factor_rows) out.push(["Factor detail empty", `All ${a.factor_rows} ranked rows have null factor scores in the report.`]);
    return out;
  }, [analysis.data, nifty.data, audit.data, flows.data, scan.data?.as_of]);

  const errors = [overview, analysis, brief, scan, audit, flows].map((x) => x.error).filter(Boolean) as string[];
  return { overview: overview.data, analysis: analysis.data, brief: brief.data, scan: scan.data, audit: audit.data, flows: flows.data, stocks, bySymbol, chains, models, indexBars, niftyBars, niftyRisk, tradeDate, flags, errors, loading: overview.loading };
}

export type Desk = ReturnType<typeof useDeskValue>;
const Ctx = createContext<Desk | null>(null);

export function DeskProvider({ children }: { children: ReactNode }) {
  const value = useDeskValue();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useDesk() {
  const d = useContext(Ctx);
  if (!d) throw new Error("useDesk needs DeskProvider");
  return d;
}

export function headline(ret5: number | null | undefined, above200: number | null | undefined) {
  if (typeof ret5 !== "number" || typeof above200 !== "number") return "Waiting for market data.";
  if (ret5 >= 1 && above200 < 40) return "The index is rallying without the broad market.";
  if (ret5 >= 1) return "A broad advance.";
  if (ret5 <= -1) return "Selling pressure across the tape.";
  return "Range-bound session.";
}
