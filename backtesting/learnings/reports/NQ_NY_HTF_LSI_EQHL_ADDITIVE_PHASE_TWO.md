# NQ NY HTF-LSI EQHL Additive Phase Two

- Objective: compare the current `5m lag24` HTF-only operating lead against the frozen additive `HTF + 15m EQHL tol1` challenger on the post-first-payout continuity path.
- Holdout: `2025-04-01` to `2026-03-24`.
- Phase one model: standard 50k funded-account first-payout framework.
- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.

## Summary

- Base `NQ NY HTF_LSI 5m lag24 operating lead`: phase one `STRONG`, phase two `CONDITIONAL`.
- Challenger `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive challenger`: phase one `STRONG`, phase two `CONDITIONAL`.

## Key Metrics

| Candidate | Source | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 operating lead | HTF-only | 1.467 | 0.199 | 2.089 | 0.398 | $208.24 | $151.51 | $5092.92 | $2012.58 | 32.2% | $200 |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive challenger | HTF+EQHL 15m tol1 | 1.516 | 0.216 | 2.089 | 0.398 | $218.54 | $151.51 | $5761.29 | $2012.58 | 33.4% | $200 |

## Risk Sweep

| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 operating lead | $200 | $7462.92 | 0.1% | $1280.63 | 0.0% | 61.1% |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive challenger | $200 | $8359.00 | 0.1% | $1280.63 | 0.0% | 65.1% |
