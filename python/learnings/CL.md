# CL (Crude Oil Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $1,000/point
- **Min tick**: 0.01
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2025-12 (~10 years, 5m + 1m)
- **Liquidity**: Tradeable in NY, LDN, and Asia sessions. Asia is the weakest.

## Strategies Tested

### Continuation (default, bullish FVG -> long, bearish FVG -> short)
- **Status**: NO-GO for prop firm
- **Best ungated results** (rr=3.5, tp1=0.5, stop_atr=1.5, min_gap_atr=3.0, 1m magnifier):

| Session | Trades | WR | Net R | Max DD | Sharpe | PF |
|---------|--------|----|-------|--------|--------|----|
| NY | 2,024 | 37.3% | 168.2R | -45.1R | 0.89 | 1.12 |
| Asia | 1,034 | 39.8% | 87.1R | -27.8R | 1.22 | 1.13 |
| LDN | 2,119 | 42.9% | 455.9R | -34.1R | 2.23 | 1.42 |

- **With SMA20 trend gate** (same params):

| Session | Trades | WR | Net R | Max DD | Sharpe | PF |
|---------|--------|----|-------|--------|--------|----|
| NY | 992 | 38.7% | 224.4R | -27.4R | 2.09 | 1.37 |
| Asia | 460 | 41.3% | 126.0R | -18.8R | 2.59 | 1.46 |
| LDN | 1,053 | 44.8% | 408.0R | -20.0R | 3.14 | 1.70 |

- SMA20 gate filters ~50% of trades, cuts DD 30-40%, doubles Sharpe across all sessions.

#### DD Reduction Sweep (SMA20 gated, rr × tp1 × min_gap_atr)

Swept rr=[2.0-3.5], tp1=[0.4-0.7], min_gap_atr=[3.0-6.0] (64 combos per session).

**NY best by DD**: rr=2.0, tp1=0.40, gap=5.0 — 793 trades, 59.6% WR, 81.7R, **-11.8R DD**, Sharpe 1.77
- DB: `bt-cl-ny-sma20-rr2-gap5-optimized-ff72f8`

**LDN best by DD**: rr=2.0, tp1=0.60, gap=6.0 — 635 trades, 49.3% WR, 49.7R, **-11.6R DD**, Sharpe 1.20
- DB: `bt-cl-ldn-sma20-rr2-tp60-gap6-optimized-4e73b8`

**Asia**: Barely breaks even at best (22.7R with rr=2.0, gap=4.0). Goes negative at gap>=5.0. Drop this session.

#### Key Sweep Findings
- **gap filter is the dominant DD lever** — moving from 3.0→6.0 cuts DD roughly in half
- **rr=2.0 safest** — more trades close at TP2 instead of reverting to BE
- **tp1_ratio has less impact** than rr or gap on DD
- LDN more sensitive to gap filter than NY (gap=3.0 produces -25 to -53R DD on LDN)

### ORB Window Duration
- **Status**: 15m ORB is definitively best for CL
- **Tested**: 5m, 10m, 15m (default) across NY, Asia, LDN with SMA20 gate

| Session | ORB | Trades | Net R | Max DD | Sharpe | PF |
|---------|-----|--------|-------|--------|--------|----|
| NY | 5m | 1,113 | 119.3R | -19.4R | 1.45 | 1.22 |
| NY | 10m | 1,070 | 114.7R | -13.2R | 1.45 | 1.22 |
| NY | **15m** | 992 | **224.4R** | -27.4R | **2.09** | **1.37** |
| LDN | 5m | 1,198 | 18.6R | -38.7R | 0.22 | 1.03 |
| LDN | 10m | 1,177 | 64.4R | -19.4R | 0.76 | 1.11 |
| LDN | **15m** | 1,053 | **408.0R** | -20.0R | **3.14** | **1.70** |
| Asia | 5m | 990 | -16.3R | -49.8R | -0.23 | 0.97 |
| Asia | 10m | 943 | 0.9R | -43.0R | 0.01 | 1.00 |
| Asia | **15m** | 460 | **126.0R** | -18.8R | **2.59** | **1.46** |

- Shorter ORB windows produce more trades but dramatically worse edge
- 15m generates 2-3x the Net R of 5m and 10m
- CL needs the full 15 minutes to establish a meaningful range — shorter windows pick up noise
- NY 10m has the best DD (-13.2R) but half the Net R of 15m

## What Works on CL
- **15-minute ORB** — Shorter windows degrade edge significantly
- **SMA20 trend gate** — Consistently improves all risk-adjusted metrics by filtering counter-trend trades
- **Higher gap filter (5.0-6.0)** — Most effective DD reduction lever
- **Lower RR (2.0-2.5)** — More TP2 fills, fewer reversions to BE
- **LDN session** — Strongest raw performance (408R over 10 years with SMA20 gate at default params)

## What Doesn't Work on CL
- **Asia session** — Weak edge at all param combos and ORB durations. Negative at shorter ORB windows. Drop.
- **Short ORB windows (5m, 10m)** — Not enough time to form a meaningful range on CL
- **High RR (3.0+) with low gap filter** — DD explodes, especially on LDN (-50 to -73R)

## Why CL Is Marginal for Prop
- Best optimized DD (-11.6 to -11.8R) still exceeds the 8-10R prop firm breach threshold
- Post-2020 average return is ~7-8R/year per session — poor payoff ratio vs DD risk
- Avg R per trade is tiny (0.08-0.10R) — minimal margin for real-world slippage
- LDN had a -7.7R year in 2024; one more bad week = breach
- Compare to NQ production: ~30R/yr, proven WF track record. CL gives 1/4 the return for similar risk.

## Parameter Sensitivity
- **min_gap_atr_pct**: Most impactful DD lever. 5.0-6.0 optimal.
- **rr**: 2.0 safest for DD. Higher RR (3.0+) increases Net R but DD grows faster.
- **tp1_ratio**: 0.4-0.6 all similar. Less impact than rr or gap.
- **stop_atr_pct**: Default (7.5 NY) used in sweep. Tighter (1.5) significantly degrades results.
- **ORB window**: 15m is definitively best. 5m and 10m produce noise.
- **SMA period**: Only SMA20 tested. Further SMA period sweep not conducted.

## Prop Firm Considerations
- At best DD of -11.6R, CL does not clear the 8-10R prop breach threshold
- ~80 trades/year (best configs) — moderate frequency
- Would need further DD reduction (filters, reduced sizing) to be viable
- Time may be better spent on assets with structural edge (GC inversion, NQ continuation)

## Outstanding Questions
- Reversal and inversion strategies not yet tested on CL
- Could a volatility regime filter (e.g., VIX or ATR regime) improve post-2020 performance?
- Multi-session combined (NY+LDN) not tested — could diversification help DD?
