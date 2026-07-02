#!/usr/bin/env python3
"""NQ NY VWAP reversion prop-firm objective optimizer.

Research artifact only. Keeps 2025+ holdout closed.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.holdout_log import check_holdout_period  # noqa: E402
from orb_backtest.data.instruments import MNQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, build_maps  # noqa: E402
from orb_backtest.engine.vwap_simulator import (  # noqa: E402
    build_vwap_signal_cache,
    run_vwap_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides  # noqa: E402


RUN_SLUG = "nq_ny_vwap_prop_firm_pipeline_20260629"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_VWAP_PROP_FIRM_PIPELINE_20260629.md"

PRE_START = "2016-01-01"
PRE_END_EXCLUSIVE = "2025-01-01"
RANKING_ACCOUNT_START_END_EXCLUSIVE = "2024-07-01"
RECENT_START = "2021-01-01"
HOLDOUT_START = "2025-01-01"
HOLDOUT_END = "2026-06-06"


@dataclass(frozen=True)
class PropPipelineProfile:
    """Dollar-denominated prop pipeline with first payout then survival-to-bust."""

    trailing_drawdown_usd: float = 2_000.0
    pass_target_usd: float = 3_000.0
    first_payout_usd: float = 1_500.0
    floor_cap_delta_usd: float = 0.0
    challenge_fee_usd: float = 0.0
    account_start_spacing_days: int = 14


PROFILE = PropPipelineProfile()


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _r2(value: Any) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(value, 2) if math.isfinite(value) else 0.0


def _pct(numerator: int, denominator: int) -> float:
    return round(float(numerator) / float(denominator), 4) if denominator else 0.0


def _config_label(config) -> str:
    session = config.sessions[0]
    return (
        f"mnq_dev{session.deviation_atr_pct:g}_stop{session.stop_atr_pct:g}_"
        f"rr{config.rr:g}_risk{config.risk_usd:g}_"
        f"{session.entry_start.replace(':', '')}-{session.entry_end.replace(':', '')}_"
        f"{config.direction_filter}"
    )


def _account_starts(start: str, end_exclusive: str, spacing_days: int) -> list[pd.Timestamp]:
    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end_exclusive).normalize() - pd.Timedelta(days=1),
            freq=f"{int(spacing_days)}D",
        )
    ]


def _trade_rows(trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trade in trades:
        if int(trade.exit_type) == EXIT_NO_FILL or int(trade.fill_bar) < 0:
            continue
        ts = pd.Timestamp(trade.exit_time) if trade.exit_time else pd.Timestamp(trade.date)
        rows.append(
            {
                "day": ts.normalize(),
                "exit_ts": ts,
                "pnl_usd": float(trade.pnl_usd),
                "r_multiple": float(trade.r_multiple),
            }
        )
    rows.sort(key=lambda row: (row["exit_ts"], row["day"]))
    return rows


def _ratchet_floor_delta(
    highest_eod_delta_usd: float,
    current_floor_delta_usd: float,
    profile: PropPipelineProfile,
) -> float:
    candidate = highest_eod_delta_usd - profile.trailing_drawdown_usd
    capped = min(candidate, profile.floor_cap_delta_usd)
    return max(current_floor_delta_usd, capped)


def _simulate_prop_pipeline(
    variant_id: str,
    trades: list[TradeResult],
    account_starts: list[pd.Timestamp],
    profile: PropPipelineProfile,
    end_exclusive: str,
) -> pd.DataFrame:
    rows = _trade_rows(trades)
    columns = [
        "variant_id",
        "account_start",
        "outcome",
        "first_payout_hit",
        "first_payout_date",
        "outcome_date",
        "days_to_first_payout",
        "days_to_outcome",
        "trades_to_first_payout",
        "trades_to_outcome",
        "payout_usd",
        "net_realized_usd",
        "marked_terminal_usd",
        "ending_balance_delta_usd",
        "floor_delta_usd",
        "highest_eod_delta_usd",
        "min_cushion_usd",
    ]
    if not account_starts:
        return pd.DataFrame(columns=columns)

    end_day = pd.Timestamp(end_exclusive).normalize() - pd.Timedelta(days=1)
    outcomes: list[dict[str, Any]] = []

    for start_day in account_starts:
        balance_delta = 0.0
        floor_delta = -float(profile.trailing_drawdown_usd)
        highest_eod_delta = 0.0
        min_cushion = float(profile.trailing_drawdown_usd)
        current_day: pd.Timestamp | None = None
        outcome = "open_pre_payout"
        outcome_day = end_day
        first_payout_hit = False
        first_payout_day: pd.Timestamp | None = None
        days_to_first_payout: int | None = None
        trades_to_first_payout: int | None = None
        trades_taken = 0
        payout_usd = 0.0
        future_seen = False

        for row in rows:
            trade_day = pd.Timestamp(row["day"]).normalize()
            if trade_day < start_day:
                continue
            future_seen = True

            if current_day is not None and trade_day != current_day:
                highest_eod_delta = max(highest_eod_delta, balance_delta)
                floor_delta = _ratchet_floor_delta(highest_eod_delta, floor_delta, profile)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                if balance_delta <= floor_delta:
                    outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                    outcome_day = current_day
                    break

            current_day = trade_day
            balance_delta += float(row["pnl_usd"])
            trades_taken += 1
            min_cushion = min(min_cushion, balance_delta - floor_delta)

            if balance_delta <= floor_delta:
                outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                outcome_day = trade_day
                break

            if not first_payout_hit and balance_delta >= profile.pass_target_usd:
                first_payout_hit = True
                first_payout_day = trade_day
                days_to_first_payout = int((trade_day.date() - start_day.date()).days) + 1
                trades_to_first_payout = trades_taken
                payout_usd += profile.first_payout_usd
                balance_delta -= profile.first_payout_usd
                floor_delta = max(floor_delta, profile.floor_cap_delta_usd)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                outcome = "open_post_payout"

            outcome_day = trade_day

        else:
            if current_day is not None:
                highest_eod_delta = max(highest_eod_delta, balance_delta)
                floor_delta = _ratchet_floor_delta(highest_eod_delta, floor_delta, profile)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                if balance_delta <= floor_delta:
                    outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                    outcome_day = current_day
                else:
                    outcome = "open_post_payout" if first_payout_hit else "open_pre_payout"
                    outcome_day = current_day
            elif not future_seen:
                outcome = "open_pre_payout"
                outcome_day = end_day

        net_realized = payout_usd - profile.challenge_fee_usd
        marked_terminal = net_realized + max(0.0, balance_delta)
        outcomes.append(
            {
                "variant_id": variant_id,
                "account_start": start_day.date().isoformat(),
                "outcome": outcome,
                "first_payout_hit": bool(first_payout_hit),
                "first_payout_date": first_payout_day.date().isoformat() if first_payout_day is not None else "",
                "outcome_date": outcome_day.date().isoformat(),
                "days_to_first_payout": days_to_first_payout,
                "days_to_outcome": int((outcome_day.date() - start_day.date()).days) + 1,
                "trades_to_first_payout": trades_to_first_payout,
                "trades_to_outcome": trades_taken,
                "payout_usd": round(payout_usd, 2),
                "net_realized_usd": round(net_realized, 2),
                "marked_terminal_usd": round(marked_terminal, 2),
                "ending_balance_delta_usd": round(balance_delta, 2),
                "floor_delta_usd": round(floor_delta, 2),
                "highest_eod_delta_usd": round(highest_eod_delta, 2),
                "min_cushion_usd": round(min_cushion, 2),
            }
        )

    return pd.DataFrame(outcomes, columns=columns)


def _score_prop_pipeline(outcomes: pd.DataFrame) -> dict[str, Any]:
    if outcomes.empty:
        return {
            "total_starts": 0,
            "first_payout_rate": 0.0,
            "bust_rate": 0.0,
            "pre_payout_bust_rate": 0.0,
            "post_payout_bust_rate": 0.0,
            "open_rate": 0.0,
            "open_post_payout_rate": 0.0,
            "ev_per_start_usd": 0.0,
            "marked_ev_per_start_usd": 0.0,
            "avg_days_to_first_payout": None,
            "median_days_to_first_payout": None,
            "avg_days_to_outcome": None,
            "median_days_to_outcome": None,
            "avg_trades_to_first_payout": None,
            "median_min_cushion_usd": None,
            "worst_min_cushion_usd": None,
        }

    total = int(len(outcomes))
    first = outcomes[outcomes["first_payout_hit"]].copy()
    bust_pre = outcomes[outcomes["outcome"] == "bust_pre_payout"].copy()
    bust_post = outcomes[outcomes["outcome"] == "bust_post_payout"].copy()
    opens = outcomes[outcomes["outcome"].str.startswith("open")].copy()
    open_post = outcomes[outcomes["outcome"] == "open_post_payout"].copy()

    return {
        "total_starts": total,
        "first_payout_rate": _pct(len(first), total),
        "bust_rate": _pct(len(bust_pre) + len(bust_post), total),
        "pre_payout_bust_rate": _pct(len(bust_pre), total),
        "post_payout_bust_rate": _pct(len(bust_post), total),
        "open_rate": _pct(len(opens), total),
        "open_post_payout_rate": _pct(len(open_post), total),
        "ev_per_start_usd": round(float(outcomes["net_realized_usd"].mean()), 2),
        "marked_ev_per_start_usd": round(float(outcomes["marked_terminal_usd"].mean()), 2),
        "avg_days_to_first_payout": (
            round(float(first["days_to_first_payout"].dropna().mean()), 2) if not first.empty else None
        ),
        "median_days_to_first_payout": (
            round(float(first["days_to_first_payout"].dropna().median()), 2) if not first.empty else None
        ),
        "avg_days_to_outcome": round(float(outcomes["days_to_outcome"].mean()), 2),
        "median_days_to_outcome": round(float(outcomes["days_to_outcome"].median()), 2),
        "avg_trades_to_first_payout": (
            round(float(first["trades_to_first_payout"].dropna().mean()), 2) if not first.empty else None
        ),
        "median_min_cushion_usd": round(float(outcomes["min_cushion_usd"].median()), 2),
        "worst_min_cushion_usd": round(float(outcomes["min_cushion_usd"].min()), 2),
    }


def _make_configs():
    base = with_vwap_overrides(
        default_vwap_config(MNQ),
        tp1_ratio=1.0,
        tp2_mode="fixed_rr",
        half_days=(),
        direction_filter="long",
    )
    configs = []
    windows = (
        ("09:35", "10:30"),
        ("09:35", "11:30"),
        ("09:35", "12:00"),
        ("10:00", "11:30"),
        ("10:00", "12:00"),
    )
    for risk_usd in (50.0, 75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 250.0, 300.0):
        for rr in (1.25, 1.5, 2.0):
            for deviation_atr_pct in (10.0, 15.0, 20.0, 25.0, 30.0):
                for stop_atr_pct in (10.0, 15.0, 20.0, 25.0):
                    for entry_start, entry_end in windows:
                        configs.append(
                            with_vwap_overrides(
                                base,
                                risk_usd=risk_usd,
                                rr=rr,
                                ny_entry_start=entry_start,
                                ny_entry_end=entry_end,
                                ny_deviation_atr_pct=deviation_atr_pct,
                                ny_stop_atr_pct=stop_atr_pct,
                                ny_rejection_mode="close",
                            )
                        )
    return configs


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    holdout_check = check_holdout_period(HOLDOUT_START, HOLDOUT_END)
    print(
        f"Phase 0: holdout {HOLDOUT_START} to {HOLDOUT_END}; "
        f"previous_tests={holdout_check.previous_test_count}; clean={holdout_check.is_clean}"
    )

    print(f"Loading NQ price data for MNQ sizing {PRE_START} to {PRE_END_EXCLUSIVE}...")
    df_5m = load_5m_data(MNQ.data_file, start=PRE_START, end=PRE_END_EXCLUSIVE)
    df_1m = load_1m_for_5m(MNQ.data_file, start=PRE_START, end=PRE_END_EXCLUSIVE)

    configs = _make_configs()
    starts = _account_starts(
        PRE_START,
        RANKING_ACCOUNT_START_END_EXCLUSIVE,
        PROFILE.account_start_spacing_days,
    )
    print(
        f"Phase 1 prop objective screen: {len(configs)} configs; "
        f"{len(starts)} account starts; MNQ risk grid"
    )

    signal_cache = build_vwap_signal_cache(df_5m, configs)
    maps = build_maps(df_5m, df_1m)

    rows: list[dict[str, Any]] = []
    best_outcomes: pd.DataFrame | None = None
    best_score = -1e18

    for idx, config in enumerate(configs, start=1):
        variant_id = _config_label(config)
        trades = run_vwap_backtest(
            df_5m,
            config,
            start_date=PRE_START,
            end_date=PRE_END_EXCLUSIVE,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        metrics = compute_metrics(trades)
        outcomes = _simulate_prop_pipeline(
            variant_id,
            trades,
            starts,
            PROFILE,
            PRE_END_EXCLUSIVE,
        )
        all_score = _score_prop_pipeline(outcomes)
        recent_outcomes = outcomes[outcomes["account_start"] >= RECENT_START].copy()
        recent_score = _score_prop_pipeline(recent_outcomes)

        session = config.sessions[0]
        rank_score = (
            float(recent_score["ev_per_start_usd"])
            + 0.50 * float(all_score["ev_per_start_usd"])
            + 0.10 * float(metrics["total_net_r"])
            - 300.0 * float(recent_score["open_rate"])
            - 150.0 * float(recent_score["pre_payout_bust_rate"])
        )
        row = {
            "rank_score": round(rank_score, 2),
            "variant_id": variant_id,
            "instrument": "MNQ",
            "price_data": "NQ",
            "session": "NY",
            "strategy": "vwap_reversion",
            "rr": config.rr,
            "risk_usd": config.risk_usd,
            "entry_start": session.entry_start,
            "entry_end": session.entry_end,
            "deviation_atr_pct": session.deviation_atr_pct,
            "stop_atr_pct": session.stop_atr_pct,
            "direction_filter": config.direction_filter,
            "total_trades": metrics["total_trades"],
            "total_net_r": _r2(metrics["total_net_r"]),
            "total_pnl_usd": _r2(sum(float(t.pnl_usd) for t in trades if t.exit_type != EXIT_NO_FILL)),
            "profit_factor": _r2(metrics["profit_factor"]),
            "win_rate": _r2(metrics["win_rate"]),
            "max_drawdown_r": _r2(metrics["max_drawdown_r"]),
            "all_total_starts": all_score["total_starts"],
            "all_first_payout_rate": all_score["first_payout_rate"],
            "all_ev_per_start_usd": all_score["ev_per_start_usd"],
            "all_marked_ev_per_start_usd": all_score["marked_ev_per_start_usd"],
            "all_pre_payout_bust_rate": all_score["pre_payout_bust_rate"],
            "all_post_payout_bust_rate": all_score["post_payout_bust_rate"],
            "all_open_rate": all_score["open_rate"],
            "all_avg_days_to_first_payout": all_score["avg_days_to_first_payout"],
            "all_median_min_cushion_usd": all_score["median_min_cushion_usd"],
            "recent_total_starts": recent_score["total_starts"],
            "recent_first_payout_rate": recent_score["first_payout_rate"],
            "recent_ev_per_start_usd": recent_score["ev_per_start_usd"],
            "recent_marked_ev_per_start_usd": recent_score["marked_ev_per_start_usd"],
            "recent_pre_payout_bust_rate": recent_score["pre_payout_bust_rate"],
            "recent_post_payout_bust_rate": recent_score["post_payout_bust_rate"],
            "recent_open_rate": recent_score["open_rate"],
            "recent_avg_days_to_first_payout": recent_score["avg_days_to_first_payout"],
            "recent_median_min_cushion_usd": recent_score["median_min_cushion_usd"],
            "deployability": "research_only",
            "live_support_notes": (
                "VWAP reversion uses the research backtester; execution parity and a live "
                "implementation are required before promotion."
            ),
            "exact_replay_required": "yes",
        }
        rows.append(row)
        if rank_score > best_score:
            best_score = rank_score
            best_outcomes = outcomes
        if idx % 100 == 0:
            print(f"  completed {idx}/{len(configs)}; current best={best_score:.2f}")

    df = pd.DataFrame(rows)
    df = df.sort_values(
        [
            "rank_score",
            "recent_ev_per_start_usd",
            "recent_first_payout_rate",
            "all_ev_per_start_usd",
            "total_net_r",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    df.insert(0, "rank", np.arange(1, len(df) + 1))

    ranked_csv = RESULT_DIR / "ranked_candidates.csv"
    top_outcomes_csv = RESULT_DIR / "top_candidate_account_outcomes.csv"
    summary_path = RESULT_DIR / "summary.json"
    df.to_csv(ranked_csv, index=False)
    if best_outcomes is not None:
        best_outcomes.to_csv(top_outcomes_csv, index=False)

    top = df.head(20).to_dict(orient="records")
    viable = df[
        (df["recent_first_payout_rate"] >= 0.35)
        & (df["recent_ev_per_start_usd"] > 0)
        & (df["total_trades"] >= 100)
    ]
    summary = {
        "run_slug": RUN_SLUG,
        "phase": "pre_holdout_prop_objective_screen",
        "profile": asdict(PROFILE),
        "instrument": "MNQ sizing on NQ price data",
        "pre_holdout_start": PRE_START,
        "pre_holdout_end_exclusive": PRE_END_EXCLUSIVE,
        "ranking_account_start_end_exclusive": RANKING_ACCOUNT_START_END_EXCLUSIVE,
        "recent_start": RECENT_START,
        "holdout_start": HOLDOUT_START,
        "holdout_end": HOLDOUT_END,
        "holdout_previous_tests": holdout_check.previous_test_count,
        "holdout_clean": holdout_check.is_clean,
        "raw_configs": len(configs),
        "account_starts": len(starts),
        "viable_recent_positive_configs": int(len(viable)),
        "top_rows": top,
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_cols = [
        "rank",
        "variant_id",
        "total_trades",
        "total_net_r",
        "profit_factor",
        "max_drawdown_r",
        "recent_first_payout_rate",
        "recent_ev_per_start_usd",
        "recent_pre_payout_bust_rate",
        "recent_post_payout_bust_rate",
        "recent_open_rate",
        "recent_avg_days_to_first_payout",
        "all_first_payout_rate",
        "all_ev_per_start_usd",
    ]
    report_lines = [
        "# NQ NY VWAP Prop-Firm Pipeline Screen",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Phase: pre-holdout prop objective screen, no 2025+ holdout trades used for ranking",
        f"- Price data: `NQ`; sizing instrument: `MNQ`",
        f"- Discovery period: `{PRE_START}` to `<{PRE_END_EXCLUSIVE}`",
        f"- Account starts used for ranking: `{PRE_START}` to `<{RANKING_ACCOUNT_START_END_EXCLUSIVE}` every `{PROFILE.account_start_spacing_days}` days",
        f"- Recent validation slice: account starts from `{RECENT_START}` onward",
        f"- Reserved holdout: `{HOLDOUT_START}` to `{HOLDOUT_END}`; previous logged tests: `{holdout_check.previous_test_count}`",
        f"- Prop model: `${PROFILE.trailing_drawdown_usd:g}` EOD trailing drawdown capped at start, `${PROFILE.pass_target_usd:g}` pass target, `${PROFILE.first_payout_usd:g}` first payout, then keep trading until bust or data end",
        f"- Challenge/account fee modeled: `${PROFILE.challenge_fee_usd:g}`",
        f"- Raw configs: `{len(configs)}`",
        f"- Positive recent-EV configs with recent payout rate >= 35% and >=100 trades: `{len(viable)}`",
        "",
        "## Top Rows By Prop Objective",
        "",
        df.head(15)[report_cols].to_markdown(index=False),
        "",
        "## Read",
        "",
        "- This is still `research_only`: the VWAP reversion entry/exit strategy needs live execution support and exact replay parity before promotion.",
        "- The first-payout EV here counts the `$1,500` withdrawal and does not assume additional withdrawals after that first payout.",
        "- Open post-payout accounts are marked through data end, but realized EV only counts completed withdrawals.",
        "- Holdout remains closed; this is an optimizer pass on pre-2025 data.",
        "",
        "## Artifacts",
        "",
        f"- Ranked candidates: `backtesting/data/results/{RUN_SLUG}/ranked_candidates.csv`",
        f"- Top account paths: `backtesting/data/results/{RUN_SLUG}/top_candidate_account_outcomes.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {ranked_csv}")
    print(f"Wrote {top_outcomes_csv}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
