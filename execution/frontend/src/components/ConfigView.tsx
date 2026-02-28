import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConfigResponse, SessionConfig } from "@/lib/types";

interface ConfigViewProps {
  config: ConfigResponse | null;
  loading: boolean;
}

function ConfigItem({
  label,
  value,
  overridden,
}: {
  label: string;
  value: string;
  overridden?: boolean;
}) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-text-muted text-xs">{label}</span>
      <span
        className={`font-mono text-xs ${overridden ? "text-amber-400" : "text-text-secondary"}`}
      >
        {value}
        {overridden && " *"}
      </span>
    </div>
  );
}

const DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface GlobalRiskDefaults {
  risk_usd: number;
  min_qty: number;
  max_single_risk_usd: number;
}

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-200">
      {children}
    </span>
  );
}

function SessionConfigCard({
  name,
  cfg,
  globalRisk,
}: {
  name: string;
  cfg: SessionConfig;
  globalRisk: GlobalRiskDefaults;
}) {
  const stopIsOrb = cfg.stop_basis === "orb";
  const gapIsOrb = cfg.gap_filter_basis === "orb";

  const maxSingleRisk = cfg.max_single_risk_usd ?? globalRisk.max_single_risk_usd;
  const riskOverridden = cfg.risk_usd !== globalRisk.risk_usd;
  const minQtyOverridden = cfg.min_qty !== globalRisk.min_qty;
  const maxRiskOverridden = maxSingleRisk !== globalRisk.max_single_risk_usd;
  const hasAnyOverride = riskOverridden || minQtyOverridden || maxRiskOverridden;

  return (
    <Card className="border-border bg-bg-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold bg-primary/20 px-2 py-1 w-fit rounded-md">{name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Session Times */}
        <div className="space-y-1">
          <SectionLabel>Session Times</SectionLabel>
          <ConfigItem label="ORB" value={`${cfg.orb_start} - ${cfg.orb_end}`} />
          <ConfigItem
            label="Entry"
            value={`${cfg.entry_start} - ${cfg.entry_end}`}
          />
          <ConfigItem
            label="Flat"
            value={`${cfg.flat_start} - ${cfg.flat_end}`}
          />
          {cfg.excluded_dow != null && (
            <ConfigItem
              label="Skip Day"
              value={DOW_NAMES[cfg.excluded_dow] ?? `DOW ${cfg.excluded_dow}`}
            />
          )}
        </div>

        {/* Strategy */}
        <div className="space-y-1 border-t border-border pt-2">
          <SectionLabel>Strategy</SectionLabel>
          <ConfigItem label="R:R" value={cfg.rr.toString()} />
          <ConfigItem label="TP1 Ratio" value={cfg.tp1_ratio.toString()} />
          {stopIsOrb ? (
            <ConfigItem label="Stop ORB %" value={`${cfg.stop_orb_pct}%`} />
          ) : (
            <ConfigItem label="Stop ATR %" value={`${cfg.stop_atr_pct}%`} />
          )}
          {gapIsOrb ? (
            <ConfigItem label="Gap ORB %" value={`${cfg.min_gap_orb_pct}%`} />
          ) : (
            <ConfigItem
              label="Gap ATR %"
              value={
                cfg.max_gap_atr_pct
                  ? `${cfg.min_gap_atr_pct} - ${cfg.max_gap_atr_pct}%`
                  : `${cfg.min_gap_atr_pct}%`
              }
            />
          )}
        </div>

        {/* Risk & Sizing */}
        <div
          className={`space-y-1 rounded-md px-2 py-2 -mx-2 ${hasAnyOverride ? "bg-amber-400/5 border border-amber-400/20" : "border-t border-border/30 pt-2"}`}
        >
          <SectionLabel>{hasAnyOverride ? "Risk & Sizing (override)" : "Risk & Sizing"}</SectionLabel>
          <ConfigItem
            label="Risk USD"
            value={`$${cfg.risk_usd}`}
            overridden={riskOverridden}
          />
          <ConfigItem
            label="Min Qty"
            value={cfg.min_qty.toString()}
            overridden={minQtyOverridden}
          />
          <ConfigItem
            label="Max Single Risk"
            value={`$${maxSingleRisk}`}
            overridden={maxRiskOverridden}
          />
          <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
          <ConfigItem label="BE Offset" value={`${cfg.be_offset_ticks} ticks`} />
          <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
          {hasAnyOverride && (
            <p className="text-[10px] text-amber-400/70 pt-0.5">
              * overridden from global default
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export function ConfigView({ config, loading }: ConfigViewProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Loading configuration...
      </div>
    );
  }

  if (!config) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted">
        Could not load configuration
      </div>
    );
  }

  const general = (config.config?.general as Record<string, unknown>) ?? {};
  const risk = (config.config?.risk as Record<string, unknown>) ?? {};
  const dates = (config.config?.dates as Record<string, unknown>) ?? {};

  const globalRisk: GlobalRiskDefaults = {
    risk_usd: Number(risk.risk_usd ?? 250),
    min_qty: Number(risk.min_qty ?? 1),
    max_single_risk_usd: Number(risk.max_single_risk_usd ?? 500),
  };

  return (
    <div className="space-y-6">
      {/* General + Risk */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">General</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(general).map(([key, value]) => (
              <ConfigItem key={key} label={key} value={String(value)} />
            ))}
          </CardContent>
        </Card>

        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Default Risk</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(risk).map(([key, value]) => (
              <ConfigItem key={key} label={key} value={String(value)} />
            ))}
          </CardContent>
        </Card>
      </div>

      {/* Session configs */}
      <div>
        <h3 className="text-sm font-semibold text-text-secondary mb-3">
          Session Configurations
        </h3>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
          {Object.entries(config.sessions).map(([name, cfg]) => (
            <SessionConfigCard
              key={name}
              name={name}
              cfg={cfg}
              globalRisk={globalRisk}
            />
          ))}
        </div>
      </div>

      {/* Date config */}
      {Object.keys(dates).length > 0 && (
        <Card className="border-border bg-bg-card">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold">Dates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1">
            {Object.entries(dates).map(([key, value]) => (
              <ConfigItem
                key={key}
                label={key}
                value={Array.isArray(value) ? value.join(", ") : String(value)}
              />
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
