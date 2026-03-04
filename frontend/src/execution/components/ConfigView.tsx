import { CONFIG_COLORS } from "@/execution/lib/constants";
import type { ConfigResponse, ExecConfigMeta, SessionConfig, WebhookEntry } from "@/execution/lib/types";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/shared/ui/card";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/shared/ui/dialog";
import { useCallback, useState } from "react";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface ConfigViewProps {
  config: ConfigResponse | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
  onUpdateSession: (name: string, overrides: Partial<SessionConfig>) => Promise<void>;
  onResetSession: (name: string) => Promise<void>;
  onUpdateWebhooks: (configName: string, webhooks: WebhookEntry[]) => Promise<void>;
  execConfigs: Record<string, ExecConfigMeta>;
}

interface GlobalRiskDefaults {
  risk_usd: number;
  min_qty: number;
  max_single_risk_usd: number;
}

type DraftValues = Record<string, string | number | boolean | number[] | null>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const DOW_OPTIONS = [
  { value: "", label: "None" },
  { value: "0", label: "Mon" },
  { value: "1", label: "Tue" },
  { value: "2", label: "Wed" },
  { value: "3", label: "Thu" },
  { value: "4", label: "Fri" },
  { value: "5", label: "Sat" },
  { value: "6", label: "Sun" },
];

/** Format excluded_dow (single int, array, or null) for display. */
function formatExcludedDow(dow: number | number[] | null): string | null {
  if (dow == null) return null;
  if (Array.isArray(dow)) {
    return dow.map((d) => DOW_NAMES[d] ?? `DOW ${d}`).join(", ");
  }
  return DOW_NAMES[dow] ?? `DOW ${dow}`;
}

// ---------------------------------------------------------------------------
// Small reusable components
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-200">
      {children}
    </span>
  );
}

function ConfigItem({
  label,
  value,
  overridden,
}: {
  label: string;
  value: string;
  overridden?: boolean;
}) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-text-muted text-xs">{label}</span>
      <span
        className={`font-mono text-xs ${overridden ? "text-amber-400" : "text-text-secondary"}`}
      >
        {value}
        {overridden && " *"}
      </span>
    </div>
  );
}

function EditableField({
  label,
  value,
  onChange,
  type = "text",
  overridden,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: "text" | "number";
  overridden?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-text-muted text-xs shrink-0">{label}</span>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`h-6 w-24 rounded border bg-bg-secondary px-2 text-right font-mono text-xs text-text-secondary outline-none focus:border-accent focus:ring-1 focus:ring-accent/50 ${
          overridden ? "border-amber-400/40" : "border-border"
        }`}
      />
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-text-muted text-xs shrink-0">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-6 w-24 rounded border border-border bg-bg-secondary px-1 text-right font-mono text-xs text-text-secondary outline-none focus:border-accent"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

// ---------------------------------------------------------------------------
// WebhookManager
// ---------------------------------------------------------------------------

function WebhookManager({
  configName,
  webhooks,
  onSave,
}: {
  configName: string;
  webhooks: WebhookEntry[];
  onSave: (configName: string, webhooks: WebhookEntry[]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<WebhookEntry[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEditing = () => {
    setDraft(webhooks.map((w) => ({ ...w })));
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setDraft([]);
    setError(null);
  };

  const setField = (idx: number, key: keyof WebhookEntry, value: string) => {
    setDraft((d) => d.map((w, i) => (i === idx ? { ...w, [key]: value } : w)));
  };

  const addRow = () => {
    setDraft((d) => [...d, { url: "", label: "" }]);
  };

  const removeRow = (idx: number) => {
    setDraft((d) => d.filter((_, i) => i !== idx));
  };

  const handleSave = async () => {
    const cleaned = draft.filter((w) => w.url.trim());
    if (draft.some((w) => !w.url.trim())) {
      setError("All webhook entries must have a URL");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(configName, cleaned);
      setEditing(false);
      setDraft([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  // ── read mode ──
  if (!editing) {
    return (
      <div className="space-y-1">
        <div className="flex items-center justify-between">
          <span className="text-text-muted text-xs">Webhooks</span>
          <button
            onClick={startEditing}
            className="text-[10px] text-text-muted hover:text-accent transition-colors"
          >
            Edit
          </button>
        </div>
        {webhooks.length === 0 ? (
          <p className="text-[11px] text-text-muted italic">not set</p>
        ) : (
          <div className="space-y-1">
            {webhooks.map((w, i) => (
              <div key={i} className="flex items-center justify-between gap-2">
                <span className="text-[11px] font-medium text-text-secondary truncate max-w-[120px]">
                  {w.label || `Webhook ${i + 1}`}
                </span>
                <span className="font-mono text-[10px] text-profit bg-profit/10 px-1.5 py-0.5 rounded">
                  configured
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ── edit mode ──
  return (
    <div className="space-y-2 rounded-md border border-accent/30 bg-accent/5 p-3">
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold text-accent uppercase tracking-wide">
          Edit Webhooks
        </span>
        <div className="flex gap-1.5">
          <button
            onClick={cancel}
            disabled={saving}
            className="rounded border border-border px-2 py-0.5 text-[10px] text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="rounded bg-accent px-2 py-0.5 text-[10px] font-medium text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      {error && (
        <p className="text-[10px] text-loss">{error}</p>
      )}

      {draft.map((w, i) => (
        <div key={i} className="space-y-1 rounded border border-border bg-bg-secondary p-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-text-muted">Account {i + 1}</span>
            <button
              onClick={() => removeRow(i)}
              className="text-[10px] text-loss/70 hover:text-loss transition-colors"
            >
              Remove
            </button>
          </div>
          <input
            type="text"
            placeholder="Label (e.g. Account 1)"
            value={w.label}
            onChange={(e) => setField(i, "label", e.target.value)}
            className="w-full rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-[11px] text-text-secondary outline-none focus:border-accent focus:ring-1 focus:ring-accent/50"
          />
          <input
            type="text"
            placeholder="Webhook URL"
            value={w.url}
            onChange={(e) => setField(i, "url", e.target.value)}
            className={`w-full rounded border bg-bg-secondary px-2 py-1 font-mono text-[10px] text-text-secondary outline-none focus:border-accent focus:ring-1 focus:ring-accent/50 ${
              w.url.trim() ? "border-border" : "border-loss/40"
            }`}
          />
        </div>
      ))}

      <button
        onClick={addRow}
        className="w-full rounded border border-dashed border-border py-1 text-[10px] text-text-muted hover:border-accent/50 hover:text-accent transition-colors"
      >
        + Add Webhook
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// SessionConfigCard
// ---------------------------------------------------------------------------

function SessionConfigCard({
  name,
  cfg,
  globalRisk,
  overrides,
  saving,
  onSave,
  onReset,
}: {
  name: string;
  cfg: SessionConfig;
  globalRisk: GlobalRiskDefaults;
  overrides: Partial<SessionConfig>;
  defaults?: Partial<SessionConfig>;
  saving: boolean;
  onSave: (name: string, overrides: Partial<SessionConfig>) => Promise<void>;
  onReset: (name: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftValues>({});
  const [cardError, setCardError] = useState<string | null>(null);

  const hasOverrides = Object.keys(overrides).length > 0;
  const isLsi = cfg.type !== "continuation";

  const stopIsOrb = cfg.stop_basis === "orb";
  const gapIsOrb = cfg.gap_filter_basis === "orb";

  // Check if a field is overridden (exists in the overrides dict from backend)
  const isOverridden = (field: string) =>
    Object.prototype.hasOwnProperty.call(overrides, field);

  // Start editing — populate draft from current cfg values
  const startEditing = useCallback(() => {
    if (isLsi) {
      setDraft({
        entry_start: cfg.entry_start,
        entry_end: cfg.entry_end,
        flat_start: cfg.flat_start,
        flat_end: cfg.flat_end,
        excluded_dow: cfg.excluded_dow,
        rr: cfg.rr,
        tp1_ratio: cfg.tp1_ratio,
        min_gap_atr_pct: cfg.min_gap_atr_pct,
        min_stop_points: cfg.min_stop_points,
        max_bars_after_sweep: cfg.max_bars_after_sweep,
        fvg_window_left: cfg.fvg_window_left,
        qty_multiplier: cfg.qty_multiplier,
        risk_usd: cfg.risk_usd,
        min_qty: cfg.min_qty,
        max_single_risk_usd: cfg.max_single_risk_usd,
        be_offset_ticks: cfg.be_offset_ticks,
      });
    } else {
      setDraft({
        orb_start: cfg.orb_start,
        orb_end: cfg.orb_end,
        entry_start: cfg.entry_start,
        entry_end: cfg.entry_end,
        flat_start: cfg.flat_start,
        flat_end: cfg.flat_end,
        excluded_dow: cfg.excluded_dow,
        rr: cfg.rr,
        tp1_ratio: cfg.tp1_ratio,
        stop_atr_pct: cfg.stop_atr_pct,
        stop_orb_pct: cfg.stop_orb_pct,
        min_gap_atr_pct: cfg.min_gap_atr_pct,
        min_gap_orb_pct: cfg.min_gap_orb_pct,
        max_gap_atr_pct: cfg.max_gap_atr_pct,
        risk_usd: cfg.risk_usd,
        min_qty: cfg.min_qty,
        max_single_risk_usd: cfg.max_single_risk_usd,
        be_offset_ticks: cfg.be_offset_ticks,
      });
    }
    setCardError(null);
    setEditing(true);
  }, [cfg, isLsi]);

  const cancelEditing = () => {
    setEditing(false);
    setDraft({});
    setCardError(null);
  };

  const setField = (key: string, raw: string) => {
    setDraft((d) => ({ ...d, [key]: raw }));
  };

  // Build field lists based on engine type
  const numericFields = isLsi
    ? [
        "rr", "tp1_ratio", "min_gap_atr_pct", "min_stop_points",
        "max_bars_after_sweep", "fvg_window_left", "qty_multiplier",
        "risk_usd", "min_qty", "max_single_risk_usd", "be_offset_ticks",
      ]
    : [
        "rr", "tp1_ratio", "stop_atr_pct", "stop_orb_pct",
        "min_gap_atr_pct", "min_gap_orb_pct", "max_gap_atr_pct",
        "risk_usd", "min_qty", "max_single_risk_usd", "be_offset_ticks",
      ];
  const timeFields = isLsi
    ? ["entry_start", "entry_end", "flat_start", "flat_end"]
    : ["orb_start", "orb_end", "entry_start", "entry_end", "flat_start", "flat_end"];

  const handleSave = async () => {
    setCardError(null);
    try {
      // Send ALL current draft values (not just diffs) so the backend can
      // compute which are actually overrides vs defaults
      const allFields: Record<string, unknown> = {};

      for (const f of timeFields) {
        allFields[f] = String(draft[f] ?? "");
      }
      for (const f of numericFields) {
        allFields[f] = Number(draft[f]);
      }
      const dowDraft = draft.excluded_dow;
      allFields.excluded_dow =
        dowDraft === null || dowDraft === "" ? null : Number(dowDraft);

      await onSave(name, allFields as Partial<SessionConfig>);
      setEditing(false);
      setDraft({});
    } catch (e) {
      setCardError(e instanceof Error ? e.message : "Failed to save");
    }
  };

  const handleReset = async () => {
    setCardError(null);
    try {
      await onReset(name);
    } catch (e) {
      setCardError(e instanceof Error ? e.message : "Failed to reset");
    }
  };

  // Risk override checks (for read mode)
  const maxSingleRisk = cfg.max_single_risk_usd ?? globalRisk.max_single_risk_usd;
  const riskOverridden = cfg.risk_usd !== globalRisk.risk_usd;
  const minQtyOverridden = cfg.min_qty !== globalRisk.min_qty;
  const maxRiskOverridden = maxSingleRisk !== globalRisk.max_single_risk_usd;
  const hasAnyRiskOverride = riskOverridden || minQtyOverridden || maxRiskOverridden;

  // ── Edit mode ───────────────────────────────────────────────────
  if (editing) {
    return (
      <Card className="border-border bg-bg-card">
        <CardHeader className="pb-2">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm font-semibold bg-primary/20 px-2 py-1 w-fit rounded-md">
              {name}
            </CardTitle>
            <div className="flex gap-1.5">
              <button
                onClick={cancelEditing}
                disabled={saving}
                className="rounded border border-border px-2.5 py-1 text-[11px] text-text-muted hover:text-text-secondary hover:bg-bg-secondary transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleSave}
                disabled={saving}
                className="rounded bg-accent px-2.5 py-1 text-[11px] font-medium text-white hover:bg-accent/90 transition-colors disabled:opacity-50"
              >
                {saving ? "Saving..." : "Save"}
              </button>
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3">
          {cardError && (
            <div className="rounded-md bg-loss/10 border border-loss/20 px-3 py-2 text-xs text-loss">
              {cardError}
            </div>
          )}

          {/* Session Times */}
          <div className="space-y-0.5">
            <SectionLabel>Session Times</SectionLabel>
            {!isLsi && (
              <>
                <EditableField
                  label="ORB Start"
                  value={String(draft.orb_start ?? "")}
                  onChange={(v) => setField("orb_start", v)}
                  overridden={isOverridden("orb_start")}
                />
                <EditableField
                  label="ORB End"
                  value={String(draft.orb_end ?? "")}
                  onChange={(v) => setField("orb_end", v)}
                  overridden={isOverridden("orb_end")}
                />
              </>
            )}
            <EditableField
              label="Entry Start"
              value={String(draft.entry_start ?? "")}
              onChange={(v) => setField("entry_start", v)}
              overridden={isOverridden("entry_start")}
            />
            <EditableField
              label="Entry End"
              value={String(draft.entry_end ?? "")}
              onChange={(v) => setField("entry_end", v)}
              overridden={isOverridden("entry_end")}
            />
            <EditableField
              label="Flat Start"
              value={String(draft.flat_start ?? "")}
              onChange={(v) => setField("flat_start", v)}
              overridden={isOverridden("flat_start")}
            />
            <EditableField
              label="Flat End"
              value={String(draft.flat_end ?? "")}
              onChange={(v) => setField("flat_end", v)}
              overridden={isOverridden("flat_end")}
            />
            {!isLsi && (
              <SelectField
                label="Skip Day"
                value={draft.excluded_dow == null ? "" : String(draft.excluded_dow)}
                options={DOW_OPTIONS}
                onChange={(v) =>
                  setDraft((d) => ({ ...d, excluded_dow: v === "" ? null : v }))
                }
              />
            )}
          </div>

          {/* Strategy */}
          <div className="space-y-0.5 border-t border-border pt-2">
            <SectionLabel>Strategy</SectionLabel>
            <EditableField
              label="R:R"
              value={String(draft.rr ?? "")}
              onChange={(v) => setField("rr", v)}
              type="number"
              overridden={isOverridden("rr")}
            />
            <EditableField
              label="TP1 Ratio"
              value={String(draft.tp1_ratio ?? "")}
              onChange={(v) => setField("tp1_ratio", v)}
              type="number"
              overridden={isOverridden("tp1_ratio")}
            />
            {isLsi ? (
              <>
                <EditableField
                  label="Gap ATR %"
                  value={String(draft.min_gap_atr_pct ?? "")}
                  onChange={(v) => setField("min_gap_atr_pct", v)}
                  type="number"
                  overridden={isOverridden("min_gap_atr_pct")}
                />
                <EditableField
                  label="Min Stop Pts"
                  value={String(draft.min_stop_points ?? "")}
                  onChange={(v) => setField("min_stop_points", v)}
                  type="number"
                  overridden={isOverridden("min_stop_points")}
                />
                <EditableField
                  label="Max Sweep Bars"
                  value={String(draft.max_bars_after_sweep ?? "")}
                  onChange={(v) => setField("max_bars_after_sweep", v)}
                  type="number"
                  overridden={isOverridden("max_bars_after_sweep")}
                />
                <EditableField
                  label="Max Inversion Bars"
                  value={String(draft.fvg_window_left ?? "")}
                  onChange={(v) => setField("fvg_window_left", v)}
                  type="number"
                  overridden={isOverridden("fvg_window_left")}
                />
              </>
            ) : (
              <>
                {stopIsOrb ? (
                  <EditableField
                    label="Stop ORB %"
                    value={String(draft.stop_orb_pct ?? "")}
                    onChange={(v) => setField("stop_orb_pct", v)}
                    type="number"
                    overridden={isOverridden("stop_orb_pct")}
                  />
                ) : (
                  <EditableField
                    label="Stop ATR %"
                    value={String(draft.stop_atr_pct ?? "")}
                    onChange={(v) => setField("stop_atr_pct", v)}
                    type="number"
                    overridden={isOverridden("stop_atr_pct")}
                  />
                )}
                {gapIsOrb ? (
                  <EditableField
                    label="Gap ORB %"
                    value={String(draft.min_gap_orb_pct ?? "")}
                    onChange={(v) => setField("min_gap_orb_pct", v)}
                    type="number"
                    overridden={isOverridden("min_gap_orb_pct")}
                  />
                ) : (
                  <>
                    <EditableField
                      label="Gap ATR % (min)"
                      value={String(draft.min_gap_atr_pct ?? "")}
                      onChange={(v) => setField("min_gap_atr_pct", v)}
                      type="number"
                      overridden={isOverridden("min_gap_atr_pct")}
                    />
                    <EditableField
                      label="Gap ATR % (max)"
                      value={String(draft.max_gap_atr_pct ?? "")}
                      onChange={(v) => setField("max_gap_atr_pct", v)}
                      type="number"
                      overridden={isOverridden("max_gap_atr_pct")}
                    />
                  </>
                )}
              </>
            )}
          </div>

          {/* Risk & Sizing */}
          <div className="space-y-0.5 border-t border-border pt-2">
            <SectionLabel>Risk & Sizing</SectionLabel>
            <EditableField
              label="Risk USD"
              value={String(draft.risk_usd ?? "")}
              onChange={(v) => setField("risk_usd", v)}
              type="number"
              overridden={isOverridden("risk_usd")}
            />
            <EditableField
              label="Min Qty"
              value={String(draft.min_qty ?? "")}
              onChange={(v) => setField("min_qty", v)}
              type="number"
              overridden={isOverridden("min_qty")}
            />
            <EditableField
              label="Max Single Risk"
              value={String(draft.max_single_risk_usd ?? "")}
              onChange={(v) => setField("max_single_risk_usd", v)}
              type="number"
              overridden={isOverridden("max_single_risk_usd")}
            />
            {isLsi && (
              <EditableField
                label="Qty Multiplier"
                value={String(draft.qty_multiplier ?? "")}
                onChange={(v) => setField("qty_multiplier", v)}
                type="number"
                overridden={isOverridden("qty_multiplier")}
              />
            )}
            <EditableField
              label="BE Offset (ticks)"
              value={String(draft.be_offset_ticks ?? "")}
              onChange={(v) => setField("be_offset_ticks", v)}
              type="number"
              overridden={isOverridden("be_offset_ticks")}
            />
            <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
            <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
          </div>
        </CardContent>

        {hasOverrides && (
          <CardFooter className="pt-0 pb-3 px-6">
            <Dialog>
              <DialogTrigger asChild>
                <button className="text-[11px] text-text-muted hover:text-amber-400 transition-colors">
                  Reset to Defaults
                </button>
              </DialogTrigger>
              <DialogContent className="max-w-sm">
                <DialogHeader>
                  <DialogTitle>Reset {name} to Defaults?</DialogTitle>
                  <DialogDescription>
                    This will remove all overrides for this strategy and restore the
                    original configuration.
                  </DialogDescription>
                </DialogHeader>
                <DialogFooter>
                  <DialogClose asChild>
                    <button className="rounded border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary">
                      Cancel
                    </button>
                  </DialogClose>
                  <DialogClose asChild>
                    <button
                      onClick={handleReset}
                      className="rounded bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600"
                    >
                      Reset
                    </button>
                  </DialogClose>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </CardFooter>
        )}
      </Card>
    );
  }

  // ── Read mode ───────────────────────────────────────────────────
  const excludedDowDisplay = formatExcludedDow(cfg.excluded_dow);

  return (
    <Card className="border-border bg-bg-card">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-semibold bg-primary/20 px-2 py-1 w-fit rounded-md">
              {name}
            </CardTitle>
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                isLsi
                  ? "text-violet-400 bg-violet-400/10"
                  : "text-emerald-400 bg-emerald-400/10"
              }`}
            >
              {isLsi ? "LSI" : "ORB"}
            </span>
            {hasOverrides && (
              <span className="text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded">
                overridden
              </span>
            )}
          </div>
          <button
            onClick={startEditing}
            className="rounded border border-border px-2.5 py-1 text-[11px] text-text-muted hover:text-text-secondary hover:bg-bg-secondary transition-colors"
          >
            Edit
          </button>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Session Times */}
        <div className="space-y-1">
          <SectionLabel>Session Times</SectionLabel>
          {!isLsi && (
            <ConfigItem
              label="ORB"
              value={`${cfg.orb_start} - ${cfg.orb_end}`}
              overridden={isOverridden("orb_start") || isOverridden("orb_end")}
            />
          )}
          <ConfigItem
            label="Entry"
            value={`${cfg.entry_start} - ${cfg.entry_end}`}
            overridden={isOverridden("entry_start") || isOverridden("entry_end")}
          />
          <ConfigItem
            label="Flat"
            value={`${cfg.flat_start} - ${cfg.flat_end}`}
            overridden={isOverridden("flat_start") || isOverridden("flat_end")}
          />
          {excludedDowDisplay && (
            <ConfigItem
              label="Skip Day"
              value={excludedDowDisplay}
              overridden={isOverridden("excluded_dow")}
            />
          )}
        </div>

        {/* Strategy */}
        <div className="space-y-1 border-t border-border pt-2">
          <SectionLabel>Strategy</SectionLabel>
          <ConfigItem label="R:R" value={cfg.rr.toString()} overridden={isOverridden("rr")} />
          <ConfigItem
            label="TP1 Ratio"
            value={cfg.tp1_ratio.toString()}
            overridden={isOverridden("tp1_ratio")}
          />
          {isLsi ? (
            <>
              <ConfigItem
                label="Gap ATR %"
                value={`${cfg.min_gap_atr_pct}%`}
                overridden={isOverridden("min_gap_atr_pct")}
              />
              <ConfigItem
                label="Min Stop Pts"
                value={cfg.min_stop_points != null ? `${cfg.min_stop_points}` : "—"}
                overridden={isOverridden("min_stop_points")}
              />
              <ConfigItem
                label="Max Sweep Bars"
                value={cfg.max_bars_after_sweep?.toString() ?? "—"}
                overridden={isOverridden("max_bars_after_sweep")}
              />
              <ConfigItem
                label="Max Inversion Bars"
                value={cfg.fvg_window_left?.toString() ?? "—"}
                overridden={isOverridden("fvg_window_left")}
              />
            </>
          ) : (
            <>
              {stopIsOrb ? (
                <ConfigItem
                  label="Stop ORB %"
                  value={`${cfg.stop_orb_pct}%`}
                  overridden={isOverridden("stop_orb_pct")}
                />
              ) : (
                <ConfigItem
                  label="Stop ATR %"
                  value={`${cfg.stop_atr_pct}%`}
                  overridden={isOverridden("stop_atr_pct")}
                />
              )}
              {gapIsOrb ? (
                <ConfigItem
                  label="Gap ORB %"
                  value={`${cfg.min_gap_orb_pct}%`}
                  overridden={isOverridden("min_gap_orb_pct")}
                />
              ) : (
                <ConfigItem
                  label="Gap ATR %"
                  value={
                    cfg.max_gap_atr_pct
                      ? `${cfg.min_gap_atr_pct} - ${cfg.max_gap_atr_pct}%`
                      : `${cfg.min_gap_atr_pct}%`
                  }
                  overridden={isOverridden("min_gap_atr_pct") || isOverridden("max_gap_atr_pct")}
                />
              )}
            </>
          )}
        </div>

        {/* Risk & Sizing */}
        <div
          className={`space-y-1 rounded-md px-2 py-2 -mx-2 ${
            hasAnyRiskOverride
              ? "bg-amber-400/5 border border-amber-400/20"
              : "border-t border-border/30 pt-2"
          }`}
        >
          <SectionLabel>
            {hasAnyRiskOverride ? "Risk & Sizing (override)" : "Risk & Sizing"}
          </SectionLabel>
          <ConfigItem
            label="Risk USD"
            value={`$${cfg.risk_usd}`}
            overridden={riskOverridden || isOverridden("risk_usd")}
          />
          <ConfigItem
            label="Min Qty"
            value={cfg.min_qty.toString()}
            overridden={minQtyOverridden || isOverridden("min_qty")}
          />
          <ConfigItem
            label="Max Single Risk"
            value={`$${maxSingleRisk}`}
            overridden={maxRiskOverridden || isOverridden("max_single_risk_usd")}
          />
          {isLsi && cfg.qty_multiplier != null && (
            <ConfigItem
              label="Qty Multiplier"
              value={`${cfg.qty_multiplier}x`}
              overridden={isOverridden("qty_multiplier")}
            />
          )}
          <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
          <ConfigItem
            label="BE Offset"
            value={`${cfg.be_offset_ticks} ticks`}
            overridden={isOverridden("be_offset_ticks")}
          />
          <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
          {(hasAnyRiskOverride || hasOverrides) && (
            <p className="text-[10px] text-amber-400/70 pt-0.5">
              * overridden from default
            </p>
          )}
        </div>
      </CardContent>

      {hasOverrides && (
        <CardFooter className="pt-0 pb-3 px-6">
          <Dialog>
            <DialogTrigger asChild>
              <button className="text-[11px] text-text-muted hover:text-amber-400 transition-colors">
                Reset to Defaults
              </button>
            </DialogTrigger>
            <DialogContent className="max-w-sm">
              <DialogHeader>
                <DialogTitle>Reset {name} to Defaults?</DialogTitle>
                <DialogDescription>
                  This will remove all overrides for this strategy and restore the
                  original configuration.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose asChild>
                  <button className="rounded border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text-secondary">
                    Cancel
                  </button>
                </DialogClose>
                <DialogClose asChild>
                  <button
                    onClick={handleReset}
                    className="rounded bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600"
                  >
                    Reset
                  </button>
                </DialogClose>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </CardFooter>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// SessionConfigsSection (tabbed view by speed prefix)
// ---------------------------------------------------------------------------

function SessionConfigsSection({
  sessions,
  overrides,
  defaults,
  globalRisk,
  saving,
  onUpdateSession,
  onResetSession,
}: {
  sessions: Record<string, SessionConfig>;
  overrides: Record<string, Partial<SessionConfig>>;
  defaults: Record<string, Partial<SessionConfig>>;
  globalRisk: GlobalRiskDefaults;
  saving: boolean;
  onUpdateSession: (name: string, overrides: Partial<SessionConfig>) => Promise<void>;
  onResetSession: (name: string) => Promise<void>;
}) {
  const allPrefixes = Array.from(
    new Set(
      Object.keys(sessions).map((n) => {
        const parts = n.split(":");
        return parts.length > 1 ? parts[0] : "OTHER";
      })
    )
  ).sort();

  const tabs = ["All", ...allPrefixes];
  const [activeTab, setActiveTab] = useState(tabs[0]);

  const filteredEntries = Object.entries(sessions).filter(([name]) => {
    if (activeTab === "All") return true;
    const parts = name.split(":");
    const prefix = parts.length > 1 ? parts[0] : "OTHER";
    return prefix === activeTab;
  });

  return (
    <div>
      <div className="flex items-center gap-4 mb-3">
        <h3 className="text-sm font-semibold text-text-secondary">
          Strategy Configurations
        </h3>
        <div className="flex items-center gap-1">
          {tabs.map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-3 py-1 rounded text-[11px] font-medium transition-colors ${
                activeTab === tab
                  ? "bg-accent/20 text-accent border border-accent/30"
                  : "text-text-muted hover:text-text-secondary hover:bg-bg-secondary border border-transparent"
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {filteredEntries.map(([name, cfg]) => (
          <SessionConfigCard
            key={name}
            name={name}
            cfg={cfg}
            globalRisk={globalRisk}
            overrides={overrides[name] ?? {}}
            defaults={defaults[name] ?? {}}
            saving={saving}
            onSave={onUpdateSession}
            onReset={onResetSession}
          />
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConfigView (main export)
// ---------------------------------------------------------------------------

export function ConfigView({
  config,
  loading,
  saving,
  error,
  onUpdateSession,
  onResetSession,
  onUpdateWebhooks,
  execConfigs,
}: ConfigViewProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading configuration...
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Could not load configuration
      </div>
    );
  }

  const general = (config.config?.general as Record<string, unknown>) ?? {};
  const risk = (config.config?.risk as Record<string, unknown>) ?? {};
  const dates = (config.config?.dates as Record<string, unknown>) ?? {};

  const globalRisk: GlobalRiskDefaults = {
    risk_usd: Number(risk.risk_usd ?? 250),
    min_qty: Number(risk.min_qty ?? 1),
    max_single_risk_usd: Number(risk.max_single_risk_usd ?? 500),
  };

  return (
    <div className="space-y-6">
      {/* Global error banner */}
      {error && (
        <div className="rounded-md bg-loss/10 border border-loss/20 px-4 py-3 text-sm text-loss">
          {error}
        </div>
      )}

      {/* Execution Configs Summary */}
      {Object.keys(execConfigs).length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-text-secondary mb-3">
            Execution Configs
          </h3>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {Object.entries(execConfigs).map(([name, meta]) => {
              const colorClasses = CONFIG_COLORS[name] ?? "bg-text-muted/20 text-text-muted border-text-muted/30";
              return (
                <Card key={name} className="border-border bg-bg-card">
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${colorClasses}`}>
                          {name}
                        </span>
                        <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                          meta.enabled
                            ? "text-profit bg-profit/10"
                            : "text-text-muted bg-text-muted/10"
                        }`}>
                          {meta.enabled ? "enabled" : "disabled"}
                        </span>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="space-y-1">
                      <WebhookManager
                        configName={name}
                        webhooks={meta.webhooks ?? []}
                        onSave={onUpdateWebhooks}
                      />
                      {((meta.sessions?.length ?? 0) > 0 || (meta.lsi_sessions?.length ?? 0) > 0) && (() => {
                        // Build a lookup: short name → session type from config.sessions
                        const typeByShort: Record<string, "continuation" | "lsi"> = {};
                        Object.entries(config.sessions ?? {}).forEach(([fullName, cfg]) => {
                          const short = fullName.includes(":") ? fullName.split(":")[1] : fullName;
                          typeByShort[short] = cfg.type === "continuation" ? "continuation" : "lsi";
                        });
                        const allSessions = [
                          ...(meta.sessions ?? []).map((s) => ({ name: s, isLsi: typeByShort[s] !== "continuation" })),
                          ...(meta.lsi_sessions ?? []).map((s) => ({ name: s, isLsi: true })),
                        ];
                        return (
                          <div className="flex justify-between pb-1 pt-8 gap-2">
                            <span className="text-text-muted text-xs shrink-0">Strategies</span>
                            <div className="flex flex-wrap gap-1 justify-end">
                              {allSessions.map(({ name: s, isLsi }) => (
                                <span key={s} className="inline-flex items-center gap-1 font-mono text-xs text-white bg-white/5 border border-white/10 rounded px-1.5 py-0.5">
                                  {s}
                                  <span className={`text-[9px] font-medium px-1 py-0.5 rounded ${
                                    isLsi
                                      ? "text-violet-400 bg-violet-400/10"
                                      : "text-emerald-400 bg-emerald-400/10"
                                  }`}>
                                    {isLsi ? "LSI" : "ORB"}
                                  </span>
                                </span>
                              ))}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      )}

      {/* General + Risk */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">General</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(general).map(([key, value]) => (
              <ConfigItem key={key} label={key} value={String(value)} />
            ))}
          </CardContent>
        </Card>

        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Default Risk</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(risk).map(([key, value]) => (
              <ConfigItem key={key} label={key} value={String(value)} />
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Strategy configs */}
      <SessionConfigsSection
        sessions={config.sessions}
        overrides={config.overrides ?? {}}
        defaults={config.defaults ?? {}}
        globalRisk={globalRisk}
        saving={saving}
        onUpdateSession={onUpdateSession}
        onResetSession={onResetSession}
      />

      {/* Date config */}
      {Object.keys(dates).length > 0 && (
        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Dates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(dates).map(([key, value]) => (
              <ConfigItem
                key={key}
                label={key}
                value={Array.isArray(value) ? value.join(", ") : String(value)}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
