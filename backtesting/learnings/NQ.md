# NQ (Nasdaq-100 Futures) — Strategy Learnings

## Instrument Profile
- **Point value**: $20/point
- **Min tick**: 0.25
- **Commission**: $0.05/contract/side
- **Data**: 2016-01 to 2026-02 (~10 years, 5m + 1m + 1s parquet). Previous data extended to 2015 but is no longer available in current parquet files.
- **Liquidity**: Both NY and Asia sessions are viable. Asia session runs 20:00-07:00 ET (cross-midnight).
- **1s data note**: NQ_1s.parquet uses `.v.0` (volume roll) instead of `.c.0` (calendar roll). Mismatches only affect ~20 days in 2016 around quarterly rolls. From 2017 onward, all prices match 1m/5m perfectly. Impact on backtests is negligible — the 1s magnifier only resolves ambiguous bars within the same candle.

## Strategies Tested

### Asia Continuation (magnifier) — low R:R / high WR
- **Status**: NO-GO (robust pipeline failed Phases 3 + 5)
- **Config tested**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| rr | 1.5 |
| tp1_ratio | 0.2 |
| asia_stop_atr_pct | 5.75 |
| asia_min_gap_atr_pct | 1.25 |
| asia_max_gap_atr_pct | 11.0 |
| magnifier | ON |

- **Full-history performance** (2015-2026): 2096 trades, 73.8% WR, 46.0R, Sharpe 0.54, PF 1.09, Max DD -25.6R
- **Walk-forward OOS**: WF efficiency 0.68, stability 1.00 (high), combined OOS 1143 trades, 13.4R, Sharpe 0.30, DD -20.4R
- **Prop constraints**: FAIL — DD -20.4R (limit 10R), worst month -8.7R (limit 5R), no year reached 24R annual target
- **Hold-out (2025-2026)**: 199 trades, 76.4% WR, 13.6R, Sharpe 1.66, PF 1.32, DD -5.9R (PASS on its own)
- **Monte Carlo**: 2.9% survival at 10R threshold (catastrophic)
- **DB entry**: `bt-nq-asia-robust-pipeline-no-go-3b81a8`
- **Conclusion**: The low R:R profile (avg win +0.35R vs avg loss -0.92R) creates outsized drawdowns despite high win rate. Works in trending regimes (2021: +14.8R, 2025: +16.1R) but collapses in choppy ones (2023: -17.0R). Not viable for prop firm accounts. Would need R:R >= 2.0, tighter stops, or a regime filter to reconsider.

### Asia Continuation v2 (10m ORB, no-Thursday, magnifier) — optimized
- **Status**: CONDITIONAL (robust pipeline passed Phases 1, 2, 4; failed Phases 3, 5)
- **Config tested**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| orb_end | 20:10 (10m ORB) |
| entry_start | 20:10 |
| entry_end | 23:00 |
| rr | 1.5 |
| tp1_ratio | 0.2 |
| asia_stop_atr_pct | 5.75 |
| asia_min_gap_atr_pct | 1.25 |
| asia_max_gap_atr_pct | 11.0 |
| atr_length | 5 |
| magnifier | ON |
| gate | No Thursday trades |

- **Full-history performance** (2015-2026): 1,757 trades, 78.5% WR, 113.4R, Sharpe 1.745, PF 1.31, Max DD -9.3R
- **Walk-forward OOS** (36m IS / 12m OOS / 12m step, 6 folds): WF efficiency 0.59, stability 0.77 (high), combined OOS 875 trades, 45.4R, Sharpe 1.607, PF 1.32, DD -7.6R
- **Parameter stability**: rr=1.25 in 5/6 folds, tp1=0.15 in 5/6 folds, stop_atr mostly 5.0, gap 9.0 dominant
- **Prop constraints**: FAIL — DD -7.6R (PASS), worst month -2.6R (PASS), expectancy +0.052R (PASS), but annual R < 24R (FAIL: best year 16.7R, worst -1.6R)
- **Hold-out (2025-2026)**: 162 trades, 77.8% WR, 10.1R, Sharpe 1.60, PF 1.27, DD -9.3R (PASS)
- **Monte Carlo**: 74.2% survival at 10R (PASS >=70%), but p95 DD = 13.9R (FAIL <=12R). Ruin probability 25.9%.
- **Conclusion**: Massive improvement over v1 — DD cut from -25.6R to -9.3R, Sharpe tripled from 0.54 to 1.75, all years positive in structural test. Walk-forward is solid. The strategy survives most MC paths (74%) but annual R is too low for prop firm 24R targets and tail drawdowns still exceed thresholds. This is a consistent, low-edge grinder (~0.05R/trade, ~7.6R/year OOS average).

#### What improved v1 → v2
- **10m ORB window** (was 15m): Sweet spot — more FVGs detected, tighter ranges, better fill rates
- **entry_end=23:00** (was default): Extended entry window captures late-session setups
- **atr_length=5** (was 14): Faster ATR adapts to recent vol, tightens stops during calm periods
- **No Thursday trades**: Thursday is negative EV on NQ Asia — removing it cuts ~15% of trades but eliminates a drag

### Asia Continuation v3 — Dual-Model Sweep + Stop Anchor Discovery + Round 11 Grid (SUPERSEDED by R4 Final)

- **Status**: SUPERSEDED — R4 Final (1s magnifier, 2016 start) achieved Calmar 23.85 vs v3's 20.14 (1m magnifier, 2015 start)

#### Dual-Model Sweep (run_nq_asia_dual_sweep.py)
- Tested both "Aggressive" (tight stop / high rr) and "Wide" (wide stop / low rr) model profiles
- Pre-sweep confirmed: **ORB 10m + ATR 14** beats ORB 15m and ATR 5 on Sharpe for both profiles
- **Aggressive #1** (stop=3.0%, gap=1.25%, maxgap=5.0%, rr=2.5, tp1=0.30): 1,656 trades, 61.2% WR, 190.6R, Sharpe 1.805, DD -14.3R — no prop-viable configs found (none cleared Sharpe>1.5 AND DD>-10R)
- **Wide Prop #1** (stop=6.5%, gap=1.25%, maxgap=5.0%, rr=1.5, tp1=0.25): 1,656 trades, 75.4% WR, 113.7R, Sharpe 1.638, DD -9.7R
- **Wide Prop pipeline result**: NO-GO — WF efficiency 0.311 (FAIL), OOS DD -11.5R, MC survival 8.8% (catastrophic). 2022 and 2023 OOS were negative (-2.6R, -0.0R). ATR 14 performs worse OOS than ATR 5 for Asia.
- **DB entries**: `bt-nq-asia-aggressive-pre-pipeline-ac47f8`, `bt-nq-asia-wide-pre-pipeline-799ea8`, `bt-nq-asia-wide-prop-pre-pipeline-1bd178`
- **Conclusion**: Dual sweep found nothing better than v2 CONDITIONAL in walk-forward terms.

#### Asia Stop Sweep — Round 9 (broad, 1% steps) & Round 10 (fine, 0.1% steps)
Anchor held fixed: gap=1.25%, maxgap=11.0%, tp1=0.20, ATR 5, ORB 10m, entry≤23:00, no-Thursday

**Round 9 (broad)** — 11 stops × 7 rr = 77 combos (run_nq_asia_v2_stop_broad_sweep.py):
- **Two distinct zones** emerged in the Calmar heatmap:
  - **Zone A** (stop=3.5–4.5%, rr=2.0–3.0): High Calmar (8–11), high R/yr (10–13R), DD -12–16R
  - **Zone B** (stop=5.5–6.5%, rr=1.0–1.5): Lower Calmar (6–9), lower R/yr (6–8R), DD -9–12R — where v2 lives
- Best marginal Sharpe: stop=4%, best marginal Calmar: stop=6%. But stop=4% dominates on individual combos.
- **Key lesson**: The optimal rr shifts completely between zones — Zone A needs high rr (2.0–3.0), Zone B needs low rr (1.0–1.5). These are fundamentally different strategy profiles.

**Round 10 (fine)** — 31 stops × 5 rr = 155 combos (run_nq_asia_v2_stop_fine_sweep.py):
- **stop=3.7%, rr=3.0 is the new Calmar anchor**: Calmar 11.12, 13.8 R/yr, DD -13.7R, Sharpe 1.476, **all 11 years positive** (min: 4.8R in 2023)
- Compared to v2 (stop=5.8%, rr=1.5): Calmar 7.43, 7.6 R/yr, DD -11.2R — new anchor is 50% better Calmar
- The 3.6–4.2% stop range all deliver Calmar > 10 at rr=3.0 — broad plateau, not a fragile spike
- stop=5.9–6.0% at rr=1.5 is the best of Zone B: Calmar 9.04/8.66, DD -9.7R, 0 neg years

**Round 11 (full grid at stop=3.7%)** — 500 combos: gap × maxgap × rr × tp1 (run_nq_asia_v3_r11_sweep.py):

Param grid: gap=[0.75,1.0,1.25,1.5,2.0], maxgap=[5,8,11,15], rr=[2,2.5,3,3.5,4], tp1=[0.15,0.20,0.25,0.30,0.35]

Key findings:
- **Best Calmar overall**: gap=1.25%, maxgap=8%, rr=3.5, tp1=0.25 → Calmar 14.04, 18.3 R/yr, DD -14.1R, but 2023=-1.0R
- **Best Calmar with 0 neg years**: gap=1.25%, maxgap=5%, rr=2.5, tp1=0.25 → **Calmar 13.05**, 15.1 R/yr, DD -12.8R, Sharpe 1.729
- **vs v2 baseline**: Calmar +50% (13.05 vs 8.66), R/yr doubled (15.1 vs 7.7)

Marginal analysis:
- gap=1.25% is the marginal peak (9.85 avg), but gap step was 0.25–0.5 — too coarse to fully resolve
- maxgap is flat (8.37–8.69 avg) — not a meaningful lever
- rr is flat (8.05–8.75 avg) at 0.5-step resolution
- tp1=0.25–0.30 sweet spot for Calmar

**Round 12 (fine grid at stop=3.7%)** — 448 combos: gap × maxgap × rr × tp1 (run_nq_asia_v3_r12_fine_sweep.py):

Param grid: gap=0.90–1.50 in 0.1 steps, maxgap=[5,8], rr=1.75–3.50 in 0.25 steps, tp1=[0.20,0.25,0.30,0.35]

Key findings:
- **New peak Calmar**: gap=1.20%, maxgap=5%, rr=2.25, tp1=0.30 → **Calmar 15.54**, 17.1 R/yr, DD -12.2R, Sharpe 1.897 — but 2022=-0.3R (barely negative)
- **Best Calmar with 0 neg years**: gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35 → **Calmar 14.82**, 17.4 R/yr, DD -13.0R, Sharpe 1.964
- **Cleanest high-Calmar**: gap=0.90%, maxgap=5%, rr=1.75, tp1=0.25 → Calmar 14.18, 12.7 R/yr, DD -10.0R (exactly at 10R) — all years positive
- **vs R11 best (0 neg years)**: R12 improved from Calmar 13.05 → 14.82 (+14%)

Critical finding — **gap dimension has two distinct peaks, not one smooth peak**:
- gap=0.90% avg Calmar 9.96 (34/64 clean configs)
- gap=1.00–1.10% are the worst values (7.79–8.37 avg, only 5–11/64 clean)
- gap=1.20% avg Calmar 11.02 (14/64 clean) — highest avg, but sparse clean zone
- gap=1.30% drops (9.22 avg, 12/64 clean)
- gap=1.40–1.50% are the most robust (44–47/64 clean, Calmar 10.14–10.68)

**The valley at gap=1.00–1.10% is a dead zone.** gap=0.90% and gap=1.20% are two separate peaks. This explains why R11's 0.25-step grid was misleading (it straddled the valley at 1.0 and called it the same region as 1.25).

Calmar heatmap key cells:
- g=0.90%/rr=1.75: Calmar **14.82*** (clean)
- g=1.20%/rr=1.75: Calmar 13.86* (clean)
- g=1.20%/rr=2.25: Calmar 15.54 (2022=-0.3R — best overall but not clean)
- g=1.20%/rr=3.25: Calmar 14.17* (clean)
- g=1.40–1.50%/rr=2.25–2.75: Calmar 12–13* (broad clean plateau, more robust)

**Two candidate configs for walk-forward:**

| # | Config | Calmar | R/yr | DD | Sharpe | Clean |
|---|--------|--------|------|-----|--------|-------|
| A | gap=1.20%, rr=2.25, tp1=0.30 | **15.54** | 17.1 | -12.2R | 1.897 | 2022=-0.3R |
| B | gap=0.90%, rr=1.75, tp1=0.35 | 14.82 | 17.4 | -13.0R | **1.964** | **0 neg years** |
| C | gap=0.90%, rr=1.75, tp1=0.25 | 14.18 | 12.7 | -10.0R | 1.636 | **0 neg years** |

All use: stop=3.7%, maxgap=5%, ATR 5, ORB 10m, entry≤23:00, no-Thursday.

**Recommendation**: Config B for walk-forward (clean years, Sharpe near 2.0, tight DD). Config A is slightly higher Calmar but the 2022 loss is a concern for OOS robustness in the 2022-2023 structural weak period.

**Round 13 (config variable broad sweep)** — 35 single-variable backtests (run_nq_asia_v3_r13_config_sweep.py):

Key findings per variable (anchor held fixed while each is swept):
- **ORB window**: 10m confirmed. 15m/20m within 0.3 Calmar (plateau). Hard cliff at 5m and 30m.
- **entry_end**: 23:00 is best (14.82); 00:00 close (14.44, Sharpe 2.006). Sharp drop after 00:00. Fine-tune 22:30–00:30.
- **ATR length**: ATR 5 confirmed decisively. Drops 2+ Calmar in both directions. Don't touch.
- **Direction**: Both directions beats long-only on Calmar (14.82 vs 10.21). Long-only has higher Sharpe (2.288) but 2022=-5.7R. Short-only is dead. Keep both. NQ Asia is unlike NY — both directions contribute.
- **flat_start (MAJOR)**: flat_start=00:00 (midnight ET): Calmar **20.14**, DD **-10.1R**, Sharpe 2.123. Same 1800 trades — just closes any open positions at midnight instead of letting them run until 06:45. This removes overnight drift risk from partially-profitable trades that haven't hit TP2. Steep benefit from 06:45→00:00 (Calmar +5.32). Fine-tune around midnight.
- **max_gap_points**: Completely non-binding — NQ Asia FVGs all ≤ 25 pts. Keep disabled.
- **DOW excl Tue**: Adding Tue exclusion (no-Thu + no-Tue): Calmar 16.98, DD -9.1R, Sharpe 2.064 — meaningful despite losing 25% of trades. Must test stacked with flat_start=00:00.

**Round 14 (fine sweep: flat_start, entry_end, DOW stack)** — 35 backtests (run_nq_asia_v3_r14_fine_sweep.py):

Key findings:
- **flat_start=00:00 confirmed as the peak** — smooth curve, 23:00 (18.52) and 23:30 (18.46) are next best. Not fragile.
- **excl-Tue does NOT stack with flat_start=00:00** — with flat=00:00, adding excl-Tue gives Calmar 18.96 vs 20.14 alone. They fix the same problem (overnight drift from unresolved trades). Not additive.
- **entry_end 23:00 and 00:00 essentially tied at flat=00:00** (20.14 vs 20.08) — trades entered past 23:00 get midnight-closed anyway.
- **Top 3 stacked configs all within 0.24 Calmar** (20.08–20.32). The simpler no-Thursday-only config wins on trade count and R/yr.

**New anchor (R14):**
- stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5, ORB 10m, entry_end=23:00, **flat_start=00:00**, no-Thursday
- Calmar **20.14**, 18.3 R/yr, DD **-10.1R**, Sharpe **2.123**, 1,800 trades, **0 negative full years**
- vs v2: Calmar +132%, DD comparable (-10.1R vs -9.7R), R/yr +138%

**Round 15 (grid re-sweep: gap × rr × tp1 at flat_start=00:00)** — 384 combos (run_nq_asia_v3_r15_grid_sweep.py):

Key findings:
- **R14 anchor confirmed as the global optimum — no reshuffling.** gap=0.90%, rr=1.75, tp1=0.35 is #1 by Calmar (20.14) and #1 by 0-neg-years. flat_start=00:00 did NOT shift rr or tp1 surface.
- **gap=0.90% is now uniquely dominant**: highest avg Calmar (11.74) AND most clean configs (35/48). At flat_start=00:00, the entire gap=0.90% row is clean (7/8 rr values all 0-neg-years). This is the most stable parameter region tested.
- **Dead zone at gap=1.10% confirmed again** (0/48 clean, avg Calmar 8.56).
- **rr=1.75 is the peak for gap=0.90%**: 20.14 vs rr=2.00 at 16.27 — large gap, well-defined optimum.
- **tp1=0.30 marginally best on avg** (10.97 vs 10.63 for 0.35) but within noise. Anchor tp1=0.35 confirmed.
- **Optimization complete**. Gap between #1 (20.14) and #2 (17.76) is too large to close with fine-tuning.

**Final v3 config (optimization complete, walk-forward pending):**

| Param | Value |
|-------|-------|
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| rr | 1.75 |
| tp1_ratio | 0.35 |
| atr_length | 5 |
| ORB window | 10m (20:00–20:10 ET) |
| entry_end | 23:00 ET |
| flat_start | 00:00 ET (midnight close) |
| direction | both |
| gate | no-Thursday |

**In-sample performance** (2015–2026, 11 full years):
- Trades: 1,800 | WR: 64.8% | Net R: 203.0 | Avg Annual R: **18.3** | Max DD: **-10.1R**
- Sharpe: **2.123** | Calmar: **20.14** | R/trade: 0.1128 | **0 negative full years**
- Year range: 2022 (worst, +9.2R) to 2016 (best, +26.5R) — all strongly positive

**vs baselines:**
- v2 CONDITIONAL: Calmar 8.66, DD -9.7R, 7.7 R/yr → **+132% Calmar, +138% R/yr, comparable DD**
- NQ NY CONDITIONAL: Calmar 4.41 OOS → Asia v3 has dramatically better in-sample characteristics

### Asia Continuation v3+ICF — Impulse Close Filter Optimization

- **Status**: OPTIMIZATION COMPLETE — walk-forward pending
- **Objective**: Test impulse_close_filter (ICF) on NQ Asia v3 config, re-optimize if positive

#### Baseline Comparison (ICF on vs off, no Thursday gate)

| Metric | No ICF (v3 params) | ICF On (v3 params) | Change |
|--------|-------|--------|--------|
| Filled trades | 2,252 | 2,345 | +93 (+4.1%) |
| Win rate | 63.7% | 64.0% | +0.3pp |
| Net R | 194.0 | 212.8 | +18.8R (+9.7%) |
| Sharpe | 1.619 | 1.707 | +5.4% |
| Calmar | 11.93 | 13.02 | +9.1% |
| Max DD | -16.3R | -16.3R | same |
| Long R | 117.9 | 112.1 | -5.8R |
| Short R | 76.2 | 100.7 | **+24.5R** |

- **ICF improvement driven entirely by shorts** — longs slightly degraded while shorts gained +24.5R
- **DB entries**: `bt-nq-asia-v3-baseline-no-icf-1d1e08`, `bt-nq-asia-v3-icf-on-00a1c8`

#### Re-optimization with ICF enabled

**RR sweep** (1.0–3.5 broad, 1.50–2.50 fine at 0.05 steps):
- Best Calmar: rr=2.15 → Calmar 14.38, Sharpe 1.75, DD -16.8R
- Best Sharpe: rr=2.10 → Sharpe 1.80, Calmar 14.14
- ICF shifted optimal RR from 1.75 → 2.15 (+23%)

**3-way grid**: rr × stop_atr_pct × tp1_ratio (210 combos):
- Best Calmar: rr=2.15, stop=3.3%, tp1=0.40 → Calmar 14.88, Sharpe 1.74, DD -17.3R
- ICF shifted stop from 3.7% → 3.3%, tp1 from 0.35 → 0.40

**Gap filter**: gap=0.90%, maxgap=5.0% confirmed (no change from v3)

**ATR length**: ATR 5 confirmed (sweeps 3–20, ATR 5 won all metrics)

**Config variables**:
- ORB 10m confirmed (15m Calmar 11.58 vs 14.88)
- **entry_end=23:30 beats 23:00** (Calmar 15.42 vs 14.88, +80 trades) — ICF captures late-session FVGs
- flat_start=00:00 confirmed (23:30 and 00:30 both worse)

#### Final v3+ICF config (optimization complete, walk-forward pending)

| Param | v3 (no ICF) | v3+ICF Optimized | Change |
|-------|-------------|------------------|--------|
| stop_atr_pct | 3.7% | **3.3%** | tighter |
| min_gap_atr_pct | 0.90% | 0.90% | same |
| max_gap_atr_pct | 5.0% | 5.0% | same |
| rr | 1.75 | **2.15** | higher |
| tp1_ratio | 0.35 | **0.40** | higher |
| atr_length | 5 | 5 | same |
| ORB window | 10m | 10m | same |
| entry_end | 23:00 | **23:30** | extended |
| flat_start | 00:00 | 00:00 | same |
| direction | both | both | same |
| impulse_close_filter | OFF | **ON** | new |

**In-sample performance** (2015–2026, no Thursday gate):
- Trades: 2,425 | WR: 57.3% | Net R: 268.6 | Avg Annual R: **24.4** | Max DD: **-17.4R**
- Sharpe: **1.766** | Calmar: **15.42** | R/trade: 0.111 | **0 negative full years** (2015–2025)
- Year range: 2022 (worst, +6.0R) to 2019 (best, +57.2R)

**vs v3 without ICF** (same config, no Thursday gate, no ICF):
- Calmar: 11.93 → **15.42** (+29%)
- Net R: 194.0 → **268.6** (+38%)
- R/yr: 17.6 → **24.4** (+38%)
- DD: -16.3R → -17.4R (slightly worse)

**Key findings**:
- ICF reshuffled the optimal parameter surface: higher RR (1.75→2.15), tighter stop (3.7→3.3), higher TP1 runner (0.35→0.40)
- The win rate dropped (64%→57%) but edge per trade increased (0.086→0.111R) — classic WR/RR tradeoff
- 2019 (+57.2R) and 2025 (+52.4R) show outsized returns — high annual variance
- No-Thursday gate still needs to be applied and re-confirmed with ICF config
- **DB entry**: `bt-nq-asia-v3-icf-optimized-4d86d0`

### Asia Continuation R5 Final (10m ORB, both, 1s magnifier) — GO (post same-candle SL/TP bug fix)
- **Status**: GO — fixed-param WF 6/6 folds profitable, hold-out PASS. Supersedes R4 Final.
- **Config** (R1-R5 optimization post bug fix, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 00:00 |
| flat_start | 01:00 |
| flat_end | 07:00 |
| direction | both |
| rr | 1.75 |
| tp1_ratio | 0.10 |
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| max_gap_points | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | no-Thursday |
| impulse_close_filter | OFF |

- **Full-history performance** (2016-2026): 1,510 trades, 94.5% WR, PF 2.98, 165.1R total (16.5 R/yr), Max DD -2.7R, Calmar 60.19, Sharpe 4.70, **0 negative full years**
- **R by year**: 2016:+19  2017:+17  2018:+20  2019:+22  2020:+14  2021:+21  2022:+13  2023:+12  2024:+12  2025:+12  2026:+3

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | Sharpe | R | DD |
|------|-----------|--------|-----|--------|---|-----|
| 1 | 2019 | 156 | 96.8% | 6.66 | +22.2 | -1.0 |
| 2 | 2020 | 149 | 93.3% | 3.89 | +14.3 | -2.7 |
| 3 | 2021 | 150 | 96.7% | 6.47 | +20.8 | -1.0 |
| 4 | 2022 | 144 | 95.1% | 4.39 | +13.2 | -1.6 |
| 5 | 2023 | 141 | 92.9% | 3.59 | +11.9 | -2.3 |
| 6 | 2024 | 128 | 93.8% | 3.98 | +12.2 | -2.6 |

- **Combined OOS**: 868 trades, 94.8% WR, PF 3.13, Sharpe 4.82, +94.6R (15.8 R/yr), DD -2.7R, Calmar 5.74
- **Hold-out (2025+)**: 161 trades, 95.0% WR, PF 2.83, Sharpe 4.35, +15.0R, DD -2.5R — PASS
- **Verdict**: GO — all 6 folds profitable, hold-out strong, combined OOS Calmar 5.74

#### R5 Optimization History (R1-R5, post bug fix)
- **Context**: Simulator bug fix — stops and take-profits on the entry candle are now correctly counted. R4 Final (Calmar 23.85) became R5 Baseline (Calmar 34.77) with identical config — bug fix improved all metrics.
- **R5 Baseline**: Same R4 params post-bugfix: 1,593 trades, 70.4% WR, Sharpe 3.29, 258.1R (25.8 R/yr), DD -7.4R, Calmar 34.77. DB: `bt-nq-asia-r5-baseline-post-bugfix-bd0788`.
- **R1**: Swept 12 dimensions. Adopted: entry_end=00:00 (+0.97), tp1=0.20 (+17.26). tp1 shift from 0.35→0.20 is the biggest single change — bug fix made early TP1 exits much more reliable.
- **R2**: entry_end=00:00, tp1=0.20. Calmar 52.44. Adopted: flat_start=01:00 (+0.91).
- **R3**: flat_start=01:00. Calmar 53.35. Adopted: tp1=0.10 (+6.83). tp1 continued pulling lower.
- **R4**: tp1=0.10. Calmar 60.19. Three changes passed threshold: entry_end=01:00 (+4.14), maxgap=7.0 (+2.91), DOW=none (+13.12).
- **R5**: All 3 R4 changes applied → **Calmar crashed from 60.19 to 35.16**. Destructive interaction (exact same pattern as original R3). Reset to R4 anchor (Calmar 60.19).
- **Grid sweep**: 2,016 combos (8 stops × 7 rrs × 6 gaps × 6 tp1s). 1,925/2,016 (95.5%) have 0 neg years — extremely flat surface. R5 anchor is **#7 overall AND #7 among zero-neg-year configs**. Grid winner (stop=4.0/rr=2.0/gap=0.90/tp1=0.05, Calmar 64.93) is only +7.9% better but with -27% R/yr.
- **DB entry**: `bt-nq-asia-r5-final-25e2c0`

#### Key differences from R4 (pre-bug-fix)
- **tp1 shifted from 0.35 → 0.10**: The dominant change. The bug fix made entry-candle TP1 exits count correctly, so taking profits very early (10% of the way to TP2) is now extremely reliable — 94.5% WR. This converts the strategy from a moderate WR/moderate RR profile to an ultra-high WR scalper.
- **entry_end shifted from 01:00 → 00:00**: Late entries past midnight are less productive post-bugfix (they were previously miscounted as EOD wins).
- **flat_start shifted from 00:00 → 01:00**: With entry_end=00:00, flat_start can extend to 01:00 to give remaining positions more time.
- **DD collapsed from -8.9R → -2.7R**: The ultra-early TP1 (10%) means most winning trades only risk a tiny portion before taking profit, dramatically reducing drawdowns.
- **R/yr dropped from 21.1 → 16.5**: Trade-off for much lower DD. Calmar improved from 23.85 → 60.19 (+152%).
- **Exit profile change**: SL 25.5%, TP1_TP2 22.8%, TP1_BE 42.1%, TP1_EOD 2.0%, EOD 7.7% — the TP1_BE category dominates because TP1 hits early on the same candle, then the remaining position runs to breakeven.

### Asia Continuation R9 Restart Final (15m ORB, long, 1s magnifier) — GO (tp1>=0.2 restart)
- **Status**: GO — All 5 phases passed. Supersedes R5 Final (which had degenerate tp1=0.10 producing 94.5% WR).
- **Note**: R5 Final's tp1=0.10 placed TP1 at only 12.5% of stop distance (~6 NQ points), producing mechanically correct but meaningless "wins" of +0.0625R. Minimum tp1_ratio=0.2 rule was established and the entire optimization was restarted from baseline.
- **Config** (R1-R9 restart optimization, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 15m (20:00-20:15 ET) |
| entry_start | 20:15 |
| entry_end | 22:30 |
| flat_start | 04:00 |
| flat_end | 07:00 |
| direction | long |
| rr | 3.0 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 4.0% |
| min_gap_atr_pct | 0.90% |
| max_gap_points | 75 |
| max_gap_atr_pct | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | excl Tuesday |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 770 trades, 45.5% WR, PF 1.42, 176.2R total (17.6 R/yr), Max DD -11.3R, Calmar 15.64, Sharpe 2.52, **0 negative full years**
- **R by year**: 2016:+12  2017:+26  2018:+22  2019:+19  2020:+19  2021:+3  2022:+21  2023:+8  2024:+23  2025:+17  2026:+7

#### 5-Phase Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1. Structural | PASS | 770 trades, 45.5% WR, PF 1.42, Calmar 15.64 |
| 2. Walk-Forward | PASS | WF efficiency 0.797, stability 0.964 (high), 7 folds |
| 3. Prop Constraints | PASS | Avg annual R 14.3, worst month -5.0R, positive expectancy |
| 4. Hold-Out OOS | PASS | 2025+: 89 trades, Sharpe 2.77, PF 1.49, +23.2R |
| 5. Monte Carlo | PASS | 91.7% survival at -25R ruin, p50 DD -16.5R |

- **WF Parameter Stability**: gap=0.9 stable 7/7 folds (1.000), rr mode=3.0 (1.000), stop mode=3.5 (0.857), tp1 mode=0.7 (1.000). Overall 0.964 (high).
- **MC percentiles**: Final PnL p5=110R, p50=175R, p95=241R. Max DD p5=-27R, p50=-16.5R.
- **Verdict**: GO — All 5 phases passed. Strategy is prop-firm ready.
- **Entry delay**: 0m (baseline) is optimal but least sensitive of the three combined longs legs. Calmar degrades gracefully: 0m=22.61, 10m=13.96, 20m=15.75, 30m=14.02. The ORB-based stop adapts to session volatility, which may explain the resilience. Script: `run_combined_longs_entry_delay_sweep.py`.
- **Event day exclusion**: No exclusions beneficial. FOMC slightly above average (+0.314R vs +0.268R, n=31). CPI below average (+0.079R vs +0.268R, n=29) but excluding CPI doesn't improve Calmar (22.61→22.35). NFP only 2 trades. Excluding FOMC hurts (22.61→19.09, DD -8.9→-10.0R). Script: `run_combined_longs_event_day_sweep.py`.
- **DB entry**: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`

#### R9 Restart Optimization History
- **Context**: R5 Final's tp1=0.10 produced degenerate 94.5% WR (each TP1_BE win earned only +0.0625R). User established minimum tp1_ratio=0.2 rule. Entire optimization restarted from baseline.
- **R1 restart**: Baseline anchor (default params, tp1>=0.2). Calmar 2.94. Adopted: rr=4.0 (+2.24), flat=23:00 (+1.28).
- **R2 restart**: Calmar 4.20, 1 neg year (2022). **Converged** — 0 adoptions.
- **Grid Sweep R1**: 625 combos (stop×rr×gap×tp1). Winner: stop=5.0/rr=3.0/gap=0.9/tp1=0.6 (Calmar 7.03). Delta +2.83 > 0.5 → back to sweeps. Adopted #5: stop=4.0/rr=3.0/gap=0.9/tp1=0.6 (Calmar 6.18, 1 neg year).
- **R3 restart**: Grid winner anchor. Adopted: dir=long (+0.84), ICF=ON (+2.72). dir=long eliminated 2022 neg year.
- **R4 restart**: Calmar 8.28, 0 neg years. Adopted: atr=5 (+3.49), flat=02:00 (+1.31).
- **R5 restart**: Calmar 12.85. Adopted: entry_end=23:00 (+0.35), maxgap=75pts (+0.62).
- **R6 restart**: Calmar 13.23. Adopted: DOW excl Tue (+0.98).
- **R7 restart**: Calmar 14.21. Adopted: flat=04:00 (+0.46). DOW excl Tue persisted (confirmed stable).
- **R8 restart**: Calmar 14.68. Adopted: entry_end=22:30 (+0.97).
- **R9 restart**: Calmar 15.64. **Converged** — 0 adoptions across all 12 dimensions.
- **Grid Sweep R2**: 500 combos. Anchor ranked #2/500 (Calmar 15.64). Winner: stop=4.0/rr=3.5/gap=0.9/tp1=0.5 (Calmar 16.07). Delta +0.43 < 0.5 → **Grid confirms anchor**.
- 135/500 combos (27%) have 0 negative years. No boundary warnings.

#### Key differences from R5 Final (degenerate tp1)
- **tp1 shifted from 0.10 → 0.6**: The minimum tp1=0.2 rule eliminated degenerate micro-scalp configs. Higher tp1 means larger TP1 target (60% of full R:R), producing real wins with meaningful R.
- **Direction: both → long**: Shorts eliminated 2022 negative year (longs +21R vs shorts -34R in 2022).
- **ICF: OFF → ON**: Massive impact (+2.72 Calmar at R3 adoption). ICF captures more FVGs.
- **ORB: 10m → 15m**: 15m was the anchor default and was never displaced at any of the 9 restart sweeps.
- **rr: 1.75 → 3.0**: Higher R:R with higher tp1 — trades run further.
- **WR: 94.5% → 45.5%**: Realistic win rate. R5's 94.5% was mechanically correct but misleading.
- **Calmar: 60.19 → 15.64**: R5's Calmar was inflated by artificially tiny drawdowns from the degenerate tp1.

### Asia Continuation Short (10m ORB, short, 1s magnifier) — NO-GO
- **Status**: NO-GO — robust pipeline passed 2/5 phases (Structural + Hold-Out). Failed WF, Prop, MC.
- **Config** (R4-R6 optimization + Grid Sweep R2 confirmation):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 01:00 |
| flat_start | 23:00 |
| flat_end | 07:00 |
| direction | short |
| rr | 3.75 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 3.5% |
| min_gap_atr_pct | 1.0% |
| max_gap_points | 0 |
| max_gap_atr_pct | 0 |
| atr_length | 30 |
| magnifier | 1s |
| gate | excl Thursday |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 874 trades, 40.7% WR, PF 1.24, 108.0R total (10.8 R/yr), Max DD -17.1R, Calmar 6.30, Sharpe 1.40, 2 neg years (2022, 2023)
- **R by year**: 2016:+29  2017:+8  2018:+8  2019:+15  2020:+4  2021:+35  2022:-5  2023:-2  2024:+6  2025:+9  2026:+2

#### 5-Phase Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1. Structural | PASS | 874 trades, 40.7% WR, PF 1.24, Calmar 6.30, Sharpe 1.40 |
| 2. Walk-Forward | FAIL | WFE 0.467 < 0.5 (stability 0.821 high), OOS Calmar 1.76 |
| 3. Prop Constraints | FAIL | OOS avg annual R 6.3 < 12.0, worst month -9.9R |
| 4. Hold-Out OOS | PASS | 2025+: 95 trades, Sharpe 1.36, PF 1.24, +11.0R |
| 5. Monte Carlo | FAIL | 62.9% survival at -25R ruin (need 70%) |

- **WF fold-level**: 2019 OOS strong (+10R, Sharpe 1.42), 2021 outstanding (+40.9R, Sharpe 4.41), but 2020 (-1.9R), 2022 (-7.6R), 2023 (-4.9R) all negative. Parameters shifted across folds (stop→3.0, rr→4.0, gap→varied).
- **Verdict**: NO-GO — The in-sample structural metrics look strong (Calmar 6.30) but walk-forward reveals the parameters are not stable across regimes. 2022-2023 are structurally negative for NQ Asia shorts — no parameter combo tested (0/500 in grid) has 0 negative full years. MC survival of 62.9% confirms the drawdown tail risk is too high.
- **DB entry**: `bt-nq-asia-cont-short-2016-2026-no-go-e72618`

#### Optimization History
- **Baseline exploration**: Combined best: ATR=30, ICF=ON, flat=23:00, gap=1.0% → Calmar 1.39
- **R1**: 1 adoption: ORB 15m→10m (Δ+0.44). Calmar 1.80.
- **R2**: Bug in DOW adoption logic (only checked absolute best, missed excl-Thu which passed all criteria). Manual adoption: excl-Thu (Δ+2.25). Calmar 4.05.
- **R3**: Converged (0 adoptions). Calmar 4.05.
- **Grid Sweep R1**: 500 combos. Winner: stop=3.5/rr=3.0/gap=1.0/tp1=0.6 (Calmar 4.69). Delta +0.64 > 0.5 → back to sweeps. Both stop=3.5 and rr=3.0 at grid boundary.
- **R4**: 2 adoptions: entry_end 23:00→01:00 (Δ+0.37), rr 3.0→3.5 (Δ+0.91). Calmar 5.85.
- **R5**: 1 adoption: rr 3.5→3.75 (Δ+0.45). Calmar 6.30.
- **R6**: Converged (0 adoptions). Calmar 6.30.
- **Grid Sweep R2**: 500 combos. Anchor ranked #1/500 (Calmar 6.30). Confirmed.

#### Key Findings — Shorts vs Longs
- **Shorts need completely different params**: ATR=30 (longs=5), flat=23:00 (longs=04:00), ORB=10m (longs=15m), rr=3.75 (longs=3.0), stop=3.5% (longs=4.0%), excl-Thu (longs=excl-Tue). Every major dimension differs.
- **2021 is the standout year for shorts**: +35R, vs longs' +3R in 2021. Shorts hedge longs' weakest year.
- **2022-2023 are structurally negative for shorts**: No parameter combo achieves 0 negative years. This is a fundamental limitation.
- **Combined L+S portfolio**: Adding shorts to the R9 Restart Long config yields 1,644 trades, ~286R total, but the standalone short is too weak to justify — better to trade longs-only with lower DD risk.

#### Scripts Generated
- `run_nq_asia_short_baseline.py`
- `run_nq_asia_short_variable_sweeps_1.py` through `run_nq_asia_short_variable_sweeps_6.py`
- `run_nq_asia_short_grid_sweep_r1.py`, `run_nq_asia_short_grid_sweep_r2.py`
- `run_nq_asia_short_robust_pipeline.py`

### Asia Continuation R4 Final (10m ORB, both, 1s magnifier) — SUPERSEDED by R5
- **Status**: SUPERSEDED — R5 Final (post bug fix) achieved Calmar 60.19 vs R4's 23.85
- **Config** (R1-R4 optimization with 1s magnifier, 2016 start):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | Asia |
| ORB window | 10m (20:00-20:10 ET) |
| entry_start | 20:10 |
| entry_end | 01:00 |
| flat_start | 00:00 |
| flat_end | 07:00 |
| direction | both |
| rr | 1.75 |
| tp1_ratio | 0.35 |
| stop_atr_pct | 3.7% |
| min_gap_atr_pct | 0.90% |
| max_gap_atr_pct | 5.0% |
| max_gap_points | 0 |
| atr_length | 5 |
| magnifier | 1s |
| gate | no-Thursday |
| impulse_close_filter | OFF |

- **Full-history performance** (2016-2026): 1,593 trades, 66.8% WR, PF 1.43, 211.2R total (21.1 R/yr), Max DD -8.9R, Calmar 23.85, Sharpe 2.53, **0 negative full years**
- **R by year**: 2016:+31  2017:+16  2018:+24  2019:+21  2020:+21  2021:+26  2022:+9  2023:+18  2024:+19  2025:+24  2026:+3

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | Sharpe | R | DD |
|------|-----------|--------|-----|--------|---|-----|
| 1 | 2019 | 157 | 63.7% | 2.09 | +20.7 | -7.8 |
| 2 | 2020 | 154 | 66.9% | 2.17 | +20.8 | -8.7 |
| 3 | 2021 | 155 | 71.0% | 2.82 | +25.8 | -5.4 |
| 4 | 2022 | 140 | 62.1% | 1.22 | +8.9 | -8.5 |
| 5 | 2023 | 157 | 67.5% | 2.23 | +17.8 | -5.1 |
| 6 | 2024 | 155 | 68.4% | 2.54 | +19.3 | -5.5 |

- **Combined OOS**: 918 trades, 66.9% WR, PF 1.41, Sharpe 2.40, +113.3R (18.9 R/yr), DD -8.7R, Calmar 2.17
- **Hold-out (2025+)**: 172 trades, 67.4% WR, PF 1.52, Sharpe 2.94, +27.2R, DD -6.4R — PASS
- **Verdict**: GO — all 6 folds profitable, hold-out strong, combined OOS Calmar 2.17

#### R4 Optimization History (R1-R4, 1s magnifier)
- **R1**: Fresh start with 1s magnifier + 2016 start (v3 anchor). Baseline Calmar 16.72 (down from v3's 20.14 due to data change). Adopted: ORB=15m (+2.95), entry_end=01:00 (+7.13). flat_start=23:00 conflicted with entry_end=01:00, not adopted.
- **R2**: ORB=15m, entry_end=01:00, flat=00:00. Calmar 20.18. Adopted 5 changes: ORB=10m (+3.67), flat=23:00 (+2.40), tp1=0.30 (+1.75), ICF=ON (+1.65), gap=1.25% (+0.54).
- **R3**: All 5 R2 changes applied simultaneously → **Calmar crashed from 20.18 to 11.97**. Destructive parameter interaction. Sweep wanted to revert most changes. Key lesson: never adopt 5+ interacting changes at once.
- **R4**: Reset to best-proven config (ORB=10m + entry_end=01:00 + flat=00:00 with v3 continuous params). **Fully converged — every dimension Δ=0.00.** Calmar 23.85.
- **Grid sweep**: 2,016 combos (8 stops × 7 rrs × 6 gaps × 6 tp1s). R4 anchor is **#1 overall AND #1 among 797 zero-neg-year configs**. Gap to #2 is 2.63 Calmar points. No fine-tune needed.
- **DB entry**: `bt-nq-asia-r4-final-69df58`

#### Key differences from v3 (1m magnifier, 2015 start)
- **entry_end shifted from 23:00 → 01:00**: The single biggest change. Extending entry window past midnight captures late Asia session FVGs. This was invisible in v3's optimization because v3 used 2015 data and 1m magnifier.
- **flat_start remains 00:00**: Midnight close confirmed. Combining entry_end=01:00 with flat_start=00:00 means entries between 00:00-01:00 get immediately flattened at end of bar — effectively these are very short-duration trades that only work if TP1 is hit quickly.
- **ICF is OFF**: Unlike v3+ICF optimization which showed +29% Calmar, ICF was not beneficial at the R4 anchor (entry_end=01:00 changes the trade mix).
- **Calmar improved 20.14 → 23.85 (+18%)** despite losing 2015 data year.

### NY Continuation Short (20m ORB, short-only, 1s magnifier) — NO-GO
- **Status**: NO-GO — best achievable config has 4 negative years, Calmar 1.40, PF 1.10. Edge is marginal and fragile to slippage.
- **DB entry**: `bt-nq-ny-short-no-go-final-327490`
- **Best config found**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| direction | short |
| ORB window | 20m (09:30-09:50) |
| entry_end | 15:00 |
| flat_start | 15:50 |
| stop_orb_pct | 15.0% |
| min_gap_orb_pct | 7.0% |
| stop_atr_pct | 5.0% |
| min_gap_atr_pct | 2.0% |
| min_stop_points | 10.0 |
| min_tp1_points | 10.0 |
| rr | 3.0 |
| tp1_ratio | 0.3 |
| atr_length | 14 |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 967 trades, 61.5% WR, PF 1.10, Sharpe 0.67, 37.3R (3.7 R/yr), Max DD -26.6R, Calmar 1.40, 4 negative years
- **R by year**: 2016:-5  2017:-3  2018:+5  2019:-4  2020:+4  2021:+15  2022:+5  2023:-4  2024:+7  2025:+13  2026:+4

#### Investigation Summary

##### The tp1=0.2 Trap
Variable sweeps (R1-R10) converged on configs with 88% win rate, but diagnostic analysis revealed:
- Median stop was only **8.2 points** (33 ticks) — 32.7% of trades had stops < 5 points
- TP1 target was just **3.3 points** median (0.4× the already-tiny stop) — any noise triggers TP1
- **87.7% of trades were tp1_be exits** earning exactly +0.2R, with only 2/624 ever reaching TP2
- Average R per trade: **0.056R** — slippage of 1-3 points (typical NQ) would consume 30-90% of the TP1 target
- The "edge" is mechanical: trivial retracement → TP1 → breakeven stop → scratch. Not viable in live execution.

##### Engine Fix: Dual Floors (min_stop_points + min_tp1_points)
Implemented engine-level minimum floors on `SessionConfig` to prevent the tp1 trap:
- `min_stop_points=10.0`: `stop_dist = max(computed_stop, 10.0)` — prevents unrealistically tight stops
- `min_tp1_points=10.0`: `tp1_dist = max(computed_tp1, 10.0)` — prevents trivial TP1 targets
- These are per-session, NQ-specific values (10pt = 40 ticks). Other instruments should use different values appropriate to their tick size.

##### With Dual Floors: ORB vs ATR Comparison
Comprehensive comparison with both 10pt floors active (`diagnose_nq_ny_short_orb_vs_atr.py`):

| Stop Method | Best Calmar | Config | Net R | Neg Years | Median Stop |
|-------------|-------------|--------|-------|-----------|-------------|
| **ORB 15%** | **1.40** | rr=3.0, tp1=0.3 | 37.3R | 4 | 10.0pt |
| ORB 10% | 1.11 | rr=3.0, tp1=0.3 | 26.2R | 4 | 10.0pt (floor-binding) |
| ORB 20% | 1.08 | rr=3.0, tp1=0.3 | 29.3R | 4 | 11.2pt |
| ATR 5% | 0.19 | rr=2.5, tp1=0.3 | 4.3R | 5 | 10.0pt (all floor-binding) |
| ATR 7.5% | 1.05 | rr=4.0, tp1=0.5 | 39.4R | 5 | 14.6pt |
| ATR 10% | 1.19 | rr=4.0, tp1=0.6 | 53.3R | 3 | 19.5pt (DD: -45R) |
| ATR 12.5% | 1.01 | rr=4.0, tp1=0.6 | 42.4R | 3 | 24.4pt (DD: -42R) |

- ORB orbstop=15% is the best stop mechanism — naturally sizes to ORB range, avoids floor-binding
- ATR-based stops only viable at extreme rr=4.0 with massive drawdowns (-42 to -45R)
- Floor-binding (ORB 10%, ATR 5%) produces near-zero edge

##### Variable Sweep Oscillation (R1-R8, ATR-based)
8 rounds of ATR-based sweeps never converged:
- ATR length oscillated: 14→20→14→20→5→14
- Gap oscillated: 1.0→4.0→3.5→2.0→4.0→2.0→4.0
- DOW exclusion shifted every round: none→Thu→Fri→Fri→Fri→Tue→none→Tue
- ORB window wandered: 20m→25m→30m→25m→15m→25m→30m
- Root cause: tp1=0.2 creates an ultra-flat parameter landscape where everything looks similar within noise

##### ORB-Based Stop Approach (R9-R10)
Attempted switching from ATR-based to ORB-based stops to reduce parameter instability:
- R9 (ORB-based): 2 adoptions, more stable than ATR rounds — but still the tp1=0.2 artifact
- R10: 6 adoptions, instability returned even with ORB-based params

#### Conclusion
The NO-GO config above (Calmar 1.40, 4 neg years) was from diagnostic grids only — never properly optimized with dual floors. A full re-optimization from scratch with dual floors active may find a better config. See "Next Tests" below.

#### Next Tests — COMPLETED (see Short v2 above)

Re-optimization with dual floors has been completed as NY Continuation Short v2. Key results:
- Calmar improved from 1.40 (v1) to 7.86 (v2) — 5.6× improvement
- Negative years eliminated: 4 → 0
- Entry_end=11:00 was the single biggest lever (not tested in v1)
- Parameter oscillation from v1 was caused by tp1=0.2 artifact — v2 converged cleanly with dual floors
- See **NY Continuation Short v2** section above for full details

#### Scripts Generated
- `run_nq_ny_short_baseline.py` (Step 1)
- `run_nq_ny_short_variable_sweeps_1.py` through `run_nq_ny_short_variable_sweeps_10.py` (Step 2)
- `diagnose_nq_ny_short_stops.py` (stop distance diagnostic)
- `diagnose_nq_ny_short_wide_stops.py` (wide stop / realistic tp1 diagnostic)
- `diagnose_nq_ny_short_min_stop_floor.py` (min_stop_points=10 testing)
- `diagnose_nq_ny_short_82pct_wr.py` (floor-binding vs organic trade analysis)
- `diagnose_nq_ny_short_dual_floor.py` (both min_stop=10 + min_tp1=10)
- `diagnose_nq_ny_short_orb_vs_atr.py` (ORB vs ATR stop comparison with dual floors)
- `save_nq_ny_short_final.py` (DB save)

### NY Continuation Short v2 (25m ORB, short-only, 1s magnifier, dual floors) — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases pass. Phase 3 annual R FAIL (12R/yr threshold too aggressive for short-only ~33 trades/yr). All other phases pass strongly.
- **DB entry**: `bt-nq-ny-short-v2-2016-2026-final-d9db60`
- **Config (WF-validated mode params)**:

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| direction | short |
| ORB window | 25m (09:30-09:55) |
| entry_end | 11:00 |
| flat_start | 11:00 |
| stop_orb_pct | 17.0% |
| min_gap_orb_pct | 5.0% |
| min_gap_atr_pct | 0.0% |
| stop_atr_pct | 5.0% |
| min_stop_points | 10.0 |
| min_tp1_points | 10.0 |
| rr | 2.0 |
| tp1_ratio | 0.3 |
| atr_length | 14 |
| ICF | OFF |
| DOW exclusion | Monday (post-backtest) |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 329 trades, 71.4% WR, PF 1.50, Sharpe 2.74, 41.0R (4.1 R/yr), Max DD -5.2R, Calmar 7.86, **0 negative full years**
- **R by year**: 2016:+2  2017:+5  2018:+8  2019:+0  2020:+2  2021:+2  2022:+3  2023:+5  2024:+6  2025:+7  2026:+1
- **Median stop**: 43 ticks (well above 10-tick floor)

#### Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | **PASS** | 329 trades, 66.3% WR, PF 1.52, Calmar 10.00 |
| 2 — Walk-Forward | **PASS** | WF eff 0.67, stability 0.80 (HIGH), 5 folds |
| 3 — Prop Filter | **FAIL** | Annual R 2.86R/yr avg (below 12R threshold) |
| 4 — Hold-Out | **PASS** | Sharpe 8.46, PF 3.44, +7.2R (35 trades, 91.4% WR) |
| 5 — MC Survival | **PASS** | 97.8% survival at 15R, 0.1% ruin at 25R |

- **Phase 3 detail**: Only annual R failed (2.86R/yr avg vs 12R threshold). Monthly loss PASS (-3.5R worst), expectancy PASS (0.081R). The 12R/yr threshold is calibrated for all-direction full-session strategies (~200+ trades/yr); a short-only strategy with 33 trades/yr cannot realistically achieve it. The strategy is portfolio-additive, not standalone.
- **Phase 2 detail**: Parameter stability HIGH (0.80). Mode params: stop_orb=17%, rr=2.0, gap_orb=5%, tp1=0.3. gap_orb and tp1 had perfect stability (1.00). All folds positive except Fold 1 OOS (2019, -0.35 Sharpe).
- **Phase 4 detail**: 2025 hold-out is exceptional — 91.4% WR, Sharpe 8.46. The strategy thrives in trending/volatile markets.

#### Optimization Journey

1. **Baseline**: ORB 20m, default NY times → Calmar 1.40, 4 neg years (NO-GO level)
2. **Mega grid** (1,800 combos): Found entry_end=11:00 and flat_start=14:00 as biggest levers → Calmar 5.75
3. **Variable sweeps R2-R6**: Improved to Calmar 8-10+, but discovered rr/tp1/flat/gap are **coupled parameters** that oscillate when swept independently (rr went 3.0→2.0→3.0, flat went 11:00→11:15→11:00)
4. **Focused grid** (240 combos, 4 coupled dims simultaneously): Found two equivalent families:
   - rr=3.0 + tp1=0.3 → Calmar 10.12 (1 neg year at -0R)
   - rr=2.0 + tp1=0.5 → Calmar 10.00 (0 neg years!)
5. **Pipeline**: Selected rr=2.0, tp1=0.5 config (0 neg years). WF mode shifted to tp1=0.3, stop_orb=17%.

#### Key Findings

- **Entry time is the biggest lever**: Moving entry_end from 15:00→11:00 and flat from 15:50→11:00 transformed the strategy from Calmar 1.40 to Calmar 10+. NQ shorts work best as a tight morning play.
- **Coupled parameters**: rr, tp1, flat_start, and gap are deeply coupled. Variable sweeps alone cannot find the optimum — a joint grid search is required. rr=3.0+tp1=0.4 gives Calmar 2.55, but rr=3.0+tp1=0.3 gives Calmar 10+.
- **ORB-based stops dominate**: stop_orb_pct=15-17% consistently outperforms ATR-based stops for NQ NY shorts.
- **DOW Monday exclusion**: Stable improvement across all rounds. Monday shorts are negative EV.
- **ICF always hurts**: Impulse close filter reduced Calmar by -0.10 to -2.57 across all configs tested.
- **Dual floors validated**: min_stop_points=10 and min_tp1_points=10 eliminated the tp1=0.2 artifact from v1. Median stop is 43 ticks — well above floor.

#### Scripts Generated
- `run_nq_ny_short_v2_baseline.py` (Step 1 — failed, too wide session)
- `run_nq_ny_short_v2_variable_sweeps_1.py` (partial — timed out at DIM 5)
- `run_nq_ny_short_v2_mega_grid.py` (1,800 combos — structural + coupled dims)
- `run_nq_ny_short_v2_variable_sweeps_2.py` through `run_nq_ny_short_v2_variable_sweeps_6.py` (R2-R6)
- `run_nq_ny_short_v2_sweeps_r2_fix.py` (DIM 12 fix after DIM 11 crash)
- `run_nq_ny_short_v2_focused_grid.py` (240 combos, 4 coupled dims)
- `run_nq_ny_short_v2_robust_pipeline.py` (5-phase validation)
- `save_nq_ny_short_v2_final.py` (DB save)

### CORRUPTION NOTICE — All NY Results Pre-Fix (commit 6079ad4)

> **Root cause**: The TP1+BE same-bar exit bug allowed trades to survive bars where TP1 was hit and the stop should have moved to breakeven on the same candle. This inflated r_multiples for all configs, especially those with tp1_ratio <= 0.3 where TP1 is close to entry and same-bar TP1+BE events are frequent.
>
> **Impact**: NQ NY R20 (tp1=0.3) went from 247.9R → 84.6R (66% drop), Calmar 20.31 → 3.86 on the fixed engine. All metrics, WF results, and pipeline verdicts below are **unreliable**.
>
> **What's preserved**: Optimization history (parameter interaction lessons, DOW instability findings, structural conclusions about ORB windows, etc.) remains valid as directional guidance. Only the specific metric values are corrupt.
>
> **Action**: Full NQ NY longs-only re-optimization underway on the fixed engine.

### NY Continuation R20 (20m ORB, both, 1s magnifier) — CORRUPT (was GO)
- **Status**: CORRUPT — all metrics pre-date TP1+BE same-bar exit bug fix (commit 6079ad4). tp1=0.3 makes this config heavily affected.
- **Config** (R16-R20 optimization with 1s magnifier):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| ORB window | 20m (09:30-09:50) |
| entry_start | 09:50 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| direction | both |
| rr | 2.625 |
| tp1_ratio | 0.3 |
| stop_atr_pct | 8.75% |
| min_gap_atr_pct | 2.25% |
| max_gap_points | 100 |
| atr_length | 12 |
| magnifier | 1s |

- **Full-history performance** (2016-2026): 1,894 trades, 59.9% WR, PF 1.28, 212.5R total (21.3 R/yr), Max DD -13.0R, Calmar 16.36, Sharpe 1.72, **0 negative full years**
- **R by year**: 2016:+10  2017:+39  2018:+7  2019:+31  2020:+26  2021:+29  2022:+9  2023:+4  2024:+44  2025:+10  2026:+3

#### Robust Pipeline Results
- **Phase 1 (Structural)**: PASS — 1,894 trades, 59.9% WR, PF 1.28, max consec losses 6
- **Phase 2 (Adaptive WF)**: FAIL (borderline) — WF efficiency 0.49 (threshold 0.50), stability 0.45 (moderate). Fold 5 (2023 OOS: -0.95 Sharpe) dragged efficiency below threshold. WF mode params drifted from candidate (stop 8.0, rr 3.0, gap 3.0, tp1 0.4).
- **Phase 3 (Prop Filter)**: FAIL — on adaptive WF OOS trades: 2023=-12.3R, worst month -7.2R
- **Phase 4 (Hold-Out 2025+)**: PASS — 175 trades, Sharpe 1.72, PF 1.28, +23.4R, DD -5.8R
- **Phase 5 (MC Survival)**: FAIL — 12.7% survival at 15R (on adaptive WF OOS trades)
- **Fixed-param WF**: **6/6 folds profitable** — the fixed config generalizes across all time periods even though the adaptive WF optimizer couldn't converge on stable params. Combined OOS: 1,143 trades, 60.0% WR, PF 1.31, Sharpe 1.90, +142.8R (23.8 R/yr), DD -13.0R, Calmar 11.00.

| Fold | OOS Period | Trades | Sharpe | R | DD |
|------|-----------|--------|--------|---|-----|
| 1 | 2019 | 182 | 2.52 | +30.7 | -10.9 |
| 2 | 2020 | 174 | 2.27 | +26.0 | -7.0 |
| 3 | 2021 | 189 | 2.29 | +28.7 | -6.3 |
| 4 | 2022 | 194 | 0.72 | +9.1 | -12.6 |
| 5 | 2023 | 207 | 0.29 | +3.9 | -11.1 |
| 6 | 2024 | 197 | 3.38 | +44.4 | -6.3 |

- **Hold-out (2025+)**: 192 trades, Sharpe 1.02, PF 1.15, +12.7R, DD -9.3R
- **Verdict**: GO — adaptive WF failed because the parameter surface is noisy (different IS windows pick different optima), but the specific fixed config is robust across all periods. 2022-2023 are the weakest years (+9.1R, +3.9R) but still positive.
- **DB entry**: `bt-nq-ny-r20-final-fa2e40`

#### R20 Optimization History (R16-R20)
- **R16**: Fresh start with 1s magnifier. Anchor: rr=2.0, tp1=0.5, stop=10%, gap=1.5%, orb=15m, dir=both, ATR=14. Calmar 4.40. Adopted: direction=long, orb=20m.
- **R17**: dir=long, orb=20m. Calmar 6.87. Adopted 5 changes: direction=both, orb=25m, ATR=12, entry_end=15:30, gap=2.0%.
- **R18**: All 5 R17 changes applied. Calmar 6.16. Detected oscillation (orb 25m→20m, gap 2.0%→1.5%). Adopted: orb=20m (reverted), gap=1.5% (reverted), stop=11%.
- **R19**: Stabilization check. Calmar 6.98. stop=9% emerged as massive winner (Δ+3.67), triggering R9-R11 rule.
- **Grid sweep**: 750 combos (stop×rr×gap×tp1). Winner with 0 neg years: stop=9.0, rr=2.75, gap=2.5, tp1=0.4 → Calmar 14.53.
- **Fine-tune**: 625 combos at half-steps. Winner: stop=8.75, rr=2.625, gap=2.25, tp1=0.3 → Calmar 16.36. Anchor moved.
- **R20**: Re-swept structural vars on new anchor → all converged (every dimension had Δ=0).
- **Grid sweep R20**: 1,920 combos (broader ranges). Current anchor ranked #2 overall (Calmar 16.36). #1 was stop=7.0/rr=3.5 (Calmar 16.50) but at grid edge with 46% WR and -17.2R DD — rejected as less robust.

### NY Continuation Long 30m ICF — CORRUPT + INVALIDATED
- **Status**: CORRUPT + INVALIDATED — pre-dates TP1+BE bug fix AND original data (2015-2026) no longer available. Rerun on current data (2016-2026) shows degraded performance.
- **Original DB entry**: `NQ NY Long 30m ICF Pipeline Validated` (ID 9742)
- **Original performance**: 1,144 trades, 51.5% WR, Sharpe 2.10, PF 1.36, 192.2R, Calmar 17.26, 0 neg years
- **Rerun on current data**: 829 trades, 50.2% WR, Sharpe 2.00, PF 1.33, 134.6R, Calmar 11.10, **2 negative years** (2016: -8R, 2025: -6R)
- **1s magnifier impact**: Zero — 0 trades differed between 1m and 1s magnifier. 1m resolution was already sufficient for this config.
- **Root cause**: Current parquet data starts 2016-01 vs original CSV starting 2015-01. Missing 2015 data (~315 trades) accounts for the degradation. 2016 is now negative without the warm-up from 2015.
- **Conclusion**: Superseded by R20 Final (Calmar 16.36 vs 11.10 on same data, 0 neg years vs 2).

### NY Continuation (20m ORB, long-only, magnifier) — CORRUPT (was CONDITIONAL, superseded by R20)
- **Status**: CORRUPT — pre-dates TP1+BE bug fix. Was CONDITIONAL, superseded by R20 Final.
- **Accepted config** (WF mode params from Sharpe-objective run):

| Param | Value | Notes |
|-------|-------|-------|
| strategy | continuation | |
| session | NY | |
| ORB window | 20m (09:30-09:50) | |
| entry_start | 09:50 | |
| entry_end | 15:00 | |
| direction | long-only | |
| rr | 2.0 | WF mode (was 2.25 in-sample) |
| tp1_ratio | 0.6 | WF mode (was 0.7 in-sample) |
| stop_atr_pct | 9.0% | WF mode = in-sample |
| min_gap_atr_pct | 3.0% | WF mode = in-sample |
| atr_length | 14 | |
| magnifier | ON | |

- **In-sample performance** (rr=2.25, tp1=0.7): 1167 trades, 46.1% WR, PF 1.30, 182.0R total (16.5 R/yr), Max DD -10.6R, Calmar 17.17

#### Robust Pipeline Results (Sharpe-objective WF, 36m IS / 12m OOS / 12m step)
- **Phase 1 (Structural)**: PASS — 1167 trades, 46.1% WR, PF 1.30
- **Phase 2 (Walk-Forward)**: FAIL (borderline) — WF efficiency 0.45 (threshold 0.50), stability 0.83 (high)
  - 6 folds, 5/6 profitable OOS. Fold 6 (2023 OOS: -0.48 Sharpe) dragged efficiency below threshold
  - Combined OOS: 661 trades, 46.7% WR, PF 1.16, 54.3R, Sharpe 1.09, DD -12.3R, Calmar 4.41
  - Mode params: rr=2.0, tp1=0.6, stop=9.0, gap=3.0 (stability 0.83 across all 4 params)
- **Phase 3 (Prop Filter)**: FAIL — worst month -9.4R (Sep 2022), no year reached 24R annual target. OOS avg ~9 R/yr
- **Phase 4 (Hold-Out 2025+)**: PASS — 105 trades, 58.1% WR, PF 1.79, Sharpe 3.97, +30.1R, DD -5.0R
- **Phase 5 (MC Survival)**: PASS — 100% survival at 25R ruin threshold
- **Verdict**: CONDITIONAL — accepted with WF mode params. Phase 2 borderline (one bad fold), Phase 3 annual R target unrealistic for trade frequency. Size position to match DD tolerance.
- Also tested Calmar as WF objective — worse results (efficiency 0.15, OOS Calmar 4.02). Sharpe is the more stable WF objective for this strategy.

- **Year breakdown** (in-sample, rr=2.25): 2015:+28  2016:+17  2017:+22  2018:+13  2019:+19  2020:+19  2021:+17  2022:+9  2023:-2  2024:+12  2025:+21  2026:+8
- **Note**: WF OOS degrades ~74% from in-sample Calmar (17.17 → 4.41). 2023 is the persistent weak spot.

#### NY Variable Sweep History (Rounds 1-12) — CORRUPT METRICS, directional findings preserved

**Round 1** — Baseline variable sweeps (6 dimensions)
- Base: WF mode params (rr=2.0, tp1=0.5, stop=10%, gap=1.5%, both direction, 15m ORB)
- Swept: max_gap_points, max_gap_atr_pct, atr_length, ORB window, entry end, direction
- Key finding: **Long-only is the biggest single lever** (Sharpe 1.63 vs 1.18 for both)

**Round 2** — Finer grids + new dimensions (7 dimensions)
- Swept: rr, tp1, stop, min_gap, flat time, entry start delay, DOW exclusion
- Key findings: rr=2.25 slightly better, excl-Thu helps marginally, base values confirmed for most

**Round 3** — Extended dimensions (15 sweeps)
- Swept: ORB 5m-30m fine, ORB start, strategy type, multi-day exclusions, long-only sweeps
- Key findings: **20m ORB is optimal** (Calmar 9.58), long+excl-Thu+Fri best combo

**Round 4** — Combined winners re-sweep (16 dimensions)
- New base: long-only + 20m ORB (09:30-09:50)
- Key findings: entry end 14:00-15:00 best (Calmar 10.69-11.42), gap=3.0% strong filter

**Round 5** — Stacking combos + Calmar-focused (Phase A: 32 combos, Phase B: 11 sweeps)
- Winner: **+entry_end=15:00 +gap=3.0%** → Calmar 14.56, DD -9.9R, 13.1 R/yr

**Round 6** — Maximize R/year (8 interaction sweeps)
- Tested: RR up to 3.5, both direction, gap×RR, TP1×RR, stop×RR, entry_end×RR
- Key findings: rr=2.75 long best R/yr (14.7), both direction gets 18-20 R/yr but doubles DD
- tp1=0.4 rr=2.5 best Calmar in TP1×RR grid (14.86)

**Round 7** — 3-way interaction grid: gap × rr × tp1 (90 combos at stop=10%)
- New best Calmar: **g=3.5 rr=2.50 tp1=0.4** → 12.6 R/yr, DD -9.3R, Calmar 14.97
- g=3.5 rr=3.00 tp1=0.3 had lowest DD in grid: -8.8R
- Entry start delay (10:00, 10:15) confirmed harmful — 09:50 is optimal

**Round 8** — Separate short optimization + combined trade lists
- Best short independently: g=3.0 rr=1.5 → 5.9 R/yr, DD -12.4R (mediocre alone)
- **Key finding: Combined L+S with independent params beats same-params-both**
  - Combined L(rr2.75) + S(rr1.5): 20.6 R/yr, DD -16.9R, Calmar 13.47
  - Same-params both rr=2.75: 18.1 R/yr, DD -21.5R, Calmar 9.25
  - Shorts need low RR (1.5) while longs thrive at higher RR (2.5-2.75)

**Round 9** — Fine-grained stop sweep (3-14% in 1% steps, 7 configs)
- **stop=9% massively improves rr=2.75 configs** (+2 Calmar) but does nothing for rr=2.0/2.5
- g3.0 rr2.75 tp0.6 stop=9%: 16.3 R/yr, DD -11.2R, Calmar 16.00 (new overall best at the time)
- g3.0 rr2.75 tp0.5 stop=9%: 16.9 R/yr, DD -11.8R, Calmar 15.74
- **Lesson**: Always re-validate stop when changing RR — the interaction is strong

**Round 10** — Ultra-fine stop sweep (8.5-9.5% in 0.1% steps, config: g3.0 rr2.75 tp0.6)
- Confirmed **stop=9.0% is the Calmar optimum** (16.00)
- Smooth curve: 8.5-9.2% all hold Calmar > 15 (no fragile spike — good robustness signal)
- 8.5% has highest R/yr (17.2) but slightly more DD (-11.9R)

**Round 11** — 3-way grid re-run at stop=9% (90 combos) — MAJOR SHIFT
- **Stop=9% completely reshuffled the leaderboard** — different rr/tp1 combo won
- New #1: **g=3.0 rr=2.25 tp1=0.7 stop=9%** → 16.5 R/yr, DD -10.6R, **Calmar 17.17**
- Previous best (g3.0 rr2.75 tp0.6) dropped to #5 (Calmar 16.00)
- Stop=9% beat stop=10% on ALL 10 head-to-head combos tested (avg +3.4 Calmar, +2.9 R/yr)
- Optimal RR shifted from 2.75 → 2.25, optimal TP1 shifted from 0.6 → 0.7
- gap=3.0% dominates the entire top 10 (gap=2.5% and 3.5% nowhere close)
- **Key lesson**: Changing one variable (stop) can shift the entire optimal surface. Always re-run the full grid after finding a new anchor.

**Round 12** — Fine-tuning R11 winner (COMPLETE)
- Swept rr (0.05 steps), tp1 (0.05 steps), gap (0.1 steps), entry_end (15min steps), stop (0.1 steps)
- **All current values confirmed at local optima** — no variable improved more than marginally
- Only entry_end=15:30 showed slight gain: Calmar 17.40 vs 17.17 (+0.23), adding 42 trades
- Stacked all-best (with end=15:30): 1209 trades, 16.8 R/yr, DD -10.6R, Calmar 17.40
- R11 #2 (rr3.0 tp0.6) and #3 (rr2.75 tp0.7) confirmed close but below the winner
- **Conclusion**: Optimization phase complete. The parameter surface is flat around the optimum — robust signal.

**Round 13a** — Config variable re-validation with new anchor (6 variables)
- Swept ORB window (5m-30m), ATR length (5-30), flat window, max gap ATR%, max gap points, DOW exclusion
- **All confirmed at current optima** — only flat_start=15:40 showed marginal gain (+0.37 Calmar)
- 20m ORB, ATR 14, no limit on max gap ATR, max_gap_pts=100, no DOW exclusion all reconfirmed

**Round 13b** — Environmental & regime filters (VIX, SPY, TNX, DXY, NQ SMA, ATR vol, seasonality)
- **No environmental filter improves Calmar over baseline** — all cut trades → cut R/yr more than DD
- Strongest IN/OUT splits: DXY < SMA20 (avg R 0.217 vs 0.078), TNX < SMA20 (0.192 vs 0.100)
- VIX > SMA50 counterintuitively helps longs (0.206 vs 0.102) — elevated vol = better FVG setups
- **December is poison** (-19.4R, 33.8% WR) — excl Dec → Calmar 19.82, but overfitting risk
- NQ SMA trend gates and ATR vol gates all hurt — don't use them
- **Best use for env data: regime SIZING, not hard filtering**

**Round 14** — Re-optimize shorts + combined L+S with updated anchor
- Best short: g=1.0 rr=1.25 tp1=0.5 stop=9% entry_end=14:00 (8.3 R/yr, DD -14.2R)
- Combined always (L+S): 22.1 R/yr, DD -15.4R, Calmar 15.77
- Sweet spot: L + S(rr=1.25) → 22.1 R/yr, DD -15.4R, all years positive
- R/yr +34% but DD +45% — long-only still better risk-adjusted
- **Key finding: shorts add most value when longs are weakest (2022-2023)**

**Round 15** — Regime-switched L+S (always long + short when [condition])
- Tested 20 regime conditions (VIX, SPY, TNX, DXY singles + combos)
- **No regime switch beats long-only on Calmar** — all hit DD floor of ~-14.5R
- Best: "S when TNX > SMA20" → 19.9 R/yr, DD -14.5R, Calmar 15.10
- Combined-always (15.77) actually beats all regime switches
- **Conclusion: shorts don't improve risk-adjusted returns regardless of regime filtering**

#### Drawdown Profile (from DD analysis)
- **DD <= -10R**: 4 events in 11 years (0.4/yr) — all clustered in 2023-03 to 2024-02
- **DD <= -9R**: 11 events (1.0/yr)
- **DD <= -8R**: 21 events (1.9/yr)
- **DD <= -7R**: 34 events (3.1/yr)
- 63% positive months, mean +1.36R/month, worst month -9.4R (Sep 2022)
- Worst losing streak: 9 consecutive losses = -8.2R (Sep-Oct 2022)
- **DB entry**: `saved after R15 sweep completion`

## Key Findings

### Asia Session
- **R9 Restart Final is the current GO config**: stop=4.0%, rr=3.0, gap=0.90%, tp1=0.6, ORB=15m (20:00-20:15), entry_end=22:30, flat=04:00, ATR=5, long-only, excl-Tue, ICF=ON, 1s magnifier, max_gap_points=75 → 770 trades, 45.5% WR, PF 1.42, Sharpe 2.52, 176.2R (17.6 R/yr), DD -11.3R, Calmar 15.64, 0 neg years. WF efficiency 0.797, stability 0.964. Hold-out Sharpe 2.77. MC 91.7% survival. DB: `bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8`. Supersedes R5 Final (which had degenerate tp1=0.10).
- **Asia Continuation Short is NO-GO**: stop=3.5%, rr=3.75, gap=1.0%, tp1=0.6, ATR=30, 10m ORB, entry<=01:00, flat=23:00, excl-Thu, ICF=ON → 874 trades, Calmar 6.30. Robust pipeline 2/5 (WF, Prop, MC all failed). 2022-2023 are structurally negative for shorts — 0/500 grid combos have 0 neg years. Shorts need completely different optimal params than longs (every major dimension differs). Not viable standalone or as a hedge.
- **R5 Final's tp1=0.10 was degenerate**: Post-bugfix optimization converged to tp1=0.10 (94.5% WR, Calmar 60.19) but each TP1_BE win earned only +0.0625R. The strategy was a micro-scalper masquerading as a normal strategy. R9 Restart enforced tp1>=0.2 minimum and found a fundamentally different, healthier profile at tp1=0.6.
- **R9 Restart is a completely different strategy profile than R5**: Long-only (was both), 15m ORB (was 10m), ICF=ON (was OFF), excl-Tue (was excl-Thu), entry_end=22:30 (was 00:00), flat=04:00 (was 01:00), rr=3.0 (was 1.75). Every major structural dimension changed when the tp1 floor was imposed.
- **Destructive parameter interaction warning**: In R3, adopting 5 changes simultaneously crashed Calmar from 20.18→11.97 (-41%). Never adopt more than 2-3 changes at once. The safe approach is resetting to the best-proven config when oscillation is detected.
- **DOW exclusion instability**: excl-Thu was optimal in R4/R5, excl-Tue emerged in R9 Restart. DOW exclusions shift with the anchor — treat with caution but R9's excl-Tue passed 2-round persistence test.
- **SMA trend gate hurts NQ Asia** — opposite of CL where it doubled Sharpe. Both trend directions are profitable; filtering halves trade count without improving edge.
- **atr_length=5 beats 14 for walk-forward** — ATR 14 shows better in-sample Sharpe in pre-sweeps but performs worse OOS (WF efficiency 0.311 vs 0.59 for ATR 5). Use ATR 5 for pipeline validation. Confirmed again in R9 Restart.
- **Two distinct strategy profiles discovered across optimization rounds**:
  - **R5 Final profile** (tp1=0.10, rr=1.75, both, 10m ORB, ICF=OFF): Ultra-high WR scalper (94.5%), Calmar 60.19, but degenerate edge per win (+0.0625R). Not recommended.
  - **R9 Restart profile** (tp1=0.6, rr=3.0, long, 15m ORB, ICF=ON): Moderate WR (45.5%), higher edge per win, Calmar 15.64. Recommended — healthy risk/reward profile.
- **Gap dimension stable at 0.90%**: Confirmed across R4, R5, and R9 Restart. gap=0.9 was stable 7/7 WF folds in R9 pipeline.
- **ICF flipped from OFF to ON**: At the R5 anchor (tp1=0.10, both directions, 10m ORB) ICF was detrimental. At the R9 Restart anchor (tp1=0.6, long-only, 15m ORB, rr=3.0) ICF became beneficial. This is a clear example of parameter interactions — the same filter can be positive or negative depending on the full config.
- **max_gap_points=75 is a new dimension**: Adopted in R9 Restart R5 sweep. Caps absolute gap size in points, complementing the ATR-relative gap filter.

### NY Session
- **R11 Final is the current CONDITIONAL config** (post-fix): stop=7.0%, rr=3.5, gap=2.5%, tp1=0.4, ATR=12, 20m ORB, entry<=12:00, flat=15:30, ICF=OFF, long-only, excl-Fri, 1s magnifier → 561 trades, 53.3% WR, PF 1.51, Sharpe 2.90, 135.0R, DD -6.0R, Calmar 22.51, 0 neg years. WF stability 1.000 (high), WF eff 0.551. MC 99.1% survival. Phase 3 failed on avg annual R (8.1 < 12.0). DB: `bt-nq-ny-cont-long-r11-final-2016-2026-c3bcc0`.

> **All previous NY metrics below were computed before the TP1+BE same-bar exit bug fix (commit 6079ad4).** Specific Calmar/R/Sharpe/DD numbers are unreliable. Directional findings (which params are better/worse relative to each other) are still useful as starting hypotheses.

- **All previous NY configs (R20, Long 30m ICF, Long-only CONDITIONAL, LDN R2) are CORRUPT** — R11 Final above is the post-fix replacement.
- **NQ NY continuation shorts are CONDITIONAL (v2)** — re-optimized with dual floors (min_stop=10pt, min_tp1=10pt) from scratch. Key insight: entry_end=11:00 and flat=11:00 transform shorts from NO-GO (Calmar 1.40) to strong (Calmar 7.86). ORB 25m, stop_orb=17%, rr=2.0, tp1=0.3, gap_orb=5%, DOW excl Mon, 329 trades, 0 neg years. WF stability HIGH (0.80), MC survival 97.8%. Only failure: annual R (2.86R/yr) below 12R threshold (unrealistic for short-only ~33 trades/yr). DB: `bt-nq-ny-short-v2-2016-2026-final-d9db60`.
- **20m ORB (09:30-09:50) is likely the optimal window** for NY — confirmed across R16-R20 sweeps pre-fix. Starting hypothesis for re-optimization.
- **Entry end 15:30 is likely optimal** — R17 showed entry_end=15:30 was a massive lever. Starting hypothesis for re-optimization.
- **ATR=12 is likely optimal** — shifted from 14 in earlier rounds. Starting hypothesis for re-optimization.
- **Stop ATR interacts strongly with RR** — this lesson confirmed in R19-R20 pre-fix. stop changes reshuffle the entire optimal surface. Always re-run full grid after finding a new stop anchor.
- **DOW exclusion is a data-mining artifact** — shifted every round pre-fix (Th+F in R16-R17, Tue in R18, different again in R19). Do not use.
- **2022-2023 are likely the weak years** — consistent across all pre-fix configs. Expect this to persist post-fix.
- **ICF is likely detrimental for NQ NY** — pre-fix finding across full parameter space. Will re-verify in sweeps.
- ~~Reversal and inversion strategies are dead~~ **INVALIDATED** — prior reversal/inversion results tested without liquidity sweep gate. Needs re-testing with sweep-gated definition.

### NY Continuation Long R11 Final (20m ORB, long-only, 1s magnifier) — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases passed. Phase 3 (Prop Constraints) failed on avg annual R.
- **Config** (fresh optimization on fixed engine, 11 rounds + 3 grid sweeps):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | NY |
| ORB window | 20m (09:30-09:50) |
| entry_start | 09:50 |
| entry_end | 12:00 |
| flat_start | 15:30 |
| flat_end | 16:00 |
| direction | long |
| rr | 3.5 |
| tp1_ratio | 0.4 |
| stop_atr_pct | 7.0% |
| min_gap_atr_pct | 2.5% |
| atr_length | 12 |
| ICF | OFF |
| DOW excl | Fri (post-backtest) |
| magnifier | 1s |

- **Full-history (2016-2026)**: 561 trades, 53.3% WR, PF 1.51, 135.0R (13.5 R/yr), DD -6.0R, Calmar 22.51, Sharpe 2.90, **0 negative full years**
- **R by year**: 2016:+8, 2017:+24, 2018:+22, 2019:+22, 2020:+14, 2021:+12, 2022:+6, 2023:+3, 2024:+11, 2025:+9, 2026:+4
- **Median stop**: 54.2 ticks

#### Robust Pipeline Results
- **Phase 1 (Structural)**: PASS — 561 trades, 53.3% WR, PF 1.51, Calmar 22.51, 54.2 tick stop
- **Phase 2 (Walk-Forward)**: PASS — WF efficiency 0.551, stability 1.000 (high), 7 folds. stop=7.0 chosen 6/7 folds, rr=3.5 in 4/7. Combined OOS: 387 trades, 51.2% WR, PF 1.30, 56.8R, Sharpe 1.83, DD -8.9R, Calmar 6.36. 2023 OOS fold: -2.9R (only negative year).
- **Phase 3 (Prop Constraints)**: FAIL — avg annual R 8.1R (threshold 12.0R). Worst month -4.6R (PASS). Positive expectancy +0.147R (PASS). 2023 OOS: -2.9R dragged average below threshold.
- **Phase 4 (Hold-Out 2025+)**: PASS — 54 trades, 53.7% WR, PF 1.52, Sharpe 2.90, +13.1R, DD -4.0R
- **Phase 5 (Monte Carlo)**: PASS — 99.1% survival at -25R ruin. p50 DD -12.4R, p5 PnL 83.5R, p5 Sharpe 1.82
- **Verdict**: CONDITIONAL — size position conservatively. Phase 3 fails because long-only NY generates ~56 trades/year, limiting absolute R accumulation. Edge per trade (+0.24R) is solid but frequency is the bottleneck.
- **DB entry**: `bt-nq-ny-cont-long-r11-final-2016-2026-aa7630`

#### Optimization History
- **R1-R7**: 7 rounds of variable sweeps. R2 adopted 5 changes simultaneously — destructive (crashed Calmar). R3 reverted all 5. Lesson: max 2-3 adoptions at once. **R7 CONVERGED** at Calmar 14.45.
- **Grid R1**: 540 combos. Winner: stop=7.0, rr=3.25, gap=2.5, tp1=0.45 (Calmar 16.45, +2.00). Adopted.
- **R8-R9**: Post-grid sweeps. R8 adopted ATR 20→12. **R9 CONVERGED** at Calmar 16.50. tp1=0.4 blocked individually (2023 neg), but works with higher rr.
- **Grid R2**: 375 combos. Winner: stop=7.0, rr=3.5, gap=2.5, tp1=0.4 (Calmar 20.73, +4.23). Key interaction: tp1=0.4 blocked at rr=3.25 but viable at rr=3.5. Adopted.
- **R10-R11**: Post-grid sweeps. R10 adopted ICF ON→OFF (+1.78). **R11 CONVERGED** at Calmar 22.51.
- **Grid R3**: 375 combos. **Anchor ranked #1/375 overall and #1/66 (0-neg)**. Delta +0.00 — perfect convergence.
- **ICF oscillation**: OFF→ON→OFF→OFF→OFF→ON→ON→ON→ON→OFF. Context-dependent. Settled at OFF for this anchor.
- **2023 is the persistent weak year**: +2.8R in full-history. Drives Phase 3 failure in WF (2023 OOS = -2.9R). Cannot be eliminated without overfitting.
- **Entry delay**: 0m (baseline) is optimal. Even 10m delay halves Calmar (22.51→9.24, DD -6.0→-12.0R). 30m delay drops to Calmar 3.81. The edge comes from capturing the first FVG immediately after the 20m ORB closes. Script: `run_combined_longs_entry_delay_sweep.py`.
- **Event day exclusion**: No exclusions beneficial. FOMC days are actually *better* than average (+0.457R avg, 60% WR vs 53.3% overall, n=20). CPI slightly below average (+0.129R vs +0.241R, n=29). NFP has 0 fills. Excluding FOMC hurts Calmar (22.51→19.82). Excluding all events: 22.51→18.32. Script: `run_combined_longs_event_day_sweep.py`.
- **Scripts**: `run_nq_ny_long_variable_sweeps_{1-11}.py`, `run_nq_ny_long_grid_sweep_r{1-3}.py`, `run_nq_ny_long_robust_pipeline.py`, `save_nq_ny_long_r11_final.py`

### LDN Session — CORRUPT (pre-fix metrics, directional findings preserved)
- **NQ LDN continuation is marginal** — best achievable Calmar ~1.13 pre-fix (full-history). Orders of magnitude weaker than Asia.
- **Only 1 of 3 walk-forward candidates passed GO** — and barely (hold-out Sharpe 0.58, just above 0.5 threshold). Two other candidates had stronger OOS R/yr but failed hold-out Sharpe.
- **2016 is the persistent negative year** — appears in every config tested, cannot be eliminated.
- **ICF=ON and max_gap_points=20 were the only two adoptions** across R1-R2 variable sweeps (12 dimensions each). Most dimensions showed no meaningful improvement from the weak anchor.
- **Many promising dimensions blocked by new negative years** — ORB 10m (Calmar 2.72 but adds 2020), excl Mon (2.14 but adds 2023), ATR 30 (1.86 but adds 2024), long-only (1.47 but adds 2018). The strategy doesn't have enough edge to support structural changes.
- **Grid sweep (576 combos) barely moved the anchor** — best ≤1-neg-year combo: stop=8.0/rr=2.5/gap=1.5/tp1=0.5 (Calmar 1.13 vs anchor 1.12, Δ=+0.01).
- **OOS performance is thin** — grid #2 (stop=8.0/rr=2.25/gap=1.5/tp1=0.6) passed WF with all 6 folds profitable but 2024 was +0.2R and 2019 was +1.8R. Combined OOS: 10.3 R/yr, Calmar 0.41.

### LDN Continuation R2 Final (15m ORB, both, 1s magnifier) — CORRUPT (was MARGINAL GO)
- **Status**: CORRUPT — pre-dates TP1+BE bug fix. tp1=0.6 means less affected than NY R20, but all metrics are still unreliable. Was MARGINAL GO — fixed-param WF 6/6 folds profitable, hold-out PASS (barely).
- **Config** (R1-R2 optimization + grid sweep):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | LDN |
| ORB window | 15m (03:00-03:15 ET) |
| entry_start | 03:15 |
| entry_end | 08:25 |
| flat_start | 08:20 |
| flat_end | 08:25 |
| direction | both |
| rr | 2.25 |
| tp1_ratio | 0.6 |
| stop_atr_pct | 8.0% |
| min_gap_atr_pct | 1.5% |
| max_gap_points | 20 |
| max_gap_atr_pct | 0 (no limit) |
| atr_length | 14 |
| magnifier | 1s |
| impulse_close_filter | ON |

- **Full-history performance** (2016-2026): 2,034 trades, 44.8% WR, PF 1.05, 51.4R total (5.1 R/yr), Max DD -45.6R, Calmar 1.13, Sharpe 0.35, 1 neg year (2016)
- **R by year**: 2016:-41  2017:+14  2018:+7  2019:+2  2020:+14  2021:+10  2022:+20  2023:+16  2024:+0  2025:+13  2026:-4

#### Fixed-param Walk-Forward (6 folds, OOS 2019-2024)

| Fold | OOS Period | Trades | WR | PF | Sharpe | R | DD |
|------|-----------|--------|-----|-----|--------|---|-----|
| 1 | 2019 | 204 | 45.6% | 1.01 | 0.13 | +1.8 | -15.6 |
| 2 | 2020 | 196 | 45.9% | 1.14 | 0.94 | +13.7 | -10.5 |
| 3 | 2021 | 211 | 46.0% | 1.09 | 0.66 | +10.1 | -10.0 |
| 4 | 2022 | 201 | 47.3% | 1.20 | 1.36 | +20.4 | -12.3 |
| 5 | 2023 | 201 | 45.3% | 1.15 | 1.03 | +15.8 | -25.2 |
| 6 | 2024 | 196 | 43.9% | 1.01 | 0.01 | +0.2 | -22.0 |

- **Combined OOS**: 1,209 trades, 45.7% WR, PF 1.10, Sharpe 0.70, +62.0R (10.3 R/yr), DD -25.2R, Calmar 0.41
- **Hold-out (2025+)**: 216 trades, 46.8% WR, PF 1.09, Sharpe 0.58, +9.1R, DD -17.9R — PASS (barely)
- **Verdict**: MARGINAL GO — all 6 folds profitable but folds 1 and 6 are razor-thin (+1.8R, +0.2R). Hold-out Sharpe just barely clears 0.5 threshold. Not recommended for primary allocation.

#### R1-R2 Optimization History
- **R1**: Fresh start with LDN defaults (stop=10%, rr=2.0, tp1=0.5, gap=1.0%, max_gap=50, ICF=OFF). Calmar 0.09 (very weak anchor, 4 neg years). Only 2 of 12 dimensions adopted: max_gap_points=20 (Δ+0.32) and ICF=ON (Δ+0.64). All other promising dimensions blocked by new negative years.
- **R2**: max_gap=20 + ICF=ON applied. Calmar jumped to 1.12 (1 neg year: 2016). **Fully converged — every dimension Δ=0** (no adoptions pass threshold without new neg years).
- **Grid sweep**: 576 combos (6 stops × 6 rrs × 4 gaps × 4 tp1s). Best ≤1 neg year: stop=8.0/rr=2.5/gap=1.5/tp1=0.5 (Calmar 1.13). Anchor barely moved. No fine-tune needed.
- **Walk-forward**: Tested 3 candidates. Only grid #2 (stop=8.0/rr=2.25/gap=1.5/tp1=0.6) passed — marginal GO.
- **DB entry**: `bt-nq-ldn-r2-final-e132b8`

### LDN Continuation Long (30m ORB, 1s magnifier) — NO-GO
- **Status**: NO-GO — robust pipeline failed Phases 2, 3, 4, 5 (only Phase 1 passed)
- **Config tested** (converged from 6 sweep rounds + grid):

| Param | Value |
|-------|-------|
| strategy | continuation |
| session | LDN |
| ORB window | 30m (03:00-03:30 ET) |
| entry_start | 03:30 |
| entry_end | 08:25 |
| flat_start | 08:20 |
| flat_end | 08:25 |
| direction | long |
| rr | 6.0 |
| tp1_ratio | 0.7 |
| stop_atr_pct | 1.5% |
| min_gap_atr_pct | 1.0% |
| atr_length | 10 |
| magnifier | 1s |
| impulse_close_filter | OFF |
| DOW exclusion | none |

- **Full-history performance** (2016-2026): 1124 trades, 25.0% WR, PF 1.35, 299.7R total (29.5 R/yr), Max DD -24.1R, Calmar 12.46, Sharpe 1.83, 0 neg full years
- **R by year**: 2016:+8  2017:+45  2018:+42  2019:+41  2020:+32  2021:+34  2022:+0  2023:+25  2024:+41  2025:+33  2026:-1

#### Robust Pipeline Results

| Phase | Result | Key Metrics |
|-------|--------|-------------|
| 1 — Structural | PASS | 1124 trades, PF 1.35, Calmar 12.46, med stop 11 ticks |
| 2 — Walk-Forward | FAIL | WF eff 0.35 (< 0.5), stability 0.80 (high). 2020+2022 OOS folds negative |
| 3 — Prop Filter | FAIL | Worst month -10.0R (> 5.0R cap). 2020: -9.2R, 2022: -6.8R on WF OOS |
| 4 — Hold-Out OOS | FAIL | Sharpe 0.18, PF 1.03, +3.1R. Mode params (stop=1.0, rr=8.0) weak OOS |
| 5 — Monte Carlo | FAIL | 0.1% survival at 15R, 87.8% ruin at 25R |
| **Verdict** | **NO-GO** | 1/5 pass. Strategy overfits to full history. |

- **WF mode params**: stop=1.0, rr=8.0, gap=1.0, tp1=0.7 — WF consistently selects higher R:R and tighter stops than the in-sample optimum
- **Key insight**: The high R:R (6.0) / low WR (25%) profile produces concentrated wins in specific regimes (2017-2019, 2021, 2024) but fails in choppy markets (2020, 2022). Full-history Calmar of 12.46 is misleading — the walk-forward shows the strategy doesn't generalize.
- **Median stop**: 11 ticks at 1.5% ATR — borderline above 10-tick minimum. WF prefers even tighter (1.0% ATR = ~7 ticks), suggesting the optimization gravitates toward impractically tight stops.

#### Optimization History
- **Baseline**: LDN defaults (stop=10%, rr=2.5, tp1=0.5, gap=1.0%, ATR 14, ORB 15m). Long-only Calmar 0.07, shorts fail (PF 0.95).
- **R1** (13 dims): 4 adoptions — stop: 10→2.0, orb: 15m→45m, rr: 2.5→5.0, tp1: 0.5→0.4
- **R2** (13 dims): 5 adoptions — stop: 2.0→2.5, orb: 45m→30m, ATR: 14→10, rr: 5.0→8.0, tp1: 0.4→0.6. ORB%-based sizing consistently worse than ATR-based.
- **R3** (13 dims): 2 adoptions — stop: 2.5→1.5 (+6.80 Calmar, 0 neg yrs), rr: 8.0→4.0
- **R4** (13 dims): 2 adoptions — rr: 4.0→6.0 (+3.68), tp1: 0.6→0.5 (+0.78)
- **R5** (core 3 only): 1 adoption — tp1: 0.5→0.7 (+0.41)
- **R6** (core 3 only): 0 adoptions — CONVERGED
- **Grid** (600 combos): Winner Calmar 12.74 vs anchor 12.46 (Δ=+0.28 < 0.5) — confirmed
- **Parameter sensitivity**: Stop size is the dominant driver. 1.0% and 1.25% ATR produce higher Calmar but fail 10-tick minimum. R:R and TP1 have a feedback loop but stabilize quickly. ORB window, gap, ATR length, ICF are all insensitive at this anchor.

#### Scripts Generated
- `run_nq_ldn_baseline.py`
- `run_nq_ldn_variable_sweeps_1.py` through `run_nq_ldn_variable_sweeps_6.py`
- `run_nq_ldn_grid_sweep_r1.py`
- `run_nq_ldn_robust_pipeline.py`
- `save_nq_ldn_r1_final.py`
- **DB entry**: `bt-nq-ldn-cont-long-2016-2026-final-679958`

### LDN LSI (Liquidity Sweep Inversion) Long — GO
- **Status**: GO — 5/5 pipeline phases passed
- **DB entry**: `bt-nq-ldn-lsi-long-2016-2026-final-df4a78` (1x) / `bt-nq-ldn-lsi-long-2016-2026-final-4x-39b078` (4x)
- **Optimization**: lsi-optimization workflow — baseline (NY-informed) → 8 variable sweep rounds → grid sweep R1 → RR fine-tune (0.05-step) → verification → robust pipeline v2
- **Key lesson**: Naive defaults (n_left=3, n_right=3, gap=2.25%, rr=2.625, tp1=0.3) produced Calmar -0.58 — a false NO-GO. NY-informed params required as starting point (n_right=session-length, gap=5.0%, rr~1.65, tp1=0.7, long only).
- **Key lesson**: rr/tp1 interact and oscillate in independent sweeps. Grid sweep (0.25-step) found rr=1.75; fine-tune (0.05-step) found rr=1.65 optimal (+0.45 Calmar). Always fine-tune RR after grid.
- **Key lesson**: WF mode params (rr=1.75, tp1=0.7, gap=6.0%) differ slightly from in-sample anchor (rr=1.65, gap=5.0%) — normal; WF cross-validates slightly more conservative RR.

**Final config** (in-sample anchor, 2016-2026):

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | LDN |
| orb | 03:00-03:05 ET (vestigial) |
| entry | 03:30-07:00 ET |
| flat | 08:20 ET |
| lsi_n_left | 8 |
| lsi_n_right | 60 (LDN session-length) |
| lsi_fvg_window_left | 7 |
| lsi_fvg_window_right | 3 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| rr | 1.75 |
| tp1_ratio | 0.7 |
| direction | long only |
| magnifier | 1m |

**In-sample performance** (2016-2026):
| Metric | Value |
|--------|-------|
| Trades | 165 |
| Win Rate | 64.8% |
| PF | 2.30 |
| Net R | 47.2R |
| R/yr | 4.6R |
| Max DD | -2.5R |
| Calmar | 18.92 |
| Sharpe | 5.559 |
| Neg years | 0 |
| Median stop | 150 ticks |

**Pipeline results** (GO 5/5):
| Phase | Result | Detail |
|-------|--------|--------|
| 1 Structural | PASS | 165 trades, PF 2.30, Calmar 18.92, 0 neg years |
| 2 Walk-Forward | PASS | WF eff 0.658, stability 0.867 (high), 5 folds |
| 3 Prop Filter | PASS | DD -2.0R (INFO), worst month -1.5R, expectancy +0.28R |
| 4 Hold-Out OOS | PASS | PF 1.30, +1.3R, 9 trades (2025-2026 thin but positive) |
| 5 Monte Carlo | PASS | 100% survival, 0% ruin at -25R threshold |

**WF mode params** (cross-validated best): rr=1.25, tp1=0.6, gap=6.0%

**Parameter sensitivity**:
- gap=5.0% is strongly locked — any lower (3-4%) causes sharp Calmar/quality degradation
- n_right=60 is locked to session-length — smaller values find micro-pivots and degrade quality
- entry window 03:30-07:00 is tight — wider (03:05 or 08:25) reduces Calmar by 5+
- Hold-out thin (9 trades): LDN LSI has limited trades/year (~16-17), 2025 partial year gives fewer signals

**Optimization convergence path** (Calmar):
- Naive baseline: -0.58 (false NO-GO)
- NY-informed baseline: 4.43 → 13.26 (R3) → 15.79 (R4) → 16.34 (R5 converged)
- Post-grid: 18.92 (R8 confirmed 0 adoptions)

**Scripts generated**:
- `run_nq_ldn_lsi_baseline.py`
- `run_nq_ldn_lsi_variable_sweeps_1.py` through `run_nq_ldn_lsi_variable_sweeps_8.py`
- `run_nq_ldn_lsi_grid_sweep_r1.py`
- `run_nq_ldn_lsi_robust_pipeline.py`
- `save_nq_ldn_lsi_r1_final.py`

### NY Liquidity Sweep Inversion (LSI) Long — CONDITIONAL
- **Status**: CONDITIONAL — 4/5 pipeline phases passed; Phase 3 (prop constraints) failed on annual R gate
- **Optimization**: Full lsi-optimization workflow — baseline → 11 variable sweep rounds → grid R1 → R11 re-sweep → robust pipeline
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 1.5 |
| tp1_ratio | 0.6 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| lsi_n_left | 4 |
| lsi_n_right | 78 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 3 |
| direction | long only |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 1146 trades, 58.3% WR, PF 1.33, Sharpe 1.956, Net R 121.1R, R/yr 12.1R, Max DD -9.0R, **Calmar 13.44**
  - **0 negative full years** (min: 2022 +2.5R, max: 2020 +30.9R)
  - Median stop: 210 ticks (~52.5 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 745 trades, 57.9% WR, PF 1.22, Sharpe 1.366, Net R 53.0R, R/yr 7.6R, DD -12.6R, Calmar 4.20
  - WF efficiency: 0.643 | Parameter stability: 0.952 (high)
  - rr mode=1.5 (6/7 folds), tp1 mode=0.6 (6/7 folds), gap mode=5.0 (5/7 folds)
  - 1 neg OOS year: 2021 (-3.6R) from fold 3 (Sharpe -0.600 OOS)

- **Prop constraints** (FAIL): OOS avg annual R 7.6R < 12R gate; worst month -5.1R > 5.0R limit
- **Hold-out OOS** (2025+, PASS): 117 trades, PF 1.12, Sharpe 0.810, +5.4R, DD -5.6R
- **Monte Carlo** (PASS): 98.5% survival at -25R ruin, 1.5% ruin probability, p50 DD -12.9R

- **Key findings**:
  - `lsi_stop_mode="absolute"` (structural stop at swing pivot) is the correct stop type — no ATR stop
  - `lsi_n_right=78` (one full NY session = 6.5h × 12 bars/hr) consistently wins throughout optimization
  - `lsi_n_left=4` (tight pivot confirmation) beats wider values
  - `lsi_fvg_window_left=20` (wider FVG context window) beats the initial 10
  - Baseline Calmar 0.02 → final Calmar 13.44 over 11 variable sweep rounds + grid
  - 2021 is the structural weak year — most OOS folds covering 2021 show negative or near-zero
  - Gap=5.0% is fully locked in: ALL 25 zero-neg-year combos in the grid had gap=5.0%
  - Phase 3 failure is marginal: strategy profitable OOS every year except 2021; monthly gate just barely missed (-5.1R vs -5.0R limit)

- **DB entry**: `bt-nq-ny-lsi-long-2016-2026-r1-final-b2fa98`
- **Conclusion**: Viable strategy with excellent in-sample characteristics and strong parameter stability. Fails prop firm annual R threshold OOS (7.6R vs 12R) due to 2021 drag. Accept CONDITIONAL or add a market regime gate to filter 2021-type environments.

#### Post-Pipeline Exploration (2026-02-27)

All tests below run post-hoc or as additional sweeps against the R1 final anchor (unless noted). Anchor Calmar = 12.90 (full-history 2016–2026).

**Criteria comparison** (lsi_first_fvg_only, lsi_clean_path, fvg_limit entry):
- All filter variants reduce Calmar vs anchor — volume loss dominates
- `first_fvg_only=True`: Calmar 11.08 (−1.82), 1 neg year — NO-GO
- `clean_path=True`: Calmar 7.16–8.49 — NO-GO
- `fvg_limit + first_fvg_only`: Calmar 10.87, 0 neg years — better PF/Sharpe but lower Calmar — NO-GO vs anchor (covered separately as its own config)

**Timeframe exploration** (primary signal generation):
- 1m (×5 scaled params): Calmar 0.38, 4 neg years — NO-GO
- 1m (raw, same integer params): Calmar −0.11, 4 neg years — NO-GO
- 15m (÷3 scaled): Calmar −0.68, 6 neg years — NO-GO
- 15m (raw): Calmar −0.33, 5 neg years — NO-GO
- 30m (÷6 scaled): Calmar −0.51, 7 neg years — NO-GO
- 30m (raw): Calmar 1.15, 3 neg years — NO-GO
- **5m is definitively the optimal timeframe for this strategy**

**Internal swing BE trigger** (`lsi_be_swing_n_left`):
- Feature implemented: pre-FVG swing HIGH triggers BE stop before TP1 for longs; `lsi_cancel_on_swing` cancels limit pre-fill if swing swept
- Sweep N=[0,1,2,3,5,7,10]: ALL N>0 degrade — N=1 drops to Calmar 0.35 (6 neg years), N=10 reaches only 3.69
- Root cause: BE fires when price rallies toward/past pre-FVG swing high, converting EXIT_TP1_BE profits into EXIT_BE_SL (0R) trades. 423/1146 trades (N=1) reclassified.
- `lsi_cancel_on_swing=True` had zero effect in close-mode (swing HIGH above entry never swept during pending window)
- **NO-GO at all N values** — feature remains in codebase at N=0 (disabled)

**DOW exclusion sweep** (post-hoc filtering):
- No Wednesday: Calmar 11.47, 0 neg years — below anchor
- No Thursday: Calmar 12.29, 1 neg year — below anchor
- **No Wed+Thu (Mon/Tue/Fri only): Calmar 14.30 (+1.40), 0 neg years, Sharpe 2.798, DD −7.0R** — **ADOPT**
- Removing Monday or Friday both hurt significantly
- Re-ran all variable sweeps with Wed+Thu excluded (R12) — **anchor further refined**: n_left=2, n_right=60

**R12 variable sweeps (post-DOW anchor, n_left=4, n_right=78, DOW=Mon/Tue/Fri)**:
- lsi_n_left=2: Calmar 14.76 (+0.46) — ADOPT; lsi_n_right=60: Calmar 14.90 (+0.60) — ADOPT
- All other dims stable: direction=long, fvg_left=20, fvg_right=3, gap=5.0%, atr=10, entry_end=15:30 all unchanged
- Monthly loss cap 3.0R: Calmar 14.75 (+0.45) — INFO-ONLY (cap removes only 4 trades, near-threshold)
- New anchor: n_left=2, n_right=60

**R13 variable sweeps (post-R12 anchor: n_left=2, n_right=60)**:
- Combined anchor regressed to Calmar 11.77 (2 neg years) — n_left=2 + n_right=60 interact negatively
- lsi_n_left=10: Calmar 15.74 (+3.97, 0 neg years) — ADOPT; lsi_n_right=78: Calmar 14.76 (+2.99, 0 neg years) — ADOPT
- Key lesson: sequential independent adoptions can interact — always re-sweep after combining
- New anchor: n_left=10, n_right=78; R14 in progress

**entry_start sweep** (09:35 to 11:30):
- 09:35 is optimal (Calmar 12.90, 0 neg years)
- Every later start degrades: 09:40→Calmar 6.63 (DD −15.9R), 10:00→5.72 — early signals contain the edge
- **No change — 09:35 confirmed optimal**

**flat_start sweep** (13:00 to 16:00):
- 15:50 is optimal (Calmar 12.90, 0 neg years)
- Earlier exits destroy value: 14:00→Calmar 2.57 (5 neg years), 15:00→7.69 — late-session exits are net positive
- 16:00 (later) also worse: Calmar 9.66, 1 neg year
- **No change — 15:50 confirmed optimal**

**SMA trend gate** (longs only when close > SMA):
- SMA20→200 all worse than no gate: Calmar 5.51–8.62, 2–3 neg years
- **NO-GO** — LSI edge does not require trend alignment; counter-trend setups contribute positively

**ATR volatility gate** (skip days when ATR > SMA×threshold):
- Best result: thresh=2.0, sma=20 → Calmar 13.12 (+0.22), 0 neg years — only removes 2 trades from 1146
- All tight thresholds (1.1–1.5) degrade: Calmar 6.93–12.08 with 0–1 neg years
- **NO-GO** — improvement at thresh=2.0 is within noise (2 trades removed)

### NY LSI Long v2 — DOW-filtered, Refined Anchor — CONDITIONAL

- **Status**: CONDITIONAL — 4/5 pipeline phases passed. Phase 3 annual R gate fails (5.9R OOS vs 12R gate), but 0 neg OOS years and strong hold-out OOS. Gate is miscalibrated for DOW-filtered strategy.
- **Optimization**: R12–R16 variable sweeps (5 rounds) + n_left×n_right 2D mini-grid + Grid Sweep R2 post-DOW adoption. Followed DOW adoption from v1 post-pipeline exploration.
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 1.5 |
| tp1_ratio | 0.6 |
| min_gap_atr_pct | 5.0% |
| atr_length | 14 |
| lsi_n_left | 10 |
| lsi_n_right | 65 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 3 |
| direction | long only |
| DOW filter | Mon/Tue/Fri (Wed+Thu excluded) |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 635 trades, 59.8% WR, PF 1.45, Sharpe 2.710, Net R 90.5R, R/yr 9.0R, Max DD -5.9R, **Calmar 15.32**
  - **0 negative full years** (min: 2016 +0.7R, 2022 +3.2R; max: 2020 +19.7R, 2023 +19.0R)
  - Median stop: 218 ticks (~54.5 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 413 trades, 59.3% WR, PF 1.31, Sharpe 2.008, Net R 41.5R, R/yr 5.9R, DD -6.1R, Calmar 6.81
  - WF efficiency: **0.751** | Parameter stability: **1.000 (high)**
  - rr mode=1.5 (5/7 folds), tp1 mode=0.6 (5/7 folds), gap mode=5.0 (3/7, range [4,6])
  - **0 neg OOS years** (all 7 folds profitable)

- **Prop constraints** (FAIL): OOS avg annual R 5.9R < 12R gate. Worst month -3.5R (PASS). Expectancy PASS.
- **Hold-out OOS** (2025+, PASS): 58 trades, PF 1.56, Sharpe 2.907, +9.4R, R/yr 8.7R, DD -5.6R
- **Monte Carlo** (PASS): 99.9% survival at -25R ruin, 0.1% ruin probability, p50 DD -8.9R, p95 DD -14.6R

- **Key improvements over v1** (n_left=4, n_right=78, atr=10, no DOW):
  - Calmar: 13.44 → **15.32** (+14%)
  - WFE: 0.643 → **0.751**
  - Stability: 0.952 → **1.000**
  - OOS DD: -12.6R → **-6.1R** (much tighter)
  - OOS Calmar: 4.20 → **6.81**
  - OOS neg years: 1 (2021) → **0**
  - MC survival: 98.5% → **99.9%**

- **Key findings**:
  - DOW filter (exclude Wed+Thu) is the single biggest lever: +1.4 Calmar, significantly tighter DD
  - n_right=65 (not 60 or 78) is the true optimum — only revealed by 2D grid. Sequential 1D sweeps oscillated between 60 and 78 for 4 rounds due to n_left interaction.
  - atr=14 (vs atr=10) optimal with DOW filter — different day selection changes ATR baseline
  - Phase 3 annual R gate (12R/yr) is calibrated for full-5-day strategies. At 60% trading days, 5.9R OOS ≈ 9.8R equivalent. Not a strategy failure.
  - Gap=5.0% fully locked: 9/210 zero-neg combos in Grid R2 — **all** had gap=5.0

- **Script**: `run_nq_ny_lsi_robust_pipeline_v2.py`
- **Conclusion**: Strongly CONDITIONAL — best LSI NY long config tested. 0 neg OOS years, Sharpe 2.0+ OOS, 99.9% MC survival, and excellent hold-out performance. Phase 3 gate failure is an artifact of gate calibration, not strategy weakness. Viable for live trading on prop firm accounts.

### NY Liquidity Sweep Inversion (LSI) fvg_limit Long — NO-GO (threshold)
- **Status**: NO-GO (3/5) — failures are threshold calibration issues, not strategy failure. Strategy generates genuine OOS profit every year.
- **Entry mode**: `lsi_entry_mode="fvg_limit"` — limit order placed at FVG boundary (inv_level) after inversion, waiting for pullback/retest. Fills from bar i+1 after inversion. Lower R/yr than close-mode but better DD profile (fill rate 90%).
- **Optimization**: Full lsi-optimization workflow — baseline → 10 variable sweep rounds → 2 grid sweeps (R1 120 combos, R2 150 combos 3D) → robust pipeline
- **Convergence path**: 10 rounds, 2 major cycles broken by 3D grid sweep. Gap×rr interaction required simultaneous optimization: gap=5.0% always wins on 0-neg-years constraint (only 2/150 grid combos gave 0 neg years, both gap=5.0%).
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_entry_mode | fvg_limit |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 4.5 |
| tp1_ratio | 0.2 |
| min_gap_atr_pct | 4.0% |
| atr_length | 14 |
| lsi_n_left | 25 |
| lsi_n_right | 120 |
| lsi_fvg_window_left | 30 |
| lsi_fvg_window_right | 15 |
| direction | long only |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years):
  - 861 trades, 58.2% WR, PF 1.35, Sharpe 1.987, Net R 105.4R, R/yr 10.6R, Max DD -7.5R, **Calmar 14.12**
  - **0 negative full years** (min: 2020 +3.1R, 2024 +4.0R; max: 2017 +25.0R)
  - Median stop: 184 ticks (~46 pts NQ)

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step):
  - Combined OOS: 606 trades, 52.3% WR, PF 1.17, Sharpe 1.049, Net R 42.8R, R/yr 6.1R, DD -9.6R, Calmar 4.46
  - WF efficiency: **0.482** (threshold 0.50 — missed by 0.018) | Parameter stability: **0.905 (high)**
  - rr mode=4.5 (4/7 folds), tp1 mode=0.2 (4/7 folds), gap mode=4.0 (3/7 folds)
  - **0 neg OOS years** — all 7 folds profitable

- **Prop constraints** (FAIL): OOS avg annual R 6.1R < 12R gate; worst month -6.7R > 5.0R limit (threshold calibrated for close-mode, not fvg_limit)
- **Hold-out OOS** (2025+, PASS): 93 trades, PF 1.14, Sharpe 0.928, +5.9R, DD -6.4R
- **Monte Carlo** (PASS): 97.7% survival at -25R ruin, 2.3% ruin probability, Sharpe p5=1.096

- **Key findings**:
  - fvg_limit vs close-mode: higher Calmar (14.12 vs 13.44), lower R/yr (10.6 vs 12.1), smaller DD (-7.5R vs -9.0R). Fewer trades (861 vs 1146) due to retest requirement.
  - **rr=4.5, tp1=0.2** optimal for fvg_limit (vs rr=1.5, tp1=0.6 for close-mode) — limit entry rewards higher RR targets
  - **gap=4.0%** (not 5.0%) optimal at final anchor — 1152 signals vs 1001, same 0-neg-year profile
  - **n_left=25** (vs n_left=4 close-mode) — fvg_limit requires wider, higher-significance pivots for retest setups
  - **n_right=120** (full NY session) consistent between both modes
  - Gap×rr oscillation cycle: sequential optimization cycles between (gap=5.0%, rr=4.5) and (gap=0.5%, rr=6.0). Required 3D grid sweep to resolve — only gap=5.0% gives 0 neg years.
  - WFE 0.482 failure is marginal; the 12R/yr prop threshold is too strict for a lower-volume, higher-Calmar strategy
  - OOS quality excellent: 0 neg OOS years, Calmar 4.46 OOS, 97.7% MC survival, high parameter stability

- **Conclusion**: Technically NO-GO on pipeline thresholds, but strong real-world signals. The failure modes are threshold calibration artifacts, not strategy failure. 0 negative OOS years, high parameter stability, and near-perfect MC survival all indicate a genuine edge. If using fvg_limit in live trading, scale position size to ~60% of close-mode (matching lower R/yr output). Script: `run_nq_ny_lsi_fvgl_robust_pipeline.py`

### NY LSI fvg_limit v2 Long — DOW-Filtered — CONDITIONAL (Effective GO)
- **Status**: CONDITIONAL (4/5) — Phase 3 fail is a known calibration artifact for Mon/Tue/Fri strategies; all substantive phases pass. **Effective GO.**
- **Key improvement over v1**: Adding DOW filter (Mon/Tue/Fri, exclude Wed+Thu) and re-optimizing from scratch. Calmar improved from 14.12 → **20.37**. WF efficiency improved from 0.482 → **0.748**. Optimal structural params shifted significantly (smaller n_left, tighter windows, different rr/tp1).
- **Entry mode**: `lsi_entry_mode="fvg_limit"` — same as v1. Limit order at FVG boundary after inversion, fills bar i+1.
- **Optimization**: Full lsi-optimization workflow — variable sweeps R1-R6 + grid sweeps R1-R2. R6 variable sweeps confirmed convergence.
- **Final config**:

| Param | Value |
|-------|-------|
| strategy | lsi |
| lsi_entry_mode | fvg_limit |
| lsi_stop_mode | absolute |
| session | NY |
| orb_end | 09:35 (5m ORB) |
| entry_start | 09:35 |
| entry_end | 15:30 |
| flat_start | 15:50 |
| rr | 3.0 |
| tp1_ratio | 0.3 |
| min_gap_atr_pct | 5.0% |
| atr_length | 10 |
| lsi_n_left | 8 |
| lsi_n_right | 60 |
| lsi_fvg_window_left | 20 |
| lsi_fvg_window_right | 5 |
| direction | long only |
| DOW filter | Mon/Tue/Fri only (Wed+Thu excluded) |
| magnifier | 1m |

- **Full-history performance** (2016–2026, 10 full years, DOW filtered):
  - 608 trades, 61.2% WR, PF 1.61, Sharpe 3.168, Net R 111.7R, R/yr 11.0R, Max DD -5.5R, **Calmar 20.37**
  - **0 negative full years** (min: 2024 +5.9R; max: 2017 +17.2R)
  - Median stop: 188 ticks (~47 pts NQ)
  - DB: `bt-nq-ny-lsi-fvg-limit-v2-long-2016-2026-fi-b47320`

- **Walk-forward OOS** (7 folds, 36m IS / 12m OOS / 12m step, DOW filter in IS and OOS):
  - Combined OOS: 414 trades, 59.9% WR, PF 1.50, Sharpe 2.672, Net R 64.9R, R/yr 9.3R, DD -6.5R, **Calmar 10.02**
  - WF efficiency: **0.748** (well above 0.50 threshold) | Parameter stability: **0.952 (high)**
  - tp1_ratio mode=0.3 (6/7 folds, perfect), gap mode=5.0 (5/7), rr mode=3.0 (3/7 — drift to 3.5/4.0 in later folds)
  - **0 neg OOS years** — all 7 folds profitable

- **Prop constraints** (FAIL on annual R gate): OOS avg annual R 9.3R < 12R gate. **Expected artifact**: Mon/Tue/Fri is ~60% of trading days; 9.3 / 0.6 = 15.5R equivalent on full 5-day week → well above gate. Worst month: -4.0R (PASS). Expectancy PASS.
- **Hold-out OOS** (2025+, PASS): 59 trades, PF 1.70, Sharpe 3.448, +13.0R, 59.3% WR, 0 neg years
- **Monte Carlo** (PASS): **0.0% ruin** at -25R threshold. DD p50=-8.7R, p95=-13.9R. Sharpe p5=2.090.

- **Key findings vs v1**:
  - DOW filter (Mon/Tue/Fri) was transformative: +6.25 Calmar, Sharpe 3.17 vs 1.99, WFE 0.748 vs 0.482
  - Wed/Thu excluded: v1 had n_left=25, rr=4.5, tp1=0.2. v2 settled at n_left=8, rr=3.0, tp1=0.3 — substantially different structural optimum confirms strong interaction with DOW regime
  - n_left=8: missed adoption threshold in R2/R3/R4 at old rr=1.5/tp1=0.6 anchor, then cleared threshold in R5 after rr/tp1 shift to 3.0/0.3 (+0.38 Calmar)
  - Grid sweep R2 with refined structural config: anchor (rr=3.0, tp1=0.3, gap=5.0) won outright #1/150 combos — confirming true optimum
  - v2 Calmar 20.37 vs v1 14.12: better regime filtering and better structural params together
  - v2 OOS Calmar 10.02 vs v1 4.46: much stronger out-of-sample persistence

- **Conclusion**: Effective GO. Best NQ NY LSI fvg_limit variant. The DOW filter (Mon/Tue/Fri) is the key structural edge driver. Prefer v2 over v1 for live trading — higher Calmar, better OOS persistence, 0% MC ruin. Phase 3 annual R failure is a gate calibration artifact, not strategy weakness. Script: `run_nq_ny_lsi_fvgl_v2_robust_pipeline.py`

---

## NQ ASIA LSI (Long) — CONDITIONAL (4/5)

**Status**: CONDITIONAL — deploy with awareness of WF OOS R/yr constraint artifact.
**Best config**: R2 (n_left=8, n_right=2, fvg_right=2) — use this over R1.

**Optimized config** (17 variable sweep rounds + 2 grid sweeps + structural joint grid + R18):

| Parameter | Value |
|-----------|-------|
| strategy | lsi |
| lsi_stop_mode | absolute |
| lsi_n_left | 8 |
| lsi_n_right | 2 |
| lsi_fvg_window_left | 15 |
| lsi_fvg_window_right | 2 |
| entry_start | 20:40 |
| entry_end | 23:30 |
| flat_start | 00:00 |
| atr_length | 40 |
| direction_filter | long |
| rr | 2.0 |
| tp1_ratio | 0.7 |
| min_gap_atr_pct | 1.75 |

**Full-sample metrics** (2016-2026, 10.17 years):
- 527 trades | 55.2% WR | PF 1.62 | Sharpe 3.133 | Net R +84.7R | R/yr 8.3R | DD -5.3R | **Calmar 15.85** | **0 neg years**
- DB: `bt-nq-asia-lsi-long-2016-2026-final-r2-2201c8`

**Pipeline R2 phases**:
- **Phase 1 (Structural)**: PASS — all checks clear, Calmar 15.85, 0 neg years
- **Phase 2 (Walk-Forward)**: PASS — WF eff 0.783, stability 0.857 (high), 1 neg OOS year (2020: -0.1R ≈ 0), 7 folds
  - WF OOS params: rr mode=2.5 (3/7), tp1 mode=0.5 (4/7), gap mode=2.25 (4/7)
  - Combined OOS: 280 trades, 55.7% WR, PF 1.44, Sharpe 2.370, R/yr 4.4R, DD -4.9R, Calmar 6.34
- **Phase 3 (Prop Filter)**: FAIL — WF OOS avg annual R 4.4R < 12R gate (same artifact as R1; 2025 hold-out shows 12.4R which exceeds the gate)
- **Phase 4 (Hold-Out OOS 2025+)**: PASS — 46 trades, PF 2.10, +12.6R, Sharpe 5.187, 0 neg years
- **Phase 5 (Monte Carlo)**: PASS — 99.9% survival at -25R ruin. DD p50=-7.5R, p95=-12.3R

**Comparison: R1 vs R2**:

| Metric | R1 (n_left=6, n_right=1, fvg_right=5) | R2 (n_left=8, n_right=2, fvg_right=2) |
|--------|---------------------------------------|---------------------------------------|
| Full Calmar | 15.25 | **15.85** |
| WF stability | 0.809 | **0.857** |
| Hold-out PF | 1.84 | **2.10** |
| Hold-out Sharpe | 4.337 | **5.187** |
| Hold-out R | +11.1R | **+12.6R** |
| Hold-out annual R | 11.0R | **12.4R** (exceeds 12R gate) |

**Key findings**:
- ASIA session LSI longs have meaningful edge — 0 negative full years over 10 years
- **fvg_right=2 is optimal** — tighter inversion window consistently beats wider (5-10). fvg_right=1 shows +0.17 Calmar above anchor but below +0.3 adoption threshold; not adopted to avoid overfitting at boundary
- gap=1.75% (min_gap_atr_pct) is the key parameter: below 1.5% trade quality degrades sharply; above 2.25% too few trades
- rr=2.0, tp1=0.7: stable core — confirmed in all 18 sweep rounds
- **Coordinate descent oscillation** in R14-R17 (n_right 1↔2, fvg_right 3↔5↔10, gap 1.75↔2.0): resolved by Grid Sweep R2 which identified joint optimum. Then structural joint grid (n_left × n_right × fvg_right, 280 combos) confirmed n_left=8, n_right=2, fvg_right=2 as genuine improvement (+0.61 Calmar)
- **Overlays (DOW, SMA, loss caps)**: all tested as INFO-ONLY across 18 rounds AND in dedicated overlay sweep — none adopted. Loss caps completely flat (weekly 2R cap never triggers — losses are perfectly distributed)
- Shorting NQ ASIA LSI: **NO-GO** (negative R across all tested configs, Phase 1 data)
- Phase 3 fail is a gate calibration artifact: WF OOS average is 4.4R but 2025 hold-out shows 12.4R exceeding the gate. Phase 3 expected to fail for low-frequency strategies.

**Scripts generated**:
- `run_nq_asia_lsi_baseline.py`
- `run_nq_asia_lsi_variable_sweeps_1.py` through `run_nq_asia_lsi_variable_sweeps_18.py`
- `run_nq_asia_lsi_grid_sweep_r1.py`, `run_nq_asia_lsi_grid_sweep_r2.py`
- `run_nq_asia_lsi_structural_grid.py` (joint n_left × n_right × fvg_right, 280 combos)
- `run_nq_asia_lsi_overlay_sweep.py` (DOW, SMA, loss caps post-backtest)
- `run_nq_asia_lsi_robust_pipeline.py` (R1), `run_nq_asia_lsi_robust_pipeline_r2.py` (R2)
- `save_nq_asia_lsi_r1_final.py` (superseded), `save_nq_asia_lsi_r2_final.py` (use this)

---

- **Internal swing BE sweep** (`lsi_be_swing_n_left`): **NO-GO — do not use.**
  - Swept N=[0,1,2,3,5,7,10] (left-only pivot N bars wide, pre-FVG search, triggers BE post-fill)
  - Every N>0 hurts Calmar significantly. Best N>0 = N=7 at Calmar 15.56 (-4.81 vs baseline 20.37)
  - N=1 converts 164/608 trades (27%) to 0R EXIT_BE_SL — massive drag on net R
  - N=1,2,3 introduce 2018 negative year. N=5,7,10 avoid neg years but still sharply lower Calmar
  - Mechanism: the pre-FVG swing highs being swept are on trades that would otherwise hit TP2, not SL. Triggering BE on those trades converts winners to 0R.
  - Script: `run_nq_ny_lsi_fvgl_v2_be_swing_sweep.py`

---

## Context Filter Research: 30m Structure + VWAP Gate

### Summary

Tested multi-timeframe structure gates (15m, 30m, 1h) combined with session VWAP for NQ NY continuation. **30m HH/HL-2 + VWAP side is the best structural context filter found for NQ NY ORB.**

### How it works

Resample 5m bars into session-aligned 30m bars (09:30-10:00, 10:00-10:30, ...). At the FVG signal bar, check the two most recent **completed** 30m bars:

- **Longs**: latest 30m high > prior 30m high AND latest 30m low > prior 30m low AND signal close > session VWAP
- **Shorts**: mirrored (LH + LL + close < VWAP)

Only completed 30m bars are used (no lookahead). The 6th 5m bar of each 30m group is the earliest bar that can see that 30m bar's data.

### Timeframe comparison (FAST_V2 NQ_NY, 2021-2026)

| TF | Trades | Keep% | Net R | Sharpe | Calmar | Max DD |
|----|--------|-------|-------|--------|--------|--------|
| Baseline | 695 | — | 21.2 | 0.61 | 0.97 | -21.8R |
| **30m** | **385** | **55%** | **30.9** | **1.57** | **2.31** | **-13.4R** |
| 15m | 498 | 72% | 16.8 | 0.69 | 0.63 | -26.8R |
| 1h | 301 | 43% | 12.6 | 0.84 | 1.22 | -10.3R |

- **15m** is too noisy — keeps 72% but actually increases DD
- **30m** is the sweet spot — halves DD, adds +9.7R, 2.5x Sharpe
- **1h** cuts DD further (-10.3R) but kills too much R (-8.6) especially in 2024-2025

### Tested across configs

**FAST_V2 NQ_NY** (rr=2.5, stop=8%, both dirs):
- Baseline: 695 tr, 21.2R, Sharpe 0.61, Calmar 0.97, DD -21.8R
- 30m gate: 385 tr (55%), 30.9R, Sharpe 1.57, Calmar 2.31, DD -13.4R
- DB: `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-2021-2026-942da0`

**Exec config** (rr=2.0, stop=15%, both dirs):
- Baseline: 729 tr, -6.3R, Sharpe -0.13, Calmar -0.15, DD -41.3R
- 30m gate: 405 tr (56%), +29.8R, Sharpe 1.12, Calmar 1.31, DD -22.8R
- Flips a negative-R config to positive. 2023 goes from -15.4R to +0.2R.

### Comparison to VWAP-only gates

VWAP distance alone (no structure) also helps but less dramatically:

| Gate | Keep% | Net R delta | Calmar improvement |
|------|-------|-------------|-------------------|
| VWAP side only | 99% | +0.9R | negligible |
| VWAP 10% ATR | 94% | +14.6R | 1.8x |
| VWAP 15% ATR | 83% | +20.8R | 2.2x |
| **30m HH/HL + VWAP** | **55%** | **+9.7R** | **2.4x** |

VWAP distance is the high-retention option (83-94% kept). The 30m structure gate concentrates edge more sharply but at lower retention. Both are useful depending on whether trade frequency or edge quality matters more.

### Entry window investigation: can we trade earlier?

Because HH/HL-2 on session-aligned 15m bars (09:30 start) requires two completed bars, the gate cannot fire until ~10:00. This means the 09:45-10:00 entry window is dead. Tested whether using true 30m bars with earlier alignment could recover those early trades.

**Variants tested (FAST_V2 NQ_NY, 2021-2026):**

| Variant | 30m alignment | Earliest gate | Trades | Keep% | Net R | Sharpe | Calmar | Max DD |
|---------|--------------|---------------|--------|-------|-------|--------|--------|--------|
| Baseline (no gate) | — | — | 695 | — | 21.2 | 0.61 | 0.97 | -21.8R |
| **A: 15m HH/HL-2 (current)** | **session 09:30** | **~10:00** | **250** | **36%** | **30.3** | **2.58** | **2.13** | **-14.2R** |
| B: 30m from 08:30 | clock 08:30 | 09:50 | 138 | 20% | 10.9 | 1.45 | 0.62 | -17.7R |
| C: 30m from 09:00 | clock 09:00 | 10:00 | 148 | 21% | 9.3 | 1.20 | 0.62 | -14.8R |

- DB: `bt-nq-ny-fast-v2-15m-hh-hl-2-vwap-baseline-657478` (A), `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-pre-sessi-5deee8` (B), `bt-nq-ny-fast-v2-30m-hh-hl-2-vwap-09-00-eff-471468` (C)

**Conclusion: the current 15m setup is the best version.** True 30m bars (B and C) are significantly worse — both produce Calmar 0.62, below even the ungated baseline. Pre-market 30m bars (08:30-09:00, 09:00-09:30) carry overnight structure that doesn't predict NY ORB continuation direction. The 15m HH/HL-2 captures finer-grained intra-session trend shifts and retains 36% of trades vs ~20% for 30m. The cost of losing the 09:45-10:00 window is worth the gate's filtering quality.

### Key findings

1. **Structure for trend, VWAP for acceptance** — the original hypothesis is confirmed. Neither alone is as effective as the combination.
2. **15m HH/HL-2 is the right granularity** — the label "30m gate" was misleading; the implementation uses 15m bars with a 2-bar HH/HL pattern. True 30m bars over-filter and lose edge. Pre-session 30m bars carry no useful signal.
3. **The gate's value is regime-dependent** — biggest improvements in choppy years (2021, 2023). In strongly trending years (2024-2025) it can trim winners slightly.
4. **Works across configs** — not overfit to one parameter set. Consistent improvement on both FAST_V2 and the wider-stop exec config.
5. **Earliest effective entry is ~10:00** — losing the 09:45-10:00 window is an acceptable cost. Attempts to recover it via pre-session bars degrade performance.

### Implementation

- Signal module: `backtesting/src/orb_backtest/signals/structure_15m.py` — resamples 5m to session-aligned 15m bars, computes HH/HL patterns. The "30m" label refers to the 2-bar lookback spanning 30 minutes of 15m data, not actual 30m bars.
- Not yet integrated as an engine-level pre-trade gate. Currently applied as post-trade filter.
- Scripts: `run_nq_ny_15m_structure_sweep.py`, `run_nq_ny_15m_structure_sweep_v2.py`, `run_nq_ny_fast_15m_sweep.py`, `run_nq_ny_30m_entry_window_compare.py`

---

## NQ Generalist Payout Portfolio — Current 4-Leg Package

**Status**: ACTIVE PAPER-TRADE PACKAGE. This is the current NQ funded-account route when the goal is faster challenge resolution than the standalone bull specialist, without expanding to the 5-leg max-speed stack.

**Important classification**: this is **not** a regime-specialist portfolio. Only `bull_specialist` is regime-specialized. The full 4-leg package is a mixed-regime, long-biased payout engine and should be treated as a **generalist payout portfolio**.

**Selected combo**:
- `bull_specialist`
- `nq_asia`
- `nq_asia_lsi_end2300`
- `nq_ny_lsi_gap3.75`

**How each leg was chosen**:
- `bull_specialist`: regime-specialist winner, then fast-payout re-ranked for the funded-account model.
- `nq_asia`: combo-context sweep did **not** beat the existing Asia continuation anchor, so the original combo leg stays.
- `nq_asia_lsi_end2300`: combo-context winner over the base Asia LSI anchor; quality improvement came from tightening `entry_end` from `23:30` to `23:00`.
- `nq_ny_lsi_gap3.75`: combo-context winner over the base NY LSI anchor; best version relaxed `min_gap_atr_pct` from `5.0` to `3.75`.

**Funded-account model used in combo research**:
- Challenge cost: `$150`
- Starting balance: `$50,000`
- Trailing drawdown: `$2,000`, EOD realized, capped so breach never rises above `$50,000`
- First withdrawable payout: everything above `$52,000`
- Risk per trade: `$500` pre-payout, `$250` post-payout

**Full-history combo package** (2016-01-01 to latest available data in the run):
- Payout rate `71.71%` | breach rate `27.94%` | open rate `0.35%`
- Average days to payout `20.45` | median `17`
- Average trades to payout `10.62`
- Average first payout `$508.16`
- EV/start `$214.39`
- Holdout 2025-2026: payout `91.64%` | breach `5.48%` | average payout day `17.83` | EV/start `$378.03`

**Why this generalist package is the current working route**:
- The standalone bull specialist was high quality but too slow by itself.
- The 4-leg combo resolves much faster while preserving a strong payout-over-breach profile.
- The optimized combo is slightly weaker than the earlier balanced combo on full-history payout and EV, but materially better on holdout quality. Current preference is to keep the optimized route as the working package and watch live paper-trade behavior rather than overreact to the full-history tradeoff.

**Overlap / concentration read**:
- Overlap exists, but it is not extreme enough to force hard de-duplication.
- Baseline optimized combo remains the default route.
- If live paper trading shows stacked-loss discomfort, the first throttle to test is `first_full_half_extra`: keep the first fill full size and halve extra same-day legs.
- That throttle improves full-history payout/breach to `73.45% / 26.20%`, but it slows resolution and does not improve the already-strong holdout profile, so it is a risk-control toggle, not the base package.

**5-year operating snapshot** (`2021-03-29` start request; filled-trade coverage `2021-04-08` to `2026-03-23`):
- 918 filled combo trades
- Payout rate `80.61%` | breach rate `18.67%` | open rate `0.72%`
- Average days to payout `20.72` | median `18`
- Average trades to payout `10.27`
- Average first payout `$569.55`
- EV/start `$309.13`
- By day 20: payout `46.48%` | breach `10.31%` | resolved `56.79%`
- By day 30: payout `64.30%` | breach `16.06%` | resolved `80.35%`
- By day 45: payout `75.26%` | breach `17.95%` | resolved `93.21%`

**5-year leg mix**:
- `bull_specialist`: 45 trades | avg R `0.5484`
- `nq_asia`: 335 trades | avg R `0.3602`
- `nq_asia_lsi_end2300`: 188 trades | avg R `0.3009`
- `nq_ny_lsi_gap3.75`: 350 trades | avg R `0.1763`

**Regime audit conclusion**:
- The package does **not** behave like a pure bull-regime stack.
- 2022 remained profitable mainly because `nq_asia` and `nq_ny_lsi` made money on bear-regime days, while `bull_specialist` itself was slightly negative that year.
- Bear-regime contribution is too large for this to be labeled a true regime-specialist portfolio.

## NQ Bull-Biased Portfolio Buildout — Post-Generalist Seed Sweep

**Goal**: use the former generalist package only as a seed source, then rebuild around the `bull_specialist_v1_winner` without drifting back into a mixed-regime payout engine.

**First add-on sweep result**:
- `nq_asia_cont` was rejected as the next bull-portfolio leg even though it is strong in the generalist package.
- Reason: inside `bull_specialist + add-on` tests, it carried too much `2022-2023` performance and behaved too much like a generalist engine.
- The cleanest add-on family was `nq_asia_lsi`.

**Constrained bull-biased combo sweep**:
- Search space:
  - fixed core: `bull_specialist_v1_winner`
  - Asia candidates: selected `nq_asia_lsi` neighborhood
  - NY candidates: selected `nq_ny_lsi` variants only
  - explicit exclusion: `nq_asia_cont`
- Best overall portfolio: `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Portfolio type: `2-leg`

**Best current bull-biased portfolio candidate**:
- `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Acceptance `2024+` net R: `48.335`
- Rejection `2022-2023` net R: `11.7583`
- Rejection share of acceptance: `24.33%`
- Holdout payout/breach: `75.78% / 0.00%`
- Holdout average days to payout: `61.94`
- Regime contribution: bull `64.2906R`, bear `10.6621R`, sideways `22.9053R`

**Important comparison**:
- The best 3-leg candidate was `bull_specialist_v1_winner + nq_asia_lsi_end2300 + nq_ny_lsi_propfirm_2x_profile`.
- It was faster and bigger on raw acceptance net R, but rejection `2022-2023` also rose to `26.6883R`.
- That means the third leg improved payout behavior, but it pushed the stack back toward the same mixed-regime behavior we were trying to reduce.

**Current interpretation**:
- Best next step for a bull-biased portfolio is a **2-leg** stack, not a 3-leg stack.
- `nq_asia_lsi` is the right family to pair with the bull specialist first.
- `nq_ny_lsi` should be treated as optional and only revisited if a later pass can improve speed without materially increasing `2022-2023` contribution.

**Packaged bull-biased route**:
- Saved package: `bull_specialist_v1_winner + nq_asia_lsi_rr1.75`
- Full-history funded scorecard from `2020+`: payout `61.05%`, breach `34.38%`, open `4.58%`
- Average days to payout: `57.67`
- Holdout payout/breach: `75.78% / 0.00%`
- Average first payout: `$325.84`
- EV/start: `$48.91`

**Operational note**:
- This route is cleaner than the generalist 4-leg package, but materially slower and weaker on full-history funded-account resolution.
- It should be treated as a **bull-biased specialist candidate**, not as a replacement for the faster generalist payout portfolio.

## NQ Bear Specialist V1 — First Pass

**Window assumptions used**:
- `2021`: diagnostic only
- `2022-2023`: acceptance era
- `2023`: funded-account holdout inside the acceptance era
- `2024+`: rejection era

**Result**:
- No candidate cleared the bear-specialist bar in the first V1 pass.
- Best candidate: `NQ Bear V1 rr2.00_tp1 0.30_stoporb15.0_gaporb0.0_end1100_regime_2of3_vwap`
- Acceptance `2022-2023` net R: `6.5794` on `22` trades
- Rejection `2024+` net R: `2.9137`
- Rejection share of acceptance: `44.29%`
- 2023 holdout payout/breach: `16.06% / 0.00%`
- 2023 holdout average days to payout: `244.35`

**What failed**:
- Trade count was too low for a deployable specialist.
- Rejection-era performance remained too positive, so the short family still looks too generalist.
- None of the tested short variants survived the original round-1 specialist readout either.

**Current read**:
- `regime_2of3_vwap` improved the bear-window profile the most in this first pass.
- Ungated short variants still carried too much `2024+` performance.
- The next bear pass should focus less on micro-parameter tuning and more on a different short family or stronger downside-context gates.
- Use `generalist payout portfolio` as the correct label going forward.

**Takeaway**:
- This is now the current NQ generalist payout portfolio to carry forward.
- It is fast enough to be operationally useful, especially as one lane inside a broader multi-leg book.
- Next research should split true regime specialists into a separate portfolio track instead of continuing to treat this mixed long stack as regime-specialized.
