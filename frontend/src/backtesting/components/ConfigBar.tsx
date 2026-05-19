import type { BacktestConfig } from "@/backtesting/lib/types";

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
  topLevel?: unknown;
}

/** Displays a param — single value if all sessions match, per-session badges otherwise. */
function ParamDisplay({ label, sessions, config, paramKey, format, topLevel }: ParamDisplayProps) {
  // If a top-level value exists, show it directly
  if (typeof topLevel === "number") {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          {label}
        </span>
        <span className="font-mono text-sm text-text-primary">{format(topLevel)}</span>
      </div>
    );
  }

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

function SimpleParam({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
        {label}
      </span>
      <span className="font-mono text-sm text-text-primary">
        {value != null ? String(value) : "—"}
      </span>
    </div>
  );
}

export function ConfigBar({ config }: ConfigBarProps) {
  const sessions = detectSessions(config);
  const isLsi = config.strategy === "lsi";

  const fmtPct = (v: number) => `${v}%`;
  const fmtNum = (v: number) => v.toString();
  const fmtUsd = (v: number) =>
    `$${v.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

  return (
    <div className="dashboard-card flex flex-wrap items-start gap-x-6 gap-y-2 rounded-lg border border-border px-4 py-3">
      {isLsi ? (
        <>
          <SimpleParam label="Swing L/R" value={`${config.lsi_n_left ?? "—"}/${config.lsi_n_right ?? "—"}`} />
          <SimpleParam label="FVG Window L/R" value={`${config.lsi_fvg_window_left ?? "—"}/${config.lsi_fvg_window_right ?? "—"}`} />
          <SimpleParam label="Stop Mode" value={config.lsi_stop_mode} />
          <SimpleParam label="Entry Mode" value={config.lsi_entry_mode} />
          {config.lsi_first_fvg_only ? <SimpleParam label="1st FVG" value="ON" /> : null}
          {config.lsi_clean_path ? <SimpleParam label="Clean Path" value="ON" /> : null}
          {(config.lsi_be_swing_n_left as number) > 0 && <SimpleParam label="BE Swing nL" value={config.lsi_be_swing_n_left} />}
          {config.lsi_cancel_on_swing ? <SimpleParam label="Cancel on Swing" value="ON" /> : null}
        </>
      ) : (
        <>
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
        </>
      )}
      <div className="flex flex-col gap-1">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-muted">
          Risk
        </span>
        <span className="font-mono text-sm text-text-primary">
          {config.risk_usd != null ? fmtUsd(config.risk_usd) : "—"}
        </span>
      </div>
      <ParamDisplay
        label="R:R"
        sessions={sessions}
        config={config}
        paramKey="rr"
        format={fmtNum}
        topLevel={config.rr}
      />
      <ParamDisplay
        label="TP1 Ratio"
        sessions={sessions}
        config={config}
        paramKey="tp1_ratio"
        format={fmtNum}
        topLevel={config.tp1_ratio}
      />
      <SimpleParam label="Exit Mode" value={config.exit_mode ?? "split"} />
    </div>
  );
}
