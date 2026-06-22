import { useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type CandlestickSeriesOptions,
  type Time,
} from "lightweight-charts";
import type { ExecTradeContext } from "@/execution/lib/types";
import { SessionTag } from "./SessionTag";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

interface ExecTradeChartModalProps {
  tradeContext: ExecTradeContext | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ExecTradeChartModal({
  tradeContext: ctx,
  open,
  onOpenChange,
}: ExecTradeChartModalProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const [candles, setCandles] = useState<
    { time: string; open: number; high: number; low: number; close: number }[]
  >([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<"1m" | "5m">("1m");

  // Fetch candles when the dialog opens
  useEffect(() => {
    if (!ctx || !open) return;

    setLoading(true);
    setError(null);
    setCandles([]);

    const params = new URLSearchParams({
      instrument: ctx.instrument,
      date: ctx.date,
      session: ctx.session,
      timeframe,
    });

    fetch(`/bt-api/candles?${params}`)
      .then((res) => {
        if (!res.ok)
          return res.json().then((e) => {
            throw new Error(e.error?.reason ?? e.detail ?? `HTTP ${res.status}`);
          });
        return res.json();
      })
      .then((data) => setCandles(data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [ctx?.instrument, ctx?.date, ctx?.session, open, timeframe]);

  // Create/destroy chart when candles arrive
  useEffect(() => {
    if (!chartContainerRef.current || !candles.length || !ctx) return;

    const container = chartContainerRef.current;
    container.innerHTML = "";

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { color: "#101010" },
        textColor: "#ccb088",
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#3a3026" },
        horzLines: { color: "#3a3026" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "#3a3026",
      },
      rightPriceScale: {
        borderColor: "#3a3026",
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#ecc997",
      downColor: "#d4775f",
      borderUpColor: "#ecc997",
      borderDownColor: "#d4775f",
      wickUpColor: "#ecc997",
      wickDownColor: "#d4775f",
    } satisfies Partial<CandlestickSeriesOptions>);

    // Convert ISO timestamps to fake UTC seconds for lightweight-charts
    // (displays Eastern wall-clock time on x-axis)
    const toFakeUtcSeconds = (isoTimestamp: string): number => {
      const d = new Date(isoTimestamp);
      const parts = d
        .toLocaleString("en-US", {
          timeZone: "America/New_York",
          year: "numeric",
          month: "2-digit",
          day: "2-digit",
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
        })
        .split(/[/,: ]+/);
      return (
        Date.UTC(
          +parts[2],
          +parts[0] - 1,
          +parts[1],
          +parts[3],
          +parts[4],
          +parts[5],
        ) / 1000
      );
    };

    const chartData = candles.map((c) => ({
      time: toFakeUtcSeconds(c.time) as unknown as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    series.setData(chartData);

    // Pin Y-axis to trade zone
    const levels = [ctx.stop, ctx.entry, ctx.tp1, ctx.tp2];
    const zoneLow = Math.min(...levels);
    const zoneHigh = Math.max(...levels);
    const zonePad = (zoneHigh - zoneLow) * 3;
    series.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: {
          minValue: zoneLow - zonePad,
          maxValue: zoneHigh + zonePad,
        },
        margins: { above: 0.1, below: 0.1 },
      }),
    });

    // Price lines
    series.createPriceLine({
      price: ctx.entry,
      color: "#e8c088",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "Entry",
    });

    series.createPriceLine({
      price: ctx.stop,
      color: "#d4775f",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Stop",
    });

    series.createPriceLine({
      price: ctx.tp1,
      color: "#ecc997",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "TP1",
    });

    series.createPriceLine({
      price: ctx.tp2,
      color: "#2f9f54",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "TP2",
    });

    // Entry arrow marker — find the candle where the limit fill occurs
    const isLong = ctx.direction === "long";
    let entryBarTime: Time | null = null;
    for (let i = 0; i < chartData.length; i++) {
      const bar = candles[i];
      if (isLong ? bar.low <= ctx.entry : bar.high >= ctx.entry) {
        entryBarTime = chartData[i].time;
        break;
      }
    }

    if (entryBarTime) {
      createSeriesMarkers(series, [
        {
          time: entryBarTime,
          position: isLong ? "belowBar" : "aboveBar",
          color: "#e8c088",
          shape: isLong ? "arrowUp" : "arrowDown",
          text: isLong ? "Buy" : "Sell",
        },
      ]);
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    // Responsive resize
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    observer.observe(container);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, ctx]);

  if (!ctx) return null;

  const fmtPrice = (n: number) =>
    n.toLocaleString("en-US", { minimumFractionDigits: 2 });

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setTimeframe("1m");
        onOpenChange(o);
      }}
    >
      <DialogContent
        className="max-h-[85vh] overflow-hidden"
        style={{ maxWidth: "80vw", width: "80vw" }}
      >
        <DialogHeader>
          <DialogTitle>
            <div className="flex items-center gap-3">
              <span className="text-sm font-medium text-text-primary">
                {ctx.date}
              </span>
              <SessionTag session={ctx.session} />
              <span
                className="text-xs font-medium"
                style={{
                  color:
                    ctx.direction === "long"
                      ? "var(--color-profit)"
                      : "var(--color-loss)",
                }}
              >
                {ctx.direction.toUpperCase()}
              </span>
            </div>
          </DialogTitle>
        </DialogHeader>

        {/* Timeframe toggle */}
        <div className="flex justify-end">
          <div className="flex rounded-md overflow-hidden border border-border-subtle text-xs">
            {(["1m", "5m"] as const).map((tf) => (
              <button
                key={tf}
                onClick={() => setTimeframe(tf)}
                className={`px-2.5 py-1 font-mono transition-colors ${
                  timeframe === tf
                    ? "bg-accent/20 text-accent"
                    : "text-text-muted hover:text-text-secondary hover:bg-bg-card-hover"
                }`}
              >
                {tf}
              </button>
            ))}
          </div>
        </div>

        {/* Chart area */}
        <div className="mt-2">
          {loading && (
            <div className="flex h-[500px] items-center justify-center rounded-lg bg-bg-card-hover animate-pulse">
              <span className="text-xs text-text-muted">Loading candles...</span>
            </div>
          )}

          {error && (
            <div className="flex h-[500px] items-center justify-center rounded-lg border border-loss/30 bg-loss/5">
              <span className="text-xs text-loss">{error}</span>
            </div>
          )}

          {!loading && !error && candles.length === 0 && open && ctx && (
            <div className="flex h-[500px] items-center justify-center text-text-muted">
              No candle data available
            </div>
          )}

          <div
            ref={chartContainerRef}
            className={
              candles.length > 0 && !loading && !error ? "" : "hidden"
            }
          />

          {/* Price level legend */}
          {candles.length > 0 && !loading && !error && (
            <div className="mt-3 flex items-center gap-5 text-xs text-text-secondary">
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#e8c088" }}
                />
                <span style={{ color: "#e8c088" }}>
                  {ctx.direction === "long" ? "\u25B2" : "\u25BC"}
                </span>
                Entry: {fmtPrice(ctx.entry)}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#d4775f" }}
                />
                Stop: {fmtPrice(ctx.stop)}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#ecc997" }}
                />
                TP1: {fmtPrice(ctx.tp1)}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#2f9f54" }}
                />
                TP2: {fmtPrice(ctx.tp2)}
              </span>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
