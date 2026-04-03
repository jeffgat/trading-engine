"""Tests for the NQ regime research module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_START,
    RegimeChallengerSpec,
    TrendFeatureSpec,
    TrialCounter,
    VolFeatureSpec,
    _build_daily_feature_frame,
    attribute_strategy_by_regime,
    audit_regime_definition,
    build_extended_regime_calendar,
    build_stage_a_scoreboard,
    compute_bucket_metrics,
    compute_vol_thresholds,
    count_regime_episodes,
    evaluate_challenger_stage_a,
    evaluate_promotion_criteria,
    make_regime_gate,
    make_baseline_challenger_spec,
    search_regime_thresholds,
    validate_regime_walkforward,
)
from orb_backtest.engine.simulator import EXIT_NO_FILL, EXIT_TP1_TP2, TradeResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trade(trade_date: str, r_multiple: float, direction: int = 1) -> TradeResult:
    """Create a minimal TradeResult for testing."""
    pnl_usd = r_multiple * 5000.0
    return TradeResult(
        date=trade_date,
        session="NY",
        direction=direction,
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


def _make_no_fill(trade_date: str) -> TradeResult:
    """Create a no-fill trade."""
    return TradeResult(
        date=trade_date,
        session="NY",
        direction=1,
        signal_bar=0,
        fill_bar=-1,
        entry_price=0.0,
        stop_price=0.0,
        tp1_price=0.0,
        tp2_price=0.0,
        exit_type=EXIT_NO_FILL,
        exit_bar=-1,
        pnl_points=0.0,
        pnl_usd=0.0,
        r_multiple=0.0,
        qty=0.0,
        half_qty=0.0,
        gap_size=0.0,
        risk_points=0.0,
        fill_time="",
        exit_time="",
    )


def _make_5m_df(n_days: int = 60, start: str = "2020-01-02") -> pd.DataFrame:
    """Build a synthetic 5m DataFrame with enough bars for regime computation.

    Creates 78 bars/day (6:30 AM to 13:00 with 5m spacing) over n_days business days.
    """
    dates = pd.bdate_range(start, periods=n_days, freq="B")
    bars_per_day = 78
    timestamps = []
    for d in dates:
        for i in range(bars_per_day):
            timestamps.append(d + pd.Timedelta(minutes=5 * i + 390))  # 6:30 AM start

    idx = pd.DatetimeIndex(timestamps)
    n_bars = len(idx)
    rng = np.random.default_rng(42)

    # Generate a trending price series with some volatility variation
    returns = rng.normal(0.0005, 0.005, n_bars)
    close = 20000.0 * np.exp(np.cumsum(returns))

    df = pd.DataFrame(
        {
            "open": close * (1 + rng.normal(0, 0.001, n_bars)),
            "high": close * (1 + np.abs(rng.normal(0, 0.003, n_bars))),
            "low": close * (1 - np.abs(rng.normal(0, 0.003, n_bars))),
            "close": close,
            "volume": rng.integers(100, 10000, n_bars),
        },
        index=idx,
    )
    return df


def _make_regime_calendar() -> pd.DataFrame:
    """Build a synthetic regime calendar for testing."""
    dates = pd.bdate_range("2020-01-02", periods=100, freq="B")
    rng = np.random.default_rng(42)

    regimes = rng.choice(["bull", "bear", "sideways"], size=len(dates))
    vol_regimes = rng.choice(["low_vol", "medium_vol", "high_vol"], size=len(dates))
    vol_values = rng.uniform(0.10, 0.40, size=len(dates))

    cal = pd.DataFrame({
        "date": dates,
        "regime": regimes,
        "vol_regime": vol_regimes,
        "combined_regime": [f"{r}_{v}" for r, v in zip(regimes, vol_regimes)],
        "close_vs_sma20": rng.normal(0, 0.02, len(dates)),
        "ret_5d": rng.normal(0, 0.03, len(dates)),
        "realized_vol_21d": vol_values,
        "warmup_ok": True,
        "low_confidence": rng.random(len(dates)) < 0.1,
    })
    return cal


# ---------------------------------------------------------------------------
# Tests: Extended regime calendar
# ---------------------------------------------------------------------------


class TestBuildExtendedRegimeCalendar:
    """Tests for build_extended_regime_calendar."""

    def test_adds_vol_axis(self):
        df = _make_5m_df(n_days=60, start="2020-01-02")
        cal = build_extended_regime_calendar(
            df, holdout_start="2023-01-01",
        )

        assert "vol_regime" in cal.columns
        assert "combined_regime" in cal.columns
        assert "regime" in cal.columns  # backward compat

        # vol_regime values must be valid
        valid_vol = {"low_vol", "medium_vol", "high_vol", "unknown"}
        assert set(cal["vol_regime"].unique()).issubset(valid_vol)

        # combined_regime should be trend_vol for non-warmup
        warmup_ok = cal[cal["warmup_ok"] == True]
        for _, row in warmup_ok.iterrows():
            expected = f"{row['regime']}_{row['vol_regime']}"
            assert row["combined_regime"] == expected

    def test_warmup_gets_unknown_vol(self):
        df = _make_5m_df(n_days=60, start="2020-01-02")
        cal = build_extended_regime_calendar(
            df, holdout_start="2023-01-01",
        )
        warmup_rows = cal[cal["regime"] == "warmup"]
        if not warmup_rows.empty:
            assert (warmup_rows["vol_regime"] == "unknown").all()
            assert (warmup_rows["combined_regime"] == "warmup").all()


class TestComputeVolThresholds:
    """Tests for compute_vol_thresholds."""

    def test_uses_pre_holdout_only(self):
        """Post-holdout extreme vol should not affect thresholds."""
        cal = _make_regime_calendar()
        holdout_start = "2020-04-01"

        # Compute thresholds normally
        t1 = compute_vol_thresholds(cal, holdout_start)

        # Add extreme vol to post-holdout period
        cal_extreme = cal.copy()
        post = cal_extreme["date"] >= pd.Timestamp(holdout_start)
        cal_extreme.loc[post, "realized_vol_21d"] = 99.0

        t2 = compute_vol_thresholds(cal_extreme, holdout_start)

        assert t1["low_upper"] == t2["low_upper"]
        assert t1["medium_upper"] == t2["medium_upper"]

    def test_tercile_bucketing(self):
        """Known vol values should produce correct tercile boundaries."""
        # Create calendar with known vol distribution
        dates = pd.bdate_range("2020-01-02", periods=30, freq="B")
        cal = pd.DataFrame({
            "date": dates,
            "realized_vol_21d": np.linspace(0.10, 0.40, len(dates)),
            "warmup_ok": True,
        })

        thresholds = compute_vol_thresholds(cal, "2025-01-01", method="tercile")
        assert "low_upper" in thresholds
        assert "medium_upper" in thresholds
        assert thresholds["low_upper"] < thresholds["medium_upper"]

    def test_quartile_method(self):
        cal = _make_regime_calendar()
        thresholds = compute_vol_thresholds(cal, "2025-01-01", method="quartile")
        assert "q25" in thresholds
        assert "q50" in thresholds
        assert "q75" in thresholds


# ---------------------------------------------------------------------------
# Tests: Episode counting
# ---------------------------------------------------------------------------


class TestCountRegimeEpisodes:
    """Tests for count_regime_episodes."""

    def test_counts_episodes_correctly(self):
        """Known sequence should produce correct episode counts."""
        cal = pd.DataFrame({
            "date": pd.bdate_range("2020-01-02", periods=10, freq="B"),
            "combined_regime": [
                "bull_low_vol", "bull_low_vol", "bull_low_vol",  # 1 episode, 3 days
                "bear_high_vol", "bear_high_vol",                 # 1 episode, 2 days
                "bull_low_vol", "bull_low_vol",                   # 1 episode, 2 days
                "sideways_medium_vol",                            # 1 episode, 1 day
                "sideways_medium_vol", "sideways_medium_vol",     # continues, 3 days total
            ],
            "warmup_ok": True,
        })

        result = count_regime_episodes(cal, "combined_regime")
        assert len(result) == 3  # 3 distinct regime labels

        bull = result[result["regime"] == "bull_low_vol"].iloc[0]
        assert bull["episode_count"] == 2
        assert bull["mean_duration"] == 2.5

        bear = result[result["regime"] == "bear_high_vol"].iloc[0]
        assert bear["episode_count"] == 1
        assert bear["mean_duration"] == 2.0

        sideways = result[result["regime"] == "sideways_medium_vol"].iloc[0]
        assert sideways["episode_count"] == 1
        assert sideways["mean_duration"] == 3.0


# ---------------------------------------------------------------------------
# Tests: Audit
# ---------------------------------------------------------------------------


class TestAuditRegimeDefinition:
    """Tests for audit_regime_definition."""

    def test_produces_required_keys(self):
        cal = _make_regime_calendar()
        audit = audit_regime_definition(cal, holdout_start="2020-04-01")

        assert "rule_spec" in audit
        assert "yearly_trend_counts" in audit
        assert "yearly_vol_counts" in audit
        assert "yearly_combined_counts" in audit
        assert "pre_holdout_summary" in audit
        assert "combined_episodes" in audit

    def test_pre_holdout_summary_has_counts(self):
        cal = _make_regime_calendar()
        audit = audit_regime_definition(cal, holdout_start="2020-04-01")

        summary = audit["pre_holdout_summary"]
        assert summary["total_days"] > 0
        assert "trend_counts" in summary
        assert "vol_counts" in summary
        assert "combined_counts" in summary


# ---------------------------------------------------------------------------
# Tests: Attribution
# ---------------------------------------------------------------------------


class TestAttributeStrategyByRegime:
    """Tests for attribute_strategy_by_regime."""

    def test_maps_trades_to_correct_regime(self):
        cal = _make_regime_calendar()
        # Pick a date from the calendar and get its regime
        row = cal.iloc[10]
        trade_date = pd.Timestamp(row["date"]).strftime("%Y-%m-%d")
        expected_regime = row["combined_regime"]

        trades = [_make_trade(trade_date, 1.5)]
        attr = attribute_strategy_by_regime(trades, cal)

        assert len(attr) == 1
        assert attr.iloc[0]["combined_regime"] == expected_regime

    def test_skips_no_fill_trades(self):
        cal = _make_regime_calendar()
        trade_date = pd.Timestamp(cal.iloc[5]["date"]).strftime("%Y-%m-%d")
        trades = [_make_no_fill(trade_date), _make_trade(trade_date, 2.0)]
        attr = attribute_strategy_by_regime(trades, cal)

        assert len(attr) == 1  # Only the filled trade

    def test_labels_holdout_period(self):
        cal = _make_regime_calendar()
        holdout_start = "2020-03-01"

        # Trade before holdout
        pre_date = pd.Timestamp(cal.iloc[5]["date"]).strftime("%Y-%m-%d")
        # Trade after holdout
        post_date = pd.Timestamp(cal.iloc[-1]["date"]).strftime("%Y-%m-%d")

        trades = [_make_trade(pre_date, 1.0), _make_trade(post_date, -0.5)]
        attr = attribute_strategy_by_regime(trades, cal, holdout_start=holdout_start)

        pre_row = attr[attr["date"] == pre_date].iloc[0]
        post_row = attr[attr["date"] == post_date].iloc[0]
        assert pre_row["period"] == "pre_holdout"
        assert post_row["period"] == "holdout"


# ---------------------------------------------------------------------------
# Tests: Regime gate
# ---------------------------------------------------------------------------


class TestMakeRegimeGate:
    """Tests for make_regime_gate."""

    def test_keeps_only_target_regime(self):
        cal = _make_regime_calendar()

        # Find a regime that has at least one date
        target = cal.iloc[0]["combined_regime"]
        target_dates = set(
            pd.to_datetime(cal[cal["combined_regime"] == target]["date"])
            .dt.strftime("%Y-%m-%d")
        )
        non_target_dates = set(
            pd.to_datetime(cal[cal["combined_regime"] != target]["date"])
            .dt.strftime("%Y-%m-%d")
        )

        trades = []
        for d in list(target_dates)[:3]:
            trades.append(_make_trade(d, 1.0))
        for d in list(non_target_dates)[:3]:
            trades.append(_make_trade(d, -1.0))

        gate = make_regime_gate(cal, target)
        filtered = gate(trades)

        # All filtered trades should be on target-regime dates
        for t in filtered:
            assert t.date in target_dates

        # Should have filtered out non-target trades
        assert len(filtered) <= len(trades)


# ---------------------------------------------------------------------------
# Tests: Promotion criteria
# ---------------------------------------------------------------------------


class TestEvaluatePromotionCriteria:
    """Tests for evaluate_promotion_criteria."""

    def test_checks_episode_count(self):
        cal = _make_regime_calendar()
        target = cal.iloc[0]["combined_regime"]

        # Get dates for this regime
        target_dates = (
            pd.to_datetime(cal[cal["combined_regime"] == target]["date"])
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )

        # Create enough winning trades
        trades = [_make_trade(d, 1.5) for d in target_dates[:5]]

        result = evaluate_promotion_criteria(
            strategy_name="test_strategy",
            target_regime=target,
            trades=trades,
            regime_calendar=cal,
            min_trades=2,
            min_episodes=1,
            holdout_start="2025-01-01",
        )

        assert "criteria" in result
        assert "min_episodes_with_trades" in result["criteria"]
        assert isinstance(result["criteria"]["min_episodes_with_trades"]["value"], int)

    def test_not_promoted_when_negative_expectancy(self):
        cal = _make_regime_calendar()
        target = cal.iloc[0]["combined_regime"]
        target_dates = (
            pd.to_datetime(cal[cal["combined_regime"] == target]["date"])
            .dt.strftime("%Y-%m-%d")
            .tolist()
        )

        # All losing trades
        trades = [_make_trade(d, -1.0) for d in target_dates]

        result = evaluate_promotion_criteria(
            strategy_name="test_strategy",
            target_regime=target,
            trades=trades,
            regime_calendar=cal,
            min_trades=1,
            min_episodes=1,
            holdout_start="2025-01-01",
        )

        assert result["promoted"] is False
        assert result["criteria"]["positive_in_regime_expectancy"]["pass"] is False


# ---------------------------------------------------------------------------
# Tests: Bucket metrics
# ---------------------------------------------------------------------------


class TestComputeBucketMetrics:
    """Tests for compute_bucket_metrics."""

    def test_computes_correctly(self):
        attr_df = pd.DataFrame({
            "combined_regime": ["bull_low_vol", "bull_low_vol", "bear_high_vol"],
            "r_multiple": [2.0, -1.0, 1.5],
        })

        result = compute_bucket_metrics(attr_df, "combined_regime")
        assert len(result) == 2

        bull = result[result["bucket"] == "bull_low_vol"].iloc[0]
        assert bull["trade_count"] == 2
        assert bull["avg_r"] == pytest.approx(0.5, abs=0.01)
        assert bull["total_r"] == pytest.approx(1.0, abs=0.01)

    def test_empty_df(self):
        result = compute_bucket_metrics(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Tests: Trial counter
# ---------------------------------------------------------------------------


class TestTrialCounter:
    """Tests for TrialCounter."""

    def test_tracks_and_reports(self):
        tc = TrialCounter()
        tc.add("phase_b", 18)
        tc.add("phase_c", 8)
        tc.add("phase_b", 5)  # cumulative

        assert tc.total == 31
        assert tc.phases["phase_b"] == 23
        assert tc.phases["phase_c"] == 8
        assert "phase_b: 23" in tc.summary()
        assert "total=31" in tc.summary()


# ---------------------------------------------------------------------------
# Tests: Threshold search
# ---------------------------------------------------------------------------


class TestSearchRegimeThresholds:
    """Tests for search_regime_thresholds."""

    def test_returns_one_row_per_variant(self):
        df = _make_5m_df(n_days=60, start="2020-01-02")
        variants = [
            {"trend_sma_threshold": 0.005, "trend_ret5d_threshold": 0.0, "vol_method": "tercile"},
            {"trend_sma_threshold": 0.01, "trend_ret5d_threshold": 0.005, "vol_method": "tercile"},
        ]
        result = search_regime_thresholds(df, variants, holdout_start="2023-01-01")

        assert len(result) == 2
        assert "trial_id" in result.columns
        assert "min_bucket_share" in result.columns
        assert result["trial_id"].tolist() == [0, 1]


# ---------------------------------------------------------------------------
# Tests: Challenger framework
# ---------------------------------------------------------------------------


def _make_trend_ema20_spec() -> RegimeChallengerSpec:
    baseline = make_baseline_challenger_spec()
    return RegimeChallengerSpec(
        name="trend_ema20",
        family="trend_only",
        trend=TrendFeatureSpec(
            name="close_vs_ema20",
            feature_col="close_vs_ema20",
            formula="close / EMA20 - 1",
            bull_threshold=0.005,
            bear_threshold=-0.005,
            ret5d_threshold=0.0,
        ),
        vol=baseline.vol,
    )


def _make_vol_yang_zhang_spec() -> RegimeChallengerSpec:
    baseline = make_baseline_challenger_spec()
    return RegimeChallengerSpec(
        name="vol_yang_zhang21",
        family="vol_only",
        trend=baseline.trend,
        vol=VolFeatureSpec(
            name="yang_zhang_21d",
            feature_col="yang_zhang_21d",
            formula="21-day Yang-Zhang volatility, annualized",
            bucketing_method="tercile",
        ),
    )


class TestChallengerFramework:
    def test_feature_builders_are_shifted_one_session(self):
        df = _make_5m_df(n_days=180, start="2020-01-02")
        raw = _build_daily_feature_frame(df).reset_index(drop=True)

        specs = [
            make_baseline_challenger_spec(),
            _make_trend_ema20_spec(),
            _make_vol_yang_zhang_spec(),
        ]

        for spec in specs:
            cal = build_extended_regime_calendar(
                df,
                holdout_start="2025-01-01",
                challenger_spec=spec,
            )
            expected_trend = raw[spec.trend.feature_col].shift(1)
            expected_vol = raw[spec.vol.feature_col].shift(1)

            trend_mask = cal["trend_value"].notna() & expected_trend.notna()
            vol_mask = cal["vol_value"].notna() & expected_vol.notna()

            np.testing.assert_allclose(
                cal.loc[trend_mask, "trend_value"],
                expected_trend.loc[trend_mask],
                rtol=0,
                atol=1e-12,
            )
            np.testing.assert_allclose(
                cal.loc[vol_mask, "vol_value"],
                expected_vol.loc[vol_mask],
                rtol=0,
                atol=1e-12,
            )

    def test_challenger_labels_are_deterministic(self):
        df = _make_5m_df(n_days=180, start="2020-01-02")
        specs = [
            make_baseline_challenger_spec(),
            _make_trend_ema20_spec(),
            _make_vol_yang_zhang_spec(),
        ]

        for spec in specs:
            cal_a = build_extended_regime_calendar(
                df,
                holdout_start="2025-01-01",
                challenger_spec=spec,
            )
            cal_b = build_extended_regime_calendar(
                df,
                holdout_start="2025-01-01",
                challenger_spec=spec,
            )
            assert cal_a[["regime", "vol_regime", "combined_regime"]].equals(
                cal_b[["regime", "vol_regime", "combined_regime"]]
            )

    def test_walkforward_thresholds_use_is_data_only(self):
        df = _make_5m_df(n_days=800, start="2020-01-02")
        base = validate_regime_walkforward(
            df,
            holdout_start="2022-12-01",
            is_months=6,
            oos_months=3,
            step_months=3,
        )

        assert base["folds"]
        first_is_end = pd.Timestamp(base["folds"][0]["is_end"])

        mutated = df.copy()
        mask = mutated.index > first_is_end
        mutated.loc[mask, "close"] = mutated.loc[mask, "close"] * 1.50
        mutated.loc[mask, "open"] = mutated.loc[mask, "open"] * 1.50
        mutated.loc[mask, "high"] = mutated.loc[mask, "high"] * 1.55
        mutated.loc[mask, "low"] = mutated.loc[mask, "low"] * 1.45

        compare = validate_regime_walkforward(
            mutated,
            holdout_start="2022-12-01",
            is_months=6,
            oos_months=3,
            step_months=3,
        )

        assert base["folds"][0]["is_vol_thresholds"] == compare["folds"][0]["is_vol_thresholds"]

    def test_stage_a_ranking_ignores_holdout_edits(self):
        df = _make_5m_df(n_days=900, start="2020-01-02")
        spec = make_baseline_challenger_spec()

        base = evaluate_challenger_stage_a(
            df,
            spec,
            holdout_start="2022-12-01",
            is_months=6,
            oos_months=3,
            step_months=3,
        )

        mutated = df.copy()
        holdout_mask = mutated.index >= pd.Timestamp("2022-12-01")
        mutated.loc[holdout_mask, "close"] = mutated.loc[holdout_mask, "close"] * 0.70
        mutated.loc[holdout_mask, "open"] = mutated.loc[holdout_mask, "open"] * 0.70
        mutated.loc[holdout_mask, "high"] = mutated.loc[holdout_mask, "high"] * 0.72
        mutated.loc[holdout_mask, "low"] = mutated.loc[holdout_mask, "low"] * 0.68

        compare = evaluate_challenger_stage_a(
            mutated,
            spec,
            holdout_start="2022-12-01",
            is_months=6,
            oos_months=3,
            step_months=3,
        )

        assert base["selection_metrics"] == compare["selection_metrics"]

    def test_stage_a_scoreboard_tracks_trial_counts_and_family_counts(self):
        trial_counter = TrialCounter()
        trial_counter.add("stage_a_model_specs", 8)
        trial_counter.add("stage_a_wf_folds", 24)

        scoreboard = build_stage_a_scoreboard(
            stage_a_results=[
                {
                    "name": "baseline_v1",
                    "family": "baseline",
                    "selection_metrics": {
                        "total_pre_holdout_days": 100,
                        "min_bucket_share": 0.04,
                        "min_bucket_days": 40,
                        "min_bucket_episodes": 10,
                        "ambiguity_rate": 0.10,
                        "mean_label_agreement": 0.90,
                        "threshold_drift_score": 0.01,
                        "distribution_concentration": 0.40,
                    },
                },
                {
                    "name": "trend_ema20",
                    "family": "trend_only",
                    "selection_metrics": {
                        "total_pre_holdout_days": 100,
                        "min_bucket_share": 0.05,
                        "min_bucket_days": 50,
                        "min_bucket_episodes": 12,
                        "ambiguity_rate": 0.12,
                        "mean_label_agreement": 0.91,
                        "threshold_drift_score": 0.02,
                        "distribution_concentration": 0.35,
                    },
                },
            ],
            trial_counter=trial_counter,
            holdout_start=REGIME_RESEARCH_HOLDOUT_START,
        )

        assert scoreboard["trial_counts"] == {
            "stage_a_model_specs": 8,
            "stage_a_wf_folds": 24,
        }
        assert scoreboard["trial_count_total"] == 32
        assert scoreboard["family_counts"] == {
            "baseline": 1,
            "trend_only": 1,
        }
        assert scoreboard["holdout_used_for_ranking"] is False
