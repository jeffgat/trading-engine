import type { BacktestConfig } from '../lib/types';

/** Known session prefixes to detect in config keys. */
const SESSION_PREFIXES = ['ny', 'asia', 'ldn'] as const;

/** Keys to skip — not strategy variables. */
const SKIP_KEYS = new Set(['instrument', 'point_value', 'min_qty', 'qty_step']);

/** Human-readable labels for known param suffixes. */
const LABELS: Record<string, string> = {
    rr: 'R:R',
    tp1_ratio: 'TP1 Ratio',
    risk_usd: 'Risk',
    atr_length: 'ATR Length',

    stop_atr_pct: 'Stop ATR%',
    stop_orb_pct: 'Stop ORB%',
    min_gap_atr_pct: 'Min Gap ATR%',
    max_gap_points: 'Max Gap Pts',
    max_gap_atr_pct: 'Max Gap ATR%',
    orb_window: 'ORB Window',
    entry_window: 'Entry Window',
    flat_window: 'Flat Window',
    qualifying_move_atr_pct: 'Liq. Sweep ATR%',
    strategy: 'Strategy',
    direction_filter: 'Direction',
    bar_magnifier: 'Bar Magnifier',
    impulse_close_filter: 'ICF',
    regime_sizing: 'Regime Sizing',
    regime_rule: 'Regime Rule',
    regime_multiplier: 'Regime Mult',
};

function formatValue(key: string, val: unknown): string {
    if (typeof val === 'string') return val;
    const n = val as number;
    if (key === 'risk_usd') return `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
    if (key.endsWith('_pct')) return `${n}%`;
    if (key.endsWith('_ticks')) return `${n} ticks`;
    return String(n);
}

function labelFor(key: string): string {
    return LABELS[key] ?? key.replace(/_/g, ' ');
}

function Pill({ label, value }: { label: string; value: string }) {
    return (
        <div className="flex items-center gap-1.5 rounded border border-border bg-bg-secondary/50 px-2 py-1">
            <span className="text-[10px] font-medium uppercase tracking-wide text-text-muted">
                {label}
            </span>
            <span className="font-mono text-xs text-text-primary">{value}</span>
        </div>
    );
}

interface VariablesTestedProps {
    config: BacktestConfig;
}

export function VariablesTested({ config }: VariablesTestedProps) {
    // Separate global vs per-session params dynamically
    const globalParams: { key: string; val: unknown }[] = [];
    const sessionParams: Record<string, { suffix: string; val: unknown }[]> = {};

    for (const [key, val] of Object.entries(config)) {
        if (val == null || SKIP_KEYS.has(key)) continue;

        const sessionMatch = SESSION_PREFIXES.find((p) => key.startsWith(`${p}_`));
        if (sessionMatch) {
            const suffix = key.slice(sessionMatch.length + 1);
            if (!sessionParams[sessionMatch]) sessionParams[sessionMatch] = [];
            sessionParams[sessionMatch].push({ suffix, val });
        } else {
            globalParams.push({ key, val });
        }
    }

    const sessionNames = Object.keys(sessionParams).sort();

    return (
        <div className="rounded-lg border border-border bg-bg-card px-4 py-3">
            <h3 className="mb-2.5 text-xs font-medium uppercase tracking-wider text-text-muted">
                Variables Tested
            </h3>

            <div className="flex flex-wrap gap-2">
                {config.instrument && (
                    <Pill label="Instrument" value={config.instrument} />
                )}
                {globalParams.map(({ key, val }) => (
                    <Pill key={key} label={labelFor(key)} value={formatValue(key, val)} />
                ))}
            </div>

            {sessionNames.length > 0 && (
                <div className="mt-3 space-y-2">
                    {sessionNames.map((session) => (
                        <div key={session} className="flex flex-wrap items-center gap-2">
                            <span className="w-10 shrink-0 text-[10px] font-bold uppercase text-text-secondary">
                                {session}
                            </span>
                            {sessionParams[session].map(({ suffix, val }) => (
                                <Pill
                                    key={suffix}
                                    label={labelFor(suffix)}
                                    value={formatValue(suffix, val)}
                                />
                            ))}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
