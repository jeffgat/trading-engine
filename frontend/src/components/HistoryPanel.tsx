import { useState } from "react";
import type { BacktestHistoryItem } from "../lib/types";
import { formatPct } from "../lib/utils";
import { ScrollArea } from "./ui/scroll-area";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionTag } from "./SessionTag";

const R_VALUE = 50000;

function formatR(r: number): string {
  const sign = r >= 0 ? "+" : "";
  return `${sign}${r.toFixed(2)}R`;
}

interface HistoryPanelProps {
  history: BacktestHistoryItem[];
  activeId: string | null;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
}

function formatTimestamp(raw: string): string {
  // raw: "2026-02-14 153045" → "Feb 14, 3:30 PM"
  const [date, time] = raw.split(" ");
  if (!date || !time) return raw;
  const [y, m, d] = date.split("-");
  const hh = time.slice(0, 2);
  const mm = time.slice(2, 4);
  const dt = new Date(+y, +m - 1, +d, +hh, +mm);
  return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
    ", " +
    dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function formatDateRange(start: string, end: string): string {
  // "2020-01-06" → "Jan 2020"
  if (!start || !end) return "";
  const fmt = (d: string) => {
    const [y, m] = d.split("-");
    const dt = new Date(+y, +m - 1);
    return dt.toLocaleDateString("en-US", { month: "short", year: "numeric" });
  };
  return `${fmt(start)} — ${fmt(end)}`;
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

export function HistoryPanel({ history, activeId, onLoad, onDelete, onRefresh }: HistoryPanelProps) {
  const [deleteId, setDeleteId] = useState<string | null>(null);

  if (history.length === 0) {
    return (
      <div className="rounded-lg border border-border bg-bg-card p-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium text-text-secondary">History</h2>
          <RefreshButton onClick={onRefresh} />
        </div>
        <p className="mt-3 text-center text-xs text-text-muted">
          No saved backtests yet
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
          const netR = item.total_pnl_usd / R_VALUE;
          const pnlPositive = netR >= 0;

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

              {/* Name label */}
              {item.name && (
                <div className="mb-0.5 text-xs font-medium text-accent">
                  {item.name}
                </div>
              )}

              {/* Top line: instrument + sessions */}
              <div className="flex items-center gap-2">
                <span className="text-xs font-medium text-text-secondary">
                  {item.instrument}
                </span>
                {item.sessions.map((s) => (
                  <SessionTag key={s} session={s} />
                ))}
              </div>

              {/* Date range */}
              {item.date_start && item.date_end && (
                <div className="mt-0.5 text-[10px] text-text-muted">
                  {formatDateRange(item.date_start, item.date_end)}
                </div>
              )}

              {/* Bottom line: P&L + trades + win rate */}
              <div className="mt-1 flex items-center gap-3">
                <span
                  className="font-mono text-sm font-semibold"
                  style={{ color: pnlPositive ? "var(--color-profit)" : "var(--color-loss)" }}
                >
                  {formatR(netR)}
                </span>
                <span className="text-xs text-text-muted">
                  {item.total_trades} trades
                </span>
                <span className="text-xs text-text-muted">
                  {formatPct(item.win_rate)} win
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
        title="Delete this backtest?"
        description="The saved backtest result will be permanently removed."
      />
    </div>
  );
}
