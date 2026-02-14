import { useMemo, useState } from "react";
import type { BacktestConfig, BacktestSummary } from "../lib/types";
import { formatCurrency, formatNumber, formatPct, pnlColor } from "../lib/utils";
import { ScrollArea } from "./ui/scroll-area";

const R_VALUE = 50000;

type SortKey = string;

interface OptimizationTableProps {
  results: { config: BacktestConfig; summary: BacktestSummary }[];
  sweptParams: string[];
}

export function OptimizationTable({ results, sweptParams }: OptimizationTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("sharpe_ratio");
  const [sortAsc, setSortAsc] = useState(false);

  const sorted = useMemo(() => {
    const arr = [...results];
    arr.sort((a, b) => {
      let va: number;
      let vb: number;

      if (sweptParams.includes(sortKey)) {
        va = (a.config[sortKey] as number) ?? 0;
        vb = (b.config[sortKey] as number) ?? 0;
      } else {
        va = (a.summary[sortKey as keyof BacktestSummary] as number) ?? 0;
        vb = (b.summary[sortKey as keyof BacktestSummary] as number) ?? 0;
      }

      return sortAsc ? va - vb : vb - va;
    });
    return arr;
  }, [results, sweptParams, sortKey, sortAsc]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const SortHeader = ({ label, sortBy }: { label: string; sortBy: string }) => {
    const isActive = sortKey === sortBy;
    return (
      <th
        className="whitespace-nowrap px-3 py-2 font-medium text-right cursor-pointer select-none transition-colors hover:text-text-primary"
        onClick={() => handleSort(sortBy)}
      >
        <span className={isActive ? "text-accent" : ""}>
          {label}
          {isActive && (
            <span className="ml-0.5">{sortAsc ? "\u25B2" : "\u25BC"}</span>
          )}
        </span>
      </th>
    );
  };

  if (!results.length) return null;

  return (
    <div className="rounded-lg border border-border bg-bg-card">
      <div className="flex items-center justify-between px-4 pt-4 pb-3">
        <h2 className="text-sm font-medium text-text-secondary">All Results</h2>
        <span className="text-xs text-text-muted">{results.length} combinations</span>
      </div>

      <ScrollArea className="h-[420px]">
        <div className="min-w-[700px]">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-bg-card">
              <tr className="border-b border-border text-text-muted">
                <th className="whitespace-nowrap px-3 py-2 font-medium">#</th>
                {sweptParams.map((p) => (
                  <SortHeader key={p} label={p.replace(/_/g, " ")} sortBy={p} />
                ))}
                <SortHeader label="Trades" sortBy="total_trades" />
                <SortHeader label="Win Rate" sortBy="win_rate" />
                <SortHeader label="Net R" sortBy="total_pnl_usd" />
                <SortHeader label="Sharpe" sortBy="sharpe_ratio" />
                <SortHeader label="PF" sortBy="profit_factor" />
                <SortHeader label="Max DD (R)" sortBy="max_drawdown_usd" />
                <SortHeader label="Avg R" sortBy="avg_r" />
              </tr>
            </thead>
            <tbody>
              {sorted.map((r, i) => {
                const s = r.summary;
                const netR = s.total_pnl_usd / R_VALUE;
                const ddR = s.max_drawdown_usd / R_VALUE;

                return (
                  <tr
                    key={i}
                    className="border-b border-border/50 transition-colors hover:bg-bg-card-hover"
                  >
                    <td className="whitespace-nowrap px-3 py-1.5 font-mono text-text-muted">
                      {i + 1}
                    </td>
                    {sweptParams.map((p) => (
                      <td
                        key={p}
                        className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary"
                      >
                        {formatNumber((r.config[p] as number) ?? 0, 2)}
                      </td>
                    ))}
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {s.total_trades}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatPct(s.win_rate)}
                    </td>
                    <td
                      className="whitespace-nowrap px-3 py-1.5 text-right font-mono font-semibold"
                      style={{ color: pnlColor(netR) }}
                    >
                      {netR >= 0 ? "+" : ""}{netR.toFixed(2)}R
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.sharpe_ratio, 3)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.profit_factor)}
                    </td>
                    <td
                      className="whitespace-nowrap px-3 py-1.5 text-right font-mono"
                      style={{ color: "var(--color-loss)" }}
                    >
                      {ddR >= 0 ? "+" : ""}{ddR.toFixed(2)}R
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.avg_r, 3)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ScrollArea>
    </div>
  );
}
