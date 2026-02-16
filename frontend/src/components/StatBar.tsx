import { useMemo } from "react";
import type { BacktestSummary, Trade } from "../lib/types";
import { formatCurrency, formatPct, formatNumber, pnlColor } from "../lib/utils";
import { StatCard } from "./StatCard";

function formatR(r: number): string {
  const sign = r >= 0 ? "+" : "";
  return `${sign}${r.toFixed(2)}R`;
}

function computeStreakR(trades: Trade[], riskUsd: number) {
  const filled = trades.filter((t) => t.exit_type !== "no_fill");
  let maxWinR = 0;
  let maxLossR = 0;
  let curWinR = 0;
  let curLossR = 0;

  for (const t of filled) {
    const r = t.pnl_usd / riskUsd;
    if (t.pnl_usd > 0) {
      curWinR += r;
      curLossR = 0;
    } else if (t.pnl_usd < 0) {
      curLossR += r;
      curWinR = 0;
    } else {
      curWinR = 0;
      curLossR = 0;
    }
    if (curWinR > maxWinR) maxWinR = curWinR;
    if (curLossR < maxLossR) maxLossR = curLossR;
  }

  return { maxWinStreakR: maxWinR, maxLossStreakR: maxLossR };
}

interface StatBarProps {
  summary: BacktestSummary;
  trades: Trade[];
  riskUsd: number;
}

export function StatBar({ summary, trades, riskUsd }: StatBarProps) {
  const ddColor = "var(--color-loss)";

  const netR = summary.total_pnl_usd / riskUsd;
  const ddR = summary.max_drawdown_usd / riskUsd;
  const avgR = summary.avg_pnl_usd / riskUsd;

  const { maxWinStreakR, maxLossStreakR } = useMemo(() => computeStreakR(trades, riskUsd), [trades, riskUsd]);

  return (
    <div className="space-y-3">
      {/* Row 1 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Net R"
          value={formatR(netR)}
          subValue={`Avg ${formatR(avgR)}/trade`}
          tooltip={`Total P&L in risk units (1R = ${formatCurrency(riskUsd)})`}
          color={pnlColor(netR)}
        />
        <StatCard
          label="Max DD (R)"
          value={formatR(ddR)}
          subValue={`${formatNumber(summary.max_drawdown_pct)}%`}
          tooltip="Max drawdown in risk units"
          color={ddColor}
        />
        <StatCard
          label="Total Trades"
          value={summary.total_trades.toString()}
          subValue={`${summary.total_signals} signals, ${summary.no_fills} no-fills`}
          tooltip="Filled trades (excludes no-fill signals)"
        />
        <StatCard
          label="Win Rate"
          value={formatPct(summary.win_rate)}
          subValue={`${summary.win_count}/${summary.total_trades}`}
          tooltip="Winning trades / total filled trades"
          color="var(--color-text-primary)"
        />
        <StatCard
          label="Profit Factor"
          value={formatNumber(summary.profit_factor)}
          subValue={`Sharpe ${formatNumber(summary.sharpe_ratio, 3)}`}
          tooltip="Gross profit / gross loss"
          color={summary.profit_factor >= 1 ? "var(--color-profit)" : "var(--color-loss)"}
        />
      </div>

      {/* Row 2 */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard
          label="Best Streak (R)"
          value={formatR(maxWinStreakR)}
          subValue={`${summary.max_consecutive_wins} consecutive wins`}
          tooltip="Total R earned during longest winning streak"
          color="var(--color-profit)"
        />
        <StatCard
          label="Worst Streak (R)"
          value={formatR(maxLossStreakR)}
          subValue={`${summary.max_consecutive_losses} consecutive losses`}
          tooltip="Total R lost during longest losing streak"
          color="var(--color-loss)"
        />
        <StatCard
          label="Sharpe / Sortino"
          value={formatNumber(summary.sharpe_ratio, 3)}
          subValue={`Sortino ${formatNumber(summary.sortino_ratio, 3)}`}
          tooltip="Risk-adjusted return ratios"
        />
        <StatCard
          label="Calmar Ratio"
          value={formatNumber(summary.calmar_ratio ?? 0, 3)}
          subValue={`Net ${formatR(netR)} / DD ${formatR(ddR)}`}
          tooltip="Net R / Max Drawdown R — higher is better"
          color={(summary.calmar_ratio ?? 0) >= 1 ? "var(--color-profit)" : "var(--color-text-primary)"}
        />
      </div>
    </div>
  );
}
