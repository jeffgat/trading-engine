import { useState, useCallback } from "react";
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
import type { ConfigResponse, SessionConfig } from "@/execution/lib/types";

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
}

interface GlobalRiskDefaults {
  risk_usd: number;
  min_qty: number;
  max_single_risk_usd: number;
}

type DraftValues = Record<string, string | number | boolean | null>;

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
// SessionConfigCard
// ---------------------------------------------------------------------------

function SessionConfigCard({
  name,
  cfg,
  globalRisk,
  overrides,
  defaults,
  saving,
  onSave,
  onReset,
}: {
  name: string;
  cfg: SessionConfig;
  globalRisk: GlobalRiskDefaults;
  overrides: Partial<SessionConfig>;
  defaults: Partial<SessionConfig>;
  saving: boolean;
  onSave: (name: string, overrides: Partial<SessionConfig>) => Promise<void>;
  onReset: (name: string) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<DraftValues>({});
  const [cardError, setCardError] = useState<string | null>(null);

  const hasOverrides = Object.keys(overrides).length > 0;

  const stopIsOrb = cfg.stop_basis === "orb";
  const gapIsOrb = cfg.gap_filter_basis === "orb";

  // Check if a field is overridden (exists in the overrides dict from backend)
  const isOverridden = (field: string) =>
    Object.prototype.hasOwnProperty.call(overrides, field);

  // Start editing — populate draft from current cfg values
  const startEditing = useCallback(() => {
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
    setCardError(null);
    setEditing(true);
  }, [cfg]);

  const cancelEditing = () => {
    setEditing(false);
    setDraft({});
    setCardError(null);
  };

  const setField = (key: string, raw: string) => {
    setDraft((d) => ({ ...d, [key]: raw }));
  };

  // Build the sparse override object — only fields that differ from defaults
  const buildOverrides = (): Partial<SessionConfig> => {
    const result: Record<string, unknown> = {};

    const numericFields = [
      "rr", "tp1_ratio", "stop_atr_pct", "stop_orb_pct",
      "min_gap_atr_pct", "min_gap_orb_pct", "max_gap_atr_pct",
      "risk_usd", "min_qty", "max_single_risk_usd", "be_offset_ticks",
    ];
    const timeFields = [
      "orb_start", "orb_end", "entry_start", "entry_end",
      "flat_start", "flat_end",
    ];

    for (const f of timeFields) {
      const val = String(draft[f] ?? "");
      if (val !== String(defaults[f as keyof SessionConfig] ?? "")) {
        result[f] = val;
      }
    }

    for (const f of numericFields) {
      const val = Number(draft[f]);
      const def = Number(defaults[f as keyof SessionConfig] ?? 0);
      if (!isNaN(val) && val !== def) {
        result[f] = val;
      }
    }

    // excluded_dow: null means "none"
    const dowDraft = draft.excluded_dow;
    const dowVal =
      dowDraft === null || dowDraft === "" ? null : Number(dowDraft);
    const dowDefault = (defaults as Record<string, unknown>).excluded_dow ?? null;
    if (dowVal !== dowDefault) {
      result.excluded_dow = dowVal;
    }

    return result as Partial<SessionConfig>;
  };

  const handleSave = async () => {
    setCardError(null);
    try {
      // Send ALL current draft values (not just diffs) so the backend can
      // compute which are actually overrides vs defaults
      const allFields: Record<string, unknown> = {};
      const numericFields = [
        "rr", "tp1_ratio", "stop_atr_pct", "stop_orb_pct",
        "min_gap_atr_pct", "min_gap_orb_pct", "max_gap_atr_pct",
        "risk_usd", "min_qty", "max_single_risk_usd", "be_offset_ticks",
      ];
      const timeFields = [
        "orb_start", "orb_end", "entry_start", "entry_end",
        "flat_start", "flat_end",
      ];

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
            <SelectField
              label="Skip Day"
              value={draft.excluded_dow == null ? "" : String(draft.excluded_dow)}
              options={DOW_OPTIONS}
              onChange={(v) =>
                setDraft((d) => ({ ...d, excluded_dow: v === "" ? null : v }))
              }
            />
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
                    This will remove all overrides for this session and restore the
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
  return (
    <Card className="border-border bg-bg-card">
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-sm font-semibold bg-primary/20 px-2 py-1 w-fit rounded-md">
              {name}
            </CardTitle>
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
          <ConfigItem
            label="ORB"
            value={`${cfg.orb_start} - ${cfg.orb_end}`}
            overridden={isOverridden("orb_start") || isOverridden("orb_end")}
          />
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
          {cfg.excluded_dow != null && (
            <ConfigItem
              label="Skip Day"
              value={DOW_NAMES[cfg.excluded_dow] ?? `DOW ${cfg.excluded_dow}`}
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
                  This will remove all overrides for this session and restore the
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
// ConfigView (main export)
// ---------------------------------------------------------------------------

export function ConfigView({
  config,
  loading,
  saving,
  error,
  onUpdateSession,
  onResetSession,
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

      {/* Session configs */}
      <div>
        <h3 className="text-sm font-semibold text-text-secondary mb-3">
          Session Configurations
        </h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(config.sessions).map(([name, cfg]) => (
            <SessionConfigCard
              key={name}
              name={name}
              cfg={cfg}
              globalRisk={globalRisk}
              overrides={config.overrides?.[name] ?? {}}
              defaults={config.defaults?.[name] ?? {}}
              saving={saving}
              onSave={onUpdateSession}
              onReset={onResetSession}
            />
          ))}
        </div>
      </div>

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
