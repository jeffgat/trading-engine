# NQ NY HTF-LSI Lag24 Day Trace — 2019-05-14

- Objective: trace one missing holdout date through the exact live-engine replay and compare it with the research-side setup on that same day.
- Profile: `HTF_LSI_5M_LAG24`
- Replay start used for exact trace: `2018-01-01`

## Research Trades

- Research rows on the day: `1`
- Research filled trades on the day: `1`
- Research `tp1_eod` | entry `2019-05-14T10:10:00` | entry_price `7381.0` | htf `2019-05-14T04:00:00` @ `7352.5` | fvg_to_inversion `3` | sweep_to_inversion `3`

## Exact Replay

- Exact filled trades on the day: `1`
- Exact state-change events on the day: `7`
- Exact `tp1_eod` | entry `2019-05-14T10:10:33-04:00` | entry_price `7376.5` | htf `2019-05-14T04:00:00-04:00` @ `7352.5` | fvg_to_inversion `18` | sweep_to_inversion `3`

## State Changes

- `2019-05-14T08:30:00-04:00` | state `scanning` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` @ `None` | fvg `None->None` | fvg_to_inversion `None` | session_filled `0`
- `2019-05-14T09:50:00-04:00` | state `waiting_for_inversion` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `None` | session_filled `0`
- `2019-05-14T10:05:00-04:00` | state `armed_limit` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `18` | session_filled `0`
- `2019-05-14T10:10:33-04:00` | state `managing` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `18` | session_filled `1`
- `2019-05-14T10:10:33-04:00` | state `managing` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `18` | session_filled `1`
- `2019-05-14T10:10:33-04:00` | state `managing` | excluded_dow `None` | latest_htf_low `7388.5` @ `2019-05-14T11:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `18` | session_filled `1`
- `2019-05-14T15:45:00-04:00` | state `flat` | excluded_dow `None` | latest_htf_low `7388.5` @ `2019-05-14T11:00:00-04:00` | swept `7352.5` @ `2019-05-14T04:00:00-04:00` | fvg `7371.0->7376.5` | fvg_to_inversion `18` | session_filled `1`

## Focus Bars

- Bars shown here are the exact-engine 5m snapshots from one hour before through one hour after the first research filled entry.

- `2019-05-14T09:10:00-04:00` close `7369.25` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:15:00-04:00` close `7373.5` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:20:00-04:00` close `7368.5` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:25:00-04:00` close `7372.5` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:30:00-04:00` close `7374.0` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:35:00-04:00` close `7384.0` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:40:00-04:00` close `7391.75` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:45:00-04:00` close `7353.5` | state `scanning` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `None` | fvg `None->None` | limit `None` | filled `0`
- `2019-05-14T09:50:00-04:00` close `7360.0` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `0`
- `2019-05-14T09:55:00-04:00` close `7362.5` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `0`
- `2019-05-14T10:00:00-04:00` close `7372.75` | state `waiting_for_inversion` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `0`
- `2019-05-14T10:05:00-04:00` close `7381.5` | state `armed_limit` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `7376.5` | filled `0`
- `2019-05-14T10:10:00-04:00` close `7384.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:15:00-04:00` close `7399.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:20:00-04:00` close `7403.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:25:00-04:00` close `7405.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:30:00-04:00` close `7395.5` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:35:00-04:00` close `7405.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:40:00-04:00` close `7406.0` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:45:00-04:00` close `7403.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:50:00-04:00` close `7398.0` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T10:55:00-04:00` close `7403.0` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T11:00:00-04:00` close `7395.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T11:05:00-04:00` close `7406.25` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`
- `2019-05-14T11:10:00-04:00` close `7416.75` | state `managing` | excluded_today `False` | excluded_dow `None` | latest_htf_low `7352.5` @ `2019-05-14T04:00:00-04:00` | swept `7352.5` | fvg `7371.0->7376.5` | limit `None` | filled `1`