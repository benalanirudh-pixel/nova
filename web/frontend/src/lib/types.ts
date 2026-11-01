import type { Maybe } from "./format";

export interface Candle { t: string; o: number; h: number; l: number; c: number; v: number }

export interface Quote {
  name?: string; price?: Maybe<number>; value?: Maybe<number>; change_percent?: Maybe<number>;
  candles?: Candle[];
}

export interface Flows {
  available?: boolean; flow_regime?: string; unit?: string;
  fii_5d?: Maybe<number>; fii_10d?: Maybe<number>; fii_20d?: Maybe<number>;
  dii_5d?: Maybe<number>; dii_10d?: Maybe<number>; dii_20d?: Maybe<number>;
  signal_allowed?: boolean; signal_reason?: string; latest_date?: string;
}

export interface Sector { name: string; return_20d: Maybe<number>; relative_strength_20d?: Maybe<number>; regime?: string }

export interface Derivatives {
  available?: boolean; oi_pcr?: Maybe<number>; volume_pcr?: Maybe<number>; max_pain?: Maybe<number>;
  atm_iv?: Maybe<number>; unusual_count?: Maybe<number>; expiry?: string;
}

export interface Breadth {
  advancing?: Maybe<number>; declining?: Maybe<number>; unchanged?: Maybe<number>; ad_ratio?: Maybe<number>;
}

export interface Freshness {
  generated?: string; age_seconds?: number | null; label?: string; saved_at?: string; file_age_seconds?: number | null;
}

/** Every top-level key is null when there is no cache. */
export interface MarketOverviewData {
  kpis: null | {
    macro?: { market_regime?: Maybe<string> };
    nifty?: Quote; banknifty?: Quote; vix?: Quote;
  };
  chart: null | { candles?: Candle[] };
  breadth: Breadth | null;
  flows: Flows | null;
  sectors: Sector[] | null;
  derivatives: Derivatives | null;
  freshness: Freshness | null;
  guardrails?: { text?: string } | null;
}
