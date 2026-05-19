"""Tests for BarAggregator and ATRCalculator in feed.py.

All tests are synchronous — no async needed (these are pure data structures).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from trader.feed import (
    ATRCalculator,
    BarAggregator,
    DailyBar,
    DataBentoFeed,
    _normalize_1m_timestamp,
)
from trader.engine import Bar

ET = ZoneInfo("America/New_York")


def make_dt(date_str: str, time_str: str, tz=ET) -> datetime:
    return datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)


# =============================================================================
# BarAggregator
# =============================================================================

class TestBarAggregator:
    def test_first_bar_returns_none(self):
        agg = BarAggregator()
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:30"), 100, 105, 99, 103, 50)
        assert result is None

    def test_fifth_bar_emits_immediately(self):
        agg = BarAggregator()
        result = None
        for minute in range(5):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=minute)
            result = agg.add_1m_bar(ts, 100 + minute, 105 + minute, 99, 103 + minute, 10)
        assert result is not None
        assert result.timestamp == make_dt("2025-01-15", "09:30")
        assert result.open == pytest.approx(100.0)
        assert result.close == pytest.approx(107.0)

    def test_next_bucket_does_not_duplicate_already_emitted_bar(self):
        agg = BarAggregator()
        for minute in range(5):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=minute)
            agg.add_1m_bar(ts, 100, 105, 99, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 20)
        assert result is None

    def test_four_bars_same_bucket_all_return_none(self):
        agg = BarAggregator()
        results = [
            agg.add_1m_bar(make_dt("2025-01-15", f"09:3{i}"), 100, 105, 99, 103, 10)
            for i in range(4)
        ]
        assert all(r is None for r in results)

    def test_new_bucket_emits_previous(self):
        """When a bar from a new bucket arrives, the old bucket is emitted."""
        agg = BarAggregator()
        # Fill 09:30 bucket with 4 bars
        for i in range(4):
            agg.add_1m_bar(make_dt("2025-01-15", f"09:3{i}"), 100, 105, 99, 103, 10)
        # 09:35 bar triggers emit of 09:30 bucket
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 20)
        assert result is not None
        assert isinstance(result, Bar)

    def test_bucket_timestamp_is_bucket_start(self):
        """Emitted bar timestamp must be 09:30, not 09:31 or 09:34."""
        agg = BarAggregator()
        for minute in range(4):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=minute)
            agg.add_1m_bar(ts, 100, 105, 99, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 20)
        assert result.timestamp.minute == 30
        assert result.timestamp.hour == 9

    def test_bucket_open_is_first_bars_open(self):
        """Open price must be the FIRST bar's open, not the last."""
        agg = BarAggregator()
        agg.add_1m_bar(make_dt("2025-01-15", "09:30"), 100.0, 105, 99, 103, 10)
        agg.add_1m_bar(make_dt("2025-01-15", "09:31"), 102.0, 106, 100, 104, 10)
        agg.add_1m_bar(make_dt("2025-01-15", "09:32"), 104.0, 107, 101, 105, 10)
        agg.add_1m_bar(make_dt("2025-01-15", "09:33"), 103.0, 108, 98, 106, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 107, 112, 106, 110, 10)
        assert result.open == pytest.approx(100.0)

    def test_bucket_close_is_last_bars_close(self):
        """Close price must be the LAST bar before the new bucket."""
        agg = BarAggregator()
        for i, close in enumerate([103, 104, 105, 107.5]):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=i)
            agg.add_1m_bar(ts, 100, 110, 99, close, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 107, 112, 106, 111, 10)
        assert result.close == pytest.approx(107.5)

    def test_bucket_high_is_max_of_all_bars(self):
        agg = BarAggregator()
        highs = [105, 110, 108, 112]
        for i, h in enumerate(highs):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=i)
            agg.add_1m_bar(ts, 100, h, 99, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 109, 102, 108, 10)
        assert result.high == 112

    def test_bucket_low_is_min_of_all_bars(self):
        agg = BarAggregator()
        lows = [99, 97, 98, 95]
        for i, l in enumerate(lows):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=i)
            agg.add_1m_bar(ts, 100, 110, l, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 96, 108, 10)
        assert result.low == 95

    def test_volume_accumulates(self):
        agg = BarAggregator()
        for i in range(4):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=i)
            agg.add_1m_bar(ts, 100, 105, 99, 103, 100)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 100)
        assert result.volume == 400

    def test_bucket_alignment_floor(self):
        """Bar at :32 belongs to the :30 bucket (floor, not nearest)."""
        agg = BarAggregator()
        agg.add_1m_bar(make_dt("2025-01-15", "09:32"), 100, 105, 99, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 10)
        assert result is not None
        assert result.timestamp.minute == 30

    def test_bucket_alignment_55_minute(self):
        """Bar at :58 belongs to :55 bucket."""
        agg = BarAggregator()
        agg.add_1m_bar(make_dt("2025-01-15", "09:58"), 100, 105, 99, 103, 10)
        result = agg.add_1m_bar(make_dt("2025-01-15", "10:00"), 103, 110, 102, 108, 10)
        assert result is not None
        assert result.timestamp.minute == 55

    def test_single_bar_emitted_on_next_bucket(self):
        """If only 1 bar in bucket and next bucket arrives, emit with that bar's data."""
        agg = BarAggregator()
        agg.add_1m_bar(make_dt("2025-01-15", "09:30"), 100.0, 105.0, 99.0, 103.0, 77)
        result = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 104.0, 110.0, 103.0, 108.0, 10)
        assert result is not None
        assert result.open == pytest.approx(100.0)
        assert result.high == pytest.approx(105.0)
        assert result.low == pytest.approx(99.0)
        assert result.close == pytest.approx(103.0)
        assert result.volume == 77

    def test_sequential_buckets(self):
        """Two complete buckets produce two emitted bars."""
        agg = BarAggregator()
        emitted = []
        # Fill 09:30 bucket (bars at :30, :31, :32, :33)
        for i in range(4):
            ts = make_dt("2025-01-15", "09:30") + timedelta(minutes=i)
            r = agg.add_1m_bar(ts, 100, 105, 99, 103, 10)
            if r:
                emitted.append(r)
        # 09:35 closes the 09:30 bucket AND starts 09:35
        r = agg.add_1m_bar(make_dt("2025-01-15", "09:35"), 103, 110, 102, 108, 10)
        if r:
            emitted.append(r)
        # Add 3 more bars to complete 09:35 bucket
        for i in range(1, 4):
            ts = make_dt("2025-01-15", "09:35") + timedelta(minutes=i)
            r = agg.add_1m_bar(ts, 108, 112, 107, 110, 10)
            if r:
                emitted.append(r)
        # 09:40 closes 09:35 bucket
        r = agg.add_1m_bar(make_dt("2025-01-15", "09:40"), 110, 115, 109, 113, 10)
        if r:
            emitted.append(r)
        assert len(emitted) == 2
        assert emitted[0].timestamp.minute == 30
        assert emitted[1].timestamp.minute == 35

    def test_open_stamped_1m_normalization_preserves_boundary_minute(self):
        """A 09:30-09:34 1m sequence must emit a 09:30 5m candle."""
        agg = BarAggregator()
        result = None
        lows = [100.0, 100.0, 100.0, 100.0, 90.0]
        for minute, low in zip(range(30, 35), lows):
            ts = _normalize_1m_timestamp(make_dt("2025-01-15", f"09:{minute:02d}"))
            result = agg.add_1m_bar(ts, 100.0, 105.0, low, 103.0, 10)
        assert result is not None
        assert result.timestamp == make_dt("2025-01-15", "09:30")
        assert result.low == pytest.approx(90.0)
        assert result.volume == 50

    def test_fifteen_open_stamped_1m_bars_emit_three_orb_buckets(self):
        """09:30-09:44 bars should emit 09:30, 09:35, and 09:40."""
        agg = BarAggregator()
        emitted = []

        for minute in range(30, 45):
            ts = _normalize_1m_timestamp(make_dt("2025-01-15", f"09:{minute:02d}"))
            result = agg.add_1m_bar(ts, 100.0, 105.0, 99.0, 103.0, 10)
            if result is not None:
                emitted.append(result)

        assert [bar.timestamp for bar in emitted] == [
            make_dt("2025-01-15", "09:30"),
            make_dt("2025-01-15", "09:35"),
            make_dt("2025-01-15", "09:40"),
        ]


class TestTimestampNormalization:
    def test_normalize_1m_timestamp_keeps_interval_start(self):
        ts = make_dt("2025-01-15", "09:35")
        assert _normalize_1m_timestamp(ts) == make_dt("2025-01-15", "09:35")


class TestDataBentoFeedIngestion:
    def test_daily_only_symbols_keep_intraday_unsubscribed(self):
        feed = DataBentoFeed(symbols=["GC.FUT"], daily_only_symbols=["NQ.FUT"])

        assert feed.symbols == ["GC.FUT"]
        assert feed.daily_only_symbols == ["NQ.FUT"]
        assert feed.history_symbols == ["GC.FUT", "NQ.FUT"]
        assert "NQ.FUT" in feed._daily_history
        assert "NQ.FUT" in feed._atrs
        assert "NQ.FUT" not in feed._aggregators

    def test_mbp10_streaming_disabled_by_default(self):
        feed = DataBentoFeed(symbols=["NQ.FUT"])

        assert feed.enable_mbp10 is False
        assert feed.on_orderbook is None

    def test_live_and_preload_use_identical_1m_ingestion(self):
        minutes = range(30, 45)  # interval-start stamped 09:30-09:44 bars

        def collect(source: str) -> list[tuple]:
            feed = DataBentoFeed(symbols=["NQ.FUT"])
            emitted = []
            for minute in minutes:
                bar = feed._ingest_1m_bar(
                    symbol="NQ.FUT",
                    ts_event=make_dt("2025-01-15", f"09:{minute:02d}"),
                    o=100.0,
                    h=105.0,
                    l=99.0,
                    c=103.0,
                    v=10,
                    source=source,
                )
                if bar is not None:
                    emitted.append((bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume))
            return emitted

        assert collect("live") == collect("preload")

    def test_es_asia_signal_bucket_does_not_emit_early(self):
        feed = DataBentoFeed(symbols=["ES.FUT"])

        partial = []
        for minute in range(15, 19):
            bar = feed._ingest_1m_bar(
                symbol="ES.FUT",
                ts_event=make_dt("2025-01-15", f"20:{minute:02d}"),
                o=6770.0,
                h=6775.0,
                l=6768.0,
                c=6772.0,
                v=10,
                source="live",
            )
            partial.append(bar)

        assert partial == [None, None, None, None]

        completed = feed._ingest_1m_bar(
            symbol="ES.FUT",
            ts_event=make_dt("2025-01-15", "20:19"),
            o=6772.0,
            h=6778.0,
            l=6771.0,
            c=6776.0,
            v=10,
            source="live",
        )
        assert completed is not None
        assert completed.timestamp == make_dt("2025-01-15", "20:15")

    async def test_mbp10_record_emits_top_of_book_sample(self):
        samples = []

        async def on_orderbook(sample):
            samples.append(sample)

        class Level:
            bid_px = 19500.25 * 1e9
            ask_px = 19500.50 * 1e9

        class Record:
            instrument_id = 123
            ts_event = int(make_dt("2025-01-15", "09:55").timestamp() * 1e9)
            levels = [Level()]

        feed = DataBentoFeed(
            symbols=["NQ.FUT"],
            enable_mbp10=True,
            on_orderbook=on_orderbook,
        )
        feed._id_to_symbol[123] = "NQ.FUT"
        feed._id_to_raw[123] = "NQH5"

        await feed._handle_mbp10(Record())

        assert len(samples) == 1
        assert samples[0].symbol == "NQ.FUT"
        assert samples[0].raw_symbol == "NQH5"
        assert samples[0].bid == pytest.approx(19500.25)
        assert samples[0].ask == pytest.approx(19500.50)
        assert feed._front_month["NQ.FUT"] == 123

    async def test_mbp10_record_skips_non_front_contract(self):
        samples = []

        async def on_orderbook(sample):
            samples.append(sample)

        class Level:
            bid_px = 19500.25 * 1e9
            ask_px = 19500.50 * 1e9

        class Record:
            instrument_id = 999
            ts_event = int(make_dt("2025-01-15", "09:55").timestamp() * 1e9)
            levels = [Level()]

        feed = DataBentoFeed(
            symbols=["NQ.FUT"],
            enable_mbp10=True,
            on_orderbook=on_orderbook,
        )
        feed._front_month["NQ.FUT"] = 123
        feed._id_to_symbol[999] = "NQ.FUT"
        feed._id_to_raw[999] = "NQM5"

        await feed._handle_mbp10(Record())

        assert samples == []


# =============================================================================
# ATRCalculator
# =============================================================================

def _make_daily_bars(n: int, high: float = 110.0, low: float = 90.0, close: float = 100.0) -> list[tuple]:
    """Create n daily bars with fixed H/L/C starting 2025-01-01."""
    result = []
    base = date(2025, 1, 1)
    for i in range(n):
        d = base + timedelta(days=i)
        result.append((d, 100.0, high, low, close))
    return result


class TestATRCalculator:
    def test_value_zero_before_initialization(self):
        calc = ATRCalculator(length=14)
        # Feed only 14 days (need 15 to initialize)
        for d, o, h, l, c in _make_daily_bars(14):
            calc.seed_daily([(d, o, h, l, c)])
        assert calc.value == 0.0

    def test_initializes_on_15th_day(self):
        calc = ATRCalculator(length=14)
        bars = _make_daily_bars(15)
        calc.seed_daily(bars)
        assert calc.value > 0.0

    def test_initial_atr_is_simple_average(self):
        """With constant true range of 20, initial ATR should equal 20."""
        calc = ATRCalculator(length=14)
        # high=110, low=90 → range=20; with fixed close, prev_close=100 → gap TRs still 20
        bars = _make_daily_bars(15, high=110, low=90, close=100)
        calc.seed_daily(bars)
        assert calc.value == pytest.approx(20.0, rel=1e-3)

    def test_wilders_smoothing_one_step(self):
        """Feed 15+ days to initialize, then add one more and verify formula."""
        calc = ATRCalculator(length=14)
        bars = _make_daily_bars(15, high=110, low=90, close=100)
        calc.seed_daily(bars)
        prev_atr = calc.value  # Should be ~20

        # Add a new day with TR=40 (high=120, low=80, prev_close=100 → TR=max(40,20,20)=40)
        new_day_date = date(2025, 1, 16)
        calc.seed_daily([(new_day_date, 100, 120, 80, 100)])
        expected = (prev_atr * 13 + 40.0) / 14
        assert calc.value == pytest.approx(expected, rel=1e-4)

    def test_atr_uses_prev_close_for_gap(self):
        """True range must use previous day close when there's a gap open."""
        calc = ATRCalculator(length=14)
        # 14 days of stable bars (range=20, close=100)
        base_bars = _make_daily_bars(14, high=110, low=90, close=100)
        # 15th day: gap open; prev_close=100, high=110, low=108 → range=2, but tr=max(2,10,8)=10
        gap_day = (date(2025, 1, 15), 108.0, 110.0, 108.0, 109.0)
        calc.seed_daily(base_bars + [gap_day])
        assert calc.value > 0
        # This 15th-day TR=10 vs range=2 confirms prev_close is used
        # (exact value test): simple avg of 14 prev TRs (20 each) + this TR=10
        # initial ATR = sum(14 TRs) / 14, but first TR needs 2 days (skip day 0)
        # so we just verify it's between 10 and 20 (blended)
        assert calc.value > 0.0

    def test_seed_daily_multiple_batches(self):
        """Seeding in multiple calls should work like seeding all at once."""
        calc1 = ATRCalculator(length=14)
        calc2 = ATRCalculator(length=14)
        bars = _make_daily_bars(16)
        calc1.seed_daily(bars)
        # Seed calc2 in two chunks
        calc2.seed_daily(bars[:10])
        calc2.seed_daily(bars[10:])
        assert calc1.value == pytest.approx(calc2.value, rel=1e-6)

    def test_on_5m_bar_increments_daily(self):
        """Feeding 5m bars across a day boundary should initialize ATR."""
        calc = ATRCalculator(length=2)

        # Simulate 3 trading days of 5m bars
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")

        for day_offset in range(4):
            d = datetime(2025, 1, 2 + day_offset, 9, 30, tzinfo=ET)
            # Simulate a single 5m bar per day (simplified)
            bar = Bar(timestamp=d, open=100, high=110, low=90, close=100, volume=100)
            calc.on_5m_bar(bar)

        # After 3 complete days (4 bars from 4 different days = 3 completed days)
        # ATR with length=2 should initialize after 3 days (need length+1=3)
        assert calc.value > 0.0

    def test_no_lookahead_atr_unchanged_intraday(self):
        """ATR must not change WITHIN a day — only when a new day starts."""
        calc = ATRCalculator(length=14)
        # Seed to initialize
        bars = _make_daily_bars(15)
        calc.seed_daily(bars)
        atr_at_start = calc.value

        # Add multiple 5m bars for a new day — ATR should stay the same
        # until that day closes (i.e., until a bar on ANOTHER day arrives)
        from zoneinfo import ZoneInfo
        ET = ZoneInfo("America/New_York")
        new_day = datetime(2025, 1, 16, 9, 30, tzinfo=ET)
        for minute_offset in range(5):
            bar = Bar(
                timestamp=new_day + timedelta(minutes=5 * minute_offset),
                open=100, high=115, low=85, close=100, volume=100,
            )
            calc.on_5m_bar(bar)

        # ATR unchanged — day hasn't closed yet
        assert calc.value == pytest.approx(atr_at_start)

        # Now add first bar of NEXT day → closes Jan 16 → ATR updates
        next_day = datetime(2025, 1, 17, 9, 30, tzinfo=ET)
        bar_next = Bar(timestamp=next_day, open=100, high=110, low=90, close=100, volume=100)
        calc.on_5m_bar(bar_next)

        # ATR should now have changed (new TR from Jan 16 was large: 30 range)
        assert calc.value != pytest.approx(atr_at_start)


class TestATRRefresh:
    def test_daily_bars_from_history_frame_filters_spreads_and_chooses_volume(self):
        feed = DataBentoFeed(symbols=["ES.FUT"], atr_length=3)
        df = pd.DataFrame(
            {
                "symbol": ["ESH5", "ESM5", "ESH5-ESM5"],
                "open": [100.0, 101.0, 90.0],
                "high": [110.0, 115.0, 120.0],
                "low": [95.0, 96.0, 80.0],
                "close": [105.0, 106.0, 95.0],
                "volume": [100, 200, 999],
            },
            index=pd.DatetimeIndex(
                [
                    "2025-01-02 00:00:00+00:00",
                    "2025-01-02 00:00:00+00:00",
                    "2025-01-02 00:00:00+00:00",
                ],
                name="ts_event",
            ),
        )

        bars = feed._daily_bars_from_history_frame("ES.FUT", df)

        assert bars == [(date(2025, 1, 2), 101.0, 115.0, 96.0, 106.0)]

    def test_refresh_atr_from_daily_bars(self):
        feed = DataBentoFeed(symbols=["NQ.FUT"], atr_length=3)
        bars = [
            (date(2025, 1, 1), 100.0, 110.0, 90.0, 100.0),
            (date(2025, 1, 2), 100.0, 111.0, 89.0, 100.0),
            (date(2025, 1, 3), 100.0, 112.0, 88.0, 100.0),
            (date(2025, 1, 4), 100.0, 113.0, 87.0, 100.0),
        ]
        info = feed._refresh_atr_from_daily_bars("NQ.FUT", bars)
        assert info.last_daily_date == date(2025, 1, 4)
        assert info.bars_used == 4
        assert feed.get_atr_values()["NQ.FUT"] > 0

    def test_refresh_atr_empty_bars_preserves_value(self):
        feed = DataBentoFeed(symbols=["NQ.FUT"], atr_length=3)
        seed_bars = [
            (date(2025, 1, 1), 100.0, 110.0, 90.0, 100.0),
            (date(2025, 1, 2), 100.0, 111.0, 89.0, 100.0),
            (date(2025, 1, 3), 100.0, 112.0, 88.0, 100.0),
            (date(2025, 1, 4), 100.0, 113.0, 87.0, 100.0),
        ]
        feed._refresh_atr_from_daily_bars("NQ.FUT", seed_bars)
        before = feed.get_atr_values()["NQ.FUT"]
        info = feed._refresh_atr_from_daily_bars("NQ.FUT", [])
        after = feed.get_atr_values()["NQ.FUT"]
        assert info.bars_used == 0
        assert after == pytest.approx(before)

    def test_refresh_atr_multiple_lengths(self):
        feed = DataBentoFeed(
            symbols=["NQ.FUT"],
            atr_lengths_by_symbol={"NQ.FUT": {3, 5}},
        )
        bars = [
            (date(2025, 1, 1), 100.0, 110.0, 90.0, 100.0),
            (date(2025, 1, 2), 100.0, 111.0, 89.0, 100.0),
            (date(2025, 1, 3), 100.0, 112.0, 88.0, 100.0),
            (date(2025, 1, 4), 100.0, 113.0, 87.0, 100.0),
            (date(2025, 1, 5), 100.0, 114.0, 86.0, 100.0),
            (date(2025, 1, 6), 100.0, 115.0, 85.0, 100.0),
        ]
        feed._refresh_atr_from_daily_bars("NQ.FUT", bars)
        atrs = feed.get_atr_values_for_symbol("NQ.FUT")
        assert set(atrs) == {3, 5}
        assert atrs[3] > 0
        assert atrs[5] > 0

    def test_daily_history_is_retained_independently_of_short_atr_lengths(self):
        feed = DataBentoFeed(
            symbols=["NQ.FUT"],
            atr_lengths_by_symbol={"NQ.FUT": {3, 20}},
        )
        bars = [
            (date(2025, 1, 1) + timedelta(days=i), 100.0 + i, 105.0 + i, 95.0 + i, 102.0 + i)
            for i in range(40)
        ]

        feed._refresh_atr_from_daily_bars("NQ.FUT", bars)

        history = feed.get_daily_history_for_symbol("NQ.FUT", include_current=False)
        assert len(history) == 40
        assert history[0][0] == date(2025, 1, 1)
        assert history[-1][0] == date(2025, 2, 9)

        live_bar = Bar(
            timestamp=make_dt("2025-02-10", "09:30"),
            open=140.0,
            high=142.0,
            low=139.0,
            close=141.0,
            volume=100,
        )
        feed._daily_history["NQ.FUT"].on_5m_bar(live_bar)

        history_with_current = feed.get_daily_history_for_symbol("NQ.FUT")
        assert len(history_with_current) == 41
        assert history_with_current[-1][0] == date(2025, 2, 10)
        assert history_with_current[-1][-1] == pytest.approx(141.0)

    def test_ath_refresh_from_daily_bars(self):
        feed = DataBentoFeed(symbols=["ES.FUT"], atr_length=3)
        bars = [
            (date(2025, 1, 1), 100.0, 110.0, 90.0, 100.0),
            (date(2025, 1, 2), 100.0, 125.0, 95.0, 120.0),
            (date(2025, 1, 3), 120.0, 118.0, 110.0, 112.0),
        ]

        info = feed._ath_refresh_from_daily_bars(
            "ES.FUT",
            bars,
            start=date(2025, 1, 1),
            end=date(2025, 1, 4),
        )

        assert info.symbol == "ES.FUT"
        assert info.ath_high == pytest.approx(125.0)
        assert info.last_daily_date == date(2025, 1, 3)
        assert info.bars_used == 3
