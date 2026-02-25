"""IFVG strategy and session configuration as frozen dataclasses."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from orb_backtest.config import Instrument


@dataclass(frozen=True)
class KillzoneConfig:
    """Killzone session definition for liquidity level tracking."""

    name: str  # "Asia", "London"
    start: str  # HH:MM in NY time
    end: str  # HH:MM in NY time
    use_high_sweeps: bool = True
    use_low_sweeps: bool = True


# Default killzone presets matching HEAD_ilm.pine
ASIA_KZ = KillzoneConfig(
    name="Asia",
    start="20:00",
    end="00:00",
)

LONDON_KZ = KillzoneConfig(
    name="London",
    start="02:00",
    end="05:00",
)


@dataclass(frozen=True)
class IFVGConfig:
    """Complete IFVG reversal strategy configuration."""

    # Risk management
    risk_usd: float = 5000.0
    rr: float = 2.0
    tp1_ratio: float = 0.5
    min_qty: float = 1.0
    qty_step: float = 1.0
    be_offset_ticks: int = 4
    atr_length: int = 14

    # Session windows (HH:MM in NY time)
    entry_start: str = "08:30"
    entry_end: str = "11:30"
    flat_start: str = "15:50"
    flat_end: str = "16:00"

    # Killzone sessions
    killzones: tuple[KillzoneConfig, ...] = field(default_factory=lambda: (ASIA_KZ, LONDON_KZ))

    # PDH/PDL sweep toggles
    use_pdh_sweeps: bool = True
    use_pdl_sweeps: bool = True

    # 1H Swing high/low sweep toggles
    use_swing_high_sweeps: bool = False
    use_swing_low_sweeps: bool = False
    swing_length: int = 24  # Lookback/look-forward bars for 1H pivot detection

    # Setup parameters
    max_bars_after_sweep: int = 20
    min_gap_atr_pct: float = 2.25  # min FVG size as % of daily ATR (matches NQ NY ORB)
    gap_window_bars: int = 10
    require_singular_gap: bool = True  # Invalidate setup if a 2nd valid gap forms in the window

    # Minimum stop distance as fraction of daily ATR (0.05 = 5%)
    min_stop_atr_pct: float = 0.05

    # Max bars after gap formation for inversion to occur (0 = unlimited)
    max_inversion_bars: int = 10

    # Candle timeframe for signal detection: "1m", "3m", "5m", "15m"
    candle_tf: str = "1m"

    # Direction filter: "both", "long", "short"
    direction_filter: str = "both"

    # Entry type: "market" (enter at close on inversion) or "limit" (limit at gap edge)
    entry_type: str = "market"

    # BPR (Balanced Price Range) filter: "none" (price-close inversion),
    # "tight" (opposite FVG overlap within bpr_tight_max_bars), "loose" (any overlap)
    bpr_filter: str = "none"
    bpr_tight_max_bars: int = 4  # max bars between original FVG bar[0] and inverting FVG bar[2]

    # Instrument
    instrument: Instrument = field(default=None)

    # Bar magnifier: use 1m sub-bars for exit simulation
    use_bar_magnifier: bool = True

    # Excluded dates (YYYYMMDD strings)
    excluded_dates: tuple[str, ...] = field(default_factory=tuple)

    # Experiment metadata
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


def with_overrides(config: IFVGConfig, **kwargs) -> IFVGConfig:
    """Create a new config with overrides.

    Supports killzone-prefixed params:
        asia_use_high_sweeps=False
        london_use_low_sweeps=True
    """
    kz_overrides: dict[str, dict[str, object]] = {}
    direct_overrides: dict = {}

    for key, value in kwargs.items():
        for kz_name in ("asia", "london"):
            prefix = f"{kz_name}_"
            if key.startswith(prefix):
                param_name = key[len(prefix):]
                kz_overrides.setdefault(kz_name, {})[param_name] = value
                break
        else:
            direct_overrides[key] = value

    if kz_overrides:
        new_kzs = []
        for kz in config.killzones:
            kz_key = kz.name.lower()
            if kz_key in kz_overrides:
                new_kzs.append(replace(kz, **kz_overrides[kz_key]))
            else:
                new_kzs.append(kz)
        direct_overrides["killzones"] = tuple(new_kzs)

    return replace(config, **direct_overrides)


def default_config(instrument: Instrument | None = None) -> IFVGConfig:
    """Create default IFVG config. Uses dataclass defaults for all params."""
    from orb_backtest.data.instruments import NQ

    inst = instrument or NQ
    return IFVGConfig(instrument=inst)
