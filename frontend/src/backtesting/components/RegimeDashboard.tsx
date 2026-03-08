import { useEffect, useMemo, useState } from "react";
import { useRegimeReports } from "@/backtesting/hooks/useRegimeReports";
import type { RegimeReportHistoryItem, RegimeReportResult, RegimeStat } from "@/backtesting/lib/types";
import { formatPct, formatNumber } from "@/backtesting/lib/utils";

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

function RegimeStatsTable({ stats }: { stats: RegimeStat[] }) {
  if (!stats.length) {
    return <div className="text-xs text-text-muted">no trades mapped</div>;
  }
  const hasVolProfile = stats.some((s) => s.days != null);
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-xs">
        <thead className="text-text-muted">
          <tr className="border-b border-border">
            <th className="px-2 py-1 text-left">regime</th>
            {hasVolProfile && (
              <>
                <th className="px-2 py-1 text-right">days</th>
                <th className="px-2 py-1 text-right">% days</th>
                <th className="px-2 py-1 text-right">avg vol</th>
                <th className="px-2 py-1 text-right">avg range</th>
              </>
            )}
            <th className="px-2 py-1 text-right">trades</th>
            <th className="px-2 py-1 text-right">win rate</th>
            <th className="px-2 py-1 text-right">total r</th>
            <th className="px-2 py-1 text-right">avg r</th>
            <th className="px-2 py-1 text-right">pf</th>
          </tr>
        </thead>
        <tbody>
          {stats.map((row) => (
            <tr key={row.regime} className="border-b border-border/60">
              <td className="px-2 py-1 text-left">R{row.regime}</td>
              {hasVolProfile && (
                <>
                  <td className="px-2 py-1 text-right">{row.days ?? "—"}</td>
                  <td className="px-2 py-1 text-right">
                    {row.pct_days != null ? formatPct(row.pct_days) : "—"}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {row.mean_vol != null ? formatPct(row.mean_vol) : "—"}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {row.mean_range_pct != null ? formatPct(row.mean_range_pct) : "—"}
                  </td>
                </>
              )}
              <td className="px-2 py-1 text-right">{row.trades}</td>
              <td className="px-2 py-1 text-right">{formatPct(row.win_rate)}</td>
              <td className="px-2 py-1 text-right">{formatNumber(row.total_r, 2)}R</td>
              <td className="px-2 py-1 text-right">{formatNumber(row.avg_r, 3)}R</td>
              <td className="px-2 py-1 text-right">{formatNumber(row.pf, 2)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-bg-secondary px-3 py-2">
      <div className="text-[11px] uppercase text-text-muted">{label}</div>
      <div className="text-sm font-medium text-text-primary">{value}</div>
    </div>
  );
}

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
        <div className="text-xs font-medium">{item.backtest_name || item.backtest_result_id}</div>
        <div className="text-[10px] text-text-muted">{item.instrument}</div>
      </div>
      <div className="mt-1 text-[11px] text-text-muted">{methods}</div>
      <div className="mt-1 text-[11px] text-text-muted">
        {formatDateRange(item.date_start, item.date_end)}
      </div>
    </button>
  );
}

export function RegimeDashboard() {
  const { history, loading, loadReport, deleteReport } = useRegimeReports();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<RegimeReportResult | null>(null);

  useEffect(() => {
    if (!selectedId) {
      setReport(null);
      return;
    }
    loadReport(selectedId).then(setReport);
  }, [selectedId, loadReport]);

  const selectedItem = useMemo(
    () => history.find((h) => h.result_id === selectedId) || null,
    [history, selectedId]
  );

  const methods = report?.summary?.methods ?? [];
  const hasMethod = (m: Method) => methods.includes(m);

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="font-display text-2xl font-bold text-text-primary">Regime Reports</h1>
        <p className="mt-1 text-sm text-text-muted">
          HMM/LSTM volatility regime analysis tied to saved backtests.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="rounded-lg border border-border bg-bg-card p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-sm font-medium text-text-secondary">History</div>
            <div className="text-[11px] text-text-muted">
              {loading ? "loading…" : `${history.length} reports`}
            </div>
          </div>
          <div className="space-y-2">
            {history.length === 0 && (
              <div className="rounded-md border border-border bg-bg-secondary px-3 py-3 text-xs text-text-muted">
                no regime reports yet
              </div>
            )}
            {history.map((item) => (
              <HistoryRow
                key={item.result_id}
                item={item}
                selected={item.result_id === selectedId}
                onClick={() => setSelectedId(item.result_id)}
              />
            ))}
          </div>
        </div>

        <div className="rounded-lg border border-border bg-bg-card p-4">
          {!report && (
            <div className="flex h-[360px] items-center justify-center text-sm text-text-muted">
              select a regime report to view details
            </div>
          )}

          {report && (
            <div className="space-y-5">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-text-primary">
                    {report.meta.backtest_name || report.meta.backtest_result_id}
                  </div>
                  <div className="mt-1 text-xs text-text-muted">
                    {report.meta.instrument} · {report.meta.sessions || "—"} ·{" "}
                    {formatDateRange(report.meta.date_start, report.meta.date_end)}
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

              <div className="grid gap-3 sm:grid-cols-3">
                <SummaryCard label="methods" value={methods.join(" + ") || "—"} />
                <SummaryCard label="trades" value={formatNumber(report.summary.trade_count, 0)} />
                <SummaryCard label="hmm total r" value={report.summary.hmm_total_r != null ? `${formatNumber(report.summary.hmm_total_r, 2)}R` : "—"} />
                <SummaryCard label="lstm total r" value={report.summary.lstm_total_r != null ? `${formatNumber(report.summary.lstm_total_r, 2)}R` : "—"} />
                <SummaryCard label="hmm best pf" value={report.summary.hmm_best_pf != null ? formatNumber(report.summary.hmm_best_pf, 2) : "—"} />
                <SummaryCard label="lstm best pf" value={report.summary.lstm_best_pf != null ? formatNumber(report.summary.lstm_best_pf, 2) : "—"} />
              </div>

              {hasMethod("hmm") && report.hmm && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-text-secondary">HMM Regimes</div>
                    <div className="text-[11px] text-text-muted">
                      states: {report.hmm.states ?? "—"} · mapped {report.hmm.coverage.mapped}/{report.hmm.coverage.total}
                    </div>
                  </div>
                  <RegimeStatsTable stats={report.hmm.regime_stats} />
                </div>
              )}

              {hasMethod("lstm") && report.lstm && (
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-medium text-text-secondary">LSTM Regimes</div>
                    <div className="text-[11px] text-text-muted">
                      clusters: {report.lstm.clusters ?? "—"} · mapped {report.lstm.coverage.mapped}/{report.lstm.coverage.total}
                    </div>
                  </div>
                  <RegimeStatsTable stats={report.lstm.regime_stats} />
                </div>
              )}

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
