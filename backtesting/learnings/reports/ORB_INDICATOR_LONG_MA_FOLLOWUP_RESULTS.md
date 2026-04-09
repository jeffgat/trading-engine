# ORB Indicator Long-MA Follow-Up

## Scope

- Indicator-set finalists from initial pass: sma100_sma200, sma200, vwap_ema200, vwap_sma200
- Upper bounds tested: 10%, 15%, 20%, 25%, 30% ATR.
- Holdout still untouched for this branch.

## Best By Indicator

- `sma100_sma200__aligned_0_15`: val avgR delta +0.033, retention 17.8%, pos anchors 5/8, pos windows 60/95
- `sma200__aligned_0_20`: val avgR delta +0.005, retention 32.3%, pos anchors 6/9, pos windows 89/216
- `vwap_ema200__aligned_0_20`: val avgR delta +0.004, retention 31.4%, pos anchors 4/9, pos windows 102/212
- `vwap_sma200__aligned_0_20`: val avgR delta +0.036, retention 28.4%, pos anchors 6/9, pos windows 88/180
