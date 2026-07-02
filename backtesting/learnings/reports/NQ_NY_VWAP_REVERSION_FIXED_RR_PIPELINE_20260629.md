# NQ NY VWAP Reversion Fixed-R Pipeline Start

- Run slug: `nq_ny_vwap_reversion_fixed_rr_pipeline_20260629`
- Phase: holdout freeze + fixed-R coarse structural screen
- Pre-holdout discovery: `2016-01-01` to `<2025-01-01`
- Reserved holdout: `2025-01-01` to `2026-06-06`; previous logged tests: `0`
- Account test: `$2000` account, `$500` risk/trade = `4.0R` account capacity
- Fixed exit: `rr=1.5`, `tp1_ratio=1.0` single target
- Raw configs: `576`
- Positive configs with at least 100 trades: `25`

## Top Rows By Total R

|   rank | variant_id                  |   total_trades |   total_r |   profit_factor |   win_rate |   max_drawdown_r |   neg_years |   worst_year |   worst_year_r | breaches_2000_500_account   | deployability   |
|-------:|:----------------------------|---------------:|----------:|----------------:|-----------:|-----------------:|------------:|-------------:|---------------:|:----------------------------|:----------------|
|      1 | dev10_stop20_0935-1200_long |            340 |     19.48 |            1.12 |       0.48 |           -12.49 |           0 |         2016 |           1.65 | True                        | research_only   |
|      2 | dev10_stop20_0935-1130_long |            310 |     16.44 |            1.11 |       0.47 |           -15.61 |           1 |         2016 |          -2.99 | True                        | research_only   |
|      3 | dev10_stop20_0935-1030_long |            231 |     16.05 |            1.13 |       0.48 |            -9.93 |           1 |         2020 |          -1    | True                        | research_only   |
|      4 | dev20_stop20_0935-1200_long |            197 |     11.96 |            1.17 |       0.47 |           -14.5  |           1 |         2016 |          -1.51 | True                        | research_only   |
|      5 | dev10_stop20_1000-1030_long |            170 |     11.74 |            1.17 |       0.47 |           -11.59 |           2 |         2016 |          -7.47 | True                        | research_only   |
|      6 | dev15_stop20_0935-1030_long |            164 |     10.98 |            1.13 |       0.48 |           -11.54 |           2 |         2016 |          -6    | True                        | research_only   |
|      7 | dev10_stop20_1000-1200_long |            302 |     10.85 |            1.09 |       0.47 |           -17.22 |           2 |         2016 |         -11.6  | True                        | research_only   |
|      8 | dev25_stop20_0935-1200_long |            151 |     10.82 |            1.18 |       0.46 |            -9.52 |           3 |         2018 |          -4.17 | True                        | research_only   |
|      9 | dev10_stop20_1000-1130_long |            269 |     10.19 |            1.09 |       0.46 |           -20.37 |           2 |         2016 |         -14.85 | True                        | research_only   |
|     10 | dev10_stop10_1000-1030_long |            275 |      9.73 |            1.09 |       0.42 |           -12.9  |           2 |         2021 |          -4    | True                        | research_only   |
|     11 | dev25_stop20_0935-1030_long |             81 |      9.2  |            1.34 |       0.47 |            -8.5  |           1 |         2016 |          -8    | True                        | research_only   |
|     12 | dev20_stop20_0935-1030_long |            113 |      8.97 |            1.23 |       0.47 |            -9.72 |           2 |         2016 |          -7.5  | True                        | research_only   |

## Read

- This is not a final promotion packet. It is the first coarse screen before walk-forward, plateau checks, PSR/DSR, or phase-one payout modeling.
- All rows are `research_only` until the VWAP reversion strategy exists in the live execution engine and exact replay confirms parity.
- The `$500` risk on a `$2,000` account means any path worse than `-4R` breaches the account.

## Artifacts

- CSV: `backtesting/data/results/nq_ny_vwap_reversion_fixed_rr_pipeline_20260629/coarse_screen.csv`
- Summary JSON: `backtesting/data/results/nq_ny_vwap_reversion_fixed_rr_pipeline_20260629/summary.json`
