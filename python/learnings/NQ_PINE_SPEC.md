# NQ NY Long Continuation — Pine Script Specification

Self-contained spec for implementing the NQ NY long continuation strategy in Pine Script v6.

**Accepted config**: WF mode params from robust pipeline (CONDITIONAL verdict, 4/5 phases pass).

## Strategy Overview

**Instrument**: NQ (Nasdaq-100 Futures, CME)
**Concept**: After the 20-minute opening range forms, detect a bullish Fair Value Gap (FVG) above the ORB high. Place a limit order at the FVG top (retest level). When price retraces into the gap, the limit fills and we ride the continuation move higher.
**Direction**: Long only. Shorts are structurally unprofitable on NQ across all strategy types (continuation, reversal, inversion).

## Instrument Details

| Field | Value |
|-------|-------|
| Symbol | NQ |
| Point value | $20/point |
| Min tick | 0.25 |
| Commission | $0.05/contract/side |
| Timezone | America/New_York |

## Parameters

### Strategy

| Param | Value | Description |
|-------|-------|-------------|
| strategy | continuation | Bullish FVG above ORB high → long |
| direction | long only | Only take longs |
| rr | 2.0 | Risk-reward ratio for TP2 |
| tp1_ratio | 0.6 | Close 60% of position at TP1 (see note) |
| atr_length | 14 | 14-day Wilder's ATR |
| risk_usd | 5000 | Risk per trade in USD |

**Note on tp1_ratio**: `tp1_ratio` defines how far TP1 is as a fraction of the full R:R target. TP1 price = entry + rr × risk_pts × tp1_ratio = entry + 2.0 × risk × 0.6 = entry + 1.2R. It does NOT mean "close 60% of qty." Qty split is always 50/50 (half at TP1, half rides to TP2/BE/EOD).

### Session (NY)

| Param | Value | Description |
|-------|-------|-------------|
| ORB window | 09:30–09:50 | 20 minutes (four 5m candles) |
| Entry window | 09:50–15:00 | FVG signals accepted + limit orders active |
| Flat window | 15:50–16:00 | Force close all positions |
| stop_atr_pct | 9.0 | Stop distance = 9% of daily ATR |
| min_gap_atr_pct | 3.0 | Min FVG size = 3% of daily ATR |
| max_gap_points | 100.0 | Max FVG size = 100 NQ points |

## Signal Flow (Step by Step)

### Step 1: Daily ATR (previous day, no look-ahead)

Compute 14-period Wilder's ATR on daily bars, shifted back 1 day. Each intraday bar uses the **previous completed day's** ATR.

```
Wilder's ATR:
  seed = simple_mean(TR[1..14])
  atr[i] = (atr[i-1] * 13 + TR[i]) / 14

TR[i] = max(high[i] - low[i], abs(high[i] - prev_close), abs(low[i] - prev_close))
```

**Pine Script:**
```pine
daily_atr = request.security(syminfo.tickerid, "D", ta.atr(14)[1], lookahead=barmerge.lookahead_on)
```
The `[1]` + `lookahead_on` replicates "previous day's ATR."

### Step 2: ORB Levels (Opening Range)

Accumulate high/low during the ORB window (09:30–09:50). This spans four 5-minute candles:

```
On each bar where 09:30 <= bar_time < 09:50:
  orb_high = max(orb_high, high)
  orb_low  = min(orb_low, low)

orb_ready = true starting from the 09:50 bar onward
```

On a new session day, reset ORB state. ORB levels are forward-filled for all bars after the ORB window closes.

### Step 3: Bullish FVG Detection (3-candle pattern)

Using bar-ago notation (`[0]` = current confirmed bar, `[2]` = 2 bars ago):

```
Bar layout:
  bar[2] = "before" candle (its high forms the FVG bottom)
  bar[1] = impulse candle (creates the gap)
  bar[0] = "after" candle (confirms gap exists; its low is the FVG top)

Bullish FVG conditions (ALL must be true):
  high[2] < low[0]         // gap exists: bar[2]'s high below current low
  high[2] < high[1]        // bar[2]'s high below impulse high
  low[2]  < low[0]         // bar[2]'s low below current low

FVG zone:
  fvg_top    = low[0]      // current bar's low = top of the gap
  fvg_bottom = high[2]     // bar[2]'s high = bottom of the gap
  gap_size   = fvg_top - fvg_bottom

Filters (ALL must pass):
  fvg_top > orb_high                           // FVG must sit ABOVE ORB high
  gap_size >= (3.0 / 100) * daily_atr          // min 3% of ATR
  gap_size <= 100.0                             // max 100 NQ points
  orb_ready == true                             // ORB window has closed
  bar is in entry window (09:50–15:00)          // valid signal time
```

When detected, store as a **pending limit order**:
- `entry_level = fvg_top = low[0]` (top of the gap = retest level)
- The limit order is a **buy limit** at `entry_level` — price must come DOWN to this level to fill

### Step 4: Limit Order Fill Scan

Starting from the bar AFTER the FVG signal bar, scan forward for a fill:

```
for each bar from (signal_bar + 1) to entry_end:
  if low <= entry_level:
    FILLED at entry_level
    break

if entry_end reached without fill:
  EXIT_NO_FILL (discard)
```

**Important**: The entry is a **limit order**, not a market order. The bar after the FVG detects the setup, and price must retrace to the FVG top for the order to fill. This is fundamentally different from the GC inversion strategy which enters at market on close.

Only ONE pending signal per session-day direction. If a bullish FVG is detected, it becomes the pending long signal. If another bullish FVG appears before the first fills, the **first one detected** retains priority.

### Step 5: Trade Parameters

Given `entry = entry_level` (the FVG top where the limit filled):

```
stop_dist  = 0.09 * daily_atr              // 9% of ATR
stop_price = entry - stop_dist
risk_pts   = stop_dist                      // = entry - stop_price

tp1_price  = entry + 2.0 * risk_pts * 0.6  // = entry + 1.2 * risk_pts
tp2_price  = entry + 2.0 * risk_pts        // = entry + 2.0 * risk_pts (full R:R)
be_price   = entry                          // breakeven at entry (0 offset)
```

### Step 6: Position Sizing

```
qty_raw   = risk_usd / (risk_pts * point_value)
          = 5000 / (risk_pts * 20)

qty       = floor(qty_raw)                  // round down to whole contracts
qty       = max(qty, 1)                     // minimum 1 contract

is_single = (qty == 1)

if not is_single:
    half_qty = floor(qty / 2)
    half_qty = max(half_qty, 1)
```

### Step 7: Exit Logic

Scan forward from the bar after fill. Track state: `tp1_hit = false`, `current_stop = stop_price`.

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
| EXIT_NO_FILL | Limit never triggered | 0 (no trade) |
| EXIT_SL | Stopped before TP1 | -1.0R |
| EXIT_TP1_TP2 | Partial at TP1 + full target | +0.5 × 1.2R + 0.5 × 2.0R = +1.6R |
| EXIT_TP1_BE | Partial at TP1 + breakeven | +0.5 × 1.2R + ~0R = +0.6R |
| EXIT_TP1_EOD | Partial at TP1 + EOD close | variable |
| EXIT_EOD | EOD close, no TP1 | variable |
| EXIT_TP2_SINGLE | Single contract, full target | +2.0R |

(R-multiple calculations assume 50/50 split for multi-contract.)

## Rules

1. **One trade per session day**. Once a long fills, no further signals accepted that day. If both a bullish and bearish FVG exist, the first to fill wins (but since we're long-only, only bullish FVGs produce signals).
2. **Long only**. Do not take shorts. NQ shorts are structurally unprofitable.
3. **All times in America/New_York (Eastern)**.
4. **All time windows are half-open [start, end)**. The bar at `start` is included, the bar at `end` is excluded.
5. **A bar's time is its open time**. The 09:30 bar represents 09:30–09:35.
6. **One pending signal per direction**. The first bullish FVG detected after the ORB closes becomes the pending long setup. It stays pending until filled or entry window ends.
7. **Entry starts one bar after signal**. The FVG is detected on bar[0] (the "after" candle). The limit order becomes active on the NEXT bar.
8. **EOD flat is mandatory**. Any open position at 15:50 exits at market.

## Backtest Performance

### In-Sample (2015–2026, rr=2.25 tp1=0.7 — optimization winner)
- 1167 trades, 46.1% WR, PF 1.30, 182.0R (16.5 R/yr), DD -10.6R, Calmar 17.17
- All years positive except 2023 (-1.7R)

### Walk-Forward OOS (36m IS / 12m OOS / 12m step, 6 folds)
- 661 trades, 46.7% WR, PF 1.16, 54.3R (~9 R/yr), Sharpe 1.09, DD -12.3R
- WF efficiency: 0.45 (borderline, threshold 0.50)
- Stability: 0.83 (high) — params converge across folds
- Mode params: rr=2.0, tp1=0.6, stop=9.0, gap=3.0

### Hold-Out (2025+, mode params)
- 105 trades, 58.1% WR, PF 1.79, Sharpe 3.97, +30.1R, DD -5.0R

### Monte Carlo (2000 bootstrap sims on OOS trades)
- 100% survival at 25R ruin threshold
- DD p50: -20.3R, DD p95: -37.7R
- Ruin probability at 25R: 28.8%

### Pipeline Verdict: CONDITIONAL
- Phases 1, 4, 5: PASS
- Phase 2: FAIL (borderline — 0.45 vs 0.50, driven by one bad fold in 2023)
- Phase 3: FAIL (annual R target 24R unrealistic for ~9 R/yr OOS edge)

## Common Pine Script Pitfalls

1. **ATR length**: Use 14, not 50 (GC uses 50 — NQ is different).
2. **ATR look-ahead**: Must use previous day's ATR. Use `[1]` shift with `lookahead_on` in `request.security`.
3. **ORB window is 20 minutes, not 5**. Accumulate high/low across bars from 09:30 to 09:50 (four 5m candles). This is different from GC which uses a single candle.
4. **Entry is a LIMIT order, not market**. The FVG detection bar sets up a pending buy limit at the FVG top. Price must retrace into the gap to fill. This is the key difference from the GC inversion strategy which enters at market on close of the inversion bar.
5. **FVG must be ABOVE ORB high**. For continuation longs, the bullish FVG's top (`low[0]`) must be above the ORB high. This ensures the gap is in the continuation direction (above the range).
6. **Entry starts one bar after FVG**. The FVG is confirmed on bar[0]. The limit order goes active on the NEXT bar. The signal bar itself cannot fill the order.
7. **Partial exits**: TradingView `strategy.*` functions support `qty` parameter for partial closes. Use `strategy.close(qty=half_qty)` for TP1. Half qty = floor(qty / 2), minimum 1.
8. **Breakeven stop**: After TP1, update the stop to `entry` (0 offset). Use `strategy.exit` with a new stop level.
9. **Session-day reset**: Clear pending FVG, reset ORB state, reset `trade_taken_today` flag on each new session day.
10. **Bar magnifier**: The Python backtester uses 1-minute data within 5-minute bars for precise fill detection. TradingView strategies natively support this via `strategy(fill_orders_on_standard_ohlc=false)` or by running on 1-minute timeframe with manual 5m aggregation.
11. **Gap filter is 3%, not 1%**. NQ uses `min_gap_atr_pct=3.0` (more aggressive filter than GC's 1.0%). This is the key drawdown reducer — it skips small, unreliable gaps.
12. **Max gap is 100 NQ points**. At $20/point, this is $2000. Gaps wider than this are filtered out.
