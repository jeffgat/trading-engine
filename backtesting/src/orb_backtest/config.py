"""Strategy and session configuration as frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


ENTRY_CONTEXT_TOKENS = frozenset(
    {
        "vwap",
        "sma20", "sma50", "sma100", "sma200", "sma300",
        "ema20", "ema50", "ema100", "ema200", "ema300",
    }
)

REF_LSI_LEVELS = (
    "previous_day_high",
    "previous_day_low",
    "previous_week_high",
    "previous_week_low",
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
    "new_york_high",
    "new_york_low",
)
DATA_REF_LSI_LEVELS = (
    "data_high",
    "data_low",
)
ALLOWED_REF_LSI_LEVELS = REF_LSI_LEVELS + DATA_REF_LSI_LEVELS
ALLOWED_DATA_SWEEP_EVENT_TYPES = ("NFP", "CPI", "PPI", "FOMC")
ALLOWED_ORB_REENTRY_POLICIES = (
    "any_reentry",
    "after_positive_first",
    "after_nonpositive_first",
    "after_sl_first",
    "after_full_target_first",
)
ALLOWED_LSI_CONFIRMATION_MODES = (
    "inversion",
    "cisd",
    "inversion_or_cisd",
)


@dataclass(frozen=True)
class Instrument:
    """Futures instrument specification."""

    symbol: str
    point_value: float
    min_tick: float
    commission: float  # per contract per side
    data_file: str
    exchange_tz: str = "America/New_York"


@dataclass(frozen=True)
class SessionConfig:
    """Per-session parameters. Maps 1:1 to Pine Script input groups.

    Time fields use "HH:MM" in exchange_tz.

    For ORB-based strategies (continuation, reversal, inversion, cisd):
        orb_start/orb_end define the ORB window; in_rth spans orb_start → flat_end.

    For non-ORB strategies (lsi, reference_lsi):
        Set ``rth_start`` instead — it defines the start of RTH for signal
        detection (FVGs, sweeps).  ``orb_start``/``orb_end`` can be omitted.
    """

    name: str = ""

    # ORB window (used by continuation/reversal/inversion/cisd)
    orb_start: str = ""
    orb_end: str = ""

    # Entry/flat windows
    entry_start: str = ""
    entry_end: str = ""
    flat_start: str = ""
    flat_end: str = ""

    # RTH start override — used instead of orb_start for in_rth when set.
    # LSI sessions use this since they have no ORB.
    rth_start: str = ""

    # Optional sweep-valid window. When set, LSI-style sweep events are only
    # allowed to activate setups inside this window. Breaches outside this
    # window can still consume an existing pivot.
    sweep_start: str = ""
    sweep_end: str = ""

    # ATR-based parameters
    stop_atr_pct: float = 0.0  # stop distance as % of daily ATR
    min_gap_atr_pct: float = 0.0  # min FVG size as % of daily ATR
    qualifying_move_atr_pct: float = 0.0  # min upward extension as % of ATR for inversion shorts (0 = disabled)

    # ORB-based parameters (override ATR-based when > 0)
    stop_orb_pct: float = 0.0  # stop distance as % of ORB range (0 = use ATR-based stop)
    min_gap_orb_pct: float = 0.0  # min FVG size as % of ORB range (0 = use ATR-based)

    # Minimum stop floor in points (0 = disabled). When > 0, stop_dist = max(computed, min_stop_points).
    min_stop_points: float = 0.0

    # Minimum TP1 distance floor in points (0 = disabled). When > 0, tp1_dist = max(computed, min_tp1_points).
    min_tp1_points: float = 0.0


@dataclass(frozen=True)
class StrategyConfig:
    """Complete strategy configuration. All optimizable params live here."""

    # Risk parameters
    risk_usd: float = 5000.0
    rr: float = 2.5
    tp1_ratio: float = 0.5
    min_qty: float = 1.0
    qty_step: float = 1.0
    # ATR
    atr_length: int = 14
    # Optional local-context VWAP gate for continuation/reversal strategies.
    # If > 0, require the signal-bar close to be at least this % of daily ATR
    # beyond session VWAP in the trade direction.
    min_vwap_distance_atr_pct: float = 0.0
    # Optional session VWAP slope confirmation lookback in bars.
    # 0 disables the slope check.
    vwap_slope_lookback: int = 0
    # Optional fill-time context overlay for continuation/reversal entries.
    # Enforced on the actual fill bar using previous completed 5m indicator values.
    # Supported values:
    #   "" -> disabled
    #   "<token>_aligned"
    #   "<token1>_<token2>_aligned"
    #   ...
    # where tokens are drawn from ENTRY_CONTEXT_TOKENS. Every component must
    # satisfy the same signed-distance band on the actual fill bar.
    entry_context_gate: str = ""
    entry_context_min_atr: float = 0.0
    entry_context_max_atr: float = 0.0

    # Session configs
    sessions: tuple[SessionConfig, ...] = field(default_factory=tuple)

    # Instrument
    instrument: Instrument = field(default=None)

    # Half-day dates (YYYYMMDD strings) — NY only
    half_days: tuple[str, ...] = field(default_factory=tuple)

    # Excluded dates (YYYYMMDD strings)
    excluded_dates: tuple[str, ...] = field(default_factory=tuple)

    # Excluded weekdays (0=mon ... 4=fri) applied as a post-trade gate.
    excluded_days: tuple[int, ...] = field(default_factory=tuple)

    # Strategy type: "continuation", "reversal", "inversion", "cisd",
    # "lsi", "htf_lsi", "reference_lsi", or "ib"
    strategy: str = "continuation"

    # Direction filter: "both", "long", or "short" — restricts which trade directions are taken
    direction_filter: str = "both"

    # Reverse direction: flip all signal directions (long→short, short→long)
    reverse_direction: bool = False

    # Allow FVGs inside ORB range when the impulse candle (bar[1]) closes outside
    impulse_close_filter: bool = False

    # Continuation/reversal same-day FVG selection.
    # Supported values:
    #   "first"   -> keep the first valid same-direction FVG of the session-day
    #                (current/default behavior)
    #   "extreme" -> long-side FVGs ratchet to the highest entry price seen that
    #                day; short-side FVGs ratchet to the lowest entry price
    #                (a "chasing" entry)
    continuation_fvg_selection: str = "first"
    # Max filled continuation/reversal trades per session-day.
    # 1 preserves the current one-trade-per-day behavior.
    # 0 removes the cap and allows sequential re-entries on fresh post-exit gaps.
    orb_trade_max_per_session: int = 1
    # Optional continuation/reversal re-entry gate once a prior filled ORB trade
    # has exited. Only active when orb_trade_max_per_session != 1.
    # Supported values:
    #   "any_reentry"             -> always allow the next fresh setup
    #   "after_positive_first"    -> only re-arm after a > 0R prior trade
    #   "after_nonpositive_first" -> only re-arm after a <= 0R prior trade
    #   "after_sl_first"          -> only re-arm after a stop-loss prior trade
    #   "after_full_target_first" -> only re-arm after a full-target prior trade
    orb_reentry_policy: str = "any_reentry"

    # Optional conditional target compression for large realized stops.
    # Disabled when either field is 0. When enabled and computed stop/risk
    # distance is >= threshold, TP1/TP2 use wide_stop_target_rr instead of rr.
    wide_stop_target_threshold_points: float = 0.0
    wide_stop_target_rr: float = 0.0

    # Bar magnifier: use 1m sub-bars for fill/exit simulation
    use_bar_magnifier: bool = True

    # Cancel still-open limit orders if price reaches the selected target
    # before the entry price is touched. "" disables; "tp1" and "tp2" use
    # the candidate's computed TP1/TP2 price as the invalidation threshold.
    limit_cancel_on_pre_entry_target_touch: str = ""
    # HTF-LSI only. When True, a pre-entry TP-touch cancel requires a fresh
    # post-signal HTF-LSI sweep event before the pending limit order is canceled.
    limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep: bool = False

    # n-bar swing pivot width for liquidity sweep detection (10 = 10 bars left + 10 bars right)
    swing_n_bars: int = 10

    # LSI (Liquidity Sweep Inversion) params
    lsi_n_left: int = 3       # swing left bars
    lsi_n_right: int = 3      # swing right bars (also the confirmation lag)
    lsi_fvg_window_left: int = 10   # bars BEFORE sweep where FVG can have formed (FVG → sweep)
    lsi_fvg_window_right: int = 10  # bars AFTER sweep where FVG can form (sweep → FVG)
    lsi_stop_mode: str = "absolute"
    # Supported values:
    #   "absolute"     -> full setup structural extreme
    #   "fvg"          -> FVG boundary
    #   "gap_1x"...    -> stop distance = N * inverted gap size, capped at the structural stop
    #   "struct_50pct" -> halfway to the structural stop
    #   "struct_75pct" -> 75% of the way to the structural stop
    #   "atr_pct"      -> session stop_atr_pct distance, capped at the structural stop
    #   "orb_pct"      -> session stop_orb_pct distance, capped at the structural stop
    lsi_target_mode: str = "risk"
    # Supported values:
    #   "risk"       -> TP1/TP2 use the actual realized stop distance (current behavior)
    #   "structural" -> TP1/TP2 use the full structural stop distance as the target basis,
    #                   with TP1 >= 1.0R and TP2 >= 1.5R on the actual stop distance
    #   "left_structure" -> TP1/TP2 use unswept swing pivots to the left of the setup.
    #                       Longs target left-side highs, shorts target left-side lows.
    #                       TP1 uses the nearest eligible pivot at or beyond 1.0R;
    #                       TP2 uses the next eligible pivot at or beyond 1.5R.
    lsi_entry_mode: str = "close"
    # Supported values:
    #   "close"        -> enter on the inversion bar close
    #   "fvg_limit"    -> wait for a retest at the inverted FVG boundary
    #   "level_limit"  -> wait for a retest at the broken confirmation level
    #                     (alias of fvg_limit for FVG inversions; CISD body level
    #                     for CISD confirmations)
    #   "timed_hybrid" -> use "close" only when sweep->inversion time is fast enough,
    #                     otherwise fall back to "fvg_limit"
    lsi_close_on_sweep_to_inversion_minutes: int = 0
    # Only used when lsi_entry_mode == "timed_hybrid". If sweep->inversion time
    # in minutes is <= this threshold, the engine enters at the inversion close.
    # Otherwise it behaves like "fvg_limit". 0 = disabled.
    lsi_confirmation_mode: str = "inversion"
    # Supported values:
    #   "inversion"         -> legacy sweep + FVG + FVG inversion path
    #   "cisd"              -> sweep + body-based internal CISD path
    #   "inversion_or_cisd" -> additive path; earliest fill wins per session-day
    cisd_min_leg_bars: int = 2
    cisd_min_leg_atr_pct: float = 5.0
    cisd_max_leg_bars: int = 60
    lsi_first_fvg_only: bool = False
    # When True: per session-day, only keep the first (chronologically earliest)
    # FVG in active_for_long/active_for_short. Prevents entering on the last
    # (lowest-level) FVG which inverts first due to price proximity.

    lsi_clean_path: bool = False
    # When True: at inversion bar, skip if any opposing FVG zone exists in the
    # price range [entry_price, tp1_estimated]. For longs: no bearish FVGs
    # between entry and TP1. For shorts: no bullish FVGs between TP1 and entry.

    lsi_be_swing_n_left: int = 0        # 0 = disabled; N > 0 = find left-only pivot N bars wide as internal swing BE trigger
    lsi_cancel_on_swing: bool = False   # True = cancel pending limit order if internal swing swept before fill
    lsi_sweep_gate: str = "sweep_window"  # "sweep_window", "entry", or "rth"
    lsi_stale_breach_consumes_pivot: bool = True
    # When False, a breach outside the active sweep gate does not retire the pivot.
    # This reproduces the legacy/live-style behavior where a pre-entry breach can
    # still re-trigger later once the active scan window opens.
    lsi_lrlr_enabled: bool = False
    lsi_lrlr_gate: str = ""  # "", "require", or "exclude"
    lsi_lrlr_swing_n_left: int = 2
    lsi_lrlr_swing_n_right: int = 2
    lsi_lrlr_min_pivots: int = 3
    lsi_lrlr_lookback_minutes: int = 120
    lsi_lrlr_max_pivot_gap_minutes: int = 30
    lsi_lrlr_max_cluster_span_minutes: int = 120
    lsi_lrlr_max_price_span_atr: float = 0.18
    lsi_lrlr_monotonic_tolerance_atr: float = 0.03
    lsi_lrlr_line_tolerance_atr: float = 0.04
    lsi_lrlr_tp1_path_enabled: bool = False
    lsi_lrlr_tp1_buffer_atr: float = 0.0

    # HTF-LSI params
    htf_level_tf_minutes: int = 60
    htf_n_left: int = 5
    htf_trade_max_per_session: int = 1  # 0 = uncapped
    htf_lsi_inversion_ordinal: int = 1
    max_fvg_to_inversion_bars: int = 0
    htf_lsi_include_htf_levels: bool = True
    htf_lsi_include_eqhl_levels: bool = False
    htf_lsi_reference_levels: tuple[str, ...] = ()
    eqhl_level_tf_minutes: int = 15
    eqhl_n_left: int = 2
    eqhl_tolerance_ticks: int = 1
    eqhl_min_touches: int = 2
    eqhl_lookback_bars: int = 48  # 0 = unbounded
    data_sweep_min_daily_atr_pct: float = 15.0
    data_sweep_require_session_extreme: bool = False
    data_sweep_event_types: tuple[str, ...] = ()
    data_sweep_release_window_minutes: int = 0

    # Reference-level LSI params
    ref_lsi_gap_lookback_bars: int = 12
    ref_lsi_inversion_max_bars: int = 18
    ref_lsi_gap_entry_edge: str = "near"  # "near" (inversion-side edge) or "far" (opposite FVG edge)
    ref_lsi_reference_levels: tuple[str, ...] = REF_LSI_LEVELS

    # Experiment metadata (not used in simulation, just for labeling results)
    name: str = ""
    notes: str = ""

    def __post_init__(self):
        # Hard rules — no backtest can violate these constraints.
        if self.rr < 1.0:
            raise ValueError(
                f"rr must be >= 1.0 (got {self.rr}). "
                f"Minimum 1:1 reward-to-risk ratio is a hard rule."
            )
        if self.rr > 0 and self.tp1_ratio * self.rr < 1.0:
            raise ValueError(
                f"tp1_ratio * rr must be >= 1.0 (got {self.tp1_ratio} * {self.rr} = "
                f"{self.tp1_ratio * self.rr:.3f}). TP1 distance from entry must be "
                f"at least as far as the stop loss distance."
            )
        if self.ref_lsi_gap_entry_edge not in {"near", "far"}:
            raise ValueError(
                "ref_lsi_gap_entry_edge must be either 'near' or 'far' "
                f"(got {self.ref_lsi_gap_entry_edge!r})"
            )
        if self.limit_cancel_on_pre_entry_target_touch not in {"", "tp1", "tp2"}:
            raise ValueError(
                "limit_cancel_on_pre_entry_target_touch must be one of '', 'tp1', or 'tp2' "
                f"(got {self.limit_cancel_on_pre_entry_target_touch!r})"
            )
        if self.continuation_fvg_selection not in {"first", "extreme"}:
            raise ValueError(
                "continuation_fvg_selection must be one of 'first' or 'extreme' "
                f"(got {self.continuation_fvg_selection!r})"
            )
        if self.orb_trade_max_per_session < 0:
            raise ValueError(
                "orb_trade_max_per_session must be >= 0 "
                f"(got {self.orb_trade_max_per_session!r})"
            )
        if self.orb_reentry_policy not in ALLOWED_ORB_REENTRY_POLICIES:
            raise ValueError(
                "orb_reentry_policy must be one of "
                f"{list(ALLOWED_ORB_REENTRY_POLICIES)} "
                f"(got {self.orb_reentry_policy!r})"
            )
        if self.wide_stop_target_threshold_points < 0:
            raise ValueError(
                "wide_stop_target_threshold_points must be >= 0 "
                f"(got {self.wide_stop_target_threshold_points!r})"
            )
        if self.wide_stop_target_rr < 0:
            raise ValueError(
                "wide_stop_target_rr must be >= 0 "
                f"(got {self.wide_stop_target_rr!r})"
            )
        if self.wide_stop_target_rr > 0:
            if self.wide_stop_target_rr < 1.0:
                raise ValueError(
                    "wide_stop_target_rr must be >= 1.0 when enabled "
                    f"(got {self.wide_stop_target_rr!r})"
                )
            if self.wide_stop_target_rr > self.rr:
                raise ValueError(
                    "wide_stop_target_rr must be <= rr because it is a target-reduction rule "
                    f"(got wide_stop_target_rr={self.wide_stop_target_rr!r}, rr={self.rr!r})"
                )
        invalid_ref_levels = sorted(set(self.ref_lsi_reference_levels) - set(ALLOWED_REF_LSI_LEVELS))
        if invalid_ref_levels:
            raise ValueError(
                f"ref_lsi_reference_levels contains unsupported levels {invalid_ref_levels}; "
                f"supported levels are {list(ALLOWED_REF_LSI_LEVELS)}"
            )
        if self.strategy == "reference_lsi" and not self.ref_lsi_reference_levels:
            raise ValueError("ref_lsi_reference_levels must contain at least one level for reference_lsi.")
        invalid_htf_ref_levels = sorted(set(self.htf_lsi_reference_levels) - set(ALLOWED_REF_LSI_LEVELS))
        if invalid_htf_ref_levels:
            raise ValueError(
                f"htf_lsi_reference_levels contains unsupported levels {invalid_htf_ref_levels}; "
                f"supported levels are {list(ALLOWED_REF_LSI_LEVELS)}"
            )
        if (
            self.strategy == "htf_lsi"
            and not self.htf_lsi_include_htf_levels
            and not self.htf_lsi_include_eqhl_levels
            and not self.htf_lsi_reference_levels
        ):
            raise ValueError(
                "htf_lsi must enable at least one sweep source via "
                "htf_lsi_include_htf_levels, htf_lsi_include_eqhl_levels, "
                "or htf_lsi_reference_levels."
            )
        if self.data_sweep_min_daily_atr_pct < 0:
            raise ValueError(
                "data_sweep_min_daily_atr_pct must be >= 0 "
                f"(got {self.data_sweep_min_daily_atr_pct!r})"
            )
        invalid_data_sweep_event_types = sorted(
            {
                str(event_type).strip().upper()
                for event_type in self.data_sweep_event_types
                if str(event_type).strip()
            }
            - set(ALLOWED_DATA_SWEEP_EVENT_TYPES)
        )
        if invalid_data_sweep_event_types:
            raise ValueError(
                "data_sweep_event_types contains unsupported values "
                f"{invalid_data_sweep_event_types}; supported types are "
                f"{list(ALLOWED_DATA_SWEEP_EVENT_TYPES)}"
            )
        if self.data_sweep_release_window_minutes < 0:
            raise ValueError(
                "data_sweep_release_window_minutes must be >= 0 "
                f"(got {self.data_sweep_release_window_minutes!r})"
            )
        if self.lsi_sweep_gate not in {"sweep_window", "entry", "rth"}:
            raise ValueError(
                "lsi_sweep_gate must be one of 'sweep_window', 'entry', or 'rth' "
                f"(got {self.lsi_sweep_gate!r})"
            )
        if self.lsi_stop_mode not in {
            "absolute",
            "fvg",
            "gap_1x",
            "gap_2x",
            "gap_3x",
            "gap_4x",
            "struct_50pct",
            "struct_75pct",
            "atr_pct",
            "orb_pct",
        }:
            raise ValueError(
                "lsi_stop_mode must be one of 'absolute', 'fvg', 'gap_1x', "
                "'gap_2x', 'gap_3x', 'gap_4x', 'struct_50pct', 'struct_75pct', "
                "'atr_pct', or 'orb_pct' "
                f"(got {self.lsi_stop_mode!r})"
            )
        if self.lsi_target_mode not in {"risk", "structural", "left_structure"}:
            raise ValueError(
                "lsi_target_mode must be one of 'risk', 'structural', or 'left_structure' "
                f"(got {self.lsi_target_mode!r})"
            )
        if self.lsi_entry_mode not in {"close", "fvg_limit", "level_limit", "timed_hybrid"}:
            raise ValueError(
                "lsi_entry_mode must be one of 'close', 'fvg_limit', 'level_limit', "
                "or 'timed_hybrid' "
                f"(got {self.lsi_entry_mode!r})"
            )
        if self.lsi_close_on_sweep_to_inversion_minutes < 0:
            raise ValueError(
                "lsi_close_on_sweep_to_inversion_minutes must be >= 0 "
                f"(got {self.lsi_close_on_sweep_to_inversion_minutes!r})"
            )
        if (
            self.lsi_entry_mode == "timed_hybrid"
            and self.lsi_close_on_sweep_to_inversion_minutes <= 0
        ):
            raise ValueError(
                "lsi_close_on_sweep_to_inversion_minutes must be > 0 when "
                "lsi_entry_mode == 'timed_hybrid'"
            )
        if self.lsi_confirmation_mode not in ALLOWED_LSI_CONFIRMATION_MODES:
            raise ValueError(
                "lsi_confirmation_mode must be one of "
                f"{list(ALLOWED_LSI_CONFIRMATION_MODES)} "
                f"(got {self.lsi_confirmation_mode!r})"
            )
        if self.cisd_min_leg_bars < 1:
            raise ValueError(
                "cisd_min_leg_bars must be >= 1 "
                f"(got {self.cisd_min_leg_bars!r})"
            )
        if self.cisd_min_leg_atr_pct < 0:
            raise ValueError(
                "cisd_min_leg_atr_pct must be >= 0 "
                f"(got {self.cisd_min_leg_atr_pct!r})"
            )
        if self.cisd_max_leg_bars < 0:
            raise ValueError(
                "cisd_max_leg_bars must be >= 0 "
                f"(got {self.cisd_max_leg_bars!r})"
            )
        if self.lsi_lrlr_gate not in {"", "require", "exclude"}:
            raise ValueError(
                "lsi_lrlr_gate must be one of '', 'require', or 'exclude' "
                f"(got {self.lsi_lrlr_gate!r})"
            )
        if self.lsi_lrlr_swing_n_left < 1:
            raise ValueError(
                "lsi_lrlr_swing_n_left must be >= 1 "
                f"(got {self.lsi_lrlr_swing_n_left!r})"
            )
        if self.lsi_lrlr_swing_n_right < 1:
            raise ValueError(
                "lsi_lrlr_swing_n_right must be >= 1 "
                f"(got {self.lsi_lrlr_swing_n_right!r})"
            )
        if self.lsi_lrlr_min_pivots < 1:
            raise ValueError(
                "lsi_lrlr_min_pivots must be >= 1 "
                f"(got {self.lsi_lrlr_min_pivots!r})"
            )
        if self.lsi_lrlr_lookback_minutes < 1:
            raise ValueError(
                "lsi_lrlr_lookback_minutes must be >= 1 "
                f"(got {self.lsi_lrlr_lookback_minutes!r})"
            )
        if self.lsi_lrlr_max_pivot_gap_minutes < 1:
            raise ValueError(
                "lsi_lrlr_max_pivot_gap_minutes must be >= 1 "
                f"(got {self.lsi_lrlr_max_pivot_gap_minutes!r})"
            )
        if self.lsi_lrlr_max_cluster_span_minutes < self.lsi_lrlr_max_pivot_gap_minutes:
            raise ValueError(
                "lsi_lrlr_max_cluster_span_minutes must be >= "
                "lsi_lrlr_max_pivot_gap_minutes"
            )
        if self.lsi_lrlr_max_price_span_atr <= 0.0:
            raise ValueError(
                "lsi_lrlr_max_price_span_atr must be > 0 "
                f"(got {self.lsi_lrlr_max_price_span_atr!r})"
            )
        if self.lsi_lrlr_monotonic_tolerance_atr < 0.0:
            raise ValueError(
                "lsi_lrlr_monotonic_tolerance_atr must be >= 0 "
                f"(got {self.lsi_lrlr_monotonic_tolerance_atr!r})"
            )
        if self.lsi_lrlr_line_tolerance_atr < 0.0:
            raise ValueError(
                "lsi_lrlr_line_tolerance_atr must be >= 0 "
                f"(got {self.lsi_lrlr_line_tolerance_atr!r})"
            )
        if self.lsi_lrlr_tp1_buffer_atr < 0.0:
            raise ValueError(
                "lsi_lrlr_tp1_buffer_atr must be >= 0 "
                f"(got {self.lsi_lrlr_tp1_buffer_atr!r})"
            )
        if self.htf_level_tf_minutes not in {30, 60, 90}:
            raise ValueError(
                "htf_level_tf_minutes must be one of 30, 60, or 90 "
                f"(got {self.htf_level_tf_minutes!r})"
            )
        if self.htf_n_left < 1:
            raise ValueError(f"htf_n_left must be >= 1 (got {self.htf_n_left!r})")
        if self.htf_trade_max_per_session not in {0, 1, 2, 3}:
            raise ValueError(
                "htf_trade_max_per_session must be one of 0, 1, 2, or 3 "
                f"(got {self.htf_trade_max_per_session!r})"
            )
        if self.htf_lsi_inversion_ordinal < 1:
            raise ValueError(
                "htf_lsi_inversion_ordinal must be >= 1 "
                f"(got {self.htf_lsi_inversion_ordinal!r})"
            )
        if self.eqhl_level_tf_minutes not in {5, 15, 60}:
            raise ValueError(
                "eqhl_level_tf_minutes must be one of 5, 15, or 60 "
                f"(got {self.eqhl_level_tf_minutes!r})"
            )
        if self.eqhl_n_left < 1:
            raise ValueError(f"eqhl_n_left must be >= 1 (got {self.eqhl_n_left!r})")
        if self.eqhl_tolerance_ticks < 0:
            raise ValueError(
                "eqhl_tolerance_ticks must be >= 0 "
                f"(got {self.eqhl_tolerance_ticks!r})"
            )
        if self.eqhl_min_touches < 2:
            raise ValueError(
                "eqhl_min_touches must be >= 2 "
                f"(got {self.eqhl_min_touches!r})"
            )
        if self.eqhl_lookback_bars < 0:
            raise ValueError(
                "eqhl_lookback_bars must be >= 0 "
                f"(got {self.eqhl_lookback_bars!r})"
            )
        if self.max_fvg_to_inversion_bars < 0:
            raise ValueError(
                "max_fvg_to_inversion_bars must be >= 0 "
                f"(got {self.max_fvg_to_inversion_bars!r})"
            )
        if self.entry_context_gate:
            if not self.entry_context_gate.endswith("_aligned"):
                raise ValueError(
                    "entry_context_gate must end with '_aligned' when enabled "
                    f"(got {self.entry_context_gate!r})"
                )
            gate_prefix = self.entry_context_gate[: -len("_aligned")]
            gate_tokens = tuple(token for token in gate_prefix.split("_") if token)
            if not gate_tokens:
                raise ValueError("entry_context_gate must include at least one indicator token.")
            invalid_tokens = sorted(set(gate_tokens) - ENTRY_CONTEXT_TOKENS)
            if invalid_tokens:
                raise ValueError(
                    f"entry_context_gate contains unsupported tokens {invalid_tokens}; "
                    f"supported tokens are {sorted(ENTRY_CONTEXT_TOKENS)}"
                )
            if self.entry_context_max_atr <= self.entry_context_min_atr:
                raise ValueError(
                    "entry_context_max_atr must be > entry_context_min_atr when "
                    "entry_context_gate is enabled."
                )

    @property
    def point_value(self) -> float:
        if self.instrument is None:
            return 20.0  # default NQ
        return self.instrument.point_value

    @property
    def min_tick(self) -> float:
        if self.instrument is None:
            return 0.25  # default NQ
        return self.instrument.min_tick

    @property
    def commission_per_contract(self) -> float:
        if self.instrument is None:
            return 0.05
        return self.instrument.commission


def with_overrides(config: StrategyConfig, **kwargs) -> StrategyConfig:
    """Create a new config with overrides. Supports dot-notation for session params.

    Examples:
        with_overrides(cfg, rr=3.0)
        with_overrides(cfg, ny_stop_atr_pct=12.0)
    """
    session_overrides: dict[str, dict[str, float]] = {}
    direct_overrides: dict = {}

    for key, value in kwargs.items():
        # Check for session-prefixed params like ny_stop_atr_pct
        for sess in ("ny", "asia", "ldn"):
            prefix = f"{sess}_"
            if key.startswith(prefix):
                param_name = key[len(prefix):]
                session_overrides.setdefault(sess, {})[param_name] = value
                break
        else:
            direct_overrides[key] = value

    if session_overrides:
        new_sessions = []
        for sess in config.sessions:
            sess_key = sess.name.lower()
            if sess_key in session_overrides:
                new_sessions.append(replace(sess, **session_overrides[sess_key]))
            else:
                new_sessions.append(sess)
        direct_overrides["sessions"] = tuple(new_sessions)

    return replace(config, **direct_overrides)


# ---------------------------------------------------------------------------
# Default session configs (matching HEAD_testing_a.pine defaults)
# ---------------------------------------------------------------------------

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=7.5,
    min_gap_atr_pct=2.25,
)

ASIA_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=5.25,
    min_gap_atr_pct=0.9,
)

LDN_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:15",
    entry_start="03:15",
    entry_end="08:25",
    flat_start="08:20",
    flat_end="08:25",
    stop_atr_pct=10.0,
    min_gap_atr_pct=1.0,
)


IB_NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="10:30",
    entry_start="10:30",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
)


def ib_config(instrument: Instrument | None = None) -> StrategyConfig:
    """Create default IB mean-reversion config. 1:1 R:R, $1000 risk."""
    from .data.instruments import NQ

    inst = instrument or NQ
    return StrategyConfig(
        strategy="ib",
        rr=1.0,
        tp1_ratio=1.0,
        risk_usd=1000.0,
        sessions=(IB_NY_SESSION,),
        instrument=inst,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def default_config(instrument: Instrument | None = None) -> StrategyConfig:
    """Create default config with NY session. Uses dataclass defaults for all params."""
    from .data.instruments import NQ

    inst = instrument or NQ
    return StrategyConfig(
        sessions=(NY_SESSION,),
        instrument=inst,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )
