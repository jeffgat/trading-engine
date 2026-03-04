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
  orb_high: number | null;
  orb_low: number | null;
  daily_atr: number;
  levels: TradeLevels | null;
  tp1_hit: boolean;
  exit_type: string | null;
  r_result: number | null;
  config_name?: string;
  paused?: boolean;
}

export interface StatusResponse {
  configs: Record<string, { engines: SessionStatus[] }>;
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

export type WsMessage =
  | { type: "status"; data: StatusResponse }
  | { type: "trade_log"; data: TradeLogEntry }
  | { type: "log"; data: MainLogEntry }
  | { type: "accounts_update"; data: AccountsUpdatePayload };
