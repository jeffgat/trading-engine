import { useCallback, useRef, useState } from 'react';
import { useBacktestHistory } from '../hooks/useBacktestHistory';
import type { BacktestResult, MonteCarloResult } from '../lib/types';
import { BacktestHistoryPanel } from './BacktestHistoryPanel';
import { ConfigBar } from './ConfigBar';
import { DateRangePicker } from './DateRangePicker';
import { EquityChart } from './EquityChart';
import { MonteCarloChart } from './MonteCarloChart';
import { Skeleton } from './Skeleton';
import { StatBar } from './StatBar';
import { StrategyTag } from './StrategyTag';
import { TradesTable } from './TradesTable';
import { VariablesTested } from './VariablesTested';

export function BacktestDashboard() {
    const { history, activeId, refreshHistory, loadBacktest, refilterBacktest, deleteBacktest, starBacktest, hideBacktest } =
        useBacktestHistory();
    const [data, setData] = useState<BacktestResult | null>(null);
    const [loading, setLoading] = useState(false);

    // Date filter state
    const [filterStart, setFilterStart] = useState('');
    const [filterEnd, setFilterEnd] = useState('');
    const [originalDateStart, setOriginalDateStart] = useState('');
    const [originalDateEnd, setOriginalDateEnd] = useState('');
    const [filterLoading, setFilterLoading] = useState(false);
    const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    // Monte Carlo state
    const [mcResult, setMcResult] = useState<MonteCarloResult | null>(null);
    const [mcLoading, setMcLoading] = useState(false);
    const [mcError, setMcError] = useState<string | null>(null);
    const [mcOpen, setMcOpen] = useState(false);
    const [mcMethod, setMcMethod] = useState<"bootstrap" | "shuffle">("bootstrap");
    const [mcSims, setMcSims] = useState(1000);

    const handleLoad = async (id: string) => {
        setLoading(true);
        setMcResult(null);
        setMcError(null);
        setMcOpen(false);
        const result = await loadBacktest(id);
        if (result) {
            setData(result);
            // Derive date range from backend response, falling back to equity curve / trades
            const r = result as any;
            const dates = r.equity_curve?.length
                ? [r.equity_curve[0].date, r.equity_curve[r.equity_curve.length - 1].date]
                : r.trades?.length
                    ? [r.trades[0].date, r.trades[r.trades.length - 1].date]
                    : ['', ''];
            const dateStart = r.date_start || dates[0] || '';
            const dateEnd = r.date_end || dates[1] || '';
            setFilterStart(dateStart);
            setFilterEnd(dateEnd);
            setOriginalDateStart(dateStart);
            setOriginalDateEnd(dateEnd);
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

    const runMonteCarlo = useCallback(async () => {
        if (!activeId) return;
        setMcLoading(true);
        setMcError(null);
        try {
            const res = await fetch("/api/monte-carlo", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    result_id: activeId,
                    method: mcMethod,
                    n_simulations: mcSims,
                }),
            });
            if (!res.ok) {
                const err = await res.json();
                throw new Error(err.detail ?? "Simulation failed");
            }
            const result = await res.json();
            setMcResult(result);
            setMcOpen(true);
        } catch (e) {
            setMcError((e as Error).message);
        } finally {
            setMcLoading(false);
        }
    }, [activeId, mcMethod, mcSims]);

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Header */}
            <div className="mb-6">
                <h1 className="text-xl font-semibold text-text-primary">Backtests</h1>
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

            {/* History table — full width */}
            <BacktestHistoryPanel
                history={history}
                activeId={activeId}
                onLoad={handleLoad}
                onDelete={deleteBacktest}
                onRefresh={refreshHistory}
                onStar={starBacktest}
                onHide={hideBacktest}
            />

            {/* Stats + Chart + Trades */}
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

                    {/* Monte Carlo section */}
                    <MonteCarloSection
                        mcResult={mcResult}
                        mcLoading={mcLoading}
                        mcError={mcError}
                        mcOpen={mcOpen}
                        mcMethod={mcMethod}
                        mcSims={mcSims}
                        onToggle={() => setMcOpen(!mcOpen)}
                        onMethodChange={setMcMethod}
                        onSimsChange={setMcSims}
                        onRun={runMonteCarlo}
                    />

                    <TradesTable trades={data.trades} riskUsd={data.config.risk_usd ?? 50000} instrument={data.config.instrument ?? "NQ"} />
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

function MonteCarloSection({
    mcResult,
    mcLoading,
    mcError,
    mcOpen,
    mcMethod,
    mcSims,
    onToggle,
    onMethodChange,
    onSimsChange,
    onRun,
}: {
    mcResult: MonteCarloResult | null;
    mcLoading: boolean;
    mcError: string | null;
    mcOpen: boolean;
    mcMethod: "bootstrap" | "shuffle";
    mcSims: number;
    onToggle: () => void;
    onMethodChange: (m: "bootstrap" | "shuffle") => void;
    onSimsChange: (n: number) => void;
    onRun: () => void;
}) {
    return (
        <div className="rounded-lg border border-border bg-bg-card">
            {/* Header / trigger */}
            <button
                onClick={onToggle}
                className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-bg-card-hover"
            >
                <div className="flex items-center gap-2">
                    <svg
                        className={`h-3.5 w-3.5 text-text-muted transition-transform ${mcOpen ? "rotate-90" : ""}`}
                        viewBox="0 0 16 16"
                        fill="currentColor"
                    >
                        <path d="M6.22 3.22a.75.75 0 011.06 0l4.25 4.25a.75.75 0 010 1.06l-4.25 4.25a.75.75 0 01-1.06-1.06L9.94 8 6.22 4.28a.75.75 0 010-1.06z" />
                    </svg>
                    <span className="text-sm font-medium text-text-secondary">
                        Monte Carlo Simulation
                    </span>
                    {mcResult && (
                        <span className="rounded-md bg-bg-secondary px-2 py-0.5 font-mono text-[10px] text-text-muted">
                            {mcResult.n_simulations.toLocaleString()} sims &middot; {mcResult.method}
                        </span>
                    )}
                </div>
            </button>

            {mcOpen && (
                <div className="border-t border-border px-4 pb-4 pt-3">
                    {/* Controls */}
                    <div className="mb-4 flex items-center gap-3">
                        <select
                            value={mcMethod}
                            onChange={(e) => onMethodChange(e.target.value as "bootstrap" | "shuffle")}
                            className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-accent"
                        >
                            <option value="bootstrap">Bootstrap (with replacement)</option>
                            <option value="shuffle">Shuffle (permutation)</option>
                        </select>
                        <input
                            type="number"
                            value={mcSims}
                            onChange={(e) => onSimsChange(Math.max(100, parseInt(e.target.value) || 1000))}
                            min={100}
                            max={10000}
                            step={100}
                            className="w-24 rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 font-mono text-xs text-text-primary outline-none focus:border-accent"
                        />
                        <span className="text-[10px] text-text-muted">simulations</span>
                        <button
                            onClick={onRun}
                            disabled={mcLoading}
                            className="rounded-md border border-accent bg-accent/10 px-3 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-50"
                        >
                            {mcLoading ? "Running..." : "Run"}
                        </button>
                    </div>

                    {mcError && (
                        <div className="mb-4 rounded-md border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
                            {mcError}
                        </div>
                    )}

                    {mcLoading && (
                        <div className="space-y-4">
                            <div className="grid grid-cols-4 gap-3">
                                {Array.from({ length: 4 }).map((_, i) => (
                                    <Skeleton key={i} className="h-[88px] rounded-lg" />
                                ))}
                            </div>
                            <Skeleton className="h-[360px] rounded-lg" />
                        </div>
                    )}

                    {mcResult && !mcLoading && <MonteCarloChart data={mcResult} />}
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
