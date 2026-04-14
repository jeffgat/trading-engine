"""Lookahead-safe approximate equal-high / equal-low levels for HTF-LSI.

Equal highs/lows are built from confirmed higher-timeframe swing pivots:

- Resample raw 1m data into the requested source timeframe
- Confirm swing highs/lows using symmetric left/right pivot width
- Publish a liquidity level when the latest pivot joins enough prior pivots
  within a configurable tick tolerance

The published level is the latest confirmed equal-high / equal-low cluster
aligned onto each base bar. Comparisons stay strict later in the simulator:
touches do not count as sweeps, only penetration does.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .swing import detect_swing_highs, detect_swing_lows


def compute_equal_htf_levels(
    df: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    *,
    tf_minutes: int,
    n_left: int,
    tolerance_points: float,
    min_touches: int = 2,
    lookback_bars: int = 48,
) -> dict[str, np.ndarray]:
    """Return latest published approximate equal highs/lows aligned to ``df``.

    A new level publishes when a confirmed swing pivot matches enough prior
    confirmed pivots within ``tolerance_points``. Matching pivots can be
    bounded with ``lookback_bars`` on the source timeframe; ``0`` disables the
    bound. Publication is delayed until the newest pivot is confirmed, and the
    interval from the earliest matched pivot close through publication must
    remain unswept on raw 1m data.
    """
    if signal_df_1m is None or signal_df_1m.empty:
        raise ValueError("signal_df_1m is required to compute equal HTF levels.")
    if tf_minutes < 1:
        raise ValueError(f"tf_minutes must be >= 1 (got {tf_minutes!r})")
    if n_left < 1:
        raise ValueError(f"n_left must be >= 1 (got {n_left!r})")
    if tolerance_points < 0:
        raise ValueError(
            f"tolerance_points must be >= 0 (got {tolerance_points!r})"
        )
    if min_touches < 2:
        raise ValueError(f"min_touches must be >= 2 (got {min_touches!r})")
    if lookback_bars < 0:
        raise ValueError(f"lookback_bars must be >= 0 (got {lookback_bars!r})")

    base_index = df.index
    raw = signal_df_1m[["high", "low"]].copy().sort_index()

    active_high_price = np.full(len(base_index), np.nan, dtype=np.float64)
    active_low_price = np.full(len(base_index), np.nan, dtype=np.float64)
    active_high_instance_id = np.full(len(base_index), -1, dtype=np.int64)
    active_low_instance_id = np.full(len(base_index), -1, dtype=np.int64)
    active_high_level_time = np.full(
        len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]"
    )
    active_low_level_time = np.full(
        len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]"
    )
    active_high_publish_time = np.full(
        len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]"
    )
    active_low_publish_time = np.full(
        len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]"
    )

    if len(base_index) == 0:
        return {
            "active_high_price": active_high_price,
            "active_high_instance_id": active_high_instance_id,
            "active_high_level_time": active_high_level_time,
            "active_high_publish_time": active_high_publish_time,
            "active_low_price": active_low_price,
            "active_low_instance_id": active_low_instance_id,
            "active_low_level_time": active_low_level_time,
            "active_low_publish_time": active_low_publish_time,
        }

    rule = f"{int(tf_minutes)}min"
    htf = (
        raw.resample(rule, label="left", closed="left")
        .agg({"high": "max", "low": "min"})
        .dropna()
    )
    if len(htf) == 0:
        return {
            "active_high_price": active_high_price,
            "active_high_instance_id": active_high_instance_id,
            "active_high_level_time": active_high_level_time,
            "active_high_publish_time": active_high_publish_time,
            "active_low_price": active_low_price,
            "active_low_instance_id": active_low_instance_id,
            "active_low_level_time": active_low_level_time,
            "active_low_publish_time": active_low_publish_time,
        }

    raw_high = raw["high"].to_numpy(dtype=np.float64)
    raw_low = raw["low"].to_numpy(dtype=np.float64)
    raw_ts = raw.index.values.astype("datetime64[ns]")
    htf_ts = htf.index.values.astype("datetime64[ns]")
    htf_high = htf["high"].to_numpy(dtype=np.float64)
    htf_low = htf["low"].to_numpy(dtype=np.float64)
    base_ts = base_index.values.astype("datetime64[ns]")
    tf_delta = np.timedelta64(int(tf_minutes), "m")

    swing_high = detect_swing_highs(htf_high, n_left=n_left, n_right=n_left)
    swing_low = detect_swing_lows(htf_low, n_left=n_left, n_right=n_left)

    high_events: list[tuple[np.datetime64, np.datetime64, float, int]] = []
    low_events: list[tuple[np.datetime64, np.datetime64, float, int]] = []
    prior_high_pivots: list[dict[str, object]] = []
    prior_low_pivots: list[dict[str, object]] = []
    recent_high_pivots: list[dict[str, object]] = []
    recent_low_pivots: list[dict[str, object]] = []
    high_instance_id = 0
    low_instance_id = 0

    for confirm_idx in range(len(htf_ts)):
        publish_time = htf_ts[confirm_idx] + tf_delta

        if swing_high[confirm_idx]:
            pivot_idx = confirm_idx - n_left
            if pivot_idx >= 0:
                pivot_start = htf_ts[pivot_idx]
                pivot_close = pivot_start + tf_delta
                pivot_price = float(htf_high[pivot_idx])
                if lookback_bars > 0:
                    while recent_high_pivots and (
                        pivot_idx - int(recent_high_pivots[0]["pivot_idx"])
                    ) > lookback_bars:
                        recent_high_pivots.pop(0)
                    candidate_high_pivots = recent_high_pivots
                else:
                    candidate_high_pivots = prior_high_pivots
                matched_highs = [
                    pivot
                    for pivot in candidate_high_pivots
                    if abs(float(pivot["price"]) - pivot_price) <= tolerance_points
                ]
                if len(matched_highs) + 1 >= min_touches:
                    level_price = max(
                        [float(pivot["price"]) for pivot in matched_highs] + [pivot_price]
                    )
                    earliest_close = min(
                        [np.datetime64(pivot["pivot_close"]) for pivot in matched_highs]
                        + [pivot_close]
                    )
                    earliest_start = min(
                        [np.datetime64(pivot["pivot_start"]) for pivot in matched_highs]
                        + [pivot_start]
                    )
                    raw_lo = raw_ts.searchsorted(earliest_close, side="left")
                    raw_hi = raw_ts.searchsorted(publish_time, side="left")
                    interval_high = (
                        np.max(raw_high[raw_lo:raw_hi]) if raw_hi > raw_lo else -np.inf
                    )
                    if interval_high <= level_price:
                        high_events.append(
                            (publish_time, earliest_start, level_price, high_instance_id)
                        )
                        high_instance_id += 1
                pivot_record = {
                    "pivot_idx": pivot_idx,
                    "pivot_start": pivot_start,
                    "pivot_close": pivot_close,
                    "price": pivot_price,
                }
                prior_high_pivots.append(pivot_record)
                if lookback_bars > 0:
                    recent_high_pivots.append(pivot_record)

        if swing_low[confirm_idx]:
            pivot_idx = confirm_idx - n_left
            if pivot_idx >= 0:
                pivot_start = htf_ts[pivot_idx]
                pivot_close = pivot_start + tf_delta
                pivot_price = float(htf_low[pivot_idx])
                if lookback_bars > 0:
                    while recent_low_pivots and (
                        pivot_idx - int(recent_low_pivots[0]["pivot_idx"])
                    ) > lookback_bars:
                        recent_low_pivots.pop(0)
                    candidate_low_pivots = recent_low_pivots
                else:
                    candidate_low_pivots = prior_low_pivots
                matched_lows = [
                    pivot
                    for pivot in candidate_low_pivots
                    if abs(float(pivot["price"]) - pivot_price) <= tolerance_points
                ]
                if len(matched_lows) + 1 >= min_touches:
                    level_price = min(
                        [float(pivot["price"]) for pivot in matched_lows] + [pivot_price]
                    )
                    earliest_close = min(
                        [np.datetime64(pivot["pivot_close"]) for pivot in matched_lows]
                        + [pivot_close]
                    )
                    earliest_start = min(
                        [np.datetime64(pivot["pivot_start"]) for pivot in matched_lows]
                        + [pivot_start]
                    )
                    raw_lo = raw_ts.searchsorted(earliest_close, side="left")
                    raw_hi = raw_ts.searchsorted(publish_time, side="left")
                    interval_low = (
                        np.min(raw_low[raw_lo:raw_hi]) if raw_hi > raw_lo else np.inf
                    )
                    if interval_low >= level_price:
                        low_events.append(
                            (publish_time, earliest_start, level_price, low_instance_id)
                        )
                        low_instance_id += 1
                pivot_record = {
                    "pivot_idx": pivot_idx,
                    "pivot_start": pivot_start,
                    "pivot_close": pivot_close,
                    "price": pivot_price,
                }
                prior_low_pivots.append(pivot_record)
                if lookback_bars > 0:
                    recent_low_pivots.append(pivot_record)

    def _align_side(
        events: list[tuple[np.datetime64, np.datetime64, float, int]],
        price_out: np.ndarray,
        id_out: np.ndarray,
        level_time_out: np.ndarray,
        publish_time_out: np.ndarray,
    ) -> None:
        if not events:
            return
        event_publish = np.array([event[0] for event in events], dtype="datetime64[ns]")
        event_level_time = np.array([event[1] for event in events], dtype="datetime64[ns]")
        event_price = np.array([event[2] for event in events], dtype=np.float64)
        event_id = np.array([event[3] for event in events], dtype=np.int64)
        pos = np.searchsorted(event_publish, base_ts, side="right") - 1
        valid = pos >= 0
        if not np.any(valid):
            return
        price_out[valid] = event_price[pos[valid]]
        id_out[valid] = event_id[pos[valid]]
        level_time_out[valid] = event_level_time[pos[valid]]
        publish_time_out[valid] = event_publish[pos[valid]]

    _align_side(
        high_events,
        active_high_price,
        active_high_instance_id,
        active_high_level_time,
        active_high_publish_time,
    )
    _align_side(
        low_events,
        active_low_price,
        active_low_instance_id,
        active_low_level_time,
        active_low_publish_time,
    )

    return {
        "active_high_price": active_high_price,
        "active_high_instance_id": active_high_instance_id,
        "active_high_level_time": active_high_level_time,
        "active_high_publish_time": active_high_publish_time,
        "active_low_price": active_low_price,
        "active_low_instance_id": active_low_instance_id,
        "active_low_level_time": active_low_level_time,
        "active_low_publish_time": active_low_publish_time,
    }
