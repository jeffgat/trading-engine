# ORB Indicator Confluence Engine Rerun

## Objective

Structural rerun of the two shortlisted fill-time overlays from the prior post-trade exploration.
This pass enforces the overlay inside the simulator at the actual fill bar on the frozen 9-anchor basket.

## Scope

- Pre-holdout only: 2016-01-01 to 2024-12-31
- Final holdout remains untouched: 2025-01-01+
- Variants: base anchors, SMA20 aligned [0,20%) ATR, VWAP+EMA20 aligned [0,10%) ATR

## Aggregate Validation

- `vwap_ema20_aligned_0_10`: trades=1007, avgR=0.164, PF=1.33, totalR=165.1, retention=52.8%, delta avgR vs base=+0.041, positive anchors=7/9
- `sma20_aligned_0_20`: trades=1537, avgR=0.162, PF=1.33, totalR=249.8, retention=80.5%, delta avgR vs base=+0.040, positive anchors=8/9

## Aggregate Pre-Holdout

- `vwap_ema20_aligned_0_10`: trades=4250, avgR=0.143, PF=1.29, totalR=609.7, retention=49.4%, delta avgR vs base=+0.011
- `sma20_aligned_0_20`: trades=6897, avgR=0.143, PF=1.29, totalR=986.9, retention=80.2%, delta avgR vs base=+0.011

## Notes

- This is the first engine-integrated pass. It is more realistic than the earlier post-trade overlay study.
- It still uses the frozen anchor universe and does not touch the 2025+ final holdout.
- `sma20_aligned_0_20` is the cleaner promotion candidate: similar validation lift to `vwap_ema20_aligned_0_10`, but much higher retention and broader non-sparse anchor support.
- `vwap_ema20_aligned_0_10` remains interesting as a secondary challenger, but some of its apparent wins come from thinner validation slices than the SMA20 overlay.
- If one overlay remains clearly positive here, the next step is a proper promotion decision and then a frozen holdout read.
