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
}

export interface StatusResponse {
  engines: SessionStatus[];
  uptime_seconds: number;
  mode: string;
}

export interface TradeLogEntry {
  timestamp: string;
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
  orb_start: string;
  orb_end: string;
  entry_start: string;
  entry_end: string;
  flat_start: string;
  flat_end: string;
  stop_atr_pct: number;
  stop_basis: string;
  stop_orb_pct: number;
  min_gap_atr_pct: number;
  max_gap_atr_pct: number;
  gap_filter_basis: string;
  min_gap_orb_pct: number;
  rr: number;
  tp1_ratio: number;
  risk_usd: number;
  point_value: number;
  min_qty: number;
  qty_step: number;
  be_offset_ticks: number;
  min_tick: number;
  exec_ticker: string;
  excluded_dow: number | null;
}

export interface ConfigResponse {
  config: Record<string, unknown>;
  sessions: Record<string, SessionConfig>;
}

export type WsMessage =
  | { type: "status"; data: StatusResponse }
  | { type: "trade_log"; data: TradeLogEntry }
  | { type: "log"; data: MainLogEntry };
