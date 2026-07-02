# NQ NY Level Mean-Reversion Context-Filter Recent 5-Year Pass

- Run slug: `nq_ny_level_reversion_context_filter_recent5_20260629`
- Data: `2021-06-05` to `<2026-06-06` using available NQ 5m bars
- Trading days: `1293`
- Base anchors tested: `4`
- Context configs per anchor: `2700`
- Raw context rows: `10800`
- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar
- Candidate rows are `research_only`; live execution and exact replay parity are not implemented.

## Context Grid

- `structure_gate`: `none`, `reject_30m_trend_acceptance`, `require_30m_mixed`
- `vwap_acceptance`: `none`, `reject_vwap_side_slope`, `reject_vwap_side_distance`
- `efficiency_max`: `none`, `0.35`, `0.45`, `0.55`, `0.65`
- `ib_location`: `none`, `must_be_outside_ib`, `must_reclaim_inside_ib`
- `session_range_atr_max`: `none`, `1.25`, `1.50`, `1.75`, `2.00`
- `time_bucket`: `full`, `10:00-12:00`, `10:00-14:00`, `11:00-15:00`
- VWAP slope rejection threshold: `0.02` ATR over the prior 6 bars
- VWAP distance rejection threshold: `0.1` ATR on the continuation side of VWAP

## Baseline Anchor Replay Audit

| base_label           | variant_id                                             |   prior_total_trades |   replay_total_trades |   prior_total_r |   replay_total_r |   prior_profit_factor |   replay_profit_factor |
|:---------------------|:-------------------------------------------------------|---------------------:|----------------------:|----------------:|-----------------:|----------------------:|-----------------------:|
| day_mid_edge_anchor  | day_mid_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2 |                  931 |                   931 |         96.254  |          96.254  |                1.1422 |                 1.1422 |
| vwap_edge_anchor     | vwap_ext0.025_cons6x0.15_timeout12_buf0.02_minrr0.2    |                  886 |                   886 |         92.89   |          92.89   |                1.1456 |                 1.1456 |
| ib_mid30_edge_anchor | ib_mid30_ext0.15_cons6x0.15_timeout24_buf0.01_minrr0.2 |                  870 |                   870 |         58.8868 |          58.8868 |                1.0838 |                 1.0838 |
| best_cadence_anchor  | vwap_ext0.025_cons6x0.2_timeout12_buf0.02_minrr0.2     |                 1393 |                  1393 |         23.5585 |          23.5585 |                1.023  |                 1.023  |

## Ungated Baselines

| base_label           | structure_gate   | vwap_acceptance   |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:---------------------|:-----------------|:------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor  | none             | none              |              nan | none          |                     nan | full          |           1393 |               1.0773 |                0.7077 |   23.5585 |          1.023  |         -82.4807 |               0 |
| day_mid_edge_anchor  | none             | none              |              nan | none          |                     nan | full          |            931 |               0.72   |                0.5189 |   96.254  |          1.1422 |         -53.7299 |               0 |
| ib_mid30_edge_anchor | none             | none              |              nan | none          |                     nan | full          |            870 |               0.6729 |                0.4888 |   58.8868 |          1.0838 |         -73.536  |               0 |
| vwap_edge_anchor     | none             | none              |              nan | none          |                     nan | full          |            886 |               0.6852 |                0.5019 |   92.89   |          1.1456 |         -55.904  |               0 |

## Top Rows By Frequency-Aware Score

|   rank | base_label          | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   total_r_delta |   profit_factor_delta |   drawdown_improvement_r |
|-------:|:--------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|--------:|----------------:|-----------:|-----------------:|----------------:|----------------------:|-------------------------:|
|      1 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |        104.218  |                0.5333 |                  70.283  |
|      2 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | 10:00-14:00   |            371 |               0.2869 |                0.263  |  126.777  |  0.3417 |          1.5495 |     0.3693 |         -12.1977 |        103.218  |                0.5265 |                  70.283  |
|      3 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | 10:00-14:00   |            368 |               0.2846 |                0.2606 |  122.272  |  0.3323 |          1.5346 |     0.3696 |         -12.1977 |         98.7135 |                0.5116 |                  70.283  |
|      4 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | full          |            564 |               0.4362 |                0.3635 |  114.288  |  0.2026 |          1.3103 |     0.3387 |         -27.0491 |         90.7298 |                0.2873 |                  55.4316 |
|      5 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | 10:00-14:00   |            369 |               0.2854 |                0.2614 |  121.272  |  0.3287 |          1.528  |     0.3686 |         -12.1977 |         97.7135 |                0.505  |                  70.283  |
|      6 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | 10:00-14:00   |            362 |               0.28   |                0.256  |  122.168  |  0.3375 |          1.5437 |     0.3702 |         -13.7745 |         98.609  |                0.5207 |                  68.7062 |
|      7 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | full          |            565 |               0.437  |                0.3643 |  113.288  |  0.2005 |          1.3068 |     0.3381 |         -27.0491 |         89.7298 |                0.2838 |                  55.4316 |
|      8 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | 11:00-15:00   |            563 |               0.4354 |                0.3627 |  113.446  |  0.2015 |          1.308  |     0.3375 |         -27.0491 |         89.8876 |                0.285  |                  55.4316 |
|      9 | day_mid_edge_anchor | none             | none                   |           nan    | none          |                    2    | full          |            930 |               0.7193 |                0.5182 |   97.254  |  0.1046 |          1.1438 |     0.2645 |         -52.7299 |          1      |                0.0016 |                   1      |
|     10 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | 11:00-15:00   |            564 |               0.4362 |                0.3635 |  112.446  |  0.1994 |          1.3045 |     0.3369 |         -27.0491 |         88.8876 |                0.2815 |                  55.4316 |
|     11 | day_mid_edge_anchor | none             | none                   |           nan    | none          |                  nan    | full          |            931 |               0.72   |                0.5189 |   96.254  |  0.1034 |          1.1422 |     0.2642 |         -53.7299 |          0      |                0      |                   0      |
|     12 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | full          |            546 |               0.4223 |                0.3503 |  113.605  |  0.2081 |          1.3197 |     0.3407 |         -29.5806 |         90.0464 |                0.2967 |                  52.9001 |
|     13 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | full          |            558 |               0.4316 |                0.3589 |  111.241  |  0.1994 |          1.3054 |     0.3387 |         -27.0491 |         87.6824 |                0.2824 |                  55.4316 |
|     14 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | 11:00-15:00   |            545 |               0.4215 |                0.3496 |  112.763  |  0.2069 |          1.3174 |     0.3394 |         -29.5806 |         89.2042 |                0.2944 |                  52.9001 |
|     15 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | 11:00-15:00   |            557 |               0.4308 |                0.3581 |  110.399  |  0.1982 |          1.303  |     0.3375 |         -27.0491 |         86.8402 |                0.28   |                  55.4316 |
|     16 | best_cadence_anchor | none             | none                   |             0.55 | none          |                    2    | 11:00-15:00   |            592 |               0.4578 |                0.3596 |  107.631  |  0.1818 |          1.2755 |     0.3294 |         -17.9066 |         84.0729 |                0.2525 |                  64.5741 |
|     17 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | full          |            561 |               0.4339 |                0.3612 |  109.784  |  0.1957 |          1.2997 |     0.3387 |         -27.0491 |         86.2251 |                0.2767 |                  55.4316 |
|     18 | best_cadence_anchor | none             | none                   |             0.55 | none          |                  nan    | 11:00-15:00   |            593 |               0.4586 |                0.3604 |  106.631  |  0.1798 |          1.2723 |     0.3288 |         -17.9066 |         83.0729 |                0.2493 |                  64.5741 |
|     19 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | 11:00-15:00   |            560 |               0.4331 |                0.3604 |  108.941  |  0.1945 |          1.2974 |     0.3375 |         -27.0491 |         85.3829 |                0.2744 |                  55.4316 |
|     20 | best_cadence_anchor | none             | none                   |             0.55 | none          |                    2    | full          |            609 |               0.471  |                0.3666 |  105.845  |  0.1738 |          1.2642 |     0.3317 |         -18.9066 |         82.2861 |                0.2412 |                  63.5741 |
|     21 | best_cadence_anchor | none             | none                   |             0.55 | none          |                  nan    | full          |            610 |               0.4718 |                0.3674 |  104.845  |  0.1719 |          1.2611 |     0.3311 |         -18.9066 |         81.2861 |                0.2381 |                  63.5741 |
|     22 | day_mid_edge_anchor | none             | none                   |           nan    | none          |                    1.5  | full          |            920 |               0.7115 |                0.5128 |   91.5039 |  0.0995 |          1.1368 |     0.2641 |         -52.7299 |         -4.7501 |               -0.0054 |                   1      |
|     23 | vwap_edge_anchor    | none             | none                   |           nan    | none          |                    2    | full          |            885 |               0.6845 |                0.5012 |   93.89   |  0.1061 |          1.1474 |     0.2712 |         -54.904  |          1      |                0.0018 |                   1      |
|     24 | vwap_edge_anchor    | none             | none                   |             0.55 | none          |                  nan    | full          |            380 |               0.2939 |                0.2452 |  117.209  |  0.3084 |          1.4813 |     0.3421 |         -18.3157 |         24.319  |                0.3357 |                  37.5883 |
|     25 | vwap_edge_anchor    | none             | none                   |             0.55 | none          |                    2    | full          |            380 |               0.2939 |                0.2452 |  117.209  |  0.3084 |          1.4813 |     0.3421 |         -18.3157 |         24.319  |                0.3357 |                  37.5883 |

## Best Row Per Base Anchor

|   rank | base_label           | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   total_r_delta |   profit_factor_delta |   drawdown_improvement_r |
|-------:|:---------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|--------:|----------------:|-----------:|-----------------:|----------------:|----------------------:|-------------------------:|
|      1 | best_cadence_anchor  | none             | reject_vwap_side_slope |             0.65 | none          |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |         104.218 |                0.5333 |                   70.283 |
|      9 | day_mid_edge_anchor  | none             | none                   |           nan    | none          |                       2 | full          |            930 |               0.7193 |                0.5182 |   97.254  |  0.1046 |          1.1438 |     0.2645 |         -52.7299 |           1     |                0.0016 |                    1     |
|    244 | ib_mid30_edge_anchor | none             | none                   |           nan    | none          |                       2 | full          |            869 |               0.6721 |                0.488  |   59.8868 |  0.0689 |          1.0853 |     0.1876 |         -72.536  |           1     |                0.0015 |                    1     |
|     23 | vwap_edge_anchor     | none             | none                   |           nan    | none          |                       2 | full          |            885 |               0.6845 |                0.5012 |   93.89   |  0.1061 |          1.1474 |     0.2712 |         -54.904  |           1     |                0.0018 |                    1     |

## Top Frequency-Fit Rows

|   rank | base_label          | structure_gate   | vwap_acceptance   |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   total_r_delta |   profit_factor_delta |   drawdown_improvement_r |
|-------:|:--------------------|:-----------------|:------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|--------:|----------------:|-----------:|-----------------:|----------------:|----------------------:|-------------------------:|
|    222 | best_cadence_anchor | none             | none              |              nan | none          |                       2 | full          |           1390 |               1.075  |                0.7053 |   26.5585 |  0.0191 |          1.0261 |     0.2612 |         -80.4807 |               3 |                0.0031 |                        2 |
|    264 | best_cadence_anchor | none             | none              |              nan | none          |                     nan | full          |           1393 |               1.0773 |                0.7077 |   23.5585 |  0.0169 |          1.023  |     0.2606 |         -82.4807 |               0 |                0      |                        0 |

## Frequency-Fit Rows With PF >= 1.05

_None._

## Edge-Improved Rows

|   rank | base_label          | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   avg_r |   profit_factor |   win_rate |   max_drawdown_r |   total_r_delta |   profit_factor_delta |   drawdown_improvement_r |
|-------:|:--------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|--------:|----------------:|-----------:|-----------------:|----------------:|----------------------:|-------------------------:|
|      1 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | 10:00-14:00   |            370 |               0.2862 |                0.2622 |   127.777 |  0.3453 |          1.5563 |     0.3703 |         -12.1977 |        104.218  |                0.5333 |                  70.283  |
|      2 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | 10:00-14:00   |            371 |               0.2869 |                0.263  |   126.777 |  0.3417 |          1.5495 |     0.3693 |         -12.1977 |        103.218  |                0.5265 |                  70.283  |
|      3 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | 10:00-14:00   |            368 |               0.2846 |                0.2606 |   122.272 |  0.3323 |          1.5346 |     0.3696 |         -12.1977 |         98.7135 |                0.5116 |                  70.283  |
|      4 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | full          |            564 |               0.4362 |                0.3635 |   114.288 |  0.2026 |          1.3103 |     0.3387 |         -27.0491 |         90.7298 |                0.2873 |                  55.4316 |
|      5 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | 10:00-14:00   |            369 |               0.2854 |                0.2614 |   121.272 |  0.3287 |          1.528  |     0.3686 |         -12.1977 |         97.7135 |                0.505  |                  70.283  |
|      6 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | 10:00-14:00   |            362 |               0.28   |                0.256  |   122.168 |  0.3375 |          1.5437 |     0.3702 |         -13.7745 |         98.609  |                0.5207 |                  68.7062 |
|      7 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | full          |            565 |               0.437  |                0.3643 |   113.288 |  0.2005 |          1.3068 |     0.3381 |         -27.0491 |         89.7298 |                0.2838 |                  55.4316 |
|      8 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | 11:00-15:00   |            563 |               0.4354 |                0.3627 |   113.446 |  0.2015 |          1.308  |     0.3375 |         -27.0491 |         89.8876 |                0.285  |                  55.4316 |
|     10 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | 11:00-15:00   |            564 |               0.4362 |                0.3635 |   112.446 |  0.1994 |          1.3045 |     0.3369 |         -27.0491 |         88.8876 |                0.2815 |                  55.4316 |
|     12 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | full          |            546 |               0.4223 |                0.3503 |   113.605 |  0.2081 |          1.3197 |     0.3407 |         -29.5806 |         90.0464 |                0.2967 |                  52.9001 |
|     13 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | full          |            558 |               0.4316 |                0.3589 |   111.241 |  0.1994 |          1.3054 |     0.3387 |         -27.0491 |         87.6824 |                0.2824 |                  55.4316 |
|     14 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | 11:00-15:00   |            545 |               0.4215 |                0.3496 |   112.763 |  0.2069 |          1.3174 |     0.3394 |         -29.5806 |         89.2042 |                0.2944 |                  52.9001 |
|     15 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | 11:00-15:00   |            557 |               0.4308 |                0.3581 |   110.399 |  0.1982 |          1.303  |     0.3375 |         -27.0491 |         86.8402 |                0.28   |                  55.4316 |
|     16 | best_cadence_anchor | none             | none                   |             0.55 | none          |                    2    | 11:00-15:00   |            592 |               0.4578 |                0.3596 |   107.631 |  0.1818 |          1.2755 |     0.3294 |         -17.9066 |         84.0729 |                0.2525 |                  64.5741 |
|     17 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | full          |            561 |               0.4339 |                0.3612 |   109.784 |  0.1957 |          1.2997 |     0.3387 |         -27.0491 |         86.2251 |                0.2767 |                  55.4316 |
|     18 | best_cadence_anchor | none             | none                   |             0.55 | none          |                  nan    | 11:00-15:00   |            593 |               0.4586 |                0.3604 |   106.631 |  0.1798 |          1.2723 |     0.3288 |         -17.9066 |         83.0729 |                0.2493 |                  64.5741 |
|     19 | best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | 11:00-15:00   |            560 |               0.4331 |                0.3604 |   108.941 |  0.1945 |          1.2974 |     0.3375 |         -27.0491 |         85.3829 |                0.2744 |                  55.4316 |
|     20 | best_cadence_anchor | none             | none                   |             0.55 | none          |                    2    | full          |            609 |               0.471  |                0.3666 |   105.845 |  0.1738 |          1.2642 |     0.3317 |         -18.9066 |         82.2861 |                0.2412 |                  63.5741 |
|     21 | best_cadence_anchor | none             | none                   |             0.55 | none          |                  nan    | full          |            610 |               0.4718 |                0.3674 |   104.845 |  0.1719 |          1.2611 |     0.3311 |         -18.9066 |         81.2861 |                0.2381 |                  63.5741 |
|     24 | vwap_edge_anchor    | none             | none                   |             0.55 | none          |                  nan    | full          |            380 |               0.2939 |                0.2452 |   117.209 |  0.3084 |          1.4813 |     0.3421 |         -18.3157 |         24.319  |                0.3357 |                  37.5883 |

## Positive Rows With >=80% Day Coverage

_None._

## Best By Filter Dimension

### Structure Gate

| base_label           | structure_gate              | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:---------------------|:----------------------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor  | none                        | reject_vwap_side_slope |             0.65 | none          |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |          1.5563 |         -12.1977 |        104.218  |
| best_cadence_anchor  | reject_30m_trend_acceptance | reject_vwap_side_slope |           nan    | none          |                       2 | 10:00-14:00   |            320 |               0.2475 |                0.2336 |   63.0046 |          1.2948 |         -18.8641 |         39.4461 |
| ib_mid30_edge_anchor | require_30m_mixed           | none                   |           nan    | none          |                     nan | full          |            260 |               0.2011 |                0.1825 |   81.8565 |          1.4013 |         -29.921  |         22.9697 |

### VWAP Acceptance

| base_label          | structure_gate   | vwap_acceptance           |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:--------------------|:-----------------|:--------------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| day_mid_edge_anchor | none             | none                      |           nan    | none          |                       2 | full          |            930 |               0.7193 |                0.5182 |   97.254  |          1.1438 |         -52.7299 |          1      |
| day_mid_edge_anchor | none             | reject_vwap_side_distance |           nan    | none          |                     nan | 10:00-14:00   |            141 |               0.109  |                0.1029 |   38.9362 |          1.5387 |          -9.6107 |        -57.3178 |
| best_cadence_anchor | none             | reject_vwap_side_slope    |             0.65 | none          |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |          1.5563 |         -12.1977 |        104.218  |

### Efficiency Max

| base_label          | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:--------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor | none             | none                   |             0.35 | none          |                     nan | 10:00-14:00   |            229 |               0.1771 |                0.1655 |   69.8411 |          1.5009 |         -12.7434 |         46.2826 |
| best_cadence_anchor | none             | none                   |             0.45 | none          |                       2 | 10:00-14:00   |            326 |               0.2521 |                0.2227 |   79.5616 |          1.3912 |         -14.8492 |         56.0031 |
| best_cadence_anchor | none             | none                   |             0.55 | none          |                       2 | 11:00-15:00   |            592 |               0.4578 |                0.3596 |  107.631  |          1.2755 |         -17.9066 |         84.0729 |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |          1.5563 |         -12.1977 |        104.218  |
| day_mid_edge_anchor | none             | none                   |           nan    | none          |                       2 | full          |            930 |               0.7193 |                0.5182 |   97.254  |          1.1438 |         -52.7299 |          1      |

### IB Location

| base_label          | structure_gate   | vwap_acceptance           |   efficiency_max | ib_location            |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:--------------------|:-----------------|:--------------------------|-----------------:|:-----------------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor | none             | reject_vwap_side_slope    |             0.65 | must_be_outside_ib     |                     nan | full          |            418 |               0.3233 |                0.2746 |   95.6339 |          1.3469 |         -23.7295 |         72.0754 |
| day_mid_edge_anchor | none             | reject_vwap_side_distance |           nan    | must_reclaim_inside_ib |                     nan | 11:00-15:00   |             29 |               0.0224 |                0.0224 |   10.1352 |          2.0135 |          -4.8313 |        -86.1188 |
| best_cadence_anchor | none             | reject_vwap_side_slope    |             0.65 | none                   |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |          1.5563 |         -12.1977 |        104.218  |

### Session Range ATR Max

| base_label          | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:--------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.25 | 10:00-14:00   |            362 |               0.28   |                0.256  |   122.168 |          1.5437 |         -13.7745 |         98.609  |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.5  | 10:00-14:00   |            368 |               0.2846 |                0.2606 |   122.272 |          1.5346 |         -12.1977 |         98.7135 |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    1.75 | 10:00-14:00   |            369 |               0.2854 |                0.2614 |   121.272 |          1.528  |         -12.1977 |         97.7135 |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                    2    | 10:00-14:00   |            370 |               0.2862 |                0.2622 |   127.777 |          1.5563 |         -12.1977 |        104.218  |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                  nan    | 10:00-14:00   |            371 |               0.2869 |                0.263  |   126.777 |          1.5495 |         -12.1977 |        103.218  |

### Time Bucket

| base_label          | structure_gate   | vwap_acceptance        |   efficiency_max | ib_location   |   session_range_atr_max | time_bucket   |   total_trades |   avg_trades_per_day |   pct_days_with_trade |   total_r |   profit_factor |   max_drawdown_r |   total_r_delta |
|:--------------------|:-----------------|:-----------------------|-----------------:|:--------------|------------------------:|:--------------|---------------:|---------------------:|----------------------:|----------:|----------------:|-----------------:|----------------:|
| best_cadence_anchor | none             | none                   |             0.45 | none          |                     nan | 10:00-12:00   |             98 |               0.0758 |                0.075  |   47.8597 |          1.9265 |          -5.2336 |         24.3012 |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                       2 | 10:00-14:00   |            370 |               0.2862 |                0.2622 |  127.777  |          1.5563 |         -12.1977 |        104.218  |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                       2 | 11:00-15:00   |            563 |               0.4354 |                0.3627 |  113.446  |          1.308  |         -27.0491 |         89.8876 |
| best_cadence_anchor | none             | reject_vwap_side_slope |             0.65 | none          |                       2 | full          |            564 |               0.4362 |                0.3635 |  114.288  |          1.3103 |         -27.0491 |         90.7298 |

## Best Context Row Year Split

|   year |   trades |   total_r |   avg_r |   win_rate |
|-------:|---------:|----------:|--------:|-----------:|
|   2021 |       39 |      8.89 |  0.2279 |     0.359  |
|   2022 |       60 |     16.49 |  0.2748 |     0.3167 |
|   2023 |       78 |     42.68 |  0.5472 |     0.4103 |
|   2024 |       95 |     43.03 |  0.453  |     0.4    |
|   2025 |       72 |      6.53 |  0.0906 |     0.3333 |
|   2026 |       26 |     10.17 |  0.391  |     0.3846 |

## Summary Read

- Frequency-fit configs (`1-3` trades/day and >=70% day coverage): `2`
- Frequency-fit configs with PF `>=1.05`: `0`
- Edge-improved configs (PF `>=1.15`, positive R delta, >=300 trades): `256`
- Positive configs with `>=80%` day coverage: `0`
- Treat this as a context-screening pass only. Any survivor still needs 1m/1s path validation, train/validation split, and prop-firm risk scoring.

## Diagnostic Read

- The replay audit now matches the prior state-machine anchors exactly, so the context-filter comparisons are apples-to-apples against the previous pass.
- The best overall context row came from the former frequency anchor, not the prior edge anchor: `best_cadence_anchor + reject_vwap_side_slope + efficiency_max=0.65 + session_range_atr_max=2.0 + 10:00-14:00`. It made `370` trades (`0.286/day`, `26.22%` day coverage), `+127.78R`, PF `1.556`, avg R `0.345`, max DD `-12.20R`, and every calendar year in the recent-five-year window was positive.
- The best higher-retention filtered version was the same VWAP-slope/efficiency idea over the full entry window: `564` trades (`0.436/day`, `36.35%` day coverage), `+114.29R`, PF `1.310`, max DD `-27.05R`.
- The one-trade-per-day goal still failed. The only frequency-fit rows were basically ungated cadence-anchor variants: best `>=1/day` row made `1,390` trades (`1.075/day`, `70.53%` day coverage), only `+26.56R`, PF `1.026`, and max DD `-80.48R`.
- The winning context ingredient was not the 30m structure gate or IB reclaim gate. Best non-`none` structure row (`require_30m_mixed`) was useful but sparse: `260` trades, `+81.86R`, PF `1.401`, max DD `-29.92R`. Best IB-gated row was also sparse and inferior to the top no-IB row.
- Practical conclusion: the branch has a real lower-frequency regime-filtered sleeve, especially around VWAP slope rejection plus directional-efficiency control. It is not a daily-trade strategy. Next validation should focus on the top lower-frequency rows with a train/validation split and 1m/1s path checks rather than forcing more trades.

## Artifacts

- Ranked context candidates: `backtesting/data/results/nq_ny_level_reversion_context_filter_recent5_20260629/ranked_context_candidates.csv`
- Best context trades: `backtesting/data/results/nq_ny_level_reversion_context_filter_recent5_20260629/best_context_trades.csv`
- Baseline audit: `backtesting/data/results/nq_ny_level_reversion_context_filter_recent5_20260629/baseline_audit.csv`
- Summary JSON: `backtesting/data/results/nq_ny_level_reversion_context_filter_recent5_20260629/summary.json`
