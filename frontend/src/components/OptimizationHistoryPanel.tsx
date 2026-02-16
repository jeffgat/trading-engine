import { useMemo, useState } from "react";
import type { OptimizationHistoryItem } from "../lib/types";
import { formatNumber, pnlColor } from "../lib/utils";
import { CopyIdButton } from "./CopyIdButton";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { SessionTag } from "./SessionTag";
import { ScrollArea } from "./ui/scroll-area";

type SortKey =
  | "instrument"
  | "total_combinations"
  | "best_sharpe"
  | "best_pnl_usd";

interface OptimizationHistoryPanelProps {
  history: OptimizationHistoryItem[];
  activeId: string | null;
  onLoad: (id: string) => void;
  onDelete: (id: string) => void;
  onRefresh: () => void;
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
  const [sortKey, setSortKey] = useState<SortKey>("best_sharpe");
  const [sortAsc, setSortAsc] = useState(false);
  const [instrumentFilter, setInstrumentFilter] = useState<string>("all");

  const instruments = useMemo(() => {
    const set = new Set(history.map((h) => h.instrument));
    return Array.from(set).sort();
  }, [history]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc(!sortAsc);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const filtered = useMemo(() => {
    if (instrumentFilter === "all") return history;
    return history.filter((h) => h.instrument === instrumentFilter);
  }, [history, instrumentFilter]);

  const sorted = useMemo(() => {
    const arr = [...filtered];
    arr.sort((a, b) => {
      if (sortKey === "instrument") {
        return sortAsc
          ? a.instrument.localeCompare(b.instrument)
          : b.instrument.localeCompare(a.instrument);
      }
      const va = (a[sortKey] ?? 0) as number;
      const vb = (b[sortKey] ?? 0) as number;
      return sortAsc ? va - vb : vb - va;
    });
    return arr;
  }, [filtered, sortKey, sortAsc]);

  const SortHeader = ({ label, sortBy, align = "right" }: { label: string; sortBy: SortKey; align?: "left" | "right" }) => {
    const isActive = sortKey === sortBy;
    return (
      <th
        className={`whitespace-nowrap px-3 py-2 font-medium cursor-pointer select-none transition-colors hover:text-text-primary ${
          align === "left" ? "text-left" : "text-right"
        }`}
        onClick={() => handleSort(sortBy)}
      >
        <span className={isActive ? "text-accent" : ""}>
          {label}
          {isActive && (
            <span className="ml-0.5">{sortAsc ? "\u25B2" : "\u25BC"}</span>
          )}
        </span>
      </th>
    );
  };

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
    <div className="rounded-lg border border-border bg-bg-card">
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-medium text-text-secondary">History</h2>
          {instruments.length > 1 && (
            <select
              value={instrumentFilter}
              onChange={(e) => setInstrumentFilter(e.target.value)}
              className="rounded border border-border bg-bg-secondary px-2 py-0.5 text-xs text-text-primary outline-none focus:border-accent"
            >
              <option value="all">All instruments</option>
              {instruments.map((inst) => (
                <option key={inst} value={inst}>{inst}</option>
              ))}
            </select>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-text-muted">{sorted.length} runs</span>
          <RefreshButton onClick={onRefresh} />
        </div>
      </div>

      <ScrollArea className="h-[288px]">
        <table className="w-full text-xs">
          <thead className="sticky top-0 z-10 bg-bg-card">
            <tr className="border-b border-border text-text-muted">
              <SortHeader label="Instrument" sortBy="instrument" align="left" />
              <th className="whitespace-nowrap px-3 py-2 text-left font-medium">Sessions</th>
              <th className="whitespace-nowrap px-3 py-2 text-left font-medium">Swept Params</th>
              <SortHeader label="Combos" sortBy="total_combinations" />
              <SortHeader label="Best Sharpe" sortBy="best_sharpe" />
              <SortHeader label="Best PnL (R)" sortBy="best_pnl_usd" />
              <th className="w-8 px-2 py-2" />
            </tr>
          </thead>
          <tbody>
            {sorted.map((item) => {
              const isActive = item.id === activeId;
              const bestR = (item.best_pnl_usd ?? 0) / (item.risk_usd || 50000);

              return (
                <tr
                  key={item.id}
                  onClick={() => onLoad(item.id)}
                  className={`group cursor-pointer border-l-2 transition-colors ${
                    isActive
                      ? "border-l-accent bg-accent/8"
                      : "border-l-transparent hover:bg-bg-card-hover"
                  }`}
                >
                  <td className="px-3 py-2 text-left">
                    <div className="flex items-start gap-1">
                      <div className="flex flex-col">
                        {item.name && (
                          <span className="text-[10px] font-medium text-accent leading-tight">
                            {item.name}
                          </span>
                        )}
                        <span className="font-bold text-text-primary">{item.instrument}</span>
                      </div>
                      <CopyIdButton value={item.name || item.id} />
                    </div>
                  </td>
                  <td className="px-3 py-2 text-left">
                    <div className="flex gap-1">
                      {item.sessions.map((s) => (
                        <SessionTag key={s} session={s} />
                      ))}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-left text-text-muted">
                    {item.swept_params.join(", ")}
                  </td>
                  <td className="px-3 py-2 text-right text-text-secondary">
                    {item.total_combinations}
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold text-accent">
                    {formatNumber(item.best_sharpe ?? 0, 3)}
                  </td>
                  <td
                    className="px-3 py-2 text-right font-mono font-medium"
                    style={{ color: pnlColor(item.best_pnl_usd ?? 0) }}
                  >
                    {bestR >= 0 ? "+" : ""}{bestR.toFixed(2)}R
                  </td>
                  <td className="px-2 py-2 text-center">
                    <span
                      role="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteId(item.id);
                      }}
                      className="hidden rounded p-0.5 text-text-muted hover:bg-bg-secondary hover:text-text-primary group-hover:inline-block"
                    >
                      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="currentColor">
                        <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                      </svg>
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
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
