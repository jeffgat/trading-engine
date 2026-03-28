"""15-minute structure signals for context filtering.

Resamples 5m bars to session-aligned 15m bars and detects:
- HH/HL (Higher-High / Higher-Low) stair-step patterns
- LH/LL (Lower-High / Lower-Low) patterns
- Directional swing score (0-3)
- Multi-day session regime (1-day, 2-day, 2-of-3)
- Pullback quality (holds VWAP / ORB after breakout)

All signals are mapped back to the 5m bar index with no lookahead:
a 5m bar only sees the most recent *completed* 15m bar.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..config import SessionConfig
from .session import compute_session_masks, compute_session_days


# ---------------------------------------------------------------------------
# 1. Resample 5m -> 15m (session-aligned, no lookahead)
# ---------------------------------------------------------------------------

def resample_session_15m(
    df: pd.DataFrame,
    session: SessionConfig,
) -> tuple[pd.DataFrame, np.ndarray]:
    """Resample 5m bars to session-aligned 15m bars within RTH.

    15m boundaries align to the session start (e.g. 09:30, 09:45, 10:00 ...
    for NY).  Each group of 3 consecutive RTH 5m bars forms one 15m bar.

    Args:
        df: 5m OHLCV DataFrame with DatetimeIndex (Eastern time).
        session: SessionConfig defining RTH boundaries.

    Returns:
        df_15m: 15m OHLCV DataFrame (index = 15m bar open time).
        map_5m_to_15m: int array of length ``len(df)``.  For each 5m bar,
            the *positional* index into ``df_15m`` of the most recent
            **completed** 15m bar.  -1 before the first completed 15m bar
            of each session day.
    """
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    in_rth = masks["in_rth"]
    _, session_day_id = compute_session_days(timestamps, session)

    # Assign each RTH 5m bar a sequential position within its session day
    # so we can group every 3 bars into one 15m bar.
    pos_in_day = np.full(len(df), -1, dtype=np.int64)
    current_day = -1
    counter = 0
    for i in range(len(df)):
        if not in_rth[i]:
            continue
        if session_day_id[i] != current_day:
            current_day = session_day_id[i]
            counter = 0
        pos_in_day[i] = counter
        counter += 1

    # 15m group index within session day (0, 0, 0, 1, 1, 1, 2, ...)
    group_in_day = np.where(pos_in_day >= 0, pos_in_day // 3, -1)

    # Build a global 15m bar id combining session_day_id and group_in_day
    # Use a tuple-like encoding: day * 10000 + group
    global_15m_id = np.where(
        group_in_day >= 0,
        session_day_id * 10000 + group_in_day,
        -1,
    )

    # Position within the 15m group (0, 1, 2, 0, 1, 2, ...)
    pos_in_group = np.where(pos_in_day >= 0, pos_in_day % 3, -1)

    # Build 15m OHLCV by grouping
    rth_mask = global_15m_id >= 0
    rth_indices = np.where(rth_mask)[0]

    if len(rth_indices) == 0:
        empty_15m = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            dtype=np.float64,
        )
        return empty_15m, np.full(len(df), -1, dtype=np.int64)

    # Aggregate: group by global_15m_id
    gids = global_15m_id[rth_indices]
    unique_gids, first_idx = np.unique(gids, return_index=True)
    # Sort by first occurrence to maintain chronological order
    order = np.argsort(first_idx)
    unique_gids = unique_gids[order]

    high_vals = df["high"].values.astype(np.float64)
    low_vals = df["low"].values.astype(np.float64)
    open_vals = df["open"].values.astype(np.float64)
    close_vals = df["close"].values.astype(np.float64)
    vol_vals = df["volume"].values.astype(np.float64)

    n_15m = len(unique_gids)
    gid_to_pos = {int(g): idx for idx, g in enumerate(unique_gids)}

    bars_15m_open = np.full(n_15m, np.nan)
    bars_15m_high = np.full(n_15m, -np.inf)
    bars_15m_low = np.full(n_15m, np.inf)
    bars_15m_close = np.full(n_15m, np.nan)
    bars_15m_vol = np.zeros(n_15m)
    bars_15m_time = [None] * n_15m
    bars_15m_count = np.zeros(n_15m, dtype=np.int64)

    for raw_i in rth_indices:
        gid = int(global_15m_id[raw_i])
        pos = gid_to_pos[gid]
        p = int(pos_in_group[raw_i])
        if p == 0:
            bars_15m_open[pos] = open_vals[raw_i]
            bars_15m_time[pos] = df.index[raw_i]
        if high_vals[raw_i] > bars_15m_high[pos]:
            bars_15m_high[pos] = high_vals[raw_i]
        if low_vals[raw_i] < bars_15m_low[pos]:
            bars_15m_low[pos] = low_vals[raw_i]
        bars_15m_close[pos] = close_vals[raw_i]  # last wins
        bars_15m_vol[pos] += vol_vals[raw_i]
        bars_15m_count[pos] += 1

    # Only keep complete 15m bars (exactly 3 constituent 5m bars)
    complete_mask = bars_15m_count == 3
    complete_indices = np.where(complete_mask)[0]

    if len(complete_indices) == 0:
        empty_15m = pd.DataFrame(
            columns=["open", "high", "low", "close", "volume"],
            dtype=np.float64,
        )
        return empty_15m, np.full(len(df), -1, dtype=np.int64)

    df_15m = pd.DataFrame(
        {
            "open": bars_15m_open[complete_indices],
            "high": bars_15m_high[complete_indices],
            "low": bars_15m_low[complete_indices],
            "close": bars_15m_close[complete_indices],
            "volume": bars_15m_vol[complete_indices],
        },
        index=pd.DatetimeIndex([bars_15m_time[i] for i in complete_indices]),
    )

    # Build a mapping from old positional index to new (complete-only) index
    old_to_new = np.full(n_15m, -1, dtype=np.int64)
    for new_idx, old_idx in enumerate(complete_indices):
        old_to_new[old_idx] = new_idx

    # Map each 5m bar to its most recent completed 15m bar index
    map_5m_to_15m = np.full(len(df), -1, dtype=np.int64)

    for raw_i in range(len(df)):
        gid = int(global_15m_id[raw_i])
        if gid < 0:
            # Not in RTH — carry forward from previous bar
            if raw_i > 0:
                map_5m_to_15m[raw_i] = map_5m_to_15m[raw_i - 1]
            continue

        pos = gid_to_pos.get(gid, -1)
        if pos < 0:
            if raw_i > 0:
                map_5m_to_15m[raw_i] = map_5m_to_15m[raw_i - 1]
            continue

        p = int(pos_in_group[raw_i])
        if p == 2:
            # Third bar of the 15m group — this 15m bar is now complete
            new_idx = old_to_new[pos]
            if new_idx >= 0:
                map_5m_to_15m[raw_i] = new_idx
            elif raw_i > 0:
                map_5m_to_15m[raw_i] = map_5m_to_15m[raw_i - 1]
        else:
            # First or second bar — use the PRIOR completed 15m bar
            if pos > 0:
                new_idx = old_to_new[pos - 1]
                if new_idx >= 0:
                    map_5m_to_15m[raw_i] = new_idx
                elif raw_i > 0:
                    map_5m_to_15m[raw_i] = map_5m_to_15m[raw_i - 1]
            elif raw_i > 0:
                map_5m_to_15m[raw_i] = map_5m_to_15m[raw_i - 1]

    return df_15m, map_5m_to_15m


# ---------------------------------------------------------------------------
# 2. HH/HL and LH/LL pattern detection
# ---------------------------------------------------------------------------

def compute_hh_hl_patterns(
    df_15m: pd.DataFrame,
    map_5m_to_15m: np.ndarray,
    n_bars: int = 2,
) -> dict[str, np.ndarray]:
    """Detect HH/HL (bullish) and LH/LL (bearish) patterns on completed 15m bars.

    HH/HL-N: the last ``n_bars`` completed 15m bars each have a higher high
    AND higher low than their predecessor.  LH/LL-N is the mirror.

    Args:
        df_15m: 15m OHLCV DataFrame from :func:`resample_session_15m`.
        map_5m_to_15m: Mapping array from :func:`resample_session_15m`.
        n_bars: Number of consecutive 15m bars required (2 or 3).

    Returns:
        Dict with ``'bullish'`` and ``'bearish'`` bool arrays on the 5m index.
    """
    n_5m = len(map_5m_to_15m)
    n_15m = len(df_15m)

    bullish_5m = np.zeros(n_5m, dtype=bool)
    bearish_5m = np.zeros(n_5m, dtype=bool)

    if n_15m < n_bars + 1:
        return {"bullish": bullish_5m, "bearish": bearish_5m}

    high_15m = df_15m["high"].values.astype(np.float64)
    low_15m = df_15m["low"].values.astype(np.float64)

    # Pre-compute pattern at each 15m bar index
    bullish_15m = np.zeros(n_15m, dtype=bool)
    bearish_15m = np.zeros(n_15m, dtype=bool)

    for k in range(n_bars, n_15m):
        bull = True
        bear = True
        for j in range(1, n_bars + 1):
            if high_15m[k - j + 1] <= high_15m[k - j]:
                bull = False
            if low_15m[k - j + 1] <= low_15m[k - j]:
                bull = False
            if high_15m[k - j + 1] >= high_15m[k - j]:
                bear = False
            if low_15m[k - j + 1] >= low_15m[k - j]:
                bear = False
        bullish_15m[k] = bull
        bearish_15m[k] = bear

    # Map to 5m index
    valid = map_5m_to_15m >= 0
    bullish_5m[valid] = bullish_15m[map_5m_to_15m[valid]]
    bearish_5m[valid] = bearish_15m[map_5m_to_15m[valid]]

    return {"bullish": bullish_5m, "bearish": bearish_5m}


def compute_relaxed_patterns(
    df_15m: pd.DataFrame,
    map_5m_to_15m: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute relaxed 15m structure patterns for higher trade retention.

    Variants (all on the most recent completed 15m bar vs its predecessor):
        ``hh_only``: latest high > prior high (ignores low)
        ``hl_only``: latest low > prior low (ignores high)
        ``hh_or_hl``: either higher high OR higher low (at least one)
        ``hh_hl_any2of3``: HH AND HL across at least 1 of the last 2
            completed 15m bar-pairs (k vs k-1, OR k-1 vs k-2).
        ``hh_hl_any2of4``: HH AND HL across at least 1 of the last 3
            completed 15m bar-pairs.
    Bearish mirrors included.

    Returns:
        Dict of bool arrays on the 5m index.
    """
    n_5m = len(map_5m_to_15m)
    n_15m = len(df_15m)

    out: dict[str, np.ndarray] = {}
    keys = [
        "hh_only_bull", "hh_only_bear",
        "hl_only_bull", "hl_only_bear",
        "hh_or_hl_bull", "hh_or_hl_bear",
        "hh_hl_any2of3_bull", "hh_hl_any2of3_bear",
        "hh_hl_any2of4_bull", "hh_hl_any2of4_bear",
    ]
    for k in keys:
        out[k] = np.zeros(n_5m, dtype=bool)

    if n_15m < 2:
        return out

    high_15m = df_15m["high"].values.astype(np.float64)
    low_15m = df_15m["low"].values.astype(np.float64)

    # Per-pair HH/HL booleans at each 15m index (pair = k vs k-1)
    pair_hh = np.zeros(n_15m, dtype=bool)
    pair_hl = np.zeros(n_15m, dtype=bool)
    pair_lh = np.zeros(n_15m, dtype=bool)
    pair_ll = np.zeros(n_15m, dtype=bool)
    pair_bull = np.zeros(n_15m, dtype=bool)  # HH AND HL
    pair_bear = np.zeros(n_15m, dtype=bool)  # LH AND LL

    for k in range(1, n_15m):
        pair_hh[k] = high_15m[k] > high_15m[k - 1]
        pair_hl[k] = low_15m[k] > low_15m[k - 1]
        pair_lh[k] = high_15m[k] < high_15m[k - 1]
        pair_ll[k] = low_15m[k] < low_15m[k - 1]
        pair_bull[k] = pair_hh[k] and pair_hl[k]
        pair_bear[k] = pair_lh[k] and pair_ll[k]

    # HH only / HL only / HH or HL (single pair, k vs k-1)
    hh_only_bull_15m = pair_hh
    hh_only_bear_15m = pair_lh
    hl_only_bull_15m = pair_hl
    hl_only_bear_15m = pair_ll
    hh_or_hl_bull_15m = pair_hh | pair_hl
    hh_or_hl_bear_15m = pair_lh | pair_ll

    # Any 2 of 3: HH+HL in at least 1 of the 2 most recent pairs
    any2of3_bull_15m = np.zeros(n_15m, dtype=bool)
    any2of3_bear_15m = np.zeros(n_15m, dtype=bool)
    for k in range(2, n_15m):
        any2of3_bull_15m[k] = pair_bull[k] or pair_bull[k - 1]
        any2of3_bear_15m[k] = pair_bear[k] or pair_bear[k - 1]

    # Any 2 of 4: HH+HL in at least 1 of the 3 most recent pairs
    any2of4_bull_15m = np.zeros(n_15m, dtype=bool)
    any2of4_bear_15m = np.zeros(n_15m, dtype=bool)
    for k in range(3, n_15m):
        any2of4_bull_15m[k] = pair_bull[k] or pair_bull[k - 1] or pair_bull[k - 2]
        any2of4_bear_15m[k] = pair_bear[k] or pair_bear[k - 1] or pair_bear[k - 2]

    # Map all to 5m
    valid = map_5m_to_15m >= 0
    m = map_5m_to_15m[valid]
    out["hh_only_bull"][valid] = hh_only_bull_15m[m]
    out["hh_only_bear"][valid] = hh_only_bear_15m[m]
    out["hl_only_bull"][valid] = hl_only_bull_15m[m]
    out["hl_only_bear"][valid] = hl_only_bear_15m[m]
    out["hh_or_hl_bull"][valid] = hh_or_hl_bull_15m[m]
    out["hh_or_hl_bear"][valid] = hh_or_hl_bear_15m[m]
    out["hh_hl_any2of3_bull"][valid] = any2of3_bull_15m[m]
    out["hh_hl_any2of3_bear"][valid] = any2of3_bear_15m[m]
    out["hh_hl_any2of4_bull"][valid] = any2of4_bull_15m[m]
    out["hh_hl_any2of4_bear"][valid] = any2of4_bear_15m[m]

    return out


# ---------------------------------------------------------------------------
# 3. Swing score (0-3)
# ---------------------------------------------------------------------------

def compute_swing_score(
    df_15m: pd.DataFrame,
    map_5m_to_15m: np.ndarray,
    vwap: np.ndarray,
    close_5m: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute directional swing score (0-3) per 5m bar.

    Bull score:
        +1 if latest completed 15m high > prior completed 15m high
        +1 if latest completed 15m low  > prior completed 15m low
        +1 if 5m close > session VWAP
    Bear score (mirrored):
        +1 if latest completed 15m high < prior completed 15m high
        +1 if latest completed 15m low  < prior completed 15m low
        +1 if 5m close < session VWAP

    Returns:
        Dict with ``'bull_score'`` and ``'bear_score'`` int8 arrays on the 5m index.
    """
    n_5m = len(map_5m_to_15m)
    n_15m = len(df_15m)
    bull_score = np.zeros(n_5m, dtype=np.int8)
    bear_score = np.zeros(n_5m, dtype=np.int8)

    if n_15m < 2:
        return {"bull_score": bull_score, "bear_score": bear_score}

    high_15m = df_15m["high"].values.astype(np.float64)
    low_15m = df_15m["low"].values.astype(np.float64)

    # Pre-compute 15m-level structure components
    hh_15m = np.zeros(n_15m, dtype=np.int8)  # +1 if higher high
    hl_15m = np.zeros(n_15m, dtype=np.int8)  # +1 if higher low
    lh_15m = np.zeros(n_15m, dtype=np.int8)  # +1 if lower high
    ll_15m = np.zeros(n_15m, dtype=np.int8)  # +1 if lower low
    for k in range(1, n_15m):
        if high_15m[k] > high_15m[k - 1]:
            hh_15m[k] = 1
        if low_15m[k] > low_15m[k - 1]:
            hl_15m[k] = 1
        if high_15m[k] < high_15m[k - 1]:
            lh_15m[k] = 1
        if low_15m[k] < low_15m[k - 1]:
            ll_15m[k] = 1

    valid = map_5m_to_15m >= 0
    mapped = map_5m_to_15m[valid]

    # Structure components from 15m
    bull_struct = hh_15m[mapped] + hl_15m[mapped]  # 0-2
    bear_struct = lh_15m[mapped] + ll_15m[mapped]  # 0-2

    # VWAP component (on 5m)
    vwap_valid = ~np.isnan(vwap)
    bull_vwap = np.zeros(n_5m, dtype=np.int8)
    bear_vwap = np.zeros(n_5m, dtype=np.int8)
    above = vwap_valid & (close_5m > vwap)
    below = vwap_valid & (close_5m < vwap)
    bull_vwap[above] = 1
    bear_vwap[below] = 1

    bull_score[valid] = bull_struct + bull_vwap[valid]
    bear_score[valid] = bear_struct + bear_vwap[valid]

    return {"bull_score": bull_score, "bear_score": bear_score}


# ---------------------------------------------------------------------------
# 4. Multi-day session regime
# ---------------------------------------------------------------------------

def compute_session_regime(
    df: pd.DataFrame,
    session: SessionConfig,
) -> dict[str, np.ndarray]:
    """Compute multi-day session regime indicators.

    Uses **prior** completed session data only (no lookahead).

    Definitions:
        1-day bullish: prior session's high > session before that AND
                       prior session's low  > session before that.
        2-day bullish: last 2 sessions each made higher session highs AND
                       higher session lows vs their predecessor.
        2-of-3 bullish: at least 2 of last 3 sessions were individually bullish.
        Bearish versions are mirrored.

    Returns:
        Dict of bool arrays on the 5m index:
        ``regime_1d_bull``, ``regime_1d_bear``,
        ``regime_2d_bull``, ``regime_2d_bear``,
        ``regime_2of3_bull``, ``regime_2of3_bear``.
    """
    n = len(df)
    timestamps = df.index
    masks = compute_session_masks(timestamps, session)
    in_rth = masks["in_rth"]
    _, session_day_id = compute_session_days(timestamps, session)

    high_vals = df["high"].values.astype(np.float64)
    low_vals = df["low"].values.astype(np.float64)

    # Compute per-session-day high and low
    unique_days = np.unique(session_day_id)
    day_high: dict[int, float] = {}
    day_low: dict[int, float] = {}

    for d in unique_days:
        mask = (session_day_id == d) & in_rth
        if not np.any(mask):
            continue
        day_high[int(d)] = float(np.nanmax(high_vals[mask]))
        day_low[int(d)] = float(np.nanmin(low_vals[mask]))

    # Build ordered list of session days
    ordered_days = sorted(day_high.keys())
    n_days = len(ordered_days)

    # Per-session bullish/bearish vs predecessor
    day_bull: dict[int, bool] = {}
    day_bear: dict[int, bool] = {}
    for idx in range(1, n_days):
        d = ordered_days[idx]
        d_prev = ordered_days[idx - 1]
        hh = day_high[d] > day_high[d_prev]
        hl = day_low[d] > day_low[d_prev]
        lh = day_high[d] < day_high[d_prev]
        ll = day_low[d] < day_low[d_prev]
        day_bull[d] = hh and hl
        day_bear[d] = lh and ll

    # Build regime arrays per session day (using PRIOR days only)
    day_to_order: dict[int, int] = {d: i for i, d in enumerate(ordered_days)}

    regime_1d_bull_day: dict[int, bool] = {}
    regime_1d_bear_day: dict[int, bool] = {}
    regime_2d_bull_day: dict[int, bool] = {}
    regime_2d_bear_day: dict[int, bool] = {}
    regime_2of3_bull_day: dict[int, bool] = {}
    regime_2of3_bear_day: dict[int, bool] = {}

    for idx in range(n_days):
        d = ordered_days[idx]
        # 1-day: was the prior session bullish?
        if idx >= 2:
            d_prev = ordered_days[idx - 1]
            regime_1d_bull_day[d] = day_bull.get(d_prev, False)
            regime_1d_bear_day[d] = day_bear.get(d_prev, False)
        else:
            regime_1d_bull_day[d] = False
            regime_1d_bear_day[d] = False

        # 2-day: were the last 2 sessions both bullish?
        if idx >= 3:
            d_m1 = ordered_days[idx - 1]
            d_m2 = ordered_days[idx - 2]
            regime_2d_bull_day[d] = day_bull.get(d_m1, False) and day_bull.get(d_m2, False)
            regime_2d_bear_day[d] = day_bear.get(d_m1, False) and day_bear.get(d_m2, False)
        else:
            regime_2d_bull_day[d] = False
            regime_2d_bear_day[d] = False

        # 2-of-3: at least 2 of last 3 sessions bullish
        if idx >= 4:
            count_bull = sum(
                1 for j in range(1, 4)
                if day_bull.get(ordered_days[idx - j], False)
            )
            count_bear = sum(
                1 for j in range(1, 4)
                if day_bear.get(ordered_days[idx - j], False)
            )
            regime_2of3_bull_day[d] = count_bull >= 2
            regime_2of3_bear_day[d] = count_bear >= 2
        else:
            regime_2of3_bull_day[d] = False
            regime_2of3_bear_day[d] = False

    # Map to 5m index
    r1b = np.zeros(n, dtype=bool)
    r1e = np.zeros(n, dtype=bool)
    r2b = np.zeros(n, dtype=bool)
    r2e = np.zeros(n, dtype=bool)
    r23b = np.zeros(n, dtype=bool)
    r23e = np.zeros(n, dtype=bool)

    for i in range(n):
        d = int(session_day_id[i])
        r1b[i] = regime_1d_bull_day.get(d, False)
        r1e[i] = regime_1d_bear_day.get(d, False)
        r2b[i] = regime_2d_bull_day.get(d, False)
        r2e[i] = regime_2d_bear_day.get(d, False)
        r23b[i] = regime_2of3_bull_day.get(d, False)
        r23e[i] = regime_2of3_bear_day.get(d, False)

    return {
        "regime_1d_bull": r1b,
        "regime_1d_bear": r1e,
        "regime_2d_bull": r2b,
        "regime_2d_bear": r2e,
        "regime_2of3_bull": r23b,
        "regime_2of3_bear": r23e,
    }


# ---------------------------------------------------------------------------
# 5. Pullback quality
# ---------------------------------------------------------------------------

def compute_pullback_quality(
    low: np.ndarray,
    high: np.ndarray,
    vwap: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    orb_ready: np.ndarray,
    session_day_id: np.ndarray,
) -> dict[str, np.ndarray]:
    """Pre-compute pullback quality arrays for each 5m bar.

    For longs: after ORB completion, tracks the running minimum low.
    ``holds_vwap_bull[i]`` is True if that running min > ``vwap[i]``.
    ``holds_vwap_orb_bull[i]`` adds the requirement that min > ``orb_high[i]``.

    For shorts: mirrors using running maximum high.

    Returns:
        Dict with ``holds_vwap_bull``, ``holds_vwap_bear``,
        ``holds_vwap_orb_bull``, ``holds_vwap_orb_bear`` bool arrays.
    """
    n = len(low)
    holds_vwap_bull = np.zeros(n, dtype=bool)
    holds_vwap_bear = np.zeros(n, dtype=bool)
    holds_vwap_orb_bull = np.zeros(n, dtype=bool)
    holds_vwap_orb_bear = np.zeros(n, dtype=bool)

    current_day = -1
    running_low = np.inf
    running_high = -np.inf
    orb_started = False

    for i in range(n):
        d = int(session_day_id[i])
        if d != current_day:
            current_day = d
            running_low = np.inf
            running_high = -np.inf
            orb_started = False

        if orb_ready[i] and not orb_started:
            orb_started = True
            running_low = low[i]
            running_high = high[i]
        elif orb_started:
            if low[i] < running_low:
                running_low = low[i]
            if high[i] > running_high:
                running_high = high[i]

        if not orb_started:
            continue

        v = vwap[i]
        if np.isnan(v):
            continue

        # Bull: pullback low held above VWAP
        holds_vwap_bull[i] = running_low > v
        # Bear: pullback high held below VWAP
        holds_vwap_bear[i] = running_high < v

        oh = orb_high[i]
        ol = orb_low[i]
        if not np.isnan(oh):
            holds_vwap_orb_bull[i] = running_low > v and running_low > oh
        if not np.isnan(ol):
            holds_vwap_orb_bear[i] = running_high < v and running_high < ol

    return {
        "holds_vwap_bull": holds_vwap_bull,
        "holds_vwap_bear": holds_vwap_bear,
        "holds_vwap_orb_bull": holds_vwap_orb_bull,
        "holds_vwap_orb_bear": holds_vwap_orb_bear,
    }


# ---------------------------------------------------------------------------
# 6. Convenience wrapper
# ---------------------------------------------------------------------------

def compute_all_15m_signals(
    df: pd.DataFrame,
    session: SessionConfig,
    vwap: np.ndarray,
    daily_atr: np.ndarray,
    orb_high: np.ndarray,
    orb_low: np.ndarray,
    orb_ready: np.ndarray,
    session_day_id: np.ndarray,
) -> dict[str, np.ndarray]:
    """Compute all 15m structure signals at once.

    Returns a flat dict of arrays on the 5m index with keys:
        hh_hl_2_bull, hh_hl_2_bear,
        hh_hl_3_bull, hh_hl_3_bear,
        bull_score, bear_score,
        regime_1d_bull, regime_1d_bear,
        regime_2d_bull, regime_2d_bear,
        regime_2of3_bull, regime_2of3_bear,
        holds_vwap_bull, holds_vwap_bear,
        holds_vwap_orb_bull, holds_vwap_orb_bear,
        close, vwap, daily_atr.
    """
    close_5m = df["close"].values.astype(np.float64)
    low_5m = df["low"].values.astype(np.float64)
    high_5m = df["high"].values.astype(np.float64)

    # 15m resampling
    df_15m, map_5m = resample_session_15m(df, session)

    # HH/HL patterns
    pat2 = compute_hh_hl_patterns(df_15m, map_5m, n_bars=2)
    pat3 = compute_hh_hl_patterns(df_15m, map_5m, n_bars=3)

    # Relaxed patterns
    relaxed = compute_relaxed_patterns(df_15m, map_5m)

    # Swing score
    scores = compute_swing_score(df_15m, map_5m, vwap, close_5m)

    # Session regime
    regime = compute_session_regime(df, session)

    # Pullback quality
    pullback = compute_pullback_quality(
        low_5m, high_5m, vwap, orb_high, orb_low, orb_ready, session_day_id,
    )

    return {
        "hh_hl_2_bull": pat2["bullish"],
        "hh_hl_2_bear": pat2["bearish"],
        "hh_hl_3_bull": pat3["bullish"],
        "hh_hl_3_bear": pat3["bearish"],
        **relaxed,
        "bull_score": scores["bull_score"],
        "bear_score": scores["bear_score"],
        **regime,
        **pullback,
        "close": close_5m,
        "vwap": vwap,
        "daily_atr": daily_atr,
    }
