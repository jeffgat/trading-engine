#!/usr/bin/env python3
"""Cross-asset pre-holdout HTF-LSI anchor transfer packet.

Uses the narrow NQ-derived anchor set we currently trust:
- 1m lag0 honest baseline
- 3m lag0 diagnostic transfer
- 5m lag0 control
- 5m lag24 promoted lead

The packet keeps the 2025-04-01+ holdout closed and only scores
discovery/validation on the pre-holdout window so we can compare assets
without prematurely burning the holdout.
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


DISCOVERY_START = "2016-01-01"
VALIDATION_START = "2023-01-01"
HOLDOUT_START = "2025-04-01"

DEFAULT_SESSION_FLOORS = {
    "ES": {"min_stop_points": 3.0, "min_tp1_points": 3.0},
}

ANCHORS = (
    {
        "id": "1m_lag0_honest",
        "timeframe": "1m",
        "note": "Honest lower-timeframe baseline from NQ. Kept uncapped because lag10 failed stitched OOS.",
        "direction_filter": "long",
        "entry_mode": "close",
        "entry_start": "08:30",
        "entry_end": "15:00",
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "lsi_fvg_window_left": 100,
        "lsi_fvg_window_right": 10,
        "max_fvg_to_inversion_bars": 0,
    },
    {
        "id": "3m_lag0_diagnostic",
        "timeframe": "3m",
        "note": "Diagnostic 3m transfer from NQ. Validation-strong there, but discovery-negative.",
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "entry_start": "08:30",
        "entry_end": "15:00",
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "lsi_fvg_window_left": 33,
        "lsi_fvg_window_right": 3,
        "max_fvg_to_inversion_bars": 0,
    },
    {
        "id": "5m_lag0_control",
        "timeframe": "5m",
        "note": "5m control row from NQ before the late-lag promotion.",
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "entry_start": "08:30",
        "entry_end": "15:00",
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "lsi_fvg_window_left": 20,
        "lsi_fvg_window_right": 2,
        "max_fvg_to_inversion_bars": 0,
    },
    {
        "id": "5m_lag24_promoted",
        "timeframe": "5m",
        "note": "Promoted 5m lead from NQ. The only lag-cap improvement that survived stitched OOS.",
        "direction_filter": "long",
        "entry_mode": "fvg_limit",
        "entry_start": "08:30",
        "entry_end": "15:00",
        "rr": 3.0,
        "tp1_ratio": 0.6,
        "min_gap_atr_pct": 3.0,
        "atr_length": 14,
        "htf_level_tf_minutes": 60,
        "htf_n_left": 3,
        "htf_trade_max_per_session": 2,
        "lsi_fvg_window_left": 20,
        "lsi_fvg_window_right": 2,
        "max_fvg_to_inversion_bars": 24,
    },
)


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


def build_config(anchor: dict, *, symbol: str, min_stop_points: float, min_tp1_points: float) -> StrategyConfig:
    instrument = get_instrument(symbol)
    session = build_session(
        entry_start=anchor["entry_start"],
        entry_end=anchor["entry_end"],
        min_gap_atr_pct=anchor["min_gap_atr_pct"],
        min_stop_points=min_stop_points,
        min_tp1_points=min_tp1_points,
    )
    return StrategyConfig(
        instrument=instrument,
        sessions=(session,),
        strategy="htf_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter=anchor["direction_filter"],
        rr=anchor["rr"],
        tp1_ratio=anchor["tp1_ratio"],
        atr_length=anchor["atr_length"],
        lsi_fvg_window_left=anchor["lsi_fvg_window_left"],
        lsi_fvg_window_right=anchor["lsi_fvg_window_right"],
        lsi_stop_mode="absolute",
        lsi_entry_mode=anchor["entry_mode"],
        htf_level_tf_minutes=anchor["htf_level_tf_minutes"],
        htf_n_left=anchor["htf_n_left"],
        htf_trade_max_per_session=anchor["htf_trade_max_per_session"],
        max_fvg_to_inversion_bars=anchor["max_fvg_to_inversion_bars"],
        name=f"{symbol} NY HTF_LSI {anchor['id']}",
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


def make_row(anchor: dict, config: StrategyConfig, trades) -> dict:
    summary = summarize_periods(trades)
    pre_holdout = summary["pre_holdout"]
    discovery = summary["discovery"]
    validation = summary["validation"]
    session = config.sessions[0]
    return {
        "label": config.name,
        "anchor_id": anchor["id"],
        "anchor_note": anchor["note"],
        "timeframe": anchor["timeframe"],
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
        "pre_holdout_r_by_year": pre_holdout["r_by_year"],
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
        "validation_r_by_year": validation["r_by_year"],
        "verdict": _verdict(summary),
    }


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def write_markdown_report(path: Path, symbol: str, rows: list[dict], *, min_stop_points: float, min_tp1_points: float) -> None:
    lines = [
        f"# {symbol} NY HTF-LSI Anchor Explore",
        "",
        f"- Instrument: `{symbol}`",
        f"- Packet: NQ-derived HTF-LSI transfer anchors (`1m lag0`, `3m lag0`, `5m lag0`, `5m lag24`)",
        f"- Date windows: discovery `{DISCOVERY_START}` to `{VALIDATION_START}`, validation `{VALIDATION_START}` to `{HOLDOUT_START}`",
        f"- Holdout policy: `2025-04-01+` remains closed in this packet",
        f"- Session floors applied: `min_stop_points={min_stop_points}`, `min_tp1_points={min_tp1_points}`",
        "",
    ]

    for timeframe in ("5m", "3m", "1m"):
        tf_rows = [row for row in rows if row["timeframe"] == timeframe]
        if not tf_rows:
            continue
        lines.extend(
            [
                f"## {timeframe}",
                "",
                "| Label | Verdict | Disc PF | Disc Avg R | Disc Trades | Val PF | Val Avg R | Val Calmar | Val Trades | Pre PF | Pre Calmar | Pre Neg Years |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for row in tf_rows:
            lines.append(
                f"| {row['anchor_id']} | {row['verdict']} | "
                f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | {row['discovery_trades']} | "
                f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | {row['validation_calmar']:.3f} | {row['validation_trades']} | "
                f"{row['pre_holdout_pf']:.3f} | {row['pre_holdout_calmar']:.3f} | {row['pre_holdout_neg_years']} |"
            )
        lines.append("")

    lines.append("## Notes")
    lines.append("")
    for row in rows:
        lines.append(f"- `{row['anchor_id']}`: {row['anchor_note']}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--instrument", default="ES", help="Symbol in instruments.py, e.g. ES, RTY, GC, SI, CL")
    parser.add_argument("--n-workers", type=int, default=None, help="Parallel workers for each timeframe sweep")
    parser.add_argument(
        "--timeframes",
        default="1m,3m,5m",
        help="Comma-separated subset of 1m,3m,5m to run",
    )
    parser.add_argument("--min-stop-points", type=float, default=None, help="Override session min_stop_points")
    parser.add_argument("--min-tp1-points", type=float, default=None, help="Override session min_tp1_points")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    symbol = args.instrument.upper()
    requested_timeframes = {token.strip() for token in args.timeframes.split(",") if token.strip()}
    valid_timeframes = {"1m", "3m", "5m"}
    if not requested_timeframes or not requested_timeframes.issubset(valid_timeframes):
        print(f"--timeframes must be a non-empty subset of {sorted(valid_timeframes)}", file=sys.stderr)
        return 1

    try:
        instrument = get_instrument(symbol)
        ensure_required_data(symbol)
    except (KeyError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    session_defaults = DEFAULT_SESSION_FLOORS.get(symbol, {})
    min_stop_points = args.min_stop_points if args.min_stop_points is not None else session_defaults.get("min_stop_points", 0.0)
    min_tp1_points = args.min_tp1_points if args.min_tp1_points is not None else session_defaults.get("min_tp1_points", 0.0)

    rows: list[dict] = []
    for timeframe in ("5m", "3m", "1m"):
        if timeframe not in requested_timeframes:
            continue
        anchors = [anchor for anchor in ANCHORS if anchor["timeframe"] == timeframe]
        configs = [
            build_config(anchor, symbol=symbol, min_stop_points=min_stop_points, min_tp1_points=min_tp1_points)
            for anchor in anchors
        ]
        print(f"Running {symbol} {timeframe} HTF-LSI anchors ({len(configs)} configs)...", flush=True)
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
        anchor_map = {cfg.name: anchor for cfg, anchor in zip(configs, anchors)}
        for config, trades in results:
            rows.append(make_row(anchor_map[config.name], config, trades))

    rows.sort(
        key=lambda row: (
            row["verdict"] == "alive",
            row["validation_calmar"],
            row["validation_pf"],
            row["discovery_pf"],
        ),
        reverse=True,
    )

    slug = f"{symbol.lower()}_ny_htf_lsi_anchor_explore"
    out_dir = ROOT / "data" / "results" / slug
    report_path = ROOT / "learnings" / "reports" / f"{symbol}_NY_HTF_LSI_ANCHOR_EXPLORE.md"

    payload = {
        "instrument": instrument.symbol,
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
        "rows": rows,
    }
    save_json(out_dir / "summary.json", payload)
    write_markdown_report(report_path, symbol, rows, min_stop_points=min_stop_points, min_tp1_points=min_tp1_points)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
