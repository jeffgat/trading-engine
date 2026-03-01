import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { BacktestHistoryItem, BacktestResult, Trade } from "@/backtesting/lib/types";
import { formatR, pnlColor } from "@/backtesting/lib/utils";
import { SessionTag } from "./SessionTag";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SelectedStrategy {
  id: string;
  meta: BacktestHistoryItem;
  data: BacktestResult | null;
  riskSize: number;
  loading: boolean;
  error: boolean;
  hidden: boolean;
}

interface SavedLayout {
  name: string;
  accountRisk: number;
  strategies: { id: string; riskSize: number }[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function computeRByYear(trades: Trade[]): Record<string, number> {
  const result: Record<string, number> = {};
  for (const t of trades) {
    if (t.exit_type === "no_fill") continue;
    const year = t.date.slice(0, 4);
    result[year] = (result[year] || 0) + t.r_multiple;
  }
  return result;
}

function computeRByMonth(trades: Trade[]): Record<string, number> {
  const result: Record<string, number> = {};
  for (const t of trades) {
    if (t.exit_type === "no_fill") continue;
    const key = t.date.slice(0, 7); // "YYYY-MM"
    result[key] = (result[key] || 0) + t.r_multiple;
  }
  return result;
}

function computeMaxDrawdownByMonth(trades: Trade[]): Record<string, number> {
  const filtered = trades
    .filter((t) => t.exit_type !== "no_fill")
    .sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  const result: Record<string, number> = {};
  let cumR = 0;
  let peak = 0;

  for (const t of filtered) {
    const key = t.date.slice(0, 7); // "YYYY-MM"
    cumR += t.r_multiple;
    if (cumR > peak) peak = cumR;
    const dd = peak - cumR; // always >= 0
    if (dd > (result[key] ?? 0)) {
      result[key] = dd;
    }
  }
  return result;
}

function computeCombinedMaxDrawdownByMonth(
  strategies: { trades: Trade[]; scale: number }[]
): Record<string, number> {
  // Merge all trades, pre-scaling each by its strategy's scale factor
  const merged: { date: string; scaledR: number }[] = [];
  for (const s of strategies) {
    for (const t of s.trades) {
      if (t.exit_type === "no_fill") continue;
      merged.push({ date: t.date, scaledR: t.r_multiple * s.scale });
    }
  }
  merged.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  const result: Record<string, number> = {};
  let cumR = 0;
  let peak = 0;

  for (const t of merged) {
    const key = t.date.slice(0, 7);
    cumR += t.scaledR;
    if (cumR > peak) peak = cumR;
    const dd = peak - cumR;
    if (dd > (result[key] ?? 0)) {
      result[key] = dd;
    }
  }
  return result;
}

function interpolateColor(t: number): string {
  if (t <= 0.5) {
    const s = t / 0.5;
    const r = Math.round(180 + (60 - 180) * s);
    const g = Math.round(50 + (60 - 50) * s);
    const b = Math.round(50 + (65 - 50) * s);
    return `rgb(${r},${g},${b})`;
  }
  const s = (t - 0.5) / 0.5;
  const r = Math.round(60 + (45 - 60) * s);
  const g = Math.round(60 + (190 - 60) * s);
  const b = Math.round(65 + (110 - 65) * s);
  return `rgb(${r},${g},${b})`;
}

function getYearRangeFromTrades(tradeSets: Trade[][]): string[] {
  let minYear = 9999;
  let maxYear = 0;
  for (const trades of tradeSets) {
    for (const t of trades) {
      if (t.exit_type === "no_fill") continue;
      const y = parseInt(t.date.slice(0, 4), 10);
      if (y < minYear) minYear = y;
      if (y > maxYear) maxYear = y;
    }
  }
  if (minYear > maxYear) return [];
  const years: string[] = [];
  for (let y = minYear; y <= maxYear; y++) {
    years.push(String(y));
  }
  return years;
}

function getMonthRangeFromTrades(tradeSets: Trade[][]): { years: string[]; firstKey: string; lastKey: string } {
  let firstKey = "9999-12";
  let lastKey = "0000-01";
  for (const trades of tradeSets) {
    for (const t of trades) {
      if (t.exit_type === "no_fill") continue;
      const key = t.date.slice(0, 7);
      if (key < firstKey) firstKey = key;
      if (key > lastKey) lastKey = key;
    }
  }
  if (firstKey > lastKey) return { years: [], firstKey: "", lastKey: "" };

  const startYear = parseInt(firstKey.slice(0, 4), 10);
  const endYear = parseInt(lastKey.slice(0, 4), 10);
  const years: string[] = [];
  for (let y = endYear; y >= startYear; y--) {
    years.push(String(y));
  }
  return { years, firstKey, lastKey };
}

function formatDateRange(start: string, end: string): string {
  if (!start || !end) return "";
  const fmt = (d: string) => {
    const [y, m] = d.split("-");
    const dt = new Date(+y, +m - 1);
    return dt.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
  };
  return `${fmt(start)}\u2013${fmt(end)}`;
}

function displayName(item: BacktestHistoryItem): string {
  return item.name || `${item.instrument} ${item.id.slice(0, 8)}`;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function RByYearRow({
  rByYear,
  years,
  scale,
}: {
  rByYear: Record<string, number>;
  years: string[];
  scale: number;
}) {
  return (
    <div className="mt-3">
      <div className="mb-1 text-[10px] font-medium text-text-muted font-display">R / Year</div>
      <div className="flex flex-wrap gap-2">
        {years.map((year) => {
          const raw = rByYear[year] ?? 0;
          const scaled = raw * scale;
          return (
            <div key={year} className="flex flex-col items-center">
              <span className="text-[10px] text-text-muted">{year}</span>
              <span
                className="font-mono text-xs"
                style={{ color: pnlColor(scaled) }}
              >
                {formatR(scaled)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function MonthlyHeatmap({
  dataByMonth,
  monthRange,
  scale,
  mode,
}: {
  dataByMonth: Record<string, number>;
  monthRange: { years: string[]; firstKey: string; lastKey: string };
  scale: number;
  mode: "net-r" | "max-dd";
}) {
  const { years, firstKey, lastKey } = monthRange;

  if (years.length === 0) return null;

  const label = mode === "net-r" ? "Monthly Net R" : "Monthly Max DD";

  return (
    <div className="mt-3">
      <div className="mb-1 text-[10px] font-medium text-text-muted font-display">{label}</div>
      <div
        className="grid gap-px"
        style={{ gridTemplateColumns: `auto repeat(12, 1fr)` }}
      >
        {/* Column headers */}
        <div />
        {MONTHS.map((m) => (
          <div
            key={m}
            className="text-center text-[10px] text-text-muted pb-0.5"
          >
            {m}
          </div>
        ))}

        {/* Rows (newest year first) */}
        {years.map((year) => (
          <MonthlyHeatmapRow
            key={year}
            year={year}
            dataByMonth={dataByMonth}
            firstKey={firstKey}
            lastKey={lastKey}
            scale={scale}
            mode={mode}
          />
        ))}
      </div>
    </div>
  );
}

function MonthlyHeatmapRow({
  year,
  dataByMonth,
  firstKey,
  lastKey,
  scale,
  mode,
}: {
  year: string;
  dataByMonth: Record<string, number>;
  firstKey: string;
  lastKey: string;
  scale: number;
  mode: "net-r" | "max-dd";
}) {
  return (
    <>
      <div className="flex items-center text-[10px] text-text-muted pr-1.5">
        {year}
      </div>
      {Array.from({ length: 12 }, (_, mi) => {
        const key = `${year}-${String(mi + 1).padStart(2, "0")}`;
        const outOfRange = key < firstKey || key > lastKey;

        if (outOfRange) {
          return (
            <div
              key={key}
              className="flex items-center justify-center rounded-sm py-1 text-[10px] font-mono text-text-muted"
              style={{ backgroundColor: "var(--color-bg-secondary)" }}
            >
              &mdash;
            </div>
          );
        }

        const raw = dataByMonth[key] ?? 0;
        const scaled = raw * scale;

        // Net R: fixed scale — full green at +10R, full red at -10R, neutral at 0
        // Max DD: ≤10R=green, >10R steep gradient to red, full red at 12R
        const R_SCALE = 10;
        const DD_GREEN_FLOOR = 8;
        const DD_RED_CEILING = 9;
        const t = mode === "net-r"
          ? Math.max(0, Math.min(1, (scaled / R_SCALE + 1) / 2))
          : scaled <= DD_GREEN_FLOOR ? 1
          : 1 - Math.min((scaled - DD_GREEN_FLOOR) / (DD_RED_CEILING - DD_GREEN_FLOOR), 1);

        const display = mode === "net-r"
          ? `${scaled >= 0 ? "+" : ""}${scaled.toFixed(1)}`
          : scaled.toFixed(1) === "0.0" ? "0.0" : `-${scaled.toFixed(1)}`;

        return (
          <div
            key={key}
            className="flex items-center justify-center rounded-sm py-1"
            style={{ backgroundColor: interpolateColor(t) }}
          >
            <span className="font-mono text-[10px] text-white/90">
              {display}
            </span>
          </div>
        );
      })}
    </>
  );
}

// ---------------------------------------------------------------------------
// Strategy Card
// ---------------------------------------------------------------------------

function StrategyCard({
  strategy,
  accountRisk,
  onRiskChange,
  onRemove,
}: {
  strategy: SelectedStrategy;
  accountRisk: number;
  onRiskChange: (riskSize: number) => void;
  onRemove: () => void;
}) {
  const { meta, data, riskSize, loading, error } = strategy;
  const scale = riskSize / Math.max(accountRisk, 1);

  const rByYear = useMemo(() => {
    if (!data) return {};
    return computeRByYear(data.trades);
  }, [data]);

  const rByMonth = useMemo(() => {
    if (!data) return {};
    return computeRByMonth(data.trades);
  }, [data]);

  const ddByMonth = useMemo(() => {
    if (!data) return {};
    return computeMaxDrawdownByMonth(data.trades);
  }, [data]);

  const years = useMemo(() => {
    if (!data) return [];
    return getYearRangeFromTrades([data.trades]);
  }, [data]);

  const monthRange = useMemo(() => {
    if (!data) return { years: [], firstKey: "", lastKey: "" };
    return getMonthRangeFromTrades([data.trades]);
  }, [data]);

  const filledTrades = useMemo(() => {
    if (!data) return 0;
    return data.trades.filter((t) => t.exit_type !== "no_fill").length;
  }, [data]);

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span
          className="max-w-[280px] truncate text-sm font-medium text-text-primary font-display"
          title={displayName(meta)}
        >
          {displayName(meta)}
        </span>
        <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-accent">
          {meta.instrument}
        </span>
        {meta.sessions.map((s) => (
          <SessionTag key={s} session={s} />
        ))}
        <div className="ml-auto flex items-center gap-2">
          <label className="text-[10px] text-text-muted font-display">Risk ($)</label>
          <input
            type="number"
            value={riskSize}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (!isNaN(v)) onRiskChange(v);
            }}
            onBlur={() => {
              if (riskSize < 1) onRiskChange(1);
            }}
            className="w-24 rounded border border-border bg-bg-secondary px-2 py-1 text-xs font-mono text-text-primary outline-none focus:border-accent"
          />
          <button
            onClick={onRemove}
            className="rounded p-1 text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary"
            title="Remove strategy"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
              <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
            </svg>
          </button>
        </div>
      </div>

      {/* Loading state */}
      {loading && (
        <div className="mt-3 animate-pulse space-y-3">
          <div className="h-4 w-48 rounded bg-bg-secondary" />
          <div className="h-20 rounded bg-bg-secondary" />
        </div>
      )}

      {/* Error state */}
      {!loading && error && !data && (
        <p className="mt-3 text-xs" style={{ color: "var(--color-loss)" }}>Failed to load strategy data</p>
      )}

      {/* No trades state */}
      {!loading && data && filledTrades === 0 && (
        <p className="mt-3 text-xs text-text-muted">No filled trades</p>
      )}

      {/* Data loaded */}
      {!loading && data && filledTrades > 0 && (
        <>
          <RByYearRow rByYear={rByYear} years={years} scale={scale} />
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
            <MonthlyHeatmap dataByMonth={rByMonth} monthRange={monthRange} scale={scale} mode="net-r" />
            <MonthlyHeatmap dataByMonth={ddByMonth} monthRange={monthRange} scale={scale} mode="max-dd" />
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Portfolio Summary Card
// ---------------------------------------------------------------------------

function PortfolioSummaryCard({
  strategies,
  accountRisk,
}: {
  strategies: SelectedStrategy[];
  accountRisk: number;
}) {
  const loaded = useMemo(
    () => strategies.filter((s) => s.data !== null),
    [strategies]
  );

  // Aggregate R by year (scale already applied — pass scale=1 to renderers)
  const aggregatedRByYear = useMemo(() => {
    const result: Record<string, number> = {};
    for (const s of loaded) {
      if (!s.data) continue;
      const scale = s.riskSize / Math.max(accountRisk, 1);
      const rByYear = computeRByYear(s.data.trades);
      for (const [year, val] of Object.entries(rByYear)) {
        result[year] = (result[year] || 0) + val * scale;
      }
    }
    return result;
  }, [loaded, accountRisk]);

  // Aggregate R by month (scale already applied — pass scale=1 to renderers)
  const aggregatedRByMonth = useMemo(() => {
    const result: Record<string, number> = {};
    for (const s of loaded) {
      if (!s.data) continue;
      const scale = s.riskSize / Math.max(accountRisk, 1);
      const rByMonth = computeRByMonth(s.data.trades);
      for (const [key, val] of Object.entries(rByMonth)) {
        result[key] = (result[key] || 0) + val * scale;
      }
    }
    return result;
  }, [loaded, accountRisk]);

  // Combined max drawdown by month (scale already applied — pass scale=1 to renderers)
  const combinedDDByMonth = useMemo(() => {
    const strats = loaded
      .filter((s) => s.data !== null)
      .map((s) => ({
        trades: s.data!.trades,
        scale: s.riskSize / Math.max(accountRisk, 1),
      }));
    return computeCombinedMaxDrawdownByMonth(strats);
  }, [loaded, accountRisk]);

  const tradeSets = useMemo(() => loaded.map((s) => s.data!.trades), [loaded]);
  const years = useMemo(() => getYearRangeFromTrades(tradeSets), [tradeSets]);
  const monthRange = useMemo(() => getMonthRangeFromTrades(tradeSets), [tradeSets]);

  if (loaded.length < 2) return null;

  return (
    <div className="rounded-lg border border-accent/30 bg-bg-card p-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-text-primary font-display">
          Portfolio Summary
        </span>
        <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-accent">
          {loaded.length} strategies
        </span>
      </div>

      {years.length > 0 && (
        <RByYearRow rByYear={aggregatedRByYear} years={years} scale={1} />
      )}
      {monthRange.years.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <MonthlyHeatmap dataByMonth={aggregatedRByMonth} monthRange={monthRange} scale={1} mode="net-r" />
          <MonthlyHeatmap dataByMonth={combinedDDByMonth} monthRange={monthRange} scale={1} mode="max-dd" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Combined Card (for combined view mode)
// ---------------------------------------------------------------------------

function CombinedCard({
  strategies,
  accountRisk,
  onRiskChange,
  onRemove,
  onToggleHide,
}: {
  strategies: SelectedStrategy[];
  accountRisk: number;
  onRiskChange: (id: string, riskSize: number) => void;
  onRemove: (id: string) => void;
  onToggleHide: (id: string) => void;
}) {
  const loaded = useMemo(
    () => strategies.filter((s) => s.data !== null && !s.hidden),
    [strategies]
  );

  // Aggregate R by year (pre-scaled — pass scale=1 to renderer)
  const aggregatedRByYear = useMemo(() => {
    const result: Record<string, number> = {};
    for (const s of loaded) {
      if (!s.data) continue;
      const scale = s.riskSize / Math.max(accountRisk, 1);
      const rByYear = computeRByYear(s.data.trades);
      for (const [year, val] of Object.entries(rByYear)) {
        result[year] = (result[year] || 0) + val * scale;
      }
    }
    return result;
  }, [loaded, accountRisk]);

  // Aggregate R by month (pre-scaled — pass scale=1 to renderer)
  const aggregatedRByMonth = useMemo(() => {
    const result: Record<string, number> = {};
    for (const s of loaded) {
      if (!s.data) continue;
      const scale = s.riskSize / Math.max(accountRisk, 1);
      const rByMonth = computeRByMonth(s.data.trades);
      for (const [key, val] of Object.entries(rByMonth)) {
        result[key] = (result[key] || 0) + val * scale;
      }
    }
    return result;
  }, [loaded, accountRisk]);

  // Combined max drawdown by month (pre-scaled — pass scale=1 to renderer)
  const combinedDDByMonth = useMemo(() => {
    const strats = loaded
      .filter((s) => s.data !== null)
      .map((s) => ({
        trades: s.data!.trades,
        scale: s.riskSize / Math.max(accountRisk, 1),
      }));
    return computeCombinedMaxDrawdownByMonth(strats);
  }, [loaded, accountRisk]);

  const tradeSets = useMemo(() => loaded.map((s) => s.data!.trades), [loaded]);
  const years = useMemo(() => getYearRangeFromTrades(tradeSets), [tradeSets]);
  const monthRange = useMemo(() => getMonthRangeFromTrades(tradeSets), [tradeSets]);

  return (
    <div className="rounded-lg border border-accent/30 bg-bg-card p-4">
      {/* Header */}
      <div className="flex items-center gap-2 mb-3">
        <span className="text-sm font-medium text-text-primary font-display">
          Combined Portfolio
        </span>
        <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-accent">
          {strategies.some((s) => s.hidden)
            ? `${strategies.filter((s) => !s.hidden).length}/${strategies.length} strategies`
            : `${strategies.length} strateg${strategies.length === 1 ? "y" : "ies"}`}
        </span>
      </div>

      {/* Strategy list */}
      <div className="space-y-1 mb-3">
        {strategies.map((s) => {
          // Compute per-strategy stats
          const filled = s.data?.trades.filter((t) => t.exit_type !== "no_fill") ?? [];
          const totalR = filled.reduce((sum, t) => sum + t.r_multiple, 0);
          const dateSet = new Set(filled.map((t) => t.date.slice(0, 4)));
          const numYears = Math.max(dateSet.size, 1);
          const rPerYear = totalR / numYears;
          const wins = filled.filter((t) => t.r_multiple > 0).length;
          const winPct = filled.length > 0 ? (wins / filled.length) * 100 : 0;
          // Max DD: peak-to-trough across all trades
          let cumR = 0, peak = 0, maxDD = 0;
          for (const t of filled.sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : 0)) {
            cumR += t.r_multiple;
            if (cumR > peak) peak = cumR;
            const dd = peak - cumR;
            if (dd > maxDD) maxDD = dd;
          }

          return (
            <div
              key={s.id}
              className={`flex items-center gap-2 rounded border px-3 py-1.5 transition-opacity ${s.hidden ? "border-border/50 bg-bg-secondary/50 opacity-40" : "border-border bg-bg-secondary"}`}
            >
              <span
                className="min-w-0 flex-1 truncate text-xs text-text-primary"
                title={displayName(s.meta)}
              >
                {displayName(s.meta)}
              </span>
              {/* Per-strategy stats */}
              {s.data && filled.length > 0 && (
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className="text-[10px] font-mono" style={{ color: pnlColor(rPerYear) }}>
                    {rPerYear >= 0 ? "+" : ""}{rPerYear.toFixed(1)}R/yr
                  </span>
                  <span className="text-[10px] font-mono text-text-muted">
                    {filled.length}
                  </span>
                  <span className="text-[10px] font-mono text-text-muted">
                    {winPct.toFixed(0)}%
                  </span>
                  <span className="text-[10px] font-mono" style={{ color: maxDD > 10 ? "var(--color-loss)" : "var(--color-text-muted)" }}>
                    -{maxDD.toFixed(1)}R
                  </span>
                </div>
              )}
              <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-accent flex-shrink-0">
                {s.meta.instrument}
              </span>
              {s.meta.sessions.map((sess) => (
                <SessionTag key={sess} session={sess} />
              ))}
              <label className="text-[10px] text-text-muted font-display flex-shrink-0">Risk ($)</label>
              <input
                type="number"
                value={s.riskSize}
                onChange={(e) => {
                  const v = parseFloat(e.target.value);
                  if (!isNaN(v)) onRiskChange(s.id, v);
                }}
                onBlur={() => {
                  if (s.riskSize < 1) onRiskChange(s.id, 1);
                }}
                className="w-20 rounded border border-border bg-bg-primary px-2 py-0.5 text-xs font-mono text-text-primary outline-none focus:border-accent flex-shrink-0"
              />
              <button
                onClick={() => onToggleHide(s.id)}
                className="rounded p-1 text-text-muted transition-colors hover:bg-bg-primary hover:text-text-primary flex-shrink-0"
                title={s.hidden ? "Show strategy" : "Hide strategy"}
              >
                {s.hidden ? (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
                    <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
                    <line x1="1" y1="1" x2="23" y2="23" />
                  </svg>
                ) : (
                  <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
                    <circle cx="12" cy="12" r="3" />
                  </svg>
                )}
              </button>
              <button
                onClick={() => onRemove(s.id)}
                className="rounded p-1 text-text-muted transition-colors hover:bg-bg-primary hover:text-text-primary flex-shrink-0"
                title="Remove strategy"
              >
                <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                </svg>
              </button>
              {s.loading && (
                <span className="text-[10px] text-text-muted flex-shrink-0">Loading...</span>
              )}
              {!s.loading && s.error && !s.data && (
                <span className="text-[10px] flex-shrink-0" style={{ color: "var(--color-loss)" }}>Error</span>
              )}
            </div>
          );
        })}
      </div>

      {/* Aggregated data */}
      {loaded.length > 0 && years.length > 0 && (
        <RByYearRow rByYear={aggregatedRByYear} years={years} scale={1} />
      )}
      {loaded.length > 0 && monthRange.years.length > 0 && (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <MonthlyHeatmap dataByMonth={aggregatedRByMonth} monthRange={monthRange} scale={1} mode="net-r" />
          <MonthlyHeatmap dataByMonth={combinedDDByMonth} monthRange={monthRange} scale={1} mode="max-dd" />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RiskEngineDashboard() {
  const [accountRisk, setAccountRisk] = useState(() => {
    const stored = localStorage.getItem("risk-engine-account-risk");
    const parsed = parseFloat(stored ?? "");
    return !isNaN(parsed) ? parsed : 100_000;
  });
  useEffect(() => {
    localStorage.setItem("risk-engine-account-risk", String(accountRisk));
  }, [accountRisk]);

  const [viewMode, setViewMode] = useState<"individual" | "combined">("individual");
  const [saveFlash, setSaveFlash] = useState(false);
  const [strategyList, setStrategyList] = useState<BacktestHistoryItem[]>([]);
  const [listLoading, setListLoading] = useState(true);
  const [selectedStrategies, setSelectedStrategies] = useState<SelectedStrategy[]>([]);
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [filterStarred, setFilterStarred] = useState(false);
  const [filterAsset, setFilterAsset] = useState<string | null>(null);
  const [filterSession, setFilterSession] = useState<string | null>(null);

  const [savedLayouts, setSavedLayouts] = useState<SavedLayout[]>(() => {
    try {
      const stored = localStorage.getItem("risk-engine-layouts");
      return stored ? JSON.parse(stored) : [];
    } catch { return []; }
  });
  const [activeLayoutName, setActiveLayoutName] = useState<string | null>(null);

  const dropdownRef = useRef<HTMLDivElement>(null);
  const fetchCancellers = useRef<Map<string, () => void>>(new Map());

  // Fetch strategy list on mount
  useEffect(() => {
    let cancelled = false;
    setListLoading(true);
    fetch("/bt-api/backtests")
      .then((res) => res.json())
      .then((json) => {
        if (!cancelled) setStrategyList(json.result ?? json);
      })
      .catch(() => {
        // silently ignore
      })
      .finally(() => {
        if (!cancelled) setListLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Cancel all in-flight fetches on unmount
  useEffect(() => {
    return () => {
      fetchCancellers.current.forEach((cancel) => cancel());
      fetchCancellers.current.clear();
    };
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem("risk-engine-layouts", JSON.stringify(savedLayouts));
    } catch {
      // localStorage quota exceeded — silently ignore
    }
  }, [savedLayouts]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!selectorOpen) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setSelectorOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [selectorOpen]);

  // Fetch full backtest data when a strategy is selected
  const fetchStrategyData = useCallback((id: string) => {
    const controller = new AbortController();
    fetch(`/bt-api/backtests/${id}`, { signal: controller.signal })
      .then((res) => res.json())
      .then((json) => {
        const result: BacktestResult = json.result ?? json;
        setSelectedStrategies((prev) =>
          prev.map((s) =>
            s.id === id ? { ...s, data: result, loading: false } : s
          )
        );
      })
      .catch((err) => {
        if (err instanceof DOMException && err.name === "AbortError") return;
        setSelectedStrategies((prev) =>
          prev.map((s) =>
            s.id === id ? { ...s, loading: false, error: true } : s
          )
        );
      });
    return () => controller.abort();
  }, []);

  const selectedIds = useMemo(
    () => new Set(selectedStrategies.map((s) => s.id)),
    [selectedStrategies]
  );

  const toggleStrategy = useCallback(
    (item: BacktestHistoryItem) => {
      if (selectedIds.has(item.id)) {
        fetchCancellers.current.get(item.id)?.();
        fetchCancellers.current.delete(item.id);
        setSelectedStrategies((prev) => prev.filter((s) => s.id !== item.id));
      } else {
        const newEntry: SelectedStrategy = {
          id: item.id,
          meta: item,
          data: null,
          riskSize: accountRisk,
          loading: true,
          error: false,
          hidden: false,
        };
        const cancel = fetchStrategyData(item.id);
        fetchCancellers.current.set(item.id, cancel);
        setSelectedStrategies((prev) => [...prev, newEntry]);
      }
    },
    [selectedIds, fetchStrategyData]
  );

  const toggleHide = useCallback((id: string) => {
    setSelectedStrategies((prev) =>
      prev.map((s) => (s.id === id ? { ...s, hidden: !s.hidden } : s))
    );
  }, []);

  const removeStrategy = useCallback((id: string) => {
    fetchCancellers.current.get(id)?.();
    fetchCancellers.current.delete(id);
    setSelectedStrategies((prev) => prev.filter((s) => s.id !== id));
  }, []);

  const updateRisk = useCallback((id: string, riskSize: number) => {
    setSelectedStrategies((prev) =>
      prev.map((s) => (s.id === id ? { ...s, riskSize } : s))
    );
  }, []);

  const saveLayoutAs = useCallback((name: string) => {
    const layout: SavedLayout = {
      name,
      accountRisk,
      strategies: selectedStrategies.map((s) => ({ id: s.id, riskSize: s.riskSize })),
    };
    setSavedLayouts((prev) => {
      const filtered = prev.filter((l) => l.name !== layout.name);
      return [...filtered, layout];
    });
    setActiveLayoutName(layout.name);
    setSaveFlash(true);
    setTimeout(() => setSaveFlash(false), 1500);
  }, [accountRisk, selectedStrategies]);

  const saveLayout = useCallback(() => {
    if (!activeLayoutName) return;
    saveLayoutAs(activeLayoutName);
  }, [activeLayoutName, saveLayoutAs]);

  const saveNewLayout = useCallback(() => {
    const name = window.prompt("Layout name:");
    if (!name?.trim()) return;
    const trimmed = name.trim();
    const exists = savedLayouts.some((l) => l.name === trimmed);
    if (exists && !window.confirm(`"${trimmed}" already exists. Overwrite?`)) return;
    saveLayoutAs(trimmed);
  }, [savedLayouts, saveLayoutAs]);

  const applyKelly = useCallback(() => {
    // First pass: compute Kelly fraction for each strategy
    const kellyFractions: Map<string, number> = new Map();
    for (const s of selectedStrategies) {
      if (!s.data) continue;
      const filled = s.data.trades.filter((t) => t.exit_type !== "no_fill");
      if (filled.length === 0) continue;
      const wins = filled.filter((t) => t.r_multiple > 0);
      const losses = filled.filter((t) => t.r_multiple <= 0);
      if (wins.length === 0 || losses.length === 0) continue;
      const winRate = wins.length / filled.length;
      const avgWin = wins.reduce((sum, t) => sum + t.r_multiple, 0) / wins.length;
      const avgLoss = Math.abs(losses.reduce((sum, t) => sum + t.r_multiple, 0) / losses.length);
      // Kelly: f = (b*p - q) / b where b = avgWin/avgLoss, p = winRate, q = 1-p
      const b = avgWin / avgLoss;
      const kellyF = Math.max(0, (b * winRate - (1 - winRate)) / b);
      kellyFractions.set(s.id, kellyF);
    }

    // Normalize: best edge gets full baseline risk, others scale proportionally
    const maxKelly = Math.max(...kellyFractions.values(), 0);
    if (maxKelly === 0) return;

    setSelectedStrategies((prev) =>
      prev.map((s) => {
        const kf = kellyFractions.get(s.id);
        if (kf === undefined) return s;
        const riskSize = Math.round((kf / maxKelly) * accountRisk);
        return { ...s, riskSize: Math.max(riskSize, 1) };
      })
    );
  }, [accountRisk, selectedStrategies]);

  const loadLayout = useCallback((name: string) => {
    if (name === activeLayoutName || listLoading) return;
    const layout = savedLayouts.find((l) => l.name === name);
    if (!layout) return;
    setAccountRisk(layout.accountRisk);
    fetchCancellers.current.forEach((cancel) => cancel());
    fetchCancellers.current.clear();
    const newStrategies: SelectedStrategy[] = [];
    let skipped = 0;
    for (const entry of layout.strategies) {
      const meta = strategyList.find((s) => s.id === entry.id);
      if (!meta) { skipped++; continue; }
      newStrategies.push({ id: entry.id, meta, data: null, riskSize: entry.riskSize, loading: true, error: false, hidden: false });
    }
    if (skipped > 0) {
      console.warn(`Layout "${name}": ${skipped} strategy(ies) no longer exist and were skipped`);
    }
    setSelectedStrategies(newStrategies);
    for (const s of newStrategies) {
      const cancel = fetchStrategyData(s.id);
      fetchCancellers.current.set(s.id, cancel);
    }
    setActiveLayoutName(name);
  }, [activeLayoutName, listLoading, savedLayouts, strategyList, fetchStrategyData]);

  const deleteLayout = useCallback((name: string) => {
    if (!window.confirm(`Delete layout "${name}"?`)) return;
    setSavedLayouts((prev) => prev.filter((l) => l.name !== name));
    if (activeLayoutName === name) setActiveLayoutName(null);
  }, [activeLayoutName]);

  // Unique filter options derived from strategy list
  const uniqueAssets = useMemo(() => {
    const set = new Set(strategyList.map((s) => s.instrument));
    return Array.from(set).sort();
  }, [strategyList]);

  const uniqueSessions = useMemo(() => {
    const set = new Set(strategyList.flatMap((s) => s.sessions));
    return Array.from(set).sort();
  }, [strategyList]);

  // Filtered dropdown list
  const filteredList = useMemo(() => {
    return strategyList.filter((item) => {
      // Starred filter
      if (filterStarred && !item.starred) return false;
      // Asset filter
      if (filterAsset && item.instrument !== filterAsset) return false;
      // Session filter
      if (filterSession && !item.sessions.includes(filterSession)) return false;
      // Text search
      if (searchQuery.trim()) {
        const q = searchQuery.trim().toLowerCase();
        const name = (item.name ?? "").toLowerCase();
        const inst = item.instrument.toLowerCase();
        const strat = (item.strategy ?? "").toLowerCase();
        const sess = item.sessions.join(" ").toLowerCase();
        if (!name.includes(q) && !inst.includes(q) && !strat.includes(q) && !sess.includes(q)) return false;
      }
      return true;
    });
  }, [strategyList, searchQuery, filterStarred, filterAsset, filterSession]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header row */}
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-lg font-semibold text-text-primary font-display">
          Risk Engine
        </h1>
        <div className="flex items-center gap-3">
          {/* Layout controls */}
          <select
            value={activeLayoutName ?? ""}
            onChange={(e) => loadLayout(e.target.value)}
            disabled={listLoading}
            className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs text-text-primary outline-none focus:border-accent disabled:opacity-50"
          >
            <option value="" disabled>Load layout…</option>
            {savedLayouts.map((l) => (
              <option key={l.name} value={l.name}>{l.name}</option>
            ))}
          </select>
          {activeLayoutName && (
            <button
              onClick={saveLayout}
              className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-secondary transition-colors hover:border-accent/50 hover:text-text-primary"
            >
              Save
            </button>
          )}
          <button
            onClick={saveNewLayout}
            className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-secondary transition-colors hover:border-accent/50 hover:text-text-primary"
          >
            Save New
          </button>
          {saveFlash && (
            <span className="text-[11px] font-medium text-green-400 animate-pulse">
              Saved
            </span>
          )}
          {activeLayoutName && (
            <button
              onClick={() => deleteLayout(activeLayoutName)}
              className="rounded border border-border bg-bg-secondary px-1.5 py-1.5 text-xs text-text-muted transition-colors hover:border-red-500/50 hover:text-red-400"
              title={`Delete "${activeLayoutName}"`}
            >
              <svg className="h-3 w-3" viewBox="0 0 16 16" fill="currentColor">
                <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
              </svg>
            </button>
          )}
          <div className="h-5 w-px bg-border" />
          {/* View mode toggle */}
          <div className="inline-flex rounded border border-border bg-bg-secondary">
            <button
              onClick={() => setViewMode("individual")}
              className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                viewMode === "individual"
                  ? "bg-accent/20 text-accent"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              Individual
            </button>
            <button
              onClick={() => setViewMode("combined")}
              className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                viewMode === "combined"
                  ? "bg-accent/20 text-accent"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              Combined
            </button>
          </div>
          <div className="h-5 w-px bg-border" />
          {/* Kelly criterion */}
          <button
            onClick={applyKelly}
            disabled={selectedStrategies.filter((s) => s.data !== null).length === 0}
            className="rounded border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-secondary transition-colors hover:border-accent/50 hover:text-text-primary disabled:opacity-40 disabled:cursor-not-allowed"
            title="Apply Kelly Criterion to risk sizes"
          >
            Kelly
          </button>
          <div className="h-5 w-px bg-border" />
          {/* Account risk input */}
          <label className="text-xs text-text-secondary font-display">
            Account Risk ($)
          </label>
          <input
            type="number"
            value={accountRisk}
            onChange={(e) => {
              const v = parseFloat(e.target.value);
              if (!isNaN(v)) {
                setAccountRisk(v);
              }
            }}
            onBlur={() => {
              if (accountRisk < 1) setAccountRisk(1);
            }}
            className="w-32 rounded border border-border bg-bg-secondary px-3 py-1.5 text-sm font-mono text-text-primary outline-none focus:border-accent"
          />
        </div>
      </div>

      {/* Strategy Selector */}
      <div ref={dropdownRef} className="relative mb-6">
        {/* Trigger button */}
        <button
          onClick={() => setSelectorOpen(!selectorOpen)}
          className="flex w-full items-center justify-between rounded-lg border border-border bg-bg-card px-4 py-2.5 text-sm text-text-secondary transition-colors hover:border-accent/50"
        >
          <span>
            {selectedStrategies.length === 0
              ? "Select strategies…"
              : `${selectedStrategies.length} strateg${selectedStrategies.length === 1 ? "y" : "ies"} selected`}
          </span>
          <svg
            className={`h-4 w-4 text-text-muted transition-transform ${selectorOpen ? "rotate-180" : ""}`}
            viewBox="0 0 16 16"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
          >
            <path d="M4 6l4 4 4-4" />
          </svg>
        </button>

        {/* Dropdown panel */}
        {selectorOpen && (
          <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-lg border border-border bg-bg-card shadow-xl shadow-black/40">
            {/* Search input */}
            <div className="border-b border-border p-2">
              <div className="relative">
                <svg
                  className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3 w-3 text-text-muted pointer-events-none"
                  viewBox="0 0 16 16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.5"
                >
                  <circle cx="6.5" cy="6.5" r="4" />
                  <path d="M10 10l3 3" />
                </svg>
                <input
                  type="text"
                  placeholder="Search strategies…"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  autoFocus
                  className="w-full rounded border border-border bg-bg-secondary pl-7 pr-8 py-1.5 text-xs text-text-primary placeholder-text-muted outline-none focus:border-accent"
                />
                {searchQuery && (
                  <button
                    onClick={() => setSearchQuery("")}
                    className="absolute right-1.5 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-secondary"
                  >
                    <svg className="h-2.5 w-2.5" viewBox="0 0 16 16" fill="currentColor">
                      <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                    </svg>
                  </button>
                )}
              </div>
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-2 py-1.5">
              {/* Saved filter */}
              <button
                onClick={() => setFilterStarred(!filterStarred)}
                className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                  filterStarred
                    ? "bg-yellow-500/20 text-yellow-400"
                    : "bg-bg-secondary text-text-muted hover:text-text-secondary"
                }`}
              >
                <svg className="h-2.5 w-2.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 1.23l2.18 4.41 4.87.71-3.52 3.43.83 4.85L8 12.26l-4.36 2.37.83-4.85L1 6.35l4.87-.71L8 1.23z" />
                </svg>
                Saved
              </button>

              {/* Asset filter */}
              {uniqueAssets.map((asset) => (
                <button
                  key={asset}
                  onClick={() => setFilterAsset(filterAsset === asset ? null : asset)}
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                    filterAsset === asset
                      ? "bg-accent/20 text-accent"
                      : "bg-bg-secondary text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {asset}
                </button>
              ))}

              {/* Session filter */}
              {uniqueSessions.map((sess) => (
                <button
                  key={sess}
                  onClick={() => setFilterSession(filterSession === sess ? null : sess)}
                  className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition-colors ${
                    filterSession === sess
                      ? "bg-accent/20 text-accent"
                      : "bg-bg-secondary text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {sess}
                </button>
              ))}
            </div>

            {/* Strategy list */}
            <div className="max-h-72 overflow-y-auto">
              {listLoading && (
                <div className="px-3 py-4 text-center text-xs text-text-muted">
                  Loading strategies…
                </div>
              )}
              {!listLoading && filteredList.length === 0 && (
                <div className="px-3 py-4 text-center text-xs text-text-muted">
                  No strategies found
                </div>
              )}
              {!listLoading &&
                filteredList.map((item) => {
                  const isSelected = selectedIds.has(item.id);
                  return (
                    <button
                      key={item.id}
                      onClick={() => toggleStrategy(item)}
                      className={`flex w-full items-center gap-2 px-3 py-2 text-left text-xs transition-colors hover:bg-bg-card-hover ${
                        isSelected ? "bg-accent/10" : ""
                      }`}
                    >
                      {/* Checkmark */}
                      <span className="w-4 flex-shrink-0 text-center">
                        {isSelected && (
                          <svg
                            className="inline h-3 w-3 text-accent"
                            viewBox="0 0 16 16"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                          >
                            <path d="M3 8l3.5 3.5L13 5" />
                          </svg>
                        )}
                      </span>

                      {/* Star indicator */}
                      {item.starred && (
                        <svg className="h-3 w-3 flex-shrink-0 text-yellow-400" viewBox="0 0 16 16" fill="currentColor">
                          <path d="M8 1.23l2.18 4.41 4.87.71-3.52 3.43.83 4.85L8 12.26l-4.36 2.37.83-4.85L1 6.35l4.87-.71L8 1.23z" />
                        </svg>
                      )}

                      {/* Name */}
                      <span className="min-w-0 flex-1 truncate text-text-primary">
                        {item.name || "Unnamed"}
                      </span>

                      {/* Instrument badge */}
                      <span className="rounded bg-accent/20 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                        {item.instrument}
                      </span>

                      {/* Sessions */}
                      <span className="flex gap-1">
                        {item.sessions.map((s) => (
                          <SessionTag key={s} session={s} />
                        ))}
                      </span>

                      {/* Date range */}
                      <span className="whitespace-nowrap text-[10px] text-text-muted">
                        {formatDateRange(item.date_start, item.date_end)}
                      </span>
                    </button>
                  );
                })}
            </div>
          </div>
        )}
      </div>

      {/* Selected strategy chips */}
      {selectedStrategies.length > 0 && (
        <div className="mb-6 flex flex-wrap gap-1.5">
          {selectedStrategies.map((s) => (
            <span
              key={s.id}
              className="inline-flex items-center gap-1 rounded-full bg-accent/15 px-2.5 py-1 text-[11px] font-medium text-accent"
            >
              <span className="max-w-[200px] truncate">
                {displayName(s.meta)}
              </span>
              <button
                onClick={() => removeStrategy(s.id)}
                className="ml-0.5 rounded-full p-0.5 transition-colors hover:bg-accent/20"
              >
                <svg className="h-2.5 w-2.5" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                </svg>
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Empty state */}
      {selectedStrategies.length === 0 && (
        <div className="rounded-lg border border-border bg-bg-card p-8 text-center">
          <p className="text-sm text-text-muted">Select one or more strategies above to view their R profile</p>
        </div>
      )}

      {/* Conditional rendering based on view mode */}
      {viewMode === "individual" && (
        <>
          {/* Strategy Cards */}
          <div className="space-y-4">
            {selectedStrategies.map((strategy) => (
              <StrategyCard
                key={strategy.id}
                strategy={strategy}
                accountRisk={accountRisk}
                onRiskChange={(riskSize) => updateRisk(strategy.id, riskSize)}
                onRemove={() => removeStrategy(strategy.id)}
              />
            ))}
          </div>

          {/* Portfolio Summary Card */}
          {selectedStrategies.filter((s) => s.data !== null).length >= 2 && (
            <div className="mt-4">
              <PortfolioSummaryCard
                strategies={selectedStrategies}
                accountRisk={accountRisk}
              />
            </div>
          )}
        </>
      )}

      {viewMode === "combined" && selectedStrategies.length > 0 && (
        <CombinedCard
          strategies={selectedStrategies}
          accountRisk={accountRisk}
          onRiskChange={(id, riskSize) => updateRisk(id, riskSize)}
          onRemove={(id) => removeStrategy(id)}
          onToggleHide={(id) => toggleHide(id)}
        />
      )}
    </div>
  );
}
