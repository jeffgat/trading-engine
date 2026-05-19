from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trader.feed import BarAggregator
from trader.htf_levels import HtfLevelTracker


ET = ZoneInfo("America/New_York")


def _dt(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=ET)


def _feed_1m_as_live_5m(
    tracker: HtfLevelTracker,
    *,
    start: str,
    high: list[float],
    low: list[float],
) -> None:
    aggregator = BarAggregator()
    start_dt = _dt(start)
    for i, (h, l) in enumerate(zip(high, low, strict=True)):
        ts = start_dt + timedelta(minutes=i)
        bar_5m = aggregator.add_1m_bar(ts, l, h, l, h, 1)
        if bar_5m is not None:
            tracker.on_bar(bar_5m)


def test_live_htf_tracker_matches_raw_1m_publication_boundary_with_equal_touch() -> None:
    tracker = HtfLevelTracker(tf_minutes=60, n_left=1, base_bar_minutes=5)
    high = [8.0] * 125
    low = [7.0] * 125
    high[:60] = [11.0] * 60
    low[:60] = [6.0] * 60
    high[75] = 11.0
    low[75] = 6.0

    _feed_1m_as_live_5m(tracker, start="2025-01-03 09:00", high=high, low=low)

    assert tracker.latest_high is not None
    assert tracker.latest_low is not None
    assert tracker.latest_high.price == pytest.approx(11.0)
    assert tracker.latest_low.price == pytest.approx(6.0)
    assert tracker.latest_high.level_time == _dt("2025-01-03 09:00").isoformat()
    assert tracker.latest_high.publish_time == _dt("2025-01-03 11:00").isoformat()


def test_live_htf_tracker_uses_strict_raw_1m_sweeps_before_publication() -> None:
    tracker = HtfLevelTracker(tf_minutes=60, n_left=1, base_bar_minutes=5)
    high = [8.0] * 125
    low = [7.0] * 125
    high[:60] = [11.0] * 60
    low[:60] = [6.0] * 60
    high[75] = 11.25
    low[76] = 5.75

    _feed_1m_as_live_5m(tracker, start="2025-01-03 09:00", high=high, low=low)

    assert tracker.latest_high is None
    assert tracker.latest_low is None
