import { useEffect } from "react";
import { SessionCard } from "./SessionCard";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/shared/ui/select";
import { ExecutionTabSkeleton } from "@/shared/ui/page-skeletons";
import type { ConfigResponse, ExecConfigMeta, SessionConfig, SessionStatus } from "@/execution/lib/types";

interface StatusPanelProps {
  configEngines: Record<string, SessionStatus[]>;
  engines: SessionStatus[];
  uptime: number;
  loading: boolean;
  activeConfig: string;
  setActiveConfig: (config: string) => void;
  config: ConfigResponse | null;
  statusExecConfigs?: Record<string, ExecConfigMeta>;
  onPause?: (sessionName: string, configName?: string) => Promise<void>;
  onFlatten?: (sessionName: string, configName?: string) => Promise<void>;
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

function buildSessionConfigLookup(config: ConfigResponse | null): Record<string, SessionConfig> {
  const map: Record<string, SessionConfig> = {};
  if (!config?.sessions) return map;
  for (const [key, cfg] of Object.entries(config.sessions)) {
    map[key] = cfg as SessionConfig;
  }
  return map;
}

/** Check if an exec config is live (has webhooks) or dry-run */
function isLiveConfig(
  configName: string,
  config: ConfigResponse | null,
  statusExecConfigs?: Record<string, ExecConfigMeta>,
): boolean {
  const meta = config?.exec_configs?.[configName] ?? statusExecConfigs?.[configName];
  if (!meta) return false;
  return meta.webhooks.length > 0;
}

const MODE_LABEL_STYLES = {
  live: "text-money-positive bg-money-positive/10 border-money-positive/20",
  dryRun: "text-warning bg-warning/10 border-warning/20",
} as const;

function ConfigOptionLabel({
  name,
  live,
  count,
}: {
  name: string;
  live: boolean;
  count: number;
}) {
  return (
    <span className="inline-flex items-center gap-2 whitespace-nowrap">
      <span className="shrink-0">{name}</span>
      <span className={`shrink-0 text-[9px] uppercase ${live ? "text-money-positive" : "text-warning"}`}>
        {live ? "Live" : "Dry-Run"}
      </span>
      <span className="shrink-0 text-text-muted">({count})</span>
    </span>
  );
}

export function StatusPanel({ configEngines, engines, uptime, loading, activeConfig, setActiveConfig, config, statusExecConfigs, onPause, onFlatten, onResume }: StatusPanelProps) {
  const stratLookup = buildStrategyLookup(config);
  const sessionCfgLookup = buildSessionConfigLookup(config);

  // Compute which configs are live vs dry-run
  const configNames = Object.keys(configEngines);
  const liveConfigs = configNames.filter((n) => isLiveConfig(n, config, statusExecConfigs));
  const dryRunConfigs = configNames.filter((n) => !isLiveConfig(n, config, statusExecConfigs));

  // Sort: live first (alphabetical), then dry-run (alphabetical)
  const sortedConfigs = [...liveConfigs.sort(), ...dryRunConfigs.sort()];

  // Default to first live config (or first config if none are live)
  const defaultConfig = liveConfigs[0] ?? sortedConfigs[0] ?? "";
  const validConfig = configEngines[activeConfig] ? activeConfig : defaultConfig;

  // Auto-select a default config only when activeConfig is unset or invalid
  useEffect(() => {
    if (!validConfig) return;
    if (!activeConfig || !configEngines[activeConfig]) {
      setActiveConfig(validConfig);
    }
  }, [validConfig, activeConfig, setActiveConfig, configEngines]);

  if (loading) {
    return <ExecutionTabSkeleton tab="status" />;
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
    isLive: isLiveConfig(validConfig, config, statusExecConfigs),
    count: displayEngines.length,
  };
  const modeStyle = selectedConfigMeta.isLive ? MODE_LABEL_STYLES.live : MODE_LABEL_STYLES.dryRun;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="text-sm text-text-muted">
            Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-end gap-3">
          <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider ${modeStyle}`}>
            {selectedConfigMeta.isLive ? "Live" : "Dry-Run"}
          </span>
          <span className="text-xs text-text-muted">
            {selectedConfigMeta.count} strateg{selectedConfigMeta.count !== 1 ? "ies" : "y"}
          </span>
          <Select value={validConfig} onValueChange={setActiveConfig}>
            <SelectTrigger className="h-10 w-max max-w-[calc(100vw-2rem)] px-3 [&>span]:line-clamp-none [&>span]:overflow-visible [&>span]:whitespace-nowrap">
              <SelectValue className="whitespace-nowrap" />
            </SelectTrigger>
            <SelectContent className="w-max max-w-[calc(100vw-2rem)]">
              {sortedConfigs.map((name) => {
                const count = (configEngines[name] ?? []).length;
                const live = isLiveConfig(name, config, statusExecConfigs);
                return (
                  <SelectItem key={name} value={name}>
                    <ConfigOptionLabel name={name} live={live} count={count} />
                  </SelectItem>
                );
              })}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {displayEngines.map((engine) => (
          <SessionCard
            key={`${engine.config_name}-${engine.session}`}
            engine={engine}
            strategyType={stratLookup[engine.session]}
            sessionConfig={sessionCfgLookup[`${engine.config_name}:${engine.session}`] ?? sessionCfgLookup[engine.session]}
            onPause={onPause}
            onFlatten={onFlatten}
            onResume={onResume}
          />
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
