#!/usr/bin/env python3
"""Sweep state timing rules for the Hunter/Classic ORB parity work."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.hunter_classic_parity_report import export_to_frame
from scripts.hunter_classic_parity_sweep import VariantConfig, VariantScore, VariantTrade, score_variant, simulate_exit
from scripts.run_hunter_classic_orb_replication import (
    ALLOWED_WEEKDAYS,
    BODY_MIN_PCT,
    REJECTION_WICK_MAX_PCT,
    SIGNAL_END,
    SIGNAL_START,
    Candidate,
    add_ema15_bias,
    body_rejection,
    load_1s,
    resample_5m,
)


@dataclass(frozen=True)
class StateTimingConfig:
    name: str
    min_reentry_minutes_from_entry: float
    min_reentry_minutes_from_exit: float
    reentry_body_min_pct: float
    allow_after_same_bar_win: bool
    allow_after_any_win: bool
    same_bar_win_minutes: float


@dataclass(frozen=True)
class StateTimingScore:
    rank: int
    name: str
    min_reentry_minutes_from_entry: float
    min_reentry_minutes_from_exit: float
    reentry_body_min_pct: float
    allow_after_same_bar_win: bool
    allow_after_any_win: bool
    same_bar_win_minutes: float
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
    win_rate: float
    tv_win_rate: float
    profit_factor: float | None
    tv_profit_factor: float | None
    recovered_remaining_misses: int
    remaining_misses: str
    extra_entries: str


REMAINING_MISSES = {
    (pd.Timestamp("2024-09-04 10:25:00"), "long"),
    (pd.Timestamp("2024-12-26 10:10:00"), "short"),
    (pd.Timestamp("2025-09-24 10:25:00"), "short"),
    (pd.Timestamp("2026-01-12 10:50:00"), "long"),
}


def build_loose_candidates(bars_5m: pd.DataFrame) -> list[Candidate]:
    bars_5m = add_ema15_bias(bars_5m, 14, source="close", timing="confirmed_prev")
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
                ema_value = float(row.ema15_bias)
                distance = float(row.close) - ema_value if side == "long" else ema_value - float(row.close)
                if distance < -2.0:
                    continue

                body_pct, rejection_pct = body_rejection(row, side)
                if body_pct < 20.0 or rejection_pct > REJECTION_WICK_MAX_PCT:
                    continue
                extension_pct = (
                    (float(row.close) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row.close)) / orb_range * 100.0
                )
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


def can_take_candidate(candidate: Candidate, day_trades: list[VariantTrade], open_until: pd.Timestamp | None, config: StateTimingConfig) -> bool:
    if open_until is not None and candidate.entry_dt <= open_until:
        return False
    if not day_trades:
        return candidate.body_pct >= BODY_MIN_PCT

    last_trade = day_trades[-1]
    last_entry = pd.Timestamp(last_trade.entry_dt)
    last_exit = pd.Timestamp(last_trade.exit_dt)
    minutes_from_entry = (candidate.entry_dt - last_entry).total_seconds() / 60.0
    minutes_from_exit = (candidate.entry_dt - last_exit).total_seconds() / 60.0

    if minutes_from_entry < config.min_reentry_minutes_from_entry:
        return False
    if minutes_from_exit < config.min_reentry_minutes_from_exit:
        return False

    last_lost = last_trade.pnl_usd < 0 and last_trade.exit_signal == "Hunter 2R"
    if last_lost:
        return candidate.body_pct >= config.reentry_body_min_pct

    if last_trade.pnl_usd > 0 and last_trade.exit_signal == "Hunter 2R":
        if config.allow_after_any_win:
            return candidate.body_pct >= BODY_MIN_PCT
        if config.allow_after_same_bar_win:
            win_minutes = (last_exit - last_entry).total_seconds() / 60.0
            return win_minutes <= config.same_bar_win_minutes and candidate.body_pct >= BODY_MIN_PCT

    return False


def exit_config(name: str) -> VariantConfig:
    return VariantConfig(
        name=name,
        state_policy="after_each_loss_any_side",
        ema15_tolerance_points=2.0,
        body_min_pct=BODY_MIN_PCT,
        overextension_max_pct=None,
        rr_reduction_threshold_points=50.0,
        reduced_rr=1.0,
        max_hold_minutes=270,
        tie_policy="stop_first",
    )


def run_variant(df_1s: pd.DataFrame, candidates: list[Candidate], config: StateTimingConfig) -> list[VariantTrade]:
    candidates_by_day: dict[Any, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_day[candidate.entry_dt.date()].append(candidate)

    trades: list[VariantTrade] = []
    trade_no = 1
    econfig = exit_config(config.name)
    for day in sorted(candidates_by_day):
        day_trades: list[VariantTrade] = []
        open_until: pd.Timestamp | None = None
        for candidate in sorted(candidates_by_day[day], key=lambda c: c.entry_dt):
            if not can_take_candidate(candidate, day_trades, open_until, config):
                continue
            trade = simulate_exit(candidate, df_1s, trade_no, econfig)
            if trade is None:
                continue
            trades.append(trade)
            day_trades.append(trade)
            open_until = pd.Timestamp(trade.exit_dt)
            trade_no += 1
    return trades


def build_configs() -> list[StateTimingConfig]:
    configs: list[StateTimingConfig] = []
    for min_from_entry, min_from_exit, reentry_body, same_bar_win, any_win, same_bar_minutes in product(
        [0.0, 20.0, 20.1, 25.0],
        [0.0, 5.0, 10.0, 10.1, 15.0],
        [55.0, 40.0, 20.0],
        [False, True],
        [False, True],
        [0.0, 5.0],
    ):
        if same_bar_win and any_win:
            continue
        if not same_bar_win and same_bar_minutes != 0.0:
            continue
        name = (
            f"entryDelay={min_from_entry:g}|exitDelay={min_from_exit:g}|"
            f"reBody={reentry_body:g}|sameBarWin={same_bar_win}|anyWin={any_win}|sameBarMin={same_bar_minutes:g}"
        )
        configs.append(
            StateTimingConfig(
                name=name,
                min_reentry_minutes_from_entry=min_from_entry,
                min_reentry_minutes_from_exit=min_from_exit,
                reentry_body_min_pct=reentry_body,
                allow_after_same_bar_win=same_bar_win,
                allow_after_any_win=any_win,
                same_bar_win_minutes=same_bar_minutes,
            )
        )
    return configs


def score_state_config(config: StateTimingConfig, trades: list[VariantTrade], tv: pd.DataFrame) -> StateTimingScore:
    base = score_variant(exit_config(config.name), trades, tv)
    sim_keys = {(pd.Timestamp(trade.entry_key_dt), trade.side) for trade in trades}
    tv_keys = set(zip(tv["entry_key_dt"], tv["side"]))
    recovered = len(REMAINING_MISSES & sim_keys)
    remaining = sorted(str(item) for item in REMAINING_MISSES - sim_keys)
    extras = sorted(str(item) for item in sim_keys - tv_keys)
    score = (
        base.entry_f1 * 100.0
        + (base.same_win_loss_rate or 0.0) * 10.0
        + (base.net_accuracy or 0.0) * 8.0
        + recovered * 2.5
        - base.extra_count * 0.05
    )
    return StateTimingScore(
        rank=0,
        name=config.name,
        min_reentry_minutes_from_entry=config.min_reentry_minutes_from_entry,
        min_reentry_minutes_from_exit=config.min_reentry_minutes_from_exit,
        reentry_body_min_pct=config.reentry_body_min_pct,
        allow_after_same_bar_win=config.allow_after_same_bar_win,
        allow_after_any_win=config.allow_after_any_win,
        same_bar_win_minutes=config.same_bar_win_minutes,
        score=round(score, 6),
        tv_trades=base.tv_trades,
        sim_trades=base.sim_trades,
        matched_entries=base.matched_entries,
        missing_count=base.missing_count,
        extra_count=base.extra_count,
        entry_precision=base.entry_precision,
        entry_recall=base.entry_recall,
        entry_f1=base.entry_f1,
        entry_jaccard=base.entry_jaccard,
        same_win_loss_rate=base.same_win_loss_rate,
        median_abs_pnl_error_usd=base.median_abs_pnl_error_usd,
        mean_abs_pnl_error_usd=base.mean_abs_pnl_error_usd,
        net_pnl_usd=base.net_pnl_usd,
        tv_net_pnl_usd=base.tv_net_pnl_usd,
        net_delta_usd=base.net_delta_usd,
        win_rate=base.win_rate,
        tv_win_rate=base.tv_win_rate,
        profit_factor=base.profit_factor,
        tv_profit_factor=base.tv_profit_factor,
        recovered_remaining_misses=recovered,
        remaining_misses=json.dumps(remaining),
        extra_entries=json.dumps(extras[:80]),
    )


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
    parser.add_argument("--start", default="2023-04-28")
    parser.add_argument("--end", default="2026-04-25")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--save-best-trades", type=int, default=5)
    args = parser.parse_args()

    tv = export_to_frame(args.export_csv)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    df_1s = load_1s(args.data_1s, start, end)
    candidates = build_loose_candidates(resample_5m(df_1s))
    configs = build_configs()

    scores: list[StateTimingScore] = []
    trade_sets: list[tuple[StateTimingScore, list[VariantTrade]]] = []
    for index, config in enumerate(configs, start=1):
        trades = run_variant(df_1s, candidates, config)
        score = score_state_config(config, trades, tv)
        scores.append(score)
        trade_sets.append((score, trades))
        if index % 50 == 0:
            print(f"scored {index}/{len(configs)} state timing variants", flush=True)

    scores = sorted(scores, key=lambda row: (-row.score, -row.entry_f1, row.extra_count, abs(row.net_delta_usd)))
    ranked = [StateTimingScore(**{**asdict(score), "rank": rank}) for rank, score in enumerate(scores, start=1)]
    by_name = {score.name: score for score in ranked}
    trade_sets = sorted(
        trade_sets,
        key=lambda item: (-by_name[item[0].name].score, -by_name[item[0].name].entry_f1, by_name[item[0].name].extra_count),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "state_timing_scores.csv", ranked)
    for rank, (score, trades) in enumerate(trade_sets[: args.save_best_trades], start=1):
        write_csv(args.output_dir / f"rank_{rank:02d}_trades.csv", trades)
        (args.output_dir / f"rank_{rank:02d}_config.json").write_text(
            json.dumps(asdict(by_name[score.name]), indent=2),
            encoding="utf-8",
        )

    summary = {
        "start": args.start,
        "end": args.end,
        "configs_scored": len(configs),
        "loose_candidate_count": len(candidates),
        "top_scores": [asdict(score) for score in ranked[:20]],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
