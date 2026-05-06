"""Execution fee schedules used by the backtesting instrument registry."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FeeSchedule:
    """Per-contract execution fees.

    The ranges are per side. Backtests use the midpoint as the reproducible
    default estimate and subtract two sides per filled round trip.
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
    "MNQ": FeeSchedule(
        symbol="MNQ",
        per_side_min=0.50,
        per_side_max=0.65,
        notes="Very common scalping contract",
    ),
    "MES": FeeSchedule(
        symbol="MES",
        per_side_min=0.50,
        per_side_max=0.65,
        notes="Slightly slower/cleaner than MNQ",
    ),
    "MGC": FeeSchedule(
        symbol="MGC",
        per_side_min=0.75,
        per_side_max=0.90,
        notes="COMEX fees are higher",
    ),
    "MCL": FeeSchedule(
        symbol="MCL",
        per_side_min=0.70,
        per_side_max=0.85,
        notes="NYMEX fees higher plus thinner liquidity",
    ),
}


def get_fee_schedule(symbol: str) -> FeeSchedule | None:
    """Return the configured execution fee schedule for ``symbol``."""
    return MICRO_FEE_SCHEDULES.get(symbol.upper())


def estimated_commission_per_side(symbol: str, fallback: float = 0.05) -> float:
    """Return per-contract, per-side commission used by the simulator."""
    schedule = get_fee_schedule(symbol)
    if schedule is None:
        return fallback
    return schedule.per_side_midpoint
