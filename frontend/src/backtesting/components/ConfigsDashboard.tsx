import { useCallback, useState } from "react";
import type { SavedConfig } from "@/backtesting/lib/types";
import { useSavedConfigs } from "@/backtesting/hooks/useSavedConfigs";
import type { SavedConfigInput } from "@/backtesting/hooks/useSavedConfigs";
import { ConfirmDeleteDialog } from "./ConfirmDeleteDialog";
import { ConfigBar } from "./ConfigBar";
import { SessionTag } from "./SessionTag";
import { StrategyTag } from "./StrategyTag";
import { VariablesTested } from "./VariablesTested";

const INPUT_CLASS =
  "w-full rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-accent";

function formatUpdated(ts: string) {
  if (!ts) return "";
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return ts;
  return d.toLocaleString("en-US", { month: "short", day: "numeric", year: "'26" === `'${d.getFullYear() % 100}` ? undefined : "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ConfigsDashboard() {
  const { configs, loading, error, updateConfig, deleteConfig } = useSavedConfigs();
  const [activeId, setActiveId] = useState<number | null>(null);
  const [deleteId, setDeleteId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editNotes, setEditNotes] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);

  const active = configs.find((c) => c.id === activeId) ?? null;

  const handleSelect = useCallback((config: SavedConfig) => {
    setActiveId(config.id);
    setEditName(config.name);
    setEditNotes(config.notes ?? "");
    setSaveMsg(null);
  }, []);

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
            <div className="px-4 py-4 text-xs text-text-muted">Loading...</div>
          )}
          {!loading && configs.length === 0 && (
            <div className="px-4 py-4 text-xs text-text-muted">
              No configs saved yet. Use "Save as Config" from a backtest result.
            </div>
          )}
          <div className="divide-y divide-border/60 max-h-[calc(100vh-240px)] overflow-y-auto">
            {configs.map((item) => (
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
            <div className="flex h-64 items-center justify-center rounded-lg border border-border bg-bg-card text-sm text-text-muted">
              Select a config to view details
            </div>
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
