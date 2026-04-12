#!/usr/bin/env python3
"""Trace a single day for NQ NY HTF-LSI lag24 research vs exact replay."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
EXEC_ROOT = ROOT.parent / "execution"
EXEC_SITE_PACKAGES = EXEC_ROOT / ".venv" / "lib" / "python3.13" / "site-packages"

if EXEC_SITE_PACKAGES.exists():
    sys.path.append(str(EXEC_SITE_PACKAGES))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(EXEC_ROOT / "src"))

from htf_lsi_common import (  # noqa: E402
    build_current_nq_ny_htf_lsi_lag24_config,
    load_timeframe_data,
    save_json,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.export import results_to_dict  # noqa: E402
from trader.broker import MultiBroker, TradersPostClient  # noqa: E402
from trader.engine import Bar  # noqa: E402
from trader.feed import ATRCalculator, DailyHistoryTracker, ET  # noqa: E402
from trader.gates import set_daily_history_provider  # noqa: E402
from trader.historical_backtest import (  # noqa: E402
    ReplayRecorder,
    TickCache,
    _active_for_ticks,
    _build_5m_events,
    _daily_history_provider_from_trackers,
    _read_parquet_frame,
    _seed_daily_bars,
    _wire_nq_ny_overlap,
    latest_common_end,
)
from trader.main import build_engines, build_lsi_engines, DEFAULT_CONFIG, load_config, load_exec_configs  # noqa: E402
from trader.position_limits import ContractCapManager  # noqa: E402


PROFILE_NAME = "HTF_LSI_5M_LAG24"
DEFAULT_TARGET_DATE = "2025-04-23"
DEFAULT_REPLAY_START = "2016-01-01"


def _compact(day: str) -> str:
    return day.replace("-", "")


def _status_snapshot(engine: Any) -> dict[str, Any]:
    status = engine.status_dict()
    keep = {
        "config_name",
        "session",
        "state",
        "raw_state",
        "date",
        "daily_atr",
        "sweep_start",
        "sweep_end",
        "latest_htf_high",
        "latest_htf_high_time",
        "latest_htf_low",
        "latest_htf_low_time",
        "entry_mode",
        "lsi_variant",
        "htf_level_tf_minutes",
        "htf_n_left",
        "htf_trade_max_per_session",
        "max_fvg_to_inversion_bars",
        "session_filled_trades",
        "trade_overlap",
        "swept_level",
        "swept_level_time",
        "fvg_top",
        "fvg_bottom",
        "fvg_to_inversion_bars",
        "sweep_to_inversion_bars",
        "skip_reason",
        "blocking_gate",
        "excluded_dow",
        "limit_price",
        "limit_direction",
        "levels",
    }
    return {key: status.get(key) for key in keep if key in status}


@dataclass
class DayTraceRecorder:
    target_date: str
    state_events: list[dict[str, Any]]
    bar_snapshots: list[dict[str, Any]]

    def __init__(self, target_date: str) -> None:
        self.target_date = target_date
        self.state_events = []
        self.bar_snapshots = []

    def make_state_callback(self, engine: Any):
        target_compact = _compact(self.target_date)

        def _record(_status: dict[str, Any]) -> None:
            status = _status_snapshot(engine)
            if status.get("date") != target_compact:
                return
            event_ts = None
            if getattr(engine, "_fill_timestamp", None) is not None and status.get("raw_state") == "managing":
                event_ts = engine._fill_timestamp.isoformat()
            elif getattr(engine, "_bars", None):
                event_ts = engine._bars[-1].timestamp.isoformat()
            self.state_events.append({
                "event_timestamp": event_ts,
                **status,
            })

        return _record

    def record_bar(self, engine: Any, bar: Bar, event_time: datetime, daily_atr: float) -> None:
        if bar.timestamp.strftime("%Y-%m-%d") != self.target_date:
            return
        self.bar_snapshots.append({
            "bar_timestamp": bar.timestamp.isoformat(),
            "event_timestamp": event_time.isoformat(),
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": int(bar.volume),
            "daily_atr": float(daily_atr),
            "excluded_today": bool(engine._is_excluded_day(bar)),
            **_status_snapshot(engine),
        })


def _load_research_target(date_str: str) -> dict[str, Any]:
    config = build_current_nq_ny_htf_lsi_lag24_config(
        name=f"NQ NY HTF_LSI 5m lag24 trace {date_str}",
    )
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    maps = build_maps(df_base)
    signal_cache = build_signal_cache(df_base, [config], signal_df_1m=signal_df_1m)
    trades = run_backtest(
        df_base,
        config,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    all_trades = results_to_dict(
        trades,
        config,
        include_trades=True,
        include_equity_curve=False,
    )["trades"]
    return {
        "all": [trade for trade in all_trades if trade["date"] == date_str],
        "filled": [
            trade
            for trade in all_trades
            if trade["date"] == date_str and trade.get("exit_type") != "no_fill"
        ],
    }


async def _run_exact_trace(
    *,
    target_date: str,
    replay_start: str,
) -> dict[str, Any]:
    config = load_config(DEFAULT_CONFIG)
    exec_configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    exec_config = exec_configs[PROFILE_NAME]

    brokers = [TradersPostClient(webhook_url="", config_name=PROFILE_NAME)]
    broker = MultiBroker(brokers)
    position_manager = ContractCapManager(max_open_contracts=exec_config.max_open_contracts)

    orb_engines, symbol_map, atr_lengths = build_engines(
        config,
        broker,
        config_name=PROFILE_NAME,
        session_list=list(exec_config.session_overrides.keys()),
        exec_overrides=exec_config.session_overrides,
        position_manager=position_manager,
    )
    lsi_engines = build_lsi_engines(
        config,
        broker,
        symbol_map,
        atr_lengths,
        config_name=PROFILE_NAME,
        lsi_list=list(exec_config.lsi_session_overrides.keys()),
        lsi_overrides=exec_config.lsi_session_overrides,
        position_manager=position_manager,
    )
    _wire_nq_ny_overlap(orb_engines, lsi_engines)

    recorder = ReplayRecorder(PROFILE_NAME)
    trace = DayTraceRecorder(target_date)
    all_engines = orb_engines + lsi_engines
    for engine in all_engines:
        engine.on_trade_exit = recorder.make_callback(engine)
        engine.on_state_change = trace.make_state_callback(engine)

    replay_start_dt = datetime.fromisoformat(replay_start).replace(tzinfo=ET) - timedelta(days=1)
    replay_end_date = datetime.fromisoformat(target_date).date()

    atr_by_symbol: dict[str, dict[int, ATRCalculator]] = {}
    daily_history_by_symbol: dict[str, DailyHistoryTracker] = {}
    events: list[tuple[datetime, str, Bar]] = []
    for symbol, lengths in atr_lengths.items():
        atr_by_symbol[symbol] = {length: ATRCalculator(length=length) for length in lengths}
        seed_daily = _seed_daily_bars(symbol.split(".")[0], replay_start_dt)
        tracker = DailyHistoryTracker()
        tracker.seed_daily(seed_daily)
        daily_history_by_symbol[symbol] = tracker
        for calc in atr_by_symbol[symbol].values():
            calc.seed_daily(seed_daily)

        frame_end = datetime.combine(replay_end_date + timedelta(days=1), time.min, tzinfo=ET)
        bars_5m = _read_parquet_frame(symbol.split(".")[0], "5m", start=replay_start_dt, end=frame_end)
        events.extend(_build_5m_events(symbol, bars_5m))

    events.sort(key=lambda item: (item[0], item[1]))
    tick_cache = TickCache()
    current_time = replay_start_dt
    final_tick_time = min(
        latest_common_end(["NQ"]),
        datetime.combine(replay_end_date + timedelta(days=1), time.min, tzinfo=ET),
    )

    set_daily_history_provider(_daily_history_provider_from_trackers(daily_history_by_symbol))
    try:
        idx = 0
        while idx < len(events):
            event_time = events[idx][0]

            active_symbols = [
                symbol for symbol, engines in symbol_map.items()
                if any(_active_for_ticks(engine) for engine in engines)
            ]
            if active_symbols and current_time < event_time:
                tick_events: list[tuple[datetime, str, Bar]] = []
                for symbol in active_symbols:
                    ticks = tick_cache.interval(symbol.split(".")[0], current_time, event_time)
                    for ts, row in ticks.iterrows():
                        tick_events.append((
                            ts.to_pydatetime(),
                            symbol,
                            Bar(
                                timestamp=ts.to_pydatetime(),
                                open=float(row["open"]),
                                high=float(row["high"]),
                                low=float(row["low"]),
                                close=float(row["close"]),
                                volume=int(row["volume"] or 0),
                            ),
                        ))
                tick_events.sort(key=lambda item: (item[0], item[1]))
                for _ts, symbol, tick in tick_events:
                    daily_atrs = {
                        length: calc.value for length, calc in atr_by_symbol[symbol].items()
                    }
                    for engine in symbol_map[symbol]:
                        await engine.on_tick(tick, daily_atrs.get(getattr(engine, "atr_length", 14), 0.0))

            while idx < len(events) and events[idx][0] == event_time:
                _, symbol, bar = events[idx]
                daily_history_by_symbol[symbol].on_5m_bar(bar)
                for calc in atr_by_symbol[symbol].values():
                    calc.on_5m_bar(bar)
                daily_atrs = {
                    length: calc.value for length, calc in atr_by_symbol[symbol].items()
                }
                for engine in symbol_map[symbol]:
                    daily_atr = daily_atrs.get(getattr(engine, "atr_length", 14), 0.0)
                    await engine.on_bar(bar, daily_atr)
                    trace.record_bar(engine, bar, event_time, daily_atr)
                idx += 1

            current_time = event_time

        active_symbols = [
            symbol for symbol, engines in symbol_map.items()
            if any(_active_for_ticks(engine) for engine in engines)
        ]
        if active_symbols and current_time < final_tick_time:
            tick_events: list[tuple[datetime, str, Bar]] = []
            for symbol in active_symbols:
                ticks = tick_cache.interval(symbol.split(".")[0], current_time, final_tick_time + timedelta(seconds=1))
                for ts, row in ticks.iterrows():
                    tick_events.append((
                        ts.to_pydatetime(),
                        symbol,
                        Bar(
                            timestamp=ts.to_pydatetime(),
                            open=float(row["open"]),
                            high=float(row["high"]),
                            low=float(row["low"]),
                            close=float(row["close"]),
                            volume=int(row["volume"] or 0),
                        ),
                    ))
            tick_events.sort(key=lambda item: (item[0], item[1]))
            for _ts, symbol, tick in tick_events:
                daily_atrs = {
                    length: calc.value for length, calc in atr_by_symbol[symbol].items()
                }
                for engine in symbol_map[symbol]:
                    await engine.on_tick(tick, daily_atrs.get(getattr(engine, "atr_length", 14), 0.0))
    finally:
        set_daily_history_provider(None)
        await broker.close()

    return {
        "trades": [trade for trade in recorder.trades if trade["date"] == target_date],
        "state_events": trace.state_events,
        "bar_snapshots": trace.bar_snapshots,
    }


def _bars_near_research_entry(bar_snapshots: list[dict[str, Any]], research_filled: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not research_filled:
        return bar_snapshots[:20]
    entries = [
        datetime.fromisoformat(trade["entry_time"])
        for trade in research_filled
        if trade.get("entry_time")
    ]
    if not entries:
        return bar_snapshots[:20]
    first_entry = min(entries)
    start = first_entry - timedelta(minutes=60)
    end = first_entry + timedelta(minutes=60)
    return [
        snapshot
        for snapshot in bar_snapshots
        if start
        <= datetime.fromisoformat(snapshot["bar_timestamp"]).replace(tzinfo=None)
        <= end
    ]


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    target_date = payload["info"]["target_date"]
    replay_start = payload["info"]["replay_start"]
    research_filled = payload["research"]["filled"]
    research_all = payload["research"]["all"]
    exact_trades = payload["exact"]["trades"]
    state_events = payload["exact"]["state_events"]
    focus_bars = _bars_near_research_entry(payload["exact"]["bar_snapshots"], research_filled)

    lines = [
        f"# NQ NY HTF-LSI Lag24 Day Trace — {target_date}",
        "",
        "- Objective: trace one missing holdout date through the exact live-engine replay and compare it with the research-side setup on that same day.",
        f"- Profile: `{PROFILE_NAME}`",
        f"- Replay start used for exact trace: `{replay_start}`",
        "",
        "## Research Trades",
        "",
        f"- Research rows on the day: `{len(research_all)}`",
        f"- Research filled trades on the day: `{len(research_filled)}`",
    ]

    for trade in research_all:
        lines.append(
            (
                f"- Research `{trade.get('exit_type')}` | entry `{trade.get('entry_time') or '-'}` "
                f"| entry_price `{trade.get('entry_price')}` | htf `{trade.get('htf_level_time')}` "
                f"@ `{trade.get('htf_level_price')}` | fvg_to_inversion `{trade.get('fvg_to_inversion_bars')}` "
                f"| sweep_to_inversion `{trade.get('sweep_to_inversion_bars')}`"
            )
        )

    lines.extend([
        "",
        "## Exact Replay",
        "",
        f"- Exact filled trades on the day: `{len(exact_trades)}`",
        f"- Exact state-change events on the day: `{len(state_events)}`",
    ])

    for trade in exact_trades:
        lines.append(
            (
                f"- Exact `{trade.get('exit_type')}` | entry `{trade.get('entry_time') or '-'}` "
                f"| entry_price `{trade.get('entry_price')}` | htf `{trade.get('htf_level_time')}` "
                f"@ `{trade.get('htf_level_price')}` | fvg_to_inversion `{trade.get('fvg_to_inversion_bars')}` "
                f"| sweep_to_inversion `{trade.get('sweep_to_inversion_bars')}`"
            )
        )

    lines.extend([
        "",
        "## State Changes",
        "",
    ])
    if not state_events:
        lines.append("- No state changes recorded on the target date.")
    else:
        for event in state_events:
            lines.append(
                f"- `{event.get('event_timestamp')}` | state `{event.get('raw_state')}` | excluded_dow `{event.get('excluded_dow')}` | latest_htf_low `{event.get('latest_htf_low')}` @ `{event.get('latest_htf_low_time')}` | "
                f"swept `{event.get('swept_level')}` @ `{event.get('swept_level_time')}` | fvg `{event.get('fvg_bottom')}->{event.get('fvg_top')}` | "
                f"fvg_to_inversion `{event.get('fvg_to_inversion_bars')}` | session_filled `{event.get('session_filled_trades')}`"
            )

    lines.extend([
        "",
        "## Focus Bars",
        "",
        "- Bars shown here are the exact-engine 5m snapshots from one hour before through one hour after the first research filled entry.",
        "",
    ])
    for snapshot in focus_bars:
        lines.append(
            f"- `{snapshot['bar_timestamp']}` close `{snapshot['close']}` | state `{snapshot.get('raw_state')}` | "
            f"excluded_today `{snapshot.get('excluded_today')}` | excluded_dow `{snapshot.get('excluded_dow')}` | "
            f"latest_htf_low `{snapshot.get('latest_htf_low')}` @ `{snapshot.get('latest_htf_low_time')}` | "
            f"swept `{snapshot.get('swept_level')}` | fvg `{snapshot.get('fvg_bottom')}->{snapshot.get('fvg_top')}` | "
            f"limit `{snapshot.get('limit_price')}` | filled `{snapshot.get('session_filled_trades')}`"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=DEFAULT_TARGET_DATE, help="Target trace date in YYYY-MM-DD")
    parser.add_argument(
        "--replay-start",
        default=DEFAULT_REPLAY_START,
        help="Replay start date for exact trace in YYYY-MM-DD",
    )
    args = parser.parse_args()

    target_slug = args.date.replace("-", "_")
    output_dir = ROOT / "data" / "results" / f"nq_ny_htf_lsi_lag24_day_trace_{target_slug}"
    output_json = output_dir / "trace.json"
    report_path = ROOT / "learnings" / "reports" / f"NQ_NY_HTF_LSI_LAG24_DAY_TRACE_{target_slug}.md"

    research = _load_research_target(args.date)
    exact = asyncio.run(_run_exact_trace(target_date=args.date, replay_start=args.replay_start))
    payload = {
        "info": {
            "profile_name": PROFILE_NAME,
            "target_date": args.date,
            "replay_start": args.replay_start,
        },
        "research": research,
        "exact": exact,
    }
    save_json(output_json, payload)
    _write_report(report_path, payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved JSON to {output_json}")
    print(f"Saved report to {report_path}")


if __name__ == "__main__":
    main()
