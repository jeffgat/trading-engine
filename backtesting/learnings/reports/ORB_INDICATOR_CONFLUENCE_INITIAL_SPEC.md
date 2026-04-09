# ORB Indicator Confluence Initial Research Spec

## Objective

Broad initial exploration of SMA / EMA / VWAP confluence on frozen ORB anchors.
The goal is not parameter optimization. The goal is to detect whether certain broad
distance bands look directionally promising enough to justify deeper follow-up.

## Bailey Posture

- Base strategy parameters are frozen.
- 2025-01-01+ remains untouched final holdout.
- Discovery window: 2016-01-01 to 2022-12-31.
- Validation window: 2023-01-01 to 2024-12-31.
- Overlay rules are coarse buckets, not fine sweeps.
- This pass is heuristic. It uses post-trade overlay filtering, not full engine-level
  re-simulation with the overlay integrated into signal generation.

## Anchor Universe

- `alpha_nq_asia_orb_long`: ALPHA NQ Asia ORB long [ALPHA_V1] | session=Asia | strategy=continuation | direction=long | rr=6.0 | tp1=0.3 | atr_len=5
- `alpha_es_asia_orb_long`: ALPHA ES Asia ORB long [ALPHA_V1] | session=Asia | strategy=continuation | direction=long | rr=1.5 | tp1=0.7 | atr_len=14
- `alpha_es_ny_orb_long`: ALPHA ES NY ORB long [ALPHA_V1] | session=NY | strategy=continuation | direction=long | rr=5.0 | tp1=0.2 | atr_len=7
- `gc_asia1_ungated`: GC Asia-1 ungated [Top Candidates] | session=Asia | strategy=continuation | direction=both | rr=2.5 | tp1=0.6 | atr_len=14
- `rty_ny1`: RTY NY-1 [Top Candidates] | session=NY | strategy=continuation | direction=both | rr=3.5 | tp1=0.6 | atr_len=14
- `es_nya_gated`: ES NY-A gated [Top Candidates] | session=NY | strategy=continuation | direction=both | rr=3.5 | tp1=0.3 | atr_len=14, regime block=bull_medium_vol,sideways_medium_vol
- `nq_asiab_gated`: NQ Asia-B gated [Top Candidates] | session=Asia | strategy=continuation | direction=long | rr=3.5 | tp1=0.6 | atr_len=14, regime block=bull_medium_vol,sideways_medium_vol
- `si_asia1`: SI Asia-1 [Top Candidates] | session=Asia | strategy=continuation | direction=short | rr=2.5 | tp1=0.6 | atr_len=14
- `cl_ldn2`: CL LDN-2 [Top Candidates] | session=LDN | strategy=continuation | direction=long | rr=3.0 | tp1=0.6 | atr_len=14

## Indicator Set

- Single indicators: VWAP, EMA20, EMA50, SMA20, SMA50.
- Combo indicators: VWAP+EMA20, VWAP+EMA50, EMA20+EMA50, VWAP+EMA20+EMA50.
- Indicator values are read from the previous completed 5m bar at each trade fill bar.
- All distances are normalized by prior-day daily ATR.

Signed distance formula:

```text
signed_dist = direction * (entry_price - indicator_prev) / prev_daily_atr
```

Interpretation:

- Positive signed distance = aligned with trade direction.
- Negative signed distance = opposite-side / reversion setup.

## Overlay Families

- `aligned_near`: all indicator distances in `[0.0, 0.20)` ATR.
- `aligned_far`: all indicator distances in `[0.20, +inf)` ATR.
- `reversion_near`: all indicator distances in `[-0.20, 0.0)` ATR.
- `reversion_far`: all indicator distances in `(-inf, -0.20)` ATR.

## Outputs

- Per-anchor rule table with discovery and validation metrics.
- Aggregate cross-anchor rule table.
- Shortlist candidates only when validation improves average R with acceptable retention.

