import type { Maybe } from "./format";

export interface Candle { t: string; o: number; h: number; l: number; c: number; v: number }

type N = Maybe<number>;

export interface Quote {
  name?: string; price?: N; value?: N; change_percent?: N; change_abs?: N; prev_close?: N;
  open?: N; high?: N; low?: N; close?: N; return_5d?: N; return_20d?: N; return_60d?: N;
  series?: { date?: string; close?: N }[]; source_label?: string; regime?: string; direction?: string;
  candles?: Candle[];
}

export interface Indicator { value?: N; unit?: string; interpretation?: string; [k: string]: unknown }
export type Indicators = Record<string, Indicator>;

export type Streak = [string, number];
export interface Flows {
  available?: boolean; flow_regime?: string; unit?: string;
  fii_5d?: N; fii_10d?: N; fii_20d?: N; dii_5d?: N; dii_10d?: N; dii_20d?: N;
  fii_streak?: Streak; dii_streak?: Streak; source_quality?: string;
  signal_allowed?: boolean; signal_reason?: string; latest_date?: string;
}

export interface Sector { name: string; return_20d: N; relative_strength_20d?: N; regime?: string }

export interface Wall { strike?: N; oi?: N; change_oi?: N }
export interface Unusual {
  option_type?: string; strike?: N; oi?: N; change_oi?: N;
  volume?: N; volume_oi_ratio?: N; oi_activity?: string; premium_state?: string;
}
export interface Derivatives {
  available?: boolean; instrument?: string; spot?: N; expiry?: string;
  oi_pcr?: N; volume_pcr?: N; max_pain?: N; atm_iv?: N; unusual_count?: N;
  put_wall?: Wall; call_wall?: Wall; unusual_activity?: Unusual[];
  interpretation?: { classification?: string; max_pain_distance_percent?: N; warning?: string };
}

export interface Breadth {
  advancing?: N; declining?: N; unchanged?: N; ad_ratio?: N;
  above_ema20_percent?: N; above_ema50_percent?: N; above_ema200_percent?: N;
  strong_uptrend_percent?: N; strong_downtrend_percent?: N;
  new_52w_highs?: N; new_52w_lows?: N; mcclellan_summation?: N;
}

export interface Regime {
  market_regime?: string; nifty_price?: N; india_vix?: N; vix_regime?: string;
  vix_change_percent?: N; vix_percentile_1y?: N; vix_direction?: string;
}

export interface Freshness {
  generated?: string; age_seconds?: number | null; label?: string; saved_at?: string; file_age_seconds?: number | null;
}

/** Every top-level key is null when there is no cache. */
export interface MarketOverviewData {
  kpis: null | { macro?: Regime; nifty?: Quote; banknifty?: Quote; vix?: Quote; indicators?: Indicators };
  chart: null | { candles?: Candle[] };
  breadth: Breadth | null;
  flows: Flows | null;
  sectors: Sector[] | null;
  derivatives: Derivatives | null;
  freshness: Freshness | null;
  guardrails?: { text?: string } | null;
}

export interface RiskEvent {
  name?: string; datetime_utc?: string; category?: string; severity?: string; risk_level?: string; impact_note?: string;
}
export interface Events {
  status?: string; source_fresh?: boolean; overall_risk?: string; source_checked_at_utc?: string;
  upcoming_event_count?: number; upcoming_events?: RiskEvent[];
}
export interface MarketAnalysisData {
  regime: Regime | null; breadth: Breadth | null; sectors: Sector[] | null; flows: Flows | null;
  derivatives: { nifty?: Derivatives; bank_nifty?: Derivatives } | null;
  indicators?: Indicators | null;
  events: Events | null; freshness: Freshness | null; guardrails?: { text?: string } | null;
}
