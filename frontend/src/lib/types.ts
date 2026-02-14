export interface BacktestConfig {
  rr: number;
  tp1_ratio: number;
  risk_usd: number;
  atr_length: number;
  be_offset_ticks: number;
  min_qty: number;
  qty_step: number;
  instrument?: string;
  point_value?: number;
  [key: string]: unknown;
}

export interface BacktestSummary {
  total_signals: number;
  total_trades: number;
  no_fills: number;
  win_count: number;
  loss_count: number;
  be_count: number;
  win_rate: number;
  total_pnl_usd: number;
  avg_pnl_usd: number;
  avg_win_usd: number;
  avg_loss_usd: number;
  largest_win_usd: number;
  largest_loss_usd: number;
  profit_factor: number;
  avg_r: number;
  avg_win_r: number;
  avg_loss_r: number;
  max_drawdown_usd: number;
  max_drawdown_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  exit_breakdown: Record<string, number>;
  pnl_by_year: Record<string, number>;
  pnl_by_month: Record<string, number>;
  pnl_by_dow: Record<string, number>;
  long_trades: number;
  short_trades: number;
  long_win_rate: number;
  short_win_rate: number;
  long_pnl_usd: number;
  short_pnl_usd: number;
}

export interface Trade {
  date: string;
  session: string;
  direction: "long" | "short";
  entry_price: number;
  stop_price: number;
  tp1_price: number;
  tp2_price: number;
  exit_type: string;
  pnl_usd: number;
  pnl_points: number;
  r_multiple: number;
  qty: number;
  gap_size: number;
  risk_points: number;
}

export interface EquityCurvePoint {
  date: string;
  pnl_cumulative: number;
  pnl_per_trade: number;
}

export interface BacktestResult {
  id?: string;
  name?: string;
  notes?: string;
  config: BacktestConfig;
  summary: BacktestSummary;
  trades: Trade[];
  equity_curve: EquityCurvePoint[];
}

export interface BacktestHistoryItem {
  id: string;
  timestamp: string;
  instrument: string;
  sessions: string[];
  total_pnl_usd: number;
  total_trades: number;
  win_rate: number;
  date_start: string;
  date_end: string;
  name?: string;
  notes?: string;
}

export interface OptimizationResult {
  id?: string;
  total_combinations: number;
  swept_params: Record<string, number[]>;
  best_by_sharpe: { config: BacktestConfig; summary: BacktestSummary } | null;
  best_by_pnl: { config: BacktestConfig; summary: BacktestSummary } | null;
  best_by_profit_factor: { config: BacktestConfig; summary: BacktestSummary } | null;
  all_results: { config: BacktestConfig; summary: BacktestSummary }[];
}

export interface OptimizationHistoryItem {
  id: string;
  timestamp: string;
  instrument: string;
  sessions: string[];
  swept_params: string[];
  total_combinations: number;
  best_sharpe: number;
  best_pnl_usd: number;
}
