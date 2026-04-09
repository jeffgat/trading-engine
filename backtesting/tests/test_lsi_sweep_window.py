from __future__ import annotations

import numpy as np
import pandas as pd

from orb_backtest.config import SessionConfig
from orb_backtest.engine.simulator import _extract_lsi_candidates
from orb_backtest.signals.session import compute_session_masks


def _bars(start: str, n: int, *, day: str = "2025-01-03") -> pd.DatetimeIndex:
    return pd.date_range(
        f"{day} {start}",
        periods=n,
        freq="5min",
        tz="America/New_York",
    )


def _df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    start: str,
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


def _run_lsi_extract(
    df: pd.DataFrame,
    session: SessionConfig,
    fvg: dict[str, np.ndarray],
    *,
    valid_long: np.ndarray | None = None,
    valid_short: np.ndarray | None = None,
    n_left: int,
    n_right: int,
    fvg_window_left: int,
    fvg_window_right: int,
    direction_filter: str,
    sweep_gate: str = "sweep_window",
    stale_breach_consumes_pivot: bool = True,
):
    masks = compute_session_masks(df.index, session)
    n = len(df)
    return _extract_lsi_candidates(
        df,
        fvg,
        np.zeros(n, dtype=bool) if valid_long is None else valid_long,
        np.zeros(n, dtype=bool) if valid_short is None else valid_short,
        np.zeros(n, dtype=np.int64),
        masks["in_entry"],
        masks["in_rth"],
        masks["in_sweep"],
        df.index.date,
        df["close"].to_numpy(dtype=float),
        np.full(n, 10.0, dtype=float),
        np.zeros(n, dtype=float),
        np.zeros(n, dtype=float),
        session,
        n_left=n_left,
        n_right=n_right,
        fvg_window_left=fvg_window_left,
        fvg_window_right=fvg_window_right,
        direction_filter=direction_filter,
        sweep_gate=sweep_gate,
        stale_breach_consumes_pivot=stale_breach_consumes_pivot,
    )


def test_lsi_pre_entry_sweep_consumes_pivot_before_later_retouch() -> None:
    session = SessionConfig(
        name="NY",
        rth_start="09:30",
        sweep_start="08:30",
        sweep_end="14:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    df = _df(
        [10.3, 9.4, 10.3, 10.4, 10.5, 10.4, 10.0, 8.8, 9.9, 10.0, 9.0, 10.1, 10.2],
        [10.6, 10.0, 10.6, 10.7, 10.8, 10.7, 10.2, 9.2, 10.1, 10.2, 9.4, 10.4, 10.5],
        [10.0, 9.0, 10.0, 10.1, 10.2, 10.1, 9.8, 8.5, 9.7, 9.8, 8.8, 9.9, 10.0],
        [10.2, 9.5, 10.4, 10.5, 10.6, 10.5, 10.0, 8.7, 9.9, 10.0, 9.2, 10.2, 10.3],
        start="08:45",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][10] = True
    fvg["short_fvg_top"][10] = 10.0
    fvg["short_entry_price"][10] = 9.4
    fvg["short_gap_size"][10] = 0.6

    candidates = _run_lsi_extract(
        df,
        session,
        fvg,
        valid_short=fvg["short_fvg"].copy(),
        n_left=1,
        n_right=4,
        fvg_window_left=20,
        fvg_window_right=2,
        direction_filter="long",
    )

    assert candidates == []


def test_lsi_allows_valid_in_window_sweep() -> None:
    session = SessionConfig(
        name="NY",
        rth_start="08:30",
        sweep_start="08:30",
        sweep_end="14:30",
        entry_start="08:30",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    df = _df(
        [10.2, 9.4, 10.1, 8.9, 9.6, 10.2],
        [10.4, 9.9, 10.3, 9.2, 9.9, 10.5],
        [10.0, 9.0, 10.0, 8.8, 9.4, 9.8],
        [10.1, 9.5, 10.1, 8.9, 9.7, 10.2],
        start="08:30",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][4] = True
    fvg["short_fvg_top"][4] = 10.0
    fvg["short_entry_price"][4] = 9.4
    fvg["short_gap_size"][4] = 0.6

    candidates = _run_lsi_extract(
        df,
        session,
        fvg,
        valid_short=fvg["short_fvg"].copy(),
        n_left=1,
        n_right=1,
        fvg_window_left=20,
        fvg_window_right=2,
        direction_filter="long",
    )

    assert len(candidates) == 1
    assert candidates[0].direction == 1
    assert candidates[0].lsi_sweep_bar == 3
    assert candidates[0].lsi_swept_level == 9.0


def test_lsi_post_window_breach_consumes_pivot_without_activation() -> None:
    session = SessionConfig(
        name="NY",
        rth_start="09:30",
        sweep_start="08:30",
        sweep_end="14:30",
        entry_start="14:00",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    df = _df(
        [10.3, 9.4, 10.3, 10.4, 10.5, 10.4, 10.0, 8.8, 9.9, 10.0, 9.0, 10.1],
        [10.6, 10.0, 10.6, 10.7, 10.8, 10.7, 10.2, 9.2, 10.1, 10.2, 9.4, 10.4],
        [10.0, 9.0, 10.0, 10.1, 10.2, 10.1, 9.8, 8.5, 9.7, 9.8, 8.8, 9.9],
        [10.2, 9.5, 10.4, 10.5, 10.6, 10.5, 10.0, 8.7, 9.9, 10.0, 9.2, 10.2],
        start="14:00",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][10] = True
    fvg["short_fvg_top"][10] = 10.0
    fvg["short_entry_price"][10] = 9.4
    fvg["short_gap_size"][10] = 0.6

    candidates = _run_lsi_extract(
        df,
        session,
        fvg,
        valid_short=fvg["short_fvg"].copy(),
        n_left=1,
        n_right=4,
        fvg_window_left=20,
        fvg_window_right=2,
        direction_filter="long",
    )

    assert candidates == []


def test_lsi_legacy_entry_gate_reuses_pre_entry_breach() -> None:
    session = SessionConfig(
        name="NY",
        rth_start="09:30",
        sweep_start="08:30",
        sweep_end="14:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )
    df = _df(
        [10.3, 9.4, 10.3, 10.4, 10.5, 10.4, 10.0, 8.8, 9.9, 10.0, 9.0, 10.1, 10.2],
        [10.6, 10.0, 10.6, 10.7, 10.8, 10.7, 10.2, 9.2, 10.1, 10.2, 9.4, 10.4, 10.5],
        [10.0, 9.0, 10.0, 10.1, 10.2, 10.1, 9.8, 8.5, 9.7, 9.8, 8.8, 9.9, 10.0],
        [10.2, 9.5, 10.4, 10.5, 10.6, 10.5, 10.0, 8.7, 9.9, 10.0, 9.2, 10.2, 10.3],
        start="08:45",
    )
    fvg = _empty_lsi_fvg(len(df))
    fvg["short_fvg"][10] = True
    fvg["short_fvg_top"][10] = 10.0
    fvg["short_entry_price"][10] = 9.4
    fvg["short_gap_size"][10] = 0.6

    candidates = _run_lsi_extract(
        df,
        session,
        fvg,
        valid_short=fvg["short_fvg"].copy(),
        n_left=1,
        n_right=4,
        fvg_window_left=20,
        fvg_window_right=2,
        direction_filter="long",
        sweep_gate="entry",
        stale_breach_consumes_pivot=False,
    )

    assert len(candidates) == 1
    assert candidates[0].direction == 1
    assert candidates[0].lsi_sweep_bar == 10
    assert candidates[0].lsi_swept_level == 9.0
