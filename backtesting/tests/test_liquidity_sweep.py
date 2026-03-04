from __future__ import annotations

import numpy as np

from orb_backtest.signals.liquidity_sweep import detect_liquidity_sweeps


def test_tick_perfect_touch_is_not_a_sweep() -> None:
    high = np.array([100.0, 110.0, 110.0], dtype=float)
    low = np.array([90.0, 90.0, 80.0], dtype=float)
    latest_swing_high = np.array([np.nan, 110.0, 110.0], dtype=float)
    latest_swing_low = np.array([np.nan, 90.0, 90.0], dtype=float)

    sweeps = detect_liquidity_sweeps(
        high=high,
        low=low,
        latest_swing_high=latest_swing_high,
        latest_swing_low=latest_swing_low,
    )

    # bar 2 compares against bar 1 swing levels; equal touch must not sweep.
    assert bool(sweeps["high_swept"][2]) is False
    assert bool(sweeps["low_swept"][1]) is False


def test_strict_penetration_triggers_sweep() -> None:
    high = np.array([100.0, 110.0, 111.0], dtype=float)
    low = np.array([90.0, 90.0, 89.0], dtype=float)
    latest_swing_high = np.array([np.nan, 110.0, 110.0], dtype=float)
    latest_swing_low = np.array([np.nan, 90.0, 90.0], dtype=float)

    sweeps = detect_liquidity_sweeps(
        high=high,
        low=low,
        latest_swing_high=latest_swing_high,
        latest_swing_low=latest_swing_low,
    )

    assert bool(sweeps["high_swept"][2]) is True
    assert bool(sweeps["low_swept"][2]) is True
    assert sweeps["swept_high_level"][2] == 110.0
    assert sweeps["swept_low_level"][2] == 90.0
