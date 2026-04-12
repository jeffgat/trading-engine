# NQ NY HTF-LSI Lag24 Day Trace — 2023-06-05

- Objective: trace one missing holdout date through the exact live-engine replay and compare it with the research-side setup on that same day.
- Profile: `HTF_LSI_5M_LAG24`
- Replay start used for exact trace: `2022-01-01`

## Research Trades

- Research rows on the day: `0`
- Research filled trades on the day: `0`

## Exact Replay

- Exact filled trades on the day: `0`
- Exact state-change events on the day: `5`

## State Changes

- `2023-06-05T08:30:00-04:00` | state `scanning` | excluded_dow `None` | latest_htf_low `14526.0` @ `2023-06-05T02:00:00-04:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2023-06-05T14:30:00-04:00` | state `waiting_for_inversion` | excluded_dow `None` | latest_htf_low `14590.25` @ `2023-06-05T10:00:00-04:00` | swept `14590.25` @ `2023-06-05T10:00:00-04:00` | fvg `14659.5->14671.25` | fvg_to_inversion `None` | session_filled `0`
- `2023-06-05T14:55:00-04:00` | state `armed_limit` | excluded_dow `None` | latest_htf_low `14590.25` @ `2023-06-05T10:00:00-04:00` | swept `14590.25` @ `2023-06-05T10:00:00-04:00` | fvg `14580.25->14607.0` | fvg_to_inversion `4` | session_filled `0`
- `2023-06-05T14:55:00-04:00` | state `flat` | excluded_dow `None` | latest_htf_low `14590.25` @ `2023-06-05T10:00:00-04:00` | swept `14590.25` @ `2023-06-05T10:00:00-04:00` | fvg `14580.25->14607.0` | fvg_to_inversion `4` | session_filled `0`
- `2023-06-05T23:55:00-04:00` | state `flat` | excluded_dow `None` | latest_htf_low `14556.5` @ `2023-06-05T20:00:00-04:00` | swept `14590.25` @ `2023-06-05T10:00:00-04:00` | fvg `14580.25->14607.0` | fvg_to_inversion `4` | session_filled `0`

## Focus Bars

- Bars shown here are the exact-engine 5m snapshots from one hour before through one hour after the first research filled entry.

- `2023-06-05T00:00:00-04:00` close `14529.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:05:00-04:00` close `14524.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:10:00-04:00` close `14523.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:15:00-04:00` close `14524.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:20:00-04:00` close `14522.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:25:00-04:00` close `14519.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:30:00-04:00` close `14523.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:35:00-04:00` close `14520.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:40:00-04:00` close `14518.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:45:00-04:00` close `14520.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:50:00-04:00` close `14523.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T00:55:00-04:00` close `14523.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:00:00-04:00` close `14521.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:05:00-04:00` close `14523.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:10:00-04:00` close `14523.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:15:00-04:00` close `14522.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:20:00-04:00` close `14522.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:25:00-04:00` close `14521.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:30:00-04:00` close `14525.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2023-06-05T01:35:00-04:00` close `14532.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `14512.75` @ `2023-06-04T20:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`