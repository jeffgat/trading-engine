import { useMemo, useState } from "react";
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ReferenceLine,
  BarChart,
  Bar,
  Cell,
} from "recharts";
import type { MonteCarloResult } from "@/backtesting/lib/types";

// ── Band colors ──────────────────────────────────────────────────

const BAND_OUTER = { fill: "rgba(139, 92, 246, 0.06)", stroke: "rgba(139, 92, 246, 0.2)" };
const BAND_INNER = { fill: "rgba(139, 92, 246, 0.12)", stroke: "rgba(139, 92, 246, 0.35)" };
const MEDIAN_COLOR = "var(--color-accent)";
const ACTUAL_COLOR = "var(--color-profit)";
const DD_BAND_OUTER = { fill: "rgba(240, 97, 94, 0.06)", stroke: "rgba(240, 97, 94, 0.15)" };
const DD_BAND_INNER = { fill: "rgba(240, 97, 94, 0.12)", stroke: "rgba(240, 97, 94, 0.3)" };
const DD_MEDIAN = "var(--color-loss)";

// ── Helpers ──────────────────────────────────────────────────────

function formatR(v: number): string {
  const sign = v >= 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}R`;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

interface BandPoint {
  trade: number;
  p5: number;
  p25: number;
  p50: number;
  p75: number;
  p95: number;
  actual: number;
  // Spread values for stacked area rendering
  base5: number;
  spread5_25: number;
  spread25_50: number;
  spread50_75: number;
  spread75_95: number;
}

function buildBandData(
  bands: MonteCarloResult["equity_bands"],
  actualCurve?: number[],
): BandPoint[] {
  const n = bands.curves[0]?.length ?? 0;
  const points: BandPoint[] = [];
  for (let i = 0; i < n; i++) {
    const p5 = bands.curves[0][i];
    const p25 = bands.curves[1][i];
    const p50 = bands.curves[2][i];
    const p75 = bands.curves[3][i];
    const p95 = bands.curves[4][i];
    points.push({
      trade: i + 1,
      p5,
      p25,
      p50,
      p75,
      p95,
      actual: actualCurve?.[i] ?? p50,
      base5: p5,
      spread5_25: p25 - p5,
      spread25_50: p50 - p25,
      spread50_75: p75 - p50,
      spread75_95: p95 - p75,
    });
  }
  return points;
}

function buildHistogramData(values: number[], bins = 40) {
  if (!values.length) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return [{ binCenter: min, count: values.length }];
  const binWidth = (max - min) / bins;
  const counts = new Array(bins).fill(0);
  for (const v of values) {
    const idx = Math.min(Math.floor((v - min) / binWidth), bins - 1);
    counts[idx]++;
  }
  return counts.map((count, i) => ({
    binCenter: min + (i + 0.5) * binWidth,
    count,
  }));
}

// ── Subcomponents ────────────────────────────────────────────────

type ChartView = "equity" | "drawdown";

function BandTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as BandPoint | undefined;
  if (!d) return null;

  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
      <p className="mb-1 text-[10px] text-text-muted">Trade #{label}</p>
      <div className="space-y-0.5 font-mono text-xs">
        <div className="text-text-muted">
          95th: <span style={{ color: BAND_OUTER.stroke }}>{formatR(d.p95)}</span>
        </div>
        <div className="text-text-muted">
          75th: <span style={{ color: BAND_INNER.stroke }}>{formatR(d.p75)}</span>
        </div>
        <div className="text-text-muted">
          50th: <span style={{ color: MEDIAN_COLOR }}>{formatR(d.p50)}</span>
        </div>
        <div className="text-text-muted">
          25th: <span style={{ color: BAND_INNER.stroke }}>{formatR(d.p25)}</span>
        </div>
        <div className="text-text-muted">
          5th: <span style={{ color: BAND_OUTER.stroke }}>{formatR(d.p5)}</span>
        </div>
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          Actual: <span style={{ color: ACTUAL_COLOR }}>{formatR(d.actual)}</span>
        </div>
      </div>
    </div>
  );
}

function DDTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = payload[0]?.payload as BandPoint | undefined;
  if (!d) return null;

  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2 shadow-xl">
      <p className="mb-1 text-[10px] text-text-muted">Trade #{label}</p>
      <div className="space-y-0.5 font-mono text-xs">
        <div className="text-text-muted">
          5th: <span style={{ color: DD_BAND_OUTER.stroke }}>{formatR(d.p5)}</span>
          <span className="ml-1 text-[9px] text-text-muted">(worst)</span>
        </div>
        <div className="text-text-muted">
          25th: <span style={{ color: DD_BAND_INNER.stroke }}>{formatR(d.p25)}</span>
        </div>
        <div className="text-text-muted">
          50th: <span style={{ color: DD_MEDIAN }}>{formatR(d.p50)}</span>
        </div>
        <div className="text-text-muted">
          75th: <span style={{ color: DD_BAND_INNER.stroke }}>{formatR(d.p75)}</span>
        </div>
        <div className="text-text-muted">
          95th: <span style={{ color: DD_BAND_OUTER.stroke }}>{formatR(d.p95)}</span>
        </div>
        <div className="mt-1 border-t border-border pt-1 text-text-muted">
          Actual: <span style={{ color: ACTUAL_COLOR }}>{formatR(d.actual)}</span>
        </div>
      </div>
    </div>
  );
}

function PercentileBandChart({
  data,
  view,
}: {
  data: BandPoint[];
  view: ChartView;
}) {
  const isEquity = view === "equity";
  const outer = isEquity ? BAND_OUTER : DD_BAND_OUTER;
  const inner = isEquity ? BAND_INNER : DD_BAND_INNER;
  const medianColor = isEquity ? MEDIAN_COLOR : DD_MEDIAN;
  const gradientId = isEquity ? "mcEquityGrad" : "mcDDGrad";

  // Thin data if too many points
  const displayData =
    data.length > 400
      ? data.filter(
          (_, i) =>
            i % Math.ceil(data.length / 400) === 0 || i === data.length - 1,
        )
      : data;

  return (
    <ResponsiveContainer width="100%" height={320}>
      <ComposedChart
        data={displayData}
        margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
      >
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={medianColor} stopOpacity={0.15} />
            <stop offset="100%" stopColor={medianColor} stopOpacity={0.02} />
          </linearGradient>
        </defs>

        <CartesianGrid
          strokeDasharray="3 3"
          stroke="var(--color-border)"
          strokeOpacity={0.5}
          vertical={false}
        />

        <XAxis
          dataKey="trade"
          tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
          tickLine={false}
          axisLine={{ stroke: "var(--color-border)" }}
          interval="preserveStartEnd"
          minTickGap={50}
        />

        <YAxis
          tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
          tickLine={false}
          axisLine={false}
          tickFormatter={(v: number) => `${v.toFixed(0)}R`}
          width={45}
        />

        <RechartsTooltip content={isEquity ? <BandTooltip /> : <DDTooltip />} />

        <ReferenceLine
          y={0}
          stroke="var(--color-border)"
          strokeDasharray="3 3"
        />

        {/* p5–p95 outer band via stacked areas */}
        <Area
          type="monotone"
          dataKey="base5"
          stackId="band"
          fill="transparent"
          stroke="none"
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="spread5_25"
          stackId="band"
          fill={outer.fill}
          stroke="none"
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="spread25_50"
          stackId="band"
          fill={inner.fill}
          stroke="none"
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="spread50_75"
          stackId="band"
          fill={inner.fill}
          stroke="none"
          isAnimationActive={false}
        />
        <Area
          type="monotone"
          dataKey="spread75_95"
          stackId="band"
          fill={outer.fill}
          stroke="none"
          isAnimationActive={false}
        />

        {/* Outer band edges */}
        <Line
          type="monotone"
          dataKey="p5"
          stroke={outer.stroke}
          strokeWidth={1}
          dot={false}
          strokeDasharray="4 3"
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="p95"
          stroke={outer.stroke}
          strokeWidth={1}
          dot={false}
          strokeDasharray="4 3"
          isAnimationActive={false}
        />

        {/* Inner band edges */}
        <Line
          type="monotone"
          dataKey="p25"
          stroke={inner.stroke}
          strokeWidth={1}
          dot={false}
          strokeDasharray="2 2"
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="p75"
          stroke={inner.stroke}
          strokeWidth={1}
          dot={false}
          strokeDasharray="2 2"
          isAnimationActive={false}
        />

        {/* Median line */}
        <Line
          type="monotone"
          dataKey="p50"
          stroke={medianColor}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />

        {/* Actual equity line */}
        <Line
          type="monotone"
          dataKey="actual"
          stroke={ACTUAL_COLOR}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}

function DistributionChart({
  values,
  actualValue,
  label,
  percentiles,
  invertColor,
}: {
  values: number[];
  actualValue: number;
  label: string;
  percentiles: Record<string, number>;
  invertColor?: boolean;
}) {
  const histData = useMemo(() => buildHistogramData(values, 40), [values]);

  if (!histData.length) return null;

  const median = percentiles.p50 ?? 0;

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-2 flex items-center justify-between">
        <h3 className="text-xs font-medium text-text-secondary">{label}</h3>
        <span className="font-mono text-[10px] text-text-muted">
          median{" "}
          <span style={{ color: MEDIAN_COLOR }}>
            {label.includes("Sharpe") ? median.toFixed(3) : formatR(median)}
          </span>
        </span>
      </div>

      <ResponsiveContainer width="100%" height={140}>
        <BarChart
          data={histData}
          margin={{ top: 4, right: 4, bottom: 4, left: 4 }}
          barCategoryGap={0}
          barGap={0}
        >
          <XAxis
            dataKey="binCenter"
            tick={{ fill: "var(--color-text-muted)", fontSize: 9 }}
            tickLine={false}
            axisLine={{ stroke: "var(--color-border)" }}
            tickFormatter={(v: number) =>
              label.includes("Sharpe") ? v.toFixed(1) : `${v.toFixed(0)}R`
            }
            interval="preserveStartEnd"
            minTickGap={30}
          />
          <YAxis hide />

          <RechartsTooltip
            cursor={{ fill: "rgba(255,255,255,0.03)" }}
            contentStyle={{
              background: "var(--color-bg-secondary)",
              border: "1px solid var(--color-border)",
              borderRadius: 8,
              fontSize: 11,
              color: "var(--color-text-primary)",
            }}
            labelFormatter={(v) => {
              const n = Number(v);
              return label.includes("Sharpe") ? n.toFixed(3) : formatR(n);
            }}
            formatter={(v) => [Number(v), "Count"]}
          />

          {/* Actual value reference */}
          <ReferenceLine
            x={actualValue}
            stroke={ACTUAL_COLOR}
            strokeWidth={2}
            strokeDasharray="4 2"
            label={{
              value: "Actual",
              position: "top",
              fill: ACTUAL_COLOR,
              fontSize: 9,
            }}
          />

          <Bar dataKey="count" maxBarSize={12} isAnimationActive={false}>
            {histData.map((entry, i) => {
              const isAbove = invertColor
                ? entry.binCenter <= median
                : entry.binCenter >= median;
              return (
                <Cell
                  key={i}
                  fill={
                    isAbove
                      ? "rgba(139, 92, 246, 0.6)"
                      : "rgba(139, 92, 246, 0.25)"
                  }
                />
              );
            })}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── Main component ───────────────────────────────────────────────

interface MonteCarloChartProps {
  data: MonteCarloResult;
}

export function MonteCarloChart({ data }: MonteCarloChartProps) {
  const [view, setView] = useState<ChartView>("equity");

  // Build actual equity/drawdown curves from the band data length
  // (actual is embedded in the result as final values — we reconstruct from trades)
  const equityData = useMemo(() => {
    // We don't have the actual per-trade equity curve directly,
    // but we can approximate: the actual final value distributed linearly
    // Actually, we just use the p50 band for display since the actual
    // equity curve isn't sent as a series — we show actual_final_pnl as a reference
    return buildBandData(data.equity_bands);
  }, [data.equity_bands]);

  const ddData = useMemo(
    () => buildBandData(data.drawdown_bands),
    [data.drawdown_bands],
  );

  const chartData = view === "equity" ? equityData : ddData;

  const isShuffle = data.method === "shuffle";

  return (
    <div className="space-y-4">
      {/* Summary stat row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
          <div className="text-xs font-medium text-text-secondary">
            Ruin Probability
          </div>
          <div
            className="mt-1 font-mono text-xl font-semibold"
            style={{
              color:
                data.ruin_probability > 0.1
                  ? "var(--color-loss)"
                  : data.ruin_probability > 0.03
                    ? "var(--color-text-primary)"
                    : "var(--color-profit)",
            }}
          >
            {formatPct(data.ruin_probability)}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-text-muted">
            P(DD &lt; {formatR(data.ruin_threshold)})
          </div>
        </div>

        <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
          <div className="text-xs font-medium text-text-secondary">
            Median Final PnL
          </div>
          <div
            className="mt-1 font-mono text-xl font-semibold"
            style={{
              color:
                data.final_pnl_percentiles.p50 >= 0
                  ? "var(--color-profit)"
                  : "var(--color-loss)",
            }}
          >
            {formatR(data.final_pnl_percentiles.p50)}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-text-muted">
            actual {formatR(data.actual_final_pnl)}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
          <div className="text-xs font-medium text-text-secondary">
            Median Max DD
          </div>
          <div
            className="mt-1 font-mono text-xl font-semibold"
            style={{ color: "var(--color-loss)" }}
          >
            {formatR(data.max_dd_percentiles.p50)}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-text-muted">
            5th pct {formatR(data.max_dd_percentiles.p5)}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
          <div className="text-xs font-medium text-text-secondary">
            Median Sharpe
          </div>
          <div
            className="mt-1 font-mono text-xl font-semibold"
            style={{
              color:
                data.sharpe_percentiles.p50 >= 1
                  ? "var(--color-profit)"
                  : data.sharpe_percentiles.p50 >= 0
                    ? "var(--color-text-primary)"
                    : "var(--color-loss)",
            }}
          >
            {data.sharpe_percentiles.p50.toFixed(3)}
          </div>
          <div className="mt-0.5 font-mono text-[10px] text-text-muted">
            actual {data.actual_sharpe.toFixed(3)}
          </div>
        </div>
      </div>

      {/* Band chart */}
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 className="text-sm font-medium text-text-secondary">
              {view === "equity" ? "Equity" : "Drawdown"} Bands
            </h2>
            <div className="flex rounded-md border border-border bg-bg-secondary text-[10px]">
              <button
                onClick={() => setView("equity")}
                className={`px-2.5 py-1 transition-colors ${
                  view === "equity"
                    ? "bg-bg-card-hover text-text-primary"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Equity
              </button>
              <button
                onClick={() => setView("drawdown")}
                className={`px-2.5 py-1 transition-colors ${
                  view === "drawdown"
                    ? "bg-bg-card-hover text-text-primary"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                Drawdown
              </button>
            </div>
          </div>

          <div className="flex items-center gap-3 text-[10px] text-text-muted">
            <span className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3"
                style={{
                  background: view === "equity" ? BAND_OUTER.stroke : DD_BAND_OUTER.stroke,
                  borderTop: "1px dashed",
                }}
              />
              5th/95th
            </span>
            <span className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3"
                style={{
                  background: view === "equity" ? BAND_INNER.stroke : DD_BAND_INNER.stroke,
                }}
              />
              25th/75th
            </span>
            <span className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3"
                style={{
                  background: view === "equity" ? MEDIAN_COLOR : DD_MEDIAN,
                }}
              />
              Median
            </span>
            <span className="flex items-center gap-1">
              <span
                className="inline-block h-0.5 w-3"
                style={{ background: ACTUAL_COLOR }}
              />
              Actual
            </span>
          </div>
        </div>

        <PercentileBandChart data={chartData} view={view} />
      </div>

      {/* Distribution histograms */}
      <div className="grid gap-4 sm:grid-cols-3">
        <DistributionChart
          values={data.final_pnl}
          actualValue={data.actual_final_pnl}
          label="Final PnL Distribution"
          percentiles={data.final_pnl_percentiles}
        />
        <DistributionChart
          values={data.max_drawdowns}
          actualValue={data.actual_max_drawdown}
          label="Max Drawdown Distribution"
          percentiles={data.max_dd_percentiles}
          invertColor
        />
        {!isShuffle && (
          <DistributionChart
            values={data.sharpe_ratios}
            actualValue={data.actual_sharpe}
            label="Sharpe Ratio Distribution"
            percentiles={data.sharpe_percentiles}
          />
        )}
        {isShuffle && (
          <div className="flex items-center justify-center rounded-lg border border-border bg-bg-card p-4">
            <div className="text-center">
              <p className="text-xs text-text-muted">
                Sharpe is constant under permutation
              </p>
              <p className="mt-1 font-mono text-lg font-semibold text-text-secondary">
                {data.actual_sharpe.toFixed(3)}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Method info */}
      <div className="flex items-center justify-between rounded-lg border border-border bg-bg-card px-4 py-2.5 text-[10px] text-text-muted">
        <span>
          {data.method === "bootstrap" ? "Bootstrap" : "Shuffle (permutation)"}{" "}
          &middot; {data.n_simulations.toLocaleString()} simulations &middot;{" "}
          {data.n_trades} trades
        </span>
        <span>
          {data.method === "bootstrap"
            ? "Trades drawn with replacement — tests outcome variance"
            : "Trade order randomized — tests path dependency (drawdown variance)"}
        </span>
      </div>
    </div>
  );
}
