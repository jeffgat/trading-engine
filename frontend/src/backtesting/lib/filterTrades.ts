import type { Trade, EquityCurvePoint, BacktestSummary } from "./types";

/**
 * Filter trades by date range and rebuild equity curve + summary stats client-side.
 */
export function filterTradesByDate(
  trades: Trade[],
  start?: string,
  end?: string,
): { trades: Trade[]; equityCurve: EquityCurvePoint[]; summary: BacktestSummary } {
  let filtered = trades;
  if (start) filtered = filtered.filter((t) => t.date >= start);
  if (end) filtered = filtered.filter((t) => t.date <= end);

  const filled = filtered.filter((t) => t.exit_type !== "no_fill");

  // Rebuild equity curve
  let cumulative = 0;
  const equityCurve: EquityCurvePoint[] = filled.map((t) => {
    cumulative += t.pnl_usd;
    return {
      date: t.date,
      pnl_cumulative: Math.round(cumulative * 100) / 100,
      pnl_per_trade: Math.round(t.pnl_usd * 100) / 100,
    };
  });

  // Recompute summary
  const summary = recomputeSummary(filtered, filled);

  return { trades: filtered, equityCurve, summary };
}

function maxConsecutive(arr: boolean[]): number {
  let max = 0;
  let cur = 0;
  for (const v of arr) {
    if (v) { cur++; max = Math.max(max, cur); }
    else cur = 0;
  }
  return max;
}

function recomputeSummary(allTrades: Trade[], filled: Trade[]): BacktestSummary {
  if (!filled.length) {
    return emptySummary(allTrades.length);
  }

  const pnlUsd = filled.map((t) => t.pnl_usd);
  const rMultiples = filled.map((t) => t.r_multiple);

  const wins = pnlUsd.filter((p) => p > 0);
  const losses = pnlUsd.filter((p) => p < 0);
  const breakevens = pnlUsd.filter((p) => p === 0);

  const totalWins = wins.reduce((s, v) => s + v, 0);
  const totalLosses = losses.reduce((s, v) => s + v, 0);

  // Drawdown (USD)
  const equity: number[] = [];
  let cum = 0;
  for (const p of pnlUsd) { cum += p; equity.push(cum); }
  let peak = -Infinity;
  let maxDd = 0;
  let maxDdPct = 0;
  for (const e of equity) {
    peak = Math.max(peak, e);
    const dd = e - peak;
    if (dd < maxDd) maxDd = dd;
    if (peak > 0) {
      const ddPct = (dd / peak) * 100;
      if (ddPct < maxDdPct) maxDdPct = ddPct;
    }
  }

  // Streaks
  const isWin = pnlUsd.map((p) => p > 0);
  const isLoss = pnlUsd.map((p) => p < 0);
  const maxConsecWins = maxConsecutive(isWin);
  const maxConsecLosses = maxConsecutive(isLoss);

  // R stats
  const avgR = mean(rMultiples);
  const stdR = rMultiples.length > 1 ? std(rMultiples) : 1;
  const sharpe = stdR > 0 ? (avgR / stdR) * Math.sqrt(252) : 0;

  const downsideR = rMultiples.map((r) => Math.min(r, 0));
  const downsideStd = Math.sqrt(mean(downsideR.map((r) => r * r)));
  const sortino = downsideStd > 0 ? (avgR / downsideStd) * Math.sqrt(252) : 0;

  // R drawdown + calmar
  const rEquity: number[] = [];
  let rCum = 0;
  for (const r of rMultiples) { rCum += r; rEquity.push(rCum); }
  let rPeak = -Infinity;
  let maxDdR = 0;
  for (const e of rEquity) {
    rPeak = Math.max(rPeak, e);
    const dd = Math.abs(e - rPeak);
    if (dd > maxDdR) maxDdR = dd;
  }
  const netR = rEquity.length > 0 ? rEquity[rEquity.length - 1] : 0;
  const calmar = maxDdR > 0 ? netR / maxDdR : 0;

  const profitFactor = totalLosses !== 0 ? Math.abs(totalWins / totalLosses) : 0;

  // Exit breakdown
  const exitBreakdown: Record<string, number> = {};
  for (const t of allTrades) {
    exitBreakdown[t.exit_type] = (exitBreakdown[t.exit_type] || 0) + 1;
  }

  // PnL by year, month, dow
  const dowNames = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const pnlByYear: Record<string, number> = {};
  const pnlByMonth: Record<string, number> = {};
  const pnlByDow: Record<string, number> = {};
  for (const t of filled) {
    pnlByYear[t.date.slice(0, 4)] = (pnlByYear[t.date.slice(0, 4)] || 0) + t.pnl_usd;
    pnlByMonth[t.date.slice(0, 7)] = (pnlByMonth[t.date.slice(0, 7)] || 0) + t.pnl_usd;
    const d = new Date(t.date + "T00:00:00");
    const dow = dowNames[d.getDay() === 0 ? 6 : d.getDay() - 1]; // JS: 0=Sun, Python: 0=Mon
    pnlByDow[dow] = (pnlByDow[dow] || 0) + t.pnl_usd;
  }

  // Direction breakdown
  const longTrades = filled.filter((t) => t.direction === "long");
  const shortTrades = filled.filter((t) => t.direction === "short");
  const longWinRate = longTrades.length ? longTrades.filter((t) => t.pnl_usd > 0).length / longTrades.length : 0;
  const shortWinRate = shortTrades.length ? shortTrades.filter((t) => t.pnl_usd > 0).length / shortTrades.length : 0;

  // R by year
  const rByYear: Record<string, number> = {};
  for (const t of filled) {
    rByYear[t.date.slice(0, 4)] = (rByYear[t.date.slice(0, 4)] || 0) + t.r_multiple;
  }

  return {
    total_signals: allTrades.length,
    total_trades: filled.length,
    no_fills: exitBreakdown["no_fill"] || 0,
    win_count: wins.length,
    loss_count: losses.length,
    be_count: breakevens.length,
    win_rate: filled.length > 0 ? wins.length / filled.length : 0,
    total_pnl_usd: sum(pnlUsd),
    avg_pnl_usd: mean(pnlUsd),
    avg_win_usd: wins.length > 0 ? mean(wins) : 0,
    avg_loss_usd: losses.length > 0 ? mean(losses) : 0,
    largest_win_usd: wins.length > 0 ? Math.max(...wins) : 0,
    largest_loss_usd: losses.length > 0 ? Math.min(...losses) : 0,
    profit_factor: profitFactor,
    avg_r: avgR,
    avg_win_r: rMultiples.filter((r) => r > 0).length > 0 ? mean(rMultiples.filter((r) => r > 0)) : 0,
    avg_loss_r: rMultiples.filter((r) => r < 0).length > 0 ? mean(rMultiples.filter((r) => r < 0)) : 0,
    max_drawdown_usd: maxDd,
    max_drawdown_pct: maxDdPct,
    sharpe_ratio: sharpe,
    sortino_ratio: sortino,
    calmar_ratio: calmar,
    max_consecutive_wins: maxConsecWins,
    max_consecutive_losses: maxConsecLosses,
    exit_breakdown: exitBreakdown,
    pnl_by_year: pnlByYear,
    pnl_by_month: pnlByMonth,
    pnl_by_dow: pnlByDow,
    r_by_year: rByYear,
    long_trades: longTrades.length,
    short_trades: shortTrades.length,
    long_win_rate: longWinRate,
    short_win_rate: shortWinRate,
    long_pnl_usd: sum(longTrades.map((t) => t.pnl_usd)),
    short_pnl_usd: sum(shortTrades.map((t) => t.pnl_usd)),
  };
}

function emptySummary(totalSignals: number): BacktestSummary {
  return {
    total_signals: totalSignals,
    total_trades: 0,
    no_fills: totalSignals,
    win_count: 0,
    loss_count: 0,
    be_count: 0,
    win_rate: 0,
    total_pnl_usd: 0,
    avg_pnl_usd: 0,
    avg_win_usd: 0,
    avg_loss_usd: 0,
    largest_win_usd: 0,
    largest_loss_usd: 0,
    profit_factor: 0,
    avg_r: 0,
    avg_win_r: 0,
    avg_loss_r: 0,
    max_drawdown_usd: 0,
    max_drawdown_pct: 0,
    sharpe_ratio: 0,
    sortino_ratio: 0,
    calmar_ratio: 0,
    max_consecutive_wins: 0,
    max_consecutive_losses: 0,
    exit_breakdown: { no_fill: totalSignals },
    pnl_by_year: {},
    pnl_by_month: {},
    pnl_by_dow: {},
    long_trades: 0,
    short_trades: 0,
    long_win_rate: 0,
    short_win_rate: 0,
    long_pnl_usd: 0,
    short_pnl_usd: 0,
  };
}

function sum(arr: number[]): number {
  return arr.reduce((s, v) => s + v, 0);
}

function mean(arr: number[]): number {
  return arr.length > 0 ? sum(arr) / arr.length : 0;
}

function std(arr: number[]): number {
  if (arr.length <= 1) return 0;
  const m = mean(arr);
  const variance = arr.reduce((s, v) => s + (v - m) ** 2, 0) / (arr.length - 1);
  return Math.sqrt(variance);
}
