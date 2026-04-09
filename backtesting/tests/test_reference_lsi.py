from __future__ import annotations

import numpy as np
import pandas as pd

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import _SetupCandidate, _extract_reference_lsi_candidates


REFERENCE_SESSION = SessionConfig(
    name="NY",
    rth_start="08:30",
    entry_start="08:30",
    entry_end="14:00",
    flat_start="14:00",
    flat_end="14:05",
    min_gap_atr_pct=5.0,
)


def _bars(start: str, n: int, *, day: str = "2025-01-03") -> pd.DatetimeIndex:
    return pd.date_range(
        f"{day} {start}",
        periods=n,
        freq="5min",
        tz="America/New_York",
    )


def _reference_df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    start: str = "08:30",
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
        index=_bars(start, len(open_), day=day),
    )


def _empty_fvg(n: int) -> dict[str, np.ndarray]:
    return {
        "long_fvg_bottom": np.full(n, np.nan, dtype=float),
        "long_entry_price": np.full(n, np.nan, dtype=float),
        "long_gap_size": np.zeros(n, dtype=float),
        "short_fvg_top": np.full(n, np.nan, dtype=float),
        "short_entry_price": np.full(n, np.nan, dtype=float),
        "short_gap_size": np.zeros(n, dtype=float),
    }


def _reference_arrays(
    n: int,
    *,
    high_level: float | None = None,
    low_level: float | None = None,
    instance_id: int = 0,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    nan_arr = np.full(n, np.nan, dtype=float)
    neg_arr = np.full(n, -1, dtype=np.int64)

    levels = {
        "previous_day_high": np.full(n, high_level, dtype=float) if high_level is not None else nan_arr.copy(),
        "previous_day_low": np.full(n, low_level, dtype=float) if low_level is not None else nan_arr.copy(),
        "asia_high": nan_arr.copy(),
        "asia_low": nan_arr.copy(),
        "london_high": nan_arr.copy(),
        "london_low": nan_arr.copy(),
    }
    ids = {
        "previous_day_high": np.full(n, instance_id, dtype=np.int64) if high_level is not None else neg_arr.copy(),
        "previous_day_low": np.full(n, instance_id, dtype=np.int64) if low_level is not None else neg_arr.copy(),
        "asia_high": neg_arr.copy(),
        "asia_low": neg_arr.copy(),
        "london_high": neg_arr.copy(),
        "london_low": neg_arr.copy(),
    }
    return levels, ids


def _run_backtest_with_candidates(
    monkeypatch,
    df: pd.DataFrame,
    candidates: list[_SetupCandidate],
    *,
    strategy: str = "reference_lsi",
    risk_usd: float = 20.0,
    min_qty: float = 1.0,
    qty_step: float = 1.0,
) -> list[simulator.TradeResult]:
    monkeypatch.setattr(simulator, "_extract_setup_candidates", lambda *_args, **_kwargs: list(candidates))
    config = StrategyConfig(
        instrument=NQ,
        sessions=(REFERENCE_SESSION,),
        strategy=strategy,
        risk_usd=risk_usd,
        min_qty=min_qty,
        qty_step=qty_step,
        rr=2.0,
        tp1_ratio=0.5,
    )
    return simulator.run_backtest(df, config)


def test_reference_lsi_requires_in_session_sweep_and_consumes_level_once() -> None:
    df = _reference_df(
        [102.0, 99.0, 98.0, 99.0],
        [103.0, 101.0, 99.0, 101.0],
        [101.0, 98.0, 97.0, 98.0],
        [102.0, 100.0, 97.0, 99.0],
    )
    fvg = _empty_fvg(len(df))
    fvg["long_fvg_bottom"][0] = 98.0
    fvg["long_entry_price"][0] = 104.0
    fvg["long_gap_size"][0] = 6.0
    valid_long = np.array([True, False, False, False], dtype=bool)
    valid_short = np.zeros(len(df), dtype=bool)
    reference_levels, reference_ids = _reference_arrays(len(df), high_level=100.0)

    candidates = _extract_reference_lsi_candidates(
        df,
        fvg,
        valid_long,
        valid_short,
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=2,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="near",
    )

    assert len(candidates) == 1
    assert candidates[0].direction == -1
    assert candidates[0].lsi_sweep_bar == 1
    assert candidates[0].reference_level_name == "previous_day_high"
    assert candidates[0].reference_level_price == 100.0


def test_reference_lsi_rejects_stale_pre_sweep_gap() -> None:
    df = _reference_df(
        [99.0, 99.0, 99.0, 98.0],
        [99.0, 99.0, 101.0, 99.0],
        [98.0, 98.0, 98.0, 97.0],
        [99.0, 99.0, 100.0, 97.0],
    )
    fvg = _empty_fvg(len(df))
    fvg["long_fvg_bottom"][0] = 98.0
    fvg["long_entry_price"][0] = 103.0
    fvg["long_gap_size"][0] = 5.0
    valid_long = np.array([True, False, False, False], dtype=bool)
    reference_levels, reference_ids = _reference_arrays(len(df), high_level=100.0)

    candidates = _extract_reference_lsi_candidates(
        df,
        fvg,
        valid_long,
        np.zeros(len(df), dtype=bool),
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=1,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="near",
    )

    assert candidates == []


def test_reference_lsi_rejects_late_inversion() -> None:
    df = _reference_df(
        [99.0, 99.0, 98.0, 98.0, 98.0],
        [99.0, 101.0, 99.0, 99.0, 99.0],
        [98.0, 98.0, 97.0, 97.0, 97.0],
        [99.0, 100.0, 99.0, 99.0, 97.0],
    )
    fvg = _empty_fvg(len(df))
    fvg["long_fvg_bottom"][0] = 98.0
    fvg["long_entry_price"][0] = 103.0
    fvg["long_gap_size"][0] = 5.0
    valid_long = np.array([True, False, False, False, False], dtype=bool)
    reference_levels, reference_ids = _reference_arrays(len(df), high_level=100.0)

    candidates = _extract_reference_lsi_candidates(
        df,
        fvg,
        valid_long,
        np.zeros(len(df), dtype=bool),
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=3,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="near",
    )

    assert candidates == []


def test_reference_lsi_near_far_edges_and_stop_use_sweep_to_inversion_range() -> None:
    df = _reference_df(
        [99.0, 99.0, 100.0],
        [99.0, 101.0, 105.0],
        [98.0, 98.0, 96.0],
        [99.0, 100.0, 101.0],
    )
    fvg = _empty_fvg(len(df))
    fvg["long_fvg_bottom"][0] = 102.0
    fvg["long_entry_price"][0] = 104.0
    fvg["long_gap_size"][0] = 2.0
    valid_long = np.array([True, False, False], dtype=bool)
    reference_levels, reference_ids = _reference_arrays(len(df), high_level=100.0)

    far_df = df.copy()
    far_df.loc[far_df.index[2], "close"] = 101.0
    near_df = df.copy()
    near_df.loc[near_df.index[2], "close"] = 101.0

    near = _extract_reference_lsi_candidates(
        near_df,
        fvg,
        valid_long,
        np.zeros(len(df), dtype=bool),
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        near_df.index.date,
        near_df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=2,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="near",
    )
    far = _extract_reference_lsi_candidates(
        far_df,
        fvg,
        valid_long,
        np.zeros(len(df), dtype=bool),
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        far_df.index.date,
        far_df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=2,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="far",
    )

    assert len(near) == 1
    assert len(far) == 1
    assert near[0].entry_price == 102.0
    assert far[0].entry_price == 104.0
    assert near[0].structural_stop_price == 105.0
    assert far[0].structural_stop_price == 105.0


def test_reference_lsi_respects_selected_reference_level_subset() -> None:
    df = _reference_df(
        [99.0, 99.0, 98.0, 98.0],
        [99.0, 103.0, 99.0, 99.0],
        [98.0, 98.0, 97.0, 97.0],
        [99.0, 102.0, 97.0, 97.0],
    )
    fvg = _empty_fvg(len(df))
    fvg["long_fvg_bottom"][0] = 98.0
    fvg["long_entry_price"][0] = 104.0
    fvg["long_gap_size"][0] = 6.0
    valid_long = np.array([True, False, False, False], dtype=bool)

    nan_arr = np.full(len(df), np.nan, dtype=float)
    neg_arr = np.full(len(df), -1, dtype=np.int64)
    reference_levels = {
        "previous_day_high": nan_arr.copy(),
        "previous_day_low": nan_arr.copy(),
        "asia_high": np.full(len(df), 100.0, dtype=float),
        "asia_low": nan_arr.copy(),
        "london_high": np.full(len(df), 100.0, dtype=float),
        "london_low": nan_arr.copy(),
    }
    reference_ids = {
        "previous_day_high": neg_arr.copy(),
        "previous_day_low": neg_arr.copy(),
        "asia_high": np.full(len(df), 1, dtype=np.int64),
        "asia_low": neg_arr.copy(),
        "london_high": np.full(len(df), 2, dtype=np.int64),
        "london_low": neg_arr.copy(),
    }

    candidates = _extract_reference_lsi_candidates(
        df,
        fvg,
        valid_long,
        np.zeros(len(df), dtype=bool),
        np.zeros(len(df), dtype=np.int64),
        np.ones(len(df), dtype=bool),
        np.ones(len(df), dtype=bool),
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(len(df), 10.0, dtype=float),
        REFERENCE_SESSION,
        reference_levels=reference_levels,
        reference_instance_ids=reference_ids,
        gap_lookback_bars=3,
        inversion_max_bars=2,
        direction_filter="short",
        gap_entry_edge="near",
        selected_level_names=("asia_high",),
    )

    assert len(candidates) == 1
    assert candidates[0].reference_level_name == "asia_high"


def test_reference_lsi_allows_multiple_same_day_trades_but_not_overlap(monkeypatch) -> None:
    df = _reference_df(
        [100.0, 100.0, 100.5, 101.0, 101.0, 101.2],
        [100.4, 100.1, 102.2, 101.2, 101.1, 103.5],
        [99.8, 99.9, 100.4, 100.8, 100.9, 101.0],
        [100.0, 100.0, 102.0, 101.0, 101.0, 103.0],
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
            reference_level_name="previous_day_low",
            reference_level_price=100.0,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=1,
            entry_price=100.5,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=99.5,
            reference_level_name="asia_low",
            reference_level_price=100.5,
        ),
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=3,
            entry_price=101.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=100.0,
            reference_level_name="london_low",
            reference_level_price=101.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, strategy="reference_lsi")
    filled = [t for t in trades if t.exit_type != simulator.EXIT_NO_FILL]

    assert len(trades) == 3
    assert len(filled) == 2
    assert filled[0].reference_level_name == "previous_day_low"
    assert filled[1].reference_level_name == "london_low"
    blocked = [t for t in trades if t.reference_level_name == "asia_low"][0]
    assert blocked.exit_type == simulator.EXIT_NO_FILL


def test_reference_lsi_applies_min_atr_stop_floor(monkeypatch) -> None:
    df = _reference_df(
        [100.0, 100.2, 100.2],
        [100.2, 100.3, 100.4],
        [99.9, 100.1, 100.1],
        [100.0, 100.2, 100.2],
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
            structural_stop_price=99.8,
            reference_level_name="previous_day_low",
            reference_level_price=100.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, strategy="reference_lsi")

    assert len(trades) == 1
    assert trades[0].stop_price == 99.5
    assert trades[0].risk_points == 0.5


def test_reference_lsi_rejects_stop_wider_than_one_contract_risk(monkeypatch) -> None:
    df = _reference_df(
        [1000.0, 1000.0, 1000.0],
        [1000.5, 1000.5, 1000.5],
        [999.5, 999.5, 999.5],
        [1000.0, 1000.0, 1000.0],
    )
    candidates = [
        _SetupCandidate(
            date_str="2025-01-03",
            session="NY",
            direction=1,
            signal_bar=0,
            entry_price=1000.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=700.0,
            reference_level_name="previous_day_low",
            reference_level_price=1000.0,
        ),
    ]

    trades = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        strategy="reference_lsi",
        risk_usd=5000.0,
        min_qty=0.1,
        qty_step=0.1,
    )

    assert trades == []


def test_existing_lsi_scheduler_remains_one_trade_per_day(monkeypatch) -> None:
    df = _reference_df(
        [100.0, 100.0, 100.5, 101.0, 101.0, 101.2],
        [100.4, 100.1, 102.2, 101.2, 101.1, 103.5],
        [99.8, 99.9, 100.4, 100.8, 100.9, 101.0],
        [100.0, 100.0, 102.0, 101.0, 101.0, 103.0],
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
            signal_bar=3,
            entry_price=101.0,
            gap_size=1.0,
            daily_atr=10.0,
            orb_range=0.0,
            structural_stop_price=100.0,
        ),
    ]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, strategy="lsi")
    filled = [t for t in trades if t.exit_type != simulator.EXIT_NO_FILL]

    assert len(trades) == 2
    assert len(filled) == 1
