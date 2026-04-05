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
            <header className="sticky top-0 z-10 border-b border-border bg-bg-secondary/80 backdrop-blur-sm">
                {/* Tab nav */}
                <div className="mx-auto max-w-7xl px-4 sm:px-6 flex items-center justify-between">
                    <nav className="flex gap-1 -mb-px">
                        {TABS.map(({ key, label }) => (
                            <button
                                key={key}
                                onClick={() => setActiveTab(key)}
                                className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                                    activeTab === key
                                        ? 'border-accent text-text-primary'
                                        : 'border-transparent text-text-muted hover:text-text-secondary hover:border-border'
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
