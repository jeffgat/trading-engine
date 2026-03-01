import { SessionCard } from "./SessionCard";
import type { StatusResponse } from "@/execution/lib/types";

interface StatusPanelProps {
  status: StatusResponse | null;
  uptime: number;
  loading: boolean;
}

export function StatusPanel({ status, uptime, loading }: StatusPanelProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading...
      </div>
    );
  }

  if (!status || status.engines.length === 0) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        No session engines running
      </div>
    );
  }

  const uptimeStr = formatUptime(uptime);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-text-muted">
          Uptime: <span className="font-mono text-text-secondary">{uptimeStr}</span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
        {status.engines.map((engine) => (
          <SessionCard key={engine.session} engine={engine} />
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
