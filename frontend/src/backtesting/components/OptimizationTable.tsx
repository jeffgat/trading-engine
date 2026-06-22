import { useMemo, useState, useCallback } from "react";
import type { BacktestConfig, BacktestSummary } from "@/backtesting/lib/types";
import { formatNumber, formatPct, moneyColor } from "@/backtesting/lib/utils";
import { ScrollArea } from "@/shared/ui/scroll-area";

type SortKey = string;

interface Filter {
  op: ">=" | "<=";
  value: string;
}

type Filters = Record<string, Filter>;

const FILTER_DEFS = [
  { key: "win_rate", label: "Win Rate", unit: "%", step: 0.5, decimals: 2, scale: 100 },
  { key: "net_r", label: "Net R", unit: "R", step: 1, decimals: 2, scale: 1 },
  { key: "profit_factor", label: "PF", unit: "", step: 0.05, decimals: 2, scale: 1 },
  { key: "max_dd_r", label: "Max DD", unit: "R", step: 0.5, decimals: 2, scale: 1 },
  { key: "calmar_ratio", label: "Calmar", unit: "", step: 0.1, decimals: 2, scale: 1 },
] as const;

function FilterInput({
  label,
  unit,
  step,
  filter,
  onChange,
  onClear,
}: {
  label: string;
  unit: string;
  step: number;
  filter: Filter;
  onChange: (f: Filter) => void;
  onClear: () => void;
}) {
  const hasValue = filter.value !== "";
  return (
    <div
      className={`flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 transition-colors ${
        hasValue
          ? "border-accent/40 bg-accent/5"
          : "border-border bg-bg-secondary"
      }`}
    >
      <span className="text-[11px] font-medium text-text-muted whitespace-nowrap">
        {label}
      </span>
      <button
        type="button"
        onClick={() =>
          onChange({ ...filter, op: filter.op === ">=" ? "<=" : ">=" })
        }
        className="rounded px-1 py-0.5 font-mono text-[11px] font-semibold text-accent transition-colors hover:bg-accent/10"
      >
        {filter.op === ">=" ? "\u2265" : "\u2264"}
      </button>
      <input
        type="number"
        step={step}
        value={filter.value}
        onChange={(e) => onChange({ ...filter, value: e.target.value })}
        placeholder="—"
        className="w-16 bg-transparent font-mono text-xs text-text-primary outline-none placeholder:text-text-muted/50 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
      />
      {unit && (
        <span className="text-[10px] text-text-muted">{unit}</span>
      )}
      {hasValue && (
        <button
          type="button"
          onClick={onClear}
          className="ml-0.5 rounded p-0.5 text-text-muted transition-colors hover:bg-bg-card-hover hover:text-text-primary"
        >
          <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
            <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
          </svg>
        </button>
      )}
    </div>
  );
}

interface OptimizationTableProps {
  results: { config: BacktestConfig; summary: BacktestSummary }[];
  sweptParams: string[];
}

export function OptimizationTable({ results, sweptParams }: OptimizationTableProps) {
  const riskUsd = results[0]?.config.risk_usd ?? 5000;
  const [sortKey, setSortKey] = useState<SortKey>("total_pnl_usd");
  const [sortAsc, setSortAsc] = useState(false);

  const [filters, setFilters] = useState<Filters>(() => {
    const init: Filters = {};
    for (const def of FILTER_DEFS) {
      init[def.key] = { op: ">=", value: "" };
    }
    return init;
  });

  const updateFilter = useCallback((key: string, f: Filter) => {
    setFilters((prev) => ({ ...prev, [key]: f }));
  }, []);

  const clearFilter = useCallback((key: string) => {
    setFilters((prev) => ({ ...prev, [key]: { ...prev[key], value: "" } }));
  }, []);

  const clearAllFilters = useCallback(() => {
    setFilters((prev) => {
      const next: Filters = {};
      for (const key of Object.keys(prev)) {
        next[key] = { ...prev[key], value: "" };
      }
      return next;
    });
  }, []);

  const activeFilterCount = Object.values(filters).filter(
    (f) => f.value !== ""
  ).length;

  /** Extract the raw number for a filter key from a result row. */
  const getFilterValue = useCallback(
    (r: { config: BacktestConfig; summary: BacktestSummary }, key: string): number => {
      switch (key) {
        case "win_rate":
          return r.summary.win_rate * 100;
        case "net_r":
          return r.summary.total_pnl_usd / riskUsd;
        case "profit_factor":
          return r.summary.profit_factor;
        case "max_dd_r":
          return r.summary.max_drawdown_usd / riskUsd;
        case "calmar_ratio":
          return r.summary.calmar_ratio ?? 0;
        default:
          return 0;
      }
    },
    [riskUsd]
  );

  const filtered = useMemo(() => {
    return results.filter((r) => {
      for (const def of FILTER_DEFS) {
        const f = filters[def.key];
        if (f.value === "") continue;
        const threshold = parseFloat(f.value);
        if (isNaN(threshold)) continue;
        const actual = getFilterValue(r, def.key);
        if (f.op === ">=" && actual < threshold) return false;
        if (f.op === "<=" && actual > threshold) return false;
      }
      return true;
    });
  }, [results, filters, getFilterValue]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
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
  }, [filtered, sweptParams, sortKey, sortAsc]);

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

  const isFiltered = activeFilterCount > 0;

  return (
    <div className="rounded-lg border border-border bg-bg-card">
      {/* Header */}
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h2 className="text-sm font-medium text-text-secondary">All Results</h2>
        <span className="text-xs text-text-muted">
          {isFiltered ? (
            <>
              <span className="font-medium text-accent">{filtered.length}</span>
              <span className="text-text-muted"> / {results.length}</span>
            </>
          ) : (
            <>{results.length} combinations</>
          )}
        </span>
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3">
        {FILTER_DEFS.map((def) => (
          <FilterInput
            key={def.key}
            label={def.label}
            unit={def.unit}
            step={def.step}
            filter={filters[def.key]}
            onChange={(f) => updateFilter(def.key, f)}
            onClear={() => clearFilter(def.key)}
          />
        ))}
        {isFiltered && (
          <button
            type="button"
            onClick={clearAllFilters}
            className="rounded-md px-2 py-1.5 text-[11px] font-medium text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary"
          >
            Clear all
          </button>
        )}
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
                <SortHeader label="Calmar" sortBy="calmar_ratio" />
                <SortHeader label="PF" sortBy="profit_factor" />
                <SortHeader label="Max DD (R)" sortBy="max_drawdown_usd" />
                <SortHeader label="Avg R" sortBy="avg_r" />
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={sweptParams.length + 9}
                    className="py-12 text-center text-xs text-text-muted"
                  >
                    No results match the current filters
                  </td>
                </tr>
              )}
              {sorted.map((r, i) => {
                const s = r.summary;
                const netR = s.total_pnl_usd / riskUsd;
                const ddR = s.max_drawdown_usd / riskUsd;

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
                      style={{ color: moneyColor(netR) }}
                    >
                      {netR >= 0 ? "+" : ""}{netR.toFixed(2)}R
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.sharpe_ratio, 3)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.calmar_ratio ?? 0, 3)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono text-text-primary">
                      {formatNumber(s.profit_factor)}
                    </td>
                    <td
                      className="whitespace-nowrap px-3 py-1.5 text-right font-mono"
                      style={{ color: moneyColor(ddR) }}
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
