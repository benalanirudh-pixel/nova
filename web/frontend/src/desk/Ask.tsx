import { useState } from "react";
import { postJSON } from "../lib/api";
import { Block, Flag } from "./ui";

interface Answer { text: string; model: string; report_saved_at: string | null }

/** Ask the Market Lab brain about the saved report, or about one stock. Analysis only. */
export default function Ask({ symbol }: { symbol?: string }) {
  const [q, setQ] = useState("");
  const [a, setA] = useState<Answer | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const run = () => {
    setBusy(true); setErr(null);
    postJSON<Answer>("/interpret", { q, symbol }).then(setA).catch((e: Error) => setErr(e.message)).finally(() => setBusy(false));
  };
  return (
    <Block wide title={symbol ? `Ask Nova about ${symbol}` : "Ask Nova"} sub={a ? `${a.model} · report ${a.report_saved_at?.slice(0, 16) ?? "n/a"}` : "Reads the saved report and live quotes. Not advice."}>
      <div className="pad ask">
        <textarea value={q} onChange={(e) => setQ(e.target.value)} rows={2} maxLength={500}
          placeholder={symbol ? "e.g. quick read, or what contradicts the trend?" : "e.g. where do flows and derivatives disagree?"} />
        <button type="button" className="tbtn" disabled={busy} onClick={run}>{busy ? "Thinking…" : "Ask"}</button>
        {err && <Flag>{err}</Flag>}
        {a && <pre className="ai">{a.text}</pre>}
      </div>
    </Block>
  );
}
