import type { BacktestResult } from "./types";

function generateMockEquityCurve() {
  const curve = [];
  let cumulative = 0;
  const startDate = new Date("2020-01-06");
  const tradeCount = 589;

  for (let i = 0; i < tradeCount; i++) {
    const date = new Date(startDate);
    date.setDate(date.getDate() + Math.floor(i * 1.7));

    // Simulate realistic trade P&L with slight positive edge
    const isWin = Math.random() < 0.518;
    let pnl: number;
    if (isWin) {
      // Wins range from small (TP1+BE) to full (TP1+TP2)
      pnl = 1000 + Math.random() * 4000;
    } else {
      // Losses are typically -1R (stop loss)
      pnl = -(2000 + Math.random() * 2500);
    }

    cumulative += pnl;
    curve.push({
      date: date.toISOString().split("T")[0],
      pnl_cumulative: Math.round(cumulative * 100) / 100,
      pnl_per_trade: Math.round(pnl * 100) / 100,
    });
  }

  return curve;
}

const equityCurve = generateMockEquityCurve();
const finalPnl = equityCurve[equityCurve.length - 1].pnl_cumulative;

export const MOCK_DATA: BacktestResult = {
  config: {
    rr: 2.5,
    tp1_ratio: 0.5,
    risk_usd: 5000,
    atr_length: 14,

    min_qty: 1,
    qty_step: 1,
    instrument: "NQ",
    point_value: 20,
    ny_stop_atr_pct: 15,
    ny_min_gap_atr_pct: 1.75,
    ny_max_gap_points: 100,
  },
  summary: {
    total_signals: 742,
    total_trades: 589,
    no_fills: 153,
    win_count: 305,
    loss_count: 271,
    be_count: 13,
    win_rate: 0.5178,
    total_pnl_usd: finalPnl,
    avg_pnl_usd: finalPnl / 589,
    avg_win_usd: 3420.5,
    avg_loss_usd: -2815.3,
    largest_win_usd: 8750.0,
    largest_loss_usd: -5125.0,
    profit_factor: 1.37,
    avg_r: 0.128,
    avg_win_r: 0.955,
    avg_loss_r: -0.812,
    max_drawdown_usd: -32450.0,
    max_drawdown_pct: -18.5,
    sharpe_ratio: 0.42,
    sortino_ratio: 0.68,
    calmar_ratio: 0.85,
    max_consecutive_wins: 8,
    max_consecutive_losses: 6,
    exit_breakdown: {
      sl: 271,
      tp1_tp2: 185,
      tp1_be: 72,
      tp1_eod: 28,
      eod: 20,
      no_fill: 153,
      tp2_single: 13,
    },
    pnl_by_year: {
      "2020": 28500,
      "2021": 42300,
      "2022": -12400,
      "2023": 35200,
      "2024": 18900,
    },
    pnl_by_month: {},
    pnl_by_dow: {
      Mon: 18200,
      Tue: 22500,
      Wed: -5400,
      Thu: 31200,
      Fri: 12300,
    },
    long_trades: 298,
    short_trades: 291,
    long_win_rate: 0.537,
    short_win_rate: 0.498,
    long_pnl_usd: finalPnl * 0.58,
    short_pnl_usd: finalPnl * 0.42,
  },
  trades: [],
  equity_curve: equityCurve,
};
