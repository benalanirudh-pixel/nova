import { useNavigate, useSearchParams } from "react-router-dom";
import { useMarketData } from "../hooks/useMarketData";
import { dayMonth, Empty, Flag, n, Pane, Pct, sg, Table, type Col } from "./ui";

interface Link {
  symbol: string; relation: "supplier" | "customer"; product: string; confidence: "filed" | "stated" | "inferred"; note?: string;
  evidence?: { title: string; url: string; date: string }; name: string; sector?: string | null;
  p: number | null; r1: number | null; r20: number | null; rs20: number | null; in_scan: boolean;
}
interface Chain {
  symbol: string; covered: boolean; checked_at?: string; covered_symbols: string[]; scan_as_of?: string;
  company?: { n: string; x: string; p: number; r1: number | null; r20: number | null; rs20: number | null } | null; links?: Link[];
}

const avg = (a: (number | null)[]) => { const v = a.filter((x): x is number => x != null); return v.length ? v.reduce((p, c) => p + c, 0) / v.length : null; };

function Side({ title, rows, go }: { title: string; rows: Link[]; go: (s: string) => void }) {
  const cited = rows.filter((r) => r.confidence !== "inferred"), inferred = rows.filter((r) => r.confidence === "inferred");
  const cols = (withEvidence: boolean): Col<Link>[] => [
    { h: "Symbol", v: (r) => r.symbol, text: true, bold: true }, { h: "Company", v: (r) => r.name.slice(0, 32), text: true }, { h: "Product", v: (r) => r.product, text: true },
    { h: "Last", v: (r) => (r.in_scan ? n(r.p) : <Flag>Not in scan</Flag>) }, { h: "1D", v: (r) => <Pct v={r.r1} /> }, { h: "20D", v: (r) => <Pct v={r.r20} d={1} /> }, { h: "RS 20D", v: (r) => sg(r.rs20, 1) },
    withEvidence
      ? { h: "Evidence", v: (r) => <a href={r.evidence!.url} target="_blank" rel="noreferrer" title={r.note}>{r.confidence === "filed" ? "Filing" : "Document"}, {dayMonth(r.evidence!.date)} {r.evidence!.date.slice(0, 4)}</a>, text: true }
      : { h: "Why", v: (r) => r.note ?? "", text: true },
  ];
  return (
    <section className="pane" aria-label={title}>
      <div className="ph"><h2>{title}</h2><span className="s">{cited.length} cited, {inferred.length} inferred. 20D average {sg(avg(cited.map((r) => r.r20)), 1)}%</span></div>
      <div className="body">
        {cited.length ? <Table cols={cols(true)} rows={cited} onRow={(r) => go(r.symbol)} /> : <Empty>No cited {title.toLowerCase()} yet.</Empty>}
        {inferred.length > 0 && (
          <>
            <div className="bh pd"><h3>Inferred from industry structure</h3><Flag>Not from a document</Flag></div>
            <Table cols={cols(false)} rows={inferred} onRow={(r) => go(r.symbol)} />
          </>
        )}
      </div>
    </section>
  );
}

export default function ChainPage() {
  const [params, setParams] = useSearchParams();
  const nav = useNavigate();
  const sym = (params.get("s") ?? "RELIANCE").toUpperCase();
  const { data, error } = useMarketData<Chain>(`/supply-chain/${encodeURIComponent(sym)}`);
  if (error) return <div className="pane full"><Empty>Supply chain unavailable. {error}</Empty></div>;
  if (!data) return <div className="pane full"><Empty>Loading supply chain for {sym}.</Empty></div>;
  const pick = (s: string) => setParams({ s });
  if (!data.covered) return (
    <div className="pane full"><Empty>
      {sym} is not covered yet. Links are added only after the company's filings are checked. Covered now:{" "}
      {data.covered_symbols.map((s) => <button key={s} type="button" className="chip" onClick={() => pick(s)}>{s}</button>)}
    </Empty></div>
  );
  const links = data.links ?? [], c = data.company;
  return (
    <div className="grid-chain">
      <section className="pane" style={{ gridArea: "hd" }}>
        <div className="qh">
          <div><h1>{c?.n ?? sym} supply chain</h1><div className="sub">{sym}, {c?.x ?? "sector unmapped"}. Links checked {dayMonth(data.checked_at)}, prices from the {dayMonth(data.scan_as_of)} scan</div></div>
          <div className="px">{n(c?.p)}</div>
          <div className="q">{[["1D", <Pct v={c?.r1} />], ["20D", <Pct v={c?.r20} d={1} />], ["RS 20D", sg(c?.rs20, 1)]].map(([k, v]) => <div key={String(k)}><u>{k}</u><b>{v}</b></div>)}</div>
          <button type="button" className="tbtn" onClick={() => nav(`/?s=${encodeURIComponent(sym)}`)}>Open stock sheet</button>
        </div>
      </section>
      <div style={{ gridArea: "up" }} className="chain-col"><Side title="Suppliers" rows={links.filter((l) => l.relation === "supplier")} go={(s) => nav(`/?s=${encodeURIComponent(s)}`)} /></div>
      <div style={{ gridArea: "down" }} className="chain-col"><Side title="Customers" rows={links.filter((l) => l.relation === "customer")} go={(s) => nav(`/?s=${encodeURIComponent(s)}`)} /></div>
      <Pane area="ft" title="How links are sourced" sub="Analysis only, not a recommendation">
        <div className="pad note-t">Filing means a stock-exchange or company related-party disclosure. Document means a company or broker document names the relationship. Inferred rows come from industry structure and no document was checked, so treat them as questions, not facts. Click a row to open its stock sheet.</div>
      </Pane>
    </div>
  );
}
