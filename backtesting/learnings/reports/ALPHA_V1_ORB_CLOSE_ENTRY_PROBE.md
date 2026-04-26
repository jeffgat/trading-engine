# ALPHA_V1 ORB Close-Entry Probe

Window: `2016-04-17` to `2026-03-24`. Holdout shown as `2025-01-01+`.

## Takeaway

- Broad screen verdict: do not replace the ALPHA_V1 ORB retest entry with a close-entry rule.
- `fvg_close` kept the FVG requirement but nearly erased the ORB sleeve edge: `+28.3R` vs `+359.5R` baseline, with max DD widening from `-21.2R` to `-54.8R`.
- `breakout_close` helped only the NQ Asia leg in raw R, but the combined sleeve turned negative because ES Asia collapsed toward flat and ES NY became strongly negative.
- The retest appears to be an important quality/liquidity filter, not just a delayed fill mechanic.

## Definitions

- `baseline_retest`: current ALPHA_V1 ORB continuation logic, first valid FVG outside ORB, limit entry on FVG retest.
- `fvg_close`: same valid FVG condition, but market-at-close on the 5m FVG confirmation bar; exits begin on the next bar.
- `breakout_close`: first 5m close outside the ORB in the leg direction; no FVG requirement; exits begin on the next bar.
- Data note: this checkout has `NQ_1s.parquet` but no `NQ_5m` file, so the NQ leg is resampled from 1-second data in-memory for this probe.

## Leg Results

| leg | variant | trades | wr_pct | pf | net_r | max_dd_r | sharpe | neg_years | holdout_trades | holdout_net_r | holdout_dd_r | delta_r | delta_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| nq_asia_orb_long | baseline_retest | 722 | 45.70 | 1.55 | 214 | -10.20 | 3 | 0 | 88 | 41.90 | -6 | 0 | 0 |
| nq_asia_orb_long | fvg_close | 896 | 41 | 1.26 | 135 | -27.60 | 1.56 | 0 | 107 | 15.10 | -8.50 | -78.20 | -17.50 |
| nq_asia_orb_long | breakout_close | 1324 | 42.70 | 1.33 | 252 | -26.10 | 1.97 | 0 | 162 | 58.70 | -5.70 | 38 | -16 |
| es_asia_orb_long | baseline_retest | 1422 | 54.40 | 1.28 | 146 | -12.30 | 1.80 | 0 | 178 | 28.50 | -5.80 | 0 | 0 |
| es_asia_orb_long | fvg_close | 1602 | 52.40 | 1.15 | 90.10 | -21.40 | 0.99 | 3 | 204 | 20.10 | -11.50 | -55.80 | -9.10 |
| es_asia_orb_long | breakout_close | 1975 | 49.50 | 1.03 | 27.40 | -27.90 | 0.24 | 4 | 237 | 15.70 | -7.20 | -118 | -15.60 |
| es_ny_orb_long | baseline_retest | 845 | 61.10 | 1.39 | 128 | -10.90 | 2.13 | 1 | 110 | 20.50 | -9.60 | 0 | 0 |
| es_ny_orb_long | fvg_close | 1052 | 50 | 0.81 | -101 | -128 | -1.46 | 9 | 145 | -25.10 | -26.60 | -228 | -117 |
| es_ny_orb_long | breakout_close | 1371 | 48.40 | 0.72 | -190 | -217 | -2.19 | 7 | 176 | -29.50 | -31.40 | -318 | -206 |

## ORB Sleeve

| variant | trades | net_r | max_dd_r | daily_sharpe | calmar |
| --- | --- | --- | --- | --- | --- |
| baseline_retest | 2989 | 360 | -21.20 | 1.73 | 1.65 |
| fvg_close | 3550 | 28.30 | -54.80 | 0.12 | 0.05 |
| breakout_close | 4670 | -40.60 | -120 | -0.15 | -0.03 |
