import { useState } from 'react';
import { useBacktestHistory } from '../hooks/useBacktestHistory';
import type { BacktestResult } from '../lib/types';
import { EquityChart } from './EquityChart';
import { BacktestHistoryPanel } from './BacktestHistoryPanel';
import { Skeleton } from './Skeleton';
import { ConfigBar } from './ConfigBar';
import { StatBar } from './StatBar';
import { TradesTable } from './TradesTable';

export function BacktestDashboard() {
    const { history, activeId, refreshHistory, loadBacktest, deleteBacktest } =
        useBacktestHistory();
    const [data, setData] = useState<BacktestResult | null>(null);
    const [loading, setLoading] = useState(false);

    const handleLoad = async (id: string) => {
        setLoading(true);
        const result = await loadBacktest(id);
        if (result) setData(result);
        setLoading(false);
    };

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-xl font-semibold text-text-primary">Backtests</h1>
                {loading && <Skeleton className="mt-1.5 h-4 w-48 rounded" />}
                {data?.config?.instrument && !loading && (
                    <p className="mt-0.5 text-sm text-text-muted">
                        {data.name && (
                            <span className="font-medium text-text-secondary">
                                {data.name} &middot;{' '}
                            </span>
                        )}
                        {data.config.instrument} &middot; R:R {data.config.rr} &middot;
                        Risk ${data.config.risk_usd?.toLocaleString()}
                    </p>
                )}
            </div>

            {/* History table — full width */}
            <BacktestHistoryPanel
                history={history}
                activeId={activeId}
                onLoad={handleLoad}
                onDelete={deleteBacktest}
                onRefresh={refreshHistory}
            />

            {/* Stats + Chart + Trades */}
            {loading && <LoadingSkeleton />}

            {!loading && data && (
                <div className="mt-4 space-y-4">
                    <ConfigBar config={data.config} />
                    <StatBar summary={data.summary} trades={data.trades} riskUsd={data.config.risk_usd ?? 50000} />
                    <EquityChart data={data.equity_curve} riskUsd={data.config.risk_usd ?? 50000} />
                    <TradesTable trades={data.trades} riskUsd={data.config.risk_usd ?? 50000} />
                </div>
            )}

            {!loading && !data && (
                <div className="flex h-[400px] items-center justify-center text-text-muted">
                    Select a backtest to view
                </div>
            )}
        </div>
    );
}

function LoadingSkeleton() {
    return (
        <div className="space-y-4">
            {/* Stat cards row 1 */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-[88px] rounded-lg" />
                ))}
            </div>
            {/* Stat cards row 2 */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
                {Array.from({ length: 5 }).map((_, i) => (
                    <Skeleton key={i} className="h-[88px] rounded-lg" />
                ))}
            </div>
            {/* Chart */}
            <Skeleton className="h-[430px] rounded-lg" />
            {/* Table */}
            <Skeleton className="h-[200px] rounded-lg" />
        </div>
    );
}
