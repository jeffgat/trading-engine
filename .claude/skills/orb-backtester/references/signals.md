# Signal Modules Reference

All signal modules live in `python/src/orb_backtest/signals/` and follow a pure-function pattern: take arrays in, return arrays out.

## FVG Detection (`signals/fvg.py`)

**Function:** `detect_fvg(high, low, close, orb_high, orb_low, in_entry, min_gap_atr, max_gap_pts, daily_atr)`

**3-candle FVG pattern:**
- Bar [2] = "before" candle
- Bar [1] = impulse candle (creates the gap)
- Bar [0] = "after" candle (confirms gap exists)

**Bullish FVG conditions:**
```python
high[2] < low[0]       # gap between before-high and after-low
high[2] < high[1]      # impulse candle made new high
low[2] < low[0]        # gap is real (before-low below after-low)
gap_bottom > orb_high  # gap must be above ORB high
```

**Bearish FVG conditions:**
```python
low[2] > high[0]       # gap between before-low and after-high
low[2] > low[1]        # impulse candle made new low
high[2] > high[0]      # gap is real
gap_top < orb_low      # gap must be below ORB low
```

**Size filters:**
- Minimum gap: `gap_size >= daily_atr * min_gap_atr_pct / 100`
- Maximum gap: `gap_size <= max_gap_pts` (if max_gap_pts > 0)

**Returns:** Dict with 6 arrays: `long_fvg`, `short_fvg` (booleans), `long_entry`, `short_entry`, `long_gap_size`, `short_gap_size`

**Entry prices:**
- Long: top of bullish FVG (retest from above)
- Short: bottom of bearish FVG (retest from below)

## ORB Levels (`signals/orb.py`)

**Function:** `compute_orb_levels(high, low, in_orb, new_day)` — Numba @njit

- Tracks running high/low during ORB window bars
- Sets `orb_ready[i] = True` on first bar after ORB window closes
- Forward-fills ORB levels for remaining session bars
- Resets on `new_day` signal

**Returns:** `orb_high`, `orb_low`, `orb_ready` arrays

## Session Masks (`signals/session.py`)

**Function:** `compute_session_masks(timestamps, session_config, exchange_tz)`

Handles cross-midnight ranges (e.g., Asia session 18:00-07:00 ET).

**Returns 5 boolean masks:** `in_orb`, `in_entry`, `in_flat`, `in_rth`, `after_cutoff`

**Function:** `compute_session_days(timestamps, session_config, exchange_tz)`

Produces session-aware day boundaries. For cross-midnight sessions, shifts timestamps back by 6 hours so groupby logic works correctly.

**Returns:** `session_day` (date strings), `new_day` (boolean array)

## Daily ATR (`signals/daily_atr.py`)

**Function:** `compute_daily_atr(df, length=14)`

1. Resamples 5m OHLCV to daily
2. Computes True Range (max of H-L, |H-prevC|, |L-prevC|)
3. Wilder's smoothing: `ATR[i] = ATR[i-1] * (n-1)/n + TR[i] / n`
4. Shifts by 1 day (prevents look-ahead bias)
5. Maps back to 5m bars via `np.searchsorted`

**Returns:** `daily_atr` array aligned to 5m bars

## Adding a New Signal Module

Follow this pattern:

```python
# python/src/orb_backtest/signals/my_signal.py
import numpy as np

def compute_my_signal(high, low, close, ...):
    """Pure vectorized signal — arrays in, arrays out."""
    result = np.zeros(len(high), dtype=np.float64)
    # ... computation ...
    return result
```

Rules:
1. Pure function — no side effects, no DataFrame dependency in core logic
2. Accept NumPy arrays, return NumPy arrays
3. Use Numba @njit only when vectorization is insufficient (bar-by-bar state)
4. Shift by 1 bar before acting to prevent look-ahead bias
5. Register in `_extract_setup_candidates()` in `simulator.py` to integrate
