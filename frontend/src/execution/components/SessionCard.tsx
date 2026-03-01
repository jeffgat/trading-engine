import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { Badge } from "@/shared/ui/badge";
import { STATE_COLORS, STATE_LABELS } from "@/execution/lib/constants";
import type { SessionStatus } from "@/execution/lib/types";

interface SessionCardProps {
  engine: SessionStatus;
}

function PriceRow({ label, value }: { label: string; value: number | null }) {
  if (value == null) return null;
  return (
    <div className="flex justify-between">
      <span className="text-text-muted text-xs">{label}</span>
      <span className="font-mono text-xs text-text-secondary">
        {value.toFixed(2)}
      </span>
    </div>
  );
}

export function SessionCard({ engine }: SessionCardProps) {
  const stateColor =
    STATE_COLORS[engine.state] ?? "bg-text-muted/20 text-text-muted";
  const stateLabel = STATE_LABELS[engine.state] ?? engine.state;

  const hasLevels = engine.levels != null;
  const dirLabel =
    engine.levels?.direction === 1
      ? "Long"
      : engine.levels?.direction === -1
        ? "Short"
        : null;

  return (
    <Card className="border-border bg-bg-card">
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-base font-semibold">
          {engine.session}
        </CardTitle>
        <Badge variant="outline" className={`border-0 ${stateColor}`}>
          {stateLabel}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Date + ATR */}
        <div className="flex justify-between text-xs">
          <span className="text-text-muted">
            {engine.date
              ? `${engine.date.slice(0, 4)}-${engine.date.slice(4, 6)}-${engine.date.slice(6)}`
              : "—"}
          </span>
          <span className="text-text-muted">
            ATR{" "}
            <span className="font-mono text-text-secondary">
              {engine.daily_atr > 0 ? engine.daily_atr.toFixed(2) : "—"}
            </span>
          </span>
        </div>

        {/* ORB levels */}
        {(engine.orb_high != null || engine.orb_low != null) && (
          <div className="rounded-md border border-border/50 bg-bg-secondary p-2 space-y-1">
            <div className="text-xs text-text-muted font-medium mb-1">
              ORB Range
            </div>
            <PriceRow label="High" value={engine.orb_high} />
            <PriceRow label="Low" value={engine.orb_low} />
            {engine.orb_high != null && engine.orb_low != null && (
              <PriceRow
                label="Range"
                value={engine.orb_high - engine.orb_low}
              />
            )}
          </div>
        )}

        {/* Trade levels */}
        {hasLevels && (
          <div className="rounded-md border border-border/50 bg-bg-secondary p-2 space-y-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-text-muted font-medium">
                Trade
              </span>
              {dirLabel && (
                <span
                  className={`text-xs font-medium ${
                    engine.levels!.direction === 1
                      ? "text-profit"
                      : "text-loss"
                  }`}
                >
                  {dirLabel} x{engine.levels!.qty}
                </span>
              )}
            </div>
            <PriceRow label="Entry" value={engine.levels!.entry} />
            <PriceRow label="Stop" value={engine.levels!.stop} />
            <PriceRow label="TP1" value={engine.levels!.tp1} />
            <PriceRow label="TP2" value={engine.levels!.tp2} />
            {engine.tp1_hit && (
              <div className="flex items-center gap-1 mt-1">
                <div className="h-1.5 w-1.5 rounded-full bg-profit" />
                <span className="text-xs text-profit">TP1 Hit</span>
              </div>
            )}
          </div>
        )}

        {/* Flat with ORB but no trade */}
        {engine.state === "flat" && !hasLevels && engine.orb_high != null && (
          <div className="text-center text-text-muted text-xs py-2">
            No setup today
          </div>
        )}

        {/* Idle — no data yet */}
        {engine.state === "idle" && !hasLevels && engine.orb_high == null && (
          <div className="text-center text-text-muted text-xs py-4">
            Waiting for session...
          </div>
        )}
      </CardContent>
    </Card>
  );
}
