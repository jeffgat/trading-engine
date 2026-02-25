"""Position sizing and trade level computation.

Matches the Pine Script logic in HEAD_prod_nq_ny_asia.pine exactly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class TradeLevels:
    """Computed trade levels for a single setup."""

    entry: float
    stop: float
    tp1: float
    tp2: float
    be: float  # breakeven stop price
    qty: float
    half_qty: float
    is_single_contract: bool
    risk_pts: float
    direction: int  # +1 long, -1 short
    gap_size: float


def _floor_to_step(x: float, step: float) -> float:
    """Floor a value to the nearest step increment."""
    if step <= 0:
        return x
    return math.floor(x / step) * step


def compute_trade_levels(
    entry: float,
    direction: int,
    gap_size: float,
    daily_atr: float,
    stop_atr_pct: float,
    rr: float,
    tp1_ratio: float,
    risk_usd: float,
    point_value: float,
    min_qty: float,
    qty_step: float,
    be_offset_ticks: int,
    min_tick: float,
) -> TradeLevels | None:
    """Compute all trade levels and position size.

    Returns None if the computed quantity is below min_qty.

    Args:
        entry: Limit entry price (FVG top for longs, bottom for shorts).
        direction: +1 for long, -1 for short.
        gap_size: FVG gap size in points.
        daily_atr: Current daily ATR value.
        stop_atr_pct: Stop distance as % of daily ATR.
        rr: Reward/risk ratio.
        tp1_ratio: Fraction of full target for TP1 (e.g., 0.5).
        risk_usd: Risk per trade in USD.
        point_value: Dollar value per point (e.g., 2.0 for MNQ, 20.0 for NQ).
        min_qty: Minimum contract quantity.
        qty_step: Contract quantity increment.
        be_offset_ticks: Ticks above/below entry for breakeven stop.
        min_tick: Minimum price increment.
    """
    stop_dist = (stop_atr_pct / 100.0) * daily_atr
    stop = entry - stop_dist * direction
    risk_pts = abs(entry - stop)

    if risk_pts <= 0:
        return None

    # Position sizing
    qty_raw = risk_usd / (risk_pts * point_value)
    qty = _floor_to_step(qty_raw, qty_step)

    if qty < min_qty:
        return None

    is_single = qty <= min_qty
    if is_single:
        half_qty = qty
    else:
        half_qty = _floor_to_step(qty / 2, qty_step)
        half_qty = max(half_qty, min_qty)

    # Price levels
    tp1 = entry + (rr * risk_pts * tp1_ratio) * direction
    tp2 = entry + (rr * risk_pts) * direction
    be_offset = be_offset_ticks * min_tick
    be = entry + be_offset * direction

    return TradeLevels(
        entry=entry,
        stop=stop,
        tp1=tp1,
        tp2=tp2,
        be=be,
        qty=qty,
        half_qty=half_qty,
        is_single_contract=is_single,
        risk_pts=risk_pts,
        direction=direction,
        gap_size=gap_size,
    )
