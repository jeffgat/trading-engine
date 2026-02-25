export const STATE_COLORS: Record<string, string> = {
  idle: "bg-text-muted/20 text-text-muted",
  orb_building: "bg-info/20 text-info",
  scanning: "bg-warning/20 text-warning",
  armed_long: "bg-profit/20 text-profit",
  armed_short: "bg-loss/20 text-loss",
  filled: "bg-accent/20 text-[#8b5cf6]",
  managing: "bg-accent/20 text-[#8b5cf6]",
  flat: "bg-text-muted/20 text-text-muted",
};

export const STATE_LABELS: Record<string, string> = {
  idle: "Idle",
  orb_building: "ORB Building",
  scanning: "Scanning",
  armed_long: "Armed Long",
  armed_short: "Armed Short",
  filled: "Filled",
  managing: "Managing",
  flat: "Flat",
};

export const EVENT_COLORS: Record<string, string> = {
  ORB_READY: "bg-info/20 text-info",
  LONG_SETUP: "bg-profit/20 text-profit",
  SHORT_SETUP: "bg-loss/20 text-loss",
  FILLED: "bg-[#8b5cf6]/20 text-[#8b5cf6]",
  TP1_PARTIAL: "bg-profit-dim/20 text-profit-dim",
  TP1_BE_SINGLE: "bg-profit-dim/20 text-profit-dim",
  TP2_HIT: "bg-profit/20 text-profit",
  TP2_DIRECT: "bg-profit/20 text-profit",
  SL_HIT: "bg-loss/20 text-loss",
  BE_HIT: "bg-text-muted/20 text-text-muted",
  EOD_FLAT: "bg-text-muted/20 text-text-muted",
  CANCEL: "bg-text-muted/20 text-text-muted",
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
  NY: "bg-info/20 text-info",
  Asia: "bg-[#8b5cf6]/20 text-[#8b5cf6]",
  LDN: "bg-warning/20 text-warning",
};
