from __future__ import annotations

import numpy as np
import pandas as pd

from orb_backtest.config import SessionConfig
from orb_backtest.engine.simulator import _LSILRLRSettings, _extract_htf_lsi_candidates, _lrlr_gate_blocks
from orb_backtest.signals.lrlr import LRLRResult, detect_lrlr_cluster


TEST_SESSION = SessionConfig(
    name="NY",
    rth_start="08:30",
    sweep_start="08:30",
    sweep_end="15:00",
    entry_start="08:40",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=0.0,
)


def _bars(start: str, n: int, *, freq: str = "5min", day: str = "2025-01-03") -> pd.DatetimeIndex:
    return pd.date_range(
        f"{day} {start}",
        periods=n,
        freq=freq,
        tz="America/New_York",
    )


def _df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    start: str = "08:35",
    freq: str = "5min",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1.0] * len(open_),
        },
        index=_bars(start, len(open_), freq=freq),
    )


def _empty_lsi_fvg(n: int) -> dict[str, np.ndarray]:
    return {
        "long_fvg": np.zeros(n, dtype=bool),
        "long_fvg_bottom": np.full(n, np.nan, dtype=float),
        "long_entry_price": np.full(n, np.nan, dtype=float),
        "long_gap_size": np.zeros(n, dtype=float),
        "short_fvg": np.zeros(n, dtype=bool),
        "short_fvg_top": np.full(n, np.nan, dtype=float),
        "short_entry_price": np.full(n, np.nan, dtype=float),
        "short_gap_size": np.zeros(n, dtype=float),
    }


def _htf_low_levels(n: int, price: float) -> dict[str, np.ndarray]:
    nat_time = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    neg_ids = np.full(n, -1, dtype=np.int64)
    return {
        "active_high_price": np.full(n, np.nan, dtype=float),
        "active_high_instance_id": neg_ids.copy(),
        "active_high_level_time": nat_time.copy(),
        "active_high_publish_time": nat_time.copy(),
        "active_low_price": np.full(n, price, dtype=float),
        "active_low_instance_id": np.zeros(n, dtype=np.int64),
        "active_low_level_time": np.full(n, np.datetime64("2025-01-03T08:00:00"), dtype="datetime64[ns]"),
        "active_low_publish_time": np.full(n, np.datetime64("2025-01-03T08:00:00"), dtype="datetime64[ns]"),
    }


def _extract_long_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    *,
    lrlr_settings: _LSILRLRSettings,
    rr: float = 2.5,
    tp1_ratio: float = 0.5,
):
    timestamps = df.index
    hour = timestamps.hour.values
    minute = timestamps.minute.values
    in_entry = (hour > 8) | ((hour == 8) & (minute >= 40))
    in_sweep = (hour > 8) | ((hour == 8) & (minute >= 30))
    in_rth = np.ones(len(df), dtype=bool)
    return _extract_htf_lsi_candidates(
        df,
        fvg,
        fvg["long_fvg"].copy(),
        fvg["short_fvg"].copy(),
        np.zeros(len(df), dtype=np.int64),
        in_entry,
        in_rth,
        in_sweep,
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        TEST_SESSION,
        htf_levels=_htf_low_levels(len(df), 100.0),
        include_htf_levels=True,
        include_eqhl_levels=False,
        fvg_window_left=20,
        fvg_window_right=5,
        direction_filter="long",
        stop_mode="absolute",
        entry_mode="fvg_limit",
        rr=rr,
        tp1_ratio=tp1_ratio,
        htf_level_tf_minutes=60,
        lrlr_settings=lrlr_settings,
    )


def test_detect_lrlr_cluster_finds_descending_unswept_highs_for_long() -> None:
    high = np.array([108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 105.0, 104.0], dtype=float)
    low = np.array([104.0, 105.0, 103.0, 104.0, 102.0, 103.0, 101.0, 100.0], dtype=float)

    match = detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=np.array([2, 4, 6], dtype=np.int64),
        pivot_high_idx=np.array([1, 3, 5], dtype=np.int64),
        pivot_high_price=np.array([110.0, 109.0, 108.0], dtype=float),
        pivot_low_confirm_idx=np.empty(0, dtype=np.int64),
        pivot_low_idx=np.empty(0, dtype=np.int64),
        pivot_low_price=np.empty(0, dtype=float),
        direction=1,
        entry_price=106.5,
        left_end_bar=6,
        daily_atr=10.0,
        bar_minutes=5.0,
        min_levels=3,
        lookback_minutes=120,
        max_pivot_gap_minutes=30,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
    )

    assert match.present is True
    assert match.level_count == 3
    assert match.nearest_level_price == 108.0
    assert match.farthest_level_price == 110.0
    assert match.slope_atr_per_bar < 0.0


def test_detect_lrlr_cluster_rejects_when_recent_highs_have_been_swept() -> None:
    high = np.array([108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 109.5, 104.0], dtype=float)
    low = np.array([104.0, 105.0, 103.0, 104.0, 102.0, 103.0, 101.0, 100.0], dtype=float)

    match = detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=np.array([2, 4, 6], dtype=np.int64),
        pivot_high_idx=np.array([1, 3, 5], dtype=np.int64),
        pivot_high_price=np.array([110.0, 109.0, 108.0], dtype=float),
        pivot_low_confirm_idx=np.empty(0, dtype=np.int64),
        pivot_low_idx=np.empty(0, dtype=np.int64),
        pivot_low_price=np.empty(0, dtype=float),
        direction=1,
        entry_price=106.5,
        left_end_bar=6,
        daily_atr=10.0,
        bar_minutes=5.0,
        min_levels=3,
        lookback_minutes=120,
        max_pivot_gap_minutes=30,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
    )

    assert match.present is False


def test_detect_lrlr_cluster_marks_tp1_path_only_when_cluster_reaches_tp1() -> None:
    high = np.array([108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 105.0, 104.0], dtype=float)
    low = np.array([104.0, 105.0, 103.0, 104.0, 102.0, 103.0, 101.0, 100.0], dtype=float)

    too_far = detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=np.array([2, 4, 6], dtype=np.int64),
        pivot_high_idx=np.array([1, 3, 5], dtype=np.int64),
        pivot_high_price=np.array([110.0, 109.0, 108.0], dtype=float),
        pivot_low_confirm_idx=np.empty(0, dtype=np.int64),
        pivot_low_idx=np.empty(0, dtype=np.int64),
        pivot_low_price=np.empty(0, dtype=float),
        direction=1,
        entry_price=106.5,
        tp1_price=107.5,
        left_end_bar=6,
        daily_atr=10.0,
        bar_minutes=5.0,
        min_levels=3,
        lookback_minutes=120,
        max_pivot_gap_minutes=30,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_buffer_atr=0.0,
    )

    buffered = detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=np.array([2, 4, 6], dtype=np.int64),
        pivot_high_idx=np.array([1, 3, 5], dtype=np.int64),
        pivot_high_price=np.array([110.0, 109.0, 108.0], dtype=float),
        pivot_low_confirm_idx=np.empty(0, dtype=np.int64),
        pivot_low_idx=np.empty(0, dtype=np.int64),
        pivot_low_price=np.empty(0, dtype=float),
        direction=1,
        entry_price=106.5,
        tp1_price=107.5,
        left_end_bar=6,
        daily_atr=10.0,
        bar_minutes=5.0,
        min_levels=3,
        lookback_minutes=120,
        max_pivot_gap_minutes=30,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_buffer_atr=0.05,
    )

    assert too_far.present is True
    assert too_far.tp1_path_present is False
    assert too_far.nearest_tp1_gap_atr == 0.05
    assert buffered.tp1_path_present is True


def test_detect_lrlr_cluster_tp1_window_only_variant_accepts_single_unswept_level() -> None:
    high = np.array([108.0, 110.0, 107.0, 106.0], dtype=float)
    low = np.array([104.0, 105.0, 103.0, 102.0], dtype=float)

    match = detect_lrlr_cluster(
        high=high,
        low=low,
        pivot_high_confirm_idx=np.array([2], dtype=np.int64),
        pivot_high_idx=np.array([1], dtype=np.int64),
        pivot_high_price=np.array([110.0], dtype=float),
        pivot_low_confirm_idx=np.empty(0, dtype=np.int64),
        pivot_low_idx=np.empty(0, dtype=np.int64),
        pivot_low_price=np.empty(0, dtype=float),
        direction=1,
        entry_price=106.5,
        tp1_price=109.5,
        left_end_bar=3,
        daily_atr=10.0,
        bar_minutes=5.0,
        min_levels=1,
        lookback_minutes=120,
        max_pivot_gap_minutes=30,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_buffer_atr=0.1,
    )

    assert match.present is True
    assert match.level_count == 1
    assert match.tp1_path_present is True
    assert match.slope_atr_per_bar == 0.0
    assert match.fit_error_atr == 0.0


def test_htf_lsi_lrlr_gate_requires_left_side_cluster() -> None:
    settings = _LSILRLRSettings(
        enabled=True,
        gate="require",
        swing_n_left=1,
        swing_n_right=1,
        min_pivots=3,
        lookback_minutes=120,
        max_pivot_gap_minutes=20,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_path_enabled=False,
        tp1_buffer_atr=0.0,
    )

    valid_df = _df(
        [107.0, 109.0, 106.0, 108.0, 105.0, 107.0, 103.0, 101.0, 100.5, 101.5],
        [108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 105.0, 102.0, 103.0, 104.0],
        [106.0, 107.0, 105.0, 106.0, 104.0, 105.0, 102.0, 99.0, 100.0, 101.0],
        [107.0, 108.0, 106.0, 107.0, 105.0, 106.0, 103.0, 100.0, 101.0, 102.0],
    )
    broken_df = valid_df.copy()
    broken_df.loc[broken_df.index[6], "high"] = 109.5

    fvg = _empty_lsi_fvg(len(valid_df))
    fvg["short_fvg"][8] = True
    fvg["short_fvg_top"][8] = 101.5
    fvg["short_entry_price"][8] = 99.5
    fvg["short_gap_size"][8] = 2.0

    valid_candidates = _extract_long_candidates(valid_df, fvg, lrlr_settings=settings)
    broken_candidates = _extract_long_candidates(broken_df, fvg, lrlr_settings=settings)

    assert len(valid_candidates) == 1
    assert valid_candidates[0].direction == 1
    assert valid_candidates[0].lsi_lrlr_present is True
    assert valid_candidates[0].lsi_lrlr_level_count == 3
    assert broken_candidates == []


def test_htf_lsi_tp1_path_gate_requires_nearest_liquidity_to_fit_inside_tp1() -> None:
    settings = _LSILRLRSettings(
        enabled=True,
        gate="require",
        swing_n_left=1,
        swing_n_right=1,
        min_pivots=2,
        lookback_minutes=120,
        max_pivot_gap_minutes=40,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_path_enabled=True,
        tp1_buffer_atr=0.0,
    )

    df = _df(
        [107.0, 109.0, 106.0, 108.0, 105.0, 107.0, 103.0, 101.0, 100.5, 101.5],
        [108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 105.0, 102.0, 103.0, 104.0],
        [106.0, 107.0, 105.0, 106.0, 104.0, 105.0, 102.0, 99.0, 100.0, 101.0],
        [107.0, 108.0, 106.0, 107.0, 105.0, 106.0, 103.0, 100.0, 101.0, 102.0],
    )

    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][8] = True
    fvg["short_fvg_top"][8] = 101.5
    fvg["short_entry_price"][8] = 99.5
    fvg["short_gap_size"][8] = 2.0

    blocked = _extract_long_candidates(df, fvg, lrlr_settings=settings, rr=1.0, tp1_ratio=1.0)
    passed = _extract_long_candidates(df, fvg, lrlr_settings=settings, rr=5.0, tp1_ratio=1.0)

    assert blocked == []
    assert len(passed) == 1
    assert passed[0].lsi_lrlr_present is True
    assert passed[0].lsi_lrlr_tp1_path_present is True
    assert passed[0].lsi_lrlr_nearest_tp1_gap_atr == 0.0


def test_htf_lsi_tp1_window_only_gate_can_pass_with_single_unswept_level() -> None:
    settings = _LSILRLRSettings(
        enabled=True,
        gate="require",
        swing_n_left=1,
        swing_n_right=1,
        min_pivots=1,
        lookback_minutes=120,
        max_pivot_gap_minutes=5,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_path_enabled=True,
        tp1_buffer_atr=0.0,
    )

    df = _df(
        [107.0, 109.0, 106.0, 108.0, 105.0, 107.0, 103.0, 101.0, 100.5, 101.5],
        [108.0, 110.0, 107.0, 109.0, 106.0, 108.0, 105.0, 102.0, 103.0, 104.0],
        [106.0, 107.0, 105.0, 106.0, 104.0, 105.0, 102.0, 99.0, 100.0, 101.0],
        [107.0, 108.0, 106.0, 107.0, 105.0, 106.0, 103.0, 100.0, 101.0, 102.0],
    )

    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][8] = True
    fvg["short_fvg_top"][8] = 101.5
    fvg["short_entry_price"][8] = 99.5
    fvg["short_gap_size"][8] = 2.0

    candidates = _extract_long_candidates(df, fvg, lrlr_settings=settings, rr=5.0, tp1_ratio=1.0)

    assert len(candidates) == 1
    assert candidates[0].lsi_lrlr_present is True
    assert candidates[0].lsi_lrlr_level_count == 1
    assert candidates[0].lsi_lrlr_tp1_path_present is True


def test_lrlr_gate_uses_tp1_path_as_part_of_effective_presence() -> None:
    settings = _LSILRLRSettings(
        enabled=True,
        gate="exclude",
        swing_n_left=1,
        swing_n_right=1,
        min_pivots=2,
        lookback_minutes=120,
        max_pivot_gap_minutes=40,
        max_cluster_span_minutes=120,
        max_price_span_atr=0.3,
        monotonic_tolerance_atr=0.02,
        line_tolerance_atr=0.02,
        tp1_path_enabled=True,
        tp1_buffer_atr=0.0,
    )

    raw_only = LRLRResult(present=True, tp1_path_present=False)
    tp1_qualified = LRLRResult(present=True, tp1_path_present=True)

    assert _lrlr_gate_blocks(raw_only, settings) is False
    assert _lrlr_gate_blocks(tp1_qualified, settings) is True
