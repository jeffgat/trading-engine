import { useCallback, useRef, useState } from 'react';
import { useStarredHistory } from '../hooks/useStarredHistory';
import type { BacktestResult } from '../lib/types';
import { BacktestHistoryPanel } from './BacktestHistoryPanel';
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog';
import { Dialog, DialogContent } from './ui/dialog';
import { ConfigBar } from './ConfigBar';
import { DateRangePicker } from './DateRangePicker';
import { EquityChart } from './EquityChart';
import { Skeleton } from './Skeleton';
import { StatBar } from './StatBar';
import { StrategyTag } from './StrategyTag';
import { TradesTable } from './TradesTable';
import { VariablesTested } from './VariablesTested';

export function SavedStrategiesDashboard() {
    const { history, activeId, refreshHistory, loadBacktest, refilterBacktest, unstarBacktest, hideBacktest, renameBacktest, bulkUnstarBacktests, bulkHideBacktests } =
        useStarredHistory();
    const [data, setData] = useState<BacktestResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [unstarId, setUnstarId] = useState<string | null>(null);
    const [historyModalOpen, setHistoryModalOpen] = useState(false);

    // Date filter state
    const [filterStart, setFilterStart] = useState('');
    const [filterEnd, setFilterEnd] = useState('');
    const [originalDateStart, setOriginalDateStart] = useState('');
    const [originalDateEnd, setOriginalDateEnd] = useState('');
    const [filterLoading, setFilterLoading] = useState(false);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const handleLoad = async (id: string) => {
        setLoading(true);
        const result = await loadBacktest(id);
        if (result) {
            const r = result as any;
            const dates = r.equity_curve?.length
                ? [r.equity_curve[0].date, r.equity_curve[r.equity_curve.length - 1].date]
                : r.trades?.length
                    ? [r.trades[0].date, r.trades[r.trades.length - 1].date]
                    : ['', ''];
            const dateStart = r.date_start || dates[0] || '';
            const dateEnd = r.date_end || dates[1] || '';

            // Always update the original (full) range for this backtest
            setOriginalDateStart(dateStart);
            setOriginalDateEnd(dateEnd);

            if (!filterStart) {
                // First load — no filter yet, use full range
                setFilterStart(dateStart);
                setFilterEnd(dateEnd);
                setData(result);
            } else {
                // Subsequent loads — keep existing date filter, re-apply it
                const filtered = await refilterBacktest(id, filterStart, filterEnd);
                setData(filtered || result);
            }
        }
        setLoading(false);
    };

    const handleDateChange = useCallback((start: string, end: string) => {
        setFilterStart(start);
        setFilterEnd(end);

        if (debounceRef.current) clearTimeout(debounceRef.current);

        debounceRef.current = setTimeout(async () => {
            if (!activeId) return;
            const isFullRange = start === originalDateStart && end === originalDateEnd;
            setFilterLoading(true);
            const result = await refilterBacktest(
                activeId,
                isFullRange ? undefined : start,
                isFullRange ? undefined : end,
            );
            if (result) setData(result);
            setFilterLoading(false);
        }, 300);
    }, [activeId, originalDateStart, originalDateEnd, refilterBacktest]);

    const handleDateReset = useCallback(() => {
        handleDateChange(originalDateStart, originalDateEnd);
    }, [originalDateStart, originalDateEnd, handleDateChange]);

    const handleUnstar = async (id: string) => {
        await unstarBacktest(id);
        if (id === activeId) {
            setData(null);
        }
    };

    const confirmUnstar = () => {
        if (unstarId) handleUnstar(unstarId);
    };

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <div className="mb-6">
                <h1 className="text-xl font-semibold text-text-primary">Saved Strategies</h1>
                {loading && <Skeleton className="mt-1.5 h-4 w-48 rounded" />}
                {data?.config?.instrument && !loading && (
                    <div className="mt-0.5 flex items-center gap-2 text-sm text-text-muted">
                        {data.name && (
                            <span className="font-medium text-text-secondary">
                                {data.name} &middot;{' '}
                            </span>
                        )}
                        {data.config.instrument} &middot; R:R {data.config.rr} &middot;
                        Risk ${data.config.risk_usd?.toLocaleString()}
                        <StrategyTag strategy={data.config.strategy} />
                    </div>
                )}
            </div>

            {history.length === 0 && !loading ? (
                <div className="rounded-lg border border-border bg-bg-card p-8">
                    <p className="text-center text-sm text-text-muted">
                        No saved strategies yet. Star a backtest to save it here.
                    </p>
                </div>
            ) : (
                <>
                    <BacktestHistoryPanel
                        history={history}
                        activeId={activeId}
                        onLoad={handleLoad}
                        onDelete={handleUnstar}
                        onRefresh={refreshHistory}
                        onStar={(id) => setUnstarId(id)}
                        onHide={hideBacktest}
                        onRename={renameBacktest}
                        onBulkUnstar={bulkUnstarBacktests}
                        onBulkHide={bulkHideBacktests}
                        onExpand={() => setHistoryModalOpen(true)}
                    />

                    <Dialog open={historyModalOpen} onOpenChange={setHistoryModalOpen}>
                        <DialogContent className="max-w-7xl p-0">
                            <BacktestHistoryPanel
                                history={history}
                                activeId={activeId}
                                onLoad={(id) => { handleLoad(id); setHistoryModalOpen(false); }}
                                onDelete={handleUnstar}
                                onRefresh={refreshHistory}
                                onStar={(id) => setUnstarId(id)}
                                onHide={hideBacktest}
                                onRename={renameBacktest}
                                onBulkUnstar={bulkUnstarBacktests}
                                onBulkHide={bulkHideBacktests}
                                isModal
                            />
                        </DialogContent>
                    </Dialog>

                    <ConfirmDeleteDialog
                        open={unstarId !== null}
                        onOpenChange={(open) => { if (!open) setUnstarId(null); }}
                        onConfirm={confirmUnstar}
                        title="Remove from saved?"
                        description="This strategy will be unstarred and removed from your saved list."
                        confirmLabel="Unstar"
                        confirmClassName="rounded-md border border-yellow-500/40 bg-yellow-500/10 px-3 py-1.5 text-xs font-medium text-yellow-400 transition-colors hover:bg-yellow-500/20"
                    />
                </>
            )}

            {loading && <LoadingSkeleton />}

            {!loading && data && (
                <div className="mt-4 space-y-4">
                    <DateRangePicker
                        startDate={filterStart}
                        endDate={filterEnd}
                        originalStart={originalDateStart}
                        originalEnd={originalDateEnd}
                        onChange={handleDateChange}
                        onReset={handleDateReset}
                        loading={filterLoading}
                        disabled={!data.trades?.length}
                    />
                    <VariablesTested config={data.config} />
                    <ConfigBar config={data.config} />
                    <StatBar summary={data.summary} trades={data.trades} riskUsd={data.config.risk_usd ?? 50000} />
                    <EquityChart data={data.equity_curve} riskUsd={data.config.risk_usd ?? 50000} />
                    <TradesTable trades={data.trades} riskUsd={data.config.risk_usd ?? 50000} instrument={data.config.instrument ?? "NQ"} />
                </div>
            )}

            {!loading && !data && history.length > 0 && (
                <div className="flex h-[400px] items-center justify-center text-text-muted">
                    Select a saved strategy to view
                </div>
            )}
        </div>
    );
}

function LoadingSkeleton() {
    return (
        <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-[88px] rounded-lg" />
                ))}
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-[88px] rounded-lg" />
                ))}
            </div>
            <Skeleton className="h-[430px] rounded-lg" />
            <Skeleton className="h-[200px] rounded-lg" />
        </div>
    );
}
