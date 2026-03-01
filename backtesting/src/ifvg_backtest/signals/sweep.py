"""Sweep detection — flags bars where liquidity levels are traded through.

A "sweep" occurs when price trades beyond a liquidity level:
    - High sweep: bar high > level high → bearish setup (reversal short)
    - Low sweep: bar low < level low → bullish setup (reversal long)

Per HEAD_ilm.pine, sweeps are detected continuously but setups are only
initiated during the entry window. Each level can only be traded once per day.
"""

from __future__ import annotations

import numpy as np

from orb_backtest.signals.session import compute_trading_days


def detect_sweeps(
    high: np.ndarray,
    low: np.ndarray,
    kz_high: np.ndarray,
    kz_low: np.ndarray,
    pdh: np.ndarray,
    pdl: np.ndarray,
    new_day: np.ndarray,
    swing_high: np.ndarray | None = None,
    swing_low: np.ndarray | None = None,
) -> dict[str, np.ndarray]:
    """Detect first-per-day sweep of each liquidity level.

    A sweep is the FIRST bar (per trading day) where price trades through the level.
    Once swept, the level stays swept for the rest of the day.

    Args:
        high: High prices array.
        low: Low prices array.
        kz_high: Killzone high levels (NaN where not active).
        kz_low: Killzone low levels (NaN where not active).
        pdh: Previous day high (NaN where not available).
        pdl: Previous day low (NaN where not available).
        new_day: Boolean array — True on first bar of each trading day.
        swing_high: 1H swing high levels (NaN where not available). Optional.
        swing_low: 1H swing low levels (NaN where not available). Optional.

    Returns:
        Dict with arrays for each level type (kz, pd, swing):
            '*_swept': bool — True from first bar that sweeps the level
            '*_sweep_bar': int — bar index of the sweep (-1 if not swept)
    """
    n = len(high)

    # Output: running "swept" flags (True from sweep bar onward for that day)
    kz_high_swept = np.zeros(n, dtype=bool)
    kz_low_swept = np.zeros(n, dtype=bool)
    pdh_swept = np.zeros(n, dtype=bool)
    pdl_swept = np.zeros(n, dtype=bool)
    sh_swept = np.zeros(n, dtype=bool)
    sl_swept = np.zeros(n, dtype=bool)

    # Sweep bar indices (per-bar: the bar where the sweep happened, or -1)
    kz_high_sweep_bar = np.full(n, -1, dtype=np.int64)
    kz_low_sweep_bar = np.full(n, -1, dtype=np.int64)
    pdh_sweep_bar = np.full(n, -1, dtype=np.int64)
    pdl_sweep_bar = np.full(n, -1, dtype=np.int64)
    sh_sweep_bar = np.full(n, -1, dtype=np.int64)
    sl_sweep_bar = np.full(n, -1, dtype=np.int64)

    has_swing = swing_high is not None and swing_low is not None

    # Track current day's sweep state
    cur_kz_high_swept = False
    cur_kz_low_swept = False
    cur_pdh_swept = False
    cur_pdl_swept = False
    cur_sh_swept = False
    cur_sl_swept = False
    cur_kz_high_sweep_bar = -1
    cur_kz_low_sweep_bar = -1
    cur_pdh_sweep_bar = -1
    cur_pdl_sweep_bar = -1
    cur_sh_sweep_bar = -1
    cur_sl_sweep_bar = -1

    # Track which swing level was swept so a new level resets the flag
    prev_swing_high_level = np.nan
    prev_swing_low_level = np.nan

    for i in range(n):
        if new_day[i]:
            cur_kz_high_swept = False
            cur_kz_low_swept = False
            cur_pdh_swept = False
            cur_pdl_swept = False
            cur_sh_swept = False
            cur_sl_swept = False
            cur_kz_high_sweep_bar = -1
            cur_kz_low_sweep_bar = -1
            cur_pdh_sweep_bar = -1
            cur_pdl_sweep_bar = -1
            cur_sh_sweep_bar = -1
            cur_sl_sweep_bar = -1

        # KZ high sweep
        if not cur_kz_high_swept and not np.isnan(kz_high[i]) and high[i] > kz_high[i]:
            cur_kz_high_swept = True
            cur_kz_high_sweep_bar = i

        # KZ low sweep
        if not cur_kz_low_swept and not np.isnan(kz_low[i]) and low[i] < kz_low[i]:
            cur_kz_low_swept = True
            cur_kz_low_sweep_bar = i

        # PDH sweep
        if not cur_pdh_swept and not np.isnan(pdh[i]) and high[i] > pdh[i]:
            cur_pdh_swept = True
            cur_pdh_sweep_bar = i

        # PDL sweep
        if not cur_pdl_swept and not np.isnan(pdl[i]) and low[i] < pdl[i]:
            cur_pdl_swept = True
            cur_pdl_sweep_bar = i

        # 1H Swing high sweep (reset traded flag when a new pivot appears)
        if has_swing:
            sh_level = swing_high[i]
            sl_level = swing_low[i]

            # New swing high pivot → reset swept/traded state
            if not np.isnan(sh_level) and sh_level != prev_swing_high_level:
                cur_sh_swept = False
                cur_sh_sweep_bar = -1
                prev_swing_high_level = sh_level

            if not np.isnan(sl_level) and sl_level != prev_swing_low_level:
                cur_sl_swept = False
                cur_sl_sweep_bar = -1
                prev_swing_low_level = sl_level

            if not cur_sh_swept and not np.isnan(sh_level) and high[i] > sh_level:
                cur_sh_swept = True
                cur_sh_sweep_bar = i

            if not cur_sl_swept and not np.isnan(sl_level) and low[i] < sl_level:
                cur_sl_swept = True
                cur_sl_sweep_bar = i

        kz_high_swept[i] = cur_kz_high_swept
        kz_low_swept[i] = cur_kz_low_swept
        pdh_swept[i] = cur_pdh_swept
        pdl_swept[i] = cur_pdl_swept
        sh_swept[i] = cur_sh_swept
        sl_swept[i] = cur_sl_swept
        kz_high_sweep_bar[i] = cur_kz_high_sweep_bar
        kz_low_sweep_bar[i] = cur_kz_low_sweep_bar
        pdh_sweep_bar[i] = cur_pdh_sweep_bar
        pdl_sweep_bar[i] = cur_pdl_sweep_bar
        sh_sweep_bar[i] = cur_sh_sweep_bar
        sl_sweep_bar[i] = cur_sl_sweep_bar

    return {
        "kz_high_swept": kz_high_swept,
        "kz_low_swept": kz_low_swept,
        "pdh_swept": pdh_swept,
        "pdl_swept": pdl_swept,
        "swing_high_swept": sh_swept,
        "swing_low_swept": sl_swept,
        "kz_high_sweep_bar": kz_high_sweep_bar,
        "kz_low_sweep_bar": kz_low_sweep_bar,
        "pdh_sweep_bar": pdh_sweep_bar,
        "pdl_sweep_bar": pdl_sweep_bar,
        "swing_high_sweep_bar": sh_sweep_bar,
        "swing_low_sweep_bar": sl_sweep_bar,
    }
