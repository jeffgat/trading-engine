import { ConnectionStatus, type ConnectionState } from '@/execution/components/ConnectionStatus';
import { useConfig } from '@/execution/hooks/useConfig';
import { useLiveTrades } from '@/execution/hooks/useLiveTrades';
import { useMainLogs } from '@/execution/hooks/useMainLogs';
import { useStatus } from '@/execution/hooks/useStatus';
import { useTradeLogs } from '@/execution/hooks/useTradeLogs';
import { useWebSocket } from '@/execution/hooks/useWebSocket';
import { ExecutionTabSkeleton } from '@/shared/ui/page-skeletons';
import { lazy, Suspense, useMemo, useState } from 'react';

export type ExecutionTab = 'status' | 'trades' | 'performance' | 'logs' | 'config';

const ConfigView = lazy(() =>
    import('@/execution/components/ConfigView').then((module) => ({ default: module.ConfigView })),
);
const LogViewer = lazy(() =>
    import('@/execution/components/LogViewer').then((module) => ({ default: module.LogViewer })),
);
const PerformanceView = lazy(() =>
    import('@/execution/components/PerformanceView').then((module) => ({ default: module.PerformanceView })),
);
const StatusPanel = lazy(() =>
    import('@/execution/components/StatusPanel').then((module) => ({ default: module.StatusPanel })),
);
const TradeFeed = lazy(() =>
    import('@/execution/components/TradeFeed').then((module) => ({ default: module.TradeFeed })),
);

const TABS: { key: ExecutionTab; label: string }[] = [
    { key: 'status', label: 'Status' },
    { key: 'config', label: 'Config' },
    { key: 'trades', label: 'Trades' },
    { key: 'performance', label: 'Performance' },
    { key: 'logs', label: 'Logs' },
];

interface ExecutionAppProps {
    forcedTab?: ExecutionTab;
    hideTabNav?: boolean;
    readOnly?: boolean;
}

export function ExecutionApp({ forcedTab, hideTabNav = false, readOnly = false }: ExecutionAppProps) {
    const [localActiveTab, setLocalActiveTab] = useState<ExecutionTab>('status');
    const activeTab = forcedTab ?? localActiveTab;
    const [activeConfig, setActiveConfig] = useState<string>('');
    const { connected, status: socketStatus, subscribe } = useWebSocket();
    const {
        uptime,
        loading: statusLoading,
        pollingHealthy,
        configEngines,
        engines,
    } = useStatus(subscribe, connected);
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
    const connectionState: ConnectionState = connected
        ? 'connected'
        : pollingHealthy
            ? 'connected'
            : socketStatus;

    return (
        <>
            {/* Execution header */}
            <header className="sticky top-0 z-10 border-b border-border bg-bg-secondary/70 backdrop-blur-sm">
                {/* Tab nav */}
                <div className="mx-auto flex max-w-7xl items-center justify-between gap-4 px-4 py-2 sm:px-6">
                    {hideTabNav ? <div /> : (
                        <nav className="flex gap-1 overflow-x-auto rounded-lg border border-border bg-bg-primary/70 p-1">
                            {TABS.map(({ key, label }) => (
                                <button
                                    key={key}
                                    onClick={() => setLocalActiveTab(key)}
                                    className={`min-h-9 shrink-0 rounded-md px-4 font-mono text-sm font-semibold lowercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-profit/40 ${
                                        activeTab === key
                                            ? 'bg-profit text-bg-primary shadow-[0_0_18px_rgba(114,242,95,0.18)]'
                                            : 'text-text-secondary hover:bg-bg-card-hover hover:text-foreground'
                                    }`}>
                                    {label}
                                </button>
                            ))}
                        </nav>
                    )}
                    <ConnectionStatus state={connectionState} />
                </div>

            </header>

            {/* Content */}
            <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
                <Suspense fallback={<ExecutionTabSkeleton tab={activeTab} />}>
                    {activeTab === 'status' && (
                        <StatusPanel
                            configEngines={configEngines}
                            engines={engines}
                            uptime={uptime}
                            loading={statusLoading}
                            activeConfig={activeConfig}
                            setActiveConfig={setActiveConfig}
                            config={config}
                            onPause={readOnly ? undefined : pauseEngine}
                            onResume={readOnly ? undefined : resumeEngine}
                        />
                    )}
                    {activeTab === 'trades' && (
                        <TradeFeedTab
                            subscribe={subscribe}
                            activeConfig={activeConfig}
                            config={config}
                        />
                    )}
                    {activeTab === 'logs' && (
                        <LogViewerTab
                            subscribe={subscribe}
                            activeConfig={activeConfig}
                        />
                    )}
                    {activeTab === 'performance' && (
                        <PerformanceTab
                            subscribe={subscribe}
                            config={config}
                            activeConfig={activeConfig}
                            configNames={configNames}
                            setActiveConfig={setActiveConfig}
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
                </Suspense>
            </main>
        </>
    );
}

function TradeFeedTab({
    subscribe,
    activeConfig,
    config,
}: {
    subscribe: (type: string, cb: (data: unknown) => void) => () => void;
    activeConfig: string;
    config: ReturnType<typeof useConfig>['config'];
}) {
    const tradeLogs = useTradeLogs(subscribe);

    return (
        <TradeFeed
            entries={tradeLogs.entries}
            total={tradeLogs.total}
            loading={tradeLogs.loading}
            loadMore={tradeLogs.loadMore}
            activeConfig={activeConfig}
            config={config}
        />
    );
}

function LogViewerTab({
    subscribe,
    activeConfig,
}: {
    subscribe: (type: string, cb: (data: unknown) => void) => () => void;
    activeConfig: string;
}) {
    const mainLogs = useMainLogs(subscribe);
    const tradeLogs = useTradeLogs(subscribe);

    return (
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
    );
}

function PerformanceTab({
    subscribe,
    config,
    activeConfig,
    configNames,
    setActiveConfig,
}: {
    subscribe: (type: string, cb: (data: unknown) => void) => () => void;
    config: ReturnType<typeof useConfig>['config'];
    activeConfig: string;
    configNames: string[];
    setActiveConfig: (config: string) => void;
}) {
    const tradeLogs = useTradeLogs(subscribe);
    const liveTrades = useLiveTrades();

    return (
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
    );
}
