import { useState } from "react";
import type { OptimizationHistoryItem } from "../lib/types";
import { formatNumber, pnlColor } from "../lib/utils";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionTag } from "./SessionTag";
import { ScrollArea } from "./ui/scroll-area";

interface OptimizationHistoryPanelProps {
  history: OptimizationHistoryItem[];
  activeId: string | null;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

function formatTimestamp(raw: string): string {
  const [date, time] = raw.split(" ");
  if (!date || !time) return raw;
  const [y, m, d] = date.split("-");
  const hh = time.slice(0, 2);
  const mm = time.slice(2, 4);
  const dt = new Date(+y, +m - 1, +d, +hh, +mm);
  return (
    dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    ", " +
    dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
  );
}

function RefreshButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="rounded p-1 text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary"
      title="Refresh history"
    >
      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M2.5 8a5.5 5.5 0 0 1 9.3-4l1.7 1.7M13.5 8a5.5 5.5 0 0 1-9.3 4l-1.7-1.7" />
        <path d="M13.5 2.5v3h-3M2.5 13.5v-3h3" />
      </svg>
    </button>
  );
}

export function OptimizationHistoryPanel({
  history,
  activeId,
  onLoad,
  onDelete,
  onRefresh,
}: OptimizationHistoryPanelProps) {
  const [deleteId, setDeleteId] = useState<string | null>(null);

  if (history.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-text-secondary">History</h2>
          <RefreshButton onClick={onRefresh} />
        </div>
        <p className="mt-3 text-center text-xs text-text-muted">
          No saved optimizations yet
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-bg-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-medium text-text-secondary">History</h2>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">{history.length} runs</span>
          <RefreshButton onClick={onRefresh} />
        </div>
      </div>

      <ScrollArea className="h-[480px]">
        <div className="space-y-1.5">
          {history.map((item) => {
            const isActive = item.id === activeId;

            return (
              <button
                key={item.id}
                onClick={() => onLoad(item.id)}
                className={`group relative w-full rounded-md border px-3 py-2.5 text-left transition-colors ${
                  isActive
                    ? "border-accent/50 bg-accent/8"
                    : "border-transparent hover:bg-bg-card-hover"
                }`}
              >
                {/* Delete button */}
                <span
                  role="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeleteId(item.id);
                  }}
                  className="absolute right-2 top-2 hidden rounded p-0.5 text-text-muted hover:bg-bg-secondary hover:text-text-primary group-hover:block"
                >
                  <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                  </svg>
                </span>

                {/* Top: instrument + sessions */}
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-text-primary">
                    {item.instrument}
                  </span>
                  {item.sessions.map((s) => (
                    <SessionTag key={s} session={s} />
                  ))}
                </div>

                {/* Swept params */}
                <div className="mt-2 text-[10px] text-text-muted">
                  {item.swept_params.join(", ")} ({item.total_combinations} combos)
                </div>

                {/* Metrics */}
                <div className="mt-1 flex items-center gap-3">
                  <span className="font-mono text-sm font-semibold text-accent">
                    Sharpe {formatNumber(item.best_sharpe, 3)}
                  </span>
                  <span
                    className="font-mono text-xs font-medium"
                    style={{ color: pnlColor(item.best_pnl_usd) }}
                  >
                    {item.best_pnl_usd >= 0 ? "+" : ""}{(item.best_pnl_usd / (item.risk_usd || 50000)).toFixed(2)}R
                  </span>
                </div>

                {/* Timestamp */}
                <div className="mt-0.5 text-[10px] text-text-muted">
                  {formatTimestamp(item.timestamp)}
                </div>
              </button>
            );
          })}
        </div>
      </ScrollArea>

      <ConfirmDeleteDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null); }}
        onConfirm={() => { if (deleteId) onDelete(deleteId); }}
        title="Delete this optimization?"
        description="The saved optimization result will be permanently removed."
      />
    </div>
  );
}
