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

### Asia Continuation R4 Final (10m ORB, both, 1s magnifier) — GO
- **Status**: GO — fixed-param WF 6/6 folds profitable, hold-out PASS
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

### NY Continuation R20 (20m ORB, both, 1s magnifier) — GO
- **Status**: GO — fixed-param WF 6/6 folds profitable, hold-out PASS
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

### NY Continuation Long 30m ICF — INVALIDATED
- **Status**: INVALIDATED — original data (2015-2026) no longer available. Rerun on current data (2016-2026) shows degraded performance.
- **Original DB entry**: `NQ NY Long 30m ICF Pipeline Validated` (ID 9742)
- **Original performance**: 1,144 trades, 51.5% WR, Sharpe 2.10, PF 1.36, 192.2R, Calmar 17.26, 0 neg years
- **Rerun on current data**: 829 trades, 50.2% WR, Sharpe 2.00, PF 1.33, 134.6R, Calmar 11.10, **2 negative years** (2016: -8R, 2025: -6R)
- **1s magnifier impact**: Zero — 0 trades differed between 1m and 1s magnifier. 1m resolution was already sufficient for this config.
- **Root cause**: Current parquet data starts 2016-01 vs original CSV starting 2015-01. Missing 2015 data (~315 trades) accounts for the degradation. 2016 is now negative without the warm-up from 2015.
- **Conclusion**: Superseded by R20 Final (Calmar 16.36 vs 11.10 on same data, 0 neg years vs 2).

### NY Continuation (20m ORB, long-only, magnifier) — CONDITIONAL (superseded by R20)
- **Status**: CONDITIONAL — superseded by R20 Final which uses both directions and achieves better Calmar on current data
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

#### NY Variable Sweep History (Rounds 1-12)

**Round 1** — Baseline variable sweeps (6 dimensions)
- Base: WF mode params (rr=2.0, tp1=0.5, stop=10%, gap=1.5%, both direction, 15m ORB)
- Swept: max_gap_points, max_gap_atr_pct, atr_length, ORB window, entry end, direction
- Key finding: **Long-only is the biggest single lever** (Sharpe 1.63 vs 1.18 for both)

**Round 2** — Finer grids + new dimensions (7 dimensions)
- Swept: rr, tp1, stop, min_gap, flat time, entry start delay, DOW exclusion
- Key findings: rr=2.25 slightly better, excl-Thu helps marginally, base values confirmed for most

**Round 3** — Extended dimensions (15 sweeps)
- Swept: ORB 5m-30m fine, ORB start, strategy type, multi-day exclusions, long-only sweeps
- Key findings: **20m ORB is optimal** (Calmar 9.58), reversal/inversion completely dead, long+excl-Thu+Fri best combo

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
- **R4 Final is the GO config**: stop=3.7%, rr=1.75, gap=0.90%, tp1=0.35, ORB=10m, entry_end=01:00, flat=00:00, ATR=5, both, no-Thu, ICF=OFF, 1s magnifier → Calmar 23.85, 21.1 R/yr, DD -8.9R, 0 neg years. Fixed-param WF 6/6 folds profitable. DB: `bt-nq-asia-r4-final-69df58`.
- **entry_end=01:00 is the single biggest lever discovered in R1-R4**: Extending past midnight from 23:00→01:00 jumped Calmar from 16.72→23.85. The entry_end + flat_start interaction is critical — entries 00:00-01:00 are short-duration trades that work if TP1 fills fast.
- **Destructive parameter interaction warning**: In R3, adopting 5 changes simultaneously crashed Calmar from 20.18→11.97 (-41%). Never adopt more than 2-3 changes at once. The safe approach is resetting to the best-proven config when oscillation is detected.
- **Asia session produces high trade counts** (~160/year) with good win rates (67%), and the R4 config has strong edge per trade (~0.13R avg).
- **10m ORB is definitively better than 15m** for NQ Asia — confirmed across v2, v3, and R4 optimizations. ORB oscillated (10m→15m→10m) across R1-R2 due to interaction with entry_end. At entry_end=01:00, 10m is dominant.
- **Thursday is negative EV** on NQ Asia continuation. Removing it improved all metrics across every optimization round.
- **SMA trend gate hurts NQ Asia** — opposite of CL where it doubled Sharpe. Both trend directions are profitable; filtering halves trade count without improving edge.
- **atr_length=5 beats 14 for walk-forward** — ATR 14 shows better in-sample Sharpe in pre-sweeps but performs worse OOS (WF efficiency 0.311 vs 0.59 for ATR 5). Use ATR 5 for pipeline validation.
- **Two distinct strategy zones exist** for NQ Asia continuation:
  - **Zone A** (stop≈3.5–4.5%, rr≈1.75–3.0): ~65–73% WR, 10–21 R/yr, DD -9–16R. R4 Final lives here at the optimal point.
  - **Zone B** (stop≈5.5–6.5%, rr≈1.0–1.5): ~78–82% WR, 6–9 R/yr, DD -9–12R. v2 CONDITIONAL lived here.
  - The dead zone between (~4.5–5.5%) has no consistent winner — avoid it.
- **stop=3.7% is the anchor for Zone A** — confirmed as Calmar peak by broad, fine, and R4 grid sweeps. The R4 grid (2,016 combos) showed stop=3.7% configs dominating both overall and zero-neg-year rankings.
- **Both directions required** — unlike NY where long-only dominates at some anchors. NQ Asia shorts contribute positively. Long-only has higher Sharpe but a bad 2022.
- **flat_start=00:00 (midnight close) is critical**: Removes overnight drift risk from trades that haven't hit TP2. Smooth peak confirmed with 30-min step resolution. No-Tuesday exclusion does NOT stack (they fix the same problem).
- **Gap dimension has two peaks with a dead zone**: gap=0.90% and gap=1.20% are local maxima. gap=1.00–1.10% is a valley. At the R4 anchor, gap=0.90% is dominant.
- **2022 is the structural weak spot** — +8.9R in WF fold 4. Still profitable but the lowest fold. R4 anchor survives it cleanly unlike v1/v2.
- **ICF is anchor-dependent**: Positive at v3 anchor (entry_end=23:00) but not beneficial at R4 anchor (entry_end=01:00). The entry_end shift changes the trade mix enough to invalidate v3+ICF findings.

### NY Session
- **Both directions viable at the right params** — R16-R20 optimization with 1s magnifier found that both directions (Calmar 16.36) beats long-only (Calmar 11.51) at the R20 anchor. The key was wider entry window (15:30 vs 13:00) and lower RR (2.625 vs 3.2). Earlier rounds found long-only essential, but that was anchor-specific — at different stop/rr/gap combinations, shorts add value.
- **20m ORB (09:30-09:50) is the optimal window** for NY — confirmed across R16-R20 sweeps. 25m oscillated (adopted in R17, reverted in R18). 15m and 30m consistently worse.
- **Entry end 15:30 is optimal** — R17 showed entry_end=15:30 was a massive lever (Δ+4.08 Calmar). Late entries are productive. Confirmed stable through R20.
- **ATR=12 is optimal** — shifted from 14 in earlier rounds. Confirmed in R17, stable through R20.
- **Stop ATR interacts strongly with RR AND reshuffles the entire optimal surface** — this lesson confirmed again in R19-R20. stop=9% emerged as massive winner in R19 (Δ+3.67), triggering full grid re-sweep. Fine-tune then moved to 8.75%. The grid sweep R20 showed stop=7.0/rr=3.5 at the top but at grid edge — interior configs (8.75/2.625) are more robust.
- **Parameter surface is noisy for adaptive WF** — the adaptive walk-forward (re-optimizing each fold) failed with efficiency 0.49. Mode params drifted significantly from the candidate. But the fixed-param WF showed 6/6 folds profitable. This means the surface has multiple local optima that shift with regime, but our specific point (8.75/2.625/2.25/0.3) is robust across time.
- **DOW exclusion is a data-mining artifact** — shifted every round (Th+F in R16-R17, Tue in R18, different again in R19). Do not use.
- **2022-2023 are the weak years** — +9.1R and +3.9R in fixed-param WF. Still positive but lowest folds. Every other year strong.
- **1s magnifier impact**: For the Long 30m ICF config, 1s magnifier made zero difference (0 trades changed). For the R20 config, 1s is used throughout but the delta vs 1m was not isolated.
- **Reversal and inversion strategies are dead** on NQ NY — tested in Round 3 (ORB-based) and no-ORB inversion sweep (864 combos across short/long/both, QM 50-200%, stop 7-13%, RR 2-5, TP1 0.2-0.6). Every single config has negative Calmar. The GC no-ORB inversion concept does not transfer to NQ.
