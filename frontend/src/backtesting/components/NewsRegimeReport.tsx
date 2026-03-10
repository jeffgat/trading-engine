import { useEffect, useState } from "react";
import { formatNumber, formatPct, pnlColor } from "@/backtesting/lib/utils";
import type { NewsStraddleEvent } from "@/backtesting/lib/types";

interface BucketStats {
  trades: number;
  win_rate: number;
  target_hit_rate: number;
  avg_final_pts: number;
  total_pts: number;
  median_final_pts: number;
  avg_mfe: number;
  avg_mae: number;
  stop_loss_rate: number;
  whipsaw_rate: number;
}

interface DimensionData {
  label: string;
  thresholds?: Record<string, number>;
  buckets: Record<string, BucketStats>;
}

interface RegimeReport {
  total_filled: number;
  date_range: { start: string; end: string };
  instrument: string;
  dimensions: Record<string, DimensionData>;
  error?: string;
}

interface Props {
  events: NewsStraddleEvent[];
  instrument: string;
}

// Dimension display order + which ones start expanded
const DIMENSION_ORDER = [
  "volatility_atr",
  "realized_vol_5d",
  "volume",
  "trend_sma20",
  "prior_day_return",
  "direction",
  "day_of_week",
  "month",
];

function BucketTable({ dimension }: { dimension: DimensionData }) {
  const entries = Object.entries(dimension.buckets);
  const allTrades = entries.reduce((s, [, b]) => s + b.trades, 0);

  // Find best/worst win rate for highlighting
  const winRates = entries.map(([, b]) => b.win_rate);
  const bestWR = Math.max(...winRates);
  const worstWR = Math.min(...winRates);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs text-text-muted">
          <tr>
            <th className="px-3 py-2">Bucket</th>
            <th className="px-3 py-2 text-right">Trades</th>
            <th className="px-3 py-2 text-right">%</th>
            <th className="px-3 py-2 text-right">Win Rate</th>
            <th className="px-3 py-2 text-right">Target Hit</th>
            <th className="px-3 py-2 text-right">Avg Pts</th>
            <th className="px-3 py-2 text-right">Total Pts</th>
            <th className="px-3 py-2 text-right">Avg MFE</th>
            <th className="px-3 py-2 text-right">Avg MAE</th>
            <th className="px-3 py-2 text-right">SL Rate</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([name, stats]) => {
            const pct = allTrades > 0 ? stats.trades / allTrades : 0;
            const isBest = entries.length > 1 && stats.win_rate === bestWR;
            const isWorst = entries.length > 1 && stats.win_rate === worstWR && bestWR !== worstWR;

            return (
              <tr
                key={name}
                className={`border-t border-border/50 ${
                  isBest ? "bg-profit/5" : isWorst ? "bg-loss/5" : ""
                }`}
              >
                <td className="whitespace-nowrap px-3 py-2 font-medium text-text-primary">
                  {name}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-secondary">
                  {stats.trades}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-muted">
                  {formatPct(pct)}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono font-semibold"
                  style={{ color: pnlColor(stats.win_rate - 0.5) }}
                >
                  {formatPct(stats.win_rate)}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono"
                  style={{ color: pnlColor(stats.target_hit_rate - 0.5) }}
                >
                  {formatPct(stats.target_hit_rate)}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono"
                  style={{ color: pnlColor(stats.avg_final_pts) }}
                >
                  {formatNumber(stats.avg_final_pts)}
                </td>
                <td
                  className="px-3 py-2 text-right font-mono"
                  style={{ color: pnlColor(stats.total_pts) }}
                >
                  {formatNumber(stats.total_pts)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-profit">
                  {formatNumber(stats.avg_mfe)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-loss">
                  {formatNumber(stats.avg_mae)}
                </td>
                <td className="px-3 py-2 text-right font-mono text-text-muted">
                  {formatPct(stats.stop_loss_rate)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function NewsRegimeReport({ events, instrument }: Props) {
  const [report, setReport] = useState<RegimeReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);
  const [collapsedDims, setCollapsedDims] = useState<Set<string>>(new Set());

  // Clear stale regime report when events change (e.g. loading a different history run)
  useEffect(() => {
    setReport(null);
    setError(null);
  }, [events]);

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/bt-api/news-straddle/regime", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ events, instrument }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
      }
      const json = await res.json();
      setReport(json.result ?? json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  };

  const toggleDim = (key: string) => {
    setCollapsedDims((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <div className="mb-6 rounded-lg border border-border bg-bg-card">
      <div
        className="flex cursor-pointer items-center justify-between border-b border-border px-4 py-3"
        onClick={() => setExpanded((v) => !v)}
      >
        <h3 className="text-sm font-medium text-text-secondary">
          Regime Analysis
        </h3>
        <div className="flex items-center gap-3">
          {!report && !loading && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                runAnalysis();
              }}
              className="rounded-md bg-accent/20 px-3 py-1 text-xs font-medium text-accent hover:bg-accent/30 transition-colors"
            >
              Run Analysis
            </button>
          )}
          <span className="text-xs text-text-muted">
            {expanded ? "\u25BC" : "\u25B6"}
          </span>
        </div>
      </div>

      {expanded && (
        <div className="p-4">
          {loading && (
            <div className="py-8 text-center text-sm text-text-muted">
              Analyzing market regimes...
            </div>
          )}

          {error && (
            <div className="rounded border border-loss/30 bg-loss/10 px-3 py-2 text-sm text-loss">
              {error}
            </div>
          )}

          {!report && !loading && !error && (
            <div className="py-6 text-center text-sm text-text-muted">
              Click "Run Analysis" to analyze how volatility, trend, and other
              market conditions affect win rate and performance.
            </div>
          )}

          {report && report.error && (
            <div className="rounded border border-loss/30 bg-loss/10 px-3 py-2 text-sm text-loss">
              {report.error}
            </div>
          )}

          {report && !report.error && (
            <div className="space-y-4">
              <div className="text-xs text-text-muted">
                {report.total_filled} filled trades | {report.date_range.start} to{" "}
                {report.date_range.end} | {report.instrument}
              </div>

              {DIMENSION_ORDER.filter((k) => k in report.dimensions).map(
                (key) => {
                  const dim = report.dimensions[key];
                  const isCollapsed = collapsedDims.has(key);

                  return (
                    <div
                      key={key}
                      className="rounded border border-border bg-bg-primary"
                    >
                      <div
                        className="flex cursor-pointer items-center justify-between px-3 py-2"
                        onClick={() => toggleDim(key)}
                      >
                        <span className="text-sm font-medium text-text-secondary">
                          {dim.label}
                        </span>
                        <span className="text-xs text-text-muted">
                          {isCollapsed ? "\u25B6" : "\u25BC"}
                        </span>
                      </div>
                      {!isCollapsed && <BucketTable dimension={dim} />}
                    </div>
                  );
                }
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
