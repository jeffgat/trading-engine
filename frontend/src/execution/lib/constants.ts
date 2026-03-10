export const STATE_COLORS: Record<string, string> = {
  idle: "bg-sky-500/20 text-sky-200",
  orb_building: "bg-info/20 text-info",
  scanning: "bg-sky-500/20 text-sky-300",
  waiting_for_gap: "bg-amber-500/20 text-amber-300",
  waiting_for_sweep: "bg-warning/20 text-warning",
  waiting_for_inversion: "bg-violet-500/20 text-violet-300",
  collecting_gaps: "bg-amber-500/20 text-amber-300",
  armed_limit: "bg-profit/20 text-profit",
  filled: "bg-accent/20 text-gold-200",
  managing: "bg-cyan-500/20 text-cyan-300",
  flat: "bg-orange-500/20 text-orange-200",
};

export const STATE_LABELS: Record<string, string> = {
  idle: "Idle",
  orb_building: "ORB Building",
  scanning: "Scanning",
  waiting_for_gap: "Waiting for Gap",
  waiting_for_sweep: "Waiting for Sweep",
  waiting_for_inversion: "Waiting for Inversion",
  collecting_gaps: "Collecting Gaps",
  armed_limit: "Armed Limit",
  filled: "Filled",
  managing: "Managing",
  flat: "Flat",
};

export const EVENT_COLORS: Record<string, string> = {
  ORB_READY: "bg-info/20 text-info",
  LONG_SETUP: "bg-profit/20 text-profit",
  SHORT_SETUP: "bg-loss/20 text-loss",
  FILLED: "bg-accent/20 text-accent",
  TP1_PARTIAL: "bg-profit-dim/20 text-profit-dim",
  TP1_BE_SINGLE: "bg-profit-dim/20 text-profit-dim",
  TP2_HIT: "bg-profit/20 text-profit",
  TP2_DIRECT: "bg-profit/20 text-profit",
  SL_HIT: "bg-loss/20 text-loss",
  BE_HIT: "bg-text-muted/20 text-text-muted",
  EOD_FLAT: "bg-text-muted/20 text-text-muted",
  CANCEL: "bg-text-muted/20 text-text-muted",
  CANCELLED_LIMITS: "bg-text-muted/20 text-text-muted",
  NO_SETUP: "bg-text-muted/20 text-text-muted",
};

export const LOG_LEVEL_COLORS: Record<string, string> = {
  DEBUG: "text-text-muted",
  INFO: "text-text-secondary",
  WARNING: "text-warning",
  WARN: "text-warning",
  ERROR: "text-loss",
  CRITICAL: "text-loss",
};

export const SESSION_COLORS: Record<string, string> = {
  NQ: "bg-info/20 text-info",
  ES: "bg-warning/20 text-warning",
  GC: "bg-profit/20 text-profit",
  NY: "bg-info/20 text-info",
  Asia: "bg-accent/20 text-accent",
  LDN: "bg-warning/20 text-warning",
};

export const CONFIG_COLORS: Record<string, string> = {
  FAST: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  FAST_V2: "bg-fuchsia-500/20 text-fuchsia-400 border-fuchsia-500/30",
  SLOW: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
};
