# ALPHA_V1 Portfolio

Separate-account portfolio optimized for prop firm payout extraction. Each leg runs on its own independent funded account. As of 2026-04-12, the NQ NY leg has been swapped from the archived legacy `NQ_NY_LSI` branch to the current canonical `HTF_LSI_5M_LAG24` operating profile.

Source: LLM Council sessions (2026-04-03), exact replacement sizing packets, and current HTF-LSI exact replay (updated 2026-04-12).

---

## Account Model

| Parameter | Value |
|-----------|-------|
| Account size | $50,000 |
| Trailing drawdown | $2,000 |
| Trail stops at | $52,000 |
| Phase 1 (Sprint) target | $52,500 |
| First payout withdrawal | $500 |
| Phase 2 (Extraction) risk | $200/trade |
| Weekly withdrawal | Friday, withdraw above $52.5K to $52K |
| Account cost | $150 per account |
| Stagger interval | 14 calendar days |

### Risk Sizing Per Leg

Risk is differentiated per leg based on actual trade-level prop sims. For the new NQ NY HTF leg, the sizing row below uses the exact replacement risk sweep; a full four-leg exact rerun on the tightened live row is still pending.

| Leg | Sprint Risk | Pay% | PayD | MCBch | EV$/acct | Rationale |
|-----|------------|------|------|-------|----------|-----------|
| NQ NY HTF-LSI lag24 | $300 | 90.6% | 304d | 9 | +$2,076 | Canonical LSI swap-in; recent 2024-2026 packet stayed strong at 98.0% / 176d |
| NQ Asia ORB | $300 | 96.9% | 132d | 2 | +$2,362 | $400 → 90.4% with 6 MCBch. $300 fixes it |
| ES Asia Cont | $200 | 98.4% | 323d | 3 | +$2,430 | Weak R production. $400 → 85.4% with 6 MCBch |
| ES NY Cont | $300 | 91.9% | 210d | 5 | +$2,137 | Lumpy wins. $400 → 82.7% with 7 MCBch |

**Current combined-account exact packet with HTF swap (legacy `NQ_NY_LSI` replaced by `HTF_LSI_5M_LAG24` at `$300`; other legs unchanged):**

| Window | Pay% | Avg PayD | Payouts | Breaches | Open | Notes |
|--------|------|----------|---------|----------|------|-------|
| 10Y | 73.6% | 134d | 192 | 69 | 0 | Exact replacement packet |
| 2024 | 84.2% | 110d | 16 | 3 | 7 | Strong replacement year |
| 2025 | 84.6% | 96d | 22 | 4 | 0 | Best fully resolved recent year |
| 2026 YTD | 100.0%* | 42d | 1 | 0 | 5 | Too open-heavy to lean on |

\* Resolved accounts only. This portfolio packet was run on the immediately prior lag24 baseline (`08:30-15:00`, `rr=3.0`, `tp1=0.6`). The live `ALPHA_V1` leg is now the tighter `08:30-13:30`, `rr=3.5`, `tp1=0.4` version, so a fresh full four-leg exact rerun is still pending.

---

## Active Legs

### Leg 1: HTF_LSI/NQ_NY-L24

**Tier 1 — Canonical LSI Swap-In**

| Param | Value |
|-------|-------|
| strategy | htf_lsi |
| entry_mode | fvg_limit |
| sweep_window | 08:30-15:00 |
| session | NY (08:30-13:30 entry, flat 15:50) |
| direction | long only |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| atr_length | 14 |
| min_gap_atr_pct | 3.0% |
| htf_level_tf_minutes | 60 |
| htf_n_left | 3 |
| htf_trade_max_per_session | 2 |
| fvg_window | 20 / 2 |
| max_fvg_to_inversion_bars | 24 |
| DOW exclusion | None |
| regime gate | None |
| magnifier | 1s |

| Metric | Full History | Holdout (2025-04-01 to 2026-03-24) |
|--------|-------------|-------------------|
| Trades | 493 | 38 |
| Win Rate | 52.1% | 57.9% |
| PF | 1.43 | 1.96 |
| Sharpe | 2.428 | 4.414 |
| Net R | +86.6 | +13.0 |
| Max DD | -10.0R | -3.0R |
| Calmar | 8.63 | 4.33 |
| Neg years | 1 | — |

Exact replay on the current live params: only `2016` was a negative full year; `2017-2025` were positive, and `2026 YTD` is still too immature to weigh heavily.

Sizing reference at `$300` risk from the prior exact replacement packet: `10Y` prop payout `90.6%`, `304d` average payout, `9` max consecutive breaches, `+$2,076` EV/start. Recent `2024-2026` packet: `98.0%` payout, `176d` average payout, `+$2,410` EV/start.

Combined swap-in reference on that same older lag24 baseline, with the other three legs unchanged: `10Y` combined payout `73.6%`, `134d` average payout.

R by year: 2016:-2.3 | 2017:+5.7 | 2018:+9.8 | 2019:+2.7 | 2020:+12.1 | 2021:+7.8 | 2022:+3.5 | 2023:+15.3 | 2024:+18.6 | 2025:+13.6 | 2026:-0.4

Execution: `ALPHA_V1` live `NQ_NY_LSI` override now mirrors this HTF-LSI profile.

---

### Leg 2: ORB/NQ_ASIA-RR6

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

### Leg 3: ORB/ES_ASIA-RR1.5

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

R by year: 2016:+7.5 | 2017:+7.6 | 2018:+1.9 | 2019:+15.3 | 2020:+14.4 | 2021:+9.1 | 2022:+22.1 | 2023:+21.7 | 2024:+18.5 | 2025:+27.4 | 2026:+1.1

DB: `bt-es-asia-cont-long-2016-2026-final-6f79d8`

---

### Leg 4: ORB/ES_NY-RR5

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

R by year: 2016:+15.4 | 2017:+25.9 | 2018:+4.6 | 2019:+11.0 | 2020:+16.6 | 2021:+19.0 | 2022:+15.2 | 2023:+13.8 | 2024:+1.7 | 2025:+17.7 | 2026:+1.8

DB: `bt-es-ny-cont-long-2016-2026-final-650260`

---

## Dry Run — Historical Reference

### Legacy LSI/NQ_NY-RR2
#### NQ NY Legacy LSI RR2/TP0.5 + Thu-only + Regime Gate

**Archived legacy alternate. No longer the active `ALPHA_V1` swap candidate after the HTF-LSI lag24 promotion.**

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

**Interpretation**: In the old legacy family, FAST was better for sprint phase (more R, faster to payout) while RR2 Gated was better for extraction phase (shallower DD = longer survival). Keep this as historical context only unless the legacy family is explicitly reopened.

R by year: 2016:+10.6 | 2017:+28.5 | 2018:+10.7 | 2019:+17.2 | 2020:+23.4 | 2021:+10.5 | 2022:+5.0 | 2023:+5.2 | 2024:+1.2 | 2025:+11.2 | 2026:+2.8

DB: `bt-nq-ny-lsi-rr2-tp0-5-thu-gated-2016-2026-174198`

**Action**: Archived reference only. Reopen only if the legacy LSI family is intentionally put back on the roadmap.

---

## Session Coverage

```
20:00  21:00  22:00  ...  04:00  ...  08:30  09:30  10:00  ...  12:00  13:00  ...  15:00  15:50
|-- NQ Asia (entry 20:15-22:30) --|
|-- ES Asia (entry 20:15-03:00) -----|
                                    |-- NQ NY HTF-LSI (entry 08:30-13:30, sweep 08:30-15:00) -----|
                                            |-- ES NY (entry 09:45-13:00) --------|
```

---

## Expansion Sequence

| Phase | Timeline | Account | Leg | Status |
|-------|----------|---------|-----|--------|
| 1 | Now | Acct 1 | NQ NY HTF-LSI lag24 | Live swap-in |
| 2 | Week 1-2 | Acct 2 | NQ Asia ORB | Already live |
| 3 | Month 1-2 | Acct 3 | ES Asia | New account application |
| 4 | Month 2-3 | Acct 4 | ES NY | New account application |
| DRY | Historical | Archive | Legacy NQ NY LSI RR2 Gated | Archived reference only |

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
| NQ Asia Discovery Asia-2 | Holdout +42.5R is exceptional, but requires regime gate build. Evaluate after the HTF-LSI swap-in stabilizes |

---

## Risk Factors

1. **Long-biased**: All 4 legs are long-only. No short-side hedge. A sustained bear market hits all legs simultaneously.
2. **NQ + ES concentration**: All 4 legs trade equity index futures (NQ or ES). No commodity diversification — GC is paused due to Apex ban.
3. **Equity correlation in stress**: NQ and ES co-drawdown during risk-off events (March 2020 type). Without GC as a partial decorrelator, all legs are exposed to the same macro risk.
4. **Portfolio-level projections are mixed-vintage**: Older lifecycle-style legacy figures should be treated as historical context only. The active NQ NY leg is now HTF-LSI, and the full four-leg exact rerun on the tightened live row is still pending.
5. **The new HTF swap is a live-policy update, not a fully rerun portfolio dossier yet**: The NQ NY leg is backed by exact single-leg replay and replacement sizing packets, but the complete `ALPHA_V1` stack has not yet been rerun end-to-end on the tighter `08:30-13:30 / rr3.5 / tp0.4` row.
6. **Prop firm instrument restrictions**: Apex Trader Funding bans GC trading, removing the strongest non-equity diversifier from the portfolio. Monitor for policy changes or alternative prop firms that allow GC.
