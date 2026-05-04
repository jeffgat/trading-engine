#!/usr/bin/env python3
"""NQ NY LSI/CISD staged discovery sequence.

This runner executes the staged test plan for the LSI trade:

1. Classic swing-sweep LSI: inversion vs CISD vs additive.
2. CISD body-structure parameter sweep.
3. 1m/3m/5m timeframe transfer.
4. Sweep-source expansion: classic swings, hourly HTF, EQH/EQL, sessions.
5. Stop refinement: sweep extreme, gap/candle, ATR%.
6. Validation/holdout scorecard for the survivors.

Targets stay fixed at 2R with 50% off at halfway.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_lsi_cisd_sequence_20260503"
CACHE_DIR = ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_SEQUENCE_20260503.md"

DISCOVERY_START = "2016-01-01"
DISCOVERY_END = "2023-01-01"
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2025-04-01"
HOLDOUT_START = "2025-04-01"

BODY_BAR_VALUES = (2, 3, 4, 5)
BODY_ATR_VALUES = (5.0, 7.5, 10.0, 12.5)
ATR_STOP_VALUES = (5.0, 7.5, 10.0, 12.5, 15.0)

SESSION_LEVELS = (
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
    "new_york_high",
    "new_york_low",
)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


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
    return out.dropna(subset=["open", "high", "low", "close"]).astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        }
    )


def build_1m_from_1s(src: Path, dest: Path) -> pd.DataFrame:
    print(f"Building 1m cache from {src.name}...", flush=True)
    t0 = time.time()
    pf = pq.ParquetFile(src)
    chunks: list[pd.DataFrame] = []
    carry = pd.DataFrame()
    columns = ["datetime", "open", "high", "low", "close", "volume"]

    for row_group in range(pf.num_row_groups):
        table = pf.read_row_group(row_group, columns=columns)
        raw = table.to_pandas()
        if "datetime" in raw.columns:
            idx = pd.DatetimeIndex(pd.to_datetime(raw.pop("datetime")))
        else:
            idx = pd.DatetimeIndex(pd.to_datetime(raw.index))
        raw.index = idx
        raw = raw.sort_index()
        combined = pd.concat([carry, raw]) if len(carry) else raw
        if combined.empty:
            continue
        cutoff = combined.index[-1].floor("1min")
        ready = combined[combined.index < cutoff]
        carry = combined[combined.index >= cutoff]
        if not ready.empty:
            chunks.append(resample_ohlcv(ready, "1min"))
        if (row_group + 1) % 10 == 0:
            print(
                f"  row groups {row_group + 1}/{pf.num_row_groups} "
                f"({time.time() - t0:.0f}s)",
                flush=True,
            )

    if not carry.empty:
        chunks.append(resample_ohlcv(carry, "1min"))

    df_1m = pd.concat(chunks).sort_index()
    df_1m = df_1m[~df_1m.index.duplicated(keep="last")]
    dest.parent.mkdir(parents=True, exist_ok=True)
    df_1m.to_parquet(dest)
    print(f"  wrote {len(df_1m):,} 1m bars to {dest} [{time.time() - t0:.0f}s]", flush=True)
    return df_1m


def load_timeframes() -> dict[str, pd.DataFrame]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path_1m = CACHE_DIR / "NQ_1m.parquet"
    path_3m = CACHE_DIR / "NQ_3m.parquet"
    path_5m = CACHE_DIR / "NQ_5m.parquet"

    if path_1m.exists():
        df_1m = pd.read_parquet(path_1m)
    else:
        df_1m = build_1m_from_1s(ROOT / "data" / "raw" / "NQ_1s.parquet", path_1m)

    for path, rule in ((path_3m, "3min"), (path_5m, "5min")):
        if not path.exists():
            out = resample_ohlcv(df_1m, rule)
            out.to_parquet(path)
            print(f"  wrote {len(out):,} {rule} bars to {path}", flush=True)

    return {
        "1m": df_1m,
        "3m": pd.read_parquet(path_3m),
        "5m": pd.read_parquet(path_5m),
    }


def ny_session(*, min_gap_atr_pct: float = 5.0, stop_atr_pct: float = 10.0) -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="09:30",
        sweep_start="09:30",
        sweep_end="15:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=min_gap_atr_pct,
        stop_atr_pct=stop_atr_pct,
    )


def tf_minutes(timeframe: str) -> int:
    return int(timeframe.removesuffix("m"))


def scaled(value_5m: int, timeframe: str) -> int:
    return max(1, int(round(value_5m * 5 / tf_minutes(timeframe))))


def base_config(
    *,
    label: str,
    timeframe: str = "5m",
    strategy: str = "lsi",
    source: str = "classic_swing",
    confirmation: str = "inversion",
    entry_mode: str = "level_limit",
    stop_mode: str = "absolute",
    cisd_min_leg_bars: int = 2,
    cisd_min_leg_atr_pct: float = 5.0,
    stop_atr_pct: float = 10.0,
    eqhl_tf_minutes: int = 15,
) -> StrategyConfig:
    kwargs: dict[str, Any] = {}
    if strategy == "htf_lsi":
        kwargs.update(
            {
                "htf_level_tf_minutes": 60,
                "htf_n_left": 3,
                "htf_trade_max_per_session": 1,
                "htf_lsi_include_htf_levels": source == "hourly_htf",
                "htf_lsi_include_eqhl_levels": source.startswith("equal_"),
                "eqhl_level_tf_minutes": eqhl_tf_minutes,
                "eqhl_n_left": 2,
                "eqhl_tolerance_ticks": 1,
                "eqhl_min_touches": 2,
                "eqhl_lookback_bars": 48,
                "htf_lsi_reference_levels": SESSION_LEVELS if source == "session_levels" else (),
            }
        )

    return StrategyConfig(
        instrument=NQ,
        sessions=(ny_session(stop_atr_pct=stop_atr_pct),),
        strategy=strategy,
        use_bar_magnifier=timeframe != "1m",
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter="both",
        rr=2.0,
        tp1_ratio=0.5,
        atr_length=10,
        lsi_n_left=scaled(8, timeframe),
        lsi_n_right=scaled(60, timeframe),
        lsi_fvg_window_left=scaled(20, timeframe),
        lsi_fvg_window_right=scaled(5, timeframe),
        lsi_stop_mode=stop_mode,
        lsi_target_mode="risk",
        lsi_entry_mode=entry_mode,
        lsi_confirmation_mode=confirmation,
        cisd_min_leg_bars=cisd_min_leg_bars,
        cisd_min_leg_atr_pct=cisd_min_leg_atr_pct,
        cisd_max_leg_bars=scaled(60, timeframe),
        name=label,
        **kwargs,
    )


def config_from_row(row: dict[str, Any], *, overrides: dict[str, Any] | None = None) -> StrategyConfig:
    overrides = overrides or {}
    return base_config(
        label=str(overrides.get("label", row["label"])),
        timeframe=str(overrides.get("timeframe", row["timeframe"])),
        strategy=str(overrides.get("strategy", row["strategy"])),
        source=str(overrides.get("source", row["source"])),
        confirmation=str(overrides.get("confirmation", row["confirmation"])),
        entry_mode=str(overrides.get("entry_mode", row["entry_mode"])),
        stop_mode=str(overrides.get("stop_mode", row["stop_mode"])),
        cisd_min_leg_bars=int(overrides.get("cisd_min_leg_bars", row["cisd_min_leg_bars"])),
        cisd_min_leg_atr_pct=float(overrides.get("cisd_min_leg_atr_pct", row["cisd_min_leg_atr_pct"])),
        stop_atr_pct=float(overrides.get("stop_atr_pct", row["stop_atr_pct"])),
        eqhl_tf_minutes=int(overrides.get("eqhl_tf_minutes", row.get("eqhl_tf_minutes", 15))),
    )


def metric_subset(trades, start: str, end: str | None) -> dict[str, Any]:
    subset = [
        trade
        for trade in trades
        if trade.exit_type != EXIT_NO_FILL
        and trade.date >= start
        and (end is None or trade.date < end)
    ]
    metrics = compute_metrics(subset)
    return {
        "trades": int(metrics["total_trades"]),
        "win_rate": float(metrics["win_rate"]),
        "total_r": float(metrics["total_r"]),
        "avg_r": float(metrics["avg_r"]),
        "max_dd_r": float(metrics["max_drawdown_r"]),
        "profit_factor": float(metrics["profit_factor"]),
        "sharpe": float(metrics["sharpe_ratio"]),
        "calmar": float(metrics["calmar_ratio"]),
    }


def score(metrics: dict[str, Any]) -> float:
    if metrics["trades"] < 25:
        return -1e9 + metrics["trades"]
    if not math.isfinite(metrics["calmar"]):
        return -1e9
    return float(metrics["calmar"]) + 0.15 * float(metrics["sharpe"]) + 0.5 * float(metrics["avg_r"])


def row_from_result(
    *,
    stage: str,
    label: str,
    timeframe: str,
    source: str,
    strategy: str,
    cfg: StrategyConfig,
    trades,
    elapsed_s: float,
) -> dict[str, Any]:
    discovery = metric_subset(trades, DISCOVERY_START, DISCOVERY_END)
    validation = metric_subset(trades, VALIDATION_START, VALIDATION_END)
    holdout = metric_subset(trades, HOLDOUT_START, None)
    filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    cisd_count = sum(1 for trade in filled if trade.lsi_confirmation_type == "cisd")
    inversion_count = sum(1 for trade in filled if trade.lsi_confirmation_type == "inversion")
    session = cfg.sessions[0]
    return {
        "stage": stage,
        "label": label,
        "timeframe": timeframe,
        "source": source,
        "strategy": strategy,
        "confirmation": cfg.lsi_confirmation_mode,
        "entry_mode": cfg.lsi_entry_mode,
        "stop_mode": cfg.lsi_stop_mode,
        "stop_atr_pct": session.stop_atr_pct,
        "cisd_min_leg_bars": cfg.cisd_min_leg_bars,
        "cisd_min_leg_atr_pct": cfg.cisd_min_leg_atr_pct,
        "eqhl_tf_minutes": cfg.eqhl_level_tf_minutes,
        "lsi_n_left": cfg.lsi_n_left,
        "lsi_n_right": cfg.lsi_n_right,
        "lsi_fvg_window_left": cfg.lsi_fvg_window_left,
        "lsi_fvg_window_right": cfg.lsi_fvg_window_right,
        "total_filled": len(filled),
        "cisd_trades": cisd_count,
        "inversion_trades": inversion_count,
        "elapsed_s": elapsed_s,
        "discovery_score": score(discovery),
        **{f"discovery_{key}": value for key, value in discovery.items()},
        **{f"validation_{key}": value for key, value in validation.items()},
        **{f"holdout_{key}": value for key, value in holdout.items()},
    }


def run_configs(
    *,
    stage: str,
    timeframe: str,
    data: dict[str, pd.DataFrame],
    specs: list[tuple[str, str, str, StrategyConfig]],
) -> list[dict[str, Any]]:
    df = data[timeframe]
    df_1m = data["1m"] if timeframe != "1m" else None
    signal_df_1m = data["1m"]
    maps = build_maps(df, df_1m=df_1m)
    configs = [spec[3] for spec in specs]
    cache = build_signal_cache(df, configs, signal_df_1m=signal_df_1m)
    rows = []

    for idx, (label, source, strategy, cfg) in enumerate(specs, start=1):
        t0 = time.time()
        trades = run_backtest(
            df,
            cfg,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            _maps=maps,
            _signal_cache=cache,
        )
        elapsed = time.time() - t0
        row = row_from_result(
            stage=stage,
            label=label,
            timeframe=timeframe,
            source=source,
            strategy=strategy,
            cfg=cfg,
            trades=trades,
            elapsed_s=elapsed,
        )
        rows.append(row)
        print(
            f"  [{idx:>3}/{len(specs)}] {stage:<16} {label:<55} "
            f"D {row['discovery_trades']:>3}tr PF {row['discovery_profit_factor']:.2f} "
            f"Calm {row['discovery_calmar']:.2f} | "
            f"V {row['validation_trades']:>3}tr PF {row['validation_profit_factor']:.2f} "
            f"Calm {row['validation_calmar']:.2f} [{elapsed:.1f}s]",
            flush=True,
        )
    return rows


def run_stage(
    *,
    stage: str,
    data: dict[str, pd.DataFrame],
    specs: list[tuple[str, str, str, StrategyConfig]],
) -> list[dict[str, Any]]:
    print(f"\n{stage}: {len(specs)} configs", flush=True)
    rows: list[dict[str, Any]] = []
    by_tf: dict[str, list[tuple[str, str, str, StrategyConfig]]] = {}
    for spec in specs:
        timeframe = spec[3].name.split("|")[0]
        by_tf.setdefault(timeframe, []).append(spec)
    for timeframe, tf_specs in sorted(by_tf.items()):
        print(f"\nTimeframe {timeframe}: {len(tf_specs)} configs", flush=True)
        rows.extend(run_configs(stage=stage, timeframe=timeframe, data=data, specs=tf_specs))
    return rows


def top_rows(rows: list[dict[str, Any]], *, n: int, require_cisd: bool = False) -> list[dict[str, Any]]:
    pool = [
        row for row in rows
        if (not require_cisd or row["confirmation"] in {"cisd", "inversion_or_cisd"})
    ]
    return sorted(pool, key=lambda row: row["discovery_score"], reverse=True)[:n]


def build_phase1_specs() -> list[tuple[str, str, str, StrategyConfig]]:
    specs = []
    for confirmation in ("inversion", "cisd", "inversion_or_cisd"):
        for entry_mode in ("close", "level_limit"):
            for stop_mode in ("absolute", "fvg", "atr_pct"):
                label = f"5m|classic|{confirmation}|{entry_mode}|{stop_mode}"
                cfg = base_config(
                    label=label,
                    confirmation=confirmation,
                    entry_mode=entry_mode,
                    stop_mode=stop_mode,
                )
                specs.append((label, "classic_swing", "lsi", cfg))
    return specs


def build_body_sweep_specs(seeds: list[dict[str, Any]]) -> list[tuple[str, str, str, StrategyConfig]]:
    specs = []
    seen = set()
    for seed in seeds:
        for bars in BODY_BAR_VALUES:
            for atr_pct in BODY_ATR_VALUES:
                label = (
                    f"{seed['timeframe']}|body|{seed['confirmation']}|{seed['entry_mode']}|"
                    f"{seed['stop_mode']}|bars{bars}|atr{atr_pct:g}"
                )
                key = (seed["timeframe"], seed["confirmation"], seed["entry_mode"], seed["stop_mode"], bars, atr_pct)
                if key in seen:
                    continue
                seen.add(key)
                cfg = config_from_row(
                    seed,
                    overrides={
                        "label": label,
                        "cisd_min_leg_bars": bars,
                        "cisd_min_leg_atr_pct": atr_pct,
                    },
                )
                specs.append((label, "classic_swing", "lsi", cfg))
    return specs


def build_timeframe_specs(seeds: list[dict[str, Any]]) -> list[tuple[str, str, str, StrategyConfig]]:
    specs = []
    seen = set()
    for seed in seeds:
        for timeframe in ("1m", "3m", "5m"):
            label = (
                f"{timeframe}|tf|{seed['confirmation']}|{seed['entry_mode']}|"
                f"{seed['stop_mode']}|bars{seed['cisd_min_leg_bars']}|atr{seed['cisd_min_leg_atr_pct']:g}"
            )
            key = (
                timeframe,
                seed["confirmation"],
                seed["entry_mode"],
                seed["stop_mode"],
                seed["cisd_min_leg_bars"],
                seed["cisd_min_leg_atr_pct"],
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = config_from_row(seed, overrides={"label": label, "timeframe": timeframe})
            specs.append((label, "classic_swing", "lsi", cfg))
    return specs


def build_source_specs(seeds: list[dict[str, Any]]) -> list[tuple[str, str, str, StrategyConfig]]:
    source_defs = (
        ("classic_swing", "lsi", {}),
        ("hourly_htf", "htf_lsi", {}),
        ("equal_15m", "htf_lsi", {"eqhl_tf_minutes": 15}),
        ("session_levels", "htf_lsi", {}),
    )
    specs = []
    seen = set()
    for seed in seeds:
        for source, strategy, extra in source_defs:
            label = (
                f"{seed['timeframe']}|source|{source}|{seed['confirmation']}|"
                f"{seed['entry_mode']}|{seed['stop_mode']}"
            )
            key = (
                seed["timeframe"],
                source,
                seed["confirmation"],
                seed["entry_mode"],
                seed["stop_mode"],
                seed["cisd_min_leg_bars"],
                seed["cisd_min_leg_atr_pct"],
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = config_from_row(
                seed,
                overrides={"label": label, "source": source, "strategy": strategy, **extra},
            )
            specs.append((label, source, strategy, cfg))
    return specs


def build_stop_specs(seeds: list[dict[str, Any]]) -> list[tuple[str, str, str, StrategyConfig]]:
    specs = []
    seen = set()
    for seed in seeds:
        for stop_mode in ("absolute", "fvg"):
            label = f"{seed['timeframe']}|stop|{seed['source']}|{seed['confirmation']}|{seed['entry_mode']}|{stop_mode}"
            key = (
                seed["timeframe"],
                seed["source"],
                seed["strategy"],
                seed["confirmation"],
                seed["entry_mode"],
                stop_mode,
                seed["cisd_min_leg_bars"],
                seed["cisd_min_leg_atr_pct"],
                seed["eqhl_tf_minutes"],
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = config_from_row(seed, overrides={"label": label, "stop_mode": stop_mode})
            specs.append((label, seed["source"], seed["strategy"], cfg))
        for atr_stop in ATR_STOP_VALUES:
            label = (
                f"{seed['timeframe']}|stop|{seed['source']}|{seed['confirmation']}|"
                f"{seed['entry_mode']}|atr_pct{atr_stop:g}"
            )
            key = (
                seed["timeframe"],
                seed["source"],
                seed["strategy"],
                seed["confirmation"],
                seed["entry_mode"],
                "atr_pct",
                atr_stop,
                seed["cisd_min_leg_bars"],
                seed["cisd_min_leg_atr_pct"],
                seed["eqhl_tf_minutes"],
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = config_from_row(
                seed,
                overrides={"label": label, "stop_mode": "atr_pct", "stop_atr_pct": atr_stop},
            )
            specs.append((label, seed["source"], seed["strategy"], cfg))
    return specs


def write_report(rows: list[dict[str, Any]], stage_counts: dict[str, int]) -> None:
    ranked = sorted(rows, key=lambda row: row["discovery_score"], reverse=True)
    top_validation = sorted(
        [row for row in rows if row["validation_trades"] >= 10],
        key=lambda row: row["validation_calmar"],
        reverse=True,
    )
    lines = [
        "# NQ NY LSI CISD Sequence",
        "",
        f"- Discovery: `{DISCOVERY_START}` to `{DISCOVERY_END}`.",
        f"- Validation: `{VALIDATION_START}` to `{VALIDATION_END}`.",
        f"- Holdout: `{HOLDOUT_START}` onward.",
        "- Targets fixed at `rr=2.0`, `tp1_ratio=0.5`.",
        "- Directions: both long and short.",
        "",
        "## Stage Counts",
        "",
    ]
    for stage, count in stage_counts.items():
        lines.append(f"- `{stage}`: {count} configs")

    lines.extend(
        [
            "",
            "## Top Discovery Rows",
            "",
            "| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for idx, row in enumerate(ranked[:12], start=1):
        lines.append(
            f"| {idx} | `{row['label']}` | {row['discovery_trades']} | "
            f"{row['discovery_profit_factor']:.2f} | {row['discovery_calmar']:.2f} | "
            f"{row['validation_trades']} | {row['validation_profit_factor']:.2f} | {row['validation_calmar']:.2f} | "
            f"{row['holdout_trades']} | {row['holdout_profit_factor']:.2f} | {row['holdout_calmar']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Top Validation Rows",
            "",
            "| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for idx, row in enumerate(top_validation[:12], start=1):
        lines.append(
            f"| {idx} | `{row['label']}` | {row['discovery_trades']} | "
            f"{row['discovery_profit_factor']:.2f} | {row['discovery_calmar']:.2f} | "
            f"{row['validation_trades']} | {row['validation_profit_factor']:.2f} | {row['validation_calmar']:.2f} | "
            f"{row['holdout_trades']} | {row['holdout_profit_factor']:.2f} | {row['holdout_calmar']:.2f} |"
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI/CISD staged sequence", flush=True)
    print("=" * 88, flush=True)

    data = load_timeframes()
    latest = str(pd.Timestamp(data["1m"].index.max()).date())
    print(
        f"Loaded data: 1m={len(data['1m']):,}, 3m={len(data['3m']):,}, "
        f"5m={len(data['5m']):,}; latest={latest}",
        flush=True,
    )

    all_rows: list[dict[str, Any]] = []
    stage_counts: dict[str, int] = {}

    phase1 = run_stage(stage="phase1_classic", data=data, specs=build_phase1_specs())
    all_rows.extend(phase1)
    stage_counts["phase1_classic"] = len(phase1)

    body_specs = build_body_sweep_specs(top_rows(phase1, n=4, require_cisd=True))
    body_rows = run_stage(stage="phase2_body", data=data, specs=body_specs)
    all_rows.extend(body_rows)
    stage_counts["phase2_body"] = len(body_rows)

    tf_specs = build_timeframe_specs(top_rows(body_rows, n=4, require_cisd=True))
    tf_rows = run_stage(stage="phase3_timeframe", data=data, specs=tf_specs)
    all_rows.extend(tf_rows)
    stage_counts["phase3_timeframe"] = len(tf_rows)

    source_specs = build_source_specs(top_rows(tf_rows, n=5, require_cisd=True))
    source_rows = run_stage(stage="phase4_sources", data=data, specs=source_specs)
    all_rows.extend(source_rows)
    stage_counts["phase4_sources"] = len(source_rows)

    stop_specs = build_stop_specs(top_rows(source_rows, n=5, require_cisd=True))
    stop_rows = run_stage(stage="phase5_stops", data=data, specs=stop_specs)
    all_rows.extend(stop_rows)
    stage_counts["phase5_stops"] = len(stop_rows)

    df_rows = pd.DataFrame(all_rows)
    df_rows.to_csv(OUTPUT_DIR / "all_rows.csv", index=False)
    save_json(
        OUTPUT_DIR / "summary.json",
        {
            "generated_at": pd.Timestamp.utcnow().isoformat(),
            "latest_data_date": latest,
            "stage_counts": stage_counts,
            "total_configs": len(all_rows),
            "top_discovery": top_rows(all_rows, n=20),
            "top_validation": sorted(
                [row for row in all_rows if row["validation_trades"] >= 10],
                key=lambda row: row["validation_calmar"],
                reverse=True,
            )[:20],
        },
    )
    write_report(all_rows, stage_counts)

    print("\nTop discovery rows:", flush=True)
    for idx, row in enumerate(top_rows(all_rows, n=10), start=1):
        print(
            f"  {idx:>2}. {row['label']} | "
            f"D {row['discovery_trades']}tr PF {row['discovery_profit_factor']:.2f} "
            f"Calm {row['discovery_calmar']:.2f} | "
            f"V {row['validation_trades']}tr PF {row['validation_profit_factor']:.2f} "
            f"Calm {row['validation_calmar']:.2f} | "
            f"H {row['holdout_trades']}tr PF {row['holdout_profit_factor']:.2f} "
            f"Calm {row['holdout_calmar']:.2f}",
            flush=True,
        )

    print(f"\nOutput: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
