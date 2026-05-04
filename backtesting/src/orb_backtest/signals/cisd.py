"""Body-based internal CISD detection.

CISD here means a close through the body level of the candle that started the
most recent internal counter-trend leg. It deliberately uses candle bodies, not
wicks, and it is causal: a signal at bar ``i`` only uses bars ``<= i``.
"""

from __future__ import annotations

import numpy as np


def detect_internal_cisd(
    open_: np.ndarray,
    close: np.ndarray,
    *,
    daily_atr: np.ndarray | None = None,
    min_leg_bars: int = 2,
    min_leg_atr_pct: float = 0.0,
    max_leg_bars: int = 60,
) -> dict[str, np.ndarray]:
    """Detect bullish/bearish internal CISD events using body structure.

    A bullish CISD is armed after a body-based down leg forms. The level is the
    body high of the first candle in that down leg. A later close above that
    level marks bullish CISD.

    A bearish CISD is the mirror image: after a body-based up leg forms, the
    level is the body low of the first candle in that up leg, and a later close
    below that level marks bearish CISD.

    Args:
        open_: Bar opens.
        close: Bar closes.
        daily_atr: Daily ATR per bar. Required when ``min_leg_atr_pct`` is
            greater than zero.
        min_leg_bars: Minimum count of consecutive body-structure bars before a
            level can trigger. ``2`` means at least two lower-body bars for a
            bullish CISD, or two higher-body bars for a bearish CISD.
        min_leg_atr_pct: Minimum body travel of the internal leg as a percentage
            of daily ATR. For bullish CISD this is source body-high minus the
            lowest body-low in the down leg; bearish is the mirrored distance.
        max_leg_bars: Expire an untriggered level after this many bars. ``0``
            disables expiry.

    Returns:
        Dict with boolean signal arrays plus the broken CISD level, the source
        level bar, and the body-leg length at trigger time.
    """
    n = len(close)
    if len(open_) != n:
        raise ValueError("open_ and close must have the same length")
    if daily_atr is not None and len(daily_atr) != n:
        raise ValueError("daily_atr must have the same length as open_ and close")
    if min_leg_bars < 1:
        raise ValueError("min_leg_bars must be >= 1")
    if min_leg_atr_pct < 0:
        raise ValueError("min_leg_atr_pct must be >= 0")
    if min_leg_atr_pct > 0 and daily_atr is None:
        raise ValueError("daily_atr is required when min_leg_atr_pct > 0")
    if max_leg_bars < 0:
        raise ValueError("max_leg_bars must be >= 0")

    body_high = np.maximum(open_.astype(float), close.astype(float))
    body_low = np.minimum(open_.astype(float), close.astype(float))
    daily_atr_arr = daily_atr.astype(float) if daily_atr is not None else None

    bullish = np.zeros(n, dtype=bool)
    bearish = np.zeros(n, dtype=bool)
    bullish_level = np.full(n, np.nan, dtype=float)
    bearish_level = np.full(n, np.nan, dtype=float)
    bullish_level_bar = np.full(n, -1, dtype=np.int64)
    bearish_level_bar = np.full(n, -1, dtype=np.int64)
    bullish_leg_bars = np.zeros(n, dtype=np.int64)
    bearish_leg_bars = np.zeros(n, dtype=np.int64)
    bullish_leg_move = np.zeros(n, dtype=float)
    bearish_leg_move = np.zeros(n, dtype=float)

    down_level = np.nan
    down_level_bar = -1
    down_leg_bars = 0
    down_leg_low = np.nan
    down_leg_move = 0.0
    in_down_leg = False

    up_level = np.nan
    up_level_bar = -1
    up_leg_bars = 0
    up_leg_high = np.nan
    up_leg_move = 0.0
    in_up_leg = False

    for i in range(1, n):
        # Trigger from levels armed by prior bars. This avoids allowing the
        # current bar to both define and break its own CISD level.
        if not np.isnan(down_level):
            expired = max_leg_bars > 0 and (i - down_level_bar) > max_leg_bars
            if expired:
                down_level = np.nan
                down_level_bar = -1
                down_leg_bars = 0
                down_leg_low = np.nan
                down_leg_move = 0.0
                in_down_leg = False
            else:
                min_move = 0.0
                if min_leg_atr_pct > 0:
                    atr = daily_atr_arr[i]
                    min_move = (
                        (min_leg_atr_pct / 100.0) * atr
                        if np.isfinite(atr) and atr > 0
                        else np.inf
                    )
                if (
                    down_leg_bars >= min_leg_bars
                    and down_leg_move >= min_move
                    and close[i] > down_level
                ):
                    bullish[i] = True
                    bullish_level[i] = down_level
                    bullish_level_bar[i] = down_level_bar
                    bullish_leg_bars[i] = down_leg_bars
                    bullish_leg_move[i] = down_leg_move
                    down_level = np.nan
                    down_level_bar = -1
                    down_leg_bars = 0
                    down_leg_low = np.nan
                    down_leg_move = 0.0
                    in_down_leg = False

        if not np.isnan(up_level):
            expired = max_leg_bars > 0 and (i - up_level_bar) > max_leg_bars
            if expired:
                up_level = np.nan
                up_level_bar = -1
                up_leg_bars = 0
                up_leg_high = np.nan
                up_leg_move = 0.0
                in_up_leg = False
            else:
                min_move = 0.0
                if min_leg_atr_pct > 0:
                    atr = daily_atr_arr[i]
                    min_move = (
                        (min_leg_atr_pct / 100.0) * atr
                        if np.isfinite(atr) and atr > 0
                        else np.inf
                    )
                if (
                    up_leg_bars >= min_leg_bars
                    and up_leg_move >= min_move
                    and close[i] < up_level
                ):
                    bearish[i] = True
                    bearish_level[i] = up_level
                    bearish_level_bar[i] = up_level_bar
                    bearish_leg_bars[i] = up_leg_bars
                    bearish_leg_move[i] = up_leg_move
                    up_level = np.nan
                    up_level_bar = -1
                    up_leg_bars = 0
                    up_leg_high = np.nan
                    up_leg_move = 0.0
                    in_up_leg = False

        lower_body = body_high[i] < body_high[i - 1] and body_low[i] < body_low[i - 1]
        higher_body = body_high[i] > body_high[i - 1] and body_low[i] > body_low[i - 1]

        if lower_body:
            if not in_down_leg:
                down_level = float(body_high[i])
                down_level_bar = i
                down_leg_bars = 1
                down_leg_low = float(body_low[i])
            else:
                down_leg_bars += 1
                down_leg_low = min(float(down_leg_low), float(body_low[i]))
            down_leg_move = max(0.0, float(down_level) - float(down_leg_low))
            in_down_leg = True
            in_up_leg = False
        elif higher_body:
            if not in_up_leg:
                up_level = float(body_low[i])
                up_level_bar = i
                up_leg_bars = 1
                up_leg_high = float(body_high[i])
            else:
                up_leg_bars += 1
                up_leg_high = max(float(up_leg_high), float(body_high[i]))
            up_leg_move = max(0.0, float(up_leg_high) - float(up_level))
            in_up_leg = True
            in_down_leg = False
        else:
            # A pause/inside bar interrupts the consecutive leg but leaves the
            # latest armed level available for a future close-through.
            in_down_leg = False
            in_up_leg = False

    return {
        "bullish_cisd": bullish,
        "bearish_cisd": bearish,
        "bullish_level": bullish_level,
        "bearish_level": bearish_level,
        "bullish_level_bar": bullish_level_bar,
        "bearish_level_bar": bearish_level_bar,
        "bullish_leg_bars": bullish_leg_bars,
        "bearish_leg_bars": bearish_leg_bars,
        "bullish_leg_move": bullish_leg_move,
        "bearish_leg_move": bearish_leg_move,
    }
