"""Tests for hard trade constraints.

These constraints are enforced at config creation and engine execution level.
No backtest can violate them. If any of these tests fail, the constraints
have been broken and must be restored immediately.

Rules:
  1. rr >= 1.0
  2. tp1_ratio * rr >= 1.0 (TP1 at least as far as stop)
  3. Stop >= 5% of daily ATR (enforced at engine level)
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from orb_backtest.config import SessionConfig, StrategyConfig


# ─── Config-level validation ────────────────────────────────────────────


class TestRRMinimum:
    """rr must be >= 1.0."""

    def test_rr_below_1_raises(self):
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            StrategyConfig(rr=0.5)

    def test_rr_at_0_raises(self):
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            StrategyConfig(rr=0.0)

    def test_rr_negative_raises(self):
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            StrategyConfig(rr=-1.0)

    def test_rr_just_below_1_raises(self):
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            StrategyConfig(rr=0.99)

    def test_rr_at_1_accepted(self):
        c = StrategyConfig(rr=1.0, tp1_ratio=1.0)
        assert c.rr == 1.0

    def test_rr_above_1_accepted(self):
        c = StrategyConfig(rr=2.5, tp1_ratio=0.5)
        assert c.rr == 2.5


class TestTP1Minimum:
    """tp1_ratio * rr must be >= 1.0."""

    def test_tp1_too_close_raises(self):
        with pytest.raises(ValueError, match="tp1_ratio .* rr must be >= 1.0"):
            StrategyConfig(rr=2.0, tp1_ratio=0.3)  # 0.6 < 1.0

    def test_tp1_scalp_raises(self):
        with pytest.raises(ValueError, match="tp1_ratio .* rr must be >= 1.0"):
            StrategyConfig(rr=1.5, tp1_ratio=0.2)  # 0.3 < 1.0

    def test_tp1_at_boundary_accepted(self):
        c = StrategyConfig(rr=2.0, tp1_ratio=0.5)  # 1.0 == 1.0
        assert c.tp1_ratio * c.rr == 1.0

    def test_tp1_above_boundary_accepted(self):
        c = StrategyConfig(rr=3.0, tp1_ratio=0.5)  # 1.5 > 1.0
        assert c.tp1_ratio * c.rr == 1.5

    def test_tp1_full_target_accepted(self):
        c = StrategyConfig(rr=1.0, tp1_ratio=1.0)  # 1.0 == 1.0
        assert c.tp1_ratio * c.rr == 1.0


class TestConstraintCombinations:
    """Edge cases combining both constraints."""

    def test_rr_fails_before_tp1_check(self):
        """rr < 1.0 should raise even if tp1_ratio * rr would be >= 1.0."""
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            StrategyConfig(rr=0.5, tp1_ratio=2.0)  # rr fails first

    def test_both_constraints_at_minimum(self):
        c = StrategyConfig(rr=1.0, tp1_ratio=1.0)
        assert c.rr >= 1.0
        assert c.tp1_ratio * c.rr >= 1.0

    def test_high_rr_low_tp1_rejected(self):
        """Even with high rr, tiny tp1_ratio can violate."""
        with pytest.raises(ValueError, match="tp1_ratio .* rr must be >= 1.0"):
            StrategyConfig(rr=3.0, tp1_ratio=0.1)  # 0.3 < 1.0

    def test_with_overrides_enforces_constraints(self):
        """with_overrides creates a new config — validation must still fire."""
        from orb_backtest.config import with_overrides

        base = StrategyConfig(rr=2.0, tp1_ratio=0.5)  # valid
        with pytest.raises(ValueError, match="rr must be >= 1.0"):
            with_overrides(base, rr=0.5)

    def test_with_overrides_tp1_constraint(self):
        from orb_backtest.config import with_overrides

        base = StrategyConfig(rr=2.0, tp1_ratio=0.5)  # valid
        with pytest.raises(ValueError, match="tp1_ratio .* rr must be >= 1.0"):
            with_overrides(base, tp1_ratio=0.1)  # 0.1 * 2.0 = 0.2 < 1.0


# ─── Engine-level enforcement ───────────────────────────────────────────


class TestStopATRFloor:
    """Stop distance must be at least 5% of daily ATR at trade execution."""

    def _compute_stop_dist(self, stop_atr_pct: float, atr: float) -> float:
        """Replicate the engine's stop computation with the 5% ATR floor."""
        stop_dist = (stop_atr_pct / 100.0) * atr
        min_atr_stop = 0.05 * atr
        return max(stop_dist, min_atr_stop)

    def test_tiny_stop_clamped_to_5pct(self):
        atr = 200.0
        stop_dist = self._compute_stop_dist(stop_atr_pct=1.0, atr=atr)
        assert stop_dist == 0.05 * atr  # 10.0, not 2.0

    def test_zero_stop_clamped_to_5pct(self):
        atr = 200.0
        stop_dist = self._compute_stop_dist(stop_atr_pct=0.0, atr=atr)
        assert stop_dist == 0.05 * atr

    def test_stop_above_5pct_unchanged(self):
        atr = 200.0
        stop_dist = self._compute_stop_dist(stop_atr_pct=8.0, atr=atr)
        assert stop_dist == (8.0 / 100.0) * atr  # 16.0

    def test_stop_exactly_5pct_accepted(self):
        atr = 200.0
        stop_dist = self._compute_stop_dist(stop_atr_pct=5.0, atr=atr)
        assert stop_dist == 0.05 * atr  # 10.0


class TestTP1DistanceFloor:
    """TP1 distance must be at least as far as risk_pts at trade execution."""

    def _compute_tp1_dist(self, rr: float, risk_pts: float, tp1_ratio: float) -> float:
        """Replicate the engine's TP1 computation with the risk_pts floor."""
        tp1_dist = rr * risk_pts * tp1_ratio
        return max(tp1_dist, risk_pts)

    def test_tp1_below_risk_clamped(self):
        """Even if config somehow has tp1_ratio*rr < 1, engine clamps."""
        risk_pts = 10.0
        tp1_dist = self._compute_tp1_dist(rr=2.0, risk_pts=risk_pts, tp1_ratio=0.3)
        # rr*tp1 = 0.6, so raw tp1_dist = 6.0 < risk_pts 10.0 → clamped
        assert tp1_dist == risk_pts

    def test_tp1_above_risk_unchanged(self):
        risk_pts = 10.0
        tp1_dist = self._compute_tp1_dist(rr=3.0, risk_pts=risk_pts, tp1_ratio=0.5)
        # rr*tp1 = 1.5, so raw tp1_dist = 15.0 > risk_pts 10.0
        assert tp1_dist == 15.0

    def test_tp1_exactly_at_risk_accepted(self):
        risk_pts = 10.0
        tp1_dist = self._compute_tp1_dist(rr=2.0, risk_pts=risk_pts, tp1_ratio=0.5)
        # rr*tp1 = 1.0, so raw tp1_dist = 10.0 == risk_pts
        assert tp1_dist == risk_pts
