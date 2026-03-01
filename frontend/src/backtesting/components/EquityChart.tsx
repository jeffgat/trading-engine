import { useMemo } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { EquityCurvePoint } from "@/backtesting/lib/types";

interface EquityChartProps {
  data: EquityCurvePoint[];
  riskUsd: number;
}

interface RPoint {
  date: string;
  r_cumulative: number;
  r_per_trade: number;
}

function formatR(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}R`;
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const equity = payload.find((p: any) => p.dataKey === "r_cumulative");
  const trade = payload.find((p: any) => p.dataKey === "r_per_trade");

  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted">{label}</p>
      {equity && (
        <p className="font-mono text-sm font-semibold" style={{ color: "var(--color-profit)" }}>
          Equity: {formatR(equity.value)}
        </p>
      )}
      {trade && (
        <p
          className="font-mono text-xs"
          style={{ color: trade.value >= 0 ? "var(--color-profit)" : "var(--color-loss)" }}
        >
          Trade: {formatR(trade.value)}
        </p>
      )}
    </div>
  );
}

export function EquityChart({ data, riskUsd }: EquityChartProps) {
  const rData: RPoint[] = useMemo(
    () =>
      data.map((d) => ({
        date: d.date,
        r_cumulative: d.pnl_cumulative / riskUsd,
        r_per_trade: d.pnl_per_trade / riskUsd,
      })),
    [data, riskUsd],
  );

  if (!data.length) {
    return (
      <div className="flex h-[400px] items-center justify-center text-text-muted">
        No equity data
      </div>
    );
  }

  const finalR = rData[rData.length - 1].r_cumulative;
  const isPositive = finalR >= 0;

  // Scale trade axis to ~10% of chart height
  const maxAbsTrade = rData.reduce((m, d) => Math.max(m, Math.abs(d.r_per_trade)), 0) || 0.01;
  const tradeDomain = [-maxAbsTrade * 10, maxAbsTrade * 10];

  // Thin the data for rendering if too many points (>300)
  const displayData =
    rData.length > 300
      ? rData.filter((_, i) => i % Math.ceil(rData.length / 300) === 0 || i === rData.length - 1)
      : rData;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">Equity Curve (R)</h2>
        <span
          className="rounded-md px-2.5 py-1 font-mono text-sm font-semibold"
          style={{
            color: isPositive ? "var(--color-profit)" : "var(--color-loss)",
            background: isPositive ? "rgba(61, 214, 140, 0.12)" : "rgba(240, 97, 94, 0.12)",
          }}
        >
          {formatR(finalR)}
        </span>
      </div>

      <ResponsiveContainer width="100%" height={380}>
        <ComposedChart data={displayData} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--color-profit)" stopOpacity={0.2} />
              <stop offset="100%" stopColor="var(--color-profit)" stopOpacity={0.01} />
            </linearGradient>
          </defs>

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

          <YAxis
            yAxisId="trade"
            orientation="right"
            domain={tradeDomain}
            hide
          />

          <Tooltip content={<CustomTooltip />} />

          <ReferenceLine yAxisId="equity" y={0} stroke="var(--color-border)" strokeDasharray="3 3" />

          <Bar
            yAxisId="trade"
            dataKey="r_per_trade"
            opacity={0.35}
            maxBarSize={2}
            barSize={1}
            isAnimationActive={false}
          >
            {displayData.map((entry, index) => (
              <Cell
                key={index}
                fill={entry.r_per_trade >= 0 ? "var(--color-profit)" : "var(--color-loss)"}
              />
            ))}
          </Bar>

          <Area
            yAxisId="equity"
            type="monotone"
            dataKey="r_cumulative"
            stroke="var(--color-profit)"
            strokeWidth={2}
            fill="url(#equityGradient)"
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
