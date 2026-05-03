# NQ Hunter Classic Original Ungated Ablation, 2025+ (2026-05-02)

Baseline is the canonical ungated Hunter EMA15C14 no-distance-cap profile before adding the stress gate.

- Window: `2025-01-01` through `2026-04-24`
- Baseline: 195 trades, +157.3R, 55.4% WR, PF 1.55, DD -26.8R

## 2025+ One-At-A-Time Ranking

| Rank | Changed | Category | Trades | Net | DD | Net Delta | DD Delta | Damage Score |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Add dist100 cap | trend | 127 | +89.7R | -14.5R | -67.5R | +12.3R | 67.5 |
| 2 | Allow Tuesday | calendar | 253 | +107.7R | -51.5R | -49.6R | -24.7R | 62.0 |
| 3 | Add stress gate | regime | 124 | +108.5R | -14.2R | -48.8R | +12.6R | 48.8 |
| 4 | First trade only | reentry | 172 | +145.2R | -27.8R | -12.1R | -1.0R | 12.6 |
| 5 | Add dist150 cap | trend | 172 | +146.9R | -26.0R | -10.4R | +0.8R | 10.4 |
| 6 | Remove EMA bias | trend | 204 | +160.5R | -26.8R | +3.3R | -0.0R | -3.3 |
| 7 | After each loss | reentry | 196 | +162.4R | -26.8R | +5.2R | +0.0R | -5.2 |
| 8 | All non-overlap reentries | reentry | 197 | +166.0R | -26.8R | +8.8R | -0.0R | -8.8 |
| 9 | Remove candle filters | candle | 330 | +171.7R | -22.9R | +14.4R | +4.0R | -14.4 |
| 10 | Remove rejection filter | candle | 239 | +173.7R | -19.0R | +16.4R | +7.8R | -16.4 |
| 11 | Always 2R target | exit | 195 | +182.1R | -35.0R | +24.8R | -8.1R | -20.8 |
| 12 | Remove body filter | candle | 233 | +183.1R | -18.0R | +25.8R | +8.8R | -25.8 |
| 13 | Signal until 13:00 | time | 256 | +186.3R | -25.7R | +29.1R | +1.1R | -29.1 |

Positive damage means the original baseline rule helped 2025+. Negative damage means the variant improved 2025+ versus the ungated original.

## Quick Read

- On 2025+ only, the original ungated Hunter is already extremely strong, so most gates reduce net R by cutting good trades.
- Adding the stress gate cuts `-48.8R` from 2025+ but improves DD by about `+12.6R`; it is a long-history risk repair, not a recent-performance enhancer.
- `dist100` is the most expensive recent gate: it gives up `-67.5R` while improving DD by `+12.3R`. That reinforces the earlier read that distance caps are quality trims, not the core recent edge.
- Tuesday is clearly bad in this recent window: adding Tuesday loses `-49.6R` and worsens DD by `-24.7R`.
- The wide-stop 1R target rule is a tradeoff in 2025+: forcing all wide-stop trades to keep 2R adds `+24.8R` but worsens DD by `-8.1R` and lowers WR.
- The loss reentry still helps, but less dramatically than in the full-history stress-gated pass: first-trade-only loses `-12.1R` in 2025+.
- EMA bias is only mildly restrictive in this hot window: removing it adds `+3.3R` with similar DD. That is useful context but not enough to drop it without the 10y damage check.
- Signal extension to `13:00` is again interesting, adding `+29.1R` in 2025+ with slightly better DD.

## Artifacts

- Results: `data/results/hunter_classic_original_ablation_2025plus_20260502`
- `ablation_metrics_2025plus.csv`
- `ablation_contribution_2025plus.csv`
- `selected_trades/*.csv`
