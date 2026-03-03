import { CONFIG_COLORS, STATE_COLORS, STATE_LABELS } from "@/execution/lib/constants";
import type { SessionStatus } from "@/execution/lib/types";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/shared/ui/alert-dialog";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { useState } from "react";

interface SessionCardProps {
  engine: SessionStatus;
  strategyType?: "continuation" | "lsi";
  onPause?: (sessionName: string, configName?: string) => Promise<void>;
  onResume?: (sessionName: string, configName?: string) => Promise<void>;
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

export function SessionCard({ engine, strategyType, onPause, onResume }: SessionCardProps) {
  const [saving, setSaving] = useState(false);
  const isLsi = strategyType === "lsi";
  const isPaused = engine.paused ?? false;
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

  const handleToggle = async () => {
    setSaving(true);
    try {
      if (isPaused) {
        await onResume?.(engine.session, engine.config_name);
      } else {
        await onPause?.(engine.session, engine.config_name);
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className={`bg-bg-card flex flex-col ${isPaused ? "border-loss/80 opacity-60" : "border-border"}`}>
      <CardHeader className="pb-2 space-y-1.5">
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base font-semibold">
            {engine.session}
          </CardTitle>
          {strategyType && (
            <span
              className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                isLsi
                  ? "text-violet-400 bg-violet-400/10"
                  : "text-emerald-400 bg-emerald-400/10"
              }`}
            >
              {isLsi ? "LSI" : "ORB"}
            </span>
          )}
          {engine.config_name && (
            <span
              className={`inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-medium ${
                CONFIG_COLORS[engine.config_name] ?? "bg-text-muted/20 text-text-muted border-text-muted/30"
              }`}
            >
              {engine.config_name}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          {isPaused && (
            <Badge variant="outline" className="border-0 bg-loss/20 text-loss">
              Paused
            </Badge>
          )}
          <Badge variant="outline" className={`border-0 ${stateColor}`}>
            {stateLabel}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col flex-1 gap-3">
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

        {/* Pause/Resume button */}
        {(onPause || onResume) && (
          <div className="mt-auto flex justify-end">
            {isPaused ? (
              <button
                onClick={handleToggle}
                disabled={saving}
                className="rounded px-3 py-1.5 text-xs font-medium transition-colors border disabled:opacity-50 bg-profit/20 text-profit hover:bg-profit/30 border-profit/30"
              >
                {saving ? "..." : "Resume"}
              </button>
            ) : (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <button
                    disabled={saving}
                    className="rounded px-3 py-1.5 text-xs font-medium transition-colors border disabled:opacity-50 bg-loss/20 text-loss hover:bg-loss/30 border-loss/30"
                  >
                    {saving ? "..." : "Pause"}
                  </button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Pause {engine.session}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will stop the engine from taking new trades. Any open position will remain active.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={handleToggle}>
                      Pause
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
