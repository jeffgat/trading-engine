import { NewsRegimeReport } from "@/backtesting/components/NewsRegimeReport";
import { NewsTradeChartModal } from "@/backtesting/components/NewsTradeChartModal";
import { StatCard } from "@/backtesting/components/StatCard";
import { useNewsStraddle } from "@/backtesting/hooks/useNewsStraddle";
import { useNewsStraddleHistory } from "@/backtesting/hooks/useNewsStraddleHistory";
import type {
  NewsStraddleEvent,
  NewsStraddleHistoryItem,
  NewsStraddleSweepRow,
} from "@/backtesting/lib/types";
import { formatNumber, formatPct, pnlColor } from "@/backtesting/lib/utils";
import { MetricGridSkeleton, Skeleton, TableSkeleton } from "@/shared/ui/skeleton";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type Mode = "single" | "sweep";
type SortKey = keyof NewsStraddleEvent;
type SortDir = "asc" | "desc";

// ── Sweep heatmap metric options ──
type HeatMetric = "target_hit_rate" | "whipsaw_rate" | "avg_mfe" | "avg_final_points" | "pct_profitable";
const HEAT_METRIC_LABELS: Record<HeatMetric, string> = {
  target_hit_rate: "Target Hit Rate",
  whipsaw_rate: "Whipsaw Rate",
  avg_mfe: "Avg MFE",
  avg_final_points: "Avg Final Pts",
  pct_profitable: "% Profitable",
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

function formatEventTypeLabel(eventType: string): string {
  return EVENT_LABELS[eventType] ?? eventType;
}

function eventBadgeClass(eventType: string): string {
  return EVENT_BADGE_CLASSES[eventType] ?? "bg-accent/20 text-accent";
}

export function NewsDashboard() {
  const { singleData, setSingleData, sweepData, loading, error, runSingle, runSweep } =
    useNewsStraddle();
  const {
    history,
    loading: historyLoading,
    refresh: refreshHistory,
    loadRun,
    deleteRun,
    starRun,
  } = useNewsStraddleHistory();

  const [mode, setMode] = useState<Mode>("single");
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [resultLoading, setResultLoading] = useState(false);

  // Refresh history when a new single run completes
  const wasLoading = useRef(false);
  useEffect(() => {
    if (wasLoading.current && !loading && singleData) {
      refreshHistory();
    }
    wasLoading.current = loading;
  }, [loading, singleData, refreshHistory]);

  // Single run config — stored as strings so users can clear & retype freely
  const [bufferPoints, setBufferPoints] = useState("5");
  const [targetPoints, setTargetPoints] = useState("25");
  const [nfpChecked, setNfpChecked] = useState(true);
  const [cpiChecked, setCpiChecked] = useState(true);
  const [ppiChecked, setPpiChecked] = useState(false);
  const [fomcChecked, setFomcChecked] = useState(false);
  const [nyOpenChecked, setNyOpenChecked] = useState(false);
  const [obsWindow, setObsWindow] = useState("120");
  const [stopLossPoints, setStopLossPoints] = useState("10");
  const [start, setStart] = useState("2021-01-01");
  const [end, setEnd] = useState("2025-12-31");

  // Regime filter state
  const [maxAtrPct, setMaxAtrPct] = useState("");
  const [minVolumeRatio, setMinVolumeRatio] = useState("");
  const [maxVolumeRatio, setMaxVolumeRatio] = useState("");
  const [directionFilter, setDirectionFilter] = useState<string>(""); // "" | "long" | "short"
  const [skipDays, setSkipDays] = useState<Set<number>>(new Set());

  // Sweep config
  const [bufferRange, setBufferRange] = useState("1:20:1");
  const [targetRange, setTargetRange] = useState("10:50:5");

  // Table sort
  const [sortKey, setSortKey] = useState<SortKey>("date");
  const [sortDir, setSortDir] = useState<SortDir>("asc");

  // Sweep heatmap metric
  const [heatMetric, setHeatMetric] = useState<HeatMetric>("target_hit_rate");

  // Chart modal
  const [chartEvent, setChartEvent] = useState<NewsStraddleEvent | null>(null);
  const [chartOpen, setChartOpen] = useState(false);

  const eventTypes = [
    ...(nfpChecked ? ["NFP"] : []),
    ...(cpiChecked ? ["CPI"] : []),
    ...(ppiChecked ? ["PPI"] : []),
    ...(fomcChecked ? ["FOMC"] : []),
    ...(nyOpenChecked ? ["NY_OPEN"] : []),
  ];

  const regimeFilters = {
    max_atr_pct: maxAtrPct === "" ? null : Number(maxAtrPct) || null,
    min_volume_ratio: minVolumeRatio === "" ? null : Number(minVolumeRatio) || null,
    max_volume_ratio: maxVolumeRatio === "" ? null : Number(maxVolumeRatio) || null,
    direction_filter: directionFilter || null,
    skip_days: skipDays.size > 0 ? [...skipDays] : null,
  };

  const handleRunSingle = () => {
    runSingle({
      buffer_points: Number(bufferPoints) || 0,
      target_points: Number(targetPoints) || 0,
      event_types: eventTypes,
      observation_window_seconds: Number(obsWindow) || 120,
      start,
      end,
      stop_loss_points: stopLossPoints === "" ? null : Number(stopLossPoints) || 0,
      ...regimeFilters,
    });
  };

  const handleRunSweep = () => {
    runSweep({
      buffer_range: bufferRange,
      target_range: targetRange,
      event_types: eventTypes,
      observation_window_seconds: Number(obsWindow) || 120,
      start,
      end,
      stop_loss_points: stopLossPoints === "" ? null : Number(stopLossPoints) || 0,
      ...regimeFilters,
    });
  };

  // Sort events
  const sortedEvents = useMemo(() => {
    if (!singleData?.events) return [];
    const sorted = [...singleData.events];
    sorted.sort((a, b) => {
      const av = a[sortKey];
      const bv = b[sortKey];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (av < bv) return sortDir === "asc" ? -1 : 1;
      if (av > bv) return sortDir === "asc" ? 1 : -1;
      return 0;
    });
    return sorted;
  }, [singleData?.events, sortKey, sortDir]);

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  // MFE histogram data
  const mfeHistogram = useMemo(() => {
    if (!singleData?.events) return [];
    const filled = singleData.events.filter((e) => e.direction_filled);
    const bucketSize = 10;
    const buckets: Record<string, number> = {};
    for (const e of filled) {
      const bucket = Math.floor(e.mfe_points / bucketSize) * bucketSize;
      const label = `${bucket}-${bucket + bucketSize}`;
      buckets[label] = (buckets[label] || 0) + 1;
    }
    return Object.entries(buckets)
      .sort(([a], [b]) => parseInt(a) - parseInt(b))
      .map(([range, count]) => ({ range, count }));
  }, [singleData?.events]);

  // Scatter data (MFE vs MAE)
  const scatterData = useMemo(() => {
    if (!singleData?.events) return [];
    return singleData.events
      .filter((e) => e.direction_filled)
      .map((e) => ({
        mae: e.mae_points,
        mfe: e.mfe_points,
        targetHit: e.target_hit,
        date: e.date,
        type: e.event_type,
      }));
  }, [singleData?.events]);

  // Timeseries: wins vs losses per event (chronological)
  const timeseriesData = useMemo(() => {
    if (!singleData?.events) return [];
    return singleData.events
      .filter((e) => e.direction_filled)
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((e) => ({
        date: e.date,
        points: e.final_points,
        type: e.event_type,
        dir: e.direction_filled,
        targetHit: e.target_hit,
      }));
  }, [singleData?.events]);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-text-primary">
          News Straddle Backtest
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Stop-buy above / stop-sell below price 1s before NFP/CPI/PPI or
          FOMC statement release, or NY open. Find optimal buffer and target.
        </p>
      </div>

      {/* History panel */}
      <NewsStraddleHistoryPanel
        history={history}
        loading={historyLoading}
        selectedRunId={selectedRunId}
        onSelect={async (item) => {
          setSelectedRunId(item.result_id);
          setMode("single");
          setResultLoading(true);
          try {
            const full = await loadRun(item.result_id);
            if (full) {
              setSingleData(full);
              // Sync config inputs
              setBufferPoints(String(item.buffer_points));
              setTargetPoints(String(item.target_points));
              setObsWindow(String(item.observation_window_seconds));
              const types: string[] = JSON.parse(item.event_types);
              setNfpChecked(types.includes("NFP"));
              setCpiChecked(types.includes("CPI"));
              setPpiChecked(types.includes("PPI"));
              setFomcChecked(types.includes("FOMC"));
              setNyOpenChecked(types.includes("NY_OPEN"));
              setStopLossPoints(item.stop_loss_points != null ? String(item.stop_loss_points) : "");
              if (item.date_start) setStart(item.date_start);
              if (item.date_end) setEnd(item.date_end);
              // Restore regime filters from loaded config
              const cfg = full.config;
              setMaxAtrPct(cfg.max_atr_pct != null ? String(cfg.max_atr_pct) : "");
              setMinVolumeRatio(cfg.min_volume_ratio != null ? String(cfg.min_volume_ratio) : "");
              setMaxVolumeRatio(cfg.max_volume_ratio != null ? String(cfg.max_volume_ratio) : "");
              setDirectionFilter(cfg.direction_filter ?? "");
              setSkipDays(new Set(cfg.skip_days ?? []));
            }
          } finally {
            setResultLoading(false);
          }
        }}
        onDelete={async (item) => {
          await deleteRun(item.result_id);
          if (selectedRunId === item.result_id) setSelectedRunId(null);
        }}
        onStar={(item) => starRun(item.result_id)}
      />

      {/* Mode toggle */}
      <div className="mb-6 flex gap-1 rounded-lg border border-border bg-bg-secondary p-1 w-fit">
        {(["single", "sweep"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={`rounded-md px-4 py-1.5 text-sm font-medium transition-colors ${
              mode === m
                ? "bg-bg-card text-text-primary"
                : "text-text-muted hover:text-text-secondary"
            }`}
          >
            {m === "single" ? "Single Run" : "Sweep"}
          </button>
        ))}
      </div>

      {/* Config panel */}
      <div className="mb-6 rounded-lg border border-border bg-bg-card p-4">
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-7">
          {mode === "single" ? (
            <>
              <div>
                <label className="mb-1 block text-xs text-text-muted">
                  Buffer (pts)
                </label>
                <input
                  type="text"
                  inputMode="decimal"
                  value={bufferPoints}
                  onChange={(e) => setBufferPoints(e.target.value)}
                  className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-muted">
                  Target (pts)
                </label>
                <input
                  type="text"
                  inputMode="numeric"
                  value={targetPoints}
                  onChange={(e) => setTargetPoints(e.target.value)}
                  className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary"
                />
              </div>
            </>
          ) : (
            <>
              <div>
                <label className="mb-1 block text-xs text-text-muted">
                  Buffer range
                </label>
                <input
                  type="text"
                  value={bufferRange}
                  onChange={(e) => setBufferRange(e.target.value)}
                  placeholder="1:20:1"
                  className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs text-text-muted">
                  Target range
                </label>
                <input
                  type="text"
                  value={targetRange}
                  onChange={(e) => setTargetRange(e.target.value)}
                  placeholder="10:50:5"
                  className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary"
                />
              </div>
            </>
          )}
          <div>
            <label className="mb-1 block text-xs text-text-muted">
              Stop Loss (pts)
            </label>
            <input
              type="text"
              inputMode="numeric"
              value={stopLossPoints}
              onChange={(e) => setStopLossPoints(e.target.value)}
              placeholder="None"
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-muted/50"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">
              Window (sec)
            </label>
            <input
              type="text"
              inputMode="numeric"
              value={obsWindow}
              onChange={(e) => setObsWindow(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Events</label>
            <div className="flex flex-col gap-1 pt-0.5">
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={nfpChecked}
                  onChange={(e) => setNfpChecked(e.target.checked)}
                  className="accent-accent"
                />
                NFP
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={cpiChecked}
                  onChange={(e) => setCpiChecked(e.target.checked)}
                  className="accent-accent"
                />
                CPI
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={ppiChecked}
                  onChange={(e) => setPpiChecked(e.target.checked)}
                  className="accent-accent"
                />
                PPI
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={fomcChecked}
                  onChange={(e) => setFomcChecked(e.target.checked)}
                  className="accent-accent"
                />
                FOMC
              </label>
              <label className="flex items-center gap-1.5 text-xs text-text-secondary">
                <input
                  type="checkbox"
                  checked={nyOpenChecked}
                  onChange={(e) => setNyOpenChecked(e.target.checked)}
                  className="accent-accent"
                />
                NY Open
              </label>
            </div>
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Start</label>
            <input
              type="date"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-2 py-1 text-xs text-text-primary"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">End</label>
            <input
              type="date"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-2 py-1 text-xs text-text-primary"
            />
          </div>
        </div>

        {/* Regime filters row */}
        <div className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 sm:grid-cols-3 md:grid-cols-6">
          <div>
            <label className="mb-1 block text-xs text-text-muted">Max ATR %</label>
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g. 1.5"
              value={maxAtrPct}
              onChange={(e) => setMaxAtrPct(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-muted/40"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Min Vol Ratio</label>
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g. 0.8"
              value={minVolumeRatio}
              onChange={(e) => setMinVolumeRatio(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-muted/40"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Max Vol Ratio</label>
            <input
              type="text"
              inputMode="decimal"
              placeholder="e.g. 2.0"
              value={maxVolumeRatio}
              onChange={(e) => setMaxVolumeRatio(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 font-mono text-sm text-text-primary placeholder:text-text-muted/40"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-text-muted">Direction</label>
            <select
              value={directionFilter}
              onChange={(e) => setDirectionFilter(e.target.value)}
              className="w-full rounded border border-border bg-bg-primary px-3 py-1.5 text-sm text-text-primary"
            >
              <option value="">Both</option>
              <option value="long">Long only</option>
              <option value="short">Short only</option>
            </select>
          </div>
          <div className="col-span-2">
            <label className="mb-1 block text-xs text-text-muted">Skip Days</label>
            <div className="flex flex-wrap gap-2 pt-0.5">
              {["Mon", "Tue", "Wed", "Thu", "Fri"].map((day, i) => (
                <label key={day} className="flex items-center gap-1 text-xs text-text-secondary">
                  <input
                    type="checkbox"
                    checked={skipDays.has(i)}
                    onChange={(e) => {
                      setSkipDays((prev) => {
                        const next = new Set(prev);
                        if (e.target.checked) next.add(i);
                        else next.delete(i);
                        return next;
                      });
                    }}
                    className="accent-accent"
                  />
                  {day}
                </label>
              ))}
            </div>
          </div>
        </div>

        <div className="mt-4">
          <button
            onClick={mode === "single" ? handleRunSingle : handleRunSweep}
            disabled={loading || eventTypes.length === 0}
            className="rounded-md bg-accent px-6 py-2 text-sm font-semibold text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            {loading ? "Running..." : mode === "single" ? "Run Backtest" : "Run Sweep"}
          </button>
        </div>
        {error && (
          <div className="mt-3 rounded border border-loss/30 bg-loss/10 px-3 py-2 text-sm text-loss">
            {error}
          </div>
        )}
      </div>

      {(loading || resultLoading) && <NewsResultsSkeleton mode={mode} />}

      {/* ═══ SINGLE RUN RESULTS ═══ */}
      {!loading && !resultLoading && mode === "single" && singleData && (
        <>
          {/* Stat cards */}
          <div className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
            <StatCard
              label="Target Hit Rate"
              value={formatPct(singleData.summary.target_hit_rate)}
              tooltip={`${singleData.summary.target_hit_count} of ${singleData.summary.fills} fills`}
              color="var(--color-profit)"
            />
            <StatCard
              label="Whipsaw Rate"
              value={formatPct(singleData.summary.whipsaw_rate)}
              tooltip={`${singleData.summary.whipsaw_count} events where opposite stop also triggered`}
              color="var(--color-loss)"
            />
            <StatCard
              label="Avg MFE"
              value={`${formatNumber(singleData.summary.avg_mfe)} pts`}
              subValue={`Median: ${formatNumber(singleData.summary.median_mfe)}`}
            />
            <StatCard
              label="Avg MAE"
              value={`${formatNumber(singleData.summary.avg_mae)} pts`}
              subValue={`Median: ${formatNumber(singleData.summary.median_mae)}`}
            />
            <StatCard
              label="Fills"
              value={`${singleData.summary.fills}`}
              subValue={`L:${singleData.summary.long_fills} S:${singleData.summary.short_fills}`}
              tooltip={`${singleData.summary.events_with_data} events with data, ${singleData.summary.skipped_no_data} skipped${singleData.summary.filtered_out ? `, ${singleData.summary.filtered_out} filtered out` : ""}`}
            />
            {singleData.summary.stop_loss_count > 0 && (
              <StatCard
                label="Stop Loss Rate"
                value={formatPct(singleData.summary.stop_loss_rate)}
                tooltip={`${singleData.summary.stop_loss_count} of ${singleData.summary.fills} fills`}
                color="var(--color-loss)"
              />
            )}
          </div>

          {/* By event type breakdown */}
          {Object.keys(singleData.summary.by_event_type).length > 1 && (
            <div className="mb-6 rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">
                By Event Type
              </h3>
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(singleData.summary.by_event_type).map(
                  ([type, stats]) => (
                      <div
                      key={type}
                      className="rounded border border-border bg-bg-primary p-3"
                    >
                      <div className="mb-2 text-sm font-semibold text-accent">
                        {formatEventTypeLabel(type)}
                      </div>
                      <div className="grid grid-cols-3 gap-2 text-xs">
                        <div>
                          <span className="text-text-muted">Fills: </span>
                          <span className="font-mono text-text-primary">
                            {stats.fills}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Hit Rate: </span>
                          <span
                            className="font-mono"
                            style={{ color: "var(--color-profit)" }}
                          >
                            {formatPct(stats.target_hit_rate)}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Whipsaws: </span>
                          <span className="font-mono text-text-primary">
                            {stats.whipsaw_count}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Avg MFE: </span>
                          <span className="font-mono text-text-primary">
                            {formatNumber(stats.avg_mfe)}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Avg MAE: </span>
                          <span className="font-mono text-text-primary">
                            {formatNumber(stats.avg_mae)}
                          </span>
                        </div>
                        <div>
                          <span className="text-text-muted">Avg Final: </span>
                          <span
                            className="font-mono"
                            style={{
                              color: pnlColor(stats.avg_final_points),
                            }}
                          >
                            {formatNumber(stats.avg_final_points)}
                          </span>
                        </div>
                      </div>
                    </div>
                  )
                )}
              </div>
            </div>
          )}

          {/* Regime analysis */}
          <NewsRegimeReport
            events={singleData.events}
            instrument={singleData.config.instrument}
          />

          {/* Charts row */}
          <div className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
            {/* MFE distribution */}
            <div className="rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">
                MFE Distribution (pts)
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <BarChart data={mfeHistogram}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3a3026" />
                  <XAxis
                    dataKey="range"
                    tick={{ fill: "#ccb088", fontSize: 11 }}
                  />
                  <YAxis tick={{ fill: "#ccb088", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#101010",
                      border: "1px solid #3a3026",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                  />
                  <Bar dataKey="count" fill="#ecc997" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* MFE vs MAE scatter */}
            <div className="rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">
                MFE vs MAE
              </h3>
              <ResponsiveContainer width="100%" height={240}>
                <ScatterChart>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3a3026" />
                  <XAxis
                    dataKey="mae"
                    name="MAE"
                    tick={{ fill: "#ccb088", fontSize: 11 }}
                    label={{
                      value: "MAE (pts)",
                      position: "insideBottom",
                      offset: -5,
                      fill: "#8a765b",
                      fontSize: 11,
                    }}
                  />
                  <YAxis
                    dataKey="mfe"
                    name="MFE"
                    tick={{ fill: "#ccb088", fontSize: 11 }}
                    label={{
                      value: "MFE (pts)",
                      angle: -90,
                      position: "insideLeft",
                      fill: "#8a765b",
                      fontSize: 11,
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#101010",
                      border: "1px solid #3a3026",
                      borderRadius: 6,
                      fontSize: 12,
                      color: "#f8e0b8",
                    }}
                    labelStyle={{ color: "#ccb088" }}
                    formatter={(value) => formatNumber(Number(value ?? 0))}
                  />
                  <Scatter data={scatterData}>
                    {scatterData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={entry.targetHit ? "#ecc997" : "#d4775f"}
                        opacity={0.7}
                      />
                    ))}
                  </Scatter>
                </ScatterChart>
              </ResponsiveContainer>
              <div className="mt-2 flex gap-4 justify-center text-xs text-text-muted">
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: "#ecc997" }}
                  />
                  Target hit
                </span>
                <span className="flex items-center gap-1">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: "#d4775f" }}
                  />
                  Target missed
                </span>
              </div>
            </div>
          </div>

          {/* Wins vs Losses timeseries */}
          {timeseriesData.length > 0 && (
            <div className="mb-6 rounded-lg border border-border bg-bg-card p-4">
              <h3 className="mb-3 text-sm font-medium text-text-secondary">
                Wins vs Losses (chronological)
              </h3>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={timeseriesData} barCategoryGap={2}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#3a3026" vertical={false} />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: "#ccb088", fontSize: 10 }}
                    interval="preserveStartEnd"
                    tickFormatter={(d: string) => d.slice(5)}
                  />
                  <YAxis tick={{ fill: "#ccb088", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#101010",
                      border: "1px solid #3a3026",
                      borderRadius: 6,
                      fontSize: 12,
                    }}
                    formatter={(value) => [`${formatNumber(Number(value ?? 0))} pts`, "Final"]}
                    labelFormatter={(label) => String(label ?? "")}
                  />
                  <ReferenceLine y={0} stroke="#8a765b" />
                  <Bar dataKey="points" radius={[2, 2, 0, 0]}>
                    {timeseriesData.map((entry, i) => (
                      <Cell
                        key={i}
                        fill={entry.points >= 0 ? "#ecc997" : "#d4775f"}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Events table */}
          <div className="rounded-lg border border-border bg-bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-medium text-text-secondary">
                Per-Event Results ({sortedEvents.length})
              </h3>
            </div>
            <div className="max-h-[500px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-bg-card text-xs text-text-muted">
                  <tr>
                    {(
                      [
                        ["date", "Date"],
                        ["event_type", "Type"],
                        ["direction_filled", "Dir"],
                        ["reference_price", "Ref Price"],
                        ["fill_price", "Fill Price"],
                        ["seconds_to_fill", "Fill (s)"],
                        ["mfe_points", "MFE"],
                        ["mae_points", "MAE"],
                        ["target_hit", "Target"],
                        ["whipsaw", "Whipsaw"],
                        ["final_points", "Final Pts"],
                        ["exit_type", "Exit"],
                      ] as [SortKey, string][]
                    ).map(([key, label]) => (
                      <th
                        key={key}
                        onClick={() => toggleSort(key)}
                        className="cursor-pointer whitespace-nowrap px-3 py-2 hover:text-text-secondary"
                      >
                        {label}
                        {sortKey === key && (
                          <span className="ml-1">
                            {sortDir === "asc" ? "\u25b2" : "\u25bc"}
                          </span>
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedEvents.map((e, i) => (
                    <tr
                      key={i}
                      className="border-t border-border/50 hover:bg-bg-card-hover transition-colors cursor-pointer"
                      onClick={() => {
                        setChartEvent(e);
                        setChartOpen(true);
                      }}
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-text-primary">
                        {e.date}
                      </td>
                      <td className="px-3 py-2">
                        <span
                          className={`inline-block rounded px-1.5 py-0.5 text-xs font-medium ${eventBadgeClass(
                            e.event_type
                          )}`}
                        >
                          {formatEventTypeLabel(e.event_type)}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        {e.direction_filled ? (
                          <span
                            className={`text-xs font-medium ${
                              e.direction_filled === "long"
                                ? "text-profit"
                                : "text-loss"
                            }`}
                          >
                            {e.direction_filled.toUpperCase()}
                          </span>
                        ) : (
                          <span className="text-xs text-text-muted">--</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-text-secondary">
                        {formatNumber(e.reference_price, 2)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 font-mono text-text-secondary">
                        {e.fill_price ? formatNumber(e.fill_price, 2) : "--"}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {e.direction_filled ? e.seconds_to_fill : "--"}
                      </td>
                      <td className="px-3 py-2 font-mono text-profit">
                        {e.direction_filled
                          ? formatNumber(e.mfe_points)
                          : "--"}
                      </td>
                      <td className="px-3 py-2 font-mono text-loss">
                        {e.direction_filled
                          ? formatNumber(e.mae_points)
                          : "--"}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {e.direction_filled ? (
                          e.target_hit ? (
                            <span className="text-profit">Yes</span>
                          ) : (
                            <span className="text-loss">No</span>
                          )
                        ) : (
                          "--"
                        )}
                      </td>
                      <td className="px-3 py-2 text-center">
                        {e.direction_filled ? (
                          e.whipsaw ? (
                            <span className="text-warning">Yes</span>
                          ) : (
                            <span className="text-text-muted">No</span>
                          )
                        ) : (
                          "--"
                        )}
                      </td>
                      <td
                        className="px-3 py-2 font-mono"
                        style={{
                          color: e.direction_filled
                            ? pnlColor(e.final_points)
                            : undefined,
                        }}
                      >
                        {e.direction_filled
                          ? formatNumber(e.final_points)
                          : "--"}
                      </td>
                      <td className="px-3 py-2 text-xs text-text-muted">
                        {e.direction_filled ? e.exit_type : "--"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ═══ SWEEP RESULTS ═══ */}
      {!loading && !resultLoading && mode === "sweep" && sweepData && (
        <>
          {/* Metric selector */}
          <div className="mb-4 flex items-center gap-3">
            <span className="text-xs text-text-muted">Heatmap metric:</span>
            <div className="flex gap-1 rounded-lg border border-border bg-bg-secondary p-0.5">
              {(Object.keys(HEAT_METRIC_LABELS) as HeatMetric[]).map((m) => (
                <button
                  key={m}
                  onClick={() => setHeatMetric(m)}
                  className={`rounded-md px-3 py-1 text-xs font-medium transition-colors ${
                    heatMetric === m
                      ? "bg-bg-card text-text-primary"
                      : "text-text-muted hover:text-text-secondary"
                  }`}
                >
                  {HEAT_METRIC_LABELS[m]}
                </button>
              ))}
            </div>
          </div>

          {/* Heatmap */}
          <SweepHeatmap
            data={sweepData.results}
            bufferValues={sweepData.swept_params.buffer_points}
            targetValues={sweepData.swept_params.target_points}
            metric={heatMetric}
          />

          {/* Sweep results table */}
          <div className="mt-6 rounded-lg border border-border bg-bg-card">
            <div className="border-b border-border px-4 py-3">
              <h3 className="text-sm font-medium text-text-secondary">
                All Combinations ({sweepData.total_combinations})
              </h3>
            </div>
            <div className="max-h-[500px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-bg-card text-xs text-text-muted">
                  <tr>
                    <th className="px-3 py-2">Buffer</th>
                    <th className="px-3 py-2">Target</th>
                    <th className="px-3 py-2">Fills</th>
                    <th className="px-3 py-2">Hit Rate</th>
                    <th className="px-3 py-2">Whipsaw</th>
                    <th className="px-3 py-2">Avg MFE</th>
                    <th className="px-3 py-2">Avg MAE</th>
                    <th className="px-3 py-2">Avg Final</th>
                    <th className="px-3 py-2">% Profitable</th>
                  </tr>
                </thead>
                <tbody>
                  {sweepData.results.map((r, i) => (
                    <tr
                      key={i}
                      className="border-t border-border/50 hover:bg-bg-card-hover transition-colors"
                    >
                      <td className="px-3 py-2 font-mono text-text-primary">
                        {r.buffer_points}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-primary">
                        {r.target_points}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {r.fills}
                      </td>
                      <td
                        className="px-3 py-2 font-mono"
                        style={{ color: "var(--color-profit)" }}
                      >
                        {formatPct(r.target_hit_rate)}
                      </td>
                      <td
                        className="px-3 py-2 font-mono"
                        style={{ color: "var(--color-loss)" }}
                      >
                        {formatPct(r.whipsaw_rate)}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {formatNumber(r.avg_mfe)}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {formatNumber(r.avg_mae)}
                      </td>
                      <td
                        className="px-3 py-2 font-mono"
                        style={{ color: pnlColor(r.avg_final_points) }}
                      >
                        {formatNumber(r.avg_final_points)}
                      </td>
                      <td className="px-3 py-2 font-mono text-text-secondary">
                        {formatPct(r.pct_profitable)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* Trade chart modal */}
      <NewsTradeChartModal
        event={chartEvent}
        instrument="NQ"
        observationWindowSeconds={Number(obsWindow) || 120}
        open={chartOpen}
        onOpenChange={setChartOpen}
      />
    </div>
  );
}

function NewsResultsSkeleton({ mode }: { mode: Mode }) {
  return (
    <div className="mb-6 space-y-6">
      {mode === "single" ? (
        <>
          <MetricGridSkeleton count={5} />
          <div className="rounded-lg border border-border bg-bg-card p-4">
            <Skeleton className="mb-4 h-4 w-36 rounded" />
            <div className="grid grid-cols-2 gap-4">
              <Skeleton className="h-28 rounded" />
              <Skeleton className="h-28 rounded" />
            </div>
          </div>
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <Skeleton className="h-72 rounded-lg" />
            <Skeleton className="h-72 rounded-lg" />
          </div>
          <TableSkeleton rows={7} columns={8} />
        </>
      ) : (
        <>
          <div className="flex items-center gap-3">
            <Skeleton className="h-4 w-28 rounded" muted />
            <Skeleton className="h-8 w-96 max-w-full rounded-lg" />
          </div>
          <Skeleton className="h-[320px] rounded-lg" />
          <TableSkeleton rows={7} columns={7} />
        </>
      )}
    </div>
  );
}

// ── Filter Badges (compact display of active regime filters) ──

const DOW_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function FilterBadges({ item }: { item: NewsStraddleHistoryItem }) {
  const badges: string[] = [];
  if (item.max_atr_pct != null) badges.push(`ATR<${item.max_atr_pct}%`);
  if (item.min_volume_ratio != null) badges.push(`Vol>${item.min_volume_ratio}`);
  if (item.max_volume_ratio != null) badges.push(`Vol<${item.max_volume_ratio}`);
  if (item.direction_filter) badges.push(item.direction_filter === "long" ? "Long" : "Short");
  if (item.skip_days) {
    try {
      const days: number[] = typeof item.skip_days === "string" ? JSON.parse(item.skip_days) : item.skip_days;
      if (days.length > 0) badges.push(`Skip ${days.map((d) => DOW_LABELS[d] ?? d).join(",")}`);
    } catch { /* ignore */ }
  }
  if (badges.length === 0) return <span className="text-text-muted/40">—</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {badges.map((b) => (
        <span
          key={b}
          className="inline-block whitespace-nowrap rounded bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent"
        >
          {b}
        </span>
      ))}
    </div>
  );
}

// ── History Panel ──

function NewsStraddleHistoryPanel({
  history,
  loading,
  selectedRunId,
  onSelect,
  onDelete,
  onStar,
}: {
  history: NewsStraddleHistoryItem[];
  loading: boolean;
  selectedRunId: string | null;
  onSelect: (item: NewsStraddleHistoryItem) => void;
  onDelete: (item: NewsStraddleHistoryItem) => void;
  onStar: (item: NewsStraddleHistoryItem) => void;
}) {
  const fmtDate = (ts: string) => {
    try {
      const d = new Date(ts);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return ts;
    }
  };

  // Sort: starred first, then by timestamp
  const sorted = [...history].sort((a, b) => {
    if (a.starred !== b.starred) return b.starred - a.starred;
    return 0; // preserve original timestamp order
  });

  return (
    <div className="mb-6 rounded-lg border border-border bg-bg-card">
      <div className="border-b border-border px-4 py-2.5">
        <h3 className="text-sm font-medium text-text-secondary">
          Run History {loading ? "" : `(${history.length})`}
        </h3>
      </div>
      <div className="max-h-[220px] overflow-auto">
        {loading ? (
          <div className="space-y-2 px-4 py-3">
            {Array.from({ length: 4 }).map((_, index) => (
              <div key={index} className="grid grid-cols-[2rem_1fr_4rem_4rem_5rem] gap-3">
                <Skeleton className="h-4 rounded" muted />
                <Skeleton className="h-4 rounded" />
                <Skeleton className="h-4 rounded" muted />
                <Skeleton className="h-4 rounded" muted />
                <Skeleton className="h-4 rounded" muted />
              </div>
            ))}
          </div>
        ) : history.length === 0 ? (
          <div className="px-4 py-4 text-xs text-text-muted">
            No runs saved yet. Run a backtest to see it here.
          </div>
        ) : (
        <table className="w-full text-left text-xs">
          <thead className="sticky top-0 z-10 bg-bg-card text-text-muted">
            <tr>
              <th className="sticky left-0 z-20 bg-bg-card px-2 py-1.5 w-8" />
              <th className="whitespace-nowrap px-3 py-1.5">Run Date</th>
              <th className="px-3 py-1.5">Buffer</th>
              <th className="px-3 py-1.5">Target</th>
              <th className="px-3 py-1.5">SL</th>
              <th className="px-3 py-1.5">Window</th>
              <th className="px-3 py-1.5">Events</th>
              <th className="px-3 py-1.5">Filters</th>
              <th className="whitespace-nowrap px-3 py-1.5">Period</th>
              <th className="px-3 py-1.5">Fills</th>
              <th className="px-3 py-1.5">Hit Rate</th>
              <th className="px-3 py-1.5">Whipsaw</th>
              <th className="px-3 py-1.5">Avg Pts</th>
              <th className="px-3 py-1.5 w-8" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((item) => {
              const isSelected = item.result_id === selectedRunId;
              let events: string[];
              try {
                events = JSON.parse(item.event_types);
              } catch {
                events = [];
              }
              return (
                <tr
                  key={item.result_id}
                  onClick={() => onSelect(item)}
                  className={`border-t border-border/50 cursor-pointer transition-colors ${
                    isSelected
                      ? "bg-accent/10 border-l-2 border-l-accent"
                      : "hover:bg-bg-card-hover"
                  }`}
                >
                  <td className="sticky left-0 z-10 bg-inherit px-2 py-1.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onStar(item);
                      }}
                      className={`text-sm transition-colors ${
                        item.starred
                          ? "text-accent"
                          : "text-text-muted/30 hover:text-accent/60"
                      }`}
                      title={item.starred ? "Unstar" : "Star"}
                    >
                      {item.starred ? "\u2605" : "\u2606"}
                    </button>
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-text-muted">
                    {fmtDate(item.timestamp)}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-text-primary">
                    {item.buffer_points}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-text-primary">
                    {item.target_points}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-text-secondary">
                    {item.stop_loss_points != null ? item.stop_loss_points : "—"}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-text-secondary">
                    {item.observation_window_seconds}s
                  </td>
                  <td className="px-3 py-1.5 text-text-secondary">
                    {events.map(formatEventTypeLabel).join(", ")}
                  </td>
                  <td className="px-3 py-1.5">
                    <FilterBadges item={item} />
                  </td>
                  <td className="whitespace-nowrap px-3 py-1.5 text-text-muted">
                    {item.date_start ?? "—"} &rarr; {item.date_end ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 font-mono text-text-secondary">
                    {item.fills ?? "—"}
                  </td>
                  <td className="px-3 py-1.5 font-mono" style={{ color: "var(--color-profit)" }}>
                    {item.target_hit_rate != null ? formatPct(item.target_hit_rate) : "—"}
                  </td>
                  <td className="px-3 py-1.5 font-mono" style={{ color: "var(--color-loss)" }}>
                    {item.whipsaw_rate != null ? formatPct(item.whipsaw_rate) : "—"}
                  </td>
                  <td
                    className="px-3 py-1.5 font-mono"
                    style={{ color: item.avg_final_points != null ? (item.avg_final_points >= 0 ? "var(--color-profit)" : "var(--color-loss)") : undefined }}
                  >
                    {item.avg_final_points != null ? formatNumber(item.avg_final_points) : "—"}
                  </td>
                  <td className="px-3 py-1.5">
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(item);
                      }}
                      className="text-text-muted hover:text-loss transition-colors"
                      title="Delete run"
                    >
                      &times;
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        )}
      </div>
    </div>
  );
}

// ── Sweep Heatmap ──

function SweepHeatmap({
  data,
  bufferValues,
  targetValues,
  metric,
}: {
  data: NewsStraddleSweepRow[];
  bufferValues: number[];
  targetValues: number[];
  metric: HeatMetric;
}) {
  // Build lookup
  const lookup = useMemo(() => {
    const map = new Map<string, number>();
    for (const row of data) {
      map.set(`${row.buffer_points}-${row.target_points}`, row[metric]);
    }
    return map;
  }, [data, metric]);

  // Find min/max for color scale
  const values = Array.from(lookup.values()).filter(
    (v) => v != null && isFinite(v)
  );
  const min = Math.min(...values);
  const max = Math.max(...values);

  const isInverse = metric === "whipsaw_rate"; // lower is better

  const getCellColor = (value: number | undefined) => {
    if (value == null || !isFinite(value)) return "#101010";
    const range = max - min || 1;
    let t = (value - min) / range;
    if (isInverse) t = 1 - t;

    // Interpolate from red → yellow → green
    if (t < 0.5) {
      const r = 240;
      const g = Math.round(97 + t * 2 * (193 - 97));
      const b = Math.round(94 + t * 2 * (89 - 94));
      return `rgb(${r},${g},${b})`;
    } else {
      const r = Math.round(240 - (t - 0.5) * 2 * (240 - 61));
      const g = Math.round(193 + (t - 0.5) * 2 * (214 - 193));
      const b = Math.round(89 + (t - 0.5) * 2 * (140 - 89));
      return `rgb(${r},${g},${b})`;
    }
  };

  const formatValue = (v: number | undefined) => {
    if (v == null) return "--";
    if (metric.includes("rate") || metric.includes("profitable"))
      return formatPct(v, 0);
    return formatNumber(v, 1);
  };

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4 overflow-auto">
      <h3 className="mb-3 text-sm font-medium text-text-secondary">
        {HEAT_METRIC_LABELS[metric]} Heatmap
      </h3>
      <table className="text-xs">
        <thead>
          <tr>
            <th className="px-2 py-1 text-text-muted">Buf \ Tgt</th>
            {targetValues.map((t) => (
              <th
                key={t}
                className="px-2 py-1 text-center font-mono text-text-muted"
              >
                {t}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bufferValues.map((b) => (
            <tr key={b}>
              <td className="px-2 py-1 font-mono text-text-muted">{b}</td>
              {targetValues.map((t) => {
                const val = lookup.get(`${b}-${t}`);
                return (
                  <td
                    key={t}
                    className="px-2 py-1 text-center font-mono font-semibold"
                    style={{
                      backgroundColor: getCellColor(val),
                      color: "#101010",
                      minWidth: 52,
                    }}
                  >
                    {formatValue(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
