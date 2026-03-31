import { useMemo, useState, useCallback } from "react";
import type { Trade } from "@/backtesting/lib/types";
import { formatCurrency } from "@/backtesting/lib/utils";
import { ScrollArea } from "@/shared/ui/scroll-area";
import { TradeChartModal } from "./TradeChartModal";

function formatR(r: number): string {
  const sign = r >= 0 ? "+" : "";
  return `${sign}${r.toFixed(2)}R`;
}

interface Filter {
  op: ">=" | "<=";
  value: string;
}

type Filters = Record<string, Filter>;

const FILTER_DEFS = [
  { key: "r", label: "R", unit: "R", step: 0.25, decimals: 2 },
  { key: "pnl", label: "P&L", unit: "$", step: 500, decimals: 0 },
  { key: "risk_pts", label: "Risk", unit: "pts", step: 1, decimals: 2 },
  { key: "gap", label: "Gap", unit: "pts", step: 1, decimals: 2 },
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

interface TradesTableProps {
  trades: Trade[];
  riskUsd: number;
  instrument: string;
}

const EXIT_LABELS: Record<string, string> = {
  tp1_tp2: "tp1+tp2",
  tp1_flat: "tp1+flat",
  tp1_be: "tp1+be",
  stop: "sl",
  flat: "flat",
  no_fill: "no fill",
};

type SortKey =
  | "date"
  | "session"
  | "direction"
  | "qty"
  | "entry_price"
  | "stop_price"
  | "risk_points"
  | "gap_size"
  | "exit_type"
  | "pnl_usd"
  | "r_multiple";

export function TradesTable({ trades, riskUsd, instrument }: TradesTableProps) {
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortAsc, setSortAsc] = useState(false);
  const [selectedTrade, setSelectedTrade] = useState<Trade | null>(null);
  const [chartOpen, setChartOpen] = useState(false);

  const handleTradeClick = useCallback((trade: Trade) => {
    setSelectedTrade(trade);
    setChartOpen(true);
  }, []);

  const [filters, setFilters] = useState<Filters>(() => {
    const init: Filters = {};
    for (const def of FILTER_DEFS) {
      init[def.key] = { op: ">=", value: "" };
    }
    return init;
  });

  const [sessionFilter, setSessionFilter] = useState<string>("all");
  const [sideFilter, setSideFilter] = useState<string>("all");
  const [exitFilter, setExitFilter] = useState<string>("all");

  const filled = useMemo(
    () => trades.filter((t) => t.exit_type !== "no_fill"),
    [trades],
  );

  const sessions = useMemo(
    () => [...new Set(filled.map((t) => t.session))].sort(),
    [filled],
  );

  const exitTypes = useMemo(
    () => [...new Set(filled.map((t) => t.exit_type))].sort(),
    [filled],
  );

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
    setSessionFilter("all");
    setSideFilter("all");
    setExitFilter("all");
  }, []);

  const getFilterValue = useCallback(
    (t: Trade, key: string): number => {
      switch (key) {
        case "r":
          return Number.isFinite(t.r_multiple) ? t.r_multiple : t.pnl_usd / riskUsd;
        case "pnl":
          return t.pnl_usd;
        case "risk_pts":
          return t.risk_points;
        case "gap":
          return t.gap_size;
        default:
          return 0;
      }
    },
    [riskUsd],
  );

  const activeFilterCount =
    Object.values(filters).filter((f) => f.value !== "").length +
    (sessionFilter !== "all" ? 1 : 0) +
    (sideFilter !== "all" ? 1 : 0) +
    (exitFilter !== "all" ? 1 : 0);

  const filtered = useMemo(() => {
    return filled.filter((t) => {
      // Numeric filters
      for (const def of FILTER_DEFS) {
        const f = filters[def.key];
        if (f.value === "") continue;
        const threshold = parseFloat(f.value);
        if (isNaN(threshold)) continue;
        const actual = getFilterValue(t, def.key);
        if (f.op === ">=" && actual < threshold) return false;
        if (f.op === "<=" && actual > threshold) return false;
      }
      // Categorical filters
      if (sessionFilter !== "all" && t.session !== sessionFilter) return false;
      if (sideFilter !== "all" && t.direction !== sideFilter) return false;
      if (exitFilter !== "all" && t.exit_type !== exitFilter) return false;
      return true;
    });
  }, [filled, filters, sessionFilter, sideFilter, exitFilter, getFilterValue]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      let va: number | string;
      let vb: number | string;

      switch (sortKey) {
        case "date":
          va = a.date;
          vb = b.date;
          return sortAsc
            ? va.localeCompare(vb)
            : vb.localeCompare(va);
        case "session":
          va = a.session;
          vb = b.session;
          return sortAsc
            ? va.localeCompare(vb)
            : vb.localeCompare(va);
        case "direction":
          va = a.direction;
          vb = b.direction;
          return sortAsc
            ? va.localeCompare(vb)
            : vb.localeCompare(va);
        case "exit_type":
          va = a.exit_type;
          vb = b.exit_type;
          return sortAsc
            ? va.localeCompare(vb)
            : vb.localeCompare(va);
        default:
          va = a[sortKey] as number;
          vb = b[sortKey] as number;
          return sortAsc ? (va as number) - (vb as number) : (vb as number) - (va as number);
      }
    });
    return arr;
  }, [filtered, sortKey, sortAsc]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const SortHeader = ({
    label,
    sortBy,
    align = "right",
  }: {
    label: string;
    sortBy: SortKey;
    align?: "left" | "right";
  }) => {
    const isActive = sortKey === sortBy;
    return (
      <th
        className={`whitespace-nowrap px-4 py-2 font-medium cursor-pointer select-none transition-colors hover:text-text-primary ${
          align === "right" ? "text-right" : "text-left"
        }`}
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

  if (!filled.length) {
    return (
      <div className="flex h-40 items-center justify-center text-text-muted">
        No trades to display
      </div>
    );
  }

  const isFiltered = activeFilterCount > 0;

  return (
    <div className="rounded-lg border border-border bg-bg-card">
      <div className="flex items-center justify-between px-4 pt-4 pb-2">
        <h2 className="text-sm font-medium text-text-secondary">Trades</h2>
        <span className="text-xs text-text-muted">
          {isFiltered ? (
            <>
              <span className="font-medium text-accent">{filtered.length}</span>
              <span className="text-text-muted"> / {filled.length}</span>
            </>
          ) : (
            <>{filled.length} filled</>
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
        <select
          value={sideFilter}
          onChange={(e) => setSideFilter(e.target.value)}
          className={`rounded-md border px-2 py-1.5 text-[11px] font-medium outline-none transition-colors ${
            sideFilter !== "all"
              ? "border-accent/40 bg-accent/5 text-accent"
              : "border-border bg-bg-secondary text-text-muted"
          }`}
        >
          <option value="all">All sides</option>
          <option value="long">Long</option>
          <option value="short">Short</option>
        </select>
        {sessions.length > 1 && (
          <select
            value={sessionFilter}
            onChange={(e) => setSessionFilter(e.target.value)}
            className={`rounded-md border px-2 py-1.5 text-[11px] font-medium outline-none transition-colors ${
              sessionFilter !== "all"
                ? "border-accent/40 bg-accent/5 text-accent"
                : "border-border bg-bg-secondary text-text-muted"
            }`}
          >
            <option value="all">All sessions</option>
            {sessions.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        )}
        <select
          value={exitFilter}
          onChange={(e) => setExitFilter(e.target.value)}
          className={`rounded-md border px-2 py-1.5 text-[11px] font-medium outline-none transition-colors ${
            exitFilter !== "all"
              ? "border-accent/40 bg-accent/5 text-accent"
              : "border-border bg-bg-secondary text-text-muted"
          }`}
        >
          <option value="all">All exits</option>
          {exitTypes.map((et) => (
            <option key={et} value={et}>{EXIT_LABELS[et] ?? et}</option>
          ))}
        </select>
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

      <ScrollArea className="h-[480px]">
        <div className="min-w-[860px]">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 z-10 bg-bg-card">
              <tr className="border-b border-border text-text-muted">
                <th className="whitespace-nowrap px-4 py-2 font-medium">#</th>
                <SortHeader label="Date" sortBy="date" align="left" />
                <SortHeader label="Session" sortBy="session" align="left" />
                <SortHeader label="Side" sortBy="direction" align="left" />
                <SortHeader label="Qty" sortBy="qty" />
                <SortHeader label="Entry" sortBy="entry_price" />
                <SortHeader label="Stop" sortBy="stop_price" />
                <SortHeader label="Risk (pts)" sortBy="risk_points" />
                <SortHeader label="Exit" sortBy="exit_type" align="left" />
                <SortHeader label="P&L" sortBy="pnl_usd" />
                <SortHeader label="R" sortBy="r_multiple" />
              </tr>
            </thead>
            <tbody>
              {sorted.length === 0 && (
                <tr>
                  <td
                    colSpan={11}
                    className="py-12 text-center text-xs text-text-muted"
                  >
                    No trades match the current filters
                  </td>
                </tr>
              )}
              {sorted.map((t, i) => {
                const isWin = t.pnl_usd > 0;
                const isLoss = t.pnl_usd < 0;
                const pnlColor = isWin
                  ? "var(--color-profit)"
                  : isLoss
                    ? "var(--color-loss)"
                    : "var(--color-text-muted)";

                return (
                  <tr
                    key={i}
                    className="border-b border-border/50 cursor-pointer transition-colors hover:bg-bg-card-hover"
                    onClick={() => handleTradeClick(t)}
                  >
                    <td className="whitespace-nowrap px-4 py-1.5 font-mono text-text-muted">
                      {i + 1}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-text-primary">{t.date}</td>
                    <td className="whitespace-nowrap px-4 py-1.5">
                      <span className="rounded bg-bg-secondary px-1.5 py-0.5 text-[10px] font-medium text-text-muted">
                        {t.session}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5">
                      <span
                        className="font-medium"
                        style={{
                          color:
                            t.direction === "long"
                              ? "var(--color-profit)"
                              : "var(--color-loss)",
                        }}
                      >
                        {t.direction === "long" ? "LONG" : "SHORT"}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-primary">
                      {t.qty}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-primary">
                      {t.entry_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-muted">
                      {t.stop_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-right font-mono text-text-muted">
                      {t.risk_points.toFixed(2)}
                    </td>
                    <td className="whitespace-nowrap px-4 py-1.5 text-text-secondary">
                      {EXIT_LABELS[t.exit_type] ?? t.exit_type}
                    </td>
                    <td
                      className="whitespace-nowrap px-4 py-1.5 text-right font-mono font-semibold"
                      style={{ color: pnlColor }}
                    >
                      {formatCurrency(t.pnl_usd)}
                    </td>
                    <td
                      className="whitespace-nowrap px-4 py-1.5 text-right font-mono"
                      style={{ color: pnlColor }}
                    >
                      {formatR(Number.isFinite(t.r_multiple) ? t.r_multiple : t.pnl_usd / riskUsd)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </ScrollArea>

      <TradeChartModal
        trade={selectedTrade}
        instrument={instrument}
        riskUsd={riskUsd}
        open={chartOpen}
        onOpenChange={setChartOpen}
      />
    </div>
  );
}
