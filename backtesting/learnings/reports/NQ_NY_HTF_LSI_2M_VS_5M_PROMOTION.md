# NQ NY HTF-LSI 2m vs 5m Promotion

- Objective: compare the current `5m lag24` operating lead against the promoted `2m` secondary anchor on the same downstream path.
- Holdout: `2025-04-01` to `2026-03-24`.
- Phase one model: standard 50k funded-account first-payout framework.
- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.

## Summary

- Lead `NQ NY HTF_LSI 5m lag24 lead`: phase one `STRONG`, phase two `CONDITIONAL`.
- Challenger `NQ NY HTF_LSI 2m anchor secondary branch`: phase one `STRONG`, phase two `CONDITIONAL`.

## Key Metrics

| Candidate | TF | Lag | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 lead | 5m | 24 | 1.347 | 0.162 | 2.200 | 0.430 | $138.33 | $81.47 | $4568.60 | $2815.14 | 9.8% | $175 |
| NQ NY HTF_LSI 2m anchor secondary branch | 2m | 0 | 1.212 | 0.104 | 1.040 | 0.004 | $53.48 | $89.36 | $2962.98 | $870.93 | 0.2% | $125 |

## Risk Sweep

| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 lead | $175 | $6037.24 | 0.0% | $1653.33 | 0.0% | 54.6% |
| NQ NY HTF_LSI 2m anchor secondary branch | $125 | $3592.51 | 0.0% | $400.37 | 0.0% | 60.3% |