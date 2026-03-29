---
name: regime-spec-pipeline
description: >
  Regime-specific validation and optimization pipeline for strategies intended to trade only in a
  named regime such as bull, bear, sideways, high-vol, or trend days. Use when the user wants to
  optimize or validate a regime specialist, build a bull-market or bear-market strategy, test
  performance only inside a target regime, or separate conditional edge from all-weather robustness.
  Focuses on causal regime labeling, same-regime out-of-sample validation, full-calendar gate
  verification, and Bailey-style overfitting discipline within regime subsets.
---

# Regime-Specific Pipeline

Regime-specific pipeline that answers: **"Does this strategy have real edge in the target regime, and can the regime gate be trusted live?"**

## When to Use

- Building a bull-only, bear-only, sideways-only, or high-vol specialist
- Re-optimizing a strategy after deciding it should only trade in one environment
- Validating a regime gate plus strategy pair as a combined live system
- Testing whether a strategy should be turned off outside its target regime

## Do NOT Use When

- The user wants one all-weather strategy across all environments
- The task is a generic robustness validation without regime routing
- The regime label is purely hindsight and cannot be known point-in-time

## Required Posture

- Regime labels must be causal and point-in-time. No hindsight tagging from future data.
- Optimize the strategy only inside the target regime.
- Validate the full gated system across all dates, because live trading includes non-target regimes too.
- Same-regime OOS is the correct conditional test. A bull specialist does not need to survive bear markets.
- Bailey still applies. Multiple regime definitions, filters, gates, and parameter sweeps all count as multiple testing.

## Key Files

| Module | Path | Purpose |
|--------|------|---------|
| Regime specialist helpers | `backtesting/src/orb_backtest/analysis/prop_regime_specialist.py` | Point-in-time regime calendar and specialist evaluation |
| Regime reports | `backtesting/src/orb_backtest/analysis/regime_reports.py` | HMM/LSTM-style regime diagnostics on saved backtests |
| Session regime signals | `backtesting/src/orb_backtest/signals/structure_15m.py` | Prior-session bull/bear regime arrays with no lookahead |
| Walk-forward engine | `backtesting/src/orb_backtest/optimize/walkforward.py` | Rolling IS/OOS optimization |
| Stability analysis | `backtesting/src/orb_backtest/optimize/stability.py` | Parameter stability across folds |
| Hold-out hygiene | `backtesting/src/orb_backtest/analysis/holdout_log.py` | Detect repeated hold-out use |

## Pipeline Summary

| # | Phase | Purpose | Pass Focus |
|---|-------|---------|------------|
| 0 | Regime Definition Audit | Verify the regime label is causal and stable enough to use | No lookahead, enough samples, clear rules |
| 1 | In-Regime Structural Check | Sanity check the candidate on pre-holdout target-regime data | Enough trades, basic viability |
| 2 | Same-Regime Walk-Forward | Optimize on earlier regime episodes, test on unseen later episodes of that regime | Conditional OOS edge, stability |
| 3 | Full-Calendar Gate Test | Run the gated system across all dates | Good in target regime, controlled outside |
| 4 | Final Same-Regime Hold-Out | One untouched final test on a later target-regime slice | Conditional hold-out confirmation |
| 5 | Monte Carlo + Specialist Diagnostics | Stress target-regime OOS trade distribution and specialization ratio | Survive path risk, stay regime-specific |

See `references/phases.md` for the workflow.
See `references/regime-rules.md` for regime-label and Bailey rules.

## Decision Framework

| Outcome | Criteria | Action |
|---------|----------|--------|
| **GO** | Same-regime WF passes, gated system behaves correctly, hold-out is clean, and specialist diagnostics support deployment | Deploy as a regime specialist |
| **CONDITIONAL** | Target-regime edge looks good but hold-out is thin, diagnostics are incomplete, or outside-regime behavior is only acceptable with tight gating | Trade reduced size or finish diagnostics |
| **NO-GO** | Regime label leaks, same-regime OOS fails, hold-out is contaminated, or the strategy is not meaningfully better in-target than out-of-target | Do not deploy as a specialist |
