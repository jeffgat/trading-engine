import { ConfigView } from "@/components/ConfigView";
import { ConnectionStatus } from "@/components/ConnectionStatus";
import { LogViewer } from "@/components/LogViewer";
import { PerformanceView } from "@/components/PerformanceView";
import { StatusPanel } from "@/components/StatusPanel";
import { TradeFeed } from "@/components/TradeFeed";
import { Badge } from "@/components/ui/badge";
import { useConfig } from "@/hooks/useConfig";
import { useMainLogs } from "@/hooks/useMainLogs";
import { useStatus } from "@/hooks/useStatus";
import { useTradeLogs } from "@/hooks/useTradeLogs";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useState } from "react";

type Tab = "status" | "trades" | "performance" | "logs" | "config";

const TABS: { key: Tab; label: string }[] = [
  { key: "status", label: "Status" },
  { key: "trades", label: "Trades" },
  { key: "performance", label: "Performance" },
  { key: "logs", label: "Logs" },
  { key: "config", label: "Config" },
];

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>("status");
  const { connected, subscribe } = useWebSocket();
  const { status, uptime, loading: statusLoading } = useStatus(subscribe);
  const tradeLogs = useTradeLogs(subscribe);
  const mainLogs = useMainLogs(subscribe);
  const { config, loading: configLoading } = useConfig();

  const mode = status?.mode ?? "—";
  const isLive = mode === "LIVE";

  return (
    <div className="min-h-screen bg-bg-primary">
      {/* Header */}
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
                    ? "border-[#8b5cf6] text-text-primary"
                    : "border-transparent text-text-muted hover:text-text-secondary hover:border-border"
                }`}
              >
                {label}
              </button>
            ))}
          </nav>
        </div>
      </header>

      {/* Content */}
      <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6">
        {activeTab === "status" && (
          <StatusPanel status={status} uptime={uptime} loading={statusLoading} />
        )}
        {activeTab === "trades" && (
          <TradeFeed
            entries={tradeLogs.entries}
            total={tradeLogs.total}
            loading={tradeLogs.loading}
            loadMore={tradeLogs.loadMore}
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
          />
        )}
        {activeTab === "performance" && (
          <PerformanceView
            entries={tradeLogs.entries}
            loading={tradeLogs.loading}
            config={config}
          />
        )}
        {activeTab === "config" && (
          <ConfigView config={config} loading={configLoading} />
        )}
      </main>
    </div>
  );
}
