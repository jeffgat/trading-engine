import { useState } from 'react';
import { useOptimizationHistory } from '../hooks/useOptimizationHistory';
import type { OptimizationResult } from '../lib/types';
import { BestResults } from './BestResults';
import { Heatmap } from './Heatmap';
import { OptimizationHistoryPanel } from './OptimizationHistoryPanel';
import { OptimizationTable } from './OptimizationTable';
import { Skeleton } from './Skeleton';

export function OptimizeDashboard() {
    const { history, activeId, refreshHistory, loadOptimization, deleteOptimization } =
        useOptimizationHistory();

    const [data, setData] = useState<OptimizationResult | null>(null);
    const [loading, setLoading] = useState(false);

    const handleLoad = async (id: string) => {
        setLoading(true);
        const result = await loadOptimization(id);
        if (result) setData(result);
        setLoading(false);
    };

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
                        {data.total_combinations} combinations &middot;{' '}
                        {sweptParamKeys.join(', ')}
                    </p>
                )}
                {loading && <Skeleton className="mt-1.5 h-4 w-48 rounded" />}
            </div>

            {/* Main content */}
            <div className="flex gap-4">
                {/* History panel */}
                <div className="w-72 shrink-0">
                    <OptimizationHistoryPanel
                        history={history}
                        activeId={activeId}
                        onLoad={handleLoad}
                        onDelete={deleteOptimization}
                        onRefresh={refreshHistory}
                    />
                </div>

                {/* Results area */}
                <div className="min-w-0 flex-1">
                    {loading && <OptimizeLoadingSkeleton />}

                    {!loading && data && (
                        <div className="space-y-4">
                            <BestResults
                                bestBySharpe={data.best_by_sharpe}
                                bestByPnl={data.best_by_pnl}
                                bestByPf={data.best_by_profit_factor}
                                sweptParams={sweptParamKeys}
                            />
                            {data.swept_params &&
                                Object.keys(data.swept_params).length >= 1 && (
                                    <Heatmap
                                        results={data.all_results}
                                        sweptParams={data.swept_params}
                                    />
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
            </div>
        </div>
    );
}

function OptimizeLoadingSkeleton() {
    return (
        <div className="space-y-4">
            {/* Best results */}
            <div className="grid gap-3 sm:grid-cols-3">
                {Array.from({ length: 3 }).map((_, i) => (
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
