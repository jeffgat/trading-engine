#!/usr/bin/env python3
"""Broad pre-holdout HTF-LSI discovery for cross-asset research.

This is a staged discovery packet:
1. Structural family sweep across timeframe / HTF TF / direction / entry mode / entry end / HTF pivot width
2. Trade-cap sweep on the best structural families
3. One-at-a-time parameter sweeps around the best base row
4. Small interaction grid from the best values found in the one-at-a-time sweeps
5. Inversion-lag sweep on the top interaction rows

Holdout stays closed throughout.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import DATA_DIR, load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics


DISCOVERY_START = "2016-01-01"
VALIDATION_START = "2023-01-01"
HOLDOUT_START = "2025-04-01"

DEFAULT_SESSION_FLOORS = {
    "ES": {"min_stop_points": 3.0, "min_tp1_points": 3.0},
}

ENTRY_END_VALUES = ("10:30", "11:00", "12:00", "13:00", "14:00", "15:00")
HTF_TF_VALUES = (30, 60, 90)
HTF_N_LEFT_STAGE_A = (3, 5)
DIRECTION_VALUES = ("long", "both", "short")
ENTRY_MODE_VALUES = ("fvg_limit", "close")
TRADE_CAP_VALUES = (1, 2, 3)

PARAM_SWEEP_VALUES = {
    "entry_end": ("10:30", "11:00", "12:00", "13:00", "14:00", "15:00"),
    "atr_length": (10, 14, 20),
    "min_gap_atr_pct": (2.0, 3.0, 4.0, 5.0),
    "rr": (2.0, 2.5, 3.0, 3.5, 4.0),
    "tp1_ratio": (0.4, 0.5, 0.6, 0.7),
    "htf_n_left": (3, 5, 7),
    "left_minutes": (60, 100, 140),
    "right_minutes": (6, 10, 15),
}

LAG_VALUES = (0, 1, 2, 3, 5, 8, 12, 16, 20, 24, 30)


def _data_exists(stem: str) -> bool:
    path = DATA_DIR / stem
    return path.with_suffix(".parquet").exists() or path.with_suffix(".csv").exists()


def ensure_required_data(symbol: str) -> None:
    missing = [stem for stem in (f"{symbol}_5m", f"{symbol}_1m") if not _data_exists(stem)]
    if missing:
        raise FileNotFoundError(
            "Missing required raw files in backtesting/data/raw: "
            + ", ".join(f"{stem}.parquet|csv" for stem in missing)
        )


def timeframe_minutes(timeframe: str) -> int:
    return {"1m": 1, "3m": 3, "5m": 5}[timeframe]


def bars_from_minutes(minutes: int, timeframe: str) -> int:
    return max(1, round(minutes / timeframe_minutes(timeframe)))


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def load_timeframe_data(symbol: str, timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None, pd.DataFrame]:
    filename_5m = f"{symbol}_5m.parquet"
    signal_df_1m = load_1m_for_5m(filename_5m)
    df_1s = load_1s_for_5m(filename_5m)

    if timeframe == "5m":
        df_base = load_5m_data(filename_5m)
        return df_base, signal_df_1m, df_1s, signal_df_1m
    if timeframe == "3m":
        return resample_ohlcv(signal_df_1m, "3min"), signal_df_1m, df_1s, signal_df_1m
    if timeframe == "1m":
        return signal_df_1m, signal_df_1m, df_1s, signal_df_1m
    raise ValueError(f"Unsupported timeframe {timeframe!r}")


def build_session(
    *,
    entry_start: str,
    entry_end: str,
    min_gap_atr_pct: float,
    min_stop_points: float,
    min_tp1_points: float,
) -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        sweep_start="08:30",
        sweep_end="15:00",
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=min_gap_atr_pct,
        min_stop_points=min_stop_points,
        min_tp1_points=min_tp1_points,
    )


def build_config(
    *,
    symbol: str,
    timeframe: str,
    direction_filter: str,
    entry_mode: str,
    entry_start: str = "08:30",
    entry_end: str = "15:00",
    rr: float = 3.0,
    tp1_ratio: float = 0.6,
    min_gap_atr_pct: float = 3.0,
    atr_length: int = 14,
    htf_level_tf_minutes: int = 60,
    htf_n_left: int = 3,
    htf_trade_max_per_session: int = 1,
    lsi_fvg_window_left: int | None = None,
    lsi_fvg_window_right: int | None = None,
    left_minutes: int = 100,
    right_minutes: int = 10,
    max_fvg_to_inversion_bars: int = 0,
    min_stop_points: float = 0.0,
    min_tp1_points: float = 0.0,
    name: str = "",
) -> StrategyConfig:
    instrument = get_instrument(symbol)
    session = build_session(
        entry_start=entry_start,
        entry_end=entry_end,
        min_gap_atr_pct=min_gap_atr_pct,
        min_stop_points=min_stop_points,
        min_tp1_points=min_tp1_points,
    )
    if lsi_fvg_window_left is None:
        lsi_fvg_window_left = bars_from_minutes(left_minutes, timeframe)
    if lsi_fvg_window_right is None:
        lsi_fvg_window_right = bars_from_minutes(right_minutes, timeframe)
    if not name:
        name = (
            f"{symbol} NY HTF_LSI {timeframe} {direction_filter} {entry_mode} "
            f"htf{htf_level_tf_minutes} n{htf_n_left} cap{htf_trade_max_per_session} "
            f"L{lsi_fvg_window_left} R{lsi_fvg_window_right} lag{max_fvg_to_inversion_bars}"
        )
    return StrategyConfig(
        instrument=instrument,
        sessions=(session,),
        strategy="htf_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter=direction_filter,
        rr=rr,
        tp1_ratio=tp1_ratio,
        atr_length=atr_length,
        lsi_fvg_window_left=lsi_fvg_window_left,
        lsi_fvg_window_right=lsi_fvg_window_right,
        lsi_stop_mode="absolute",
        lsi_entry_mode=entry_mode,
        htf_level_tf_minutes=htf_level_tf_minutes,
        htf_n_left=htf_n_left,
        htf_trade_max_per_session=htf_trade_max_per_session,
        max_fvg_to_inversion_bars=max_fvg_to_inversion_bars,
        name=name,
    )


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def summarize_periods(trades) -> dict[str, dict]:
    return {
        "pre_holdout": compute_metrics(slice_trades(trades, DISCOVERY_START, HOLDOUT_START)),
        "discovery": compute_metrics(slice_trades(trades, DISCOVERY_START, VALIDATION_START)),
        "validation": compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START)),
    }


def _neg_years(metrics: dict) -> int:
    return sum(1 for value in metrics.get("r_by_year", {}).values() if value < 0)


def _verdict(summary: dict) -> str:
    discovery = summary["discovery"]
    validation = summary["validation"]
    if (
        discovery["profit_factor"] >= 1.05
        and discovery["avg_r"] > 0.0
        and discovery["total_trades"] >= 150
        and validation["profit_factor"] >= 1.0
        and validation["avg_r"] > 0.0
    ):
        return "alive"
    if validation["profit_factor"] >= 1.0 and validation["avg_r"] > 0.0:
        return "diagnostic_only"
    if summary["pre_holdout"]["profit_factor"] >= 1.0 and summary["pre_holdout"]["avg_r"] > 0.0:
        return "weak"
    return "dead"


def make_row(config: StrategyConfig, trades, *, stage: str, extra: dict | None = None) -> dict:
    summary = summarize_periods(trades)
    pre_holdout = summary["pre_holdout"]
    discovery = summary["discovery"]
    validation = summary["validation"]
    session = config.sessions[0]
    row = {
        "label": config.name,
        "stage": stage,
        "timeframe": extra.get("timeframe") if extra else "",
        "direction_filter": config.direction_filter,
        "entry_mode": config.lsi_entry_mode,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "min_stop_points": session.min_stop_points,
        "min_tp1_points": session.min_tp1_points,
        "atr_length": config.atr_length,
        "htf_level_tf_minutes": config.htf_level_tf_minutes,
        "htf_n_left": config.htf_n_left,
        "htf_trade_max_per_session": config.htf_trade_max_per_session,
        "lsi_fvg_window_left": config.lsi_fvg_window_left,
        "lsi_fvg_window_right": config.lsi_fvg_window_right,
        "max_fvg_to_inversion_bars": config.max_fvg_to_inversion_bars,
        "pre_holdout_trades": int(pre_holdout["total_trades"]),
        "pre_holdout_pf": float(pre_holdout["profit_factor"]),
        "pre_holdout_avg_r": float(pre_holdout["avg_r"]),
        "pre_holdout_calmar": float(pre_holdout["calmar_ratio"]),
        "pre_holdout_max_dd_r": float(pre_holdout["max_drawdown_r"]),
        "pre_holdout_total_r": float(pre_holdout["total_r"]),
        "pre_holdout_neg_years": _neg_years(pre_holdout),
        "discovery_trades": int(discovery["total_trades"]),
        "discovery_pf": float(discovery["profit_factor"]),
        "discovery_avg_r": float(discovery["avg_r"]),
        "discovery_calmar": float(discovery["calmar_ratio"]),
        "discovery_total_r": float(discovery["total_r"]),
        "validation_trades": int(validation["total_trades"]),
        "validation_pf": float(validation["profit_factor"]),
        "validation_avg_r": float(validation["avg_r"]),
        "validation_calmar": float(validation["calmar_ratio"]),
        "validation_total_r": float(validation["total_r"]),
        "validation_max_dd_r": float(validation["max_drawdown_r"]),
        "validation_neg_years": _neg_years(validation),
        "verdict": _verdict(summary),
    }
    if extra:
        row.update(extra)
    return row


def row_sort_key(row: dict):
    verdict_rank = {"alive": 3, "diagnostic_only": 2, "weak": 1, "dead": 0}
    return (
        verdict_rank[row["verdict"]],
        row["validation_calmar"],
        row["validation_pf"],
        row["discovery_pf"],
        row["discovery_avg_r"],
        -row["validation_max_dd_r"],
    )


def sort_rows(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=row_sort_key, reverse=True)


def standard_survivors(rows: list[dict]) -> list[dict]:
    return [
        row for row in rows
        if row["discovery_pf"] >= 1.05
        and row["discovery_avg_r"] > 0.0
        and row["discovery_trades"] >= 150
        and row["validation_pf"] >= 1.0
    ]


def fallback_families(rows: list[dict], limit: int) -> list[dict]:
    soft = [
        row for row in rows
        if row["validation_pf"] >= 1.0
        and row["pre_holdout_trades"] >= 150
    ]
    return (soft or rows)[:limit]


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def write_markdown_report(path: Path, title: str, sections: list[tuple[str, list[dict]]], notes: list[str]) -> None:
    lines = [f"# {title}", ""]
    if notes:
        for note in notes:
            lines.append(f"- {note}")
        lines.append("")
    for section_title, rows in sections:
        lines.append(f"## {section_title}")
        lines.append("")
        if not rows:
            lines.append("No rows.")
            lines.append("")
            continue
        lines.append("| Label | Verdict | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in rows:
            lines.append(
                f"| {row['label']} | {row['verdict']} | "
                f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
                f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} | {row['validation_trades']} | "
                f"{row['pre_holdout_pf']:.3f} | {row['pre_holdout_calmar']:.3f} |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default="ES")
    parser.add_argument("--timeframes", default="3m,5m")
    parser.add_argument("--n-workers", type=int, default=None)
    parser.add_argument("--min-stop-points", type=float, default=None)
    parser.add_argument("--min-tp1-points", type=float, default=None)
    return parser.parse_args()


def stage_a_search_space(symbol: str, timeframe: str) -> tuple[tuple[int, ...], tuple[int, ...], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    if symbol == "CL" and timeframe == "1m":
        # CL only showed life on the 1m honest anchor, and the full generic
        # stage-A packet is disproportionately expensive on 10y of 1m bars.
        # Keep direction breadth, but narrow the HTF / cutoff grid around the
        # realistic NY branch so discovery stays tractable.
        return (
            (30, 60, 90),
            HTF_N_LEFT_STAGE_A,
            DIRECTION_VALUES,
            ENTRY_MODE_VALUES,
            ("13:00", "14:00", "15:00"),
        )
    return (
        HTF_TF_VALUES,
        HTF_N_LEFT_STAGE_A,
        DIRECTION_VALUES,
        ENTRY_MODE_VALUES,
        ENTRY_END_VALUES,
    )


def build_stage_a_configs(symbol: str, timeframes: tuple[str, ...], min_stop_points: float, min_tp1_points: float) -> dict[str, list[StrategyConfig]]:
    out: dict[str, list[StrategyConfig]] = {}
    for timeframe in timeframes:
        configs = []
        htf_tfs, htf_n_lefts, directions, entry_modes, entry_ends = stage_a_search_space(symbol, timeframe)
        for htf_tf, htf_n_left, direction, entry_mode, entry_end in product(
            htf_tfs,
            htf_n_lefts,
            directions,
            entry_modes,
            entry_ends,
        ):
            cfg = build_config(
                symbol=symbol,
                timeframe=timeframe,
                direction_filter=direction,
                entry_mode=entry_mode,
                entry_end=entry_end,
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=htf_tf,
                htf_n_left=htf_n_left,
                htf_trade_max_per_session=1,
                left_minutes=100,
                right_minutes=10,
                max_fvg_to_inversion_bars=0,
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=(
                    f"{symbol} NY HTF_LSI stageA {timeframe} htf{htf_tf} n{htf_n_left} "
                    f"{direction} {entry_mode} 08:30-{entry_end}"
                ),
            )
            configs.append(cfg)
        out[timeframe] = configs
    return out


def main() -> int:
    args = parse_args()
    symbol = args.instrument.upper()
    requested_timeframes = tuple(token.strip() for token in args.timeframes.split(",") if token.strip())
    valid_timeframes = {"1m", "3m", "5m"}
    if not requested_timeframes or any(tf not in valid_timeframes for tf in requested_timeframes):
        print(f"--timeframes must be a non-empty subset of {sorted(valid_timeframes)}", file=sys.stderr)
        return 1

    try:
        get_instrument(symbol)
        ensure_required_data(symbol)
    except (KeyError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    session_defaults = DEFAULT_SESSION_FLOORS.get(symbol, {})
    min_stop_points = args.min_stop_points if args.min_stop_points is not None else session_defaults.get("min_stop_points", 0.0)
    min_tp1_points = args.min_tp1_points if args.min_tp1_points is not None else session_defaults.get("min_tp1_points", 0.0)

    notes = [
        f"Instrument: `{symbol}`",
        f"Timeframes explored: `{', '.join(requested_timeframes)}`",
        f"Holdout remains closed from `{HOLDOUT_START}` onward",
        f"Session floors applied: `min_stop_points={min_stop_points}`, `min_tp1_points={min_tp1_points}`",
    ]

    out_dir = ROOT / "data" / "results" / f"{symbol.lower()}_ny_htf_lsi_broad_discovery"
    report_path = ROOT / "learnings" / "reports" / f"{symbol}_NY_HTF_LSI_BROAD_DISCOVERY.md"

    stage_a_config_map = build_stage_a_configs(symbol, requested_timeframes, min_stop_points, min_tp1_points)
    stage_a_rows: list[dict] = []

    for timeframe in requested_timeframes:
        print(f"Running stage A for {symbol} {timeframe} ({len(stage_a_config_map[timeframe])} configs)...", flush=True)
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(symbol, timeframe)
        results = run_sweep(
            df_base,
            stage_a_config_map[timeframe],
            n_workers=args.n_workers,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        for cfg, trades in results:
            stage_a_rows.append(make_row(cfg, trades, stage="stage_a", extra={"timeframe": timeframe}))

    stage_a_rows = sort_rows(stage_a_rows)
    save_json(out_dir / "stage_a_structural.json", stage_a_rows)

    survivors = standard_survivors(stage_a_rows)
    if survivors:
        stage_b_bases = survivors[:4]
        notes.append(f"Stage A produced {len(survivors)} standard survivors; Stage B used the top {len(stage_b_bases)}.")
    else:
        stage_b_bases = fallback_families(stage_a_rows, limit=6)
        notes.append(
            "Stage A produced no standard survivors, so discovery continued on the top fallback families "
            "with positive validation PF or the best-ranked structural rows."
        )

    stage_b_rows: list[dict] = []
    for base_row in stage_b_bases:
        timeframe = base_row["timeframe"]
        print(f"Running stage B trade-cap sweep from {base_row['label']}...", flush=True)
        configs = [
            build_config(
                symbol=symbol,
                timeframe=timeframe,
                direction_filter=base_row["direction_filter"],
                entry_mode=base_row["entry_mode"],
                entry_start=base_row["entry_start"],
                entry_end=base_row["entry_end"],
                rr=base_row["rr"],
                tp1_ratio=base_row["tp1_ratio"],
                min_gap_atr_pct=base_row["min_gap_atr_pct"],
                atr_length=base_row["atr_length"],
                htf_level_tf_minutes=base_row["htf_level_tf_minutes"],
                htf_n_left=base_row["htf_n_left"],
                htf_trade_max_per_session=cap,
                lsi_fvg_window_left=base_row["lsi_fvg_window_left"],
                lsi_fvg_window_right=base_row["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=base_row["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI stageB {timeframe} cap{cap} {base_row['label']}",
            )
            for cap in TRADE_CAP_VALUES
        ]
        df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(symbol, timeframe)
        results = run_sweep(
            df_base,
            configs,
            n_workers=args.n_workers,
            start_date=DISCOVERY_START,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        for cfg, trades in results:
            stage_b_rows.append(make_row(cfg, trades, stage="stage_b", extra={"timeframe": timeframe, "base_label": base_row["label"]}))

    stage_b_rows = sort_rows(stage_b_rows)
    save_json(out_dir / "stage_b_trade_cap.json", stage_b_rows)
    best_base = stage_b_rows[0]
    notes.append(f"Stage B lead: `{best_base['label']}`.")

    best_timeframe = best_base["timeframe"]
    oat_configs: list[StrategyConfig] = []
    for value in PARAM_SWEEP_VALUES["entry_end"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=value,
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat entry_end {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["atr_length"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=value,
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat atr {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["min_gap_atr_pct"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=value,
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat gap {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["rr"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=value,
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat rr {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["tp1_ratio"]:
        if best_base["rr"] * value < 1.0:
            continue
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=value,
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat tp1 {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["htf_n_left"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=value,
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                lsi_fvg_window_left=best_base["lsi_fvg_window_left"],
                lsi_fvg_window_right=best_base["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat htf_n {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["left_minutes"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                left_minutes=value,
                right_minutes=best_base["lsi_fvg_window_right"] * timeframe_minutes(best_timeframe),
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat left_minutes {value}",
            )
        )
    for value in PARAM_SWEEP_VALUES["right_minutes"]:
        oat_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=best_base["entry_end"],
                rr=best_base["rr"],
                tp1_ratio=best_base["tp1_ratio"],
                min_gap_atr_pct=best_base["min_gap_atr_pct"],
                atr_length=best_base["atr_length"],
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=best_base["htf_n_left"],
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                left_minutes=best_base["lsi_fvg_window_left"] * timeframe_minutes(best_timeframe),
                right_minutes=value,
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI oat right_minutes {value}",
            )
        )

    print(f"Running stage C one-at-a-time packet ({len(oat_configs)} configs)...", flush=True)
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data(symbol, best_timeframe)
    oat_results = run_sweep(
        df_base,
        oat_configs,
        n_workers=args.n_workers,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    oat_rows = []
    for cfg, trades in oat_results:
        sweep_dim = cfg.name.split()[4]
        oat_rows.append(make_row(cfg, trades, stage="stage_c_oat", extra={"timeframe": best_timeframe, "sweep_dimension": sweep_dim}))
    oat_rows = sort_rows(oat_rows)
    save_json(out_dir / "stage_c_oat.json", oat_rows)

    top_values: dict[str, list] = {}
    for dimension in PARAM_SWEEP_VALUES:
        dim_rows = [row for row in oat_rows if row["sweep_dimension"] == dimension]
        values = []
        for row in dim_rows:
            if dimension == "entry_end":
                val = row["entry_end"]
            elif dimension == "atr_length":
                val = row["atr_length"]
            elif dimension == "min_gap_atr_pct":
                val = row["min_gap_atr_pct"]
            elif dimension == "rr":
                val = row["rr"]
            elif dimension == "tp1_ratio":
                val = row["tp1_ratio"]
            elif dimension == "htf_n_left":
                val = row["htf_n_left"]
            elif dimension == "left_minutes":
                val = row["lsi_fvg_window_left"] * timeframe_minutes(best_timeframe)
            elif dimension == "right_minutes":
                val = row["lsi_fvg_window_right"] * timeframe_minutes(best_timeframe)
            else:
                continue
            if val not in values:
                values.append(val)
            if len(values) == 2:
                break
        if len(values) == 1:
            values.append(values[0])
        top_values[dimension] = values or list(PARAM_SWEEP_VALUES[dimension])[:2]

    stage_d_configs = []
    for entry_end, atr_length, gap, rr, tp1, htf_n_left, left_minutes, right_minutes in product(
        top_values["entry_end"],
        top_values["atr_length"],
        top_values["min_gap_atr_pct"],
        top_values["rr"],
        top_values["tp1_ratio"],
        top_values["htf_n_left"],
        top_values["left_minutes"],
        top_values["right_minutes"],
    ):
        if rr * tp1 < 1.0:
            continue
        stage_d_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=best_base["direction_filter"],
                entry_mode=best_base["entry_mode"],
                entry_start=best_base["entry_start"],
                entry_end=entry_end,
                rr=rr,
                tp1_ratio=tp1,
                min_gap_atr_pct=gap,
                atr_length=atr_length,
                htf_level_tf_minutes=best_base["htf_level_tf_minutes"],
                htf_n_left=htf_n_left,
                htf_trade_max_per_session=best_base["htf_trade_max_per_session"],
                left_minutes=left_minutes,
                right_minutes=right_minutes,
                max_fvg_to_inversion_bars=best_base["max_fvg_to_inversion_bars"],
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=(
                    f"{symbol} NY HTF_LSI stageD {best_timeframe} "
                    f"end{entry_end} atr{atr_length} gap{gap} rr{rr} tp{tp1} "
                    f"n{htf_n_left} L{left_minutes} R{right_minutes}"
                ),
            )
        )

    print(f"Running stage D interaction grid ({len(stage_d_configs)} configs)...", flush=True)
    stage_d_results = run_sweep(
        df_base,
        stage_d_configs,
        n_workers=args.n_workers,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    stage_d_rows = sort_rows([make_row(cfg, trades, stage="stage_d_grid", extra={"timeframe": best_timeframe}) for cfg, trades in stage_d_results])
    save_json(out_dir / "stage_d_grid.json", stage_d_rows)

    lag_base_rows = stage_d_rows[:8]
    stage_e_configs = []
    for base_row, lag in product(lag_base_rows, LAG_VALUES):
        stage_e_configs.append(
            build_config(
                symbol=symbol,
                timeframe=best_timeframe,
                direction_filter=base_row["direction_filter"],
                entry_mode=base_row["entry_mode"],
                entry_start=base_row["entry_start"],
                entry_end=base_row["entry_end"],
                rr=base_row["rr"],
                tp1_ratio=base_row["tp1_ratio"],
                min_gap_atr_pct=base_row["min_gap_atr_pct"],
                atr_length=base_row["atr_length"],
                htf_level_tf_minutes=base_row["htf_level_tf_minutes"],
                htf_n_left=base_row["htf_n_left"],
                htf_trade_max_per_session=base_row["htf_trade_max_per_session"],
                lsi_fvg_window_left=base_row["lsi_fvg_window_left"],
                lsi_fvg_window_right=base_row["lsi_fvg_window_right"],
                max_fvg_to_inversion_bars=lag,
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
                name=f"{symbol} NY HTF_LSI stageE lag{lag} {base_row['label']}",
            )
        )

    print(f"Running stage E lag sweep ({len(stage_e_configs)} configs)...", flush=True)
    stage_e_results = run_sweep(
        df_base,
        stage_e_configs,
        n_workers=args.n_workers,
        start_date=DISCOVERY_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        signal_df_1m=signal_df_1m,
        df_1s=df_1s,
    )
    stage_e_rows = sort_rows([make_row(cfg, trades, stage="stage_e_lag", extra={"timeframe": best_timeframe}) for cfg, trades in stage_e_results])
    save_json(out_dir / "stage_e_lag.json", stage_e_rows)

    summary = {
        "instrument": symbol,
        "date_windows": {
            "discovery_start": DISCOVERY_START,
            "validation_start": VALIDATION_START,
            "holdout_start": HOLDOUT_START,
        },
        "holdout_opened": False,
        "session_floors": {
            "min_stop_points": min_stop_points,
            "min_tp1_points": min_tp1_points,
        },
        "timeframes": requested_timeframes,
        "notes": notes,
        "stage_a_top": stage_a_rows[:15],
        "stage_b_top": stage_b_rows[:15],
        "stage_c_top": oat_rows[:15],
        "stage_d_top": stage_d_rows[:15],
        "stage_e_top": stage_e_rows[:15],
    }
    save_json(out_dir / "summary.json", summary)

    write_markdown_report(
        report_path,
        f"{symbol} NY HTF-LSI Broad Discovery",
        [
            ("Stage A Structural", stage_a_rows[:10]),
            ("Stage B Trade Cap", stage_b_rows[:10]),
            ("Stage C One-at-a-Time", oat_rows[:10]),
            ("Stage D Interaction Grid", stage_d_rows[:10]),
            ("Stage E Inversion Lag", stage_e_rows[:10]),
        ],
        notes,
    )

    print(json.dumps(summary["stage_e_top"][:10], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
