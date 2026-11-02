import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import GuardrailsBar from "./components/GuardrailsBar";
import TickerTape from "./components/TickerTape";
import { fetchJSON } from "./lib/api";
import { GUARDRAIL_TEXT } from "./lib/theme";
import type { MarketOverviewData } from "./lib/types";
import { useSSE } from "./hooks/useSSE";
import { SSEContext } from "./hooks/SSEContext";
import { nextRefreshLabel } from "./lib/schedule";
import MarketOverview from "./pages/MarketOverview";
import StockAnalysis from "./pages/StockAnalysis";
import MarketAnalysis from "./pages/MarketAnalysis";

const NAV = [
  { to: "/", label: "Market Overview", end: true },
  { to: "/stock", label: "Stock Analysis" },
  { to: "/analysis", label: "Market Analysis" },
];

export default function App() {
  const [open, setOpen] = useState(true);
  const [guardrail, setGuardrail] = useState(GUARDRAIL_TEXT);
  const [overview, setOverview] = useState<MarketOverviewData | null>(null);
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(nextRefreshLabel());
  const sse = useSSE();
  const { last, reconnects } = sse;

  // one fetch feeds the ticker tape (prices, regimes, data age); keep last good data on error
  const loadOverview = useCallback(() => {
    fetchJSON<MarketOverviewData>("/market-overview").then(setOverview).catch(() => {});
  }, []);

  useEffect(() => {
    fetchJSON<{ guardrail?: string }>("/health")
      .then((d) => d.guardrail && setGuardrail(d.guardrail))
      .catch(() => {});
  }, []);

  // refetch on mount, SSE event, and SSE (re)connect
  useEffect(() => {
    loadOverview();
    setRefreshMsg(null);
  }, [loadOverview, last, reconnects]);

  useEffect(() => {
    const t = setInterval(() => setCountdown(nextRefreshLabel()), 30_000);
    return () => clearInterval(t);
  }, []);

  const refresh = () =>
    fetchJSON<{ status: string }>("/refresh", { method: "POST" })
      .then((d) => setRefreshMsg(d.status === "refreshing" ? "Refreshing…" : "already running"))
      .catch(() => setRefreshMsg("Refresh failed"));

  return (
    <SSEContext.Provider value={sse}>
    <div className="flex h-screen flex-col pb-7 text-[13px]">
      <header className="flex items-center gap-3 border-b border-line bg-panel px-3 py-1.5">
        <button onClick={() => setOpen(!open)} aria-label="Toggle sidebar" aria-expanded={open}
          className="rounded-sm p-0.5 text-secondary hover:text-fg focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">
          <svg viewBox="0 0 16 16" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
            <path d="M2 4h12M2 8h12M2 12h12" />
          </svg>
        </button>
        <span className="text-sm font-bold tracking-[0.2em] text-accent">NOVA</span>
        <span className="text-[10px] uppercase tracking-wider text-muted">NSE analysis terminal</span>
        <span className="ml-auto text-[11px] text-muted">Next refresh in <span className="font-mono tabular-nums text-secondary">{countdown}</span></span>
        {last?.type === "refresh_failed" && <span className="text-[11px] text-negative">Last refresh failed</span>}
        <button onClick={refresh} className="rounded-sm border border-accent/70 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent hover:bg-accent/10 focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">
          {refreshMsg ?? "Refresh"}
        </button>
      </header>
      <TickerTape data={overview} />
      <div className="flex min-h-0 flex-1">
        {open && (
          <nav className="w-44 shrink-0 space-y-px border-r border-line/50 bg-panel p-1.5">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) =>
                  `block rounded-sm border-l-2 px-2 py-1.5 text-xs uppercase tracking-wide focus:outline-none focus-visible:ring-1 focus-visible:ring-accent ${isActive ? "border-accent bg-accent/10 text-accent" : "border-transparent text-secondary hover:bg-line/20 hover:text-fg"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        )}
        <main className="min-w-0 flex-1 overflow-auto p-2">
          <Routes>
            <Route path="/" element={<MarketOverview />} />
            <Route path="/stock" element={<StockAnalysis />} />
            <Route path="/analysis" element={<MarketAnalysis />} />
          </Routes>
        </main>
      </div>
      <GuardrailsBar text={guardrail} />
    </div>
    </SSEContext.Provider>
  );
}
