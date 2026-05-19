import { useCallback, useMemo, useState } from "react";
import type { SavedConfig } from "@/backtesting/lib/types";
import { useSavedConfigs } from "@/backtesting/hooks/useSavedConfigs";
import type { SavedConfigInput } from "@/backtesting/hooks/useSavedConfigs";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { ConfigBar } from "./ConfigBar";
import { SessionTag } from "./SessionTag";
import { StrategyTag } from "./StrategyTag";
import { VariablesTested } from "./VariablesTested";
import { DateRangePicker } from "./DateRangePicker";
import { Skeleton, SkeletonText } from "@/shared/ui/skeleton";

const INPUT_CLASS =
  "w-full rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-accent";

function formatDateInput(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDefaultBacktestRange() {
  const end = new Date();
  const start = new Date(end);
  start.setFullYear(start.getFullYear() - 10);
  return {
    start: formatDateInput(start),
    end: formatDateInput(end),
  };
}

function normalizeSessionName(session: string): string {
  const normalized = session.trim().toUpperCase();
  if (normalized === "ASIA") return "Asia";
  if (normalized === "LDN") return "LDN";
  return "NY";
}

/** Build a flat params object from a SavedConfig for the backtest API. */
function configToBacktestParams(
  config: SavedConfig,
  start: string,
  end: string,
): Record<string, unknown> {
  const c = config.config;
  const params: Record<string, unknown> = {
    instrument: config.instrument,
    sessions: config.sessions.map(normalizeSessionName),
    start,
    end,
    name: config.name,
    // Global params
    rr: c.rr,
    tp1_ratio: c.tp1_ratio,
    risk_usd: c.risk_usd,
    atr_length: c.atr_length,
    strategy: c.strategy ?? config.strategy,
  };

  // Forward all remaining config keys (session-prefixed params, LSI params, etc.)
  for (const [key, value] of Object.entries(c)) {
    if (value != null && !(key in params) && key !== "min_qty" && key !== "qty_step" && key !== "point_value" && key !== "instrument") {
      params[key] = value;
    }
  }

  return params;
}

function formatUpdated(ts: string) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", year: "'26" === `'${d.getFullYear() % 100}` ? undefined : "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ConfigsDashboard() {
  const defaultRange = useMemo(() => getDefaultBacktestRange(), []);
  const { configs, loading, error, updateConfig, deleteConfig } = useSavedConfigs();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  // Date range for running backtests
  const [dateStart, setDateStart] = useState(defaultRange.start);
  const [dateEnd, setDateEnd] = useState(defaultRange.end);

  // Backtest run state
  const [btLoading, setBtLoading] = useState(false);
  const [btResult, setBtResult] = useState<{ id: string; trades: number; netR: number; sharpe: number; maxDDR: number; winRate: number } | null>(null);
  const [btError, setBtError] = useState<string | null>(null);

  const active = configs.find((c) => c.id === activeId) ?? null;

  const handleSelect = useCallback((config: SavedConfig) => {
    setActiveId(config.id);
    setEditName(config.name);
    setEditNotes(config.notes ?? "");
    setSaveMsg(null);
    setBtResult(null);
    setBtError(null);
  }, []);

  const handleDateChange = useCallback((start: string, end: string) => {
    setDateStart(start);
    setDateEnd(end);
  }, []);

  const handleDateReset = useCallback(() => {
    setDateStart(defaultRange.start);
    setDateEnd(defaultRange.end);
  }, [defaultRange.end, defaultRange.start]);

  const handleRunBacktest = async () => {
    if (!active) return;
    setBtLoading(true);
    setBtResult(null);
    setBtError(null);
    try {
      const params = configToBacktestParams(active, dateStart, dateEnd);
      const res = await fetch("/bt-api/backtest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(params),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error?.message || body.detail || `HTTP ${res.status}`);
      }
      const json = await res.json();
      const result = json.result ?? json;
      const riskUsd = result.config?.risk_usd ?? active.config.risk_usd ?? 5000;
      setBtResult({
        id: result.id,
        trades: result.summary?.total_trades ?? 0,
        netR: result.summary?.total_pnl_usd != null
          ? +(result.summary.total_pnl_usd / riskUsd).toFixed(1)
          : 0,
        sharpe: result.summary?.sharpe_ratio ?? 0,
        maxDDR: result.summary?.max_drawdown_usd != null
          ? +(result.summary.max_drawdown_usd / riskUsd).toFixed(2)
          : 0,
        winRate: result.summary?.win_rate ?? 0,
      });
    } catch (err) {
      setBtError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setBtLoading(false);
    }
  };

  const handleSave = async () => {
    if (!active) return;
    setSaving(true);
    setSaveMsg(null);
    const payload: SavedConfigInput = {
      name: editName.trim() || active.name,
      notes: editNotes.trim() || null,
      instrument: active.instrument,
      sessions: active.sessions,
      strategy: active.strategy,
      config: active.config,
    };
    const result = await updateConfig(active.id, payload);
    setSaving(false);
    setSaveMsg(result ? "Saved" : "Failed to save");
    if (result) setTimeout(() => setSaveMsg(null), 2000);
  };

  const handleDelete = async () => {
    if (deleteId == null) return;
    await deleteConfig(deleteId);
    if (activeId === deleteId) setActiveId(null);
    setDeleteId(null);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
      <div className="mb-6">
        <h1 className="text-xl font-semibold text-text-primary">Configs</h1>
        <p className="text-xs text-text-muted">
          Saved configs from backtests. Use "Save as Config" from the Backtests page to add new configs.
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-md border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
          {error}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_2fr]">
        {/* Config list */}
        <div className="rounded-lg border border-border bg-bg-card">
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <h2 className="text-sm font-medium text-text-secondary">Saved Configs</h2>
            <span className="text-xs text-text-muted">{configs.length} total</span>
          </div>
          {loading && (
            <div className="divide-y divide-border/60">
              {Array.from({ length: 6 }).map((_, index) => (
                <div key={index} className="px-4 py-3">
                  <div className="flex items-center justify-between gap-3">
                    <Skeleton className="h-4 w-36 rounded" />
                    <Skeleton className="h-3 w-16 rounded" muted />
                  </div>
                  <div className="mt-2 flex gap-2">
                    <Skeleton className="h-5 w-10 rounded" muted />
                    <Skeleton className="h-5 w-20 rounded" muted />
                    <Skeleton className="h-5 w-12 rounded" muted />
                  </div>
                </div>
              ))}
            </div>
          )}
          {!loading && configs.length === 0 && (
            <div className="px-4 py-4 text-xs text-text-muted">
              No configs saved yet. Use "Save as Config" from a backtest result.
            </div>
          )}
          <div className="divide-y divide-border/60 max-h-[calc(100vh-240px)] overflow-y-auto">
            {!loading && configs.map((item) => (
              <button
                key={item.id}
                onClick={() => handleSelect(item)}
                className={`flex w-full flex-col gap-1.5 px-4 py-3 text-left transition-colors hover:bg-bg-card-hover ${
                  activeId === item.id ? "bg-accent/10 border-l-2 border-l-accent" : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-text-primary truncate">{item.name}</span>
                  <span className="text-[10px] text-text-muted shrink-0">{formatUpdated(item.updated_at)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="font-mono text-xs font-medium text-text-secondary">{item.instrument}</span>
                  <StrategyTag strategy={item.strategy} />
                  {item.sessions.map((s) => (
                    <SessionTag key={s} session={s} />
                  ))}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Config detail */}
        <div className="space-y-4">
          {!active && (
            loading ? (
              <div className="rounded-lg border border-border bg-bg-card p-4">
                <SkeletonText lines={6} />
              </div>
            ) : (
              <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-bg-card text-sm text-text-muted">
                Select a config to view details
              </div>
            )
          )}

          {active && (
            <>
              {/* Editable header */}
              <div className="rounded-lg border border-border bg-bg-card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 space-y-3">
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wider text-text-muted">Name</label>
                      <input
                        className={INPUT_CLASS}
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                      />
                    </div>
                    <div>
                      <label className="text-[11px] font-medium uppercase tracking-wider text-text-muted">Notes</label>
                      <textarea
                        className={`${INPUT_CLASS} min-h-[48px]`}
                        value={editNotes}
                        onChange={(e) => setEditNotes(e.target.value)}
                        placeholder="Add notes..."
                      />
                    </div>
                  </div>
                  <div className="flex flex-col items-end gap-2 shrink-0">
                    <div className="flex items-center gap-1.5">
                      <span className="font-mono text-sm font-medium text-text-secondary">{active.instrument}</span>
                      <StrategyTag strategy={active.strategy} />
                      {active.sessions.map((s) => (
                        <SessionTag key={s} session={s} />
                      ))}
                    </div>
                    <div className="flex items-center gap-2">
                      {saveMsg && (
                        <span className={`text-xs ${saveMsg === "Saved" ? "text-profit" : "text-loss"}`}>
                          {saveMsg}
                        </span>
                      )}
                      <button
                        onClick={handleSave}
                        disabled={saving}
                        className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
                      >
                        {saving ? "Saving..." : "Save Changes"}
                      </button>
                      <button
                        onClick={() => setDeleteId(active.id)}
                        className="rounded-md border border-red-500/30 bg-red-500/10 px-3 py-1.5 text-xs font-medium text-red-400 transition-colors hover:bg-red-500/20"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Config display — reusing existing components */}
              <VariablesTested config={active.config} />
              <ConfigBar config={active.config} />

              {/* Date range picker + Run backtest */}
              <div className="rounded-lg border border-border bg-bg-card p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-[11px] font-medium uppercase tracking-wider text-text-muted">Run Backtest</h3>
                  <button
                    onClick={handleRunBacktest}
                    disabled={btLoading}
                    className="rounded-md bg-accent px-4 py-1.5 text-xs font-medium text-white transition-colors hover:bg-accent/80 disabled:opacity-50"
                  >
                    {btLoading ? (
                      <span className="flex items-center gap-1.5">
                        <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/30 border-t-white" />
                        Running...
                      </span>
                    ) : (
                      "Run Backtest"
                    )}
                  </button>
                </div>
                <DateRangePicker
                  startDate={dateStart}
                  endDate={dateEnd}
                  originalStart={defaultRange.start}
                  originalEnd={defaultRange.end}
                  onChange={handleDateChange}
                  onReset={handleDateReset}
                  loading={btLoading}
                  disabled={false}
                />
                {btError && (
                  <div className="rounded-md border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
                    {btError}
                  </div>
                )}
                {btResult && (
                  <div className="rounded-md border border-profit/30 bg-profit/5 px-3 py-2">
                    <div className="flex items-center gap-4 text-xs">
                      <span className="text-profit font-medium">Backtest complete</span>
                      <span className="text-text-secondary">{btResult.trades} trades</span>
                      <span className="text-text-secondary">Net R: <span className={btResult.netR >= 0 ? "text-profit" : "text-loss"}>{btResult.netR > 0 ? "+" : ""}{btResult.netR.toFixed(1)}</span></span>
                      <span className="text-text-secondary">WR: {(btResult.winRate * 100).toFixed(1)}%</span>
                      <span className="text-text-secondary">Sharpe: {btResult.sharpe.toFixed(2)}</span>
                      <span className="text-text-secondary">Max DD: <span className="text-loss">{btResult.maxDDR.toFixed(2)}R</span></span>
                    </div>
                    <p className="mt-1 text-[10px] text-text-muted">Saved as: {btResult.id}</p>
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      <ConfirmDeleteDialog
        open={deleteId !== null}
        onOpenChange={(open) => { if (!open) setDeleteId(null); }}
        onConfirm={handleDelete}
        title="Delete config?"
        description="This config will be permanently removed."
      />
    </div>
  );
}
