"""Gap Fill strategy configuration as frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .config import Instrument


@dataclass(frozen=True)
class GapFillSessionConfig:
    """Per-session parameters for Gap Fill strategy."""

    name: str  # "NY"

    # RTH open time (HH:MM) — gap is measured at this bar
    rth_open: str = "09:30"

    # Flat/EOD window
    flat_start: str = "15:50"
    flat_end: str = "16:00"

    # For cross-midnight sessions (e.g. Asia), set actual session open
    session_open: str = ""


@dataclass(frozen=True)
class GapFillStrategyConfig:
    """Complete Gap Fill strategy configuration."""

    # Gap filters
    min_gap_atr_pct: float = 5.0   # min gap size as % of daily ATR
    max_gap_atr_pct: float = 100.0  # max gap size as % of daily ATR
    min_gap_points: float = 0.0     # absolute min gap size in points (0 = disabled)

    # Risk parameters
    stop_multiplier: float = 1.0  # stop = stop_multiplier × gap_size beyond open
    tp1_ratio: float = 0.5       # partial exit at tp1_ratio × gap_size toward prior close
    risk_usd: float = 5000.0
    min_qty: float = 1.0
    qty_step: float = 1.0

    # ATR
    atr_length: int = 14

    # Max staleness: skip if prior RTH close is > N calendar days ago
    max_gap_staleness_days: int = 5

    # Direction filter: "both", "long", or "short"
    direction_filter: str = "both"

    # Session configs
    sessions: tuple[GapFillSessionConfig, ...] = field(default_factory=tuple)

    # Instrument
    instrument: Instrument = field(default=None)

    # Half-day dates (YYYYMMDD strings)
    half_days: tuple[str, ...] = field(default_factory=tuple)

    # Excluded dates (YYYYMMDD strings)
    excluded_dates: tuple[str, ...] = field(default_factory=tuple)

    # Bar magnifier
    use_bar_magnifier: bool = True

    # Experiment metadata
    name: str = ""
    notes: str = ""

    @property
    def point_value(self) -> float:
        if self.instrument is None:
            return 50.0  # default ES
        return self.instrument.point_value

    @property
    def min_tick(self) -> float:
        if self.instrument is None:
            return 0.25
        return self.instrument.min_tick

    @property
    def commission_per_contract(self) -> float:
        if self.instrument is None:
            return 0.05
        return self.instrument.commission


def with_gapfill_overrides(config: GapFillStrategyConfig, **kwargs) -> GapFillStrategyConfig:
    """Create a new config with overrides. Supports session-prefixed params.

    Examples:
        with_gapfill_overrides(cfg, stop_multiplier=1.5)
        with_gapfill_overrides(cfg, ny_rth_open="09:30")
    """
    session_overrides: dict[str, dict[str, float]] = {}
    direct_overrides: dict = {}

    for key, value in kwargs.items():
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
# Default Gap Fill session configs
# ---------------------------------------------------------------------------

NY_GAPFILL_SESSION = GapFillSessionConfig(
    name="NY",
    rth_open="09:30",
    flat_start="15:50",
    flat_end="16:00",
)


def default_gapfill_config(instrument: Instrument | None = None) -> GapFillStrategyConfig:
    """Create default Gap Fill config with NY session."""
    from .data.instruments import ES

    inst = instrument or ES
    return GapFillStrategyConfig(
        sessions=(NY_GAPFILL_SESSION,),
        instrument=inst,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )
