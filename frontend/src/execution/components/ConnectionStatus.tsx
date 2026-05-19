interface ConnectionStatusProps {
  connected: boolean;
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <div
        className={`status-pulse-dot ${
          connected ? "text-profit" : "text-loss"
        }`}
      />
      <span className="font-mono text-xs font-semibold lowercase text-text-secondary">
        {connected ? "Connected" : "Reconnecting..."}
      </span>
    </div>
  );
}
