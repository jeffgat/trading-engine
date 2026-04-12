# NQ NY HTF-LSI Lag24 Day Trace — 2025-04-23

- Objective: trace one missing holdout date through the exact live-engine replay and compare it with the research-side setup on that same day.
- Profile: `HTF_LSI_5M_LAG24`
- Replay start used for exact trace: `2016-01-01`

## Research Trades

- Research rows on the day: `1`
- Research filled trades on the day: `1`
- Research `sl` | entry `2025-04-23T13:00:00` | entry_price `18883.75` | htf `2025-04-23T06:00:00` @ `18839.0` | fvg_to_inversion `13` | sweep_to_inversion `14`

## Exact Replay

- Exact filled trades on the day: `1`
- Exact state-change events on the day: `6`
- Exact `sl` | entry `2025-04-23T13:00:02-04:00` | entry_price `18883.75` | htf `2025-04-23T06:00:00-04:00` @ `18839.0` | fvg_to_inversion `13` | sweep_to_inversion `14`

## State Changes

- `2025-04-23T08:30:00-04:00` | state `scanning` | excluded_dow `None` | latest_htf_low `18775.0` @ `2025-04-23T04:00:00-04:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2025-04-23T11:45:00-04:00` | state `waiting_for_inversion` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` @ `2025-04-23T06:00:00-04:00` | fvg `18978.75->19004.75` | fvg_to_inversion `None` | session_filled `0`
- `2025-04-23T12:55:00-04:00` | state `armed_limit` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` @ `2025-04-23T06:00:00-04:00` | fvg `18851.5->18883.75` | fvg_to_inversion `13` | session_filled `0`
- `2025-04-23T13:00:02-04:00` | state `managing` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` @ `2025-04-23T06:00:00-04:00` | fvg `18851.5->18883.75` | fvg_to_inversion `13` | session_filled `1`
- `2025-04-23T15:30:00-04:00` | state `flat` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` @ `2025-04-23T06:00:00-04:00` | fvg `18851.5->18883.75` | fvg_to_inversion `13` | session_filled `1`
- `2025-04-23T23:55:00-04:00` | state `flat` | excluded_dow `None` | latest_htf_low `18740.5` @ `2025-04-23T18:00:00-04:00` | swept `18839.0` @ `2025-04-23T06:00:00-04:00` | fvg `18851.5->18883.75` | fvg_to_inversion `13` | session_filled `1`

## Focus Bars

- Bars shown here are the exact-engine 5m snapshots from one hour before through one hour after the first research filled entry.

- `2025-04-23T12:00:00-04:00` close `18868.0` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:05:00-04:00` close `18820.75` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:10:00-04:00` close `18829.75` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:15:00-04:00` close `18773.5` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:20:00-04:00` close `18771.0` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:25:00-04:00` close `18835.75` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:30:00-04:00` close `18838.25` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:35:00-04:00` close `18877.25` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:40:00-04:00` close `18872.0` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:45:00-04:00` close `18827.5` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:50:00-04:00` close `18871.75` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18978.75->19004.75` | limit `None` | filled `0`
- `2025-04-23T12:55:00-04:00` close `18916.75` | state `armed_limit` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `18883.75` | filled `0`
- `2025-04-23T13:00:00-04:00` close `18917.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:05:00-04:00` close `18938.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:10:00-04:00` close `18941.0` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:15:00-04:00` close `18949.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:20:00-04:00` close `18950.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:25:00-04:00` close `18920.0` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:30:00-04:00` close `18897.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:35:00-04:00` close `18867.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:40:00-04:00` close `18897.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:45:00-04:00` close `18882.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:50:00-04:00` close `18925.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T13:55:00-04:00` close `18925.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`
- `2025-04-23T14:00:00-04:00` close `18912.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `18839.0` @ `2025-04-23T06:00:00-04:00` | swept `18839.0` | fvg `18851.5->18883.75` | limit `None` | filled `1`