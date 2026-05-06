export const STATE_COLORS: Record<string, string> = {
  idle: "bg-sky-500/20 text-sky-200",
  orb_building: "bg-info/20 text-info",
  scanning: "bg-sky-500/20 text-sky-300",
  waiting_for_gap: "bg-amber-500/20 text-amber-300",
  waiting_for_sweep: "bg-warning/20 text-warning",
  waiting_for_inversion: "bg-violet-500/20 text-violet-300",
  collecting_gaps: "bg-amber-500/20 text-amber-300",
  armed_limit: "bg-profit/20 text-profit",
  trade_overlap: "bg-loss/20 text-loss",
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
  trade_overlap: "Trade Overlap",
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
  TP1_SINGLE_EXIT: "bg-profit-dim/20 text-profit-dim",
  TP2_HIT: "bg-profit/20 text-profit",
  TP2_DIRECT: "bg-profit/20 text-profit",
  SL_HIT: "bg-loss/20 text-loss",
  BE_HIT: "bg-text-muted/20 text-text-muted",
  EOD_FLAT: "bg-text-muted/20 text-text-muted",
  CANCEL: "bg-text-muted/20 text-text-muted",
  CANCELLED_LIMITS: "bg-text-muted/20 text-text-muted",
  NO_SETUP: "bg-text-muted/20 text-text-muted",
  TRADE_OVERLAP: "bg-loss/20 text-loss",
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

/** Map engine session names to research leg names (strategy/ASSET_SESSION-RR). */
export const SESSION_DISPLAY_NAMES: Record<string, Record<string, string>> = {
  ALPHA_V1: {
    NQ_NY_LSI: "HTF_LSI/NQ_NY-RR3.5",
    NQ_Asia: "ORB/NQ_ASIA-RR6",
    ES_Asia: "ORB/ES_ASIA-RR1.5",
    ES_NY: "ORB/ES_NY-RR5",
  },
  "ALPHA_V1-A": {
    NQ_NY_LSI: "HTF_LSI/NQ_NY-RR3.5",
    NQ_Asia: "ORB/NQ_ASIA-RR6",
    ES_Asia: "ORB/ES_ASIA-RR1.5",
    ES_NY: "ORB/ES_NY-RR5",
  },
  "ALPHA_V1-C": {
    NQ_NY_LSI: "HTF_LSI/NQ_NY-RR3.5",
    NQ_Asia: "ORB/NQ_ASIA-RR6",
    ES_Asia: "ORB/ES_ASIA-RR1.5",
    ES_NY: "ORB/ES_NY-RR5",
  },
  TESTING: {
    NQ_NY_LSI: "LSI/NQ_NY-RR2",
    GC_Asia: "ORB/GC_ASIA-RR2.5",
    ES_NY_ATH_GATE: "ORB/ES_NY_ATH_GATE",
  },
};

export const CONFIG_COLORS: Record<string, string> = {
  ALPHA_V1: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
  "ALPHA_V1-A": "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
  "ALPHA_V1-C": "bg-cyan-500/20 text-cyan-300 border-cyan-500/40",
  TESTING: "bg-amber-500/20 text-amber-400 border-amber-500/40",
  FAST: "bg-neutral-600/20 text-neutral-500 border-neutral-600/30",
  "FAST_V1.1": "bg-neutral-600/20 text-neutral-500 border-neutral-600/30",
  FAST_V2: "bg-neutral-600/20 text-neutral-500 border-neutral-600/30",
  "FAST_V2.1": "bg-neutral-600/20 text-neutral-500 border-neutral-600/30",
};
