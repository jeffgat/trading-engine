#!/usr/bin/env python3
"""Focused day traces for CL NY HTF-LSI research vs exact replay mismatches."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
EXEC_ROOT = ROOT.parent / "execution"
EXEC_SRC = EXEC_ROOT / "src"
EXEC_SCRIPTS = EXEC_ROOT / "scripts"

for path in (ROOT / "src", Path(__file__).resolve().parent, EXEC_SRC, EXEC_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_cl_ny_htf_lsi_exact_replay import (  # noqa: E402
    EXEC_MIN_TICK,
    EXEC_POINT_VALUE,
    EXEC_RISK_USD,
    EXEC_TICKER,
    FULL_START,
    HTF_LSI_VARIANT,
    PROFILE_NAME,
    SESSION_NAME,
    _build_events,
    _load_candidate,
)
from run_cross_asset_htf_lsi_broad_discovery import build_config, load_timeframe_data  # noqa: E402
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.export import results_to_dict  # noqa: E402
from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402
from orb_backtest.signals.fvg import detect_fvg_no_orb  # noqa: E402
from orb_backtest.signals.htf_levels import compute_htf_unswept_levels  # noqa: E402
from orb_backtest.signals.session import compute_session_days, compute_session_masks  # noqa: E402
from trader.broker import MultiBroker, TradersPostClient  # noqa: E402
from trader.feed import ATRCalculator, DailyHistoryTracker, ET  # noqa: E402
from trader.gates import set_daily_history_provider  # noqa: E402
from trader.historical_backtest import (  # noqa: E402
    ReplayRecorder,
    TickCache,
    _active_for_ticks,
    _read_parquet_frame,
    _seed_daily_bars,
)
from trader.lsi_engine import LSIEngine  # noqa: E402


TRACE_DATES = ("2016-08-22", "2025-05-20", "2025-06-20")
LOOKBACK_DAYS = 45

OUTPUT_DIR = ROOT / "data" / "results" / "cl_ny_htf_lsi_gap_trace"


def _output_json(tag: str) -> Path:
    suffix = "" if tag == "gap_trace" else f"_{tag}"
    return OUTPUT_DIR / f"trace_summary{suffix}.json"


def _report_path(tag: str) -> Path:
    suffix = "" if tag == "gap_trace" else f"_{tag.upper()}"
    return ROOT / "learnings" / "reports" / f"CL_NY_HTF_LSI_GAP_TRACE{suffix}.md"


def _slice_window(df: pd.DataFrame, start: str, end_inclusive: str) -> pd.DataFrame:
    end_exclusive = (pd.Timestamp(end_inclusive) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    return df.loc[(df.index >= start) & (df.index < end_exclusive)].copy()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    return ts.isoformat()


def _hhmm(ts: str | None) -> str | None:
    if not ts:
        return None
    return pd.Timestamp(ts).strftime("%H:%M")


def _serialize_gap(gap) -> dict[str, Any] | None:
    if gap is None:
        return None
    return {
        "top": round(float(gap.top), 4),
        "bottom": round(float(gap.bottom), 4),
        "is_bullish": bool(gap.is_bullish),
        "bar_index": int(gap.bar_index),
    }


def _serialize_exact_level(level) -> dict[str, Any] | None:
    if level is None:
        return None
    return {
        "instance_id": int(level.instance_id),
        "price": round(float(level.price), 4),
        "level_time": str(level.level_time),
        "publish_time": str(level.publish_time),
    }


def _candidate_config(candidate: dict):
    return build_config(
        symbol="CL",
        timeframe=str(candidate["timeframe"]),
        direction_filter=str(candidate["direction_filter"]),
        entry_mode=str(candidate["entry_mode"]),
        entry_start=str(candidate["entry_start"]),
        entry_end=str(candidate["entry_end"]),
        rr=float(candidate["rr"]),
        tp1_ratio=float(candidate["tp1_ratio"]),
        min_gap_atr_pct=float(candidate["min_gap_atr_pct"]),
        atr_length=int(candidate["atr_length"]),
        htf_level_tf_minutes=int(candidate["htf_level_tf_minutes"]),
        htf_n_left=int(candidate["htf_n_left"]),
        htf_trade_max_per_session=int(candidate["htf_trade_max_per_session"]),
        lsi_fvg_window_left=int(candidate["lsi_fvg_window_left"]),
        lsi_fvg_window_right=int(candidate["lsi_fvg_window_right"]),
        max_fvg_to_inversion_bars=int(candidate["max_fvg_to_inversion_bars"]),
        min_stop_points=float(candidate["min_stop_points"]),
        min_tp1_points=float(candidate["min_tp1_points"]),
        name="CL NY HTF_LSI gap trace",
    )


def _research_trades_for_day(
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame | None,
    signal_df_1m: pd.DataFrame,
    config,
    trace_date: str,
) -> list[dict[str, Any]]:
    maps = build_maps(df_base)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    trades = run_backtest(
        df_base,
        config,
        start_date=df_base.index[0].strftime("%Y-%m-%d"),
        end_date=(df_base.index[-1] + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    rows = results_to_dict(
        trades,
        config,
        include_trades=True,
        include_equity_curve=False,
    )["trades"]
    return [row for row in rows if row["date"] == trace_date and row.get("exit_type") != "no_fill"]


def _trace_research_day(
    trace_date: str,
    candidate: dict,
    df_base_all: pd.DataFrame,
    df_1m_all: pd.DataFrame,
    df_1s_all: pd.DataFrame | None,
    signal_df_1m_all: pd.DataFrame,
) -> dict[str, Any]:
    target = pd.Timestamp(trace_date)
    window_start = (target - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    window_end = trace_date

    df_base = _slice_window(df_base_all, window_start, window_end)
    df_1m = _slice_window(df_1m_all, window_start, window_end)
    signal_df_1m = _slice_window(signal_df_1m_all, window_start, window_end)
    df_1s = _slice_window(df_1s_all, window_start, window_end) if df_1s_all is not None else None

    config = _candidate_config(candidate)
    session = config.sessions[0]
    trades = _research_trades_for_day(df_base, df_1m, df_1s, signal_df_1m, config, trace_date)

    timestamps = df_base.index
    masks = compute_session_masks(timestamps, session)
    _new_session_day, session_day_id = compute_session_days(timestamps, session)
    daily_atr = compute_daily_atr(df_base, config.atr_length)
    fvg = detect_fvg_no_orb(
        df_base["high"].to_numpy(dtype=float),
        df_base["low"].to_numpy(dtype=float),
        daily_atr,
        session.min_gap_atr_pct,
    )
    htf_levels = compute_htf_unswept_levels(
        df_base,
        signal_df_1m,
        tf_minutes=config.htf_level_tf_minutes,
        n_left=config.htf_n_left,
    )

    valid_long = fvg["long_fvg"] & masks["in_entry"] & masks["in_rth"]
    valid_short = fvg["short_fvg"] & masks["in_entry"] & masks["in_rth"]

    dates = timestamps.date
    close = df_base["close"].to_numpy(dtype=float)
    high = df_base["high"].to_numpy(dtype=float)
    low = df_base["low"].to_numpy(dtype=float)

    active_low_price = htf_levels["active_low_price"]
    active_low_ids = htf_levels["active_low_instance_id"]
    active_low_times = htf_levels["active_low_level_time"]
    active_high_price = htf_levels["active_high_price"]
    active_high_ids = htf_levels["active_high_instance_id"]
    active_high_times = htf_levels["active_high_level_time"]
    active_low_publish = htf_levels["active_low_publish_time"]
    active_high_publish = htf_levels["active_high_publish_time"]

    short_fvg_top = fvg["short_fvg_top"]
    short_fvg_bottom = fvg["short_entry_price"]
    short_gap_size = fvg["short_gap_size"]
    long_fvg_bottom = fvg["long_fvg_bottom"]
    long_fvg_top = fvg["long_entry_price"]
    long_gap_size = fvg["long_gap_size"]

    take_longs = config.direction_filter in ("both", "long")
    take_shorts = config.direction_filter in ("both", "short")

    detected_bullish_fvgs: list[tuple[int, float, float, float, int]] = []
    detected_bearish_fvgs: list[tuple[int, float, float, float, int]] = []
    active_for_short: list[tuple[int, float, float, float, int, float, float, int, int, str]] = []
    active_for_long: list[tuple[int, float, float, float, int, float, float, int, int, str]] = []
    recent_sweep_highs: list[tuple[int, float, int, int, str]] = []
    recent_sweep_lows: list[tuple[int, float, int, int, str]] = []
    armed_high_instances: set[int] = set()
    armed_low_instances: set[int] = set()
    high_state = {"instance_id": -1, "consumed": False}
    low_state = {"instance_id": -1, "consumed": False}
    started_target_day = False
    events: list[dict[str, Any]] = []

    def record_event(i: int, event: str, **payload: Any) -> None:
        bar_ts = timestamps[i]
        if bar_ts.strftime("%Y-%m-%d") != trace_date:
            return
        row = {
            "time": bar_ts.isoformat(),
            "event": event,
        }
        row.update(payload)
        events.append(row)

    for i in range(len(df_base)):
        bar_ts = timestamps[i]
        cur_date = bar_ts.strftime("%Y-%m-%d")
        sd = int(session_day_id[i])

        if cur_date == trace_date and not started_target_day:
            started_target_day = True
            record_event(
                i,
                "DAY_START",
                active_low={
                    "instance_id": int(active_low_ids[i]) if i < len(active_low_ids) else -1,
                    "price": round(float(active_low_price[i]), 4) if pd.notna(active_low_price[i]) else None,
                    "level_time": _iso(active_low_times[i]),
                    "publish_time": _iso(active_low_publish[i]),
                },
                active_high={
                    "instance_id": int(active_high_ids[i]) if i < len(active_high_ids) else -1,
                    "price": round(float(active_high_price[i]), 4) if pd.notna(active_high_price[i]) else None,
                    "level_time": _iso(active_high_times[i]),
                    "publish_time": _iso(active_high_publish[i]),
                },
            )

        high_instance_id = int(active_high_ids[i]) if i < len(active_high_ids) else -1
        if high_instance_id != high_state["instance_id"]:
            high_state["instance_id"] = high_instance_id
            high_state["consumed"] = False
            record_event(
                i,
                "ACTIVE_HIGH_UPDATED",
                instance_id=high_instance_id,
                price=round(float(active_high_price[i]), 4) if pd.notna(active_high_price[i]) else None,
                level_time=_iso(active_high_times[i]),
                publish_time=_iso(active_high_publish[i]),
            )

        low_instance_id = int(active_low_ids[i]) if i < len(active_low_ids) else -1
        if low_instance_id != low_state["instance_id"]:
            low_state["instance_id"] = low_instance_id
            low_state["consumed"] = False
            record_event(
                i,
                "ACTIVE_LOW_UPDATED",
                instance_id=low_instance_id,
                price=round(float(active_low_price[i]), 4) if pd.notna(active_low_price[i]) else None,
                level_time=_iso(active_low_times[i]),
                publish_time=_iso(active_low_publish[i]),
            )

        valid_sweep_high = False
        valid_sweep_low = False

        if (
            take_shorts
            and not high_state["consumed"]
            and high_instance_id >= 0
            and pd.notna(active_high_price[i])
            and high[i] > active_high_price[i]
            and masks["in_sweep"][i]
        ):
            high_state["consumed"] = True
            if masks["in_entry"][i] and high_instance_id not in armed_high_instances:
                recent_sweep_highs.append(
                    (
                        i,
                        float(active_high_price[i]),
                        sd,
                        high_instance_id,
                        _iso(active_high_times[i]) or "",
                    )
                )
                valid_sweep_high = True
                record_event(
                    i,
                    "SWEEP_HIGH_DETECTED",
                    level=round(float(active_high_price[i]), 4),
                    level_time=_iso(active_high_times[i]),
                    instance_id=high_instance_id,
                )

        if (
            take_longs
            and not low_state["consumed"]
            and low_instance_id >= 0
            and pd.notna(active_low_price[i])
            and low[i] < active_low_price[i]
            and masks["in_sweep"][i]
        ):
            low_state["consumed"] = True
            if masks["in_entry"][i] and low_instance_id not in armed_low_instances:
                recent_sweep_lows.append(
                    (
                        i,
                        float(active_low_price[i]),
                        sd,
                        low_instance_id,
                        _iso(active_low_times[i]) or "",
                    )
                )
                valid_sweep_low = True
                record_event(
                    i,
                    "SWEEP_LOW_DETECTED",
                    level=round(float(active_low_price[i]), 4),
                    level_time=_iso(active_low_times[i]),
                    instance_id=low_instance_id,
                )

        recent_sweep_highs = [
            sweep for sweep in recent_sweep_highs
            if sweep[2] == sd
            and (i - sweep[0]) <= config.lsi_fvg_window_right
            and sweep[3] not in armed_high_instances
        ]
        recent_sweep_lows = [
            sweep for sweep in recent_sweep_lows
            if sweep[2] == sd
            and (i - sweep[0]) <= config.lsi_fvg_window_right
            and sweep[3] not in armed_low_instances
        ]

        if valid_long[i] and take_shorts:
            base_entry = (i, float(long_fvg_bottom[i]), float(long_gap_size[i]), float(daily_atr[i]), sd)
            if recent_sweep_highs:
                sweep_bar, swept_level, _, level_instance_id, level_time_iso = recent_sweep_highs[-1]
                active_for_short.append(
                    base_entry + (
                        swept_level,
                        float(long_fvg_top[i]),
                        sweep_bar,
                        level_instance_id,
                        level_time_iso,
                    )
                )
                record_event(
                    i,
                    "BULLISH_FVG_POST_SWEEP",
                    fvg_bar_time=bar_ts.isoformat(),
                    sweep_bar_time=timestamps[sweep_bar].isoformat(),
                    level_time=level_time_iso,
                    inv_level=round(float(long_fvg_bottom[i]), 4),
                    other_bound=round(float(long_fvg_top[i]), 4),
                )
            else:
                detected_bullish_fvgs.append(base_entry)
                record_event(
                    i,
                    "BULLISH_FVG_BUFFERED_PRE_SWEEP",
                    fvg_bar_time=bar_ts.isoformat(),
                    inv_level=round(float(long_fvg_bottom[i]), 4),
                    other_bound=round(float(long_fvg_top[i]), 4),
                )

        if valid_short[i] and take_longs:
            base_entry = (i, float(short_fvg_top[i]), float(short_gap_size[i]), float(daily_atr[i]), sd)
            if recent_sweep_lows:
                sweep_bar, swept_level, _, level_instance_id, level_time_iso = recent_sweep_lows[-1]
                active_for_long.append(
                    base_entry + (
                        swept_level,
                        float(short_fvg_bottom[i]),
                        sweep_bar,
                        level_instance_id,
                        level_time_iso,
                    )
                )
                record_event(
                    i,
                    "BEARISH_FVG_POST_SWEEP",
                    fvg_bar_time=bar_ts.isoformat(),
                    sweep_bar_time=timestamps[sweep_bar].isoformat(),
                    level_time=level_time_iso,
                    inv_level=round(float(short_fvg_top[i]), 4),
                    other_bound=round(float(short_fvg_bottom[i]), 4),
                )
            else:
                detected_bearish_fvgs.append(base_entry)
                record_event(
                    i,
                    "BEARISH_FVG_BUFFERED_PRE_SWEEP",
                    fvg_bar_time=bar_ts.isoformat(),
                    inv_level=round(float(short_fvg_top[i]), 4),
                    other_bound=round(float(short_fvg_bottom[i]), 4),
                )

        if valid_sweep_high and recent_sweep_highs:
            sweep_bar, swept_level, _, level_instance_id, level_time_iso = recent_sweep_highs[-1]
            still_pending = []
            to_promote = []
            for pending in detected_bullish_fvgs:
                fvg_bar, inv_level, gap_sz, atr_v, fvg_sd = pending
                if fvg_sd == sd and abs(i - fvg_bar) <= config.lsi_fvg_window_left:
                    to_promote.append(
                        (
                            fvg_bar,
                            inv_level,
                            gap_sz,
                            atr_v,
                            fvg_sd,
                            swept_level,
                            float(long_fvg_top[fvg_bar]),
                            sweep_bar,
                            level_instance_id,
                            level_time_iso,
                        )
                    )
                    record_event(
                        i,
                        "BULLISH_FVG_PROMOTED_PRE_SWEEP",
                        fvg_bar_time=timestamps[fvg_bar].isoformat(),
                        sweep_bar_time=timestamps[sweep_bar].isoformat(),
                        level_time=level_time_iso,
                        inv_level=round(float(inv_level), 4),
                    )
                else:
                    still_pending.append(pending)
            active_for_short.extend(to_promote)
            detected_bullish_fvgs = still_pending

        if valid_sweep_low and recent_sweep_lows:
            sweep_bar, swept_level, _, level_instance_id, level_time_iso = recent_sweep_lows[-1]
            still_pending = []
            to_promote = []
            for pending in detected_bearish_fvgs:
                fvg_bar, inv_level, gap_sz, atr_v, fvg_sd = pending
                if fvg_sd == sd and abs(i - fvg_bar) <= config.lsi_fvg_window_left:
                    to_promote.append(
                        (
                            fvg_bar,
                            inv_level,
                            gap_sz,
                            atr_v,
                            fvg_sd,
                            swept_level,
                            float(short_fvg_bottom[fvg_bar]),
                            sweep_bar,
                            level_instance_id,
                            level_time_iso,
                        )
                    )
                    record_event(
                        i,
                        "BEARISH_FVG_PROMOTED_PRE_SWEEP",
                        fvg_bar_time=timestamps[fvg_bar].isoformat(),
                        sweep_bar_time=timestamps[sweep_bar].isoformat(),
                        level_time=level_time_iso,
                        inv_level=round(float(inv_level), 4),
                    )
                else:
                    still_pending.append(pending)
            active_for_long.extend(to_promote)
            detected_bearish_fvgs = still_pending

        remaining_short_active = []
        for pending in active_for_short:
            (
                fvg_bar,
                inv_level,
                gap_sz,
                atr_v,
                fvg_sd,
                swept_level,
                fvg_other_bound,
                sweep_bar,
                level_instance_id,
                level_time_iso,
            ) = pending
            if level_instance_id in armed_high_instances:
                continue
            if fvg_sd != sd or i <= fvg_bar:
                remaining_short_active.append(pending)
                continue
            if not masks["in_entry"][i]:
                continue
            if close[i] < inv_level:
                fvg_to_inversion = i - fvg_bar
                if config.max_fvg_to_inversion_bars > 0 and fvg_to_inversion > config.max_fvg_to_inversion_bars:
                    continue
                armed_high_instances.add(level_instance_id)
                record_event(
                    i,
                    "SHORT_CANDIDATE_CREATED",
                    entry_time=bar_ts.isoformat(),
                    entry_price=round(float(close[i]), 4),
                    fvg_bar_time=timestamps[fvg_bar].isoformat(),
                    sweep_bar_time=timestamps[sweep_bar].isoformat(),
                    htf_level_time=level_time_iso,
                    htf_level_price=round(float(swept_level), 4),
                    fvg_to_inversion_bars=int(fvg_to_inversion),
                    sweep_to_inversion_bars=int(i - sweep_bar),
                    source="pre_sweep" if fvg_bar < sweep_bar else "post_sweep",
                )
                continue
            remaining_short_active.append(pending)
        active_for_short = remaining_short_active

        remaining_long_active = []
        for pending in active_for_long:
            (
                fvg_bar,
                inv_level,
                gap_sz,
                atr_v,
                fvg_sd,
                swept_level,
                fvg_other_bound,
                sweep_bar,
                level_instance_id,
                level_time_iso,
            ) = pending
            if level_instance_id in armed_low_instances:
                continue
            if fvg_sd != sd or i <= fvg_bar:
                remaining_long_active.append(pending)
                continue
            if not masks["in_entry"][i]:
                continue
            if close[i] > inv_level:
                fvg_to_inversion = i - fvg_bar
                if config.max_fvg_to_inversion_bars > 0 and fvg_to_inversion > config.max_fvg_to_inversion_bars:
                    continue
                armed_low_instances.add(level_instance_id)
                record_event(
                    i,
                    "LONG_CANDIDATE_CREATED",
                    entry_time=bar_ts.isoformat(),
                    entry_price=round(float(close[i]), 4),
                    fvg_bar_time=timestamps[fvg_bar].isoformat(),
                    sweep_bar_time=timestamps[sweep_bar].isoformat(),
                    htf_level_time=level_time_iso,
                    htf_level_price=round(float(swept_level), 4),
                    fvg_to_inversion_bars=int(fvg_to_inversion),
                    sweep_to_inversion_bars=int(i - sweep_bar),
                    source="pre_sweep" if fvg_bar < sweep_bar else "post_sweep",
                )
                continue
            remaining_long_active.append(pending)
        active_for_long = remaining_long_active

        detected_bullish_fvgs = [p for p in detected_bullish_fvgs if p[4] >= sd]
        detected_bearish_fvgs = [p for p in detected_bearish_fvgs if p[4] >= sd]
        active_for_short = [p for p in active_for_short if p[4] >= sd and p[8] not in armed_high_instances]
        active_for_long = [p for p in active_for_long if p[4] >= sd and p[8] not in armed_low_instances]

    return {
        "window_start": window_start,
        "window_end": window_end,
        "trades": trades,
        "events": events,
    }


def _daily_history_provider(trackers: dict[str, DailyHistoryTracker]):
    def _provider(symbol: str):
        tracker = trackers.get(symbol)
        if tracker is None:
            return []
        return tracker.snapshot(include_current=True)

    return _provider


def _exact_snapshot(engine: LSIEngine, current_ts: datetime) -> dict[str, Any]:
    tracker = engine._htf_levels
    return {
        "time": current_ts.isoformat(),
        "raw_state": engine._state.value,
        "latest_low": _serialize_exact_level(tracker.latest_low if tracker is not None else None),
        "latest_high": _serialize_exact_level(tracker.latest_high if tracker is not None else None),
        "low_consumed": bool(engine._htf_low_state["consumed"]),
        "high_consumed": bool(engine._htf_high_state["consumed"]),
        "active_sweep_side": engine._active_htf_level_side,
        "active_sweep_instance_id": int(engine._active_sweep_instance_id),
        "active_sweep_level": round(float(engine._active_sweep.level), 4) if engine._active_sweep is not None else None,
        "active_sweep_pivot_time": engine._active_sweep.pivot_time if engine._active_sweep is not None else None,
        "sweep_bar_index": int(engine._sweep_bar_index),
        "pending_gaps": [_serialize_gap(gap) for gap in engine._pending_gaps],
        "active_gap": _serialize_gap(engine._active_gap),
        "fvg_to_inversion_bars": engine._fvg_to_inversion_bars,
        "sweep_to_inversion_bars": engine._sweep_to_inversion_bars,
        "session_filled_trades": int(engine._session_filled_trades),
    }


def _snapshot_signature(snapshot: dict[str, Any]) -> str:
    payload = dict(snapshot)
    payload.pop("time", None)
    return json.dumps(payload, sort_keys=True, default=str)


async def _trace_exact_day(trace_date: str, candidate: dict) -> dict[str, Any]:
    target = pd.Timestamp(trace_date)
    window_start = (target - pd.Timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    replay_start = datetime.fromisoformat(window_start).replace(tzinfo=ET) - timedelta(days=1)
    frame_end = datetime.combine((target + pd.Timedelta(days=1)).date(), datetime.min.time(), tzinfo=ET)

    bars_1m = _read_parquet_frame("CL", "1m", start=replay_start, end=frame_end)
    events = _build_events("CL.FUT", bars_1m, bar_minutes=1)
    events.sort(key=lambda item: (item[0], item[1]))

    broker = MultiBroker([TradersPostClient(webhook_url="", config_name=PROFILE_NAME)])
    engine = LSIEngine(
        name=SESSION_NAME,
        broker=broker,
        exec_ticker=EXEC_TICKER,
        entry_start=str(candidate["entry_start"]),
        entry_end=str(candidate["entry_end"]),
        sweep_start="08:30",
        sweep_end="15:00",
        flat_start="15:50",
        flat_end="16:00",
        rr=float(candidate["rr"]),
        tp1_ratio=float(candidate["tp1_ratio"]),
        atr_length=int(candidate["atr_length"]),
        min_gap_atr_pct=float(candidate["min_gap_atr_pct"]),
        min_stop_points=float(candidate["min_stop_points"]),
        fvg_window_left=int(candidate["lsi_fvg_window_left"]),
        fvg_window_right=int(candidate["lsi_fvg_window_right"]),
        lsi_entry_mode=str(candidate["entry_mode"]),
        lsi_variant=HTF_LSI_VARIANT,
        risk_usd=EXEC_RISK_USD,
        point_value=EXEC_POINT_VALUE,
        min_qty=1.0,
        qty_step=1.0,
        qty_multiplier=1.0,
        min_tick=EXEC_MIN_TICK,
        max_single_risk_usd=EXEC_RISK_USD,
        long_only=True,
        lsi_n_left=3,
        lsi_n_right=3,
        htf_level_tf_minutes=int(candidate["htf_level_tf_minutes"]),
        htf_n_left=int(candidate["htf_n_left"]),
        htf_trade_max_per_session=int(candidate["htf_trade_max_per_session"]),
        max_fvg_to_inversion_bars=int(candidate["max_fvg_to_inversion_bars"]),
        base_bar_minutes=1,
        config_name=PROFILE_NAME,
    )

    recorder = ReplayRecorder(PROFILE_NAME)
    engine.on_trade_exit = recorder.make_callback(engine)

    exact_events: list[dict[str, Any]] = []
    state_snapshots: list[dict[str, Any]] = []
    current_context: dict[str, datetime | None] = {"timestamp": None}
    last_signature: str | None = None
    day_started = False

    original_log_trade = engine._log_trade

    def _capture_log(event: str, detail: str = "") -> None:
        ts = current_context["timestamp"]
        if ts is not None and ts.strftime("%Y-%m-%d") == trace_date:
            exact_events.append(
                {
                    "time": ts.isoformat(),
                    "event": event,
                    "detail": detail,
                    "snapshot": _exact_snapshot(engine, ts),
                }
            )
        original_log_trade(event, detail)

    engine._log_trade = _capture_log  # type: ignore[method-assign]

    atr_calc = ATRCalculator(length=int(candidate["atr_length"]))
    daily_tracker = DailyHistoryTracker()
    seed_daily = _seed_daily_bars("CL", replay_start)
    daily_tracker.seed_daily(seed_daily)
    atr_calc.seed_daily(seed_daily)
    daily_history_by_symbol = {"CL.FUT": daily_tracker}

    tick_cache = TickCache()
    current_time = replay_start

    set_daily_history_provider(_daily_history_provider(daily_history_by_symbol))
    try:
        idx = 0
        while idx < len(events):
            event_time = events[idx][0]
            if _active_for_ticks(engine) and current_time < event_time:
                ticks = tick_cache.interval("CL", current_time, event_time)
                for ts, row in ticks.iterrows():
                    from trader.engine import Bar

                    tick = Bar(
                        timestamp=ts.to_pydatetime(),
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"] or 0),
                    )
                    current_context["timestamp"] = tick.timestamp
                    await engine.on_tick(tick, atr_calc.value)

            while idx < len(events) and events[idx][0] == event_time:
                _close_time, _symbol, bar = events[idx]
                current_context["timestamp"] = bar.timestamp
                daily_tracker.on_5m_bar(bar)
                atr_calc.on_5m_bar(bar)
                await engine.on_bar(bar, atr_calc.value)
                if bar.timestamp.strftime("%Y-%m-%d") == trace_date:
                    if not day_started:
                        day_started = True
                        state_snapshots.append(
                            {
                                "time": bar.timestamp.isoformat(),
                                "event": "DAY_START",
                                "snapshot": _exact_snapshot(engine, bar.timestamp),
                            }
                        )
                    snapshot = _exact_snapshot(engine, bar.timestamp)
                    signature = _snapshot_signature(snapshot)
                    if signature != last_signature:
                        state_snapshots.append(
                            {
                                "time": bar.timestamp.isoformat(),
                                "event": "STATE_CHANGE",
                                "snapshot": snapshot,
                            }
                        )
                        last_signature = signature
                idx += 1

            current_time = event_time
    finally:
        set_daily_history_provider(None)

    trades = [trade for trade in recorder.trades if trade["date"] == trace_date]
    return {
        "window_start": window_start,
        "window_end": trace_date,
        "trades": trades,
        "log_events": exact_events,
        "state_snapshots": state_snapshots,
    }


def _short_trade_view(trade: dict[str, Any] | None) -> dict[str, Any] | None:
    if trade is None:
        return None
    return {
        "entry_time": trade.get("entry_time"),
        "entry_price": trade.get("entry_price"),
        "htf_level_time": trade.get("htf_level_time"),
        "htf_level_price": trade.get("htf_level_price"),
        "fvg_to_inversion_bars": trade.get("fvg_to_inversion_bars"),
        "sweep_to_inversion_bars": trade.get("sweep_to_inversion_bars"),
        "exit_type": trade.get("exit_type"),
    }


def _same_minute(a: dict[str, Any] | None, b: dict[str, Any] | None) -> bool:
    if a is None or b is None:
        return False
    if not a.get("entry_time") or not b.get("entry_time"):
        return False
    return pd.Timestamp(a["entry_time"]).strftime("%Y-%m-%dT%H:%M") == pd.Timestamp(b["entry_time"]).strftime("%Y-%m-%dT%H:%M")


def _diagnose_date(trace_date: str, research: dict[str, Any], exact: dict[str, Any]) -> str:
    r_trade = research["trades"][0] if research["trades"] else None
    e_trade = exact["trades"][0] if exact["trades"] else None
    if r_trade and e_trade and _same_minute(r_trade, e_trade):
        same_level = (
            round(float(r_trade.get("htf_level_price") or 0.0), 4)
            == round(float(e_trade.get("htf_level_price") or 0.0), 4)
            and _hhmm(r_trade.get("htf_level_time")) == _hhmm(e_trade.get("htf_level_time"))
        )
        same_gap = (
            same_level
            and r_trade.get("fvg_to_inversion_bars") == e_trade.get("fvg_to_inversion_bars")
            and r_trade.get("sweep_to_inversion_bars") == e_trade.get("sweep_to_inversion_bars")
            and round(float(r_trade.get("entry_price") or 0.0), 4)
            == round(float(e_trade.get("entry_price") or 0.0), 4)
        )
        if same_gap:
            return (
                "Resolved on the traced entry trade. Exact replay now matches the research HTF level, "
                "entry minute, and chosen gap."
            )
        if same_level and r_trade.get("fvg_to_inversion_bars") != e_trade.get("fvg_to_inversion_bars"):
            return (
                "Same entry minute and same HTF level, but different gap age. "
                "This points to chosen-gap lifecycle / queue selection rather than timestamp drift."
            )
        if not same_level:
            return (
                "Same entry minute and same entry price, but a different active HTF level fed the trade. "
                "This points to HTF level publication / retention mismatch."
            )
    if r_trade and e_trade:
        return (
            "Research and exact replay took different same-day trades. "
            "This points to HTF level selection diverging before the sweep/gap chain even lines up."
        )
    if r_trade and not e_trade:
        return "Research found a trade but exact replay did not. This points to a live-engine gating mismatch."
    if e_trade and not research["trades"]:
        return "Exact replay found a trade that research did not. This points to extra live-engine arming."
    return "No trade on either side during the traced day."


def _select_relevant_research_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wanted = {
        "DAY_START",
        "ACTIVE_LOW_UPDATED",
        "SWEEP_LOW_DETECTED",
        "BEARISH_FVG_BUFFERED_PRE_SWEEP",
        "BEARISH_FVG_PROMOTED_PRE_SWEEP",
        "BEARISH_FVG_POST_SWEEP",
        "LONG_CANDIDATE_CREATED",
    }
    return [event for event in events if event["event"] in wanted][:20]


def _select_relevant_exact_events(log_events: list[dict[str, Any]], snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for event in log_events:
        if event["event"] in {"SWEEP_DETECTED", "GAP_DETECTED", "FILLED", "ENTRY_REJECTED"}:
            selected.append(
                {
                    "time": event["time"],
                    "event": event["event"],
                    "detail": event["detail"],
                    "active_gap": event["snapshot"].get("active_gap"),
                    "latest_low": event["snapshot"].get("latest_low"),
                    "fvg_to_inversion_bars": event["snapshot"].get("fvg_to_inversion_bars"),
                    "sweep_to_inversion_bars": event["snapshot"].get("sweep_to_inversion_bars"),
                }
            )
    pending_changes = [
        snap for snap in snapshots
        if snap["event"] == "STATE_CHANGE"
        and (
            snap["snapshot"].get("pending_gaps")
            or snap["snapshot"].get("active_gap")
            or snap["snapshot"].get("active_sweep_level") is not None
        )
    ]
    selected.extend(
        {
            "time": snap["time"],
            "event": "STATE_CHANGE",
            "raw_state": snap["snapshot"]["raw_state"],
            "latest_low": snap["snapshot"].get("latest_low"),
            "active_sweep_level": snap["snapshot"].get("active_sweep_level"),
            "pending_gaps": snap["snapshot"].get("pending_gaps"),
            "active_gap": snap["snapshot"].get("active_gap"),
            "fvg_to_inversion_bars": snap["snapshot"].get("fvg_to_inversion_bars"),
        }
        for snap in pending_changes[:12]
    )
    selected.sort(key=lambda row: row.get("time", ""))
    return selected[:20]


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    candidate = payload["candidate"]
    all_resolved = all(
        day["diagnosis"].startswith("Resolved on the traced entry trade")
        for day in payload["dates"].values()
    )
    lines = [
        "# CL NY HTF-LSI Gap Trace",
        "",
        "- Objective: trace representative CL HTF-LSI mismatch days to separate HTF-level publication issues from gap-candidate lifecycle issues.",
        f"- Candidate: `{candidate['config_summary']}`",
        f"- Traced dates: `{', '.join(payload['trace_dates'])}`",
        "",
        "## Key Findings",
        "",
    ]

    for trace_date in payload["trace_dates"]:
        day = payload["dates"][trace_date]
        lines.append(f"- `{trace_date}`: {day['diagnosis']}")

    lines.extend(
        [
            "",
            "## Trade Comparison",
            "",
            "| Date | Research | Exact Replay | Diagnosis |",
            "| --- | --- | --- | --- |",
        ]
    )

    for trace_date in payload["trace_dates"]:
        day = payload["dates"][trace_date]
        r = day["research"]["trades"][0] if day["research"]["trades"] else None
        e = day["exact"]["trades"][0] if day["exact"]["trades"] else None
        r_text = (
            f"{_hhmm(r.get('entry_time'))} @ {r.get('entry_price')} "
            f"`lvl {_hhmm(r.get('htf_level_time'))} / {r.get('htf_level_price')}` "
            f"`fvg {r.get('fvg_to_inversion_bars')}`"
            if r is not None
            else "none"
        )
        e_text = (
            f"{_hhmm(e.get('entry_time'))} @ {e.get('entry_price')} "
            f"`lvl {_hhmm(e.get('htf_level_time'))} / {e.get('htf_level_price')}` "
            f"`fvg {e.get('fvg_to_inversion_bars')}`"
            if e is not None
            else "none"
        )
        lines.append(f"| {trace_date} | {r_text} | {e_text} | {day['diagnosis']} |")

    for trace_date in payload["trace_dates"]:
        day = payload["dates"][trace_date]
        lines.extend(
            [
                "",
                f"## {trace_date}",
                "",
                f"- Research trade: `{json.dumps(day['research_trade_view'])}`",
                f"- Exact trade: `{json.dumps(day['exact_trade_view'])}`",
                "",
                "Research trace:",
            ]
        )
        for event in day["research_relevant_events"]:
            lines.append(f"- `{event['time']}` `{event['event']}` `{json.dumps({k: v for k, v in event.items() if k not in {'time', 'event'}})}`")
        lines.append("")
        lines.append("Exact replay trace:")
        for event in day["exact_relevant_events"]:
            lines.append(f"- `{event['time']}` `{event['event']}` `{json.dumps({k: v for k, v in event.items() if k not in {'time', 'event'}})}`")

    lines.extend(["", "## Next Debug Target", ""])
    if all_resolved:
        lines.extend(
            [
                "- The traced mismatch set is resolved. Use the full parity diff as the primary checkpoint instead of opening a new date-level debug branch from this report.",
                "- If a future parity gap reappears, start by checking whether it belongs to the same two families that were fixed here: sweep retention after expired promoted gaps, or HTF multi-trade rearm after a 1s exit.",
            ]
        )
    else:
        lines.extend(
            [
                "- First, compare the live `HtfLevelTracker` output directly against research `compute_htf_unswept_levels` on the same raw 1m window, because two traced days diverged before the same sweep ever formed.",
                "- Second, once HTF level alignment is closed, inspect gap queue ordering on same-minute same-level days like `2025-05-20`, where exact replay appears to keep an older pre-sweep gap alive while research promotes the newer post-sweep gap.",
            ]
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dates",
        type=str,
        default=",".join(TRACE_DATES),
        help="Comma-separated trace dates in YYYY-MM-DD format.",
    )
    parser.add_argument(
        "--tag",
        type=str,
        default="gap_trace",
        help="Artifact tag suffix for the output JSON/report names.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    trace_dates = tuple(date.strip() for date in args.dates.split(",") if date.strip())
    if not trace_dates:
        raise SystemExit("No trace dates provided.")

    candidate = _load_candidate()
    df_base_all, df_1m_all, df_1s_all, signal_df_1m_all = load_timeframe_data("CL", str(candidate["timeframe"]))

    payload: dict[str, Any] = {
        "candidate": candidate,
        "trace_dates": list(trace_dates),
        "dates": {},
    }

    for trace_date in trace_dates:
        research = _trace_research_day(
            trace_date,
            candidate,
            df_base_all,
            df_1m_all,
            df_1s_all,
            signal_df_1m_all,
        )
        exact = asyncio.run(_trace_exact_day(trace_date, candidate))
        diagnosis = _diagnose_date(trace_date, research, exact)
        payload["dates"][trace_date] = {
            "diagnosis": diagnosis,
            "research": research,
            "exact": exact,
            "research_trade_view": _short_trade_view(research["trades"][0] if research["trades"] else None),
            "exact_trade_view": _short_trade_view(exact["trades"][0] if exact["trades"] else None),
            "research_relevant_events": _select_relevant_research_events(research["events"]),
            "exact_relevant_events": _select_relevant_exact_events(exact["log_events"], exact["state_snapshots"]),
        }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_json = _output_json(args.tag)
    report_path = _report_path(args.tag)
    output_json.write_text(json.dumps(payload, indent=2, default=str))
    _write_report(report_path, payload)
    print(f"Wrote trace summary to {output_json}")
    print(f"Wrote report to {report_path}")


if __name__ == "__main__":
    main()
