# NQ NY EQHL-LSI Phase One

- Frozen candidate source: [5m_eqhl5m_summary.json](/Users/jeffreygatbonton/Desktop/Code/main_backtests/orb_backtests_chris/backtesting/data/results/nq_ny_eqhl_lsi_promotion_packet/5m_eqhl5m_summary.json)
- Holdout opened once for phase one: `2025-04-01` to `2026-03-24`.
- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2025-03-31`).

## Summary

- `NQ NY EQHL_LSI 5m eqhl5m tol2t touches2 long fvg_limit end13:00 L20 R3`: verdict `STRONG`, OOS prop payout `64.3%`, OOS funded payout `44.2%`, holdout prop payout `62.4%`, holdout funded payout `62.4%`

## Candidate Details

### NQ NY EQHL_LSI 5m eqhl5m tol2t touches2 long fvg_limit end13:00 L20 R3

- verdict: `STRONG`
- config: `long fvg_limit 08:30-13:00 rr3.25 tp0.6 gap3.0 atr14 eqhl5m tol2t touches2 left20 right3`
- promotion source metrics: validation PF `1.8845`, validation avgR `0.3527`, stitched OOS PF `1.248`, stitched OOS avgR `0.1237`
- discovery PSR / DSR: `not_run` / `not_run`
- pre-holdout structural metrics: trades `428.0`, PF `1.2549`, avgR `0.1249`, totalR `53.454`
- stitched OOS metrics: trades `257.0`, PF `1.248`, avgR `0.1237`, totalR `31.795`
- OOS prop scorecard: payout `64.3%`, breach `29.3%`, open `6.4%`, EV `$12788.82`, avg days `172.27`
- OOS funded scorecard: payout `44.2%`, breach `49.4%`, open `6.4%`, EV `$101.46`, avg days `92.66`
- holdout metrics: trades `28.0`, PF `1.4585`, avgR `0.2512`, totalR `7.0339`
- holdout prop scorecard: payout `62.4%`, breach `0.0%`, open `37.6%`, EV `$12433.66`, avg days `130.53`
- holdout funded scorecard: payout `62.4%`, breach `0.0%`, open `37.6%`, EV `$226.69`, avg days `130.35`
- OOS cohort EV: prop `10/25/50 = $127888.2 / $319720.5 / $639441.0`, funded `10/25/50 = $1014.6 / $2536.5 / $5073.0`
- holdout cohort EV: prop `10/25/50 = $124336.6 / $310841.5 / $621683.0`, funded `10/25/50 = $2266.9 / $5667.25 / $11334.5`
