import { AccountsView } from "@/execution/components/AccountsView";
import { ConfigView } from "@/execution/components/ConfigView";
import { ConnectionStatus } from "@/execution/components/ConnectionStatus";
import { LogViewer } from "@/execution/components/LogViewer";
import { PerformanceView } from "@/execution/components/PerformanceView";
import { StatusPanel } from "@/execution/components/StatusPanel";
import { TradeFeed } from "@/execution/components/TradeFeed";
import { Badge } from "@/shared/ui/badge";
import { CONFIG_COLORS } from "@/execution/lib/constants";
import { useConfig } from "@/execution/hooks/useConfig";
import { useMainLogs } from "@/execution/hooks/useMainLogs";
import { useStatus } from "@/execution/hooks/useStatus";
import { useTradeLogs } from "@/execution/hooks/useTradeLogs";
import { useWebSocket } from "@/execution/hooks/useWebSocket";
import { useMemo, useState } from "react";

type Tab = "status" | "trades" | "performance" | "logs" | "config" | "accounts";

const TABS: { key: Tab; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "trades", label: "Trades" },
  { key: "performance", label: "Performance" },
  { key: "logs", label: "Logs" },
  { key: "config", label: "Config" },
  { key: "accounts", label: "Accounts" },
];

export function ExecutionApp() {
  const [activeTab, setActiveTab] = useState<Tab>("status");
  const [activeConfig, setActiveConfig] = useState<string>("ALL");
  const { connected, subscribe } = useWebSocket();
  const { status, uptime, loading: statusLoading, configEngines, engines } = useStatus(subscribe);
  const tradeLogs = useTradeLogs(subscribe);
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
  } = useConfig(subscribe);

  const mode = status?.mode ?? "\u2014";
  const isLive = mode === "LIVE";

  // Derive config names from the status response
  const configNames = useMemo(() => {
    return Object.keys(configEngines).sort();
  }, [configEngines]);

  return (
    <>
      {/* Execution header */}
      <header className="sticky top-0 z-10 border-b border-border bg-bg-secondary/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
          <div className="flex items-center gap-4">
            <h1 className="text-lg font-semibold tracking-tight">
              ORB Trader
            </h1>
            <Badge
              variant="outline"
              className={`border-0 text-xs ${
                isLive
                  ? "bg-loss/20 text-loss"
                  : "bg-text-muted/20 text-text-muted"
              }`}
            >
              {mode}
            </Badge>
          </div>
          <ConnectionStatus connected={connected} />
        </div>

        {/* Tab nav */}
        <div className="mx-auto max-w-7xl px-4 sm:px-6">
          <nav className="flex gap-1 -mb-px">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                  activeTab === key
                    ? "border-accent text-text-primary"
                    : "border-transparent text-text-muted hover:text-text-secondary hover:border-border"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>

        {/* Config selector pills — hidden on config/accounts tabs */}
        {configNames.length > 0 && activeTab !== "config" && activeTab !== "accounts" && (
          <div className="mx-auto max-w-7xl px-4 sm:px-6 py-2">
            <div className="flex gap-1.5">
              <button
                onClick={() => setActiveConfig("ALL")}
                className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                  activeConfig === "ALL"
                    ? "bg-text-muted/20 text-text-primary border-text-muted/40"
                    : "border-border text-text-muted hover:text-text-secondary hover:border-text-muted/40"
                }`}
              >
                ALL
              </button>
              {configNames.map((name) => {
                const isActive = activeConfig === name;
                const colorClasses = CONFIG_COLORS[name] ?? "bg-text-muted/20 text-text-muted border-text-muted/30";
                return (
                  <button
                    key={name}
                    onClick={() => setActiveConfig(name)}
                    className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                      isActive
                        ? colorClasses
                        : "border-border text-text-muted hover:text-text-secondary hover:border-text-muted/40"
                    }`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </div>
        )}
      </header>

      {/* Content */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {activeTab === "status" && (
          <StatusPanel
            configEngines={configEngines}
            engines={engines}
            uptime={uptime}
            loading={statusLoading}
            activeConfig={activeConfig}
          />
        )}
        {activeTab === "trades" && (
          <TradeFeed
            entries={tradeLogs.entries}
            total={tradeLogs.total}
            loading={tradeLogs.loading}
            loadMore={tradeLogs.loadMore}
            activeConfig={activeConfig}
          />
        )}
        {activeTab === "logs" && (
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
        {activeTab === "performance" && (
          <PerformanceView
            entries={tradeLogs.entries}
            loading={tradeLogs.loading}
            config={config}
            activeConfig={activeConfig}
          />
        )}
        {activeTab === "config" && (
          <ConfigView
            config={config}
            loading={configLoading}
            saving={configSaving}
            error={configError}
            onUpdateSession={updateSession}
            onResetSession={resetSession}
            onUpdateWebhooks={updateWebhooks}
            execConfigs={execConfigs}
          />
        )}
        {activeTab === "accounts" && (
          <AccountsView
            execConfigs={execConfigs}
            onPause={pauseWebhook}
            onResume={resumeWebhook}
            onUpdateMultiplier={updateWebhookMultiplier}
            onFlatten={flattenWebhook}
            onUpdateWebhooks={updateWebhooks}
          />
        )}
      </main>
    </>
  );
}
