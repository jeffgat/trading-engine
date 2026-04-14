# NQ NY EQHL-LSI Short-Only Discovery

- Objective: isolate the EQHL family on the short side and answer whether NQ NY EQHL-driven HTF-LSI has any real short-only edge before spending downstream promotion time.
- Method: staged short-only discovery.
- Stage 1: `2m` and `5m` base entries across EQHL source TF `{5m,15m,60m}`, tolerance `{0,1,2,4}`, touches `{2,3}`, entry mode `{fvg_limit,close}`, and entry end `{11:00,13:00,15:00}`.
- Stage 2: focused `1m` follow-up only around the surviving family: `5m EQHL`, `touches=2`, tolerance `{0,1,2}`, entry mode `{fvg_limit,close}`, entry end `{11:00,13:00,15:00}`.

## Summary

- Shorts are not dead, but they are much narrower than the long-side EQHL family.
- The live short rows clustered around exact `5m EQHL` sweeps, not relative matching.
- `1m` did not transfer the short edge at all.

## Stage 1 Verdict

- Configs tested: `288`
- Alive rows: `6`
- Diagnostic only: `44`
- Weak/dead: `238`

### Alive rows

| Candidate | Pre trades | Pre PF | Pre Avg R | Val trades | Val PF | Val Avg R | Val Calmar |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `5m -> 5m EQHL tol0 touches2 short fvg_limit end13:00` | 164 | 1.272 | 0.119 | 25 | 2.250 | 0.359 | 2.917 |
| `5m -> 5m EQHL tol0 touches2 short close end15:00` | 228 | 1.158 | 0.072 | 35 | 1.709 | 0.221 | 1.668 |
| `5m -> 5m EQHL tol0 touches2 short close end13:00` | 185 | 1.198 | 0.094 | 27 | 1.438 | 0.181 | 1.053 |
| `2m -> 5m EQHL tol0 touches2 short fvg_limit end15:00` | 260 | 1.223 | 0.108 | 43 | 1.041 | 0.064 | 0.415 |
| `2m -> 5m EQHL tol0 touches2 short close end15:00` | 275 | 1.118 | 0.053 | 48 | 1.031 | 0.039 | 0.230 |
| `5m -> 15m EQHL tol2 touches2 short close end13:00` | 199 | 1.066 | 0.028 | 34 | 1.136 | 0.032 | 0.205 |

## Structural Read

- `5m EQHL` dominated the short-side survivors: `5` of `6` alive rows.
- Exact matching dominated: `5` of `6` alive rows used `tol=0`.
- Every alive row used `touches=2`.
- `5m` clearly beat `2m` on quality even though the `2m` rows had more sample.
- `15m` was only marginally alive, and `60m` produced no serious short-side branch worth promoting.

This is the opposite of the long-side EQHL family, where relative matching (`1-2` ticks) was the healthier read. For shorts, exact equal highs matter more than approximate matching.

## Stage 2 Verdict

- Configs tested: `18`
- Timeframe: `1m`
- Result: `0` alive, `0` diagnostic-only, `10` weak, `8` dead

Best `1m` row:

- `1m -> 5m EQHL tol0 touches2 short fvg_limit end15:00`
- Pre-holdout: `277` trades, PF `1.097`, avg R `0.048`
- Validation: `53` trades, PF `0.786`, avg R `-0.128`, Calmar `-0.959`

So the short EQHL edge does not transfer down into `1m`.

## Conclusion

- The only serious short-only EQHL branch worth remembering is the `5m entry / 5m EQHL / tol0 / touches2 / short` family.
- The best current short lead is `5m -> 5m EQHL tol0 touches2 short fvg_limit end13:00`.
- `2m` stays alive only as a weaker secondary branch.
- `1m` should be closed on the short side.
- This is enough to answer the short-only research question. It is not enough to justify diverting into a full short downstream promotion path before finishing phase two on the stronger main branch.

## Artifacts

- Stage 1: `backtesting/data/results/nq_ny_eqhl_lsi_broad_discovery_short_only_stage1/`
- Stage 2: `backtesting/data/results/nq_ny_eqhl_lsi_broad_discovery_short_only_1m_focus/`
