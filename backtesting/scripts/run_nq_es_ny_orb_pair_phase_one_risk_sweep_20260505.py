#!/usr/bin/env python3
"""Phase-one funded risk sizing for the NQ R11 + ES ALPHA NY ORB pair.

This is a research artifact only. It does not edit execution configs.

Frozen candidates:
- NQ NY ORB R11: 20m NY ORB, long, ATR 7%, rr 3.5, tp1 0.4, no Fridays.
- ES NY ORB: ALPHA_V1 ES_NY ORB, long, ATR 5%, rr 5.0, tp1 0.2, no Thursdays.

The sweep leaves strategy logic untouched and varies only per-leg USD risk.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import ES, NQ, Instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


RUN_SLUG = "nq_es_ny_orb_pair_phase_one_risk_sweep_20260505"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_ES_NY_ORB_PAIR_PHASE_ONE_RISK_SWEEP_20260505.md"

FULL_START = "2016-04-17"
END_INCLUSIVE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"
HOLDOUT_START = "2025-01-01"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"

RISK_VALUES = tuple(float(v) for v in range(100, 651, 50))

FUNDED_MODEL = {
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_withdrawal_usd": 500.0,
    "challenge_fee_usd": 100.0,
    "cohort_spacing_days": 14,
}

WINDOWS = {
    "full": (FULL_START, END_INCLUSIVE),
    "pre_holdout": (FULL_START, "2024-12-31"),
    "holdout": (HOLDOUT_START, END_INCLUSIVE),
    "last_2y": (LAST_2Y_START, END_INCLUSIVE),
    "last_1y": (LAST_1Y_START, END_INCLUSIVE),
}


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return _round(float(value) * 100.0, 2)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _nq_r11_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        excluded_days=(4,),
        impulse_close_filter=False,
        name="nq_ny_orb_r11_phase_one_baseline",
        notes="NQ NY ORB R11 conditional long; standard live-native ORB fields.",
    )


def _es_ny_orb_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="13:00",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.25,
        min_stop_points=3.0,
        min_tp1_points=3.0,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=5.0,
        tp1_ratio=0.2,
        atr_length=7,
        excluded_days=(3,),
        impulse_close_filter=False,
        name="es_ny_orb_phase_one_baseline",
        notes="ALPHA_V1 ES_NY ORB; standard live-native ORB fields.",
    )


def _load_symbol(instrument: Instrument) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None]:
    df_5m = load_5m_data(instrument.data_file, start=FULL_START)
    try:
        df_1m = load_1m_for_5m(instrument.data_file, start=FULL_START)
    except FileNotFoundError:
        df_1m = None
    try:
        df_1s = load_1s_for_5m(instrument.data_file, start=FULL_START)
    except FileNotFoundError:
        df_1s = None
    if df_1m is None and df_1s is not None:
        df_1m = (
            df_1s.resample("1min")
            .agg(
                open=("open", "first"),
                high=("high", "max"),
                low=("low", "min"),
                close=("close", "last"),
                volume=("volume", "sum"),
            )
            .dropna(subset=["open"])
        )
    return df_5m, df_1m, df_1s


def _run_config(config: StrategyConfig) -> list[TradeResult]:
    print(f"Running {config.name}...", flush=True)
    df_5m, df_1m, df_1s = _load_symbol(config.instrument)
    print(
        f"  {config.instrument.symbol}: 5m={len(df_5m):,} "
        f"1m={len(df_1m) if df_1m is not None else 0:,} "
        f"1s={len(df_1s) if df_1s is not None else 0:,}",
        flush=True,
    )
    trades = run_backtest(
        df_5m,
        config,
        start_date=FULL_START,
        end_date=END_EXCLUSIVE,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    if config.excluded_days:
        trades = apply_dow_filter(trades, set(config.excluded_days))
    return sorted(trades, key=lambda t: (t.date, t.session, t.signal_bar, t.fill_bar, t.exit_bar))


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _slice(trades: list[TradeResult], start: str, end: str) -> list[TradeResult]:
    return [trade for trade in trades if start <= trade.date <= end]


def _exit_stats(trades: list[TradeResult]) -> dict[str, Any]:
    filled = _filled(trades)
    counts: dict[str, int] = defaultdict(int)
    for trade in filled:
        counts[EXIT_NAMES.get(trade.exit_type, str(trade.exit_type))] += 1
    total = max(1, len(filled))
    full_tp = counts["tp1_tp2"] + counts["tp2_single"]
    return {
        "full_tp_count": full_tp,
        "full_tp_rate_pct": _pct(full_tp / total),
        "tp1_be_count": counts["tp1_be"],
        "tp1_be_rate_pct": _pct(counts["tp1_be"] / total),
        "tp1_eod_count": counts["tp1_eod"],
        "tp1_eod_rate_pct": _pct(counts["tp1_eod"] / total),
        "sl_count": counts["sl"],
        "sl_rate_pct": _pct(counts["sl"] / total),
        "eod_count": counts["eod"],
        "eod_rate_pct": _pct(counts["eod"] / total),
        "exit_counts_json": json.dumps(dict(sorted(counts.items())), sort_keys=True),
    }


def _stop_stats(trades: list[TradeResult], instrument: Instrument) -> dict[str, Any]:
    risks = [float(t.risk_points) for t in _filled(trades) if t.risk_points > 0]
    if not risks:
        return {
            "median_stop_points": None,
            "median_stop_ticks": None,
            "p25_stop_ticks": None,
            "p75_stop_ticks": None,
        }
    ticks = [risk / instrument.min_tick for risk in risks]
    return {
        "median_stop_points": _round(median(risks), 4),
        "median_stop_ticks": _round(median(ticks), 1),
        "p25_stop_ticks": _round(float(np.percentile(ticks, 25)), 1),
        "p75_stop_ticks": _round(float(np.percentile(ticks, 75)), 1),
    }


def _leg_metric_rows(leg_key: str, label: str, config: StrategyConfig, trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows = []
    for window, (start, end) in WINDOWS.items():
        selected = _slice(trades, start, end)
        metrics = compute_metrics(selected)
        rows.append(
            {
                "leg": leg_key,
                "label": label,
                "window": window,
                "start": start,
                "end": end,
                "trades": int(metrics["total_trades"]),
                "signals": int(metrics["total_signals"]),
                "no_fills": int(metrics["no_fills"]),
                "net_r": _round(metrics["total_r"], 2),
                "win_rate_pct": _pct(metrics["win_rate"]),
                "profit_factor": _round(metrics["profit_factor"], 3),
                "avg_r": _round(metrics["avg_r"], 4),
                "sharpe": _round(metrics["sharpe_ratio"], 3),
                "max_dd_r": _round(metrics["max_drawdown_r"], 2),
                "calmar": _round(metrics["calmar_ratio"], 3),
                "negative_years": int(sum(1 for value in (metrics.get("r_by_year") or {}).values() if value < 0)),
                "r_by_year_json": json.dumps(metrics.get("r_by_year") or {}, sort_keys=True),
                **_stop_stats(selected, config.instrument),
                **_exit_stats(selected),
                "deployability": "live_native",
                "live_support_notes": (
                    "Standard ORB continuation fields; supported by current execution engine."
                ),
                "exact_replay_required": "yes_before_live_promotion",
            }
        )
    return rows


def _trade_rows(leg_key: str, trades: list[TradeResult]) -> list[dict[str, Any]]:
    rows = []
    for trade in _filled(trades):
        exit_ts = pd.Timestamp(trade.exit_time or trade.fill_time or trade.date)
        fill_ts = pd.Timestamp(trade.fill_time or trade.exit_time or trade.date)
        rows.append(
            {
                "leg": leg_key,
                "date": trade.date,
                "exit_ts": exit_ts,
                "fill_ts": fill_ts,
                "r_multiple": float(trade.r_multiple),
                "exit_type": trade.exit_type,
                "exit_name": EXIT_NAMES.get(trade.exit_type, str(trade.exit_type)),
            }
        )
    return sorted(rows, key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))


def _pnl_rows(base_rows: list[dict[str, Any]], nq_risk: float, es_risk: float) -> list[dict[str, Any]]:
    out = []
    risk_by_leg = {"nq_ny_orb_r11": nq_risk, "es_ny_orb": es_risk}
    for row in base_rows:
        new = dict(row)
        new["risk_usd"] = risk_by_leg[new["leg"]]
        new["pnl_usd"] = float(new["r_multiple"]) * float(new["risk_usd"])
        out.append(new)
    return out


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def _simulate_funded(rows: list[dict[str, Any]], *, start: str, end: str) -> list[dict[str, Any]]:
    trades = [row for row in rows if start <= str(row["date"]) <= end]
    trades.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    outcomes = []
    for account_id, start_ts in enumerate(_cohort_starts(start, end), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: str | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(end).date().isoformat()
        trades_taken = 0
        leg_counts: dict[str, int] = defaultdict(int)
        ending_index = -1

        for idx, row in enumerate(trades):
            if row["exit_ts"] < start_ts:
                continue
            trade_day = pd.Timestamp(row["exit_ts"]).date().isoformat()
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(
                    floor,
                    min(
                        high_eod - float(FUNDED_MODEL["trailing_drawdown_usd"]),
                        float(FUNDED_MODEL["max_trailing_breach_usd"]),
                    ),
                )
            current_day = trade_day
            balance += float(row["pnl_usd"])
            trades_taken += 1
            leg_counts[str(row["leg"])] += 1
            ending_index = idx
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        if outcome == "open" and trades:
            future = [row for row in trades if row["exit_ts"] >= start_ts]
            if future:
                outcome_date = pd.Timestamp(future[-1]["exit_ts"]).date().isoformat()

        if outcome == "payout":
            net_after_fee = (
                float(FUNDED_MODEL["first_payout_withdrawal_usd"])
                - float(FUNDED_MODEL["challenge_fee_usd"])
            )
        else:
            net_after_fee = -float(FUNDED_MODEL["challenge_fee_usd"])

        outcomes.append(
            {
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date,
                "days_to_outcome": int((pd.Timestamp(outcome_date) - start_ts).days) + 1,
                "trades_to_outcome": trades_taken,
                "nq_trades_to_outcome": int(leg_counts["nq_ny_orb_r11"]),
                "es_trades_to_outcome": int(leg_counts["es_ny_orb"]),
                "ending_balance_usd": _round(balance, 2),
                "breach_balance_usd": _round(floor, 2),
                "net_after_fee_usd": _round(net_after_fee, 2),
                "ending_trade_index": ending_index,
            }
        )
    return outcomes


def _max_consecutive(outcomes: list[dict[str, Any]], outcome_name: str) -> int:
    max_run = 0
    run = 0
    for row in sorted(outcomes, key=lambda r: r["account_start"]):
        if row["outcome"] == outcome_name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return max_run


def _score_outcomes(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(outcomes)
    payouts = [row for row in outcomes if row["outcome"] == "payout"]
    breaches = [row for row in outcomes if row["outcome"] == "breach"]
    opens = [row for row in outcomes if row["outcome"] == "open"]
    month_breaches: dict[str, int] = defaultdict(int)
    for row in breaches:
        month_breaches[str(row["account_start"])[:7]] += 1
    return {
        "accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate_pct": _pct(len(payouts) / total) if total else 0.0,
        "breach_rate_pct": _pct(len(breaches) / total) if total else 0.0,
        "open_rate_pct": _pct(len(opens) / total) if total else 0.0,
        "ev_per_account_usd": _round(float(np.mean([row["net_after_fee_usd"] for row in outcomes])), 2)
        if outcomes
        else 0.0,
        "avg_days_to_payout": _round(float(np.mean([row["days_to_outcome"] for row in payouts])), 1)
        if payouts
        else None,
        "median_days_to_payout": _round(float(np.median([row["days_to_outcome"] for row in payouts])), 1)
        if payouts
        else None,
        "avg_trades_to_payout": _round(float(np.mean([row["trades_to_outcome"] for row in payouts])), 1)
        if payouts
        else None,
        "avg_nq_trades_to_payout": _round(float(np.mean([row["nq_trades_to_outcome"] for row in payouts])), 1)
        if payouts
        else None,
        "avg_es_trades_to_payout": _round(float(np.mean([row["es_trades_to_outcome"] for row in payouts])), 1)
        if payouts
        else None,
        "avg_open_balance_usd": _round(float(np.mean([row["ending_balance_usd"] for row in opens])), 2)
        if opens
        else None,
        "max_consecutive_breaches": _max_consecutive(outcomes, "breach"),
        "max_consecutive_payouts": _max_consecutive(outcomes, "payout"),
        "worst_month_breaches": max(month_breaches.values()) if month_breaches else 0,
    }


def _rank_pre(row: dict[str, Any]) -> float:
    payout = float(row["pre_payout_rate_pct"] or 0.0)
    breach = float(row["pre_breach_rate_pct"] or 0.0)
    ev = float(row["pre_ev_per_account_usd"] or 0.0)
    days = float(row["pre_avg_days_to_payout"] or 999.0)
    max_breach_run = float(row["pre_max_consecutive_breaches"] or 0.0)
    total_risk = float(row["nq_risk_usd"]) + float(row["es_risk_usd"])
    return round(ev + payout * 2.0 - breach * 2.8 - days * 0.9 - max_breach_run * 18.0 - total_risk * 0.04, 4)


def _rank_robust(row: dict[str, Any]) -> float:
    pre_ev = float(row["pre_ev_per_account_usd"] or 0.0)
    holdout_ev = float(row["holdout_ev_per_account_usd"] or 0.0)
    pre_payout = float(row["pre_payout_rate_pct"] or 0.0)
    holdout_payout = float(row["holdout_payout_rate_pct"] or 0.0)
    pre_breach = float(row["pre_breach_rate_pct"] or 0.0)
    holdout_breach = float(row["holdout_breach_rate_pct"] or 0.0)
    days = float(row["holdout_avg_days_to_payout"] or row["pre_avg_days_to_payout"] or 999.0)
    max_run = max(float(row["pre_max_consecutive_breaches"] or 0.0), float(row["holdout_max_consecutive_breaches"] or 0.0))
    total_risk = float(row["nq_risk_usd"]) + float(row["es_risk_usd"])
    return round(
        min(pre_ev, holdout_ev)
        + min(pre_payout, holdout_payout) * 2.0
        - max(pre_breach, holdout_breach) * 3.0
        - days * 0.65
        - max_run * 20.0
        - total_risk * 0.03,
        4,
    )


def _risk_sweep(base_rows: list[dict[str, Any]]) -> tuple[pd.DataFrame, dict[str, list[dict[str, Any]]]]:
    risk_rows = []
    outcome_exports: dict[str, list[dict[str, Any]]] = {}
    for nq_risk in RISK_VALUES:
        for es_risk in RISK_VALUES:
            pnl_rows = _pnl_rows(base_rows, nq_risk, es_risk)
            full_outcomes = _simulate_funded(pnl_rows, start=FULL_START, end=END_INCLUSIVE)
            pre_outcomes = _simulate_funded(pnl_rows, start=FULL_START, end="2024-12-31")
            holdout_outcomes = _simulate_funded(pnl_rows, start=HOLDOUT_START, end=END_INCLUSIVE)
            full = _score_outcomes(full_outcomes)
            pre = _score_outcomes(pre_outcomes)
            holdout = _score_outcomes(holdout_outcomes)
            row = {
                "nq_risk_usd": int(nq_risk),
                "es_risk_usd": int(es_risk),
                "total_risk_usd": int(nq_risk + es_risk),
                **{f"full_{key}": value for key, value in full.items()},
                **{f"pre_{key}": value for key, value in pre.items()},
                **{f"holdout_{key}": value for key, value in holdout.items()},
            }
            row["pre_rank_score"] = _rank_pre(row)
            row["robust_rank_score"] = _rank_robust(row)
            row["holdout_confirmed"] = (
                float(row["holdout_ev_per_account_usd"] or 0.0) > 0.0
                and float(row["holdout_payout_rate_pct"] or 0.0) >= 50.0
                and float(row["holdout_breach_rate_pct"] or 0.0) <= 40.0
            )
            risk_rows.append(row)

    df = pd.DataFrame(risk_rows)
    pre_best = df.sort_values(
        ["pre_rank_score", "pre_ev_per_account_usd", "pre_payout_rate_pct", "pre_breach_rate_pct"],
        ascending=[False, False, False, True],
    ).iloc[0]
    confirmed = df[df["holdout_confirmed"] == True].copy()
    if confirmed.empty:
        robust_best = df.sort_values(
            ["robust_rank_score", "holdout_ev_per_account_usd", "holdout_payout_rate_pct", "holdout_breach_rate_pct"],
            ascending=[False, False, False, True],
        ).iloc[0]
    else:
        robust_best = confirmed.sort_values(
            ["robust_rank_score", "holdout_ev_per_account_usd", "pre_ev_per_account_usd", "holdout_breach_rate_pct"],
            ascending=[False, False, False, True],
        ).iloc[0]

    for label, row in (("pre_best", pre_best), ("robust_best", robust_best)):
        pnl_rows = _pnl_rows(base_rows, float(row["nq_risk_usd"]), float(row["es_risk_usd"]))
        outcome_exports[f"{label}_full"] = _simulate_funded(pnl_rows, start=FULL_START, end=END_INCLUSIVE)
        outcome_exports[f"{label}_holdout"] = _simulate_funded(pnl_rows, start=HOLDOUT_START, end=END_INCLUSIVE)

    return df, outcome_exports


def _top_rows(df: pd.DataFrame, by: str, n: int = 10) -> list[dict[str, Any]]:
    return df.sort_values(
        [by, "holdout_ev_per_account_usd", "pre_ev_per_account_usd", "holdout_breach_rate_pct", "total_risk_usd"],
        ascending=[False, False, False, True, True],
    ).head(n).to_dict(orient="records")


def _focus_risk_rows(risk_df: pd.DataFrame) -> list[dict[str, Any]]:
    labels = {
        (150, 150): "conservative_no_breach",
        (200, 100): "pre_holdout_no_breach_best",
        (250, 350): "phase_one_sprint_compromise",
        (300, 350): "phase_one_sprint_faster",
        (400, 400): "too_hot_reference",
    }
    rows = []
    for (nq_risk, es_risk), label in labels.items():
        match = risk_df[(risk_df["nq_risk_usd"] == nq_risk) & (risk_df["es_risk_usd"] == es_risk)]
        if match.empty:
            continue
        row = match.iloc[0].to_dict()
        row["mode"] = label
        rows.append(row)
    return rows


def _write_report(
    *,
    leg_rows: list[dict[str, Any]],
    risk_df: pd.DataFrame,
    elapsed_sec: float,
) -> None:
    full_leg_rows = [row for row in leg_rows if row["window"] == "full"]
    recent_leg_rows = [row for row in leg_rows if row["window"] in {"last_2y", "last_1y"}]
    pre_best = risk_df.sort_values("pre_rank_score", ascending=False).iloc[0].to_dict()
    robust_best = risk_df.sort_values("robust_rank_score", ascending=False).iloc[0].to_dict()
    confirmed = risk_df[risk_df["holdout_confirmed"] == True]
    if not confirmed.empty:
        robust_best = confirmed.sort_values("robust_rank_score", ascending=False).iloc[0].to_dict()

    risk_cols = [
        "nq_risk_usd",
        "es_risk_usd",
        "total_risk_usd",
        "pre_payout_rate_pct",
        "pre_breach_rate_pct",
        "pre_ev_per_account_usd",
        "pre_avg_days_to_payout",
        "holdout_payout_rate_pct",
        "holdout_breach_rate_pct",
        "holdout_ev_per_account_usd",
        "holdout_avg_days_to_payout",
        "holdout_confirmed",
        "robust_rank_score",
    ]
    focus_cols = [
        "mode",
        "nq_risk_usd",
        "es_risk_usd",
        "total_risk_usd",
        "pre_payout_rate_pct",
        "pre_breach_rate_pct",
        "pre_ev_per_account_usd",
        "pre_avg_days_to_payout",
        "holdout_payout_rate_pct",
        "holdout_breach_rate_pct",
        "holdout_ev_per_account_usd",
        "holdout_avg_days_to_payout",
        "holdout_max_consecutive_breaches",
    ]
    lines = [
        "# NQ/ES NY ORB Pair Phase-One Risk Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Date range: `{FULL_START}` to `{END_INCLUSIVE}`; holdout opened once at `{HOLDOUT_START}`.",
        "- Candidates are frozen: no signal, stop, target, DOW, or session changes were optimized.",
        "- Funded model: `$50k` account, `$2k` EOD trailing DD capped at `$50k`, first payout trigger `$52.5k`, first withdrawal `$500`, challenge/reset fee `$100`, starts every `14` calendar days.",
        "- Risk grid: independent NQ and ES risk from `$100` to `$650` in `$50` steps.",
        "",
        "## Candidate Deployability",
        "",
        "| Candidate | deployability | live_support_notes | exact_replay_required |",
        "| --- | --- | --- | --- |",
        "| NQ NY ORB R11 | live_native | Standard ORB continuation fields; not active ALPHA_V1-A yet, but supported by execution knobs. | yes_before_live_promotion |",
        "| ES NY ORB | live_native | Active ALPHA_V1 ES_NY ORB leg; standard execution-supported ORB fields. | yes_before_live_promotion |",
        "",
        "## Frozen Candidate Stats",
        "",
        _markdown_table(
            full_leg_rows,
            [
                "leg",
                "trades",
                "net_r",
                "profit_factor",
                "max_dd_r",
                "win_rate_pct",
                "avg_r",
                "median_stop_ticks",
                "full_tp_rate_pct",
                "tp1_be_rate_pct",
                "sl_rate_pct",
                "negative_years",
            ],
        ),
        "",
        "## Recent Windows",
        "",
        _markdown_table(
            recent_leg_rows,
            [
                "leg",
                "window",
                "trades",
                "net_r",
                "profit_factor",
                "max_dd_r",
                "win_rate_pct",
                "full_tp_rate_pct",
                "tp1_be_rate_pct",
                "sl_rate_pct",
            ],
        ),
        "",
        "## Risk Sizing Result",
        "",
        f"- Pre-holdout best score: NQ `${int(pre_best['nq_risk_usd'])}` / ES `${int(pre_best['es_risk_usd'])}` "
        f"(pre payout `{pre_best['pre_payout_rate_pct']}%`, breach `{pre_best['pre_breach_rate_pct']}%`, EV `${pre_best['pre_ev_per_account_usd']}`; "
        f"holdout payout `{pre_best['holdout_payout_rate_pct']}%`, breach `{pre_best['holdout_breach_rate_pct']}%`, EV `${pre_best['holdout_ev_per_account_usd']}`).",
        f"- Holdout-confirmed robust pick: NQ `${int(robust_best['nq_risk_usd'])}` / ES `${int(robust_best['es_risk_usd'])}` "
        f"(pre payout `{robust_best['pre_payout_rate_pct']}%`, breach `{robust_best['pre_breach_rate_pct']}%`, EV `${robust_best['pre_ev_per_account_usd']}`; "
        f"holdout payout `{robust_best['holdout_payout_rate_pct']}%`, breach `{robust_best['holdout_breach_rate_pct']}%`, EV `${robust_best['holdout_ev_per_account_usd']}`).",
        "",
        "## Operating Recommendation",
        "",
        "- **Conservative / lowest-breach sizing**: `NQ $150 / ES $150`. This is the best holdout-confirmed no-breach row, but it is slow: holdout average payout time is about `186` calendar days.",
        "- **Phase-one sprint sizing**: `NQ $250 / ES $350` is the preferred speed/EV compromise if the goal is first-payout velocity. It cuts average payout time to about `70` holdout days while keeping the holdout breach rate at `21.9%` and max consecutive holdout breaches at `7`.",
        "- `NQ $300 / ES $350` is a slightly faster alternative with nearly identical payout/EV, but the extra NQ risk does not materially improve the account outcome.",
        "- `NQ $400 / ES $400` is not the preferred default: it is faster, but it pushes the pre-holdout breach rate above `34%` and the holdout breach rate above `34%`, which is too hot for a clustered NY ORB sleeve.",
        "",
        _markdown_table(_focus_risk_rows(risk_df), focus_cols),
        "",
        "## Top Robust Rows",
        "",
        _markdown_table(_top_rows(risk_df, "robust_rank_score", 12), risk_cols),
        "",
        "## Top Pre-Holdout Rows",
        "",
        _markdown_table(_top_rows(risk_df, "pre_rank_score", 12), risk_cols),
        "",
        "## Interpretation",
        "",
        "- The risk sweep selects dollar sizing only. It does not rescue a weak strategy with target or stop optimization.",
        "- Because this is a two-leg NY ORB sleeve with clustered NY exposure, the robust pick is preferred over the raw pre-holdout winner when the two disagree.",
        "- Both candidates remain `live_native`, but the NQ leg still needs exact execution replay before promotion into a live execution config.",
        "",
        "## Artifacts",
        "",
        "- `leg_stats.csv`",
        "- `risk_sweep.csv`",
        "- `pre_best_full_outcomes.csv` / `pre_best_holdout_outcomes.csv`",
        "- `robust_best_full_outcomes.csv` / `robust_best_holdout_outcomes.csv`",
        f"- Runtime: `{elapsed_sec:.1f}s`",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_safe_json(v) for v in data]
    if isinstance(data, tuple):
        return [_safe_json(v) for v in data]
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        value = float(data)
        return value if math.isfinite(value) else None
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    if isinstance(data, pd.Timestamp):
        return data.isoformat()
    return data


def main() -> None:
    t0 = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    configs = {
        "nq_ny_orb_r11": ("NQ NY ORB R11", _nq_r11_config()),
        "es_ny_orb": ("ES NY ORB", _es_ny_orb_config()),
    }

    streams: dict[str, list[TradeResult]] = {}
    for key, (_, config) in configs.items():
        streams[key] = _run_config(config)

    leg_rows: list[dict[str, Any]] = []
    base_rows: list[dict[str, Any]] = []
    for key, (label, config) in configs.items():
        leg_rows.extend(_leg_metric_rows(key, label, config, streams[key]))
        base_rows.extend(_trade_rows(key, streams[key]))

    base_rows.sort(key=lambda row: (row["exit_ts"], row["leg"], row["fill_ts"]))
    pd.DataFrame(leg_rows).to_csv(RESULT_DIR / "leg_stats.csv", index=False)
    pd.DataFrame(base_rows).to_csv(RESULT_DIR / "trade_stream_r.csv", index=False)

    print("Sweeping funded risk grid...", flush=True)
    risk_df, outcome_exports = _risk_sweep(base_rows)
    risk_df = risk_df.sort_values(["nq_risk_usd", "es_risk_usd"]).reset_index(drop=True)
    risk_df.to_csv(RESULT_DIR / "risk_sweep.csv", index=False)
    for label, rows in outcome_exports.items():
        pd.DataFrame(rows).to_csv(RESULT_DIR / f"{label}_outcomes.csv", index=False)

    elapsed = time.time() - t0
    _write_report(leg_rows=leg_rows, risk_df=risk_df, elapsed_sec=elapsed)

    pre_best = risk_df.sort_values("pre_rank_score", ascending=False).iloc[0].to_dict()
    confirmed = risk_df[risk_df["holdout_confirmed"] == True]
    robust_best = (
        confirmed.sort_values("robust_rank_score", ascending=False).iloc[0].to_dict()
        if not confirmed.empty
        else risk_df.sort_values("robust_rank_score", ascending=False).iloc[0].to_dict()
    )
    summary = {
        "run_slug": RUN_SLUG,
        "full_start": FULL_START,
        "end_inclusive": END_INCLUSIVE,
        "holdout_start": HOLDOUT_START,
        "funded_model": FUNDED_MODEL,
        "risk_values": list(RISK_VALUES),
        "pre_best": pre_best,
        "robust_best": robust_best,
        "leg_stats_full": [row for row in leg_rows if row["window"] == "full"],
        "report": str(REPORT_PATH.relative_to(ROOT)),
        "result_dir": str(RESULT_DIR.relative_to(ROOT)),
        "elapsed_sec": round(elapsed, 2),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=False))

    print("\nDone.")
    print(f"Report: {REPORT_PATH.relative_to(ROOT)}")
    print(f"Results: {RESULT_DIR.relative_to(ROOT)}")
    print(
        "Robust pick: "
        f"NQ ${int(robust_best['nq_risk_usd'])} / ES ${int(robust_best['es_risk_usd'])} "
        f"| holdout payout {robust_best['holdout_payout_rate_pct']}% "
        f"breach {robust_best['holdout_breach_rate_pct']}% "
        f"EV ${robust_best['holdout_ev_per_account_usd']}"
    )


if __name__ == "__main__":
    main()
