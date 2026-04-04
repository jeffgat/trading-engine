"""Tests for ALPHA_V1 downside research helpers."""

from __future__ import annotations

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    build_drawdown_clusters,
    build_generalist_promotion_memo,
    pairwise_overlap,
    weakest_rolling_windows,
)
from orb_backtest.engine.simulator import EXIT_TP1_TP2, TradeResult


def _trade(date: str, direction: int = 1, r_multiple: float = 1.0) -> TradeResult:
    return TradeResult(
        date=date,
        session="NY",
        direction=direction,
        signal_bar=1,
        fill_bar=1,
        entry_price=100.0,
        stop_price=99.0,
        tp1_price=101.0,
        tp2_price=102.0,
        exit_type=EXIT_TP1_TP2,
        exit_bar=2,
        pnl_points=r_multiple,
        pnl_usd=r_multiple * 100.0,
        r_multiple=r_multiple,
        qty=2.0,
        half_qty=1.0,
        gap_size=1.0,
        risk_points=1.0,
        fill_time=f"{date}T10:00:00",
        exit_time=f"{date}T10:05:00",
    )


def test_build_drawdown_clusters_orders_by_depth() -> None:
    idx = pd.date_range("2025-01-01", periods=8, freq="B")
    series = pd.Series([1.0, -2.0, -1.0, 3.0, -1.0, -3.0, 1.0, 4.0], index=idx)

    clusters = build_drawdown_clusters(series, top_n=10)

    assert len(clusters) == 2
    assert clusters[0]["drawdown_r"] <= clusters[1]["drawdown_r"]
    assert clusters[0]["start_date"] == "2025-01-07"
    assert clusters[0]["recovery_date"] == "2025-01-10"


def test_weakest_rolling_windows_returns_worst_window() -> None:
    idx = pd.date_range("2025-01-01", periods=6, freq="B")
    series = pd.Series([2.0, -4.0, 1.0, -3.0, 2.0, 1.0], index=idx)

    windows = weakest_rolling_windows(series, windows={"short": 3}, top_n=2)

    assert windows["short"][0]["window_r"] == -6.0
    assert windows["short"][0]["start_date"] == "2025-01-02"
    assert windows["short"][0]["end_date"] == "2025-01-06"


def test_pairwise_overlap_measures_shared_trade_dates() -> None:
    left = [_trade("2025-01-02"), _trade("2025-01-03"), _trade("2025-01-06")]
    right = [_trade("2025-01-03"), _trade("2025-01-07")]

    rows = pairwise_overlap({"left": left, "right": right})

    assert len(rows) == 1
    row = rows[0]
    assert row["shared_trade_dates"] == 1
    assert row["jaccard_overlap"] == 0.25
    assert row["left_overlap_share"] == 0.3333
    assert row["right_overlap_share"] == 0.5


def test_generalist_promotion_memo_promotes_additive_candidate() -> None:
    idx = pd.date_range("2025-01-01", periods=90, freq="B")
    baseline_full = pd.Series([0.1] * len(idx), index=idx)
    baseline_full.iloc[10:20] = -0.6
    baseline_holdout = baseline_full.copy()

    combined_full = baseline_full.copy()
    combined_full.iloc[10:20] = -0.3
    combined_holdout = combined_full.copy()

    memo = build_generalist_promotion_memo(
        baseline_holdout_daily=baseline_holdout,
        baseline_full_daily=baseline_full,
        baseline_attr={"downside_regime_net_r": {"holdout": -10.0}},
        combined_holdout_daily=combined_holdout,
        combined_full_daily=combined_full,
        combined_attr={"downside_regime_net_r": {"holdout": -6.0}},
        standalone_metrics={
            "full": {"total_trades": 90, "r_by_year": {"2025": 20.0}, "avg_win_r": 0.6},
            "pre_holdout": {"total_r": 5.0},
            "holdout": {"total_r": 4.5},
        },
        psr_dsr={"psr": {"value": 0.98}, "dsr": {"value": 0.62}},
    )

    assert memo["verdict"] == "promote"
    assert memo["structural_screen"]["pass"] is True
    assert memo["additivity_checks"]["rule_a_pass"] is True
