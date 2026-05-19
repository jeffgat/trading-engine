import { CONFIG_COLORS, SESSION_DISPLAY_NAMES, STATE_COLORS, STATE_LABELS } from "@/execution/lib/constants";
import type { SessionConfig, SessionStatus } from "@/execution/lib/types";
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

const DOW_NAMES: Record<number, string> = {
  0: "Mon",
  1: "Tue",
  2: "Wed",
  3: "Thu",
  4: "Fri",
  5: "Sat",
  6: "Sun",
};

function getSkipDays(engine: SessionStatus): string[] {
  const days: string[] = [];
  if (engine.excluded_dow != null) {
    const dows = Array.isArray(engine.excluded_dow)
      ? engine.excluded_dow
      : [engine.excluded_dow];
    for (const d of dows) {
      if (DOW_NAMES[d]) days.push(DOW_NAMES[d]);
    }
  }
  if (engine.fomc_exclusion) {
    days.push("FOMC");
  }
  return days;
}

function getEnginePyWeekday(engine: SessionStatus): number | null {
  if (!engine.date || engine.date.length !== 8) return null;
  const year = Number(engine.date.slice(0, 4));
  const month = Number(engine.date.slice(4, 6));
  const day = Number(engine.date.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day, 12, 0, 0));
  if (Number.isNaN(date.getTime())) return null;
  return (date.getUTCDay() + 6) % 7;
}

function isSkippedToday(engine: SessionStatus): boolean {
  const dow = getEnginePyWeekday(engine);
  if (dow == null || engine.excluded_dow == null) return false;
  const dows = Array.isArray(engine.excluded_dow)
    ? engine.excluded_dow
    : [engine.excluded_dow];
  return dows.includes(dow);
}

function getPrimaryRegimeEvaluation(engine: SessionStatus) {
  const evaluations = engine.regime_gate_status?.evaluations ?? [];
  return evaluations.find((evaluation) => !evaluation.allowed) ?? evaluations[0] ?? null;
}

const EXIT_LABELS: Record<string, string> = {
  sl: "SL Hit",
  tp1_single: "TP1 Hit",
  tp1_be: "BE Hit",
  tp1_tp2: "TP2 Hit",
  tp1_eod: "EOD Exit",
  tp2_direct: "TP2 Hit",
  eod: "EOD Exit",
};

const EXIT_COLORS: Record<string, { dot: string; text: string }> = {
  sl: { dot: "bg-loss", text: "text-loss" },
  tp1_single: { dot: "bg-profit-dim", text: "text-profit-dim" },
  tp1_be: { dot: "bg-text-muted", text: "text-text-muted" },
  tp1_tp2: { dot: "bg-profit", text: "text-profit" },
  tp1_eod: { dot: "bg-text-muted", text: "text-text-muted" },
  tp2_direct: { dot: "bg-profit", text: "text-profit" },
  eod: { dot: "bg-text-muted", text: "text-text-muted" },
};

const USD_FORMATTER = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  maximumFractionDigits: 0,
});

interface SessionCardProps {
  engine: SessionStatus;
  strategyType?: "continuation" | "lsi";
  sessionConfig?: SessionConfig;
  onPause?: (sessionName: string, configName?: string) => Promise<void>;
  onResume?: (sessionName: string, configName?: string) => Promise<void>;
}

function getGrossRiskUsd(engine: SessionStatus, sessionConfig?: SessionConfig, fallbackRiskUsd?: number) {
  const levels = engine.levels;
  const pointValue = engine.point_value ?? sessionConfig?.point_value;
  if (levels && pointValue != null) {
    const riskPoints = Math.abs(levels.entry - levels.stop);
    const grossRiskUsd = riskPoints * levels.qty * pointValue;
    if (Number.isFinite(grossRiskUsd) && grossRiskUsd > 0) {
      return grossRiskUsd;
    }
  }
  return fallbackRiskUsd;
}

function getRoundTripCommissionUsd(engine: SessionStatus) {
  const qty = engine.levels?.qty;
  const commissionPerContract = engine.commission_per_contract;
  if (qty == null || commissionPerContract == null) return 0;
  const commission = 2 * qty * commissionPerContract;
  return Number.isFinite(commission) ? commission : 0;
}

function formatResult(value: number, engine: SessionStatus, sessionConfig?: SessionConfig) {
  const rLabel = `${value > 0 ? "+" : ""}${value.toFixed(2)}R`;
  const riskUsd = getGrossRiskUsd(engine, sessionConfig, sessionConfig?.risk_usd ?? engine.risk_usd);
  if (riskUsd == null) return rLabel;
  const netUsd = value * riskUsd - getRoundTripCommissionUsd(engine);
  return `${rLabel} (${USD_FORMATTER.format(netUsd)})`;
}

function getTp1HitResult(engine: SessionStatus, sessionConfig?: SessionConfig) {
  const levels = engine.levels;
  if (levels) {
    const riskPoints = Math.abs(levels.entry - levels.stop);
    if (riskPoints > 0) {
      const tp1R = Math.abs(levels.tp1 - levels.entry) / riskPoints;
      return levels.qty <= 1 ? tp1R : 0.5 * tp1R;
    }
  }
  if (!sessionConfig?.rr || sessionConfig.tp1_ratio == null) return null;
  return 0.5 * sessionConfig.rr * sessionConfig.tp1_ratio;
}

function PriceRow({ label, value }: { label: string; value: number | null | undefined }) {
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

function formatPct(value: number | null | undefined) {
  return value == null ? "—" : `${value.toFixed(3)}%`;
}

function formatAthTime(value: string | null | undefined) {
  if (!value) return "—";
  return value.length >= 16 ? value.slice(11, 16) : value;
}

function GateRow({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="flex justify-between gap-3">
      <span className="text-text-muted text-xs">{label}</span>
      <span className={`font-mono text-xs text-right ${tone ?? "text-text-secondary"}`}>
        {value}
      </span>
    </div>
  );
}

export function SessionCard({ engine, strategyType, sessionConfig, onPause, onResume }: SessionCardProps) {
  const [saving, setSaving] = useState(false);
  const isLsi = strategyType === "lsi";
  const isLsiTag = (label: string | null | undefined) => label?.includes("LSI") ?? false;
  const hasLevels = engine.levels != null && engine.levels.entry != null;
  const dirLabel = hasLevels
    ? engine.levels!.direction === 1
      ? "LONG"
      : engine.levels!.direction === -1
        ? "SHORT"
        : null
    : null;
  const isPaused = engine.paused ?? false;
  const skippedToday = isSkippedToday(engine);
  const regimeBlocked = engine.skip_reason === "regime_gate" && engine.regime_gate_status?.allowed === false;
  const regimeEval = getPrimaryRegimeEvaluation(engine);
  const ath = engine.ath;
  const athEnabled = ath?.enabled === true;
  const athLastCheck = ath?.last_check ?? null;
  const athLastBlocked = athLastCheck?.blocked === true;
  const athHasSeed = ath?.high != null;
  const athStatusLabel = !athHasSeed
    ? "No Seed"
    : athLastCheck == null
    ? "Watching"
    : athLastBlocked
    ? "Blocked"
    : athLastCheck.available === false
    ? "No Check"
    : "Passed";
  const tp1HitResult = getTp1HitResult(engine, sessionConfig);
  const stateColor = regimeBlocked && engine.state === "flat"
    ? "bg-amber-500/20 text-amber-300"
    : skippedToday && engine.state === "idle"
    ? "bg-amber-500/20 text-amber-300"
    : (STATE_COLORS[engine.state] ?? "bg-text-muted/20 text-text-muted");
  const stateLabel = regimeBlocked && engine.state === "flat"
    ? "Blocked Today"
    : skippedToday && engine.state === "idle"
    ? "Skipped Today"
    : (STATE_LABELS[engine.state] ?? engine.state);

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
          {(() => {
            const displayName = SESSION_DISPLAY_NAMES[engine.config_name ?? ""]?.[engine.session];
            if (displayName) {
              // Split "LSI/NQ_NY-RR3" into prefix "LSI" and body "NQ_NY-RR3"
              const slashIdx = displayName.indexOf("/");
              const prefix = slashIdx >= 0 ? displayName.slice(0, slashIdx) : null;
              const body = slashIdx >= 0 ? displayName.slice(slashIdx + 1) : displayName;
              return (
                <>
                  <CardTitle className="text-base font-semibold text-white">{body}</CardTitle>
                  {prefix && (
                    <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                      isLsiTag(prefix)
                        ? "text-info bg-info/10"
                        : "text-profit bg-profit/10"
                    }`}>
                      {prefix}
                    </span>
                  )}
                </>
              );
            }
            return (
              <>
                <CardTitle className="text-base font-semibold text-white">{engine.session}</CardTitle>
                {strategyType && (
                  <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${
                    isLsi
                      ? "text-info bg-info/10"
                      : "text-profit bg-profit/10"
                  }`}>
                    {isLsi ? "LSI" : "ORB"}
                  </span>
                )}
              </>
            );
          })()}
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
          {athEnabled && athLastBlocked && (
            <Badge variant="outline" className="border-0 bg-amber-500/20 text-amber-300">
              ATH Blocked
            </Badge>
          )}
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

        {/* Skip days */}
        {(() => {
          const skipDays = getSkipDays(engine);
          if (skipDays.length === 0) return null;
          return (
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-[10px] text-text-muted">Skip:</span>
              {skipDays.map((day) => (
                <span
                  key={day}
                  className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-400/10 text-amber-400"
                >
                  {day}
                </span>
              ))}
            </div>
          );
        })()}

        {engine.regime_gate_status && (
          <div className="rounded-md border border-border/50 bg-bg-secondary p-2 space-y-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-text-muted font-medium">Regime Gate</span>
              <span className={`text-xs font-medium ${engine.regime_gate_status.allowed ? "text-profit" : "text-amber-300"}`}>
                {engine.regime_gate_status.allowed ? "Passed" : "Blocked"}
              </span>
            </div>
            {(engine.regime_gate_status.blocking_gate || regimeEval?.gate) && (
              <div className="flex justify-between">
                <span className="text-text-muted text-xs">Gate</span>
                <span className="font-mono text-xs text-text-secondary">
                  {engine.regime_gate_status.blocking_gate ?? regimeEval?.gate}
                </span>
              </div>
            )}
            {(regimeEval?.combined_regime || regimeEval?.regime) && (
              <div className="flex justify-between">
                <span className="text-text-muted text-xs">Bucket</span>
                <span className="font-mono text-xs text-text-secondary">
                  {regimeEval?.combined_regime ?? regimeEval?.regime}
                </span>
              </div>
            )}
            {regimeEval?.low_confidence != null && (
              <div className="flex justify-between">
                <span className="text-text-muted text-xs">Low Conf</span>
                <span className="font-mono text-xs text-text-secondary">
                  {regimeEval.low_confidence ? "Yes" : "No"}
                </span>
              </div>
            )}
            {regimeEval?.reason && (
              <div className="flex justify-between">
                <span className="text-text-muted text-xs">Reason</span>
                <span className="font-mono text-xs text-text-secondary">
                  {regimeEval.reason}
                </span>
              </div>
            )}
          </div>
        )}

        {athEnabled && (
          <div className="rounded-md border border-border/50 bg-bg-secondary p-2 space-y-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-text-muted font-medium">ATH Gate</span>
              <span
                className={`text-xs font-medium ${
                  athStatusLabel === "Blocked"
                    ? "text-amber-300"
                    : athStatusLabel === "Passed"
                    ? "text-profit"
                    : athStatusLabel === "No Seed"
                    ? "text-loss"
                    : "text-text-muted"
                }`}
              >
                {athStatusLabel}
              </span>
            </div>
            <GateRow
              label="Blocked Band"
              value={`${formatPct(ath?.block_min_pct)}-${formatPct(ath?.block_max_pct)}`}
            />
            <GateRow label="Now From ATH" value={formatPct(ath?.current_gap_pct)} />
            <GateRow
              label="Last Check"
              value={
                athLastCheck
                  ? `${athLastCheck.available === false ? "No Seed" : athLastCheck.blocked ? "Blocked" : "Passed"} ${formatPct(athLastCheck.gap_pct)}`
                  : "—"
              }
              tone={
                athLastBlocked
                  ? "text-amber-300"
                  : athLastCheck?.available === false
                  ? "text-loss"
                  : athLastCheck
                  ? "text-profit"
                  : undefined
              }
            />
            {athLastCheck && (
              <GateRow
                label="Check Time"
                value={`${formatAthTime(athLastCheck.bar_time)} ${athLastCheck.direction.toUpperCase()}`}
              />
            )}
            <GateRow
              label="Checks"
              value={`${ath?.check_count ?? 0} (${ath?.block_count ?? 0} blocked / ${ath?.pass_count ?? 0} passed)`}
            />
            {ath?.last_block && !athLastBlocked && (
              <GateRow
                label="Last Block"
                value={`${formatPct(ath.last_block.gap_pct)} @ ${formatAthTime(ath.last_block.bar_time)}`}
                tone="text-amber-300"
              />
            )}
          </div>
        )}

        {/* ORB levels (continuation strategies) */}
        {!isLsi && (engine.orb_high != null || engine.orb_low != null) && (
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

        {/* LSI overlay: swept level + FVG zone */}
        {isLsi && (engine.swept_level != null || engine.fvg_top != null) && (
          <div className="rounded-md border border-border/50 bg-bg-secondary p-2 space-y-1">
            <div className="text-xs text-text-muted font-medium mb-1">
              Sweep &amp; Gap
            </div>
            {engine.swept_level != null && (
              <div className="flex justify-between">
                <span className="text-text-muted text-xs">Swept Level</span>
                <span className="font-mono text-xs text-text-secondary">
                  {engine.swept_level.toFixed(2)}
                  {engine.swept_level_time && (
                    <span className="text-text-muted ml-1.5">{engine.swept_level_time}</span>
                  )}
                </span>
              </div>
            )}
            <PriceRow label="Gap High" value={engine.fvg_top ?? null} />
            <PriceRow label="Gap Low" value={engine.fvg_bottom ?? null} />
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
            {/* TP1 Hit indicator (shown while managing AND on resolved trades where TP1 was hit) */}
            {engine.tp1_hit && (
              <div className="flex items-center justify-between gap-2 mt-1">
                <div className="flex items-center gap-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-profit" />
                  <span className="text-xs text-profit">TP1 Hit</span>
                </div>
                {tp1HitResult != null && (
                  <span
                    className="font-mono text-xs font-medium text-profit"
                    title="Estimated net after round-turn fees"
                  >
                    {formatResult(tp1HitResult, engine, sessionConfig)}
                  </span>
                )}
              </div>
            )}
            {/* Resolved trade: show exit type + R result */}
            {engine.exit_type && (
              <div className="flex items-center justify-between mt-1">
                <div className="flex items-center gap-1">
                  <div className={`h-1.5 w-1.5 rounded-full ${EXIT_COLORS[engine.exit_type]?.dot ?? "bg-text-muted"}`} />
                  <span className={`text-xs ${EXIT_COLORS[engine.exit_type]?.text ?? "text-text-muted"}`}>
                    {EXIT_LABELS[engine.exit_type] ?? engine.exit_type}
                  </span>
                </div>
                {engine.r_result != null && (
                  <span
                    className={`font-mono text-xs font-medium ${engine.r_result > 0 ? "text-profit" : engine.r_result < 0 ? "text-loss" : "text-text-muted"}`}
                    title="Estimated net after round-turn fees"
                  >
                    {formatResult(engine.r_result, engine, sessionConfig)}
                  </span>
                )}
              </div>
            )}
          </div>
        )}

        {/* Flat with no trade */}
        {engine.state === "flat" && !hasLevels && (
          <div className="text-center text-text-muted text-xs py-2">
            {regimeBlocked
              ? "Blocked by regime gate."
              : athLastBlocked
              ? "Last setup skipped by ATH gate."
              : "No setup today"}
          </div>
        )}

        {/* Idle — no data yet */}
        {engine.state === "idle" && !hasLevels && engine.orb_high == null && (
          <div className="text-center text-text-muted text-xs py-4">
            {skippedToday ? "Excluded by day-of-week filter." : "Waiting for data..."}
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
                    className="rounded px-3 py-1.5 text-xs font-medium transition-colors border disabled:opacity-50 bg-loss/10 text-loss hover:bg-loss/20 border-loss/30"
                  >
                    {saving ? "..." : "Pause"}
                  </button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Pause {engine.session}?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will flatten any open position and pause the strategy from taking new trades.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={handleToggle}>
                      Flatten/Pause
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
