from __future__ import annotations

import pandas as pd
import pytest

import orb_backtest.engine.simulator as simulator
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import EXIT_NO_FILL, _SetupCandidate


def _df(
    open_: list[float],
    high: list[float],
    low: list[float],
    close: list[float],
    *,
    start: str = "2024-01-02 09:30",
) -> pd.DataFrame:
    idx = pd.date_range(start=start, periods=len(open_), freq="5min", tz="America/New_York")
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": [1.0] * len(open_),
        },
        index=idx,
    )


def _cand(signal_bar: int, entry_price: float) -> _SetupCandidate:
    return _SetupCandidate(
        date_str="2024-01-02",
        session="NY",
        direction=1,
        signal_bar=signal_bar,
        entry_price=entry_price,
        gap_size=1.0,
        daily_atr=10.0,
        orb_range=10.0,
    )


def _run_backtest_with_candidates(
    monkeypatch: pytest.MonkeyPatch,
    df: pd.DataFrame,
    candidates: list[_SetupCandidate],
    *,
    trade_cap: int,
    reentry_policy: str = "any_reentry",
    rr: float = 2.0,
    tp1_ratio: float = 0.5,
    wide_stop_target_threshold_points: float = 0.0,
    wide_stop_target_rr: float = 0.0,
    wide_stop_full_exit_at_tp1: bool = False,
) -> list[simulator.TradeResult]:
    monkeypatch.setattr(simulator, "_extract_setup_candidates", lambda *_args, **_kwargs: list(candidates))
    config = StrategyConfig(
        instrument=NQ,
        sessions=(
            SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:35",
                entry_start="09:35",
                entry_end="10:15",
                flat_start="10:30",
                flat_end="10:35",
                stop_atr_pct=10.0,
            ),
        ),
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=False,
        risk_usd=20.0,
        min_qty=1.0,
        qty_step=1.0,
        rr=rr,
        tp1_ratio=tp1_ratio,
        orb_trade_max_per_session=trade_cap,
        orb_reentry_policy=reentry_policy,
        wide_stop_target_threshold_points=wide_stop_target_threshold_points,
        wide_stop_target_rr=wide_stop_target_rr,
        wide_stop_full_exit_at_tp1=wide_stop_full_exit_at_tp1,
    )
    return simulator.run_backtest(df, config)


def test_orb_trade_cap_one_keeps_single_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 100.5, 101.5, 102.0, 102.5, 103.0],
        [100.0, 100.2, 102.2, 101.8, 102.2, 104.2, 103.5],
        [100.0, 99.8, 100.4, 101.2, 101.8, 102.2, 102.8],
        [100.0, 100.0, 101.8, 101.6, 102.0, 103.8, 103.0],
    )
    candidates = [_cand(0, 100.0), _cand(1, 101.4), _cand(3, 102.0)]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=1)

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    assert len(filled) == 1
    assert filled[0].signal_bar == 0
    assert filled[0].fill_bar == 1


def test_orb_trade_cap_two_allows_second_post_exit_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 100.5, 101.5, 102.0, 102.5, 103.0],
        [100.0, 100.2, 102.2, 101.8, 102.2, 104.2, 103.5],
        [100.0, 99.8, 100.4, 101.2, 101.8, 102.2, 102.8],
        [100.0, 100.0, 101.8, 101.6, 102.0, 103.8, 103.0],
    )
    candidates = [_cand(0, 100.0), _cand(1, 101.4), _cand(3, 102.0)]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=2)

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    no_fills = [t for t in trades if t.exit_type == EXIT_NO_FILL]

    assert [t.signal_bar for t in filled] == [0, 3]
    assert [t.fill_bar for t in filled] == [1, 4]
    assert len(no_fills) == 1
    assert no_fills[0].signal_bar == 1


def test_orb_reentry_does_not_skip_a_no_fill_first_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.6, 100.7, 101.0, 101.0, 103.0, 103.0],
        [100.0, 100.9, 101.0, 101.3, 103.2, 103.6, 103.4],
        [100.0, 100.4, 100.5, 100.8, 100.9, 102.8, 102.9],
        [100.0, 100.8, 100.9, 101.1, 102.9, 103.4, 103.1],
    )
    candidates = [_cand(0, 100.0), _cand(3, 101.0)]

    trades = _run_backtest_with_candidates(monkeypatch, df, candidates, trade_cap=2)

    assert all(t.exit_type == EXIT_NO_FILL for t in trades)


def test_orb_nonpositive_policy_blocks_second_trade_after_winner(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 100.5, 101.5, 102.0, 102.5, 103.0],
        [100.0, 100.2, 102.2, 101.8, 102.2, 104.2, 103.5],
        [100.0, 99.8, 100.4, 101.2, 101.8, 102.2, 102.8],
        [100.0, 100.0, 101.8, 101.6, 102.0, 103.8, 103.0],
    )
    candidates = [_cand(0, 100.0), _cand(1, 101.4), _cand(3, 102.0)]

    trades = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=2,
        reentry_policy="after_nonpositive_first",
    )

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    no_fills = [t for t in trades if t.exit_type == EXIT_NO_FILL]

    assert [t.signal_bar for t in filled] == [0]
    assert filled[0].r_multiple > 0
    assert [t.signal_bar for t in no_fills] == [1, 3]


def test_orb_nonpositive_policy_allows_second_trade_after_loss(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 99.1, 100.8, 101.0, 101.4, 101.8],
        [100.0, 100.2, 99.9, 101.0, 101.1, 103.2, 102.4],
        [100.0, 99.8, 98.8, 100.6, 100.8, 101.2, 101.5],
        [100.0, 100.0, 99.0, 100.9, 101.0, 102.8, 102.0],
    )
    candidates = [_cand(0, 100.0), _cand(3, 101.0)]

    trades = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=2,
        reentry_policy="after_nonpositive_first",
    )

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    assert [t.signal_bar for t in filled] == [0, 3]
    assert filled[0].exit_type == simulator.EXIT_SL
    assert filled[0].r_multiple < 0
    assert filled[1].fill_bar == 4


def test_negative_orb_trade_cap_rejected() -> None:
    with pytest.raises(ValueError, match="orb_trade_max_per_session must be >= 0"):
        StrategyConfig(orb_trade_max_per_session=-1)


def test_invalid_orb_reentry_policy_rejected() -> None:
    with pytest.raises(ValueError, match="orb_reentry_policy must be one of"):
        StrategyConfig(orb_reentry_policy="not_a_policy")


def test_wide_stop_target_reduction_uses_lower_effective_rr(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 100.4, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2],
        [100.0, 100.2, 101.3, 100.4, 100.4, 100.4, 100.4, 100.4, 100.4, 100.4, 100.4, 100.4, 100.4],
        [100.0, 99.8, 100.2, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1, 100.1],
        [100.0, 100.1, 100.3, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2, 100.2],
    )
    candidates = [_cand(0, 100.0)]

    normal = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        rr=3.0,
        tp1_ratio=0.5,
    )
    reduced = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        rr=3.0,
        tp1_ratio=0.5,
        wide_stop_target_threshold_points=0.5,
        wide_stop_target_rr=1.25,
    )

    normal_fill = [t for t in normal if t.exit_type != EXIT_NO_FILL][0]
    reduced_fill = [t for t in reduced if t.exit_type != EXIT_NO_FILL][0]

    assert normal_fill.tp2_price == pytest.approx(103.0)
    assert reduced_fill.tp2_price == pytest.approx(101.25)
    assert normal_fill.r_multiple < 1.0
    assert reduced_fill.r_multiple == pytest.approx(1.25)


def test_wide_stop_full_exit_at_tp1_uses_normal_tp1_as_full_target(monkeypatch: pytest.MonkeyPatch) -> None:
    df = _df(
        [100.0, 100.0, 100.4, 100.2, 100.2],
        [100.0, 100.2, 101.6, 100.4, 100.4],
        [100.0, 99.8, 100.2, 100.1, 100.1],
        [100.0, 100.1, 101.4, 100.2, 100.2],
    )
    candidates = [_cand(0, 100.0)]

    normal = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        rr=3.0,
        tp1_ratio=0.5,
    )
    full_at_tp1 = _run_backtest_with_candidates(
        monkeypatch,
        df,
        candidates,
        trade_cap=1,
        rr=3.0,
        tp1_ratio=0.5,
        wide_stop_target_threshold_points=0.5,
        wide_stop_full_exit_at_tp1=True,
    )

    normal_fill = [t for t in normal if t.exit_type != EXIT_NO_FILL][0]
    full_at_tp1_fill = [t for t in full_at_tp1 if t.exit_type != EXIT_NO_FILL][0]

    assert normal_fill.tp1_price == pytest.approx(101.5)
    assert normal_fill.tp2_price == pytest.approx(103.0)
    assert full_at_tp1_fill.tp1_price == pytest.approx(101.5)
    assert full_at_tp1_fill.tp2_price == pytest.approx(101.5)
    assert full_at_tp1_fill.r_multiple == pytest.approx(1.5)
    assert full_at_tp1_fill.r_multiple > normal_fill.r_multiple


def test_invalid_wide_stop_target_reduction_rejected() -> None:
    with pytest.raises(ValueError, match="wide_stop_target_rr must be >= 1.0"):
        StrategyConfig(wide_stop_target_rr=0.5)

    with pytest.raises(ValueError, match="wide_stop_target_rr must be <= rr"):
        StrategyConfig(rr=2.0, wide_stop_target_rr=2.5)
