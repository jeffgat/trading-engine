# NQ Hunter Classic ORB Ablation (2026-05-02)

## Baseline

Baseline is the balanced stress-gated Hunter candidate: `ema14_tol2_distnone_relegacy_samewin0`.

- Full 10y: 1,008 trades, +164.7R, 41.4% WR, PF 1.17, DD -41.8R
- Stress gate skips `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.

## One-At-A-Time Removal Ranking

| Rank | Removed / Changed | Category | Full Net Delta | Full DD Delta | 2025+ Net Delta | Last 1y Net Delta | Damage Score |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | Remove stress gate | regime | -96.3R | -97.0R | +48.8R | +37.8R | 202.8 |
| 2 | Always 2R target | exit | -64.6R | -19.5R | -27.6R | -8.6R | 94.6 |
| 3 | First trade only | reentry | -44.8R | -1.7R | -25.0R | -21.3R | 58.6 |
| 4 | Remove EMA bias | trend | -10.3R | -1.1R | +7.1R | -1.0R | 17.9 |
| 5 | Remove candle filters | candle | +6.0R | -19.9R | -1.0R | -6.7R | 4.2 |
| 6 | All non-overlap reentries | reentry | -1.9R | +0.0R | +3.6R | +3.6R | 4.1 |
| 7 | Remove body filter | candle | +11.2R | -13.6R | -6.3R | -6.0R | -3.1 |
| 8 | Remove rejection filter | candle | +13.5R | -2.2R | +13.7R | +11.6R | -12.3 |
| 9 | Signal until 13:00 | time | +20.4R | +2.3R | +13.4R | +3.6R | -20.4 |
| 10 | Allow Tuesday | calendar | +27.8R | +4.0R | -15.0R | -17.0R | -24.8 |

Positive damage means the baseline rule was helping. Negative damage means the variant improved the baseline.

## Sensitivity Rows

| Variant | Full 10y | 2025+ | Last 1y | Read |
|---|---:|---:|---:|---|
| Strict EMA tol0 | +162.9R / -40.5R DD | +104.2R | +88.4R | Slightly cleaner pre-holdout/workflow, but gives up recent R. |
| Loose EMA tol5 | +160.2R / -41.8R DD | +113.4R | +92.8R | Mostly neutral; tolerance is not a major lever. |
| Add dist100 cap | +112.5R / -42.2R DD | +86.7R | +77.1R | Too tight; raises recent PF but loses too much R. |
| Add dist150 cap | +142.6R / -45.6R DD | +110.0R | +93.9R | Best cap sensitivity, especially recent, but weaker pre-holdout than no-cap. |
| After each loss | +162.2R / -41.8R DD | +108.5R | +92.8R | Very close to baseline; reentry policy detail is secondary. |
| Same-bar win reentry | +161.7R / -41.8R DD | +108.5R | +92.8R | Adds little and can slightly dilute. |

## Read

- The **stress gate** is the largest structural contributor. Removing it keeps recent performance strong but reopens the old-history damage profile.
- The **wide-stop target reduction** is the biggest non-regime protection rule. Forcing wide-stop trades to keep a 2R target loses `-64.6R` and widens DD by `-19.5R`; the 1R cap is doing real work.
- The **one reentry after loss** is also meaningful. Removing reentries loses `-44.8R` full and `-21.3R` last 1y, so the reentry is part of the edge rather than just extra churn.
- The **15m EMA bias** is a smaller but real entry-quality filter. Removing it loses `-10.3R` full and `-17.4R` pre-holdout, while slightly helping 2025+.
- The **candle-quality package** is more about DD/recent protection than raw R. Removing both adds `+6.0R` full but worsens DD by about `-19.9R` and gives up recent R. Body filter looks more protective than rejection filter; removing rejection alone improved net in this pass, so rejection is a follow-up candidate rather than sacred.
- **Tuesday is a recency tradeoff.** Adding Tuesday improves full 10y (`+27.8R`) and DD (`+4.0R`) but hurts 2025+ (`-15.0R`) and last 1y (`-17.0R`). Do not re-add it just from full-history hindsight.
- **Signal extension to 13:00 is the most interesting follow-up.** It improved full, 2025+, and DD in this one-at-a-time pass, but it changes the strategy's timing profile and needs a workflow-clean test before touching the baseline.
- `dist100` remains a quality trim, not a core edge. If using a distance cap at all, `dist150` is the better research branch.

## Artifacts

- Results packet: `data/results/hunter_classic_ablation_20260502`
- `ablation_metrics.csv`
- `ablation_contribution.csv`
- `selected_trades/*.csv`
