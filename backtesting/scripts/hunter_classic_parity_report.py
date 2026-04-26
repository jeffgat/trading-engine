#!/usr/bin/env python3
"""Create a focused parity report for the Hunter/Classic ORB replication.

This is a research diagnostic for the TradingView N4A ORB reverse-engineering
work. It compares exported TradingView trades to the current local replication
and produces an autopsy of entry mismatches plus the largest matched-trade P&L
outliers.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_hunter_classic_orb_replication import (
    BODY_MIN_PCT,
    COMMISSION_PER_CONTRACT_ROUND_TRIP,
    INITIAL_CAPITAL,
    POINT_VALUE,
    REJECTION_WICK_MAX_PCT,
    SIGNAL_START,
    SIGNAL_END,
    build_candidates,
    body_rejection,
    load_1s,
    read_export,
    resample_5m,
)


@dataclass(frozen=True)
class MismatchRow:
    kind: str
    entry_dt: str
    side: str
    year: int
    reason: str
    tv_trade_no: int | None
    sim_trade_no: int | None
    tv_pnl_usd: float | None
    sim_pnl_usd: float | None
    tv_exit_dt: str | None
    sim_exit_dt: str | None
    tv_exit_signal: str | None
    sim_exit_signal: str | None
    tv_position_open_at_entry: bool
    sim_position_open_at_entry: bool
    orb_high: float | None
    orb_low: float | None
    orb_range: float | None
    prev_close: float | None
    signal_open: float | None
    signal_high: float | None
    signal_low: float | None
    signal_close: float | None
    cross_side_on_local_close: bool | None
    body_pct: float | None
    body_pass: bool | None
    rejection_wick_pct: float | None
    rejection_pass: bool | None
    extension_pct_of_orb: float | None
    overextension_gt_35: bool | None
    ema15_close_14: float | None
    ema15_distance_points: float | None
    ema15_bias_pass: bool | None
    ema9_close: float | None
    ema9_close_pass: bool | None
    ema9_cloud_pass: bool | None
    ema200_close: float | None
    ema200_close_pass: bool | None
    ema200_cloud_pass: bool | None
    volume_ratio_sma20: float | None
    volume_2x_pass: bool | None
    wae_momentum: float | None
    wae_direction_pass: bool | None
    rg_filter: float | None
    rg_direction: int | None
    rg_pass: bool | None
    nq_extreme_15: bool | None
    es_extreme_15: bool | None
    smt_divergence_15: bool | None
    es_confirm_same_extreme_15: bool | None


@dataclass(frozen=True)
class OutlierRow:
    entry_dt: str
    side: str
    year: int
    tv_trade_no: int
    sim_trade_no: int
    pnl_delta_usd: float
    abs_pnl_delta_usd: float
    tv_pnl_usd: float
    sim_pnl_usd: float
    same_win_loss: bool
    tv_qty: int
    sim_qty: int
    tv_exit_dt: str
    sim_exit_dt: str
    exit_delta_minutes: float
    tv_exit_signal: str
    sim_exit_signal: str
    sim_risk_points: float
    sim_rr: float
    sim_body_pct: float
    sim_rejection_wick_pct: float
    sim_extension_pct: float


@dataclass(frozen=True)
class FilterDamageRow:
    test_name: str
    rule: str
    removed_total: int
    removed_matched: int
    removed_extra: int
    kept_matched: int
    kept_extra: int
    note: str


def parse_sim(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    for column in ["signal_dt", "entry_dt", "exit_dt"]:
        df[column] = pd.to_datetime(df[column])
    df["entry_key_dt"] = df["signal_dt"] + pd.Timedelta(minutes=5)
    return df


def export_to_frame(path: Path) -> pd.DataFrame:
    records = []
    for trade in read_export(path):
        records.append(
            {
                **asdict(trade),
                "entry_key_dt": trade.entry_dt,
            }
        )
    df = pd.DataFrame(records)
    if not df.empty:
        for column in ["entry_dt", "exit_dt", "entry_key_dt"]:
            df[column] = pd.to_datetime(df[column])
    return df


def add_indicator_features(bars: pd.DataFrame, es_bars: pd.DataFrame | None) -> pd.DataFrame:
    out = bars.copy()

    bars_15m = (
        out.resample("15min", label="left", closed="left")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna()
    )
    ema15 = bars_15m["close"].ewm(span=14, adjust=False).mean()
    out["ema15_close_14"] = ema15.reindex(out.index, method="ffill")

    out["ema9_close"] = out["close"].ewm(span=9, adjust=False).mean()
    out["ema9_high"] = out["high"].ewm(span=9, adjust=False).mean()
    out["ema200_close"] = out["close"].ewm(span=200, adjust=False).mean()
    out["ema200_high"] = out["high"].ewm(span=200, adjust=False).mean()
    out["vol_sma20"] = out["volume"].rolling(20).mean()
    out["volume_ratio_sma20"] = out["volume"] / out["vol_sma20"]

    fast = out["close"].ewm(span=8, adjust=False).mean()
    slow = out["close"].ewm(span=100, adjust=False).mean()
    out["wae_momentum"] = (fast - slow).diff() * 250.0

    smooth_range = out["close"].diff().abs().ewm(span=50, adjust=False).mean()
    smooth_range = smooth_range.ewm(span=99, adjust=False).mean() * 6.0
    filt: list[float] = []
    directions: list[int] = []
    prev_filter: float | None = None
    prev_direction = 0
    for close, rng in zip(out["close"], smooth_range):
        if pd.isna(rng):
            current_filter = float(close)
        elif prev_filter is None:
            current_filter = float(close)
        elif close > prev_filter:
            current_filter = max(float(close) - float(rng), prev_filter)
        elif close < prev_filter:
            current_filter = min(float(close) + float(rng), prev_filter)
        else:
            current_filter = prev_filter

        if prev_filter is None:
            direction = 0
        elif current_filter > prev_filter:
            direction = 1
        elif current_filter < prev_filter:
            direction = -1
        else:
            direction = prev_direction
        filt.append(current_filter)
        directions.append(direction)
        prev_filter = current_filter
        prev_direction = direction
    out["rg_filter"] = filt
    out["rg_direction"] = directions

    out["nq_new_high_15"] = out["high"] >= out["high"].shift(1).rolling(15).max()
    out["nq_new_low_15"] = out["low"] <= out["low"].shift(1).rolling(15).min()
    if es_bars is not None and not es_bars.empty:
        es = es_bars.reindex(out.index, method="ffill")
        out["es_new_high_15"] = es["high"] >= es["high"].shift(1).rolling(15).max()
        out["es_new_low_15"] = es["low"] <= es["low"].shift(1).rolling(15).min()
    else:
        out["es_new_high_15"] = pd.NA
        out["es_new_low_15"] = pd.NA

    return out


def day_levels(bars: pd.DataFrame) -> dict[Any, tuple[float, float]]:
    levels: dict[Any, tuple[float, float]] = {}
    for day, group in bars.groupby(bars.index.date):
        orb = group.between_time("09:30", "09:40")
        if len(orb) >= 3:
            levels[day] = (float(orb.high.max()), float(orb.low.min()))
    return levels


def bool_or_none(value: Any) -> bool | None:
    if pd.isna(value):
        return None
    return bool(value)


def round_or_none(value: Any, digits: int = 4) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), digits)


def side_filter_value(row: pd.Series, side: str, long_column: str, short_column: str) -> bool | None:
    value = row[long_column] if side == "long" else row[short_column]
    return bool_or_none(value)


def feature_snapshot(
    entry_dt: pd.Timestamp,
    side: str,
    bars: pd.DataFrame,
    levels: dict[Any, tuple[float, float]],
) -> dict[str, Any]:
    signal_dt = entry_dt - pd.Timedelta(minutes=5)
    if signal_dt not in bars.index or signal_dt.date() not in levels:
        return {
            "reason_hint": "missing_local_signal_bar_or_orb",
            "orb_high": None,
            "orb_low": None,
            "orb_range": None,
            "prev_close": None,
            "signal_open": None,
            "signal_high": None,
            "signal_low": None,
            "signal_close": None,
            "cross_side_on_local_close": None,
            "body_pct": None,
            "body_pass": None,
            "rejection_wick_pct": None,
            "rejection_pass": None,
            "extension_pct_of_orb": None,
            "overextension_gt_35": None,
            "ema15_close_14": None,
            "ema15_distance_points": None,
            "ema15_bias_pass": None,
            "ema9_close": None,
            "ema9_close_pass": None,
            "ema9_cloud_pass": None,
            "ema200_close": None,
            "ema200_close_pass": None,
            "ema200_cloud_pass": None,
            "volume_ratio_sma20": None,
            "volume_2x_pass": None,
            "wae_momentum": None,
            "wae_direction_pass": None,
            "rg_filter": None,
            "rg_direction": None,
            "rg_pass": None,
            "nq_extreme_15": None,
            "es_extreme_15": None,
            "smt_divergence_15": None,
            "es_confirm_same_extreme_15": None,
        }

    day_group = bars[bars.index.date == signal_dt.date()]
    pos = day_group.index.get_loc(signal_dt)
    row = bars.loc[signal_dt]
    prev_close = float(day_group.iloc[pos - 1].close) if pos > 0 else None
    orb_high, orb_low = levels[signal_dt.date()]
    orb_range = max(orb_high - orb_low, 1e-9)
    body_pct, rejection_pct = body_rejection(row, side)
    if side == "long":
        crossed = prev_close is not None and float(row.close) > orb_high and prev_close <= orb_high
        extension_pct = (float(row.close) - orb_high) / orb_range * 100.0
        ema15_dist = float(row.close) - float(row.ema15_close_14)
        ema15_pass = float(row.close) > float(row.ema15_close_14)
        ema9_close_pass = float(row.close) > float(row.ema9_close)
        ema9_cloud_pass = float(row.close) > float(row.ema9_high)
        ema200_close_pass = float(row.close) > float(row.ema200_close)
        ema200_cloud_pass = float(row.close) > float(row.ema200_high)
        wae_pass = float(row.wae_momentum) > 0
        rg_pass = float(row.close) > float(row.rg_filter) and int(row.rg_direction) >= 0
        nq_extreme = bool_or_none(row.nq_new_high_15)
        es_extreme = bool_or_none(row.es_new_high_15)
    else:
        crossed = prev_close is not None and float(row.close) < orb_low and prev_close >= orb_low
        extension_pct = (orb_low - float(row.close)) / orb_range * 100.0
        ema15_dist = float(row.ema15_close_14) - float(row.close)
        ema15_pass = float(row.close) < float(row.ema15_close_14)
        ema9_close_pass = float(row.close) < float(row.ema9_close)
        ema9_cloud_pass = float(row.close) < float(row.ema9_close)
        ema200_close_pass = float(row.close) < float(row.ema200_close)
        ema200_cloud_pass = float(row.close) < float(row.ema200_close)
        wae_pass = float(row.wae_momentum) < 0
        rg_pass = float(row.close) < float(row.rg_filter) and int(row.rg_direction) <= 0
        nq_extreme = bool_or_none(row.nq_new_low_15)
        es_extreme = bool_or_none(row.es_new_low_15)

    smt_div = None if es_extreme is None or nq_extreme is None else bool(nq_extreme and not es_extreme)
    es_confirm = None if es_extreme is None or nq_extreme is None else bool(nq_extreme and es_extreme)
    vol_ratio = round_or_none(row.volume_ratio_sma20, 4)

    return {
        "reason_hint": None,
        "orb_high": round_or_none(orb_high),
        "orb_low": round_or_none(orb_low),
        "orb_range": round_or_none(orb_range),
        "prev_close": round_or_none(prev_close),
        "signal_open": round_or_none(row.open),
        "signal_high": round_or_none(row.high),
        "signal_low": round_or_none(row.low),
        "signal_close": round_or_none(row.close),
        "cross_side_on_local_close": crossed,
        "body_pct": round(body_pct, 4),
        "body_pass": body_pct >= BODY_MIN_PCT,
        "rejection_wick_pct": round(rejection_pct, 4),
        "rejection_pass": rejection_pct <= REJECTION_WICK_MAX_PCT,
        "extension_pct_of_orb": round(extension_pct, 4),
        "overextension_gt_35": extension_pct > 35.0,
        "ema15_close_14": round_or_none(row.ema15_close_14),
        "ema15_distance_points": round_or_none(ema15_dist),
        "ema15_bias_pass": ema15_pass,
        "ema9_close": round_or_none(row.ema9_close),
        "ema9_close_pass": ema9_close_pass,
        "ema9_cloud_pass": ema9_cloud_pass,
        "ema200_close": round_or_none(row.ema200_close),
        "ema200_close_pass": ema200_close_pass,
        "ema200_cloud_pass": ema200_cloud_pass,
        "volume_ratio_sma20": vol_ratio,
        "volume_2x_pass": None if vol_ratio is None else vol_ratio >= 2.0,
        "wae_momentum": round_or_none(row.wae_momentum, 6),
        "wae_direction_pass": wae_pass,
        "rg_filter": round_or_none(row.rg_filter),
        "rg_direction": int(row.rg_direction),
        "rg_pass": rg_pass,
        "nq_extreme_15": nq_extreme,
        "es_extreme_15": es_extreme,
        "smt_divergence_15": smt_div,
        "es_confirm_same_extreme_15": es_confirm,
    }


def position_open_at(entry_dt: pd.Timestamp, trades: pd.DataFrame) -> bool:
    if trades.empty:
        return False
    same_day = trades[trades["entry_key_dt"].dt.date == entry_dt.date()]
    return bool(((same_day["entry_key_dt"] < entry_dt) & (entry_dt <= same_day["exit_dt"])).any())


def infer_missing_reason(features: dict[str, Any], sim_open: bool) -> str:
    if features["reason_hint"]:
        return features["reason_hint"]
    if not features["cross_side_on_local_close"]:
        return "local_signal_does_not_cross_orb"
    if not features["body_pass"]:
        return "local_body_filter_failed"
    if not features["rejection_pass"]:
        return "local_rejection_wick_filter_failed"
    if not features["ema15_bias_pass"]:
        return "ema15_bias_filter_failed"
    if sim_open:
        return "sim_trade_management_blocked"
    return "candidate_exists_but_sim_skipped_unknown"


def infer_extra_reason(features: dict[str, Any], tv_open: bool) -> str:
    if tv_open:
        return "tv_trade_management_blocked"
    if features["overextension_gt_35"]:
        return "possible_overextension_filter"
    if features["smt_divergence_15"] is False:
        return "possible_smt_divergence_requirement"
    if features["volume_2x_pass"] is False:
        return "possible_volume_filter_but_low_confidence"
    if features["rg_pass"] is False:
        return "possible_rg_filter"
    return "unknown_secondary_filter_or_data_difference"


def build_mismatch_rows(
    sim: pd.DataFrame,
    tv: pd.DataFrame,
    bars: pd.DataFrame,
    levels: dict[Any, tuple[float, float]],
) -> list[MismatchRow]:
    sim_by_key = {(row.entry_key_dt, row.side): row for row in sim.itertuples(index=False)}
    tv_by_key = {(row.entry_key_dt, row.side): row for row in tv.itertuples(index=False)}
    sim_keys = set(sim_by_key)
    tv_keys = set(tv_by_key)

    rows: list[MismatchRow] = []
    for kind, keys in [
        ("missing_tv_trade", sorted(tv_keys - sim_keys)),
        ("extra_sim_trade", sorted(sim_keys - tv_keys)),
    ]:
        for entry_dt, side in keys:
            tv_row = tv_by_key.get((entry_dt, side))
            sim_row = sim_by_key.get((entry_dt, side))
            features = feature_snapshot(entry_dt, side, bars, levels)
            tv_open = position_open_at(entry_dt, tv)
            sim_open = position_open_at(entry_dt, sim)
            reason = (
                infer_missing_reason(features, sim_open)
                if kind == "missing_tv_trade"
                else infer_extra_reason(features, tv_open)
            )
            rows.append(
                MismatchRow(
                    kind=kind,
                    entry_dt=str(entry_dt),
                    side=side,
                    year=int(entry_dt.year),
                    reason=reason,
                    tv_trade_no=int(tv_row.trade_no) if tv_row is not None else None,
                    sim_trade_no=int(sim_row.trade_no) if sim_row is not None else None,
                    tv_pnl_usd=round_or_none(tv_row.pnl_usd, 2) if tv_row is not None else None,
                    sim_pnl_usd=round_or_none(sim_row.pnl_usd, 2) if sim_row is not None else None,
                    tv_exit_dt=str(tv_row.exit_dt) if tv_row is not None else None,
                    sim_exit_dt=str(sim_row.exit_dt) if sim_row is not None else None,
                    tv_exit_signal=tv_row.exit_signal if tv_row is not None else None,
                    sim_exit_signal=sim_row.exit_signal if sim_row is not None else None,
                    tv_position_open_at_entry=tv_open,
                    sim_position_open_at_entry=sim_open,
                    **{key: features[key] for key in MismatchRow.__dataclass_fields__ if key in features},
                )
            )
    return rows


def build_outliers(sim: pd.DataFrame, tv: pd.DataFrame, limit: int) -> list[OutlierRow]:
    merged = sim.merge(tv, on=["entry_key_dt", "side"], suffixes=("_sim", "_tv"))
    merged["pnl_delta_usd"] = merged["pnl_usd_sim"] - merged["pnl_usd_tv"]
    merged["abs_pnl_delta_usd"] = merged["pnl_delta_usd"].abs()
    merged["exit_delta_minutes"] = (
        (merged["exit_dt_sim"] - merged["exit_dt_tv"]).dt.total_seconds().abs() / 60.0
    )
    merged = merged.sort_values("abs_pnl_delta_usd", ascending=False).head(limit)

    rows: list[OutlierRow] = []
    for row in merged.itertuples(index=False):
        rows.append(
            OutlierRow(
                entry_dt=str(row.entry_key_dt),
                side=row.side,
                year=int(row.entry_key_dt.year),
                tv_trade_no=int(row.trade_no_tv),
                sim_trade_no=int(row.trade_no_sim),
                pnl_delta_usd=round(float(row.pnl_delta_usd), 2),
                abs_pnl_delta_usd=round(float(row.abs_pnl_delta_usd), 2),
                tv_pnl_usd=round(float(row.pnl_usd_tv), 2),
                sim_pnl_usd=round(float(row.pnl_usd_sim), 2),
                same_win_loss=bool((row.pnl_usd_sim > 0) == (row.pnl_usd_tv > 0)),
                tv_qty=int(row.qty_tv),
                sim_qty=int(row.qty_sim),
                tv_exit_dt=str(row.exit_dt_tv),
                sim_exit_dt=str(row.exit_dt_sim),
                exit_delta_minutes=round(float(row.exit_delta_minutes), 4),
                tv_exit_signal=row.exit_signal_tv,
                sim_exit_signal=row.exit_signal_sim,
                sim_risk_points=round(float(row.risk_points), 4),
                sim_rr=round(float(row.rr), 4),
                sim_body_pct=round(float(row.body_pct), 4),
                sim_rejection_wick_pct=round(float(row.rejection_wick_pct), 4),
                sim_extension_pct=round(float(row.extension_pct), 4),
            )
        )
    return rows


def build_filter_damage_rows(
    sim: pd.DataFrame,
    tv: pd.DataFrame,
    bars: pd.DataFrame,
    levels: dict[Any, tuple[float, float]],
) -> list[FilterDamageRow]:
    tv_keys = set(zip(tv["entry_key_dt"], tv["side"]))
    sim_keys = set(zip(sim["entry_key_dt"], sim["side"]))
    matched = sim_keys & tv_keys
    extra = sim_keys - tv_keys

    feature_rows = []
    for row in sim.itertuples(index=False):
        key = (row.entry_key_dt, row.side)
        features = feature_snapshot(row.entry_key_dt, row.side, bars, levels)
        feature_rows.append({"matched": key in matched, "extra": key in extra, **features})
    features_df = pd.DataFrame(feature_rows)

    tests = [
        (
            "require_smt_divergence_true",
            "Keep only trades where NQ makes a 15-bar extreme and ES does not.",
            features_df["smt_divergence_15"] == True,  # noqa: E712
            "Too blunt if used literally; removes many true positives.",
        ),
        (
            "require_es_confirm_true",
            "Keep only trades where both NQ and ES make the same 15-bar extreme.",
            features_df["es_confirm_same_extreme_15"] == True,  # noqa: E712
            "Too blunt if used literally; useful only as a clue for exact SMT logic.",
        ),
        (
            "reject_extension_gt35",
            "Reject trades where breakout extension exceeds 35% of the ORB range proxy.",
            features_df["overextension_gt_35"] == False,  # noqa: E712
            "Explains a few extras but damages many matched trades with this proxy.",
        ),
        (
            "require_volume_2x",
            "Keep only trades with 5m volume >= 2x 20-bar SMA.",
            features_df["volume_2x_pass"] == True,  # noqa: E712
            "The visible volume setting is not this simple, or is not applied this way.",
        ),
        (
            "require_rg_pass",
            "Keep only trades that pass the approximate RG filter.",
            features_df["rg_pass"] == True,  # noqa: E712
            "Mildly helpful but still removes too many matched trades.",
        ),
    ]

    rows: list[FilterDamageRow] = []
    for name, rule, keep_mask, note in tests:
        removed = features_df[~keep_mask]
        kept = features_df[keep_mask]
        rows.append(
            FilterDamageRow(
                test_name=name,
                rule=rule,
                removed_total=int(len(removed)),
                removed_matched=int(removed["matched"].sum()),
                removed_extra=int(removed["extra"].sum()),
                kept_matched=int(kept["matched"].sum()),
                kept_extra=int(kept["extra"].sum()),
                note=note,
            )
        )
    return rows


def metric_block(df: pd.DataFrame) -> dict[str, Any]:
    pnl = df["pnl_usd"] if not df.empty else pd.Series(dtype=float)
    gross_profit = pnl[pnl > 0].sum()
    gross_loss = -pnl[pnl < 0].sum()
    return {
        "trades": int(len(df)),
        "wins": int((pnl > 0).sum()),
        "win_rate": round(float((pnl > 0).mean()), 6) if len(df) else None,
        "net_pnl_usd": round(float(pnl.sum()), 2),
        "profit_factor": round(float(gross_profit / gross_loss), 6) if gross_loss else None,
    }


def summarize(
    sim: pd.DataFrame,
    tv: pd.DataFrame,
    mismatches: list[MismatchRow],
    outliers: list[OutlierRow],
    filter_damage: list[FilterDamageRow],
) -> dict[str, Any]:
    sim_keys = set(zip(sim["entry_key_dt"], sim["side"]))
    tv_keys = set(zip(tv["entry_key_dt"], tv["side"]))
    matched = sim_keys & tv_keys
    precision = len(matched) / len(sim_keys) if sim_keys else 0.0
    recall = len(matched) / len(tv_keys) if tv_keys else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    merged = sim.merge(tv, on=["entry_key_dt", "side"], suffixes=("_sim", "_tv"))
    same_win_loss = ((merged["pnl_usd_sim"] > 0) == (merged["pnl_usd_tv"] > 0)).mean()
    return {
        "window": {
            "start": str(min(tv["entry_key_dt"].min(), sim["entry_key_dt"].min())),
            "end": str(max(tv["entry_key_dt"].max(), sim["entry_key_dt"].max())),
        },
        "entry_accuracy": {
            "tv_trades": int(len(tv)),
            "sim_trades": int(len(sim)),
            "matched": int(len(matched)),
            "missing_tv": int(len(tv_keys - sim_keys)),
            "extra_sim": int(len(sim_keys - tv_keys)),
            "precision": round(precision, 6),
            "recall": round(recall, 6),
            "f1": round(f1, 6),
            "jaccard": round(len(matched) / len(sim_keys | tv_keys), 6),
        },
        "metric_accuracy": {
            "tv": metric_block(tv),
            "sim": metric_block(sim),
            "matched_same_win_loss_rate": round(float(same_win_loss), 6),
            "matched_median_abs_pnl_error_usd": round(float((merged["pnl_usd_sim"] - merged["pnl_usd_tv"]).abs().median()), 2),
            "matched_mean_abs_pnl_error_usd": round(float((merged["pnl_usd_sim"] - merged["pnl_usd_tv"]).abs().mean()), 2),
        },
        "mismatch_reason_counts": dict(Counter(row.reason for row in mismatches)),
        "extra_reason_counts": dict(Counter(row.reason for row in mismatches if row.kind == "extra_sim_trade")),
        "missing_reason_counts": dict(Counter(row.reason for row in mismatches if row.kind == "missing_tv_trade")),
        "outlier_count": len(outliers),
        "filter_damage_checks": [asdict(row) for row in filter_damage],
    }


def write_dataclass_csv(path: Path, rows: list[Any]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        for row in rows:
            writer.writerow(asdict(row))


def write_report(
    path: Path,
    summary: dict[str, Any],
    mismatches: list[MismatchRow],
    outliers: list[OutlierRow],
    filter_damage: list[FilterDamageRow],
) -> None:
    entry = summary["entry_accuracy"]
    tv = summary["metric_accuracy"]["tv"]
    sim = summary["metric_accuracy"]["sim"]
    lines = [
        "# Hunter/Classic ORB Parity Report",
        "",
        f"Window: {summary['window']['start']} to {summary['window']['end']}",
        "",
        "## Accuracy Snapshot",
        "",
        f"- Entry recall: {entry['recall'] * 100:.2f}% ({entry['matched']}/{entry['tv_trades']} TradingView trades matched)",
        f"- Entry precision: {entry['precision'] * 100:.2f}% ({entry['matched']}/{entry['sim_trades']} simulated trades matched)",
        f"- Entry F1: {entry['f1'] * 100:.2f}%",
        f"- Same win/loss on matched trades: {summary['metric_accuracy']['matched_same_win_loss_rate'] * 100:.2f}%",
        f"- Median matched-trade absolute P&L error: ${summary['metric_accuracy']['matched_median_abs_pnl_error_usd']:,.2f}",
        f"- TV net/PF: ${tv['net_pnl_usd']:,.2f} / {tv['profit_factor']}",
        f"- Sim net/PF: ${sim['net_pnl_usd']:,.2f} / {sim['profit_factor']}",
        "",
        "## Mismatch Reason Counts",
        "",
    ]
    for reason, count in summary["mismatch_reason_counts"].items():
        lines.append(f"- {reason}: {count}")

    lines.extend(
        [
            "",
            "## Highest-Value Next Tests",
            "",
            "1. Trade management/re-entry state: several extras occur where TradingView appears to be blocking a local candidate because a prior TV trade state differs.",
            "2. Exact SMT divergence: several extras lack the simple 15-bar ES extreme condition, but naive SMT proxies remove too many true positives.",
            "3. Exact EMA/body timing: several missing TV trades are valid local candidates but our current state machine skips them, and two fail the EMA15 approximation.",
            "4. Fill/exit mechanics: the matched trades have nearly identical win/loss outcomes, so most remaining P&L drift likely comes from target/stop placement, rounding, and bar-magnifier path.",
            "",
            "## Naive Filter Damage Checks",
            "",
            "| Test | Removed Matched | Removed Extras | Kept Matched | Kept Extras | Note |",
            "|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in filter_damage:
        lines.append(
            f"| {row.test_name} | {row.removed_matched} | {row.removed_extra} | "
            f"{row.kept_matched} | {row.kept_extra} | {row.note} |"
        )

    lines.extend(
        [
            "",
            "## Top P&L Outliers",
            "",
            "| Entry | Side | TV P&L | Sim P&L | Delta | TV Exit | Sim Exit | Same W/L |",
            "|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for row in outliers[:15]:
        lines.append(
            f"| {row.entry_dt} | {row.side} | ${row.tv_pnl_usd:,.2f} | ${row.sim_pnl_usd:,.2f} | "
            f"${row.pnl_delta_usd:,.2f} | {row.tv_exit_dt} | {row.sim_exit_dt} | {row.same_win_loss} |"
        )

    lines.extend(
        [
            "",
            "## Entry Mismatches",
            "",
            "| Kind | Entry | Side | Reason | TV P&L | Sim P&L | Ext% | EMA15 Pass | SMT Div | ES Confirm |",
            "|---|---|---|---|---:|---:|---:|---|---|---|",
        ]
    )
    for row in mismatches:
        tv_pnl = "" if row.tv_pnl_usd is None else f"${row.tv_pnl_usd:,.2f}"
        sim_pnl = "" if row.sim_pnl_usd is None else f"${row.sim_pnl_usd:,.2f}"
        ext = "" if row.extension_pct_of_orb is None else f"{row.extension_pct_of_orb:.2f}"
        lines.append(
            f"| {row.kind} | {row.entry_dt} | {row.side} | {row.reason} | {tv_pnl} | {sim_pnl} | "
            f"{ext} | {row.ema15_bias_pass} | {row.smt_divergence_15} | {row.es_confirm_same_extreme_15} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export-csv", type=Path, required=True)
    parser.add_argument("--sim-csv", type=Path, required=True)
    parser.add_argument("--data-1s", type=Path, default=Path("data/raw/NQ_1s.parquet"))
    parser.add_argument("--es-data-1s", type=Path, default=Path("data/raw/ES_1s.parquet"))
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--outlier-limit", type=int, default=40)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    tv = export_to_frame(args.export_csv)
    sim = parse_sim(args.sim_csv)
    if args.start is None:
        start = min(tv["entry_key_dt"].min(), sim["entry_key_dt"].min()).normalize()
    else:
        start = pd.Timestamp(args.start)
    if args.end is None:
        end = max(tv["entry_key_dt"].max(), sim["entry_key_dt"].max()).normalize() + pd.Timedelta(days=1)
    else:
        end = pd.Timestamp(args.end)

    df_1s = load_1s(args.data_1s, start, end)
    bars = resample_5m(df_1s)
    es_bars = None
    if args.es_data_1s.exists():
        es_bars = resample_5m(load_1s(args.es_data_1s, start, end))
    bars = add_indicator_features(bars, es_bars)
    levels = day_levels(bars)

    mismatches = build_mismatch_rows(sim, tv, bars, levels)
    outliers = build_outliers(sim, tv, args.outlier_limit)
    filter_damage = build_filter_damage_rows(sim, tv, bars, levels)
    summary = summarize(sim, tv, mismatches, outliers, filter_damage)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_dataclass_csv(args.output_dir / "entry_mismatch_autopsy.csv", mismatches)
    write_dataclass_csv(args.output_dir / "matched_pnl_outliers.csv", outliers)
    write_dataclass_csv(args.output_dir / "filter_damage_checks.csv", filter_damage)
    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_report(args.output_dir / "parity_report.md", summary, mismatches, outliers, filter_damage)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
