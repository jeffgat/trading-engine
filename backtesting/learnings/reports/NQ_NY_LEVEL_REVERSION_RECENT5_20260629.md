# NQ NY Level Mean-Reversion Recent 5-Year Prototype

- Run slug: `nq_ny_level_reversion_recent5_20260629`
- Data: `2021-06-05` to `<2026-06-06` using available NQ 5m bars
- Trading days: `1293`
- Pattern: extension from mean -> tight consolidation -> sweep/reclaim of consolidation edge -> target fixed mean level
- Mean modes tested: `vwap`, `ny_open`, `ib_mid30`, `day_mid`
- Entry window: `09:45` to `15:00`; flat by `15:55`
- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar
- Raw configs: `2160`
- Configs averaging 1-3 trades/day with at least 60% trade-day coverage: `980`

## Top Rows By Frequency-Aware Score

|   rank | variant_id                                   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   pct_days_1_to_3_trades |   zero_trade_days |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   target_exits |   stop_exits |   eod_exits |
|-------:|:---------------------------------------------|---------------:|---------------------:|----------------------:|-------------------------:|------------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------------:|-------------:|------------:|
|      1 | day_mid_ext0.025_cons6x0.15_buf0.02_minrr0.2 |           1038 |               0.8028 |                0.5189 |                   0.5189 |               622 |   92.1648 |  0.0888 |          1.121  |     0.2572 |         -62.8297 |            198 |          758 |          82 |
|      2 | day_mid_ext0.05_cons6x0.15_buf0.02_minrr0.2  |           1038 |               0.8028 |                0.5189 |                   0.5189 |               622 |   91.8336 |  0.0885 |          1.1206 |     0.2572 |         -62.8297 |            198 |          758 |          82 |
|      3 | day_mid_ext0.025_cons6x0.15_buf0.02_minrr0.6 |           1024 |               0.792  |                0.5128 |                   0.5128 |               630 |   93.0168 |  0.0908 |          1.1224 |     0.25   |         -63.4824 |            188 |          756 |          80 |
|      4 | day_mid_ext0.025_cons6x0.15_buf0.02_minrr0.4 |           1031 |               0.7974 |                0.5159 |                   0.5159 |               626 |   91.356  |  0.0886 |          1.1201 |     0.2532 |         -62.5391 |            192 |          757 |          82 |
|      5 | day_mid_ext0.05_cons6x0.15_buf0.02_minrr0.6  |           1024 |               0.792  |                0.5128 |                   0.5128 |               630 |   92.6856 |  0.0905 |          1.122  |     0.25   |         -63.4824 |            188 |          756 |          80 |
|      6 | day_mid_ext0.05_cons6x0.15_buf0.02_minrr0.4  |           1031 |               0.7974 |                0.5159 |                   0.5159 |               626 |   91.0248 |  0.0883 |          1.1197 |     0.2532 |         -62.5391 |            192 |          757 |          82 |
|      7 | day_mid_ext0.075_cons6x0.15_buf0.02_minrr0.2 |           1031 |               0.7974 |                0.5151 |                   0.5151 |               627 |   86.9269 |  0.0843 |          1.1143 |     0.2541 |         -64.9168 |            194 |          757 |          80 |
|      8 | day_mid_ext0.075_cons6x0.15_buf0.02_minrr0.6 |           1017 |               0.7865 |                0.5089 |                   0.5089 |               635 |   87.7789 |  0.0863 |          1.1157 |     0.2468 |         -65.5695 |            184 |          755 |          78 |
|      9 | day_mid_ext0.075_cons6x0.15_buf0.02_minrr0.4 |           1024 |               0.792  |                0.512  |                   0.512  |               631 |   86.1181 |  0.0841 |          1.1134 |     0.25   |         -64.6262 |            188 |          756 |          80 |
|     10 | day_mid_ext0.025_cons6x0.15_buf0.01_minrr0.2 |           1064 |               0.8229 |                0.5189 |                   0.5189 |               622 |   85.7598 |  0.0806 |          1.1038 |     0.2171 |         -73.1503 |            174 |          824 |          66 |
|     11 | day_mid_ext0.05_cons6x0.15_buf0.01_minrr0.2  |           1064 |               0.8229 |                0.5189 |                   0.5189 |               622 |   85.0025 |  0.0799 |          1.1029 |     0.2171 |         -73.9076 |            174 |          824 |          66 |
|     12 | day_mid_ext0.1_cons6x0.15_buf0.02_minrr0.2   |           1017 |               0.7865 |                0.5058 |                   0.5058 |               639 |   79.4936 |  0.0782 |          1.1052 |     0.2488 |         -66.2671 |            187 |          753 |          77 |
|     13 | day_mid_ext0.1_cons6x0.15_buf0.02_minrr0.6   |           1005 |               0.7773 |                0.5004 |                   0.5004 |               646 |   80.552  |  0.0802 |          1.1069 |     0.2418 |         -66.9198 |            177 |          751 |          77 |
|     14 | day_mid_ext0.1_cons6x0.15_buf0.02_minrr0.4   |           1010 |               0.7811 |                0.5027 |                   0.5027 |               643 |   78.6848 |  0.0779 |          1.1043 |     0.2446 |         -65.9765 |            181 |          752 |          77 |
|     15 | day_mid_ext0.025_cons6x0.15_buf0.01_minrr0.4 |           1058 |               0.8183 |                0.5159 |                   0.5159 |               626 |   83.8501 |  0.0793 |          1.1015 |     0.2127 |         -73.8919 |            168 |          824 |          66 |

## Top Rows Meeting 1-3 Trades/Day Frequency Filter

|   rank | variant_id                                     |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   pct_days_1_to_3_trades |   zero_trade_days |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   target_exits |   stop_exits |   eod_exits |
|-------:|:-----------------------------------------------|---------------:|---------------------:|----------------------:|-------------------------:|------------------:|----------:|--------:|----------------:|-----------:|-----------------:|---------------:|-------------:|------------:|
|     35 | ib_mid30_ext0.15_cons4x0.15_buf0.005_minrr0.2  |           1863 |               1.4408 |                0.7448 |                   0.7448 |               330 |   60.8336 |  0.0327 |          1.0395 |     0.1696 |        -111.549  |            204 |         1538 |         121 |
|     39 | ib_mid30_ext0.15_cons4x0.15_buf0.005_minrr0.4  |           1860 |               1.4385 |                0.744  |                   0.744  |               331 |   60.0889 |  0.0323 |          1.039  |     0.1683 |        -111.549  |            201 |         1538 |         121 |
|     41 | ib_mid30_ext0.15_cons4x0.15_buf0.005_minrr0.6  |           1855 |               1.4346 |                0.7417 |                   0.7417 |               334 |   59.0975 |  0.0319 |          1.0384 |     0.1666 |        -111.527  |            197 |         1537 |         121 |
|     51 | vwap_ext0.025_cons6x0.2_buf0.01_minrr0.2       |           1656 |               1.2807 |                0.7077 |                   0.7077 |               378 |   23.68   |  0.0143 |          1.0183 |     0.2168 |         -73.4277 |            303 |         1289 |          64 |
|     54 | vwap_ext0.025_cons6x0.2_buf0.01_minrr0.4       |           1650 |               1.2761 |                0.7061 |                   0.7061 |               380 |   21.9967 |  0.0133 |          1.017  |     0.2139 |         -73.4277 |            297 |         1289 |          64 |
|     55 | vwap_ext0.05_cons6x0.2_buf0.01_minrr0.2        |           1654 |               1.2792 |                0.7061 |                   0.7061 |               380 |   22.3924 |  0.0135 |          1.0174 |     0.2164 |         -75.7153 |            302 |         1288 |          64 |
|     60 | vwap_ext0.05_cons6x0.2_buf0.01_minrr0.4        |           1648 |               1.2746 |                0.7046 |                   0.7046 |               382 |   20.7091 |  0.0126 |          1.0161 |     0.2136 |         -75.7153 |            296 |         1288 |          64 |
|     61 | vwap_ext0.025_cons6x0.2_buf0.01_minrr0.6       |           1639 |               1.2676 |                0.7015 |                   0.7015 |               386 |   20.6058 |  0.0126 |          1.016  |     0.2105 |         -75.0649 |            289 |         1287 |          63 |
|     65 | vwap_ext0.05_cons6x0.2_buf0.01_minrr0.6        |           1637 |               1.266  |                0.6999 |                   0.6999 |               388 |   19.3182 |  0.0118 |          1.015  |     0.2101 |         -77.3525 |            288 |         1286 |          63 |
|     76 | vwap_ext0.075_cons6x0.2_buf0.01_minrr0.2       |           1645 |               1.2722 |                0.7015 |                   0.7015 |               386 |   11.617  |  0.0071 |          1.009  |     0.2134 |         -75.3226 |            295 |         1286 |          64 |
|     80 | ib_mid30_ext0.075_cons4x0.15_buf0.005_minrr0.2 |           2030 |               1.57   |                0.7858 |                   0.7858 |               277 |   39.8009 |  0.0196 |          1.0241 |     0.1828 |        -117.906  |            260 |         1650 |         120 |
|     84 | vwap_ext0.075_cons6x0.2_buf0.01_minrr0.4       |           1640 |               1.2684 |                0.7007 |                   0.7007 |               387 |   10.1749 |  0.0062 |          1.0079 |     0.211  |         -75.3226 |            290 |         1286 |          64 |
|     87 | ib_mid30_ext0.075_cons4x0.15_buf0.005_minrr0.4 |           2022 |               1.5638 |                0.7842 |                   0.7842 |               279 |   38.7535 |  0.0192 |          1.0235 |     0.18   |        -118.253  |            253 |         1649 |         120 |
|    100 | vwap_ext0.075_cons6x0.2_buf0.01_minrr0.6       |           1629 |               1.2599 |                0.6961 |                   0.6961 |               393 |    8.784  |  0.0054 |          1.0068 |     0.2075 |         -76.5785 |            282 |         1284 |          63 |
|    104 | ib_mid30_ext0.05_cons4x0.15_buf0.005_minrr0.4  |           2038 |               1.5762 |                0.7881 |                   0.7881 |               274 |   38.0335 |  0.0187 |          1.0229 |     0.1806 |        -121.714  |            256 |         1661 |         121 |

## Read

- This is a prototype screen, not a promotion packet. It uses 5m conservative exit sequencing and has no live/exact replay support.
- The frequency objective is explicit: prefer average `1-3` trades/day and high percent of days with at least one trade.
- Any promising row needs a second pass with 1m/1s magnifier, train/validation split, and prop-firm risk analysis before being taken seriously.

## Diagnostic Read

- The best expectancy row used `day_mid` as the mean and made `1,038` trades over `1,293` RTH days (`0.80/day`, `51.89%` of days), with `+92.16R`, PF `1.121`, and max DD `-62.83R`. It is the best edge read but misses the requested minimum 1/day cadence.
- The best row that meets the 1-3/day cadence target used `ib_mid30`: `ib_mid30_ext0.15_cons4x0.15_buf0.005_minrr0.2`, with `1,863` trades (`1.44/day`, `74.48%` of days), `+60.83R`, PF `1.0395`, and max DD `-111.55R`.
- No configuration with average `>=1` trade/day reached PF `1.05`. There were also no positive rows with `>=80%` day coverage.
- The requested high-frequency shape is feasible mechanically, but the first-pass edge is thin once cadence is forced above 1/day. Treat `day_mid` as the cleaner edge anchor and `ib_mid30` as the cadence anchor.
- Next iteration should use a state-machine consolidation window after extension, not just the immediately prior bars, and validate top candidates with 1m/1s pathing before prop-risk scoring.

## Artifacts

- Ranked candidates: `backtesting/data/results/nq_ny_level_reversion_recent5_20260629/ranked_candidates.csv`
- Top candidate trades: `backtesting/data/results/nq_ny_level_reversion_recent5_20260629/top_candidate_trades.csv`
- Summary JSON: `backtesting/data/results/nq_ny_level_reversion_recent5_20260629/summary.json`
