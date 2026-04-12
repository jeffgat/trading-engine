# NQ NY HTF-LSI Lag24 Day Trace — 2016-01-05

- Objective: trace one missing holdout date through the exact live-engine replay and compare it with the research-side setup on that same day.
- Profile: `HTF_LSI_5M_LAG24`
- Replay start used for exact trace: `2016-01-01`

## Research Trades

- Research rows on the day: `0`
- Research filled trades on the day: `0`

## Exact Replay

- Exact filled trades on the day: `0`
- Exact state-change events on the day: `6`

## State Changes

- `2016-01-05T08:30:00-05:00` | state `scanning` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2016-01-05T08:30:00-05:00` | state `waiting_for_gap` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `4506.0` @ `2016-01-04T20:00:00-05:00` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2016-01-05T08:45:00-05:00` | state `scanning` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2016-01-05T12:00:00-05:00` | state `waiting_for_gap` | excluded_dow `None` | latest_htf_low `4471.75` @ `2016-01-05T07:00:00-05:00` | swept `4471.75` @ `2016-01-05T07:00:00-05:00` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2016-01-05T12:15:00-05:00` | state `scanning` | excluded_dow `None` | latest_htf_low `4471.75` @ `2016-01-05T07:00:00-05:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2016-01-05T15:00:00-05:00` | state `flat` | excluded_dow `None` | latest_htf_low `4471.75` @ `2016-01-05T07:00:00-05:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`

## Focus Bars

- Bars shown here are the exact-engine 5m snapshots from one hour before through one hour after the first research filled entry.

- `2016-01-05T00:00:00-05:00` close `4515.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:05:00-05:00` close `4513.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:10:00-05:00` close `4512.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:15:00-05:00` close `4509.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:20:00-05:00` close `4508.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:25:00-05:00` close `4506.0` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:30:00-05:00` close `4505.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:35:00-05:00` close `4507.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:40:00-05:00` close `4509.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:45:00-05:00` close `4507.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:50:00-05:00` close `4506.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T00:55:00-05:00` close `4507.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:00:00-05:00` close `4506.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:05:00-05:00` close `4505.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:10:00-05:00` close `4501.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:15:00-05:00` close `4501.25` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:20:00-05:00` close `4503.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:25:00-05:00` close `4508.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:30:00-05:00` close `4508.75` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2016-01-05T01:35:00-05:00` close `4513.5` | state `idle` | excluded_today `False` | excluded_dow `None` | latest_htf_low `4506.0` @ `2016-01-04T20:00:00-05:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`