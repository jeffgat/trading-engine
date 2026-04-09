# ORB Indicator Confluence Holdout Read

## Objective

Frozen holdout read for the promoted engine-integrated indicator overlays.
This is the first and only 2025+ read for this research branch.

## Scope

- Holdout start: 2025-01-01
- Holdout end in current data: 2026-03-31
- Variants: base anchors, SMA20 aligned [0,20%) ATR, VWAP+EMA20 aligned [0,10%) ATR

## Aggregate Holdout

- `sma20_aligned_0_20`: trades=960, avgR=0.156, PF=1.30, totalR=149.6, retention=80.2%, delta avgR vs base=+0.013, positive anchors=4/9, positive anchors (>=50 trades)=4/9
- `vwap_ema20_aligned_0_10`: trades=530, avgR=0.155, PF=1.29, totalR=82.3, retention=44.3%, delta avgR vs base=+0.013, positive anchors=3/9, positive anchors (>=50 trades)=2/9

## Readout

- Best aggregate holdout transfer: `sma20_aligned_0_20`
- Holdout improvement was modest and quality-focused: both overlays raised avgR by about `+0.013`, but both reduced total R versus the unfilted base because they traded less.
- `sma20_aligned_0_20` kept the cleaner profile on holdout: much higher retention than the combo overlay and better cross-anchor support, even though only `4/9` anchors were positive on avgR.
- This holdout read should be treated as final for this branch. No more threshold tuning off these results.
