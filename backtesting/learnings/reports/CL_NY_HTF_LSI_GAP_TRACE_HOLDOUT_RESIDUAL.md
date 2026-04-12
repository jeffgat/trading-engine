# CL NY HTF-LSI Gap Trace

- Objective: trace representative CL HTF-LSI mismatch days to separate HTF-level publication issues from gap-candidate lifecycle issues.
- Candidate: `long close 08:30-14:30 rr3.0 tp0.6 gap3.0 htf60 n3 cap2 fvgL100 fvgR10 lag15 atr20`
- Traced dates: `2025-06-23, 2025-10-28, 2026-02-13, 2026-02-20, 2026-03-19`

## Key Findings

- `2025-06-23`: Research found a trade but exact replay did not. This points to a live-engine gating mismatch.
- `2025-10-28`: Research found a trade but exact replay did not. This points to a live-engine gating mismatch.
- `2026-02-13`: Research found a trade but exact replay did not. This points to a live-engine gating mismatch.
- `2026-02-20`: Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap.
- `2026-03-19`: Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap.

## Trade Comparison

| Date | Research | Exact Replay | Diagnosis |
| --- | --- | --- | --- |
| 2025-06-23 | 10:16 @ 73.41 `lvl 04:00 / 73.16` `fvg 11` | none | Research found a trade but exact replay did not. This points to a live-engine gating mismatch. |
| 2025-10-28 | 11:48 @ 60.01 `lvl 04:00 / 59.93` `fvg 13` | none | Research found a trade but exact replay did not. This points to a live-engine gating mismatch. |
| 2026-02-13 | 09:55 @ 62.8 `lvl 14:00 / 62.39` `fvg 5` | none | Research found a trade but exact replay did not. This points to a live-engine gating mismatch. |
| 2026-02-20 | 09:35 @ 66.32 `lvl 20:00 / 66.62` `fvg 5` | 09:35 @ 66.32 `lvl 20:00 / 66.62` `fvg 5` | Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap. |
| 2026-03-19 | 08:40 @ 96.92 `lvl 23:00 / 96.67` `fvg 7` | 08:40 @ 96.92 `lvl 23:00 / 96.67` `fvg 7` | Resolved on the traced entry trade. Exact replay now matches the research HTF level, entry minute, and chosen gap. |

## 2025-06-23

- Research trade: `{"entry_time": "2025-06-23T10:16:00", "entry_price": 73.41, "htf_level_time": "2025-06-23T04:00:00", "htf_level_price": 73.16, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 12, "exit_type": "sl"}`
- Exact trade: `null`

Research trace:
- `2025-06-23T00:00:00` `DAY_START` `{"active_low": {"instance_id": 273, "price": 74.59, "level_time": "2025-06-20T14:00:00", "publish_time": "2025-06-20T18:00:00"}, "active_high": {"instance_id": 245, "price": 76.16, "level_time": "2025-06-22T20:00:00", "publish_time": "2025-06-23T00:00:00"}}`
- `2025-06-23T08:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 274, "price": 73.16, "level_time": "2025-06-23T04:00:00", "publish_time": "2025-06-23T08:00:00"}`
- `2025-06-23T08:35:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T08:35:00", "inv_level": 73.6, "other_bound": 73.51}`
- `2025-06-23T09:19:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:19:00", "inv_level": 74.35, "other_bound": 74.24}`
- `2025-06-23T09:20:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:20:00", "inv_level": 74.23, "other_bound": 74.09}`
- `2025-06-23T09:37:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:37:00", "inv_level": 74.05, "other_bound": 73.96}`
- `2025-06-23T09:38:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:38:00", "inv_level": 73.88, "other_bound": 73.73}`
- `2025-06-23T10:04:00` `SWEEP_LOW_DETECTED` `{"level": 73.16, "level_time": "2025-06-23T04:00:00", "instance_id": 274}`
- `2025-06-23T10:04:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T08:35:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 73.6}`
- `2025-06-23T10:04:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:19:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 74.35}`
- `2025-06-23T10:04:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:20:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 74.23}`
- `2025-06-23T10:04:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:37:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 74.05}`
- `2025-06-23T10:04:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T09:38:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 73.88}`
- `2025-06-23T10:05:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2025-06-23T10:05:00", "sweep_bar_time": "2025-06-23T10:04:00", "level_time": "2025-06-23T04:00:00", "inv_level": 73.39, "other_bound": 72.97}`
- `2025-06-23T10:16:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2025-06-23T10:16:00", "entry_price": 73.41, "fvg_bar_time": "2025-06-23T10:05:00", "sweep_bar_time": "2025-06-23T10:04:00", "htf_level_time": "2025-06-23T04:00:00", "htf_level_price": 73.16, "fvg_to_inversion_bars": 11, "sweep_to_inversion_bars": 12, "source": "post_sweep"}`
- `2025-06-23T10:20:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T10:20:00", "inv_level": 73.09, "other_bound": 73.0}`
- `2025-06-23T12:38:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T12:38:00", "inv_level": 74.08, "other_bound": 73.93}`
- `2025-06-23T12:39:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T12:39:00", "inv_level": 73.89, "other_bound": 73.45}`
- `2025-06-23T12:41:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T12:41:00", "inv_level": 73.21, "other_bound": 72.87}`
- `2025-06-23T12:43:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-06-23T12:43:00", "inv_level": 72.6, "other_bound": 72.29}`

Exact replay trace:
- `2025-06-23T10:04:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=73.16 dir=long bar_count=39546", "active_gap": null, "latest_low": {"instance_id": 290, "price": 73.16, "level_time": "2025-06-23T04:00:00-04:00", "publish_time": "2025-06-23T08:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-06-23T10:04:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=73.60 bottom=73.51 size=0.09 (pre-sweep)", "active_gap": {"top": 73.6, "bottom": 73.51, "is_bullish": false, "bar_index": 39457}, "latest_low": {"instance_id": 290, "price": 73.16, "level_time": "2025-06-23T04:00:00-04:00", "publish_time": "2025-06-23T08:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`

## 2025-10-28

- Research trade: `{"entry_time": "2025-10-28T11:48:00", "entry_price": 60.01, "htf_level_time": "2025-10-28T04:00:00", "htf_level_price": 59.93, "fvg_to_inversion_bars": 13, "sweep_to_inversion_bars": 14, "exit_type": "eod"}`
- Exact trade: `null`

Research trace:
- `2025-10-28T00:00:00` `DAY_START` `{"active_low": {"instance_id": 252, "price": 61.1, "level_time": "2025-10-27T20:00:00", "publish_time": "2025-10-28T00:00:00"}, "active_high": {"instance_id": 264, "price": 61.5, "level_time": "2025-10-27T18:00:00", "publish_time": "2025-10-27T22:00:00"}}`
- `2025-10-28T00:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 252, "price": 61.1, "level_time": "2025-10-27T20:00:00", "publish_time": "2025-10-28T00:00:00"}`
- `2025-10-28T01:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 253, "price": 61.11, "level_time": "2025-10-27T21:00:00", "publish_time": "2025-10-28T01:00:00"}`
- `2025-10-28T08:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 254, "price": 59.93, "level_time": "2025-10-28T04:00:00", "publish_time": "2025-10-28T08:00:00"}`
- `2025-10-28T08:43:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T08:43:00", "inv_level": 60.47, "other_bound": 60.36}`
- `2025-10-28T08:44:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T08:44:00", "inv_level": 60.36, "other_bound": 60.31}`
- `2025-10-28T08:46:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T08:46:00", "inv_level": 60.26, "other_bound": 60.19}`
- `2025-10-28T09:49:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T09:49:00", "inv_level": 60.7, "other_bound": 60.64}`
- `2025-10-28T10:08:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:08:00", "inv_level": 60.62, "other_bound": 60.54}`
- `2025-10-28T10:39:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:39:00", "inv_level": 60.52, "other_bound": 60.46}`
- `2025-10-28T10:41:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:41:00", "inv_level": 60.41, "other_bound": 60.29}`
- `2025-10-28T10:59:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:59:00", "inv_level": 60.1, "other_bound": 60.03}`
- `2025-10-28T11:18:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T11:18:00", "inv_level": 60.13, "other_bound": 60.07}`
- `2025-10-28T11:34:00` `SWEEP_LOW_DETECTED` `{"level": 59.93, "level_time": "2025-10-28T04:00:00", "instance_id": 254}`
- `2025-10-28T11:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:08:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.62}`
- `2025-10-28T11:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:39:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.52}`
- `2025-10-28T11:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:41:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.41}`
- `2025-10-28T11:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T10:59:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.1}`
- `2025-10-28T11:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2025-10-28T11:18:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.13}`
- `2025-10-28T11:35:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2025-10-28T11:35:00", "sweep_bar_time": "2025-10-28T11:34:00", "level_time": "2025-10-28T04:00:00", "inv_level": 60.0, "other_bound": 59.95}`

Exact replay trace:
- `2025-10-28T11:34:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=59.93 dir=long bar_count=39880", "active_gap": null, "latest_low": {"instance_id": 262, "price": 59.93, "level_time": "2025-10-28T04:00:00-04:00", "publish_time": "2025-10-28T08:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2025-10-28T11:34:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=60.62 bottom=60.54 size=0.08 (pre-sweep)", "active_gap": {"top": 60.62, "bottom": 60.54, "is_bullish": false, "bar_index": 39794}, "latest_low": {"instance_id": 262, "price": 59.93, "level_time": "2025-10-28T04:00:00-04:00", "publish_time": "2025-10-28T08:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`

## 2026-02-13

- Research trade: `{"entry_time": "2026-02-13T09:55:00", "entry_price": 62.8, "htf_level_time": "2026-02-12T14:00:00", "htf_level_price": 62.39, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 14, "exit_type": "sl"}`
- Exact trade: `null`

Research trace:
- `2026-02-13T00:01:00` `DAY_START` `{"active_low": {"instance_id": 312, "price": 62.39, "level_time": "2026-02-12T14:00:00", "publish_time": "2026-02-12T18:00:00"}, "active_high": {"instance_id": 250, "price": 63.01, "level_time": "2026-02-12T20:00:00", "publish_time": "2026-02-13T00:00:00"}}`
- `2026-02-13T09:01:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T09:01:00", "inv_level": 62.96, "other_bound": 62.88}`
- `2026-02-13T09:07:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T09:07:00", "inv_level": 62.85, "other_bound": 62.77}`
- `2026-02-13T09:41:00` `SWEEP_LOW_DETECTED` `{"level": 62.39, "level_time": "2026-02-12T14:00:00", "instance_id": 312}`
- `2026-02-13T09:41:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T09:01:00", "sweep_bar_time": "2026-02-13T09:41:00", "level_time": "2026-02-12T14:00:00", "inv_level": 62.96}`
- `2026-02-13T09:41:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T09:07:00", "sweep_bar_time": "2026-02-13T09:41:00", "level_time": "2026-02-12T14:00:00", "inv_level": 62.85}`
- `2026-02-13T09:50:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2026-02-13T09:50:00", "sweep_bar_time": "2026-02-13T09:41:00", "level_time": "2026-02-12T14:00:00", "inv_level": 62.69, "other_bound": 62.62}`
- `2026-02-13T09:55:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2026-02-13T09:55:00", "entry_price": 62.8, "fvg_bar_time": "2026-02-13T09:50:00", "sweep_bar_time": "2026-02-13T09:41:00", "htf_level_time": "2026-02-12T14:00:00", "htf_level_price": 62.39, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 14, "source": "post_sweep"}`
- `2026-02-13T10:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 313, "price": 62.14, "level_time": "2026-02-13T06:00:00", "publish_time": "2026-02-13T10:00:00"}`
- `2026-02-13T10:17:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T10:17:00", "inv_level": 62.67, "other_bound": 62.61}`
- `2026-02-13T11:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 314, "price": 62.3, "level_time": "2026-02-13T07:00:00", "publish_time": "2026-02-13T11:00:00"}`
- `2026-02-13T11:49:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-13T11:49:00", "inv_level": 62.79, "other_bound": 62.72}`
- `2026-02-13T13:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 315, "price": 62.33, "level_time": "2026-02-13T09:00:00", "publish_time": "2026-02-13T13:00:00"}`
- `2026-02-13T15:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 316, "price": 62.44, "level_time": "2026-02-13T11:00:00", "publish_time": "2026-02-13T15:00:00"}`

Exact replay trace:
- `2026-02-13T09:41:00-05:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=62.39 dir=long bar_count=42948", "active_gap": null, "latest_low": {"instance_id": 319, "price": 62.39, "level_time": "2026-02-12T14:00:00-05:00", "publish_time": "2026-02-12T18:00:00-05:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2026-02-13T09:41:00-05:00` `GAP_DETECTED` `{"detail": "type=bearish top=62.96 bottom=62.88 size=0.08 (pre-sweep)", "active_gap": {"top": 62.96, "bottom": 62.88, "is_bullish": false, "bar_index": 42908}, "latest_low": {"instance_id": 319, "price": 62.39, "level_time": "2026-02-12T14:00:00-05:00", "publish_time": "2026-02-12T18:00:00-05:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`

## 2026-02-20

- Research trade: `{"entry_time": "2026-02-20T09:35:00", "entry_price": 66.32, "htf_level_time": "2026-02-19T20:00:00", "htf_level_price": 66.62, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 12, "exit_type": "sl"}`
- Exact trade: `{"entry_time": "2026-02-20T09:35:00-05:00", "entry_price": 66.32, "htf_level_time": "2026-02-19T20:00:00-05:00", "htf_level_price": 66.62, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 12, "exit_type": "sl"}`

Research trace:
- `2026-02-20T00:14:00` `DAY_START` `{"active_low": {"instance_id": 326, "price": 66.62, "level_time": "2026-02-19T20:00:00", "publish_time": "2026-02-20T00:00:00"}, "active_high": {"instance_id": 241, "price": 66.9, "level_time": "2026-02-19T16:00:00", "publish_time": "2026-02-19T20:00:00"}}`
- `2026-02-20T00:14:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 326, "price": 66.62, "level_time": "2026-02-19T20:00:00", "publish_time": "2026-02-20T00:00:00"}`
- `2026-02-20T08:36:00` `SWEEP_LOW_DETECTED` `{"level": 66.62, "level_time": "2026-02-19T20:00:00", "instance_id": 326}`
- `2026-02-20T09:03:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 327, "price": 65.95, "level_time": "2026-02-20T05:00:00", "publish_time": "2026-02-20T09:00:00"}`
- `2026-02-20T09:16:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2026-02-20T09:16:00", "sweep_bar_time": "2026-02-20T08:36:00", "level_time": "2026-02-19T20:00:00", "inv_level": 66.3, "other_bound": 66.15}`
- `2026-02-20T09:35:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2026-02-20T09:35:00", "entry_price": 66.32, "fvg_bar_time": "2026-02-20T09:16:00", "sweep_bar_time": "2026-02-20T08:36:00", "htf_level_time": "2026-02-19T20:00:00", "htf_level_price": 66.62, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 12, "source": "post_sweep"}`
- `2026-02-20T09:49:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T09:49:00", "inv_level": 66.44, "other_bound": 66.28}`
- `2026-02-20T09:59:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T09:59:00", "inv_level": 66.36, "other_bound": 66.29}`
- `2026-02-20T10:03:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:03:00", "inv_level": 66.44, "other_bound": 66.38}`
- `2026-02-20T10:12:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:12:00", "inv_level": 66.54, "other_bound": 66.3}`
- `2026-02-20T10:13:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:13:00", "inv_level": 66.42, "other_bound": 66.25}`
- `2026-02-20T10:21:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:21:00", "inv_level": 66.44, "other_bound": 66.28}`
- `2026-02-20T10:26:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:26:00", "inv_level": 66.24, "other_bound": 66.15}`
- `2026-02-20T10:34:00` `SWEEP_LOW_DETECTED` `{"level": 65.95, "level_time": "2026-02-20T05:00:00", "instance_id": 327}`
- `2026-02-20T10:34:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2026-02-20T10:34:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.04, "other_bound": 65.96}`
- `2026-02-20T10:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T09:49:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.44}`
- `2026-02-20T10:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T09:59:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.36}`
- `2026-02-20T10:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:03:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.44}`
- `2026-02-20T10:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:12:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.54}`
- `2026-02-20T10:34:00` `BEARISH_FVG_PROMOTED_PRE_SWEEP` `{"fvg_bar_time": "2026-02-20T10:13:00", "sweep_bar_time": "2026-02-20T10:34:00", "level_time": "2026-02-20T05:00:00", "inv_level": 66.42}`

Exact replay trace:
- `2026-02-20T08:36:00-05:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=66.62 dir=long bar_count=42772", "active_gap": null, "latest_low": {"instance_id": 337, "price": 66.62, "level_time": "2026-02-19T20:00:00-05:00", "publish_time": "2026-02-20T00:00:00-05:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2026-02-20T08:36:00-05:00` `STATE_CHANGE` `{"raw_state": "waiting_for_gap", "latest_low": {"instance_id": 337, "price": 66.62, "level_time": "2026-02-19T20:00:00-05:00", "publish_time": "2026-02-20T00:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": null, "fvg_to_inversion_bars": null}`
- `2026-02-20T08:59:00-05:00` `STATE_CHANGE` `{"raw_state": "waiting_for_gap", "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": null, "fvg_to_inversion_bars": null}`
- `2026-02-20T09:16:00-05:00` `GAP_DETECTED` `{"detail": "type=bearish top=66.30 bottom=66.15 size=0.15", "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2026-02-20T09:16:00-05:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [{"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}], "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "fvg_to_inversion_bars": null}`
- `2026-02-20T09:35:00-05:00` `FILLED` `{"detail": "dir=long entry=66.32 stop=66.14 tp1=66.64 tp2=66.86 qty=278.0 (close)", "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "fvg_to_inversion_bars": 5, "sweep_to_inversion_bars": 12}`
- `2026-02-20T09:35:00-05:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "fvg_to_inversion_bars": 5}`
- `2026-02-20T09:37:00-05:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "fvg_to_inversion_bars": 5}`
- `2026-02-20T10:34:00-05:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 338, "price": 65.95, "level_time": "2026-02-20T05:00:00-05:00", "publish_time": "2026-02-20T09:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "fvg_to_inversion_bars": 5}`
- `2026-02-20T13:59:00-05:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 339, "price": 65.94, "level_time": "2026-02-20T10:00:00-05:00", "publish_time": "2026-02-20T14:00:00-05:00"}, "active_sweep_level": 66.62, "pending_gaps": [], "active_gap": {"top": 66.3, "bottom": 66.15, "is_bullish": false, "bar_index": 42779}, "fvg_to_inversion_bars": 5}`

## 2026-03-19

- Research trade: `{"entry_time": "2026-03-19T08:40:00", "entry_price": 96.92, "htf_level_time": "2026-03-18T23:00:00", "htf_level_price": 96.67, "fvg_to_inversion_bars": 7, "sweep_to_inversion_bars": 8, "exit_type": "tp1_tp2"}`
- Exact trade: `{"entry_time": "2026-03-19T08:40:00-04:00", "entry_price": 96.92, "htf_level_time": "2026-03-18T23:00:00-04:00", "htf_level_price": 96.67, "fvg_to_inversion_bars": 7, "sweep_to_inversion_bars": 8, "exit_type": "tp1_tp2"}`

Research trace:
- `2026-03-19T00:00:00` `DAY_START` `{"active_low": {"instance_id": 315, "price": 96.82, "level_time": "2026-03-18T15:00:00", "publish_time": "2026-03-18T19:00:00"}, "active_high": {"instance_id": 253, "price": 100.02, "level_time": "2026-03-18T20:00:00", "publish_time": "2026-03-19T00:00:00"}}`
- `2026-03-19T02:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 316, "price": 96.56, "level_time": "2026-03-18T22:00:00", "publish_time": "2026-03-19T02:00:00"}`
- `2026-03-19T03:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00", "publish_time": "2026-03-19T03:00:00"}`
- `2026-03-19T08:32:00` `SWEEP_LOW_DETECTED` `{"level": 96.67, "level_time": "2026-03-18T23:00:00", "instance_id": 317}`
- `2026-03-19T08:33:00` `BEARISH_FVG_POST_SWEEP` `{"fvg_bar_time": "2026-03-19T08:33:00", "sweep_bar_time": "2026-03-19T08:32:00", "level_time": "2026-03-18T23:00:00", "inv_level": 96.81, "other_bound": 96.34}`
- `2026-03-19T08:40:00` `LONG_CANDIDATE_CREATED` `{"entry_time": "2026-03-19T08:40:00", "entry_price": 96.92, "fvg_bar_time": "2026-03-19T08:33:00", "sweep_bar_time": "2026-03-19T08:32:00", "htf_level_time": "2026-03-18T23:00:00", "htf_level_price": 96.67, "fvg_to_inversion_bars": 7, "sweep_to_inversion_bars": 8, "source": "post_sweep"}`
- `2026-03-19T09:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 318, "price": 95.27, "level_time": "2026-03-19T05:00:00", "publish_time": "2026-03-19T09:00:00"}`
- `2026-03-19T09:16:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T09:16:00", "inv_level": 97.19, "other_bound": 96.98}`
- `2026-03-19T09:51:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T09:51:00", "inv_level": 97.39, "other_bound": 96.82}`
- `2026-03-19T10:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 319, "price": 95.74, "level_time": "2026-03-19T06:00:00", "publish_time": "2026-03-19T10:00:00"}`
- `2026-03-19T10:09:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T10:09:00", "inv_level": 97.72, "other_bound": 97.48}`
- `2026-03-19T10:32:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T10:32:00", "inv_level": 98.04, "other_bound": 97.76}`
- `2026-03-19T10:44:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T10:44:00", "inv_level": 97.76, "other_bound": 97.52}`
- `2026-03-19T10:48:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T10:48:00", "inv_level": 97.77, "other_bound": 97.44}`
- `2026-03-19T10:49:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T10:49:00", "inv_level": 97.61, "other_bound": 97.36}`
- `2026-03-19T11:05:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T11:05:00", "inv_level": 97.36, "other_bound": 97.15}`
- `2026-03-19T11:52:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T11:52:00", "inv_level": 100.92, "other_bound": 100.62}`
- `2026-03-19T11:53:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T11:53:00", "inv_level": 100.49, "other_bound": 99.88}`
- `2026-03-19T12:00:00` `ACTIVE_LOW_UPDATED` `{"instance_id": 320, "price": 96.14, "level_time": "2026-03-19T08:00:00", "publish_time": "2026-03-19T12:00:00"}`
- `2026-03-19T12:02:00` `BEARISH_FVG_BUFFERED_PRE_SWEEP` `{"fvg_bar_time": "2026-03-19T12:02:00", "inv_level": 99.04, "other_bound": 98.8}`

Exact replay trace:
- `2026-03-19T08:32:00-04:00` `SWEEP_DETECTED` `{"detail": "source=htf_low level=96.67 dir=long bar_count=44263", "active_gap": null, "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2026-03-19T08:32:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_gap", "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": null, "fvg_to_inversion_bars": null}`
- `2026-03-19T08:33:00-04:00` `GAP_DETECTED` `{"detail": "type=bearish top=96.81 bottom=96.34 size=0.47", "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "fvg_to_inversion_bars": null, "sweep_to_inversion_bars": null}`
- `2026-03-19T08:33:00-04:00` `STATE_CHANGE` `{"raw_state": "waiting_for_inversion", "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [{"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": null}`
- `2026-03-19T08:40:00-04:00` `FILLED` `{"detail": "dir=long entry=96.92 stop=96.14 tp1=98.32 tp2=99.26 qty=64.0 (close)", "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "fvg_to_inversion_bars": 7, "sweep_to_inversion_bars": 8}`
- `2026-03-19T08:40:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 317, "price": 96.67, "level_time": "2026-03-18T23:00:00-04:00", "publish_time": "2026-03-19T03:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T08:59:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 318, "price": 95.27, "level_time": "2026-03-19T05:00:00-04:00", "publish_time": "2026-03-19T09:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T09:59:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 319, "price": 95.74, "level_time": "2026-03-19T06:00:00-04:00", "publish_time": "2026-03-19T10:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T10:59:00-04:00` `STATE_CHANGE` `{"raw_state": "managing", "latest_low": {"instance_id": 319, "price": 95.74, "level_time": "2026-03-19T06:00:00-04:00", "publish_time": "2026-03-19T10:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T11:44:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 319, "price": 95.74, "level_time": "2026-03-19T06:00:00-04:00", "publish_time": "2026-03-19T10:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T11:59:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 320, "price": 96.14, "level_time": "2026-03-19T08:00:00-04:00", "publish_time": "2026-03-19T12:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T12:59:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 321, "price": 96.26, "level_time": "2026-03-19T09:00:00-04:00", "publish_time": "2026-03-19T13:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T13:29:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 321, "price": 96.26, "level_time": "2026-03-19T09:00:00-04:00", "publish_time": "2026-03-19T13:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T15:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 321, "price": 96.26, "level_time": "2026-03-19T09:00:00-04:00", "publish_time": "2026-03-19T13:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`
- `2026-03-19T16:00:00-04:00` `STATE_CHANGE` `{"raw_state": "flat", "latest_low": {"instance_id": 321, "price": 96.26, "level_time": "2026-03-19T09:00:00-04:00", "publish_time": "2026-03-19T13:00:00-04:00"}, "active_sweep_level": 96.67, "pending_gaps": [], "active_gap": {"top": 96.81, "bottom": 96.34, "is_bullish": false, "bar_index": 44264}, "fvg_to_inversion_bars": 7}`

## Next Debug Target

- First, compare the live `HtfLevelTracker` output directly against research `compute_htf_unswept_levels` on the same raw 1m window, because two traced days diverged before the same sweep ever formed.
- Second, once HTF level alignment is closed, inspect gap queue ordering on same-minute same-level days like `2025-05-20`, where exact replay appears to keep an older pre-sweep gap alive while research promotes the newer post-sweep gap.
