import type { BacktestConfig, BacktestSummary } from "../lib/types";
import { formatCurrency, formatNumber, formatPct, pnlColor } from "../lib/utils";

interface BestEntry {
  config: BacktestConfig;
  summary: BacktestSummary;
}

interface BestResultsProps {
  bestBySharpe: BestEntry | null;
  bestByPnl: BestEntry | null;
  bestByPf: BestEntry | null;
  sweptParams: string[];
}

function getSweptValues(config: BacktestConfig, params: string[]): string {
  return params
    .map((p) => {
      const val = config[p];
      if (val == null) return null;
      const label = p.replace(/_/g, " ");
      return `${label}: ${typeof val === "number" ? formatNumber(val, val % 1 === 0 ? 0 : 2) : val}`;
    })
    .filter(Boolean)
    .join(" · ");
}

function BestCard({
  label,
  entry,
  metric,
  metricLabel,
  metricColor,
  sweptParams,
}: {
  label: string;
  entry: BestEntry | null;
  metric: number;
  metricLabel: string;
  metricColor: string;
  sweptParams: string[];
}) {
  if (!entry) {
    return (
      <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
        <div className="text-xs font-medium text-text-secondary">{label}</div>
        <div className="mt-1 text-sm text-text-muted">No data</div>
      </div>
    );
  }

  const s = entry.summary;

  return (
    <div className="rounded-lg border border-border bg-bg-card px-4 py-3 transition-colors hover:bg-bg-card-hover">
      <div className="text-xs font-medium text-text-secondary">{label}</div>
      <div className="mt-1 font-mono text-xl font-semibold" style={{ color: metricColor }}>
        {metricLabel}
      </div>
      <div className="mt-1 text-[11px] text-text-muted">
        {getSweptValues(entry.config, sweptParams)}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-0.5 text-xs text-text-muted">
        <span>{s.total_trades} trades</span>
        <span>{formatPct(s.win_rate)} win</span>
        <span style={{ color: pnlColor(s.total_pnl_usd) }}>
          {formatCurrency(s.total_pnl_usd)}
        </span>
        <span>PF {formatNumber(s.profit_factor)}</span>
        {entry.config.risk_usd != null && (
          <span>Risk {formatCurrency(entry.config.risk_usd)}/trade</span>
        )}
      </div>
    </div>
  );
}

export function BestResults({ bestBySharpe, bestByPnl, bestByPf, sweptParams }: BestResultsProps) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      <BestCard
        label="Best by Sharpe"
        entry={bestBySharpe}
        metric={bestBySharpe?.summary.sharpe_ratio ?? 0}
        metricLabel={formatNumber(bestBySharpe?.summary.sharpe_ratio ?? 0, 3)}
        metricColor="var(--color-accent)"
        sweptParams={sweptParams}
      />
      <BestCard
        label="Best by P&L"
        entry={bestByPnl}
        metric={bestByPnl?.summary.total_pnl_usd ?? 0}
        metricLabel={formatCurrency(bestByPnl?.summary.total_pnl_usd ?? 0)}
        metricColor={pnlColor(bestByPnl?.summary.total_pnl_usd ?? 0)}
        sweptParams={sweptParams}
      />
      <BestCard
        label="Best by Profit Factor"
        entry={bestByPf}
        metric={bestByPf?.summary.profit_factor ?? 0}
        metricLabel={formatNumber(bestByPf?.summary.profit_factor ?? 0)}
        metricColor="var(--color-accent)"
        sweptParams={sweptParams}
      />
    </div>
  );
}
