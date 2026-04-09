# ORB Indicator Confluence Follow-Up

## Scope

- Confirmatory follow-up on the strongest phase-1 family: aligned but not stretched.
- Candidates: SMA20, EMA20, VWAP+EMA20.
- Upper bounds tested: 10%, 15%, 20%, 25%, 30% ATR.
- Holdout 2025-01-01+ still untouched.

## Combined Base Book

- Discovery: 6689 trades | avgR=0.135
- Validation: 1909 trades | avgR=0.123

## Best By Indicator

- `ema20__aligned_0_10`: val avgR delta +0.050, retention 65.7%, positive anchors 8/9, positive windows 153/286
- `sma20__aligned_0_10`: val avgR delta +0.057, retention 60.4%, positive anchors 9/9, positive windows 123/265
- `vwap_ema20__aligned_0_10`: val avgR delta +0.041, retention 52.5%, positive anchors 6/8, positive windows 115/225

## Overall Ranking

- `sma20__aligned_0_10`: val avgR delta +0.057, retention 60.4%, pos anchors 9/9, pos windows 123/265
- `ema20__aligned_0_10`: val avgR delta +0.050, retention 65.7%, pos anchors 8/9, pos windows 153/286
- `vwap_ema20__aligned_0_10`: val avgR delta +0.041, retention 52.5%, pos anchors 6/8, pos windows 115/225
- `sma20__aligned_0_20`: val avgR delta +0.038, retention 80.3%, pos anchors 8/9, pos windows 167/300
- `sma20__aligned_0_25`: val avgR delta +0.037, retention 85.3%, pos anchors 7/9, pos windows 162/302
- `sma20__aligned_0_30`: val avgR delta +0.033, retention 87.5%, pos anchors 7/9, pos windows 160/302
- `sma20__aligned_0_15`: val avgR delta +0.033, retention 73.4%, pos anchors 8/9, pos windows 154/297
- `ema20__aligned_0_15`: val avgR delta +0.030, retention 76.3%, pos anchors 8/9, pos windows 159/300
- `vwap_ema20__aligned_0_20`: val avgR delta +0.026, retention 73.2%, pos anchors 7/9, pos windows 148/297
- `ema20__aligned_0_25`: val avgR delta +0.025, retention 85.2%, pos anchors 8/9, pos windows 166/302

## Notes

- This still uses post-trade filtering and should not be treated as a final deployment verdict.
- The next clean step is a true engine-level re-simulation on only the top 1-3 overlays.
