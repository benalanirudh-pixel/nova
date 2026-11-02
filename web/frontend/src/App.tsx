import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes, useNavigate } from "react-router-dom";
import GuardrailsBar from "./components/GuardrailsBar";
import SymbolSearch, { SEARCH_ID, type SymbolItem } from "./components/SymbolSearch";
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
  { to: "/", label: "Overview", end: true },
  { to: "/stock", label: "Stock" },
  { to: "/analysis", label: "F&O desk" },
];

export default function App() {
  const navigate = useNavigate();
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
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
    fetchJSON<SymbolItem[]>("/symbols").then((d) => Array.isArray(d) && setSymbols(d)).catch(() => {});
  }, []);

  // keyboard: "/" or Ctrl+K search, 1-3 pages, R refresh; ignored while typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      const typing = t instanceof HTMLElement && (t.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(t.tagName));
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); document.getElementById(SEARCH_ID)?.focus(); return; }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); document.getElementById(SEARCH_ID)?.focus(); }
      else if (/^[1-3]$/.test(e.key)) navigate(NAV[Number(e.key) - 1].to);
      else if (e.key.toLowerCase() === "r") refresh();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

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
      <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line/40 bg-panel px-3 py-1.5 lg:h-12 lg:flex-nowrap lg:py-0">
        <div className="flex shrink-0 items-center gap-2">
          <svg viewBox="0 0 16 16" className="h-4 w-4 text-accent" aria-hidden>
            <path d="M8 0l1.6 6.4L16 8l-6.4 1.6L8 16l-1.6-6.4L0 8l6.4-1.6z" fill="currentColor" />
          </svg>
          <span className="text-[15px] font-semibold tracking-tight">Nova</span>
          <span className="hidden text-[11px] text-muted xl:inline">NSE analysis terminal</span>
        </div>
        <nav className="flex items-stretch self-stretch" aria-label="Pages">
          {NAV.map((n, i) => (
            <NavLink key={n.to} to={n.to} end={n.end} title={`${n.label} (${i + 1})`}
              className={({ isActive }) =>
                `flex items-center whitespace-nowrap border-b-2 px-2 py-1.5 text-[13px] sm:px-3 font-medium focus:outline-none focus-visible:bg-raised ${isActive ? "border-accent text-fg" : "border-transparent text-secondary hover:text-fg"}`}>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="order-last min-w-0 basis-full lg:order-none lg:max-w-sm lg:flex-1 lg:basis-auto">
          <SymbolSearch symbols={symbols} onSelect={(sym) => navigate(`/stock?s=${encodeURIComponent(sym)}`)} />
        </div>
        <div className="ml-auto flex shrink-0 items-center gap-3">
          {last?.type === "refresh_failed" && <span className="text-[11px] text-negative">Last refresh failed</span>}
          <span className="hidden text-[11px] text-muted md:inline">Next refresh <span className="font-mono tabular-nums text-secondary">{countdown}</span></span>
          <button onClick={refresh} title="Refresh market data (R)"
            className="rounded border border-accent/60 px-2.5 py-1 text-[12px] font-medium text-accent hover:bg-accent/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/60">
            {refreshMsg ?? "Refresh data"}
          </button>
        </div>
      </header>
      <TickerTape data={overview} />
      <main className="min-h-0 min-w-0 flex-1 overflow-auto p-2">
        <Routes>
          <Route path="/" element={<MarketOverview />} />
          <Route path="/stock" element={<StockAnalysis />} />
          <Route path="/analysis" element={<MarketAnalysis />} />
        </Routes>
      </main>
      <GuardrailsBar text={guardrail} />
    </div>
    </SSEContext.Provider>
  );
}
