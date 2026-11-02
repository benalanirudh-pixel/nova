import { fmt, isNum } from "../lib/format";
import type { Breadth } from "../lib/types";
import { Num, Panel, PctBar, Stat } from "./ui";

/** A/D bar, % above EMAs, strong trend split; `detail` adds 52W highs/lows and McClellan. */
export default function BreadthBars({ breadth: b, detail }: { breadth: Breadth | null; detail?: boolean }) {
  const { advancing: a, declining: d, unchanged: u } = b ?? {};
  const ok = isNum(a) && isNum(d) && isNum(u) && a + d + u > 0;
  const total = ok ? a + d + u : 1;
  const seg = (n: number, cls: string, t: string) => <div className={cls} style={{ width: `${(n / total) * 100}%` }} title={t} />;
  return (
    <Panel title="Market breadth" right={<span>A/D <Num v={b?.ad_ratio} className="text-secondary" /></span>}>
      {!b ? <div className="text-xs text-muted">N/A</div> : (
        <div className="space-y-2">
          {ok ? (
            <div>
              <div className="flex h-2 overflow-hidden rounded-sm">
                {seg(a, "bg-positive", `Advancing ${a}`)}{seg(u, "bg-muted", `Unchanged ${u}`)}{seg(d, "bg-negative", `Declining ${d}`)}
              </div>
              <div className="mt-1 flex justify-between font-mono text-[11px] tabular-nums">
                <span className="text-positive">▲ {fmt(a, 0)}</span>
                <span className="text-muted">UNCH {fmt(u, 0)}</span>
                <span className="text-negative">▼ {fmt(d, 0)}</span>
              </div>
            </div>
          ) : <div className="text-xs text-muted">Advance/decline N/A</div>}
          <div className="space-y-1">
            <PctBar k="Above EMA 20" v={b.above_ema20_percent} />
            <PctBar k="Above EMA 50" v={b.above_ema50_percent} />
            <PctBar k="Above EMA 200" v={b.above_ema200_percent} />
            <PctBar k="Strong uptrend" v={b.strong_uptrend_percent} bar="bg-positive" />
            <PctBar k="Strong downtrend" v={b.strong_downtrend_percent} bar="bg-negative" />
          </div>
          {detail && (
            <div className="grid grid-cols-3 gap-1">
              <Stat k="52W highs"><Num v={b.new_52w_highs} d={0} /></Stat>
              <Stat k="52W lows"><Num v={b.new_52w_lows} d={0} /></Stat>
              <Stat k="McClellan sum"><Num v={b.mcclellan_summation} /></Stat>
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}
