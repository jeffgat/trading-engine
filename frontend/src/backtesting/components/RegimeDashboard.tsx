import { useMemo, useState } from "react";
import { useRegimeReports } from "@/backtesting/hooks/useRegimeReports";
import type {
  RegimeReportHistoryItem,
  RegimeReportResult,
  RegimeReportSection,
  RegimeStat,
} from "@/backtesting/lib/types";
import { formatPct, formatNumber } from "@/backtesting/lib/utils";
import { MetricGridSkeleton, Skeleton, SkeletonText } from "@/shared/ui/skeleton";

type Method = "hmm" | "lstm";

function parseMethods(methods: string | null): string[] {
  if (!methods) return [];
  try {
    return JSON.parse(methods);
  } catch {
    return [];
  }
}

function formatDateRange(start?: string | null, end?: string | null) {
  if (!start || !end) return "—";
  return `${start} → ${end}`;
}

function formatTimestamp(ts: string) {
  if (!ts) return "—";
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleString();
}

// Human-readable feature names for display
const FEATURE_LABELS: Record<string, string> = {
  realized_vol_21d: "21d Vol",
  realized_vol_5d: "5d Vol",
  range_pct: "Daily Range",
  atr_pct: "ATR %",
  abs_return: "Abs Return",
  volume_zscore: "Volume Z",
  close_vs_sma20: "vs SMA20",
  close_vs_sma50: "vs SMA50",
  high_low_ratio: "H/L Ratio",
  gk_vol_5d: "GK Vol 5d",
  gk_vol_21d: "GK Vol 21d",
  up_vol_ratio: "Up/Down Vol",
  returns: "Returns",
};

function featureLabel(key: string): string {
  return FEATURE_LABELS[key] || key;
}

/** Format feature value — percentages for vol/range, raw for ratios/z-scores */
function formatFeatureVal(key: string, val: number): string {
  if (
    key.includes("vol") ||
    key.includes("range") ||
    key.includes("atr") ||
    key.includes("return") ||
    key.includes("sma") ||
    key === "high_low_ratio"
  ) {
    return formatPct(val);
  }
  return formatNumber(val, 2);
}

// ── Regime Card ──────────────────────────────────────────────────────

function RegimeCard({ stat, method }: { stat: RegimeStat; method: Method }) {
  const hasFeatures = stat.features && Object.keys(stat.features).length > 0;
  const totalRColor =
    stat.total_r > 0
      ? "text-profit"
      : stat.total_r < 0
        ? "text-loss"
        : "text-text-secondary";

  // Pick the most informative features to highlight
  const highlightFeatures = useMemo(() => {
    if (!stat.features) return [];
    const entries = Object.entries(stat.features);

    if (method === "hmm") {
      // HMM: show all 4 features (small set)
      return entries;
    }
    // LSTM: show the top features that define the cluster character
    const priority = [
      "close_vs_sma50",
      "close_vs_sma20",
      "realized_vol_21d",
      "volume_zscore",
      "up_vol_ratio",
      "range_pct",
      "atr_pct",
      "realized_vol_5d",
      "gk_vol_21d",
    ];
    const sorted = entries.sort((a, b) => {
      const ai = priority.indexOf(a[0]);
      const bi = priority.indexOf(b[0]);
      return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
    });
    return sorted.slice(0, 7);
  }, [stat.features, method]);

  return (
    <div className="rounded-lg border border-border bg-bg-secondary">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex items-center gap-2">
          <div className="flex h-6 w-6 items-center justify-center rounded-md bg-accent/20 text-[11px] font-bold text-accent">
            R{stat.regime}
          </div>
          {stat.label && (
            <span className="text-xs font-medium text-text-primary">
              {stat.label}
            </span>
          )}
        </div>
        <div className="flex items-center gap-3 text-[11px] text-text-muted">
          {stat.days != null && <span>{stat.days} days</span>}
          {stat.pct_days != null && (
            <span className="font-medium text-text-secondary">
              {formatPct(stat.pct_days)}
            </span>
          )}
        </div>
      </div>

      <div className="grid gap-0 sm:grid-cols-2">
        {/* Left: Market Character */}
        {hasFeatures && (
          <div className="border-b border-border/60 p-3 sm:border-b-0 sm:border-r">
            <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-text-muted">
              Market Character
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {highlightFeatures.map(([key, val]) => (
                <div key={key} className="flex items-baseline justify-between">
                  <span className="text-[11px] text-text-muted">
                    {featureLabel(key)}
                  </span>
                  <span className="font-mono text-[11px] text-text-secondary">
                    {formatFeatureVal(key, val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Right: Strategy Performance */}
        <div className="p-3">
          <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-text-muted">
            Strategy Performance
          </div>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1">
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">Trades</span>
              <span className="font-mono text-[11px] text-text-secondary">
                {stat.trades}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">Win Rate</span>
              <span className="font-mono text-[11px] text-text-secondary">
                {formatPct(stat.win_rate)}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">Total R</span>
              <span className={`font-mono text-[11px] font-medium ${totalRColor}`}>
                {formatNumber(stat.total_r, 2)}R
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">Avg R</span>
              <span className={`font-mono text-[11px] ${totalRColor}`}>
                {formatNumber(stat.avg_r, 3)}R
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">PF</span>
              <span className="font-mono text-[11px] text-text-secondary">
                {formatNumber(stat.pf, 2)}
              </span>
            </div>
            <div className="flex items-baseline justify-between">
              <span className="text-[11px] text-text-muted">L / S</span>
              <span className="font-mono text-[11px] text-text-secondary">
                {stat.long_trades} / {stat.short_trades}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Method Section ───────────────────────────────────────────────────

function MethodSection({
  method,
  section,
}: {
  method: Method;
  section: RegimeReportSection;
}) {
  const title = method === "hmm" ? "HMM Regimes" : "LSTM Regimes";
  const subtitle =
    method === "hmm"
      ? "Gaussian Hidden Markov Model — clusters days by volatility state"
      : "LSTM Autoencoder + K-Means — clusters days by multi-feature market structure";

  return (
    <div className="space-y-3">
      {/* Section header */}
      <div>
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <div className="flex items-center gap-2 text-[11px] text-text-muted">
            {method === "hmm" && section.states != null && (
              <span className="rounded bg-bg-secondary px-1.5 py-0.5">
                {section.states} states
              </span>
            )}
            {method === "hmm" && section.bic != null && (
              <span className="rounded bg-bg-secondary px-1.5 py-0.5">
                BIC {formatNumber(section.bic, 0)}
              </span>
            )}
            {method === "lstm" && section.clusters != null && (
              <span className="rounded bg-bg-secondary px-1.5 py-0.5">
                {section.clusters} clusters
              </span>
            )}
            {method === "lstm" && section.silhouette != null && (
              <span className="rounded bg-bg-secondary px-1.5 py-0.5">
                silhouette {formatNumber(section.silhouette, 3)}
              </span>
            )}
            <span className="rounded bg-bg-secondary px-1.5 py-0.5">
              mapped {section.coverage.mapped}/{section.coverage.total}
            </span>
          </div>
        </div>
        <p className="mt-0.5 text-[11px] text-text-muted">
          {section.description || subtitle}
        </p>
        {method === "lstm" && section.feature_cols && (
          <p className="mt-0.5 text-[10px] text-text-muted">
            Features: {section.feature_cols.map(featureLabel).join(", ")}
          </p>
        )}
      </div>

      {/* Regime cards */}
      <div className="grid gap-3">
        {section.regime_stats.map((stat) => (
          <RegimeCard key={stat.regime} stat={stat} method={method} />
        ))}
      </div>
    </div>
  );
}

// ── Summary Card ─────────────────────────────────────────────────────

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2">
      <div className="text-[11px] uppercase text-text-muted">{label}</div>
      <div className="text-sm font-medium text-text-primary">{value}</div>
    </div>
  );
}

// ── History Row ──────────────────────────────────────────────────────

function HistoryRow({
  item,
  selected,
  onClick,
}: {
  item: RegimeReportHistoryItem;
  selected: boolean;
  onClick: () => void;
}) {
  const methods = parseMethods(item.methods).join(", ").toUpperCase() || "—";
  return (
    <button
      onClick={onClick}
      className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
        selected
          ? "border-accent bg-accent/10 text-text-primary"
          : "border-border bg-bg-card hover:bg-bg-card-hover text-text-secondary"
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs font-medium">
          {item.backtest_name || item.backtest_result_id}
        </div>
        <div className="text-[10px] text-text-muted">{item.instrument}</div>
      </div>
      <div className="mt-1 text-[11px] text-text-muted">{methods}</div>
      <div className="mt-1 text-[11px] text-text-muted">
        {formatDateRange(item.date_start, item.date_end)}
      </div>
    </button>
  );
}

// ── Main Dashboard ───────────────────────────────────────────────────

export function RegimeDashboard() {
  const { history, loading, loadReport, deleteReport } = useRegimeReports();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<RegimeReportResult | null>(null);
  const [reportLoading, setReportLoading] = useState(false);

  const handleSelectReport = async (resultId: string) => {
    setSelectedId(resultId);
    setReport(null);
    setReportLoading(true);
    try {
      const nextReport = await loadReport(resultId);
      setReport(nextReport);
    } finally {
      setReportLoading(false);
    }
  };

  const selectedItem = useMemo(
    () => history.find((h) => h.result_id === selectedId) || null,
    [history, selectedId],
  );

  const methods = report?.summary?.methods ?? [];
  const hasMethod = (m: Method) => methods.includes(m);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-text-primary">
          Regime Reports
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          HMM/LSTM volatility regime analysis tied to saved backtests.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        {/* Sidebar */}
        <div className="rounded-lg border border-border bg-bg-card p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium text-text-secondary">
              History
            </div>
            <div className="text-[11px] text-text-muted">
              {loading ? <Skeleton className="h-3 w-16 rounded" muted /> : `${history.length} reports`}
            </div>
          </div>
          <div className="space-y-2">
            {loading && (
              <>
                {Array.from({ length: 5 }).map((_, index) => (
                  <Skeleton key={index} className="h-20 rounded-md" muted />
                ))}
              </>
            )}
            {!loading && history.length === 0 && (
              <div className="rounded-md border border-border bg-bg-secondary px-3 py-3 text-xs text-text-muted">
                no regime reports yet
              </div>
            )}
            {!loading && history.map((item) => (
              <HistoryRow
                key={item.result_id}
                item={item}
                selected={item.result_id === selectedId}
                onClick={() => handleSelectReport(item.result_id)}
              />
            ))}
          </div>
        </div>

        {/* Detail panel */}
        <div className="rounded-lg border border-border bg-bg-card p-4">
          {reportLoading && <RegimeDetailSkeleton />}

          {!reportLoading && !report && (
            <div className="flex h-[360px] items-center justify-center text-sm text-text-muted">
              select a regime report to view details
            </div>
          )}

          {!reportLoading && report && (
            <div className="space-y-6">
              {/* Report header */}
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-text-primary">
                    {report.meta.backtest_name ||
                      report.meta.backtest_result_id}
                  </div>
                  <div className="mt-1 text-xs text-text-muted">
                    {report.meta.instrument} ·{" "}
                    {report.meta.sessions || "—"} ·{" "}
                    {formatDateRange(
                      report.meta.date_start,
                      report.meta.date_end,
                    )}
                  </div>
                  <div className="mt-1 text-[11px] text-text-muted">
                    backtest id: {report.meta.backtest_result_id}
                  </div>
                </div>
                {selectedItem && (
                  <div className="text-[11px] text-text-muted">
                    created: {formatTimestamp(selectedItem.timestamp)}
                  </div>
                )}
              </div>

              {/* Summary cards */}
              <div className="grid gap-3 sm:grid-cols-3">
                <SummaryCard
                  label="methods"
                  value={methods.join(" + ") || "—"}
                />
                <SummaryCard
                  label="trades"
                  value={formatNumber(report.summary.trade_count, 0)}
                />
                {report.summary.hmm_total_r != null && (
                  <SummaryCard
                    label="hmm total r"
                    value={`${formatNumber(report.summary.hmm_total_r, 2)}R`}
                  />
                )}
                {report.summary.lstm_total_r != null && (
                  <SummaryCard
                    label="lstm total r"
                    value={`${formatNumber(report.summary.lstm_total_r, 2)}R`}
                  />
                )}
                {report.summary.hmm_best_pf != null && (
                  <SummaryCard
                    label="hmm best pf"
                    value={formatNumber(report.summary.hmm_best_pf, 2)}
                  />
                )}
                {report.summary.lstm_best_pf != null && (
                  <SummaryCard
                    label="lstm best pf"
                    value={formatNumber(report.summary.lstm_best_pf, 2)}
                  />
                )}
              </div>

              {/* HMM Section */}
              {hasMethod("hmm") && report.hmm && (
                <MethodSection method="hmm" section={report.hmm} />
              )}

              {/* LSTM Section */}
              {hasMethod("lstm") && report.lstm && (
                <MethodSection method="lstm" section={report.lstm} />
              )}

              {/* Actions */}
              <div className="flex items-center justify-end">
                <button
                  onClick={() => selectedId && deleteReport(selectedId)}
                  className="rounded-md border border-border bg-bg-secondary px-3 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card-hover"
                >
                  delete report
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RegimeDetailSkeleton() {
  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="w-full max-w-xl">
          <Skeleton className="h-4 w-64 rounded" />
          <SkeletonText lines={2} className="mt-3" />
        </div>
        <Skeleton className="h-3 w-32 rounded" muted />
      </div>
      <MetricGridSkeleton count={3} className="sm:grid-cols-3 lg:grid-cols-3" />
      <Skeleton className="h-72 rounded-lg" />
    </div>
  );
}
