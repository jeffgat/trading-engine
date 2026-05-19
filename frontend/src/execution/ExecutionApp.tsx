import { ConfigView } from '@/execution/components/ConfigView';
import { ConnectionStatus } from '@/execution/components/ConnectionStatus';
import { LogViewer } from '@/execution/components/LogViewer';
import { PerformanceView } from '@/execution/components/PerformanceView';
import { StatusPanel } from '@/execution/components/StatusPanel';
import { TradeFeed } from '@/execution/components/TradeFeed';
import { useConfig } from '@/execution/hooks/useConfig';
import { useMainLogs } from '@/execution/hooks/useMainLogs';
import { useStatus } from '@/execution/hooks/useStatus';
import { useTradeLogs } from '@/execution/hooks/useTradeLogs';
import { useLiveTrades } from '@/execution/hooks/useLiveTrades';
import { useWebSocket } from '@/execution/hooks/useWebSocket';
import { useMemo, useState } from 'react';

type Tab = 'status' | 'trades' | 'performance' | 'logs' | 'config';

const TABS: { key: Tab; label: string }[] = [
    { key: 'status', label: 'Status' },
    { key: 'config', label: 'Config' },
    { key: 'trades', label: 'Trades' },
    { key: 'performance', label: 'Performance' },
    { key: 'logs', label: 'Logs' },
];

export function ExecutionApp() {
    const [activeTab, setActiveTab] = useState<Tab>('status');
    const [activeConfig, setActiveConfig] = useState<string>('');
    const { connected, subscribe } = useWebSocket();
    const {
        uptime,
        loading: statusLoading,
        configEngines,
        engines,
    } = useStatus(subscribe);
    const tradeLogs = useTradeLogs(subscribe);
    const liveTrades = useLiveTrades();
    const mainLogs = useMainLogs(subscribe);
    const {
        config,
        loading: configLoading,
        saving: configSaving,
        error: configError,
        updateSession,
        resetSession,
        updateWebhooks,
        execConfigs,
        pauseWebhook,
        resumeWebhook,
        updateWebhookMultiplier,
        flattenWebhook,
        pauseEngine,
        resumeEngine,
        toggleEnabled,
    } = useConfig(subscribe);

    // Derive config names from the status response
    const configNames = useMemo(() => {
        return Object.keys(configEngines).sort();
    }, [configEngines]);

    return (
        <>
            {/* Execution header */}
            <header className="sticky top-0 z-10 border-b border-border bg-bg-secondary/70 backdrop-blur-sm">
                {/* Tab nav */}
                <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6">
                    <nav className="flex gap-1 overflow-x-auto rounded-lg border border-border bg-bg-primary/70 p-1">
                        {TABS.map(({ key, label }) => (
                            <button
                                key={key}
                                onClick={() => setActiveTab(key)}
                                className={`min-h-9 shrink-0 rounded-md px-4 font-mono text-sm font-semibold lowercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-profit/40 ${
                                    activeTab === key
                                        ? 'bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]'
                                        : 'text-text-secondary hover:bg-bg-card-hover hover:text-foreground'
                                }`}>
                                {label}
                            </button>
                        ))}
                    </nav>
                    <ConnectionStatus connected={connected} />
                </div>

            </header>

            {/* Content */}
            <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
                {activeTab === 'status' && (
                    <StatusPanel
                        configEngines={configEngines}
                        engines={engines}
                        uptime={uptime}
                        loading={statusLoading}
                        activeConfig={activeConfig}
                        setActiveConfig={setActiveConfig}
                        config={config}
                        onPause={pauseEngine}
                        onResume={resumeEngine}
                    />
                )}
                {activeTab === 'trades' && (
                    <TradeFeed
                        entries={tradeLogs.entries}
                        total={tradeLogs.total}
                        loading={tradeLogs.loading}
                        loadMore={tradeLogs.loadMore}
                        activeConfig={activeConfig}
                        config={config}
                    />
                )}
                {activeTab === 'logs' && (
                    <LogViewer
                        mainEntries={mainLogs.entries}
                        mainTotal={mainLogs.total}
                        mainLoading={mainLogs.loading}
                        loadMoreMain={mainLogs.loadMore}
                        tradeEntries={tradeLogs.entries}
                        tradeTotal={tradeLogs.total}
                        tradeLoading={tradeLogs.loading}
                        loadMoreTrade={tradeLogs.loadMore}
                        activeConfig={activeConfig}
                    />
                )}
                {activeTab === 'performance' && (
                    <PerformanceView
                        entries={tradeLogs.entries}
                        loading={tradeLogs.loading}
                        config={config}
                        activeConfig={activeConfig}
                        configNames={configNames}
                        setActiveConfig={setActiveConfig}
                        dbTrades={liveTrades.trades}
                        dbLoading={liveTrades.loading}
                    />
                )}
                {activeTab === 'config' && (
                    <ConfigView
                        config={config}
                        loading={configLoading}
                        saving={configSaving}
                        error={configError}
                        onUpdateSession={updateSession}
                        onResetSession={resetSession}
                        onUpdateWebhooks={updateWebhooks}
                        onToggleEnabled={toggleEnabled}
                        execConfigs={execConfigs}
                        onPauseWebhook={pauseWebhook}
                        onResumeWebhook={resumeWebhook}
                        onUpdateMultiplier={updateWebhookMultiplier}
                        onFlattenWebhook={flattenWebhook}
                    />
                )}
            </main>
        </>
    );
}
