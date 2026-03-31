import type { BacktestConfig, BacktestSummary } from "@/backtesting/lib/types";
import { formatNumber, formatPct, pnlColor } from "@/backtesting/lib/utils";

interface BestEntry {
  config: BacktestConfig;
  summary: BacktestSummary;
}

interface BestResultsProps {
  bestBySharpe: BestEntry | null;
  bestByPnl: BestEntry | null;
  bestByPf: BestEntry | null;
  bestByCalmar: BestEntry | null;
  sweptParams: string[];
}

function formatR(r: number): string {
  const sign = r >= 0 ? "+" : "";
  return `${sign}${r.toFixed(2)}R`;
}

function getRiskUsd(entry: BestEntry): number {
  return entry.config.risk_usd ?? 5000;
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
  metricLabel,
  metricColor,
  sweptParams,
}: {
  label: string;
  entry: BestEntry | null;
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
  const riskUsd = getRiskUsd(entry);
  const netR = s.total_pnl_usd / riskUsd;

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
        <span style={{ color: pnlColor(netR) }}>
          {formatR(netR)}
        </span>
        <span>PF {formatNumber(s.profit_factor)}</span>
      </div>
    </div>
  );
}

export function BestResults({ bestBySharpe, bestByPnl, bestByPf, bestByCalmar, sweptParams }: BestResultsProps) {
  const pnlRiskUsd = bestByPnl ? getRiskUsd(bestByPnl) : 5000;
  const pnlNetR = (bestByPnl?.summary.total_pnl_usd ?? 0) / pnlRiskUsd;

  return (
    <div className="grid gap-3 sm:grid-cols-4">
      <BestCard
        label="Best by Sharpe"
        entry={bestBySharpe}
        metricLabel={formatNumber(bestBySharpe?.summary.sharpe_ratio ?? 0, 3)}
        metricColor="var(--color-accent)"
        sweptParams={sweptParams}
      />
      <BestCard
        label="Best by R"
        entry={bestByPnl}
        metricLabel={formatR(pnlNetR)}
        metricColor={pnlColor(pnlNetR)}
        sweptParams={sweptParams}
      />
      <BestCard
        label="Best by Profit Factor"
        entry={bestByPf}
        metricLabel={formatNumber(bestByPf?.summary.profit_factor ?? 0)}
        metricColor="var(--color-accent)"
        sweptParams={sweptParams}
      />
      <BestCard
        label="Best by Calmar"
        entry={bestByCalmar}
        metricLabel={formatNumber(bestByCalmar?.summary.calmar_ratio ?? 0, 3)}
        metricColor="var(--color-accent)"
        sweptParams={sweptParams}
      />
    </div>
  );
}
