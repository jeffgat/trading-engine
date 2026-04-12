# NQ NY HTF-LSI Lag24 Promotion

- Objective: compare the frozen `5m lag=0` lead against the `5m lag=24` late-lag challenger on the downstream promotion path only.
- Holdout: `2025-04-01` to `2026-03-24`.
- Phase one model: standard 50k funded-account first-payout framework.
- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.

## Summary

- Baseline `NQ NY HTF_LSI 5m lag0 baseline`: phase one `STRONG`, phase two `CONDITIONAL`.
- Challenger `NQ NY HTF_LSI 5m lag24 promotion challenger`: phase one `STRONG`, phase two `CONDITIONAL`.

## Key Metrics

| Candidate | Lag | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag0 baseline | 0 | 1.298 | 0.130 | 1.987 | 0.361 | $158.58 | $78.68 | $4140.27 | $2689.18 | 6.8% | $150 |
| NQ NY HTF_LSI 5m lag24 promotion challenger | 24 | 1.347 | 0.162 | 2.200 | 0.430 | $138.33 | $81.47 | $4568.60 | $2815.14 | 9.8% | $175 |

## Risk Sweep

| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag0 baseline | $150 | $4431.12 | 0.0% | $1361.77 | 0.0% | 61.7% |
| NQ NY HTF_LSI 5m lag24 promotion challenger | $175 | $6037.24 | 0.0% | $1653.33 | 0.0% | 54.6% |