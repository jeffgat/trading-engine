# 4-Way Portfolio — Pine Script Specification

Combined spec for all four production strategies. Each runs as a **separate Pine Script** on its own instrument/symbol — TradingView cannot run multi-instrument strategies in a single script. This document covers all four in one place so the common patterns are clear and differences are explicit.

**Portfolio DB entry**: `4-Way Portfolio: ES LDN + NQ ASIA + NQ NY + GC NY` (ID 6719)

---

## Portfolio Summary

| Script | Instrument | Session | Direction | Strategy Type | Status |
|--------|-----------|---------|-----------|---------------|--------|
| ES_LDN | ES | London (ET 03:00–08:25) | Both | FVG Continuation | CONDITIONAL GO |
| NQ_ASIA | NQ | Asia (ET 20:00–00:00) | Both | FVG Continuation | IN-SAMPLE VALIDATED |
| NQ_NY | NQ | NY (ET 09:30–16:00) | Long only | FVG Continuation | CONDITIONAL GO |
| GC_NY | GC | NY (ET 09:30–16:45) | Long only | FVG Inversion (stacked) | GO |

**Combined in-sample (2015–2026)**: 5,644 trades, 54.71% WR, +1,130.95R, Max DD -25.94R, Calmar 43.6, Sharpe 2.33, PF 1.45

**All legs risk $5,000/trade** (same R unit across instruments).

---

## Common Building Blocks

All four strategies share these patterns. Implement them once per script.

### ATR Computation (Daily, Previous Day)

Each intraday bar uses the **previous completed day's ATR** — no look-ahead:

```pine
// Replace N with the atr_length for each strategy
daily_atr = request.security(syminfo.tickerid, "D", ta.atr(N)[1], lookahead=barmerge.lookahead_on)
```

- ES LDN: `N = 14`
- NQ ASIA: `N = 5`
- NQ NY: `N = 14`
- GC NY: `N = 50`

The `[1]` shift combined with `lookahead_on` means "the ATR as of yesterday's close" — the same value available to a live trader before today's session opens.

### FVG Detection (3-Candle Pattern)

**Bar notation** — all on the confirmed (closed) bar timeframe (5m):
- `bar[0]` = current (just closed) bar — the "after" candle
- `bar[1]` = 1 bar ago — the impulse candle
- `bar[2]` = 2 bars ago — the "before" candle

#### Bullish FVG (for long continuation)

```pine
bullish_fvg = high[2] < low[0] and high[2] < high[1] and low[2] < low[0]

fvg_top    = low[0]     // entry level for buy limit (top of gap)
fvg_bottom = high[2]    // bottom of gap
gap_size   = fvg_top - fvg_bottom
stop_level = low[2]     // before-candle's low = stop below entry
```

#### Bearish FVG (for short continuation)

```pine
bearish_fvg = low[2] > high[0] and low[2] > low[1] and high[2] > high[0]

fvg_bottom = high[0]    // entry level for sell limit (bottom of gap)
fvg_top    = low[2]     // top of gap
gap_size   = fvg_top - fvg_bottom
stop_level = high[2]    // before-candle's high = stop above entry
```

### Exit Logic (Shared Across All Continuation Strategies)

All strategies use the same exit state machine. Inputs differ by strategy but the structure is identical.

```
State: tp1_hit = false, current_stop = initial_stop

Each bar after fill, check in this priority order:

A. EOD Flat
   if bar_time >= flat_start AND position not stopped:
       if tp1_hit → EXIT_TP1_EOD (close remaining at close price)
       else       → EXIT_EOD     (close all at close price)

B. Stop Loss (before TP1)
   if (long: low <= current_stop) or (short: high >= current_stop):
       if not tp1_hit → EXIT_SL (full -1R loss)

C. Same-bar conflict: SL + TP1 on same bar
   if stop triggered AND tp1 level reached AND not tp1_hit:
       SL WINS → EXIT_SL

D. TP1 Partial (multi-contract only)
   if (long: high >= tp1_price) or (short: low <= tp1_price):
       if not tp1_hit and qty > 1:
           close floor(qty/2) at tp1_price
           tp1_hit = true
           current_stop = entry  // move stop to breakeven
           remaining = qty - floor(qty/2)

E. After TP1 — Breakeven Stop
   if tp1_hit:
       if (long: low <= current_stop) or (short: high >= current_stop):
           EXIT_TP1_BE (exit at entry price)

F. After TP1 — TP2 Full Target
   if tp1_hit:
       if (long: high >= tp2_price) or (short: low <= tp2_price):
           EXIT_TP1_TP2

G. Single Contract Path
   if qty == 1:
       if tp1 reached: tp1_hit = true, current_stop = entry (no partial exit)
       if tp2 reached: EXIT_TP2_SINGLE
```

### Position Sizing

```pine
risk_pts = math.abs(entry - stop_price)
qty_raw  = risk_usd / (risk_pts * point_value)
qty      = math.max(math.floor(qty_raw), 1)
half_qty = math.max(math.floor(qty / 2), 1)
is_single = (qty == 1)
```

---

## Strategy 1 — ES LDN Continuation (Both Directions)

**File**: `ES_LDN_continuation.pine`
**Instrument**: ES (E-mini S&P 500), COMEX
**DB**: `ES LDN 2016-2026 Continuation Both WF Mode` (ID 6707)
**Performance**: 2,328 trades | 48.0% WR | +609.19R | Max DD -18.0R | Sharpe 2.51

### Instrument Details

| Field | Value |
|-------|-------|
| Symbol | ES (e.g. `CME_MINI:ES1!`) |
| Point value | $50/point |
| Min tick | 0.25 |
| Timezone | America/New_York |

### Parameters

| Param | Value |
|-------|-------|
| rr | 3.0 |
| tp1_ratio | 0.5 |
| atr_length | 14 |
| risk_usd | 5000 |
| stop_atr_pct | 1.5% |
| min_gap_atr_pct | 1.25% |
| max_gap_points | 50.0 |
| ORB window | 03:00–03:15 ET (15 min, three 5m candles) |
| Entry window | 03:15–08:25 ET |
| Flat window | 08:20–08:25 ET |
| direction | both (long + short) |
| bar_magnifier | ON |
| be_offset_ticks | 0 (stop moves to exact entry) |

### Signal Flow

#### Step 1: Session Clock
London session day = the calendar date in ET. A new session day starts when bar time first reaches 03:00 ET.

#### Step 2: ORB (03:00–03:15)
Accumulate across three 5m candles (03:00, 03:05, 03:10 bars):

```pine
if bar_time >= 03:00 and bar_time < 03:15
    orb_high := math.max(orb_high, high)
    orb_low  := math.min(orb_low,  low)

orb_ready = bar_time >= 03:15
```

Reset `orb_high`, `orb_low`, `orb_ready` on each new session day.

#### Step 3: FVG Detection (both directions)

During entry window (03:15–08:25):

**Bullish FVG → Long setup:**
```pine
if bullish_fvg and orb_ready
    and fvg_top > orb_high                          // above ORB
    and gap_size >= 0.0125 * daily_atr              // min 1.25% ATR
    and gap_size <= 50.0                             // max 50 ES points
    → store pending_long: entry_level = fvg_top
```

**Bearish FVG → Short setup:**
```pine
if bearish_fvg and orb_ready
    and fvg_bottom < orb_low                        // below ORB
    and gap_size >= 0.0125 * daily_atr              // min 1.25% ATR
    and gap_size <= 50.0                             // max 50 ES points
    → store pending_short: entry_level = fvg_bottom
```

First FVG per direction detected retains priority. One signal per direction per session day.

#### Step 4: Limit Order Fill

Starting the bar AFTER the signal bar:

```pine
// Long: price must come DOWN to entry_level
if long pending and low <= entry_level → FILL LONG at entry_level

// Short: price must go UP to entry_level
if short pending and high >= entry_level → FILL SHORT at entry_level
```

One-trade-per-day enforced: once either direction fills, the other is cancelled.

#### Step 5: Trade Parameters

**Long:**
```
stop_dist  = 0.015 * daily_atr              // 1.5% of ATR
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 3.0 * risk_pts * 0.5   // = entry + 1.5 * risk_pts
tp2_price  = entry + 3.0 * risk_pts
be_price   = entry
```

**Note**: The stop is ATR-computed — `stop = entry - 0.015 * daily_atr`. The Python simulator always uses `stop_dist = (stop_atr_pct / 100) * ATR` as the actual stop level, not the structural `low[2]`. Pine Script must match this.

**Short (mirror image):**
```
stop_dist  = 0.015 * daily_atr
stop_level = entry + stop_dist
risk_pts   = stop_dist
tp1_price  = entry - 3.0 * risk_pts * 0.5
tp2_price  = entry - 3.0 * risk_pts
be_price   = entry
```

#### Step 6: Exit

Apply shared exit logic with `flat_start = 08:20 ET`.

### ES LDN Pitfalls

1. **London session is cross-midnight for ET** — 03:00 ET is the ORB open. Date context is ET, not JST or GMT.
2. **Both directions**: Unlike NQ NY (long only), take both bullish FVGs above ORB AND bearish FVGs below ORB. One-trade-per-day: first fill cancels the other pending.
3. **ATR stop, not structural**: The stop is ATR-computed — `stop = entry ± 0.015 * daily_atr`. The Python simulator always derives the stop from `stop_atr_pct`, not from `low[2]`/`high[2]`. Do not use the before-candle low/high as the stop level.
4. **be=0**: No tick offset on breakeven. Stop moves to exact entry price after TP1.
5. **Flat at 08:20**: Close everything by 08:20 ET. London session liquidity drops sharply before US open.
6. **2025 hold-out was exceptional** (+61.2R, Sharpe 2.27). Accept structural DD (~18-24R in OOS) — it cannot be reduced. Trade at reduced size.

---

## Strategy 2 — NQ ASIA Continuation (Both Directions, No Thursday)

**File**: `NQ_ASIA_continuation.pine`
**Instrument**: NQ (Nasdaq-100 Futures), CME
**DB**: `NQ ASIA 2015-2026 v3 flat00 Pipeline NO-GO` (ID 6718) — name reflects pipeline result; IN-SAMPLE metrics are the production config
**Performance**: 1,800 trades | 64.8% WR | +197.23R | Max DD -10.2R | Sharpe 2.12

### Instrument Details

| Field | Value |
|-------|-------|
| Symbol | NQ (e.g. `CME_MINI:NQ1!`) |
| Point value | $20/point |
| Min tick | 0.25 |
| Timezone | America/New_York |

### Parameters

| Param | Value |
|-------|-------|
| rr | 1.75 |
| tp1_ratio | 0.35 |
| atr_length | 5 |
| risk_usd | 5000 |
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% (no max_gap_points — disabled) |
| ORB window | 20:00–20:10 ET (10 min, two 5m candles) |
| Entry window | 20:10–23:00 ET |
| Flat window | 00:00–07:00 ET (midnight close) |
| direction | both |
| gate | skip Thursday trades |
| bar_magnifier | ON |

### Session Day Definition

Asia session crosses midnight ET. A **session day** is defined by the DATE of the **ORB open** (20:00 bar). The flat at 00:00 closes trades from the session that opened at 20:00 the prior calendar day.

```pine
// New Asia session starts at 20:00 ET
new_session = (hour == 20 and minute == 0) and not (hour[1] == 20 and minute[1] == 0)

// Thursday gate: skip if today's session opened on a Thursday
// dayofweek == 5 means Friday in Pine (TradingView) — verify carefully
// Session opens 20:00 ET, so if dayofweek at 20:00 is Thursday → skip
```

**Thursday gate**: If the bar at 20:00 ET falls on a Thursday (day of week = Thursday in the ET calendar), mark the entire session as skipped. No signals for that session day.

### Signal Flow

#### Step 1: ORB (20:00–20:10)
Two 5m candles: 20:00 and 20:05 bars.

```pine
if bar_time >= 20:00 and bar_time < 20:10 and not thursday_session
    orb_high := math.max(orb_high, high)
    orb_low  := math.min(orb_low,  low)

orb_ready = bar_time >= 20:10
```

#### Step 2: FVG Detection (both directions)

During entry window (20:10–23:00):

**Bullish FVG → Long:**
```pine
if bullish_fvg and orb_ready and not thursday_session
    and fvg_top > orb_high                          // above ORB
    and gap_size >= 0.009 * daily_atr               // min 0.90% ATR
    and gap_size <= 0.05 * daily_atr                // max 5.0% ATR (no point cap)
    → pending_long: entry = fvg_top
```

**Bearish FVG → Short:**
```pine
if bearish_fvg and orb_ready and not thursday_session
    and fvg_bottom < orb_low                        // below ORB
    and gap_size >= 0.009 * daily_atr               // min 0.90% ATR
    and gap_size <= 0.05 * daily_atr                // max 5.0% ATR
    → pending_short: entry = fvg_bottom
```

#### Step 3: Trade Parameters

**Long:**
```
stop_dist  = 0.037 * daily_atr              // 3.7% of ATR
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 1.75 * risk_pts * 0.35   // = entry + 0.6125 * risk_pts
tp2_price  = entry + 1.75 * risk_pts
be_price   = entry
```

**Short:**
```
stop_dist  = 0.037 * daily_atr
stop_level = entry + stop_dist
risk_pts   = stop_dist
tp1_price  = entry - 1.75 * risk_pts * 0.35
tp2_price  = entry - 1.75 * risk_pts
be_price   = entry
```

#### Step 4: Exit

Apply shared exit logic with `flat_start = 00:00 ET (midnight)`. Any position open at midnight exits at that bar's close, regardless of where price is. This is the key innovation of v3 — cutting overnight risk.

### NQ ASIA Pitfalls

1. **ATR stop, not structural**: Like all strategies, the stop is ATR-computed — `stop = entry ± 0.037 * daily_atr`. Do not use `low[2]`/`high[2]` as the stop. The Python simulator always derives stop from `stop_atr_pct`.
3. **ATR length = 5**, not 14. NQ Asia requires faster ATR. Walk-forward confirmed ATR 5 outperforms ATR 14 OOS.
4. **No Thursday sessions**: Check day of week at session open (20:00 bar). Pine Script's `dayofweek` is 1=Sunday, 7=Saturday. Thursday = 5. Verify with backtester.
5. **Cross-midnight session**: The 20:00 bar opens "tonight's" session; the 00:00 bar closes it. Use a `var bool session_active` flag to track this correctly.
6. **Midnight flat is a hard close**: If position is open at 00:00, close at that bar's close, even if mid-trade. This removes the overnight drift that caused the most losses in prior versions.
7. **max_gap is ATR-based, not point-based**: `max_gap_points = 0.0` in config means the Python backtester uses the ATR-pct cap only. In Pine, compute `max_gap_points_dynamic = 0.05 * daily_atr`.
8. **Both directions**: Long AND short FVGs are valid. High win rate (64.8%) comes from both. Long-only drops to Calmar ~10 with a bad 2022.
9. **Session on NQ runs until 23:00 for entries but flat at 00:00**: Signals detected 20:10-23:00 can stay open until midnight. No new signals after 23:00 but existing position rides to TP or midnight.

---

## Strategy 3 — NQ NY Long Continuation

**File**: `NQ_NY_continuation.pine`
**Instrument**: NQ (Nasdaq-100 Futures), CME
**DB**: `NQ NY Long Continuation Accepted (WF Mode)` (ID 6717)
**Performance**: 1,167 trades | 51.7% WR | +155.89R | Max DD -10.9R | Sharpe 1.93

### Parameters

| Param | Value |
|-------|-------|
| rr | 2.0 |
| tp1_ratio | 0.6 |
| atr_length | 14 |
| risk_usd | 5000 |
| stop_atr_pct | 9.0% |
| min_gap_atr_pct | 3.0% |
| max_gap_points | 100.0 |
| ORB window | 09:30–09:50 ET (20 min, four 5m candles) |
| Entry window | 09:50–15:00 ET |
| Flat window | 15:50–16:00 ET |
| direction | long only |
| bar_magnifier | ON |

### Signal Flow

#### Step 1: ORB (09:30–09:50)
Four 5m candles: 09:30, 09:35, 09:40, 09:45 bars.

```pine
if bar_time >= 09:30 and bar_time < 09:50
    orb_high := math.max(orb_high, high)
    orb_low  := math.min(orb_low,  low)

orb_ready = bar_time >= 09:50
```

#### Step 2: Bullish FVG Detection (long only)

During entry window (09:50–15:00):

```pine
if bullish_fvg and orb_ready and not trade_taken_today
    and fvg_top > orb_high                          // above ORB high
    and gap_size >= 0.03 * daily_atr                // min 3.0% ATR
    and gap_size <= 100.0                            // max 100 NQ points
    → pending_long: entry = fvg_top, stop = low[2]
```

Only bullish FVGs. Bearish FVGs ignored entirely.

#### Step 3: Limit Order Fill

```pine
// From bar after signal: buy fills when price comes DOWN to entry
if long pending and low <= entry_level → FILL at entry_level
```

One pending long per day. If another bullish FVG forms before the first fills, the first retains priority.

#### Step 4: Trade Parameters

```
risk_pts   = entry - low[2]
tp1_price  = entry + 2.0 * risk_pts * 0.6    // = entry + 1.2 * risk_pts
tp2_price  = entry + 2.0 * risk_pts
be_price   = entry
```

#### Step 5: Exit

Apply shared exit logic with `flat_start = 15:50 ET`.

### NQ NY Pitfalls

1. **Long only**. Do not take short setups. NQ NY shorts are structurally broken across all strategy types — confirmed in 15 sweep rounds.
2. **ORB is 20m**, not 5m or 15m. Confirmed as the optimal window over extensive sweeps. Accumulate across four bars.
3. **gap=3.0% is the DD reducer**. The key insight: larger minimum gap filters out weak FVGs that lead to drawdown. Do not lower below 3.0%.
4. **stop=9.0% of ATR is structural** (not the before-candle stop for this strategy). The Python backtester uses ATR-based stop sizing: `stop_dist = 0.09 * daily_atr`, `stop_price = entry - stop_dist`. This differs from the structural `low[2]` stop used in theory — use the ATR-based computation for NQ NY.
5. **Entry immediately after ORB closes** (09:50, no delay). Delaying to 10:00 or later hurts performance.
6. **Entry ends at 15:00** — allow the full session (not 12:00 or 14:00).
7. **2023 is the weak year** (about -2R most configs). All other years positive. Accept this.

---

## Strategy 4 — GC NY Inversion Longs (Stacked v9 + Clean Air)

**File**: `GC_NY_inversion_stacked.pine`
**Instrument**: GC (Gold Futures), COMEX
**DB**: `GC NY Inv Longs Stacked v9+CleanAir` (ID 6693)
**Performance**: 349 trades | 57.6% WR | +142.54R | Max DD -8.2R | Sharpe 3.83

This is a **two-signal stacked strategy** on a single instrument. Full details in `GC_PINE_SPEC.md`. Summary below.

### Instrument Details

| Field | Value |
|-------|-------|
| Symbol | GC (e.g. `COMEX:GC1!`) |
| Point value | $100/point |
| Min tick | 0.10 |
| ATR length | 50 |
| Timezone | America/New_York |

### Signal A — v9 Regime-Sized ORB Inversion

| Param | Value |
|-------|-------|
| ORB window | 09:30–09:35 (5 min = 1 candle) |
| Entry window | 09:35–15:00 |
| Flat | 15:50–16:00 |
| stop_atr_pct | 9.0% |
| min_gap_atr_pct | 1.0% |
| max_gap_points | 25.0 |
| qualifying_move_atr_pct | 10.0% |
| rr | 3.5 |
| tp1_ratio | 0.2 |
| regime_sizing | 2x when VIX<18 AND DXY<SMA50 (prior day close) |

**Signal A Flow**:
1. ORB low = low of the 09:30 candle
2. Detect bearish FVGs BELOW the ORB low (09:35–15:00)
3. QM gate: session running low must have swept ≥ 10% ATR below the ORB low at some point
4. Trigger: `close > fvg_top (low[2])` with QM gate passing → MARKET LONG at bar close
5. Regime check: if VIX_prev < 18 AND DXY_prev < DXY_SMA50, double the position size

### Signal B — Clean Air No-ORB Inversion

| Param | Value |
|-------|-------|
| Entry window | 09:35–16:45 |
| Flat | 16:45–16:50 |
| stop_atr_pct | 12.0% |
| qualifying_move_atr_pct | 100.0% (= 1 full ATR below session high) |
| clean_air_n | 1 (prior trading day lookback) |
| rr | 5.0 |
| tp1_ratio | 0.2 |

**Signal B Flow**:
1. No ORB — detect bearish FVGs anywhere in session (09:35–16:45)
2. QM gate: session running low ≤ session running high − daily_atr (full ATR sweep from session high)
3. Trigger: `close > fvg_top` with QM gate passing AND clean air check passing
4. Clean air: session running low must NOT have dipped into any bullish FVG zone from yesterday
5. MARKET LONG at bar close (same entry type as Signal A)

**Dedup**: If Signal A fires first on a given day, Signal B is suppressed for that day. Track a single `trade_taken_today` flag.

### GC Pitfalls

1. **Market entry, not limit order**: Both GC signals enter at bar close (inversion confirmation), not a limit order. This is the key architectural difference from the three continuation strategies.
2. **ATR=50**: Much longer smoothing than NQ/ES. Use `ta.atr(50)` on daily.
3. **5-min ORB only**: orb_high = high of the single 09:30 candle, orb_low = low of the same candle.
4. **QM gate does NOT kill pending FVGs** — the FVG stays pending until QM passes or session ends.
5. **Clean air lookback**: Maintain a `var float[] prev_fvg_tops` array. At each new session day start, copy yesterday's bullish FVG zones in. Clear at next day. Full implementation in `GC_PINE_SPEC.md`.
6. **Regime sizing for Signal A only** — Signal B uses flat 1x. Apply 2x only when `vix_prev < 18 AND dxy_prev < dxy_sma50`.
7. **Different flat times**: Signal A exits by 15:50, Signal B by 16:45. Track which signal opened the position.

---

## Portfolio Execution Rules

### Risk Allocation

Each script risks $5,000/trade. On a given day, up to four signals could fire (one per strategy, each on a different instrument). Maximum simultaneous exposure:

- ES LDN (03:00–08:25 ET) — isolated time window, no overlap with NY sessions
- NQ ASIA (20:00–00:00 ET) — isolated time window, no overlap with NY
- NQ NY (09:50–15:50 ET) and GC NY (09:35–16:45 ET) — **overlap on NY hours**

On NQ NY + GC NY days, both can have open positions simultaneously. Combined risk = 2R if both hold.

### Sizing for Combined Portfolio

These in-sample metrics are with $5,000/R per leg:

| Leg | R/yr (IS) | Max DD (IS) |
|-----|-----------|-------------|
| ES LDN | +60.3R | -18.0R |
| NQ ASIA | +17.8R | -10.2R |
| NQ NY | +14.1R | -10.9R |
| GC NY | +14.4R | -8.2R |
| **Portfolio** | **~106R** | **-25.9R** |

The combined in-sample portfolio DD is -25.9R (better than simple sum due to diversification). At $5K/R, that is -$129,500. Adjust per-leg sizing to fit your account. Example: at 0.5x ($2,500/R per leg), combined DD ≈ -13R × $2,500 = -$32,500.

### What Each Leg Contributes

- **ES LDN**: Volume engine (~230 trades/yr). Both directions. Highest absolute R but highest DD. Sets the floor for correlated macro risk (ES and NQ share equity correlation).
- **NQ ASIA**: Consistency layer. 64.8% WR, flat midnight close, no Thursdays. Mostly uncorrelated with daytime sessions.
- **NQ NY**: Long-only momentum capture. Strong when equities trend higher.
- **GC NY**: True diversifier. Gold inversion has near-zero correlation with equity continuation. Highest Sharpe (3.83), lowest DD (-8.2R).

### Correlation Warning

ES LDN and NQ NY both trade equity index instruments. In sharp macro down moves (2022-style), both can underperform simultaneously. The GC and NQ ASIA legs provide meaningful diversification.

---

## Implementation Checklist (Per Script)

- [ ] ATR computed on daily timeframe, previous day, correct period
- [ ] ORB accumulated across correct number of 5m candles
- [ ] Session day resets correctly (especially for NQ ASIA cross-midnight)
- [ ] FVG detection uses `[0]`, `[1]`, `[2]` correctly (not `[1]`, `[2]`, `[3]`)
- [ ] One signal per direction per session day
- [ ] Entry is a LIMIT order (continuation) or MARKET at close (GC inversion)
- [ ] Limit order starts scanning from bar AFTER signal bar
- [ ] TP1/TP2/stop computed correctly for direction (long vs short)
- [ ] Partial exit: floor(qty/2) at TP1, not half of original qty
- [ ] Breakeven stop moves to entry after TP1 (0 tick offset for all strategies)
- [ ] Same-bar SL+TP1 conflict: SL wins
- [ ] EOD flat fires at the correct time per strategy
- [ ] Thursday exclusion (NQ ASIA only)
- [ ] Regime sizing and Clean Air filter (GC only)
- [ ] `fill_orders_on_standard_ohlc = false` or equivalent for bar magnifier

---

## Exit Types and R-Multiple Reference

Applies to all strategies. R-multiples below use each strategy's specific rr and tp1_ratio.

| Exit | Condition | R-Multiple (general formula) |
|------|-----------|------------------------------|
| EXIT_NO_FILL | Limit never reached | 0R (no trade) |
| EXIT_SL | Stopped before TP1 | -1.0R |
| EXIT_TP1_TP2 | TP1 + TP2 both hit | 0.5×(rr×tp1) + 0.5×rr |
| EXIT_TP1_BE | TP1 + breakeven stop | 0.5×(rr×tp1) + 0R |
| EXIT_TP1_EOD | TP1 + EOD close | 0.5×(rr×tp1) + variable |
| EXIT_EOD | EOD close, no TP1 | variable |
| EXIT_TP2_SINGLE | 1 contract, TP2 hit | rr × 1R |

**Per-strategy EXIT_TP1_TP2 approximate R** (multi-contract, 50/50 split):

| Strategy | TP1R | TP2R | EXIT_TP1_TP2 |
|----------|------|------|--------------|
| ES LDN | +1.50R | +3.0R | +2.25R |
| NQ ASIA | +0.61R | +1.75R | +1.18R |
| NQ NY | +1.20R | +2.0R | +1.60R |
| GC v9 | +0.70R | +3.5R | +2.10R |
| GC CleanAir | +1.00R | +5.0R | +3.00R |

---

*Reference specs: `NQ_PINE_SPEC.md` (NQ NY full detail), `GC_PINE_SPEC.md` (GC stacked full detail).*
*All times America/New_York (Eastern). All time windows half-open [start, end).*
