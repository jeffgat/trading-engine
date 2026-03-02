"""VWAP Reversion strategy configuration as frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .config import Instrument


@dataclass(frozen=True)
class VWAPSessionConfig:
    """Per-session parameters for VWAP Reversion strategy."""

    name: str  # "NY", "Asia", "LDN"

    # VWAP anchor
    vwap_anchor: str = "session"  # always session-anchored VWAP

    # When session data begins (HH:MM). If empty, defaults to entry_start.
    # For cross-midnight sessions (e.g. Asia), this should be set to the
    # actual session open time so that session-day boundaries are correct.
    session_open: str = ""

    # Time windows (HH:MM in exchange_tz)
    entry_start: str = "09:35"
    entry_end: str = "12:00"
    flat_start: str = "15:50"
    flat_end: str = "16:00"

    # Deviation threshold as % of daily ATR (for mode="atr")
    deviation_atr_pct: float = 30.0
    # Number of std devs for bands (for mode="std")
    deviation_std: float = 2.0
    # "atr" or "std"
    deviation_mode: str = "atr"

    # Rejection candle mode: "close" or "pinbar"
    rejection_mode: str = "close"

    # Stop buffer as % of daily ATR (added beyond rejection candle extreme)
    stop_atr_pct: float = 0.0

    # Pinbar parameters (% of ATR)
    min_wick_atr_pct: float = 0.0  # pinbar min wick length as % of ATR
    max_body_atr_pct: float = 0.0  # pinbar max body size as % of ATR

    # Minimum distance floors in points (0 = disabled)
    min_stop_points: float = 0.0
    min_tp1_points: float = 0.0


@dataclass(frozen=True)
class VWAPStrategyConfig:
    """Complete VWAP Reversion strategy configuration. All optimizable params live here."""

    # Risk parameters
    risk_usd: float = 5000.0
    rr: float = 2.5
    tp1_ratio: float = 0.5
    min_qty: float = 1.0
    qty_step: float = 1.0

    # ATR
    atr_length: int = 14

    # TP2 mode: "fixed_rr" uses standard R:R target, "vwap" exits at VWAP touch
    tp2_mode: str = "fixed_rr"

    # Session configs
    sessions: tuple[VWAPSessionConfig, ...] = field(default_factory=tuple)

    # Instrument
    instrument: Instrument = field(default=None)

    # Half-day dates (YYYYMMDD strings) -- NY only
    half_days: tuple[str, ...] = field(default_factory=tuple)

    # Excluded dates (YYYYMMDD strings)
    excluded_dates: tuple[str, ...] = field(default_factory=tuple)

    # Direction filter: "both", "long", or "short" -- restricts which trade directions are taken
    direction_filter: str = "both"

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


def with_vwap_overrides(config: VWAPStrategyConfig, **kwargs) -> VWAPStrategyConfig:
    """Create a new config with overrides. Supports dot-notation for session params.

    Examples:
        with_vwap_overrides(cfg, rr=3.0)
        with_vwap_overrides(cfg, ny_deviation_atr_pct=25.0)
    """
    session_overrides: dict[str, dict[str, float]] = {}
    direct_overrides: dict = {}

    for key, value in kwargs.items():
        # Check for session-prefixed params like ny_deviation_atr_pct
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
# Default VWAP session configs
# ---------------------------------------------------------------------------

NY_VWAP_SESSION = VWAPSessionConfig(
    name="NY",
    vwap_anchor="session",
    session_open="09:30",
    entry_start="09:35",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    deviation_atr_pct=30.0,
    deviation_std=2.0,
    deviation_mode="atr",
    rejection_mode="close",
    stop_atr_pct=0.0,
    min_wick_atr_pct=0.0,
    max_body_atr_pct=0.0,
)

ASIA_VWAP_SESSION = VWAPSessionConfig(
    name="Asia",
    vwap_anchor="session",
    session_open="20:00",
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    deviation_atr_pct=25.0,
    deviation_std=2.0,
    deviation_mode="atr",
    rejection_mode="close",
    stop_atr_pct=0.0,
)

LDN_VWAP_SESSION = VWAPSessionConfig(
    name="LDN",
    vwap_anchor="session",
    session_open="03:00",
    entry_start="03:15",
    entry_end="08:20",
    flat_start="08:20",
    flat_end="08:25",
    deviation_atr_pct=25.0,
    deviation_std=2.0,
    deviation_mode="atr",
    rejection_mode="close",
    stop_atr_pct=0.0,
)


def default_vwap_config(instrument: Instrument | None = None) -> VWAPStrategyConfig:
    """Create default VWAP config with NY session. Uses dataclass defaults for all params."""
    from .data.instruments import NQ

    inst = instrument or NQ
    return VWAPStrategyConfig(
        sessions=(NY_VWAP_SESSION,),
        instrument=inst,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )
