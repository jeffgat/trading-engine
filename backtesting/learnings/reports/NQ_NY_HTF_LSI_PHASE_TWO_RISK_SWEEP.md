# NQ NY HTF-LSI Phase Two Risk Sweep

- Objective: reduce post-payout path risk without reopening strategy discovery.
- Model: weekly withdrawals above `$52,500` back to `$52,000` after first payout.

## Summary

- Best balanced post-payout risk in this sweep: `$150.0` with OOS withdrawals/start `$4431.12`, holdout withdrawals/start `$1361.77`, OOS breach `0.0%`, holdout breach `0.0%`, and MC survival `61.7%` at `13.3R`.

## Grid

| Risk | OOS Withdraw | OOS Breach | Holdout Withdraw | Holdout Breach | MC Survival | MC DD p95 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| $100 | $2998.40 | 0.0% | $919.41 | 0.0% | 94.2% | 7.71R |
| $125 | $3692.60 | 0.0% | $1276.43 | 0.0% | 80.3% | 7.71R |
| $150 | $4431.12 | 0.0% | $1361.77 | 0.0% | 61.7% | 7.71R |
| $175 | $5667.26 | 0.1% | $1565.16 | 0.0% | 42.6% | 7.71R |
| $200 | $6196.61 | 4.5% | $1818.76 | 0.0% | 25.8% | 7.71R |
| $225 | $4712.70 | 34.6% | $2392.58 | 0.0% | 15.2% | 7.71R |
| $250 | $4140.27 | 48.2% | $2689.18 | 0.0% | 6.8% | 7.71R |