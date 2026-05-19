# ALPHA_V1 ES Asia-B Direct Compare

- Run slug: `alpha_v1_es_asia_b_direct_compare_20260516`
- Engine path: `execution/src/trader/historical_backtest.py` with temporary ES_Asia-only profiles.
- Window: `2016-04-17` to `2026-03-24`.
- No execution config files were edited.

## Exact Standalone Full Window

| Candidate | Trades | Net R | PF | WR % | DD R | Sharpe | Calmar | Full TP % | TP1-BE % | SL % | EOD % |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Active ALPHA ES Asia ORB | 1426 | 179.17 | 1.15 | 55.05 | -12.47 | 1.94 | 14.36 | 34.78 | 14.03 | 42.71 | 7.57 |
| ES Asia-B original | 911 | 113.65 | 1.15 | 46.98 | -11.55 | 1.66 | 9.84 | 7.03 | 4.61 | 43.47 | 44.57 |
| ES Asia-B constrained target | 911 | 113.54 | 1.15 | 48.52 | -11.95 | 1.75 | 9.50 | 21.41 | 4.17 | 42.59 | 31.50 |

## Exact Recent Windows

| Candidate | Window | Trades | Net R | PF | DD R | Sharpe |
| --- | --- | --- | --- | --- | --- | --- |
| Active ALPHA ES Asia ORB | 2025_plus | 176 | 30.65 | 1.32 | -5.83 | 2.71 |
| Active ALPHA ES Asia ORB | last_1y | 142 | 21.65 | 1.27 | -5.83 | 2.38 |
| ES Asia-B original | 2025_plus | 108 | 37.42 | 1.72 | -4.67 | 4.42 |
| ES Asia-B original | last_1y | 83 | 29.16 | 1.69 | -4.47 | 4.39 |
| ES Asia-B constrained target | 2025_plus | 108 | 31.68 | 1.59 | -4.67 | 4.06 |
| ES Asia-B constrained target | last_1y | 83 | 24.06 | 1.56 | -4.47 | 3.98 |

## Five-Leg Portfolio Replacement Read, 2025

| Variant | Risk | Payout % | Breach % | Open % | Avg PayD | Max CBr | EV/start |
| --- | --- | --- | --- | --- | --- | --- | --- |
| current_active_es_asia | fast_safe | 100.00 | 0.00 | 7.41 | 47.30 | 0 | 312.96 |
| current_active_es_asia | balanced_ny | 84.62 | 15.38 | 3.70 | 27.70 | 4 | 257.41 |
| current_active_es_asia | aggressive_sprint | 84.62 | 15.38 | 3.70 | 21.20 | 4 | 257.41 |
| es_asia_b_original_rr3_tp0p6 | fast_safe | 100.00 | 0.00 | 7.41 | 40.60 | 0 | 312.96 |
| es_asia_b_original_rr3_tp0p6 | balanced_ny | 96.15 | 3.85 | 3.70 | 34.20 | 1 | 312.96 |
| es_asia_b_original_rr3_tp0p6 | aggressive_sprint | 80.77 | 19.23 | 3.70 | 21.00 | 4 | 238.89 |
| es_asia_b_constrained_rr2_tp0p75 | fast_safe | 100.00 | 0.00 | 7.41 | 40.40 | 0 | 312.96 |
| es_asia_b_constrained_rr2_tp0p75 | balanced_ny | 96.15 | 3.85 | 3.70 | 34.80 | 1 | 312.96 |
| es_asia_b_constrained_rr2_tp0p75 | aggressive_sprint | 80.77 | 19.23 | 3.70 | 21.70 | 4 | 238.89 |

## Artifacts

- `backtesting/data/results/alpha_v1_es_asia_b_direct_compare_20260516/window_metrics.csv`
- `backtesting/data/results/alpha_v1_es_asia_b_direct_compare_20260516/portfolio_summary.csv`
- `backtesting/data/results/alpha_v1_es_asia_b_direct_compare_20260516/exact_trades.csv`
- `backtesting/data/results/alpha_v1_es_asia_b_direct_compare_20260516/summary.json`
