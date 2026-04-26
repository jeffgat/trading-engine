# Promising ORB Close-Entry Probe

Window: `2016-04-17` to `2026-03-24`. Holdout shown as `2025-01-01+`.

## Takeaway

- `fvg_close` is a NO-GO across this broader candidate set; it either loses edge outright or worsens drawdown enough to be uninteresting.
- `breakout_close` is still a NO-GO for both GC candidates. It turns `GC NY R3` and `GC Asia-1` structurally negative on full history.
- `NQ Asia-2 breakout_close` is the only candidate worth follow-up: full-history R improved from `+177.8R` to `+285.5R`, and holdout R improved from `+38.3R` to `+71.4R`, but max DD widened from `-17.5R` to `-24.0R` and Sharpe fell from `1.95` to `1.70`.
- Practical read: close-entry remains rejected as a general replacement; the one live thread is a separate NQ Asia-2 high-flow breakout-close branch that needs risk/regime/prop validation before it can matter.

## Scope

- Candidates: `NQ Asia-2 backup`, `GC NY R3 paused`, `GC Asia-1 diversifier`.
- Variants match the ALPHA_V1 probe: baseline retest, FVG confirmation close, and first breakout close with no FVG requirement.
- Regime gates are not applied here; this is a broad entry-mechanics screen.

## Results

| leg | variant | trades | wr_pct | pf | net_r | max_dd_r | sharpe | neg_years | holdout_trades | holdout_net_r | holdout_dd_r | delta_r | delta_dd |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| NQ Asia-2 backup | baseline_retest | 951 | 40.60 | 1.32 | 178 | -17.50 | 1.95 | 0 | 115 | 38.30 | -6 | 0 | 0 |
| NQ Asia-2 backup | fvg_close | 1165 | 38.70 | 1.22 | 155 | -25.40 | 1.40 | 2 | 137 | 18.90 | -8.50 | -22.50 | -7.90 |
| NQ Asia-2 backup | breakout_close | 1739 | 39.20 | 1.27 | 286 | -24 | 1.70 | 1 | 209 | 71.40 | -7.50 | 108 | -6.50 |
| GC NY R3 paused | baseline_retest | 617 | 31 | 1.36 | 154 | -15.10 | 1.86 | 1 | 68 | 39.30 | -10.40 | 0 | 0 |
| GC NY R3 paused | fvg_close | 754 | 24.70 | 0.95 | -28.30 | -74.90 | -0.31 | 5 | 92 | 20.70 | -11.40 | -182 | -59.80 |
| GC NY R3 paused | breakout_close | 1287 | 25.30 | 0.95 | -43 | -86.50 | -0.28 | 7 | 160 | 14.40 | -15 | -196 | -71.50 |
| GC Asia-1 diversifier | baseline_retest | 1225 | 45.30 | 1.17 | 115 | -21 | 1.17 | 3 | 149 | 13.30 | -11.60 | 0 | 0 |
| GC Asia-1 diversifier | fvg_close | 1889 | 42.50 | 0.94 | -67.70 | -91.10 | -0.48 | 8 | 240 | 16.10 | -9.50 | -182 | -70.20 |
| GC Asia-1 diversifier | breakout_close | 2419 | 41.60 | 0.91 | -120 | -124 | -0.66 | 9 | 301 | -31.10 | -33.20 | -235 | -103 |
