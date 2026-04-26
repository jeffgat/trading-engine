# NQ Eval Fit 1s Read

- Objective: test which current NQ branches are the cleanest fits for Lucid / Apex-style eval passes.
- Window: `2024-04-01` to `2026-03-24`.
- Targets tested on exact 1-second paths: `1.2R` and `1.5R`.
- Fill handling: each trade's exact fill was inferred as the earliest `1s` touch of the limit price inside the recorded `5m` fill bar.
- Ambiguity handling: if the fill second or any later `1s` bar could support multiple orderings (for example stop and target in the same second), that target read is marked `ambiguous` rather than forced.

## Candidate Summary

| Candidate | Trades | Trades / Month | TP1 in R | Pass 1.2R | Pass 1.5R | Lucid 2-win approx | Retrace <= BE after 1.2R | Retrace <= BE after 1.5R | Median worst R after 1.2R hit | Median worst R after 1.5R hit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ Asia ORB ALPHA_V1 | 136 | 5.73 | 1.80 | 52.9% | 51.5% | 52.2% | 45.8% | 44.3% | 0.20 | 0.26 |
| NQ Asia R9 Restart | 140 | 5.89 | 1.80 | 52.9% | 47.1% | 45.7% | 66.2% | 60.6% | -0.95 | -0.61 |
| NQ Asia-2 phase-one winner | 171 | 7.20 | 2.10 | 48.0% | 43.3% | 40.0% | 48.8% | 40.5% | 0.08 | 0.34 |

## Read

- `NQ Asia ORB ALPHA_V1` is the cleanest `1.5R` pass branch. It has the best exact `1.5R` hit rate and the best giveback profile of the top two Asia candidates.
- `NQ Asia R9 Restart` is the raw `1.2R` leader, but it gives back the most after hitting target. That makes it attractive only if the eval plan explicitly locks the win near the target instead of letting the trade breathe.
- `NQ Asia-2 phase-one winner` is the higher-flow backup. It trails the top two on pass rate, but it resolves more often because it trades more frequently.

