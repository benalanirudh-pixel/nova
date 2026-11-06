import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Activity, ArrowLeftRight, LayoutGrid, Layers, RefreshCw, Search } from "lucide-react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandShortcut } from "@/components/ui/command";

export interface SymbolItem { symbol: string; name: string }

const OPEN = "nova:search";
/** Open the palette from anywhere (buttons, empty states). */
export const openSearch = () => window.dispatchEvent(new Event(OPEN));

/** Rank: exact symbol, then symbol prefix, then name substring, so Enter picks what was typed. */
export function rankSymbols(symbols: SymbolItem[], query: string, n = 25): SymbolItem[] {
  const q = query.trim().toUpperCase();
  if (!q) return [];
  const rank = (s: SymbolItem) => {
    const sym = s.symbol.toUpperCase();
    return sym === q ? 0 : sym.startsWith(q) ? 1 : s.name.toUpperCase().includes(q) ? 2 : 3;
  };
  return symbols.map((s) => [rank(s), s] as const).filter(([r]) => r < 3).sort((a, b) => a[0] - b[0]).slice(0, n).map(([, s]) => s);
}

const PAGES = [
  { to: "/", label: "Stock analysis", icon: LayoutGrid, key: "F1" },
  { to: "/fno", label: "F&O desk", icon: Layers, key: "F2" },
  { to: "/flows", label: "Institutional flows", icon: ArrowLeftRight, key: "F3" },
  { to: "/screener", label: "Screener", icon: LayoutGrid, key: "F4" },
];
const DESKS = ["NIFTY", "BANKNIFTY", "SENSEX"];

/** Ctrl+K / "/" palette: NSE symbols, pages, F&O desks and actions in one place. */
export default function CommandPalette({ symbols, onRefresh }: { symbols: SymbolItem[]; onRefresh: () => void }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const navigate = useNavigate();
  const matches = useMemo(() => rankSymbols(symbols, q), [symbols, q]);
  const typed = q.trim().toUpperCase();

  useEffect(() => {
    const onOpen = () => setOpen(true);
    window.addEventListener(OPEN, onOpen);
    return () => window.removeEventListener(OPEN, onOpen);
  }, []);

  const run = (fn: () => void) => { setOpen(false); setQ(""); fn(); };
  const stock = (s: string) => run(() => navigate(`/?s=${encodeURIComponent(s)}`));
  const q2 = typed.toLowerCase();
  const pages = PAGES.filter((p) => !q2 || p.label.toLowerCase().includes(q2));
  const desks = DESKS.filter((d) => !typed || d.includes(typed.replace(/\s/g, "")));

  return (
    <CommandDialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setQ(""); }} shouldFilter={false}
      title="Search Nova" description="Search NSE symbols, pages and actions" className="border-line/50 bg-panel sm:max-w-xl">
      <CommandInput value={q} onValueChange={setQ} placeholder="Search a symbol or company, a page, or an action…" />
      <CommandList className="max-h-[60vh]">
        <CommandEmpty>{typed ? `No match for "${q.trim()}". Press Enter to try it as a symbol.` : "Type to search."}</CommandEmpty>
        {matches.length > 0 && (
          <CommandGroup heading="Stocks">
            {matches.map((m) => (
              <CommandItem key={m.symbol} value={`sym-${m.symbol}`} onSelect={() => stock(m.symbol)}>
                <Search className="text-muted" />
                <span className="w-28 shrink-0 font-mono font-medium text-accent">{m.symbol}</span>
                <span className="truncate text-secondary">{m.name}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {typed && matches.length === 0 && /^[A-Z0-9&-]{1,20}$/.test(typed) && (
          <CommandGroup heading="Stocks">
            <CommandItem value={`raw-${typed}`} onSelect={() => stock(typed)}>
              <Search className="text-muted" />Analyze <span className="font-mono text-accent">{typed}</span>
            </CommandItem>
          </CommandGroup>
        )}
        {desks.length > 0 && (
          <CommandGroup heading="F&O desk">
            {desks.map((d) => (
              <CommandItem key={d} value={`desk-${d}`} onSelect={() => run(() => navigate(`/fno?i=${d}`))}>
                <Activity className="text-muted" />{d === "BANKNIFTY" ? "BANK NIFTY" : d === "NIFTY" ? "NIFTY 50" : d} option chain
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {pages.length > 0 && (
          <CommandGroup heading="Pages">
            {pages.map((p) => (
              <CommandItem key={p.to} value={`page-${p.to}`} onSelect={() => run(() => navigate(p.to))}>
                <p.icon className="text-muted" />{p.label}<CommandShortcut>{p.key}</CommandShortcut>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {(!typed || "refresh data".includes(q2)) && (
          <CommandGroup heading="Actions">
            <CommandItem value="act-refresh" onSelect={() => run(onRefresh)}>
              <RefreshCw className="text-muted" />Refresh market data<CommandShortcut>R</CommandShortcut>
            </CommandItem>
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
