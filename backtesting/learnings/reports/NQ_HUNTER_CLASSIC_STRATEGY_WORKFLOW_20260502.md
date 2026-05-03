# NQ Hunter Classic Stress-Gated Strategy Workflow (2026-05-02)

## Scope

This run applies `CURRENT_STRATEGY_WORKFLOW.md` to the stress-gated Hunter Classic baseline.

- Baseline family: NQ NY Hunter Classic ORB replication
- Fixed stress gate: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`
- Hold-out freeze: `2025-01-01+`
- Search space: 450 variants
- Swept knobs: EMA15 length, EMA15 tolerance, EMA15 distance cap, re-entry policy, same-bar win re-entry
- Results packet: `backtesting/data/results/hunter_classic_stress_gate_strategy_workflow_20260502/`
- Repro script: `backtesting/scripts/run_hunter_classic_stress_gate_strategy_workflow.py`

## Workflow-Valid Pre-Holdout Ranking

These candidates are ranked without using the 2025+ holdout.

| Candidate | Trades | Net | WR | PF | DD | Score |
|---|---:|---:|---:|---:|---:|---:|
| `ema14_tol0_distnone_relegacy_samewin0` | 882 | +58.7R | 39.2% | 1.07 | -40.5R | 27.8 |
| `ema14_tol0_distnone_reloss_samewin0` | 884 | +56.2R | 39.1% | 1.07 | -40.5R | 25.2 |
| `ema14_tol0_distnone_relegacy_samewin1` | 883 | +55.7R | 39.2% | 1.07 | -40.5R | 24.7 |
| `ema14_tol2_distnone_relegacy_samewin0` | 884 | +56.2R | 39.1% | 1.07 | -41.8R | 24.1 |
| `ema20_tol2_distnone_relegacy_samewin0` | 871 | +52.3R | 39.2% | 1.07 | -38.7R | 22.7 |

## Best 10-Year Candidates

This leaderboard uses the full 10-year window, so it is retrospective rather than workflow-clean.

| Candidate | Trades | Net | WR | PF | DD | Score |
|---|---:|---:|---:|---:|---:|---:|
| `ema10_tol0_dist150_relegacy_samewin0` | 998 | +165.1R | 41.2% | 1.18 | -41.8R | 144.2 |
| `ema14_tol2_distnone_relegacy_samewin0` | 1,008 | +164.7R | 41.4% | 1.17 | -41.8R | 143.7 |
| `ema14_tol0_distnone_relegacy_samewin0` | 1,005 | +162.9R | 41.4% | 1.17 | -40.5R | 142.8 |
| `ema10_tol5_dist150_reall_samewin1` | 1,011 | +162.9R | 41.0% | 1.17 | -40.8R | 142.5 |
| `ema10_tol5_dist150_reall_samewin0` | 1,011 | +162.9R | 41.0% | 1.17 | -40.8R | 142.5 |

## Best 1-Year Candidates

This is recent-regime hindsight. It is useful for understanding the current hot profile, not for direct promotion.

| Candidate | Trades | Net | WR | PF | DD | Score |
|---|---:|---:|---:|---:|---:|---:|
| `ema10_tol0_dist150_reall_samewin0` | 96 | +107.6R | 60.4% | 2.02 | -14.2R | 117.9 |
| `ema10_tol5_dist150_reall_samewin0` | 96 | +107.6R | 60.4% | 2.02 | -14.2R | 117.9 |
| `ema10_tol2_dist150_reall_samewin0` | 96 | +107.6R | 60.4% | 2.02 | -14.2R | 117.9 |
| `ema10_tol2_dist150_reall_samewin1` | 96 | +107.6R | 60.4% | 2.02 | -14.2R | 117.9 |
| `ema10_tol0_dist150_reall_samewin1` | 96 | +107.6R | 60.4% | 2.02 | -14.2R | 117.9 |

## Key Candidate Comparison

| Candidate | Role | Pre-HO | Full 10y | 2025+ | Last 1y |
|---|---|---:|---:|---:|---:|
| `ema14_tol2_distnone_reloss_samewin0` | baseline | +53.7R / -41.8R DD | +162.2R / -41.8R DD | +108.5R / -14.2R DD | +92.8R / -14.2R DD |
| `ema14_tol0_distnone_relegacy_samewin0` | workflow/pre-HO leader | +58.7R / -40.5R DD | +162.9R / -40.5R DD | +104.2R / -14.2R DD | +88.4R / -14.2R DD |
| `ema10_tol0_dist150_relegacy_samewin0` | 10y hindsight leader | +35.8R / -41.8R DD | +165.1R / -41.8R DD | +129.3R / -14.2R DD | +104.0R / -14.2R DD |
| `ema10_tol0_dist150_reall_samewin0` | 1y hindsight leader | +30.3R / -41.8R DD | +163.2R / -41.8R DD | +132.9R / -14.2R DD | +107.6R / -14.2R DD |
| `ema14_tol2_distnone_relegacy_samewin0` | 10y/workflow-balanced | +56.2R / -41.8R DD | +164.7R / -41.8R DD | +108.5R / -14.2R DD | +92.8R / -14.2R DD |

## PSR / DSR

DSR is conservative in this packet: effective trials are set equal to raw trials (`450`) because the first completed grid run failed only at final JSON serialization before every trade-date set was serialized.

| Candidate | Window | PSR | Conservative DSR |
|---|---|---:|---:|
| `ema14_tol0_distnone_relegacy_samewin0` | pre-holdout | 0.8108 | 0.0154 |
| `ema14_tol0_distnone_relegacy_samewin0` | full 10y | 0.9819 | 0.1686 |
| `ema14_tol0_distnone_relegacy_samewin0` | last 1y | 0.9932 | 0.3128 |
| `ema10_tol0_dist150_relegacy_samewin0` | pre-holdout | 0.7073 | 0.0064 |
| `ema10_tol0_dist150_relegacy_samewin0` | full 10y | 0.9849 | 0.1863 |
| `ema10_tol0_dist150_relegacy_samewin0` | last 1y | 0.9986 | 0.5370 |
| `ema10_tol0_dist150_reall_samewin0` | pre-holdout | 0.6774 | 0.0051 |
| `ema10_tol0_dist150_reall_samewin0` | full 10y | 0.9837 | 0.1785 |
| `ema10_tol0_dist150_reall_samewin0` | last 1y | 0.9990 | 0.5746 |
| `ema14_tol2_distnone_relegacy_samewin0` | pre-holdout | 0.8001 | 0.0140 |
| `ema14_tol2_distnone_relegacy_samewin0` | full 10y | 0.9827 | 0.1734 |
| `ema14_tol2_distnone_relegacy_samewin0` | last 1y | 0.9949 | 0.3527 |

## Read

- Workflow-valid leader: `ema14_tol0_distnone_relegacy_samewin0`. It improves pre-holdout and keeps a strong full 10y profile, but gives up a few R in the last year versus the baseline.
- Best 10y hindsight candidate: `ema10_tol0_dist150_relegacy_samewin0`. It has the best full 10y score and strong 2025+, but weak pre-holdout, so it is a challenger rather than the clean workflow winner.
- Best 1y hindsight candidate: `ema10_tol0_dist150_reall_samewin0` and equivalent tolerance variants. This is the hot-regime candidate, but its pre-holdout score is weak, so do not promote it directly.
- Balanced candidate worth keeping: `ema14_tol2_distnone_relegacy_samewin0`. It is almost baseline mechanics, but with legacy one-reentry-after-loss. It ranks #2 on full 10y and has much better workflow hygiene than the EMA10/all-nonoverlap recent candidate.

## Conclusion

Shortlist for downstream validation:

1. **Workflow leader**: `ema14_tol0_distnone_relegacy_samewin0`
2. **Balanced 10y challenger**: `ema14_tol2_distnone_relegacy_samewin0`
3. **Recent hot-regime challenger only**: `ema10_tol0_dist150_reall_samewin0`

Do not treat the 1-year leader as a promotion winner. It is useful if the goal is to study what made the last year exceptional, but it is not workflow-clean.
