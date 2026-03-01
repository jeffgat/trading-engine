import { useState } from "react";
import { useCoverage } from "@/backtesting/hooks/useCoverage";
import type {
  InstrumentCoverage,
  TestingPlanItem,
  ParamCoverageDetail,
} from "@/backtesting/lib/types";
import { SessionTag } from "./SessionTag";
import { Skeleton } from "./Skeleton";
import { formatNumber, pnlColor } from "@/backtesting/lib/utils";

// All registered instruments — show cards even for untested ones
const ALL_INSTRUMENTS = ["NQ", "MNQ", "ES", "CL", "YM"];

const PARAM_LABELS: Record<string, string> = {
  rr: "R:R",
  tp1_ratio: "TP1 Ratio",
  ny_stop_atr_pct: "NY Stop ATR%",
  ny_min_gap_atr_pct: "NY Min Gap ATR%",
  asia_stop_atr_pct: "Asia Stop ATR%",
  asia_min_gap_atr_pct: "Asia Min Gap ATR%",
  ldn_stop_atr_pct: "LDN Stop ATR%",
  ldn_min_gap_atr_pct: "LDN Min Gap ATR%",
};

const ALL_SESSIONS = ["NY", "ASIA", "LDN"];

function generateSuggestions(
  coverage: InstrumentCoverage | null,
  planItems: TestingPlanItem[],
  paramDetail?: Record<string, ParamCoverageDetail>
): string[] {
  const pool: string[] = [];
  const pendingTitles = planItems
    .filter((i) => i.status === "pending")
    .map((i) => i.title.toLowerCase());

  // P1: No runs at all
  if (!coverage) {
    pool.push("Run baseline NY backtest");
    return pool.slice(0, 3);
  }

  // P2: Session not tested
  const tested = new Set(coverage.sessions_tested.map((s) => s.toUpperCase()));
  for (const session of ALL_SESSIONS) {
    if (!tested.has(session)) {
      pool.push(`Test ${session} session`);
    }
  }

  // P3: No optimizations
  if (coverage.optimization_count === 0 && coverage.sessions_tested.length > 0) {
    pool.push(`Run parameter sweep on ${coverage.sessions_tested[0]}`);
  }

  // P4: Only 1 value tested for a key param
  if (paramDetail) {
    for (const [param, detail] of Object.entries(paramDetail)) {
      if (detail.count === 1) {
        const label = PARAM_LABELS[param] ?? param;
        pool.push(`Sweep ${label} (only ${detail.values[0]} tested)`);
      }
    }
  }

  // P5: Negative or null best Sharpe
  if (coverage.best_sharpe != null && coverage.best_sharpe < 0) {
    pool.push(`Investigate negative Sharpe (${formatNumber(coverage.best_sharpe)})`);
  } else if (coverage.best_sharpe == null && (coverage.backtest_count + coverage.optimization_count) > 0) {
    pool.push("Investigate null Sharpe");
  }

  // P6: Low param diversity (2-3 values)
  if (paramDetail) {
    for (const [param, detail] of Object.entries(paramDetail)) {
      if (detail.count >= 2 && detail.count <= 3) {
        const label = PARAM_LABELS[param] ?? param;
        pool.push(`Expand ${label} range (${formatNumber(detail.min)}–${formatNumber(detail.max)})`);
      }
    }
  }

  // P7: No recent runs (> 30 days)
  if (coverage.last_run_at) {
    const daysSince = (Date.now() - new Date(coverage.last_run_at).getTime()) / (1000 * 60 * 60 * 24);
    if (daysSince > 30) {
      pool.push("Re-test with latest data");
    }
  }

  // Filter out suggestions that match existing pending items (fuzzy substring)
  const filtered = pool.filter((s) => {
    const lower = s.toLowerCase();
    return !pendingTitles.some((t) => lower.includes(t) || t.includes(lower));
  });

  return filtered.slice(0, 3);
}

export function CoverageDashboard() {
  const {
    coverage,
    planItems,
    loading,
    paramCoverage,
    loadParamCoverage,
    createPlanItem,
    updatePlanItem,
    deletePlanItem,
  } = useCoverage();

  if (loading) {
    return (
      <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
        <h1 className="mb-6 text-xl font-semibold text-text-primary">
          Testing Coverage
        </h1>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[320px] rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  // Build a lookup from coverage data
  const coverageMap = new Map<string, InstrumentCoverage>();
  for (const c of coverage) {
    coverageMap.set(c.instrument, c);
  }

  // Group plan items by instrument
  const planByInstrument = new Map<string, TestingPlanItem[]>();
  for (const item of planItems) {
    const list = planByInstrument.get(item.instrument) ?? [];
    list.push(item);
    planByInstrument.set(item.instrument, list);
  }

  // Merge: all registered instruments + any from coverage data
  const instrumentSet = new Set([
    ...ALL_INSTRUMENTS,
    ...coverageMap.keys(),
  ]);
  const instruments = [...instrumentSet].sort();

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-text-primary">
          Testing Coverage
        </h1>
        <p className="mt-1 text-sm text-text-muted">
          Auto-derived from experiment history. Add checklist items to track
          what to test next.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {instruments.map((inst) => (
          <InstrumentCard
            key={inst}
            instrument={inst}
            coverage={coverageMap.get(inst) ?? null}
            planItems={planByInstrument.get(inst) ?? []}
            paramDetail={paramCoverage[inst]}
            onLoadParams={loadParamCoverage}
            onCreateItem={createPlanItem}
            onUpdateItem={updatePlanItem}
            onDeleteItem={deletePlanItem}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Instrument Card
// ---------------------------------------------------------------------------

interface InstrumentCardProps {
  instrument: string;
  coverage: InstrumentCoverage | null;
  planItems: TestingPlanItem[];
  paramDetail?: Record<string, ParamCoverageDetail>;
  onLoadParams: (instrument: string) => Promise<void>;
  onCreateItem: (
    instrument: string,
    title: string,
    notes?: string
  ) => Promise<TestingPlanItem | null>;
  onUpdateItem: (
    id: number,
    updates: { title?: string; notes?: string; status?: string }
  ) => Promise<void>;
  onDeleteItem: (id: number) => Promise<void>;
}

function InstrumentCard({
  instrument,
  coverage,
  planItems,
  paramDetail,
  onLoadParams,
  onCreateItem,
  onUpdateItem,
  onDeleteItem,
}: InstrumentCardProps) {
  const [paramsExpanded, setParamsExpanded] = useState(false);

  const totalRuns =
    (coverage?.backtest_count ?? 0) + (coverage?.optimization_count ?? 0);

  const suggestions = generateSuggestions(coverage, planItems, paramDetail);

  const handleExpandParams = () => {
    const next = !paramsExpanded;
    setParamsExpanded(next);
    if (next && !paramDetail) {
      onLoadParams(instrument);
    }
  };

  const formatTimestamp = (ts: string) => {
    if (!ts) return "";
    try {
      const d = new Date(ts);
      return d.toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return ts.slice(0, 10);
    }
  };

  const pendingItems = planItems.filter((i) => i.status === "pending");
  const completedItems = planItems.filter((i) => i.status === "completed");

  return (
    <div className="rounded-lg border border-border bg-bg-card">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-text-primary">
            {instrument}
          </span>
          {totalRuns > 0 && (
            <span className="rounded-full bg-accent/15 px-2 py-0.5 text-[11px] font-medium text-accent">
              {totalRuns} runs
            </span>
          )}
        </div>
        {coverage?.last_run_at && (
          <span className="text-[11px] text-text-muted">
            Last: {formatTimestamp(coverage.last_run_at)}
          </span>
        )}
      </div>

      <div className="p-4 space-y-3">
        {/* Auto-derived stats */}
        {coverage ? (
          <>
            {/* Sessions */}
            {coverage.sessions_tested.length > 0 && (
              <div className="flex items-center gap-1.5">
                {coverage.sessions_tested.map((s) => (
                  <SessionTag key={s} session={s} />
                ))}
              </div>
            )}

            {/* Counts + date range */}
            <div className="text-xs text-text-secondary space-y-1">
              <div>
                {coverage.backtest_count} backtests,{" "}
                {coverage.optimization_count} optimizations
              </div>
              {coverage.earliest_date && (
                <div className="text-text-muted">
                  {coverage.earliest_date.slice(0, 7)} &mdash;{" "}
                  {coverage.latest_date.slice(0, 7)}
                </div>
              )}
            </div>

            {/* Best results */}
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
              <MetricCell
                label="Sharpe"
                value={coverage.best_sharpe}
                format={(v) => formatNumber(v)}
              />
              <MetricCell
                label="R/yr"
                value={coverage.best_r_per_year}
                format={(v) => formatNumber(v)}
                colored
              />
              <MetricCell
                label="Win Rate"
                value={coverage.best_win_rate}
                format={(v) => `${(v * 100).toFixed(1)}%`}
              />
              <MetricCell
                label="PF"
                value={coverage.best_profit_factor}
                format={(v) => formatNumber(v)}
              />
            </div>

            {/* Param coverage (collapsible) */}
            <button
              onClick={handleExpandParams}
              className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text-secondary transition-colors"
            >
              <span
                className="inline-block transition-transform"
                style={{
                  transform: paramsExpanded ? "rotate(90deg)" : "rotate(0deg)",
                }}
              >
                &#9654;
              </span>
              Param coverage
            </button>

            {paramsExpanded && (
              <div className="rounded border border-border bg-bg-secondary p-2 text-[11px] text-text-secondary space-y-0.5">
                {paramDetail ? (
                  Object.keys(paramDetail).length > 0 ? (
                    Object.entries(paramDetail).map(([param, detail]) => (
                      <ParamRow key={param} param={param} detail={detail} />
                    ))
                  ) : (
                    <span className="text-text-muted">
                      No param variation found
                    </span>
                  )
                ) : (
                  <span className="text-text-muted">Loading...</span>
                )}
              </div>
            )}
          </>
        ) : (
          <div className="py-2 text-center text-xs text-text-muted">
            No tests run yet
          </div>
        )}

        {/* Checklist */}
        <div className="border-t border-border pt-3">
          <div className="mb-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">
            Testing Plan
          </div>

          <div className="space-y-1">
            {pendingItems.map((item) => (
              <ChecklistItem
                key={item.id}
                item={item}
                onToggle={() =>
                  onUpdateItem(item.id, { status: "completed" })
                }
                onDelete={() => onDeleteItem(item.id)}
              />
            ))}
            {completedItems.map((item) => (
              <ChecklistItem
                key={item.id}
                item={item}
                onToggle={() =>
                  onUpdateItem(item.id, { status: "pending" })
                }
                onDelete={() => onDeleteItem(item.id)}
              />
            ))}
          </div>

          {/* Suggestion chips */}
          {suggestions.length > 0 && (
            <div className="mt-2 space-y-1.5">
              <div className="text-[10px] font-medium uppercase tracking-wider text-text-muted">
                Suggestions
              </div>
              <div className="flex flex-wrap gap-1.5">
                {suggestions.map((suggestion) => (
                  <button
                    key={suggestion}
                    onClick={() => onCreateItem(instrument, suggestion)}
                    className="inline-flex items-center gap-1 rounded border border-border px-2 py-0.5 text-[11px] text-text-muted hover:border-text-muted hover:text-text-secondary hover:bg-bg-secondary transition-colors"
                  >
                    <span className="text-accent">+</span>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function MetricCell({
  label,
  value,
  format,
  colored,
}: {
  label: string;
  value: number | null;
  format: (v: number) => string;
  colored?: boolean;
}) {
  if (value == null) {
    return (
      <div>
        <span className="text-text-muted">{label}</span>{" "}
        <span className="text-text-muted">&mdash;</span>
      </div>
    );
  }
  return (
    <div>
      <span className="text-text-muted">{label}</span>{" "}
      <span
        className="font-medium"
        style={colored ? { color: pnlColor(value) } : undefined}
      >
        {format(value)}
      </span>
    </div>
  );
}

function ParamRow({
  param,
  detail,
}: {
  param: string;
  detail: ParamCoverageDetail;
}) {
  const label = PARAM_LABELS[param] ?? param;
  return (
    <div className="flex justify-between">
      <span className="text-text-muted">{label}</span>
      <span>
        {formatNumber(detail.min)} &ndash; {formatNumber(detail.max)}{" "}
        <span className="text-text-muted">({detail.count} values)</span>
      </span>
    </div>
  );
}

function ChecklistItem({
  item,
  onToggle,
  onDelete,
}: {
  item: TestingPlanItem;
  onToggle: () => void;
  onDelete: () => void;
}) {
  const isCompleted = item.status === "completed";

  return (
    <div className="group flex items-center gap-2 rounded px-1 py-0.5 hover:bg-bg-secondary">
      <button
        onClick={onToggle}
        className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-sm border transition-colors ${
          isCompleted
            ? "border-accent bg-accent/20 text-accent"
            : "border-border hover:border-text-muted"
        }`}
      >
        {isCompleted && (
          <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
            <path
              d="M1.5 4L3.25 5.75L6.5 2.25"
              stroke="currentColor"
              strokeWidth="1.2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        )}
      </button>
      <span
        className={`flex-1 text-xs ${
          isCompleted
            ? "text-text-muted line-through opacity-60"
            : "text-text-secondary"
        }`}
      >
        {item.title}
      </span>
      <button
        onClick={onDelete}
        className="hidden text-text-muted hover:text-red-400 group-hover:block"
        title="Delete"
      >
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
          <path
            d="M3 3L9 9M9 3L3 9"
            stroke="currentColor"
            strokeWidth="1.2"
            strokeLinecap="round"
          />
        </svg>
      </button>
    </div>
  );
}
