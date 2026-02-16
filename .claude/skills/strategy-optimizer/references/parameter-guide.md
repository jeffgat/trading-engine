# Parameter Guide

All sweepable parameters in the ORB+FVG engine, with recommended sweep ranges and notes on sensitivity.

## Strategy-Level Parameters

These apply globally across all sessions.

| Parameter | Type | Default | Sweep Range | Notes |
|-----------|------|---------|-------------|-------|
| `rr` | float | 2.5 | 1.5 - 4.0 (step 0.5) | Reward-to-risk ratio. Higher = fewer wins but larger. Core param — always include in sweeps |
| `tp1_ratio` | float | 0.5 | 0.3 - 0.7 (step 0.1) | Fraction of position exited at TP1. Higher = more locked in early |
| `risk_usd` | float | 5000 | 2000 - 10000 | Dollar risk per trade. Affects position sizing but NOT win rate or Sharpe |
| `be_offset_ticks` | int | 4 | 2 - 8 (step 2) | Ticks above/below entry for breakeven stop. Too tight = stopped out on noise |
| `atr_length` | int | 14 | 10 - 20 (step 2) | ATR lookback period. Lower = more responsive, higher = smoother |

## Session-Level Parameters

These are prefixed by session name in CLI/sweeps (e.g., `ny_stop_atr_pct`).

| Parameter | Session Prefix | Default (NY/Asia/LDN) | Sweep Range | Notes |
|-----------|---------------|----------------------|-------------|-------|
| `stop_atr_pct` | `ny_`, `asia_`, `ldn_` | 7.5 / 5.25 / 10.0 | 3 - 25 (step 2.5) | Stop distance as % of daily ATR. Most impactful filter param |
| `min_gap_atr_pct` | `ny_`, `asia_`, `ldn_` | 2.25 / 0.9 / 1.0 | 0.5 - 4.0 (step 0.25) | Minimum FVG size as % of ATR. Filters out tiny gaps |
| `max_gap_points` | `ny_`, `asia_`, `ldn_` | 100 / 50 / 50 | 25 - 150 (step 25) | Maximum FVG size in points. Filters out enormous gaps |

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
--sweep rr=2.0:3.5:0.5 --sweep tp1_ratio=0.3:0.7:0.1 --sweep be_offset_ticks=2,4,6
```
60 combinations — explores the TP/BE tradeoff space.

### Cross-session comparison
Run the same sweep separately for each session to compare behavior:
```bash
--sessions ny --sweep ny_stop_atr_pct=5:20:5
--sessions asia --sweep asia_stop_atr_pct=3:15:3
```

## Parameter Interaction Notes

- **`stop_atr_pct` and `rr` are coupled**: Wider stops with high R:R means very distant targets — fewer TP2 hits. Sweep them together.
- **`min_gap_atr_pct` filters trade count**: High values = fewer but potentially higher-quality setups. Check total trades doesn't drop below ~50 for statistical significance.
- **`max_gap_points` is instrument-dependent**: NQ moves more points than ES. A 100-point max gap on NQ is equivalent to ~40 on ES in relative terms.
- **`tp1_ratio` interacts with `rr`**: Higher tp1_ratio with low rr locks in small wins. Higher tp1_ratio with high rr captures meaningful partial profits.
- **`be_offset_ticks` is noise-sensitive**: On NQ (tick = $5), 2 ticks of offset means breakeven stop is just $10 from entry — easily hit by noise.
