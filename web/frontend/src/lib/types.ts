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

export interface Regime {
  market_regime?: string; india_vix?: Maybe<number>; vix_regime?: string;
  vix_percentile_1y?: Maybe<number>; vix_direction?: string;
}
export interface BreadthFull extends Breadth {
  above_ema20_percent?: Maybe<number>; above_ema50_percent?: Maybe<number>; above_ema200_percent?: Maybe<number>;
  strong_uptrend_percent?: Maybe<number>; strong_downtrend_percent?: Maybe<number>;
  new_52w_highs?: Maybe<number>; new_52w_lows?: Maybe<number>; mcclellan_summation?: Maybe<number>;
}
export type Streak = [string, number];
export interface FlowsFull extends Flows { fii_streak?: Streak; dii_streak?: Streak }
export interface Wall { strike?: Maybe<number>; oi?: Maybe<number>; change_oi?: Maybe<number> }
export interface Unusual {
  option_type?: string; strike?: Maybe<number>; oi?: Maybe<number>; change_oi?: Maybe<number>;
  volume?: Maybe<number>; volume_oi_ratio?: Maybe<number>; oi_activity?: string; premium_state?: string;
}
export interface DerivativesFull extends Derivatives {
  instrument?: string; spot?: Maybe<number>; put_wall?: Wall; call_wall?: Wall; unusual_activity?: Unusual[];
}
export interface RiskEvent {
  name?: string; datetime_utc?: string; category?: string; severity?: string; risk_level?: string; impact_note?: string;
}
export interface Events {
  status?: string; source_fresh?: boolean; overall_risk?: string; source_checked_at_utc?: string;
  upcoming_event_count?: number; upcoming_events?: RiskEvent[];
}
export interface MarketAnalysisData {
  regime: Regime | null; breadth: BreadthFull | null; sectors: Sector[] | null; flows: FlowsFull | null;
  derivatives: { nifty?: DerivativesFull; bank_nifty?: DerivativesFull } | null;
  events: Events | null; freshness: Freshness | null; guardrails?: { text?: string } | null;
}
