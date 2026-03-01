export interface BacktestConfig {
  rr: number;
  tp1_ratio: number;
  risk_usd: number;
  atr_length: number;
  min_qty: number;
  qty_step: number;
  strategy?: string;
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
  calmar_ratio: number;
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
  entry_time?: string;
  exit_time?: string;
}

export interface CandleBar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
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
  total_trades: number;
  date_start: string;
  date_end: string;
  name?: string;
  notes?: string;
  strategy?: string;
  starred?: boolean;
  hidden?: boolean;
  // Strategy params (global)
  rr: number;
  tp1_ratio: number;
  risk_usd: number;
  atr_length: number;
  min_qty: number;
  qty_step: number;
  point_value: number;
  // Per-session params (nullable — only present when session is active)
  ny_stop_atr_pct?: number;
  ny_min_gap_atr_pct?: number;
  ny_max_gap_points?: number;
  ny_orb_window?: string;
  ny_entry_window?: string;
  ny_flat_window?: string;
  asia_stop_atr_pct?: number;
  asia_min_gap_atr_pct?: number;
  asia_max_gap_points?: number;
  asia_orb_window?: string;
  asia_entry_window?: string;
  asia_flat_window?: string;
  ldn_stop_atr_pct?: number;
  ldn_min_gap_atr_pct?: number;
  ldn_max_gap_points?: number;
  ldn_orb_window?: string;
  ldn_entry_window?: string;
  ldn_flat_window?: string;
  // Metrics (dedicated columns)
  total_pnl_usd: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown_usd: number;
  profit_factor: number;
  sortino_ratio: number;
  calmar_ratio: number;
}

export interface OptimizationResult {
  id?: string;
  run_type?: "sweep" | "bayesian" | "lhs";
  total_combinations: number;
  swept_params: Record<string, number[]>;
  best_by_sharpe: { config: BacktestConfig; summary: BacktestSummary } | null;
  best_by_pnl: { config: BacktestConfig; summary: BacktestSummary } | null;
  best_by_profit_factor: { config: BacktestConfig; summary: BacktestSummary } | null;
  best_by_calmar: { config: BacktestConfig; summary: BacktestSummary } | null;
  all_results: { config: BacktestConfig; summary: BacktestSummary }[];
  date_start?: string;
  date_end?: string;
  has_trade_data?: boolean;
  bayesian?: {
    sampler: string;
    objective: string;
    n_trials: number;
    convergence: { trial: number; value: number; best_so_far: number }[];
  };
}

export interface EquityBand {
  percentiles: number[];
  curves: number[][];
}

export interface MonteCarloResult {
  n_simulations: number;
  n_trades: number;
  method: "bootstrap" | "shuffle";
  equity_bands: EquityBand;
  drawdown_bands: EquityBand;
  final_pnl: number[];
  max_drawdowns: number[];
  sharpe_ratios: number[];
  final_pnl_percentiles: Record<string, number>;
  max_dd_percentiles: Record<string, number>;
  sharpe_percentiles: Record<string, number>;
  actual_final_pnl: number;
  actual_max_drawdown: number;
  actual_sharpe: number;
  ruin_probability: number;
  ruin_threshold: number;
}

export interface InstrumentCoverage {
  instrument: string;
  backtest_count: number;
  optimization_count: number;
  earliest_date: string;
  latest_date: string;
  last_run_at: string;
  sessions_tested: string[];
  best_sharpe: number | null;
  best_r_per_year: number | null;
  best_win_rate: number | null;
  best_profit_factor: number | null;
}

export interface TestingPlanItem {
  id: number;
  instrument: string;
  title: string;
  status: "pending" | "completed";
  notes: string | null;
  sort_order: number;
  created_at: string;
  completed_at: string | null;
}

export interface ParamCoverageDetail {
  values: number[];
  min: number;
  max: number;
  count: number;
}

export interface OptimizationHistoryItem {
  id: string;
  timestamp: string;
  instrument: string;
  sessions: string[];
  risk_usd: number;
  swept_params: string[];
  total_combinations: number;
  best_sharpe: number;
  best_pnl_usd: number;
  date_start: string;
  date_end: string;
  run_type?: string;
  strategy?: string;
  name?: string;
}
