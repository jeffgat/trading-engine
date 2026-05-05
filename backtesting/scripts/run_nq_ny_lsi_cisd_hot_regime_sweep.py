#!/usr/bin/env python3
"""Hot-regime in-sample sweep for NQ NY LSI/CISD legs.

This is intentionally a recent-window research pass, similar in spirit to the
HOT_REGIME work: optimize on the trailing one-year tape to see how much R can
be squeezed out of the current behavior. These rows are research-only until
they survive exact replay or fresh forward/holdout validation.
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

import run_nq_ny_lsi_cisd_candidate_validation as val
import run_nq_ny_lsi_cisd_restricted_finalists as restricted
import run_nq_ny_lsi_cisd_sequence as seq

sys.path.insert(0, str(seq.ROOT / "src"))

from orb_backtest.engine.simulator import EXIT_NO_FILL  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402


RUN_SLUG = "nq_ny_lsi_cisd_hot_regime_sweep_20260504"
OUTPUT_DIR = seq.ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_HOT_REGIME_SWEEP_20260504.md"

STOP_ATR_VALUES = (7.5, 10.0, 12.5, 15.0, 20.0)
CISD_BARS_VALUES = (2, 3, 4)
CISD_ATR_VALUES = (5.0, 7.5, 10.0)
ENTRY_END_VALUES = ("12:00", "13:00", "14:00", "15:30")

RR_VALUES = (1.5, 2.0, 2.5, 3.0, 4.0, 5.0)
TP1_VALUES = (0.3, 0.4, 0.5, 0.6, 0.8)
TOP_STRUCTURES_PER_FAMILY = 12
N_WORKERS = 8


@dataclasses.dataclass(frozen=True)
class FamilySpec:
    key: str
    label: str
    base_spec: val.CandidateSpec
    direction_filter: str
    no_thursday: bool
    base_entry_end: str
    base_rr: float
    base_tp1_ratio: float


@dataclasses.dataclass(frozen=True)
class VariantSpec:
    key: str
    family_key: str
    stage: str
    stop_atr_pct: float
    cisd_min_leg_bars: int
    cisd_min_leg_atr_pct: float
    entry_end: str
    rr: float
    tp1_ratio: float
    config: seq.StrategyConfig


def fmt(value: float | int | str) -> str:
    return str(value).replace(".", "p").replace(":", "")


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def families() -> tuple[FamilySpec, ...]:
    return (
        FamilySpec(
            key="add_allDOW",
            label="Additive allDOW",
            base_spec=val.CANDIDATES[0],
            direction_filter="both",
            no_thursday=False,
            base_entry_end="15:30",
            base_rr=2.5,
            base_tp1_ratio=0.4,
        ),
        FamilySpec(
            key="add_noThu",
            label="Additive noThu",
            base_spec=val.CANDIDATES[0],
            direction_filter="both",
            no_thursday=True,
            base_entry_end="15:30",
            base_rr=2.5,
            base_tp1_ratio=0.4,
        ),
        FamilySpec(
            key="pure_cisd",
            label="Pure CISD",
            base_spec=val.CANDIDATES[1],
            direction_filter="long",
            no_thursday=False,
            base_entry_end="12:00",
            base_rr=2.0,
            base_tp1_ratio=0.6,
        ),
    )


def variant_key(
    family: FamilySpec,
    *,
    stop_atr_pct: float,
    cisd_min_leg_bars: int,
    cisd_min_leg_atr_pct: float,
    entry_end: str,
    rr: float,
    tp1_ratio: float,
) -> str:
    return (
        f"{family.key}"
        f"__stop{fmt(stop_atr_pct)}"
        f"__b{cisd_min_leg_bars}"
        f"__a{fmt(cisd_min_leg_atr_pct)}"
        f"__cut{fmt(entry_end)}"
        f"__rr{fmt(rr)}"
        f"__tp1_{fmt(tp1_ratio)}"
    )


def make_config(
    family: FamilySpec,
    *,
    key: str,
    stop_atr_pct: float,
    cisd_min_leg_bars: int,
    cisd_min_leg_atr_pct: float,
    entry_end: str,
    rr: float,
    tp1_ratio: float,
) -> seq.StrategyConfig:
    cfg = val.cfg_for(
        family.base_spec,
        label=f"hot1|{key}",
        stop_atr_pct=stop_atr_pct,
        cisd_min_leg_bars=cisd_min_leg_bars,
        cisd_min_leg_atr_pct=cisd_min_leg_atr_pct,
    )
    session = dataclasses.replace(cfg.sessions[0], entry_end=entry_end, stop_atr_pct=stop_atr_pct)
    return dataclasses.replace(
        cfg,
        direction_filter=family.direction_filter,
        excluded_days=(3,) if family.no_thursday else (),
        sessions=(session,),
        rr=rr,
        tp1_ratio=tp1_ratio,
        name=f"hot1|{key}",
    )


def make_variant(
    family: FamilySpec,
    *,
    stage: str,
    stop_atr_pct: float,
    cisd_min_leg_bars: int,
    cisd_min_leg_atr_pct: float,
    entry_end: str,
    rr: float,
    tp1_ratio: float,
) -> VariantSpec:
    key = variant_key(
        family,
        stop_atr_pct=stop_atr_pct,
        cisd_min_leg_bars=cisd_min_leg_bars,
        cisd_min_leg_atr_pct=cisd_min_leg_atr_pct,
        entry_end=entry_end,
        rr=rr,
        tp1_ratio=tp1_ratio,
    )
    return VariantSpec(
        key=key,
        family_key=family.key,
        stage=stage,
        stop_atr_pct=stop_atr_pct,
        cisd_min_leg_bars=cisd_min_leg_bars,
        cisd_min_leg_atr_pct=cisd_min_leg_atr_pct,
        entry_end=entry_end,
        rr=rr,
        tp1_ratio=tp1_ratio,
        config=make_config(
            family,
            key=key,
            stop_atr_pct=stop_atr_pct,
            cisd_min_leg_bars=cisd_min_leg_bars,
            cisd_min_leg_atr_pct=cisd_min_leg_atr_pct,
            entry_end=entry_end,
            rr=rr,
            tp1_ratio=tp1_ratio,
        ),
    )


def structural_variants() -> tuple[VariantSpec, ...]:
    out: list[VariantSpec] = []
    for family in families():
        for stop in STOP_ATR_VALUES:
            for bars in CISD_BARS_VALUES:
                for atr in CISD_ATR_VALUES:
                    for entry_end in ENTRY_END_VALUES:
                        out.append(
                            make_variant(
                                family,
                                stage="structure",
                                stop_atr_pct=stop,
                                cisd_min_leg_bars=bars,
                                cisd_min_leg_atr_pct=atr,
                                entry_end=entry_end,
                                rr=family.base_rr,
                                tp1_ratio=family.base_tp1_ratio,
                            )
                        )
    return tuple(out)


def target_pairs() -> tuple[tuple[float, float], ...]:
    pairs: list[tuple[float, float]] = []
    for rr in RR_VALUES:
        for tp1 in TP1_VALUES:
            if rr * tp1 >= 1.0:
                pairs.append((rr, tp1))
    return tuple(pairs)


def target_variants_from_structures(structure_rows: pd.DataFrame) -> tuple[VariantSpec, ...]:
    by_family = {family.key: family for family in families()}
    selected: list[dict[str, Any]] = []
    for family_key in by_family:
        pool = structure_rows[structure_rows["family_key"] == family_key]
        top_net = pool.sort_values("total_r", ascending=False).head(TOP_STRUCTURES_PER_FAMILY)
        top_score = pool.sort_values("hot_score", ascending=False).head(TOP_STRUCTURES_PER_FAMILY // 2)
        baseline = pool[
            np.isclose(pool["stop_atr_pct"], by_family[family_key].base_spec.stop_atr_pct)
            & (pool["cisd_min_leg_bars"] == by_family[family_key].base_spec.cisd_min_leg_bars)
            & np.isclose(pool["cisd_min_leg_atr_pct"], by_family[family_key].base_spec.cisd_min_leg_atr_pct)
            & (pool["entry_end"] == by_family[family_key].base_entry_end)
        ]
        merged = pd.concat([top_net, top_score, baseline.head(1)], ignore_index=True)
        merged = merged.drop_duplicates(
            subset=["family_key", "stop_atr_pct", "cisd_min_leg_bars", "cisd_min_leg_atr_pct", "entry_end"]
        )
        selected.extend(merged.to_dict("records"))

    out: list[VariantSpec] = []
    seen: set[str] = set()
    for row in selected:
        family = by_family[str(row["family_key"])]
        for rr, tp1 in target_pairs():
            variant = make_variant(
                family,
                stage="target",
                stop_atr_pct=float(row["stop_atr_pct"]),
                cisd_min_leg_bars=int(row["cisd_min_leg_bars"]),
                cisd_min_leg_atr_pct=float(row["cisd_min_leg_atr_pct"]),
                entry_end=str(row["entry_end"]),
                rr=rr,
                tp1_ratio=tp1,
            )
            if variant.key not in seen:
                out.append(variant)
                seen.add(variant.key)
    return tuple(out)


def filled_trades(trades: list[Any]) -> list[Any]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def hot_score(row: dict[str, Any]) -> float:
    if row["trades"] < 8:
        return -1e9 + row["trades"]
    return float(row["total_r"]) - 0.50 * abs(float(row["max_dd_r"])) + 0.05 * int(row["trades"])


def score_rows(trades_by_key: dict[str, list[Any]], variant_by_key: dict[str, VariantSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, trades in trades_by_key.items():
        variant = variant_by_key[key]
        filled = filled_trades(trades)
        row = val.row_from_r(key, variant.stage, "last_1y", filled, [trade.r_multiple for trade in filled])
        row.update(
            {
                "family_key": variant.family_key,
                "stage": variant.stage,
                "stop_atr_pct": variant.stop_atr_pct,
                "cisd_min_leg_bars": variant.cisd_min_leg_bars,
                "cisd_min_leg_atr_pct": variant.cisd_min_leg_atr_pct,
                "entry_end": variant.entry_end,
                "rr": variant.rr,
                "tp1_ratio": variant.tp1_ratio,
                "deployability": "research_only",
                "live_support_notes": (
                    "Recent-window in-sample optimization. Uses live-native fields, but the selected "
                    "row itself is not promotion-ready without exact replay or forward validation."
                ),
                "exact_replay_required": "yes",
            }
        )
        row["hot_score"] = hot_score(row)
        rows.append(row)
    return rows


def run_variants(
    *,
    label: str,
    df: pd.DataFrame,
    signal_df: pd.DataFrame,
    variants: tuple[VariantSpec, ...],
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, list[Any]]]:
    variant_by_name = {variant.config.name: variant for variant in variants}
    variant_by_key = {variant.key: variant for variant in variants}
    total = len(variants)
    print(f"{label}: running {total} rows", flush=True)

    def progress(done: int, total_count: int) -> None:
        if done == total_count or done % 50 == 0:
            print(f"  {label} completed {done}/{total_count}", flush=True)

    results = run_sweep(
        df,
        [variant.config for variant in variants],
        n_workers=N_WORKERS,
        progress_fn=progress,
        start_date=start_date,
        end_date=end_date,
        signal_df_1m=signal_df,
    )
    trades_by_key: dict[str, list[Any]] = {}
    for config, trades in results:
        variant = variant_by_name[config.name]
        trades_by_key[variant.key] = trades
    return score_rows(trades_by_key, variant_by_key), trades_by_key


def markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows_"
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        values = []
        for col in columns:
            value = row.get(col, "")
            if isinstance(value, float):
                if col in {"win_rate"}:
                    value = f"{value:.1%}"
                else:
                    value = f"{value:.2f}"
            values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def compact_candidate(row: pd.Series) -> dict[str, Any]:
    return {
        "family": row["family_key"],
        "trades": int(row["trades"]),
        "win_rate": float(row["win_rate"]),
        "total_r": float(row["total_r"]),
        "max_dd_r": float(row["max_dd_r"]),
        "profit_factor": float(row["profit_factor"]),
        "calmar": float(row["calmar"]),
        "long": int(row["long_trades"]),
        "short": int(row["short_trades"]),
        "cisd": int(row["cisd_trades"]),
        "inv": int(row["inversion_trades"]),
        "stop": float(row["stop_atr_pct"]),
        "bars": int(row["cisd_min_leg_bars"]),
        "body_atr": float(row["cisd_min_leg_atr_pct"]),
        "cut": row["entry_end"],
        "rr": float(row["rr"]),
        "tp1": float(row["tp1_ratio"]),
        "score": float(row["hot_score"]),
    }


def write_report(
    *,
    latest_date: str,
    start_date: str,
    end_date: str,
    structure_rows: pd.DataFrame,
    target_rows: pd.DataFrame,
) -> None:
    family_labels = {family.key: family.label for family in families()}
    lines = [
        "# NQ NY LSI/CISD Hot-Regime Sweep",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data latest date: `{latest_date}`",
        f"- Optimization window: `{start_date}` to `{pd.Timestamp(end_date) - pd.Timedelta(days=1):%Y-%m-%d}`",
        "- Intent: in-sample trailing-one-year squeeze for the pure-CISD leg and the two additive finalist legs.",
        "- Status: `research_only`; this is not a robust promotion packet.",
        f"- Stage 1 structure rows: `{len(structure_rows)}`. Stage 2 target rows: `{len(target_rows)}`.",
        "",
        "## Best Target Rows By Family",
        "",
    ]

    best_rows: list[dict[str, Any]] = []
    for family_key, label in family_labels.items():
        pool = target_rows[target_rows["family_key"] == family_key].sort_values("total_r", ascending=False)
        if pool.empty:
            continue
        best_rows.append({"leg": label, **compact_candidate(pool.iloc[0])})
    lines.append(
        markdown_table(
            best_rows,
            [
                "leg",
                "trades",
                "win_rate",
                "total_r",
                "max_dd_r",
                "profit_factor",
                "long",
                "short",
                "cisd",
                "inv",
                "stop",
                "bars",
                "body_atr",
                "cut",
                "rr",
                "tp1",
            ],
        )
    )
    lines.append("")

    lines.append("## Top 10 Overall By Net R")
    lines.append("")
    top_overall = [compact_candidate(row) for _, row in target_rows.sort_values("total_r", ascending=False).head(10).iterrows()]
    lines.append(
        markdown_table(
            top_overall,
            [
                "family",
                "trades",
                "win_rate",
                "total_r",
                "max_dd_r",
                "profit_factor",
                "long",
                "short",
                "cisd",
                "inv",
                "stop",
                "bars",
                "body_atr",
                "cut",
                "rr",
                "tp1",
            ],
        )
    )
    lines.append("")

    lines.append("## Baseline Vs Best")
    lines.append("")
    baseline_rows: list[dict[str, Any]] = []
    for family in families():
        pool = target_rows[target_rows["family_key"] == family.key]
        best = pool.sort_values("total_r", ascending=False).iloc[0]
        base = pool[
            np.isclose(pool["stop_atr_pct"], family.base_spec.stop_atr_pct)
            & (pool["cisd_min_leg_bars"] == family.base_spec.cisd_min_leg_bars)
            & np.isclose(pool["cisd_min_leg_atr_pct"], family.base_spec.cisd_min_leg_atr_pct)
            & (pool["entry_end"] == family.base_entry_end)
            & np.isclose(pool["rr"], family.base_rr)
            & np.isclose(pool["tp1_ratio"], family.base_tp1_ratio)
        ]
        if base.empty:
            continue
        base_row = base.iloc[0]
        baseline_rows.append(
            {
                "leg": family.label,
                "baseline_r": float(base_row["total_r"]),
                "best_r": float(best["total_r"]),
                "delta_r": float(best["total_r"] - base_row["total_r"]),
                "baseline_dd": float(base_row["max_dd_r"]),
                "best_dd": float(best["max_dd_r"]),
                "baseline_trades": int(base_row["trades"]),
                "best_trades": int(best["trades"]),
            }
        )
    lines.append(
        markdown_table(
            baseline_rows,
            ["leg", "baseline_r", "best_r", "delta_r", "baseline_dd", "best_dd", "baseline_trades", "best_trades"],
        )
    )
    lines.append("")

    lines.extend(
        [
            "## Read",
            "",
            "- Rows are intentionally optimized on the same trailing-year window they report, so treat them as hot-regime research candidates.",
            "- The highest-net-R rows answer the squeeze question; prefer follow-up exact replay and forward testing before deployment sizing.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    data = seq.load_timeframes()
    full_1m = data["1m"]
    latest_date = full_1m.index.max().date().isoformat()
    latest_ts = pd.Timestamp(latest_date)
    start_date = (latest_ts - pd.Timedelta(days=365)).date().isoformat()
    end_date = (latest_ts + pd.Timedelta(days=1)).date().isoformat()
    warmup_start = (pd.Timestamp(start_date) - pd.Timedelta(days=70)).date().isoformat()

    df = full_1m[full_1m.index >= warmup_start].copy()
    signal_df = df

    print("NQ NY LSI/CISD hot-regime sweep", flush=True)
    print("=" * 88, flush=True)
    print(f"Latest data date: {latest_date}", flush=True)
    print(f"Optimization window: {start_date} to {latest_date}", flush=True)
    print(f"Warmup from: {warmup_start}", flush=True)

    structures = structural_variants()
    structure_rows, _ = run_variants(
        label="stage1_structure",
        df=df,
        signal_df=signal_df,
        variants=structures,
        start_date=start_date,
        end_date=end_date,
    )
    structure_df = pd.DataFrame(structure_rows).sort_values("total_r", ascending=False)
    structure_df.to_csv(OUTPUT_DIR / "structure_scores.csv", index=False)

    targets = target_variants_from_structures(structure_df)
    target_rows, _ = run_variants(
        label="stage2_targets",
        df=df,
        signal_df=signal_df,
        variants=targets,
        start_date=start_date,
        end_date=end_date,
    )
    target_df = pd.DataFrame(target_rows).sort_values("total_r", ascending=False)
    target_df.to_csv(OUTPUT_DIR / "target_scores.csv", index=False)

    top_rows = []
    for family in families():
        pool = target_df[target_df["family_key"] == family.key].sort_values("total_r", ascending=False).head(20)
        top_rows.extend(pool.to_dict("records"))
    pd.DataFrame(top_rows).to_csv(OUTPUT_DIR / "top_by_family.csv", index=False)

    manifest = {
        "run_slug": RUN_SLUG,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "latest_data_date": latest_date,
        "start_date": start_date,
        "end_date_exclusive": end_date,
        "warmup_start": warmup_start,
        "workers": N_WORKERS,
        "families": [dataclasses.asdict(family) for family in families()],
        "stage1_grid": {
            "stop_atr_pct": STOP_ATR_VALUES,
            "cisd_min_leg_bars": CISD_BARS_VALUES,
            "cisd_min_leg_atr_pct": CISD_ATR_VALUES,
            "entry_end": ENTRY_END_VALUES,
            "rows": len(structures),
        },
        "stage2_grid": {
            "rr": RR_VALUES,
            "tp1_ratio": TP1_VALUES,
            "valid_target_pairs": target_pairs(),
            "top_structures_per_family": TOP_STRUCTURES_PER_FAMILY,
            "rows": len(targets),
        },
    }
    save_json(OUTPUT_DIR / "manifest.json", manifest)
    write_report(
        latest_date=latest_date,
        start_date=start_date,
        end_date=end_date,
        structure_rows=structure_df,
        target_rows=target_df,
    )

    print("\nBest rows by family:", flush=True)
    for family in families():
        row = target_df[target_df["family_key"] == family.key].sort_values("total_r", ascending=False).iloc[0]
        print(
            f"  {family.label:<16} {row['total_r']:.1f}R DD {row['max_dd_r']:.1f} "
            f"PF {row['profit_factor']:.2f} trades {int(row['trades'])} "
            f"stop {row['stop_atr_pct']} bars {row['cisd_min_leg_bars']} "
            f"atr {row['cisd_min_leg_atr_pct']} cut {row['entry_end']} "
            f"rr {row['rr']} tp1 {row['tp1_ratio']}",
            flush=True,
        )
    print(f"\nOutput: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
