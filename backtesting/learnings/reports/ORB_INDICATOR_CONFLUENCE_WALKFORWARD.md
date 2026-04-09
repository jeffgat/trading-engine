# ORB Indicator Confluence Walk-Forward

## Scope

- Candidate overlays: sma20__aligned_0_10, ema20__aligned_0_10, sma20__aligned_0_20, vwap_ema20__aligned_0_10
- Walk-forward: 12m IS / 3m OOS / 3m step
- Holdout untouched: 2025-01-01+

## Fixed Overlay OOS Summary

- `sma20__aligned_0_20`: OOS avgR +0.143, PF 1.29, trades 6204, totalR +884.6, DD -24.6R
- `vwap_ema20__aligned_0_10`: OOS avgR +0.139, PF 1.28, trades 3797, totalR +528.7, DD -22.3R
- `ema20__aligned_0_10`: OOS avgR +0.135, PF 1.27, trades 4886, totalR +660.1, DD -20.5R
- `sma20__aligned_0_10`: OOS avgR +0.135, PF 1.27, trades 4413, totalR +594.3, DD -21.8R

## Overlay Selection Frequency

- `vwap_ema20__aligned_0_10` selected in 12 folds
- `sma20__aligned_0_20` selected in 12 folds
- `sma20__aligned_0_10` selected in 8 folds

## Selected-By-IS Combined OOS

- Trades: 4952
- Avg R: +0.140
- PF: 1.28
- Total R: +694.5
- Sharpe: 1.73
- Max DD: -24.6R

## Notes

- This is the strongest Bailey-style step completed so far for the overlay shortlist.
- The next clean step is to engine-integrate only the winner or top 2 candidates and rerun pre-holdout structurally.
