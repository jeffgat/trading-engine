# ALPHA_V1 Portfolio

Separate-account portfolio optimized for prop firm payout extraction. Each leg runs on its own independent funded account. The separate-account model generates 3-4x more lifetime value than combining legs on a single account ($1.66M vs $478K for NQ_NY_LSI alone) because single-leg accounts survive the extraction phase much longer.

Source: LLM Council sessions (2026-04-03), lifecycle simulation, OOS verification.

---

## Account Model

| Parameter | Value |
|-----------|-------|
| Account size | $50,000 |
| Trailing drawdown | $2,000 |
| Trail stops at | $52,000 |
| Phase 1 (Sprint) target | $52,500 (+5R at $400/trade) |
| First payout withdrawal | $500 |
| Phase 2 (Extraction) risk | $200/trade |
| Weekly withdrawal | Friday, withdraw above $52.5K to $52K |
| Account cost | $150 per account |
| Stagger interval | 14 calendar days |

---

## Active Legs

### Leg 1: NQ NY LSI (FAST_V1.1)

**Tier 1 — Flagship**

| Param | Value |
|-------|-------|
| strategy | lsi |
| entry_mode | fvg_limit |
| session | NY (09:35-15:30, flat 15:50) |
| direction | long only |
| rr | 3.0 |
| tp1_ratio | 0.34 |
| atr_length | 10 |
| min_gap_atr_pct | 5.0% |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| fvg_window | 20 / 5 |
| DOW exclusion | Wed + Thu |
| regime gate | None |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-04+) |
|--------|-------------|-------------------|
| Trades | 611 | 48 |
| Win Rate | 59.2% | 66.7% |
| PF | 1.61 | 2.16 |
| Sharpe | 3.217 | 5.122 |
| Net R | +120.1 | +16.2 |
| Max DD | -6.6R | -5.4R |
| Calmar | 18.10 | 2.99 |
| Neg years | 0 | — |

Payout sim (10yr): 92.7% success, +4.30R EV, 6 max consec breach, 126d avg payout.
Lifecycle sim: **$1.66M net**, 1,135 days avg extraction, 81% reach extraction.

R by year: 2016:+9.4 | 2017:+17.6 | 2018:+2.6 | 2019:+7.8 | 2020:+16.7 | 2021:+14.9 | 2022:+9.8 | 2023:+15.7 | 2024:+7.2 | 2025:+13.3 | 2026:+5.1

DB: FAST_V1.1 execution profile

---

### Leg 2: NQ Asia ORB (FAST_V1.1)

**Tier 1 — Fastest payout engine**

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia (20:00-20:15 ORB, entry 20:15-22:30, flat 04:00) |
| direction | long only |
| rr | 6.0 |
| tp1_ratio | 0.3 |
| atr_length | 5 |
| stop | ORB 100% |
| gap_filter | ORB-based, min_gap_orb_pct=10.0 |
| DOW exclusion | Tuesday |
| regime gate | None |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-03+) |
|--------|-------------|-------------------|
| Trades | 753 | 68 |
| Win Rate | 45.2% | — |
| Sharpe | 2.860 | 5.87 |
| Net R | +212.0 | +30.8 |
| Max DD | -10.2R | — |
| Neg years | 0 | — |

Payout sim: 82.4% success, +3.31R EV, **67 days avg payout** (fastest), 9 max consec breach.
Lifecycle sim: **$657K net**, 226 days avg extraction.

R by year: 2016:+21.5 | 2017:+19.7 | 2018:+28.1 | 2019:+11.0 | 2020:+15.8 | 2021:+5.5 | 2022:+31.3 | 2023:+24.6 | 2024:+12.6 | 2025:+37.1 | 2026:+4.8

---

### Leg 3: ES Asia ORB Continuation Long

**Tier 2 — Session diversification, exceptionally robust parameter surface**

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia (20:00-20:15 ORB, entry 20:15-03:00, flat 07:00) |
| direction | long only |
| rr | 1.5 |
| tp1_ratio | 0.7 |
| atr_length | 14 |
| stop | ORB 125% |
| min_gap_atr_pct | 0.5% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 1,454 | 164 |
| Win Rate | 55.1% | — |
| PF | 1.28 | 1.56 |
| Sharpe | 1.900 | 3.47 |
| Net R | +183.3 | +37.6 |
| Max DD | -12.5R | — |
| Calmar | 14.68 | — |
| Neg years | 0 | — |

WF: WFE 0.834, stability 0.893. MC: 89.7% survival. 672/900 grid combos have 0 neg years.
Lifecycle sim: **$598K net**, 321 days avg extraction.

R by year: 2016:+15 | 2017:+15 | 2018:+12 | 2019:+24 | 2020:+14 | 2021:+8 | 2022:+19 | 2023:+20 | 2024:+18 | 2025:+33 | 2026:+4

DB: `bt-es-asia-cont-long-2016-2026-final-6f79d8`

---

### Leg 4: ES NY ORB Continuation Long

**Tier 2 — Most parameter-stable leg in the portfolio**

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:45 ORB, entry 09:45-13:00, flat 15:50) |
| direction | long only |
| rr | 5.0 |
| tp1_ratio | 0.2 |
| atr_length | 7 |
| stop_atr_pct | 5.0% |
| min_gap_atr_pct | 0.25% |
| min_stop_points | 3.0 |
| min_tp1_points | 3.0 |
| DOW exclusion | Thursday |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 866 | 101 |
| Win Rate | 61.3% | — |
| PF | 1.42 | 1.55 |
| Sharpe | 2.280 | 2.83 |
| Net R | +142.8 | +18.2 |
| Max DD | -10.4R | — |
| Calmar | 13.74 | — |
| Neg years | 0 | — |

WF: WFE 0.776, stability 0.893. **tp1=0.2 selected in 7/7 WF folds** (extremely stable). MC: 97.3% survival.
Lifecycle sim: **$563K net**, 289 days avg extraction.

R by year: 2016:+18 | 2017:+25 | 2018:+4 | 2019:+11 | 2020:+16 | 2021:+20 | 2022:+15 | 2023:+13 | 2024:+2 | 2025:+16

DB: `bt-es-ny-cont-long-2016-2026-final-650260`

---

## Dry Run — To Verify

### NQ NY LSI RR2/TP0.5 + Thu-only + Regime Gate

**Shadow-run alongside FAST NQ_NY_LSI for 60 days before swapping live.**

The research variant has better per-trade quality on full history (higher WR, PF, Sharpe, DSR) and dramatically shallower holdout DD (-2.6R vs -5.4R). But FAST generated more raw holdout R (+16.2 vs +11.2) and higher holdout Sharpe (5.12 vs 4.27). The regime gate is a fitted parameter that needs live confirmation.

| Param | Value |
|-------|-------|
| strategy | lsi |
| entry_mode | fvg_limit |
| session | NY (09:35-15:30, flat 15:50) |
| direction | long only |
| rr | 2.0 |
| tp1_ratio | 0.5 |
| atr_length | 14 |
| min_gap_atr_pct | 5.0% |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| fvg_window | 20 / 5 |
| DOW exclusion | Thu only |
| regime gate | skip bull_medium_vol + sideways_medium_vol |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-04+) |
|--------|-------------|-------------------|
| Trades | 588 | 45 |
| Win Rate | 61.1% | 66.7% |
| PF | 1.70 | 1.92 |
| Sharpe | 3.646 | 4.268 |
| Net R | +126.4 | +11.2 |
| Max DD | -7.6R | -2.6R |
| Calmar | 16.72 | 4.33 |
| Neg years | 0 | — |

WF OOS: 311 trades, Sharpe 3.38, WFE 0.766, stability 0.833.
PSR: 0.9999, DSR: **0.709** (survives multiple-testing deflation).
MC: 99.3% survival, 0.7% ruin.
Holdout payout sim: 17 payouts, 0 breaches, 9 open = **100% success rate**.

**OOS verification passed** (2026-04-03):
- 45 holdout trades >= 30 threshold
- Sharpe 4.268 >= 1.0 threshold
- PF 1.92 >= 1.0 threshold

**Holdout comparison vs FAST:**

| Metric | RR2 Gated | FAST V1.1 | Better for... |
|--------|-----------|-----------|---------------|
| Net R | +11.2 | **+16.2** | FAST wins raw R |
| Sharpe | 4.268 | **5.122** | FAST wins quality |
| Max DD | **-2.6R** | -5.4R | RR2 wins risk |
| Calmar | **4.33** | 2.99 | RR2 wins risk-adjusted |
| PF | 1.92 | **2.16** | FAST wins efficiency |

**Interpretation**: FAST is better for sprint phase (more R, faster to payout). RR2 Gated is better for extraction phase (shallower DD = longer survival). Consider running both as separate accounts.

R by year: 2016:+10.6 | 2017:+28.5 | 2018:+10.7 | 2019:+17.2 | 2020:+23.4 | 2021:+10.5 | 2022:+5.0 | 2023:+5.2 | 2024:+1.2 | 2025:+11.2 | 2026:+2.8

DB: `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`

**Action**: Build regime gate infrastructure in execution engine. Shadow-run for 60 days. If live metrics confirm, either swap FAST or run both as separate accounts.

---

## Session Coverage

```
20:00  21:00  22:00  ...  04:00  ...  09:30  10:00  ...  12:00  13:00  ...  15:50
|-- NQ Asia (entry 20:15-22:30) --|
|-- ES Asia (entry 20:15-03:00) -----|
                                            |-- ES NY (entry 09:45-13:00) --------|
                                            |-- NQ NY LSI (entry 09:35-15:30) -----------|
```

---

## Expansion Sequence

| Phase | Timeline | Account | Leg | Status |
|-------|----------|---------|-----|--------|
| 1 | Now | Acct 1 | NQ NY LSI (FAST) | Already live |
| 2 | Week 1-2 | Acct 2 | NQ Asia ORB | Already live |
| 3 | Month 1-2 | Acct 3 | ES Asia | New account application |
| 4 | Month 2-3 | Acct 4 | ES NY | New account application |
| DRY | Ongoing | Shadow | NQ NY LSI RR2 Gated | 60-day shadow run |

---

## Paused Legs

### GC NY R3 Continuation Longs

**Paused — GC trading banned on Apex Trader Funding. RR 9.0 also exceeds practical prop firm constraints at standard risk sizing. Could see future use with smaller risk per trade or on a different prop firm that allows GC.**

This was the strongest walk-forward validated leg in the entire candidate set (WFE 0.956). If GC becomes tradeable, this is the first leg to activate.

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY (09:30-09:38 ORB, entry 09:40-12:00, flat 13:30) |
| direction | long only |
| rr | 9.0 |
| tp1_ratio | 0.35 |
| atr_length | 7 |
| stop_atr_pct | 4.5% |
| min_gap_atr_pct | 3.0% |
| impulse_close_filter | ON |
| DOW exclusion | Friday |
| excluded_dates | FOMC |
| magnifier | 1s |

| Metric | Full History | Holdout (2025+) |
|--------|-------------|-----------------|
| Trades | 622 | 62 |
| Win Rate | 31.8% | 37.1% |
| PF | 1.52 | 2.08 |
| Sharpe | 2.310 | 4.256 |
| Net R | +200.3 | +41.7 |
| Max DD | -12.4R | — |
| Calmar | 16.11 | — |
| Neg years | 0 | — |

WF: **WFE 0.956** (near-perfect), stability 0.929. MC: 63.4% survival (borderline).

R by year: 2016:+3 | 2017:+9 | 2018:+19 | 2019:+28 | 2020:+24 | 2021:+13 | 2022:+12 | 2023:+27 | 2024:+26 | 2025:+42.4

DB: `bt-gc-ny-cont-longs-r3-high-rr-final-fri-ex-692e90`

---

## Excluded Legs (with reasoning)

| Leg | Reason |
|-----|--------|
| SI Asia-1 | DSR 0.507 barely above noise — insufficient statistical confidence |
| RTY NY-4 | 2026: -10R — live regime break, recent performance disqualifying |
| CL LDN-1 | 2025: +0R — no recent edge detected |
| GC NY LSI | PF 2.29, Sharpe 4.79, but only 13 trades/year — below 30-trade OOS threshold |
| GC Asia-1 | DSR 0.652 (strong), but GC banned on Apex — revisit if prop firm changes |
| NQ Asia Discovery Asia-2 | Holdout +42.5R is exceptional, but requires regime gate build. Evaluate after RR2 gated shadow run |

---

## Risk Factors

1. **Long-biased**: All 4 legs are long-only. No short-side hedge. A sustained bear market hits all legs simultaneously.
2. **NQ + ES concentration**: All 4 legs trade equity index futures (NQ or ES). No commodity diversification — GC is paused due to Apex ban.
3. **Equity correlation in stress**: NQ and ES co-drawdown during risk-off events (March 2020 type). Without GC as a partial decorrelator, all legs are exposed to the same macro risk.
4. **Lifecycle projections are in-sample**: The $1.66M figure is a backtest-on-backtest projection. Direction is correct but magnitude is likely inflated.
5. **Regime gate not yet live**: The RR2 Gated variant's improvement depends on a fitted parameter (medium-vol classification) that hasn't been confirmed in live trading.
6. **Prop firm instrument restrictions**: Apex Trader Funding bans GC trading, removing the strongest non-equity diversifier from the portfolio. Monitor for policy changes or alternative prop firms that allow GC.
