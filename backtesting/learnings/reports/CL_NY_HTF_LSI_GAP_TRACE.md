# CL NY HTF-LSI Gap Trace

- Objective: trace representative CL HTF-LSI mismatch days to separate HTF-level publication issues from gap-candidate lifecycle issues.
- Candidate: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- Traced dates: `2016-08-22, 2025-05-20, 2025-06-20`

## Key Findings

- `2016-08-22`: Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap.
- `2025-05-20`: Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap.
- `2025-06-20`: Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap.

## Trade Comparison

| Date | Research | Exact Replay | Diagnosis |
| --- | --- | --- | --- |
| 2016-08-22 | 09:08 @ 47.48 `lvl 16:00 / 48.44` `fvg 11` | 09:08 @ 47.48 `lvl 16:00 / 48.44` `fvg 11` | Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap. |
| 2025-05-20 | 10:02 @ 62.44 `lvl 03:00 / 62.24` `fvg 1` | 10:02 @ 62.44 `lvl 03:00 / 62.24` `fvg 1` | Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap. |
| 2025-06-20 | 08:51 @ 75.35 `lvl 03:00 / 75.55` `fvg 13` | 08:51 @ 75.35 `lvl 03:00 / 75.55` `fvg 13` | Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap. |

## 2016-08-22

- Research trade: `{"entry_time": "2016-08-22T09:08:00", "entry_price": 47.48, "htf_level_time": "2016-08-19T16:00:00", "htf_level_price": 48.44, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 21, "exit_type": "sl"}`
- Exact trade: `{"entry_time": "2016-08-22T09:08:00-04:00", "entry_price": 47.48, "htf_level_time": "2016-08-19T16:00:00-04:00", "htf_level_price": 48.44, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 21, "exit_type": "sl"}`

Research trace:
- `2016-08-22T00:18:00` `DAY_START` `{"active_low": {"instance_id": 275, "price": 48.44, "level_time": "2016-08-19T16:00:00", "publish_time": "2016-08-19T20:00:00"}, "active_high": {"instance_id": 255, "price": 48.23, "level_time": "2016-08-21T20:00:00", "publish_time": "2016-08-22T00:00:00"}}`
- `2016-08-22T08:30:00` `SWEEP_LOW_DETECTED` `{"level": 48.44, "level_time": "2016-08-19T16:00:00", "instance_id": 275}`
- `2016-08-22T08:51:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2016-08-22T08:51:00", "sweep_bar_time": "2016-08-22T08:30:00", "level_time": "2016-08-19T16:00:00", "inv_level": 47.47, "other_bound": 47.36}`
- `2016-08-22T08:52:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T08:52:00", "inv_level": 47.44, "other_bound": 47.35}`
- `2016-08-22T08:54:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T08:54:00", "inv_level": 47.36, "other_bound": 47.31}`
- `2016-08-22T08:55:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T08:55:00", "inv_level": 47.35, "other_bound": 47.3}`
- `2016-08-22T08:56:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T08:56:00", "inv_level": 47.31, "other_bound": 47.26}`
- `2016-08-22T08:57:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T08:57:00", "inv_level": 47.3, "other_bound": 47.26}`
- `2016-08-22T09:08:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2016-08-22T09:08:00", "entry_price": 47.48, "fvg_bar_time": "2016-08-22T08:51:00", "sweep_bar_time": "2016-08-22T08:30:00", "htf_level_time": "2016-08-19T16:00:00", "htf_level_price": 48.44, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 21, "source": "post_sweep"}`
- `2016-08-22T09:25:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:25:00", "inv_level": 47.51, "other_bound": 47.36}`
- `2016-08-22T09:30:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:30:00", "inv_level": 47.48, "other_bound": 47.26}`
- `2016-08-22T09:31:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:31:00", "inv_level": 47.36, "other_bound": 47.15}`
- `2016-08-22T09:33:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:33:00", "inv_level": 47.26, "other_bound": 47.14}`
- `2016-08-22T09:50:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:50:00", "inv_level": 47.29, "other_bound": 47.23}`
- `2016-08-22T09:55:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T09:55:00", "inv_level": 47.28, "other_bound": 47.23}`
- `2016-08-22T10:02:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 276, "price": 47.09, "level_time": "2016-08-22T06:00:00", "publish_time": "2016-08-22T10:00:00"}`
- `2016-08-22T10:02:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T10:02:00", "inv_level": 47.27, "other_bound": 47.12}`
- `2016-08-22T10:10:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T10:10:00", "inv_level": 47.28, "other_bound": 47.21}`
- `2016-08-22T10:15:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T10:15:00", "inv_level": 47.25, "other_bound": 47.19}`
- `2016-08-22T10:23:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2016-08-22T10:23:00", "inv_level": 47.34, "other_bound": 47.19}`

Exact replay trace:
- `2016-08-22T08:30:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=48.44 dir=long bar_count=42350", "active_gap": null, "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2016-08-22T08:30:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_gap", "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": null, "fvg_to_inversion_bars": null}`
- `2016-08-22T08:51:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=47.47 bottom=47.36 size=0.11", "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2016-08-22T08:51:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [{"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": null}`
- `2016-08-22T09:00:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [{"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": null}`
- `2016-08-22T09:08:00-04:00` `FILLED` `{"detail": "dir=long entry=47.48 stop=47.24 tp1=47.91 tp2=48.20 qty=208.0 (close)", "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 21}`
- `2016-08-22T09:08:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T09:31:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 287, "price": 48.44, "level_time": "2016-08-19T16:00:00-04:00", "publish_time": "2016-08-19T20:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T10:02:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 288, "price": 47.09, "level_time": "2016-08-22T06:00:00-04:00", "publish_time": "2016-08-22T10:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T11:25:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 288, "price": 47.09, "level_time": "2016-08-22T06:00:00-04:00", "publish_time": "2016-08-22T10:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T13:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 288, "price": 47.09, "level_time": "2016-08-22T06:00:00-04:00", "publish_time": "2016-08-22T10:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T20:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 289, "price": 46.75, "level_time": "2016-08-22T14:00:00-04:00", "publish_time": "2016-08-22T18:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`
- `2016-08-22T23:59:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 289, "price": 46.75, "level_time": "2016-08-22T14:00:00-04:00", "publish_time": "2016-08-22T18:00:00-04:00"}, "active_sweep_level": 48.44, "pending_gaps": [], "active_gap": {"top": 47.47, "bottom": 47.36, "is_bullish": false, "bar_index": 42360}, "fvg_to_inversion_bars": 11}`

## 2025-05-20

- Research trade: `{"entry_time": "2025-05-20T10:02:00", "entry_price": 62.44, "htf_level_time": "2025-05-20T03:00:00", "htf_level_price": 62.24, "fvg_to_inversion_bars": 1, "sweep_to_inversion_bars": 1, "exit_type": "sl"}`
- Exact trade: `{"entry_time": "2025-05-20T10:02:00-04:00", "entry_price": 62.44, "htf_level_time": "2025-05-20T03:00:00-04:00", "htf_level_price": 62.24, "fvg_to_inversion_bars": 1, "sweep_to_inversion_bars": 1, "exit_type": "sl"}`

Research trace:
- `2025-05-20T00:02:00` `DAY_START` `{"active_low": {"instance_id": 287, "price": 62.66, "level_time": "2025-05-19T18:00:00", "publish_time": "2025-05-19T22:00:00"}, "active_high": {"instance_id": 265, "price": 62.86, "level_time": "2025-05-19T20:00:00", "publish_time": "2025-05-20T00:00:00"}}`
- `2025-05-20T03:01:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 289, "price": 62.69, "level_time": "2025-05-19T23:00:00", "publish_time": "2025-05-20T03:00:00"}`
- `2025-05-20T07:05:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 290, "price": 62.24, "level_time": "2025-05-20T03:00:00", "publish_time": "2025-05-20T07:00:00"}`
- `2025-05-20T09:23:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:23:00", "inv_level": 62.92, "other_bound": 62.84}`
- `2025-05-20T09:24:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:24:00", "inv_level": 62.89, "other_bound": 62.8}`
- `2025-05-20T09:27:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:27:00", "inv_level": 62.78, "other_bound": 62.71}`
- `2025-05-20T09:31:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:31:00", "inv_level": 62.68, "other_bound": 62.54}`
- `2025-05-20T09:32:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:32:00", "inv_level": 62.6, "other_bound": 62.5}`
- `2025-05-20T09:34:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:34:00", "inv_level": 62.53, "other_bound": 62.45}`
- `2025-05-20T09:35:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:35:00", "inv_level": 62.5, "other_bound": 62.33}`
- `2025-05-20T09:39:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:39:00", "inv_level": 62.36, "other_bound": 62.25}`
- `2025-05-20T09:51:00` `SWEEP_LOW_DETECTED` `{"level": 62.24, "level_time": "2025-05-20T03:00:00", "instance_id": 290}`
- `2025-05-20T09:51:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2025-05-20T09:51:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.33, "other_bound": 62.21}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:23:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.92}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:24:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.89}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:27:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.78}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:31:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.68}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:32:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.6}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:34:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.53}`
- `2025-05-20T09:51:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-05-20T09:35:00", "sweep_bar_time": "2025-05-20T09:51:00", "level_time": "2025-05-20T03:00:00", "inv_level": 62.5}`

Exact replay trace:
- `2025-05-20T09:51:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=62.24 dir=long bar_count=39308", "active_gap": null, "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-05-20T09:51:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=62.33 bottom=62.21 size=0.12 (pre-sweep)", "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-05-20T09:51:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, {"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": null}`
- `2025-05-20T10:02:00-04:00` `FILLED` `{"detail": "dir=long entry=62.44 stop=62.19 tp1=62.89 tp2=63.19 qty=200.0 (close)", "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "fvg_to_inversion_bars": 1, "sweep_to_inversion_bars": 1}`
- `2025-05-20T10:02:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": 1}`
- `2025-05-20T10:08:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 296, "price": 62.24, "level_time": "2025-05-20T03:00:00-04:00", "publish_time": "2025-05-20T07:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": 1}`
- `2025-05-20T13:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 297, "price": 62.19, "level_time": "2025-05-20T09:00:00-04:00", "publish_time": "2025-05-20T13:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": 1}`
- `2025-05-20T14:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 298, "price": 62.19, "level_time": "2025-05-20T10:00:00-04:00", "publish_time": "2025-05-20T14:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": 1}`
- `2025-05-20T20:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 300, "price": 62.45, "level_time": "2025-05-20T14:00:00-04:00", "publish_time": "2025-05-20T18:00:00-04:00"}, "active_sweep_level": 62.24, "pending_gaps": [{"top": 62.78, "bottom": 62.71, "is_bullish": false, "bar_index": 39295}, {"top": 62.68, "bottom": 62.54, "is_bullish": false, "bar_index": 39298}, {"top": 62.6, "bottom": 62.5, "is_bullish": false, "bar_index": 39299}, {"top": 62.53, "bottom": 62.45, "is_bullish": false, "bar_index": 39300}, {"top": 62.5, "bottom": 62.33, "is_bullish": false, "bar_index": 39301}, {"top": 62.36, "bottom": 62.25, "is_bullish": false, "bar_index": 39302}], "active_gap": {"top": 62.33, "bottom": 62.21, "is_bullish": false, "bar_index": 39308}, "fvg_to_inversion_bars": 1}`

## 2025-06-20

- Research trade: `{"entry_time": "2025-06-20T08:51:00", "entry_price": 75.35, "htf_level_time": "2025-06-20T03:00:00", "htf_level_price": 75.55, "fvg_to_inversion_bars": 13, "sweep_to_inversion_bars": 16, "exit_type": "sl"}`
- Exact trade: `{"entry_time": "2025-06-20T08:51:00-04:00", "entry_price": 75.35, "htf_level_time": "2025-06-20T03:00:00-04:00", "htf_level_price": 75.55, "fvg_to_inversion_bars": 13, "sweep_to_inversion_bars": 16, "exit_type": "sl"}`

Research trace:
- `2025-06-20T01:54:00` `DAY_START` `{"active_low": {"instance_id": 305, "price": 75.29, "level_time": "2025-06-19T19:00:00", "publish_time": "2025-06-19T23:00:00"}, "active_high": {"instance_id": 257, "price": 76.02, "level_time": "2025-06-19T21:00:00", "publish_time": "2025-06-20T01:00:00"}}`
- `2025-06-20T01:54:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 305, "price": 75.29, "level_time": "2025-06-19T19:00:00", "publish_time": "2025-06-19T23:00:00"}`
- `2025-06-20T05:29:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 306, "price": 75.0, "level_time": "2025-06-20T01:00:00", "publish_time": "2025-06-20T05:00:00"}`
- `2025-06-20T07:14:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 307, "price": 75.55, "level_time": "2025-06-20T03:00:00", "publish_time": "2025-06-20T07:00:00"}`
- `2025-06-20T08:30:00` `SWEEP_LOW_DETECTED` `{"level": 75.55, "level_time": "2025-06-20T03:00:00", "instance_id": 307}`
- `2025-06-20T08:38:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2025-06-20T08:38:00", "sweep_bar_time": "2025-06-20T08:30:00", "level_time": "2025-06-20T03:00:00", "inv_level": 75.33, "other_bound": 75.09}`
- `2025-06-20T08:51:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2025-06-20T08:51:00", "entry_price": 75.35, "fvg_bar_time": "2025-06-20T08:38:00", "sweep_bar_time": "2025-06-20T08:30:00", "htf_level_time": "2025-06-20T03:00:00", "htf_level_price": 75.55, "fvg_to_inversion_bars": 13, "sweep_to_inversion_bars": 16, "source": "post_sweep"}`
- `2025-06-20T09:02:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T09:02:00", "inv_level": 75.35, "other_bound": 75.1}`
- `2025-06-20T09:21:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T09:21:00", "inv_level": 75.28, "other_bound": 75.17}`
- `2025-06-20T09:29:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T09:29:00", "inv_level": 75.2, "other_bound": 74.91}`
- `2025-06-20T09:35:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T09:35:00", "inv_level": 75.05, "other_bound": 74.86}`
- `2025-06-20T09:39:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T09:39:00", "inv_level": 74.8, "other_bound": 74.63}`
- `2025-06-20T10:02:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T10:02:00", "inv_level": 74.95, "other_bound": 74.85}`
- `2025-06-20T11:05:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 308, "price": 74.3, "level_time": "2025-06-20T07:00:00", "publish_time": "2025-06-20T11:00:00"}`
- `2025-06-20T11:06:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T11:06:00", "inv_level": 75.26, "other_bound": 74.92}`
- `2025-06-20T11:23:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T11:23:00", "inv_level": 75.15, "other_bound": 75.05}`
- `2025-06-20T12:03:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T12:03:00", "inv_level": 75.3, "other_bound": 75.19}`
- `2025-06-20T12:21:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T12:21:00", "inv_level": 75.26, "other_bound": 75.12}`
- `2025-06-20T12:27:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T12:27:00", "inv_level": 75.19, "other_bound": 75.06}`
- `2025-06-20T12:28:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-20T12:28:00", "inv_level": 75.1, "other_bound": 75.0}`

Exact replay trace:
- `2025-06-20T08:30:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=75.55 dir=long bar_count=42533", "active_gap": null, "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-06-20T08:30:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_gap", "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": null, "fvg_to_inversion_bars": null}`
- `2025-06-20T08:38:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=75.33 bottom=75.09 size=0.24", "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-06-20T08:38:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [{"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": null}`
- `2025-06-20T08:51:00-04:00` `FILLED` `{"detail": "dir=long entry=75.35 stop=75.09 tp1=75.82 tp2=76.13 qty=192.0 (close)", "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "fvg_to_inversion_bars": 13, "sweep_to_inversion_bars": 16}`
- `2025-06-20T08:51:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": 13}`
- `2025-06-20T08:54:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 321, "price": 75.55, "level_time": "2025-06-20T03:00:00-04:00", "publish_time": "2025-06-20T07:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": 13}`
- `2025-06-20T11:05:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 322, "price": 74.3, "level_time": "2025-06-20T07:00:00-04:00", "publish_time": "2025-06-20T11:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": 13}`
- `2025-06-20T12:59:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 323, "price": 74.62, "level_time": "2025-06-20T09:00:00-04:00", "publish_time": "2025-06-20T13:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": 13}`
- `2025-06-20T14:13:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 323, "price": 74.62, "level_time": "2025-06-20T09:00:00-04:00", "publish_time": "2025-06-20T13:00:00-04:00"}, "active_sweep_level": 75.55, "pending_gaps": [], "active_gap": {"top": 75.33, "bottom": 75.09, "is_bullish": false, "bar_index": 42536}, "fvg_to_inversion_bars": 13}`

## Next Debug Target

- First, compare the live `HtfLevelTracker` output directly against research `compute_htf_unswept_levels` on the same raw 1m window, because two traced days diverged before the same sweep ever formed.
- Second, once HTF level alignment is closed, inspect gap queue ordering on same-minute same-level days like `2025-05-20`, where exact replay appears to keep an older pre-sweep gap alive while research promotes the newer post-sweep gap.
