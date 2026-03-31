import { useEffect, useRef, useState } from "react";
import {
  createChart,
  createSeriesMarkers,
  BaselineSeries,
  CandlestickSeries,
  CrosshairMode,
  LineStyle,
  type IChartApi,
  type BaselineSeriesOptions,
  type CandlestickSeriesOptions,
  type Time,
} from "lightweight-charts";
import type { Trade, CandleBar } from "@/backtesting/lib/types";
import { formatCurrency, formatR, pnlColor } from "@/backtesting/lib/utils";
import { SessionTag } from "./SessionTag";
import { Skeleton } from "./Skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

const EXIT_LABELS: Record<string, string> = {
  tp1_tp2: "tp1+tp2",
  tp1_flat: "tp1+flat",
  tp1_be: "tp1+be",
  stop: "sl",
  flat: "flat",
  no_fill: "no fill",
};

interface TradeChartModalProps {
  trade: Trade | null;
  instrument: string;
  riskUsd: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function TradeChartModal({
  trade,
  instrument,
  riskUsd,
  open,
  onOpenChange,
}: TradeChartModalProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [timeframe, setTimeframe] = useState<"1m" | "5m">("5m");

  // Fetch candles when the dialog opens with a trade
  useEffect(() => {
    if (!trade || !open) return;

    setLoading(true);
    setError(null);
    setCandles([]);

    const params = new URLSearchParams({
      instrument,
      date: trade.date,
      session: trade.session,
      timeframe,
    });
    if (trade.lsi_sweep_time) {
      params.set("sweep_time", trade.lsi_sweep_time);
    }

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
  }, [trade?.date, trade?.session, instrument, open, timeframe]);

  // Create/destroy chart when candles arrive
  useEffect(() => {
    if (!chartContainerRef.current || !candles.length || !trade) return;

    const container = chartContainerRef.current;

    // Clear any residual Lightweight Charts DOM before creating a new instance
    container.innerHTML = "";

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { color: "#1c1c21" },
        textColor: "#a0a0ab",
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#242429" },
        horzLines: { color: "#242429" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
        borderColor: "#2c2c33",
      },
      rightPriceScale: {
        borderColor: "#2c2c33",
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#3dd68c",
      downColor: "#f0615e",
      borderUpColor: "#3dd68c",
      borderDownColor: "#f0615e",
      wickUpColor: "#3dd68c",
      wickDownColor: "#f0615e",
    } satisfies Partial<CandlestickSeriesOptions>);

    // Convert ISO timestamps to Unix seconds for lightweight-charts.
    // The API returns Eastern time (e.g. "2025-12-18T20:00:00-05:00").
    // lightweight-charts treats UTCTimestamp as UTC, so we extract the
    // Eastern wall-clock components and fake them as UTC so the x-axis
    // displays Eastern time directly.
    const toFakeUtcSeconds = (isoTimestamp: string): number => {
      const d = new Date(isoTimestamp);
      const parts = d.toLocaleString("en-US", {
        timeZone: "America/New_York",
        year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit",
        hour12: false,
      }).split(/[/,: ]+/);
      return Date.UTC(
        +parts[2], +parts[0] - 1, +parts[1],
        +parts[3], +parts[4], +parts[5],
      ) / 1000;
    };

    const chartData = candles.map((c) => ({
      time: toFakeUtcSeconds(c.time) as unknown as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    series.setData(chartData);

    // Pin the Y-axis to the trade zone so large intraday moves (e.g. GC)
    // don't compress the entry/stop/TP levels into a tiny band at the top.
    const levels = [trade.stop_price, trade.entry_price, trade.tp1_price, trade.tp2_price];
    if (trade.lsi_fvg_top) levels.push(trade.lsi_fvg_top);
    if (trade.lsi_fvg_bottom) levels.push(trade.lsi_fvg_bottom);
    if (trade.lsi_swept_level) levels.push(trade.lsi_swept_level);
    const zoneLow = Math.min(...levels);
    const zoneHigh = Math.max(...levels);
    const zonePad = (zoneHigh - zoneLow) * 3;
    series.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: { minValue: zoneLow - zonePad, maxValue: zoneHigh + zonePad },
        margins: { above: 0.1, below: 0.1 },
      }),
    });

    // Add price lines for trade levels
    series.createPriceLine({
      price: trade.entry_price,
      color: "#22d3ee",
      lineWidth: 1,
      lineStyle: LineStyle.Solid,
      axisLabelVisible: true,
      title: "Entry",
    });

    series.createPriceLine({
      price: trade.stop_price,
      color: "#f0615e",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Stop",
    });

    series.createPriceLine({
      price: trade.tp1_price,
      color: "#3dd68c",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "TP1",
    });

    series.createPriceLine({
      price: trade.tp2_price,
      color: "#2a9962",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "TP2",
    });

    // LSI overlay: swept liquidity level (amber dashed horizontal line)
    if (trade.lsi_swept_level) {
      series.createPriceLine({
        price: trade.lsi_swept_level,
        color: "#f59e0b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Swept",
      });
    }

    // LSI overlay: FVG inversion zone rectangle
    // BaselineSeries fills from lsi_fvg_bottom (baseValue) to lsi_fvg_top (data line)
    // over the time range [lsi_fvg_time, entry_time]
    let fvgZoneSeries: ReturnType<IChartApi["addSeries"]> | null = null;
    if (trade.lsi_fvg_top && trade.lsi_fvg_bottom && trade.lsi_fvg_time) {
      fvgZoneSeries = chart.addSeries(BaselineSeries, {
        baseValue: { type: "price", price: trade.lsi_fvg_bottom },
        topFillColor1: "rgba(139, 92, 246, 0.3)",
        topFillColor2: "rgba(139, 92, 246, 0.15)",
        topLineColor: "rgba(139, 92, 246, 0.8)",
        bottomFillColor1: "rgba(0, 0, 0, 0)",
        bottomFillColor2: "rgba(0, 0, 0, 0)",
        bottomLineColor: "rgba(0, 0, 0, 0)",
        lineWidth: 1,
        crosshairMarkerVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
      } satisfies Partial<BaselineSeriesOptions>);
    }

    // Fallback: approximate entry/exit times from candle data when
    // timestamps are missing (old backtests stored before fill_time was added).
    let entryTime = trade.entry_time;
    let exitTime = trade.exit_time;

    if (!entryTime && trade.exit_type !== "no_fill") {
      const isLong = trade.direction === "long";
      for (const c of candles) {
        // Long limit buy fills when low <= entry; short limit sell fills when high >= entry
        if (isLong ? c.low <= trade.entry_price : c.high >= trade.entry_price) {
          entryTime = c.time;
          break;
        }
      }
    }

    if (!exitTime && entryTime && trade.exit_type !== "no_fill") {
      const isLong = trade.direction === "long";
      const entryTs = new Date(entryTime).getTime();
      const barsAfterEntry = candles.filter((c) => new Date(c.time).getTime() >= entryTs);

      if (trade.exit_type === "flat") {
        // Flat = last candle in session
        exitTime = candles[candles.length - 1]?.time;
      } else if (trade.exit_type === "stop") {
        // Stop hit: first bar after entry where price crosses stop
        for (const c of barsAfterEntry) {
          if (isLong ? c.low <= trade.stop_price : c.high >= trade.stop_price) {
            exitTime = c.time;
            break;
          }
        }
      } else {
        // TP-based exits: find first bar after entry where price crosses TP2 (or TP1)
        const tpPrice = trade.tp2_price;
        for (const c of barsAfterEntry) {
          if (isLong ? c.high >= tpPrice : c.low <= tpPrice) {
            exitTime = c.time;
            break;
          }
        }
        // Fallback for tp1_be / tp1_flat: check if TP2 wasn't hit, scan for BE/flat
        if (!exitTime) {
          if (trade.exit_type === "tp1_be") {
            for (const c of barsAfterEntry) {
              if (isLong ? c.low <= trade.entry_price : c.high >= trade.entry_price) {
                exitTime = c.time;
                break;
              }
            }
          } else if (trade.exit_type === "tp1_flat") {
            exitTime = candles[candles.length - 1]?.time;
          }
        }
      }
    }

    // Set FVG zone data now that entryTime is resolved
    if (fvgZoneSeries && trade.lsi_fvg_time && trade.lsi_fvg_top) {
      const fvgStart = toFakeUtcSeconds(trade.lsi_fvg_time) as unknown as Time;
      // Extend the zone to entry time (or slightly beyond the last candle if no fill)
      const zoneEnd = entryTime
        ? (toFakeUtcSeconds(entryTime) as unknown as Time)
        : (toFakeUtcSeconds(candles[candles.length - 1].time) as unknown as Time);
      fvgZoneSeries.setData([
        { time: fvgStart, value: trade.lsi_fvg_top },
        { time: zoneEnd, value: trade.lsi_fvg_top },
      ]);
    }

    // Entry/exit arrow markers
    const markers: {
      time: Time;
      position: "belowBar" | "aboveBar";
      color: string;
      shape: "arrowUp" | "arrowDown";
      text: string;
    }[] = [];

    // Sweep marker (add before entry/exit so it sorts correctly)
    if (trade.lsi_sweep_time) {
      const sweepTimeSeconds = toFakeUtcSeconds(trade.lsi_sweep_time);
      // Find candle closest to sweep time for position
      const sweepCandle = chartData.find(
        (c) => Math.abs((c.time as number) - sweepTimeSeconds) < 300
      );
      if (sweepCandle) {
        markers.push({
          time: sweepCandle.time,
          position: trade.direction === "long" ? "aboveBar" : "belowBar",
          color: "#f59e0b",
          shape: trade.direction === "long" ? "arrowDown" : "arrowUp",
          text: "Sweep",
        });
      }
    }

    if (entryTime) {
      const isLong = trade.direction === "long";
      markers.push({
        time: toFakeUtcSeconds(entryTime) as unknown as Time,
        position: isLong ? "belowBar" : "aboveBar",
        color: "#22d3ee",
        shape: isLong ? "arrowUp" : "arrowDown",
        text: isLong ? "Buy" : "Sell",
      });
    }

    if (exitTime) {
      const isLong = trade.direction === "long";
      const isWin = trade.pnl_usd >= 0;
      const exitLabel =
        EXIT_LABELS[trade.exit_type] ?? trade.exit_type;
      markers.push({
        time: toFakeUtcSeconds(exitTime) as unknown as Time,
        position: isLong ? "aboveBar" : "belowBar",
        color: isWin ? "#3dd68c" : "#f0615e",
        shape: isLong ? "arrowDown" : "arrowUp",
        text: exitLabel,
      });
    }

    if (markers.length > 0) {
      markers.sort(
        (a, b) => (a.time as number) - (b.time as number),
      );
      createSeriesMarkers(series, markers);
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    // Resize observer for responsive chart
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
  }, [candles, trade]);

  if (!trade) return null;

  const rMultiple = Number.isFinite(trade.r_multiple) ? trade.r_multiple : trade.pnl_usd / riskUsd;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) setTimeframe("5m"); onOpenChange(o); }}>
      <DialogContent
        className="max-h-[85vh] overflow-hidden"
        style={{ maxWidth: "80vw", width: "80vw" }}
      >
        <DialogHeader>
          <DialogTitle>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-text-primary">
                  {trade.date}
                </span>
                <SessionTag session={trade.session} />
                <span
                  className="text-xs font-medium"
                  style={{
                    color:
                      trade.direction === "long"
                        ? "var(--color-profit)"
                        : "var(--color-loss)",
                  }}
                >
                  {trade.direction.toUpperCase()}
                </span>
                <span className="text-xs text-text-muted">
                  {EXIT_LABELS[trade.exit_type] ?? trade.exit_type}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className="font-mono text-sm font-semibold"
                  style={{ color: pnlColor(trade.pnl_usd) }}
                >
                  {formatCurrency(trade.pnl_usd)}
                </span>
                <span
                  className="font-mono text-xs"
                  style={{ color: pnlColor(trade.pnl_usd) }}
                >
                  {formatR(rMultiple)}
                </span>
              </div>
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
          {loading && <Skeleton className="h-[500px] rounded-lg" />}

          {error && (
            <div className="flex h-[500px] items-center justify-center rounded-lg border border-loss/30 bg-loss/5">
              <span className="text-xs text-loss">{error}</span>
            </div>
          )}

          {!loading && !error && candles.length === 0 && (
            <div className="flex h-[500px] items-center justify-center text-text-muted">
              No candle data available
            </div>
          )}

          <div
            ref={chartContainerRef}
            className={candles.length > 0 && !loading && !error ? "" : "hidden"}
          />

          {/* Price level legend */}
          {candles.length > 0 && !loading && !error && (
            <div className="mt-3 flex items-center gap-5 text-xs text-text-secondary">
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#22d3ee" }}
                />
                <span style={{ color: "#22d3ee" }}>
                  {trade.direction === "long" ? "\u25B2" : "\u25BC"}
                </span>
                Entry:{" "}
                {trade.entry_price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#f0615e" }}
                />
                Stop:{" "}
                {trade.stop_price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#3dd68c" }}
                />
                TP1:{" "}
                {trade.tp1_price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3"
                  style={{ background: "#2a9962" }}
                />
                TP2:{" "}
                {trade.tp2_price.toLocaleString("en-US", {
                  minimumFractionDigits: 2,
                })}
              </span>
              {trade.exit_time && (
                <span className="flex items-center gap-1.5">
                  <span
                    style={{
                      color: trade.pnl_usd >= 0 ? "#3dd68c" : "#f0615e",
                    }}
                  >
                    {trade.direction === "long" ? "\u25BC" : "\u25B2"}
                  </span>
                  Exit:{" "}
                  {EXIT_LABELS[trade.exit_type] ?? trade.exit_type}
                </span>
              )}
              {trade.lsi_swept_level ? (
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-0.5 w-3 border-t border-dashed"
                    style={{ borderColor: "#f59e0b" }}
                  />
                  Swept:{" "}
                  {trade.lsi_swept_level.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}
                </span>
              ) : null}
              {trade.lsi_fvg_top && trade.lsi_fvg_bottom ? (
                <span className="flex items-center gap-1.5">
                  <span
                    className="inline-block h-3 w-3 rounded-sm border"
                    style={{
                      background: "rgba(139, 92, 246, 0.25)",
                      borderColor: "rgba(139, 92, 246, 0.7)",
                    }}
                  />
                  FVG:{" "}
                  {trade.lsi_fvg_bottom.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}
                  {" – "}
                  {trade.lsi_fvg_top.toLocaleString("en-US", {
                    minimumFractionDigits: 2,
                  })}
                </span>
              ) : null}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
