# NQ NY LSI 3m Trapped-Reversal Exact Probe

- Date: 2026-05-17
- Scope: no-fetch exact-engine probe using a temporary execution profile.
- Candidate: `add_3m_hourly_atr12p5_b3_a7p5`
- Feature: `trapped_reversal_confirm_score`
- DataBento fetches: `0`
- Parity status: `blocked`

## Probe Read

- Research holdout trades expected: `46`
- Exact trades produced: `52`
- Date match: `False`
- Missing dates: `9`
- Extra dates: `15`
- Fallback decisions: `17`
- Tier counts: `{'fallback': 17, 'high': 18, 'low': 11, 'mid': 6}`

## Exact Metrics

- Exact baseline R: `5.073R`
- Exact baseline avg: `0.098R`
- Exact baseline PF: `1.22`
- Exact baseline max DD: `-5.000R`
- Shadow weighted R: `9.355R`
- Shadow weighted avg: `0.180R`
- Shadow weighted PF: `1.39`
- Shadow weighted max DD: `-6.242R`
- Shadow delta: `+4.282R`

## Interpretation

This is a probe, not a promotion packet. A `blocked` result means the execution profile can run 3m bars, but the signal stream is not yet exact-parity with the research candidate or the scored feature rows. That would make exact 3m parity the next engineering task before live shadowing.

## Output Files

- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_3m_trapped_reversal_exact_shadow_probe_20260517/temp_exec_configs.json`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_3m_trapped_reversal_exact_shadow_probe_20260517/exact_shadow_trades.csv`
- `/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_lsi_3m_trapped_reversal_exact_shadow_probe_20260517/summary.json`
