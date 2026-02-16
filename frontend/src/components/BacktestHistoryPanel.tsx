import { useMemo, useState } from 'react';
import type { BacktestHistoryItem } from '../lib/types';
import { formatPct } from '../lib/utils';
import { CopyIdButton } from './CopyIdButton';
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog';
import { SessionTag } from './SessionTag';
import { ScrollArea } from './ui/scroll-area';

type SortKey =
    | 'instrument'
    | 'total_pnl_usd'
    | 'total_trades'
    | 'win_rate'
    | 'max_drawdown_usd'
    | 'sharpe_ratio'
    | 'profit_factor'
    | 'rr'
    | 'r_per_year';

function formatR(pnl: number, risk: number): string {
    const r = pnl / (risk || 50000);
    const sign = r >= 0 ? '+' : '';
    return `${sign}${r.toFixed(2)}R`;
}

function getSessionParam(item: BacktestHistoryItem, suffix: 'stop_atr_pct' | 'min_gap_atr_pct'): number | undefined {
    const prefixes = ['ny', 'asia', 'ldn'] as const;
    for (const p of prefixes) {
        const key = `${p}_${suffix}` as keyof BacktestHistoryItem;
        if (item[key] != null) return item[key] as number;
    }
    return undefined;
}

function calcRPerYear(item: BacktestHistoryItem): number {
    const netR = (item.total_pnl_usd ?? 0) / (item.risk_usd || 50000);
    if (!item.date_start || !item.date_end) return 0;
    const ms = new Date(item.date_end).getTime() - new Date(item.date_start).getTime();
    const years = ms / (365.25 * 24 * 60 * 60 * 1000);
    return years > 0 ? netR / years : 0;
}

function formatDateRange(start: string, end: string): string {
    if (!start || !end) return '';
    const fmt = (d: string) => {
        const [y, m] = d.split('-');
        const dt = new Date(+y, +m - 1);
        return dt.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    };
    return `${fmt(start)}\u2013${fmt(end)}`;
}

function RefreshButton({ onClick }: { onClick: () => void }) {
    return (
        <button
            onClick={onClick}
            className="rounded p-1 text-text-muted transition-colors hover:bg-bg-secondary hover:text-text-primary"
            title="Refresh history">
            <svg
                className="h-3.5 w-3.5"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5">
                <path d="M2.5 8a5.5 5.5 0 0 1 9.3-4l1.7 1.7M13.5 8a5.5 5.5 0 0 1-9.3 4l-1.7-1.7" />
                <path d="M13.5 2.5v3h-3M2.5 13.5v-3h3" />
            </svg>
        </button>
    );
}

interface HistoryPanelProps {
    history: BacktestHistoryItem[];
    activeId: string | null;
    onLoad: (id: string) => void;
    onDelete: (id: string) => void;
    onRefresh: () => void;
    onStar?: (id: string) => void;
    onHide?: (id: string) => void;
}

export function BacktestHistoryPanel({
    history,
    activeId,
    onLoad,
    onDelete,
    onRefresh,
    onStar,
    onHide,
}: HistoryPanelProps) {
    const [deleteId, setDeleteId] = useState<string | null>(null);
    const [sortKey, setSortKey] = useState<SortKey>('total_pnl_usd');
    const [sortAsc, setSortAsc] = useState(false);
    const [instrumentFilter, setInstrumentFilter] = useState<string>('all');
    const [showHidden, setShowHidden] = useState(false);

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

    const hiddenCount = useMemo(() => history.filter((h) => h.hidden).length, [history]);

    const filtered = useMemo(() => {
        let items = history;
        if (!showHidden && onHide) {
            items = items.filter((h) => !h.hidden);
        }
        if (instrumentFilter !== 'all') {
            items = items.filter((h) => h.instrument === instrumentFilter);
        }
        return items;
    }, [history, instrumentFilter, showHidden, onHide]);

    const sorted = useMemo(() => {
        const arr = [...filtered];
        arr.sort((a, b) => {
            let va: number | string;
            let vb: number | string;

            if (sortKey === 'instrument') {
                va = a.instrument;
                vb = b.instrument;
                return sortAsc
                    ? va.localeCompare(vb)
                    : vb.localeCompare(va);
            }

            if (sortKey === 'r_per_year') {
                va = calcRPerYear(a);
                vb = calcRPerYear(b);
            } else {
                va = a[sortKey] ?? 0;
                vb = b[sortKey] ?? 0;
            }
            return sortAsc ? (va as number) - (vb as number) : (vb as number) - (va as number);
        });
        return arr;
    }, [filtered, sortKey, sortAsc]);

    const SortHeader = ({ label, sortBy, align = 'right' }: { label: string; sortBy: SortKey; align?: 'left' | 'right' }) => {
        const isActive = sortKey === sortBy;
        return (
            <th
                className={`whitespace-nowrap px-3 py-2 font-medium cursor-pointer select-none transition-colors hover:text-text-primary ${
                    align === 'left' ? 'text-left' : 'text-right'
                }`}
                onClick={() => handleSort(sortBy)}>
                <span className={isActive ? 'text-accent' : ''}>
                    {label}
                    {isActive && (
                        <span className="ml-0.5">{sortAsc ? '\u25B2' : '\u25BC'}</span>
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
                    No saved backtests yet
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
                            className="rounded border border-border bg-bg-secondary px-2 py-0.5 text-xs text-text-primary outline-none focus:border-accent">
                            <option value="all">All instruments</option>
                            {instruments.map((inst) => (
                                <option key={inst} value={inst}>{inst}</option>
                            ))}
                        </select>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    {onHide && hiddenCount > 0 && (
                        <button
                            onClick={() => setShowHidden(!showHidden)}
                            className={`rounded px-2 py-0.5 text-[10px] font-medium transition-colors ${
                                showHidden
                                    ? 'bg-text-muted/15 text-text-secondary'
                                    : 'text-text-muted hover:text-text-secondary'
                            }`}
                            title={showHidden ? 'Hide hidden rows' : 'Show hidden rows'}>
                            {showHidden ? `${hiddenCount} hidden` : `${hiddenCount} hidden`}
                            <svg className="ml-1 inline h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                {showHidden ? (
                                    <><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" /><circle cx="8" cy="8" r="2" /></>
                                ) : (
                                    <><path d="M2 2l12 12" /><path d="M6.5 6.5a2 2 0 002.8 2.8M4 4.5C2.8 5.6 1.8 7.2 1 8c1 1.5 3.5 5 7 5 1 0 1.9-.2 2.7-.6M9.5 4.2c.5.2 1 .5 1.5.8 1.5 1 3 3 4 3-1-1.5-3.5-5-7-5-.3 0-.7 0-1 .1" /></>
                                )}
                            </svg>
                        </button>
                    )}
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
                            <th className="whitespace-nowrap px-3 py-2 text-left font-medium">Date Range</th>
                            <SortHeader label="RR" sortBy="rr" />
                            <th className="whitespace-nowrap px-3 py-2 text-right font-medium">Stop%</th>
                            <th className="whitespace-nowrap px-3 py-2 text-right font-medium">Gap%</th>
                            <SortHeader label="Net R" sortBy="total_pnl_usd" />
                            <SortHeader label="R/Yr" sortBy="r_per_year" />
                            <SortHeader label="Trades" sortBy="total_trades" />
                            <SortHeader label="Win%" sortBy="win_rate" />
                            <SortHeader label="Max DD (R)" sortBy="max_drawdown_usd" />
                            <SortHeader label="Sharpe" sortBy="sharpe_ratio" />
                            <SortHeader label="PF" sortBy="profit_factor" />
                            <th className="w-20 px-2 py-2" />
                        </tr>
                    </thead>
                    <tbody>
                        {sorted.map((item) => {
                            const isActive = item.id === activeId;
                            const netR = (item.total_pnl_usd ?? 0) / (item.risk_usd || 50000);
                            const rPerYear = calcRPerYear(item);
                            const ddR = (item.max_drawdown_usd ?? 0) / (item.risk_usd || 50000);
                            const sharpe = item.sharpe_ratio ?? 0;
                            const pf = item.profit_factor ?? 0;
                            const pnlPositive = netR >= 0;

                            return (
                                <tr
                                    key={item.id}
                                    onClick={() => onLoad(item.id)}
                                    className={`group cursor-pointer border-l-2 transition-colors ${
                                        isActive
                                            ? 'border-l-accent bg-accent/8'
                                            : 'border-l-transparent hover:bg-bg-card-hover'
                                    } ${item.hidden ? 'opacity-40' : ''}`}>
                                    <td className="px-3 py-2 text-left">
                                        <div className="flex items-start gap-1">
                                            <div className="flex flex-col">
                                                {item.name && (
                                                    <span className="text-[10px] font-medium text-accent leading-tight">
                                                        {item.name}
                                                    </span>
                                                )}
                                                <span className="font-bold text-text-primary">
                                                    {item.instrument}
                                                </span>
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
                                    <td className="whitespace-nowrap px-3 py-2 text-left text-text-muted">
                                        {formatDateRange(item.date_start, item.date_end)}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {item.rr != null ? item.rr : '\u2014'}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {getSessionParam(item, 'stop_atr_pct')?.toFixed(0) ?? '\u2014'}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {getSessionParam(item, 'min_gap_atr_pct')?.toFixed(0) ?? '\u2014'}
                                    </td>
                                    <td className="whitespace-nowrap px-3 py-2 text-right font-mono font-semibold"
                                        style={{ color: pnlPositive ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                                        {formatR(item.total_pnl_usd, item.risk_usd)}
                                    </td>
                                    <td className="whitespace-nowrap px-3 py-2 text-right font-mono text-text-secondary"
                                        style={{ color: rPerYear >= 0 ? 'var(--color-profit)' : 'var(--color-loss)' }}>
                                        {rPerYear >= 0 ? '+' : ''}{rPerYear.toFixed(2)}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {item.total_trades}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {formatPct(item.win_rate)}
                                    </td>
                                    <td className="whitespace-nowrap px-3 py-2 text-right font-mono text-loss">
                                        {ddR.toFixed(2)}R
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {sharpe.toFixed(2)}
                                    </td>
                                    <td className="px-3 py-2 text-right text-text-secondary">
                                        {pf.toFixed(2)}
                                    </td>
                                    <td className="px-2 py-2 text-center">
                                        <span className="inline-flex items-center gap-0.5">
                                            {onStar && (
                                                <span
                                                    role="button"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onStar(item.id);
                                                    }}
                                                    className={`rounded p-0.5 transition-colors ${
                                                        item.starred
                                                            ? 'inline-block text-yellow-400 hover:bg-bg-secondary'
                                                            : 'hidden text-text-muted hover:bg-bg-secondary hover:text-yellow-400 group-hover:inline-block'
                                                    }`}
                                                    title={item.starred ? 'Unstar' : 'Star'}>
                                                    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill={item.starred ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1">
                                                        <path d="M8 1.5l2.1 4.3 4.7.7-3.4 3.3.8 4.7L8 12.2 3.8 14.5l.8-4.7L1.2 6.5l4.7-.7z" />
                                                    </svg>
                                                </span>
                                            )}
                                            {onHide && (
                                                <span
                                                    role="button"
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        onHide(item.id);
                                                    }}
                                                    className={`rounded p-0.5 transition-colors ${
                                                        item.hidden
                                                            ? 'inline-block text-text-muted hover:bg-bg-secondary hover:text-text-primary'
                                                            : 'hidden text-text-muted hover:bg-bg-secondary hover:text-text-primary group-hover:inline-block'
                                                    }`}
                                                    title={item.hidden ? 'Unhide' : 'Hide'}>
                                                    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                                        {item.hidden ? (
                                                            <><path d="M2 2l12 12" /><path d="M6.5 6.5a2 2 0 002.8 2.8M4 4.5C2.8 5.6 1.8 7.2 1 8c1 1.5 3.5 5 7 5 1 0 1.9-.2 2.7-.6M9.5 4.2c.5.2 1 .5 1.5.8 1.5 1 3 3 4 3-1-1.5-3.5-5-7-5-.3 0-.7 0-1 .1" /></>
                                                        ) : (
                                                            <><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" /><circle cx="8" cy="8" r="2" /></>
                                                        )}
                                                    </svg>
                                                </span>
                                            )}
                                            <span
                                                role="button"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    setDeleteId(item.id);
                                                }}
                                                className="hidden rounded p-0.5 text-text-muted hover:bg-bg-secondary hover:text-text-primary group-hover:inline-block">
                                                <svg
                                                    className="h-3.5 w-3.5"
                                                    viewBox="0 0 16 16"
                                                    fill="currentColor">
                                                    <path d="M3.72 3.72a.75.75 0 011.06 0L8 6.94l3.22-3.22a.75.75 0 111.06 1.06L9.06 8l3.22 3.22a.75.75 0 11-1.06 1.06L8 9.06l-3.22 3.22a.75.75 0 01-1.06-1.06L6.94 8 3.72 4.78a.75.75 0 010-1.06z" />
                                                </svg>
                                            </span>
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
                onOpenChange={(open) => {
                    if (!open) setDeleteId(null);
                }}
                onConfirm={() => {
                    if (deleteId) onDelete(deleteId);
                }}
                title="Delete this backtest?"
                description="The saved backtest result will be permanently removed."
            />
        </div>
    );
}
