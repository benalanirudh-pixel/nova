import { isNum } from "../lib/format";
import type { Indicators } from "../lib/types";
import { Chip, Num, Panel } from "./ui";

/** One compact card per API indicator (RSI / MACD / ATR / VOL); extra numeric fields shown as sub-values. */
export default function IndicatorStrip({ ind, title = "NIFTY indicators" }: { ind?: Indicators | null; title?: string }) {
  const entries = Object.entries(ind ?? {});
  if (entries.length === 0) return null;
  return (
    <div className="grid grid-cols-2 gap-2 lg:grid-cols-4" aria-label={title}>
      {entries.map(([name, i]) => {
        const extras = Object.entries(i).filter(([k, v]) => k !== "value" && isNum(v));
        const unit = i.unit === "%" ? "%" : "";
        return (
          <Panel key={name} title={name} right={<Chip text={i.interpretation} />}>
            <div className="flex items-baseline gap-1">
              <Num v={i.value} d={2} suffix={isNum(i.value) ? unit : ""} className="text-lg font-semibold" />
              {i.unit && i.unit !== "%" && <span className="text-[10px] text-muted">{i.unit}</span>}
            </div>
            {extras.length > 0 && (
              <div className="mt-0.5 flex flex-wrap gap-x-3 text-[11px]">
                {extras.map(([k, v]) => (
                  <span key={k}><span className="text-muted">{k} </span>
                    <Num v={v} suffix={k === "percent" ? "%" : ""} signed={k === "histogram"} className="text-secondary" /></span>
                ))}
              </div>
            )}
          </Panel>
        );
      })}
    </div>
  );
}
