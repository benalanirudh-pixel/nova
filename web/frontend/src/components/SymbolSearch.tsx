import { useEffect, useMemo, useState } from "react";

export interface SymbolItem { symbol: string; name: string }

export default function SymbolSearch({ onSelect, symbols }: { onSelect: (s: string) => void; symbols: SymbolItem[] }) {
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [idx, setIdx] = useState(0);

  useEffect(() => {
    const t = setTimeout(() => { setQ(text.trim().toUpperCase()); setIdx(0); }, 300);
    return () => clearTimeout(t);
  }, [text]);

  const matches = useMemo(() => {
    if (!q) return [];
    // rank: exact symbol, then symbol prefix, then name substring — so Enter picks what was typed
    const rank = (s: { symbol: string; name: string }) => {
      const sym = s.symbol.toUpperCase();
      return sym === q ? 0 : sym.startsWith(q) ? 1 : s.name.toUpperCase().includes(q) ? 2 : 3;
    };
    return symbols.map((s) => [rank(s), s] as const).filter(([r]) => r < 3)
      .sort((a, b) => a[0] - b[0]).slice(0, 10).map(([, s]) => s);
  }, [q, symbols]);

  const pick = (s: string) => { setText(""); setQ(""); setOpen(false); onSelect(s); };

  return (
    <div className="relative w-full max-w-md">
      <input
        value={text}
        onChange={(e) => { setText(e.target.value); setOpen(true); }}
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, matches.length - 1)); }
          else if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
          else if (e.key === "Escape") setOpen(false);
          else if (e.key === "Enter") {
            // before the debounce fires, fall back to the typed text itself
            const m = matches[idx];
            if (m) pick(m.symbol); else if (text.trim()) pick(text.trim().toUpperCase());
          }
        }}
        placeholder="Search symbol or company (e.g. RELIANCE)"
        aria-label="Search symbol"
        className="w-full rounded border border-line/50 bg-panel px-3 py-2 text-sm text-fg outline-none focus:border-accent"
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-10 mt-1 max-h-72 w-full overflow-auto rounded border border-line/50 bg-panel shadow-lg" role="listbox">
          {matches.map((m, i) => (
            <li
              key={m.symbol}
              role="option"
              aria-selected={i === idx}
              onMouseDown={(e) => { e.preventDefault(); pick(m.symbol); }}
              onMouseEnter={() => setIdx(i)}
              className={`flex cursor-pointer justify-between gap-3 px-3 py-1.5 text-sm ${i === idx ? "bg-line/30" : ""}`}
            >
              <span className="font-semibold text-accent">{m.symbol}</span>
              <span className="truncate text-secondary">{m.name}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
