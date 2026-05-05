# ALPHA_V1 Constrained Top Exact Replay

- Run slug: `alpha_v1_constrained_top_exact_replay_20260504`
- Base profile: `ALPHA_V1-A` cloned in memory; `execution/config/exec_configs.json` was not edited.
- Window: `2016-04-17` to `2026-03-24`.
- Purpose: exact replay the top constrained active-ALPHA target profile from the broad research sweep.

## Target Overrides

```json
{
  "lsi_sessions": {
    "NQ_NY_LSI": {
      "rr": 3.0,
      "tp1_ratio": 0.5
    }
  },
  "sessions": {
    "ES_Asia": {
      "rr": 1.5,
      "tp1_ratio": 0.8333333333333334
    },
    "ES_NY": {
      "rr": 2.5,
      "tp1_ratio": 0.5
    },
    "NQ_Asia": {
      "rr": 3.0,
      "tp1_ratio": 0.5
    }
  }
}
```

## Exact Metrics

| Scope | Window | Trades | Net R | WR | PF | DD | Sharpe | Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| combined | last_1y | 269 | 71.08 | 53.53% | 1.648 | -12.55 | 3.419 | 5.664 |
| ES_Asia | last_1y | 118 | 19.50 | 51.69% | 1.355 | -5.05 | 2.357 | 3.860 |
| ES_NY | last_1y | 57 | 11.75 | 52.63% | 1.526 | -4.50 | 2.636 | 2.611 |
| NQ_Asia | last_1y | 66 | 23.25 | 51.52% | 1.740 | -6.00 | 4.063 | 3.875 |
| NQ_NY_LSI | last_1y | 28 | 16.59 | 67.86% | 2.986 | -3.00 | 7.343 | 5.528 |
| combined | last_2y | 529 | 119.00 | 51.80% | 1.473 | -12.55 | 2.913 | 9.481 |
| ES_Asia | last_2y | 226 | 42.88 | 53.10% | 1.427 | -6.00 | 2.684 | 7.146 |
| ES_NY | last_2y | 116 | 10.50 | 46.55% | 1.224 | -9.88 | 1.152 | 1.063 |
| NQ_Asia | last_2y | 120 | 43.55 | 51.67% | 1.677 | -6.00 | 4.163 | 7.258 |
| NQ_NY_LSI | last_2y | 67 | 22.08 | 56.72% | 1.848 | -6.25 | 4.295 | 3.532 |
| combined | full | 2605 | 393.48 | 49.75% | 1.316 | -20.50 | 2.006 | 19.197 |
| ES_Asia | full | 1112 | 158.64 | 51.71% | 1.313 | -15.54 | 2.049 | 10.207 |
| ES_NY | full | 506 | 55.03 | 49.21% | 1.196 | -14.14 | 1.440 | 3.892 |
| NQ_Asia | full | 632 | 117.12 | 46.36% | 1.382 | -10.46 | 2.185 | 11.193 |
| NQ_NY_LSI | full | 355 | 62.69 | 50.42% | 1.428 | -10.13 | 2.377 | 6.191 |

## Read

- This exact pass validates execution-engine behavior for the active-leg constrained target shortlist only.
- It does not exact-replay the conditional research branches; those still need separate implementation/parity work before promotion.
