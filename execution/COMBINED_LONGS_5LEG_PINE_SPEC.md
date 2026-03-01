# NQ+GC+ES Combined Longs (5-Leg) — Pine Script Specification

Five independently optimized long-only FVG continuation strategies combined into a portfolio. Each runs as a **separate Pine Script** per instrument — TradingView cannot run multi-instrument strategies in a single script.

**Portfolio DB entry**: `NQ+GC+ES Combined Longs (5-Leg Portfolio)`

---

## Portfolio Summary

| Script | Instrument | Session | Direction | Key Params | Pipeline |
|--------|-----------|---------|-----------|------------|----------|
| NQ NY R11 | NQ | NY (09:30–15:30) | Long only | rr=3.5, stop=7.0% ATR | CONDITIONAL (4/5) |
| NQ Asia R9 | NQ | Asia (20:00–04:00) | Long only | rr=6.0, stop=100% ORB | GO (5/5) |
| GC NY R3 | GC | NY (09:30–13:30) | Long only | rr=9.0, stop=4.5% ATR | GO (user override) |
| ES NY Final | ES | NY (09:30–15:50) | Long only | rr=5.0, stop=5.0% ATR | CONDITIONAL (4/5) |
| ES Asia Final | ES | Asia (20:00–07:00) | Long only | rr=1.5, stop=125% ORB | CONDITIONAL (4/5) |

**Combined (2016–2026)**: 4,253 trades, +855.2R (85.5 R/yr), Calmar 35.47, 0 negative full years.

**All legs risk $5,000/trade** (same R unit across instruments).

---

## Pine Script Files

| File | Instrument | Sessions |
|------|-----------|----------|
| `NQ_combined_longs.pine` | NQ (`CME_MINI:NQ1!`) | NY R11 + Asia R9 |
| `GC_NY_cont_longs.pine` | GC (`COMEX:GC1!`) | NY R3 |
| `ES_combined_longs.pine` | ES (`CME_MINI:ES1!`) | NY Final + Asia Final |

NQ NY and NQ Asia share a single script because they're the same instrument with non-overlapping sessions (Asia flats at 04:00, NY opens at 09:30 — 5.5-hour gap).

ES NY and ES Asia share a single script because they're the same instrument with non-overlapping sessions (Asia flats at 07:00, NY opens at 09:30 — 2.5-hour gap).

---

## Common Building Blocks

All five strategies are **FVG continuation** (bullish FVG above ORB → limit buy at top of gap). They share identical FVG detection, limit order fill, and exit logic. Only the parameters differ.

### FVG Detection (3-Candle Pattern)

**Bar notation** — all on confirmed (closed) 5m bars:
- `bar[0]` = current (just closed) — the "after" candle
- `bar[1]` = 1 bar ago — the impulse candle
- `bar[2]` = 2 bars ago — the "before" candle

#### Bullish FVG (all five strategies are long-only)

```pine
bullish_fvg = high[2] < low[0] and high[2] < high[1] and low[2] < low[0]

fvg_top    = low[0]     // entry level for buy limit (top of gap)
fvg_bottom = high[2]    // bottom of gap
gap_size   = fvg_top - fvg_bottom
```

No bearish FVG detection needed — all five legs are long only.

### ORB Directional Filter: Standard vs ICF

**Standard (NQ NY R11, NQ Asia R9, ES NY Final, ES Asia Final — ICF OFF):**
```pine
long_orb_ok = fvg_top > orb_high    // bullish FVG must be above ORB high
```

**ICF-Relaxed (GC NY R3 — ICF ON):**
```pine
// Accept FVG if gap zone is above ORB high, OR impulse candle closed above ORB high
long_orb_ok = (fvg_top > orb_high) or (close[1] > orb_high)
```

### Limit Order Fill

Starting the bar AFTER the signal bar:

```pine
// Long: price must come DOWN to entry_level (retest the top of the gap)
if long_pending and low <= entry_level → FILL LONG at entry_level
```

One signal per session-day. First FVG detected retains priority.

### Exit Logic State Machine

All strategies share the same exit priority order. Only the parameters (flat_start, rr, tp1_ratio) differ.

```
State: tp1_hit = false, current_stop = initial_stop

Each bar after fill, check in this priority order:

A. EOD Flat
   if bar_time >= flat_start AND position not stopped:
       if tp1_hit → EXIT_TP1_EOD (close remaining at close price)
       else       → EXIT_EOD     (close all at close price)

B. Stop Loss (before TP1)
   if low <= current_stop AND not tp1_hit:
       → EXIT_SL (full -1R loss)

C. Same-bar conflict: SL + TP1 on same bar
   if low <= current_stop AND high >= tp1_price AND not tp1_hit:
       SL WINS → EXIT_SL

D. TP1 Partial (multi-contract only)
   if high >= tp1_price AND not tp1_hit AND qty > 1:
       close floor(qty/2) at tp1_price
       tp1_hit = true
       current_stop = entry  // move stop to breakeven
       remaining = qty - floor(qty/2)

E. After TP1 — Breakeven Stop
   if tp1_hit AND low <= current_stop:
       → EXIT_TP1_BE (exit at entry price)

F. After TP1 — TP2 Full Target
   if tp1_hit AND high >= tp2_price:
       → EXIT_TP1_TP2

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

- NQ: `point_value = 20`
- GC: `point_value = 100`
- ES: `point_value = 50`

### Dual Floor Rule (ES Only)

ES strategies apply a minimum point floor to both stop distance and TP1 distance:

```pine
// After computing stop_dist and tp1_dist from ATR/ORB:
stop_dist = math.max(stop_dist, 3.0)   // min 3.0 points
tp1_dist  = math.max(tp1_dist, 3.0)    // min 3.0 points
```

Both ES NY and ES Asia use `min_stop = 3.0 points` and `min_tp1 = 3.0 points`. At ES's $50/point, this means minimum risk per contract = $150 and minimum TP1 distance = $150.

The floor prevents degenerate trades when ATR is unusually low or the ORB range is tiny. Without it, risk_pts can be so small that a single tick of slippage overwhelms the trade.

NQ and GC do NOT use dual floor.

---

## Script 1 — NQ Combined Longs (NY R11 + Asia R9)

**File**: `NQ_combined_longs.pine`
**Instrument**: NQ (`CME_MINI:NQ1!`, $20/point, 0.25 tick)

### Combined Parameter Tables

#### Strategy Parameters

| Param | NY (R11) | Asia (R9) |
|-------|----------|-----------|
| strategy | continuation | continuation |
| direction | long only | long only |
| rr | 3.5 | 6.0 |
| tp1_ratio | 0.4 | 0.3 |
| atr_length | 12 | 5 |
| risk_usd | 5000 | 5000 |
| impulse_close_filter | **OFF** | **OFF** |
| DOW exclusion | **Friday** | **Tuesday** |

#### Session Timing

| Param | NY (R11) | Asia (R9) |
|-------|----------|-----------|
| ORB window | 09:30–09:50 (20m, 4 bars) | 20:00–20:15 (15m, 3 bars) |
| Entry window | 09:50–12:00 | 20:15–22:30 |
| Flat time | 15:30 | 04:00 |
| Flat end | 16:00 | 07:00 |

#### Stop & Gap Sizing

| Param | NY (R11) | Asia (R9) |
|-------|----------|-----------|
| Stop basis | **ATR** | **ORB range** |
| stop_atr_pct | 7.0% | — (not used) |
| stop_orb_pct | — | 100.0% |
| Gap min basis | **ATR** | **ORB range** |
| min_gap_atr_pct | 2.5% | — (not used) |
| min_gap_orb_pct | — | 10.0% |

**Critical difference**: NY computes stop from ATR; Asia computes stop from the ORB range.

### ATR Computation

Two `request.security` calls needed:

```pine
// NY uses 12-period ATR
daily_atr_12 = request.security(syminfo.tickerid, "D", ta.atr(12)[1], lookahead=barmerge.lookahead_on)

// Asia uses 5-period ATR (only for warmup, NOT for stop/gap — those use ORB range)
daily_atr_5 = request.security(syminfo.tickerid, "D", ta.atr(5)[1], lookahead=barmerge.lookahead_on)
```

The `[1]` + `lookahead_on` = "yesterday's ATR" — no look-ahead bias.

**Note**: Asia R9 uses ATR-5 only for the engine's internal ATR warmup. The actual stop and gap filters are ORB-based. In Pine Script, `daily_atr_5` is NOT needed for Asia's trade parameters — only the ORB range matters. You may still declare it if the engine requires an ATR for other purposes (e.g., daily_atr display), but stop/gap computations must use ORB range.

---

### Session 1 — NQ NY Long R11

**DB**: `NQ NY Cont Long R11 Final 2016-2026`
**Performance**: 561 trades, 53.3% WR, PF 1.51, Sharpe 2.90, +135.0R, DD -6.0R, Calmar 22.51

#### Session Day Definition

Calendar date in ET. New session day starts at 09:30 ET.

#### Friday Exclusion

Skip the entire NY session on Fridays:

```pine
is_friday = dayofweek == dayofweek.friday  // == 6
```

If it's Friday, no ORB, no signals, no trades for that day.

#### Step 1: ORB (09:30–09:50)

Four 5m candles: 09:30, 09:35, 09:40, 09:45.

```pine
if bar_time >= 09:30 and bar_time < 09:50 and not is_friday
    ny_orb_high := math.max(ny_orb_high, high)
    ny_orb_low  := math.min(ny_orb_low,  low)

ny_orb_ready = bar_time >= 09:50
```

Reset `ny_orb_high`, `ny_orb_low`, `ny_orb_ready`, `ny_long_pending`, `ny_trade_taken_today` at 09:30.

#### Step 2: Bullish FVG Detection (long only, NO ICF)

During entry window (09:50–12:00):

```pine
if bullish_fvg and ny_orb_ready and not is_friday and not ny_trade_taken_today
    and fvg_top > ny_orb_high                          // above ORB (standard check)
    and gap_size >= 0.025 * daily_atr_12               // min 2.5% of ATR-12
    → store ny_pending_long: entry_level = fvg_top
```

First FVG detected retains priority. One signal per session day.

#### Step 3: Limit Order Fill

```pine
if ny_long_pending and low <= ny_entry_level → FILL LONG at ny_entry_level
```

#### Step 4: Trade Parameters

```
stop_dist  = 0.07 * daily_atr_12              // 7.0% of ATR-12
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 3.5 * risk_pts * 0.4     // = entry + 1.4 * risk_pts
tp2_price  = entry + 3.5 * risk_pts
be_price   = entry
```

**The stop is ATR-computed** — `stop = entry - 0.07 * daily_atr_12`. NOT `low[2]`.

#### Step 5: Exit

Apply shared exit logic with `flat_start = 15:30 ET`.

---

### Session 2 — NQ Asia Long R9

**DB**: `NQ Asia Cont Long 2016-2026 GO`
**Performance**: 746 trades, 44.8% WR, PF 1.49, Sharpe 2.71, +200.1R, DD -8.9R, Calmar 22.61

#### Session Day Definition

Asia session crosses midnight ET. Session day = the DATE of the 20:00 bar.

```pine
new_asia_session = (hour == 20 and minute == 0) and not (hour[1] == 20 and minute[1] == 0)
```

#### Tuesday Exclusion

If the 20:00 bar falls on Tuesday, skip the entire session:

```pine
is_tuesday = dayofweek == dayofweek.tuesday  // == 3
```

#### Step 1: ORB (20:00–20:15)

Three 5m candles: 20:00, 20:05, 20:10.

```pine
if bar_time >= 20:00 and bar_time < 20:15 and not asia_session_skipped
    asia_orb_high := math.max(asia_orb_high, high)
    asia_orb_low  := math.min(asia_orb_low,  low)

asia_orb_ready = bar_time >= 20:15
asia_orb_range = asia_orb_high - asia_orb_low
```

Reset all Asia state at 20:00.

#### Step 2: Bullish FVG Detection (long only, NO ICF)

During entry window (20:15–22:30):

```pine
if bullish_fvg and asia_orb_ready and not asia_session_skipped and not asia_trade_taken_today
    and fvg_top > asia_orb_high                             // above ORB (standard check)
    and gap_size >= 0.10 * asia_orb_range                   // min 10% of ORB range
    → store asia_pending_long: entry_level = fvg_top
```

**Gap filter is ORB-based**, not ATR-based. `min_gap = 10% of ORB range`.

#### Step 3: Limit Order Fill

```pine
if asia_long_pending and low <= asia_entry_level → FILL LONG at asia_entry_level
```

#### Step 4: Trade Parameters (ORB-Based Stop)

```
orb_range  = asia_orb_high - asia_orb_low
stop_dist  = 1.00 * orb_range                 // 100% of ORB range
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 6.0 * risk_pts * 0.3     // = entry + 1.8 * risk_pts
tp2_price  = entry + 6.0 * risk_pts
be_price   = entry
```

**The stop is ORB-based** — `stop = entry - orb_range`. This is the key difference from all other strategies which use ATR-based stops. The ORB range defines the risk on each trade.

#### Step 5: Exit

Apply shared exit logic with `flat_start = 04:00 ET`.

---

### NQ Session Interaction Rules

1. **Independent state machines**: NY and Asia maintain completely separate state.
2. **No time overlap**: Asia flats at 04:00, NY starts at 09:30 — 5.5-hour gap.
3. **TradingView single-position model**: Works correctly since positions never overlap.
4. **Defensive check**: If Asia position is somehow still open at NY start, suppress NY signals.
5. **Independent risk**: Each session risks $5,000/trade independently. Sequential, never simultaneous.
6. **Both long only**: Neither session takes short setups.

---

## Script 2 — GC NY Continuation Longs R3

**File**: `GC_NY_cont_longs.pine`
**Instrument**: GC (`COMEX:GC1!`, $100/point, 0.10 tick)
**DB**: `GC NY Cont Longs R3 High-RR Final (Fri Excl)`
**Performance**: 626 trades, 31.6% WR, PF 1.45, Sharpe 2.23, +194.0R, DD -12.4R, Calmar 15.60

**This is a CONTINUATION strategy** — bullish FVG above ORB → limit buy at top of gap. NOT the GC inversion strategy documented in `GC_PINE_SPEC.md`.

### Parameters

| Param | Value |
|-------|-------|
| rr | 9.0 |
| tp1_ratio | 0.35 |
| atr_length | 7 |
| risk_usd | 5000 |
| stop_atr_pct | 4.5% |
| min_gap_atr_pct | 3.0% |
| impulse_close_filter | **ON** |
| direction | long only |
| ORB window | 09:30–09:38 (8m, ~2 bars) |
| Entry window | 09:38–12:00 |
| Flat time | 13:30 |
| Flat end | 16:00 |
| DOW exclusion | **Friday** |
| FOMC exclusion | **Yes** (skip FOMC days) |
| bar_magnifier | ON |

### ATR Computation

```pine
daily_atr_7 = request.security(syminfo.tickerid, "D", ta.atr(7)[1], lookahead=barmerge.lookahead_on)
```

### Friday Exclusion

```pine
is_friday = dayofweek == dayofweek.friday  // == 6
```

### FOMC Date Exclusion

FOMC meeting days must be skipped entirely (no ORB, no signals, no trades). In Pine Script, maintain a lookup of FOMC dates:

```pine
// FOMC dates — update annually
// Check if today's date matches any FOMC date
// Pine Script approach: use an array of YYYYMMDD integers
var int[] fomc_dates = array.from(
    20160127, 20160316, 20160427, 20160615, 20160727, 20160921, 20161102, 20161214,
    20170201, 20170315, 20170503, 20170614, 20170726, 20170920, 20171101, 20171213,
    20180131, 20180321, 20180502, 20180613, 20180801, 20180926, 20181108, 20181219,
    20190130, 20190320, 20190501, 20190619, 20190731, 20190918, 20191030, 20191211,
    20200129, 20200311, 20200429, 20200610, 20200729, 20200916, 20201105, 20201216,
    20210127, 20210317, 20210428, 20210616, 20210728, 20210922, 20211103, 20211215,
    20220126, 20220316, 20220504, 20220615, 20220727, 20220921, 20221102, 20221214,
    20230201, 20230322, 20230503, 20230614, 20230726, 20230920, 20231101, 20231213,
    20240131, 20240320, 20240501, 20240612, 20240731, 20240918, 20241107, 20241218,
    20250129, 20250319, 20250507, 20250618, 20250730, 20250917, 20251029, 20251210,
    20260128, 20260318, 20260429, 20260610, 20260729, 20260916, 20261104, 20261216
)

today_int = year * 10000 + month * 100 + dayofmonth
is_fomc = array.includes(fomc_dates, today_int)
```

Skip the entire session if `is_friday OR is_fomc`.

### ORB Window (09:30–09:38)

**8-minute ORB** — this spans parts of two 5m candles on a 5m chart:
- The 09:30 bar (09:30–09:35): fully included
- The 09:35 bar (09:35–09:40): partially included (only first 3 minutes)

**Pine Script on 5m timeframe**: Cannot precisely capture 8 minutes. Options:
1. **Conservative (recommended)**: Use 2 full bars (09:30 + 09:35 = 10 minutes). ORB ready at 09:40.
2. **Precise**: Run on 1m timeframe and aggregate manually. ORB ready at 09:38.

```pine
// Option 1: 10m approximation on 5m chart
if bar_time >= 09:30 and bar_time < 09:40 and not session_skipped
    gc_orb_high := math.max(gc_orb_high, high)
    gc_orb_low  := math.min(gc_orb_low,  low)

gc_orb_ready = bar_time >= 09:40
```

**Note**: The Python backtester uses 1m bar magnifier to get the precise 09:38 boundary. On a 5m Pine Script, the 10m approximation (2 bars) is the closest match. If exact fidelity is needed, run on a 1m chart.

### Bullish FVG Detection (long only, ICF ON)

During entry window (09:38/09:40–12:00):

```pine
if bullish_fvg and gc_orb_ready and not session_skipped and not gc_trade_taken_today
    and ((fvg_top > gc_orb_high) or (close[1] > gc_orb_high))  // ICF relaxed check
    and gap_size >= 0.03 * daily_atr_7                          // min 3.0% of ATR-7
    → store gc_pending_long: entry_level = fvg_top
```

**ICF is ON** — accept FVGs where the impulse candle (bar[1]) closed above OBR high, even if the gap zone itself doesn't clear it.

### Limit Order Fill

```pine
if gc_long_pending and low <= gc_entry_level → FILL LONG at gc_entry_level
```

### Trade Parameters

```
stop_dist  = 0.045 * daily_atr_7              // 4.5% of ATR-7
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_price  = entry + 9.0 * risk_pts * 0.35    // = entry + 3.15 * risk_pts
tp2_price  = entry + 9.0 * risk_pts
be_price   = entry
```

**High R:R strategy**: TP2 is at 9R. Most trades that don't hit TP1 will stop out (-1R). The 31.6% win rate is expected — the winners are large.

### Exit

Apply shared exit logic with `flat_start = 13:30 ET`.

### Half Days

On early-close trading days, the session ends early. The half_days list:

```
20250109, 20250703, 20251128, 20251224, 20260119
```

On these days, consider moving flat time earlier (e.g., 13:00) to avoid thin liquidity. The Python backtester handles this via the `half_days` config field.

---

## Script 3 — ES Combined Longs (NY Final + Asia Final)

**File**: `ES_combined_longs.pine`
**Instrument**: ES (`CME_MINI:ES1!`, $50/point, 0.25 tick)

### Combined Parameter Tables

#### Strategy Parameters

| Param | NY (Final) | Asia (Final) |
|-------|-----------|-------------|
| strategy | continuation | continuation |
| direction | long only | long only |
| rr | 5.0 | 1.5 |
| tp1_ratio | 0.2 | 0.7 |
| atr_length | 7 | 14 |
| risk_usd | 5000 | 5000 |
| impulse_close_filter | **OFF** | **OFF** |
| DOW exclusion | **Thursday** | **None** |
| dual_floor | min_stop=3.0, min_tp1=3.0 | min_stop=3.0, min_tp1=3.0 |

#### Session Timing

| Param | NY (Final) | Asia (Final) |
|-------|-----------|-------------|
| ORB window | 09:30–09:45 (15m, 3 bars) | 20:00–20:15 (15m, 3 bars) |
| Entry window | 09:45–13:00 | 20:15–03:00 |
| Flat time | 15:50 | 07:00 |
| Flat end | 16:00 | 07:00 |

#### Stop & Gap Sizing

| Param | NY (Final) | Asia (Final) |
|-------|-----------|-------------|
| Stop basis | **ATR** | **ORB range** |
| stop_atr_pct | 5.0% | — (not used) |
| stop_orb_pct | — | 125.0% |
| Gap min basis | **ATR** | **ATR** |
| min_gap_atr_pct | 0.25% | 0.5% |
| Dual floor | 3.0 / 3.0 pts | 3.0 / 3.0 pts |

**Critical differences**:
- NY computes stop from ATR; Asia computes stop from the ORB range (125%).
- Both use ATR-based gap filters, but Asia uses ATR-14 while NY uses ATR-7.
- Asia's gap filter uses ATR (0.5%) unlike NQ Asia which uses ORB-based gap filter.

### ATR Computation

Two `request.security` calls needed:

```pine
// NY uses 7-period ATR (for stop AND gap filter)
daily_atr_7 = request.security(syminfo.tickerid, "D", ta.atr(7)[1], lookahead=barmerge.lookahead_on)

// Asia uses 14-period ATR (for gap filter ONLY — stop uses ORB range)
daily_atr_14 = request.security(syminfo.tickerid, "D", ta.atr(14)[1], lookahead=barmerge.lookahead_on)
```

The `[1]` + `lookahead_on` = "yesterday's ATR" — no look-ahead bias.

**Note**: Asia uses ATR-14 ONLY for the gap filter (`min_gap = 0.005 * daily_atr_14`). The stop is ORB-based (`1.25 * orb_range`). This is a hybrid setup — do not use ATR for Asia's stop.

---

### Session 1 — ES NY Long Final

**DB**: `ES NY Cont Long 2016-2026 Final`
**Pipeline**: CONDITIONAL (4/5). WF stability 0.893, WF eff 0.776. Holdout OOS (2025+): 101 trades, PF 1.55, Sharpe 2.83, +18.2R. MC survival 97.3% at -25R ruin.

#### Session Day Definition

Calendar date in ET. New session day starts at 09:30 ET.

#### Thursday Exclusion

Skip the entire NY session on Thursdays:

```pine
is_thursday = dayofweek == dayofweek.thursday  // == 5
```

If it's Thursday, no ORB, no signals, no trades for that day.

#### Step 1: ORB (09:30–09:45)

Three 5m candles: 09:30, 09:35, 09:40.

```pine
if bar_time >= 09:30 and bar_time < 09:45 and not is_thursday
    ny_orb_high := math.max(ny_orb_high, high)
    ny_orb_low  := math.min(ny_orb_low,  low)

ny_orb_ready = bar_time >= 09:45
```

Reset `ny_orb_high`, `ny_orb_low`, `ny_orb_ready`, `ny_long_pending`, `ny_trade_taken_today` at 09:30.

#### Step 2: Bullish FVG Detection (long only, NO ICF)

During entry window (09:45–13:00):

```pine
if bullish_fvg and ny_orb_ready and not is_thursday and not ny_trade_taken_today
    and fvg_top > ny_orb_high                          // above ORB (standard check)
    and gap_size >= 0.0025 * daily_atr_7               // min 0.25% of ATR-7
    → store ny_pending_long: entry_level = fvg_top
```

First FVG detected retains priority. One signal per session day.

#### Step 3: Limit Order Fill

```pine
if ny_long_pending and low <= ny_entry_level → FILL LONG at ny_entry_level
```

#### Step 4: Trade Parameters

```
stop_dist  = 0.05 * daily_atr_7                // 5.0% of ATR-7
stop_dist  = math.max(stop_dist, 3.0)          // dual floor: min 3.0 points
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_dist   = 5.0 * risk_pts * 0.2              // = 1.0 * risk_pts
tp1_dist   = math.max(tp1_dist, 3.0)           // dual floor: min 3.0 points
tp1_price  = entry + tp1_dist
tp2_price  = entry + 5.0 * risk_pts
be_price   = entry
```

**The stop is ATR-computed** — `stop = entry - 0.05 * daily_atr_7`, then clamped by dual floor (min 3.0 points). TP1 is also clamped. TP2 uses the original risk_pts (after stop floor).

#### Step 5: Exit

Apply shared exit logic with `flat_start = 15:50 ET`.

---

### Session 2 — ES Asia Long Final

**DB**: `ES Asia Cont Long 2016-2026 Final`
**Pipeline**: CONDITIONAL (4/5). WF stability 0.893, WF eff 0.834. Holdout OOS (2025+): 164 trades, PF 1.56, Sharpe 3.47, +37.6R. MC survival 89.7% at -25R ruin.

#### Session Day Definition

Asia session crosses midnight ET. Session day = the DATE of the 20:00 bar.

```pine
new_asia_session = (hour == 20 and minute == 0) and not (hour[1] == 20 and minute[1] == 0)
```

#### No DOW Exclusion

No day-of-week filter. All days are traded.

#### Step 1: ORB (20:00–20:15)

Three 5m candles: 20:00, 20:05, 20:10.

```pine
if bar_time >= 20:00 and bar_time < 20:15
    asia_orb_high := math.max(asia_orb_high, high)
    asia_orb_low  := math.min(asia_orb_low,  low)

asia_orb_ready = bar_time >= 20:15
asia_orb_range = asia_orb_high - asia_orb_low
```

Reset all Asia state at 20:00.

#### Step 2: Bullish FVG Detection (long only, NO ICF)

During entry window (20:15–03:00):

```pine
if bullish_fvg and asia_orb_ready and not asia_trade_taken_today
    and fvg_top > asia_orb_high                             // above ORB (standard check)
    and gap_size >= 0.005 * daily_atr_14                    // min 0.5% of ATR-14
    → store asia_pending_long: entry_level = fvg_top
```

**Gap filter is ATR-based** — `min_gap = 0.5% of ATR-14`. This differs from NQ Asia which uses ORB-based gap filter. The ATR-14 value is fetched from the daily `request.security` call.

#### Step 3: Limit Order Fill

```pine
if asia_long_pending and low <= asia_entry_level → FILL LONG at asia_entry_level
```

#### Step 4: Trade Parameters (HYBRID — ORB stop + ATR gap)

```
orb_range  = asia_orb_high - asia_orb_low
stop_dist  = 1.25 * orb_range                  // 125% of ORB range
stop_dist  = math.max(stop_dist, 3.0)          // dual floor: min 3.0 points
stop_level = entry - stop_dist
risk_pts   = stop_dist
tp1_dist   = 1.5 * risk_pts * 0.7              // = 1.05 * risk_pts
tp1_dist   = math.max(tp1_dist, 3.0)           // dual floor: min 3.0 points
tp1_price  = entry + tp1_dist
tp2_price  = entry + 1.5 * risk_pts
be_price   = entry
```

**The stop is ORB-based** — `stop = entry - 1.25 * orb_range`, NOT ATR. TP1 and TP2 are computed from the ORB-based risk_pts. The only ATR usage in Asia is the gap filter (Step 2).

#### Step 5: Exit

Apply shared exit logic with `flat_start = 07:00 ET`.

---

### ES Session Interaction Rules

1. **Independent state machines**: NY and Asia maintain completely separate state (ORB levels, pending signals, trade flags, exit tracking).
2. **No time overlap**: Asia flats at 07:00, NY starts at 09:30 — 2.5-hour gap. Sessions never hold positions simultaneously.
3. **TradingView single-position model**: Works correctly since positions never overlap.
4. **Defensive check**: If Asia position is somehow still open at NY start, suppress NY signals. Implement as: `if strategy.position_size != 0 and ny_orb_ready → skip NY signals`.
5. **Independent risk**: Each session risks $5,000/trade independently. On a day where both sessions trade, combined exposure is sequential (never simultaneous).
6. **Both long only**: Neither session takes short setups. No bearish FVG detection needed.

---

## Exit Types & R-Multiples

### NQ NY R11 (rr=3.5, tp1_ratio=0.4)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 × (3.5 × 0.4) + 0.5 × 3.5 = 0.7 + 1.75 = **+2.45R** |
| EXIT_TP1_BE | 0.5 × (3.5 × 0.4) = **+0.7R** |
| EXIT_TP2_SINGLE | **+3.5R** |

### NQ Asia R9 (rr=6.0, tp1_ratio=0.3)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 × (6.0 × 0.3) + 0.5 × 6.0 = 0.9 + 3.0 = **+3.9R** |
| EXIT_TP1_BE | 0.5 × (6.0 × 0.3) = **+0.9R** |
| EXIT_TP2_SINGLE | **+6.0R** |

### GC NY R3 (rr=9.0, tp1_ratio=0.35)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 × (9.0 × 0.35) + 0.5 × 9.0 = 1.575 + 4.5 = **+6.075R** |
| EXIT_TP1_BE | 0.5 × (9.0 × 0.35) = **+1.575R** |
| EXIT_TP2_SINGLE | **+9.0R** |

### ES NY Final (rr=5.0, tp1_ratio=0.2)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 × (5.0 × 0.2) + 0.5 × 5.0 = 0.5 + 2.5 = **+3.0R** |
| EXIT_TP1_BE | 0.5 × (5.0 × 0.2) = **+0.5R** |
| EXIT_TP2_SINGLE | **+5.0R** |

### ES Asia Final (rr=1.5, tp1_ratio=0.7)

| Exit | R-Multiple |
|------|------------|
| EXIT_SL | -1.0R |
| EXIT_TP1_TP2 | 0.5 × (1.5 × 0.7) + 0.5 × 1.5 = 0.525 + 0.75 = **+1.275R** |
| EXIT_TP1_BE | 0.5 × (1.5 × 0.7) = **+0.525R** |
| EXIT_TP2_SINGLE | **+1.5R** |

---

## Portfolio Execution Rules

### Risk Allocation

Each script risks $5,000/trade. Session time windows and overlaps:

| Session | Time Window (ET) | Instrument |
|---------|-----------------|------------|
| NQ Asia | 20:00–04:00 | NQ |
| ES Asia | 20:00–07:00 | ES |
| NQ NY | 09:50–15:30 | NQ |
| GC NY | 09:38–13:30 | GC |
| ES NY | 09:45–15:50 | ES |

#### Time Overlap Analysis

| Time Block (ET) | Active Legs | Max Simultaneous R |
|-----------------|-------------|-------------------|
| 20:00–04:00 | NQ Asia + ES Asia | 2R (different instruments) |
| 04:00–07:00 | ES Asia only | 1R |
| 07:00–09:30 | None | 0R |
| 09:30–13:00 | NQ NY + GC NY + ES NY | 3R (3 different instruments) |
| 13:00–13:30 | NQ NY + GC NY | 2R |
| 13:30–15:30 | NQ NY only | 1R |
| 15:30–15:50 | ES NY only | 1R |

Peak exposure: **3R during 09:30–13:00** when all three NY legs are active (NQ + GC + ES).

Overnight exposure: **2R during 20:00–04:00** when both Asia legs are active (NQ + ES, different instruments).

### Sizing for Combined Portfolio

| Leg | R/yr | Max DD | Calmar |
|-----|------|--------|--------|
| NQ NY R11 | 13.5 | -6.0R | 22.51 |
| NQ Asia R9 | 20.0 | -8.9R | 22.61 |
| GC NY R3 | 19.4 | -12.4R | 15.60 |
| ES NY Final | (from DB) | (from DB) | (from DB) |
| ES Asia Final | (from DB) | (from DB) | (from DB) |
| **Portfolio** | **85.5** | **-24.1R** | **35.47** |

ES NY Holdout OOS (2025+): 101 trades, PF 1.55, Sharpe 2.83, +18.2R. Pipeline CONDITIONAL (4/5). WF stability 0.893, WF eff 0.776. MC survival 97.3% at -25R ruin. DB: `ES NY Cont Long 2016-2026 Final`.

ES Asia Holdout OOS (2025+): 164 trades, PF 1.56, Sharpe 3.47, +37.6R. Pipeline CONDITIONAL (4/5). WF stability 0.893, WF eff 0.834. MC survival 89.7% at -25R ruin. DB: `ES Asia Cont Long 2016-2026 Final`.

Individual ES leg R/yr and Max DD are available from the DB runs. The combined portfolio totals (85.5 R/yr, -24.1R DD, Calmar 35.47) are from the `analyze_5leg_combined_longs.py` output.

### What Each Leg Contributes

- **NQ NY R11**: Highest win rate (53.3%). Consistent small winners. Moderate R:R. Strong equity trend-follower.
- **NQ Asia R9**: High R:R (6.0) with ORB-based stop. Uncorrelated with daytime sessions. Biggest single-leg R contributor.
- **GC NY R3**: True diversifier. Gold has near-zero correlation with NQ/ES. Extreme R:R (9.0). Low WR (31.6%) but massive winners.
- **ES NY Final**: High R:R (5.0) with ATR-based stop. Thursday exclusion. Adds US equity exposure on different instrument than NQ.
- **ES Asia Final**: Low R:R (1.5) but high WR with ORB-based stop. Complements NQ Asia with different instrument, providing additional overnight exposure.

### R by Year (Combined)

| Year | NQ NY | NQ Asia | GC NY | ES NY | ES Asia | **Combined** |
|------|-------|---------|-------|-------|---------|-------------|

(Note: exact year-by-year values per leg to be filled from `analyze_5leg_combined_longs.py` output. The combined portfolio totals 855.2R across 2016–2026, averaging 85.5 R/yr with 0 negative full years.)

### Correlation Notes

- NQ NY and NQ Asia trade NQ at different times — drawdowns can coincide on NQ macro moves.
- GC provides genuine diversification (different asset class).
- ES NY and NQ NY trade correlated indices (ES/NQ) during overlapping NY hours — some drawdown correlation expected.
- ES Asia and NQ Asia trade correlated indices overnight — similar correlation concern.
- Cross-asset diversification (NQ+GC+ES) is the primary risk reduction driver.

---

## Pine Script Pitfalls

### NQ Script

1. **Two ATR lengths**: NY uses ATR-12, Asia uses ATR-5 (though Asia doesn't use ATR for stop/gap — only for internal warmup). Maintain separate `request.security` calls.

2. **Different stop bases**: NY uses ATR-based stop (`0.07 * daily_atr_12`). Asia uses ORB-based stop (`1.00 * orb_range`). Do not mix these up — using the wrong base will produce completely different trade parameters.

3. **ORB-based gap filter for Asia**: Asia's minimum gap check is `gap_size >= 0.10 * orb_range`, NOT `0.009 * daily_atr`. The ORB range must be computed and available before gap filtering.

4. **Both sessions long only**: Neither takes short setups. No bearish FVG detection needed.

5. **Both sessions ICF OFF**: Standard ORB check only (`fvg_top > orb_high`). Do not use ICF-relaxed check for either NQ session.

6. **DOW exclusions differ**: NY excludes **Friday** (dayofweek == 6). Asia excludes **Tuesday** (dayofweek == 3). Each is session-specific.

7. **Entry window differs**: NY entries close at **12:00** (not 15:00 or 15:30). Asia entries close at **22:30**. The earlier NY entry cutoff is a key part of this config — extending to 15:00 changes the strategy character.

8. **Flat times differ**: NY flats at **15:30** (not 15:50). Asia flats at **04:00**.

9. **Cross-midnight Asia session**: The 20:00 bar opens tonight's session; 04:00 closes it. Use `var` flags for state across midnight.

10. **ORB windows differ**: NY uses 20 minutes (4 bars). Asia uses 15 minutes (3 bars).

11. **Entry starts one bar after signal bar**: The FVG is confirmed on bar[0]. The limit order becomes active on the NEXT bar.

12. **Same-bar SL+TP1 conflict**: SL always wins (conservative assumption).

13. **Half-open time intervals**: `[start, end)`. The 09:50 bar is the first bar of the NY entry window.

### GC Script

14. **ATR length = 7**: Much shorter than the 50 used in the GC inversion strategy. Use `ta.atr(7)`.

15. **ICF is ON for GC**: Unlike the NQ sessions, GC uses ICF-relaxed check: `fvg_top > orb_high OR close[1] > orb_high`.

16. **8-minute ORB on 5m chart**: Cannot perfectly capture 8m on 5m bars. Use 2-bar (10m) approximation or run on 1m chart.

17. **Early flat at 13:30**: Much earlier than typical NY sessions. This reflects GC's optimal exit timing — gold continuation works best in the first half of the NY session.

18. **FOMC exclusion**: Must maintain a list of FOMC dates and skip those days entirely. Update the list annually.

19. **Friday exclusion**: Same as NQ NY — skip Fridays.

20. **High R:R = low WR**: 9.0 R:R with 31.6% win rate is expected. Most trades stop out. The winners are 6–9R. Do not be alarmed by the low win rate.

21. **This is CONTINUATION, not inversion**: The GC strategy in this portfolio uses standard bullish FVG → limit buy. It is NOT the GC inversion stacked strategy from `GC_PINE_SPEC.md`. Do not confuse the two.

22. **No regime sizing**: Unlike the GC inversion strategy, this continuation strategy uses flat 1x sizing. No VIX/DXY overlay.

### ES Script

23. **Two ATR lengths for ES**: NY uses ATR-7 (for stop AND gap), Asia uses ATR-14 (for gap ONLY). Maintain separate `request.security` calls.

24. **Hybrid stop/gap on ES Asia**: Stop is ORB-based (`1.25 * orb_range`), but the gap filter is ATR-based (`0.005 * daily_atr_14`). Do NOT use ORB range for the gap filter or ATR for the stop.

25. **Dual floor clamping order**: Compute stop_dist from ATR/ORB first, THEN clamp to min 3.0 points. Same for tp1_dist — compute from rr × risk_pts × tp1_ratio first, THEN clamp to min 3.0. The floor is a lower bound, not a replacement.

26. **ES point_value = 50**: Not 20 (NQ) or 100 (GC). This affects position sizing.

27. **Thursday exclusion for ES NY**: `dayofweek == dayofweek.thursday  // == 5`. Different from NQ NY (Friday) and GC (Friday+FOMC).

28. **No DOW exclusion for ES Asia**: Unlike NQ Asia (Tuesday excl), ES Asia trades every day.

29. **Extended entry window for ES NY**: Entry ends at **13:00**, later than NQ NY (12:00) and GC (12:00). This is intentional — ES benefits from the longer window.

30. **Late flat for ES NY**: Flat at **15:50**, later than NQ NY (15:30) and GC (13:30). Only 10 minutes before the close.

31. **ES Asia flats at 07:00**: Later than NQ Asia (which flats at 04:00). This leaves a 2.5-hour gap before NY (vs NQ's 5.5-hour gap). Still no overlap, but the gap is tighter.

32. **Near-zero gap filter for ES NY**: `min_gap_atr_pct = 0.25%` is very small — nearly every FVG passes. This is intentional (the optimization found this optimal). Do not accidentally use 2.5% (which is the NQ NY value).

33. **Low R:R character of ES Asia**: rr=1.5 with tp1_ratio=0.7 means TP1 is at 1.05R and TP2 at 1.5R. This is a high-frequency, high-WR strategy. Most profitable exits are TP1_TP2 at +1.275R. Very different character from NQ Asia (rr=6.0) or GC (rr=9.0).

34. **ES Asia entry extends to 03:00**: Longer than NQ Asia (22:30). The broader entry window compensates for the lower R:R.

35. **Asia time overlap between NQ and ES**: Both NQ Asia (20:00–04:00) and ES Asia (20:00–07:00) are active overnight. This is on different instruments (different Pine scripts), so no TradingView conflict, but means 2R overnight exposure.

---

## Implementation Checklist

### Common (All Scripts)

- [ ] FVG detection uses `[0]`, `[1]`, `[2]` correctly (not `[1]`, `[2]`, `[3]`)
- [ ] Same-bar SL+TP1 conflict: SL wins
- [ ] Partial exit: `floor(qty/2)` at TP1
- [ ] BE stop moves to entry after TP1 (0 tick offset)
- [ ] `fill_orders_on_standard_ohlc = false` in strategy declaration
- [ ] Limit order active from bar AFTER FVG signal bar
- [ ] First FVG per session-day retains priority
- [ ] All time comparisons use half-open [start, end) intervals
- [ ] Long only — no bearish FVG detection

### NQ NY R11

- [ ] Friday exclusion (`dayofweek == 6`)
- [ ] ORB across four 5m candles (09:30–09:50)
- [ ] No ICF (standard ORB check only)
- [ ] Entry window 09:50–12:00
- [ ] Flat at 15:30
- [ ] ATR-12 for stop and gap filters
- [ ] `stop_dist = 0.07 * daily_atr_12`
- [ ] `min_gap = 0.025 * daily_atr_12`

### NQ Asia R9

- [ ] Tuesday exclusion (`dayofweek == 3`)
- [ ] Session day resets at 20:00 (cross-midnight with `var` flags)
- [ ] ORB across three 5m candles (20:00–20:15)
- [ ] No ICF (standard ORB check only)
- [ ] Entry window 20:15–22:30
- [ ] Flat at 04:00
- [ ] **ORB-based stop**: `stop_dist = 1.00 * orb_range`
- [ ] **ORB-based gap filter**: `min_gap = 0.10 * orb_range`
- [ ] ATR-5 declared but NOT used for stop/gap

### GC NY R3

- [ ] Friday exclusion (`dayofweek == 6`)
- [ ] FOMC date exclusion (array lookup)
- [ ] ORB across ~2 bars on 5m chart (09:30–09:38/09:40)
- [ ] ICF ON (`fvg_top > orb_high OR close[1] > orb_high`)
- [ ] Entry window 09:38/09:40–12:00
- [ ] Flat at 13:30
- [ ] ATR-7 for stop and gap filters
- [ ] `stop_dist = 0.045 * daily_atr_7`
- [ ] `min_gap = 0.03 * daily_atr_7`
- [ ] Half-day handling
- [ ] Position sizing uses `point_value = 100`

### ES NY Final

- [ ] Thursday exclusion (`dayofweek == 5`)
- [ ] ORB across three 5m candles (09:30–09:45)
- [ ] No ICF (standard ORB check only)
- [ ] Entry window 09:45–13:00
- [ ] Flat at 15:50
- [ ] ATR-7 for stop and gap filters
- [ ] `stop_dist = 0.05 * daily_atr_7`
- [ ] `min_gap = 0.0025 * daily_atr_7`
- [ ] Dual floor: `stop_dist = max(stop_dist, 3.0)`
- [ ] Dual floor: `tp1_dist = max(tp1_dist, 3.0)`
- [ ] Position sizing uses `point_value = 50`

### ES Asia Final

- [ ] No DOW exclusion (trades every day)
- [ ] Session day resets at 20:00 (cross-midnight with `var` flags)
- [ ] ORB across three 5m candles (20:00–20:15)
- [ ] No ICF (standard ORB check only)
- [ ] Entry window 20:15–03:00
- [ ] Flat at 07:00
- [ ] **ORB-based stop**: `stop_dist = 1.25 * orb_range`
- [ ] **ATR-based gap filter**: `min_gap = 0.005 * daily_atr_14` (NOT ORB-based)
- [ ] Dual floor: `stop_dist = max(stop_dist, 3.0)`
- [ ] Dual floor: `tp1_dist = max(tp1_dist, 3.0)`
- [ ] Position sizing uses `point_value = 50`
- [ ] ATR-14 used for gap filter only, NOT for stop

---

## Notes

- All times are America/New_York (Eastern).
- All time windows are half-open [start, end).
- A bar's time is its open time (the 09:30 bar represents 09:30–09:35).
- This is the 5-leg version of the combined longs portfolio. The original 3-leg version (NQ+GC only) is documented in `COMBINED_LONGS_PINE_SPEC.md`.
- The GC strategy here is **continuation**, NOT the **inversion** documented in `GC_PINE_SPEC.md`.
- The NQ configs here (R11 + R9) differ from `NQ_COMBINED_PINE_SPEC.md` (which documents R20 + R9 Restart with different parameters).
- ES configs are from `save_es_ny_long_final.py` and `save_es_asia_long_r1_final.py`.
