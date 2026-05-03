# NQ Hunter Classic Stress Gate Validation (2026-05-02)

## Scope

This is the next-step validation after the initial Hunter Classic regime-gate read. The candidate is locked as:

- Base strategy: canonical Hunter Classic ORB replication, `EMA15C14`, no distance cap
- Gate: skip `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`
- Regime calendar: causal, point-in-time labels from the prior run

Evidence:

- Result packet: `backtesting/data/results/hunter_classic_stress_gate_validation_20260502/`
- Prior gate read: `backtesting/learnings/reports/NQ_HUNTER_CLASSIC_ORB_REGIME_GATE_20260502.md`

## Standalone Results

| Variant | Window | Trades | Net | WR | PF | DD |
|---|---:|---:|---:|---:|---:|---:|
| Ungated | Full 10y | 1,506 | +46.9R | 40.2% | 1.03 | -161.9R |
| Ungated | 2025+ | 195 | +157.0R | 55.4% | 1.54 | -26.8R |
| Ungated | Last 1y | 154 | +130.3R | 55.8% | 1.61 | -26.8R |
| Stress gated | Full 10y | 1,004 | +150.9R | 41.0% | 1.16 | -41.8R |
| Stress gated | 2025+ | 124 | +108.5R | 57.3% | 1.68 | -14.2R |
| Stress gated | Last 1y | 101 | +92.8R | 57.4% | 1.76 | -14.2R |
| Excluded buckets only | Full 10y | 502 | -104.0R | 38.6% | 0.87 | -168.4R |
| Excluded buckets only | 2025+ | 71 | +48.5R | 52.1% | 1.37 | -21.8R |
| Excluded buckets only | Last 1y | 53 | +37.5R | 52.8% | 1.41 | -21.8R |

Full calendar years 2017-2025: 6 of 9 positive. Negative years were:

- 2018: `-5.8R`
- 2019: `-17.7R`
- 2022: `-10.5R`

## Fixed-Gate Annual OOS

No optimization is performed in these folds. Each OOS year applies the locked stress gate after an initial 3-year history window.

| OOS year | Trades | Net | WR | PF | DD |
|---:|---:|---:|---:|---:|---:|
| 2019 | 105 | -17.7R | 31.4% | 0.74 | -26.9R |
| 2020 | 70 | +51.8R | 50.0% | 1.90 | -9.7R |
| 2021 | 121 | +4.8R | 38.8% | 1.04 | -31.9R |
| 2022 | 28 | -10.5R | 42.9% | 0.81 | -24.7R |
| 2023 | 106 | +4.6R | 38.7% | 1.03 | -24.9R |
| 2024 | 133 | +13.5R | 41.4% | 1.08 | -24.2R |
| 2025 | 96 | +52.9R | 54.2% | 1.41 | -14.2R |
| 2026 partial | 28 | +55.7R | 67.9% | 2.78 | -5.2R |

## Monte Carlo

20,000 trade-bootstrap paths over the 1,004 gated trades:

- Median net: `+150.0R`
- 5th percentile net: `+22.4R`
- Median drawdown: `-50.8R`
- 1st percentile drawdown: `-119.7R`
- Probability net negative: `2.8%`
- Probability drawdown worse than `-50R`: `51.9%`

This is the key sizing warning. The gate fixes the historical curve shape, but full-size Hunter still has heavy sequence risk. At 0.25x sizing, the Monte Carlo median drawdown scales to about `-12.7R`, and the 1st percentile drawdown scales to about `-29.9R`.

## ALPHA_V1 Portfolio Fit

Portfolio fit uses frozen ALPHA_V1 daily R from `2016-04-25` to `2026-03-24`. Hunter scale is relative to one baseline leg risk unit.

| Scenario | Total | DD | Sharpe | Calmar | Worst 3m |
|---|---:|---:|---:|---:|---:|
| Baseline | +597.1R | -15.6R | 2.50 | 3.86 | -10.7R |
| Add Hunter 0.25x | +634.0R | -16.5R | 2.59 | 3.88 | -11.9R |
| Add Hunter 0.50x | +670.9R | -17.9R | 2.52 | 3.78 | -13.0R |
| Add Hunter 1.00x | +744.6R | -30.9R | 2.21 | 2.43 | -19.6R |
| ES NY 0.75x + Hunter 0.25x | +602.3R | -15.8R | 2.56 | 3.84 | -12.0R |
| ES NY 0.50x + Hunter 0.50x | +607.6R | -16.5R | 2.44 | 3.71 | -13.8R |

Daily R correlation between Hunter and the existing ALPHA_V1 legs is low:

- NQ NY LSI: `-0.035`
- NQ Asia ORB: `-0.033`
- ES Asia ORB: `-0.025`
- ES NY ORB: `+0.055`

That is good from an independence perspective. The problem is not correlation; it is standalone sequence risk at full size.

## Pipeline Read

- Phase 0, causal regime audit: PASS
- Phase 1, full-calendar attribution: PASS, but post-hoc
- Phase 2, structural: CONDITIONAL; 10y profile is much better, but only 6/9 full years positive
- Phase 3, annual OOS: CONDITIONAL/FAIL for full-risk promotion; 2019 and 2022 remain negative, and 2021/2023 are thin positives
- Phase 4, full-calendar gate test: PASS versus raw Hunter
- Phase 5, 2025+ holdout: PASS for the gated candidate, but the excluded buckets were also positive in the recent hot streak, so the opportunity cost is real
- Monte Carlo/sizing: full-risk NO-GO; 0.25x pilot is the cleaner expression

## Conclusion

Status: CONDITIONAL reduced-risk pilot candidate.

Do not promote Hunter full-size. The best next operating candidate is Hunter stress-gated at `0.25x` risk, optionally paired with ES NY ORB reduced to `0.75x` if the goal is to avoid adding more NY-session gross exposure.

The research thesis remains alive because the gate turns 10y from `+46.9R / -161.9R DD` into `+150.9R / -41.8R DD`, and the ALPHA_V1 correlation profile is genuinely low. The deployment thesis should stay conservative because the yearly OOS record is still lumpy and the full-risk bootstrap drawdown is too large.
