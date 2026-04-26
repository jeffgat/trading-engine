#!/usr/bin/env python3
"""Sweep Hunter/Classic ORB parity hypotheses against a TradingView export."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.hunter_classic_parity_report import add_indicator_features, day_levels, export_to_frame
from scripts.run_hunter_classic_orb_replication import (
    ALLOWED_WEEKDAYS,
    COMMISSION_PER_CONTRACT_ROUND_TRIP,
    HUNTER_TARGET_RR,
    INITIAL_CAPITAL,
    MAX_CONTRACTS,
    MAX_RISK_USD,
    POINT_VALUE,
    REJECTION_WICK_MAX_PCT,
    SIGNAL_END,
    SIGNAL_START,
    SL_BUFFER_POINTS,
    Candidate,
    body_rejection,
    load_1s,
    resample_5m,
)


StatePolicy = Literal[
    "current_any_side_one_reentry",
    "current_same_side_one_reentry",
    "after_each_loss_any_side",
    "after_each_loss_same_side",
    "one_trade_per_day",
    "all_nonoverlap",
]
TiePolicy = Literal["stop_first", "target_first"]


@dataclass(frozen=True)
class VariantConfig:
    name: str
    state_policy: StatePolicy
    ema15_tolerance_points: float
    body_min_pct: float
    overextension_max_pct: float | None
    rr_reduction_threshold_points: float | None
    reduced_rr: float
    max_hold_minutes: int
    tie_policy: TiePolicy


@dataclass(frozen=True)
class VariantTrade:
    trade_no: int
    side: str
    signal_dt: str
    entry_dt: str
    entry_key_dt: str
    exit_dt: str
    entry_price: float
    exit_price: float
    stop_price: float
    target_price: float
    risk_points: float
    rr: float
    qty: int
    pnl_usd: float
    mfe_usd: float
    mae_usd: float
    exit_signal: str
    body_pct: float
    rejection_wick_pct: float
    extension_pct: float
    variant: str


@dataclass(frozen=True)
class VariantScore:
    rank: int
    name: str
    state_policy: str
    ema15_tolerance_points: float
    body_min_pct: float
    overextension_max_pct: float | None
    rr_reduction_threshold_points: float | None
    reduced_rr: float
    max_hold_minutes: int
    tie_policy: str
    score: float
    tv_trades: int
    sim_trades: int
    matched_entries: int
    missing_count: int
    extra_count: int
    entry_precision: float
    entry_recall: float
    entry_f1: float
    entry_jaccard: float
    same_win_loss_rate: float | None
    median_abs_pnl_error_usd: float | None
    mean_abs_pnl_error_usd: float | None
    net_pnl_usd: float
    tv_net_pnl_usd: float
    net_delta_usd: float
    net_accuracy: float | None
    win_rate: float
    tv_win_rate: float
    profit_factor: float | None
    tv_profit_factor: float | None
    pf_accuracy: float | None
    exit_counts: str
    qty_counts: str


def contracts_for_risk(risk_points: float) -> int:
    if risk_points <= 0:
        return 1
    raw = int(MAX_RISK_USD // (risk_points * POINT_VALUE))
    return max(1, min(MAX_CONTRACTS, raw))


def build_variant_candidates(bars_5m: pd.DataFrame, config: VariantConfig) -> list[Candidate]:
    candidates: list[Candidate] = []
    for day, group in bars_5m.groupby(bars_5m.index.date):
        if pd.Timestamp(day).weekday() not in ALLOWED_WEEKDAYS:
            continue

        orb = group.between_time("09:30", "09:40")
        if len(orb) < 3:
            continue
        orb_high = float(orb.high.max())
        orb_low = float(orb.low.min())
        orb_range = max(orb_high - orb_low, 1e-9)

        for signal_dt, row in group.between_time(SIGNAL_START, SIGNAL_END).iterrows():
            pos = group.index.get_loc(signal_dt)
            if pos == 0:
                continue
            previous_close = float(group.iloc[pos - 1].close)
            raw_sides: list[str] = []
            if float(row.close) > orb_high and previous_close <= orb_high:
                raw_sides.append("long")
            if float(row.close) < orb_low and previous_close >= orb_low:
                raw_sides.append("short")

            for side in raw_sides:
                ema_value = float(row.ema15_close_14)
                if side == "long":
                    if float(row.close) < ema_value - config.ema15_tolerance_points:
                        continue
                else:
                    if float(row.close) > ema_value + config.ema15_tolerance_points:
                        continue

                body_pct, rejection_pct = body_rejection(row, side)
                if body_pct < config.body_min_pct or rejection_pct > REJECTION_WICK_MAX_PCT:
                    continue
                extension_pct = (
                    (float(row.close) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row.close)) / orb_range * 100.0
                )
                if config.overextension_max_pct is not None and extension_pct > config.overextension_max_pct:
                    continue
                candidates.append(
                    Candidate(
                        signal_dt=signal_dt,
                        entry_dt=signal_dt + pd.Timedelta(minutes=5),
                        side=side,
                        orb_high=orb_high,
                        orb_low=orb_low,
                        signal_open=float(row.open),
                        signal_high=float(row.high),
                        signal_low=float(row.low),
                        signal_close=float(row.close),
                        body_pct=body_pct,
                        rejection_wick_pct=rejection_pct,
                        extension_pct=extension_pct,
                    )
                )
    return candidates


def simulate_exit(candidate: Candidate, df_1s: pd.DataFrame, trade_no: int, config: VariantConfig) -> VariantTrade | None:
    if candidate.entry_dt not in df_1s.index:
        start_slice = df_1s.loc[candidate.entry_dt : candidate.entry_dt + pd.Timedelta(minutes=5)]
        if start_slice.empty:
            return None
        entry_dt = start_slice.index[0]
    else:
        entry_dt = candidate.entry_dt

    entry_price = float(df_1s.loc[entry_dt].open)
    if candidate.side == "long":
        stop_price = candidate.signal_low - SL_BUFFER_POINTS
        risk_points = entry_price - stop_price
        rr = (
            config.reduced_rr
            if config.rr_reduction_threshold_points is not None
            and risk_points >= config.rr_reduction_threshold_points
            else HUNTER_TARGET_RR
        )
        target_price = entry_price + risk_points * rr
    else:
        stop_price = candidate.signal_high + SL_BUFFER_POINTS
        risk_points = stop_price - entry_price
        rr = (
            config.reduced_rr
            if config.rr_reduction_threshold_points is not None
            and risk_points >= config.rr_reduction_threshold_points
            else HUNTER_TARGET_RR
        )
        target_price = entry_price - risk_points * rr

    if risk_points <= 0:
        return None

    qty = contracts_for_risk(risk_points)
    max_hold_cutoff = entry_dt + pd.Timedelta(minutes=config.max_hold_minutes)
    scan = df_1s.loc[entry_dt : max_hold_cutoff + pd.Timedelta(minutes=10)]
    if scan.empty:
        return None

    high = scan["high"].to_numpy()
    low = scan["low"].to_numpy()
    close = scan["close"].to_numpy()
    index_values = scan.index.to_numpy()
    hold_idx = int(np.searchsorted(index_values, np.datetime64(max_hold_cutoff), side="left"))
    if hold_idx >= len(scan):
        hold_idx = len(scan) - 1

    if candidate.side == "long":
        hit_stop_arr = low <= stop_price
        hit_target_arr = high >= target_price
    else:
        hit_stop_arr = high >= stop_price
        hit_target_arr = low <= target_price
    hit_any = hit_stop_arr | hit_target_arr
    hit_indices = np.flatnonzero(hit_any)

    if len(hit_indices) and int(hit_indices[0]) <= hold_idx:
        exit_idx = int(hit_indices[0])
        hit_stop = bool(hit_stop_arr[exit_idx])
        hit_target = bool(hit_target_arr[exit_idx])
        exit_dt = scan.index[exit_idx]
        if hit_stop and hit_target:
            exit_price = target_price if config.tie_policy == "target_first" else stop_price
        elif hit_stop:
            exit_price = stop_price
        else:
            exit_price = target_price
        exit_signal = "Hunter 2R"
    else:
        exit_idx = hold_idx
        exit_dt = scan.index[exit_idx]
        exit_price = float(close[exit_idx])
        exit_signal = "Max Hold Time"

    if candidate.side == "long":
        mfe_points = float(high[: exit_idx + 1].max() - entry_price)
        mae_points = float(min(0.0, low[: exit_idx + 1].min() - entry_price))
    else:
        mfe_points = float(entry_price - low[: exit_idx + 1].min())
        mae_points = float(min(0.0, entry_price - high[: exit_idx + 1].max()))

    gross_points = exit_price - entry_price if candidate.side == "long" else entry_price - exit_price
    pnl_usd = gross_points * POINT_VALUE * qty - COMMISSION_PER_CONTRACT_ROUND_TRIP * qty
    return VariantTrade(
        trade_no=trade_no,
        side=candidate.side,
        signal_dt=str(candidate.signal_dt),
        entry_dt=str(entry_dt),
        entry_key_dt=str(candidate.entry_dt),
        exit_dt=str(exit_dt),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        stop_price=round(stop_price, 2),
        target_price=round(target_price, 2),
        risk_points=round(risk_points, 2),
        rr=rr,
        qty=qty,
        pnl_usd=round(pnl_usd, 2),
        mfe_usd=round(mfe_points * POINT_VALUE * qty, 2),
        mae_usd=round(mae_points * POINT_VALUE * qty, 2),
        exit_signal=exit_signal,
        body_pct=round(candidate.body_pct, 4),
        rejection_wick_pct=round(candidate.rejection_wick_pct, 4),
        extension_pct=round(candidate.extension_pct, 4),
        variant=config.name,
    )


def can_take_candidate(
    candidate: Candidate,
    day_trades: list[VariantTrade],
    open_until: pd.Timestamp | None,
    config: VariantConfig,
) -> bool:
    if open_until is not None and candidate.entry_dt <= open_until:
        return False
    if not day_trades:
        return True

    if config.state_policy == "all_nonoverlap":
        return True
    if config.state_policy == "one_trade_per_day":
        return False

    last_trade = day_trades[-1]
    last_lost = last_trade.pnl_usd < 0 and last_trade.exit_signal == "Hunter 2R"
    same_side = last_trade.side == candidate.side
    if not last_lost:
        return False

    if config.state_policy == "after_each_loss_any_side":
        return True
    if config.state_policy == "after_each_loss_same_side":
        return same_side

    prior_reentries = max(0, len(day_trades) - 1)
    if config.state_policy == "current_any_side_one_reentry":
        return prior_reentries < 1
    if config.state_policy == "current_same_side_one_reentry":
        return prior_reentries < 1 and same_side

    raise ValueError(f"Unknown state policy: {config.state_policy}")


def run_variant(df_1s: pd.DataFrame, bars_5m: pd.DataFrame, config: VariantConfig) -> tuple[list[VariantTrade], int]:
    candidates = build_variant_candidates(bars_5m, config)
    candidates_by_day: dict[Any, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_day[candidate.entry_dt.date()].append(candidate)

    trades: list[VariantTrade] = []
    trade_no = 1
    for day in sorted(candidates_by_day):
        day_candidates = sorted(candidates_by_day[day], key=lambda c: c.entry_dt)
        day_trades: list[VariantTrade] = []
        open_until: pd.Timestamp | None = None
        for candidate in day_candidates:
            if not can_take_candidate(candidate, day_trades, open_until, config):
                continue
            trade = simulate_exit(candidate, df_1s, trade_no, config)
            if trade is None:
                continue
            trades.append(trade)
            day_trades.append(trade)
            trade_no += 1
            open_until = pd.Timestamp(trade.exit_dt)
    return trades, len(candidates)


def metric_block_from_pnl(pnl: pd.Series) -> dict[str, Any]:
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()
    return {
        "trades": int(len(pnl)),
        "net_pnl_usd": round(float(pnl.sum()), 2),
        "wins": int((pnl > 0).sum()),
        "win_rate": float((pnl > 0).mean()) if len(pnl) else 0.0,
        "profit_factor": float(gross_profit / gross_loss) if gross_loss else None,
    }


def trades_to_frame(trades: list[VariantTrade]) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame()
    df = pd.DataFrame([asdict(trade) for trade in trades])
    df["entry_key_dt"] = pd.to_datetime(df["entry_key_dt"])
    df["entry_dt"] = pd.to_datetime(df["entry_dt"])
    df["exit_dt"] = pd.to_datetime(df["exit_dt"])
    return df


def score_variant(config: VariantConfig, trades: list[VariantTrade], tv: pd.DataFrame) -> VariantScore:
    sim = trades_to_frame(trades)
    if sim.empty:
        sim_keys: set[tuple[pd.Timestamp, str]] = set()
    else:
        sim_keys = set(zip(sim["entry_key_dt"], sim["side"]))
    tv_keys = set(zip(tv["entry_key_dt"], tv["side"]))
    matched = sim_keys & tv_keys
    precision = len(matched) / len(sim_keys) if sim_keys else 0.0
    recall = len(matched) / len(tv_keys) if tv_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    jaccard = len(matched) / len(sim_keys | tv_keys) if sim_keys | tv_keys else 0.0

    tv_metrics = metric_block_from_pnl(tv["pnl_usd"])
    sim_metrics = metric_block_from_pnl(sim["pnl_usd"] if not sim.empty else pd.Series(dtype=float))
    tv_pf = tv_metrics["profit_factor"]
    sim_pf = sim_metrics["profit_factor"]
    net_delta = sim_metrics["net_pnl_usd"] - tv_metrics["net_pnl_usd"]
    net_accuracy = (
        1.0 - abs(net_delta) / abs(tv_metrics["net_pnl_usd"])
        if tv_metrics["net_pnl_usd"]
        else None
    )
    pf_accuracy = 1.0 - abs(sim_pf - tv_pf) / tv_pf if sim_pf is not None and tv_pf else None

    same_win_loss_rate = None
    median_abs_pnl_error = None
    mean_abs_pnl_error = None
    if not sim.empty:
        merged = sim.merge(tv, on=["entry_key_dt", "side"], suffixes=("_sim", "_tv"))
        if not merged.empty:
            same_win_loss_rate = float(((merged["pnl_usd_sim"] > 0) == (merged["pnl_usd_tv"] > 0)).mean())
            errors = (merged["pnl_usd_sim"] - merged["pnl_usd_tv"]).abs()
            median_abs_pnl_error = round(float(errors.median()), 2)
            mean_abs_pnl_error = round(float(errors.mean()), 2)

    score = (
        f1 * 100.0
        + max(0.0, net_accuracy or 0.0) * 20.0
        + max(0.0, pf_accuracy or 0.0) * 10.0
        + (same_win_loss_rate or 0.0) * 10.0
        - abs(len(sim_keys) - len(tv_keys)) * 0.05
    )
    exit_counts = dict(Counter(trade.exit_signal for trade in trades))
    qty_counts = dict(Counter(str(trade.qty) for trade in trades))
    return VariantScore(
        rank=0,
        name=config.name,
        state_policy=config.state_policy,
        ema15_tolerance_points=config.ema15_tolerance_points,
        body_min_pct=config.body_min_pct,
        overextension_max_pct=config.overextension_max_pct,
        rr_reduction_threshold_points=config.rr_reduction_threshold_points,
        reduced_rr=config.reduced_rr,
        max_hold_minutes=config.max_hold_minutes,
        tie_policy=config.tie_policy,
        score=round(score, 6),
        tv_trades=len(tv_keys),
        sim_trades=len(sim_keys),
        matched_entries=len(matched),
        missing_count=len(tv_keys - sim_keys),
        extra_count=len(sim_keys - tv_keys),
        entry_precision=round(precision, 6),
        entry_recall=round(recall, 6),
        entry_f1=round(f1, 6),
        entry_jaccard=round(jaccard, 6),
        same_win_loss_rate=round(same_win_loss_rate, 6) if same_win_loss_rate is not None else None,
        median_abs_pnl_error_usd=median_abs_pnl_error,
        mean_abs_pnl_error_usd=mean_abs_pnl_error,
        net_pnl_usd=sim_metrics["net_pnl_usd"],
        tv_net_pnl_usd=tv_metrics["net_pnl_usd"],
        net_delta_usd=round(net_delta, 2),
        net_accuracy=round(net_accuracy, 6) if net_accuracy is not None else None,
        win_rate=round(sim_metrics["win_rate"], 6),
        tv_win_rate=round(tv_metrics["win_rate"], 6),
        profit_factor=round(sim_pf, 6) if sim_pf is not None else None,
        tv_profit_factor=round(tv_pf, 6) if tv_pf is not None else None,
        pf_accuracy=round(pf_accuracy, 6) if pf_accuracy is not None else None,
        exit_counts=json.dumps(exit_counts, sort_keys=True),
        qty_counts=json.dumps(qty_counts, sort_keys=True),
    )


def make_config(
    state_policy: StatePolicy,
    ema_tol: float,
    body_min: float,
    overext: float | None,
    rr_threshold: float | None,
    reduced_rr: float,
    max_hold: int,
    tie_policy: TiePolicy,
) -> VariantConfig:
    name = (
        f"state={state_policy}|emaTol={ema_tol:g}|body={body_min:g}|"
        f"overext={overext if overext is not None else 'none'}|"
        f"rrTh={rr_threshold if rr_threshold is not None else 'none'}|"
        f"redRR={reduced_rr:g}|hold={max_hold}|tie={tie_policy}"
    )
    return VariantConfig(
        name=name,
        state_policy=state_policy,
        ema15_tolerance_points=ema_tol,
        body_min_pct=body_min,
        overextension_max_pct=overext,
        rr_reduction_threshold_points=rr_threshold,
        reduced_rr=reduced_rr,
        max_hold_minutes=max_hold,
        tie_policy=tie_policy,
    )


def build_configs(preset: str, limit: int | None = None) -> list[VariantConfig]:
    configs: list[VariantConfig] = []
    if preset == "targeted":
        # Stage 1: isolate entry/state policy effects with current exit mechanics.
        for state_policy, ema_tol, body_min, overext in product(
            [
                "current_any_side_one_reentry",
                "current_same_side_one_reentry",
                "after_each_loss_any_side",
                "after_each_loss_same_side",
                "one_trade_per_day",
                "all_nonoverlap",
            ],
            [0.0, 2.0, 6.0],
            [55.0, 50.0, 20.0],
            [None, 35.0],
        ):
            configs.append(make_config(state_policy, ema_tol, body_min, overext, 50.0, 1.0, 270, "stop_first"))

        # Stage 2: exit mechanics around the plausible re-entry policies.
        for (
            state_policy,
            ema_tol,
            body_min,
            rr_threshold,
            reduced_rr,
            max_hold,
            tie_policy,
        ) in product(
            [
                "current_any_side_one_reentry",
                "current_same_side_one_reentry",
                "after_each_loss_any_side",
                "after_each_loss_same_side",
            ],
            [0.0, 6.0],
            [55.0, 20.0],
            [50.0, 49.0, 48.0, 45.0, None],
            [1.0, 0.5],
            [270, 275],
            ["stop_first", "target_first"],
        ):
            if rr_threshold is None and reduced_rr != 1.0:
                continue
            configs.append(
                make_config(state_policy, ema_tol, body_min, None, rr_threshold, reduced_rr, max_hold, tie_policy)
            )

        # Deduplicate overlap between stages while preserving order.
        seen: set[str] = set()
        deduped = []
        for config in configs:
            if config.name in seen:
                continue
            seen.add(config.name)
            deduped.append(config)
        return deduped[:limit] if limit else deduped

    if preset != "full":
        raise ValueError(f"Unknown preset {preset!r}; expected 'targeted' or 'full'")

    state_policies: list[StatePolicy] = [
        "current_any_side_one_reentry",
        "current_same_side_one_reentry",
        "after_each_loss_any_side",
        "after_each_loss_same_side",
        "one_trade_per_day",
        "all_nonoverlap",
    ]
    ema_tolerances = [0.0, 2.0, 6.0]
    body_mins = [55.0, 50.0, 20.0]
    overextension_maxes: list[float | None] = [None, 35.0]
    rr_thresholds: list[float | None] = [50.0, 49.0, 48.0, 45.0, None]
    reduced_rrs = [1.0, 0.5]
    max_holds = [270, 275]
    tie_policies: list[TiePolicy] = ["stop_first", "target_first"]

    for (
        state_policy,
        ema_tol,
        body_min,
        overext,
        rr_threshold,
        reduced_rr,
        max_hold,
        tie_policy,
    ) in product(
        state_policies,
        ema_tolerances,
        body_mins,
        overextension_maxes,
        rr_thresholds,
        reduced_rrs,
        max_holds,
        tie_policies,
    ):
        if rr_threshold is None and reduced_rr != 1.0:
            continue
        configs.append(make_config(state_policy, ema_tol, body_min, overext, rr_threshold, reduced_rr, max_hold, tie_policy))
    return configs[:limit] if limit else configs


def write_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-csv", type=Path, required=True)
    parser.add_argument("--data-1s", type=Path, default=Path("data/raw/NQ_1s.parquet"))
    parser.add_argument("--es-data-1s", type=Path, default=Path("data/raw/ES_1s.parquet"))
    parser.add_argument("--start", default="2023-04-28")
    parser.add_argument("--end", default="2026-04-25")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--preset", choices=["targeted", "full"], default="targeted")
    parser.add_argument("--limit-configs", type=int, default=None)
    parser.add_argument("--save-best-trades", type=int, default=10)
    args = parser.parse_args()

    tv = export_to_frame(args.export_csv)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    df_1s = load_1s(args.data_1s, start, end)
    bars_5m = resample_5m(df_1s)
    es_bars = None
    if args.es_data_1s.exists():
        es_bars = resample_5m(load_1s(args.es_data_1s, start, end))
    bars_5m = add_indicator_features(bars_5m, es_bars)

    scores: list[VariantScore] = []
    best_trade_sets: list[tuple[VariantScore, list[VariantTrade]]] = []
    configs = build_configs(args.preset, args.limit_configs)
    for index, config in enumerate(configs, start=1):
        trades, _candidate_count = run_variant(df_1s, bars_5m, config)
        score = score_variant(config, trades, tv)
        scores.append(score)
        best_trade_sets.append((score, trades))
        if index % 100 == 0:
            print(f"scored {index}/{len(configs)} variants", flush=True)

    scores = sorted(scores, key=lambda row: (-row.score, -row.entry_f1, abs(row.net_delta_usd)))
    ranked_scores = [
        VariantScore(**{**asdict(score), "rank": rank})
        for rank, score in enumerate(scores, start=1)
    ]
    score_by_name = {score.name: score for score in scores}
    best_trade_sets = sorted(
        best_trade_sets,
        key=lambda item: (-score_by_name[item[0].name].score, -score_by_name[item[0].name].entry_f1, abs(score_by_name[item[0].name].net_delta_usd)),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "variant_scores.csv", ranked_scores)

    for rank, (score, trades) in enumerate(best_trade_sets[: args.save_best_trades], start=1):
        score = score_by_name[score.name]
        write_csv(args.output_dir / f"rank_{rank:02d}_trades.csv", trades)
        (args.output_dir / f"rank_{rank:02d}_config.json").write_text(
            json.dumps(asdict(score), indent=2),
            encoding="utf-8",
        )

    summary = {
        "start": args.start,
        "end": args.end,
        "configs_scored": len(configs),
        "preset": args.preset,
        "top_scores": [asdict(score) for score in ranked_scores[:20]],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
