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
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
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
    # "lsi", "reference_lsi", or "ib"
    strategy: str = "continuation"

    # Direction filter: "both", "long", or "short" — restricts which trade directions are taken
    direction_filter: str = "both"

    # Reverse direction: flip all signal directions (long→short, short→long)
    reverse_direction: bool = False

    # Allow FVGs inside ORB range when the impulse candle (bar[1]) closes outside
    impulse_close_filter: bool = False

    # Bar magnifier: use 1m sub-bars for fill/exit simulation
    use_bar_magnifier: bool = True

    # n-bar swing pivot width for liquidity sweep detection (10 = 10 bars left + 10 bars right)
    swing_n_bars: int = 10

    # LSI (Liquidity Sweep Inversion) params
    lsi_n_left: int = 3       # swing left bars
    lsi_n_right: int = 3      # swing right bars (also the confirmation lag)
    lsi_fvg_window_left: int = 10   # bars BEFORE sweep where FVG can have formed (FVG → sweep)
    lsi_fvg_window_right: int = 10  # bars AFTER sweep where FVG can form (sweep → FVG)
    lsi_stop_mode: str = "absolute"  # "absolute" (full setup range) or "fvg" (FVG boundary)
    lsi_entry_mode: str = "close"    # "close" (inversion bar close) or "fvg_limit" (limit at FVG boundary)
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
        invalid_ref_levels = sorted(set(self.ref_lsi_reference_levels) - set(REF_LSI_LEVELS))
        if invalid_ref_levels:
            raise ValueError(
                f"ref_lsi_reference_levels contains unsupported levels {invalid_ref_levels}; "
                f"supported levels are {list(REF_LSI_LEVELS)}"
            )
        if self.strategy == "reference_lsi" and not self.ref_lsi_reference_levels:
            raise ValueError("ref_lsi_reference_levels must contain at least one level for reference_lsi.")
        if self.lsi_sweep_gate not in {"sweep_window", "entry", "rth"}:
            raise ValueError(
                "lsi_sweep_gate must be one of 'sweep_window', 'entry', or 'rth' "
                f"(got {self.lsi_sweep_gate!r})"
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
