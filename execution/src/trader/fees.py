"""Execution fee schedules for live and exact-replay accounting."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    """Per-contract execution fees.

    The ranges are per side. Exact replays use the midpoint as the default
    estimate and subtract two sides per filled round trip.
    """

    symbol: str
    per_side_min: float
    per_side_max: float
    notes: str = ""

    @property
    def per_side_midpoint(self) -> float:
        return (self.per_side_min + self.per_side_max) / 2.0

    @property
    def round_turn_midpoint(self) -> float:
        return self.per_side_midpoint * 2.0


MICRO_FEE_SCHEDULES: dict[str, FeeSchedule] = {
    "MNQ": FeeSchedule("MNQ", 0.50, 0.65, "Very common scalping contract"),
    "MES": FeeSchedule("MES", 0.50, 0.65, "Slightly slower/cleaner than MNQ"),
    "MGC": FeeSchedule("MGC", 0.75, 0.90, "COMEX fees are higher"),
    "MCL": FeeSchedule("MCL", 0.70, 0.85, "NYMEX fees higher plus thinner liquidity"),
}


def get_fee_schedule(symbol: str) -> FeeSchedule | None:
    return MICRO_FEE_SCHEDULES.get(symbol.upper())


def estimated_commission_per_side(symbol: str, fallback: float = 0.05) -> float:
    schedule = get_fee_schedule(symbol)
    if schedule is None:
        return fallback
    return schedule.per_side_midpoint
