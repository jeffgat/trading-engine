# NQ NY HTF-LSI Gated Count Tie-Break

- Objective: test whether the new higher-count `5m` HTF-LSI candidates become more promotable when paired with a regime gate, while keeping the `2025-04-01+` holdout closed.
- Reference branch: promoted `5m lag24` long-only HTF-LSI lead.
- Gate candidates were chosen from actual pre-holdout regime attribution on the promoted lead. The only useful gate was `skip bear_high_vol`; the old medium-vol gate remained a loser for this branch.

## Fixed-Split Gate Check

| Candidate | Gate | Pre/Yr | Val/Yr | Val PF | Val Avg R | Val Calmar |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `gap3.0 right2 lag24` | none | 54.7 | 56.5 | 1.597 | 0.268 | 6.382 |
| `gap3.0 right2 lag24` | `skip bear_high_vol` | 47.4 | 54.3 | 1.644 | 0.289 | 8.138 |
| `gap2.5 right2 lag0` | none | 66.4 | 69.0 | 1.668 | 0.265 | 7.328 |
| `gap2.5 right2 lag0` | `skip bear_high_vol` | 58.0 | 66.3 | 1.713 | 0.283 | 8.117 |
| `gap2.5 right3 lag0` | none | 70.2 | 71.2 | 1.569 | 0.243 | 6.457 |
| `gap2.5 right3 lag0` | `skip bear_high_vol` | 61.5 | 68.5 | 1.607 | 0.260 | 7.001 |

## Pre-Holdout Stitched OOS Tie-Break

`36m IS / 12m OOS / 12m step`, same standard used for the main HTF-LSI promotion path.

| Candidate | Combined OOS Trades | PF | Avg R | Calmar | Max DD R | Total R |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `lag24` ungated lead | 330 | 1.347 | 0.162 | 4.849 | -11.01 | 53.39 |
| `gap2.5 right2 lag0 + skip bear_high_vol` | 339 | 1.408 | 0.176 | 6.332 | -9.44 | 59.81 |
| `gap2.5 right3 lag0 + skip bear_high_vol` | 359 | 1.347 | 0.155 | 5.427 | -10.23 | 55.50 |

## Read

- `skip bear_high_vol` is the only regime gate worth carrying forward for this long-only HTF-LSI family.
- The quality winner is `gap2.5 right2 lag0 + skip bear_high_vol`. It beat the promoted `lag24` lead on stitched OOS PF, avg R, Calmar, drawdown, and total R, while still keeping validation flow near the target band.
- The count-preserving sibling is `gap2.5 right3 lag0 + skip bear_high_vol`. It kept the branch closer to the original `60-80` trades/year objective, but its stitched OOS quality was weaker than the `right2` gated row.
- Holdout remains untouched. The next honest step is to freeze those two gated count candidates as a mini-shortlist and only then decide whether either deserves a one-time holdout read against the current `lag24` operating lead.
