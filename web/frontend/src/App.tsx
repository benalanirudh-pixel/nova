import { useCallback, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import { Search } from "lucide-react";
import { toast } from "sonner";
import CommandPalette, { openSearch, type SymbolItem } from "./components/CommandPalette";
import GuardrailsBar from "./components/GuardrailsBar";
import { Toaster } from "./components/ui/sonner";
import { TooltipProvider } from "./components/ui/tooltip";
import { DeskProvider, useDesk } from "./desk/data";
import "./desk/desk.css";
import Equity from "./desk/Equity";
import Fno from "./desk/Fno";
import { AuditScreen, Flows, Note, Screener, Sectors } from "./desk/Screens";
import { n, pc } from "./desk/ui";
import { SSEContext } from "./hooks/SSEContext";
import { useFeedStatus, useLiveQuote } from "./hooks/useLive";
import { useSSE } from "./hooks/useSSE";
import { fetchJSON } from "./lib/api";
import { isNum } from "./lib/format";
import { istSession, nextRefreshLabel } from "./lib/schedule";
import { GUARDRAIL_TEXT } from "./lib/theme";

const NAV = [
  { to: "/", label: "Equity", end: true }, { to: "/fno", label: "F&O" }, { to: "/flows", label: "Flows" }, { to: "/screener", label: "Screener" },
  { to: "/sectors", label: "Sectors" }, { to: "/note", label: "Note" }, { to: "/audit", label: "Audit" },
];
type TapeItem = [string, unknown, unknown];

function Tape() {
  const { overview, chains, brief } = useDesk();
  const nifty = useLiveQuote("NIFTY"), bank = useLiveQuote("BANKNIFTY"), vix = useLiveQuote("INDIAVIX");
  const k = overview?.kpis, g = brief?.global, sx = chains.SENSEX, sxPrev = sx?.technicals?.prev_close, gift = overview?.live?.gift_nifty;
  const items: TapeItem[] = [
    ["Nifty 50", nifty?.ltp ?? k?.nifty?.price, nifty?.change_pct ?? k?.nifty?.change_percent],
    ["Bank Nifty", bank?.ltp ?? k?.banknifty?.price, bank?.change_pct ?? k?.banknifty?.change_percent],
    ["Sensex", sx?.spot, isNum(sx?.spot) && isNum(sxPrev) ? (sx!.spot! / sxPrev - 1) * 100 : null],
    ["VIX", vix?.ltp ?? k?.vix?.value, vix?.change_pct ?? k?.vix?.change_percent],
    ...(gift ? [["GIFT Nifty", gift.price, gift.change_pct] as TapeItem] : []),
    ...(g?.indices ?? []).slice(0, 3).map((i) => [i.name, i.last, i.change_pct] as TapeItem),
    ...(g?.fx?.[0] ? [["USD/INR", g.fx[0].rate, g.fx[0].change_pct] as TapeItem] : []),
    ...(g?.commodities ?? []).slice(0, 2).map((i) => [i.name, i.price, i.change_pct] as TapeItem),
  ];
  return (
    <div className="tape" aria-label="Market tape">
      {items.map(([t, v, c]) => <div className="t" key={t}><u>{t}</u><b>{n(v)}</b><i className={isNum(c) ? (c > 0 ? "up" : c < 0 ? "dn" : "") : ""}>{pc(c)}</i></div>)}
    </div>
  );
}

function Foot({ text }: { text: string }) {
  const { overview, audit, errors } = useDesk();
  const { status } = useFeedStatus();
  return (
    <GuardrailsBar text={text}>
      <span>Feed {status?.state ?? "unknown"}. Report {audit?.report_saved_at?.slice(11, 16) ?? "n/a"} IST ({overview?.freshness?.label ?? "n/a"})</span>
      {errors[0] && <span className="flag">{errors[0]}</span>}
      <span className="k"><span><i style={{ background: "var(--read)" }} />Nova read</span><span><i className="flag" style={{ padding: 0, width: 14 }} />Unverified</span></span>
    </GuardrailsBar>
  );
}

export default function App() {
  const navigate = useNavigate();
  const sse = useSSE();
  const { last } = sse;
  const [symbols, setSymbols] = useState<SymbolItem[]>([]);
  const [guardrail, setGuardrail] = useState(GUARDRAIL_TEXT);
  const [theme, setTheme] = useState(() => { try { return localStorage.getItem("nova.theme") ?? "dark"; } catch { return "dark"; } });
  const [clock, setClock] = useState(() => istSession());
  const [next, setNext] = useState(nextRefreshLabel());

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try { localStorage.setItem("nova.theme", theme); } catch { /* storage unavailable */ }
  }, [theme]);
  useEffect(() => { fetchJSON<{ guardrail?: string }>("/health").then((d) => d.guardrail && setGuardrail(d.guardrail)).catch(() => {}); }, []);
  useEffect(() => { fetchJSON<SymbolItem[]>("/symbols").then((d) => Array.isArray(d) && setSymbols(d)).catch(() => {}); }, []);
  useEffect(() => {
    const t = setInterval(() => { setClock(istSession()); setNext(nextRefreshLabel()); }, 1000);
    return () => clearInterval(t);
  }, []);
  useEffect(() => {
    if (last?.type === "refresh_complete") toast.success("Market data refreshed", { id: "refresh", description: "Report and scan-based panels are up to date." });
    else if (last?.type === "refresh_failed") toast.error("Refresh failed", { id: "refresh", description: (last as { error?: string }).error ?? "See the server log." });
  }, [last]);

  const refresh = useCallback(() =>
    fetchJSON<{ status: string }>("/refresh", { method: "POST" })
      .then((d) => (d.status === "refreshing"
        ? toast.loading("Refreshing market data", { id: "refresh", description: "Full NSE scan, about 2-3 minutes. Live prices keep updating meanwhile." })
        : toast.info("A refresh is already running", { id: "refresh" })))
      .catch((e: Error) => toast.error("Refresh failed", { id: "refresh", description: e.message })), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target, typing = t instanceof HTMLElement && (t.isContentEditable || /INPUT|TEXTAREA|SELECT/.test(t.tagName));
      const f = e.key.match(/^F([1-7])$/);
      if (f) { e.preventDefault(); navigate(NAV[+f[1] - 1].to); return; }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openSearch(); return; }
      if (typing || e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "/") { e.preventDefault(); openSearch(); }
      else if (e.key.toLowerCase() === "r") refresh();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, refresh]);

  return (
    <SSEContext.Provider value={sse}>
      <TooltipProvider delayDuration={250}>
        <DeskProvider>
          <div className="app">
            <header className="top">
              <NavLink to="/" className="brand">Nova</NavLink>
              <nav className="tabs" aria-label="Pages">{NAV.map((p, i) => <NavLink key={p.to} to={p.to} end={p.end} title={`F${i + 1}`} className="tab">{p.label}</NavLink>)}</nav>
              <button type="button" className="tbtn go-btn" onClick={openSearch} aria-label="Search symbols, pages and actions">
                <span><Search size={13} style={{ display: "inline", marginRight: 6, verticalAlign: -2 }} aria-hidden />Symbol, page or action</span><kbd>Ctrl K</kbd>
              </button>
              <div className="right">
                <span><span className={`dot${clock.session === "Open" ? "" : " off"}`} />NSE {clock.session.toLowerCase()}</span>
                <span className="m">{clock.clock}</span>
                <span className="fa">Next scan {next}</span>
                <button className="tbtn" type="button" title="Run the full NSE scan (R)" onClick={refresh}>Refresh</button>
                <button className="tbtn" type="button" onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? "Day" : "Graphite"}</button>
              </div>
            </header>
            <Tape />
            <main id="view">
              <Routes>
                <Route path="/" element={<Equity />} />
                <Route path="/fno" element={<Fno />} />
                <Route path="/flows" element={<Flows />} />
                <Route path="/screener" element={<Screener />} />
                <Route path="/sectors" element={<Sectors />} />
                <Route path="/note" element={<Note />} />
                <Route path="/audit" element={<AuditScreen />} />
                <Route path="/stock" element={<Navigate to="/" replace />} />
                <Route path="/analysis" element={<Navigate to="/fno" replace />} />
              </Routes>
            </main>
            <Foot text={guardrail} />
            <CommandPalette symbols={symbols} onRefresh={refresh} />
            <Toaster position="bottom-right" offset={40} richColors closeButton />
          </div>
        </DeskProvider>
      </TooltipProvider>
    </SSEContext.Provider>
  );
}
