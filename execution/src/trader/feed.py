"""DataBento live feed with 1m → 5m bar aggregation, 1s tick forwarding, and daily ATR.

Connects to DataBento's GLBX.MDP3 dataset, subscribes to both 1-minute and
1-second OHLCV bars on a single connection.  1m bars are aggregated into
5-minute bars for signal detection (ORB, FVG); 1s bars are forwarded directly
to the session engines for fill detection and exit management (TP1/SL/BE/TP2).
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, date
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from .engine import Bar

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

# TEMPORARY: keep these narrow diagnostics until live validation confirms the
# minute-stamp model matches the observed NQ_NY / ES_Asia timing behavior.
TEMPORARY_1M_DIAGNOSTIC_WINDOWS: dict[str, tuple[tuple[time, time, str], ...]] = {
    "NQ.FUT": ((time(9, 25), time(9, 50), "NQ_NY"),),
    "ES.FUT": ((time(20, 5), time(20, 25), "ES_Asia"),),
}


def _normalize_1m_timestamp(ts: datetime) -> datetime:
    """Normalize a 1m bar to TradingView-style minute labels.

    TradingView labels 1m/5m bars by interval start. DataBento's completed
    1m bars are treated here as already representing that minute, so we keep
    the minute label and only strip sub-minute fields. This makes ORB/session
    windows line up with the prices shown on TradingView across all sessions.
    """
    return ts.replace(second=0, microsecond=0)


def _diagnostic_session(symbol: str, ts: datetime) -> str | None:
    """Return the temporary diagnostic session tag for a timestamp, if any."""
    windows = TEMPORARY_1M_DIAGNOSTIC_WINDOWS.get(symbol, ())
    current = ts.timetz().replace(tzinfo=None)
    for start, end, session in windows:
        if start <= current < end:
            return session
    return None


# ---------------------------------------------------------------------------
# Daily bar for ATR computation
# ---------------------------------------------------------------------------

@dataclass
class DailyBar:
    """One day's OHLC, accumulated from 5m bars."""

    date: date
    open: float = float("nan")
    high: float = float("-inf")
    low: float = float("inf")
    close: float = float("nan")

    def update(self, bar: Bar) -> None:
        if math.isnan(self.open):
            self.open = bar.open
        if bar.high > self.high:
            self.high = bar.high
        if bar.low < self.low:
            self.low = bar.low
        self.close = bar.close


class DailyHistoryTracker:
    """Tracks completed daily bars plus the current partial day."""

    def __init__(self, max_days: int = 90) -> None:
        self.max_days = max_days
        self._completed_days: deque[DailyBar] = deque(maxlen=max_days)
        self._current_day: DailyBar | None = None

    def seed_daily(self, daily_bars: list[tuple[date, float, float, float, float]]) -> None:
        self._completed_days = deque(
            (DailyBar(date=d, open=o, high=h, low=l, close=c) for d, o, h, l, c in daily_bars),
            maxlen=self.max_days,
        )
        self._current_day = None

    def on_5m_bar(self, bar: Bar) -> None:
        bar_date = bar.timestamp.date()
        if self._current_day is None or bar_date != self._current_day.date:
            if self._current_day is not None:
                self._completed_days.append(self._current_day)
            self._current_day = DailyBar(date=bar_date)
        self._current_day.update(bar)

    def snapshot(self, include_current: bool = True) -> list[tuple[date, float, float, float, float]]:
        bars = [
            (bar.date, bar.open, bar.high, bar.low, bar.close)
            for bar in self._completed_days
        ]
        if include_current and self._current_day is not None and not math.isnan(self._current_day.close):
            bars.append(
                (
                    self._current_day.date,
                    self._current_day.open,
                    self._current_day.high,
                    self._current_day.low,
                    self._current_day.close,
                )
            )
        return bars


# ---------------------------------------------------------------------------
# ATR calculator (Wilder's smoothing, matches core/signals/daily_atr.py)
# ---------------------------------------------------------------------------

class ATRCalculator:
    """Incremental daily ATR using Wilder's smoothing.

    Produces the same result as core/signals/daily_atr.py but operates
    on one day at a time instead of a full array.
    """

    def __init__(self, length: int = 14) -> None:
        self.length = length
        self._daily_bars: deque[DailyBar] = deque(maxlen=length + 1)
        self._current_day: DailyBar | None = None
        self._atr: float = 0.0
        self._prev_close: float = float("nan")
        self._initialized: bool = False

    @property
    def value(self) -> float:
        """Current ATR value (lagged by 1 day — no lookahead)."""
        return self._atr

    def seed_daily(self, daily_bars: list[tuple[date, float, float, float, float]]) -> None:
        """Seed with historical daily OHLC to bootstrap ATR on cold start.

        Args:
            daily_bars: List of (date, open, high, low, close) sorted chronologically.
        """
        for d, o, h, l, c in daily_bars:
            day = DailyBar(date=d, open=o, high=h, low=l, close=c)
            self._close_day(day)
        if self._initialized:
            logger.info("ATR seeded: %.2f from %d daily bars", self._atr, len(daily_bars))
        else:
            logger.warning(
                "ATR not yet initialized after seeding %d bars (need %d+1)",
                len(daily_bars), self.length,
            )

    def on_5m_bar(self, bar: Bar) -> None:
        """Feed a 5m bar to update daily OHLC and ATR."""
        bar_date = bar.timestamp.date()

        # New trading day?
        if self._current_day is None or bar_date != self._current_day.date:
            # Close previous day and recompute ATR
            if self._current_day is not None:
                self._close_day(self._current_day)
            self._current_day = DailyBar(date=bar_date)

        self._current_day.update(bar)

    def _close_day(self, day: DailyBar) -> None:
        """Finalize a daily bar and update ATR."""
        self._daily_bars.append(day)

        if len(self._daily_bars) < 2:
            self._prev_close = day.close
            return

        prev = self._daily_bars[-2]
        prev_close = prev.close

        # True range
        tr = max(
            day.high - day.low,
            abs(day.high - prev_close),
            abs(day.low - prev_close),
        )

        if not self._initialized and len(self._daily_bars) >= self.length + 1:
            # Initial ATR: simple average of first `length` true ranges
            trs = []
            for i in range(1, len(self._daily_bars)):
                d = self._daily_bars[i]
                pc = self._daily_bars[i - 1].close
                trs.append(max(d.high - d.low, abs(d.high - pc), abs(d.low - pc)))
            self._atr = sum(trs[-self.length :]) / self.length
            self._initialized = True
        elif self._initialized:
            # Wilder's smoothing: ATR = (prev_ATR * (n-1) + TR) / n
            self._atr = (self._atr * (self.length - 1) + tr) / self.length

        self._prev_close = day.close


# ---------------------------------------------------------------------------
# ATR refresh metadata
# ---------------------------------------------------------------------------

@dataclass
class ATRRefreshInfo:
    symbol: str
    last_daily_date: date | None
    atr_value: float
    refreshed_at: str
    bars_used: int


# ---------------------------------------------------------------------------
# 1m → 5m bar aggregator
# ---------------------------------------------------------------------------

class BarAggregator:
    """Aggregates 1-minute bars into clock-aligned 5-minute bars.

    A 5m bar at 09:30 covers 09:30, 09:31, 09:32, 09:33, 09:34.
    The bar is emitted when the 5th 1m bar completes (or a new 5m bucket starts).
    """

    def __init__(self) -> None:
        self._bucket_start: datetime | None = None
        self._open: float = 0.0
        self._high: float = float("-inf")
        self._low: float = float("inf")
        self._close: float = 0.0
        self._volume: int = 0
        self._count: int = 0

    @staticmethod
    def _bucket_for(ts: datetime) -> datetime:
        """Get the 5m bucket start time for a given timestamp."""
        return ts.replace(minute=(ts.minute // 5) * 5, second=0, microsecond=0)

    def add_1m_bar(
        self,
        ts: datetime,
        o: float,
        h: float,
        l: float,
        c: float,
        v: int,
    ) -> Bar | None:
        """Add a 1m bar. Returns a completed 5m Bar if one just closed, else None."""
        bucket = self._bucket_for(ts)
        result: Bar | None = None

        # If this bar belongs to a new bucket, close any still-open partial bucket.
        if self._bucket_start is not None and bucket != self._bucket_start:
            result = Bar(
                timestamp=self._bucket_start,
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._close,
                volume=self._volume,
            )
            self._reset()

        # Accumulate into current bucket
        if self._bucket_start is None:
            self._bucket_start = bucket
            self._open = o
            self._high = h
            self._low = l
        else:
            if h > self._high:
                self._high = h
            if l < self._low:
                self._low = l

        self._close = c
        self._volume += v
        self._count += 1

        # In the normal live path, emit immediately when the 5th constituent
        # 1m bar completes so the engine reacts on the 5m close, not 1 minute later.
        if self._count >= 5:
            result = Bar(
                timestamp=self._bucket_start,
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._close,
                volume=self._volume,
            )
            self._reset()

        return result

    def _reset(self) -> None:
        self._bucket_start = None
        self._open = 0.0
        self._high = float("-inf")
        self._low = float("inf")
        self._close = 0.0
        self._volume = 0
        self._count = 0


# ---------------------------------------------------------------------------
# Callback type
# ---------------------------------------------------------------------------
ATRValuesByLength = dict[int, float]

OnBarCallback = Callable[[Bar, ATRValuesByLength], Awaitable[None]]
# Signature: async def on_bar(bar: Bar, daily_atrs: dict[int, float]) -> None

# Multi-symbol callback includes the symbol name
OnSymbolBarCallback = Callable[[str, Bar, ATRValuesByLength], Awaitable[None]]
# Signature: async def on_bar(symbol: str, bar: Bar, daily_atrs: dict[int, float]) -> None

# 1-second tick callback (same signature — each 1s bar forwarded as-is)
OnSymbolTickCallback = Callable[[str, Bar, ATRValuesByLength], Awaitable[None]]
# Signature: async def on_tick(symbol: str, tick: Bar, daily_atrs: dict[int, float]) -> None


# ---------------------------------------------------------------------------
# DataBento live feed (multi-symbol)
# ---------------------------------------------------------------------------

class DataBentoFeed:
    """Live feed from DataBento streaming 1m + 1s bars.

    Subscribes to both ``ohlcv-1m`` (aggregated into 5m bars for signals) and
    ``ohlcv-1s`` (forwarded directly for fill/exit management) on a single
    connection.  Supports multiple symbols (e.g., NQ.FUT + ES.FUT).

    Args:
        api_key: DataBento API key (or reads from DATABENTO_API_KEY env var).
        symbols: DataBento parent symbols (e.g., ["NQ.FUT", "ES.FUT"]).
        dataset: DataBento dataset (default: "GLBX.MDP3").
        on_bar: Async callback for each completed 5m bar (symbol, bar, atrs).
        on_tick: Async callback for each 1s bar (symbol, tick, atrs).
        atr_length: Fallback ATR period when no per-symbol mapping is given.
        atr_lengths_by_symbol: Optional ATR lengths per symbol.
        reconnect_delay: Initial reconnect delay in seconds.
        max_reconnect_delay: Maximum reconnect delay.
    """

    def __init__(
        self,
        api_key: str | None = None,
        symbols: list[str] | None = None,
        daily_only_symbols: list[str] | None = None,
        dataset: str = "GLBX.MDP3",
        on_bar: OnSymbolBarCallback | None = None,
        on_tick: OnSymbolTickCallback | None = None,
        atr_length: int = 14,
        atr_lengths_by_symbol: dict[str, list[int] | set[int] | tuple[int, ...]] | None = None,
        reconnect_delay: float = 1.0,
        max_reconnect_delay: float = 60.0,
        # Legacy single-symbol support
        symbol: str | None = None,
    ) -> None:
        self.api_key = api_key
        # Support both old single-symbol and new multi-symbol API
        if symbols:
            self.symbols = symbols
        elif symbol:
            self.symbols = [symbol]
        else:
            self.symbols = ["NQ.FUT"]
        # Extra symbols can be loaded for daily ATR/history only without
        # subscribing to their intraday streams.
        self.daily_only_symbols = [
            sym for sym in (daily_only_symbols or []) if sym and sym not in self.symbols
        ]
        self.history_symbols = self.symbols + self.daily_only_symbols
        self.dataset = dataset
        self.on_bar = on_bar
        self.on_tick = on_tick
        self.atr_length = atr_length
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        # per-symbol aggregator + ATR
        self._aggregators: dict[str, BarAggregator] = {}
        self._atr_lengths_by_symbol: dict[str, list[int]] = {}
        self._atrs: dict[str, dict[int, ATRCalculator]] = {}
        self._daily_history: dict[str, DailyHistoryTracker] = {}
        for sym in self.symbols:
            self._aggregators[sym] = BarAggregator()
        for sym in self.history_symbols:
            raw_lengths = None if atr_lengths_by_symbol is None else atr_lengths_by_symbol.get(sym)
            lengths = sorted({int(length) for length in (raw_lengths or [atr_length])})
            self._atr_lengths_by_symbol[sym] = lengths
            self._atrs[sym] = {
                length: ATRCalculator(length=length) for length in lengths
            }
            self._daily_history[sym] = DailyHistoryTracker()

        self._running = False
        # Populated after connection — maps instrument_id to parent symbol
        self._id_to_symbol: dict[int, str] = {}
        # Maps instrument_id to raw contract name (e.g. 42002475 → "NQH6")
        self._id_to_raw: dict[int, str] = {}
        # Front-month selection: cumulative volume per (parent, instrument_id)
        # and the currently elected front-month id per parent symbol
        self._id_volumes: dict[int, int] = {}  # instrument_id → cumulative volume
        self._front_month: dict[str, int] = {}  # parent symbol → instrument_id

    def _ingest_1m_bar(
        self,
        *,
        symbol: str,
        ts_event: datetime,
        o: float,
        h: float,
        l: float,
        c: float,
        v: int,
        source: str,
    ) -> Bar | None:
        """Normalize and aggregate a completed 1m bar for live or preload."""
        ts_bar_open = _normalize_1m_timestamp(ts_event)
        bucket_start = BarAggregator._bucket_for(ts_bar_open)
        diag_session = _diagnostic_session(symbol, ts_bar_open)
        if diag_session is not None:
            logger.info(
                "TEMP_1M_TRACE | source=%s session=%s symbol=%s ts_event=%s normalized=%s bucket=%s",
                source,
                diag_session,
                symbol,
                ts_event.isoformat(),
                ts_bar_open.isoformat(),
                bucket_start.isoformat(),
            )

        bar_5m = self._aggregators[symbol].add_1m_bar(ts_bar_open, o, h, l, c, v)
        if bar_5m is not None and diag_session is not None:
            logger.info(
                "TEMP_5M_EMIT | source=%s session=%s symbol=%s bucket=%s emitted=%s o=%.2f h=%.2f l=%.2f c=%.2f v=%d",
                source,
                diag_session,
                symbol,
                bucket_start.isoformat(),
                bar_5m.timestamp.isoformat(),
                bar_5m.open,
                bar_5m.high,
                bar_5m.low,
                bar_5m.close,
                bar_5m.volume,
            )
        return bar_5m

    def warm_up(self, lookback_days: int = 30) -> None:
        """Seed ATR calculators with historical daily bars from DataBento.

        Fetches `lookback_days` of daily OHLCV for each symbol and feeds
        them into the ATR calculator so it's initialized on first live bar.
        """
        self.refresh_atr_daily(lookback_days=lookback_days)

    def _refresh_atr_from_daily_bars(
        self,
        sym: str,
        bars: list[tuple[date, float, float, float, float]],
    ) -> ATRRefreshInfo:
        """Reseed ATR from daily bars and return refresh metadata."""
        primary_length = self._atr_lengths_by_symbol[sym][0]
        if not bars:
            current = self._atrs[sym][primary_length]
            return ATRRefreshInfo(
                symbol=sym,
                last_daily_date=None,
                atr_value=current.value,
                refreshed_at=datetime.now(tz=ET).isoformat(),
                bars_used=0,
            )

        refreshed_values: ATRValuesByLength = {}
        refreshed_calcs: dict[int, ATRCalculator] = {}
        for length in self._atr_lengths_by_symbol[sym]:
            calc = ATRCalculator(length=length)
            calc.seed_daily(bars)
            refreshed_calcs[length] = calc
            refreshed_values[length] = calc.value
        self._atrs[sym] = refreshed_calcs
        self._daily_history[sym].seed_daily(bars)
        last_date = bars[-1][0]
        return ATRRefreshInfo(
            symbol=sym,
            last_daily_date=last_date,
            atr_value=refreshed_values[primary_length],
            refreshed_at=datetime.now(tz=ET).isoformat(),
            bars_used=len(bars),
        )

    def refresh_atr_daily(
        self,
        lookback_days: int = 30,
        end_date: date | None = None,
    ) -> list[ATRRefreshInfo]:
        """Refresh ATR using daily bars up to the last completed day."""
        import databento as db

        end = end_date or (date.today() - timedelta(days=1))
        start = end - timedelta(days=lookback_days)
        refreshed: list[ATRRefreshInfo] = []

        for sym in self.history_symbols:
            try:
                logger.info(
                    "Refreshing ATR for %s: fetching %d days ending %s",
                    sym, lookback_days, end.isoformat(),
                )
                client = db.Historical(key=self.api_key)
                data = client.timeseries.get_range(
                    dataset=self.dataset,
                    symbols=[sym],
                    schema="ohlcv-1d",
                    stype_in="parent",
                    start=start.isoformat(),
                    end=end.isoformat(),
                )
                df = data.to_df()

                # Filter to outright contracts only (no spreads with "-")
                if "symbol" in df.columns:
                    df = df[~df["symbol"].str.contains("-", na=False)]

                if df.empty:
                    logger.warning("No daily bars returned for %s", sym)
                    refreshed.append(self._refresh_atr_from_daily_bars(sym, []))
                    continue

                df = df.reset_index()
                if "ts_event" not in df.columns:
                    logger.warning("Daily bars missing ts_event for %s", sym)
                    refreshed.append(self._refresh_atr_from_daily_bars(sym, []))
                    continue

                df["bar_date"] = df["ts_event"].dt.date
                daily = (
                    df.sort_values("volume", ascending=False)
                    .groupby("bar_date")
                    .first()
                    .sort_index()
                )

                bars = [
                    (d, float(row["open"]), float(row["high"]),
                     float(row["low"]), float(row["close"]))
                    for d, row in daily.iterrows()
                ]

                info = self._refresh_atr_from_daily_bars(sym, bars)
                refreshed.append(info)
            except Exception:
                logger.exception("Failed to refresh ATR for %s", sym)
                refreshed.append(self._refresh_atr_from_daily_bars(sym, []))

        return refreshed

    def get_atr_value(self, symbol: str, atr_length: int) -> float:
        calc = self._atrs.get(symbol, {}).get(atr_length)
        return calc.value if calc is not None else 0.0

    def get_atr_values_for_symbol(self, symbol: str) -> ATRValuesByLength:
        return {
            length: calc.value for length, calc in self._atrs.get(symbol, {}).items()
        }

    def get_atr_values(self) -> dict[str, float]:
        """Return the primary ATR value per symbol (backward-compatible)."""
        result: dict[str, float] = {}
        for sym in self.symbols:
            primary_length = self._atr_lengths_by_symbol[sym][0]
            result[sym] = self._atrs[sym][primary_length].value
        return result

    def get_daily_history_for_symbol(
        self,
        symbol: str,
        *,
        include_current: bool = True,
    ) -> list[tuple[date, float, float, float, float]]:
        tracker = self._daily_history.get(symbol)
        if tracker is None:
            return []
        return tracker.snapshot(include_current=include_current)

    def preload_intraday_5m(self, lookback_hours: int = 18) -> dict[str, list[Bar]]:
        """load recent 1m history and build 5m bars for restart recovery."""
        import databento as db
        import pandas as pd

        # DataBento historical data has a short delay; subtract 5 min buffer
        # to avoid 'data_end_after_available_end' errors on restart.
        # (Previously 20 min — reduced to capture more of the ORB window.)
        end_dt = datetime.now(tz=ET) - timedelta(minutes=5)
        start_dt = end_dt - timedelta(hours=lookback_hours)
        bars_by_symbol: dict[str, list[Bar]] = {sym: [] for sym in self.symbols}

        try:
            logger.info(
                "Preloading intraday history: symbols=%s lookback_hours=%d",
                self.symbols,
                lookback_hours,
            )

            client = db.Historical(key=self.api_key)
            data = client.timeseries.get_range(
                dataset=self.dataset,
                symbols=self.symbols,
                schema="ohlcv-1m",
                stype_in="parent",
                start=start_dt.isoformat(),
                end=end_dt.isoformat(),
            )
            df = data.to_df()
            if df.empty:
                logger.warning("No intraday preload bars returned")
                return bars_by_symbol

            df = df.reset_index()
            if "ts_event" not in df.columns:
                logger.warning("Skipping intraday preload: ts_event column missing")
                return bars_by_symbol

            if "symbol" in df.columns:
                df = df[~df["symbol"].astype(str).str.contains("-", na=False)]

            df["ts_event"] = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
            df = df[df["ts_event"].notna()]
            if df.empty:
                logger.warning("Skipping intraday preload: no valid timestamps")
                return bars_by_symbol

            if "stype_in_symbol" in df.columns:
                df["parent_symbol"] = df["stype_in_symbol"].astype(str)
            elif len(self.symbols) == 1:
                df["parent_symbol"] = self.symbols[0]
            elif "symbol" in df.columns:
                root_to_parent = {sym.split(".")[0]: sym for sym in self.symbols}
                df["parent_symbol"] = (
                    df["symbol"]
                    .astype(str)
                    .str.extract(r"^([A-Za-z]+)", expand=False)
                    .str.upper()
                    .map(root_to_parent)
                )
            else:
                logger.warning("Skipping intraday preload: parent symbol unavailable")
                return bars_by_symbol

            df = df[df["parent_symbol"].isin(self.symbols)]
            if df.empty:
                logger.warning("Skipping intraday preload: no matching symbols")
                return bars_by_symbol

            # pick the highest-volume contract each minute for each parent symbol.
            df = (
                df.sort_values(["parent_symbol", "ts_event", "volume"], ascending=[True, True, False])
                .groupby(["parent_symbol", "ts_event"], as_index=False)
                .first()
                .sort_values(["ts_event", "parent_symbol"])
            )

            # reset aggregators so live stream continues from this rebuilt bucket state.
            for sym in self.symbols:
                self._aggregators[sym] = BarAggregator()

            for _, row in df.iterrows():
                symbol = str(row["parent_symbol"])
                ts_et = row["ts_event"].tz_convert(ET).to_pydatetime()
                bar_5m = self._ingest_1m_bar(
                    symbol=symbol,
                    ts_event=ts_et,
                    o=float(row["open"]),
                    h=float(row["high"]),
                    l=float(row["low"]),
                    c=float(row["close"]),
                    v=int(row.get("volume", 0)),
                    source="preload",
                )
                if bar_5m is not None:
                    bars_by_symbol[symbol].append(bar_5m)

            logger.info(
                "Intraday preload complete: %s",
                {sym: len(bars) for sym, bars in bars_by_symbol.items()},
            )
            return bars_by_symbol
        except Exception:
            logger.exception("Failed to preload intraday 5m history")
            return bars_by_symbol

    async def run(self) -> None:
        """Start streaming. Blocks forever, reconnects on failure."""
        import databento as db

        self._running = True
        delay = self.reconnect_delay

        while self._running:
            try:
                logger.info(
                    "Connecting to DataBento: dataset=%s symbols=%s schemas=ohlcv-1m+ohlcv-1s",
                    self.dataset, self.symbols,
                )

                # Run blocking DataBento connect + subscribe in a thread so
                # the event loop stays free for uvicorn to start.
                loop = asyncio.get_running_loop()

                def _connect():
                    c = db.Live(key=self.api_key)
                    c.subscribe(
                        dataset=self.dataset,
                        schema="ohlcv-1m",
                        stype_in="parent",
                        symbols=self.symbols,
                    )
                    c.subscribe(
                        dataset=self.dataset,
                        schema="ohlcv-1s",
                        stype_in="parent",
                        symbols=self.symbols,
                    )
                    return c

                client = await loop.run_in_executor(None, _connect)

                logger.info("DataBento connected — streaming 1m + 1s bars")
                delay = self.reconnect_delay  # reset on successful connect
                self._id_to_symbol.clear()
                self._id_to_raw.clear()
                self._id_volumes.clear()
                self._front_month.clear()

                from databento_dbn import RType

                async for record in client:
                    if not self._running:
                        break

                    if isinstance(record, db.SymbolMappingMsg):
                        # Map instrument IDs to parent symbols
                        # stype_in_symbol = parent (e.g. "NQ.FUT")
                        # stype_out_symbol = raw contract (e.g. "NQH6")
                        parent = record.stype_in_symbol
                        raw = record.stype_out_symbol
                        iid = record.instrument_id
                        if parent in self.symbols and "-" not in raw:
                            self._id_to_symbol[iid] = parent
                            self._id_to_raw[iid] = raw
                            self._id_volumes[iid] = 0
                            logger.debug(
                                "Symbol mapped: %s (id=%d) → %s",
                                raw, iid, parent,
                            )
                    elif isinstance(record, db.OHLCVMsg):
                        if record.rtype == RType.OHLCV_1M:
                            await self._handle_ohlcv(record)
                        elif record.rtype == RType.OHLCV_1S:
                            await self._handle_ohlcv_1s(record)
                    elif isinstance(record, db.ErrorMsg):
                        logger.error("DataBento error: %s", record.err)

            except Exception:
                logger.exception("DataBento feed error — reconnecting in %.1fs", delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, self.max_reconnect_delay)

    async def _handle_ohlcv(self, record) -> None:
        """Process a single 1m OHLCV record from DataBento."""
        # Resolve which parent symbol this record belongs to
        iid = record.instrument_id
        symbol = self._id_to_symbol.get(iid)
        if symbol is None:
            return  # spread or unknown instrument, skip

        v = record.volume

        # Track cumulative volume to elect front-month contract
        self._id_volumes[iid] = self._id_volumes.get(iid, 0) + v

        current_front = self._front_month.get(symbol)
        if current_front is None:
            # First bar for this symbol — elect this contract
            self._front_month[symbol] = iid
            current_front = iid
            raw = self._id_to_raw.get(iid, "?")
            logger.info("Front-month elected for %s: %s (id=%d)", symbol, raw, iid)
        elif iid != current_front:
            # Check if this contract has overtaken the current front-month
            if self._id_volumes[iid] > self._id_volumes.get(current_front, 0):
                old_raw = self._id_to_raw.get(current_front, "?")
                new_raw = self._id_to_raw.get(iid, "?")
                logger.info(
                    "Front-month rolled for %s: %s → %s (vol %d > %d)",
                    symbol, old_raw, new_raw,
                    self._id_volumes[iid], self._id_volumes.get(current_front, 0),
                )
                self._front_month[symbol] = iid
                current_front = iid
                # Reset aggregator on roll — partial bucket from old contract is stale
                self._aggregators[symbol] = BarAggregator()

        # Only process bars from the front-month contract
        if iid != current_front:
            return

        # DataBento prices are in fixed-point (1e-9 scale)
        o = record.open / 1e9
        h = record.high / 1e9
        l = record.low / 1e9
        c = record.close / 1e9

        # Convert timestamp to Eastern and aggregate through the canonical
        # 1m->5m path shared with preload recovery.
        ts_dt = datetime.fromtimestamp(record.ts_event / 1e9, tz=ET)
        bar_5m = self._ingest_1m_bar(
            symbol=symbol,
            ts_event=ts_dt,
            o=o,
            h=h,
            l=l,
            c=c,
            v=v,
            source="live",
        )
        atr_calcs = self._atrs[symbol]

        if bar_5m is not None:
            self._daily_history[symbol].on_5m_bar(bar_5m)
            # update daily ATR for each configured length on this symbol
            for atr_calc in atr_calcs.values():
                atr_calc.on_5m_bar(bar_5m)
            atr_values = {
                length: calc.value for length, calc in atr_calcs.items()
            }

            logger.debug(
                "5m bar [%s]: %s O=%.2f H=%.2f L=%.2f C=%.2f V=%d ATRs=%s",
                symbol, bar_5m.timestamp, bar_5m.open, bar_5m.high, bar_5m.low,
                bar_5m.close, bar_5m.volume,
                {length: round(value, 2) for length, value in atr_values.items()},
            )

            # call session engines with symbol tag
            if self.on_bar is not None:
                await self.on_bar(symbol, bar_5m, atr_values)

    async def _handle_ohlcv_1s(self, record) -> None:
        """Process a single 1s OHLCV record — forwarded directly to engines."""
        iid = record.instrument_id
        symbol = self._id_to_symbol.get(iid)
        if symbol is None:
            return  # spread or unknown instrument, skip

        # Only process front-month contract (don't update volume election from 1s)
        current_front = self._front_month.get(symbol)
        if current_front is None or iid != current_front:
            return

        o = record.open / 1e9
        h = record.high / 1e9
        l = record.low / 1e9
        c = record.close / 1e9
        v = record.volume

        ts_dt = datetime.fromtimestamp(record.ts_event / 1e9, tz=ET)

        tick = Bar(timestamp=ts_dt, open=o, high=h, low=l, close=c, volume=v)

        if self.on_tick is not None:
            await self.on_tick(symbol, tick, self.get_atr_values_for_symbol(symbol))

    def stop(self) -> None:
        """Signal the feed to stop."""
        self._running = False


# ---------------------------------------------------------------------------
# Historical replay feed (for testing / reconciliation)
# ---------------------------------------------------------------------------

class ReplayFeed:
    """Replay historical 5m bars from a CSV file through the engine.

    Useful for testing the state machine against known backtest output.

    Args:
        csv_path: Path to a 5m CSV (datetime, open, high, low, close, volume).
        on_bar: Async callback for each bar.
        atr_length: ATR period.
        start_date: Optional start date filter.
        end_date: Optional end date filter.
    """

    def __init__(
        self,
        csv_path: str,
        on_bar: OnBarCallback | None = None,
        atr_length: int = 14,
        atr_lengths: list[int] | set[int] | tuple[int, ...] | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        self.csv_path = csv_path
        self.on_bar = on_bar
        self.atr_length = atr_length
        self.atr_lengths = sorted({int(length) for length in (atr_lengths or [atr_length])})
        self.start_date = start_date
        self.end_date = end_date
        self._atrs = {
            length: ATRCalculator(length=length) for length in self.atr_lengths
        }

    async def run(self) -> None:
        """Replay all bars from the CSV."""
        import pandas as pd

        df = pd.read_csv(self.csv_path, parse_dates=["datetime"], index_col="datetime")

        if df.index.tz is None:
            df.index = df.index.tz_localize(ET)
        else:
            df.index = df.index.tz_convert(ET)

        if self.start_date:
            df = df[df.index >= self.start_date]
        if self.end_date:
            df = df[df.index <= self.end_date]

        for ts, row in df.iterrows():
            bar = Bar(
                timestamp=ts.to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=int(row.get("volume", 0)),
            )

            for atr_calc in self._atrs.values():
                atr_calc.on_5m_bar(bar)

            if self.on_bar is not None:
                await self.on_bar(
                    bar,
                    {length: calc.value for length, calc in self._atrs.items()},
                )
