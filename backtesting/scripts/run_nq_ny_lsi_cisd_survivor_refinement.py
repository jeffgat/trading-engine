#!/usr/bin/env python3
"""Targeted survivor refinement for the NQ NY LSI/CISD sequence.

The first sequence is discovery-led. This supplemental runner refines the
validation/holdout survivors so promising 1m/3m candidates are not discarded
only because their discovery score trailed the 5m structural-stop rows.
"""

from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import pandas as pd

import run_nq_ny_lsi_cisd_sequence as seq


OUTPUT_DIR = seq.ROOT / "data" / "results" / "nq_ny_lsi_cisd_sequence_20260503"
ROWS_PATH = OUTPUT_DIR / "survivor_rows.csv"
SUMMARY_PATH = OUTPUT_DIR / "survivor_summary.json"
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_SURVIVOR_REFINEMENT_20260503.md"


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [row._asdict() for row in df.itertuples(index=False)]


def _seed(
    df: pd.DataFrame,
    *,
    confirmation: str,
    timeframe: str,
    source: str | None = None,
    strategy: str | None = None,
    entry_mode: str,
    stop_mode: str,
    bars: int,
    atr_pct: float,
    min_validation_trades: int = 0,
) -> dict[str, Any]:
    pool = df[
        (df["confirmation"] == confirmation)
        & (df["timeframe"] == timeframe)
        & (df["entry_mode"] == entry_mode)
        & (df["stop_mode"] == stop_mode)
        & (df["cisd_min_leg_bars"] == bars)
        & (df["cisd_min_leg_atr_pct"] == atr_pct)
        & (df["validation_trades"] >= min_validation_trades)
    ].copy()
    if source is not None:
        pool = pool[pool["source"] == source]
    if strategy is not None:
        pool = pool[pool["strategy"] == strategy]
    if pool.empty:
        raise ValueError(
            "No seed found for "
            f"{timeframe} {confirmation} {entry_mode} {stop_mode} bars={bars} atr={atr_pct}"
        )
    pool = pool.sort_values(
        ["validation_calmar", "holdout_calmar", "discovery_score"],
        ascending=False,
    )
    return pool.iloc[0].to_dict()


def _stop_label(stop_mode: str, stop_atr_pct: float) -> str:
    return f"atr_pct{stop_atr_pct:g}" if stop_mode == "atr_pct" else stop_mode


def _robust_score(row: dict[str, Any]) -> float:
    if row["validation_trades"] < 30 or row["holdout_trades"] < 20:
        return -1e9 + row["validation_trades"] + row["holdout_trades"]
    if row["validation_profit_factor"] <= 1.0 or row["holdout_profit_factor"] <= 1.0:
        return -1e6 + row["validation_calmar"] + row["holdout_calmar"]
    return (
        min(row["validation_calmar"], row["holdout_calmar"])
        + 0.25 * min(row["validation_profit_factor"], row["holdout_profit_factor"])
        + 0.05 * math.log1p(row["validation_trades"] + row["holdout_trades"])
    )


def _top_robust(rows: list[dict[str, Any]], n: int = 12) -> list[dict[str, Any]]:
    return sorted(rows, key=_robust_score, reverse=True)[:n]


def build_stop_refinement_specs(prior: pd.DataFrame) -> list[tuple[str, str, str, seq.StrategyConfig]]:
    specs: list[tuple[str, str, str, seq.StrategyConfig]] = []
    seen = set()

    pure_seeds = [
        _seed(
            prior,
            confirmation="cisd",
            timeframe="5m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="fvg",
            bars=2,
            atr_pct=5.0,
            min_validation_trades=20,
        ),
        _seed(
            prior,
            confirmation="cisd",
            timeframe="5m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="fvg",
            bars=2,
            atr_pct=7.5,
            min_validation_trades=20,
        ),
    ]

    additive_seeds = [
        _seed(
            prior,
            confirmation="inversion_or_cisd",
            timeframe="1m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="absolute",
            bars=2,
            atr_pct=5.0,
            min_validation_trades=50,
        ),
        _seed(
            prior,
            confirmation="inversion_or_cisd",
            timeframe="1m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="absolute",
            bars=3,
            atr_pct=7.5,
            min_validation_trades=50,
        ),
        _seed(
            prior,
            confirmation="inversion_or_cisd",
            timeframe="3m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="absolute",
            bars=3,
            atr_pct=7.5,
            min_validation_trades=50,
        ),
        _seed(
            prior,
            confirmation="inversion_or_cisd",
            timeframe="3m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="absolute",
            bars=4,
            atr_pct=10.0,
            min_validation_trades=50,
        ),
        _seed(
            prior,
            confirmation="inversion_or_cisd",
            timeframe="3m",
            source="classic_swing",
            strategy="lsi",
            entry_mode="level_limit",
            stop_mode="absolute",
            bars=4,
            atr_pct=12.5,
            min_validation_trades=50,
        ),
    ]

    stop_defs = [("absolute", 10.0), ("fvg", 10.0)] + [
        ("atr_pct", stop_atr_pct) for stop_atr_pct in seq.ATR_STOP_VALUES
    ]

    for seed in pure_seeds:
        for timeframe in ("1m", "3m", "5m"):
            for stop_mode, stop_atr_pct in stop_defs:
                label = (
                    f"{timeframe}|survivor_stop|pure_cisd|classic_swing|level_limit|"
                    f"{_stop_label(stop_mode, stop_atr_pct)}|bars{int(seed['cisd_min_leg_bars'])}|"
                    f"atr{float(seed['cisd_min_leg_atr_pct']):g}"
                )
                key = (
                    "pure",
                    timeframe,
                    stop_mode,
                    stop_atr_pct,
                    int(seed["cisd_min_leg_bars"]),
                    float(seed["cisd_min_leg_atr_pct"]),
                )
                if key in seen:
                    continue
                seen.add(key)
                cfg = seq.config_from_row(
                    seed,
                    overrides={
                        "label": label,
                        "timeframe": timeframe,
                        "confirmation": "cisd",
                        "entry_mode": "level_limit",
                        "stop_mode": stop_mode,
                        "stop_atr_pct": stop_atr_pct,
                    },
                )
                specs.append((label, "classic_swing", "lsi", cfg))

    for seed in additive_seeds:
        for stop_mode, stop_atr_pct in stop_defs:
            label = (
                f"{seed['timeframe']}|survivor_stop|additive|classic_swing|level_limit|"
                f"{_stop_label(stop_mode, stop_atr_pct)}|bars{int(seed['cisd_min_leg_bars'])}|"
                f"atr{float(seed['cisd_min_leg_atr_pct']):g}"
            )
            key = (
                "additive",
                seed["timeframe"],
                stop_mode,
                stop_atr_pct,
                int(seed["cisd_min_leg_bars"]),
                float(seed["cisd_min_leg_atr_pct"]),
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = seq.config_from_row(
                seed,
                overrides={
                    "label": label,
                    "stop_mode": stop_mode,
                    "stop_atr_pct": stop_atr_pct,
                },
            )
            specs.append((label, "classic_swing", "lsi", cfg))

    return specs


def build_source_refinement_specs(
    stop_rows: list[dict[str, Any]],
) -> list[tuple[str, str, str, seq.StrategyConfig]]:
    source_defs = (
        ("classic_swing", "lsi", {}),
        ("hourly_htf", "htf_lsi", {}),
        ("equal_15m", "htf_lsi", {"eqhl_tf_minutes": 15}),
        ("session_levels", "htf_lsi", {}),
    )
    seeds = _top_robust(stop_rows, n=4)
    specs: list[tuple[str, str, str, seq.StrategyConfig]] = []
    seen = set()

    for seed in seeds:
        for source, strategy, extra in source_defs:
            label = (
                f"{seed['timeframe']}|survivor_source|{source}|{seed['confirmation']}|"
                f"{seed['entry_mode']}|{_stop_label(seed['stop_mode'], float(seed['stop_atr_pct']))}|"
                f"bars{int(seed['cisd_min_leg_bars'])}|atr{float(seed['cisd_min_leg_atr_pct']):g}"
            )
            key = (
                seed["timeframe"],
                source,
                strategy,
                seed["confirmation"],
                seed["entry_mode"],
                seed["stop_mode"],
                float(seed["stop_atr_pct"]),
                int(seed["cisd_min_leg_bars"]),
                float(seed["cisd_min_leg_atr_pct"]),
            )
            if key in seen:
                continue
            seen.add(key)
            cfg = seq.config_from_row(
                seed,
                overrides={
                    "label": label,
                    "source": source,
                    "strategy": strategy,
                    **extra,
                },
            )
            specs.append((label, source, strategy, cfg))

    return specs


def write_report(rows: list[dict[str, Any]], stage_counts: dict[str, int]) -> None:
    top = _top_robust(rows, n=20)

    def fmt(row: dict[str, Any], rank: int) -> str:
        return (
            f"| {rank} | `{row['label']}` | {row['discovery_trades']} | "
            f"{row['discovery_profit_factor']:.2f} | {row['discovery_calmar']:.2f} | "
            f"{row['validation_trades']} | {row['validation_profit_factor']:.2f} | "
            f"{row['validation_calmar']:.2f} | {row['holdout_trades']} | "
            f"{row['holdout_profit_factor']:.2f} | {row['holdout_calmar']:.2f} | "
            f"{row['cisd_trades']} | {row['inversion_trades']} |"
        )

    lines = [
        "# NQ NY LSI CISD Survivor Refinement",
        "",
        "- Purpose: refine validation/holdout survivors from the staged NQ NY LSI/CISD sequence.",
        f"- Discovery: `{seq.DISCOVERY_START}` to `{seq.DISCOVERY_END}`.",
        f"- Validation: `{seq.VALIDATION_START}` to `{seq.VALIDATION_END}`.",
        f"- Holdout: `{seq.HOLDOUT_START}` onward.",
        "- Targets fixed at `rr=2.0`, `tp1_ratio=0.5`.",
        "",
        "## Stage Counts",
        "",
    ]
    lines.extend(f"- `{stage}`: {count} configs" for stage, count in stage_counts.items())
    lines.extend(
        [
            "",
            "## Top Robust Rows",
            "",
            "| Rank | Label | D Tr | D PF | D Calmar | V Tr | V PF | V Calmar | H Tr | H PF | H Calmar | CISD | Inversion |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(fmt(row, idx) for idx, row in enumerate(top, start=1))
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    prior_path = OUTPUT_DIR / "all_rows.csv"
    prior = pd.read_csv(prior_path)
    data = seq.load_timeframes()
    latest = max(df.index.max() for df in data.values()).date().isoformat()

    print("NQ NY LSI/CISD survivor refinement", flush=True)
    print("=" * 88, flush=True)
    print(f"Loaded prior rows: {len(prior):,}; latest data: {latest}", flush=True)

    stop_specs = build_stop_refinement_specs(prior)
    stop_rows = seq.run_stage(stage="survivor_stop", data=data, specs=stop_specs)

    source_specs = build_source_refinement_specs(stop_rows + _records(prior))
    source_rows = seq.run_stage(stage="survivor_source", data=data, specs=source_specs)

    rows = stop_rows + source_rows
    stage_counts = {
        "survivor_stop": len(stop_rows),
        "survivor_source": len(source_rows),
    }
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(ROWS_PATH, index=False)
    SUMMARY_PATH.write_text(
        json.dumps(
            {
                "generated_at": pd.Timestamp.now("UTC").isoformat(),
                "latest_data_date": latest,
                "stage_counts": stage_counts,
                "total_configs": len(rows),
                "top_robust": _top_robust(rows, n=20),
            },
            indent=2,
            default=str,
        )
    )
    write_report(rows, stage_counts)

    print("\nTop robust survivor rows:", flush=True)
    for idx, row in enumerate(_top_robust(rows, n=10), start=1):
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

    print(f"\nOutput: {ROWS_PATH}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
