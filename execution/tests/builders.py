"""Bar sequence builders for tests.

Provides factory functions for constructing realistic bar sequences
(ORB, FVG patterns) for use in engine tests.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trader.engine import Bar

ET = ZoneInfo("America/New_York")


def make_bar(
    ts: str,
    o: float,
    h: float,
    l: float,
    c: float,
    v: int = 100,
    tz: ZoneInfo = ET,
) -> Bar:
    """Create a Bar from a 'YYYY-MM-DD HH:MM' Eastern-time string."""
    dt = datetime.strptime(ts, "%Y-%m-%d %H:%M").replace(tzinfo=tz)
    return Bar(timestamp=dt, open=o, high=h, low=l, close=c, volume=v)


def build_orb_sequence(
    date: str = "2025-01-15",
    orb_high: float = 19530.0,
    orb_low: float = 19480.0,
) -> list[Bar]:
    """Two 5m bars forming a stable ORB at 09:30 and 09:35.

    The bars span [orb_low, orb_high] across two candles.
    """
    mid = (orb_high + orb_low) / 2
    return [
        make_bar(f"{date} 09:30", mid, orb_high, orb_low, mid + 5),
        make_bar(f"{date} 09:35", mid + 5, orb_high - 2, orb_low + 2, mid + 3),
    ]


def build_bullish_fvg_bars(
    date: str = "2025-01-15",
    orb_high: float = 19530.0,
    gap: float = 10.0,
) -> list[Bar]:
    """Three 5m bars forming a valid bullish FVG above the ORB high.

    Bars are timed at 09:50, 09:55, 10:00 (starting one bar AFTER the ORB
    transition bar at 09:45) to prevent false pattern matches with the
    transition bar.

    Pattern (bar2 = oldest, bar0 = newest):
      - bar2.high < bar0.low  (gap exists; gap_size = bar0.low - bar2.high ≥ gap)
      - bar2.high < bar1.high  (bar2 is lower than impulse)
      - bar2.low < bar0.low
      - bar0.low > orb_high   (above ORB — required for ORB directional filter)

    Geometry:
      bar2: H = orb_high + 5,  L = orb_high
      bar1: H = orb_high + 30, L = orb_high + 5   (impulse)
      bar0: H = orb_high + 40, L = orb_high + 5 + gap  (after; gap_size = gap)
    """
    h = orb_high
    b2_high = h + 5
    b2_low = h
    b1_high = h + 30
    b1_low = h + 5
    b0_low = h + 5 + gap          # gap_size = b0_low - b2_high = gap
    b0_high = h + 40
    return [
        make_bar(f"{date} 09:50", h + 1, b2_high, b2_low, h + 4),
        make_bar(f"{date} 09:55", h + 4, b1_high, b1_low, h + 25),
        make_bar(f"{date} 10:00", h + 25, b0_high, b0_low, h + 38),
    ]


def build_bearish_fvg_bars(
    date: str = "2025-01-15",
    orb_low: float = 19480.0,
    gap: float = 10.0,
) -> list[Bar]:
    """Three 5m bars forming a valid bearish FVG below the ORB low.

    Bars are timed at 09:50, 09:55, 10:00 (starting one bar AFTER the ORB
    transition bar at 09:45) to prevent false pattern matches.

    Pattern (bar2 = oldest, bar0 = newest):
      - bar2.low > bar0.high  (gap exists; gap_size = bar2.low - bar0.high ≥ gap)
      - bar2.low > bar1.low   (bar2 is higher than impulse)
      - bar2.high > bar0.high
      - bar0.high < orb_low   (below ORB — required for ORB directional filter)

    Geometry:
      bar2: H = orb_low - 5, L = orb_low - 10
      bar1: H = orb_low - 5, L = orb_low - 35   (impulse)
      bar0: H = orb_low - 10 - gap, L = orb_low - 40
             gap_size = bar2.low - bar0.high = (orb_low-10) - (orb_low-10-gap) = gap
    """
    l = orb_low
    b2_low = l - 10
    b2_high = l - 5
    b1_high = l - 5
    b1_low = l - 35
    b0_high = l - 10 - gap       # gap_size = b2_low - b0_high = (l-10) - (l-10-gap) = gap
    b0_low = l - 40
    return [
        make_bar(f"{date} 09:50", l - 6, b2_high, b2_low, l - 6),
        make_bar(f"{date} 09:55", l - 6, b1_high, b1_low, l - 30),
        make_bar(f"{date} 10:00", l - 30, b0_high, b0_low, l - 28),
    ]
