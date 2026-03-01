interface ConnectionStatusProps {
  connected: boolean;
}

export function ConnectionStatus({ connected }: ConnectionStatusProps) {
  return (
    <div className="flex items-center gap-2 text-sm">
      <div
        className={`h-2 w-2 rounded-full ${
          connected ? "bg-profit animate-pulse" : "bg-loss"
        }`}
      />
      <span className="text-text-muted">
        {connected ? "Connected" : "Reconnecting..."}
      </span>
    </div>
  );
}
