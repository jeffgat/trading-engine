import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { ConfigResponse, SessionConfig } from "@/lib/types";

interface ConfigViewProps {
  config: ConfigResponse | null;
  loading: boolean;
}

function ConfigItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between py-1">
      <span className="text-text-muted text-xs">{label}</span>
      <span className="font-mono text-xs text-text-secondary">{value}</span>
    </div>
  );
}

const DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function SessionConfigCard({
  name,
  cfg,
}: {
  name: string;
  cfg: SessionConfig;
}) {
  const stopIsOrb = cfg.stop_basis === "orb";
  const gapIsOrb = cfg.gap_filter_basis === "orb";

  return (
    <Card className="border-border bg-bg-card">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-semibold">{name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-1">
        <ConfigItem label="ORB" value={`${cfg.orb_start} - ${cfg.orb_end}`} />
        <ConfigItem
          label="Entry"
          value={`${cfg.entry_start} - ${cfg.entry_end}`}
        />
        <ConfigItem
          label="Flat"
          value={`${cfg.flat_start} - ${cfg.flat_end}`}
        />
        <ConfigItem label="Exec Contract" value={cfg.exec_ticker} />
        {cfg.excluded_dow != null && (
          <ConfigItem
            label="Skip Day"
            value={DOW_NAMES[cfg.excluded_dow] ?? `DOW ${cfg.excluded_dow}`}
          />
        )}
        <div className="border-t border-border/30 my-1" />
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
        <div className="border-t border-border/30 my-1" />
        <ConfigItem label="Risk USD" value={`$${cfg.risk_usd}`} />
        <ConfigItem label="Point Value" value={`$${cfg.point_value}`} />
        <ConfigItem label="Min Qty" value={cfg.min_qty.toString()} />
        <ConfigItem label="BE Offset" value={`${cfg.be_offset_ticks} ticks`} />
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
            <CardTitle className="text-sm font-semibold">Risk</CardTitle>
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
            <SessionConfigCard key={name} name={name} cfg={cfg} />
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
