import { useState } from "react";
import { SessionCard } from "./SessionCard";
import { CONFIG_COLORS } from "@/execution/lib/constants";
import type { ConfigResponse, SessionStatus } from "@/execution/lib/types";

interface StatusPanelProps {
  configEngines: Record<string, SessionStatus[]>;
  engines: SessionStatus[];
  uptime: number;
  loading: boolean;
  activeConfig: string;
  config: ConfigResponse | null;
  onPause?: (sessionName: string, configName?: string) => Promise<void>;
  onResume?: (sessionName: string, configName?: string) => Promise<void>;
}

/** Build a map from short session name (e.g. "NQ_NY") to normalized strategy type.
 *  Config keys may be prefixed like "FAST:NQ_NY", so we strip the prefix.
 *  Backend may send "ifvg" — normalize to "lsi" for display. */
function buildStrategyLookup(config: ConfigResponse | null): Record<string, "continuation" | "lsi"> {
  const map: Record<string, "continuation" | "lsi"> = {};
  if (!config?.sessions) return map;
  for (const [key, cfg] of Object.entries(config.sessions)) {
    const short = key.includes(":") ? key.split(":")[1] : key;
    map[short] = cfg.type === "continuation" ? "continuation" : "lsi";
  }
  return map;
}

/** Check if an exec config is live (has webhooks) or dry-run */
function isLiveConfig(configName: string, config: ConfigResponse | null): boolean {
  const meta = config?.exec_configs?.[configName];
  if (!meta) return false;
  return meta.webhooks.length > 0;
}

export function StatusPanel({ configEngines, engines, uptime, loading, activeConfig, config, onPause, onResume }: StatusPanelProps) {
  const stratLookup = buildStrategyLookup(config);

  // Compute which configs are live vs dry-run for collapse default
  const configNames = Object.keys(configEngines);
  const liveConfigs = configNames.filter((n) => isLiveConfig(n, config));
  const dryRunConfigs = configNames.filter((n) => !isLiveConfig(n, config));

  // Sort: live first (alphabetical), then dry-run (alphabetical)
  const sortedConfigs = [...liveConfigs.sort(), ...dryRunConfigs.sort()];

  // Collapsed state: dry-run configs start collapsed, live configs start expanded
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {};
    for (const name of configNames) {
      init[name] = !isLiveConfig(name, config);
    }
    return init;
  });

  const toggleCollapse = (name: string) => {
    setCollapsed((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading...
      </div>
    );
  }

  if (engines.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        No strategies running
      </div>
    );
  }

  const uptimeStr = formatUptime(uptime);

  // When a specific config is selected, show only that config's engines (no collapse)
  if (activeConfig !== "ALL") {
    const selectedEngines = configEngines[activeConfig] ?? [];
    return (
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="text-sm text-text-muted">
            Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
          </div>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {selectedEngines.map((engine) => (
            <SessionCard key={`${engine.config_name}-${engine.session}`} engine={engine} strategyType={stratLookup[engine.session]} onPause={onPause} onResume={onResume} />
          ))}
        </div>
      </div>
    );
  }

  // ALL: show sections grouped by config name, live first, with collapse
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="text-sm text-text-muted">
          Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
        </div>
      </div>

      {sortedConfigs.map((configName) => {
        const groupEngines = configEngines[configName] ?? [];
        if (groupEngines.length === 0) return null;
        const colorClasses = CONFIG_COLORS[configName] ?? "bg-text-muted/20 text-text-muted border-text-muted/30";
        const isLive = isLiveConfig(configName, config);
        const isCollapsed = collapsed[configName] ?? false;

        return (
          <div key={configName} className="space-y-3">
            <button
              onClick={() => toggleCollapse(configName)}
              className="flex w-full items-center gap-2 text-left group"
            >
              <svg
                className={`h-3.5 w-3.5 text-text-muted transition-transform ${isCollapsed ? "" : "rotate-90"}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2.5}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
              <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${colorClasses}`}>
                {configName}
              </span>
              <span className={`text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded ${
                isLive
                  ? "text-profit bg-profit/10"
                  : "text-amber-400 bg-amber-400/10"
              }`}>
                {isLive ? "Live" : "Dry Run"}
              </span>
              <span className="text-xs text-text-muted">
                {groupEngines.length} strateg{groupEngines.length !== 1 ? "ies" : "y"}
              </span>
            </button>
            {!isCollapsed && (
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
                {groupEngines.map((engine) => (
                  <SessionCard key={`${configName}-${engine.session}`} engine={engine} strategyType={stratLookup[engine.session]} onPause={onPause} onResume={onResume} />
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function formatUptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${s}s`;
  return `${s}s`;
}
