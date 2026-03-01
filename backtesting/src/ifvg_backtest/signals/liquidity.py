"""Liquidity level computation — killzone session H/L and PDH/PDL.

Vectorized pre-computation of all liquidity levels that the IFVG strategy
monitors for sweeps. Matches HEAD_ilm.pine killzone and PDH/PDL tracking.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from orb_backtest.signals.session import _time_in_range, compute_trading_days


def compute_killzone_levels(
    timestamps: pd.DatetimeIndex,
    high: np.ndarray,
    low: np.ndarray,
    kz_start: str,
    kz_end: str,
) -> dict[str, np.ndarray]:
    """Compute session high/low for a killzone, locked after session ends.

    During the killzone window, tracks running high/low. When the session ends,
    those levels are "locked" and forward-filled until the next session starts.

    Matches Pine Script logic:
        - Track H/L during session
        - Lock levels when session ends (asiaJustEnded / londonJustEnded)
        - Levels persist until next session resets them

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        high: High prices array.
        low: Low prices array.
        kz_start: Killzone start time "HH:MM" in NY time.
        kz_end: Killzone end time "HH:MM" in NY time.

    Returns:
        Dict with arrays aligned to bar index:
            'kz_high': Locked KZ high (NaN before first session ends)
            'kz_low': Locked KZ low (NaN before first session ends)
            'kz_high_bar': Bar index where the KZ high was made
            'kz_low_bar': Bar index where the KZ low was made
    """
    n = len(high)
    hour = timestamps.hour.values
    minute = timestamps.minute.values

    in_kz = _time_in_range(hour, minute, kz_start, kz_end)

    # Detect session boundaries
    in_kz_prev = np.roll(in_kz, 1)
    in_kz_prev[0] = False
    kz_just_ended = ~in_kz & in_kz_prev  # First bar after session ends

    # Output arrays
    kz_high = np.full(n, np.nan)
    kz_low = np.full(n, np.nan)
    kz_high_bar = np.full(n, -1, dtype=np.int64)
    kz_low_bar = np.full(n, -1, dtype=np.int64)

    # Temp tracking during session
    temp_high = np.nan
    temp_low = np.nan
    temp_high_bar = -1
    temp_low_bar = -1

    # Locked levels
    locked_high = np.nan
    locked_low = np.nan
    locked_high_bar = -1
    locked_low_bar = -1

    for i in range(n):
        if in_kz[i]:
            if np.isnan(temp_high) or high[i] > temp_high:
                temp_high = high[i]
                temp_high_bar = i
            if np.isnan(temp_low) or low[i] < temp_low:
                temp_low = low[i]
                temp_low_bar = i

        if kz_just_ended[i] and not np.isnan(temp_high) and not np.isnan(temp_low):
            locked_high = temp_high
            locked_low = temp_low
            locked_high_bar = temp_high_bar
            locked_low_bar = temp_low_bar
            # Reset temp for next session
            temp_high = np.nan
            temp_low = np.nan
            temp_high_bar = -1
            temp_low_bar = -1

        kz_high[i] = locked_high
        kz_low[i] = locked_low
        kz_high_bar[i] = locked_high_bar
        kz_low_bar[i] = locked_low_bar

    return {
        "kz_high": kz_high,
        "kz_low": kz_low,
        "kz_high_bar": kz_high_bar,
        "kz_low_bar": kz_low_bar,
    }


def compute_pdh_pdl(
    timestamps: pd.DatetimeIndex,
    high: np.ndarray,
    low: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute Previous Day High/Low.

    Tracks current day's running H/L, then locks as PDH/PDL on the next
    new trading day. PDH/PDL are only valid if from the previous day
    (within 4 calendar days to account for weekends).

    Matches Pine Script logic in HEAD_ilm.pine lines 156-208.

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        high: High prices array.
        low: Low prices array.

    Returns:
        Dict with arrays:
            'pdh': Previous day high (NaN until day 2)
            'pdl': Previous day low (NaN until day 2)
            'pdh_bar': Bar index where PDH was made
            'pdl_bar': Bar index where PDL was made
    """
    n = len(high)
    new_day = compute_trading_days(timestamps)

    pdh = np.full(n, np.nan)
    pdl = np.full(n, np.nan)
    pdh_bar = np.full(n, -1, dtype=np.int64)
    pdl_bar = np.full(n, -1, dtype=np.int64)

    # Current day tracking
    cur_high = np.nan
    cur_low = np.nan
    cur_high_bar = -1
    cur_low_bar = -1

    # Locked previous day
    locked_pdh = np.nan
    locked_pdl = np.nan
    locked_pdh_bar = -1
    locked_pdl_bar = -1

    for i in range(n):
        if new_day[i]:
            # Lock current day as previous
            if not np.isnan(cur_high):
                locked_pdh = cur_high
                locked_pdl = cur_low
                locked_pdh_bar = cur_high_bar
                locked_pdl_bar = cur_low_bar
            # Reset current day
            cur_high = high[i]
            cur_low = low[i]
            cur_high_bar = i
            cur_low_bar = i
        else:
            if np.isnan(cur_high) or high[i] > cur_high:
                cur_high = high[i]
                cur_high_bar = i
            if np.isnan(cur_low) or low[i] < cur_low:
                cur_low = low[i]
                cur_low_bar = i

        pdh[i] = locked_pdh
        pdl[i] = locked_pdl
        pdh_bar[i] = locked_pdh_bar
        pdl_bar[i] = locked_pdl_bar

    return {
        "pdh": pdh,
        "pdl": pdl,
        "pdh_bar": pdh_bar,
        "pdl_bar": pdl_bar,
    }


def compute_swing_pivots(
    timestamps: pd.DatetimeIndex,
    high: np.ndarray,
    low: np.ndarray,
    swing_length: int = 24,
    htf_rule: str = "1h",
) -> dict[str, np.ndarray]:
    """Compute 1H (or other HTF) swing high/low pivot levels.

    Resamples intraday data to the higher timeframe, detects pivot highs/lows
    using a left/right lookback of *swing_length* bars (on the HTF), then maps
    the detected levels back to the intraday bar array.

    Matches Pine Script logic:
        htfPivotHigh = ta.pivothigh(high, swingLength, swingLength)
    on the "60" timeframe.

    Once a new pivot is confirmed (swing_length bars later), the level persists
    until a newer pivot replaces it. Levels are NOT reset on new day (they span
    multiple days, matching the Pine Script behaviour).

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        high: High prices array (intraday bars).
        low: Low prices array (intraday bars).
        swing_length: Lookback/look-forward for pivot detection on the HTF.
        htf_rule: Pandas resample rule for the higher timeframe (default "1h").

    Returns:
        Dict with arrays aligned to intraday bar index:
            'swing_high': Current swing high level (NaN until first pivot)
            'swing_low': Current swing low level (NaN until first pivot)
    """
    n = len(high)
    df_intra = pd.DataFrame(
        {"high": high, "low": low},
        index=timestamps,
    )

    # Resample to HTF
    htf = df_intra.resample(htf_rule).agg({"high": "max", "low": "min"}).dropna()
    htf_high = htf["high"].values
    htf_low = htf["low"].values
    n_htf = len(htf_high)

    # Detect pivot highs: htf_high[i] is a pivot if it's the max within
    # [i - swing_length, i + swing_length]
    pivot_high_idx: list[int] = []
    pivot_high_val: list[float] = []
    pivot_low_idx: list[int] = []
    pivot_low_val: list[float] = []

    for i in range(swing_length, n_htf - swing_length):
        # Pivot high: bar is strictly the highest in the window
        window_high = htf_high[i - swing_length : i + swing_length + 1]
        if htf_high[i] == np.max(window_high) and np.sum(window_high == htf_high[i]) == 1:
            pivot_high_idx.append(i)
            pivot_high_val.append(htf_high[i])

        # Pivot low: bar is strictly the lowest in the window
        window_low = htf_low[i - swing_length : i + swing_length + 1]
        if htf_low[i] == np.min(window_low) and np.sum(window_low == htf_low[i]) == 1:
            pivot_low_idx.append(i)
            pivot_low_val.append(htf_low[i])

    # Map HTF pivot detections back to intraday bars.
    # A pivot at HTF bar i is *confirmed* at HTF bar i + swing_length
    # (Pine confirms pivots swing_length bars later).
    # Use .values.astype("int64") for both to ensure consistent units
    # (datetime64[us] → microseconds since epoch on both sides).
    htf_ts_int = htf.index.values.astype("int64")

    # Build intraday-aligned arrays: forward-fill confirmed pivots
    swing_high_out = np.full(n, np.nan)
    swing_low_out = np.full(n, np.nan)

    # For each confirmed pivot, find the intraday bar where confirmation happens
    # (i.e. the first intraday bar >= htf_ts[pivot_idx + swing_length])
    intra_ts = timestamps.values.astype("int64")

    cur_swing_high = np.nan
    cur_swing_low = np.nan

    # Pre-build confirmation timestamps for pivots
    confirm_high: list[tuple[int, float]] = []  # (intraday_bar_idx, level)
    for pi, pv in zip(pivot_high_idx, pivot_high_val):
        confirm_htf_idx = pi + swing_length
        if confirm_htf_idx < n_htf:
            confirm_ts = htf_ts_int[confirm_htf_idx]
            # Find first intraday bar >= confirmation timestamp
            intra_idx = np.searchsorted(intra_ts, confirm_ts, side="left")
            if intra_idx < n:
                confirm_high.append((int(intra_idx), pv))

    confirm_low: list[tuple[int, float]] = []
    for pi, pv in zip(pivot_low_idx, pivot_low_val):
        confirm_htf_idx = pi + swing_length
        if confirm_htf_idx < n_htf:
            confirm_ts = htf_ts_int[confirm_htf_idx]
            intra_idx = np.searchsorted(intra_ts, confirm_ts, side="left")
            if intra_idx < n:
                confirm_low.append((int(intra_idx), pv))

    # Sort by confirmation bar
    confirm_high.sort(key=lambda x: x[0])
    confirm_low.sort(key=lambda x: x[0])

    # Forward-fill through intraday bars
    ch_ptr = 0
    cl_ptr = 0
    for i in range(n):
        while ch_ptr < len(confirm_high) and confirm_high[ch_ptr][0] <= i:
            cur_swing_high = confirm_high[ch_ptr][1]
            ch_ptr += 1
        while cl_ptr < len(confirm_low) and confirm_low[cl_ptr][0] <= i:
            cur_swing_low = confirm_low[cl_ptr][1]
            cl_ptr += 1
        swing_high_out[i] = cur_swing_high
        swing_low_out[i] = cur_swing_low

    return {
        "swing_high": swing_high_out,
        "swing_low": swing_low_out,
    }


def compute_all_liquidity_levels(
    timestamps: pd.DatetimeIndex,
    high: np.ndarray,
    low: np.ndarray,
    killzones: list[tuple[str, str, str]],
    swing_length: int = 0,
) -> dict[str, np.ndarray]:
    """Compute all liquidity levels for the IFVG strategy.

    The IFVG strategy (per HEAD_ilm.pine) only tracks the MOST RECENT killzone.
    London levels replace Asia levels when London ends. So we compute both but
    merge them: London overrides Asia on bars after London ends.

    Args:
        timestamps: DatetimeIndex in America/New_York timezone.
        high: High prices array.
        low: Low prices array.
        killzones: List of (name, start, end) tuples.
        swing_length: Pivot lookback for 1H swing detection (0 = disabled).

    Returns:
        Dict with merged KZ levels + PDH/PDL + swing pivots:
            'kz_high', 'kz_low', 'kz_high_bar', 'kz_low_bar': Merged KZ (London overrides Asia)
            'kz_source': int array — 0=none, 1=asia, 2=london
            'pdh', 'pdl', 'pdh_bar', 'pdl_bar': Previous day levels
            'swing_high', 'swing_low': 1H swing pivot levels (NaN if disabled)
    """
    n = len(high)
    hour = timestamps.hour.values
    minute = timestamps.minute.values

    # Compute each KZ independently
    kz_results = {}
    for name, start, end in killzones:
        kz_results[name] = compute_killzone_levels(timestamps, high, low, start, end)

    # Merge KZ levels: later killzones override earlier ones (London > Asia)
    # This matches Pine Script's behavior where London replaces Asia
    merged_high = np.full(n, np.nan)
    merged_low = np.full(n, np.nan)
    merged_high_bar = np.full(n, -1, dtype=np.int64)
    merged_low_bar = np.full(n, -1, dtype=np.int64)
    kz_source = np.zeros(n, dtype=np.int64)  # 0=none

    # Process KZs in order: later KZs override earlier
    for idx, (name, start, end) in enumerate(killzones, 1):
        res = kz_results[name]
        in_kz = _time_in_range(hour, minute, start, end)
        in_kz_prev = np.roll(in_kz, 1)
        in_kz_prev[0] = False
        kz_just_ended = ~in_kz & in_kz_prev

        # Find bars where this KZ locks new levels
        lock_bars = np.where(kz_just_ended)[0]
        for lb in lock_bars:
            if not np.isnan(res["kz_high"][lb]):
                # This KZ just locked — override merged from this bar onward
                # until another KZ locks or new day resets
                merged_high[lb:] = res["kz_high"][lb]
                merged_low[lb:] = res["kz_low"][lb]
                merged_high_bar[lb:] = res["kz_high_bar"][lb]
                merged_low_bar[lb:] = res["kz_low_bar"][lb]
                kz_source[lb:] = idx

    # Reset on new day (matches Pine Script daily reset)
    new_day = compute_trading_days(timestamps)
    day_starts = np.where(new_day)[0]
    for ds in day_starts:
        # Clear merged levels — will be re-set when first KZ locks after this day
        # Find next KZ lock after this day start
        merged_high[ds:] = np.nan
        merged_low[ds:] = np.nan
        merged_high_bar[ds:] = -1
        merged_low_bar[ds:] = -1
        kz_source[ds:] = 0

    # Re-apply KZ locks in chronological order after daily resets
    # Build a chronological list of all lock events
    lock_events = []  # (bar_index, kz_idx, high, low, high_bar, low_bar)
    for idx, (name, start, end) in enumerate(killzones, 1):
        res = kz_results[name]
        in_kz = _time_in_range(hour, minute, start, end)
        in_kz_prev = np.roll(in_kz, 1)
        in_kz_prev[0] = False
        kz_just_ended = ~in_kz & in_kz_prev
        for lb in np.where(kz_just_ended)[0]:
            if not np.isnan(res["kz_high"][lb]):
                lock_events.append((
                    lb, idx,
                    res["kz_high"][lb], res["kz_low"][lb],
                    res["kz_high_bar"][lb], res["kz_low_bar"][lb],
                ))

    # Sort by bar index and apply sequentially
    lock_events.sort(key=lambda x: x[0])

    # Reset all
    merged_high[:] = np.nan
    merged_low[:] = np.nan
    merged_high_bar[:] = -1
    merged_low_bar[:] = -1
    kz_source[:] = 0

    # Apply locks and daily resets in order
    event_idx = 0
    cur_high = np.nan
    cur_low = np.nan
    cur_high_bar = -1
    cur_low_bar = -1
    cur_source = 0

    for i in range(n):
        if new_day[i]:
            cur_high = np.nan
            cur_low = np.nan
            cur_high_bar = -1
            cur_low_bar = -1
            cur_source = 0

        # Apply any lock events at this bar
        while event_idx < len(lock_events) and lock_events[event_idx][0] == i:
            _, src, h, l, hb, lb = lock_events[event_idx]
            cur_high = h
            cur_low = l
            cur_high_bar = hb
            cur_low_bar = lb
            cur_source = src
            event_idx += 1

        merged_high[i] = cur_high
        merged_low[i] = cur_low
        merged_high_bar[i] = cur_high_bar
        merged_low_bar[i] = cur_low_bar
        kz_source[i] = cur_source

    # PDH/PDL
    pdh_pdl = compute_pdh_pdl(timestamps, high, low)

    # 1H Swing pivots
    if swing_length > 0:
        swings = compute_swing_pivots(timestamps, high, low, swing_length=swing_length)
    else:
        swings = {
            "swing_high": np.full(n, np.nan),
            "swing_low": np.full(n, np.nan),
        }

    return {
        "kz_high": merged_high,
        "kz_low": merged_low,
        "kz_high_bar": merged_high_bar,
        "kz_low_bar": merged_low_bar,
        "kz_source": kz_source,
        **pdh_pdl,
        **swings,
    }
