# 4-Leg ORB Portfolio — Config & Gating Reference

**DB Entry**: `bt-4-leg-portfolio-nq-cl-rty-es-281328`
**Script**: `run_portfolio_4leg_backtest.py`
**Strategy**: ORB Continuation across 4 instruments, 3 sessions, 2 asset classes

---

## Portfolio Summary

| Metric | Value |
|--------|-------|
| Total R (2015-2026) | +522.6R |
| Avg Annual R | +43.6R |
| Max DD | -38.3R |
| Calmar | 1.14 |
| Sharpe | 1.86 |
| Negative years | 0 |
| Avg pairwise correlation | 0.010 |
| Holdout R (2025-2026) | +39.5R |
| Funded model PR (pre-HO) | 47.1% |
| Funded model EV | $178 |
| Avg days to payout | 12 |

---

## Why This Portfolio

Removed GC and SI from the 5-leg portfolio to reduce commodity exposure and simplify execution. Added ES NY Long as the 4th leg — it has the strongest standalone metrics of any candidate (Calmar 13.13, 0 neg years, 97.3% MC survival) and near-zero correlation with the other 3 legs (+0.027 with the base portfolio).

**vs 5-Leg Portfolio (v2)**:

| Metric | 5-Leg (v2) | 4-Leg | Change |
|--------|-----------|-------|--------|
| Total R | +601.5 | +522.6 | -78.9 |
| Max DD | -38.9R | -38.3R | +0.6R better |
| Calmar | 1.29 | 1.14 | -0.15 |
| Sharpe | 1.86 | 1.86 | same |
| Holdout R | +47.4 | +39.5 | -7.9 |
| Funded PR | 48.9% | 47.1% | -1.8% |
| Legs | 5 | 4 | simpler |
| Commodities | 3 (GC, SI, CL) | 1 (CL) | lighter |

The 4-leg portfolio trades ~80R of total R for simpler execution (4 instruments vs 5), no precious metals exposure, and essentially the same Sharpe/DD/funded metrics.

---

## Leg Overview

| # | Leg | Instrument | Session | Direction | ORB | Stop | RR | TP1 | Status |
|---|-----|-----------|---------|-----------|-----|------|----|-----|--------|
| 1 | NQ_Asia_L | NQ (Nasdaq) | Asia | Long | 15m | ATR 4.0% | 3.0 | 0.6 | GO |
| 2 | CL_LDN_L | CL (Crude) | LDN | Long | 30m | ATR 8.0% | 3.5 | 0.6 | CONDITIONAL |
| 3 | RTY_NY_B | RTY (Russell) | NY | Both | 10m | ORB 100% | 3.0 | 0.4 | STRONG |
| 4 | ES_NY_L | ES (S&P 500) | NY | Long | 15m | ATR 5.0% | 5.0 | 0.2 | CONDITIONAL |

---

## Leg 1: NQ Asia Continuation Longs (R9 Restart Final)

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
| tp1_ratio | 0.6 | |
| atr_length | 5 | Fast ATR |
| stop_atr_pct | 4.0% | |
| min_gap_atr_pct | 0.90% | |
| impulse_close_filter | ON | |
| magnifier | 1s | |

### Gating
- **DOW exclusion**: Tuesday (negative EV on NQ Asia)

### Performance
588 trades | +120.9R | Calmar 8.00 | Sharpe 1.69 | DD -15.1R | WR 41.1% | 1 neg year (2021: -3.9R)

R by year: 2016:+11 | 2017:+13 | 2018:+18 | 2019:+22 | 2020:+12 | 2021:-4 | 2022:+13 | 2023:+15 | 2024:+12 | 2025:+6 | 2026:+3

### Pipeline: GO (5/5 phases passed)
- WFE 0.797, Stability 0.964, MC 91.7% survival
- DB: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`

---

## Leg 2: CL LDN Continuation Longs (LDN-1)

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
| stop_atr_pct | 8.0% | CL needs >= 7% to avoid sub-tick artifact |
| min_gap_atr_pct | 1.0% | |
| magnifier | 1m | No 1s data |

### Gating
- None

### Performance
1,201 trades | +139.8R | Calmar 6.06 | Sharpe 1.20 | DD -23.1R | WR 36.7% | 1 neg year (2018: -0.2R)

R by year: 2015:+7 | 2016:+14 | 2017:+6 | 2018:-0 | 2019:+6 | 2020:+3 | 2021:+22 | 2022:+22 | 2023:+35 | 2024:+10 | 2025:+0 | 2026:+16

### Pipeline: CONDITIONAL (from 3-session discovery sweep)
- WFE 0.463, Stability 0.903, PSR 0.995, DSR 0.186 (marginal)
- Holdout: +12.8R, PR 54.1%

---

## Leg 3: RTY NY Continuation Both (NY-4)

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
| direction | both | Catches either ORB direction |
| rr | 3.0 | |
| tp1_ratio | 0.4 | |
| atr_length | 14 | |
| stop_orb_pct | 100.0% | Full ORB range stop |
| min_gap_atr_pct | 1.0% | |
| magnifier | 1m | No 1s data |

### Gating
- None

### Performance
1,622 trades | +119.3R | Calmar 6.81 | Sharpe 1.09 | DD -17.5R | WR 50.4% | 0 neg years

R by year: 2017:+7 | 2018:+19 | 2019:+1 | 2020:+24 | 2021:+21 | 2022:+10 | 2023:+20 | 2024:+23 | 2025:+4 | 2026:-10

### Pipeline: STRONG (from 3-session discovery sweep)
- WFE 0.376, Stability 0.860, PSR 0.999, DSR 0.419
- Pre-holdout PR 62.7%, Holdout PR 47.0%, EV $12,479

---

## Leg 4: ES NY Continuation Longs (Final)

### Session Times (all Eastern)
| Window | Time |
|--------|------|
| ORB | 09:30 - 09:45 (15 minutes) |
| Entry | 09:45 - 13:00 |
| Flat | 15:50 |

### Parameters
| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| direction | long only | |
| rr | 5.0 | |
| tp1_ratio | 0.2 | TP1 at 20% of full target — stable in 7/7 WF folds |
| atr_length | 7 | Short ATR |
| stop_atr_pct | 5.0% | |
| min_gap_atr_pct | 0.25% | Gap nearly insensitive (0.0-0.5% same result) |
| min_stop_points | 3.0 | Dual floor — prevents degenerate sub-tick stops |
| min_tp1_points | 3.0 | Dual floor — prevents degenerate TP1 placement |
| magnifier | 1s | |

### Gating
- **DOW exclusion**: Thursday (+1.6 Calmar improvement, consistent across all anchor configs)

### Performance
876 trades | +142.6R | Calmar 13.13 | Sharpe 2.28 | DD -10.9R | WR 61.3% | 0 neg years

R by year: 2016:+15 | 2017:+26 | 2018:+5 | 2019:+11 | 2020:+17 | 2021:+19 | 2022:+15 | 2023:+14 | 2024:+2 | 2025:+18 | 2026:+2

### Pipeline: CONDITIONAL GO (4/5 phases)
- WFE 0.776, Stability 0.893, MC 97.3% survival
- Phase 3 fail: avg annual R < 12R (2024 OOS weak at +2.0R) — borderline, not structural
- tp1=0.2 selected in 7/7 folds — extremely stable
- DB: `bt-es-ny-cont-long-2016-2026-final-650260`

---

## Diversification Structure

### Session Coverage (Eastern Time)

```
20:00  21:00  22:00  ...  03:00  04:00  ...  07:00  08:00  09:30  10:00  ...  13:00  ...  15:50
|-- NQ Asia (entry 20:15-22:30) --|
                                  |---- CL LDN (entry 03:30-07:00) ----|
                                                                              |-- ES NY (entry 09:45-13:00) ---|
                                                                              |--- RTY NY (entry 09:40-13:00) ----|
```

Three distinct session windows with zero overlap. ES NY and RTY NY share the NY session but trade different indices (S&P 500 large-cap vs Russell 2000 small-cap) with daily R correlation of only +0.033.

### Correlation Matrix (Daily R)

|  | NQ Asia | CL LDN | RTY NY | ES NY |
|--|---------|--------|--------|-------|
| NQ Asia | 1.000 | -0.005 | 0.010 | -0.003 |
| CL LDN | -0.005 | 1.000 | 0.009 | 0.015 |
| RTY NY | 0.010 | 0.009 | 1.000 | 0.033 |
| ES NY | -0.003 | 0.015 | 0.033 | 1.000 |

**Average pairwise correlation: 0.010**

### Asset Class Balance
- **3 indices**: NQ (Nasdaq-100), RTY (Russell 2000), ES (S&P 500)
- **1 commodity**: CL (Crude Oil)

### Direction Balance
- **3 long legs**: NQ, CL, ES
- **1 both-direction leg**: RTY
- Net bias: long (structural equity premium)

---

## Combined R by Year

| Year | NQ Asia | CL LDN | RTY NY | ES NY | **Portfolio** |
|------|---------|--------|--------|-------|------------|
| 2015 | — | +7 | — | — | **+7** |
| 2016 | +11 | +14 | — | +15 | **+40** |
| 2017 | +13 | +6 | +7 | +26 | **+52** |
| 2018 | +18 | -0 | +19 | +5 | **+41** |
| 2019 | +22 | +6 | +1 | +11 | **+40** |
| 2020 | +12 | +3 | +24 | +17 | **+56** |
| 2021 | -4 | +22 | +21 | +19 | **+58** |
| 2022 | +13 | +22 | +10 | +15 | **+59** |
| 2023 | +15 | +35 | +20 | +14 | **+84** |
| 2024 | +12 | +10 | +23 | +2 | **+46** |
| 2025 | +6 | +0 | +4 | +18 | **+28** |
| 2026 | +3 | +16 | -10 | +2 | **+12** |

Every year where one leg is negative, other legs compensate. 2021: NQ is -3.9R but CL/RTY/ES all strong. 2026: RTY is -9.5R but CL (+16.4) covers.

---

## Position Sizing Notes

Each leg uses `risk_usd = $5,000` (1R) independently.

- **Max theoretical daily exposure**: 4R (if all 4 legs trade and lose on the same day)
- **Funded model at full 1R per leg**: 47.1% payout rate, $178 EV, 12 days to payout
- **Holdout funded model**: 41.9% PR, $194 EV — consistent with pre-holdout
- **R-based prop model**: 29% PR — high breach rate due to multi-leg daily variance. Scale to ~0.6R per leg for better prop model fit.

---

## Risk Factors

1. **Long-biased**: 3/4 legs are long-only. In a sustained bear market, only RTY (both-direction) provides short-side coverage.
2. **No commodity short hedge**: Removing SI eliminated the only short leg. If commodities spike, CL longs benefit but there's no offsetting short.
3. **RTY 2026 weakness**: -9.5R YTD (worst leg). March 2026 alone was -7.2R. Could be a rough patch or a regime shift.
4. **CL concentration**: 2023 (+35R) is ~25% of CL's total R. DSR 0.186 is marginal.
5. **ES-RTY NY overlap**: Both trade during NY session. While daily R correlation is only +0.033, a systemic equity market crash would hit both simultaneously.
6. **Holdout DD deeper**: -34.6R holdout DD vs -38.3R full history — the holdout period has been challenging.
