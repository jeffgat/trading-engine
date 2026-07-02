# NQ NY Level Mean-Reversion State-Machine Recent 5-Year Pass

- Run slug: `nq_ny_level_reversion_state_machine_recent5_20260629`
- Data: `2021-06-05` to `<2026-06-06` using available NQ 5m bars
- Trading days: `1293`
- Pattern: extension from mean first, then consolidation can form within a timeout, then sweep/reclaim targets the signal-time mean
- Mean modes tested: `day_mid`, `ib_mid30`, `vwap`
- Entry window: `09:45` to `15:00`; flat by `15:55`
- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar
- Raw configs: `1620`
- Frequency-fit configs (`1-3` trades/day and >=70% day coverage): `702`
- Positive configs with >=80% day coverage: `0`

## Top Rows By Frequency-Aware Score

|   rank | variant_id                                             |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   pct_days_1_to_3_trades |   zero_trade_days |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   target_exits |   stop_exits |   eod_exits |   avg_setup_wait_bars |
|-------:|:-------------------------------------------------------|---------------:|---------------------:|----------------------:|-------------------------:|------------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------------:|-------------:|------------:|----------------------:|
|      1 | day_mid_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2 |            931 |               0.72   |                0.5189 |                   0.5189 |               622 |   96.254  |  0.1034 |          1.1422 |     0.2642 |         -53.7299 |            187 |          674 |          70 |                 11.26 |
|      2 | day_mid_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.4 |            924 |               0.7146 |                0.5159 |                   0.5159 |               626 |   95.4452 |  0.1033 |          1.1412 |     0.2597 |         -52.7299 |            181 |          673 |          70 |                 11.26 |
|      3 | day_mid_ext0.05_cons6x0.15_timeout12_buf0.02_minrr0.2  |            927 |               0.7169 |                0.5159 |                   0.5159 |               626 |   93.8759 |  0.1013 |          1.1389 |     0.2621 |         -53.7299 |            184 |          673 |          70 |                 11.16 |
|      4 | day_mid_ext0.05_cons6x0.15_timeout12_buf0.02_minrr0.4  |            920 |               0.7115 |                0.5128 |                   0.5128 |               630 |   93.0671 |  0.1012 |          1.1379 |     0.2576 |         -52.7299 |            178 |          672 |          70 |                 11.16 |
|      5 | day_mid_ext0.025_cons6x0.15_timeout24_buf0.02_minrr0.2 |            931 |               0.72   |                0.5189 |                   0.5189 |               622 |   91.4969 |  0.0983 |          1.1349 |     0.2632 |         -53.7299 |            186 |          675 |          70 |                 19.23 |
|      6 | day_mid_ext0.025_cons6x0.15_timeout24_buf0.02_minrr0.4 |            924 |               0.7146 |                0.5159 |                   0.5159 |               626 |   90.6881 |  0.0981 |          1.1339 |     0.2587 |         -52.7299 |            180 |          674 |          70 |                 19.25 |
|      7 | vwap_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2    |            886 |               0.6852 |                0.5019 |                   0.5019 |               644 |   92.89   |  0.1048 |          1.1456 |     0.2709 |         -55.904  |            192 |          635 |          59 |                 11.24 |
|      8 | vwap_ext0.025_cons6x0.15_timeout24_buf0.02_minrr0.2    |            886 |               0.6852 |                0.5019 |                   0.5019 |               644 |   92.89   |  0.1048 |          1.1456 |     0.2709 |         -55.904  |            192 |          635 |          59 |                 19.38 |
|      9 | day_mid_ext0.05_cons6x0.15_timeout24_buf0.02_minrr0.2  |            928 |               0.7177 |                0.5166 |                   0.5166 |               625 |   89.415  |  0.0964 |          1.1321 |     0.2619 |         -53.7299 |            184 |          674 |          70 |                 19.01 |
|     10 | vwap_ext0.05_cons6x0.15_timeout24_buf0.02_minrr0.2     |            881 |               0.6814 |                0.4988 |                   0.4988 |               648 |   91.9794 |  0.1044 |          1.1447 |     0.2701 |         -54.904  |            190 |          633 |          58 |                 19.06 |
|     11 | day_mid_ext0.05_cons6x0.15_timeout24_buf0.02_minrr0.4  |            921 |               0.7123 |                0.5135 |                   0.5135 |               629 |   88.6062 |  0.0962 |          1.1311 |     0.2573 |         -52.7299 |            178 |          673 |          70 |                 19.04 |
|     12 | vwap_ext0.05_cons6x0.15_timeout36_buf0.02_minrr0.2     |            881 |               0.6814 |                0.4988 |                   0.4988 |               648 |   91.571  |  0.1039 |          1.1441 |     0.2701 |         -54.904  |            190 |          633 |          58 |                 24.94 |
|     13 | day_mid_ext0.025_cons6x0.15_timeout36_buf0.02_minrr0.2 |            929 |               0.7185 |                0.5189 |                   0.5189 |               622 |   87.7111 |  0.0944 |          1.1294 |     0.2616 |         -53.7299 |            184 |          675 |          70 |                 24.89 |
|     14 | vwap_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.4    |            879 |               0.6798 |                0.4988 |                   0.4988 |               648 |   90.9535 |  0.1035 |          1.1426 |     0.2651 |         -56.2866 |            185 |          635 |          59 |                 11.23 |
|     15 | vwap_ext0.025_cons6x0.15_timeout24_buf0.02_minrr0.4    |            879 |               0.6798 |                0.4988 |                   0.4988 |               648 |   90.9535 |  0.1035 |          1.1426 |     0.2651 |         -56.2866 |            185 |          635 |          59 |                 19.39 |

## Top Frequency-Fit Rows

|   rank | variant_id                                            |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   pct_days_1_to_3_trades |   zero_trade_days |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   target_exits |   stop_exits |   eod_exits |   avg_setup_wait_bars |
|-------:|:------------------------------------------------------|---------------:|---------------------:|----------------------:|-------------------------:|------------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------------:|-------------:|------------:|----------------------:|
|    102 | vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2    |           1393 |               1.0773 |                0.7077 |                   0.7077 |               378 |   23.5585 |  0.0169 |          1.023  |     0.2606 |         -82.4807 |            306 |         1020 |          67 |                 11.02 |
|    109 | vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.4    |           1387 |               1.0727 |                0.7061 |                   0.7061 |               380 |   22.0046 |  0.0159 |          1.0215 |     0.2574 |         -82.7036 |            300 |         1020 |          67 |                 11.02 |
|    113 | vwap_ext0.025_cons6x0.2_timeout24_buf0.02_minrr0.2    |           1391 |               1.0758 |                0.7077 |                   0.7077 |               378 |   20.8763 |  0.015  |          1.0204 |     0.2595 |         -83.642  |            304 |         1020 |          67 |                 18.04 |
|    114 | vwap_ext0.05_cons6x0.2_timeout12_buf0.02_minrr0.2     |           1387 |               1.0727 |                0.7038 |                   0.7038 |               383 |   21.0596 |  0.0152 |          1.0207 |     0.2596 |         -83.2691 |            303 |         1017 |          67 |                 10.91 |
|    115 | day_mid_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.4 |           1466 |               1.1338 |                0.7293 |                   0.7293 |               350 |   16.5502 |  0.0113 |          1.0151 |     0.2483 |         -77.8893 |            291 |         1094 |          81 |                 11.03 |
|    117 | day_mid_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2 |           1473 |               1.1392 |                0.7309 |                   0.7309 |               348 |   16.1262 |  0.0109 |          1.0147 |     0.2505 |         -78.2008 |            296 |         1096 |          81 |                 11.03 |
|    119 | vwap_ext0.05_cons6x0.2_timeout24_buf0.02_minrr0.2     |           1386 |               1.0719 |                0.7046 |                   0.7046 |               382 |   19.9657 |  0.0144 |          1.0196 |     0.259  |         -84.7737 |            302 |         1018 |          66 |                 17.76 |
|    120 | day_mid_ext0.05_cons6x0.2_timeout12_buf0.02_minrr0.4  |           1460 |               1.1292 |                0.7254 |                   0.7254 |               355 |   16.1721 |  0.0111 |          1.0148 |     0.2473 |         -80.0164 |            288 |         1091 |          81 |                 10.94 |
|    124 | vwap_ext0.025_cons6x0.2_timeout24_buf0.02_minrr0.4    |           1385 |               1.0712 |                0.7061 |                   0.7061 |               380 |   19.3224 |  0.014  |          1.0189 |     0.2563 |         -83.8649 |            298 |         1020 |          67 |                 18.05 |
|    126 | vwap_ext0.05_cons6x0.2_timeout12_buf0.02_minrr0.4     |           1381 |               1.0681 |                0.7022 |                   0.7022 |               385 |   19.5057 |  0.0141 |          1.0191 |     0.2563 |         -83.492  |            297 |         1017 |          67 |                 10.91 |
|    127 | day_mid_ext0.05_cons6x0.2_timeout12_buf0.02_minrr0.2  |           1467 |               1.1346 |                0.727  |                   0.727  |               353 |   15.7481 |  0.0107 |          1.0144 |     0.2495 |         -80.766  |            293 |         1093 |          81 |                 10.94 |
|    134 | vwap_ext0.05_cons6x0.2_timeout24_buf0.02_minrr0.4     |           1380 |               1.0673 |                0.703  |                   0.703  |               384 |   18.4118 |  0.0133 |          1.018  |     0.2558 |         -84.9966 |            296 |         1018 |          66 |                 17.78 |
|    144 | vwap_ext0.05_cons6x0.2_timeout36_buf0.02_minrr0.2     |           1384 |               1.0704 |                0.7046 |                   0.7046 |               382 |   16.1071 |  0.0116 |          1.0158 |     0.2579 |         -85.7864 |            300 |         1018 |          66 |                 22.21 |
|    147 | vwap_ext0.025_cons6x0.2_timeout36_buf0.02_minrr0.2    |           1389 |               1.0742 |                0.7077 |                   0.7077 |               378 |   14.8551 |  0.0107 |          1.0145 |     0.2585 |         -83.642  |            302 |         1020 |          67 |                 22.57 |
|    149 | day_mid_ext0.025_cons6x0.2_timeout24_buf0.02_minrr0.4 |           1466 |               1.1338 |                0.7293 |                   0.7293 |               350 |   11.7931 |  0.008  |          1.0107 |     0.2476 |         -82.6464 |            290 |         1095 |          81 |                 17.8  |

## Top Positive Rows With >=80% Day Coverage

_None._

## Read

- This is a second-pass prototype, not a promotion packet. It still uses 5m conservative pathing and no live/exact replay support.
- The state-machine pass tests whether separating extension from consolidation improves the edge/cadence tradeoff from the first pass.
- Any survivor still needs 1m/1s path validation, train/validation split, and prop-firm risk scoring.

## Diagnostic Read

- The state machine improved the **edge anchor** but not the **daily cadence** objective.
- Best edge row: `day_mid_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2` made `931` trades (`0.72/day`, `51.89%` day coverage), `+96.25R`, PF `1.142`, avg R `0.103`, max DD `-53.73R`. Compared with first pass best edge (`+92.16R`, PF `1.121`, DD `-62.83R`, `0.80/day`), this is cleaner but sparser.
- Best frequency-fit row: `vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2` made `1,393` trades (`1.08/day`, `70.77%` day coverage), `+23.56R`, PF `1.023`, max DD `-82.48R`. This is lower EV than the first pass frequency-fit IB-mid row (`+60.83R`, PF `1.0395`, DD `-111.55R`) but with less drawdown.
- No config averaging `>=1` trade/day reached PF `1.05`; no positive config achieved `>=80%` day coverage.
- By mean anchor, best total R was `day_mid +96.25R`, `vwap +92.89R`, `ib_mid30 +58.89R`. The state machine shifted the useful frequency-fit rows from `ib_mid30` toward `vwap`, but the 1/day edge remains thin.
- Yearly R for the top edge row: `2021 +3.96R`, `2022 -24.07R`, `2023 -5.36R`, `2024 +41.88R`, `2025 +54.13R`, `2026 +25.71R`. The edge is recent-heavy and not stable enough for promotion.
- Read: keep this branch alive as a structural research thesis, but do not push it to prop-risk optimization yet. The next productive pass is not more frequency forcing; it should add a regime/context filter or use the state-machine edge anchor as a lower-frequency component.

## Artifacts

- Ranked candidates: `backtesting/data/results/nq_ny_level_reversion_state_machine_recent5_20260629/ranked_candidates.csv`
- Top candidate trades: `backtesting/data/results/nq_ny_level_reversion_state_machine_recent5_20260629/top_candidate_trades.csv`
- Summary JSON: `backtesting/data/results/nq_ny_level_reversion_state_machine_recent5_20260629/summary.json`
