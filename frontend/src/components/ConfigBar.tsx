import type { BacktestConfig } from "../lib/types";

/** Session names detected from config keys like `ny_orb_window`. */
function detectSessions(config: BacktestConfig): string[] {
  const sessions: string[] = [];
  for (const key of Object.keys(config)) {
    if (key.endsWith("_orb_window")) {
      sessions.push(key.replace("_orb_window", ""));
    }
  }
  return sessions.sort();
}

/** Get a per-session param value, e.g. getSessionParam(config, "ny", "stop_atr_pct"). */
function getSessionParam(config: BacktestConfig, session: string, param: string): number | undefined {
  const val = config[`${session}_${param}`];
  return typeof val === "number" ? val : undefined;
}

interface ParamDisplayProps {
  label: string;
  sessions: string[];
  config: BacktestConfig;
  paramKey: string;
  format: (v: number) => string;
}

/** Displays a param — single value if all sessions match, per-session badges otherwise. */
function ParamDisplay({ label, sessions, config, paramKey, format }: ParamDisplayProps) {
  const values = sessions.map((s) => ({
    session: s,
    value: getSessionParam(config, s, paramKey),
  }));

  const allSame = values.length <= 1 || values.every((v) => v.value === values[0].value);

  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </span>
      {allSame ? (
        <span className="font-mono text-sm text-text-primary">
          {values[0]?.value != null ? format(values[0].value) : "—"}
        </span>
      ) : (
        <div className="flex items-center gap-2">
          {values.map(({ session, value }) => (
            <span key={session} className="flex items-center gap-1">
              <span className="rounded bg-bg-card-hover px-1 py-px text-[10px] font-medium uppercase text-text-muted">
                {session}
              </span>
              <span className="font-mono text-sm text-text-primary">
                {value != null ? format(value) : "—"}
              </span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

interface ConfigBarProps {
  config: BacktestConfig;
}

export function ConfigBar({ config }: ConfigBarProps) {
  const sessions = detectSessions(config);

  const fmtPct = (v: number) => `${v}%`;
  const fmtNum = (v: number) => v.toString();
  const fmtUsd = (v: number) =>
    `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

  return (
    <div className="flex flex-wrap items-start gap-x-6 gap-y-2 rounded-lg border border-border bg-bg-card px-4 py-3">
      <ParamDisplay
        label="Stop ATR %"
        sessions={sessions}
        config={config}
        paramKey="stop_atr_pct"
        format={fmtPct}
      />
      <ParamDisplay
        label="Min Gap ATR %"
        sessions={sessions}
        config={config}
        paramKey="min_gap_atr_pct"
        format={fmtPct}
      />
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          Risk
        </span>
        <span className="font-mono text-sm text-text-primary">
          {fmtUsd(config.risk_usd)}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          R:R
        </span>
        <span className="font-mono text-sm text-text-primary">
          {fmtNum(config.rr)}
        </span>
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          TP1 Ratio
        </span>
        <span className="font-mono text-sm text-text-primary">
          {fmtNum(config.tp1_ratio)}
        </span>
      </div>
    </div>
  );
}
