# NQ NY Wide-EQHL Branches Downstream Compare

- Objective: compare the current additive `5m lag24 + 15m EQHL tol1` operating lead against the promoted wide-tolerance standalone EQHL challengers on the downstream phase-one and phase-two path.
- Holdout: `2025-04-01` to `2026-03-24`.
- Phase one model: standard 50k funded-account first-payout framework.
- Phase two model: `$52k` start, fixed `$50k` breach, weekly withdrawals above `$52.5k`.

## Winner Snapshot

- Highest stitched-OOS funded EV: `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead`.
- Highest holdout funded EV: `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead`.
- Highest default post-payout stitched-OOS withdrawals: `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead`.
- Highest best-risk stitched-OOS withdrawals: `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead`.

## Scorecard

| Candidate | Family | TF | Phase 1 | Phase 2 | OOS PF | OOS Avg R | Holdout PF | Holdout Avg R | OOS Funded EV | Holdout Funded EV | OOS Withdraw/Start @250 | Best Risk | MC Survival @250 |
| --- | --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead | htf_plus_eqhl_15m_tol1 | 5m | STRONG | CONDITIONAL | 1.516 | 0.216 | 2.089 | 0.398 | $218.54 | $151.51 | $5761.29 | $200 | 33.4% |
| NQ NY EQHL_LSI 5m eqhl5m tol5p lead | eqhl_5m_to_5m_5pt | 5m | STRONG | CONDITIONAL | 1.372 | 0.169 | 1.287 | 0.157 | $123.40 | $73.09 | $5619.70 | $125 | 12.5% |
| NQ NY EQHL_LSI 1m eqhl60m tol15p lead | eqhl_1m_to_60m_15pt | 1m | CONDITIONAL | CONDITIONAL | 1.350 | 0.164 | 1.175 | 0.081 | $140.43 | $-58.17 | $3783.57 | $125 | 7.0% |
| NQ NY EQHL_LSI 3m eqhl15m tol15p lead | eqhl_3m_to_15m_15pt | 3m | CONDITIONAL | CONDITIONAL | 1.225 | 0.110 | 1.585 | 0.199 | $18.18 | $144.82 | $4888.37 | $100 | 1.5% |

## Delta Vs Additive Anchor

- Anchor: `NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead`.

| Candidate | OOS Funded EV Delta | Holdout Funded EV Delta | Default OOS Withdraw Delta | Best-Risk OOS Withdraw Delta |
| --- | ---: | ---: | ---: | ---: |
| NQ NY EQHL_LSI 5m eqhl5m tol5p lead | $-95.14 | $-78.42 | $-141.59 | $-3471.18 |
| NQ NY EQHL_LSI 1m eqhl60m tol15p lead | $-78.11 | $-209.68 | $-1977.72 | $-4917.27 |
| NQ NY EQHL_LSI 3m eqhl15m tol15p lead | $-200.36 | $-6.69 | $-872.92 | $-4598.86 |

## Best-Risk Rows

| Candidate | Best Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 additive lead | $200 | $8359.00 | 0.1% | $1280.63 | 0.0% | 65.1% |
| NQ NY EQHL_LSI 5m eqhl5m tol5p lead | $125 | $4887.82 | 0.0% | $471.66 | 0.0% | 67.6% |
| NQ NY EQHL_LSI 1m eqhl60m tol15p lead | $125 | $3441.73 | 0.0% | $85.40 | 0.0% | 78.8% |
| NQ NY EQHL_LSI 3m eqhl15m tol15p lead | $100 | $3760.14 | 0.1% | $649.50 | 0.0% | 85.8% |
