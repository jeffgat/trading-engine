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
import type { NewsStraddleEvent, CandleBar } from "@/backtesting/lib/types";
import { formatNumber, pnlColor } from "@/backtesting/lib/utils";
import { Skeleton } from "./Skeleton";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/shared/ui/dialog";

const EXIT_LABELS: Record<string, string> = {
  target: "Target",
  stop_loss: "Stop Loss",
  eow: "End of Window",
  no_fill: "No Fill",
};

const EVENT_LABELS: Record<string, string> = {
  NFP: "NFP",
  CPI: "CPI",
  PPI: "PPI",
  FOMC: "FOMC",
  NY_OPEN: "NY Open",
};

const EVENT_BADGE_CLASSES: Record<string, string> = {
  NFP: "bg-info/20 text-info",
  CPI: "bg-accent/20 text-accent",
  PPI: "bg-warning/20 text-warning",
  FOMC: "bg-loss/20 text-loss",
  NY_OPEN: "bg-profit/20 text-profit",
};

interface NewsTradeChartModalProps {
  event: NewsStraddleEvent | null;
  instrument: string;
  observationWindowSeconds: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function NewsTradeChartModal({
  event,
  instrument,
  observationWindowSeconds,
  open,
  onOpenChange,
}: NewsTradeChartModalProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const [candles, setCandles] = useState<CandleBar[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch 1s candles when dialog opens
  useEffect(() => {
    if (!event || !open) return;

    setLoading(true);
    setError(null);
    setCandles([]);

    // Compute tight time window around the trade
    const secondsBefore = 1;
    let secondsAfter: number;
    if (!event.direction_filled) {
      // No fill — just show a few seconds after release
      secondsAfter = 10;
    } else if (event.exit_type === "target" && event.time_to_target_seconds != null) {
      secondsAfter = event.seconds_to_fill + event.time_to_target_seconds + 5;
    } else {
      // stop_loss or eow — use fill time + observation window as upper bound
      secondsAfter = event.seconds_to_fill + observationWindowSeconds + 5;
    }

    const params = new URLSearchParams({
      instrument,
      date: event.date,
      seconds_before: String(secondsBefore),
      seconds_after: String(secondsAfter),
      event_type: event.event_type,
    });

    fetch(`/bt-api/news-candles?${params}`)
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
  }, [event?.date, event?.event_type, instrument, observationWindowSeconds, open]);

  // Create chart when candles arrive
  useEffect(() => {
    if (!chartContainerRef.current || !candles.length || !event) return;

    const container = chartContainerRef.current;

    // Clear any residual Lightweight Charts DOM before creating a new instance
    container.innerHTML = "";

    const { chart, observer } = buildChart(container, event, candles);
    chartRef.current = chart;

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [candles, event]);

  const formatEventTypeLabel = (eventType: string) => EVENT_LABELS[eventType] ?? eventType;
  const eventBadgeClass = (eventType: string) =>
    EVENT_BADGE_CLASSES[eventType] ?? "bg-accent/20 text-accent";

  function buildChart(container: HTMLDivElement, event: NewsStraddleEvent, candles: CandleBar[]) {
    container.innerHTML = "";

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 500,
      layout: {
        background: { color: "#050909" },
        textColor: "#a1adab",
        fontFamily: '"JetBrains Mono", monospace',
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "rgba(29,52,52,0.76)" },
        horzLines: { color: "rgba(29,52,52,0.72)" },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: {
        timeVisible: true,
        secondsVisible: true,
        borderColor: "rgba(29,52,52,0.95)",
      },
      rightPriceScale: {
        borderColor: "rgba(29,52,52,0.95)",
      },
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#72f25f",
      downColor: "#ff554f",
      borderUpColor: "#72f25f",
      borderDownColor: "#ff554f",
      wickUpColor: "#72f25f",
      wickDownColor: "#ff554f",
    } satisfies Partial<CandlestickSeriesOptions>);

    // Convert ISO timestamps to fake-UTC seconds so lightweight-charts
    // displays Eastern wall-clock time.
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
          +parts[5]
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

    // Price levels
    const refPrice = event.reference_price;
    const stopBuy = refPrice + event.buffer_points;
    const stopSell = refPrice - event.buffer_points;

    // Reference price
    series.createPriceLine({
      price: refPrice,
      color: "#a1adab",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      axisLabelVisible: true,
      title: "Ref",
    });

    // Stop-buy level
    series.createPriceLine({
      price: stopBuy,
      color: "#72f25f",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Stop Buy",
    });

    // Stop-sell level
    series.createPriceLine({
      price: stopSell,
      color: "#ff554f",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: "Stop Sell",
    });

    // If filled, show fill price + target/stop levels
    if (event.direction_filled && event.fill_price) {
      const isLong = event.direction_filled === "long";

      series.createPriceLine({
        price: event.fill_price,
        color: "#35d6e6",
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: "Fill",
      });

      // Target level
      const targetPrice = isLong
        ? event.fill_price + event.target_points
        : event.fill_price - event.target_points;
      series.createPriceLine({
        price: targetPrice,
        color: "#f8c159",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        axisLabelVisible: true,
        title: "Target",
      });
    }

    // Pin Y-axis to the trade zone
    const levels = [refPrice, stopBuy, stopSell];
    if (event.fill_price) {
      levels.push(event.fill_price);
      const isLong = event.direction_filled === "long";
      levels.push(
        isLong
          ? event.fill_price + event.target_points
          : event.fill_price - event.target_points
      );
    }
    const zoneLow = Math.min(...levels);
    const zoneHigh = Math.max(...levels);
    const zonePad = (zoneHigh - zoneLow) * 1.5;
    series.applyOptions({
      autoscaleInfoProvider: () => ({
        priceRange: {
          minValue: zoneLow - zonePad,
          maxValue: zoneHigh + zonePad,
        },
        margins: { above: 0.1, below: 0.1 },
      }),
    });

    // Arrow markers
    const markers: {
      time: Time;
      position: "belowBar" | "aboveBar";
      color: string;
      shape: "arrowUp" | "arrowDown";
      text: string;
    }[] = [];

    // Find the release bar marker
    // Build release time as fake-UTC seconds directly (Eastern wall-clock)
    const releaseDateStr = event.date; // YYYY-MM-DD
    const [ry, rm, rd] = releaseDateStr.split("-").map(Number);
    const releaseHour = event.event_type === "NY_OPEN" ? 9 : event.event_type === "FOMC" ? 14 : 8;
    const releaseMinute = event.event_type === "FOMC" ? 0 : 30;
    const releaseSeconds = Date.UTC(ry, rm - 1, rd, releaseHour, releaseMinute, 0) / 1000;
    const releaseCandle = chartData.find((c) =>
      Math.abs((c.time as number) - releaseSeconds) < 2
    );
    if (releaseCandle) {
      markers.push({
        time: releaseCandle.time,
        position: "aboveBar",
        color: "#f8c159",
        shape: "arrowDown",
        text:
          event.event_type === "NY_OPEN"
            ? "OPEN"
            : event.event_type === "FOMC"
              ? "FOMC"
              : "NEWS",
      });
    }

    // Fill marker
    if (event.direction_filled && event.seconds_to_fill >= 0) {
      const fillSeconds = event.seconds_to_fill;
      const fillTarget = releaseSeconds + fillSeconds;
      const fillCandle = chartData.find(
        (c) => Math.abs((c.time as number) - fillTarget) < 2
      );
      if (fillCandle) {
        const isLong = event.direction_filled === "long";
        markers.push({
          time: fillCandle.time,
          position: isLong ? "belowBar" : "aboveBar",
          color: "#35d6e6",
          shape: isLong ? "arrowUp" : "arrowDown",
          text: isLong ? "Buy" : "Sell",
        });
      }
    }

    if (markers.length > 0) {
      markers.sort((a, b) => (a.time as number) - (b.time as number));
      createSeriesMarkers(series, markers);
    }

    chart.timeScale().fitContent();

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    observer.observe(container);

    return { chart, observer };
  }

  if (!event) return null;

  const exitLabel = EXIT_LABELS[event.exit_type] ?? event.exit_type;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[85vh] overflow-y-auto"
        style={{ maxWidth: "80vw", width: "80vw" }}
      >
        <DialogHeader>
          <DialogTitle>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-sm font-medium text-text-primary">
                  {event.date}
                </span>
                <span
                  className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${eventBadgeClass(
                    event.event_type
                  )}`}
                >
                  {formatEventTypeLabel(event.event_type)}
                </span>
                {event.direction_filled && (
                  <span
                    className="text-xs font-medium"
                    style={{
                      color:
                        event.direction_filled === "long"
                          ? "var(--color-profit)"
                          : "var(--color-loss)",
                    }}
                  >
                    {event.direction_filled.toUpperCase()}
                  </span>
                )}
                <span className="text-xs text-text-muted">{exitLabel}</span>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className="font-mono text-sm font-semibold"
                  style={{ color: pnlColor(event.final_points) }}
                >
                  {event.final_points >= 0 ? "+" : ""}
                  {formatNumber(event.final_points)} pts
                </span>
              </div>
            </div>
          </DialogTitle>
        </DialogHeader>

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
              No 1s candle data available for this date
            </div>
          )}

          <div
            ref={chartContainerRef}
            className={
              candles.length > 0 && !loading && !error ? "h-[500px]" : "hidden"
            }
          />

          {/* Price level legend */}
          {candles.length > 0 && !loading && !error && (
            <div className="mt-3 flex flex-wrap items-center gap-5 text-xs text-text-secondary">
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3 border-t border-dotted"
                  style={{ borderColor: "#a1adab" }}
                />
                Ref: {event.reference_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3 border-t border-dashed"
                  style={{ borderColor: "#72f25f" }}
                />
                Stop Buy: {(event.reference_price + event.buffer_points).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
              <span className="flex items-center gap-1.5">
                <span
                  className="inline-block h-0.5 w-3 border-t border-dashed"
                  style={{ borderColor: "#ff554f" }}
                />
                Stop Sell: {(event.reference_price - event.buffer_points).toLocaleString("en-US", { minimumFractionDigits: 2 })}
              </span>
              {event.direction_filled && event.fill_price > 0 && (
                <>
                  <span className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-0.5 w-3"
                      style={{ background: "#35d6e6" }}
                    />
                    Fill: {event.fill_price.toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>
                  <span className="flex items-center gap-1.5">
                    <span
                      className="inline-block h-0.5 w-3 border-t border-dotted"
                      style={{ borderColor: "#f8c159" }}
                    />
                    Target: {(event.direction_filled === "long"
                      ? event.fill_price + event.target_points
                      : event.fill_price - event.target_points
                    ).toLocaleString("en-US", { minimumFractionDigits: 2 })}
                  </span>
                </>
              )}
              <span className="flex items-center gap-1.5">
                MFE: <span className="font-mono text-profit">{formatNumber(event.mfe_points)}</span>
                &nbsp;MAE: <span className="font-mono text-loss">{formatNumber(event.mae_points)}</span>
              </span>
              {event.whipsaw && (
                <span className="text-warning font-medium">WHIPSAW</span>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
