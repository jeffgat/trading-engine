# Discovery Pipeline — Discovery & Promotion Guide

Detailed instructions for the pre-holdout discovery pipeline. Run from `backtesting/` using `uv run`.

This guide is intentionally upstream of `phase-one-robust-pipeline`. Its job is to produce a frozen shortlist, not a final payout verdict.

---

## Phase 0: Freeze the Final Hold-Out

**Goal**: Preserve one truly untouched final OOS period for downstream payout validation.

- Reserve the most recent `12-24` months before any discovery or screening.
- Exclude this period from every step in this guide.
- Check `orb_backtest.analysis.holdout_log` before using that period later.
- If the same hold-out has already been probed repeatedly, mark it contaminated in the write-up.

This is mandatory. Bailey's warning is simple: once the final hold-out influences search decisions, it is no longer final OOS.

**Output**:
- Hold-out start/end
- Statement that all discovery work below is pre-holdout only

---

## Phase 1: Structural Family Screen

**Goal**: Reject obviously broken parameter regions before spending search budget on them.

**Data**: Longest available history excluding the reserved hold-out.

Use this phase for broad anchors and family-level sanity checks, not precise tuning.

```python
from orb_backtest.data.loader import load_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

df = load_data("NQ_5m.csv")
pre_holdout_df = df.loc[:holdout_start]

trades = run_backtest(pre_holdout_df, anchor_config, start_date="2015-01-01")
m = compute_metrics(trades)
```

**Typical reject rules**:
- `total_trades < 100`
- `profit_factor <= 1.0`
- obviously pathological DD / expectancy shape
- setup family only works in one tiny corner of the sample

**Important**:
- Do not pick the winner here.
- Use this to remove dead regions and define a search box for Phase 2.

**Output**:
- Viable anchors / viable search ranges
- Rejected regions and why they were rejected

---

## Phase 2: Discovery Search

**Goal**: Search the pre-holdout space while keeping the search process legible.

Use `strategy-optimizer` style sweeps, but with explicit promotion discipline:

- limit each round to `2-3` parameters
- start coarse, then narrow
- track how many rounds and combinations were tried
- prefer objective stacks like `Calmar + OOS plausibility`, not one magic metric

```python
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep

param_ranges = {
    "stop_atr_pct": [4.0, 5.0, 6.0, 7.0],
    "rr": [1.5, 2.0, 2.5],
    "tp1_ratio": [0.3, 0.4, 0.5],
}

configs = generate_param_grid(base_config, param_ranges)
results = run_sweep(pre_holdout_df, configs, n_workers=8, start_date="2015-01-01")
```

**Best practices**:
- keep a research log: rounds, ranges, objective, number of combos
- if one round changes the search box, record why
- avoid giant blind sweeps unless the user explicitly wants brute force

**Do not**:
- touch the final hold-out
- crown a winner purely from IS metrics
- hide the number of trials

**Output**:
- candidate pool
- search log with trial count

---

## Phase 3: Rolling Walk-Forward Ranking

**Goal**: Rank discovery candidates by combined OOS behavior rather than by in-sample maxima.

Preferred setup:
- default `12m IS / 3m OOS / 3m step`
- use larger windows only when the strategy is sparse

```python
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability

wf_result = run_walkforward(
    df=pre_holdout_df,
    base_config=base_config,
    param_ranges=param_ranges,
    is_months=12,
    oos_months=3,
    step_months=3,
    objective="sharpe",
    n_workers=8,
    start_date="2015-01-01",
)

stability = analyze_parameter_stability(wf_result, param_ranges)
```

**Rank on**:
- combined OOS metrics
- walk-forward efficiency
- number of usable folds
- degradation profile in recent folds

**Not on**:
- best single fold
- best IS point

**Heuristic thresholds**:
- `walk_forward_efficiency >= 0.3`
- `stability.overall_score >= 0.4`
- prefer `8+` folds; more is better

**Output**:
- OOS-ranked shortlist
- combined OOS summary
- per-candidate stability notes

---

## Phase 4: Local Stability / Plateau Check

**Goal**: Prefer robust neighborhoods over fragile maxima.

For each leading candidate, run a narrow local sweep around the discovered values:

- `best +/- 10-20%` for continuous parameters
- nearest neighboring discrete values for categorical choices

This phase should answer:
- does performance degrade gracefully?
- is the selected point near the center of a good region?
- is the candidate a plateau or a spike?

**Promotion preference**:
- center-of-mass / modal region over absolute best score
- stable parameter cluster over isolated winner

**Reject if**:
- the candidate collapses at neighboring values
- the “winner” exists only as a one-cell peak
- different nearby configs reverse the story completely

**Output**:
- frozen promoted params
- plateau vs spike judgment

---

## Phase 5: Promotion Packet

**Goal**: Hand off a small frozen shortlist into `phase-one-robust-pipeline`.

Produce `1-3` final candidates:
- `1` leader
- optional `1-2` challengers

Each promotion packet should include:
- full parameter set
- exact pre-holdout date range used
- search rounds / approximate trial count
- combined OOS metrics
- stability score
- plateau judgment
- Bailey caveat if `PBO/DSR/PSR/CSCV` are not implemented

Recommended language:

```text
PROMOTE: candidate A
- selected from 4 discovery rounds / ~312 evaluated configs
- ranked by combined walk-forward OOS, not IS peak
- local neighborhood shows moderate plateau behavior
- Bailey-style PBO/DSR not implemented; promotion is heuristic
```

This output is what should enter `phase-one-robust-pipeline`.

---

## Final Classification

Use these labels at the end of the discovery pipeline:

- **PROMOTE**: strong pre-holdout candidate worth phase-one payout testing
- **CHALLENGER**: viable backup candidate, but not the lead
- **REJECT**: not robust enough to carry forward

Do not use:
- final live deployment language
- final payout EV claims
- “GO to production” wording

That belongs downstream, after `phase-one-robust-pipeline`.
