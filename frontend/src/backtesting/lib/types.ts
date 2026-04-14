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
  total_r: number;
  max_drawdown_usd: number;
  max_drawdown_pct: number;
  max_drawdown_r: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  calmar_ratio: number;
  max_consecutive_wins: number;
  max_consecutive_losses: number;
  exit_breakdown: Record<string, number>;
  pnl_by_year: Record<string, number>;
  pnl_by_month: Record<string, number>;
  pnl_by_dow: Record<string, number>;
  r_by_year?: Record<string, number>;
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
  // LSI overlay data (only present for lsi strategy trades)
  lsi_swept_level?: number;
  lsi_fvg_top?: number;
  lsi_fvg_bottom?: number;
  lsi_fvg_time?: string;
  lsi_sweep_time?: string;
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
  date_start?: string;
  date_end?: string;
  config: BacktestConfig;
  summary: BacktestSummary;
  trades: Trade[];
  equity_curve: EquityCurvePoint[];
}

export interface SavedConfig {
  id: number;
  timestamp: string;
  updated_at: string;
  name: string;
  notes?: string | null;
  instrument: string;
  sessions: string[];
  strategy: string;
  config: BacktestConfig;
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
  // LSI params (present when strategy === "lsi")
  lsi_n_left?: number;
  lsi_n_right?: number;
  lsi_fvg_window_left?: number;
  lsi_fvg_window_right?: number;
  lsi_stop_mode?: string;
  lsi_entry_mode?: string;
  lsi_first_fvg_only?: number;
  lsi_clean_path?: number;
  lsi_be_swing_n_left?: number;
  lsi_cancel_on_swing?: number;
  // HTF-LSI params
  htf_level_tf_minutes?: number;
  htf_n_left?: number;
  htf_trade_max_per_session?: number;
  max_fvg_to_inversion_bars?: number;
  htf_lsi_include_htf_levels?: number;
  htf_lsi_reference_levels?: string;
  data_sweep_min_daily_atr_pct?: number;
  data_sweep_require_session_extreme?: number;
  data_sweep_event_types?: string;
  data_sweep_release_window_minutes?: number;
  // Metrics (dedicated columns)
  total_pnl_usd: number;
  total_r: number;
  win_rate: number;
  sharpe_ratio: number;
  max_drawdown_usd: number;
  max_drawdown_r: number;
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

// ── Regime report types ───────────────────────────────────────────────

export interface RegimeCoverage {
  mapped: number;
  unmapped: number;
  total: number;
}

export interface RegimeStat {
  regime: number;
  trades: number;
  win_rate: number;
  total_r: number;
  avg_r: number;
  pf: number;
  long_trades: number;
  short_trades: number;
  // Volatility profile (from daily regime data)
  days?: number;
  pct_days?: number;
  mean_vol?: number | null;
  mean_range_pct?: number | null;
  // Feature fingerprint & label
  label?: string;
  features?: Record<string, number>;
}

export interface RegimeReportSection {
  coverage: RegimeCoverage;
  regime_stats: RegimeStat[];
  states?: number;
  clusters?: number;
  bic?: number;
  silhouette?: number;
  device?: string;
  description?: string;
  feature_cols?: string[];
}

export interface RegimeReportSummary {
  methods: string[];
  trade_count: number;
  hmm_total_r?: number;
  lstm_total_r?: number;
  hmm_best_pf?: number;
  lstm_best_pf?: number;
}

export interface RegimeReportMeta {
  backtest_result_id: string;
  backtest_name?: string;
  instrument: string;
  sessions: string;
  date_start: string;
  date_end: string;
}

export interface RegimeReportResult {
  result_id?: string;
  meta: RegimeReportMeta;
  summary: RegimeReportSummary;
  hmm?: RegimeReportSection;
  lstm?: RegimeReportSection;
}

export interface RegimeReportHistoryItem {
  id: number;
  result_id: string;
  timestamp: string;
  instrument: string;
  sessions: string | null;
  backtest_result_id: string;
  backtest_name?: string | null;
  date_start?: string | null;
  date_end?: string | null;
  methods: string;
  hmm_states?: number | null;
  lstm_clusters?: number | null;
  hmm_total_r?: number | null;
  lstm_total_r?: number | null;
  hmm_best_pf?: number | null;
  lstm_best_pf?: number | null;
}

// ── News Straddle types ──────────────────────────────────────────────

export interface NewsStraddleEvent {
  date: string;
  event_type: string;
  reference_price: number;
  buffer_points: number;
  target_points: number;
  direction_filled: "long" | "short" | null;
  fill_price: number;
  seconds_to_fill: number;
  mfe_points: number;
  mae_points: number;
  time_to_mfe_seconds: number;
  target_hit: boolean;
  time_to_target_seconds: number | null;
  whipsaw: boolean;
  final_points: number;
  exit_type: string;
}

export interface NewsStraddleByEventType {
  fills: number;
  target_hit_count: number;
  target_hit_rate: number;
  avg_mfe: number;
  avg_mae: number;
  avg_final_points: number;
  whipsaw_count: number;
}

export interface NewsStraddleSummary {
  total_events: number;
  events_with_data: number;
  skipped_no_data: number;
  fills: number;
  no_fills: number;
  long_fills: number;
  short_fills: number;
  target_hit_count: number;
  target_hit_rate: number;
  whipsaw_count: number;
  whipsaw_rate: number;
  avg_mfe: number;
  avg_mae: number;
  median_mfe: number;
  median_mae: number;
  avg_final_points: number;
  pct_profitable: number;
  avg_seconds_to_fill: number;
  avg_time_to_mfe_seconds: number;
  stop_loss_count: number;
  stop_loss_rate: number;
  filtered_out?: number;
  by_event_type: Record<string, NewsStraddleByEventType>;
}

export interface NewsStraddleResult {
  config: {
    buffer_points: number;
    target_points: number;
    event_types: string[];
    observation_window_seconds: number;
    instrument: string;
    stop_loss_points: number | null;
    max_atr_pct?: number | null;
    min_volume_ratio?: number | null;
    max_volume_ratio?: number | null;
    direction_filter?: string | null;
    skip_days?: number[];
  };
  summary: NewsStraddleSummary;
  events: NewsStraddleEvent[];
}

export interface NewsStraddleSweepRow {
  buffer_points: number;
  target_points: number;
  fills: number;
  target_hit_count: number;
  target_hit_rate: number;
  whipsaw_count: number;
  whipsaw_rate: number;
  avg_mfe: number;
  avg_mae: number;
  avg_final_points: number;
  pct_profitable: number;
}

export interface NewsStraddleSweepResult {
  swept_params: Record<string, number[]>;
  results: NewsStraddleSweepRow[];
  total_combinations: number;
  event_types: string[];
  observation_window_seconds: number;
  instrument: string;
}

export interface NewsStraddleHistoryItem {
  id: number;
  result_id: string;
  timestamp: string;
  instrument: string;
  buffer_points: number;
  target_points: number;
  observation_window_seconds: number;
  event_types: string;
  date_start: string | null;
  date_end: string | null;
  fills: number | null;
  target_hit_rate: number | null;
  whipsaw_rate: number | null;
  pct_profitable: number | null;
  avg_mfe: number | null;
  avg_mae: number | null;
  avg_final_points: number | null;
  stop_loss_points: number | null;
  starred: number;
  max_atr_pct: number | null;
  min_volume_ratio: number | null;
  max_volume_ratio: number | null;
  direction_filter: string | null;
  skip_days: string | null; // JSON array string from sqlite json_extract
}
