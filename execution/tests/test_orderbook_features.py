"""Tests for order-book dynamic-sizing helpers."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trader.orderbook_features import (
    DynamicSizingContext,
    OrderbookDynamicSizingConfig,
    OrderbookFeatureCache,
    OrderbookVelocityTierSizer,
    ScoredFeatureLookupProvider,
)

ET = ZoneInfo("America/New_York")


def dt(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)


def test_frozen_thresholds_match_pure_1m_survivor():
    sizer = OrderbookVelocityTierSizer()

    low = sizer.decision_from_feature_value(-0.3221, sample_count=2)
    edge_mid = sizer.decision_from_feature_value(-0.322, sample_count=2)
    mid = sizer.decision_from_feature_value(0.9, sample_count=2)
    high = sizer.decision_from_feature_value(0.912, sample_count=2)

    assert low.tier == "low"
    assert low.risk_weight == pytest.approx(0.5)
    assert edge_mid.tier == "mid"
    assert edge_mid.risk_weight == pytest.approx(1.0)
    assert mid.tier == "mid"
    assert high.tier == "high"
    assert high.risk_weight == pytest.approx(1.5)


def test_direction_disabled_returns_neutral_fallback():
    config = OrderbookDynamicSizingConfig(directions=(1,))
    sizer = OrderbookVelocityTierSizer(config)

    decision = sizer.decision_from_feature_value(3.0, direction=-1, sample_count=2)

    assert decision.active is False
    assert decision.tier == "fallback"
    assert decision.risk_weight == pytest.approx(1.0)
    assert decision.reason == "direction_disabled"


def test_insufficient_coverage_returns_neutral_fallback():
    sizer = OrderbookVelocityTierSizer()

    decision = sizer.decision_from_feature_value(3.0, coverage=0.5, sample_count=2)

    assert decision.active is False
    assert decision.tier == "fallback"
    assert decision.risk_weight == pytest.approx(1.0)
    assert decision.reason == "insufficient_coverage"


def test_cache_midpoint_velocity_scores_long_direction():
    cache = OrderbookFeatureCache(retention_seconds=90)
    start = dt("2025-05-16 10:49:50")
    for offset, mid in ((0, 100.0), (5, 101.0), (9, 102.5), (10, 103.0)):
        cache.add_top_of_book(
            symbol="NQ.FUT",
            timestamp=start + timedelta(seconds=offset),
            bid=mid - 0.25,
            ask=mid + 0.25,
        )

    result = cache.midpoint_velocity(
        symbol="NQ.FUT",
        direction=1,
        start=start,
        end=start + timedelta(seconds=10),
        min_tick=0.25,
    )

    # The right edge is exclusive, so the 10s sample is not used.
    assert result.sample_count == 3
    assert result.coverage == pytest.approx(1.0)
    assert result.feature_value == pytest.approx(1.0)


def test_cache_midpoint_velocity_flips_for_short_direction():
    cache = OrderbookFeatureCache(retention_seconds=90)
    start = dt("2025-05-16 10:49:50")
    for offset, mid in ((0, 100.0), (5, 101.0), (9, 102.5)):
        cache.add_top_of_book(
            symbol="NQ.FUT",
            timestamp=start + timedelta(seconds=offset),
            bid=mid - 0.25,
            ask=mid + 0.25,
        )

    result = cache.midpoint_velocity(
        symbol="NQ.FUT",
        direction=-1,
        start=start,
        end=start + timedelta(seconds=10),
        min_tick=0.25,
    )

    assert result.feature_value == pytest.approx(-1.0)


def test_sizer_scores_cache_window_with_signal_end():
    config = OrderbookDynamicSizingConfig(min_coverage=0.8)
    cache = OrderbookFeatureCache(retention_seconds=90)
    sizer = OrderbookVelocityTierSizer(config)
    signal_end = dt("2025-05-16 10:50:00")
    start = signal_end - timedelta(seconds=10)
    for offset, mid in ((0, 100.0), (4, 101.0), (9, 102.5), (10, 103.0)):
        cache.add_top_of_book(
            symbol="NQ.FUT",
            timestamp=start + timedelta(seconds=offset),
            bid=mid - 0.25,
            ask=mid + 0.25,
        )

    decision = sizer.decision_from_cache(
        DynamicSizingContext(symbol="NQ.FUT", direction=1, signal_end=signal_end),
        cache,
    )

    assert decision.active is True
    assert decision.feature_value == pytest.approx(1.0)
    assert decision.tier == "high"
    assert decision.risk_weight == pytest.approx(1.5)


def test_cache_status_reports_latest_top_of_book_sample():
    cache = OrderbookFeatureCache(retention_seconds=90)
    ts = dt("2025-01-15 09:55:00")
    cache.add_top_of_book(
        symbol="NQ.FUT",
        timestamp=ts,
        bid=19500.25,
        ask=19500.50,
        instrument_id=123,
        raw_symbol="NQH5",
    )

    status = cache.status()

    assert status["total_samples"] == 1
    assert status["last_sample_time"] == ts.isoformat()
    assert status["symbols"]["NQ.FUT"]["sample_count"] == 1
    assert status["symbols"]["NQ.FUT"]["last_mid"] == pytest.approx(19500.375)
    assert status["symbols"]["NQ.FUT"]["raw_symbol"] == "NQH5"


def test_scored_feature_lookup_provider_replays_csv_row(tmp_path):
    path = tmp_path / "scores.csv"
    path.write_text(
        "\n".join([
            "overlay,candidate,feature,profile,signal_start,direction,feature_value,coverage,sample_count",
            (
                "pure_1m_long_confirm_last_velocity,cand,"
                "confirm_last_10s_mid_velocity_ticks_per_second,tier_0p5_1_1p5,"
                "2025-01-15T09:55:00-05:00,1,1.25,1.0,6"
            ),
        ])
    )
    provider = ScoredFeatureLookupProvider.from_csv(
        path,
        overlay="pure_1m_long_confirm_last_velocity",
        candidate="cand",
        profile="tier_0p5_1_1p5",
    )

    decision = provider(DynamicSizingContext(
        symbol="NQ.FUT",
        direction=1,
        signal_start=dt("2025-01-15 09:55:00"),
    ))

    assert decision.active is True
    assert decision.tier == "high"
    assert decision.risk_weight == pytest.approx(1.5)
    assert decision.reason == "scored_feature_csv"


def test_scored_feature_lookup_provider_missing_row_falls_back(tmp_path):
    path = tmp_path / "scores.csv"
    path.write_text(
        "overlay,candidate,feature,profile,signal_start,direction,feature_value\n"
        "x,cand,confirm_last_10s_mid_velocity_ticks_per_second,p,2025-01-15T09:55:00-05:00,1,1.25\n"
    )
    provider = ScoredFeatureLookupProvider.from_csv(path, overlay="different")

    decision = provider(DynamicSizingContext(
        symbol="NQ.FUT",
        direction=1,
        signal_start=dt("2025-01-15 09:55:00"),
    ))

    assert decision.active is False
    assert decision.risk_weight == pytest.approx(1.0)
    assert decision.reason == "scored_feature_missing"


def test_scored_feature_lookup_provider_replays_mbp10_validation_csv(tmp_path):
    path = tmp_path / "mbp10_replay.csv"
    path.write_text(
        "\n".join([
            "trade_uid,date,signal_start,direction,actual_feature_value,coverage,sample_count,reason",
            (
                "cand|2025-01-15|2025-01-15T09:55:00|1|19500.00|2,"
                "2025-01-15,2025-01-15T09:55:00-05:00,1,1.25,0.99,42,ok"
            ),
        ])
    )
    provider = ScoredFeatureLookupProvider.from_csv(path, candidate="cand")

    decision = provider(DynamicSizingContext(
        symbol="NQ.FUT",
        direction=1,
        signal_start=dt("2025-01-15 09:55:00"),
    ))

    assert decision.active is True
    assert decision.feature_value == pytest.approx(1.25)
    assert decision.tier == "high"
    assert decision.risk_weight == pytest.approx(1.5)
    assert decision.coverage == pytest.approx(0.99)
    assert decision.sample_count == 42
    assert decision.reason == "ok"
