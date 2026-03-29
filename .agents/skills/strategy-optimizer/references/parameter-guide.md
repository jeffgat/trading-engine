# Parameter Guide

All sweepable parameters in the ORB+FVG engine, with recommended sweep ranges and notes on sensitivity.

## Primary Optimization Objective: Calmar

**Always rank results by Calmar ratio (Avg Annual R ÷ |Max DD R|) first.**

Absolute drawdown in R is NOT a hard filter. Position sizing handles dollar DD — if a strategy has -15R DD and 15 R/yr, that's Calmar 1.0, identical to -10R DD and 10 R/yr at 2/3 position size. What can't be fixed by sizing is a low Calmar.

**Optimization priority order:**
1. **Calmar** — primary objective, always
2. **0 negative full years** — consistency across all full calendar years
3. **Sharpe** — secondary; useful for walk-forward objective
4. **Net R / Avg Annual R** — only meaningful relative to DD (i.e., as Calmar)

Do NOT apply a fixed DD threshold (e.g., "must be < 10R") as a hard filter during sweeps. Report DD alongside Calmar so the user can set position size accordingly.

---

## Strategy-Level Parameters

These apply globally across all sessions.

| Parameter | Type | Default | Sweep Range | Notes |
|-----------|------|---------|-------------|-------|
| `rr` | float | 2.5 | 1.5 - 5.0 (step 0.5) | Reward-to-risk ratio. Higher = fewer wins but larger. Core param — always include in sweeps. Optimal value is highly instrument-dependent (see profiles below) |
| `tp1_ratio` | float | 0.5 | 0.15 - 0.7 (step 0.05 or 0.1) | Fraction of position exited at TP1. Higher = more locked in early. GC WF consistently prefers 0.15-0.2; NQ/CL: 0.4-0.6 all similar |
| `risk_usd` | float | 5000 | 2000 - 10000 | Dollar risk per trade. Affects position sizing but NOT win rate or Sharpe |

| `atr_length` | int | 14 | 10 - 50 (step 5-10) | ATR lookback period. Lower = more responsive, higher = smoother. Default 14 works for NQ/ES. GC benefits from 50 (smoother volatility on gold). Test 14 vs 30 vs 50 when exploring a new instrument |
| `strategy` | str | continuation | continuation, reversal, inversion | Strategy type. Not a sweep param — choose based on instrument learnings. Reversal is NO-GO on all tested instruments. Inversion only works on GC (longs). |
| `direction_filter` | str | None | long, short, None | Direction filter. GC is long-only (shorts structurally broken). Check learnings before assuming both directions contribute — test long-only and short-only separately first. |

## Session-Level Parameters

These are prefixed by session name in CLI/sweeps (e.g., `ny_stop_atr_pct`).

| Parameter | Session Prefix | Default (NY/Asia/LDN) | Sweep Range | Notes |
|-----------|---------------|----------------------|-------------|-------|
| `stop_atr_pct` | `ny_`, `asia_`, `ldn_` | 7.5 / 5.25 / 10.0 | 3 - 25 (step 2.5) | Stop distance as % of daily ATR. Most impactful filter param. Low-volatility instruments (6B) need wider stops (15%+) — tight stops get clipped by noise |
| `min_gap_atr_pct` | `ny_`, `asia_`, `ldn_` | 2.25 / 0.9 / 1.0 | 0.5 - 6.0 (step 0.25-0.5) | Minimum FVG size as % of ATR. Filters out tiny gaps. On CL this is the dominant DD lever — moving from 3.0→6.0 cuts DD roughly in half |
| `max_gap_points` | `ny_`, `asia_`, `ldn_` | 100 / 50 / 50 | 25 - 150 (step 25) | Maximum FVG size in points. Filters out enormous gaps. Highly instrument-dependent — GC FVGs all land under 20 pts (non-binding above 25). NQ needs 50-150 range |
| `qualifying_move_atr_pct` | `ny_`, `asia_`, `ldn_` | 0 (disabled) | 0 - 25 (step 5) | Inversion strategy only. Minimum sweep distance below ORB (as % of ATR) required before accepting an inversion signal. Filters shallow/fake sweeps. GC sweet spot is 10% for longs — removes ~9 weak trades, adds 0.3R with no DD cost. Beyond 15% trade count drops too fast. |

## Time Window Parameters

Not swept via `--sweep` CLI — set directly via session config. Worth testing manually when exploring a new instrument.

| Parameter | Default | Tested Range | Notes |
|-----------|---------|-------------|-------|
| ORB window duration | 15 min | 3 - 30 min | **Highly instrument-dependent**. GC: 3-5 min identical, 7+ degrades (use 5 min). CL: 15 min definitively best — 5m/10m produce noise, 15m generates 2-3x Net R. 6B: 30 min required — default 15 min is unprofitable. Always test ORB duration early. |
| `entry_end` | varies | 11:00 - 15:00 | GC shows monotonic improvement extending later (11:00→15:00). Later entries pull their weight — adding 15 trades and 7.9R with no DD increase on GC. |
| `flat_start` | varies | 14:00 - 15:50 | Later is always better. 15:50 optimal on GC. Gives trades more time to reach TP2. |
| `entry_start` | varies | 09:35 - 10:00 | Baseline (09:35) generally has best DD. Later starts trade DD for per-trade quality. GC: early trades (09:35-10:00) are actually the strongest segment at 73.3% WR regardless of VIX. |

## Sweep Spec Syntax

Two formats supported by the CLI:

```bash
# Range: param=start:stop:step
--sweep ny_stop_atr_pct=5:25:2.5

# Explicit values: param=val1,val2,val3
--sweep rr=1.5,2.0,2.5,3.0
```

## Grid Size Guidelines

| Combinations | Estimated Time (4 workers, NQ 10yr) | Recommendation |
|-------------|-------------------------------------|----------------|
| < 50 | ~2-5 min | Fine for quick exploration |
| 50-200 | ~5-20 min | Good for focused 2-param sweeps |
| 200-500 | ~20-60 min | Acceptable for 3-param sweeps |
| > 500 | 1+ hours | Consider narrowing ranges first |

## Common Sweep Recipes

### Quick stop ATR exploration (NY)
```bash
--sweep ny_stop_atr_pct=5:20:2.5
```
9 combinations — good first pass.

### Stop + R:R grid (NY)
```bash
--sweep ny_stop_atr_pct=5:20:2.5 --sweep rr=1.5,2.0,2.5,3.0
```
36 combinations — the classic 2-param sweep.

### Full filter sweep (NY)
```bash
--sweep ny_stop_atr_pct=5:20:5 --sweep ny_min_gap_atr_pct=1.0:3.0:0.5 --sweep ny_max_gap_points=50,75,100
```
60 combinations — 3-param sweep covering all filter dimensions.

### Exit management sweep
```bash
--sweep rr=2.0:3.5:0.5 --sweep tp1_ratio=0.3:0.7:0.1
```
20 combinations — explores the R:R / TP1 tradeoff space.

### DD reduction sweep (CL-style)
```bash
--sweep rr=2.0,2.5,3.0,3.5 --sweep tp1_ratio=0.4,0.5,0.6,0.7 --sweep ny_min_gap_atr_pct=3.0:6.0:1.0
```
64 combinations — targets drawdown reduction. `min_gap_atr_pct` is the dominant DD lever on CL.

### Cross-session comparison
Run the same sweep separately for each session to compare behavior:
```bash
--sessions ny --sweep ny_stop_atr_pct=5:20:5
--sessions asia --sweep asia_stop_atr_pct=3:15:3
```

## Parameter Interaction Notes

- **`stop_atr_pct` and `rr` are coupled**: Wider stops with high R:R means very distant targets — fewer TP2 hits. Sweep them together.
- **`min_gap_atr_pct` filters trade count**: High values = fewer but potentially higher-quality setups. Check total trades doesn't drop below ~50 for statistical significance. On CL, this is the strongest DD lever — prioritize sweeping it.
- **`max_gap_points` is instrument-dependent**: NQ moves more points than ES. A 100-point max gap on NQ is equivalent to ~40 on ES in relative terms. On GC, all FVGs land under 20 points — set to 20-25 and don't sweep.
- **`tp1_ratio` interacts with `rr`**: Higher tp1_ratio with low rr locks in small wins. Higher tp1_ratio with high rr captures meaningful partial profits.

- **`qualifying_move_atr_pct` interacts with trade count**: Higher values = stronger signal quality but fewer trades. On GC, 10% removes only 9 trades while filtering out all shallow sweeps. Above 15%, trade count drops fast for diminishing returns.
- **`rr` is instrument-dependent**: NQ production uses 3.25. GC WF locks on 3.5. CL: 2.0 is safest for DD (more TP2 fills). 6B needs 4.0+ for positive expectancy.
- **ORB duration is the most instrument-sensitive param**: GC=5min, CL=15min, 6B=30min. Always test ORB duration early — wrong ORB can make an instrument appear non-viable when it isn't.
- **Direction filtering matters**: Always test long-only and short-only separately before assuming both directions contribute. GC shorts are structurally broken (-98R to -292R). NQ Asia long-only outperforms both-directions. YM NY short-only is "least bad."

## Instrument-Specific Parameter Profiles

Established parameter preferences from learnings. Check `python/learnings/{INSTRUMENT}.md` for full context.

### GC (Gold) — Inversion longs only
| Param | Optimal | Notes |
|-------|---------|-------|
| strategy | inversion | Only viable strategy. Continuation/reversal/CISD all NO-GO |
| direction | long only | Shorts structurally broken across all strategy types |
| rr | 3.5 | WF stable across folds |
| tp1_ratio | 0.2 | WF prefers 0.15-0.2 (lock in early) |
| atr_length | 50 | Longer is better — smooths gold's volatility spikes |
| stop_atr_pct | 9.0 | WF locks on 9.0 |
| min_gap_atr_pct | 1.0 | Stable |
| max_gap_points | 25.0 | Non-binding — all GC FVGs under 20 pts |
| qualifying_move_atr_pct | 10.0 | Sweet spot. Beyond 15% trades drop too fast |
| ORB window | 5 min | 3-5 min identical. 7+ min degrades |
| entry_end | 15:00 | Later is monotonically better |
| flat_start | 15:50 | Later is always better |
| Sessions | NY only | Asia/LDN too illiquid (~1 bar/hr) |

### CL (Crude Oil) — Continuation with SMA20 gate
| Param | Optimal | Notes |
|-------|---------|-------|
| strategy | continuation | Reversal/inversion not yet tested |
| rr | 2.0 | Safest for DD. Higher RR increases Net R but DD grows faster |
| tp1_ratio | 0.4-0.6 | Low sensitivity |
| min_gap_atr_pct | 5.0-6.0 | Dominant DD lever. 3.0→6.0 cuts DD ~50% |
| ORB window | 15 min | Definitively best. 5m/10m produce noise |
| Sessions | NY, LDN | Asia too weak. LDN strongest raw performance |
| Gate | SMA20 trend | Halves trades, doubles Sharpe, cuts DD 30-40% |

### 6B (British Pound) — Inversion, 30-min ORB
| Param | Optimal | Notes |
|-------|---------|-------|
| strategy | inversion | Continuation/reversal/CISD all NO-GO |
| rr | 4.0-5.0 | WF selects 5.0 in 3/7 folds. Below 3.0 consistently negative |
| stop_atr_pct | 15.0 | Widest tested. Low-vol instrument needs wide stops |
| min_gap_atr_pct | 0.5-1.5 | Mode 1.0. Stability 1.00 |
| ORB window | 30 min | Required. Default 15 min is unprofitable |
| Sessions | LDN only | Primary session for GBP/USD |
| Status | NO-GO (prop) | DD -17.8R OOS. Viable only for personal accounts |

### NQ (Nasdaq) — Continuation
| Param | Optimal | Notes |
|-------|---------|-------|
| strategy | continuation | Production strategy |
| rr | 3.25 (NY) / 2.0 (Asia) | Per-session optimization |
| tp1_ratio | 0.55 (NY) / 0.4 (Asia) | Per-session optimization |
| stop_atr_pct | 6.75 (NY) / 4.75 (Asia) | Tighter than defaults |
| min_gap_atr_pct | 2.5 (NY) / 3.0 (Asia) | Higher than defaults |
| Sessions | NY + Asia | Both viable. Asia high volume but thin edge |

### YM (Dow Jones) — NO-GO
All strategy/session/direction combinations tested. None viable for prop firm. Best variant (NY short continuation) still -19R DD on WF OOS. Do not optimize — test a different instrument instead.
