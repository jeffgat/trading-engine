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
import type { EquityCurvePoint } from "../lib/types";
import { formatCurrency } from "../lib/utils";

interface EquityChartProps {
  data: EquityCurvePoint[];
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;

  const equity = payload.find((p: any) => p.dataKey === "pnl_cumulative");
  const trade = payload.find((p: any) => p.dataKey === "pnl_per_trade");

  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
      <p className="text-xs text-text-muted">{label}</p>
      {equity && (
        <p className="font-mono text-sm font-semibold" style={{ color: "var(--color-profit)" }}>
          Equity: {formatCurrency(equity.value)}
        </p>
      )}
      {trade && (
        <p
          className="font-mono text-xs"
          style={{ color: trade.value >= 0 ? "var(--color-profit)" : "var(--color-loss)" }}
        >
          Trade: {formatCurrency(trade.value)}
        </p>
      )}
    </div>
  );
}

export function EquityChart({ data }: EquityChartProps) {
  if (!data.length) {
    return (
      <div className="flex h-[400px] items-center justify-center text-text-muted">
        No equity data
      </div>
    );
  }

  const finalValue = data[data.length - 1].pnl_cumulative;
  const isPositive = finalValue >= 0;

  // Scale trade axis to ~10% of chart height
  const maxAbsTrade = data.reduce((m, d) => Math.max(m, Math.abs(d.pnl_per_trade)), 0) || 1;
  const tradeDomain = [-maxAbsTrade * 10, maxAbsTrade * 10];

  // Thin the data for rendering if too many points (>300)
  const displayData =
    data.length > 300
      ? data.filter((_, i) => i % Math.ceil(data.length / 300) === 0 || i === data.length - 1)
      : data;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">Equity Curve</h2>
        <span
          className="rounded-md px-2.5 py-1 font-mono text-sm font-semibold"
          style={{
            color: isPositive ? "var(--color-profit)" : "var(--color-loss)",
            background: isPositive ? "rgba(61, 214, 140, 0.12)" : "rgba(240, 97, 94, 0.12)",
          }}
        >
          {formatCurrency(finalValue)}
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
            tickFormatter={(v: number) => `$${(v / 1000).toFixed(0)}k`}
            width={55}
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
            dataKey="pnl_per_trade"
            opacity={0.35}
            maxBarSize={2}
            barSize={1}
            isAnimationActive={false}
          >
            {displayData.map((entry, index) => (
              <Cell
                key={index}
                fill={entry.pnl_per_trade >= 0 ? "var(--color-profit)" : "var(--color-loss)"}
              />
            ))}
          </Bar>

          <Area
            yAxisId="equity"
            type="monotone"
            dataKey="pnl_cumulative"
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
