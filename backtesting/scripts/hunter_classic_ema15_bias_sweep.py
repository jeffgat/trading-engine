#!/usr/bin/env python3
"""Sweep 15-minute EMA bias interpretations for Hunter/Classic parity."""

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
from scripts.hunter_classic_parity_sweep import (
    VariantConfig,
    VariantTrade,
    can_take_candidate,
    score_variant,
    simulate_exit,
    trades_to_frame,
)
from scripts.run_hunter_classic_orb_replication import (
    ALLOWED_WEEKDAYS,
    BODY_MIN_PCT,
    REJECTION_WICK_MAX_PCT,
    SIGNAL_END,
    SIGNAL_START,
    Candidate,
    body_rejection,
    load_1s,
    resample_5m,
)


@dataclass(frozen=True)
class EmaVariant:
    name: str
    length: int
    timing: str
    source: str
    direction_mode: str
    tolerance_points: float
    max_distance_points: float | None


@dataclass(frozen=True)
class EmaScore:
    rank: int
    name: str
    length: int
    timing: str
    source: str
    direction_mode: str
    tolerance_points: float
    max_distance_points: float | None
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
    recovered_known_ema_misses: int
    remaining_known_ema_misses: str


KNOWN_EMA_MISSES = {
    (pd.Timestamp("2023-06-02 09:50:00"), "short"),
    (pd.Timestamp("2024-06-07 10:35:00"), "long"),
}


def make_source(df: pd.DataFrame, source: str) -> pd.Series:
    if source == "close":
        return df["close"]
    if source == "hl2":
        return (df["high"] + df["low"]) / 2.0
    if source == "hlc3":
        return (df["high"] + df["low"] + df["close"]) / 3.0
    if source == "ohlc4":
        return (df["open"] + df["high"] + df["low"] + df["close"]) / 4.0
    if source == "high":
        return df["high"]
    if source == "low":
        return df["low"]
    raise ValueError(f"Unknown EMA source {source}")


def add_ema_columns(bars_5m: pd.DataFrame, variants: list[EmaVariant]) -> pd.DataFrame:
    bars = bars_5m.copy()
    bars_15m = (
        bars.resample("15min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    for variant in variants:
        key = f"ema_{variant.length}_{variant.timing}_{variant.source}"
        if key in bars.columns:
            continue
        source_15m = make_source(bars_15m, variant.source)
        ema_15m = source_15m.ewm(span=variant.length, adjust=False).mean()
        if variant.timing == "current_final":
            series = ema_15m.reindex(bars.index, method="ffill")
        elif variant.timing == "confirmed_prev":
            series = ema_15m.shift(1).reindex(bars.index, method="ffill")
        elif variant.timing == "bar_close_only":
            series = ema_15m.reindex(bars.index).ffill()
        else:
            raise ValueError(f"Unknown EMA timing {variant.timing}")
        bars[key] = series

    for length in sorted({variant.length for variant in variants}):
        for timing in sorted({variant.timing for variant in variants}):
            for source in ["high", "low", "close"]:
                key = f"ema_{length}_{timing}_{source}"
                if key in bars.columns:
                    continue
                source_15m = make_source(bars_15m, source)
                ema_15m = source_15m.ewm(span=length, adjust=False).mean()
                if timing == "current_final":
                    series = ema_15m.reindex(bars.index, method="ffill")
                elif timing == "confirmed_prev":
                    series = ema_15m.shift(1).reindex(bars.index, method="ffill")
                elif timing == "bar_close_only":
                    series = ema_15m.reindex(bars.index).ffill()
                else:
                    continue
                bars[key] = series
    return bars


def ema_pass(row: pd.Series, side: str, variant: EmaVariant) -> bool:
    base_key = f"ema_{variant.length}_{variant.timing}_{variant.source}"
    if variant.direction_mode == "single":
        ema_value = float(row[base_key])
        if side == "long":
            distance = float(row.close) - ema_value
        else:
            distance = ema_value - float(row.close)
    elif variant.direction_mode == "high_close_cloud":
        if side == "long":
            ema_value = float(row[f"ema_{variant.length}_{variant.timing}_high"])
            distance = float(row.close) - ema_value
        else:
            ema_value = float(row[f"ema_{variant.length}_{variant.timing}_close"])
            distance = ema_value - float(row.close)
    elif variant.direction_mode == "high_low_cloud":
        if side == "long":
            ema_value = float(row[f"ema_{variant.length}_{variant.timing}_high"])
            distance = float(row.close) - ema_value
        else:
            ema_value = float(row[f"ema_{variant.length}_{variant.timing}_low"])
            distance = ema_value - float(row.close)
    else:
        raise ValueError(f"Unknown direction mode {variant.direction_mode}")

    if pd.isna(distance):
        return False
    if distance < -variant.tolerance_points:
        return False
    if variant.max_distance_points is not None and distance > variant.max_distance_points:
        return False
    return True


def build_candidates(bars_5m: pd.DataFrame, variant: EmaVariant) -> list[Candidate]:
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
                if not ema_pass(row, side, variant):
                    continue
                body_pct, rejection_pct = body_rejection(row, side)
                if body_pct < BODY_MIN_PCT or rejection_pct > REJECTION_WICK_MAX_PCT:
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


def run_variant(df_1s: pd.DataFrame, bars_5m: pd.DataFrame, ema_variant: EmaVariant) -> list[VariantTrade]:
    exit_config = VariantConfig(
        name=ema_variant.name,
        state_policy="after_each_loss_any_side",
        ema15_tolerance_points=ema_variant.tolerance_points,
        body_min_pct=BODY_MIN_PCT,
        overextension_max_pct=None,
        rr_reduction_threshold_points=50.0,
        reduced_rr=1.0,
        max_hold_minutes=270,
        tie_policy="stop_first",
    )
    candidates = build_candidates(bars_5m, ema_variant)
    candidates_by_day: dict[Any, list[Candidate]] = defaultdict(list)
    for candidate in candidates:
        candidates_by_day[candidate.entry_dt.date()].append(candidate)

    trades: list[VariantTrade] = []
    trade_no = 1
    for day in sorted(candidates_by_day):
        day_trades: list[VariantTrade] = []
        open_until: pd.Timestamp | None = None
        for candidate in sorted(candidates_by_day[day], key=lambda c: c.entry_dt):
            if not can_take_candidate(candidate, day_trades, open_until, exit_config):
                continue
            trade = simulate_exit(candidate, df_1s, trade_no, exit_config)
            if trade is None:
                continue
            trades.append(trade)
            day_trades.append(trade)
            open_until = pd.Timestamp(trade.exit_dt)
            trade_no += 1
    return trades


def build_variants(limit: int | None = None) -> list[EmaVariant]:
    variants: list[EmaVariant] = []
    for length, timing, source, mode, tol, max_dist in product(
        [9, 14, 21, 50, 100, 200],
        ["current_final", "confirmed_prev", "bar_close_only"],
        ["close", "hl2", "hlc3", "ohlc4"],
        ["single"],
        [0.0, 2.0, 6.0],
        [None, 100.0],
    ):
        name = f"len={length}|timing={timing}|source={source}|mode={mode}|tol={tol:g}|maxDist={max_dist or 'none'}"
        variants.append(EmaVariant(name, length, timing, source, mode, tol, max_dist))

    for length, timing, mode, tol, max_dist in product(
        [9, 14, 21, 50, 100, 200],
        ["current_final", "confirmed_prev", "bar_close_only"],
        ["high_close_cloud", "high_low_cloud"],
        [0.0, 2.0, 6.0],
        [None, 100.0],
    ):
        name = f"len={length}|timing={timing}|source=cloud|mode={mode}|tol={tol:g}|maxDist={max_dist or 'none'}"
        variants.append(EmaVariant(name, length, timing, "close", mode, tol, max_dist))
    return variants[:limit] if limit else variants


def score_ema_variant(ema_variant: EmaVariant, trades: list[VariantTrade], tv: pd.DataFrame) -> EmaScore:
    exit_config = VariantConfig(
        name=ema_variant.name,
        state_policy="after_each_loss_any_side",
        ema15_tolerance_points=ema_variant.tolerance_points,
        body_min_pct=BODY_MIN_PCT,
        overextension_max_pct=None,
        rr_reduction_threshold_points=50.0,
        reduced_rr=1.0,
        max_hold_minutes=270,
        tie_policy="stop_first",
    )
    base_score = score_variant(exit_config, trades, tv)
    sim = trades_to_frame(trades)
    sim_keys = set(zip(sim["entry_key_dt"], sim["side"])) if not sim.empty else set()
    recovered = len(KNOWN_EMA_MISSES & sim_keys)
    remaining = sorted(str(item) for item in KNOWN_EMA_MISSES - sim_keys)
    score = (
        base_score.entry_f1 * 100.0
        + (base_score.net_accuracy or 0.0) * 10.0
        + (base_score.same_win_loss_rate or 0.0) * 10.0
        + recovered * 2.0
        - base_score.extra_count * 0.03
    )
    return EmaScore(
        rank=0,
        name=ema_variant.name,
        length=ema_variant.length,
        timing=ema_variant.timing,
        source=ema_variant.source,
        direction_mode=ema_variant.direction_mode,
        tolerance_points=ema_variant.tolerance_points,
        max_distance_points=ema_variant.max_distance_points,
        score=round(score, 6),
        tv_trades=base_score.tv_trades,
        sim_trades=base_score.sim_trades,
        matched_entries=base_score.matched_entries,
        missing_count=base_score.missing_count,
        extra_count=base_score.extra_count,
        entry_precision=base_score.entry_precision,
        entry_recall=base_score.entry_recall,
        entry_f1=base_score.entry_f1,
        entry_jaccard=base_score.entry_jaccard,
        same_win_loss_rate=base_score.same_win_loss_rate,
        median_abs_pnl_error_usd=base_score.median_abs_pnl_error_usd,
        mean_abs_pnl_error_usd=base_score.mean_abs_pnl_error_usd,
        net_pnl_usd=base_score.net_pnl_usd,
        tv_net_pnl_usd=base_score.tv_net_pnl_usd,
        net_delta_usd=base_score.net_delta_usd,
        win_rate=base_score.win_rate,
        tv_win_rate=base_score.tv_win_rate,
        profit_factor=base_score.profit_factor,
        tv_profit_factor=base_score.tv_profit_factor,
        recovered_known_ema_misses=recovered,
        remaining_known_ema_misses=json.dumps(remaining),
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
    parser.add_argument("--limit-configs", type=int, default=None)
    parser.add_argument("--save-best-trades", type=int, default=5)
    args = parser.parse_args()

    tv = export_to_frame(args.export_csv)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end)
    df_1s = load_1s(args.data_1s, start, end)
    bars_5m = resample_5m(df_1s)
    variants = build_variants(args.limit_configs)
    bars_5m = add_ema_columns(bars_5m, variants)

    scores: list[EmaScore] = []
    trade_sets: list[tuple[EmaScore, list[VariantTrade]]] = []
    for index, variant in enumerate(variants, start=1):
        trades = run_variant(df_1s, bars_5m, variant)
        score = score_ema_variant(variant, trades, tv)
        scores.append(score)
        trade_sets.append((score, trades))
        if index % 100 == 0:
            print(f"scored {index}/{len(variants)} EMA variants", flush=True)

    scores = sorted(scores, key=lambda row: (-row.score, -row.entry_f1, row.extra_count, abs(row.net_delta_usd)))
    ranked_scores = [EmaScore(**{**asdict(score), "rank": rank}) for rank, score in enumerate(scores, start=1)]
    score_by_name = {score.name: score for score in ranked_scores}
    trade_sets = sorted(
        trade_sets,
        key=lambda item: (
            -score_by_name[item[0].name].score,
            -score_by_name[item[0].name].entry_f1,
            score_by_name[item[0].name].extra_count,
            abs(score_by_name[item[0].name].net_delta_usd),
        ),
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "ema_variant_scores.csv", ranked_scores)
    for rank, (score, trades) in enumerate(trade_sets[: args.save_best_trades], start=1):
        write_csv(args.output_dir / f"rank_{rank:02d}_trades.csv", trades)
        (args.output_dir / f"rank_{rank:02d}_config.json").write_text(
            json.dumps(asdict(score_by_name[score.name]), indent=2),
            encoding="utf-8",
        )

    summary = {
        "start": args.start,
        "end": args.end,
        "variants_scored": len(variants),
        "top_scores": [asdict(score) for score in ranked_scores[:20]],
    }
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
