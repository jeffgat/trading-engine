from __future__ import annotations

import pandas as pd

from orb_backtest.analysis.prop_regime_specialist import (
    PropFirmProfile,
    block_bootstrap_outcomes,
    build_nq_ny_regime_calendar,
    build_prop_scorecard,
    simulate_account_attempts,
)
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import EXIT_TP1_TP2, TradeResult
from orb_backtest.engine.vwap_simulator import build_vwap_signal_cache
from orb_backtest.vwap_config import default_vwap_config


def _make_trade(trade_date: str, r_multiple: float) -> TradeResult:
    pnl_usd = r_multiple * 5000.0
    return TradeResult(
        date=trade_date,
        session="NY",
        direction=1 if r_multiple >= 0 else -1,
        signal_bar=0,
        fill_bar=0,
        entry_price=100.0,
        stop_price=99.0,
        tp1_price=101.0,
        tp2_price=102.0,
        exit_type=EXIT_TP1_TP2,
        exit_bar=0,
        pnl_points=r_multiple,
        pnl_usd=pnl_usd,
        r_multiple=r_multiple,
        qty=1.0,
        half_qty=0.5,
        gap_size=1.0,
        risk_points=1.0,
        fill_time=f"{trade_date}T09:30:00",
        exit_time=f"{trade_date}T10:00:00",
    )


def test_build_nq_ny_regime_calendar_is_point_in_time() -> None:
    idx = pd.bdate_range("2025-01-01", periods=45, freq="B") + pd.Timedelta(hours=9, minutes=30)
    base_close = pd.Series(range(100, 145), index=idx, dtype=float)
    df = pd.DataFrame(
        {
            "open": base_close - 0.25,
            "high": base_close + 0.5,
            "low": base_close - 0.5,
            "close": base_close,
            "volume": 1_000,
        },
        index=idx,
    )

    cal_a = build_nq_ny_regime_calendar(df)

    changed = df.copy()
    target_day = idx[35]
    changed.loc[target_day, "close"] = 10.0
    changed.loc[target_day, "high"] = 10.5
    changed.loc[target_day, "low"] = 9.5
    cal_b = build_nq_ny_regime_calendar(changed)

    same_day = pd.Timestamp(target_day).normalize()
    next_day = pd.Timestamp(idx[36]).normalize()

    row_a_same = cal_a.loc[cal_a["date"] == same_day].iloc[0]
    row_b_same = cal_b.loc[cal_b["date"] == same_day].iloc[0]
    row_a_next = cal_a.loc[cal_a["date"] == next_day].iloc[0]
    row_b_next = cal_b.loc[cal_b["date"] == next_day].iloc[0]

    assert row_a_same["regime"] == row_b_same["regime"]
    assert row_a_same["close_vs_sma20"] == row_b_same["close_vs_sma20"]
    assert row_a_same["ret_5d"] == row_b_same["ret_5d"]
    assert row_a_next["close_vs_sma20"] != row_b_next["close_vs_sma20"]


def test_simulate_account_attempts_respects_min_trading_days_for_payout() -> None:
    trades = [_make_trade(f"2025-01-0{i}", 1.0) for i in range(1, 6)]
    trading_dates = [f"2025-01-0{i}" for i in range(1, 7)]
    profile = PropFirmProfile(payout_target_r=3.0, min_trading_days=5)

    outcomes = simulate_account_attempts(
        specialist_name="test",
        trades=trades,
        trading_dates=trading_dates,
        profile=profile,
        risk_per_r_usd=5000.0,
    )

    first = outcomes.iloc[0]
    assert first["outcome"] == "payout"
    assert first["trading_days_to_outcome"] == 5
    assert first["days_to_outcome"] == 5
    assert first["trades_to_outcome"] == 5


def test_simulate_account_attempts_can_breach_on_daily_loss_limit() -> None:
    trades = [
        _make_trade("2025-01-01", -2.5),
        _make_trade("2025-01-02", 1.0),
    ]
    trading_dates = ["2025-01-01", "2025-01-02", "2025-01-03"]
    profile = PropFirmProfile(daily_loss_limit_r=-2.0, breach_limit_r=-4.0)

    outcomes = simulate_account_attempts(
        specialist_name="test",
        trades=trades,
        trading_dates=trading_dates,
        profile=profile,
        risk_per_r_usd=5000.0,
    )

    first = outcomes.iloc[0]
    assert first["outcome"] == "breach"
    assert first["breach_reason"] == "daily_loss_limit"
    assert first["days_to_outcome"] == 1


def test_build_prop_scorecard_and_bootstrap_are_reproducible() -> None:
    outcomes = pd.DataFrame(
        [
            {
                "specialist_name": "test",
                "account_start": f"2025-01-{i:02d}",
                "outcome": "payout" if i % 3 else "breach",
                "outcome_date": f"2025-01-{min(i + 2, 28):02d}",
                "days_to_outcome": 3,
                "trades_to_outcome": 2,
                "trading_days_to_outcome": 2,
                "final_r": 5.0 if i % 3 else -4.0,
                "peak_r": 5.0 if i % 3 else 0.0,
                "trough_r": -1.0 if i % 3 else -4.0,
                "net_payout": 19950.0 if i % 3 else -100.0,
                "breach_reason": "" if i % 3 else "max_drawdown",
            }
            for i in range(1, 13)
        ]
    )
    profile = PropFirmProfile()

    scorecard = build_prop_scorecard(outcomes, profile)
    boot_a = block_bootstrap_outcomes(outcomes, block_size=4, n_sims=25, seed=7)
    boot_b = block_bootstrap_outcomes(outcomes, block_size=4, n_sims=25, seed=7)

    assert scorecard["total_attempts"] == 12
    assert scorecard["ev_by_cohort"]["10"] == round(scorecard["ev_per_attempt"] * 10, 2)
    assert boot_a == boot_b


def test_vwap_signal_cache_builds_for_default_ny_config() -> None:
    idx = pd.date_range("2025-01-02 09:30", periods=12, freq="5min")
    close = pd.Series([100.0 + i * 0.25 for i in range(len(idx))], index=idx)
    df = pd.DataFrame(
        {
            "open": close - 0.1,
            "high": close + 0.2,
            "low": close - 0.2,
            "close": close,
            "volume": 1000,
        },
        index=idx,
    )

    cache = build_vwap_signal_cache(df, [default_vwap_config(NQ)])

    assert "session" in cache
    assert "vwap_signals" in cache
