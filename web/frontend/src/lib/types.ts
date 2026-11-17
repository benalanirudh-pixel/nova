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
  breadth: Breadth | null;
  flows: Flows | null;
  sectors: Sector[] | null;
  derivatives: Derivatives | null;
  freshness: Freshness | null;
  guardrails?: { text?: string } | null;
  live?: LiveBlock;
}

export interface LiveQuote { name: string; price: number | null; change_abs: number | null; change_percent: number | null }
export interface GiftNifty { price: number; change: number | null; change_pct: number | null; expiry?: string; as_of?: string }
/** Live NSE overlay added by the API; data fields are null when NSE could not be reached (reason in `error`). */
export interface LiveBlock {
  as_of: string | null; error: string | null;
  status: { state?: string; message?: string; trade_date?: string } | null;
  gift_nifty: GiftNifty | null; sectors: LiveQuote[] | null;
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

type C = number | null;
export interface Quarter {
  period: string; revenue_cr: C; ebitda_cr: C; operating_income_cr: C; net_income_cr: C; eps: C;
  operating_margin: C; revenue_qoq: C; net_income_qoq: C; revenue_yoy: C;
}
export interface Peer {
  symbol: string; company_name?: string; price?: C; return_20d?: C; return_60d?: C; relative_strength_20d?: C;
  rsi_14?: C; trend?: string; momentum_score?: C; traded_value_cr?: C; is_self?: boolean;
}
export interface NewsItem { title: string; link: string; source?: string | null; published?: string | null }
export interface Highlight { tone: "positive" | "negative" | "neutral"; text: string }

/** /api/stock/{symbol}/profile — every section is null when its source failed; reason in `errors`. */
export interface StockProfile {
  symbol: string;
  profile: null | { company?: string; sector?: string; industry?: string; website?: string | null; description?: string; employees?: C };
  ratios: null | Record<string, C>;
  quarters: Quarter[] | null;
  results: null | {
    next_date: string | null; eps_estimate: C; revenue_estimate_cr: C; ex_dividend_date: string | null;
    board_meetings: { date: string; purpose: string | null }[]; source: string;
  };
  ownership: null | {
    nse: null | { promoter_pct: C; fii_pct: C; dii_pct: C; public_pct: C };
    yahoo: null | { insiders_pct: C; institutions_pct: C; institutions_float_pct: C; institutions_count: C };
  };
  peers: null | { basis: string; group: string; peer_count?: number; as_of: string | null; rows: Peer[] };
  news: NewsItem[] | null;
  corporate_actions: { ex_date?: string; subject?: string }[] | null;
  highlights: Highlight[];
  errors: Record<string, string>;
  generated: string;
}

export interface PreopenRow { symbol: string; iep: C; change_pct: C; prev_close: C; turnover_cr: C }
export interface FocusRow {
  symbol: string; company_name?: string | null; sector?: string | null; price?: C; return_1d?: C; return_20d?: C;
  rsi_14?: C; relative_volume?: C; distance_52w_high?: C; trend?: string; score?: C;
}
export interface CallLine { tone: "positive" | "negative" | "neutral"; topic: string; text: string }

/** /api/morning-brief — live sections are null when their source failed; reason in `errors`. */
export interface MorningBrief {
  range: null | { base: number; points: number; pct: C; low: number; high: number };
  session: null | { status?: string; message?: string; trade_date?: string; nifty_last: C; nifty_change: C; nifty_change_pct: C };
  preopen: null | {
    timestamp?: string; is_today: boolean; advances: C; declines: C; unchanged: C; min_turnover_cr: number;
    gainers: PreopenRow[]; losers: PreopenRow[]; most_active: PreopenRow[];
  };
  fii_dii: null | { category: string; date?: string; buy_cr: C; sell_cr: C; net_cr: C }[];
  movers: { gainers: { symbol: string; ltp: C; change_pct: C; turnover?: string }[]; losers: { symbol: string; ltp: C; change_pct: C; turnover?: string }[] };
  news: NewsItem[] | null;
  global: {
    indices: null | { name: string; region: string; last: number; change_pct: number; date: string }[];
    commodities: null | { name: string; price: C; change_pct: C; currency?: string }[];
    fx: null | { pair: string; rate: C; change_pct: C }[];
  };
  focus: null | { as_of: string; universe: number; screens: { key: string; title: string; rule: string; rows: FocusRow[] }[] };
  morning_call: CallLine[];
  gift_nifty?: GiftNifty | null;
  errors: Record<string, string>;
  generated: string;
  report_saved_at: string | null;
}

export interface ChainRow {
  strike: number; call_oi: C; call_change_oi: C; call_volume: C; call_iv: C; call_ltp: C;
  put_oi: C; put_change_oi: C; put_volume: C; put_iv: C; put_ltp: C;
}
export interface OiLevel { strike: number; oi: C; change_oi: C }

/** /api/fno/{NIFTY|BANKNIFTY|SENSEX} — metrics/technicals null when their source failed; reason in `errors`. */
export interface FnoDesk {
  instrument: string; name: string; exchange: string; spot: C;
  expiry: string | null; expiries: string[]; source: string | null;
  metrics: null | {
    atm: number; days_to_expiry: C; pcr_oi: C; pcr_volume: C; pcr_change_oi: C;
    call_oi: number; put_oi: number; call_change_oi: number; put_change_oi: number;
    max_pain: C; atm_iv: C; atm_call_iv: C; atm_put_iv: C; skew: C;
    straddle: C; expected_move_pct: C; breakeven_low: C; breakeven_high: C;
    resistance: OiLevel[]; support: OiLevel[]; fresh_call_writing: OiLevel[]; fresh_put_writing: OiLevel[];
    profile: ChainRow[];
  };
  technicals: null | {
    last: number; prev_close: number; change: number; change_pct: number; day_high: number; day_low: number;
    as_of: string; ema: Record<string, number>; rsi: number; atr: number; atr_pct: number; rv20: number;
    pivots: { r2: number; r1: number; pp: number; s1: number; s2: number; from: string };
    high_52w: number; low_52w: number; returns: Record<string, C>;
    candles?: { t: string; o: number; h: number; l: number; c: number }[];
  };
  read: CallLine[];
  errors: Record<string, string>;
  generated: string;
}

/* ---- Quant engine (analysis/data/quant_engine.py). Every figure is null when it could not be computed. ---- */
type QN = number | null;
export interface QuantRisk {
  status: "AVAILABLE" | "NOT_AVAILABLE"; reason?: string; as_of?: string; sessions?: number; from?: string; conventions?: string;
  returns_pct: { "1m": QN; "3m": QN; "6m": QN; "12m": QN; "12m_ex_1m": QN };
  volatility: { vol_20d_pct: QN; vol_60d_pct: QN; vol_full_pct: QN; vol_20d_percentile: QN; downside_dev_pct: QN };
  tail: { var_95_pct: QN; cvar_95_pct: QN; var_99_pct: QN; worst_day_pct: QN; worst_day_date: string; best_day_pct: QN; best_day_date: string; skew: QN; excess_kurtosis: QN };
  drawdown: { max_pct: QN; peak_date: string; trough_date: string; current_pct: QN; sessions_underwater: number; longest_underwater: number };
  ratios: { return_annual_pct: QN; sharpe_rf0: QN; sortino_rf0: QN; calmar: QN };
  benchmark: {
    name: string; status: "AVAILABLE" | "NOT_AVAILABLE"; reason?: string; sessions?: number; beta?: QN; beta_60d?: QN; correlation?: QN; r_squared?: QN;
    alpha_annual_pct?: QN; tracking_error_pct?: QN; information_ratio?: QN; up_capture_pct?: QN; down_capture_pct?: QN; excess_return_pct?: QN;
  };
  liquidity: { adv_20d_cr: QN; adv_60d_cr: QN; median_60d_cr: QN; adv_20d_vs_60d: QN; amihud_bps_per_cr: QN; participation_pct: number; days_to_exit: { notional_cr: number; days: QN }[] };
  trend_quality: { fit_60d: null | { sessions: number; slope_annual_pct: QN; r_squared: QN }; fit_120d: null | { sessions: number; slope_annual_pct: QN; r_squared: QN }; efficiency_20d: QN };
  volume_profile: null | { sessions: number; poc: number; value_area_low: number; value_area_high: number; value_area_share_pct: number; bins: { price: number; share_pct: number }[] };
  anchored_vwap: { anchor: string; date: string; vwap: number }[];
}
export interface QuantScorecard {
  status: "AVAILABLE" | "NOT_AVAILABLE"; reason?: string; sector?: string | null; universe?: number; sector_peers?: number | null;
  composite?: QN; stance?: string; pillars?: { pillar: string; universe_pct: QN; sector_pct: QN | undefined }[]; liquidity_pct?: QN;
  conflicts?: string[]; method?: string; scan_as_of?: string | null; universe_source?: string;
}
export interface StockQuant { risk: QuantRisk; scorecard: QuantScorecard }

export interface QBreadth {
  stocks: number; advancing: number; declining: number; unchanged: number; ad_ratio: QN; up_value_share_pct: QN;
  above_ema20_pct: QN; above_ema50_pct: QN; above_ema200_pct: QN; new_highs: number; new_lows: number; within_5pct_of_high_pct: QN;
  rsi_over_70_pct: QN; rsi_under_30_pct: QN; median_1d_pct: QN; median_5d_pct: QN; median_20d_pct: QN; median_60d_pct: QN; dispersion_1d_pct: QN; dispersion_20d_pct: QN;
}
export interface RotationRow {
  sector: string; stocks: number; quadrant: "Leading" | "Improving" | "Weakening" | "Lagging"; rs_60d: number; rs_20d: number; rs_momentum: number;
  median_1d: QN; median_5d: QN; median_20d: QN; above_ema50_pct: QN; above_ema200_pct: QN; value_share_pct: QN; leader: string | null;
}
export interface FactorRow { factor: string; status: string; names: number; top_pct?: number; bottom_pct?: number; spread_pct?: number; ic?: QN; monotonic?: boolean; quintiles_pct?: number[] }
export interface FactorWindow { base_date: string; to_date: string; calendar_days: number; names: number; dropped_corporate_action_suspects: number; universe_median_pct: QN; factors: FactorRow[] }
export interface BreadthPoint { date: string; stocks: number; advancing: number; declining: number; above_ema20_pct: QN; above_ema50_pct: QN; above_ema200_pct: QN; new_highs: number; new_lows: number; median_20d_pct: QN; rsi_over_70_pct: QN; rsi_under_30_pct: QN }
export interface QuantInternals {
  available: boolean; reason?: string; as_of?: string; stocks?: number; engine?: string; sector_map?: boolean; source?: string;
  internals?: {
    status: string; breadth: QBreadth; regime: { label: string; rule: string }; tiers: (QBreadth & { tier: string; value_cr: QN })[];
    concentration: { total_value_cr: QN; top10_share_pct: QN; top50_share_pct: QN; hhi: QN; top10: { symbol: string; value_cr: QN; return_1d: QN }[] };
  };
  rotation?: { status: string; sectors: RotationRow[]; counts: Record<string, number>; method: string; universe_median_60d: QN; universe_median_20d: QN };
  factor_windows?: FactorWindow[];
  breadth_history?: BreadthPoint[];
  read?: CallLine[];
}
