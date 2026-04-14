# ALPHA_V1 EQHL Additive Portfolio Proxy

- Objective: test the frozen `5m lag24 + 15m EQHL tol1` NQ leg inside the practical ALPHA_V1-style portfolio layer.
- Other legs stay fixed and exact: `NQ_Asia=250`, `ES_Asia=250`, `ES_NY=400`.
- NQ leg risk sweep: `250,300,350,400,450`.
- Stagger policies: same calendar and R-trigger menu used in the prior HTF replacement work.
- Important caveat: the NQ additive EQHL leg is a research-side replay proxy because the live execution engine does not yet support EQHL additive fields. The control HTF leg and the other three legs are exact execution replays.

## Best Rows

### control_exact
- Best `>=80%` payout row: risk `350`, policy `r_trigger_4R`, payout `86.4%`, breach `13.6%`, avg payout `43.7d`.
- Absolute fastest row: risk `350`, policy `r_trigger_4R`, payout `86.4%`, breach `13.6%`, avg payout `43.7d`.

### additive_proxy
- Best `>=80%` payout row: risk `250`, policy `r_trigger_3R`, payout `87.0%`, breach `13.0%`, avg payout `67.5d`.
- Absolute fastest row: risk `250`, policy `r_trigger_3R`, payout `87.0%`, breach `13.0%`, avg payout `67.5d`.

## Full Frontier

| Variant | Risk | Policy | Payout % | Breach % | Avg Payout Days | Fastest | Slowest | Starts |
| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| additive_proxy | 250 | r_trigger_2R | 86.0 | 14.0 | 71.6 | 6 | 223 | 46 |
| additive_proxy | 250 | r_trigger_3R | 87.0 | 13.0 | 67.5 | 12 | 223 | 25 |
| additive_proxy | 250 | r_trigger_4R | 90.0 | 10.0 | 88.0 | 22 | 223 | 11 |
| additive_proxy | 250 | r_trigger_5R | 87.5 | 12.5 | 75.0 | 12 | 179 | 9 |
| additive_proxy | 250 | time_10d | 87.3 | 12.7 | 76.8 | 10 | 230 | 73 |
| additive_proxy | 250 | time_14d | 92.2 | 7.8 | 75.1 | 13 | 212 | 53 |
| additive_proxy | 250 | time_21d | 91.2 | 8.8 | 84.1 | 13 | 231 | 35 |
| additive_proxy | 250 | time_7d | 89.2 | 10.8 | 77.8 | 4 | 231 | 105 |
| additive_proxy | 300 | r_trigger_2R | 86.0 | 14.0 | 71.6 | 6 | 223 | 46 |
| additive_proxy | 300 | r_trigger_3R | 87.0 | 13.0 | 67.5 | 12 | 223 | 25 |
| additive_proxy | 300 | r_trigger_4R | 90.0 | 10.0 | 88.0 | 22 | 223 | 11 |
| additive_proxy | 300 | r_trigger_5R | 87.5 | 12.5 | 75.0 | 12 | 179 | 9 |
| additive_proxy | 300 | time_10d | 87.3 | 12.7 | 76.8 | 10 | 230 | 73 |
| additive_proxy | 300 | time_14d | 92.2 | 7.8 | 75.1 | 13 | 212 | 53 |
| additive_proxy | 300 | time_21d | 91.2 | 8.8 | 84.1 | 13 | 231 | 35 |
| additive_proxy | 300 | time_7d | 89.2 | 10.8 | 77.8 | 4 | 231 | 105 |
| additive_proxy | 350 | r_trigger_2R | 86.0 | 14.0 | 71.6 | 6 | 223 | 46 |
| additive_proxy | 350 | r_trigger_3R | 87.0 | 13.0 | 67.5 | 12 | 223 | 25 |
| additive_proxy | 350 | r_trigger_4R | 90.0 | 10.0 | 88.0 | 22 | 223 | 11 |
| additive_proxy | 350 | r_trigger_5R | 87.5 | 12.5 | 75.0 | 12 | 179 | 9 |
| additive_proxy | 350 | time_10d | 87.3 | 12.7 | 76.8 | 10 | 230 | 73 |
| additive_proxy | 350 | time_14d | 92.2 | 7.8 | 75.1 | 13 | 212 | 53 |
| additive_proxy | 350 | time_21d | 91.2 | 8.8 | 84.1 | 13 | 231 | 35 |
| additive_proxy | 350 | time_7d | 89.2 | 10.8 | 77.8 | 4 | 231 | 105 |
| additive_proxy | 400 | r_trigger_2R | 87.2 | 12.8 | 74.3 | 12 | 223 | 41 |
| additive_proxy | 400 | r_trigger_3R | 84.2 | 15.8 | 70.1 | 15 | 244 | 20 |
| additive_proxy | 400 | r_trigger_4R | 83.3 | 16.7 | 75.4 | 16 | 184 | 13 |
| additive_proxy | 400 | r_trigger_5R | 90.0 | 10.0 | 75.6 | 15 | 184 | 11 |
| additive_proxy | 400 | time_10d | 87.3 | 12.7 | 77.5 | 10 | 230 | 73 |
| additive_proxy | 400 | time_14d | 92.2 | 7.8 | 75.5 | 13 | 212 | 53 |
| additive_proxy | 400 | time_21d | 91.2 | 8.8 | 84.6 | 13 | 231 | 35 |
| additive_proxy | 400 | time_7d | 89.2 | 10.8 | 78.2 | 4 | 231 | 105 |
| additive_proxy | 450 | r_trigger_2R | 87.2 | 12.8 | 74.3 | 12 | 223 | 41 |
| additive_proxy | 450 | r_trigger_3R | 84.2 | 15.8 | 70.1 | 15 | 244 | 20 |
| additive_proxy | 450 | r_trigger_4R | 83.3 | 16.7 | 75.4 | 16 | 184 | 13 |
| additive_proxy | 450 | r_trigger_5R | 90.0 | 10.0 | 75.6 | 15 | 184 | 11 |
| additive_proxy | 450 | time_10d | 87.3 | 12.7 | 77.5 | 10 | 230 | 73 |
| additive_proxy | 450 | time_14d | 92.2 | 7.8 | 75.5 | 13 | 212 | 53 |
| additive_proxy | 450 | time_21d | 91.2 | 8.8 | 84.6 | 13 | 231 | 35 |
| additive_proxy | 450 | time_7d | 89.2 | 10.8 | 78.2 | 4 | 231 | 105 |
| control_exact | 250 | r_trigger_2R | 87.2 | 12.8 | 60.9 | 12 | 132 | 49 |
| control_exact | 250 | r_trigger_3R | 85.7 | 14.3 | 56.4 | 12 | 132 | 30 |
| control_exact | 250 | r_trigger_4R | 87.5 | 12.5 | 58.2 | 14 | 131 | 17 |
| control_exact | 250 | r_trigger_5R | 72.7 | 27.3 | 48.6 | 18 | 129 | 12 |
| control_exact | 250 | time_10d | 94.4 | 5.6 | 57.4 | 3 | 144 | 73 |
| control_exact | 250 | time_14d | 94.1 | 5.9 | 59.2 | 11 | 142 | 53 |
| control_exact | 250 | time_21d | 91.2 | 8.8 | 57.2 | 11 | 132 | 35 |
| control_exact | 250 | time_7d | 90.2 | 9.8 | 54.7 | 4 | 149 | 105 |
| control_exact | 300 | r_trigger_2R | 87.0 | 13.0 | 51.4 | 6 | 148 | 56 |
| control_exact | 300 | r_trigger_3R | 85.2 | 14.8 | 46.2 | 11 | 131 | 28 |
| control_exact | 300 | r_trigger_4R | 88.9 | 11.1 | 48.5 | 15 | 148 | 19 |
| control_exact | 300 | r_trigger_5R | 84.6 | 15.4 | 56.8 | 12 | 133 | 14 |
| control_exact | 300 | time_10d | 91.8 | 8.2 | 52.6 | 3 | 144 | 73 |
| control_exact | 300 | time_14d | 90.2 | 9.8 | 54.0 | 11 | 142 | 53 |
| control_exact | 300 | time_21d | 91.2 | 8.8 | 57.5 | 11 | 132 | 35 |
| control_exact | 300 | time_7d | 87.4 | 12.6 | 51.1 | 2 | 149 | 105 |
| control_exact | 350 | r_trigger_2R | 86.4 | 13.6 | 48.0 | 11 | 135 | 61 |
| control_exact | 350 | r_trigger_3R | 85.7 | 14.3 | 49.0 | 11 | 135 | 36 |
| control_exact | 350 | r_trigger_4R | 86.4 | 13.6 | 43.7 | 11 | 129 | 23 |
| control_exact | 350 | r_trigger_5R | 84.6 | 15.4 | 46.5 | 11 | 147 | 14 |
| control_exact | 350 | time_10d | 93.2 | 6.8 | 50.5 | 3 | 130 | 73 |
| control_exact | 350 | time_14d | 90.2 | 9.8 | 49.3 | 6 | 128 | 53 |
| control_exact | 350 | time_21d | 91.2 | 8.8 | 52.3 | 9 | 128 | 35 |
| control_exact | 350 | time_7d | 88.3 | 11.7 | 48.4 | 2 | 128 | 105 |
| control_exact | 400 | r_trigger_2R | 87.5 | 12.5 | 46.0 | 12 | 131 | 67 |
| control_exact | 400 | r_trigger_3R | 86.7 | 13.3 | 49.5 | 7 | 129 | 31 |
| control_exact | 400 | r_trigger_4R | 81.8 | 18.2 | 51.2 | 12 | 129 | 24 |
| control_exact | 400 | r_trigger_5R | 93.3 | 6.7 | 55.3 | 12 | 131 | 16 |
| control_exact | 400 | time_10d | 93.2 | 6.8 | 48.4 | 3 | 130 | 73 |
| control_exact | 400 | time_14d | 92.3 | 7.7 | 47.8 | 6 | 133 | 53 |
| control_exact | 400 | time_21d | 91.4 | 8.6 | 47.2 | 9 | 132 | 35 |
| control_exact | 400 | time_7d | 90.4 | 9.6 | 46.7 | 2 | 133 | 105 |
| control_exact | 450 | r_trigger_2R | 85.7 | 14.3 | 44.7 | 10 | 127 | 66 |
| control_exact | 450 | r_trigger_3R | 90.6 | 9.4 | 48.1 | 12 | 127 | 34 |
| control_exact | 450 | r_trigger_4R | 84.0 | 16.0 | 45.6 | 10 | 127 | 26 |
| control_exact | 450 | r_trigger_5R | 83.3 | 16.7 | 44.6 | 6 | 127 | 19 |
| control_exact | 450 | time_10d | 93.2 | 6.8 | 46.5 | 3 | 126 | 73 |
| control_exact | 450 | time_14d | 90.4 | 9.6 | 44.8 | 6 | 128 | 53 |
| control_exact | 450 | time_21d | 91.4 | 8.6 | 46.5 | 9 | 128 | 35 |
| control_exact | 450 | time_7d | 88.5 | 11.5 | 43.8 | 2 | 128 | 105 |
