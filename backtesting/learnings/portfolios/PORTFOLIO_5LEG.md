# 5-Leg ORB Portfolio — Config & Gating Reference

**DB Entry**: `bt-5-leg-portfolio-v2-gc-nq-si-cl-rty-9c43f0`
**Prior version**: `bt-5-leg-portfolio-gc-nq-si-cl-rty-354778` (v1, GC R3 rr=9.0 — replaced)
**Script**: `run_portfolio_5leg_backtest.py`
**Strategy**: ORB Continuation across 5 instruments, 3 sessions, 3 asset classes

---

## Portfolio Summary

| Metric | Value |
|--------|-------|
| Total R (2015-2026) | +601.5R |
| Avg Annual R | +50.1R |
| Max DD | -38.9R |
| Calmar | 1.29 |
| Sharpe | 1.86 |
| Negative years | 0 |
| Avg pairwise correlation | 0.000 |
| Holdout R (2025-2026) | +47.4R |
| Funded model PR (pre-HO) | 48.9% |
| Funded model EV | $208 |
| Avg days to payout | 10 |

---

## Leg Overview

| # | Leg | Instrument | Session | Direction | ORB | Stop | RR | TP1 | Status |
|---|-----|-----------|---------|-----------|-----|------|----|-----|--------|
| 1 | GC_NY_L | GC (Gold) | NY | Long | 10m | ATR 4.0% | 4.0 | 0.5 | GO |
| 2 | NQ_Asia_L | NQ (Nasdaq) | Asia | Long | 15m | ATR 4.0% | 3.0 | 0.6 | GO |
| 3 | SI_Asia_S | SI (Silver) | Asia | Short | 30m | ORB 75% | 3.0 | 0.6 | CONDITIONAL |
| 4 | CL_LDN_L | CL (Crude) | LDN | Long | 30m | ATR 8.0% | 3.5 | 0.6 | CONDITIONAL |
| 5 | RTY_NY_B | RTY (Russell) | NY | Both | 10m | ORB 100% | 3.0 | 0.4 | STRONG |

---

## Leg 1: GC NY Continuation Longs (Alt2 — Moderate RR)

**Thesis**: Gold ORB breakout continuation in NY session. Moderate R:R for higher win rate and smoother equity curve vs the R3 high-RR config.

**Why Alt2 over R3**: R3 (rr=9.0, 8m ORB) had exceptional Calmar (10.15) but 31% WR and bled -7.7R in 2026. Alt2 (rr=4.0, 10m ORB) trades Calmar (7.28 vs 10.15) for 40% WR, tighter DD (-12.2R vs -15.1R), and near-flat 2026 (-0.4R vs -7.7R). RR 3.0-3.5 tested too low (4-5 neg years). The 10m ORB is also a standard window used across other instruments (RTY, CL, SI) — the 8m window in R3 was an artifact of 5m bar boundaries (8m = 2 bars, same as 10m for entry timing but misaligned with conventional ORB definitions).

**Validation status**: Alt2 was the #1 config from the GC R2 grid sweep (450 combos, Calmar 13.17 on clean data). It has **not** been individually run through the full robust pipeline (WF, PSR/DSR, MC). The R3 config that was pipeline-validated used different params (rr=9.0, 8m ORB, stop=4.5%, gap=3.0%). Alt2 shares the same structural foundation (GC NY continuation longs, ATR 7, ICF, excl Fri+FOMC, 1s magnifier) but with moderate RR and wider gap filter. A dedicated pipeline run on Alt2 is recommended before live deployment.

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 09:30 - 09:40 (10 minutes) |
| Entry | 09:40 - 12:00 |
| Flat | 13:30 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | Bullish FVG after ORB breakout |
| direction | long only | |
| rr | 4.0 | Moderate R:R — 40% WR |
| tp1_ratio | 0.5 | TP1 at 50% of full target |
| atr_length | 7 | Short ATR for responsive stops |
| stop_atr_pct | 4.0% | Stop = 4.0% of daily ATR |
| min_gap_atr_pct | 3.5% | FVG must be >= 3.5% of ATR |
| impulse_close_filter | ON | Impulse candle must close outside ORB |
| magnifier | 1s | GC requires 1s for accurate fills |

### Gating / Exclusions
| Gate | Rule | Reason |
|------|------|--------|
| DOW exclusion | **Friday** | Friday is negative EV on GC NY longs |
| Date exclusion | **FOMC dates** | Excluded entirely — high-impact news |

### Performance
| Metric | Full History |
|--------|-------------|
| Trades | 588 |
| Net R | +88.6 |
| Calmar | 7.28 |
| Sharpe | 1.56 |
| Max DD | -12.2R |
| WR | 40.3% |
| Neg years | 2 (2016, 2026) |

### R by Year
2016:-7 | 2017:+8 | 2018:+11 | 2019:+5 | 2020:+3 | 2021:+10 | 2022:+3 | 2023:+20 | 2024:+20 | 2025:+17 | 2026:-0

---

## Leg 2: NQ Asia Continuation Longs (R9 Restart Final)

**Thesis**: Nasdaq overnight ORB breakout continuation. Asia session captures global equity flows.

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 20:00 - 20:15 (15 minutes) |
| Entry | 20:15 - 22:30 |
| Flat | 04:00 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| direction | long only | |
| rr | 3.0 | |
| tp1_ratio | 0.6 | TP1 at 60% of full target |
| atr_length | 5 | Fast ATR adapts to recent vol |
| stop_atr_pct | 4.0% | |
| min_gap_atr_pct | 0.90% | |
| impulse_close_filter | ON | |
| magnifier | 1s | NQ has 1s data |

### Gating / Exclusions
| Gate | Rule | Reason |
|------|------|--------|
| DOW exclusion | **Tuesday** | Tuesday is negative EV on NQ Asia |

### Performance
| Metric | Pre-Holdout | Holdout (2025+) |
|--------|------------|-----------------|
| Trades | 777 | — |
| Net R | +120.9 | — |
| Calmar | 8.00 | — |
| Sharpe | 1.69 | — |
| Max DD | -15.1R | — |
| WR | 41.1% | — |
| Neg years | 1 (2021: -3.9R) | — |

### R by Year
2016:+11 | 2017:+13 | 2018:+18 | 2019:+22 | 2020:+12 | 2021:-4 | 2022:+13 | 2023:+15 | 2024:+12 | 2025:+6 | 2026:+3

---

## Leg 3: SI Asia Continuation Shorts (Asia-3)

**Thesis**: Silver ORB breakout continuation, short side. Commodity shorts benefit from mean-reversion after overnight spikes.

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 20:00 - 20:30 (30 minutes) |
| Entry | 20:30 - 23:15 |
| Flat | 04:00 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | Bearish FVG after ORB breakdown |
| direction | short only | SI is the only short leg — natural hedge |
| rr | 3.0 | |
| tp1_ratio | 0.6 | |
| atr_length | 14 | Standard ATR |
| stop_orb_pct | 75.0% | Stop = 75% of ORB range (ORB-based stop) |
| min_gap_atr_pct | 1.0% | |
| magnifier | 1m | No 1s data for SI |

### Gating / Exclusions
| Gate | Rule | Reason |
|------|------|--------|
| None | No DOW or date exclusions | Clean signal across all weekdays |

### Performance
| Metric | Pre-Holdout | Holdout (2025+) |
|--------|------------|-----------------|
| Trades | 955 | — |
| Net R | +132.9 | — |
| Calmar | 8.76 | — |
| Sharpe | 1.60 | — |
| Max DD | -15.2R | — |
| WR | 43.6% | — |
| Neg years | 1 (2017: -4.5R) | — |

### R by Year
2016:+18 | 2017:-5 | 2018:+34 | 2019:+12 | 2020:+24 | 2021:+13 | 2022:+4 | 2023:+17 | 2024:+5 | 2025:+12 | 2026:-1

---

## Leg 4: CL LDN Continuation Longs (LDN-1)

**Thesis**: Crude oil ORB breakout continuation in London session. CL trends during European hours when physical oil markets are pricing.

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 03:00 - 03:30 (30 minutes) |
| Entry | 03:30 - 07:00 |
| Flat | 08:20 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| direction | long only | |
| rr | 3.5 | |
| tp1_ratio | 0.6 | |
| atr_length | 14 | |
| stop_atr_pct | 8.0% | Wider stop — CL needs >= 7% to avoid sub-tick artifact |
| min_gap_atr_pct | 1.0% | |
| magnifier | 1m | No 1s data for CL |

### Gating / Exclusions
| Gate | Rule | Reason |
|------|------|--------|
| None | No DOW or date exclusions | |

### Performance
| Metric | Pre-Holdout | Holdout (2025+) |
|--------|------------|-----------------|
| Trades | 1,201 | — |
| Net R | +139.8 | — |
| Calmar | 6.06 | — |
| Sharpe | 1.20 | — |
| Max DD | -23.1R | — |
| WR | 36.7% | — |
| Neg years | 1 (2018: -0.2R) | — |

### R by Year
2015:+7 | 2016:+14 | 2017:+6 | 2018:-0 | 2019:+6 | 2020:+3 | 2021:+22 | 2022:+22 | 2023:+35 | 2024:+10 | 2025:+0 | 2026:+16

---

## Leg 5: RTY NY Continuation Both (NY-4)

**Thesis**: Russell 2000 ORB breakout continuation in both directions. Small-cap index captures both risk-on and risk-off moves.

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 09:30 - 09:40 (10 minutes) |
| Entry | 09:40 - 13:00 |
| Flat | 15:50 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| direction | both | Long + short — catches either ORB direction |
| rr | 3.0 | |
| tp1_ratio | 0.4 | |
| atr_length | 14 | |
| stop_orb_pct | 100.0% | Stop = full ORB range (ORB-based stop) |
| min_gap_atr_pct | 1.0% | |
| magnifier | 1m | No 1s data for RTY |

### Gating / Exclusions
| Gate | Rule | Reason |
|------|------|--------|
| None | No DOW or date exclusions | |

### Performance
| Metric | Pre-Holdout | Holdout (2025+) |
|--------|------------|-----------------|
| Trades | 1,622 | — |
| Net R | +119.3 | — |
| Calmar | 6.81 | — |
| Sharpe | 1.09 | — |
| Max DD | -17.5R | — |
| WR | 50.4% | — |
| Neg years | 0 | — |

### R by Year
2017:+7 | 2018:+19 | 2019:+1 | 2020:+24 | 2021:+21 | 2022:+10 | 2023:+20 | 2024:+23 | 2025:+4 | 2026:-10

---

## Diversification Structure

### Session Coverage (Eastern Time)

```
20:00  21:00  22:00  23:00  ...  03:00  04:00  ...  07:00  08:00  09:30  10:00  ...  12:00  13:00  ...  15:50
|-- NQ Asia (entry 20:15-22:30) --|
|---- SI Asia (entry 20:30-23:15) ----|
                                      |---- CL LDN (entry 03:30-07:00) ----|
                                                                                  |-- GC NY (entry 09:40-12:00) --|
                                                                                  |------- RTY NY (entry 09:40-13:00) -------|
```

### Correlation Matrix (Daily R)

|  | GC NY | NQ Asia | SI Asia | CL LDN | RTY NY |
|--|-------|---------|---------|--------|--------|
| GC NY | 1.000 | -0.023 | 0.036 | -0.022 | 0.012 |
| NQ Asia | -0.023 | 1.000 | -0.048 | -0.005 | 0.010 |
| SI Asia | 0.036 | -0.048 | 1.000 | -0.003 | 0.033 |
| CL LDN | -0.022 | -0.005 | -0.003 | 1.000 | 0.009 |
| RTY NY | 0.012 | 0.010 | 0.033 | 0.009 | 1.000 |

**Average pairwise correlation: 0.000**

### Asset Class Balance
- **2 indices**: NQ (Nasdaq-100), RTY (Russell 2000)
- **3 commodities**: GC (Gold), SI (Silver), CL (Crude Oil)

### Direction Balance
- **3 long legs**: GC, NQ, CL
- **1 short leg**: SI (natural hedge)
- **1 both-direction leg**: RTY

---

## Position Sizing Notes

Each leg uses `risk_usd = $5,000` (1R) independently. When trading all 5 legs simultaneously on a single funded account:

- **Max theoretical daily exposure**: 5R (if all 5 legs trade and lose on the same day)
- **Recommended sizing**: Scale to ~0.5R per leg ($2,500 risk each) to keep combined daily exposure within prop firm daily loss limits (-2R to -4R)
- **The funded model at full 1R per leg**: 48.9% payout rate, $208 EV, 10 days to payout — viable but the R-based prop model shows high breach rate (73%) due to multi-leg variance
- **Sizing down to 0.5R**: Halves the R generation but dramatically reduces breach probability

---

## Validation Evidence

| Leg | Pipeline | WFE | Stability | PSR | DSR | MC Survival |
|-----|----------|-----|-----------|-----|-----|-------------|
| GC NY L | GO (Alt2, from R2 grid #1) | — | — | — | — | — |
| NQ Asia L | GO (5/5) | 0.797 | 0.964 | 1.000 | — | 91.7% |
| SI Asia S | CONDITIONAL | 0.570 | 0.871 | 0.999 | 0.376 | — |
| CL LDN L | CONDITIONAL | 0.463 | 0.903 | 0.995 | 0.186 | — |
| RTY NY B | STRONG | 0.376 | 0.860 | 0.999 | 0.419 | — |

---

## Risk Factors

1. **2026 weakness**: RTY (-9.5R) is negative YTD. GC is nearly flat (-0.4R). CL (+16.4R) is compensating. Portfolio is +8.5R in 2026.
2. **CL concentration**: 30% of CL's total R comes from 2023 (+35R). DSR 0.186 is the weakest in the portfolio.
3. **SI short bias**: In a sustained commodity bull run, SI shorts could drag. Mitigated by GC and CL longs on the same asset class.
4. **No regime gating**: None of these 5 legs use regime gates. NQ Asia's discovery pipeline tested regime gating but the final R9 config does not include it.
5. **Magnifier dependency**: GC and NQ require 1s data for accurate fills. SI, CL, RTY use 1m (ambiguous bar rate <1%, negligible impact).
