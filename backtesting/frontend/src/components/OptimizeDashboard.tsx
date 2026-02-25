import { useState, useRef, useCallback } from 'react';
import { useOptimizationHistory } from '../hooks/useOptimizationHistory';
import type { OptimizationResult } from '../lib/types';
import { BayesianScatter } from './BayesianScatter';
import { BestResults } from './BestResults';
import { DateRangePicker } from './DateRangePicker';
import { Heatmap } from './Heatmap';
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel';
import { OptimizationTable } from './OptimizationTable';
import { Skeleton } from './Skeleton';

export function OptimizeDashboard() {
    const { history, activeId, refreshHistory, loadOptimization, refilterOptimization, deleteOptimization } =
        useOptimizationHistory();

    const [data, setData] = useState<OptimizationResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [filterLoading, setFilterLoading] = useState(false);
    const [filterStart, setFilterStart] = useState('');
    const [filterEnd, setFilterEnd] = useState('');
    const [originalDateStart, setOriginalDateStart] = useState('');
    const [originalDateEnd, setOriginalDateEnd] = useState('');
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const handleLoad = async (id: string) => {
        setLoading(true);
        const result = await loadOptimization(id);
        if (result) {
            setData(result);
            setFilterStart(result.date_start || '');
            setFilterEnd(result.date_end || '');
            setOriginalDateStart(result.date_start || '');
            setOriginalDateEnd(result.date_end || '');
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
            const result = await refilterOptimization(
                activeId,
                isFullRange ? undefined : start,
                isFullRange ? undefined : end,
            );
            if (result) setData(result);
            setFilterLoading(false);
        }, 300);
    }, [activeId, originalDateStart, originalDateEnd, refilterOptimization]);

    const handleDateReset = useCallback(() => {
        handleDateChange(originalDateStart, originalDateEnd);
    }, [originalDateStart, originalDateEnd, handleDateChange]);

    const sweptParamKeys = data?.swept_params ? Object.keys(data.swept_params) : [];

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-xl font-semibold text-text-primary">
                    Parameter Optimizations
                </h1>
                {data && !loading && (
                    <p className="mt-0.5 text-sm text-text-muted">
                        {data.total_combinations} {data.run_type === 'bayesian' ? 'trials' : 'combinations'} &middot;{' '}
                        {sweptParamKeys.join(', ')}
                    </p>
                )}
                {loading && <Skeleton className="mt-1.5 h-4 w-48 rounded" />}
            </div>

            {/* History table — full width */}
            <OptimizationHistoryPanel
                history={history}
                activeId={activeId}
                onLoad={handleLoad}
                onDelete={deleteOptimization}
                onRefresh={refreshHistory}
            />

            {/* Results area */}
            {loading && <OptimizeLoadingSkeleton />}

            {!loading && data && (
                <div className="mt-4 space-y-4">
                    {data.run_type !== 'bayesian' && (
                        <DateRangePicker
                            startDate={filterStart}
                            endDate={filterEnd}
                            originalStart={originalDateStart}
                            originalEnd={originalDateEnd}
                            onChange={handleDateChange}
                            onReset={handleDateReset}
                            loading={filterLoading}
                            disabled={!data.has_trade_data}
                        />
                    )}
                    <BestResults
                        bestBySharpe={data.best_by_sharpe}
                        bestByPnl={data.best_by_pnl}
                        bestByPf={data.best_by_profit_factor}
                        bestByCalmar={data.best_by_calmar}
                        sweptParams={sweptParamKeys}
                    />
                    {data.run_type === 'bayesian' ? (
                        <BayesianScatter data={data} />
                    ) : (
                        data.swept_params &&
                        Object.keys(data.swept_params).length >= 1 && (
                            <Heatmap
                                results={data.all_results}
                                sweptParams={data.swept_params}
                            />
                        )
                    )}
                    <OptimizationTable
                        results={data.all_results}
                        sweptParams={sweptParamKeys}
                    />
                </div>
            )}

            {!loading && !data && (
                <div className="flex h-[400px] items-center justify-center text-text-muted">
                    Select an optimization to view
                </div>
            )}
        </div>
    );
}

function OptimizeLoadingSkeleton() {
    return (
        <div className="space-y-4">
            {/* Best results */}
            <div className="grid gap-3 sm:grid-cols-4">
                {Array.from({ length: 4 }).map((_, i) => (
                    <Skeleton key={i} className="h-[120px] rounded-lg" />
                ))}
            </div>
            {/* Heatmap */}
            <Skeleton className="h-[300px] rounded-lg" />
            {/* Table */}
            <Skeleton className="h-[200px] rounded-lg" />
        </div>
    );
}
