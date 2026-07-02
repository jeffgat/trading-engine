# NQ NY VWAP Prop-Firm Pipeline Screen

- Run slug: `nq_ny_vwap_prop_firm_pipeline_20260629`
- Phase: pre-holdout prop objective screen, no 2025+ holdout trades used for ranking
- Price data: `NQ`; sizing instrument: `MNQ`
- Discovery period: `2016-01-01` to `<2025-01-01`
- Account starts used for ranking: `2016-01-01` to `<2024-07-01` every `14` days
- Recent validation slice: account starts from `2021-01-01` onward
- Reserved holdout: `2025-01-01` to `2026-06-06`; previous logged tests: `0`
- Prop model: `$2000` EOD trailing drawdown capped at start, `$3000` pass target, `$1500` first payout, then keep trading until bust or data end
- Challenge/account fee modeled: `$0`
- Raw configs: `2700`
- Positive recent-EV configs with recent payout rate >= 35% and >=100 trades: `2`

## Coarse Top Rows By Prop Objective

|   rank | variant_id                                     |   total_trades |   total_net_r |   profit_factor |   max_drawdown_r |   recent_first_payout_rate |   recent_ev_per_start_usd |   recent_pre_payout_bust_rate |   recent_post_payout_bust_rate |   recent_open_rate |   recent_avg_days_to_first_payout |   all_first_payout_rate |   all_ev_per_start_usd |
|-------:|:-----------------------------------------------|---------------:|--------------:|----------------:|-----------------:|---------------------------:|--------------------------:|------------------------------:|-------------------------------:|-------------------:|----------------------------------:|------------------------:|-----------------------:|
|      1 | mnq_dev30_stop15_rr2_risk300_0935-1030_long    |            260 |         -5.72 |            0.97 |           -17.5  |                     0.2637 |                    395.6  |                        0.7363 |                         0.2637 |             0      |                            568.17 |                  0.6171 |                 925.68 |
|      2 | mnq_dev10_stop15_rr2_risk300_0935-1200_long    |           1301 |        -24.09 |            0.97 |           -49.12 |                     0.3956 |                    593.41 |                        0.6044 |                         0.1429 |             0.2527 |                            204.06 |                  0.2658 |                 398.65 |
|      3 | mnq_dev30_stop15_rr1.5_risk300_0935-1030_long  |            260 |         -4.74 |            0.98 |           -20.5  |                     0.1758 |                    263.74 |                        0.8022 |                         0.1758 |             0.022  |                            577.19 |                  0.6036 |                 905.41 |
|      4 | mnq_dev30_stop15_rr1.5_risk300_0935-1130_long  |            460 |        -14.39 |            0.95 |           -24.28 |                     0.3626 |                    543.96 |                        0.6374 |                         0.3626 |             0      |                            431.64 |                  0.1757 |                 263.51 |
|      5 | mnq_dev10_stop20_rr1.5_risk300_0935-1200_long  |           1300 |          9.73 |            1    |           -32.54 |                     0.3187 |                    478.02 |                        0.6593 |                         0.2967 |             0.044  |                            252.1  |                  0.2658 |                 398.65 |
|      6 | mnq_dev10_stop20_rr1.25_risk250_0935-1130_long |           1196 |        -12.95 |            0.97 |           -31.66 |                     0.3077 |                    461.54 |                        0.6923 |                         0.3077 |             0      |                            347.93 |                  0.2703 |                 405.41 |
|      7 | mnq_dev30_stop10_rr2_risk300_0935-1030_long    |            260 |        -18.79 |            0.89 |           -27    |                     0.2527 |                    379.12 |                        0.7363 |                         0.2527 |             0.011  |                            477.87 |                  0.3784 |                 567.57 |
|      8 | mnq_dev25_stop20_rr2_risk300_0935-1030_long    |            367 |          6.55 |            1.03 |           -22.24 |                     0.2088 |                    313.19 |                        0.7692 |                         0.2088 |             0.022  |                            670.05 |                  0.4369 |                 655.41 |
|      9 | mnq_dev10_stop15_rr2_risk300_0935-1130_long    |           1217 |        -29.45 |            0.96 |           -46.47 |                     0.2967 |                    445.05 |                        0.7033 |                         0.1868 |             0.1099 |                            209.67 |                  0.2568 |                 385.14 |
|     10 | mnq_dev25_stop20_rr2_risk250_0935-1030_long    |            364 |          3.56 |            1.01 |           -24.24 |                     0.1648 |                    247.25 |                        0.8132 |                         0.1648 |             0.022  |                            584.07 |                  0.491  |                 736.49 |
|     11 | mnq_dev25_stop25_rr1.5_risk300_0935-1030_long  |            364 |          4.07 |            1.02 |           -13.77 |                     0.1319 |                    197.8  |                        0.8571 |                         0.1319 |             0.011  |                            742.92 |                  0.545  |                 817.57 |
|     12 | mnq_dev10_stop20_rr2_risk300_0935-1200_long    |           1300 |        -12.45 |            0.98 |           -36.01 |                     0.2637 |                    395.6  |                        0.6813 |                         0.2637 |             0.0549 |                            215.46 |                  0.2342 |                 351.35 |
|     13 | mnq_dev10_stop20_rr1.5_risk300_0935-1130_long  |           1216 |          7.79 |            1.01 |           -28.32 |                     0.2527 |                    379.12 |                        0.7253 |                         0.2418 |             0.033  |                            212.35 |                  0.2523 |                 378.38 |
|     14 | mnq_dev25_stop10_rr1.25_risk250_1000-1200_long |            634 |        -42.77 |            0.87 |           -48.92 |                     0.3187 |                    478.02 |                        0.5714 |                         0.2088 |             0.2198 |                            445.21 |                  0.1306 |                 195.95 |
|     15 | mnq_dev30_stop20_rr1.5_risk200_0935-1130_long  |            431 |        -12.27 |            0.98 |           -21.59 |                     0.1538 |                    230.77 |                        0.8132 |                         0.1538 |             0.033  |                            619.5  |                  0.4189 |                 628.38 |

## Targeted Risk/RR Refinement

- Source: top `30` coarse rows by recent prop EV / payout rate / all-period EV.
- Refined `17` unique signal shapes over risk `$250,$300,$325,$350,$375,$400,$450,$500,$600` and RR `1.25,1.5,1.75,2.0,2.25,2.5`.
- Refined configs: `918`.
- Best refined candidate: `mnq_dev25_stop20_rr1.75_risk450_0935-1030_long`.
- Best trade metrics: `367` trades, `+17.65R`, `$7,155.36` net PnL at simulated MNQ sizing, PF `1.09`, WR `41%`, max DD `-16.98R`.
- Best all-start prop path: first payout rate `54.95%`, realized first-payout EV `$824.32/start`, open rate `19.82%`, avg days to first payout `313.61`.
- Best recent-start prop path (`2021-01-01+`): first payout rate `47.25%`, realized first-payout EV `$708.79/start`, pre-payout bust rate `52.75%`, post-payout bust rate `47.25%`, open rate `0%`, avg days to first payout `195.58`.
- Top refined account outcomes: `100` bust before payout, `78` bust after first payout, `44` still open after payout across `222` staggered starts. Recent starts had `48` bust before payout and `43` bust after payout, with no open accounts.

|   rank | variant_id                                      |   total_trades |   total_net_r |   profit_factor |   max_drawdown_r |   recent_first_payout_rate |   recent_ev_per_start_usd |   recent_pre_payout_bust_rate |   recent_post_payout_bust_rate |   recent_open_rate |   recent_avg_days_to_first_payout |   all_first_payout_rate |   all_ev_per_start_usd |
|-------:|:------------------------------------------------|---------------:|--------------:|----------------:|-----------------:|---------------------------:|--------------------------:|------------------------------:|-------------------------------:|-------------------:|----------------------------------:|------------------------:|-----------------------:|
|      1 | mnq_dev25_stop20_rr1.75_risk450_0935-1030_long |            367 |         17.65 |            1.09 |           -16.98 |                     0.4725 |                    708.79 |                        0.5275 |                         0.4725 |             0      |                            195.58 |                  0.5495 |                 824.32 |
|      2 | mnq_dev30_stop10_rr2.5_risk300_0935-1030_long  |            260 |        -21.66 |            0.88 |           -30.11 |                     0.4505 |                    675.82 |                        0.5495 |                         0.4505 |             0      |                            427.9  |                  0.4595 |                 689.19 |
|      3 | mnq_dev25_stop20_rr2.5_risk325_0935-1030_long  |            367 |          7.77 |            1.06 |           -21.05 |                     0.3846 |                    576.92 |                        0.6154 |                         0.3846 |             0      |                            429.66 |                  0.5586 |                 837.84 |
|      4 | mnq_dev25_stop20_rr1.5_risk450_0935-1030_long  |            367 |         19.64 |            1.10 |           -14.73 |                     0.4066 |                    609.89 |                        0.5934 |                         0.4066 |             0      |                            228.62 |                  0.4820 |                 722.97 |
|      5 | mnq_dev25_stop20_rr1.5_risk375_0935-1030_long  |            367 |         19.64 |            1.08 |           -14.73 |                     0.4066 |                    609.89 |                        0.4286 |                         0.4066 |             0.1648 |                            344.30 |                  0.5090 |                 763.51 |

## Read

- This is still `research_only`: the VWAP reversion entry/exit strategy needs live execution support and exact replay parity before promotion.
- The first-payout EV here counts the `$1,500` withdrawal and does not assume additional withdrawals after that first payout.
- Open post-payout accounts are marked through data end, but realized EV only counts completed withdrawals.
- The refined leader is a candidate for walk-forward/holdout-gated validation, not a promotion. It still has a high pre-payout bust rate and uses MNQ sizing over NQ price data.
- Holdout remains closed; this is an optimizer pass on pre-2025 data.

## Artifacts

- Ranked candidates: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/ranked_candidates.csv`
- Top account paths: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/top_candidate_account_outcomes.csv`
- Summary JSON: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/summary.json`
- Refined candidates: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/risk_refine_candidates.csv`
- Refined top account paths: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/risk_refine_top_account_outcomes.csv`
- Refined summary JSON: `backtesting/data/results/nq_ny_vwap_prop_firm_pipeline_20260629/risk_refine_summary.json`
