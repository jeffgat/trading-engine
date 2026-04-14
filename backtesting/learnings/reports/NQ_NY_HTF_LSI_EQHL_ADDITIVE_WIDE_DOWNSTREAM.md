# NQ NY HTF-LSI EQHL Additive Wide Downstream

- Objective: compare the current additive incumbent `HTF + 15m EQHL tol1` against the best wide additive EQHL challenger on the downstream phase-one and phase-two path.
- Holdout: `2025-04-01` to `2026-03-24`.
- Phase one model: standard 50k funded-account first-payout framework.
- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.

## Summary

- Incumbent `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent`: phase one `STRONG`, phase two `CONDITIONAL`.
- Wide challenger `NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt`: phase one `STRONG`, phase two `CONDITIONAL`.

## Key Metrics

| Candidate | Source | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Holdout Withdraw/Start @250 | MC Survival @250 | Best Risk |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent | incumbent_tight | 1.516 | 0.216 | 2.089 | 0.398 | $218.54 | $151.51 | $5761.29 | $2012.58 | 33.4% | $200 |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt | wide_eqhl_60m_15pt | 1.471 | 0.201 | 1.630 | 0.246 | $163.24 | $83.31 | $5499.48 | $1730.44 | 14.9% | $175 |

## Risk Sweep

| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 incumbent | $200 | $8359.00 | 0.1% | $1280.63 | 0.0% | 65.1% |
| NQ NY HTF_LSI 5m lag24 + EQHL60m 15pt | $175 | $8264.97 | 0.1% | $1203.79 | 0.0% | 66.3% |
