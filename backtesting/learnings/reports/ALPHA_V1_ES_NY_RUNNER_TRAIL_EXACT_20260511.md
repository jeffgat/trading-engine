# ALPHA_V1 ES_NY Runner-Trail Exact Replay (2026-05-11)

- Replay: exact/live execution engine, `2016-04-17` through `2026-03-24`.
- Scope: ES_NY only, ALPHA_V1-A base profile, 1s execution replay where active.
- Candidates promoted from the simulator sweep: `risk_gap_0p75r` and `atr_gap_5pct`.

## Verdict

Baseline remains the production incumbent; the runner trails need more evidence before replacing it.

## Metrics

| candidate      | window        |   trades |   total_r |   profit_factor |   max_dd_r |   calmar |   win_rate_pct |   positive_runner_stops |   tp1_be |   tp1_tp2 |
|:---------------|:--------------|---------:|----------:|----------------:|-----------:|---------:|---------------:|------------------------:|---------:|----------:|
| baseline       | full          |      849 |    145.8  |           1.215 |     -12    |   12.15  |          55.83 |                       0 |      320 |        86 |
| baseline       | last_2y       |      183 |     37.42 |           1.28  |      -9    |    4.158 |          53.01 |                       0 |       66 |        28 |
| baseline       | last_1y       |       93 |     17.54 |           1.256 |      -9    |    1.949 |          53.76 |                       0 |       35 |        13 |
| baseline       | holdout_2025p |      111 |     18.04 |           1.21  |      -9    |    2.005 |          54.05 |                       0 |       44 |        14 |
| risk_gap_0p75r | full          |      849 |     83.22 |           1.057 |     -15.42 |    5.397 |          55.83 |                     458 |      458 |         2 |
| risk_gap_0p75r | last_2y       |      183 |     12.14 |           1     |      -8.88 |    1.367 |          53.01 |                      96 |       96 |         1 |
| risk_gap_0p75r | last_1y       |       93 |      6.05 |           1.003 |      -8.4  |    0.72  |          53.76 |                      49 |       49 |         1 |
| risk_gap_0p75r | holdout_2025p |      111 |      8.11 |           1.022 |      -8.4  |    0.965 |          54.05 |                      59 |       59 |         1 |
| atr_gap_5pct   | full          |      849 |    103.08 |           1.107 |     -12.11 |    8.514 |          55.83 |                     460 |      460 |         6 |
| atr_gap_5pct   | last_2y       |      183 |     20.41 |           1.091 |      -8.76 |    2.329 |          53.01 |                      95 |       95 |         2 |
| atr_gap_5pct   | last_1y       |       93 |     11.44 |           1.12  |      -8.76 |    1.305 |          53.76 |                      48 |       48 |         2 |
| atr_gap_5pct   | holdout_2025p |      111 |     13.34 |           1.12  |      -8.76 |    1.522 |          54.05 |                      58 |       58 |         2 |

## Candidate Notes

- Baseline full: 146R, PF 1.22, DD -12.0R.
- Risk 0.75R full: 83.2R, PF 1.06, DD -15.4R; 2025+ 8.11R.
- ATR 5% full: 103R, PF 1.11, DD -12.1R; 2025+ 13.3R.
- Last-2Y risk vs ATR: 12.1R vs 20.4R.

## Artifacts

- Summary CSV: `backtesting/data/results/alpha_v1_es_ny_runner_trail_exact_20260511/summary.csv`
- Summary JSON: `backtesting/data/results/alpha_v1_es_ny_runner_trail_exact_20260511/summary.json`
- `baseline` exact cache: `backtesting/data/results/alpha_v1_es_ny_runner_trail_exact_20260511/exact_baseline.json` (211.15s)
- `risk_gap_0p75r` exact cache: `backtesting/data/results/alpha_v1_es_ny_runner_trail_exact_20260511/exact_risk_gap_0p75r.json` (155.21s)
- `atr_gap_5pct` exact cache: `backtesting/data/results/alpha_v1_es_ny_runner_trail_exact_20260511/exact_atr_gap_5pct.json` (165.26s)
