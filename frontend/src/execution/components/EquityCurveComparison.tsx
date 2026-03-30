import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Line,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { ComparisonCurvePoint } from "@/execution/lib/types";

interface EquityCurveComparisonProps {
  data: ComparisonCurvePoint[];
  deployDate: string;
  configName: string; // "FAST" | "SLOW"
  liveR?: number | null; // Raw live cumulative R (independent of backtest window)
  backtestR?: number | null; // Backtest total R for the visible window
}

const CONFIG_LINE_COLORS: Record<string, string> = {
  FAST: "#3b82f6",    // blue-500
  "FAST_V1.1": "#60a5fa", // blue-400
  FAST_V2: "#d946ef", // fuchsia-500
  "FAST_V2.1": "#e879f9", // fuchsia-400
  GENERAL_V1: "#f97316", // orange-500
  SLOW: "#10b981",    // emerald-500
};

function formatR(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}R`;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const backtest = payload.find((p: any) => p.dataKey === "backtest_r");
  const live = payload.find((p: any) => p.dataKey === "live_r");
  const rawLiveR = live?.payload?._rawLiveR;

  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted">{label}</p>
      {backtest?.value != null && (
        <p className="font-mono text-sm" style={{ color: "#9ca3af" }}>
          Backtest: {formatR(backtest.value)}
        </p>
      )}
      {rawLiveR != null && (
        <p className="font-mono text-sm font-semibold" style={{ color: rawLiveR >= 0 ? "var(--color-profit)" : "var(--color-loss)" }}>
          Live: {formatR(rawLiveR)}
        </p>
      )}
    </div>
  );
}

export function EquityCurveComparison({ data, deployDate, configName, liveR: liveRProp, backtestR: backtestRProp }: EquityCurveComparisonProps) {
  const liveColor = CONFIG_LINE_COLORS[configName] ?? "var(--color-profit)";

  // Thin data for rendering if > 300 points
  const displayData = useMemo(() => {
    if (data.length <= 300) return data;
    const step = Math.ceil(data.length / 300);
    return data.filter((_, i) => i % step === 0 || i === data.length - 1);
  }, [data]);

  // Scale trade bars to ~10% of chart height
  const tradeDomain = useMemo(() => {
    const maxAbs = displayData.reduce(
      (m, d) => Math.max(m, Math.abs(d.live_r_per_trade ?? 0)),
      0.01,
    );
    return [-maxAbs * 10, maxAbs * 10] as [number, number];
  }, [displayData]);

  // Raw live R from props (stable across backtest window changes),
  // fallback to deriving from chart data
  const derivedLiveR = useMemo(() => {
    for (let i = displayData.length - 1; i >= 0; i--) {
      if (displayData[i].live_r != null) return displayData[i].live_r!;
    }
    return null;
  }, [displayData]);
  const finalLiveR = liveRProp ?? derivedLiveR;

  if (!data.length) {
    return (
      <div className="flex h-[380px] items-center justify-center rounded-lg border border-dashed border-border bg-bg-card text-text-muted text-sm">
        Enter a backtest ID to compare against live performance
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">
          Backtest vs Live ({configName})
        </h2>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: "#9ca3af", opacity: 0.7 }} />
            Backtest
          </div>
          <div className="flex items-center gap-1.5 text-xs text-text-muted">
            <span className="inline-block h-0.5 w-4 rounded" style={{ background: liveColor }} />
            Live
          </div>
          {backtestRProp != null && (
            <span
              className="rounded-md px-2 py-0.5 font-mono text-xs font-semibold"
              style={{
                color: backtestRProp >= 0 ? "var(--color-profit)" : "var(--color-loss)",
                background: backtestRProp >= 0 ? "rgba(61, 214, 140, 0.12)" : "rgba(240, 97, 94, 0.12)",
              }}
            >
              BT: {formatR(backtestRProp)}
            </span>
          )}
          {finalLiveR != null && (
            <span
              className="rounded-md px-2 py-0.5 font-mono text-xs font-semibold"
              style={{
                color: finalLiveR >= 0 ? "var(--color-profit)" : "var(--color-loss)",
                background: finalLiveR >= 0 ? "rgba(61, 214, 140, 0.12)" : "rgba(240, 97, 94, 0.12)",
              }}
            >
              Live: {formatR(finalLiveR)}
            </span>
          )}
        </div>
      </div>

      <ResponsiveContainer width="100%" height={380}>
        <ComposedChart data={displayData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <CartesianGrid
            strokeDasharray="3 3"
            stroke="var(--color-border)"
            strokeOpacity={0.5}
            vertical={false}
          />

          <XAxis
            dataKey="date"
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: "var(--color-border)" }}
            interval="preserveStartEnd"
            minTickGap={60}
          />

          <YAxis
            yAxisId="equity"
            tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `${v.toFixed(0)}R`}
            width={45}
          />

          <YAxis yAxisId="trade" orientation="right" domain={tradeDomain} hide />

          <Tooltip content={<CustomTooltip />} />

          <ReferenceLine
            yAxisId="equity"
            y={0}
            stroke="var(--color-border)"
            strokeDasharray="3 3"
          />

          {/* Deploy date vertical line */}
          {deployDate && (
            <ReferenceLine
              x={deployDate}
              yAxisId="equity"
              stroke="var(--color-accent)"
              strokeDasharray="4 4"
              strokeWidth={1.5}
              label={{
                value: "Deploy",
                position: "insideTopRight",
                fill: "var(--color-accent)",
                fontSize: 11,
              }}
            />
          )}

          {/* Per-trade bars (live only) */}
          <Bar
            yAxisId="trade"
            dataKey="live_r_per_trade"
            opacity={0.35}
            maxBarSize={2}
            barSize={1}
            isAnimationActive={false}
          >
            {displayData.map((entry, index) => (
              <Cell
                key={index}
                fill={
                  (entry.live_r_per_trade ?? 0) >= 0
                    ? "var(--color-profit)"
                    : "var(--color-loss)"
                }
              />
            ))}
          </Bar>

          {/* Backtest curve */}
          <Line
            yAxisId="equity"
            type="monotone"
            dataKey="backtest_r"
            stroke="#9ca3af"
            strokeWidth={1.5}
            strokeDasharray="6 3"
            strokeOpacity={0.7}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />

          {/* Live curve */}
          <Line
            yAxisId="equity"
            type="monotone"
            dataKey="live_r"
            stroke={liveColor}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
