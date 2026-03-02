import { SessionCard } from "./SessionCard";
import { CONFIG_COLORS } from "@/execution/lib/constants";
import type { SessionStatus } from "@/execution/lib/types";

interface StatusPanelProps {
  configEngines: Record<string, SessionStatus[]>;
  engines: SessionStatus[];
  uptime: number;
  loading: boolean;
  activeConfig: string;
}

export function StatusPanel({ configEngines, engines, uptime, loading, activeConfig }: StatusPanelProps) {
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
        No session engines running
      </div>
    );
  }

  const uptimeStr = formatUptime(uptime);

  // When a specific config is selected, show only that config's engines
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
            <SessionCard key={`${engine.config_name}-${engine.session}`} engine={engine} />
          ))}
        </div>
      </div>
    );
  }

  // ALL: show sections grouped by config name
  const configNames = Object.keys(configEngines).sort();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-text-muted">
          Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
        </div>
      </div>

      {configNames.map((configName) => {
        const groupEngines = configEngines[configName] ?? [];
        if (groupEngines.length === 0) return null;
        const colorClasses = CONFIG_COLORS[configName] ?? "bg-text-muted/20 text-text-muted border-text-muted/30";
        return (
          <div key={configName} className="space-y-3">
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium ${colorClasses}`}>
                {configName}
              </span>
              <span className="text-xs text-text-muted">
                {groupEngines.length} engine{groupEngines.length !== 1 ? "s" : ""}
              </span>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {groupEngines.map((engine) => (
                <SessionCard key={`${configName}-${engine.session}`} engine={engine} />
              ))}
            </div>
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
