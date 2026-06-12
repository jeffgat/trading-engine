import { AccountsView } from '@/execution/components/AccountsView';
import { CONFIG_COLORS, SESSION_DISPLAY_NAMES } from '@/execution/lib/constants';
import type {
  ConfigResponse,
  ExecConfigMeta,
  SessionConfig,
  WebhookEntry,
} from '@/execution/lib/types';
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/shared/ui/card';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/shared/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/ui/select';
import { ExecutionTabSkeleton } from '@/shared/ui/page-skeletons';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/ui/tabs';
import { useCallback, useState } from 'react';

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
    onToggleEnabled?: (configName: string, enabled: boolean) => Promise<void>;
    execConfigs: Record<string, ExecConfigMeta>;
    onPauseWebhook: (configName: string, idx: number) => Promise<void>;
    onResumeWebhook: (configName: string, idx: number) => Promise<void>;
    onUpdateMultiplier: (
        configName: string,
        idx: number,
        multiplier: number,
    ) => Promise<void>;
    onFlattenWebhook: (configName: string, idx: number) => Promise<void>;
}

/** Derive the 3-state mode from config metadata. */
function getConfigMode(meta: ExecConfigMeta): 'live' | 'dry-run' | 'disabled' {
    if (!meta.enabled) return 'disabled';
    if (meta.webhooks.length > 0) return 'live';
    return 'dry-run';
}

const MODE_STYLES = {
    live: 'text-profit bg-profit/10',
    'dry-run': 'text-amber-400 bg-amber-400/10',
    disabled: 'text-text-muted bg-text-muted/10',
} as const;

const MODE_LABELS = {
    live: 'Live',
    'dry-run': 'Dry Run',
    disabled: 'Disabled',
} as const;

interface GlobalRiskDefaults {
    risk_usd: number;
    min_qty: number;
    max_single_risk_usd: number;
}

type DraftValues = Record<string, string | number | boolean | number[] | null>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DOW_NAMES = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

const DOW_OPTIONS = [
    { value: '', label: 'None' },
    { value: '0', label: 'Mon' },
    { value: '1', label: 'Tue' },
    { value: '2', label: 'Wed' },
    { value: '3', label: 'Thu' },
    { value: '4', label: 'Fri' },
    { value: '5', label: 'Sat' },
    { value: '6', label: 'Sun' },
];

/** Format excluded_dow (single int, array, or null) for display. */
function formatExcludedDow(dow: number | number[] | null): string | null {
    if (dow == null) return null;
    if (Array.isArray(dow)) {
        return dow.map((d) => DOW_NAMES[d] ?? `DOW ${d}`).join(', ');
    }
    return DOW_NAMES[dow] ?? `DOW ${dow}`;
}

// ---------------------------------------------------------------------------
// Small reusable components
// ---------------------------------------------------------------------------

function SectionLabel({ children }: { children: React.ReactNode }) {
    return (
        <span className="text-[10px] font-semibold uppercase tracking-wider text-text-primary">
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
                className={`font-mono text-xs ${
                    overridden ? 'text-amber-400' : 'text-text-secondary'
                }`}>
                {value}
                {overridden && ' *'}
            </span>
        </div>
    );
}

function formatLsiVariant(value: string | null | undefined): string {
    if (!value) return '—';
    if (value === 'htf-LSI') return 'HTF LSI';
    if (value === 'legacy-LSI') return 'Legacy LSI';
    return value;
}

function formatLsiEntryMode(value: string | null | undefined): string {
    if (!value) return '—';
    if (value === 'fvg_limit') return 'FVG Retest Limit';
    if (value === 'close') return 'Signal Bar Close';
    return value;
}

function formatBars(value: number | null | undefined, suffix = 'bars'): string {
    if (value == null) return '—';
    return `${value} ${suffix}`;
}

function formatMinutes(value: number | null | undefined): string {
    if (value == null) return '—';
    return `${value} min`;
}

function EditableField({
    label,
    value,
    onChange,
    type = 'text',
    overridden,
}: {
    label: string;
    value: string;
    onChange: (v: string) => void;
    type?: 'text' | 'number';
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
                    overridden ? 'border-amber-400/40' : 'border-border'
                }`}
            />
        </div>
    );
}

/** Parse excluded_dow draft value into a number array. */
function parseDowDraft(raw: string | number | boolean | number[] | null): number[] {
    if (raw == null || raw === '') return [];
    if (Array.isArray(raw)) return raw;
    const n = Number(raw);
    return Number.isFinite(n) ? [n] : [];
}

/** Multi-day skip selector with + Add / - Remove buttons. */
function SkipDaysField({
    value,
    onChange,
}: {
    value: string | number | boolean | number[] | null;
    onChange: (days: number[] | null) => void;
}) {
    const selected = parseDowDraft(value);
    const available = DOW_OPTIONS.filter(
        (o) => o.value !== '' && !selected.includes(Number(o.value)),
    );

    const addDay = (dow: string) => {
        if (dow === '') return;
        const next = [...selected, Number(dow)].sort();
        onChange(next);
    };

    const removeDay = (dow: number) => {
        const next = selected.filter((d) => d !== dow);
        onChange(next.length > 0 ? next : null);
    };

    return (
        <div className="py-0.5 space-y-1">
            <span className="text-text-muted text-xs">Skip Days</span>
            {selected.length > 0 && (
                <div className="flex flex-wrap gap-1">
                    {selected.map((d) => (
                        <span
                            key={d}
                            className="inline-flex items-center gap-1 rounded bg-amber-400/10 px-1.5 py-0.5 text-[10px] font-medium text-amber-400">
                            {DOW_NAMES[d] ?? `DOW ${d}`}
                            <button
                                type="button"
                                onClick={() => removeDay(d)}
                                className="text-amber-400/60 hover:text-loss transition-colors leading-none">
                                &minus;
                            </button>
                        </span>
                    ))}
                </div>
            )}
            {available.length > 0 && (
                <div className="flex items-center gap-1.5">
                    <select
                        id="skip-day-add"
                        defaultValue=""
                        className="h-5 rounded border border-border bg-bg-secondary px-1 font-mono text-[10px] text-text-secondary outline-none focus:border-accent">
                        <option value="" disabled>
                            Day...
                        </option>
                        {available.map((o) => (
                            <option key={o.value} value={o.value}>
                                {o.label}
                            </option>
                        ))}
                    </select>
                    <button
                        type="button"
                        onClick={() => {
                            const sel = document.getElementById(
                                'skip-day-add',
                            ) as HTMLSelectElement | null;
                            if (sel && sel.value) {
                                addDay(sel.value);
                                sel.value = '';
                            }
                        }}
                        className="text-[10px] font-medium text-profit hover:text-profit/80 transition-colors">
                        + Add
                    </button>
                </div>
            )}
            {selected.length === 0 && available.length > 0 && (
                <span className="text-[10px] text-text-muted">None</span>
            )}
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
        setDraft((d) => [...d, { url: '', label: '' }]);
    };

    const removeRow = (idx: number) => {
        setDraft((d) => d.filter((_, i) => i !== idx));
    };

    const handleSave = async () => {
        const cleaned = draft.filter((w) => w.url.trim());
        if (draft.some((w) => !w.url.trim())) {
            setError('All webhook entries must have a URL');
            return;
        }
        setSaving(true);
        setError(null);
        try {
            await onSave(configName, cleaned);
            setEditing(false);
            setDraft([]);
        } catch (e) {
            setError(e instanceof Error ? e.message : 'Failed to save');
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
                        className="text-[10px] text-text-muted hover:text-accent transition-colors">
                        Edit
                    </button>
                </div>
                {webhooks.length === 0 ? (
                    <p className="text-[11px] text-text-muted italic">not set</p>
                ) : (
                    <div className="space-y-1">
                        {webhooks.map((w, i) => (
                            <div
                                key={i}
                                className="flex items-center justify-between gap-2">
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
                        className="rounded border border-border px-2 py-0.5 text-[10px] text-text-muted hover:text-text-secondary transition-colors disabled:opacity-50">
                        Cancel
                    </button>
                    <button
                        onClick={handleSave}
                        disabled={saving}
                        className="rounded bg-accent px-2 py-0.5 text-[10px] font-medium text-white hover:bg-accent/90 transition-colors disabled:opacity-50">
                        {saving ? 'Saving…' : 'Save'}
                    </button>
                </div>
            </div>

            {error && <p className="text-[10px] text-loss">{error}</p>}

            {draft.map((w, i) => (
                <div
                    key={i}
                    className="space-y-1 rounded border border-border bg-bg-secondary p-2">
                    <div className="flex items-center justify-between">
                        <span className="text-[10px] text-text-muted">
                            Account {i + 1}
                        </span>
                        <button
                            onClick={() => removeRow(i)}
                            className="text-[10px] text-loss/70 hover:text-loss transition-colors">
                            Remove
                        </button>
                    </div>
                    <input
                        type="text"
                        placeholder="Label (e.g. Account 1)"
                        value={w.label}
                        onChange={(e) => setField(i, 'label', e.target.value)}
                        className="w-full rounded border border-border bg-bg-secondary px-2 py-1 font-mono text-[11px] text-text-secondary outline-none focus:border-accent focus:ring-1 focus:ring-accent/50"
                    />
                    <input
                        type="text"
                        placeholder="Webhook URL"
                        value={w.url}
                        onChange={(e) => setField(i, 'url', e.target.value)}
                        className={`w-full rounded border bg-bg-secondary px-2 py-1 font-mono text-[10px] text-text-secondary outline-none focus:border-accent focus:ring-1 focus:ring-accent/50 ${
                            w.url.trim() ? 'border-border' : 'border-loss/40'
                        }`}
                    />
                </div>
            ))}

            <button
                onClick={addRow}
                className="w-full rounded border border-dashed border-border py-1 text-[10px] text-text-muted hover:border-accent/50 hover:text-accent transition-colors">
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
    maxOpenContracts,
    globalRisk,
    overrides,
    saving,
    onSave,
    onReset,
}: {
    name: string;
    cfg: SessionConfig;
    maxOpenContracts?: number;
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
    const isLsi = cfg.type !== 'continuation';

    // Derive short name and config prefix for display
    const shortName = name.includes(':') ? name.split(':')[1] : name;
    const configPrefix = name.includes(':') ? name.split(':')[0] : null;
    const configColorClasses = configPrefix
        ? CONFIG_COLORS[configPrefix] ??
          'bg-text-muted/20 text-text-muted border-text-muted/30'
        : null;

    const stopIsOrb = cfg.stop_basis === 'orb';
    const gapIsOrb = cfg.gap_filter_basis === 'orb';

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
                exit_mode: cfg.exit_mode ?? 'split',
                min_gap_atr_pct: cfg.min_gap_atr_pct,
                min_stop_points: cfg.min_stop_points,
                max_bars_after_sweep: cfg.max_bars_after_sweep,
                fvg_window_left: cfg.fvg_window_left,
                qty_multiplier: cfg.qty_multiplier,
                risk_usd: cfg.risk_usd,
                min_qty: cfg.min_qty,
                max_single_risk_usd: cfg.max_single_risk_usd,
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
                exit_mode: cfg.exit_mode ?? 'split',
                stop_atr_pct: cfg.stop_atr_pct,
                stop_orb_pct: cfg.stop_orb_pct,
                min_gap_atr_pct: cfg.min_gap_atr_pct,
                min_gap_orb_pct: cfg.min_gap_orb_pct,
                max_gap_atr_pct: cfg.max_gap_atr_pct,
                risk_usd: cfg.risk_usd,
                min_qty: cfg.min_qty,
                max_single_risk_usd: cfg.max_single_risk_usd,
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
              'rr',
              'tp1_ratio',
              'min_gap_atr_pct',
              'min_stop_points',
              'max_bars_after_sweep',
              'fvg_window_left',
              'qty_multiplier',
              'risk_usd',
              'min_qty',
              'max_single_risk_usd',
          ]
        : [
              'rr',
              'tp1_ratio',
              'stop_atr_pct',
              'stop_orb_pct',
              'min_gap_atr_pct',
              'min_gap_orb_pct',
              'max_gap_atr_pct',
              'risk_usd',
              'min_qty',
              'max_single_risk_usd',
          ];
    const timeFields = isLsi
        ? ['entry_start', 'entry_end', 'flat_start', 'flat_end']
        : ['orb_start', 'orb_end', 'entry_start', 'entry_end', 'flat_start', 'flat_end'];
    const stringFields = ['exit_mode'];

    const handleSave = async () => {
        setCardError(null);
        try {
            // Send ALL current draft values (not just diffs) so the backend can
            // compute which are actually overrides vs defaults
            const allFields: Record<string, unknown> = {};

            for (const f of timeFields) {
                allFields[f] = String(draft[f] ?? '');
            }
            for (const f of numericFields) {
                allFields[f] = Number(draft[f]);
            }
            for (const f of stringFields) {
                allFields[f] = String(draft[f] ?? 'split');
            }
            const dowDraft = draft.excluded_dow;
            if (
                dowDraft == null ||
                dowDraft === '' ||
                (Array.isArray(dowDraft) && dowDraft.length === 0)
            ) {
                allFields.excluded_dow = null;
            } else if (Array.isArray(dowDraft)) {
                allFields.excluded_dow = dowDraft.map(Number);
            } else {
                allFields.excluded_dow = Number(dowDraft);
            }

            await onSave(name, allFields as Partial<SessionConfig>);
            setEditing(false);
            setDraft({});
        } catch (e) {
            setCardError(e instanceof Error ? e.message : 'Failed to save');
        }
    };

    const handleReset = async () => {
        setCardError(null);
        try {
            await onReset(name);
        } catch (e) {
            setCardError(e instanceof Error ? e.message : 'Failed to reset');
        }
    };

    // Risk override checks (for read mode)
    const maxSingleRisk = cfg.max_single_risk_usd ?? globalRisk.max_single_risk_usd;
    const riskOverridden = cfg.risk_usd !== globalRisk.risk_usd;
    const minQtyOverridden = cfg.min_qty !== globalRisk.min_qty;
    const maxRiskOverridden = maxSingleRisk !== globalRisk.max_single_risk_usd;
    const hasAnyRiskOverride = riskOverridden || minQtyOverridden || maxRiskOverridden;
    const maxContractCapValue =
        maxOpenContracts && maxOpenContracts > 0
            ? maxOpenContracts.toString()
            : '—';

    // ── Edit mode ───────────────────────────────────────────────────
    if (editing) {
        return (
            <Card className="border-border bg-bg-card">
                <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                            <CardTitle className="text-sm font-semibold text-white">
                                {shortName}
                            </CardTitle>
                            <span
                                className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                    isLsi
                                        ? 'text-info bg-info/10'
                                        : 'text-profit bg-profit/10'
                                }`}>
                                {isLsi ? 'LSI' : 'ORB'}
                            </span>
                            {configPrefix && configColorClasses && (
                                <span
                                    className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${configColorClasses}`}>
                                    {configPrefix}
                                </span>
                            )}
                        </div>
                        <div className="flex gap-1.5">
                            <button
                                onClick={cancelEditing}
                                disabled={saving}
                                className="rounded border border-border px-2.5 py-1 text-[11px] text-text-muted hover:text-text-secondary hover:bg-bg-secondary transition-colors disabled:opacity-50">
                                Cancel
                            </button>
                            <button
                                onClick={handleSave}
                                disabled={saving}
                                className="rounded bg-accent px-2.5 py-1 text-[11px] font-medium text-white hover:bg-accent/90 transition-colors disabled:opacity-50">
                                {saving ? 'Saving...' : 'Save'}
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
                                    value={String(draft.orb_start ?? '')}
                                    onChange={(v) => setField('orb_start', v)}
                                    overridden={isOverridden('orb_start')}
                                />
                                <EditableField
                                    label="ORB End"
                                    value={String(draft.orb_end ?? '')}
                                    onChange={(v) => setField('orb_end', v)}
                                    overridden={isOverridden('orb_end')}
                                />
                            </>
                        )}
                        <EditableField
                            label="Entry Start"
                            value={String(draft.entry_start ?? '')}
                            onChange={(v) => setField('entry_start', v)}
                            overridden={isOverridden('entry_start')}
                        />
                        <EditableField
                            label="Entry End"
                            value={String(draft.entry_end ?? '')}
                            onChange={(v) => setField('entry_end', v)}
                            overridden={isOverridden('entry_end')}
                        />
                        <EditableField
                            label="Flat Start"
                            value={String(draft.flat_start ?? '')}
                            onChange={(v) => setField('flat_start', v)}
                            overridden={isOverridden('flat_start')}
                        />
                        <EditableField
                            label="Flat End"
                            value={String(draft.flat_end ?? '')}
                            onChange={(v) => setField('flat_end', v)}
                            overridden={isOverridden('flat_end')}
                        />
                        <SkipDaysField
                            value={draft.excluded_dow as number[] | number | null}
                            onChange={(days) =>
                                setDraft((d) => ({ ...d, excluded_dow: days }))
                            }
                        />
                    </div>

                    {/* Strategy */}
                    <div className="space-y-0.5 border-t border-border pt-2">
                        <SectionLabel>Strategy</SectionLabel>
                        <EditableField
                            label="R:R"
                            value={String(draft.rr ?? '')}
                            onChange={(v) => setField('rr', v)}
                            type="number"
                            overridden={isOverridden('rr')}
                        />
                        <EditableField
                            label="TP1 Ratio"
                            value={String(draft.tp1_ratio ?? '')}
                            onChange={(v) => setField('tp1_ratio', v)}
                            type="number"
                            overridden={isOverridden('tp1_ratio')}
                        />
                        <div className="grid grid-cols-[110px_1fr] items-center gap-2 py-1">
                            <label className="text-[11px] uppercase tracking-wider text-text-muted">
                                Exit Mode{isOverridden('exit_mode') ? ' *' : ''}
                            </label>
                            <Select
                                value={String(draft.exit_mode ?? 'split')}
                                onValueChange={(value) =>
                                    setDraft((d) => ({ ...d, exit_mode: value }))
                                }>
                                <SelectTrigger className="h-7 border-border bg-bg-secondary text-xs">
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="split">Split</SelectItem>
                                    <SelectItem value="single_target">
                                        Single Target
                                    </SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        {isLsi ? (
                            <>
                                <EditableField
                                    label="Gap ATR %"
                                    value={String(draft.min_gap_atr_pct ?? '')}
                                    onChange={(v) => setField('min_gap_atr_pct', v)}
                                    type="number"
                                    overridden={isOverridden('min_gap_atr_pct')}
                                />
                                <EditableField
                                    label="Min Stop Pts"
                                    value={String(draft.min_stop_points ?? '')}
                                    onChange={(v) => setField('min_stop_points', v)}
                                    type="number"
                                    overridden={isOverridden('min_stop_points')}
                                />
                                <EditableField
                                    label="Max Sweep Bars"
                                    value={String(draft.max_bars_after_sweep ?? '')}
                                    onChange={(v) => setField('max_bars_after_sweep', v)}
                                    type="number"
                                    overridden={isOverridden('max_bars_after_sweep')}
                                />
                                <EditableField
                                    label="Max Inversion Bars"
                                    value={String(draft.fvg_window_left ?? '')}
                                    onChange={(v) => setField('fvg_window_left', v)}
                                    type="number"
                                    overridden={isOverridden('fvg_window_left')}
                                />
                                {cfg.lsi_variant && (
                                    <ConfigItem
                                        label="LSI Variant"
                                        value={formatLsiVariant(cfg.lsi_variant)}
                                        overridden={isOverridden('lsi_variant')}
                                    />
                                )}
                                {cfg.lsi_entry_mode && (
                                    <ConfigItem
                                        label="Entry Trigger"
                                        value={formatLsiEntryMode(cfg.lsi_entry_mode)}
                                        overridden={isOverridden('lsi_entry_mode')}
                                    />
                                )}
                                {cfg.htf_level_tf_minutes != null && (
                                    <ConfigItem
                                        label="HTF Sweep Timeframe"
                                        value={formatMinutes(cfg.htf_level_tf_minutes)}
                                        overridden={isOverridden('htf_level_tf_minutes')}
                                    />
                                )}
                                {cfg.htf_n_left != null && (
                                    <ConfigItem
                                        label="HTF Pivot Width"
                                        value={`${cfg.htf_n_left} bars each side`}
                                        overridden={isOverridden('htf_n_left')}
                                    />
                                )}
                                {cfg.htf_trade_max_per_session != null && (
                                    <ConfigItem
                                        label="HTF Trades / Session"
                                        value={cfg.htf_trade_max_per_session.toString()}
                                        overridden={isOverridden('htf_trade_max_per_session')}
                                    />
                                )}
                                {cfg.max_fvg_to_inversion_bars != null && (
                                    <ConfigItem
                                        label="FVG Inversion Window"
                                        value={formatBars(cfg.max_fvg_to_inversion_bars)}
                                        overridden={isOverridden('max_fvg_to_inversion_bars')}
                                    />
                                )}
                            </>
                        ) : (
                            <>
                                {stopIsOrb ? (
                                    <EditableField
                                        label="Stop ORB %"
                                        value={String(draft.stop_orb_pct ?? '')}
                                        onChange={(v) => setField('stop_orb_pct', v)}
                                        type="number"
                                        overridden={isOverridden('stop_orb_pct')}
                                    />
                                ) : (
                                    <EditableField
                                        label="Stop ATR %"
                                        value={String(draft.stop_atr_pct ?? '')}
                                        onChange={(v) => setField('stop_atr_pct', v)}
                                        type="number"
                                        overridden={isOverridden('stop_atr_pct')}
                                    />
                                )}
                                {gapIsOrb ? (
                                    <EditableField
                                        label="Gap ORB %"
                                        value={String(draft.min_gap_orb_pct ?? '')}
                                        onChange={(v) => setField('min_gap_orb_pct', v)}
                                        type="number"
                                        overridden={isOverridden('min_gap_orb_pct')}
                                    />
                                ) : (
                                    <>
                                        <EditableField
                                            label="Gap ATR % (min)"
                                            value={String(draft.min_gap_atr_pct ?? '')}
                                            onChange={(v) =>
                                                setField('min_gap_atr_pct', v)
                                            }
                                            type="number"
                                            overridden={isOverridden('min_gap_atr_pct')}
                                        />
                                        <EditableField
                                            label="Gap ATR % (max)"
                                            value={String(draft.max_gap_atr_pct ?? '')}
                                            onChange={(v) =>
                                                setField('max_gap_atr_pct', v)
                                            }
                                            type="number"
                                            overridden={isOverridden('max_gap_atr_pct')}
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
                            value={String(draft.risk_usd ?? '')}
                            onChange={(v) => setField('risk_usd', v)}
                            type="number"
                            overridden={isOverridden('risk_usd')}
                        />
                        <EditableField
                            label="Min Qty"
                            value={String(draft.min_qty ?? '')}
                            onChange={(v) => setField('min_qty', v)}
                            type="number"
                            overridden={isOverridden('min_qty')}
                        />
                        <EditableField
                            label="Max Single Risk"
                            value={String(draft.max_single_risk_usd ?? '')}
                            onChange={(v) => setField('max_single_risk_usd', v)}
                            type="number"
                            overridden={isOverridden('max_single_risk_usd')}
                        />
                        {isLsi && (
                            <EditableField
                                label="Qty Multiplier"
                                value={String(draft.qty_multiplier ?? '')}
                                onChange={(v) => setField('qty_multiplier', v)}
                                type="number"
                                overridden={isOverridden('qty_multiplier')}
                            />
                        )}
                        <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
                        <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
                        <ConfigItem
                            label="Max Contract Cap"
                            value={maxContractCapValue}
                        />
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
                                        This will remove all overrides for this strategy
                                        and restore the original configuration.
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
                                            className="rounded bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600">
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
                        <CardTitle className="text-sm font-semibold text-white">
                            {shortName}
                        </CardTitle>
                        <span
                            className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                                isLsi
                                    ? 'text-info bg-info/10'
                                    : 'text-profit bg-profit/10'
                            }`}>
                            {isLsi ? 'LSI' : 'ORB'}
                        </span>
                        {configPrefix && configColorClasses && (
                            <span
                                className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${configColorClasses}`}>
                                {configPrefix}
                            </span>
                        )}
                        {hasOverrides && (
                            <span className="text-[10px] text-amber-400 bg-amber-400/10 px-1.5 py-0.5 rounded">
                                overridden
                            </span>
                        )}
                    </div>
                    <button
                        onClick={startEditing}
                        className="rounded border border-border px-2.5 py-1 text-[11px] text-text-muted hover:text-text-secondary hover:bg-bg-secondary transition-colors">
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
                            overridden={
                                isOverridden('orb_start') || isOverridden('orb_end')
                            }
                        />
                    )}
                    <ConfigItem
                        label="Entry"
                        value={`${cfg.entry_start} - ${cfg.entry_end}`}
                        overridden={
                            isOverridden('entry_start') || isOverridden('entry_end')
                        }
                    />
                    <ConfigItem
                        label="Flat"
                        value={`${cfg.flat_start} - ${cfg.flat_end}`}
                        overridden={
                            isOverridden('flat_start') || isOverridden('flat_end')
                        }
                    />
                    {excludedDowDisplay && (
                        <ConfigItem
                            label="Skip Day"
                            value={excludedDowDisplay}
                            overridden={isOverridden('excluded_dow')}
                        />
                    )}
                </div>

                {/* Strategy */}
                <div className="space-y-1 border-t border-border pt-2">
                    <SectionLabel>Strategy</SectionLabel>
                    <ConfigItem
                        label="R:R"
                        value={cfg.rr.toString()}
                        overridden={isOverridden('rr')}
                    />
                    <ConfigItem
                        label="Direction"
                        value={cfg.long_only ? 'Long' : 'Both'}
                    />
                    {!!cfg.regime_gates?.length && (
                        <ConfigItem
                            label="Regime Gates"
                            value={cfg.regime_gates.join(', ')}
                        />
                    )}
                    {!cfg.regime_gates?.length && cfg.regime_gate && (
                        <ConfigItem label="Regime Gate" value={cfg.regime_gate} />
                    )}
                    {cfg.structure_gate && (
                        <ConfigItem label="Structure Gate" value={cfg.structure_gate} />
                    )}
                    <ConfigItem
                        label="TP1 Ratio"
                        value={cfg.tp1_ratio.toString()}
                        overridden={isOverridden('tp1_ratio')}
                    />
                    <ConfigItem
                        label="Exit Mode"
                        value={
                            (cfg.exit_mode ?? 'split') === 'single_target'
                                ? 'Single Target'
                                : 'Split'
                        }
                        overridden={isOverridden('exit_mode')}
                    />
                    {isLsi ? (
                        <>
                            <ConfigItem
                                label="Gap ATR %"
                                value={`${cfg.min_gap_atr_pct}%`}
                                overridden={isOverridden('min_gap_atr_pct')}
                            />
                            <ConfigItem
                                label="Min Stop Pts"
                                value={
                                    cfg.min_stop_points != null
                                        ? `${cfg.min_stop_points}`
                                        : '—'
                                }
                                overridden={isOverridden('min_stop_points')}
                            />
                            <ConfigItem
                                label="Max Sweep Bars"
                                value={cfg.max_bars_after_sweep?.toString() ?? '—'}
                                overridden={isOverridden('max_bars_after_sweep')}
                            />
                            <ConfigItem
                                label="Max Inversion Bars"
                                value={cfg.fvg_window_left?.toString() ?? '—'}
                                overridden={isOverridden('fvg_window_left')}
                            />
                            {cfg.lsi_variant && (
                                <ConfigItem
                                    label="LSI Variant"
                                    value={formatLsiVariant(cfg.lsi_variant)}
                                    overridden={isOverridden('lsi_variant')}
                                />
                            )}
                            {cfg.lsi_entry_mode && (
                                <ConfigItem
                                    label="Entry Trigger"
                                    value={formatLsiEntryMode(cfg.lsi_entry_mode)}
                                    overridden={isOverridden('lsi_entry_mode')}
                                />
                            )}
                            {cfg.htf_level_tf_minutes != null && (
                                <ConfigItem
                                    label="HTF Sweep Timeframe"
                                    value={formatMinutes(cfg.htf_level_tf_minutes)}
                                    overridden={isOverridden('htf_level_tf_minutes')}
                                />
                            )}
                            {cfg.htf_n_left != null && (
                                <ConfigItem
                                    label="HTF Pivot Width"
                                    value={`${cfg.htf_n_left} bars each side`}
                                    overridden={isOverridden('htf_n_left')}
                                />
                            )}
                            {cfg.htf_trade_max_per_session != null && (
                                <ConfigItem
                                    label="HTF Trades / Session"
                                    value={cfg.htf_trade_max_per_session.toString()}
                                    overridden={isOverridden('htf_trade_max_per_session')}
                                />
                            )}
                            {cfg.max_fvg_to_inversion_bars != null && (
                                <ConfigItem
                                    label="FVG Inversion Window"
                                    value={formatBars(cfg.max_fvg_to_inversion_bars)}
                                    overridden={isOverridden('max_fvg_to_inversion_bars')}
                                />
                            )}
                        </>
                    ) : (
                        <>
                            {stopIsOrb ? (
                                <ConfigItem
                                    label="Stop ORB %"
                                    value={`${cfg.stop_orb_pct}%`}
                                    overridden={isOverridden('stop_orb_pct')}
                                />
                            ) : (
                                <ConfigItem
                                    label="Stop ATR %"
                                    value={`${cfg.stop_atr_pct}%`}
                                    overridden={isOverridden('stop_atr_pct')}
                                />
                            )}
                            {gapIsOrb ? (
                                <ConfigItem
                                    label="Gap ORB %"
                                    value={`${cfg.min_gap_orb_pct}%`}
                                    overridden={isOverridden('min_gap_orb_pct')}
                                />
                            ) : (
                                <ConfigItem
                                    label="Gap ATR %"
                                    value={
                                        cfg.max_gap_atr_pct
                                            ? `${cfg.min_gap_atr_pct} - ${cfg.max_gap_atr_pct}%`
                                            : `${cfg.min_gap_atr_pct}%`
                                    }
                                    overridden={
                                        isOverridden('min_gap_atr_pct') ||
                                        isOverridden('max_gap_atr_pct')
                                    }
                                />
                            )}
                        </>
                    )}
                </div>

                {/* Risk & Sizing */}
                <div
                    className={`space-y-1 rounded-md px-2 py-2 -mx-2 ${
                        hasAnyRiskOverride
                            ? 'bg-amber-400/5 border border-amber-400/20'
                            : 'border-t border-border/30 pt-2'
                    }`}>
                    <SectionLabel>
                        {hasAnyRiskOverride
                            ? 'Risk & Sizing (override)'
                            : 'Risk & Sizing'}
                    </SectionLabel>
                    <ConfigItem
                        label="Risk USD"
                        value={`$${cfg.risk_usd}`}
                        overridden={riskOverridden || isOverridden('risk_usd')}
                    />
                    <ConfigItem
                        label="Min Qty"
                        value={cfg.min_qty.toString()}
                        overridden={minQtyOverridden || isOverridden('min_qty')}
                    />
                    <ConfigItem
                        label="Max Single Risk"
                        value={`$${maxSingleRisk}`}
                        overridden={
                            maxRiskOverridden || isOverridden('max_single_risk_usd')
                        }
                    />
                    {isLsi && cfg.qty_multiplier != null && (
                        <ConfigItem
                            label="Qty Multiplier"
                            value={`${cfg.qty_multiplier}x`}
                            overridden={isOverridden('qty_multiplier')}
                        />
                    )}
                    <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
                    <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
                    <ConfigItem
                        label="Max Contract Cap"
                        value={maxContractCapValue}
                    />
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
                                    This will remove all overrides for this strategy and
                                    restore the original configuration.
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
                                        className="rounded bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600">
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
// SessionConfigsSection (dropdown filter by exec config)
// ---------------------------------------------------------------------------

/** Check if an exec config is live (has webhooks) */
function isExecConfigLive(meta: ExecConfigMeta): boolean {
    return meta.webhooks.length > 0;
}

function SessionConfigsSection({
    sessions,
    overrides,
    defaults,
    globalRisk,
    saving,
    onUpdateSession,
    onResetSession,
    execConfigs,
}: {
    sessions: Record<string, SessionConfig>;
    overrides: Record<string, Partial<SessionConfig>>;
    defaults: Record<string, Partial<SessionConfig>>;
    globalRisk: GlobalRiskDefaults;
    saving: boolean;
    onUpdateSession: (name: string, overrides: Partial<SessionConfig>) => Promise<void>;
    onResetSession: (name: string) => Promise<void>;
    execConfigs: Record<string, ExecConfigMeta>;
}) {
    // Sort configs: live first, then dry-run, alphabetical within each group
    const configNames = Object.keys(execConfigs);
    const liveConfigs = configNames
        .filter((n) => isExecConfigLive(execConfigs[n]))
        .sort();
    const dryRunConfigs = configNames
        .filter((n) => !isExecConfigLive(execConfigs[n]))
        .sort();
    const sortedConfigs = [...liveConfigs, ...dryRunConfigs];

    const defaultConfig = liveConfigs[0] ?? sortedConfigs[0] ?? '';
    const [activeConfig, setActiveConfig] = useState(defaultConfig);

    // If the active config was removed, fall back to default
    const validConfig = execConfigs[activeConfig] ? activeConfig : defaultConfig;

    // Sync state when the valid config diverges (e.g. config deleted externally)
    if (validConfig !== activeConfig) {
        setActiveConfig(validConfig);
    }

    const activeMeta = execConfigs[validConfig];

    // Filter sessions by prefix matching: "FAST_V1.1:NQ_Asia" matches config "FAST_V1.1"
    const filteredEntries = Object.entries(sessions).filter(([name]) => {
        if (!name.includes(':')) return false;
        const prefix = name.split(':')[0];
        return prefix === validConfig;
    });

    const selectedIsLive = activeMeta ? isExecConfigLive(activeMeta) : false;

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-text-secondary">
                    Strategy Parameters
                </h3>
                <div className="flex items-center gap-3">
                    <span
                        className={`text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded ${
                            selectedIsLive
                                ? 'text-profit bg-profit/10'
                                : 'text-amber-400 bg-amber-400/10'
                        }`}>
                        {selectedIsLive ? 'Live' : 'Dry Run'}
                    </span>
                    <span className="text-xs text-text-muted">
                        {filteredEntries.length} strateg
                        {filteredEntries.length !== 1 ? 'ies' : 'y'}
                    </span>
                    <Select value={validConfig} onValueChange={setActiveConfig}>
                        <SelectTrigger className="w-[180px]">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {sortedConfigs.map((name) => {
                                const meta = execConfigs[name];
                                const live = meta ? isExecConfigLive(meta) : false;
                                const count =
                                    (meta?.sessions?.length ?? 0) +
                                    (meta?.lsi_sessions?.length ?? 0);
                                return (
                                    <SelectItem key={name} value={name}>
                                        <span className="flex items-center gap-2">
                                            {name}
                                            <span
                                                className={`text-[9px] uppercase ${
                                                    live
                                                        ? 'text-profit'
                                                        : 'text-amber-400'
                                                }`}>
                                                {live ? 'Live' : 'Dry'}
                                            </span>
                                            <span className="text-text-muted">
                                                ({count})
                                            </span>
                                        </span>
                                    </SelectItem>
                                );
                            })}
                        </SelectContent>
                    </Select>
                </div>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {filteredEntries.map(([name, cfg]) => (
                    <SessionConfigCard
                        key={name}
                        name={name}
                        cfg={cfg}
                        maxOpenContracts={activeMeta?.max_open_contracts}
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
    onToggleEnabled,
    execConfigs,
    onPauseWebhook,
    onResumeWebhook,
    onUpdateMultiplier,
    onFlattenWebhook,
}: ConfigViewProps) {
    if (loading) {
        return <ExecutionTabSkeleton tab="config" />;
    }

    if (!config) {
        return (
            <div className="flex flex-col items-center justify-center gap-2 py-20 text-center">
                <p className="text-text-muted">Could not load configuration</p>
                {error && <p className="max-w-lg text-sm text-loss">{error}</p>}
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

            <Tabs defaultValue="strategy" className="space-y-4">
                <TabsList className="bg-bg-card border border-border">
                    <TabsTrigger value="strategy">Parameters</TabsTrigger>
                    <TabsTrigger value="execution">Configs Overview</TabsTrigger>
                    <TabsTrigger value="accounts">Accounts</TabsTrigger>
                </TabsList>

                <TabsContent value="strategy" className="space-y-6">
                    <SessionConfigsSection
                        sessions={config.sessions}
                        overrides={config.overrides ?? {}}
                        defaults={config.defaults ?? {}}
                        globalRisk={globalRisk}
                        saving={saving}
                        onUpdateSession={onUpdateSession}
                        onResetSession={onResetSession}
                        execConfigs={execConfigs}
                    />
                </TabsContent>

                <TabsContent value="execution" className="space-y-6">
                    {Object.keys(execConfigs).length > 0 && (
                        <div>
                            <h3 className="text-sm font-semibold text-text-secondary mb-3">
                                Execution Configs
                            </h3>
                            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                                {Object.entries(execConfigs).map(([name, meta]) => {
                                    const colorClasses =
                                        CONFIG_COLORS[name] ??
                                        'bg-text-muted/20 text-text-muted border-text-muted/30';
                                    const isActive =
                                        name === 'ALPHA_V1' ||
                                        name === 'ALPHA_V1-A' ||
                                        name === 'ALPHA_V1-C' ||
                                        name === 'TESTING';
                                    return (
                                        <Card
                                            key={name}
                                            className={`border-border bg-bg-card ${
                                                !isActive ? 'opacity-40' : ''
                                            }`}>
                                            <CardHeader className="pb-2">
                                                <div className="flex items-center justify-between">
                                                    <div className="flex items-center gap-2">
                                                        <span
                                                            className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${colorClasses}`}>
                                                            {name}
                                                        </span>
                                                        {(() => {
                                                            const mode =
                                                                getConfigMode(meta);
                                                            return (
                                                                <span
                                                                    className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${MODE_STYLES[mode]}`}>
                                                                    {MODE_LABELS[mode]}
                                                                </span>
                                                            );
                                                        })()}
                                                    </div>
                                                    {meta.webhooks.length === 0 &&
                                                        onToggleEnabled && (
                                                            <button
                                                                onClick={() =>
                                                                    onToggleEnabled(
                                                                        name,
                                                                        !meta.enabled,
                                                                    )
                                                                }
                                                                className="text-[10px] text-text-muted hover:text-text-secondary transition-colors">
                                                                {meta.enabled
                                                                    ? 'Disable'
                                                                    : 'Enable'}
                                                            </button>
                                                        )}
                                                </div>
                                            </CardHeader>
                                            <CardContent className="space-y-2">
                                                <div className="space-y-1">
                                                    <WebhookManager
                                                        configName={name}
                                                        webhooks={meta.webhooks ?? []}
                                                        onSave={onUpdateWebhooks}
                                                    />
                                                    {((meta.sessions?.length ?? 0) > 0 ||
                                                        (meta.lsi_sessions?.length ?? 0) >
                                                            0) &&
                                                        (() => {
                                                            const typeByShort: Record<
                                                                string,
                                                                'continuation' | 'lsi'
                                                            > = {};
                                                            Object.entries(
                                                                config.sessions ?? {},
                                                            ).forEach(
                                                                ([fullName, cfg]) => {
                                                                    const short =
                                                                        fullName.includes(
                                                                            ':',
                                                                        )
                                                                            ? fullName.split(
                                                                                  ':',
                                                                              )[1]
                                                                            : fullName;
                                                                    typeByShort[short] =
                                                                        cfg.type ===
                                                                        'continuation'
                                                                            ? 'continuation'
                                                                            : 'lsi';
                                                                },
                                                            );
                                                            const allSessions = [
                                                                ...(
                                                                    meta.sessions ?? []
                                                                ).map((s) => ({
                                                                    name: s,
                                                                    isLsi:
                                                                        typeByShort[s] !==
                                                                        'continuation',
                                                                })),
                                                                ...(
                                                                    meta.lsi_sessions ??
                                                                    []
                                                                ).map((s) => ({
                                                                    name: s,
                                                                    isLsi: true,
                                                                })),
                                                            ];
                                                            return (
                                                                <div className="flex justify-between pb-1 pt-8 gap-2">
                                                                    <span className="text-text-muted text-xs shrink-0">
                                                                        Strategies
                                                                    </span>
                                                                    <div className="flex flex-wrap gap-1 justify-end">
                                                                        {allSessions.map(
                                                                            ({
                                                                                name: s,
                                                                                isLsi,
                                                                            }) => {
                                                                                const displayName =
                                                                                    SESSION_DISPLAY_NAMES[
                                                                                        name
                                                                                    ]?.[
                                                                                        s
                                                                                    ] ??
                                                                                    s;
                                                                                return (
                                                                                    <span
                                                                                        key={
                                                                                            s
                                                                                        }
                                                                                        className="inline-flex items-center gap-1 font-mono text-xs text-white bg-white/5 border border-white/10 rounded px-1.5 py-0.5">
                                                                                        {
                                                                                            displayName
                                                                                        }
                                                                                        {!SESSION_DISPLAY_NAMES[
                                                                                            name
                                                                                        ]?.[
                                                                                            s
                                                                                        ] && (
                                                                                            <span
                                                                                                className={`text-[9px] font-medium px-1 py-0.5 rounded ${
                                                                                                    isLsi
                                                                                                        ? 'text-info bg-info/10'
                                                                                                        : 'text-profit bg-profit/10'
                                                                                                }`}>
                                                                                                {isLsi
                                                                                                    ? 'LSI'
                                                                                                    : 'ORB'}
                                                                                            </span>
                                                                                        )}
                                                                                    </span>
                                                                                );
                                                                            },
                                                                        )}
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

                    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                        <Card className="border-border bg-bg-card">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-semibold">
                                    General
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-1">
                                {Object.entries(general).map(([key, value]) => (
                                    <ConfigItem
                                        key={key}
                                        label={key}
                                        value={String(value)}
                                    />
                                ))}
                            </CardContent>
                        </Card>

                        <Card className="border-border bg-bg-card">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-semibold">
                                    Default Risk
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-1">
                                {Object.entries(risk).map(([key, value]) => (
                                    <ConfigItem
                                        key={key}
                                        label={key}
                                        value={String(value)}
                                    />
                                ))}
                            </CardContent>
                        </Card>
                    </div>

                    {Object.keys(dates).length > 0 && (
                        <Card className="border-border bg-bg-card">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-semibold">
                                    Dates
                                </CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-1">
                                {Object.entries(dates).map(([key, value]) => (
                                    <ConfigItem
                                        key={key}
                                        label={key}
                                        value={
                                            Array.isArray(value)
                                                ? value.join(', ')
                                                : String(value)
                                        }
                                    />
                                ))}
                            </CardContent>
                        </Card>
                    )}
                </TabsContent>

                <TabsContent value="accounts" className="space-y-6">
                    <AccountsView
                        execConfigs={execConfigs}
                        onPause={onPauseWebhook}
                        onResume={onResumeWebhook}
                        onUpdateMultiplier={onUpdateMultiplier}
                        onFlatten={onFlattenWebhook}
                        onUpdateWebhooks={onUpdateWebhooks}
                    />
                </TabsContent>
            </Tabs>
        </div>
    );
}
