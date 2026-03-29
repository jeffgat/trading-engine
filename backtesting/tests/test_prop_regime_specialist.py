from __future__ import annotations

import pandas as pd

from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    PropFirmProfile,
    bear_market_rank_key,
    block_bootstrap_outcomes,
    bull_market_rank_key,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    build_prop_scorecard,
    evaluate_bear_market_windows,
    evaluate_bull_market_windows,
    filter_trades_by_low_confidence,
    simulate_funded_first_payouts,
    simulate_account_attempts,
    trade_passes_structure_vwap_gate,
    trading_dates_from_calendar,
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


def test_filter_trades_by_low_confidence_can_exclude_flagged_days() -> None:
    trades = [
        _make_trade("2025-01-01", 1.0),
        _make_trade("2025-01-02", 1.0),
    ]
    calendar = pd.DataFrame(
        [
            {"date": pd.Timestamp("2025-01-01"), "regime": "bull", "low_confidence": True},
            {"date": pd.Timestamp("2025-01-02"), "regime": "bull", "low_confidence": False},
        ]
    )

    filtered = filter_trades_by_low_confidence(
        trades,
        calendar,
        include_low_confidence=False,
    )

    assert [trade.date for trade in filtered] == ["2025-01-02"]


def test_trading_dates_from_calendar_can_drop_low_confidence_days() -> None:
    calendar = pd.DataFrame(
        [
            {"date": pd.Timestamp("2025-01-01"), "regime": "warmup", "low_confidence": False},
            {"date": pd.Timestamp("2025-01-02"), "regime": "bull", "low_confidence": True},
            {"date": pd.Timestamp("2025-01-03"), "regime": "sideways", "low_confidence": False},
        ]
    )

    assert trading_dates_from_calendar(calendar) == ["2025-01-02", "2025-01-03"]
    assert trading_dates_from_calendar(calendar, include_low_confidence=False) == ["2025-01-03"]


def test_trade_passes_structure_vwap_gate_for_both_directions() -> None:
    long_trade = _make_trade("2025-01-02", 1.0)
    short_trade = _make_trade("2025-01-03", -1.0)
    signals = {
        "close": [101.0],
        "vwap": [100.0],
        "daily_atr": [10.0],
        "hh_hl_2_bull": [True],
        "hh_hl_2_bear": [True],
        "hh_hl_3_bull": [False],
        "hh_hl_3_bear": [False],
        "hh_hl_any2of3_bull": [True],
        "hh_hl_any2of3_bear": [True],
        "bull_score": [3],
        "bear_score": [3],
        "regime_2d_bull": [True],
        "regime_2d_bear": [True],
        "regime_2of3_bull": [True],
        "regime_2of3_bear": [True],
        "holds_vwap_bull": [True],
        "holds_vwap_bear": [True],
        "holds_vwap_orb_bull": [True],
        "holds_vwap_orb_bear": [True],
    }

    assert trade_passes_structure_vwap_gate("hh_hl_2_vwap", long_trade, signals) is True

    signals["close"][0] = 99.0
    signals["vwap"][0] = 100.0

    assert trade_passes_structure_vwap_gate("pullback_holds_vwap_orb", short_trade, signals) is True


def test_simulate_funded_first_payouts_tracks_fee_and_payout_amount() -> None:
    trades = [
        _make_trade("2025-01-01", 1.0),
        _make_trade("2025-01-02", 4.0),
    ]
    dates = ["2025-01-01", "2025-01-02"]
    profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
    )

    outcomes = simulate_funded_first_payouts(
        specialist_name="test",
        trades=trades,
        trading_dates=dates,
        profile=profile,
    )
    scorecard = build_funded_first_payout_scorecard(outcomes, profile)

    first = outcomes.iloc[0]
    assert first["outcome"] == "payout"
    assert first["calendar_days_to_outcome"] == 2
    assert first["first_payout_amount_usd"] == 500.0
    assert first["net_payout_after_fee_usd"] == 350.0
    assert scorecard["payout_rate"] == 1.0


def test_simulate_funded_first_payouts_caps_trailing_breach_at_start_balance() -> None:
    trades = [
        _make_trade("2025-01-01", 6.0),
        _make_trade("2025-01-02", -5.0),
    ]
    dates = ["2025-01-01", "2025-01-02"]
    profile = FundedFirstPayoutProfile(
        first_payout_floor_usd=99_999.0,
        risk_pre_payout_usd=500.0,
    )

    outcomes = simulate_funded_first_payouts(
        specialist_name="test",
        trades=trades,
        trading_dates=dates,
        profile=profile,
    )

    first = outcomes.iloc[0]
    assert first["outcome"] == "open"
    assert first["ending_balance_usd"] == 50_500.0
    assert first["breach_balance_usd"] == 50_000.0


def test_build_funded_first_payout_forecast_tracks_resolution_timeline() -> None:
    outcomes = pd.DataFrame(
        [
            {
                "specialist_name": "test",
                "account_start": "2025-01-01",
                "outcome": "payout",
                "outcome_date": "2025-01-10",
                "calendar_days_to_outcome": 10,
                "trades_to_outcome": 4,
                "ending_balance_usd": 52_300.0,
                "breach_balance_usd": 49_000.0,
                "highest_eod_balance_usd": 52_300.0,
                "first_payout_amount_usd": 300.0,
                "net_payout_after_fee_usd": 150.0,
            },
            {
                "specialist_name": "test",
                "account_start": "2025-01-02",
                "outcome": "breach",
                "outcome_date": "2025-01-15",
                "calendar_days_to_outcome": 15,
                "trades_to_outcome": 5,
                "ending_balance_usd": 48_900.0,
                "breach_balance_usd": 49_000.0,
                "highest_eod_balance_usd": 50_600.0,
                "first_payout_amount_usd": 0.0,
                "net_payout_after_fee_usd": -150.0,
            },
            {
                "specialist_name": "test",
                "account_start": "2025-01-03",
                "outcome": "payout",
                "outcome_date": "2025-01-20",
                "calendar_days_to_outcome": 20,
                "trades_to_outcome": 6,
                "ending_balance_usd": 52_800.0,
                "breach_balance_usd": 50_000.0,
                "highest_eod_balance_usd": 52_800.0,
                "first_payout_amount_usd": 800.0,
                "net_payout_after_fee_usd": 650.0,
            },
            {
                "specialist_name": "test",
                "account_start": "2025-01-04",
                "outcome": "open",
                "outcome_date": "2025-02-15",
                "calendar_days_to_outcome": 43,
                "trades_to_outcome": 3,
                "ending_balance_usd": 50_400.0,
                "breach_balance_usd": 49_000.0,
                "highest_eod_balance_usd": 50_700.0,
                "first_payout_amount_usd": 0.0,
                "net_payout_after_fee_usd": -150.0,
            },
        ]
    )

    forecast = build_funded_first_payout_forecast(outcomes, horizons_days=(10, 15, 20))

    assert forecast["total_starts"] == 4
    assert forecast["payout_days_quantiles"]["p50"] == 15.0
    assert forecast["breach_days_quantiles"]["p50"] == 15.0
    assert forecast["resolution_days_quantiles"]["p75"] == 17.5
    assert forecast["timeline"] == [
        {
            "horizon_days": 10,
            "payout_rate_by_horizon": 0.25,
            "breach_rate_by_horizon": 0.0,
            "resolved_rate_by_horizon": 0.25,
            "payout_share_of_resolved_by_horizon": 1.0,
            "open_rate_after_horizon": 0.75,
        },
        {
            "horizon_days": 15,
            "payout_rate_by_horizon": 0.25,
            "breach_rate_by_horizon": 0.25,
            "resolved_rate_by_horizon": 0.5,
            "payout_share_of_resolved_by_horizon": 0.5,
            "open_rate_after_horizon": 0.5,
        },
        {
            "horizon_days": 20,
            "payout_rate_by_horizon": 0.5,
            "breach_rate_by_horizon": 0.25,
            "resolved_rate_by_horizon": 0.75,
            "payout_share_of_resolved_by_horizon": 0.6667,
            "open_rate_after_horizon": 0.25,
        },
    ]


def test_evaluate_bull_market_windows_uses_fixed_year_buckets() -> None:
    trades = [
        _make_trade("2021-06-01", 0.5),
        _make_trade("2022-05-01", -1.0),
        _make_trade("2024-06-01", 1.0),
        _make_trade("2025-01-02", 5.0),
    ]
    trading_dates = [
        "2021-06-01",
        "2022-05-01",
        "2024-06-01",
        "2025-01-02",
        "2025-01-03",
    ]
    profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
    )

    windows = evaluate_bull_market_windows(
        specialist_name="bull_v1",
        trades=trades,
        trading_dates=trading_dates,
        funded_profile=profile,
        min_acceptance_trades=2,
    )

    assert windows["diagnostic_2021"]["total_trades"] == 1
    assert windows["rejection_2022_2023"]["total_trades"] == 1
    assert windows["acceptance_2024_latest"]["total_trades"] == 2
    assert windows["passes_bull_v1"]["acceptance_positive_net_r"] is True
    assert windows["passes_bull_v1"]["acceptance_min_trades"] is True


def test_bull_market_rank_key_prioritizes_holdout_then_acceptance_then_speed() -> None:
    slower_better = {
        "survives_bull_v1": True,
        "acceptance_net_r": 8.0,
        "acceptance_rejection_separation": 8.0,
        "holdout_2025_latest": {
            "payout_rate": 0.8,
            "breach_rate": 0.2,
            "average_days_to_payout": 30.0,
        },
    }
    faster_worse = {
        "survives_bull_v1": True,
        "acceptance_net_r": 6.0,
        "acceptance_rejection_separation": 6.0,
        "holdout_2025_latest": {
            "payout_rate": 0.7,
            "breach_rate": 0.2,
            "average_days_to_payout": 10.0,
        },
    }

    assert bull_market_rank_key(slower_better) > bull_market_rank_key(faster_worse)


def test_evaluate_bear_market_windows_uses_fixed_year_buckets() -> None:
    trades = [
        _make_trade("2021-06-01", -0.5),
        _make_trade("2022-05-01", 1.0),
        _make_trade("2023-06-01", 5.0),
        _make_trade("2024-06-03", -1.0),
    ]
    trading_dates = [
        "2021-06-01",
        "2022-05-01",
        "2023-06-01",
        "2023-06-02",
        "2024-06-03",
    ]
    profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
    )

    windows = evaluate_bear_market_windows(
        specialist_name="bear_v1",
        trades=trades,
        trading_dates=trading_dates,
        funded_profile=profile,
        min_acceptance_trades=2,
    )

    assert windows["diagnostic_2021"]["total_trades"] == 1
    assert windows["acceptance_2022_2023"]["total_trades"] == 2
    assert windows["holdout_2023"]["payout_rate"] == 0.5
    assert windows["holdout_2023"]["breach_rate"] == 0.0
    assert windows["rejection_2024_latest"]["total_trades"] == 1
    assert windows["passes_bear_v1"]["acceptance_positive_net_r"] is True
    assert windows["passes_bear_v1"]["acceptance_min_trades"] is True


def test_bear_market_rank_key_prioritizes_holdout_then_acceptance_then_speed() -> None:
    slower_better = {
        "survives_bear_v1": True,
        "acceptance_net_r": 8.0,
        "acceptance_rejection_separation": 8.0,
        "holdout_2023": {
            "payout_rate": 0.8,
            "breach_rate": 0.2,
            "average_days_to_payout": 30.0,
        },
    }
    faster_worse = {
        "survives_bear_v1": True,
        "acceptance_net_r": 6.0,
        "acceptance_rejection_separation": 6.0,
        "holdout_2023": {
            "payout_rate": 0.7,
            "breach_rate": 0.2,
            "average_days_to_payout": 10.0,
        },
    }

    assert bear_market_rank_key(slower_better) > bear_market_rank_key(faster_worse)
