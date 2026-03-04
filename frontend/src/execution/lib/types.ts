export interface TradeLevels {
  entry: number;
  stop: number;
  tp1: number;
  tp2: number;
  qty: number;
  direction: number; // 1 = long, -1 = short
}

export interface SessionStatus {
  session: string;
  state: string;
  date: string;
  daily_atr: number;
  tp1_hit: boolean;
  exit_type: string | null;
  r_result: number | null;
  config_name?: string;
  paused?: boolean;
  excluded_dow?: number | number[] | null;
  fomc_exclusion?: boolean;
  // Engine type — absent for continuation, "ifvg" for LSI
  type?: "ifvg";
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
  qty_multiplier: number;
  // Common strategy fields
  rr: number;
  tp1_ratio: number;
  long_only: boolean;
  // Risk & sizing
  risk_usd: number;
  point_value: number;
  min_qty: number;
  max_single_risk_usd: number;
  qty_step: number;
  be_offset_ticks: number;
  min_tick: number;
  exec_ticker: string;
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
  /** New multi-webhook format */
  webhooks: WebhookEntry[];
  sessions: string[];
  lsi_sessions: string[];
}

export interface ConfigResponse {
  config: Record<string, unknown>;
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
