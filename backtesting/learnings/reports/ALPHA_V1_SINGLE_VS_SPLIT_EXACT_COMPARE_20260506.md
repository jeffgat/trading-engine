# ALPHA_V1 Exact Single vs Split Target Comparison

- Run slug: `alpha_v1_single_vs_split_exact_compare_20260506`
- Window: `2016-04-17` to `2026-03-24`
- Engine path: `execution/src/trader/historical_backtest.py`; all rows are single-leg exact live-engine replays.
- Split counterparts use the same session/stop/gap definitions as the single-target candidates, with only `exit_mode`, `rr`, and `tp1_ratio` reverted to the split structure.

## Full-Window Delta

| leg | single_target | split_target | single_trades | split_trades | single_net_r | split_net_r | delta_r | single_pf | split_pf | delta_pf | single_dd_r | split_dd_r | delta_dd_r | single_target_pct | split_full_target_pct | split_tp1_be_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB | single 1.0R | split rr 5 / tp1 0.2 | 849 | 849 | 102 | 146 | -44.2 | 1.28 | 1.40 | -0.12 | 12.2 | 12.0 | 0.22 | 55.0 | 10.1 | 37.7 |
| NQ NY ORB R11 | single 1.4R | split rr 3.5 / tp1 0.4 | 554 | 554 | 137 | 148 | -11.6 | 1.47 | 1.51 | -0.04 | 6.40 | 6.45 | -0.05 | 51.6 | 20.9 | 29.2 |
| ES Asia ORB | single 1.25R | split rr 1.5 / tp1 0.7 | 1428 | 1428 | 220 | 181 | 38.3 | 1.34 | 1.30 | 0.04 | 15.0 | 12.5 | 2.52 | 47.6 | 35.4 | 14.2 |

## All Windows

| leg | window | single_net_r | split_net_r | delta_r | single_pf | split_pf | single_dd_r | split_dd_r | single_target_pct | split_full_target_pct | split_tp1_be_pct |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ES NY ORB | full | 102 | 146 | -44.2 | 1.28 | 1.40 | 12.2 | 12.0 | 55.0 | 10.1 | 37.7 |
| ES NY ORB | last_2y | 12.0 | 37.4 | -25.4 | 1.16 | 1.46 | 10.0 | 9.00 | 53.0 | 15.3 | 36.1 |
| ES NY ORB | last_1y | 7.00 | 17.5 | -10.5 | 1.22 | 1.49 | 10.0 | 9.00 | 53.8 | 14.0 | 37.6 |
| NQ NY ORB R11 | full | 137 | 148 | -11.6 | 1.47 | 1.51 | 6.40 | 6.45 | 51.6 | 20.9 | 29.2 |
| NQ NY ORB R11 | last_2y | 18.5 | 20.4 | -1.90 | 1.33 | 1.37 | 6.40 | 6.00 | 48.2 | 19.1 | 27.3 |
| NQ NY ORB R11 | last_1y | 3.80 | 4.65 | -0.85 | 1.14 | 1.18 | 6.40 | 6.00 | 44.9 | 16.3 | 24.5 |
| ES Asia ORB | full | 220 | 181 | 38.3 | 1.34 | 1.30 | 15.0 | 12.5 | 47.6 | 35.4 | 14.2 |
| ES Asia ORB | last_2y | 49.5 | 41.4 | 8.04 | 1.38 | 1.35 | 7.10 | 7.65 | 49.8 | 36.0 | 15.9 |
| ES Asia ORB | last_1y | 23.2 | 21.8 | 1.41 | 1.35 | 1.37 | 7.10 | 5.83 | 47.9 | 35.2 | 15.5 |

## Read

- ES NY does not validate as a single-target upgrade: exact split is stronger on net R, PF, and DD, although it gets there with the same uncomfortable TP1/BE-heavy behavior.
- NQ R11 is also better as split on exact edge: single target greatly increases clean target exits, but gives up R/PF for almost no DD benefit.
- ES Asia is the only true exact single-target upgrade on R/PF, but it expands DD and lowers WR, so it is still a tradeoff rather than a free replacement.

## Result IDs

| leg | single_result_id | split_result_id |
| --- | --- | --- |
| ES NY ORB | bt-alpha-v1-exact-singletarget-es-ny-orb-single-1-0-89f860 | bt-alpha-v1-exact-split-es-ny-orb-2016-04-17-to-202-c0fca0 |
| NQ NY ORB R11 | bt-alpha-v1-exact-singletarget-nq-ny-orb-r11-single-842410 | bt-alpha-v1-exact-split-nq-ny-orb-r11-2016-04-17-to-1a7130 |
| ES Asia ORB | bt-alpha-v1-exact-singletarget-es-asia-orb-single-1-dee938 | bt-alpha-v1-exact-split-es-asia-orb-2016-04-17-to-2-bb6fb8 |
