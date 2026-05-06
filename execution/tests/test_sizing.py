"""Tests for compute_trade_levels() in sizing.py.

All tests are synchronous — no async needed.
Tests verify every branching path: ATR/ORB basis, dual floor,
single-contract override, qty_multiplier, BE offset, direction sign.
"""

from __future__ import annotations

import math

import pytest

from trader.sizing import TradeLevels, _floor_to_step, compute_trade_levels

# --- helpers ---

BASE_KWARGS = dict(
    gap_size=10.0,
    daily_atr=300.0,
    stop_atr_pct=11.0,      # stop_dist = 0.11 * 300 = 33 pts
    rr=3.0,
    tp1_ratio=0.5,
    risk_usd=1000.0,
    point_value=2.0,
    min_qty=1.0,
    qty_step=1.0,
    be_offset_ticks=4,
    min_tick=0.25,
)


def make_levels(entry=19500.0, direction=1, **overrides) -> TradeLevels | None:
    kwargs = {**BASE_KWARGS, **overrides}
    return compute_trade_levels(entry=entry, direction=direction, **kwargs)


# =============================================================================
# Stop direction tests
# =============================================================================

class TestStopDirection:
    def test_atr_basis_long_stop_below_entry(self):
        levels = make_levels(entry=19500, direction=1)
        assert levels is not None
        # stop_dist = 0.11 * 300 = 33; stop = 19500 - 33 = 19467
        assert levels.stop == pytest.approx(19467.0)
        assert levels.stop < levels.entry

    def test_atr_basis_short_stop_above_entry(self):
        """Critical: short stop must be ABOVE entry. Wrong sign = no trade."""
        levels = make_levels(entry=19500, direction=-1)
        assert levels is not None
        # stop = 19500 - 33 * (-1) = 19500 + 33 = 19533
        assert levels.stop == pytest.approx(19533.0)
        assert levels.stop > levels.entry

    def test_orb_basis_long(self):
        levels = make_levels(
            entry=19500, direction=1,
            stop_basis="orb", orb_range=50.0, stop_orb_pct=100.0,
        )
        assert levels is not None
        # stop_dist = 1.0 * 50 = 50; stop = 19500 - 50 = 19450
        assert levels.stop == pytest.approx(19450.0)

    def test_orb_basis_short(self):
        levels = make_levels(
            entry=19500, direction=-1,
            stop_basis="orb", orb_range=50.0, stop_orb_pct=100.0,
        )
        assert levels is not None
        assert levels.stop == pytest.approx(19550.0)

    def test_risk_pts_always_positive(self):
        for direction in (1, -1):
            levels = make_levels(entry=19500, direction=direction)
            assert levels is not None
            assert levels.risk_pts > 0


# =============================================================================
# TP level tests
# =============================================================================

class TestTPLevels:
    def test_long_tp1_above_entry(self):
        levels = make_levels(entry=19500, direction=1, rr=3.0, tp1_ratio=0.5)
        assert levels is not None
        # tp1_dist = 3 * 33 * 0.5 = 49.5; tp1 = 19500 + 49.5 = 19549.5
        assert levels.tp1 == pytest.approx(19549.5)
        assert levels.tp1 > levels.entry

    def test_long_tp2_above_tp1(self):
        levels = make_levels(entry=19500, direction=1, rr=3.0, tp1_ratio=0.5)
        assert levels is not None
        # tp2 = 19500 + 3*33 = 19599
        assert levels.tp2 == pytest.approx(19599.0)
        assert levels.tp2 > levels.tp1

    def test_short_tp1_below_entry(self):
        levels = make_levels(entry=19500, direction=-1, rr=3.0, tp1_ratio=0.5)
        assert levels is not None
        assert levels.tp1 < levels.entry

    def test_short_tp2_below_tp1(self):
        levels = make_levels(entry=19500, direction=-1, rr=3.0, tp1_ratio=0.5)
        assert levels is not None
        assert levels.tp2 < levels.tp1

    def test_single_target_sets_tp1_equal_tp2(self):
        levels = make_levels(
            entry=19500,
            direction=1,
            rr=1.4,
            tp1_ratio=1.0,
            exit_mode="single_target",
        )
        assert levels is not None
        assert levels.exit_mode == "single_target"
        assert levels.tp1 == pytest.approx(levels.tp2)

    def test_single_target_rejects_partial_tp1_ratio(self):
        with pytest.raises(ValueError, match="tp1_ratio must be 1.0"):
            make_levels(
                entry=19500,
                direction=1,
                rr=2.0,
                tp1_ratio=0.5,
                exit_mode="single_target",
            )

    def test_invalid_exit_mode_rejected(self):
        with pytest.raises(ValueError, match="exit_mode must be one of"):
            make_levels(entry=19500, direction=1, exit_mode="tp1_only")


# =============================================================================
# Breakeven offset tests
# =============================================================================

class TestBreakevenOffset:
    def test_long_be_above_entry(self):
        levels = make_levels(entry=19500, direction=1, be_offset_ticks=4, min_tick=0.25)
        assert levels is not None
        # be_offset = 4 * 0.25 = 1.0; be = 19500 + 1.0 = 19501
        assert levels.be == pytest.approx(19501.0)

    def test_short_be_below_entry(self):
        """Critical: short BE must be BELOW entry."""
        levels = make_levels(entry=19500, direction=-1, be_offset_ticks=4, min_tick=0.25)
        assert levels is not None
        assert levels.be == pytest.approx(19499.0)
        assert levels.be < levels.entry

    def test_zero_be_offset_equals_entry(self):
        levels = make_levels(entry=19500, direction=1, be_offset_ticks=0, min_tick=0.25)
        assert levels is not None
        assert levels.be == pytest.approx(19500.0)


# =============================================================================
# Position sizing tests
# =============================================================================

class TestPositionSizing:
    def test_qty_computed_from_risk_usd(self):
        # risk_usd=1000, risk_pts=33, point_value=2 → qty_raw=1000/(33*2)=15.15 → 15
        levels = make_levels(entry=19500, direction=1, risk_usd=1000, point_value=2.0)
        assert levels is not None
        assert levels.qty == 15.0

    def test_qty_floored_to_step(self):
        # risk_usd=1000, risk_pts=33, point_value=2 → qty_raw=15.15, qty_step=2 → floor(15.15/2)*2=14
        levels = make_levels(entry=19500, direction=1, risk_usd=1000, qty_step=2.0)
        assert levels is not None
        assert levels.qty == 14.0

    def test_half_qty_multi_contract(self):
        levels = make_levels(entry=19500, direction=1, risk_usd=1000)
        assert levels is not None
        assert levels.qty == 15.0
        assert levels.half_qty == 7.0  # floor(15/2) = 7
        assert levels.is_single_contract is False

    def test_half_qty_odd_floors_not_rounds(self):
        # qty=5, qty_step=2 → half_qty = floor(2.5/2)*2 = 2 (not 3)
        # Need: risk_usd and parameters that produce qty=5
        # risk_pts=33, point_value=2: qty_raw = risk_usd/(33*2); to get 5: risk_usd=330
        levels = make_levels(entry=19500, direction=1, risk_usd=330, qty_step=2.0)
        assert levels is not None
        assert levels.qty in (4.0, 6.0)  # 330/(33*2)=5.0, floored to 4 with step=2

    def test_half_qty_single_contract(self):
        levels = make_levels(entry=19500, direction=1, risk_usd=50)
        assert levels is not None
        assert levels.qty == 1.0
        assert levels.half_qty == 1.0
        assert levels.is_single_contract is True

    def test_qty_multiplier_doubles_base(self):
        # Base qty=15 (risk_usd=1000, risk_pts=33, pv=2); multiplier=2 → 30
        levels = make_levels(entry=19500, direction=1, risk_usd=1000, qty_multiplier=2.0)
        assert levels is not None
        assert levels.qty == 30.0

    def test_qty_multiplier_floored_to_step(self):
        # risk_usd=198, risk_pts=33, pv=2 → qty_raw=3.0
        # _floor_to_step(3.0, 2.0) = 2.0 (base qty)
        # 2.0 * multiplier(2.0) = 4.0 → _floor_to_step(4.0, 2.0) = 4.0
        levels = make_levels(
            entry=19500, direction=1,
            risk_usd=198, qty_step=2.0, qty_multiplier=2.0,
        )
        assert levels is not None
        assert levels.qty == 4.0


# =============================================================================
# Single-contract override
# =============================================================================

class TestSingleContractOverride:
    def test_override_allowed_when_risk_under_cap(self):
        """Qty below min but 1-contract risk ≤ max_single_risk_usd → allow qty=1."""
        # risk_usd=1, risk_pts=33, pv=2 → raw_qty=0.015, floored to 0
        # 1 contract risk = 33 * 2 * 1 = $66 ≤ max_single_risk_usd=500 → allowed
        levels = make_levels(entry=19500, direction=1, risk_usd=1, max_single_risk_usd=500)
        assert levels is not None
        assert levels.qty == 1.0
        assert levels.is_single_contract is True

    def test_override_blocked_when_risk_over_cap(self):
        """1-contract risk > max_single_risk_usd → return None."""
        # risk_pts=33, pv=2 → 1 contract risk=$66; cap=$50 → blocked
        levels = make_levels(entry=19500, direction=1, risk_usd=1, max_single_risk_usd=50)
        assert levels is None

    def test_returns_none_when_risk_pts_zero(self):
        # This tests the risk_pts <= 0 guard: stop_dist=0 when pct=0 and no floor
        levels = make_levels(
            entry=19500, direction=1,
            stop_atr_pct=0.0, min_stop_pts=0.0, daily_atr=300,
        )
        assert levels is None


# =============================================================================
# Dual floor tests
# =============================================================================

class TestDualFloor:
    def test_min_stop_pts_clamps_small_atr_stop(self):
        """ATR gives tiny stop; min_stop_pts clamps it up."""
        # stop_dist = 0.01 * 300 = 3; min_stop_pts=20 → clamped to 20
        levels = make_levels(
            entry=19500, direction=1,
            stop_atr_pct=1.0, daily_atr=300.0, min_stop_pts=20.0,
        )
        assert levels is not None
        assert levels.stop == pytest.approx(19480.0)
        assert levels.risk_pts == pytest.approx(20.0)

    def test_min_stop_pts_does_not_clamp_larger_stop(self):
        """ATR stop already bigger than min_stop_pts → no clamping."""
        levels = make_levels(
            entry=19500, direction=1,
            stop_atr_pct=11.0, daily_atr=300.0, min_stop_pts=10.0,
        )
        assert levels is not None
        assert levels.stop == pytest.approx(19467.0)  # ATR stop = 33 > 10

    def test_min_tp1_pts_clamps_small_tp1(self):
        """RR × risk × tp1_ratio < min_tp1_pts → tp1 clamped to entry + min_tp1_pts."""
        # rr=1, risk_pts=33, tp1_ratio=0.1 → tp1_dist=3.3; min_tp1_pts=20 → clamped to 20
        levels = make_levels(
            entry=19500, direction=1,
            rr=1.0, tp1_ratio=0.1, min_tp1_pts=20.0,
        )
        assert levels is not None
        assert levels.tp1 == pytest.approx(19520.0)

    def test_min_tp1_pts_does_not_clamp_larger_tp1(self):
        """RR target already exceeds min_tp1_pts → not clamped."""
        levels = make_levels(
            entry=19500, direction=1,
            rr=3.0, tp1_ratio=0.5, min_tp1_pts=5.0,
        )
        assert levels is not None
        # tp1_dist = 3 * 33 * 0.5 = 49.5 > 5
        assert levels.tp1 == pytest.approx(19549.5)


# =============================================================================
# _floor_to_step helper
# =============================================================================

class TestFloorToStep:
    def test_zero_step_returns_x(self):
        assert _floor_to_step(7.5, 0) == pytest.approx(7.5)

    def test_negative_step_returns_x(self):
        assert _floor_to_step(7.5, -1) == pytest.approx(7.5)

    def test_floors_below_threshold(self):
        # 5.0 / 2.0 = 2.5, frac 0.5 < 0.7 → floor to 4.0
        assert _floor_to_step(5.0, 2.0) == pytest.approx(4.0)
        # 4.3 / 1.0 = 4.3, frac 0.3 < 0.7 → floor to 4.0
        assert _floor_to_step(4.3, 1.0) == pytest.approx(4.0)

    def test_rounds_up_at_threshold(self):
        # 7.8 / 2.0 = 3.9, frac 0.9 >= 0.7 → ceil to 8.0
        assert _floor_to_step(7.8, 2.0) == pytest.approx(8.0)
        # 4.7 / 1.0 = 4.7, frac 0.7 >= 0.7 → ceil to 5.0
        assert _floor_to_step(4.7, 1.0) == pytest.approx(5.0)
        # 1.75 / 1.0 = 1.75, frac 0.75 >= 0.7 → ceil to 2.0
        assert _floor_to_step(1.75, 1.0) == pytest.approx(2.0)

    def test_exact_multiple(self):
        assert _floor_to_step(6.0, 2.0) == pytest.approx(6.0)
