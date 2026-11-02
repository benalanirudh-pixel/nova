import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import GuardrailsBar from "./components/GuardrailsBar";
import { fetchJSON } from "./lib/api";
import { GUARDRAIL_TEXT } from "./lib/theme";
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
  const [freshness, setFreshness] = useState<string>("No cache");
  const [refreshMsg, setRefreshMsg] = useState<string | null>(null);
  const [countdown, setCountdown] = useState(nextRefreshLabel());
  const sse = useSSE();
  const { last, reconnects } = sse;

  const loadFreshness = useCallback(() => {
    fetchJSON<{ freshness?: { label?: string } | null }>("/market-overview")
      .then((d) => setFreshness(d.freshness?.label || "No cache"))
      .catch(() => setFreshness("No cache"));
  }, []);

  useEffect(() => {
    fetchJSON<{ guardrail?: string }>("/health")
      .then((d) => d.guardrail && setGuardrail(d.guardrail))
      .catch(() => {});
  }, []);

  // refetch on mount, SSE event, and SSE (re)connect
  useEffect(() => {
    loadFreshness();
    setRefreshMsg(null);
  }, [loadFreshness, last, reconnects]);

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
    <div className="flex h-screen flex-col pb-8">
      <header className="flex items-center gap-4 border-b border-line bg-panel px-4 py-2">
        <button onClick={() => setOpen(!open)} className="text-secondary" aria-label="Toggle sidebar">☰</button>
        <span className="text-lg font-semibold text-accent">Nova</span>
        <span className="rounded border border-line px-2 py-0.5 text-xs text-secondary">Data: {freshness}</span>
        <span className="ml-auto text-xs text-muted">Next refresh in {countdown}</span>
        <button onClick={refresh} className="rounded border border-accent px-3 py-1 text-xs text-accent hover:bg-accent/10">
          {refreshMsg ?? "Refresh"}
        </button>
        {last?.type === "refresh_failed" && <span className="text-xs text-negative">Last refresh failed</span>}
      </header>
      <div className="flex min-h-0 flex-1">
        {open && (
          <nav className="w-48 shrink-0 space-y-1 border-r border-line bg-panel p-2">
            {NAV.map((n) => (
              <NavLink key={n.to} to={n.to} end={n.end}
                className={({ isActive }) =>
                  `block rounded px-3 py-2 text-sm ${isActive ? "bg-accent/15 text-accent" : "text-secondary hover:text-fg"}`}>
                {n.label}
              </NavLink>
            ))}
          </nav>
        )}
        <main className="flex-1 overflow-auto p-4">
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
