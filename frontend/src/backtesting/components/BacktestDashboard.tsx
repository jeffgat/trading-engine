import { useCallback, useMemo, useState } from 'react';
import { useBacktestHistory } from "@/backtesting/hooks/useBacktestHistory";
import type { BacktestConfig, BacktestResult, MonteCarloResult } from "@/backtesting/lib/types";
import { filterTradesByDate } from "@/backtesting/lib/filterTrades";
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
import { Dialog, DialogContent } from "@/shared/ui/dialog";
import { ConfirmDeleteDialog } from './ConfirmDeleteDialog';
import { useRegimeReports } from "@/backtesting/hooks/useRegimeReports";

const SESSION_PREFIXES = ['ny', 'asia', 'ldn'] as const;

function detectSessionsFromConfig(config: BacktestConfig): string[] {
    const sessionLabels = {
        ny: "NY",
        asia: "Asia",
        ldn: "LDN",
    } as const;
    const sessions: string[] = [];
    for (const key of Object.keys(config)) {
        for (const prefix of SESSION_PREFIXES) {
            const label = sessionLabels[prefix];
            if (key.startsWith(`${prefix}_`) && !sessions.includes(label)) {
                sessions.push(label);
            }
        }
    }
    return sessions.length > 0 ? sessions : ["NY"];
}

export function BacktestDashboard() {
    const { history, activeId, refreshHistory, loadBacktest, deleteBacktest, starBacktest, hideBacktest, renameBacktest, bulkStarBacktests, bulkHideBacktests } =
        useBacktestHistory();
    const { createReport } = useRegimeReports();
    const [data, setData] = useState<BacktestResult | null>(null);
    const [loading, setLoading] = useState(false);
    const [regimeMethod, setRegimeMethod] = useState<"both" | "hmm" | "lstm">("both");
    const [regimeLoading, setRegimeLoading] = useState(false);
    const [regimeError, setRegimeError] = useState<string | null>(null);
    const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

    const activeItem = useMemo(() => history.find((h) => h.id === activeId), [history, activeId]);

    // Date filter state
    const [filterStart, setFilterStart] = useState('');
    const [filterEnd, setFilterEnd] = useState('');
    const [originalDateStart, setOriginalDateStart] = useState('');
    const [originalDateEnd, setOriginalDateEnd] = useState('');

    const [historyModalOpen, setHistoryModalOpen] = useState(false);

    // Monte Carlo state
    const [mcResult, setMcResult] = useState<MonteCarloResult | null>(null);
    const [mcLoading, setMcLoading] = useState(false);
    const [mcError, setMcError] = useState<string | null>(null);
    const [mcOpen, setMcOpen] = useState(false);
    const [mcMethod, setMcMethod] = useState<"bootstrap" | "shuffle">("bootstrap");
    const [mcSims, setMcSims] = useState(1000);

    // Save as config state
    const [saveConfigLoading, setSaveConfigLoading] = useState(false);
    const [saveConfigMsg, setSaveConfigMsg] = useState<string | null>(null);

    const handleSaveAsConfig = useCallback(async () => {
        if (!data?.config) return;
        setSaveConfigLoading(true);
        setSaveConfigMsg(null);
        try {
            const config: BacktestConfig = {
                ...data.config,
                ...(activeItem?.date_start ? { date_start: activeItem.date_start } : {}),
                ...(activeItem?.date_end ? { date_end: activeItem.date_end } : {}),
                ...(data.id ? { source_backtest_id: data.id } : {}),
                ...(data.name ? { source_backtest_name: data.name } : {}),
            };
            const instrument = (config.instrument as string) ?? "NQ";
            const sessions = detectSessionsFromConfig(config);
            const strategy = (config.strategy as string) ?? "continuation";
            const name = data.name || `${instrument} ${sessions.join("+")} ${strategy}`;
            const res = await fetch("/bt-api/configs", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name, notes: data.notes ?? null, instrument, sessions, strategy, config }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            setSaveConfigMsg("Saved to Configs");
            setTimeout(() => setSaveConfigMsg(null), 3000);
        } catch (e) {
            setSaveConfigMsg(`Failed: ${(e as Error).message}`);
        } finally {
            setSaveConfigLoading(false);
        }
    }, [activeItem?.date_end, activeItem?.date_start, data]);

    const handleLoad = async (id: string) => {
        setLoading(true);
        setMcResult(null);
        setMcError(null);
        setMcOpen(false);
        const result = await loadBacktest(id);
        if (result) {
            setData(result);
            // Derive date range from trades (most complete source)
            const r = result as any;
            const dates = r.trades?.length
                ? [r.trades[0].date, r.trades[r.trades.length - 1].date]
                : r.equity_curve?.length
                    ? [r.equity_curve[0].date, r.equity_curve[r.equity_curve.length - 1].date]
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

    // Client-side filtered view of trades, equity curve, and summary
    const isFiltered = filterStart !== originalDateStart || filterEnd !== originalDateEnd;
    const filtered = useMemo(() => {
        if (!data?.trades?.length || !isFiltered) return null;
        return filterTradesByDate(data.trades, filterStart, filterEnd);
    }, [data, isFiltered, filterStart, filterEnd]);

    const displayTrades = filtered?.trades ?? data?.trades ?? [];
    const displayEquity = filtered?.equityCurve ?? data?.equity_curve ?? [];
    const displaySummary = filtered?.summary ?? data?.summary;

    const handleDateChange = useCallback((start: string, end: string) => {
        setFilterStart(start);
        setFilterEnd(end);
    }, []);

    const handleDateReset = useCallback(() => {
        setFilterStart(originalDateStart);
        setFilterEnd(originalDateEnd);
    }, [originalDateStart, originalDateEnd]);

    const runMonteCarlo = useCallback(async () => {
        if (!activeId) return;
        setMcLoading(true);
        setMcError(null);
        try {
            const res = await fetch("/bt-api/monte-carlo", {
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

    const handleCreateRegimeReport = useCallback(async () => {
        if (!activeId) return;
        setRegimeLoading(true);
        setRegimeError(null);
        try {
            await createReport(activeId, regimeMethod);
        } catch (e) {
            setRegimeError((e as Error).message);
        } finally {
            setRegimeLoading(false);
        }
    }, [activeId, createReport, regimeMethod]);

    return (
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            {/* Header */}
            <div className="mb-6">
                <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                        <h1 className="text-xl font-semibold text-text-primary">Backtests</h1>
                        {data?.id && !loading && (
                            <div className="mt-0.5 flex items-center gap-1.5 text-xs text-text-muted font-mono">
                                {data.id}
                            </div>
                        )}
                    </div>
                    <div className="flex flex-wrap items-center justify-end gap-1.5">
                        {/* Row actions */}
                        <button
                            onClick={() => activeId && starBacktest(activeId)}
                            disabled={!activeId}
                            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                                activeItem?.starred
                                    ? 'border-yellow-500/30 bg-yellow-500/10 text-yellow-400 hover:bg-yellow-500/20'
                                    : 'border-border bg-bg-secondary text-text-secondary hover:bg-bg-card-hover'
                            }`}
                        >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill={activeItem?.starred ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1">
                                <path d="M8 1.5l2.1 4.3 4.7.7-3.4 3.3.8 4.7L8 12.2 3.8 14.5l.8-4.7L1.2 6.5l4.7-.7z" />
                            </svg>
                            {activeItem?.starred ? 'Starred' : 'Star'}
                        </button>
                        <button
                            onClick={() => activeId && hideBacktest(activeId)}
                            disabled={!activeId}
                            className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs font-medium transition-colors disabled:opacity-40 ${
                                activeItem?.hidden
                                    ? 'border-text-muted/30 bg-text-muted/10 text-text-secondary hover:bg-text-muted/20'
                                    : 'border-border bg-bg-secondary text-text-secondary hover:bg-bg-card-hover'
                            }`}
                        >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                {activeItem?.hidden ? (
                                    <><path d="M2 2l12 12" /><path d="M6.5 6.5a2 2 0 002.8 2.8M4 4.5C2.8 5.6 1.8 7.2 1 8c1 1.5 3.5 5 7 5 1 0 1.9-.2 2.7-.6M9.5 4.2c.5.2 1 .5 1.5.8 1.5 1 3 3 4 3-1-1.5-3.5-5-7-5-.3 0-.7 0-1 .1" /></>
                                ) : (
                                    <><path d="M1 8s2.5-5 7-5 7 5 7 5-2.5 5-7 5-7-5-7-5z" /><circle cx="8" cy="8" r="2" /></>
                                )}
                            </svg>
                            {activeItem?.hidden ? 'Hidden' : 'Hide'}
                        </button>
                        <button
                            onClick={() => setDeleteConfirmOpen(true)}
                            disabled={!activeId}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:border-red-500/30 hover:bg-red-500/10 hover:text-red-400 disabled:opacity-40"
                        >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M2 4h12M5.5 4V2.5h5V4M6 7v4.5M10 7v4.5M3.5 4l.5 9.5h8l.5-9.5" />
                            </svg>
                            Delete
                        </button>

                        {/* Divider */}
                        <div className="mx-1 h-5 w-px bg-border" />

                        {/* Config & report actions */}
                        {saveConfigMsg && (
                            <span className={`text-xs ${saveConfigMsg.startsWith("Failed") ? "text-loss" : "text-profit"}`}>
                                {saveConfigMsg}
                            </span>
                        )}
                        <button
                            onClick={handleSaveAsConfig}
                            disabled={!data || saveConfigLoading}
                            className="inline-flex items-center gap-1.5 rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs font-medium text-text-secondary transition-colors hover:bg-bg-card-hover disabled:opacity-40"
                        >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M12.5 14.5h-9a1 1 0 01-1-1v-11a1 1 0 011-1h7l3 3v9a1 1 0 01-1 1z" />
                                <path d="M10.5 1.5v3h3M5.5 9.5h5M5.5 12h3" />
                            </svg>
                            {saveConfigLoading ? "Saving..." : "Save Config"}
                        </button>
                        <select
                            value={regimeMethod}
                            onChange={(e) => setRegimeMethod(e.target.value as "both" | "hmm" | "lstm")}
                            className="rounded-md border border-border bg-bg-secondary px-2.5 py-1.5 text-xs text-text-primary outline-none focus:border-accent"
                        >
                            <option value="both">HMM + LSTM</option>
                            <option value="hmm">HMM only</option>
                            <option value="lstm">LSTM only</option>
                        </select>
                        <button
                            onClick={handleCreateRegimeReport}
                            disabled={!activeId || regimeLoading}
                            className="inline-flex items-center gap-1.5 rounded-md border border-accent bg-accent/10 px-2.5 py-1.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20 disabled:opacity-40"
                        >
                            <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
                                <path d="M2 2.5h12M2 5.5h8M2 8.5h10M2 11.5h6M2 14.5h9" />
                            </svg>
                            {regimeLoading ? "Creating..." : "Regime Report"}
                        </button>
                    </div>
                </div>
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
                {regimeError && (
                    <div className="mt-2 rounded-md border border-loss/30 bg-loss/5 px-3 py-2 text-xs text-loss">
                        {regimeError}
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
                onRename={renameBacktest}
                onBulkStar={bulkStarBacktests}
                onBulkHide={bulkHideBacktests}
                onExpand={() => setHistoryModalOpen(true)}
            />

            {/* History expanded modal */}
            <Dialog open={historyModalOpen} onOpenChange={setHistoryModalOpen}>
                <DialogContent className="max-w-7xl p-0">
                    <BacktestHistoryPanel
                        history={history}
                        activeId={activeId}
                        onLoad={(id) => { handleLoad(id); setHistoryModalOpen(false); }}
                        onDelete={deleteBacktest}
                        onRefresh={refreshHistory}
                        onStar={starBacktest}
                        onHide={hideBacktest}
                        onRename={renameBacktest}
                        onBulkStar={bulkStarBacktests}
                        onBulkHide={bulkHideBacktests}
                        isModal
                    />
                </DialogContent>
            </Dialog>

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
                        loading={false}
                        disabled={!data.trades?.length}
                    />
                    <VariablesTested config={data.config} />
                    <ConfigBar config={data.config} />
                    {displaySummary && <StatBar summary={displaySummary} trades={displayTrades} riskUsd={data.config.risk_usd ?? 5000} />}
                    <EquityChart data={displayEquity} trades={displayTrades} riskUsd={data.config.risk_usd ?? 5000} />

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

                    <TradesTable trades={displayTrades} riskUsd={data.config.risk_usd ?? 5000} instrument={data.config.instrument ?? "NQ"} />
                </div>
            )}

            {!loading && !data && (
                <div className="flex h-[400px] items-center justify-center text-text-muted">
                    Select a backtest to view
                </div>
            )}

            <ConfirmDeleteDialog
                open={deleteConfirmOpen}
                onOpenChange={setDeleteConfirmOpen}
                onConfirm={() => {
                    if (activeId) {
                        deleteBacktest(activeId);
                        setData(null);
                    }
                }}
                title="Delete this backtest?"
                description="The saved backtest result will be permanently removed."
            />
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
