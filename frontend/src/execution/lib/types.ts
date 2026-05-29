export interface TradeLevels {
  entry: number;
  stop: number;
  tp1: number;
  tp2: number;
  qty: number;
  direction: number; // 1 = long, -1 = short
}

export interface RegimeGateEvaluation {
  gate: string;
  date: string;
  allowed: boolean;
  reason?: string;
  regime?: string;
  vol_regime?: string;
  combined_regime?: string;
  low_confidence?: boolean;
  warmup_ok?: boolean;
}

export interface RegimeGateStatus {
  date: string;
  allowed: boolean;
  blocking_gate?: string | null;
  evaluations: RegimeGateEvaluation[];
}

export interface AthGateCheck {
  direction: string;
  bar_time: string;
  blocked: boolean;
  available?: boolean;
  gap_pct?: number | null;
  ath_high?: number | null;
  close?: number | null;
  block_min_pct: number;
  block_max_pct: number;
}

export interface AthGateStatus {
  enabled: boolean;
  high?: number | null;
  last_update?: string | null;
  last_close?: number | null;
  current_gap_pct?: number | null;
  block_min_pct: number;
  block_max_pct: number;
  check_count?: number;
  block_count?: number;
  pass_count?: number;
  last_check?: AthGateCheck | null;
  last_block?: AthGateCheck | null;
}

export interface SessionStatus {
  session: string;
  state: string;
  raw_state?: string;
  date: string;
  daily_atr: number;
  atr_length?: number;
  tp1_hit: boolean;
  exit_type: string | null;
  r_result: number | null;
  risk_usd?: number;
  point_value?: number;
  commission_per_contract?: number;
  config_name?: string;
  signal_ticker?: string;
  exec_ticker?: string;
  paused?: boolean;
  excluded_dow?: number | number[] | null;
  fomc_exclusion?: boolean;
  skip_reason?: string | null;
  blocking_gate?: string | null;
  regime_gate_status?: RegimeGateStatus | null;
  ath?: AthGateStatus | null;
  // Engine type — absent for continuation, may be "ifvg" or "lsi" for LSI
  type?: "ifvg" | "lsi";
  // ORB fields (continuation only)
  orb_high?: number | null;
  orb_low?: number | null;
  orb_range?: number | null;
  levels?: TradeLevels | null;
  fill_timestamp?: string | null;
  stop_basis?: string;
  long_only?: boolean;
  // IFVG fields (LSI only)
  kz_high?: number | null;
  kz_low?: number | null;
  kz_source?: string | null;
  pdh?: number | null;
  pdl?: number | null;
  entry?: number | null;
  stop?: number | null;
  tp1?: number | null;
  tp2?: number | null;
  direction?: number | null;
  qty?: number | null;
  // LSI overlay fields
  swept_level?: number | null;
  swept_level_time?: string | null;  // "HH:MM" ET of the pivot bar
  fvg_top?: number | null;
  fvg_bottom?: number | null;
}

export interface ConfigGroup {
  engines: SessionStatus[];
}

export interface StatusResponse {
  configs: Record<string, ConfigGroup>;
  uptime_seconds: number;
  mode: string;
  exec_configs?: Record<string, ExecConfigMeta>;
}

export interface TradeLogEntry {
  timestamp: string;
  config?: string | null;
  asset?: string | null;
  session: string;
  event: string;
  details: Record<string, string>;
}

export interface MainLogEntry {
  timestamp: string;
  level: string;
  logger: string;
  message: string;
}

export interface LogResponse<T> {
  entries: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface SessionConfig {
  type: "continuation" | "lsi" | "ifvg";
  // ORB fields (continuation only)
  orb_start: string;
  orb_end: string;
  // Common time fields
  sweep_start?: string;
  sweep_end?: string;
  entry_start: string;
  entry_end: string;
  flat_start: string;
  flat_end: string;
  // Continuation strategy fields
  stop_atr_pct: number;
  stop_basis: string;
  stop_orb_pct: number;
  min_gap_atr_pct: number;
  max_gap_atr_pct: number;
  gap_filter_basis: string;
  min_gap_orb_pct: number;
  icf_enabled: boolean;
  fomc_exclusion: boolean;
  min_stop_pts: number;
  min_tp1_pts: number;
  // LSI strategy fields
  min_stop_points: number;
  max_bars_after_sweep: number;
  fvg_window_left: number;
  fvg_window_right?: number;
  lsi_entry_mode?: string;
  lsi_variant?: string;
  htf_level_tf_minutes?: number;
  htf_n_left?: number;
  htf_trade_max_per_session?: number;
  max_fvg_to_inversion_bars?: number;
  qty_multiplier: number;
  // Common strategy fields
  atr_length?: number;
  rr: number;
  tp1_ratio: number;
  exit_mode?: string;
  long_only: boolean;
  regime_gate?: string | null;
  regime_gates?: string[];
  structure_gate?: string | null;
  // Risk & sizing
  risk_usd: number;
  point_value: number;
  min_qty: number;
  max_single_risk_usd: number;
  qty_step: number;
  be_offset_ticks: number;
  min_tick: number;
  exec_ticker: string;
  signal_ticker?: string;
  excluded_dow: number | number[] | null;
}

export interface WebhookEntry {
  url: string;
  label: string;
  paused?: boolean;
  multiplier?: number;
}

export interface ExecConfigMeta {
  enabled: boolean;
  max_open_contracts?: number;
  /** New multi-webhook format */
  webhooks: WebhookEntry[];
  sessions: string[];
  lsi_sessions: string[];
}

export interface ConfigResponse {
  config: Record<string, unknown>;
  baseline_r: number;
  sessions: Record<string, SessionConfig>;
  overrides: Record<string, Partial<SessionConfig>>;
  defaults: Record<string, Partial<SessionConfig>>;
  exec_configs?: Record<string, ExecConfigMeta>;
}

export interface AccountsUpdatePayload {
  exec_config: string;
  webhooks: WebhookEntry[];
}

/** Raw status shape from the API/WebSocket (flat engines array). */
export interface RawStatusPayload {
  engines: SessionStatus[];
  uptime_seconds: number;
  mode: string;
}

export interface BacktestMapping {
  backtestId: string;
  deployDate: string; // YYYY-MM-DD
}

export interface ComparisonCurvePoint {
  date: string;
  backtest_r?: number;
  live_r?: number;
  live_r_per_trade?: number;
  _rawLiveR?: number;
}

export type WsMessage =
  | { type: "status"; data: RawStatusPayload }
  | { type: "trade_log"; data: TradeLogEntry }
  | { type: "log"; data: MainLogEntry }
  | { type: "accounts_update"; data: AccountsUpdatePayload };

export interface ExecTradeContext {
  instrument: string;   // "NQ", "ES", "GC"
  session: string;      // "NY", "Asia", "LDN"
  date: string;         // "YYYY-MM-DD" (from FILLED timestamp)
  direction: "long" | "short";
  entry: number;
  stop: number;
  tp1: number;
  tp2: number;
}
