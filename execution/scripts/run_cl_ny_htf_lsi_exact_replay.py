#!/usr/bin/env python3
"""Execution-side exact replay prototype for the frozen CL NY HTF-LSI 1m lead."""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
BACKTESTING_ROOT = ROOT / "backtesting"
BACKTESTING_SRC = BACKTESTING_ROOT / "src"
BACKTESTING_SCRIPTS = BACKTESTING_ROOT / "scripts"

for path in (EXEC_SRC, BACKTESTING_SRC, BACKTESTING_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from trader.broker import MultiBroker, TradersPostClient  # noqa: E402
from trader.feed import ATRCalculator, DailyHistoryTracker, ET  # noqa: E402
from trader.gates import set_daily_history_provider  # noqa: E402
from trader.historical_backtest import (  # noqa: E402
    ReplayRecorder,
    TickCache,
    _active_for_ticks,
    _compute_summary,
    _latest_timestamp,
    _read_parquet_frame,
    _seed_daily_bars,
)
from trader.lsi_engine import HTF_LSI_VARIANT, LSIEngine  # noqa: E402


SUMMARY_PATH = BACKTESTING_ROOT / "data" / "results" / "cl_ny_htf_lsi_local_refinement" / "summary.json"
OUTPUT_DIR = BACKTESTING_ROOT / "data" / "results" / "cl_ny_htf_lsi_exact_replay"
OUTPUT_JSON = OUTPUT_DIR / "exact_replay_compare.json"
REPORT_PATH = BACKTESTING_ROOT / "learnings" / "reports" / "CL_NY_HTF_LSI_EXACT_REPLAY.md"

FULL_START = "2016-01-01"
PRE_HOLDOUT_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"
TARGET_END = "2026-03-31"

PROFILE_NAME = "CL_NY_HTF_LSI_1M_FROZEN"
SESSION_NAME = "CL_NY_HTF_LSI_1M_FROZEN"
DB_SYMBOL = "CL.FUT"
EXEC_TICKER = "MCL"
EXEC_POINT_VALUE = 100.0
EXEC_MIN_TICK = 0.01
EXEC_RISK_USD = 5000.0


@dataclass(frozen=True)
class PropProfile:
    account_fee: float = 50.0
    reset_fee: float = 50.0
    payout_split: float = 0.80
    payout_target_r: float = 5.0
    breach_limit_r: float = -4.0
    daily_loss_limit_r: float = -2.0
    min_trading_days: int = 5


@dataclass(frozen=True)
class FundedProfile:
    challenge_fee: float = 100.0
    starting_balance_usd: float = 50_000.0
    trailing_drawdown_usd: float = 2_000.0
    max_trailing_breach_usd: float = 50_000.0
    first_payout_floor_usd: float = 52_500.0
    risk_pre_payout_usd: float = 500.0
    risk_post_payout_usd: float = 250.0


PROP_PROFILE = PropProfile()
FUNDED_PROFILE = FundedProfile()


def _build_events(symbol: str, frame: pd.DataFrame, bar_minutes: int) -> list[tuple[datetime, str, object]]:
    from trader.engine import Bar

    events: list[tuple[datetime, str, object]] = []
    delta = timedelta(minutes=bar_minutes)
    for ts, row in frame.iterrows():
        bar = Bar(
            timestamp=ts.to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"] or 0),
        )
        events.append((ts.to_pydatetime() + delta, symbol, bar))
    return events


def _slice_trades(trades: list[dict], start: str | None = None, end: str | None = None) -> list[dict]:
    return [
        trade
        for trade in trades
        if (start is None or trade["date"] >= start)
        and (end is None or trade["date"] <= end)
    ]


def _save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def _load_candidate() -> dict:
    payload = json.loads(SUMMARY_PATH.read_text())
    return payload["recommended_restart"]


def _target_end_date() -> str:
    latest_1m = _latest_timestamp("CL", "1m")
    latest_1s = _latest_timestamp("CL", "1s")
    latest_available = min(latest_1m, latest_1s).date()
    target = min(pd.Timestamp(TARGET_END).date(), latest_available)
    return target.isoformat()


def _daily_history_provider(trackers: dict[str, DailyHistoryTracker]):
    def _provider(symbol: str):
        tracker = trackers.get(symbol)
        if tracker is None:
            return []
        return tracker.snapshot(include_current=True)

    return _provider


def _pseudo_trade_results(trades: list[dict]) -> list[SimpleNamespace]:
    ordered = sorted(
        trades,
        key=lambda trade: (
            trade.get("entry_time") or trade.get("exit_time") or "",
            trade.get("exit_time") or "",
            trade.get("session") or "",
        ),
    )
    pseudo: list[SimpleNamespace] = []
    for idx, trade in enumerate(ordered):
        pseudo.append(
            SimpleNamespace(
                date=str(trade["date"]),
                exit_type=str(trade.get("exit_type") or ""),
                r_multiple=float(trade.get("r_multiple") or 0.0),
                signal_bar=idx,
                fill_bar=idx,
                fill_time=str(trade.get("entry_time") or ""),
                exit_time=str(trade.get("exit_time") or ""),
            )
        )
    return pseudo


def _window_dates(frame_1m: pd.DataFrame, start: str, end_inclusive: str) -> list[str]:
    end_exclusive = (pd.Timestamp(end_inclusive) + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    idx = frame_1m.index[(frame_1m.index >= start) & (frame_1m.index < end_exclusive)]
    if len(idx) == 0:
        return []
    dates = pd.Index(pd.to_datetime(idx.normalize()).unique()).sort_values()
    return [d.strftime("%Y-%m-%d") for d in dates]


def _simulate_prop_outcomes(
    trades: list[SimpleNamespace],
    trading_dates: list[str],
    profile: PropProfile,
    risk_per_r_usd: float,
) -> pd.DataFrame:
    rows = []
    all_dates = [pd.Timestamp(day).normalize() for day in trading_dates]
    day_to_rs: dict[pd.Timestamp, list[float]] = {}
    for trade in trades:
        day = pd.Timestamp(trade.date).normalize()
        day_to_rs.setdefault(day, []).append(float(trade.r_multiple))

    for start_day in all_dates:
        cum_r = 0.0
        peak_r = 0.0
        trough_r = 0.0
        trades_taken = 0
        trading_days_taken = 0
        outcome = "open"
        breach_reason = ""
        outcome_day = start_day

        for cur_day in all_dates:
            if cur_day < start_day:
                continue

            day_rs = day_to_rs.get(cur_day, [])
            if day_rs:
                trading_days_taken += 1

            day_r = 0.0
            for r_multiple in day_rs:
                day_r += r_multiple
                cum_r += r_multiple
                trades_taken += 1
                peak_r = max(peak_r, cum_r)
                trough_r = min(trough_r, cum_r)

            if day_rs and day_r <= profile.daily_loss_limit_r:
                outcome = "breach"
                breach_reason = "daily_loss_limit"
                outcome_day = cur_day
                break

            if cum_r <= profile.breach_limit_r:
                outcome = "breach"
                breach_reason = "max_drawdown"
                outcome_day = cur_day
                break

            if cum_r >= profile.payout_target_r and trading_days_taken >= profile.min_trading_days:
                outcome = "payout"
                outcome_day = cur_day
                break

            outcome_day = cur_day

        if outcome == "payout":
            net_payout = profile.payout_target_r * risk_per_r_usd * profile.payout_split - profile.account_fee
        elif outcome == "breach":
            net_payout = -(profile.account_fee + profile.reset_fee)
        else:
            net_payout = -profile.account_fee

        rows.append(
            {
                "account_start": start_day.strftime("%Y-%m-%d"),
                "outcome": outcome,
                "outcome_date": outcome_day.strftime("%Y-%m-%d"),
                "days_to_outcome": (outcome_day.date() - start_day.date()).days + 1,
                "trades_to_outcome": trades_taken,
                "trading_days_to_outcome": trading_days_taken,
                "final_r": round(cum_r, 4),
                "peak_r": round(peak_r, 4),
                "trough_r": round(trough_r, 4),
                "net_payout": round(net_payout, 2),
                "breach_reason": breach_reason,
            }
        )

    return pd.DataFrame(rows)


def _build_prop_scorecard(outcomes: pd.DataFrame, profile: PropProfile) -> dict:
    if outcomes.empty:
        return {
            "profile": asdict(profile),
            "total_attempts": 0,
            "first_payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "average_days_to_payout": None,
            "average_trades_to_payout": None,
            "ev_per_attempt": 0.0,
        }

    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    total = int(len(outcomes))

    return {
        "profile": asdict(profile),
        "total_attempts": total,
        "first_payout_rate": round(len(payouts) / total, 4) if total else 0.0,
        "breach_rate": round(len(breaches) / total, 4) if total else 0.0,
        "open_rate": round(len(opens) / total, 4) if total else 0.0,
        "average_days_to_payout": round(float(payouts["days_to_outcome"].mean()), 2) if not payouts.empty else None,
        "average_trades_to_payout": round(float(payouts["trades_to_outcome"].mean()), 2) if not payouts.empty else None,
        "ev_per_attempt": round(float(outcomes["net_payout"].mean()), 2),
    }


def _simulate_funded_outcomes(
    trades: list[SimpleNamespace],
    trading_dates: list[str],
    profile: FundedProfile,
) -> pd.DataFrame:
    rows = []
    all_dates = [pd.Timestamp(day).normalize() for day in trading_dates]
    day_to_rs: dict[pd.Timestamp, list[float]] = {}
    for trade in trades:
        day = pd.Timestamp(trade.date).normalize()
        day_to_rs.setdefault(day, []).append(float(trade.r_multiple))

    starting_breach = min(
        profile.starting_balance_usd - profile.trailing_drawdown_usd,
        profile.max_trailing_breach_usd,
    )

    for start_day in all_dates:
        balance_usd = float(profile.starting_balance_usd)
        highest_eod_balance_usd = float(profile.starting_balance_usd)
        breach_balance_usd = float(starting_breach)
        risk_usd = float(profile.risk_pre_payout_usd)
        trades_taken = 0
        outcome = "open"
        outcome_day = start_day
        first_payout_amount_usd = 0.0

        for cur_day in all_dates:
            if cur_day < start_day:
                continue

            for r_multiple in day_to_rs.get(cur_day, []):
                balance_usd += r_multiple * risk_usd
                trades_taken += 1
                if balance_usd <= breach_balance_usd:
                    outcome = "breach"
                    outcome_day = cur_day
                    break

            if outcome == "breach":
                break

            if balance_usd >= profile.first_payout_floor_usd:
                outcome = "payout"
                outcome_day = cur_day
                first_payout_amount_usd = max(0.0, balance_usd - profile.first_payout_floor_usd)
                risk_usd = float(profile.risk_post_payout_usd)
                break

            highest_eod_balance_usd = max(highest_eod_balance_usd, balance_usd)
            breach_balance_usd = min(
                highest_eod_balance_usd - profile.trailing_drawdown_usd,
                profile.max_trailing_breach_usd,
            )
            outcome_day = cur_day

        net_after_fee = first_payout_amount_usd - profile.challenge_fee if outcome == "payout" else -profile.challenge_fee
        rows.append(
            {
                "account_start": start_day.strftime("%Y-%m-%d"),
                "outcome": outcome,
                "outcome_date": outcome_day.strftime("%Y-%m-%d"),
                "calendar_days_to_outcome": (outcome_day.date() - start_day.date()).days + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": round(balance_usd, 2),
                "breach_balance_usd": round(breach_balance_usd, 2),
                "highest_eod_balance_usd": round(highest_eod_balance_usd, 2),
                "first_payout_amount_usd": round(first_payout_amount_usd, 2),
                "net_payout_after_fee_usd": round(net_after_fee, 2),
            }
        )

    return pd.DataFrame(rows)


def _build_funded_scorecard(outcomes: pd.DataFrame, profile: FundedProfile) -> dict:
    if outcomes.empty:
        return {
            "profile": asdict(profile),
            "total_starts": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "average_days_to_payout": None,
            "average_trades_to_payout": None,
            "average_first_payout_amount_usd": None,
            "ev_per_start_usd": 0.0,
        }

    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    total = int(len(outcomes))

    return {
        "profile": asdict(profile),
        "total_starts": total,
        "payout_rate": round(len(payouts) / total, 4) if total else 0.0,
        "breach_rate": round(len(breaches) / total, 4) if total else 0.0,
        "open_rate": round(len(opens) / total, 4) if total else 0.0,
        "average_days_to_payout": round(float(payouts["calendar_days_to_outcome"].mean()), 2) if not payouts.empty else None,
        "average_trades_to_payout": round(float(payouts["trades_to_outcome"].mean()), 2) if not payouts.empty else None,
        "average_first_payout_amount_usd": round(float(payouts["first_payout_amount_usd"].mean()), 2) if not payouts.empty else None,
        "ev_per_start_usd": round(float(outcomes["net_payout_after_fee_usd"].mean()), 2),
    }


def _scorecards(trades: list[dict], frame_1m: pd.DataFrame, label: str, start: str, end_inclusive: str) -> dict:
    window_trades = _slice_trades(trades, start, end_inclusive)
    pseudo_trades = _pseudo_trade_results(window_trades)
    trading_dates = _window_dates(frame_1m, start, end_inclusive)

    prop_scorecard = _build_prop_scorecard(
        _simulate_prop_outcomes(
            trades=pseudo_trades,
            trading_dates=trading_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=EXEC_RISK_USD,
        ),
        profile=PROP_PROFILE,
    )
    funded_scorecard = _build_funded_scorecard(
        _simulate_funded_outcomes(
            trades=pseudo_trades,
            trading_dates=trading_dates,
            profile=FUNDED_PROFILE,
        ),
        profile=FUNDED_PROFILE,
    )
    return {
        "prop": prop_scorecard,
        "funded": funded_scorecard,
    }


def _delta_row(exact_metrics: dict, research_metrics: dict) -> dict:
    return {
        "trades_delta": int(exact_metrics.get("total_trades", 0) - research_metrics.get("total_trades", 0)),
        "pf_delta": round(float(exact_metrics.get("profit_factor", 0.0) - research_metrics.get("profit_factor", 0.0)), 4),
        "avg_r_delta": round(float(exact_metrics.get("avg_r", 0.0) - research_metrics.get("avg_r", 0.0)), 4),
        "total_r_delta": round(float(exact_metrics.get("total_r", 0.0) - research_metrics.get("total_r", 0.0)), 4),
        "max_dd_r_delta": round(float(exact_metrics.get("max_drawdown_r", 0.0) - research_metrics.get("max_drawdown_r", 0.0)), 4),
        "calmar_delta": round(float(exact_metrics.get("calmar_ratio", 0.0) - research_metrics.get("calmar_ratio", 0.0)), 4),
    }


async def _run_exact_replay(candidate: dict, end_date: str) -> dict:
    replay_start = datetime.fromisoformat(FULL_START).replace(tzinfo=ET) - timedelta(days=1)
    replay_end_date = datetime.fromisoformat(end_date).date()
    frame_end = datetime.combine(replay_end_date + timedelta(days=1), datetime.min.time(), tzinfo=ET)

    bars_1m = _read_parquet_frame("CL", "1m", start=replay_start, end=frame_end)
    events = _build_events(DB_SYMBOL, bars_1m, bar_minutes=1)
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

    atr_length = int(candidate["atr_length"])
    atr_calc = ATRCalculator(length=atr_length)
    daily_tracker = DailyHistoryTracker()
    seed_daily = _seed_daily_bars("CL", replay_start)
    daily_tracker.seed_daily(seed_daily)
    atr_calc.seed_daily(seed_daily)
    daily_history_by_symbol = {DB_SYMBOL: daily_tracker}

    tick_cache = TickCache()
    current_time = replay_start
    final_tick_time = min(
        _latest_timestamp("CL", "1m"),
        _latest_timestamp("CL", "1s"),
    )

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
                    await engine.on_tick(tick, atr_calc.value)

            while idx < len(events) and events[idx][0] == event_time:
                _close_time, _symbol, bar = events[idx]
                daily_tracker.on_5m_bar(bar)
                atr_calc.on_5m_bar(bar)
                await engine.on_bar(bar, atr_calc.value)
                idx += 1

            current_time = event_time

        if _active_for_ticks(engine) and current_time < final_tick_time:
            ticks = tick_cache.interval("CL", current_time, final_tick_time + timedelta(seconds=1))
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
                await engine.on_tick(tick, atr_calc.value)
    finally:
        set_daily_history_provider(None)

    trades = [
        trade
        for trade in recorder.trades
        if FULL_START <= trade["date"] <= end_date
    ]
    trades = sorted(
        trades,
        key=lambda trade: (
            trade.get("entry_time") or trade.get("exit_time") or "",
            trade.get("exit_time") or "",
            trade["session"],
        ),
    )
    return {
        "trades": trades,
        "summary": _compute_summary(trades),
        "frame_1m": bars_1m,
        "latest_common_end_1m_1s": min(_latest_timestamp("CL", "1m"), _latest_timestamp("CL", "1s")).isoformat(),
    }


def _write_report(path: Path, payload: dict) -> None:
    info = payload["info"]
    candidate = payload["candidate"]
    exact = payload["exact"]
    research = payload["research"]
    delta = payload["delta"]
    scorecards = payload["scorecards"]

    lines = [
        "# CL NY HTF-LSI Exact Replay",
        "",
        "- Objective: replay the frozen `1m` CL HTF-LSI lead through the live `LSIEngine` state machine using `1m + 1s` local parquet data.",
        "- Scope note: this is an execution-side replay prototype for the 1m branch. The normal live feed still aggregates signals to 5m, so this is not full production-feed parity yet.",
        f"- Candidate: `{candidate['config_summary']}`",
        f"- Replay window: `{info['full_start']}` to `{info['end_date_inclusive']}`",
        "",
        "## Candidate",
        "",
        f"- Direction / entry: `{candidate['direction_filter']} / {candidate['entry_mode']}`",
        f"- Windows: `sweep 08:30-15:00`, `entry {candidate['entry_start']}-{candidate['entry_end']}`, `flat 15:50-16:00`",
        f"- Structure: `htf{candidate['htf_level_tf_minutes']} n{candidate['htf_n_left']} cap{candidate['htf_trade_max_per_session']}`",
        f"- Risk shape: `rr {candidate['rr']}`, `tp1 {candidate['tp1_ratio']}`, `gap {candidate['min_gap_atr_pct']}`, `atr {candidate['atr_length']}`",
        f"- FVG / lag: `left {candidate['lsi_fvg_window_left']}`, `right {candidate['lsi_fvg_window_right']}`, `lag {candidate['max_fvg_to_inversion_bars']}`",
        "",
        "## Raw Metrics",
        "",
        "| Window | Exact Trades | Exact PF | Exact Avg R | Exact Total R | Exact Max DD | Exact Calmar | Research Trades | Research PF | Research Avg R | Delta Trades | Delta PF | Delta Avg R |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        (
            f"| Pre-Holdout | "
            f"{int(exact['pre_holdout']['total_trades'])} | "
            f"{float(exact['pre_holdout']['profit_factor']):.3f} | "
            f"{float(exact['pre_holdout']['avg_r']):.3f} | "
            f"{float(exact['pre_holdout']['total_r']):.3f} | "
            f"{float(exact['pre_holdout']['max_drawdown_r']):.3f}R | "
            f"{float(exact['pre_holdout']['calmar_ratio']):.3f} | "
            f"{int(research['pre_holdout']['total_trades'])} | "
            f"{float(research['pre_holdout']['profit_factor']):.3f} | "
            f"{float(research['pre_holdout']['avg_r']):.3f} | "
            f"{delta['pre_holdout']['trades_delta']} | "
            f"{delta['pre_holdout']['pf_delta']:.3f} | "
            f"{delta['pre_holdout']['avg_r_delta']:.3f} |"
        ),
        (
            f"| Holdout | "
            f"{int(exact['holdout']['total_trades'])} | "
            f"{float(exact['holdout']['profit_factor']):.3f} | "
            f"{float(exact['holdout']['avg_r']):.3f} | "
            f"{float(exact['holdout']['total_r']):.3f} | "
            f"{float(exact['holdout']['max_drawdown_r']):.3f}R | "
            f"{float(exact['holdout']['calmar_ratio']):.3f} | "
            f"{int(research['holdout']['total_trades'])} | "
            f"{float(research['holdout']['profit_factor']):.3f} | "
            f"{float(research['holdout']['avg_r']):.3f} | "
            f"{delta['holdout']['trades_delta']} | "
            f"{delta['holdout']['pf_delta']:.3f} | "
            f"{delta['holdout']['avg_r_delta']:.3f} |"
        ),
        "",
        "## Exact Replay Scorecards",
        "",
        f"- Pre-holdout prop payout: `{scorecards['pre_holdout']['prop']['first_payout_rate']:.1%}` | funded payout: `{scorecards['pre_holdout']['funded']['payout_rate']:.1%}` | funded EV/start: `${scorecards['pre_holdout']['funded']['ev_per_start_usd']}`",
        f"- Holdout prop payout: `{scorecards['holdout']['prop']['first_payout_rate']:.1%}` | funded payout: `{scorecards['holdout']['funded']['payout_rate']:.1%}` | funded EV/start: `${scorecards['holdout']['funded']['ev_per_start_usd']}`",
        "",
        "## Full Replay Snapshot",
        "",
        f"- Trades: `{int(exact['full']['total_trades'])}`",
        f"- PF: `{float(exact['full']['profit_factor']):.3f}`",
        f"- Avg R: `{float(exact['full']['avg_r']):.3f}`",
        f"- Total R: `{float(exact['full']['total_r']):.3f}`",
        f"- Max DD: `{float(exact['full']['max_drawdown_r']):.3f}R`",
        f"- Calmar: `{float(exact['full']['calmar_ratio']):.3f}`",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main() -> None:
    candidate = _load_candidate()
    end_date = _target_end_date()
    result = asyncio.run(_run_exact_replay(candidate, end_date))

    trades = result["trades"]
    frame_1m = result["frame_1m"]
    exact_full = result["summary"]
    exact_pre = _compute_summary(_slice_trades(trades, FULL_START, PRE_HOLDOUT_END))
    exact_holdout = _compute_summary(_slice_trades(trades, HOLDOUT_START, end_date))

    scorecards = {
        "pre_holdout": _scorecards(trades, frame_1m, f"{PROFILE_NAME} pre_holdout", FULL_START, PRE_HOLDOUT_END),
        "holdout": _scorecards(trades, frame_1m, f"{PROFILE_NAME} holdout", HOLDOUT_START, end_date),
    }

    payload = {
        "info": {
            "profile_name": PROFILE_NAME,
            "session_name": SESSION_NAME,
            "full_start": FULL_START,
            "pre_holdout_end_inclusive": PRE_HOLDOUT_END,
            "holdout_start": HOLDOUT_START,
            "end_date_inclusive": end_date,
            "latest_common_end_1m_1s": result["latest_common_end_1m_1s"],
        },
        "candidate": candidate,
        "research": {
            "pre_holdout": candidate["pre_holdout_metrics"],
            "holdout": candidate["holdout_metrics"],
            "holdout_funded_scorecard": candidate["holdout_funded_scorecard"],
            "holdout_prop_scorecard": candidate["holdout_prop_scorecard"],
            "stitched_oos_metrics": candidate["oos_metrics"],
            "stitched_oos_funded_scorecard": candidate["oos_funded_scorecard"],
            "stitched_oos_prop_scorecard": candidate["oos_prop_scorecard"],
        },
        "exact": {
            "full": exact_full,
            "pre_holdout": exact_pre,
            "holdout": exact_holdout,
        },
        "scorecards": scorecards,
        "delta": {
            "pre_holdout": _delta_row(exact_pre, candidate["pre_holdout_metrics"]),
            "holdout": _delta_row(exact_holdout, candidate["holdout_metrics"]),
        },
    }

    _save_json(OUTPUT_JSON, payload)
    _write_report(REPORT_PATH, payload)

    print(json.dumps(payload, indent=2, default=str))
    print(f"\nSaved JSON to {OUTPUT_JSON}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
