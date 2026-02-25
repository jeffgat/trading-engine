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

        # If this bar belongs to a new bucket, close the old one
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
OnBarCallback = Callable[[Bar, float], Awaitable[None]]
# Signature: async def on_bar(bar: Bar, daily_atr: float) -> None

# Multi-symbol callback includes the symbol name
OnSymbolBarCallback = Callable[[str, Bar, float], Awaitable[None]]
# Signature: async def on_bar(symbol: str, bar: Bar, daily_atr: float) -> None

# 1-second tick callback (same signature — each 1s bar forwarded as-is)
OnSymbolTickCallback = Callable[[str, Bar, float], Awaitable[None]]
# Signature: async def on_tick(symbol: str, tick: Bar, daily_atr: float) -> None


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
        on_bar: Async callback for each completed 5m bar (symbol, bar, atr).
        on_tick: Async callback for each 1s bar (symbol, tick, atr).
        atr_length: ATR period (default: 14 days).
        reconnect_delay: Initial reconnect delay in seconds.
        max_reconnect_delay: Maximum reconnect delay.
    """

    def __init__(
        self,
        api_key: str | None = None,
        symbols: list[str] | None = None,
        dataset: str = "GLBX.MDP3",
        on_bar: OnSymbolBarCallback | None = None,
        on_tick: OnSymbolTickCallback | None = None,
        atr_length: int = 14,
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
        self.dataset = dataset
        self.on_bar = on_bar
        self.on_tick = on_tick
        self.atr_length = atr_length
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        # Per-symbol aggregator + ATR
        self._aggregators: dict[str, BarAggregator] = {}
        self._atrs: dict[str, ATRCalculator] = {}
        for sym in self.symbols:
            self._aggregators[sym] = BarAggregator()
            self._atrs[sym] = ATRCalculator(length=atr_length)

        self._running = False
        # Populated after connection — maps instrument_id to parent symbol
        self._id_to_symbol: dict[int, str] = {}
        # Maps instrument_id to raw contract name (e.g. 42002475 → "NQH6")
        self._id_to_raw: dict[int, str] = {}
        # Front-month selection: cumulative volume per (parent, instrument_id)
        # and the currently elected front-month id per parent symbol
        self._id_volumes: dict[int, int] = {}  # instrument_id → cumulative volume
        self._front_month: dict[str, int] = {}  # parent symbol → instrument_id

    def warm_up(self, lookback_days: int = 30) -> None:
        """Seed ATR calculators with historical daily bars from DataBento.

        Fetches `lookback_days` of daily OHLCV for each symbol and feeds
        them into the ATR calculator so it's initialized on first live bar.
        """
        import databento as db

        end = date.today()
        start = end - timedelta(days=lookback_days)

        for sym in self.symbols:
            try:
                logger.info(
                    "Warming up ATR for %s: fetching %d days of daily bars",
                    sym, lookback_days,
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

                # Group by date, pick the row with highest volume (front month)
                if df.empty:
                    logger.warning("No daily bars returned for %s", sym)
                    continue

                df = df.reset_index()
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

                self._atrs[sym].seed_daily(bars)

            except Exception:
                logger.exception("Failed to warm up ATR for %s", sym)

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

                client = db.Live(key=self.api_key)
                client.subscribe(
                    dataset=self.dataset,
                    schema="ohlcv-1m",
                    stype_in="parent",
                    symbols=self.symbols,
                )
                client.subscribe(
                    dataset=self.dataset,
                    schema="ohlcv-1s",
                    stype_in="parent",
                    symbols=self.symbols,
                )

                logger.info("DataBento connected — streaming 1m + 1s bars")
                delay = self.reconnect_delay  # reset on successful connect
                self._id_to_symbol.clear()
                self._id_to_raw.clear()
                self._id_volumes.clear()
                self._front_month.clear()

                from databento_dbn import RType

                for record in client:
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
                                "Symbol mapping: %s (id=%d) → %s",
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

        # Convert timestamp to Eastern — ts_event is nanoseconds since epoch
        ts_dt = datetime.fromtimestamp(record.ts_event / 1e9, tz=ET)

        aggregator = self._aggregators[symbol]
        atr_calc = self._atrs[symbol]

        bar_5m = aggregator.add_1m_bar(ts_dt, o, h, l, c, v)

        if bar_5m is not None:
            # Update daily ATR
            atr_calc.on_5m_bar(bar_5m)

            logger.debug(
                "5m bar [%s]: %s O=%.2f H=%.2f L=%.2f C=%.2f V=%d ATR=%.2f",
                symbol, bar_5m.timestamp, bar_5m.open, bar_5m.high, bar_5m.low,
                bar_5m.close, bar_5m.volume, atr_calc.value,
            )

            # Call session engines with symbol tag
            if self.on_bar is not None:
                await self.on_bar(symbol, bar_5m, atr_calc.value)

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
            atr_value = self._atrs[symbol].value
            await self.on_tick(symbol, tick, atr_value)

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
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> None:
        self.csv_path = csv_path
        self.on_bar = on_bar
        self.atr_length = atr_length
        self.start_date = start_date
        self.end_date = end_date
        self._atr = ATRCalculator(length=atr_length)

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

            self._atr.on_5m_bar(bar)

            if self.on_bar is not None:
                await self.on_bar(bar, self._atr.value)
