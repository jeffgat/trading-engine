# ORB Indicator Long-MA Initial Research Spec

## Objective

Fresh pre-holdout exploration of long-horizon moving-average confluence on frozen ORB anchors.
This branch extends the earlier SMA20/EMA20 work by testing slower 5m trend references.

## Bailey Posture

- Discovery window: 2016-01-01 to 2022-12-31
- Validation window: 2023-01-01 to 2024-12-31
- Already-opened holdout remains unused for this branch: 2025-01-01+
- Base ORB parameters remain frozen.
- This pass is heuristic only: post-trade overlay filtering on actual filled trades.

## Indicator Set

- Single indicators: SMA100, SMA200, SMA300, EMA100, EMA200, EMA300.
- Combos: VWAP paired with each long MA, same-family long-MA pairs, and same-period SMA/EMA pairs.
- All indicator values come from the previous completed 5m bar at the fill bar.
- Distances are normalized by prior-day daily ATR.

## Anchor Universe

- `alpha_nq_asia_orb_long`: ALPHA NQ Asia ORB long | session=Asia | direction=long
- `alpha_es_asia_orb_long`: ALPHA ES Asia ORB long | session=Asia | direction=long
- `alpha_es_ny_orb_long`: ALPHA ES NY ORB long | session=NY | direction=long
- `gc_asia1_ungated`: GC Asia-1 ungated | session=Asia | direction=both
- `rty_ny1`: RTY NY-1 | session=NY | direction=both
- `es_nya_gated`: ES NY-A gated | session=NY | direction=both, regime block=bull_medium_vol,sideways_medium_vol
- `nq_asiab_gated`: NQ Asia-B gated | session=Asia | direction=long, regime block=bull_medium_vol,sideways_medium_vol
- `si_asia1`: SI Asia-1 | session=Asia | direction=short
- `cl_ldn2`: CL LDN-2 | session=LDN | direction=long

## Rule Families

- aligned_near: [0.0, 0.20) ATR
- aligned_far: [0.20, +inf) ATR
- reversion_near: [-0.20, 0.0) ATR
- reversion_far: (-inf, -0.20) ATR

