# NQ NY Optimization Protocol

Use this skill when re-optimizing NQ NY continuation from scratch — fresh data, new data period, or regime shift. Documents the NQ-specific process on top of the generic skills.

**Related skills:**
- `multi-phase-backtest` — generic 4-phase optimization workflow (referenced by this skill)
- `robust-pipeline` — 5-phase validation once the anchor stabilizes

---

## Phase 0: Data Validation (before anything)

NQ requires three data files. Fail here = invalid results across all rounds.

```bash
# Check bar counts across all three files
cd python
uv run python -c "
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
df = load_5m_data('NQ_5m.csv')
m = load_1m_for_5m('NQ_5m.csv')
s = load_1s_for_5m('NQ_5m.csv')
print(f'5m: {len(df):,} bars  ({len(df)/252/78:.1f} bars/day avg)')
print(f'1m: {len(m):,} bars')
print(f'1s: {len(s):,} bars  ({len(s)/252/23400:.2f} expected ratio vs 5m)')
"
```

**Expected values (2015-2026, ~11 years):**
- 5m: ~860K bars, ~78 bars/trading day
- 1m: ~4.3M bars
- 1s: ~90M+ bars

**Critical checks:**
- [ ] NQ uses `.c.0` **calendar roll** — NOT `.v.0` volume roll (NQ is an index future)
- [ ] `NQ_5m.csv`, `NQ_1m.csv`, and `NQ_1s.parquet` all present
- [ ] ~78 bars/day on 5m (sparse bars = bad data)
- [ ] If 1s/5m ratio is under 200:1 the 1s file is suspect
- [ ] Confirm the 1s parquet exists: `data/cache/NQ_1s_*.parquet`

---

## NQ-Specific Constraints (hardcoded for all rounds)

These never change — do not sweep them:

| Constraint | Value | Reason |
|------------|-------|--------|
| Sessions | NY only | Asia session tested; no structural edge found |
| Strategy | continuation | Reversal/inversion untested at scale for NQ NY |
| Magnifier | 1s required | NQ bars can span entry+stop — 1s precision essential for accurate fill/stop simulation |
| Data roll | `.c.0` | Calendar roll for index futures — standard for NQ/ES/YM |
| Direction | **DO NOT hardcode** | Sweep every round — NQ shorts have shown regime-dependent value |

**Direction note**: Unlike GC (always long), NQ direction is not assumed. Long-only has historically dominated the full 2015-2026 period, but 2022 is a bear year where shorts contribute. Always sweep direction and test the long-only vs both vs short-only split before deciding.

---

## Phase 1: Structural Baseline (first run only)

Start with conservative defaults to establish the initial anchor:

```python
# Initial anchor config for Round 1 variable sweeps
NQ_NY = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:45",   # 15m ORB (default)
    entry_start="09:45", entry_end="13:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=10.0,
    min_gap_atr_pct=1.5,
    max_gap_points=100.0,
)

BASE = StrategyConfig(
    rr=2.0, tp1_ratio=0.5,
    atr_length=14,
    sessions=(NQ_NY,),
    instrument=NQ,
    strategy="continuation",
    direction_filter="both",   # Start with both; sweep will determine optimal
    use_bar_magnifier=True,
)
```

Minimum bar count for Phase 1 to be meaningful: **500+ filled trades over full history**.

---

## Phase 2: Variable Sweeps (iterative)

Run all dimensions in parallel, hold all others at anchor. Sweep script convention:
`python/scripts/run_nq_ny_variable_sweeps_{N}.py`

### Dimensions to sweep every round

| Variable | Values to test | NQ notes |
|----------|---------------|----------|
| Direction | long, both, short | **Never skip** — NQ direction is not predetermined; 2022 regime shifts the answer |
| ORB window | 5m, 10m, 15m, 20m, 25m, 30m | 20m (09:30-09:50) is the structural winner; re-confirm after any anchor change |
| ATR length | 7, 10, 12, 14, 16, 18, 20, 25 | ATR 14 optimal; NQ is less sensitive here than GC |
| entry_end | 12:00, 13:00, 14:00, 15:00, 15:30 | 15:00 has dominated; late entries remain productive on NQ |
| flat_start | 14:30, 15:00, 15:30, 15:50 | Insensitive — confirm annually |
| min_gap_atr_pct | 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0 | 3.0% is the structural winner; larger gaps = higher quality |
| stop_atr_pct | 6, 7, 8, 9, 10, 11, 12, 14 | **Critical lever** — 9% won decisively, but reshuffled rr/tp1 surface (see R9-R11 rule) |
| rr | 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5 | 2.25 optimal at stop=9%; shifts with stop |
| tp1_ratio | 0.3, 0.4, 0.5, 0.6, 0.7, 0.8 | 0.7 optimal at rr=2.25, stop=9%; interaction with rr is strong |
| DOW exclusion | none, excl Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri | Test but treat with skepticism; shifts each round |
| max_gap_points | 50, 75, 100, 150, none | Insensitive; natural ATR filter already limits gaps |

### Adoption rule

> **Adopt if Calmar Δ > +0.3 AND no new negative years**

If adopted: increment N, update anchor, **re-run all dimensions** (sensitivity changes with anchor).

### Convergence rule

> **Move to environmental filter phase when 2 consecutive rounds show no change (all Δ < 0.3)**

### DOW exclusion handling

**Do NOT hardcode DOW exclusions** — they shift every round and are data-mining artifacts on NQ. Unlike GC (where FOMC has a mechanistic explanation), NQ DOW exclusions have shown inconsistent patterns across rounds. If any DOW exclusion shows Calmar Δ > +1.0, run a decomposition to check if it's driven by a specific macro event cluster (Fed meetings, earnings seasons) before adopting.

---

## CRITICAL: The R9-R11 Rule (Stop Change = Full Grid Re-run)

> **After ANY stop change, the entire gap × rr × tp1 parameter surface must be re-run.**

This was discovered empirically in rounds 9-11 of the prior optimization:

- **R7**: Grid winner at stop=10% was `g=3.5, rr=2.50, tp1=0.4` (Calmar ~15)
- **R9**: Fine stop sweep discovered stop=9% dramatically improves `rr=2.75` configs but NOT `rr=2.0/2.5` — stop and rr/tp1 interact
- **R10**: Ultra-fine stop sweep confirmed stop=9.0% as optimum for the target config
- **R11**: Re-ran the 90-combo gap×rr×tp1 grid at stop=9%. **Winner was completely different**: `g=3.0, rr=2.25, tp1=0.7` (Calmar 17.17)

If R11 had been skipped, the optimization would have been trading a suboptimal config at a correct stop. The stop change reshuffled the best rr/tp1 combination entirely.

**The rule**: Whenever a stop sweep produces a new optimal stop value, treat it as an anchor change and re-run the full 3-way grid (gap × rr × tp1) before proceeding.

---

## Phase 2.5: Environmental Filter Testing

Once the structural anchor stabilizes (2+ rounds with Δ < 0.3 on all non-env dimensions), test environmental regime filters. **Do not skip this phase** — unlike GC where env filters were mostly rejected, NQ has shown some sensitivity (particularly to VIX and SPY trend).

### Files needed for env filter testing

| File | Notes |
|------|-------|
| `data/raw/VIX_daily.csv` | CBOE VIX — key for NQ vol regime |
| `data/raw/SPY_daily.csv` | Equity benchmark — risk-on/off |
| `data/raw/TNX_daily.csv` | 10Y yield — rising rates bearish for tech |
| `data/raw/DXY_daily.csv` | Dollar index — secondary signal |

### Filters to test (using prior-day close — no look-ahead)

1. **VIX level** — buckets (<15, 15-20, 20-25, 25-30, >30) + SMA20/50 trend
2. **SPY trend** — price vs SMA20/50/200 (risk-on vs risk-off)
3. **TNX trend** — rising/falling rates (tech-bearish when rising)
4. **DXY trend** — dollar strength (secondary signal)
5. **NQ own SMA trend gate** — long only when NQ > SMA50 (built-in `apply_sma_trend_gate`)
6. **ATR volatility gate** — skip days when NQ ATR > 1.25× rolling average
7. **Month-of-year seasonality** — monthly R breakdown, Q1-Q4 groupings
8. **Cross-env combos** — VIX<20 + SPY>SMA50, VIX>SMA50 + SPY<SMA50, etc.

### Decision rule for adopting env filters

> **Adopt if: Calmar Δ > +0.3 AND filter activates in 5+ distinct years AND trades removed < 30%**

If a filter only activates in 1-2 years (e.g., SPY < SMA200 = only 2022), it is curve-fitting the bear year. Reject.

If a filter cuts > 30% of trades but improves Calmar, use it only for **regime sizing** (reduce position size in bad-filter regime), not as a hard on/off gate.

**Prior results (1m magnifier era, for context only — re-run on new data):**
- NQ SMA trend gate (SMA50) showed modest improvement but was below threshold
- VIX > 20 excluded ~25% of trades; longs still profitable in high-VIX periods
- Monthly seasonality: no month was strongly negative across all years
- SPY < SMA200 (pure bear) improved Calmar but only activates in 2022 — rejected as curve-fit

---

## Phase 3: Grid Sweep

Once structural vars and direction are stable, sweep all continuous params together:

```python
STOPS    = [7.5, 8.0, 8.5, 9.0, 9.5, 10.0, 11.0]
RRS      = [1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5]
MIN_GAPS = [2.0, 2.5, 3.0, 3.5, 4.0]
TP1S     = [0.4, 0.5, 0.6, 0.7, 0.8]
# Total: 7×7×5×5 = 1225 combos — run with workers=8
```

Script: `run_nq_ny_variable_sweeps_{N}.py` or a dedicated grid script.

**Success signal**: If the anchor appears in the top 3 grid combos, variable sweeps converged correctly.
**Failure signal**: If a completely different stop appears in the grid winner, re-apply the R9-R11 rule — run the grid again at the new stop before updating anchor.

---

## Phase 4: Robust Pipeline

Use `run_nq_ny_robust_pipeline.py`. See `robust-pipeline` skill for the generic phases.

**NQ-specific pipeline settings:**

| Setting | Value | Reason |
|---------|-------|--------|
| WF: IS/OOS/step | 36m / 12m / 12m | Gives 5-6 folds over 11 years |
| WF workers | 8 | NQ 5m data is fast; multiprocessing helps |
| Min WF efficiency | 0.30 | 2022-2023 historically weak for NQ continuation; expect some flat OOS folds |
| WF objective | calmar | Primary metric |
| MC ruin threshold | -25R | Standalone prop sizing constraint |
| Hold-out start | 2025-01-01 | Keep 2025+ completely unseen through all optimization |
| ATR warmup | Load from 2014-11-01 | 14-bar ATR needs ~2 months of lookback |
| WF param ranges | stop × rr × tp1 × gap | Keep range tight around known good region |

**2022-2023 regime note**: NQ continuation longs historically underperform in bear markets (2022) and choppy recoveries (2023). WF folds covering these years as OOS will show lower efficiency. This is a regime property, not a strategy failure. Do not penalize WF efficiency for these years if the overall OOS Calmar is still positive.

**WF mode params may differ from grid anchor** — The WF may select stop=8.5% or 9.5% rather than the grid's 9.0%. The mode params are the trading config; the grid anchor is the starting point. Both are valid.

---

## Decision Thresholds for NQ NY

| Check | GO | CAUTION | NO-GO |
|-------|-----|---------|-------|
| WF efficiency | > 0.45 | 0.30 - 0.45 | < 0.30 |
| OOS Calmar | > 5.0 | 2.0 - 5.0 | < 2.0 |
| OOS annual R | > 12R/yr | 6-12R/yr | < 6R/yr |
| OOS neg years | 0 | 1 | 2+ |
| MC survival (-25R) | > 80% | 60-80% | < 60% |
| Param stability | > 0.7 | 0.4-0.7 | < 0.4 |

A CAUTION result is still tradeable — reduce position size so dollar DD fits account ceiling.

---

## Quick Reference: Known NQ NY Parameter Sensitivity

These are prior optimal ranges from the 1m magnifier era. Use as starting points only — new 1s magnifier results may shift values.

| Parameter | Prior optimal range | Notes |
|-----------|-------------------|-------|
| stop_atr_pct | **9.0%** | Fine-grained sweet spot; 9% wins over 10% after proper R9-R11 re-grid |
| rr | **2.0-2.25** | Lower than GC; NQ retraces and requires fewer runner bars to hit target |
| min_gap_atr_pct | **3.0%** | 3% structural winner; filters noise FVGs |
| tp1_ratio | **0.7** | Locks in 70% at TP1; high value because NQ runners often get stopped at BE |
| ORB window | **20m** (09:30-09:50) | 15m default is noisier; 20m cuts DD |
| ATR length | **14** | Matches standard daily ATR; NQ less sensitive than GC |
| entry_end | **15:00** | NQ can fill late in session — unlike GC, no hard cliff at 11:00 |
| flat_start | **15:50** | Completely insensitive |
| direction | **long-only** (prior) | Long dominated full history; re-test every round — may change on new data |

---

## Sweep-History Reference

See `references/sweep-history.md` for the full 15-round anchor evolution log (note: all numbers from 1m magnifier era — new 1s magnifier results may differ in magnitude).
