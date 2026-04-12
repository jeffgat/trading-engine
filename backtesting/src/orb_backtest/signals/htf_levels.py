"""Lookahead-safe higher-timeframe bar extremes for HTF-LSI."""

from __future__ import annotations

import numpy as np
import pandas as pd


def compute_htf_unswept_levels(
    df: pd.DataFrame,
    signal_df_1m: pd.DataFrame,
    *,
    tf_minutes: int,
    n_left: int,
) -> dict[str, np.ndarray]:
    """Align the latest published unswept HTF high/low to each base bar.

    HTF bars are built from raw 1m data. Each completed HTF bar contributes a
    high candidate and a low candidate. A candidate is published only after
    ``n_left`` later HTF bars have completed and only if no raw 1m bar strictly
    swept that level before publication.
    """
    if signal_df_1m is None or signal_df_1m.empty:
        raise ValueError("signal_df_1m is required to compute HTF levels.")

    base_index = df.index
    raw = signal_df_1m[["high", "low"]].copy()
    raw = raw.sort_index()

    rule = f"{int(tf_minutes)}min"
    htf = raw.resample(rule, label="left", closed="left").agg({"high": "max", "low": "min"}).dropna()
    raw_high = raw["high"].to_numpy(dtype=np.float64)
    raw_low = raw["low"].to_numpy(dtype=np.float64)
    raw_ts = raw.index.values.astype("datetime64[ns]")
    htf_ts = htf.index.values.astype("datetime64[ns]")
    htf_high = htf["high"].to_numpy(dtype=np.float64)
    htf_low = htf["low"].to_numpy(dtype=np.float64)

    active_high_price = np.full(len(base_index), np.nan, dtype=np.float64)
    active_low_price = np.full(len(base_index), np.nan, dtype=np.float64)
    active_high_instance_id = np.full(len(base_index), -1, dtype=np.int64)
    active_low_instance_id = np.full(len(base_index), -1, dtype=np.int64)
    active_high_level_time = np.full(len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]")
    active_low_level_time = np.full(len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]")
    active_high_publish_time = np.full(len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]")
    active_low_publish_time = np.full(len(base_index), np.datetime64("NaT"), dtype="datetime64[ns]")

    if len(htf) == 0 or len(base_index) == 0:
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

    tf_delta = np.timedelta64(int(tf_minutes), "m")
    base_ts = base_index.values.astype("datetime64[ns]")

    high_events: list[tuple[np.datetime64, np.datetime64, float, int]] = []
    low_events: list[tuple[np.datetime64, np.datetime64, float, int]] = []

    high_instance_id = 0
    low_instance_id = 0
    for idx in range(len(htf_ts)):
        publish_idx = idx + n_left + 1
        if publish_idx > len(htf_ts):
            break
        candidate_start = htf_ts[idx]
        candidate_close = candidate_start + tf_delta
        publish_time = candidate_start + np.timedelta64((n_left + 1) * int(tf_minutes), "m")
        if publish_time > raw_ts[-1] + np.timedelta64(1, "m"):
            continue

        raw_lo = raw_ts.searchsorted(candidate_close, side="left")
        raw_hi = raw_ts.searchsorted(publish_time, side="left")

        interval_high_max = np.max(raw_high[raw_lo:raw_hi]) if raw_hi > raw_lo else -np.inf
        interval_low_min = np.min(raw_low[raw_lo:raw_hi]) if raw_hi > raw_lo else np.inf

        candidate_high = float(htf_high[idx])
        candidate_low = float(htf_low[idx])

        if interval_high_max <= candidate_high:
            high_events.append((publish_time, candidate_start, candidate_high, high_instance_id))
            high_instance_id += 1
        if interval_low_min >= candidate_low:
            low_events.append((publish_time, candidate_start, candidate_low, low_instance_id))
            low_instance_id += 1

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
