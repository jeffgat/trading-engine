# NQ NY HTF-LSI Execution Robustness

- Objective: stress the live exact `HTF_LSI_5M_LAG24` profile under harsher execution assumptions.
- Base stream: exact historical replay through the live execution engine.
- Stress model: per-side slippage plus Monte Carlo missed fills on the exact trade stream.
- Important note: same-bar exit luck is already removed by the live engine, so this packet focuses on extra slippage / queue-miss style degradation rather than re-testing same-bar assumptions.
- Replay window: `2019-01-01` to `2026-03-24`

## Scenario Table

| Scenario | Pre PF | Pre Avg R | Pre Funded EV | Pre Withdrawals | Holdout PF | Holdout Avg R | Holdout Funded EV | Holdout Withdrawals |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| baseline_exact | 1.483 | 0.192 | 332.79 | 5086.40 | 2.152 | 0.379 | 228.95 | 1585.26 |
| slip_1t_side | 1.448 | 0.181 | 331.15 | 4831.36 | 2.123 | 0.372 | 228.95 | 1519.05 |
| slip_2t_side | 1.413 | 0.169 | 318.03 | 4488.72 | 2.094 | 0.365 | 228.95 | 1510.16 |
| slip_1t_side__miss_5pct | 1.451 | 0.182 | 315.05 | 4790.75 | 2.134 | 0.372 | 220.77 | 1401.29 |
| slip_2t_side__miss_10pct | 1.415 | 0.169 | 294.67 | 4392.91 | 2.113 | 0.365 | 214.23 | 1270.62 |
| slip_3t_side__miss_15pct | 1.381 | 0.157 | 277.43 | 3763.64 | 2.120 | 0.364 | 197.48 | 1090.59 |
