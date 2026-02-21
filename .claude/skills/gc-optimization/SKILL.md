# GC Optimization Protocol

Use this skill when re-optimizing GC continuation longs from scratch — fresh data, new data period, or regime shift. It documents the GC-specific process on top of the generic skills.

**Related skills:**
- `multi-phase-backtest` — generic 4-phase optimization workflow (referenced by this skill)
- `robust-pipeline` — 5-phase validation once the anchor stabilizes

---

## Phase 0: Data Validation (before anything)

GC has critical data requirements. Fail here = invalid results across all rounds.

```bash
# Check 5m bars (expect ~780K for 2016-2026)
python -c "
import pandas as pd
df = pd.read_csv('data/raw/GC_5m.csv', nrows=5)
print(df.head())
"

# Check bar counts across all three files
cd python
uv run python -c "
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
df = load_5m_data('GC_5m.csv')
m = load_1m_for_5m('GC_5m.csv')
s = load_1s_for_5m('GC_5m.csv')
print(f'5m: {len(df):,} bars  ({len(df)/252/78:.1f} bars/day avg)')
print(f'1m: {len(m):,} bars')
print(f'1s: {len(s):,} bars  ({len(s)/252/23400:.2f} expected ratio vs 5m)')
"
```

**Expected values (2016-2026, ~10 years):**
- 5m: ~777K bars, ~78 bars/trading day
- 1m: ~3.9M bars
- 1s: ~84M bars

**Critical checks:**
- [ ] 1s data downloaded with `--contract-type front_month` (NOT all contracts)
- [ ] GC uses `.v.0` volume roll — NOT `.c.0` calendar roll
- [ ] ~78 bars/day on 5m (sparse bars = bad data)
- [ ] If 1s/5m ratio is under 200:1 the 1s file is suspect
- [ ] Confirm the 1s parquet exists: `data/cache/GC_1s_*.parquet`

---

## GC-Specific Constraints (hardcoded for all rounds)

These never change — do not sweep them:

| Constraint | Value | Reason |
|------------|-------|--------|
| Sessions | NY only | Asia/LDN have ~1 bar/hour — too thin for FVG |
| Direction | long only | Continuation shorts are structurally broken (tested: -98R over 10 years) |
| Strategy | continuation | Reversals/inversions have no edge on complete data |
| Magnifier | 1s required | GC stop is 3-5% ATR (~$12-15/bar at 1m) — 1m bars can span entry+stop simultaneously |
| Data roll | `.v.0` | Volume roll only — calendar roll tracks illiquid near-expiry contracts |

---

## Phase 1: Structural Baseline (first run only)

Start with conservative defaults to establish the initial anchor:

```python
# Initial anchor config for Round 1 variable sweeps
GC_NY = SessionConfig(
    orb_start="09:30", orb_end="09:35",   # 5m ORB (default)
    entry_start="09:35", entry_end="12:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=2.5,
    max_gap_points=25.0,
)

BASE = StrategyConfig(
    rr=4.0, tp1_ratio=0.5,
    atr_length=50,                          # default (will improve dramatically)
    sessions=(GC_NY,),
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
)
```

Minimum bar count for Phase 1 to be meaningful: **400+ filled trades over full history**.

---

## Phase 2: Variable Sweeps (iterative)

Run all dimensions in parallel, hold all others at anchor. Sweep script convention:
`python/scripts/run_gc_cont_long_variable_sweeps_{N}.py`

### Dimensions to sweep every round

| Variable | Values to test | GC notes |
|----------|---------------|----------|
| ORB window | 5m, 8m, 10m, 15m, 20m | 10m structural winner confirmed across multiple rounds |
| ATR length | 5, 8, 10, 12, 14, 16, 18, 20, 25, 30 | Dominant lever — short ATR (10-18) vs default 50 is 3-6 Calmar Δ |
| entry_end | 10:00, 10:30, 11:00, 11:30, 12:00 | 11:00 is a hard cliff — post-11:00 entries are low quality |
| flat_start | 13:00, 14:00, 14:30, 15:00, 15:30, 15:50 | Completely insensitive — GC entries finish by 11:00 |
| direction | long, both, short | Always long-only — shorts add 5+ neg years |
| DOW exclusion | excl Mon, Tue, Wed, Thu, Fri, Mon+Fri, Thu+Fri | See FOMC diagnostic note below |
| max_gap_points | 15, 20, 25, 30, none | Insensitive — natural ATR filter already limits gaps |
| max_gap_atr_pct | off, 15%, 20%, 25%, 30% | Marginal; usually anchor is best |

### Adoption rule

> **Adopt if Calmar Δ > +0.3 AND no new negative years**

If adopted: increment N, update anchor, **re-run all dimensions** (sensitivity changes with anchor).

### Convergence rule

> **Move to FOMC diagnostic when 2 consecutive rounds show no change (all Δ < 0.3)**

### DOW exclusion handling

**Do NOT hardcode DOW exclusions** — they shift every round and are data-mining artifacts. Instead:
- If any DOW exclusion shows Calmar Δ > +1.0, run the **FOMC diagnostic** (Phase 2.5)
- DOW effects on GC are almost always driven by FOMC announcement days, not the day-of-week itself

---

## Phase 2.5: FOMC Diagnostic (when DOW signal appears)

If Wednesday (or any day) shows strong DOW effect, decompose:

```python
# Pattern from run_gc_fomc_vs_wed.py
# Run the anchor once, then filter post-hoc:
fomc_wed_set = frozenset(d for d in FOMC_SET if d in wed_dates)
non_fomc_wed_set = frozenset(d for d in wed_dates if d not in FOMC_SET)

# Compare:
# excl_fomc_only       → adopt if FOMC fill avg R is negative
# excl_all_wed         → skip if non-FOMC Wed trades are profitable
# excl_fomc_wed_only   → explains how much the FOMC-Wednesday cluster drives the effect
```

**Decision rule:**
- If **FOMC fill avg R < 0** → adopt FOMC exclusion (mechanically sound; Fed creates gold whipsaw)
- If non-FOMC Wednesdays avg R > 0 → DOW effect is data-mining; skip Wednesday exclusion
- Use `from orb_backtest.data.news_dates import FOMC_DATES` for the canonical date list

After adopting FOMC exclusion, run one more full variable sweep to confirm anchor stability.

---

## Phase 3: Grid Sweep

Once anchor stabilizes, sweep all continuous params together:

```python
STOPS    = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
RRS      = [3.0, 3.5, 4.0, 4.5, 5.0]
MIN_GAPS = [1.5, 2.0, 2.5, 3.0, 3.5]
TP1S     = [0.3, 0.4, 0.5]
# Total: 6×5×5×3 = 450 combos
```

Script: `run_gc_cont_long_grid_r{N}.py` (N = round number)

**Success signal**: If the anchor appears in the top 3 grid combos, the variable sweeps converged correctly.
**Failure signal**: If a completely different config wins the grid, the variable sweeps had a bug or anchor drift — go back to sweeps.

---

## Phase 4: Robust Pipeline

Use `run_gc_cont_long_r{N}_pipeline.py`. See `robust-pipeline` skill for the generic phases.

**GC-specific pipeline settings:**

| Setting | Value | Reason |
|---------|-------|--------|
| WF: IS/OOS/step | 36m / 12m / 12m | Gives 5 folds over 9 years; enough for stability |
| WF workers | 1 | 1s IPC overhead — single worker is faster than multiprocessing |
| Min WF efficiency | 0.30 | 0.40 is too strict for 5-fold WF (single flat year = 20% weight) |
| WF objective | calmar | Primary metric |
| MC ruin threshold | -25R | Standalone prop sizing constraint |
| Hold-out start | 2025-01-01 | Keep 2025+ completely unseen through all optimization |
| ATR warmup | Load from 2024-11-01 | 16-bar ATR needs ~2 months of lookback |

**2021 is structurally flat for GC continuation longs** — WF fold covering 2021 OOS will always show low Calmar (~0.2-0.3). This is a property of gold in 2021, not a strategy failure. Do not penalize WF efficiency for a single anomalous year.

**WF mode params typically differ from grid anchor** — The WF may select stop=3.5% rather than the grid's 4.0%. The mode params are the trading config; the grid anchor is the starting point. Both are valid; mode params are adaptive.

---

## Decision Thresholds for GC

| Check | GO | CAUTION | NO-GO |
|-------|-----|---------|-------|
| WF efficiency | > 0.40 | 0.30 - 0.40 | < 0.30 |
| OOS Calmar | > 3.0 | 1.0 - 3.0 | < 1.0 |
| OOS annual R | > 12R/yr | 8-12R/yr | < 8R/yr |
| OOS neg years | 0 | 1 | 2+ |
| MC survival (-25R) | > 80% | 60-80% | < 60% |
| Param stability | > 0.7 | 0.4-0.7 | < 0.4 |

A CAUTION result is still tradeable — reduce position size so dollar DD fits account ceiling.

---

## Quick Reference: Known GC Parameter Sensitivity

| Parameter | Optimal range | Notes |
|-----------|--------------|-------|
| ATR length | **10-18** | Short ATR is the dominant lever; long ATR (50) costs 3-5 Calmar |
| stop_atr_pct | **3.5-4.5%** | WF tends to select 3.5%, grid peak is 4.0% |
| rr | **4.0-5.0** | 4.5 consistently optimal |
| min_gap_atr_pct | **2.0-3.0%** | 2.5% consistently optimal; larger gaps = fewer but better trades |
| tp1_ratio | **0.5** | Lock 50% at TP1; runner targets full rr |
| ORB window | **10m** | 5m ORB is noisier; 15m+ degrades trade count |
| entry_end | **11:00** | Hard cliff — post-11:00 entries are low quality |
| flat_start | Any | Completely insensitive; GC entries all finish before noon |

---

## Sweep-History Reference

See `references/sweep-history.md` for the full anchor evolution log across all optimization rounds (data contamination note: prior rounds used contaminated 1s data — methodology valid, performance numbers directional only).
