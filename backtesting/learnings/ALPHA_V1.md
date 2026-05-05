# ALPHA_V1 Portfolio

Separate-account portfolio optimized for prop firm payout extraction. Each leg runs on its own independent funded account. As of 2026-04-12, the NQ NY leg has been swapped from the archived legacy `NQ_NY_LSI` branch to the current preferred **live / discretionary** NQ NY LSI profile: the `ALPHA_V1` HTF-LSI override (`08:30-13:30`, `rr=3.5`, `tp1=0.4`, `risk_usd=400`). This should be treated as the active operating profile. The standalone `HTF_LSI_5M_LAG24` block remains the frozen canonical research anchor for the underlying HTF-LSI thesis.

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

Execution note: this `ES_NY ORB` leg was backtested with the hierarchical bar magnifier enabled, so ambiguous fills/exits were resolved using `5m -> 1m -> 1s` execution data rather than 5-minute bars alone.

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

### ES_NY ORB Live Retention Review (2026-05-05)

Live `ALPHA_V1-A` currently risks `$400` on `ES_NY`, while the original ALPHA sizing table marked `$300` as the preferred sprint risk and explicitly noted that `$400` reduced first-payout quality (`82.7%` payout, `7` max consecutive breaches). Treat `$400` ES_NY as an aggressive live override, not the canonical ALPHA risk.

Production exact replay still supports keeping the leg in the research portfolio: over `2016-04-17` to `2026-03-24`, exact `ALPHA_V1-A` replay shows `ES_NY ORB` at `506` trades, `+71.13R`, `55.34%` WR, `PF 1.33`, and `-12.00R` DD; last 1y shows `57` trades, `+18.88R`, `61.40%` WR, `PF 1.996`, and `-6.00R` DD. Removing ES_NY from the same exact replay lowers full-history portfolio R from `+445.45R` to `+374.33R`, but only slightly improves full-history DD (`-14.89R` to `-14.42R`).

Live DB sample after the local data cutoff is weak and matches the discretionary concern: from `2026-04-15` through `2026-05-05`, `ES_NY` has `7` closed live trades for `-4.0R` / `-$1,600` at `$400` risk, with `5` full stopouts, `2` TP1-to-breakeven exits, and `0` full TP2 exits. This is not enough sample to invalidate the historical edge, but it confirms the leg's uncomfortable payoff shape: without occasional TP2/EOD extension, two `+0.5R` partials are needed just to offset one `-1R` loss.

**Operating conclusion:** do not permanently delete ES_NY ORB on this sample alone, but do not keep it at `$400` while it is failing live. Demote to `$200-$300` or pause until fresh post-2026-03-24 data can be exact-replayed. If ALPHA_V1 needs a leg removed for simplicity or drawdown relief, ES_NY is the first ORB leg to cut because it is positive but least essential: the portfolio remains profitable without it, and the current live sizing magnifies its worst behavioral mode.

### NY ORB Wide-Stop Target Sweep (2026-05-05)

Report: `backtesting/learnings/reports/NQ_ES_NY_ORB_WIDE_STOP_TARGET_SWEEP_20260505.md`

Focused sweep across `794` valid configs tested whether **NQ NY ORB R11** and **ES_NY ORB** could use wider NY-session stops while sweeping `rr` and TP1 distance. Structure was held fixed for each candidate; only stop basis/width, `rr`, and TP1 moved.

**Conclusion: do not widen either NY ORB as an ALPHA_V1 replacement.** Zero rows widened the actual median stop by at least `20%` while preserving full-history, last-1y, last-2y, PF, DD, and negative-year quality. NQ R11's least-bad actual widening (`ATR 9%`, about `1.29x` wider) cost roughly `26R-30R` full-history. ES_NY's first meaningful wider families (`ATR 10%+`, `ATR 12%+`, `ORB 50%+`) either damaged recent performance or materially increased DD; `ATR 6%` and `ORB 25%` mostly hit the same `12`-tick median stop because the `3pt` floor dominated.

Operating implication: if NY ORB stopouts are emotionally or live-operationally uncomfortable, solve that with **risk sizing**, not wider stops. ES_NY remains the first ORB leg to risk down or pause when live behavior is bad. NQ NY ORB R11 remains a separate conditional candidate that needs exact execution replay before live promotion; widening its stop is not the upgrade path. Both tested branches are `deployability=live_native` mechanically, but `exact_replay_required=yes_before_live_promotion`.

---

## ORB Mechanic Transfer Test — Hunter Wide-Stop + Re-Entry

2026-05-02 report: `backtesting/learnings/reports/ALPHA_V1_ORB_WIDESTOP_REENTRY_TRANSFER_20260502.md`

Artifacts: `backtesting/data/results/alpha_v1_orb_widestop_reentry_transfer_20260502/`

Scope was the three active ALPHA_V1 ORB legs only: `NQ Asia ORB`, `ES Asia ORB`, `ES NY ORB`. The HTF-LSI leg was excluded because the hypothesis was whether Hunter ORB mechanics transfer to ORB continuation legs.

**Conclusion: one-loss/nonpositive re-entry transfers; wide-stop TP compression does not.**

Combined ORB sleeve, `2016-04-17` to `2026-03-24`:

| Variant | Fills | Net R | PF | Sharpe | DD | Neg years | Read |
|---------|------:|------:|---:|-------:|---:|----------:|------|
| Baseline `cap1` | 2,989 | +486.9R | 1.40 | 1.73 | -21.2R | 0 | Current one-trade-per-session ORB sleeve |
| `cap2_after_nonpositive` / `after_sl` | 3,224 | +545.6R | 1.41 | 1.93 | -22.0R | 0 | Best clean Hunter-style transfer |
| `cap2_any` | 3,698 | +568.5R | 1.37 | 1.92 | -23.2R | 0 | Highest R, but more flow and worse DD/PF |
| Best wide-stop only | 2,989 | +482.3R | 1.39 | — | -21.2R | 0 | Still loses R; no meaningful DD benefit |

Recent windows:
- `cap2_after_nonpositive` adds `+25.7R` in 2024+, `+6.6R` in 2025+, and `+1.7R` in the last 1y, with small DD giveback.
- `cap2_any` adds more R (`+34.7R` in 2024+, `+13.6R` in 2025+, `+11.7R` last 1y) but worsens recent daily DD by about `-2.7R`.
- Every combined wide-stop-only variant loses net R versus baseline. Best full-history wide-only is still `-4.7R`; median wide-only is about `-32.9R`. Do not port Hunter's wide-stop 1R cap to ALPHA_V1 ORB as a sleeve rule.

Per-leg read:
- `NQ Asia` and `ES Asia` both favor `cap2_after_nonpositive` / `after_sl` over target compression.
- `ES NY` likes extra flow most; its best full-history row is a cap2-any + light wide-stop combo, but it introduces a negative year and needs prop/risk validation before promotion.

2026-05-03 follow-up report: `backtesting/learnings/reports/ALPHA_V1_ORB_GAP_CANDLE_STOP_COMPARE_20260503.md`

Tested replacing the current ATR/ORB-distance stop logic on the same three ORB legs with an FVG impulse-candle structural stop: long stop = `low[signal_bar - 1] - 1pt`, short stop = `high[signal_bar - 1] + 1pt`, while leaving the engine's hard floors active. **Conclusion: NO-GO as a sleeve rule.** Combined 10yr fell from `+486.9R / -21.2R DD` to `+375.5R / -28.8R DD`; funded first-payout outcomes fell from `186` payouts / `70` breaches to `170` payouts / `85` breaches. The damage was largest in `ES NY` (`-62.6R`) and `NQ Asia` (`-35.0R`). The only favorable read was small 2026 YTD noise (`+1.6R`, DD `+0.9R`) and is not enough to offset the long-run and 2025 degradation.

2026-05-04 follow-up report: `backtesting/learnings/reports/ALPHA_V1_ASIA_ORB_FULL_TP1_WIDESTOP_SWEEP_20260504.md`

Tested a narrower wide-stop exit rule on the two Asia ORB legs only: when realized stop/risk points are above `large_sl_threshold_points`, exit the full trade at the normal TP1 level instead of partialing at TP1 and targeting TP2. **Conclusion: NO-GO / tiny research-only NQ sidecar at best.** NQ Asia's best full-history threshold was `35` points for only `+3.82R` with no DD change. ES Asia's best threshold was `15` points and still lost `-0.18R`. The best combined NQ+ES Asia row was simply `nq_sl35p0__es_baseline`, adding `+3.82R` with no DD improvement; 2025+ best combined lift was only `+1.42R`. This does not justify live/exact replay implementation unless paired with a broader exit-management project.

Completed follow-up: the promotion packet below tests `cap2_after_nonpositive` on `NQ Asia ORB` and `ES Asia ORB` inside the full active ALPHA_V1 stack.

### ORB One-Loss Reentry Promotion Packet (2026-05-02)

Report: `backtesting/learnings/reports/ALPHA_V1_ORB_REENTRY_PROMOTION_20260502.md`

Artifacts: `backtesting/data/results/alpha_v1_orb_reentry_promotion_20260502/`

Candidate: `NQ Asia ORB` and `ES Asia ORB` move to `orb_trade_max_per_session=2` with `orb_reentry_policy=after_nonpositive_first`; `ES NY ORB` and `NQ NY HTF-LSI` stay unchanged. The test used the active four-leg ALPHA_V1 lineup and current sprint risk sizing: HTF-LSI `$300`, NQ Asia `$300`, ES Asia `$200`, ES NY `$300`.

**Read: research pass, execution build required before dry-run.** Full-history combined R improves, recent windows improve, and 2025 remains strong; however, current-dollar funded cohorts are mixed across the entire 10-year history and the generic execution `ORBEngine` does not yet support the same cap2/reentry semantics.

Combined active portfolio, `2016-04-17` to `2026-03-24`:

| Window | Baseline | Candidate | Delta | DD change | Current-$ delta |
|--------|---------:|----------:|------:|----------:|----------------:|
| Full | +579.5R | +625.6R | +46.1R | -0.9R | +$11.6k |
| 2024+ | +159.0R | +174.0R | +15.0R | +0.5R | +$4.0k |
| 2025+ | +106.5R | +113.1R | +6.6R | +1.3R | +$1.6k |
| Last 1y | +91.4R | +98.1R | +6.7R | +1.3R | +$1.6k |
| Calendar 2025 | +97.5R | +103.1R | +5.6R | +1.3R | +$1.4k |

Per-leg contribution on full history:
- `NQ Asia ORB`: `+23.8R` / `+$7.1k`, DD roughly flat (`-0.1R`).
- `ES Asia ORB`: `+22.3R` / `+$4.5k`, DD slightly better (`+0.6R`).
- `ES NY ORB` and `NQ NY HTF-LSI`: unchanged by design.

Funded first-payout model at current risk sizing:

| Window | Baseline Pay% | Candidate Pay% | Baseline breaches | Candidate breaches | Read |
|--------|--------------:|---------------:|------------------:|-------------------:|------|
| Full | 77.2% | 74.1% | 55 | 64 | Mixed: more R, but slightly more historical account stress |
| 2024+ | 81.4% | 79.7% | 7 | 8 | Slightly worse |
| 2025+ | 84.4% | 84.4% | 2 | 2 | Same payout rate, faster median payout |
| Last 1y | 74.1% | 77.8% | 3 | 2 | Better recent cohort behavior |

Timing-overlap check: candidate generated `134` reentry fills for `+46.1R` / `+$11.6k`; other legs were negative on `31.3%` of reentry days versus `46.2%` of all candidate trading days. The reentry trades do not appear to disproportionately cluster with other-leg loss days, though the worst overlap days still include multi-leg drawdowns.

Execution action: do not flip this live from config alone. Add generic `ORBEngine` support for `orb_trade_max_per_session` and `orb_reentry_policy=after_nonpositive_first`, wire checkpoint/API/exact-replay fields, then run dry-mode parity before promotion.

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

## ORB Entry Research Notes

### Close-Entry Probe (2026-04-25)

**NO-GO for ALPHA_V1 ORB replacement.** Tested two broad variants against the three active ORB legs (`NQ Asia`, `ES Asia`, `ES NY`) over `2016-04-17` to `2026-03-24`:

1. `fvg_close`: keep the valid FVG requirement but enter at the 5m FVG confirmation close instead of waiting for retest.
2. `breakout_close`: enter on the first 5m close outside ORB with no FVG requirement.

Result: the retest remains an important quality/liquidity filter. ORB sleeve baseline was `+359.5R / -21.2R DD`; `fvg_close` fell to `+28.3R / -54.8R DD`; `breakout_close` fell to `-40.6R / -119.8R DD`. `breakout_close` improved NQ Asia raw R in isolation, but ES Asia degraded sharply and ES NY became structurally negative.

Report: `backtesting/learnings/reports/ALPHA_V1_ORB_CLOSE_ENTRY_PROBE.md`

### Promising Excluded/Paused ORB Candidate Probe (2026-04-26)

Extended the same close-entry screen to three non-ALPHA candidates that remain worth tracking: `NQ Asia-2 backup`, `GC NY R3 paused`, and `GC Asia-1 diversifier` over `2016-04-17` to `2026-03-24`. Regime gates were not applied in this broad entry-mechanics pass.

Result: `fvg_close` is a broad NO-GO. It did not improve any candidate cleanly. `breakout_close` is also a clear NO-GO for both GC candidates (`GC NY R3` fell from `+153.7R` baseline to `-43.0R`; `GC Asia-1` fell from `+114.7R` to `-120.4R`). The only open thread is `NQ Asia-2 breakout_close`, which improved full-history R from `+177.8R` to `+285.5R` and holdout R from `+38.3R` to `+71.4R`, but at the cost of wider DD (`-17.5R` to `-24.0R`) and lower Sharpe (`1.95` to `1.70`). Treat it as a separate high-flow NQ Asia branch needing prop/risk/regime validation, not as a general replacement for retest entries.

Report: `backtesting/learnings/reports/PROMISING_ORB_CLOSE_ENTRY_PROBE.md`

---

## ATH Regime First Pass (2026-05-05)

Report: `backtesting/learnings/reports/ALPHA_V1_ATH_REGIME_FIRST_PASS_20260505.md`

Artifacts: `backtesting/data/results/alpha_v1_ath_regime_first_pass_20260505/`

Scope was the active ALPHA_V1 baseline trade set from the 2026-05-02 reentry promotion packet: `3,470` filled trades across `NQ NY HTF-LSI`, `NQ Asia ORB`, `ES Asia ORB`, and `ES NY ORB`, annotated with point-in-time ATH features from local continuous futures data only.

**First read: promising as attribution, not yet a live filter.** The clearest broad weak bucket is signal-time `0.5-1%` below futures ATH. Full history is almost flat in that zone (`381` trades, `+2.6R`, `0.01R` avg, `46.7%` WR), while the full portfolio baseline is `+579.5R`, `0.167R` avg, `54.0%` WR. A simple skip probe preserves full-history net R (`+576.9R`) while raising avg R to `0.187` and PF from `1.41` to `1.46`; in `2025+`, the same skip improves `+106.3R / -11.2R DD` to `+111.5R / -8.5R DD`.

Leg-level behavior is not a universal "near ATH good" rule:
- `ES Asia ORB` likes the closest ATH band: `0-0.5%` below ATH produced `325` trades, `+61.1R`, `0.188R` avg, with much lower SL rate (`21.2%`) than its baseline.
- `NQ Asia ORB` is strongest in deeper ATH drawdowns or `1-2%` below ATH, not simply right at ATH.
- `NQ NY HTF-LSI` is strongest around `2-5%` below futures ATH (`102` trades, `+42.1R`, `0.412R` avg).
- `ES NY ORB` also dislikes the `0.5-1%` band, but has good buckets both very near ATH and far below ATH.

**Next step:** pre-register and validate `skip_pct_0p5_1_all` with same-regime OOS and a full-calendar gated-system run before any execution work. Separately diagnose ES-near-ATH and HTF-LSI `2-5%` behavior as leg-specific theses.

---

## Risk Factors

1. **Long-biased**: All 4 legs are long-only. No short-side hedge. A sustained bear market hits all legs simultaneously.
2. **NQ + ES concentration**: All 4 legs trade equity index futures (NQ or ES). No commodity diversification — GC is paused due to Apex ban.
3. **Equity correlation in stress**: NQ and ES co-drawdown during risk-off events (March 2020 type). Without GC as a partial decorrelator, all legs are exposed to the same macro risk.
4. **Portfolio-level projections are mixed-vintage**: Older lifecycle-style legacy figures should be treated as historical context only. The active NQ NY leg is now HTF-LSI, and the full four-leg exact rerun on the tightened live row is still pending.
5. **The new HTF swap is a live-policy update, not a fully rerun portfolio dossier yet**: The NQ NY leg is backed by exact single-leg replay and replacement sizing packets, but the complete `ALPHA_V1` stack has not yet been rerun end-to-end on the tighter `08:30-13:30 / rr3.5 / tp0.4` row.
6. **Prop firm instrument restrictions**: Apex Trader Funding bans GC trading, removing the strongest non-equity diversifier from the portfolio. Monitor for policy changes or alternative prop firms that allow GC.

### Hot-Regime Ablation / Overfit Candidate Pass (2026-05-03)

Report: `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_ABLATION_20260503.md`

Artifacts: `backtesting/data/results/alpha_v1_hot_regime_ablation_20260503/`

Intentional TESTING-only research pass inspired by `TESTING.H_ORB_ABLATED`: maximize recent R with last 1y weighted most, last 2y second, and full 10y as warning context. Hot score used: `3*last1_net + 2*last2_net + full_net - 0.50*abs(last1_dd) - 0.25*abs(last2_dd) - 0.10*abs(full_dd) - 10*full_negative_years - 25*(last1_fills<12)`. Window was `2016-04-17` to `2026-03-24`.

Best hot-score candidates by active leg:

| Leg | Candidate | Full R / DD | Last 2y R | Last 1y R | Warning |
|-----|-----------|-------------|-----------|-----------|---------|
| NQ NY HTF-LSI | `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL20_R2__lag24__cap2__mode_fvg_limit` | `113.2R / -17.91R` | `29.9R` | `16.61R` | 1 negative year |
| NQ Asia ORB | `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__uncapped_any__fvg_first__wide_none` | `242.84R / -14.22R` | `61.07R` | `41.4R` | warning layer acceptable for TESTING |
| ES Asia ORB | `combo__entry_0600__dow_baseline__rr4p0_tp0p25__stop_orb_pct_125p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` | `203.35R / -17.05R` | `44.8R` | `38.33R` | warning layer acceptable for TESTING |
| ES NY ORB | `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p25__cap2_any__fvg_first__wide_none` | `157.1R / -20.62R` | `48.48R` | `19.75R` | 1 negative year |

Research read: this pass should not supersede the robust ALPHA_V1 operating profile. Use it to select dry-run TESTING candidates only, with full-history drawdown/negative-year warnings attached.

#### Expanded top-3 Cartesian follow-up

Report: `backtesting/learnings/reports/ALPHA_V1_HOT_REGIME_EXPANDED_GRID_20260503.md`

Artifacts: `backtesting/data/results/alpha_v1_hot_regime_expanded_grid_20260503/`

Follow-up grid expanded the top-ranked OAT families into 4,378 scored variants. It kept the intentionally hot-regime objective, but constrained clearly destructive branches from the first pass: FVG extreme chasing, wide-stop target compression, and close-entry HTF-LSI. Score formula was unchanged.

Best expanded hot-score candidates by active leg:

| Leg | Expanded candidate | Full R / DD | Last 2y R / DD | Last 1y R / DD | Warning |
|-----|--------------------|-------------|----------------|----------------|---------|
| NQ NY HTF-LSI | `combo__window_0830_1430__dow_none__rr3p5_tp0p4__gap1p0__fvgL10_R2__lag24__cap2__mode_fvg_limit` | `113.04R / -16.33R` | `31.22R / -8.48R` | `18.06R / -5.62R` | 0 negative years, but worse DD than baseline |
| NQ Asia ORB | `combo__entry_2230__dow_none__rr6p0_tp0p3__stop_orb_pct_100p0__min_gap_orb_pct_10p0__cap2_after_nonpositive__fvg_first__wide_none` | `243.62R / -14.22R` | `61.07R / -7.00R` | `41.40R / -7.00R` | Better recent R, full DD worse than baseline |
| ES Asia ORB | `combo__entry_0600__dow_baseline__rr1p5_tp0p7__stop_orb_pct_125p0__min_gap_atr_pct_0p25__uncapped_any__fvg_first__wide_none` | `252.59R / -21.65R` | `61.17R / -16.07R` | `38.52R / -6.38R` | 1 negative year, lower PF, high trade count |
| ES NY ORB | `combo__entry_1300__dow_baseline__rr7p0_tp0p2__stop_atr_pct_5p0__min_gap_atr_pct_0p5__cap2_any__fvg_first__wide_none` | `165.11R / -22.30R` | `50.06R / -13.25R` | `20.03R / -13.25R` | 0 negative years, but last-1y DD worsens |

Portfolio proxy replacing all four baseline legs with these expanded best-score rows improved total net R from `+578.51R` to `+774.36R`, last-2y from `+140.46R` to `+203.52R`, and last-1y from `+90.38R` to `+118.02R`. The cost is obvious: PF drops from `1.401` to `1.287`, full DD worsens from `-15.40R` to `-25.83R`, and last-1y DD worsens from `-11.21R` to `-18.20R`.

Pure last-1y maximizers exist, especially NQ Asia `entry_2315/gap0/cap1` at `+49.70R` last-1y and ES Asia `entry_0400/exMon/stop75/uncapped` at `+56.50R` last-1y. Those are more fragile than the best-score rows and should only be used as explicit hot-regime dry-run experiments.
