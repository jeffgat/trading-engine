import { useMemo, useState } from "react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
  LineChart,
  Line,
} from "recharts";
import type { BacktestConfig, BacktestSummary, OptimizationResult } from "@/backtesting/lib/types";
import { formatNumber } from "@/backtesting/lib/utils";

type MetricKey = "sharpe_ratio" | "total_pnl_usd" | "profit_factor" | "win_rate" | "avg_r" | "max_drawdown_usd" | "calmar_ratio";

const METRIC_OPTIONS: { key: MetricKey; label: string }[] = [
  { key: "sharpe_ratio", label: "Sharpe Ratio" },
  { key: "total_pnl_usd", label: "Net R" },
  { key: "profit_factor", label: "Profit Factor" },
  { key: "calmar_ratio", label: "Calmar Ratio" },
  { key: "win_rate", label: "Win Rate" },
  { key: "avg_r", label: "Avg R" },
  { key: "max_drawdown_usd", label: "Max DD (R)" },
];

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
  const b = Math.round(65 + (65 - 65) * s);
  return `rgb(${r},${g},${b})`;
}

function getMetricValue(summary: BacktestSummary, key: MetricKey, riskUsd: number): number {
  switch (key) {
    case "total_pnl_usd":
    case "max_drawdown_usd":
      return summary[key] / riskUsd;
    case "win_rate":
      return summary[key] * 100;
    default:
      return summary[key] as number;
  }
}

function formatMetricLabel(key: MetricKey): string {
  return METRIC_OPTIONS.find((o) => o.key === key)?.label ?? key;
}

interface BayesianScatterProps {
  data: OptimizationResult;
}

export function BayesianScatter({ data }: BayesianScatterProps) {
  const [metric, setMetric] = useState<MetricKey>("sharpe_ratio");
  const paramKeys = Object.keys(data.swept_params);
  const riskUsd = data.all_results[0]?.config.risk_usd ?? 5000;

  // Build scatter points
  const { points, minMetric, maxMetric } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    const pts = data.all_results.map((r) => {
      const val = getMetricValue(r.summary, metric, riskUsd);
      if (val < min) min = val;
      if (val > max) max = val;
      const point: Record<string, unknown> = {
        metricValue: val,
        config: r.config,
        summary: r.summary,
      };
      for (const pk of paramKeys) {
        point[pk] = r.config[pk] as number;
      }
      return point;
    });
    return { points: pts, minMetric: min, maxMetric: max };
  }, [data.all_results, metric, paramKeys, riskUsd]);

  // Determine axes: use first two params, or first param + metric
  const xKey = paramKeys[0];
  const yKey = paramKeys.length >= 2 ? paramKeys[1] : null;

  // Convergence data
  const convergence = data.bayesian?.convergence;

  return (
    <div className="space-y-4">
      {/* Scatter plot */}
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-sm font-medium text-text-secondary">
            Trial Scatter
            <span className="ml-2 text-[10px] font-normal text-text-muted">
              {data.total_combinations} trials
            </span>
          </h2>
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

        {/* Color legend */}
        <div className="mb-3 flex items-center gap-2 text-[10px] text-text-muted">
          <span>Color: {formatMetricLabel(metric)}</span>
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full" style={{ background: interpolateColor(0) }} />
            <span>Low</span>
          </div>
          <div
            className="h-2 w-24 rounded-full"
            style={{
              background: `linear-gradient(to right, ${interpolateColor(0)}, ${interpolateColor(0.5)}, ${interpolateColor(1)})`,
            }}
          />
          <div className="flex items-center gap-1">
            <div className="h-2 w-2 rounded-full" style={{ background: interpolateColor(1) }} />
            <span>High</span>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={320}>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 28, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey={xKey}
              type="number"
              name={xKey}
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              stroke="var(--color-border)"
              label={{
                value: xKey,
                position: "bottom",
                offset: 12,
                style: { fontSize: 11, fill: "var(--color-text-muted)" },
              }}
              domain={["dataMin", "dataMax"]}
            />
            <YAxis
              dataKey={yKey ?? "metricValue"}
              type="number"
              name={yKey ?? formatMetricLabel(metric)}
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              stroke="var(--color-border)"
              label={{
                value: yKey ?? formatMetricLabel(metric),
                angle: -90,
                position: "insideLeft",
                offset: 4,
                style: { fontSize: 11, fill: "var(--color-text-muted)" },
              }}
              domain={["dataMin", "dataMax"]}
            />
            <RechartsTooltip
              cursor={false}
              content={({ payload }) => {
                if (!payload?.length) return null;
                const d = payload[0].payload as Record<string, unknown>;
                const config = d.config as BacktestConfig;
                const summary = d.summary as BacktestSummary;
                return (
                  <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
                    <div className="space-y-0.5 text-xs">
                      {paramKeys.map((p) => (
                        <div key={p} className="text-text-muted">
                          {p}:{" "}
                          <span className="font-mono text-text-primary">
                            {formatNumber(config[p] as number, 2)}
                          </span>
                        </div>
                      ))}
                      <div className="my-1 border-t border-border" />
                      <div className="text-text-muted">
                        Trades: <span className="font-mono text-text-primary">{summary.total_trades}</span>
                      </div>
                      <div className="text-text-muted">
                        Win Rate:{" "}
                        <span className="font-mono text-text-primary">{(summary.win_rate * 100).toFixed(1)}%</span>
                      </div>
                      <div className="text-text-muted">
                        Sharpe:{" "}
                        <span className="font-mono text-text-primary">{formatNumber(summary.sharpe_ratio, 3)}</span>
                      </div>
                      <div className="text-text-muted">
                        Net R:{" "}
                        <span className="font-mono text-text-primary">
                          {(summary.total_pnl_usd / riskUsd).toFixed(2)}R
                        </span>
                      </div>
                      <div className="text-text-muted">
                        PF:{" "}
                        <span className="font-mono text-text-primary">
                          {formatNumber(summary.profit_factor)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              }}
            />
            <Scatter data={points} fill="var(--color-accent)">
              {points.map((pt, i) => {
                const val = pt.metricValue as number;
                const range = maxMetric - minMetric;
                const isInverted = metric === "max_drawdown_usd";
                let t = range > 0 ? (val - minMetric) / range : 0.5;
                if (isInverted) t = 1 - t;
                return <Cell key={i} fill={interpolateColor(t)} fillOpacity={0.85} />;
              })}
            </Scatter>
          </ScatterChart>
        </ResponsiveContainer>
      </div>

      {/* Convergence chart */}
      {convergence && convergence.length > 0 && (
        <div className="rounded-lg border border-border bg-bg-card p-4">
          <h2 className="mb-3 text-sm font-medium text-text-secondary">
            Convergence
            <span className="ml-2 text-[10px] font-normal text-text-muted">
              {data.bayesian?.objective ?? "objective"} &middot; {data.bayesian?.sampler?.toUpperCase()}
            </span>
          </h2>
          <ResponsiveContainer width="100%" height={180}>
            <LineChart data={convergence} margin={{ top: 4, right: 16, bottom: 20, left: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="trial"
                tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                stroke="var(--color-border)"
                label={{
                  value: "Trial",
                  position: "bottom",
                  offset: 4,
                  style: { fontSize: 11, fill: "var(--color-text-muted)" },
                }}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
                stroke="var(--color-border)"
                label={{
                  value: data.bayesian?.objective ?? "objective",
                  angle: -90,
                  position: "insideLeft",
                  offset: 4,
                  style: { fontSize: 11, fill: "var(--color-text-muted)" },
                }}
              />
              <RechartsTooltip
                contentStyle={{
                  background: "var(--color-bg-secondary)",
                  border: "1px solid var(--color-border)",
                  borderRadius: 8,
                  fontSize: 11,
                  color: "var(--color-text-primary)",
                }}
                labelStyle={{ color: "var(--color-text-muted)" }}
                formatter={((value: number | string | undefined, name: string | undefined) => [
                  typeof value === "number" ? value.toFixed(4) : String(value ?? ""),
                  name === "best_so_far" ? "Best" : "Trial",
                ]) as never}
                labelFormatter={(label) => `Trial ${label}`}
              />
              <Line
                dataKey="value"
                stroke="var(--color-text-muted)"
                strokeWidth={1}
                dot={false}
                opacity={0.4}
                name="value"
              />
              <Line
                dataKey="best_so_far"
                stroke="var(--color-accent)"
                strokeWidth={2}
                dot={false}
                name="best_so_far"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
