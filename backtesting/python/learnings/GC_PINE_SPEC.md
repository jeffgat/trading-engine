# GC NY Inversion Longs — Stacked Strategy Pine Script Specification

Self-contained spec for implementing the full stacked GC strategy in Pine Script v6. Covers both signals, all logic, and dedup rules.

**Current production model**: `GC NY Inv Longs Stacked v9+CleanAir` (DB: `bt-gc-ny-inv-longs-stacked-v9-cleanair-2365b0`)

## Strategy Overview

**Instrument**: GC (Gold Futures, COMEX)
**Concept**: After the 5-minute opening range forms, wait for a bearish Fair Value Gap (FVG) below the ORB low. When price closes back above that FVG (invalidating it), enter long. This captures false breakdowns that reverse higher.
**Direction**: Long only. Shorts are structurally broken on GC across all strategy types.

## Instrument Details

| Field | Value |
|-------|-------|
| Symbol | GC |
| Point value | $100/point |
| Min tick | 0.10 |
| Commission | $0.05/contract/side |
| Timezone | America/New_York |

## Parameters

### Strategy

| Param | Value | Description |
|-------|-------|-------------|
| strategy | inversion | Wait for FVG invalidation, then enter |
| direction | long only | Only take longs |
| rr | 3.5 | Risk-reward ratio for TP2 |
| tp1_ratio | 0.2 | Close 20% of position at TP1 |
| atr_length | 50 | 50-day Wilder's ATR (NOT default 14) |
| risk_usd | 5000 | Risk per trade in USD |

### Session (NY)

| Param | Value | Description |
|-------|-------|-------------|
| ORB window | 09:30-09:35 | 5 minutes (one 5m candle) |
| Entry window | 09:35-15:00 | FVG signals accepted |
| Flat window | 15:50-16:00 | Force close all positions |
| stop_atr_pct | 9.0 | Stop distance = 9% of daily ATR |
| min_gap_atr_pct | 1.0 | Min FVG size = 1% of daily ATR |
| max_gap_points | 25.0 | Max FVG size = 25 GC points |
| qualifying_move_atr_pct | 10.0 | Min sweep below ORB low = 10% of ATR |

### Regime Sizing

| Param | Value | Description |
|-------|-------|-------------|
| regime_sizing | ON | Variable position size by macro regime |
| regime_rule | VIX < 18 AND DXY < SMA50 | Prior day close, no look-ahead |
| favorable_multiplier | 2x | Double position size in favorable regime |
| default_multiplier | 1x | Normal size otherwise |

## Signal Flow (Step by Step)

### Step 1: Daily ATR (previous day, no look-ahead)

Compute 50-period Wilder's ATR on daily bars, shifted back 1 day. Each intraday bar uses the **previous completed day's** ATR.

```
Wilder's ATR:
  seed = simple_mean(TR[1..50])
  atr[i] = (atr[i-1] * 49 + TR[i]) / 50

TR[i] = max(high[i] - low[i], abs(high[i] - prev_close), abs(low[i] - prev_close))
```

**Pine Script:**
```pine
daily_atr = request.security(syminfo.tickerid, "D", ta.atr(50)[1], lookahead=barmerge.lookahead_on)
```
The `[1]` + `lookahead_on` replicates "previous day's ATR."

### Step 2: ORB Levels (Opening Range)

Accumulate high/low during the ORB window (09:30-09:35). Since this is exactly one 5-minute candle:

```
orb_high = high of the 09:30 candle
orb_low  = low of the 09:30 candle
orb_ready = true starting from the 09:35 bar onward
```

On a new session day, reset ORB state. ORB levels are forward-filled for all bars after the ORB window closes.

### Step 3: Bearish FVG Detection (3-candle pattern)

Using bar-ago notation (`[0]` = current confirmed bar, `[2]` = 2 bars ago):

```
Bar layout:
  bar[2] = "before" candle (its low forms the FVG top)
  bar[1] = impulse candle (creates the gap)
  bar[0] = "after" candle (confirms gap exists)

Bearish FVG conditions (ALL must be true):
  low[2]  > high[0]        // gap exists: bar[2]'s low above current high
  low[2]  > low[1]         // bar[2]'s low above impulse low
  high[2] > high[0]        // bar[2]'s high above current high

FVG zone:
  fvg_top    = low[2]      // this is the "inversion level"
  fvg_bottom = high[0]
  gap_size   = fvg_top - fvg_bottom

Filters (ALL must pass):
  fvg_bottom < orb_low                           // FVG must sit BELOW ORB low
  gap_size >= (1.0 / 100) * daily_atr            // min 1% of ATR
  gap_size <= 25.0                                // max 25 GC points
  orb_ready == true                               // ORB window has closed
  bar is in entry window (09:35-15:00)            // valid signal time
```

When detected, store `inversion_level = fvg_top = low[2]` as a pending signal.

### Step 4: Session Running Low (for Qualifying Move Gate)

Track the running minimum low from session start:

```
On new session day:
  session_running_low = low

On each subsequent bar:
  session_running_low = min(session_running_low, low)
```

### Step 5: Qualifying Move Gate (v9 addition)

Before accepting an inversion trigger, verify the ORB low has been meaningfully swept:

```
qualifying_level = orb_low - (10.0 / 100.0) * daily_atr

Gate passes when: session_running_low <= qualifying_level
```

This ensures price has swept at least 10% of ATR below the ORB low at some point during the session. Filters out shallow/fake sweeps.

**Important**: If the gate fails on a given bar, the pending FVG stays alive. It can fire on a later bar once the gate passes (price sweeps deeper). The gate does NOT kill the signal — it just delays it.

### Step 6: Inversion Trigger (Entry Signal)

On each bar after a bearish FVG was detected, check:

```
if close > pending_inversion_level          // price closed above FVG top
   AND session_running_low <= qualifying_level  // sweep was deep enough
   AND no trade taken today                     // one trade per day
   AND still in entry window (09:35-15:00)
   AND same session day as the FVG
then:
   → LONG ENTRY at this bar's close
```

**The entry is at market (close of the inversion bar)**, not a limit order. The inversion bar itself is the entry bar.

Multiple bearish FVGs can be pending simultaneously on the same day. The first one to get invalidated (close above its `fvg_top`) while the QM gate is satisfied triggers the entry.

### Step 7: Trade Parameters

Given `entry = close` of the inversion bar:

```
stop_dist  = 0.09 * daily_atr              // 9% of ATR
stop_price = entry - stop_dist
risk_pts   = stop_dist                      // = entry - stop_price

tp1_price  = entry + 3.5 * risk_pts * 0.2  // = entry + 0.70 * risk_pts
tp2_price  = entry + 3.5 * risk_pts        // full R:R target
be_price   = entry                          // breakeven at entry (0 ticks offset)
```

### Step 8: Position Sizing

```
qty_raw   = risk_usd / (risk_pts * point_value)
          = 5000 / (risk_pts * 100)

qty       = floor(qty_raw)                  // round down to whole contracts
qty       = max(qty, 1)                     // minimum 1 contract

is_single = (qty == 1)

if not is_single:
    half_qty = floor(qty / 2)
    half_qty = max(half_qty, 1)
```

### Step 9: Regime Sizing Overlay

Before executing the trade, check macro regime using **prior day's close** (no look-ahead):

```
// Get prior day VIX and DXY closes
vix_prev = request.security("TVC:VIX", "D", close[1], lookahead=barmerge.lookahead_on)
dxy_prev = request.security("TVC:DXY", "D", close[1], lookahead=barmerge.lookahead_on)
dxy_sma50 = request.security("TVC:DXY", "D", ta.sma(close, 50)[1], lookahead=barmerge.lookahead_on)

favorable = vix_prev < 18 and dxy_prev < dxy_sma50

if favorable:
    qty = qty * 2                           // double position size
    half_qty = half_qty * 2                 // scale partial exit too
```

**Note on ticker symbols**: TradingView ticker symbols for VIX and DXY may differ. Common alternatives:
- VIX: `CBOE:VIX`, `TVC:VIX`, `VIX`
- DXY: `TVC:DXY`, `ICEEUR:DX1!`, `DXY`

Verify which symbols are available on your TradingView plan.

### Step 10: Exit Logic

Scan forward from the bar after entry. Track state: `tp1_hit = false`, `current_stop = stop_price`.

**Priority order within each bar (checked in this sequence):**

#### A. EOD Flat (overrides everything except stop)
```
if bar_time >= 15:50 AND low > current_stop:
    if tp1_hit:
        exit remaining at close → EXIT_TP1_EOD
    else:
        exit all at close → EXIT_EOD
```

#### B. Full Stop Loss (before TP1)
```
if low <= current_stop AND not tp1_hit:
    exit all at current_stop → EXIT_SL
    (this is a full loss = -1R)
```

#### C. Same-Bar Conflict: SL + TP1 on same bar
```
if low <= current_stop AND high >= tp1_price AND not tp1_hit:
    SL WINS (conservative assumption)
    exit all at current_stop → EXIT_SL
```

#### D. TP1 Partial Exit (multi-contract)
```
if high >= tp1_price AND not tp1_hit AND not is_single:
    close half_qty at tp1_price
    tp1_hit = true
    current_stop = be_price (= entry)
    remaining_qty = qty - half_qty
    continue scanning...
```

#### E. After TP1 — Breakeven Stop
```
if tp1_hit AND low <= current_stop (which is now be_price):
    exit remaining at be_price → EXIT_TP1_BE
```

#### F. After TP1 — TP2 Full Target
```
if tp1_hit AND high >= tp2_price:
    exit remaining at tp2_price → EXIT_TP1_TP2
```

#### G. Single Contract Path
```
if is_single AND high >= tp1_price AND not tp1_hit:
    tp1_hit = true
    current_stop = be_price
    (NO partial exit — just move stop to BE)

if is_single AND high >= tp2_price:
    exit all at tp2_price → EXIT_TP2_SINGLE
```

### Exit Types Summary

| Exit | Meaning | R-Multiple |
|------|---------|------------|
| EXIT_SL | Stopped before TP1 | -1.0R |
| EXIT_TP1_TP2 | Partial at TP1 + full target | +0.2 * 0.7R + 0.8 * 3.5R = +2.94R |
| EXIT_TP1_BE | Partial at TP1 + breakeven | +0.2 * 0.7R + ~0R = +0.14R |
| EXIT_TP1_EOD | Partial at TP1 + EOD close | variable |
| EXIT_EOD | EOD close, no TP1 | variable |
| EXIT_TP2_SINGLE | Single contract, full target | +3.5R |

(R-multiple calculations assume 20/80 split for multi-contract, approximate.)

## Rules

1. **One trade per session day**. Once a long fires, no further signals accepted that day.
2. **Long only**. Do not take shorts. GC shorts are structurally broken.
3. **All times in America/New_York (Eastern)**.
4. **All time windows are half-open [start, end)**. The bar at `start` is included, the bar at `end` is excluded.
5. **A bar's time is its open time**. The 09:30 bar represents 09:30-09:35.
6. **Multiple pending FVGs can exist**. Track all bearish FVGs in the entry window. First one to get its inversion level breached (with QM gate satisfied) wins.
7. **EOD flat is mandatory**. Any open position at 15:50 exits at market.

## Backtest Performance (2016-2026, 10 years)

### Base v9 (1x flat sizing)
- 250 trades, 56.8% WR, 74.7R, PF 1.70, Max DD -5.2R
- Walk-forward OOS: efficiency 0.82, stability 0.85
- Monte Carlo: 82.2% survival at 10R threshold (STRONG)
- **Status: GO** (all 5 pipeline phases pass)

### v9 Regime-Sized (Signal A alone, 2x VIX<18 + DXY<SMA50)
- 250 trades, 56.8% WR, 117.7R, PF 1.91, Max DD -6.5R (in-sample)
- WF OOS (7 folds, 2019-2026): 169 trades, 58.8R, -7.3R DD, Sharpe 3.314, WF eff 1.21

### Stacked v9+CleanAir (Signal A + Signal B, current production model)
- 349 trades (~32/yr), 57.6% WR, 146.0R, Max DD -8.3R, Sharpe 3.828 (in-sample)
- WF OOS (7 folds, 2019-2026): 229 trades, 89.1R, -10.0R DD, Sharpe 3.695, WF eff 1.13
- 2024-2025 hold-out: 70 trades, 41.7R, -4.0R DD, Sharpe 5.087
- **DB**: `bt-gc-ny-inv-longs-stacked-v9-cleanair-2365b0`

## Common Pine Script Pitfalls

1. **ATR length**: Use 50, not the default 14. `ta.atr(50)`.
2. **ATR look-ahead**: Must use previous day's ATR. Use `[1]` shift with `lookahead_on` in `request.security`.
3. **FVG lookback**: The FVG pattern references `[2]` (2 bars ago). Make sure you have enough historical bars.
4. **Pending FVG list**: Pine Script doesn't have mutable arrays pre-v5. Use `var` arrays and manage manually. Each pending FVG needs: `inversion_level`, `fvg_bar_index`, `session_day`.
5. **Qualifying move gate**: This gate does NOT discard the pending FVG on failure. It stays pending until the gate passes or the session ends. This is different from a simple filter.
6. **Partial exits**: TradingView `strategy.*` functions support `qty` parameter for partial closes. Use `strategy.close(qty=half_qty)` for TP1.
7. **Breakeven stop**: After TP1, update the stop to `entry`. Use `strategy.exit` with a new stop level.
8. **Session-day reset**: Clear all pending FVGs, reset `session_running_low`, reset `orb_ready`, reset `trade_taken_today` flag on each new session day.
9. **Bar magnifier**: The Python backtester uses 1-minute data within 5-minute bars for precise fill detection. TradingView strategies natively support this via `strategy(fill_orders_on_standard_ohlc=false)` or by running on 1-minute timeframe. Consider using `calc_on_every_tick=true` or running on 1m bars with manual 5m aggregation for accuracy.
10. **Regime data symbols**: VIX and DXY may have different ticker symbols across TradingView data providers. Test that `request.security` returns valid data before going live.

---

## Signal B — Clean Air No-ORB (Stacked Component)

This section documents the second signal in the stacked strategy. It runs independently of Signal A on the same instrument and session.

### Concept

Remove the ORB as a reference entirely. Instead of requiring price to sweep the ORB low, require price to make a large liquidity sweep (100% ATR) downward from the session high, then invert via a bearish FVG anywhere in the session. The key quality filter is "clean air": the sweep must happen into empty space — no prior bullish FVG zone from the past N trading days sits below (which would absorb the sweep and reduce its validity as a clean liquidity grab).

### Parameters

| Param | Value | Description |
|-------|-------|-------------|
| rr | 5.0 | Higher R:R — sweeps run farther after 100% ATR move |
| tp1_ratio | 0.2 | Close 20% at TP1 |
| atr_length | 50 | Same 50-period Wilder's ATR |
| risk_usd | 5000 | Same risk per trade |
| stop_atr_pct | 12.0 | Wider stop: 12% of ATR |
| min_gap_atr_pct | 1.0 | Min FVG size = 1% ATR |
| max_gap_points | 25.0 | Max FVG size = 25 points |
| qualifying_move_atr_pct | 100.0 | Min sweep = 100% of ATR (large move) |
| entry_start | 09:35 | Same as Signal A |
| entry_end | 16:45 | Extended — runs all day |
| flat_start | 16:45 | Immediately flat |
| flat_end | 16:50 | Close window |
| clean_air_n | 1 | Look back 1 prior trading day for FVG zones |

### Signal B Flow (Step by Step)

#### Step 1: Daily ATR
Same as Signal A — 50-period Wilder's ATR from previous day's close.

#### Step 2: Session Running High (for QM gate)
Track the running maximum high from session open (no ORB needed):

```
On new session day:
  session_running_high = high

On each subsequent bar:
  session_running_high = max(session_running_high, high)
```

#### Step 3: Bearish FVG Detection (no ORB filter)
Same 3-candle pattern as Signal A but WITHOUT the `fvg_bottom < orb_low` filter:

```
Bearish FVG conditions (ALL must be true):
  low[2]  > high[0]        // gap exists
  low[2]  > low[1]
  high[2] > high[0]

FVG zone:
  fvg_top    = low[2]      // inversion level
  fvg_bottom = high[0]
  gap_size   = fvg_top - fvg_bottom

Filters:
  gap_size >= (1.0 / 100) * daily_atr    // min 1% ATR
  gap_size <= 25.0                        // max 25 points
  bar is in entry window (09:35-16:45)   // NOTE: extended window vs Signal A
  // NO orb_low check — FVG can appear anywhere in session
```

#### Step 4: Qualifying Move Gate (100% ATR sweep)
Before accepting an inversion trigger:

```
qualifying_level = session_running_high - (100.0 / 100.0) * daily_atr
                 = session_running_high - daily_atr

Gate passes when: session_running_low <= qualifying_level
```

This requires price to have dropped at least a full ATR from the session high at some point — a large liquidity sweep regardless of where the ORB is.

#### Step 5: Inversion Trigger
Same logic as Signal A, different window:

```
if close > pending_inversion_level
   AND session_running_low <= qualifying_level
   AND no Signal-B trade taken today
   AND still in entry window (09:35-16:45)
then:
   → LONG ENTRY at this bar's close
```

#### Step 6: Trade Parameters

```
stop_dist  = 0.12 * daily_atr              // 12% of ATR (wider than Signal A)
stop_price = entry - stop_dist
risk_pts   = stop_dist

tp1_price  = entry + 5.0 * risk_pts * 0.2  // = entry + 1.0 * risk_pts
tp2_price  = entry + 5.0 * risk_pts         // full 5R target
be_price   = entry                          // 0 ticks offset
```

#### Step 7: Position Sizing
Same as Signal A — `floor(5000 / (risk_pts * 100))`, minimum 1 contract. **No regime sizing overlay** — Signal B uses flat 1x sizing only.

#### Step 8: Exit Logic
Same exit priority order as Signal A (EOD flat overrides, SL priority over TP1 on same bar, partial at TP1, BE stop, TP2). EOD flat at **16:45** (not 15:50).

### Clean Air Filter

This is the key quality gate applied after a Signal B trade fires. In Pine Script, this must be pre-computed at the start of each trading day.

#### What is a bullish FVG zone?
3-candle bullish pattern detected on 5m bars:
```
Bullish FVG conditions (ALL must be true):
  high[2] < low[0]         // gap exists: bar[2]'s high below current low
  high[2] < high[1]
  low[2]  < low[0]

Zone:
  fvg_bottom = high[2]     // bottom of gap
  fvg_top    = low[0]      // top of gap (the key level)
```

#### Clean air check (N=1 lookback)
At the start of each session day, look at all bullish FVGs that formed on the **prior trading day**. Then, after a Signal B inversion trigger fires, check:

```
session_low_so_far = running minimum low since session open

clean_air = (no prior bullish FVGs exist from yesterday)
            OR
            (session_low_so_far > every prior_fvg_top from yesterday)
```

If `clean_air` is true: **take the trade**. If false: **skip it** (session low has dipped into or below a prior bullish FVG zone — the sweep was absorbed by known order flow, not clean air).

**Pine implementation note**: Store yesterday's bullish FVG tops in a `var float[] prev_fvg_tops` array. Reset at session open with the prior day's zones. The check runs at trade trigger time, not bar-by-bar.

```pine
// At new session day start:
array.clear(prev_fvg_tops)
// Copy yesterday's bullish FVG tops into prev_fvg_tops

// At Signal B trigger:
session_low = ta.lowest(low, bars_since_session_open)
clean_air = true
for i = 0 to array.size(prev_fvg_tops) - 1
    if session_low <= array.get(prev_fvg_tops, i)
        clean_air := false
        break
if clean_air
    // execute Signal B trade
```

---

## Stacked Strategy: Combining Signal A and Signal B

### Dedup Rule
If Signal A (v9) fires on the same calendar day as Signal B (clean air), **Signal A wins**. Do not take Signal B on a day when Signal A has already traded.

In Pine Script: maintain a single `trade_taken_today` flag per session day. Both signals check this before firing. Signal A sets it first (entry window 09:35-15:00); Signal B would be suppressed if A already fired.

Note: ~4.8% of trading days have both signals fire. In those cases, Signal A's trade is kept.

### Session Day Reset
At the start of each new session day, reset ALL of the following:
- `orb_high`, `orb_low`, `orb_ready` (Signal A)
- `session_running_low`, `session_running_high`
- All pending bearish FVG lists (Signal A and Signal B separately)
- `trade_taken_today`
- `prev_fvg_tops` populated with prior day's bullish FVG zones (for clean air check)

### Combined Exit Rules
The two signals have different exit windows:
- Signal A: flat at 15:50
- Signal B: flat at 16:45

Track which signal opened the trade and apply the corresponding flat time.

### Combined Performance (2016-2026)
| Signal | Trades | Net R | Max DD | Sharpe |
|--------|--------|-------|--------|--------|
| Signal A only (v9 regime-sized) | 250 | 117.7R | -6.5R | — |
| Signal B only (clean air N=1) | 121 | 59.5R | -6.5R | 4.978 |
| Stacked (A+B, dedup) | 349 | 146.0R | -8.3R | 3.828 |

WF OOS (2019-2026): 229 trades, 89.1R, -10.0R DD, Sharpe 3.695, WF eff 1.13.
