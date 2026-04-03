import { useEffect } from "react";
import { SessionCard } from "./SessionCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import type { ConfigResponse, SessionStatus } from "@/execution/lib/types";

interface StatusPanelProps {
  configEngines: Record<string, SessionStatus[]>;
  engines: SessionStatus[];
  uptime: number;
  loading: boolean;
  activeConfig: string;
  setActiveConfig: (config: string) => void;
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

export function StatusPanel({ configEngines, engines, uptime, loading, activeConfig, setActiveConfig, config, onPause, onResume }: StatusPanelProps) {
  const stratLookup = buildStrategyLookup(config);

  // Compute which configs are live vs dry-run
  const configNames = Object.keys(configEngines);
  const liveConfigs = configNames.filter((n) => isLiveConfig(n, config));
  const dryRunConfigs = configNames.filter((n) => !isLiveConfig(n, config));

  // Sort: live first (alphabetical), then dry-run (alphabetical)
  const sortedConfigs = [...liveConfigs.sort(), ...dryRunConfigs.sort()];

  // Default to first live config (or first config if none are live)
  const defaultConfig = liveConfigs[0] ?? sortedConfigs[0] ?? "";
  const validConfig = configEngines[activeConfig] ? activeConfig : defaultConfig;

  // Sync the parent state when we auto-select a default, or when
  // config metadata arrives and reveals a live config should be selected
  useEffect(() => {
    if (!validConfig) return;
    // If activeConfig is unset or doesn't exist in engines, pick the default
    if (!activeConfig || !configEngines[activeConfig]) {
      setActiveConfig(validConfig);
      return;
    }
    // If activeConfig is a dry-run but a live config exists, switch to live
    if (liveConfigs.length > 0 && !liveConfigs.includes(activeConfig)) {
      setActiveConfig(liveConfigs[0]);
    }
  }, [validConfig, activeConfig, setActiveConfig, liveConfigs, configEngines]);

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

  const displayEngines = configEngines[validConfig] ?? [];
  const selectedConfigMeta = {
    isLive: isLiveConfig(validConfig, config),
    count: displayEngines.length,
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="text-sm text-text-muted">
            Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <span className={`text-[10px] font-medium uppercase tracking-wider px-1.5 py-0.5 rounded ${
            selectedConfigMeta.isLive
              ? "text-profit bg-profit/10"
              : "text-amber-400 bg-amber-400/10"
          }`}>
            {selectedConfigMeta.isLive ? "Live" : "Dry Run"}
          </span>
          <span className="text-xs text-text-muted">
            {selectedConfigMeta.count} strateg{selectedConfigMeta.count !== 1 ? "ies" : "y"}
          </span>
          <Select value={validConfig} onValueChange={setActiveConfig}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {sortedConfigs.map((name) => {
                const count = (configEngines[name] ?? []).length;
                const live = isLiveConfig(name, config);
                return (
                  <SelectItem key={name} value={name}>
                    <span className="flex items-center gap-2">
                      {name}
                      <span className={`text-[9px] uppercase ${live ? "text-profit" : "text-amber-400"}`}>
                        {live ? "Live" : "Dry"}
                      </span>
                      <span className="text-text-muted">({count})</span>
                    </span>
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {displayEngines.map((engine) => (
          <SessionCard key={`${engine.config_name}-${engine.session}`} engine={engine} strategyType={stratLookup[engine.session]} onPause={onPause} onResume={onResume} />
        ))}
      </div>
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
