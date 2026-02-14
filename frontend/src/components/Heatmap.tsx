import { Fragment, useMemo, useState } from "react";
import type { BacktestConfig, BacktestSummary } from "../lib/types";
import { formatNumber } from "../lib/utils";
import { ScrollArea } from "./ui/scroll-area";

type MetricKey = "sharpe_ratio" | "total_pnl_usd" | "profit_factor" | "win_rate" | "avg_r" | "max_drawdown_usd";

const METRIC_OPTIONS: { key: MetricKey; label: string }[] = [
  { key: "sharpe_ratio", label: "Sharpe Ratio" },
  { key: "total_pnl_usd", label: "Total P&L ($)" },
  { key: "profit_factor", label: "Profit Factor" },
  { key: "win_rate", label: "Win Rate" },
  { key: "avg_r", label: "Avg R" },
  { key: "max_drawdown_usd", label: "Max Drawdown ($)" },
];

interface HeatmapProps {
  results: { config: BacktestConfig; summary: BacktestSummary }[];
  sweptParams: Record<string, number[]>;
}

function interpolateColor(t: number): string {
  // Deep red → neutral dark → bright green
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

function formatMetricValue(key: MetricKey, value: number): string {
  switch (key) {
    case "total_pnl_usd":
    case "max_drawdown_usd":
      return `$${value.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
    case "win_rate":
      return `${(value * 100).toFixed(1)}%`;
    case "sharpe_ratio":
    case "avg_r":
      return formatNumber(value, 3);
    default:
      return formatNumber(value, 2);
  }
}

export function Heatmap({ results, sweptParams }: HeatmapProps) {
  const [metric, setMetric] = useState<MetricKey>("sharpe_ratio");
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    config: BacktestConfig;
    summary: BacktestSummary;
  } | null>(null);

  const paramKeys = Object.keys(sweptParams);

  const { grid, xValues, yValues, minVal, maxVal } = useMemo(() => {
    if (paramKeys.length < 2) {
      // 1D: use single param as x-axis, dummy y
      const xKey = paramKeys[0];
      const xVals = sweptParams[xKey] ?? [];
      const yVals = [0];

      const grid = new Map<string, { config: BacktestConfig; summary: BacktestSummary }>();
      let min = Infinity;
      let max = -Infinity;

      for (const r of results) {
        const xVal = r.config[xKey] as number;
        const key = `${xVal}_0`;
        grid.set(key, r);
        const v = r.summary[metric] as number;
        if (v < min) min = v;
        if (v > max) max = v;
      }

      return { grid, xValues: xVals, yValues: yVals, minVal: min, maxVal: max };
    }

    // 2D heatmap
    const xKey = paramKeys[0];
    const yKey = paramKeys[1];
    const xVals = sweptParams[xKey] ?? [];
    const yVals = sweptParams[yKey] ?? [];

    const grid = new Map<string, { config: BacktestConfig; summary: BacktestSummary }>();
    let min = Infinity;
    let max = -Infinity;

    for (const r of results) {
      const xVal = r.config[xKey] as number;
      const yVal = r.config[yKey] as number;
      const key = `${xVal}_${yVal}`;
      grid.set(key, r);
      const v = r.summary[metric] as number;
      if (v < min) min = v;
      if (v > max) max = v;
    }

    return { grid, xValues: xVals, yValues: yVals, minVal: min, maxVal: max };
  }, [results, sweptParams, paramKeys, metric]);

  const is1D = paramKeys.length < 2;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">Heatmap</h2>
        <select
          value={metric}
          onChange={(e) => setMetric(e.target.value as MetricKey)}
          className="rounded-md border border-border bg-bg-secondary px-2.5 py-1 text-xs text-text-primary outline-none focus:border-accent"
        >
          {METRIC_OPTIONS.map((opt) => (
            <option key={opt.key} value={opt.key}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      <ScrollArea className="w-full">
        {/* Y-axis label */}
        {!is1D && (
          <div className="mb-1 text-[10px] font-medium text-text-muted">
            {paramKeys[1]}
          </div>
        )}

        <div className="inline-block">
          {/* Grid */}
          <div
            className="grid gap-px"
            style={{
              gridTemplateColumns: is1D
                ? `32px repeat(${xValues.length}, minmax(42px, 1fr))`
                : `32px repeat(${xValues.length}, minmax(42px, 1fr))`,
              gridTemplateRows: is1D
                ? "auto"
                : `repeat(${yValues.length}, minmax(24px, 1fr)) auto`,
            }}
          >
            {/* Rows */}
            {yValues.map((yVal, yi) => (
              <Fragment key={`row-${yi}`}>
                {/* Y label */}
                <div
                  className="flex items-center justify-end pr-1 text-[10px] font-mono text-text-muted"
                >
                  {is1D ? "" : formatNumber(yVal, yVal % 1 === 0 ? 0 : 2)}
                </div>

                {/* Cells */}
                {xValues.map((xVal, xi) => {
                  const key = `${xVal}_${yVal}`;
                  const entry = grid.get(key);
                  const val = entry ? (entry.summary[metric] as number) : 0;
                  const range = maxVal - minVal;
                  const isInverted = metric === "max_drawdown_usd";
                  let t = range > 0 ? (val - minVal) / range : 0.5;
                  if (isInverted) t = 1 - t;
                  const bgColor = entry ? interpolateColor(t) : "var(--color-bg-secondary)";

                  return (
                    <div
                      key={`cell-${xi}-${yi}`}
                      className="flex items-center justify-center rounded-sm cursor-default px-1 py-0.5 transition-opacity hover:opacity-80"
                      style={{
                        backgroundColor: bgColor,
                        minHeight: is1D ? "28px" : "24px",
                      }}
                      onMouseEnter={(e) => {
                        if (!entry) return;
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltip({
                          x: rect.left + rect.width / 2,
                          y: rect.top,
                          config: entry.config,
                          summary: entry.summary,
                        });
                      }}
                      onMouseLeave={() => setTooltip(null)}
                    >
                      <span className="text-[10px] font-mono font-medium text-white/90">
                        {entry ? formatMetricValue(metric, val) : "—"}
                      </span>
                    </div>
                  );
                })}
              </Fragment>
            ))}

            {/* X labels row */}
            <div /> {/* empty corner */}
            {xValues.map((xVal, xi) => (
              <div
                key={`xlabel-${xi}`}
                className="flex items-start justify-center pt-1 text-[10px] font-mono text-text-muted"
              >
                {formatNumber(xVal, xVal % 1 === 0 ? 0 : 2)}
              </div>
            ))}
          </div>

          {/* X-axis label */}
          <div className="mt-1 text-center text-[10px] font-medium text-text-muted">
            {paramKeys[0]}
          </div>
        </div>
      </ScrollArea>

      {/* Tooltip portal */}
      {tooltip && (
        <div
          className="fixed z-50 rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl"
          style={{
            left: tooltip.x,
            top: tooltip.y - 8,
            transform: "translate(-50%, -100%)",
          }}
        >
          <div className="space-y-0.5 text-xs">
            {paramKeys.map((p) => (
              <div key={p} className="text-text-muted">
                {p}: <span className="font-mono text-text-primary">{formatNumber(tooltip.config[p] as number, 2)}</span>
              </div>
            ))}
            <div className="my-1 border-t border-border" />
            <div className="text-text-muted">
              Trades: <span className="font-mono text-text-primary">{tooltip.summary.total_trades}</span>
            </div>
            <div className="text-text-muted">
              Win Rate: <span className="font-mono text-text-primary">{(tooltip.summary.win_rate * 100).toFixed(1)}%</span>
            </div>
            <div className="text-text-muted">
              Sharpe: <span className="font-mono text-text-primary">{formatNumber(tooltip.summary.sharpe_ratio, 3)}</span>
            </div>
            <div className="text-text-muted">
              P&L: <span className="font-mono text-text-primary">${tooltip.summary.total_pnl_usd.toLocaleString()}</span>
            </div>
            <div className="text-text-muted">
              PF: <span className="font-mono text-text-primary">{formatNumber(tooltip.summary.profit_factor)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
