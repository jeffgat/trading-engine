#!/usr/bin/env python3
"""Broad discovery sweep for equal-high/low-driven HTF-LSI.

This script keeps the LSI logic fixed and varies the equal-high/low sweep
source broadly enough to tell us where to zoom in next:

- LSI entry timeframe: 1m, 2m, 5m
- Equal-high/low source timeframe: 5m, 15m, 60m
- Matching tolerance: exact through loose (in ticks)
- Minimum touches: 2 or 3
- Direction, entry mode, and entry window

The sweep source is EQHL-only: traditional HTF pivot levels and named
reference levels are disabled so the output isolates the equal-high/low idea.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import DATA_DIR, load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics


RESEARCH_START = "2016-01-01"
VALIDATION_START = "2023-01-01"
HOLDOUT_START = "2025-04-01"

DEFAULT_SESSION_FLOORS = {
    "ES": {"min_stop_points": 3.0, "min_tp1_points": 3.0},
}


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
    return {"1m": 1, "2m": 2, "3m": 3, "5m": 5}[timeframe]


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


def load_timeframe_data(symbol: str, timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    filename_5m = f"{symbol}_5m.parquet"
    signal_df_1m = load_1m_for_5m(filename_5m)
    df_1s = load_1s_for_5m(filename_5m)

    if timeframe == "5m":
        return load_5m_data(filename_5m), signal_df_1m, df_1s
    if timeframe == "3m":
        return resample_ohlcv(signal_df_1m, "3min"), signal_df_1m, df_1s
    if timeframe == "2m":
        return resample_ohlcv(signal_df_1m, "2min"), signal_df_1m, df_1s
    if timeframe == "1m":
        return signal_df_1m, signal_df_1m, df_1s
    raise ValueError(f"Unsupported timeframe {timeframe!r}")


def build_session(
    *,
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
        entry_start="08:30",
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
    eqhl_tf_minutes: int,
    eqhl_tolerance_ticks: int,
    tolerance_label: str | None = None,
    eqhl_min_touches: int,
    direction_filter: str,
    entry_mode: str,
    entry_end: str,
    rr: float,
    tp1_ratio: float,
    min_gap_atr_pct: float,
    atr_length: int,
    eqhl_n_left: int,
    eqhl_lookback_bars: int,
    left_minutes: int,
    right_minutes: int,
    min_stop_points: float,
    min_tp1_points: float,
) -> StrategyConfig:
    instrument = get_instrument(symbol)
    session = build_session(
        entry_end=entry_end,
        min_gap_atr_pct=min_gap_atr_pct,
        min_stop_points=min_stop_points,
        min_tp1_points=min_tp1_points,
    )
    left_bars = bars_from_minutes(left_minutes, timeframe)
    right_bars = bars_from_minutes(right_minutes, timeframe)
    tolerance_name = tolerance_label or f"{eqhl_tolerance_ticks}t"
    name = (
        f"{symbol} NY EQHL_LSI {timeframe} eqhl{eqhl_tf_minutes}m "
        f"tol{tolerance_name} touches{eqhl_min_touches} "
        f"{direction_filter} {entry_mode} end{entry_end} "
        f"L{left_bars} R{right_bars}"
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
        lsi_fvg_window_left=left_bars,
        lsi_fvg_window_right=right_bars,
        lsi_stop_mode="absolute",
        lsi_entry_mode=entry_mode,
        htf_lsi_include_htf_levels=False,
        htf_lsi_include_eqhl_levels=True,
        htf_lsi_reference_levels=(),
        eqhl_level_tf_minutes=eqhl_tf_minutes,
        eqhl_n_left=eqhl_n_left,
        eqhl_tolerance_ticks=eqhl_tolerance_ticks,
        eqhl_min_touches=eqhl_min_touches,
        eqhl_lookback_bars=eqhl_lookback_bars,
        name=name,
    )


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        trade
        for trade in trades
        if (start is None or trade.date >= start) and (end is None or trade.date < end)
    ]


def summarize_periods(trades) -> dict[str, dict]:
    return {
        "pre_holdout": compute_metrics(slice_trades(trades, RESEARCH_START, HOLDOUT_START)),
        "discovery": compute_metrics(slice_trades(trades, RESEARCH_START, VALIDATION_START)),
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
        and discovery["total_trades"] >= 120
        and validation["profit_factor"] >= 1.0
        and validation["avg_r"] > 0.0
    ):
        return "alive"
    if validation["profit_factor"] >= 1.0 and validation["avg_r"] > 0.0:
        return "diagnostic_only"
    if summary["pre_holdout"]["profit_factor"] >= 1.0 and summary["pre_holdout"]["avg_r"] > 0.0:
        return "weak"
    return "dead"


def _verdict_rank(verdict: str) -> int:
    return {
        "alive": 0,
        "diagnostic_only": 1,
        "weak": 2,
        "dead": 3,
    }.get(verdict, 9)


def make_row(config: StrategyConfig, trades, *, timeframe: str) -> dict:
    summary = summarize_periods(trades)
    session = config.sessions[0]
    verdict = _verdict(summary)
    tolerance_points = float(config.eqhl_tolerance_ticks) * float(config.min_tick)
    return {
        "label": config.name,
        "timeframe": timeframe,
        "direction_filter": config.direction_filter,
        "entry_mode": config.lsi_entry_mode,
        "entry_end": session.entry_end,
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "atr_length": config.atr_length,
        "eqhl_level_tf_minutes": config.eqhl_level_tf_minutes,
        "eqhl_n_left": config.eqhl_n_left,
        "eqhl_tolerance_ticks": config.eqhl_tolerance_ticks,
        "eqhl_tolerance_points": tolerance_points,
        "eqhl_min_touches": config.eqhl_min_touches,
        "eqhl_lookback_bars": config.eqhl_lookback_bars,
        "lsi_fvg_window_left": config.lsi_fvg_window_left,
        "lsi_fvg_window_right": config.lsi_fvg_window_right,
        "pre_holdout_trades": int(summary["pre_holdout"]["total_trades"]),
        "pre_holdout_pf": float(summary["pre_holdout"]["profit_factor"]),
        "pre_holdout_avg_r": float(summary["pre_holdout"]["avg_r"]),
        "pre_holdout_total_r": float(summary["pre_holdout"]["total_r"]),
        "pre_holdout_calmar": float(summary["pre_holdout"]["calmar_ratio"]),
        "pre_holdout_neg_years": _neg_years(summary["pre_holdout"]),
        "validation_trades": int(summary["validation"]["total_trades"]),
        "validation_pf": float(summary["validation"]["profit_factor"]),
        "validation_avg_r": float(summary["validation"]["avg_r"]),
        "validation_total_r": float(summary["validation"]["total_r"]),
        "validation_calmar": float(summary["validation"]["calmar_ratio"]),
        "validation_max_dd_r": float(summary["validation"]["max_drawdown_r"]),
        "verdict": verdict,
        "verdict_rank": _verdict_rank(verdict),
    }


def progress(label: str):
    def _inner(done: int, total: int) -> None:
        print(f"[{label}] {done}/{total}")

    return _inner


def _parse_csv_str(raw: str, *, upper: bool = False) -> tuple[str, ...]:
    values = [value.strip() for value in raw.split(",") if value.strip()]
    if upper:
        values = [value.upper() for value in values]
    return tuple(values)


def _parse_csv_int(raw: str) -> tuple[int, ...]:
    return tuple(int(value.strip()) for value in raw.split(",") if value.strip())


def _parse_csv_float(raw: str) -> tuple[float, ...]:
    return tuple(float(value.strip()) for value in raw.split(",") if value.strip())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Broad EQHL-LSI discovery sweep.")
    parser.add_argument("--symbol", default="NQ", help="Instrument symbol, e.g. NQ or ES.")
    parser.add_argument("--workers", type=int, default=None, help="Optional worker override for run_sweep().")
    parser.add_argument("--rr", type=float, default=3.0, help="Fixed RR anchor for the broad pass.")
    parser.add_argument("--tp1-ratio", type=float, default=0.5, help="Fixed TP1 anchor for the broad pass.")
    parser.add_argument("--min-gap-atr-pct", type=float, default=3.0, help="Session min-gap ATR percent.")
    parser.add_argument("--atr-length", type=int, default=14, help="ATR length.")
    parser.add_argument("--eqhl-n-left", type=int, default=2, help="Swing width used to confirm EQHL pivots.")
    parser.add_argument("--eqhl-lookback-bars", type=int, default=48, help="Source bars allowed between matching touches. Use 0 for unlimited.")
    parser.add_argument("--left-minutes", type=int, default=100, help="FVG lookback window in real minutes.")
    parser.add_argument("--right-minutes", type=int, default=10, help="Sweep-to-FVG window in real minutes.")
    parser.add_argument("--timeframes", default="1m,2m,5m", help="Comma-separated base LSI timeframes.")
    parser.add_argument("--eqhl-tfs", default="5,15,60", help="Comma-separated EQHL source timeframes in minutes.")
    parser.add_argument("--tolerance-ticks", default="0,1,2,4", help="Comma-separated EQHL tolerance values in ticks.")
    parser.add_argument(
        "--tolerance-points",
        default="",
        help=(
            "Optional comma-separated EQHL tolerance values in price points. "
            "When provided, overrides --tolerance-ticks."
        ),
    )
    parser.add_argument("--min-touches", default="2,3", help="Comma-separated EQHL minimum-touch counts.")
    parser.add_argument("--directions", default="long,both,short", help="Comma-separated direction filters.")
    parser.add_argument("--entry-modes", default="fvg_limit,close", help="Comma-separated LSI entry modes.")
    parser.add_argument("--entry-ends", default="11:00,13:00,15:00", help="Comma-separated NY entry-end times.")
    parser.add_argument("--suffix", default="", help="Optional suffix appended to the output directory name.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbol = str(args.symbol).upper()
    ensure_required_data(symbol)
    timeframes = _parse_csv_str(str(args.timeframes))
    eqhl_tfs = _parse_csv_int(str(args.eqhl_tfs))
    min_touches = _parse_csv_int(str(args.min_touches))
    directions = _parse_csv_str(str(args.directions))
    entry_modes = _parse_csv_str(str(args.entry_modes))
    entry_ends = _parse_csv_str(str(args.entry_ends))
    instrument = get_instrument(symbol)

    tolerance_specs: list[tuple[int, float, str]] = []
    if str(args.tolerance_points).strip():
        tolerance_points = _parse_csv_float(str(args.tolerance_points))
        for points in tolerance_points:
            ticks = points / float(instrument.min_tick)
            rounded_ticks = int(round(ticks))
            if abs(ticks - rounded_ticks) > 1e-9:
                raise ValueError(
                    f"Tolerance {points!r} points is not an exact multiple of min_tick "
                    f"{instrument.min_tick!r} for {symbol}."
                )
            tolerance_specs.append((rounded_ticks, float(points), f"{points:g}p"))
    else:
        tolerance_ticks = _parse_csv_int(str(args.tolerance_ticks))
        tolerance_specs = [
            (ticks, float(ticks) * float(instrument.min_tick), f"{ticks}t")
            for ticks in tolerance_ticks
        ]

    floor_cfg = DEFAULT_SESSION_FLOORS.get(symbol, {})
    min_stop_points = float(floor_cfg.get("min_stop_points", 0.0))
    min_tp1_points = float(floor_cfg.get("min_tp1_points", 0.0))

    out_slug = f"{symbol.lower()}_ny_eqhl_lsi_broad_discovery"
    if str(args.suffix).strip():
        out_slug = f"{out_slug}_{str(args.suffix).strip()}"
    out_dir = ROOT / "data" / "results" / out_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    for timeframe in timeframes:
        df_base, signal_df_1m, df_1s = load_timeframe_data(symbol, timeframe)
        configs = [
            build_config(
                symbol=symbol,
                timeframe=timeframe,
                eqhl_tf_minutes=eqhl_tf_minutes,
                eqhl_tolerance_ticks=eqhl_tolerance_ticks,
                tolerance_label=tolerance_label,
                eqhl_min_touches=eqhl_min_touches,
                direction_filter=direction_filter,
                entry_mode=entry_mode,
                entry_end=entry_end,
                rr=float(args.rr),
                tp1_ratio=float(args.tp1_ratio),
                min_gap_atr_pct=float(args.min_gap_atr_pct),
                atr_length=int(args.atr_length),
                eqhl_n_left=int(args.eqhl_n_left),
                eqhl_lookback_bars=int(args.eqhl_lookback_bars),
                left_minutes=int(args.left_minutes),
                right_minutes=int(args.right_minutes),
                min_stop_points=min_stop_points,
                min_tp1_points=min_tp1_points,
            )
            for eqhl_tf_minutes in eqhl_tfs
            for eqhl_tolerance_ticks, _eqhl_tolerance_points, tolerance_label in tolerance_specs
            for eqhl_min_touches in min_touches
            for direction_filter in directions
            for entry_mode in entry_modes
            for entry_end in entry_ends
        ]
        print(f"[{timeframe}] running {len(configs)} configs")
        results = run_sweep(
            df_base,
            configs,
            n_workers=args.workers,
            progress_fn=progress(timeframe),
            df_1m=signal_df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
        )
        for config, trades in results:
            rows.append(make_row(config, trades, timeframe=timeframe))

    ranking = pd.DataFrame(rows)
    ranking = ranking.sort_values(
        by=[
            "verdict_rank",
            "validation_avg_r",
            "validation_pf",
            "pre_holdout_avg_r",
            "pre_holdout_total_r",
        ],
        ascending=[True, False, False, False, False],
    ).reset_index(drop=True)

    csv_path = out_dir / "ranking.csv"
    json_path = out_dir / "summary.json"
    md_path = out_dir / "summary.md"

    ranking.to_csv(csv_path, index=False)
    with open(json_path, "w") as f:
        json.dump(ranking.to_dict(orient="records"), f, indent=2)

    top = ranking.head(40)
    md_lines = [
        f"# {symbol} NY EQHL-LSI broad discovery",
        "",
        f"- Configs tested: `{len(ranking)}`",
        f"- Base timeframes: `{', '.join(timeframes)}`",
        f"- EQHL source timeframes: `{', '.join(str(v) for v in eqhl_tfs)}`",
        f"- Tolerance points: `{', '.join(f'{points:g}' for _ticks, points, _label in tolerance_specs)}`",
        f"- Tolerance ticks: `{', '.join(str(ticks) for ticks, _points, _label in tolerance_specs)}`",
        "",
        "## Top 40",
        "",
    ]
    md_lines.extend(
        [
            f"- `{row.label}` | verdict `{row.verdict}` | val PF `{row.validation_pf:.3f}` | "
            f"val avgR `{row.validation_avg_r:.4f}` | pre PF `{row.pre_holdout_pf:.3f}` | "
            f"pre trades `{int(row.pre_holdout_trades)}`"
            for row in top.itertuples(index=False)
        ]
    )
    md_path.write_text("\n".join(md_lines) + "\n")

    print(f"Saved ranking to {csv_path}")
    print(f"Saved summary to {json_path}")
    print(f"Saved markdown to {md_path}")


if __name__ == "__main__":
    main()
