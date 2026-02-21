"""Strategy and session configuration as frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace


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
    """Per-session parameters. Maps 1:1 to Pine Script input groups."""

    name: str  # "NY", "Asia", "LDN"

    # Time windows (HH:MM in exchange_tz)
    orb_start: str
    orb_end: str
    entry_start: str
    entry_end: str
    flat_start: str
    flat_end: str

    # ATR-based parameters
    stop_atr_pct: float  # stop distance as % of daily ATR
    min_gap_atr_pct: float  # min FVG size as % of daily ATR
    max_gap_points: float  # max FVG size in points (0 = no limit)
    max_gap_atr_pct: float = 0.0  # max FVG size as % of daily ATR (0 = no limit)
    qualifying_move_atr_pct: float = 0.0  # min upward extension as % of ATR for inversion shorts (0 = disabled)


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

    # Session configs
    sessions: tuple[SessionConfig, ...] = field(default_factory=tuple)

    # Instrument
    instrument: Instrument = field(default=None)

    # Half-day dates (YYYYMMDD strings) — NY only
    half_days: tuple[str, ...] = field(default_factory=tuple)

    # Excluded dates (YYYYMMDD strings)
    excluded_dates: tuple[str, ...] = field(default_factory=tuple)

    # Strategy type: "continuation", "reversal", "inversion", or "cisd"
    strategy: str = "continuation"

    # Direction filter: "both", "long", or "short" — restricts which trade directions are taken
    direction_filter: str = "both"

    # Allow FVGs inside ORB range when the impulse candle (bar[1]) closes outside
    impulse_close_filter: bool = False

    # Bar magnifier: use 1m sub-bars for fill/exit simulation
    use_bar_magnifier: bool = True

    # Experiment metadata (not used in simulation, just for labeling results)
    name: str = ""
    notes: str = ""

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
    max_gap_points=100.0,
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
    max_gap_points=50.0,
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
    max_gap_points=50.0,
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
