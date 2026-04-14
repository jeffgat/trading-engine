from __future__ import annotations

import numpy as np
import pandas as pd

from orb_backtest.signals.equal_levels import compute_equal_htf_levels


def _raw_from_blocks(
    highs: list[float],
    lows: list[float],
    *,
    start: str = "2025-01-03 09:00",
) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(highs) * 5, freq="1min", tz="America/New_York")
    high_arr = np.repeat(np.asarray(highs, dtype=float), 5)
    low_arr = np.repeat(np.asarray(lows, dtype=float), 5)
    return pd.DataFrame(
        {
            "open": low_arr,
            "high": high_arr,
            "low": low_arr,
            "close": high_arr,
            "volume": np.ones(len(idx), dtype=float),
        },
        index=idx,
    )


def test_equal_htf_levels_publish_after_second_matching_pivot_confirms() -> None:
    raw = _raw_from_blocks(
        highs=[9.0, 10.0, 8.0, 10.0, 7.0, 6.0],
        lows=[7.0, 8.0, 6.0, 8.0, 5.0, 5.0],
    )

    levels = compute_equal_htf_levels(
        raw,
        raw,
        tf_minutes=5,
        n_left=1,
        tolerance_points=0.0,
        min_touches=2,
        lookback_bars=0,
    )

    before_publish = raw.index.get_loc(pd.Timestamp("2025-01-03 09:24:00", tz="America/New_York"))
    at_publish = raw.index.get_loc(pd.Timestamp("2025-01-03 09:25:00", tz="America/New_York"))

    assert np.isnan(levels["active_high_price"][before_publish])
    assert levels["active_high_price"][at_publish] == 10.0
    assert int(levels["active_high_instance_id"][at_publish]) == 0


def test_equal_htf_levels_tolerance_can_admit_near_equal_highs() -> None:
    raw = _raw_from_blocks(
        highs=[9.0, 10.0, 8.0, 10.2, 7.0, 6.0],
        lows=[7.0, 8.0, 6.0, 8.0, 5.0, 5.0],
    )

    exact_levels = compute_equal_htf_levels(
        raw,
        raw,
        tf_minutes=5,
        n_left=1,
        tolerance_points=0.0,
        min_touches=2,
        lookback_bars=0,
    )
    tolerant_levels = compute_equal_htf_levels(
        raw,
        raw,
        tf_minutes=5,
        n_left=1,
        tolerance_points=0.25,
        min_touches=2,
        lookback_bars=0,
    )
    at_publish = raw.index.get_loc(pd.Timestamp("2025-01-03 09:25:00", tz="America/New_York"))

    assert np.isnan(exact_levels["active_high_price"][at_publish])
    assert tolerant_levels["active_high_price"][at_publish] == 10.2


def test_equal_htf_levels_reject_pre_publication_breach() -> None:
    raw = _raw_from_blocks(
        highs=[9.0, 10.0, 8.0, 10.5, 8.0, 10.0, 7.0, 6.0],
        lows=[7.0, 8.0, 6.0, 8.0, 6.0, 8.0, 5.0, 5.0],
    )

    levels = compute_equal_htf_levels(
        raw,
        raw,
        tf_minutes=5,
        n_left=1,
        tolerance_points=0.0,
        min_touches=2,
        lookback_bars=0,
    )

    assert np.all(np.isnan(levels["active_high_price"]))
