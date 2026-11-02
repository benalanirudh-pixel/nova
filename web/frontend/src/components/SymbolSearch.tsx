import { useEffect, useMemo, useState } from "react";

export interface SymbolItem { symbol: string; name: string }

export const SEARCH_ID = "symbol-search";

export default function SymbolSearch({ onSelect, symbols }: { onSelect: (s: string) => void; symbols: SymbolItem[] }) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => { setQ(text.trim().toUpperCase()); setIdx(0); }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const rankMatches = (q: string) => {
    if (!q) return [];
    // rank: exact symbol, then symbol prefix, then name substring — so Enter picks what was typed
    const rank = (s: { symbol: string; name: string }) => {
      const sym = s.symbol.toUpperCase();
      return sym === q ? 0 : sym.startsWith(q) ? 1 : s.name.toUpperCase().includes(q) ? 2 : 3;
    };
    return symbols.map((s) => [rank(s), s] as const).filter(([r]) => r < 3)
      .sort((a, b) => a[0] - b[0]).slice(0, 10).map(([, s]) => s);
  };
  const matches = useMemo(() => rankMatches(q), [q, symbols]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (s: string) => { setText(""); setQ(""); setOpen(false); onSelect(s); };

  return (
    <div className="relative w-full">
      <input
        value={text}
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.max(0, Math.min(i + 1, matches.length - 1))); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Escape") setOpen(false);
          else if (e.key === "Enter") {
            // act on the live text, not the debounced q; keep arrow selection only once q has caught up
            const live = text.trim().toUpperCase();
            const m = (live === q ? matches[idx] : rankMatches(live)[0]);
            if (m) pick(m.symbol); else if (live) pick(live);
          }
        }}
        id={SEARCH_ID}
        placeholder="Search NSE symbol or company"
        aria-label="Search symbol"
        className="peer w-full rounded border border-line/40 bg-deep py-1.5 pl-8 pr-14 text-[13px] text-fg outline-none placeholder:text-muted focus:border-accent/70"
      />
      <svg viewBox="0 0 16 16" className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
        <circle cx="7" cy="7" r="4.5" /><path d="M10.5 10.5L14 14" />
      </svg>
      <kbd className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 rounded border border-line/50 px-1 font-mono text-[10px] text-muted peer-focus:hidden">Ctrl K</kbd>
      {open && matches.length > 0 && (
        <ul className="absolute z-30 mt-1 max-h-80 w-full min-w-[20rem] overflow-auto rounded-md border border-line/50 bg-raised py-1 shadow-xl shadow-black/40" role="listbox">
          {matches.map((m, i) => (
            <li
              key={m.symbol}
              role="option"
              aria-selected={i === idx}
              onMouseDown={(e) => { e.preventDefault(); pick(m.symbol); }}
              onMouseEnter={() => setIdx(i)}
              className={`flex cursor-pointer items-baseline justify-between gap-3 px-3 py-1.5 text-[13px] ${i === idx ? "bg-accent/10" : ""}`}
            >
              <span className="font-mono font-medium text-accent">{m.symbol}</span>
              <span className="truncate text-secondary">{m.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
