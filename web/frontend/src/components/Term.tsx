import type { ReactNode } from "react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/** One-line plain-English definitions for every metric the terminal shows. */
export const GLOSSARY: Record<string, string> = {
  pcr: "Put-call ratio: total put open interest divided by call open interest. Above 1.2 = put-heavy (writers defending lower strikes); below 0.7 = call-heavy.",
  pcr_vol: "Put volume divided by call volume traded today.",
  pcr_chg: "Put OI added today divided by call OI added today.",
  max_pain: "The expiry settlement strike at which option buyers, in total, would lose the most.",
  atm: "At-the-money: the strike closest to the current index level.",
  atm_iv: "Implied volatility of the at-the-money options, annualized: what option prices assume about future movement.",
  iv_rv: "ATM implied vol minus the index's 20-day realized vol. Positive = options priced richer than recent movement.",
  rv20: "Realized volatility: annualized standard deviation of the last 20 daily returns.",
  skew: "3% out-of-the-money put IV minus 3% OTM call IV. Positive = traders pay more for downside protection.",
  straddle: "ATM call + put premium. It prices the move the market expects by expiry.",
  move: "ATM straddle as a % of spot: the ± move priced in by expiry.",
  call_wall: "Strike with the most call open interest: option writers' likely ceiling.",
  put_wall: "Strike with the most put open interest: option writers' likely floor.",
  oi: "Open interest: contracts outstanding at this strike.",
  doi: "Change in open interest today. Rising OI = new positions; falling = unwinding.",
  pivot: "Floor-trader pivots from the last completed session's high, low and close.",
  vix: "India VIX: NIFTY's 30-day implied volatility, the market's fear gauge.",
  rsi: "Relative strength index (14 days). Above 70 overbought, below 30 oversold.",
  atr: "Average true range (14 days): the typical daily move in points.",
  ad: "Advance/decline ratio: stocks up divided by stocks down.",
  rs: "Relative strength: the stock's 20-day return minus NIFTY's.",
  rel_vol: "Today's volume divided by the 20-day average volume.",
  pe: "Price to trailing 12-month earnings per share.",
  pb: "Price to book value per share.",
  peg: "P/E divided by the earnings growth rate. Below 1 = cheap relative to growth.",
  ev_ebitda: "Enterprise value divided by EBITDA (operating earnings before depreciation).",
  roe: "Return on equity: net profit as a % of shareholders' equity.",
  de: "Debt divided by shareholders' equity.",
  fii: "Foreign institutional investors' net cash-market buying (₹ crore).",
  dii: "Domestic institutional investors' (mutual funds, insurers) net cash-market buying (₹ crore).",
  gift: "GIFT Nifty: NIFTY futures traded at NSE IX, open almost round the clock; an early read on the next open.",
};

/** A label with a dotted underline that explains itself on hover or focus. */
export default function Term({ k, children }: { k: keyof typeof GLOSSARY | string; children: ReactNode }) {
  const text = GLOSSARY[k];
  if (!text) return <>{children}</>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span tabIndex={0} className="cursor-help underline decoration-line decoration-dotted underline-offset-[3px] focus:outline-none focus-visible:ring-1 focus-visible:ring-accent">{children}</span>
      </TooltipTrigger>
      <TooltipContent side="top" className="max-w-[18rem] text-[12px] leading-snug">{text}</TooltipContent>
    </Tooltip>
  );
}
