"""Position sizing and trade level computation.

Supports the 5-leg combined longs portfolio:
  - ATR-based stops (NQ NY, GC NY, ES NY)
  - ORB-based stops (NQ Asia, ES Asia)
  - Dual floor clamping (ES NY, ES Asia)
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


def _floor_to_step(x: float, step: float, round_up_threshold: float = 0.7) -> float:
    """Round to nearest step, rounding up when fractional part >= threshold."""
    if step <= 0:
        return x
    ratio = x / step
    if ratio - math.floor(ratio) >= round_up_threshold:
        return math.ceil(ratio) * step
    return math.floor(ratio) * step


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
    *,
    stop_basis: str = "atr",
    orb_range: float = 0.0,
    stop_orb_pct: float = 0.0,
    min_stop_pts: float = 0.0,
    min_tp1_pts: float = 0.0,
    max_single_risk_usd: float = 500.0,
    qty_multiplier: float = 1.0,
    target_rr: float | None = None,
    wide_stop_target_threshold_points: float = 0.0,
    wide_stop_target_rr: float = 0.0,
) -> TradeLevels | None:
    """Compute all trade levels and position size.

    Returns None if the computed quantity is below min_qty.

    Args:
        entry: Limit entry price (FVG top for longs, bottom for shorts).
        direction: +1 for long, -1 for short.
        gap_size: FVG gap size in points.
        daily_atr: Current daily ATR value.
        stop_atr_pct: Stop distance as % of daily ATR (used when stop_basis="atr").
        rr: Reward/risk ratio.
        tp1_ratio: Fraction of full target for TP1 (e.g., 0.5).
        risk_usd: Risk per trade in USD.
        point_value: Dollar value per point (e.g., 2.0 for MNQ, 20.0 for NQ).
        min_qty: Minimum contract quantity.
        qty_step: Contract quantity increment.
        be_offset_ticks: Ticks above/below entry for breakeven stop.
        min_tick: Minimum price increment.
        stop_basis: "atr" or "orb" — how to compute stop distance.
        orb_range: ORB high - ORB low (required when stop_basis="orb").
        stop_orb_pct: Stop distance as % of ORB range (used when stop_basis="orb").
        min_stop_pts: Minimum stop distance in points (dual floor, ES only).
        min_tp1_pts: Minimum TP1 distance in points (dual floor, ES only).
        max_single_risk_usd: Max dollar risk for a 1-contract override when
            risk_usd isn't enough for 1 contract. Defaults to $500.
    """
    # Compute stop distance based on basis
    if stop_basis == "orb":
        stop_dist = (stop_orb_pct / 100.0) * orb_range
    else:
        stop_dist = (stop_atr_pct / 100.0) * daily_atr

    # Dual floor: clamp stop distance to minimum points
    if min_stop_pts > 0:
        stop_dist = max(stop_dist, min_stop_pts)

    stop = entry - stop_dist * direction
    risk_pts = abs(entry - stop)

    if risk_pts <= 0:
        return None

    # Position sizing
    qty_raw = risk_usd / (risk_pts * point_value)
    qty = _floor_to_step(qty_raw, qty_step)

    if qty < min_qty:
        # 1 contract exceeds risk_usd — allow if dollar risk <= max_single_risk_usd
        single_risk = risk_pts * point_value * min_qty
        if single_risk <= max_single_risk_usd:
            qty = min_qty
        else:
            return None

    # Apply qty multiplier (e.g. 2x for LSI strategy)
    if qty_multiplier != 1.0:
        qty = _floor_to_step(qty * qty_multiplier, qty_step)
        qty = max(qty, min_qty)

    is_single = qty <= min_qty
    if is_single:
        half_qty = qty
    else:
        half_qty = _floor_to_step(qty / 2, qty_step)
        half_qty = max(half_qty, min_qty)

    # Price levels
    effective_rr = rr if target_rr is None else target_rr
    if (
        target_rr is None
        and wide_stop_target_threshold_points > 0.0
        and wide_stop_target_rr > 0.0
        and risk_pts >= wide_stop_target_threshold_points
    ):
        effective_rr = min(rr, wide_stop_target_rr)
    tp1_dist = effective_rr * risk_pts * tp1_ratio

    # Dual floor: clamp TP1 distance to minimum points
    if min_tp1_pts > 0:
        tp1_dist = max(tp1_dist, min_tp1_pts)

    tp1 = entry + tp1_dist * direction
    tp2 = entry + (effective_rr * risk_pts) * direction
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
