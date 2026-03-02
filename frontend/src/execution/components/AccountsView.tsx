import { CONFIG_COLORS } from "@/execution/lib/constants";
import type { ExecConfigMeta, WebhookEntry } from "@/execution/lib/types";
import { useEffect, useRef, useState } from "react";

interface AccountsViewProps {
  execConfigs: Record<string, ExecConfigMeta>;
  onPause: (configName: string, idx: number) => Promise<void>;
  onResume: (configName: string, idx: number) => Promise<void>;
  onUpdateMultiplier: (configName: string, idx: number, multiplier: number) => Promise<void>;
  onFlatten: (configName: string, idx: number) => Promise<void>;
  onUpdateWebhooks: (configName: string, webhooks: WebhookEntry[]) => Promise<void>;
}

interface AccountCardProps {
  configName: string;
  webhookIndex: number;
  webhook: WebhookEntry;
  allWebhooks: WebhookEntry[];
  onPause: (configName: string, idx: number) => Promise<void>;
  onResume: (configName: string, idx: number) => Promise<void>;
  onUpdateMultiplier: (configName: string, idx: number, multiplier: number) => Promise<void>;
  onFlatten: (configName: string, idx: number) => Promise<void>;
  onUpdateWebhooks: (configName: string, webhooks: WebhookEntry[]) => Promise<void>;
}

function AccountCard({
  configName,
  webhookIndex,
  webhook,
  allWebhooks,
  onPause,
  onResume,
  onUpdateMultiplier,
  onFlatten,
  onUpdateWebhooks,
}: AccountCardProps) {
  const [multiplierDraft, setMultiplierDraft] = useState(
    String(webhook.multiplier ?? 1.0),
  );
  const [savingPause, setSavingPause] = useState(false);
  const [savingMultiplier, setSavingMultiplier] = useState(false);
  const [flattenState, setFlattenState] = useState<"idle" | "confirm" | "sending">("idle");
  const [flattenTimer, setFlattenTimer] = useState<ReturnType<typeof setTimeout> | null>(null);
  const inputFocused = useRef(false);

  // Edit mode state
  const [editing, setEditing] = useState(false);
  const [editLabel, setEditLabel] = useState(webhook.label);
  const [editUrl, setEditUrl] = useState(webhook.url);
  const [editError, setEditError] = useState<string | null>(null);
  const [savingEdit, setSavingEdit] = useState(false);

  const label = webhook.label || `Account ${webhookIndex + 1}`;
  const isPaused = webhook.paused ?? false;
  const configColorClasses =
    CONFIG_COLORS[configName] ?? "bg-text-muted/20 text-text-muted border-text-muted/30";

  const handlePauseToggle = async () => {
    setSavingPause(true);
    try {
      if (isPaused) {
        await onResume(configName, webhookIndex);
      } else {
        await onPause(configName, webhookIndex);
      }
    } finally {
      setSavingPause(false);
    }
  };

  const handleMultiplierCommit = async () => {
    const val = parseFloat(multiplierDraft);
    if (isNaN(val) || val <= 0) {
      setMultiplierDraft(String(webhook.multiplier ?? 1.0));
      return;
    }
    if (val === (webhook.multiplier ?? 1.0)) return;
    setSavingMultiplier(true);
    try {
      await onUpdateMultiplier(configName, webhookIndex, val);
    } finally {
      setSavingMultiplier(false);
    }
  };

  const handleFlattenClick = () => {
    if (flattenState === "idle") {
      setFlattenState("confirm");
      const t = setTimeout(() => setFlattenState("idle"), 3000);
      setFlattenTimer(t);
    } else if (flattenState === "confirm") {
      if (flattenTimer) {
        clearTimeout(flattenTimer);
        setFlattenTimer(null);
      }
      setFlattenState("sending");
      onFlatten(configName, webhookIndex).finally(() => setFlattenState("idle"));
    }
  };

  const handleEditOpen = () => {
    setEditLabel(webhook.label);
    setEditUrl(webhook.url);
    setEditError(null);
    setEditing(true);
  };

  const handleEditCancel = () => {
    setEditing(false);
    setEditError(null);
  };

  const handleEditSave = async () => {
    const trimUrl = editUrl.trim();
    if (!trimUrl) {
      setEditError("Webhook URL cannot be empty.");
      return;
    }
    setSavingEdit(true);
    setEditError(null);
    try {
      const updated = allWebhooks.map((wh, i) =>
        i === webhookIndex
          ? { ...wh, label: editLabel.trim(), url: trimUrl }
          : wh,
      );
      await onUpdateWebhooks(configName, updated);
      setEditing(false);
    } catch (e) {
      setEditError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSavingEdit(false);
    }
  };

  // Keep multiplier draft in sync when webhook prop updates (e.g. WS broadcast)
  useEffect(() => {
    if (!savingMultiplier && !inputFocused.current) {
      setMultiplierDraft(String(webhook.multiplier ?? 1.0));
    }
  }, [webhook.multiplier, savingMultiplier]);

  return (
    <div className="rounded-lg border border-border bg-bg-card flex flex-col">
      {editing ? (
        /* ── Edit mode ── */
        <div className="px-4 py-4 flex flex-col gap-3 flex-1">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-text-secondary">Edit account</span>
            <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${configColorClasses}`}>
              {configName}
            </span>
          </div>

          <div className="space-y-2">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-muted">Account name</label>
              <input
                type="text"
                value={editLabel}
                onChange={(e) => setEditLabel(e.target.value)}
                placeholder="e.g. Lucid Flex Eval 1"
                className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs text-text-primary focus:border-accent focus:outline-none"
              />
            </div>
            <div className="flex flex-col gap-1">
              <label className="text-xs text-text-muted">Webhook URL</label>
              <input
                type="text"
                value={editUrl}
                onChange={(e) => setEditUrl(e.target.value)}
                placeholder="https://webhooks.traderspost.io/..."
                className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs font-mono text-text-primary focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {editError && (
            <p className="text-xs text-loss">{editError}</p>
          )}

          <div className="flex gap-2 mt-auto pt-1">
            <button
              onClick={handleEditSave}
              disabled={savingEdit}
              className="flex-1 rounded bg-accent/20 text-accent border border-accent/30 px-3 py-1.5 text-xs font-medium hover:bg-accent/30 transition-colors disabled:opacity-50"
            >
              {savingEdit ? "Saving…" : "Save"}
            </button>
            <button
              onClick={handleEditCancel}
              disabled={savingEdit}
              className="flex-1 rounded border border-border text-text-muted px-3 py-1.5 text-xs font-medium hover:text-text-secondary hover:border-text-muted/40 transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        /* ── Read mode ── */
        <>
          {/* Header */}
          <div className="px-4 pt-4 pb-3 space-y-2">
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-1.5 min-w-0">
                <span className="text-sm font-semibold text-text-primary leading-tight truncate">{label}</span>
                <button
                  onClick={handleEditOpen}
                  title="Edit account"
                  className="text-text-muted hover:text-accent transition-colors shrink-0"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                {/* Config badge */}
                <span className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${configColorClasses}`}>
                  {configName}
                </span>
                {/* Status badge */}
                <span
                  className={`inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium ${
                    isPaused
                      ? "bg-warning/20 text-warning border-warning/30"
                      : "bg-profit/20 text-profit border-profit/30"
                  }`}
                >
                  {isPaused ? "Paused" : "Active"}
                </span>
              </div>
            </div>
            {/* URL hint */}
            <div className="flex items-center gap-2">
              <p className="text-xs text-text-muted font-mono truncate flex-1 min-w-0">
                …{webhook.url.slice(-36)}
              </p>
            </div>
          </div>

          {/* Body */}
          <div className="px-4 pb-3 flex-1">
            <div className="flex items-center gap-3">
              <label className="text-xs text-text-muted w-20 shrink-0">Multiplier</label>
              <input
                type="number"
                step="0.1"
                min="0.1"
                value={multiplierDraft}
                onChange={(e) => setMultiplierDraft(e.target.value)}
                onFocus={() => { inputFocused.current = true; }}
                onBlur={() => { inputFocused.current = false; handleMultiplierCommit(); }}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    (e.target as HTMLInputElement).blur();
                  }
                }}
                disabled={savingMultiplier}
                className="w-24 rounded border border-border bg-bg-secondary px-2 py-1 text-xs font-mono text-text-primary focus:border-accent focus:outline-none disabled:opacity-50"
              />
              {savingMultiplier && (
                <span className="text-xs text-text-muted">Saving…</span>
              )}
            </div>
          </div>

          {/* Footer buttons */}
          <div className="px-4 pb-4 flex gap-2">
            <button
              onClick={handlePauseToggle}
              disabled={savingPause}
              className={`flex-1 rounded px-3 py-1.5 text-xs font-medium transition-colors border disabled:opacity-50 ${
                isPaused
                  ? "bg-profit/20 text-profit hover:bg-profit/30 border-profit/30"
                  : "bg-warning/20 text-warning hover:bg-warning/30 border-warning/30"
              }`}
            >
              {savingPause ? "…" : isPaused ? "Resume" : "Pause"}
            </button>

            <button
              onClick={handleFlattenClick}
              disabled={flattenState === "sending"}
              className={`flex-1 rounded px-3 py-1.5 text-xs font-medium transition-colors border disabled:opacity-50 ${
                flattenState === "confirm"
                  ? "bg-loss/30 text-loss border-loss/50 animate-pulse"
                  : "bg-loss/20 text-loss hover:bg-loss/30 border-loss/30"
              }`}
            >
              {flattenState === "sending"
                ? "Sending…"
                : flattenState === "confirm"
                  ? "Confirm Flatten"
                  : "Flatten"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

interface AddAccountFormProps {
  configNames: string[];
  onAdd: (configName: string, label: string, url: string) => Promise<void>;
  onCancel: () => void;
}

function AddAccountForm({ configNames, onAdd, onCancel }: AddAccountFormProps) {
  const [label, setLabel] = useState("");
  const [url, setUrl] = useState("");
  const [selectedConfig, setSelectedConfig] = useState(configNames[0] ?? "");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const handleSubmit = async () => {
    if (!url.trim()) {
      setError("Webhook URL is required.");
      return;
    }
    if (!selectedConfig) {
      setError("Select an execution config.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onAdd(selectedConfig, label.trim(), url.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add account");
      setSaving(false);
    }
  };

  return (
    <div className="rounded-lg border border-accent/30 bg-bg-card flex flex-col">
      <div className="px-4 py-4 flex flex-col gap-3">
        <span className="text-xs font-medium text-text-secondary">Add account</span>

        <div className="space-y-2">
          <div className="flex flex-col gap-1">
            <label className="text-xs text-text-muted">Execution config</label>
            <select
              value={selectedConfig}
              onChange={(e) => setSelectedConfig(e.target.value)}
              className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs text-text-primary focus:border-accent focus:outline-none"
            >
              {configNames.map((name) => (
                <option key={name} value={name}>{name}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-text-muted">Account name</label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="e.g. Lucid Flex Eval 1"
              className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs text-text-primary focus:border-accent focus:outline-none"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-xs text-text-muted">Webhook URL</label>
            <input
              type="text"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://webhooks.traderspost.io/..."
              className="rounded border border-border bg-bg-secondary px-2 py-1.5 text-xs font-mono text-text-primary focus:border-accent focus:outline-none"
            />
          </div>
        </div>

        {error && <p className="text-xs text-loss">{error}</p>}

        <div className="flex gap-2 mt-auto pt-1">
          <button
            onClick={handleSubmit}
            disabled={saving}
            className="flex-1 rounded bg-accent/20 text-accent border border-accent/30 px-3 py-1.5 text-xs font-medium hover:bg-accent/30 transition-colors disabled:opacity-50"
          >
            {saving ? "Adding…" : "Add account"}
          </button>
          <button
            onClick={onCancel}
            disabled={saving}
            className="flex-1 rounded border border-border text-text-muted px-3 py-1.5 text-xs font-medium hover:text-text-secondary hover:border-text-muted/40 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
}

export function AccountsView({
  execConfigs,
  onPause,
  onResume,
  onUpdateMultiplier,
  onFlatten,
  onUpdateWebhooks,
}: AccountsViewProps) {
  const [showAddForm, setShowAddForm] = useState(false);

  const configNames = Object.keys(execConfigs);
  const accounts = Object.entries(execConfigs).flatMap(([configName, meta]) =>
    meta.webhooks.map((wh, idx) => ({ configName, webhookIndex: idx, webhook: wh, allWebhooks: meta.webhooks })),
  );

  const handleAddAccount = async (configName: string, label: string, url: string) => {
    const existing = execConfigs[configName]?.webhooks ?? [];
    const updated: WebhookEntry[] = [...existing, { url, label }];
    await onUpdateWebhooks(configName, updated);
    setShowAddForm(false);
  };

  const configCount = configNames.length;

  return (
    <div className="space-y-4">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-xs text-text-muted">
          {accounts.length} account{accounts.length !== 1 ? "s" : ""} across{" "}
          {configCount} execution config{configCount !== 1 ? "s" : ""}
        </p>
        {!showAddForm && (
          <button
            onClick={() => setShowAddForm(true)}
            className="rounded border border-accent/30 bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent hover:bg-accent/20 transition-colors"
          >
            + Add account
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {/* Add account form card */}
        {showAddForm && (
          <AddAccountForm
            configNames={configNames}
            onAdd={handleAddAccount}
            onCancel={() => setShowAddForm(false)}
          />
        )}

        {accounts.length === 0 && !showAddForm ? (
          <div className="col-span-full flex flex-col items-center justify-center py-16 gap-2 text-text-muted">
            <span className="text-sm">No accounts configured</span>
            <span className="text-xs">Click &quot;Add account&quot; to connect a webhook.</span>
          </div>
        ) : (
          accounts.map(({ configName, webhookIndex, webhook, allWebhooks }) => (
            <AccountCard
              key={`${configName}-${webhookIndex}`}
              configName={configName}
              webhookIndex={webhookIndex}
              webhook={webhook}
              allWebhooks={allWebhooks}
              onPause={onPause}
              onResume={onResume}
              onUpdateMultiplier={onUpdateMultiplier}
              onFlatten={onFlatten}
              onUpdateWebhooks={onUpdateWebhooks}
            />
          ))
        )}
      </div>
    </div>
  );
}
