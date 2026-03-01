# NQ Combined — Asia + NY Continuation — Pine Script Specification

Self-contained spec for implementing both NQ continuation strategies (NY R20 + Asia R9 Restart) in a single Pine Script v6 indicator/strategy. Both strategies are **GO** from the robust pipeline.

**Single-script rationale**: Same instrument (NQ), sessions never overlap (Asia 20:00-04:00 ET, NY 09:30-15:50 ET -- 5.5-hour gap between Asia flat and NY open). TradingView's single-position model works since both sessions cannot hold positions simultaneously.

**Supersedes**: `NQ_PINE_SPEC.md` (old config: rr=2.0 / tp1=0.6 / long-only / stop=9.0% -- CONDITIONAL verdict, now replaced by R20 Final with both directions, rr=2.625, stop=8.75%).

**Combined performance** (2016-2026): ~2,664 trades, ~388.7R total (~38.9 R/yr), 0 negative full years across both sessions.

---

## Instrument Details

| Field | Value |
|-------|-------|
| Symbol | NQ (e.g. `CME_MINI:NQ1!`) |
| Point value | $20/point |
| Min tick | 0.25 |
| Commission | $0.05/contract/side |
| Timezone | America/New_York |

---

## Combined Parameter Tables

### Strategy Parameters

| Param | NY (R20) | Asia (R9 Restart) |
|-------|----------|-------------------|
| strategy | continuation | continuation |
| direction | both | long only |
| rr | 2.625 | 3.0 |
| tp1_ratio | 0.3 | 0.6 |
| atr_length | 12 | 5 |
| risk_usd | 5000 | 5000 |
| impulse_close_filter | **OFF** | **ON** |
| DOW exclusion | none | **Tuesday** |

### Session Timing

| Param | NY (R20) | Asia (R9 Restart) |
|-------|----------|-------------------|
| ORB window | 09:30-09:50 (20m, 4 bars) | 20:00-20:15 (15m, 3 bars) |
| Entry window | 09:50-15:30 | 20:15-22:30 |
| Flat window | 15:50-16:00 | 04:00-07:00 |
| stop_atr_pct | 8.75% | 4.0% |
| min_gap_atr_pct | 2.25% | 0.90% |
| max_gap_points | 100 | 75 |
| max_gap_atr_pct | 0 (disabled) | 0 (disabled) |

---

## Common Building Blocks

### 4a. ATR Computation (Daily, Previous Day)

Both sessions require daily ATR but with **different periods**. Two `request.security` calls are needed:

```pine
// NY uses 12-period ATR
daily_atr_12 = request.security(syminfo.tickerid, "D", ta.atr(12)[1], lookahead=barmerge.lookahead_on)

// Asia uses 5-period ATR
daily_atr_5  = request.security(syminfo.tickerid, "D", ta.atr(5)[1], lookahead=barmerge.lookahead_on)
```

The `[1]` shift combined with `lookahead_on` means "the ATR as of yesterday's close" -- the same value available to a live trader before today's session opens. This eliminates look-ahead bias.

### 4b. FVG Detection (3-Candle Pattern)

**Bar notation** -- all on the confirmed (closed) bar timeframe (5m):
- `bar[0]` = current (just closed) bar -- the "after" candle
- `bar[1]` = 1 bar ago -- the impulse candle
- `bar[2]` = 2 bars ago -- the "before" candle

#### Bullish FVG (for long continuation)

```pine
bullish_fvg = high[2] < low[0] and high[2] < high[1] and low[2] < low[0]

fvg_top    = low[0]     // entry level for buy limit (top of gap)
fvg_bottom = high[2]    // bottom of gap
gap_size   = fvg_top - fvg_bottom
```

#### Bearish FVG (for short continuation)

```pine
bearish_fvg = low[2] > high[0] and low[2] > low[1] and high[2] > high[0]

fvg_bottom = high[0]    // entry level for sell limit (bottom of gap)
fvg_top    = low[2]     // top of gap
gap_size   = fvg_top - fvg_bottom
```

#### ORB Directional Filter: Standard vs ICF

**Standard (NY -- ICF OFF):**
```pine
// Bullish FVG must be above ORB high
long_orb_ok  = fvg_top > orb_high

// Bearish FVG must be below ORB low
short_orb_ok = fvg_bottom < orb_low
```

**ICF-Relaxed (Asia -- ICF ON):**

When `impulse_close_filter = true`, the ORB directional check is relaxed: even if the FVG zone itself does not clear the ORB, the signal is accepted if bar[1]'s close (the impulse candle's close) was beyond the ORB range.

```pine
// close[1] = close of bar[1] (the impulse candle)
long_orb_ok  = (fvg_top > orb_high) or (close[1] > orb_high)
short_orb_ok = (fvg_bottom < orb_low) or (close[1] < orb_low)
```

Since Asia is long-only, only `long_orb_ok` is relevant for Asia signals.

#### Gap Size Filters

```pine
// NY gap filters (using daily_atr_12)
ny_min_gap = 0.0225 * daily_atr_12
ny_max_gap = 100.0  // points

ny_gap_valid = gap_size >= ny_min_gap and gap_size <= ny_max_gap

// Asia gap filters (using daily_atr_5)
asia_min_gap = 0.009 * daily_atr_5
asia_max_gap = 75.0  // points

asia_gap_valid = gap_size >= asia_min_gap and gap_size <= asia_max_gap
```

Note: `max_gap_atr_pct = 0` for both sessions (disabled). Only point-based maximum and ATR-pct minimum apply.

### 4c. Exit Logic State Machine

All exit logic is shared between sessions. The same priority order applies regardless of which session opened the trade. Inputs differ (flat_start, rr, tp1_ratio) but the structure is identical.

```
State: tp1_hit = false, current_stop = initial_stop

Each bar after fill, check in this priority order:

A. EOD Flat
   if bar_time >= flat_start AND position not stopped:
       if tp1_hit -> EXIT_TP1_EOD (close remaining at close price)
       else       -> EXIT_EOD     (close all at close price)

B. Stop Loss (before TP1)
   if (long: low <= current_stop) or (short: high >= current_stop):
       if not tp1_hit -> EXIT_SL (full -1R loss)

C. Same-bar conflict: SL + TP1 on same bar
   if stop triggered AND tp1 level reached AND not tp1_hit:
       SL WINS -> EXIT_SL

D. TP1 Partial (multi-contract only)
   if (long: high >= tp1_price) or (short: low <= tp1_price):
       if not tp1_hit and qty > 1:
           close floor(qty/2) at tp1_price
           tp1_hit = true
           current_stop = entry  // move stop to breakeven
           remaining = qty - floor(qty/2)

E. After TP1 -- Breakeven Stop
   if tp1_hit:
       if (long: low <= current_stop) or (short: high >= current_stop):
           EXIT_TP1_BE (exit at entry price)

F. After TP1 -- TP2 Full Target
   if tp1_hit:
       if (long: high >= tp2_price) or (short: low <= tp2_price):
           EXIT_TP1_TP2

G. Single Contract Path
   if qty == 1:
       if tp1 reached: tp1_hit = true, current_stop = entry (no partial exit)
       if tp2 reached: EXIT_TP2_SINGLE
```

### 4d. Position Sizing

```pine
risk_pts = math.abs(entry - stop_price)
qty_raw  = risk_usd / (risk_pts * point_value)      // point_value = 20 for NQ
qty      = math.max(math.floor(qty_raw), 1)
half_qty = math.max(math.floor(qty / 2), 1)
is_single = (qty == 1)
```

Both sessions risk $5,000/trade independently.

---

## Session 1 -- NY Continuation (Both Directions)

**DB**: `bt-nq-ny-r20-final-fa2e40`

### Session Day Definition

Calendar date in ET. A new session day starts when bar time first reaches 09:30 ET. Simple (no cross-midnight).

### Step-by-Step Signal Flow

#### Step 1: Session Clock

Reset all NY state at 09:30:
- `ny_orb_high`, `ny_orb_low`, `ny_orb_ready`
- `ny_long_pending`, `ny_short_pending`
- `ny_trade_taken_today`

#### Step 2: ORB (09:30-09:50)

Four 5m candles: the 09:30, 09:35, 09:40, and 09:45 bars.

```pine
if bar_time >= 09:30 and bar_time < 09:50
    ny_orb_high := math.max(ny_orb_high, high)
    ny_orb_low  := math.min(ny_orb_low,  low)

ny_orb_ready = bar_time >= 09:50
```

#### Step 3: FVG Detection (both directions, NO ICF)

During entry window (09:50-15:30), detect bullish and bearish FVGs using **standard ORB check** (ICF is OFF for NY):

**Bullish FVG -> Long:**
```pine
if bullish_fvg and ny_orb_ready
    and fvg_top > ny_orb_high                          // above ORB (standard check)
    and gap_size >= 0.0225 * daily_atr_12              // min 2.25% of ATR-12
    and gap_size <= 100.0                              // max 100 NQ points
    -> store ny_pending_long: entry_level = fvg_top
```

**Bearish FVG -> Short:**
```pine
if bearish_fvg and ny_orb_ready
    and fvg_bottom < ny_orb_low                        // below ORB (standard check)
    and gap_size >= 0.0225 * daily_atr_12              // min 2.25% of ATR-12
    and gap_size <= 100.0                              // max 100 NQ points
    -> store ny_pending_short: entry_level = fvg_bottom
```

First FVG per direction detected retains priority. One signal per direction per session day.

#### Step 4: Limit Order Fill

Starting the bar AFTER the signal bar:

```pine
// Long: price must come DOWN to entry_level
if ny_long_pending and low <= ny_entry_level -> FILL LONG at ny_entry_level

// Short: price must go UP to entry_level
if ny_short_pending and high >= ny_entry_level -> FILL SHORT at ny_entry_level
```

One-trade-per-day enforced: once either direction fills, the other is cancelled.

#### Step 5: Trade Parameters

**Long:**
```
stop_dist  = 0.0875 * daily_atr_12              // 8.75% of ATR-12
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 2.625 * risk_pts * 0.3     // = entry + 0.7875 * risk_pts
tp2_price  = entry + 2.625 * risk_pts
be_price   = entry
```

**Short (mirror):**
```
stop_dist  = 0.0875 * daily_atr_12
stop_level = entry + stop_dist
risk_pts   = stop_dist
tp1_price  = entry - 2.625 * risk_pts * 0.3
tp2_price  = entry - 2.625 * risk_pts
be_price   = entry
```

**Note**: The stop is ATR-computed -- `stop = entry +/- 0.0875 * daily_atr_12`. The Python simulator always uses `stop_dist = (stop_atr_pct / 100) * ATR` as the actual stop level, NOT the structural `low[2]`/`high[2]`. Pine Script must match this.

#### Step 6: Exit

Apply shared exit logic (Section 4c) with `flat_start = 15:50 ET`.

---

## Session 2 -- Asia Continuation (Long Only)

**DB**: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`

### Session Day Definition

Asia session crosses midnight ET. A **session day** is defined by the DATE of the **ORB open** (20:00 bar). The flat at 04:00 closes trades from the session that opened at 20:00 the prior calendar day.

```pine
new_asia_session = (hour == 20 and minute == 0) and not (hour[1] == 20 and minute[1] == 0)
```

### Tuesday Gate

If the 20:00 bar falls on a Tuesday, skip the entire session. No ORB, no signals, no trades for that session day.

Pine Script: `dayofweek == dayofweek.tuesday` (value 3). Note: Pine Script's `dayofweek` uses 1=Sunday, 2=Monday, 3=Tuesday, 4=Wednesday, 5=Thursday, 6=Friday, 7=Saturday.

```pine
is_tuesday = dayofweek == dayofweek.tuesday  // == 3
```

Verify against a known calendar date when implementing.

### Step-by-Step Signal Flow

#### Step 1: Session Clock

Reset all Asia state at 20:00 (when `new_asia_session` fires). Check Tuesday gate -- if Tuesday, mark session as skipped.

Reset:
- `asia_orb_high`, `asia_orb_low`, `asia_orb_ready`
- `asia_long_pending`
- `asia_trade_taken_today`
- `asia_session_skipped` (set to true if Tuesday)

#### Step 2: ORB (20:00-20:15)

Three 5m candles: the 20:00, 20:05, and 20:10 bars.

```pine
if bar_time >= 20:00 and bar_time < 20:15 and not asia_session_skipped
    asia_orb_high := math.max(asia_orb_high, high)
    asia_orb_low  := math.min(asia_orb_low,  low)

asia_orb_ready = bar_time >= 20:15
```

#### Step 3: Bullish FVG Detection (LONG ONLY, ICF ON)

During entry window (20:15-22:30), detect only bullish FVGs using the **ICF-relaxed ORB check**:

```pine
if bullish_fvg and asia_orb_ready and not asia_session_skipped and not asia_trade_taken_today
    and ((fvg_top > asia_orb_high) or (close[1] > asia_orb_high))   // ICF relaxed check
    and gap_size >= 0.009 * daily_atr_5                              // min 0.90% of ATR-5
    and gap_size <= 75.0                                             // max 75 NQ points
    -> store asia_pending_long: entry_level = fvg_top
```

Only bullish FVGs. First detected retains priority. One signal per session day.

#### Step 4: Limit Order Fill

Starting the bar AFTER the signal bar:

```pine
if asia_long_pending and low <= asia_entry_level -> FILL LONG at asia_entry_level
```

One trade per session day.

#### Step 5: Trade Parameters

```
stop_dist  = 0.04 * daily_atr_5                 // 4.0% of ATR-5
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 3.0 * risk_pts * 0.6       // = entry + 1.8 * risk_pts
tp2_price  = entry + 3.0 * risk_pts
be_price   = entry
```

**Note**: The stop is ATR-computed -- `stop = entry - 0.04 * daily_atr_5`. NOT the structural `low[2]`. Pine Script must match this.

#### Step 6: Exit

Apply shared exit logic (Section 4c) with `flat_start = 04:00 ET`.

---

## Session Interaction Rules

1. **Independent state machines**: NY and Asia maintain completely separate state (ORB levels, pending signals, trade flags, exit tracking).
2. **No time overlap**: Asia flat at 04:00 ET, NY start at 09:30 ET -- 5.5-hour gap. Sessions never hold positions simultaneously.
3. **TradingView single-position model**: Works correctly since positions never overlap. No need for multi-position workarounds.
4. **Defensive check**: If Asia position is somehow still open at NY start (e.g., code bug), suppress NY signals for that day. Implement as: `if strategy.position_size != 0 and ny_orb_ready -> skip NY signals`.
5. **Independent risk**: Each session risks $5,000/trade independently. On a day where both sessions trade, combined exposure is sequential (never simultaneous).

---

## Exit Types & R-Multiples

### NY (rr=2.625, tp1_ratio=0.3)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 * (2.625 * 0.3) + 0.5 * 2.625 = 0.39375 + 1.3125 = **+1.706R** |
| EXIT_TP1_BE | 0.5 * (2.625 * 0.3) = **+0.394R** |
| EXIT_TP2_SINGLE | **+2.625R** |
| EXIT_TP1_EOD | 0.394R + variable |
| EXIT_EOD | variable |

### Asia (rr=3.0, tp1_ratio=0.6)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 * (3.0 * 0.6) + 0.5 * 3.0 = 0.9 + 1.5 = **+2.4R** |
| EXIT_TP1_BE | 0.5 * (3.0 * 0.6) = **+0.9R** |
| EXIT_TP2_SINGLE | **+3.0R** |
| EXIT_TP1_EOD | 0.9R + variable |
| EXIT_EOD | variable |

---

## Backtest Performance

### NY R20 -- Full History (2016-2026)

| Metric | Value |
|--------|-------|
| Trades | 1,894 |
| Win Rate | 59.9% |
| Profit Factor | 1.28 |
| Net R | 212.5 |
| Avg Annual R | 21.3 |
| Max DD | -13.0R |
| Calmar | 16.36 |
| Sharpe | 1.72 |
| Negative years | 0 |

**R by year**: 2016:+10 | 2017:+39 | 2018:+7 | 2019:+31 | 2020:+26 | 2021:+29 | 2022:+9 | 2023:+4 | 2024:+44 | 2025:+10 | 2026:+3

**Fixed-param Walk-Forward** (6 folds, OOS 2019-2024):

| Fold | OOS Period | Trades | Sharpe | R | DD |
|------|-----------|--------|--------|---|-----|
| 1 | 2019 | 182 | 2.52 | +30.7 | -10.9 |
| 2 | 2020 | 174 | 2.27 | +26.0 | -7.0 |
| 3 | 2021 | 189 | 2.29 | +28.7 | -6.3 |
| 4 | 2022 | 194 | 0.72 | +9.1 | -12.6 |
| 5 | 2023 | 207 | 0.29 | +3.9 | -11.1 |
| 6 | 2024 | 197 | 3.38 | +44.4 | -6.3 |

- **Combined OOS**: 1,143 trades, 60.0% WR, 142.8R (23.8 R/yr), DD -13.0R, Sharpe 1.90
- **Hold-out (2025+)**: 192 trades, Sharpe 1.02, PF 1.15, +12.7R

### Asia R9 Restart -- Full History (2016-2026)

| Metric | Value |
|--------|-------|
| Trades | 770 |
| Win Rate | 45.5% |
| Profit Factor | 1.42 |
| Net R | 176.2 |
| Avg Annual R | 17.6 |
| Max DD | -11.3R |
| Calmar | 15.64 |
| Sharpe | 2.52 |
| Negative years | 0 |

**R by year**: 2016:+12 | 2017:+26 | 2018:+22 | 2019:+19 | 2020:+19 | 2021:+3 | 2022:+21 | 2023:+8 | 2024:+23 | 2025:+17 | 2026:+7

**Walk-Forward** (7 folds):
- WF efficiency: 0.797, stability: 0.964 (high)
- Combined OOS: +100.2R (15.8 R/yr)
- **Hold-out (2025+)**: 89 trades, Sharpe 2.77, PF 1.49, +23.2R
- **Monte Carlo**: 91.7% survival at -25R ruin

### 5-Phase Robust Pipeline Results (Asia R9 Restart)

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1. Structural | PASS | 770 trades, 45.5% WR, PF 1.42, Calmar 15.64 |
| 2. Walk-Forward | PASS | WF efficiency 0.797, stability 0.964 |
| 3. Prop Constraints | PASS | Avg annual R 14.3, worst month -5.0R |
| 4. Hold-Out OOS | PASS | 2025+: 89 trades, Sharpe 2.77, +23.2R |
| 5. Monte Carlo | PASS | 91.7% survival at -25R ruin |

---

## Pine Script Pitfalls

1. **Two ATR lengths**: NY uses ATR-12, Asia uses ATR-5. Both must be maintained via separate `request.security` calls. Do not mix them up -- the wrong ATR will produce incorrect stop distances and gap filters.

2. **ICF is session-specific**: NY uses the standard ORB directional check (ICF OFF). Asia uses the ICF-relaxed check (ICF ON): `fvg_top > orb_high OR close[1] > orb_high`. Applying ICF to NY drops Calmar from 16.36 to 7.13.

3. **Direction is session-specific**: NY takes both long and short FVGs. Asia takes only bullish FVGs (long only). Do not detect bearish FVGs for Asia.

4. **DOW exclusion is session-specific**: NY has no day-of-week exclusion. Asia excludes Tuesday. If the 20:00 bar falls on Tuesday, skip the entire Asia session.

5. **Cross-midnight Asia session**: The Asia session opens at 20:00 and flats at 04:00 (next calendar day). Use `var` flags to track session state across the midnight boundary. Reset state at 20:00, not at midnight.

6. **Tuesday dayofweek value**: Pine Script `dayofweek.tuesday` = 3 (Sunday=1, Monday=2, ..., Saturday=7). Verify on a known calendar date before deploying.

7. **ATR stop for BOTH sessions**: The stop is always ATR-computed -- `stop = entry +/- (stop_atr_pct / 100) * daily_atr`. NOT the structural `low[2]`/`high[2]` from the FVG pattern. Pine Script must match this.

8. **Entry starts one bar after signal bar**: The FVG is confirmed on bar[0] (the "after" candle). The limit order becomes active on the NEXT bar. The signal bar itself cannot fill the order.

9. **One trade per session-day per session**: NY and Asia each independently enforce one-trade-per-day. NY's trade flag does not affect Asia and vice versa.

10. **Bar magnifier**: Use `strategy(fill_orders_on_standard_ohlc=false)` in the strategy declaration. This tells TradingView to use intrabar data for fill detection, matching the Python backtester's 1-minute/1-second bar magnifier behavior.

11. **max_gap_atr_pct=0 for both**: The ATR-percentage maximum gap filter is disabled for both sessions. Only the point-based maximum (100 for NY, 75 for Asia) and ATR-percentage minimum apply.

12. **Same-bar SL+TP1 conflict**: When both stop loss and TP1 are triggered on the same bar, SL always wins. This is the conservative assumption matching the Python backtester.

13. **Half-open time intervals**: All time windows use [start, end) convention. The bar AT `start` is included; the bar AT `end` is excluded. The 09:50 bar is the first bar of the NY entry window (not the last ORB bar).

14. **ORB windows differ**: NY uses 20 minutes (4 bars: 09:30, 09:35, 09:40, 09:45). Asia uses 15 minutes (3 bars: 20:00, 20:05, 20:10). Do not hardcode a single ORB bar count.

15. **FVG bar notation**: `[0]`=after candle (current), `[1]`=impulse candle, `[2]`=before candle. This is NOT `[1]`, `[2]`, `[3]`. The FVG is confirmed when bar[0] closes.

---

## Implementation Checklist

### Common

- [ ] Two `request.security` calls for ATR (period 12 and period 5)
- [ ] FVG detection uses `[0]`, `[1]`, `[2]` correctly (not `[1]`, `[2]`, `[3]`)
- [ ] Same-bar SL+TP1 conflict: SL wins
- [ ] Partial exit: `floor(qty/2)` at TP1
- [ ] BE stop moves to entry after TP1 (0 tick offset)
- [ ] `fill_orders_on_standard_ohlc = false` in strategy declaration
- [ ] Position sizing: `floor(risk_usd / (risk_pts * 20))`, minimum 1
- [ ] All time comparisons use half-open [start, end) intervals
- [ ] Defensive: if position open at opposite session start, suppress signals
- [ ] Limit order active from bar AFTER FVG signal bar (signal bar itself cannot fill)
- [ ] First FVG per direction per session-day retains priority; later same-direction signals discarded

### NY

- [ ] ORB across four 5m candles (09:30-09:50)
- [ ] Both directions (long + short FVGs)
- [ ] No ICF (standard ORB check only: `fvg_top > orb_high` / `fvg_bottom < orb_low`)
- [ ] No DOW exclusion
- [ ] Entry window 09:50-15:30, Flat at 15:50
- [ ] ATR 12 for stop and gap filters
- [ ] `stop_dist = 0.0875 * daily_atr_12`
- [ ] `min_gap = 0.0225 * daily_atr_12`, `max_gap = 100` pts
- [ ] First-to-fill cancels other direction

### Asia

- [ ] Session day resets at 20:00 (cross-midnight handling with `var` flags)
- [ ] Tuesday exclusion (`dayofweek == dayofweek.tuesday`)
- [ ] ORB across three 5m candles (20:00-20:15)
- [ ] Long only (no bearish FVG detection for Asia)
- [ ] ICF ON: `fvg_top > orb_high OR close[1] > orb_high`
- [ ] Entry window 20:15-22:30, Flat at 04:00
- [ ] ATR 5 for stop and gap filters
- [ ] `stop_dist = 0.04 * daily_atr_5`
- [ ] `min_gap = 0.009 * daily_atr_5`, `max_gap = 75` pts

---

## Notes

- All times are America/New_York (Eastern).
- All time windows are half-open [start, end).
- A bar's time is its open time (the 09:30 bar represents 09:30-09:35).
- This document supersedes `NQ_PINE_SPEC.md` (old config: rr=2.0, tp1=0.6, long-only, stop=9.0%, ATR=14).
- Reference specs: `NQ_PINE_SPEC.md` (old, superseded), `PORTFOLIO_PINE_SPEC.md` (4-way portfolio — note: its NQ sections use older ATR=14/rr=2.0 configs, not the R20 values here), `GC_PINE_SPEC.md` (GC stacked).
