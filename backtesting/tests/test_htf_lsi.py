from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import _SetupCandidate, _extract_htf_lsi_candidates
from orb_backtest.signals.htf_levels import compute_htf_unswept_levels


HTF_SESSION = SessionConfig(
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
    start: str,
    freq: str = "5min",
    day: str = "2025-01-03",
) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1.0] * len(open_),
        },
        index=_bars(start, len(open_), freq=freq, day=day),
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


def _htf_level_arrays(
    n: int,
    *,
    high_price: float | None = None,
    low_price: float | None = None,
    high_instance_id: int = 0,
    low_instance_id: int = 0,
    high_time: str = "2025-01-03T08:00:00",
    low_time: str = "2025-01-03T08:00:00",
) -> dict[str, np.ndarray]:
    nan_float = np.full(n, np.nan, dtype=float)
    neg_ids = np.full(n, -1, dtype=np.int64)
    nat_time = np.full(n, np.datetime64("NaT"), dtype="datetime64[ns]")
    return {
        "active_high_price": np.full(n, high_price, dtype=float) if high_price is not None else nan_float.copy(),
        "active_high_instance_id": np.full(n, high_instance_id, dtype=np.int64) if high_price is not None else neg_ids.copy(),
        "active_high_level_time": np.full(n, np.datetime64(high_time), dtype="datetime64[ns]") if high_price is not None else nat_time.copy(),
        "active_high_publish_time": np.full(n, np.datetime64(high_time), dtype="datetime64[ns]") if high_price is not None else nat_time.copy(),
        "active_low_price": np.full(n, low_price, dtype=float) if low_price is not None else nan_float.copy(),
        "active_low_instance_id": np.full(n, low_instance_id, dtype=np.int64) if low_price is not None else neg_ids.copy(),
        "active_low_level_time": np.full(n, np.datetime64(low_time), dtype="datetime64[ns]") if low_price is not None else nat_time.copy(),
        "active_low_publish_time": np.full(n, np.datetime64(low_time), dtype="datetime64[ns]") if low_price is not None else nat_time.copy(),
    }


def _reference_level_arrays(
    n: int,
    *,
    level_name: str,
    level_price: float,
    instance_id: int = 0,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    nan_arr = np.full(n, np.nan, dtype=float)
    neg_arr = np.full(n, -1, dtype=np.int64)
    levels = {
        "previous_day_high": nan_arr.copy(),
        "previous_day_low": nan_arr.copy(),
        "previous_week_high": nan_arr.copy(),
        "previous_week_low": nan_arr.copy(),
        "asia_high": nan_arr.copy(),
        "asia_low": nan_arr.copy(),
        "london_high": nan_arr.copy(),
        "london_low": nan_arr.copy(),
        "new_york_high": nan_arr.copy(),
        "new_york_low": nan_arr.copy(),
        "data_high": nan_arr.copy(),
        "data_low": nan_arr.copy(),
    }
    ids = {key: neg_arr.copy() for key in levels}
    levels[level_name] = np.full(n, level_price, dtype=float)
    ids[level_name] = np.full(n, instance_id, dtype=np.int64)
    return levels, ids


def _extract_candidates(
    df: pd.DataFrame,
    fvg: dict[str, np.ndarray],
    htf_levels: dict[str, np.ndarray] | None = None,
    *,
    eqhl_levels: dict[str, np.ndarray] | None = None,
    reference_levels: dict[str, np.ndarray] | None = None,
    reference_ids: dict[str, np.ndarray] | None = None,
    selected_reference_level_names: tuple[str, ...] = (),
    include_htf_levels: bool = True,
    include_eqhl_levels: bool = False,
    entry_mode: str = "close",
    close_on_sweep_to_inversion_minutes: int = 0,
    confirmation_mode: str = "inversion",
    stale_breach_consumes_pivot: bool = True,
) -> list[_SetupCandidate]:
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
        np.full(len(df), 110.0, dtype=float),
        np.full(len(df), 90.0, dtype=float),
        HTF_SESSION,
        htf_levels=htf_levels,
        eqhl_levels=eqhl_levels,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        selected_reference_level_names=selected_reference_level_names,
        include_htf_levels=include_htf_levels,
        include_eqhl_levels=include_eqhl_levels,
        fvg_window_left=20,
        fvg_window_right=5,
        direction_filter="both",
        stop_mode="absolute",
        entry_mode=entry_mode,
        close_on_sweep_to_inversion_minutes=close_on_sweep_to_inversion_minutes,
        confirmation_mode=confirmation_mode,
        htf_level_tf_minutes=60,
        stale_breach_consumes_pivot=stale_breach_consumes_pivot,
    )


def _run_backtest_with_candidates(
    monkeypatch,
    df: pd.DataFrame,
    candidates: list[_SetupCandidate],
    *,
    trade_cap: int,
    limit_cancel_on_pre_entry_target_touch: str = "",
    limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep: bool = False,
) -> list[simulator.TradeResult]:
    monkeypatch.setattr(simulator, "_extract_setup_candidates", lambda *_args, **_kwargs: list(candidates))
    config = StrategyConfig(
        instrument=NQ,
        sessions=(
            SessionConfig(
                name="NY",
                rth_start="08:30",
                sweep_start="08:30",
                sweep_end="15:00",
                entry_start="08:30",
                entry_end="09:30",
                flat_start="09:30",
                flat_end="09:35",
                min_gap_atr_pct=0.0,
            ),
        ),
        strategy="htf_lsi",
        htf_trade_max_per_session=trade_cap,
        risk_usd=20.0,
        min_qty=1.0,
        qty_step=1.0,
        rr=2.0,
        tp1_ratio=0.5,
        limit_cancel_on_pre_entry_target_touch=limit_cancel_on_pre_entry_target_touch,
        limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep=(
            limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep
        ),
    )
    return simulator.run_backtest(df, config)


def test_htf_lsi_cisd_replaces_fvg_inversion_after_level_sweep() -> None:
    df = _df(
        open_=[10.2, 10.0, 9.8, 9.5, 9.3, 9.6],
        high=[10.4, 10.2, 10.0, 9.7, 9.8, 10.3],
        low=[9.0, 9.7, 8.8, 9.1, 9.2, 9.5],
        close=[10.0, 9.8, 9.5, 9.3, 9.6, 10.2],
        start="08:40",
    )
    n = len(df)
    candidates = _extract_candidates(
        df,
        _empty_lsi_fvg(n),
        _htf_level_arrays(n, low_price=9.0),
        confirmation_mode="cisd",
        entry_mode="level_limit",
    )

    assert len(candidates) == 1
    assert candidates[0].direction == 1
    assert candidates[0].lsi_confirmation_type == "cisd"
    assert candidates[0].entry_price == pytest.approx(10.0)
    assert candidates[0].lsi_cisd_level == pytest.approx(10.0)
    assert candidates[0].lsi_sweep_bar == 2


def test_htf_lsi_level_publishes_only_after_n_left_bars_and_equal_touch_does_not_sweep() -> None:
    raw_idx = _bars("09:00", 180, freq="1min")
    raw_high = np.full(len(raw_idx), 8.0, dtype=float)
    raw_low = np.full(len(raw_idx), 7.0, dtype=float)
    raw_high[:60] = 10.0
    raw_low[:60] = 5.0
    raw_high[75] = 10.0
    raw_low[75] = 5.0
    raw = pd.DataFrame(
        {
            "open": raw_low,
            "high": raw_high,
            "low": raw_low,
            "close": raw_high,
            "volume": np.ones(len(raw_idx), dtype=float),
        },
        index=raw_idx,
    )
    base = _df(
        [8.0, 8.0],
        [8.0, 8.0],
        [7.0, 7.0],
        [8.0, 8.0],
        start="10:55",
    )

    levels = compute_htf_unswept_levels(base, raw, tf_minutes=60, n_left=1)

    assert np.isnan(levels["active_high_price"][0])
    assert np.isnan(levels["active_low_price"][0])
    assert levels["active_high_price"][1] == 10.0
    assert levels["active_low_price"][1] == 5.0
    assert int(levels["active_high_instance_id"][1]) == 0


def test_htf_lsi_pre_entry_breach_invalidates_without_arming() -> None:
    df = _df(
        [99.0, 99.0, 100.0, 100.0, 100.0],
        [99.5, 101.0, 100.5, 101.5, 100.5],
        [98.5, 98.5, 99.5, 99.5, 97.0],
        [99.0, 100.0, 100.0, 100.0, 97.0],
        start="08:30",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][2] = True
    fvg["long_fvg_bottom"][2] = 98.0
    fvg["long_entry_price"][2] = 101.0
    fvg["long_gap_size"][2] = 3.0

    htf_levels = _htf_level_arrays(len(df), high_price=100.0)
    candidates = _extract_candidates(df, fvg, htf_levels)

    assert candidates == []


def test_htf_lsi_breach_outside_broad_scan_consumes_by_default() -> None:
    df = _df(
        [99.0, 99.0, 100.0, 100.0, 100.0],
        [101.0, 99.5, 100.0, 101.5, 100.5],
        [98.5, 98.5, 99.5, 99.5, 97.0],
        [100.0, 99.0, 100.0, 100.0, 97.0],
        start="08:25",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][2] = True
    fvg["long_fvg_bottom"][2] = 98.0
    fvg["long_entry_price"][2] = 101.0
    fvg["long_gap_size"][2] = 3.0

    htf_levels = _htf_level_arrays(len(df), high_price=100.0)
    candidates = _extract_candidates(df, fvg, htf_levels)

    assert candidates == []


def test_htf_lsi_breach_outside_broad_scan_can_preserve_legacy_mode() -> None:
    df = _df(
        [99.0, 99.0, 100.0, 100.0, 100.0],
        [101.0, 99.5, 100.0, 101.5, 100.5],
        [98.5, 98.5, 99.5, 99.5, 97.0],
        [100.0, 99.0, 100.0, 100.0, 97.0],
        start="08:25",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][2] = True
    fvg["long_fvg_bottom"][2] = 98.0
    fvg["long_entry_price"][2] = 101.0
    fvg["long_gap_size"][2] = 3.0

    htf_levels = _htf_level_arrays(len(df), high_price=100.0)
    candidates = _extract_candidates(
        df,
        fvg,
        htf_levels,
        stale_breach_consumes_pivot=False,
    )

    assert len(candidates) == 1
    assert candidates[0].direction == -1
    assert candidates[0].htf_level_side == "high"
    assert candidates[0].htf_level_price == 100.0
    assert candidates[0].sweep_to_inversion_bars == 1


def test_htf_lsi_timed_hybrid_switches_entry_mode_at_threshold() -> None:
    df = _df(
        [99.0, 99.0, 100.0, 100.0, 100.0],
        [101.0, 99.5, 100.0, 101.5, 100.5],
        [98.5, 98.5, 99.5, 99.5, 97.0],
        [100.0, 99.0, 100.0, 100.0, 97.0],
        start="08:25",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][2] = True
    fvg["long_fvg_bottom"][2] = 98.0
    fvg["long_entry_price"][2] = 101.0
    fvg["long_gap_size"][2] = 3.0

    htf_levels = _htf_level_arrays(len(df), high_price=101.0)

    limit_candidates = _extract_candidates(
        df,
        fvg,
        htf_levels,
        entry_mode="timed_hybrid",
        close_on_sweep_to_inversion_minutes=4,
    )
    close_candidates = _extract_candidates(
        df,
        fvg,
        htf_levels,
        entry_mode="timed_hybrid",
        close_on_sweep_to_inversion_minutes=5,
    )

    assert len(limit_candidates) == 1
    assert limit_candidates[0].signal_bar == 4
    assert limit_candidates[0].entry_price == pytest.approx(98.0)

    assert len(close_candidates) == 1
    assert close_candidates[0].signal_bar == 3
    assert close_candidates[0].entry_price == pytest.approx(97.0)


def test_htf_lsi_can_arm_from_named_reference_level_without_htf_pivots() -> None:
    df = _df(
        [99.0, 99.0, 100.0],
        [99.5, 99.8, 101.5],
        [98.5, 99.0, 97.0],
        [99.0, 100.0, 97.0],
        start="08:35",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][1] = True
    fvg["long_fvg_bottom"][1] = 98.0
    fvg["long_entry_price"][1] = 101.0
    fvg["long_gap_size"][1] = 3.0

    reference_levels, reference_ids = _reference_level_arrays(
        len(df),
        level_name="previous_day_high",
        level_price=100.0,
    )
    candidates = _extract_candidates(
        df,
        fvg,
        None,
        reference_levels=reference_levels,
        reference_ids=reference_ids,
        selected_reference_level_names=("previous_day_high",),
        include_htf_levels=False,
    )

    assert len(candidates) == 1
    assert candidates[0].direction == -1
    assert candidates[0].reference_level_name == "previous_day_high"
    assert candidates[0].reference_level_price == 100.0
    assert candidates[0].htf_level_side == "high"
    assert candidates[0].htf_level_tf_minutes == 0


def test_htf_lsi_can_arm_from_equal_high_level_without_other_sources() -> None:
    df = _df(
        [99.0, 99.0, 100.0],
        [99.5, 99.8, 101.5],
        [98.5, 99.0, 97.0],
        [99.0, 100.0, 97.0],
        start="08:35",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["long_fvg"][1] = True
    fvg["long_fvg_bottom"][1] = 98.0
    fvg["long_entry_price"][1] = 101.0
    fvg["long_gap_size"][1] = 3.0

    eqhl_levels = _htf_level_arrays(len(df), high_price=100.0)
    eqhl_levels["tf_minutes"] = 15
    candidates = _extract_candidates(
        df,
        fvg,
        None,
        eqhl_levels=eqhl_levels,
        include_htf_levels=False,
        include_eqhl_levels=True,
    )

    assert len(candidates) == 1
    assert candidates[0].direction == -1
    assert candidates[0].reference_level_name == "equal_high_15m"
    assert candidates[0].reference_level_price == 100.0
    assert candidates[0].htf_level_side == "high"
    assert candidates[0].htf_level_tf_minutes == 15


def test_htf_lsi_can_arm_from_data_low_without_htf_pivots() -> None:
    df = _df(
        [101.0, 101.0, 101.0],
        [102.0, 101.5, 103.0],
        [100.5, 100.8, 98.5],
        [101.5, 101.0, 102.0],
        start="08:35",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][1] = True
    fvg["short_fvg_top"][1] = 101.5
    fvg["short_entry_price"][1] = 99.5
    fvg["short_gap_size"][1] = 2.0

    reference_levels, reference_ids = _reference_level_arrays(
        len(df),
        level_name="data_low",
        level_price=100.0,
    )
    candidates = _extract_candidates(
        df,
        fvg,
        None,
        reference_levels=reference_levels,
        reference_ids=reference_ids,
        selected_reference_level_names=("data_low",),
        include_htf_levels=False,
    )

    assert len(candidates) == 1
    assert candidates[0].direction == 1
    assert candidates[0].reference_level_name == "data_low"
    assert candidates[0].reference_level_price == 100.0
    assert candidates[0].htf_level_side == "low"
    assert candidates[0].htf_level_tf_minutes == 0


def test_htf_lsi_trade_cap_1_blocks_later_fills(monkeypatch) -> None:
    df = _df(
        [101.0, 101.0, 101.0, 101.0, 101.0],
        [101.0, 102.5, 101.0, 102.5, 101.0],
        [101.0, 99.5, 101.0, 99.5, 101.0],
        [101.0, 102.2, 101.0, 102.2, 101.0],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
            htf_level_time="2025-01-03T08:00:00-05:00",
            htf_level_price=100.0,
            htf_level_side="low",
            htf_level_tf_minutes=60,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=2,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
            htf_level_time="2025-01-03T09:00:00-05:00",
            htf_level_price=99.0,
            htf_level_side="low",
            htf_level_tf_minutes=60,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=1)

    assert len(trades) == 2
    assert trades[0].exit_type != simulator.EXIT_NO_FILL
    assert trades[1].exit_type == simulator.EXIT_NO_FILL


def test_htf_lsi_trade_cap_2_allows_second_post_exit_trade(monkeypatch) -> None:
    df = _df(
        [101.0, 101.0, 101.0, 101.0, 101.0],
        [101.0, 102.5, 101.0, 102.5, 101.0],
        [101.0, 99.5, 101.0, 99.5, 101.0],
        [101.0, 102.2, 101.0, 102.2, 101.0],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=2,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=2)

    assert len(trades) == 2
    assert all(trade.exit_type != simulator.EXIT_NO_FILL for trade in trades)


def test_htf_lsi_trade_cap_0_is_uncapped(monkeypatch) -> None:
    df = _df(
        [101.0, 101.0, 101.0, 101.0, 101.0, 101.0, 101.0],
        [101.0, 102.5, 101.0, 102.5, 101.0, 102.5, 101.0],
        [101.0, 99.5, 101.0, 99.5, 101.0, 99.5, 101.0],
        [101.0, 102.2, 101.0, 102.2, 101.0, 102.2, 101.0],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=2,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=4,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=0)

    assert len(trades) == 3
    assert all(trade.exit_type != simulator.EXIT_NO_FILL for trade in trades)


def test_htf_lsi_no_fill_does_not_use_trade_slot(monkeypatch) -> None:
    df = _df(
        [101.0, 101.0, 101.0, 101.0, 101.0],
        [101.0, 101.0, 101.0, 102.5, 101.0],
        [101.0, 100.5, 101.0, 99.5, 101.0],
        [101.0, 101.0, 101.0, 102.2, 101.0],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=99.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=98.0,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=2,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=1)

    assert len(trades) == 2
    assert sum(trade.exit_type == simulator.EXIT_NO_FILL for trade in trades) == 1
    assert sum(trade.exit_type != simulator.EXIT_NO_FILL for trade in trades) == 1


def test_htf_lsi_pre_entry_tp1_touch_can_cancel_pending_limit(monkeypatch) -> None:
    df = _df(
        [100.2, 100.8, 100.4, 100.0],
        [100.8, 101.1, 101.5, 102.2],
        [100.2, 100.4, 99.8, 100.8],
        [100.6, 100.9, 101.2, 102.0],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    baseline = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=1)
    tp1_cancel = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        limit_cancel_on_pre_entry_target_touch="tp1",
    )

    assert baseline[0].exit_type != simulator.EXIT_NO_FILL
    assert tp1_cancel[0].exit_type == simulator.EXIT_NO_FILL


def test_htf_lsi_pre_entry_tp2_touch_waits_for_full_target(monkeypatch) -> None:
    df = _df(
        [100.2, 100.8, 100.4, 100.0, 100.0],
        [100.8, 101.1, 101.8, 102.2, 102.4],
        [100.2, 100.4, 99.8, 99.8, 100.9],
        [100.6, 100.9, 101.4, 102.0, 102.1],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    tp1_cancel = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        limit_cancel_on_pre_entry_target_touch="tp1",
    )
    tp2_cancel = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        limit_cancel_on_pre_entry_target_touch="tp2",
    )

    assert tp1_cancel[0].exit_type == simulator.EXIT_NO_FILL
    assert tp2_cancel[0].exit_type != simulator.EXIT_NO_FILL


def test_htf_lsi_pre_entry_tp2_touch_plus_sweep_requires_both_conditions(monkeypatch) -> None:
    df = _df(
        [100.2, 100.8, 100.8, 100.0],
        [100.8, 102.2, 101.0, 101.5],
        [100.2, 100.4, 100.4, 99.8],
        [100.6, 101.9, 100.9, 101.2],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    monkeypatch.setattr(
        simulator,
        "_build_htf_lsi_pre_entry_cancel_sweep_flags",
        lambda **_kwargs: (
            np.zeros(len(df), dtype=bool),
            np.zeros(len(df), dtype=bool),
        ),
    )
    no_sweep_cancel = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        limit_cancel_on_pre_entry_target_touch="tp2",
        limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep=True,
    )

    assert no_sweep_cancel[0].exit_type != simulator.EXIT_NO_FILL


def test_htf_lsi_pre_entry_tp2_touch_plus_sweep_cancels_on_later_fresh_sweep(monkeypatch) -> None:
    df = _df(
        [100.2, 100.8, 100.8, 100.0],
        [100.8, 102.2, 101.0, 101.5],
        [100.2, 100.4, 100.4, 99.8],
        [100.6, 101.9, 100.9, 101.2],
        start="08:30",
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=100.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.0,
        ),
    ]

    monkeypatch.setattr(
        simulator,
        "_build_htf_lsi_pre_entry_cancel_sweep_flags",
        lambda **_kwargs: (
            np.zeros(len(df), dtype=bool),
            np.array([False, False, True, False], dtype=bool),
        ),
    )
    sweep_cancel = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        limit_cancel_on_pre_entry_target_touch="tp2",
        limit_cancel_on_pre_entry_target_touch_requires_htf_lsi_sweep=True,
    )

    assert sweep_cancel[0].exit_type == simulator.EXIT_NO_FILL


def test_htf_lsi_transfer_alignment_uses_raw_1m_for_2m_3m_5m() -> None:
    raw_idx = _bars("09:00", 180, freq="1min")
    raw_high = np.full(len(raw_idx), 8.0, dtype=float)
    raw_low = np.full(len(raw_idx), 7.0, dtype=float)
    raw_high[:60] = 11.0
    raw_low[:60] = 6.0
    raw = pd.DataFrame(
        {
            "open": raw_low,
            "high": raw_high,
            "low": raw_low,
            "close": raw_high,
            "volume": np.ones(len(raw_idx), dtype=float),
        },
        index=raw_idx,
    )

    for rule in ("2min", "3min", "5min"):
        base = raw.resample(rule, label="left", closed="left").agg(
            {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
        ).dropna()
        levels = compute_htf_unswept_levels(base, raw, tf_minutes=60, n_left=1)
        pos = np.where(base.index == pd.Timestamp("2025-01-03 11:00:00", tz="America/New_York"))[0][0]
        assert levels["active_high_price"][pos] == 11.0
        assert levels["active_low_price"][pos] == 6.0


def test_htf_lsi_requires_at_least_one_sweep_source() -> None:
    with pytest.raises(ValueError, match="at least one sweep source"):
        StrategyConfig(
            instrument=NQ,
            sessions=(HTF_SESSION,),
            strategy="htf_lsi",
            htf_lsi_include_htf_levels=False,
            htf_lsi_include_eqhl_levels=False,
            htf_lsi_reference_levels=(),
        )


def test_htf_lsi_equal_levels_satisfy_source_requirement() -> None:
    config = StrategyConfig(
        instrument=NQ,
        sessions=(HTF_SESSION,),
        strategy="htf_lsi",
        htf_lsi_include_htf_levels=False,
        htf_lsi_include_eqhl_levels=True,
        htf_lsi_reference_levels=(),
    )

    assert config.htf_lsi_include_eqhl_levels is True
