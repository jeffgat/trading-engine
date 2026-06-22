export type ConnectionState = "connected" | "polling" | "connecting" | "reconnecting" | "offline";

interface ConnectionStatusProps {
  state: ConnectionState;
}

const STATUS_DISPLAY: Record<ConnectionState, { label: string; tone: string; title: string }> = {
  connected: {
    label: "Connected",
    tone: "text-money-positive",
    title: "Dashboard connection healthy.",
  },
  polling: {
    label: "Polling",
    tone: "text-money-negative",
    title: "REST API is reachable; WebSocket stream is unavailable.",
  },
  connecting: {
    label: "Connecting...",
    tone: "text-money-negative",
    title: "Opening WebSocket stream.",
  },
  reconnecting: {
    label: "Reconnecting...",
    tone: "text-money-negative",
    title: "WebSocket stream is reconnecting.",
  },
  offline: {
    label: "Offline",
    tone: "text-money-negative",
    title: "REST API and WebSocket stream are unavailable.",
  },
};

export function ConnectionStatus({ state }: ConnectionStatusProps) {
  const display = STATUS_DISPLAY[state];

  return (
    <div className="flex items-center gap-2 text-sm" title={display.title} aria-label={display.title}>
      <div className={`status-pulse-dot ${display.tone}`} />
      <span className="font-mono text-xs font-semibold lowercase text-text-secondary">
        {display.label}
      </span>
    </div>
  );
}
