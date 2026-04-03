from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import _session_key, build_signal_cache
from orb_backtest.optimize import parallel


def _sample_ohlcv() -> pd.DataFrame:
    index = pd.date_range("2024-01-02 08:00", periods=144, freq="5min")
    base = np.linspace(100.0, 115.0, len(index))
    return pd.DataFrame(
        {
            "open": base,
            "high": base + 1.0,
            "low": base - 1.0,
            "close": base + 0.25,
            "volume": np.full(len(index), 1000.0),
        },
        index=index,
    )


def _lsi_session(*, rth_start: str) -> SessionConfig:
    return SessionConfig(
        name="NY",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        rth_start=rth_start,
        stop_atr_pct=7.5,
        min_gap_atr_pct=2.25,
    )


def test_build_signal_cache_separates_sessions_with_different_rth_start():
    df = _sample_ohlcv()
    session_a = _lsi_session(rth_start="09:30")
    session_b = replace(session_a, rth_start="08:30")

    config_a = StrategyConfig(instrument=NQ, strategy="lsi", sessions=(session_a,))
    config_b = StrategyConfig(instrument=NQ, strategy="lsi", sessions=(session_b,))

    cache = build_signal_cache(df, [config_a, config_b])

    key_a = _session_key(session_a)
    key_b = _session_key(session_b)

    assert key_a != key_b
    assert len(cache["session"]) == 2
    assert not np.array_equal(
        cache["session"][key_a]["masks"]["in_rth"],
        cache["session"][key_b]["masks"]["in_rth"],
    )


def test_load_or_build_signal_cache_invalidates_when_dataframe_content_changes(
    monkeypatch,
    tmp_path,
):
    df_a = _sample_ohlcv()
    df_b = df_a.copy()
    df_b.iloc[10, df_b.columns.get_loc("high")] += 7.0

    config = StrategyConfig(
        instrument=NQ,
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=7.5,
                min_gap_atr_pct=2.25,
            ),
        ),
    )

    calls: list[float] = []

    def fake_build_signal_cache(df: pd.DataFrame, _configs: list[StrategyConfig]) -> dict:
        calls.append(float(df["high"].iloc[10]))
        return {"marker": float(df["high"].iloc[10])}

    monkeypatch.setattr(parallel, "build_signal_cache", fake_build_signal_cache)
    monkeypatch.setattr(
        parallel,
        "_signal_cache_path",
        lambda df, configs: tmp_path / f"sigcache_{parallel._dataframe_cache_fingerprint(df)}_{len(configs)}.pkl",
    )

    cache_a = parallel._load_or_build_signal_cache(df_a, [config])
    cache_a_again = parallel._load_or_build_signal_cache(df_a.copy(), [config])
    cache_b = parallel._load_or_build_signal_cache(df_b, [config])

    assert cache_a == cache_a_again
    assert cache_b != cache_a
    assert len(calls) == 2


def test_run_sweep_returns_empty_list_for_empty_configs():
    assert parallel.run_sweep(_sample_ohlcv(), [], n_workers=4) == []


def test_run_sweep_parallel_matches_sequential_for_same_configs():
    df = _sample_ohlcv()
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=7.5,
        min_gap_atr_pct=2.25,
    )
    config_a = StrategyConfig(instrument=NQ, sessions=(session,))
    config_b = replace(config_a, rr=3.0)

    sequential = sorted(
        parallel.run_sweep(df, [config_a, config_b], n_workers=1, start_date="2024-01-02"),
        key=lambda item: item[0].rr,
    )
    parallel_results = sorted(
        parallel.run_sweep(df, [config_a, config_b], n_workers=2, start_date="2024-01-02"),
        key=lambda item: item[0].rr,
    )

    assert sequential == parallel_results
