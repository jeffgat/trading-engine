#!/usr/bin/env python3
"""Target-only sweep for NQ NY LSI/CISD finalists.

Keeps signal, entry, stop, timeframe, and DOW restrictions frozen for:

- additive all weekdays cutoff 15:30
- additive no Thursday cutoff 15:30
- pure CISD long-only cutoff 12:00

Only rr and tp1_ratio are swept. Invalid rows where TP1 would be less than
1R are skipped by construction.
"""

from __future__ import annotations

import dataclasses
import json
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


OUTPUT_DIR = seq.ROOT / "data" / "results" / "nq_ny_lsi_cisd_target_sweep_20260504"
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_TARGET_SWEEP_20260504.md"

RR_VALUES = (1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0)
TP1_VALUES = (0.4, 0.5, 0.6, 0.7, 0.8)


@dataclasses.dataclass(frozen=True)
class TargetVariant:
    key: str
    base_key: str
    base_label: str
    rr: float
    tp1_ratio: float
    config: seq.StrategyConfig


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def target_label(base_key: str, rr: float, tp1_ratio: float) -> str:
    def fmt(value: float) -> str:
        return str(value).replace(".", "p")

    return f"{base_key}__rr{fmt(rr)}__tp1_{fmt(tp1_ratio)}"


def base_variants() -> tuple[restricted.VariantSpec, ...]:
    return (
        restricted.make_variant(
            val.CANDIDATES[0],
            direction="both",
            no_thursday=False,
            noon_cutoff=False,
        ),
        restricted.make_variant(
            val.CANDIDATES[0],
            direction="both",
            no_thursday=True,
            noon_cutoff=False,
        ),
        restricted.make_variant(
            val.CANDIDATES[1],
            direction="long",
            no_thursday=False,
            noon_cutoff=True,
        ),
    )


def build_variants() -> tuple[TargetVariant, ...]:
    variants: list[TargetVariant] = []
    for base in base_variants():
        for rr in RR_VALUES:
            for tp1_ratio in TP1_VALUES:
                if rr * tp1_ratio < 1.0:
                    continue
                key = target_label(base.key, rr, tp1_ratio)
                cfg = dataclasses.replace(
                    base.config,
                    rr=rr,
                    tp1_ratio=tp1_ratio,
                    name=f"1m|target_sweep|{key}",
                )
                variants.append(
                    TargetVariant(
                        key=key,
                        base_key=base.key,
                        base_label=base.label,
                        rr=rr,
                        tp1_ratio=tp1_ratio,
                        config=cfg,
                    )
                )
    return tuple(variants)


def filled_trades(trades: list[Any], *, start: str | None = None, end: str | None = None) -> list[Any]:
    return [
        trade for trade in trades
        if trade.exit_type != EXIT_NO_FILL
        and (start is None or trade.date >= start)
        and (end is None or trade.date < end)
    ]


def period_rows(
    trades_by_key: dict[str, list[Any]],
    variant_by_key: dict[str, TargetVariant],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, trades in trades_by_key.items():
        variant = variant_by_key[key]
        for period, (start, end) in val.PERIODS.items():
            subset = filled_trades(trades, start=start, end=end)
            row = val.row_from_r(key, "period", period, subset, [trade.r_multiple for trade in subset])
            row.update(
                {
                    "base_key": variant.base_key,
                    "base_label": variant.base_label,
                    "rr": variant.rr,
                    "tp1_ratio": variant.tp1_ratio,
                    "deployability": "live_native",
                    "live_support_notes": (
                        "Uses simulator-native LSI/CISD confirmation, level-limit entry, "
                        "ATR stop, rr/tp1, session cutoff, and DOW exclusion fields."
                    ),
                    "exact_replay_required": "yes",
                }
            )
            rows.append(row)
    return rows


def year_rows(
    trades_by_key: dict[str, list[Any]],
    variant_by_key: dict[str, TargetVariant],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, trades in trades_by_key.items():
        variant = variant_by_key[key]
        years = sorted({trade.date[:4] for trade in filled_trades(trades, start="2016-01-01")})
        for year in years:
            subset = filled_trades(trades, start=f"{year}-01-01", end=f"{int(year) + 1}-01-01")
            row = val.row_from_r(key, "year", year, subset, [trade.r_multiple for trade in subset])
            row.update({"base_key": variant.base_key, "rr": variant.rr, "tp1_ratio": variant.tp1_ratio})
            rows.append(row)
    return rows


def rank_rows(periods: list[dict[str, Any]], years: list[dict[str, Any]]) -> list[dict[str, Any]]:
    period_df = pd.DataFrame(periods)
    year_df = pd.DataFrame(years)
    year_map = {}
    if not year_df.empty:
        for candidate, group in year_df.groupby("candidate"):
            full_years = group[group["name"].astype(str) < "2026"]
            year_map[candidate] = {
                "negative_years": int((full_years["total_r"] < 0).sum()),
                "worst_year_r": float(full_years["total_r"].min()) if not full_years.empty else 0.0,
                "r_2025": float(group.loc[group["name"] == "2025", "total_r"].iloc[0])
                if (group["name"] == "2025").any()
                else 0.0,
            }

    by_candidate: dict[str, dict[str, dict[str, Any]]] = {}
    for _, row in period_df.iterrows():
        by_candidate.setdefault(str(row["candidate"]), {})[str(row["name"])] = row.to_dict()

    ranked: list[dict[str, Any]] = []
    for candidate, periods in by_candidate.items():
        full = periods.get("full")
        validation = periods.get("validation")
        holdout = periods.get("holdout")
        post = periods.get("post_2023")
        if not (full and validation and holdout and post):
            continue
        robust = (
            validation["trades"] >= 20
            and holdout["trades"] >= 15
            and validation["profit_factor"] > 1.0
            and holdout["profit_factor"] > 1.0
            and full["total_r"] > 0
            and post["total_r"] > 0
        )
        year_info = year_map.get(candidate, {"negative_years": 0, "worst_year_r": 0.0, "r_2025": 0.0})
        score = (
            min(validation["calmar"], holdout["calmar"], post["calmar"])
            + 0.25 * min(validation["profit_factor"], holdout["profit_factor"], post["profit_factor"])
            + 0.02 * post["trades"]
            - 0.5 * year_info["negative_years"]
        )
        ranked.append(
            {
                "candidate": candidate,
                "base_key": post["base_key"],
                "rr": float(post["rr"]),
                "tp1_ratio": float(post["tp1_ratio"]),
                "robust": bool(robust),
                "score": float(score),
                "full_trades": int(full["trades"]),
                "full_total_r": float(full["total_r"]),
                "full_pf": float(full["profit_factor"]),
                "full_dd": float(full["max_dd_r"]),
                "validation_total_r": float(validation["total_r"]),
                "validation_pf": float(validation["profit_factor"]),
                "validation_calmar": float(validation["calmar"]),
                "holdout_total_r": float(holdout["total_r"]),
                "holdout_pf": float(holdout["profit_factor"]),
                "holdout_calmar": float(holdout["calmar"]),
                "post_2023_trades": int(post["trades"]),
                "post_2023_total_r": float(post["total_r"]),
                "post_2023_pf": float(post["profit_factor"]),
                "post_2023_dd": float(post["max_dd_r"]),
                "post_2023_calmar": float(post["calmar"]),
                "negative_years": int(year_info["negative_years"]),
                "worst_year_r": float(year_info["worst_year_r"]),
                "r_2025": float(year_info["r_2025"]),
                "deployability": "live_native",
                "live_support_notes": (
                    "Uses simulator-native LSI/CISD confirmation, level-limit entry, "
                    "ATR stop, rr/tp1, session cutoff, and DOW exclusion fields."
                ),
                "exact_replay_required": "yes",
            }
        )
    return sorted(ranked, key=lambda row: (row["robust"], row["score"]), reverse=True)


def baseline_delta_rows(ranked: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(ranked)
    out: list[dict[str, Any]] = []
    for base_key in df["base_key"].unique():
        base = df[
            (df["base_key"] == base_key)
            & np.isclose(df["rr"], 2.0)
            & np.isclose(df["tp1_ratio"], 0.5)
        ]
        if base.empty:
            continue
        base_row = base.iloc[0]
        for _, row in df[df["base_key"] == base_key].iterrows():
            out.append(
                {
                    "candidate": row["candidate"],
                    "base_key": base_key,
                    "rr": float(row["rr"]),
                    "tp1_ratio": float(row["tp1_ratio"]),
                    "delta_full_r": float(row["full_total_r"] - base_row["full_total_r"]),
                    "delta_full_dd": float(row["full_dd"] - base_row["full_dd"]),
                    "delta_post_2023_r": float(row["post_2023_total_r"] - base_row["post_2023_total_r"]),
                    "delta_post_2023_pf": float(row["post_2023_pf"] - base_row["post_2023_pf"]),
                    "delta_2025_r": float(row["r_2025"] - base_row["r_2025"]),
                    "delta_score": float(row["score"] - base_row["score"]),
                }
            )
    return out


def phase_one_rows(
    trades_by_key: dict[str, list[Any]],
    ranked: list[dict[str, Any]],
    latest_date: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    finalist_keys: list[str] = []
    ranked_df = pd.DataFrame(ranked)
    for base_key in ranked_df["base_key"].unique():
        base_rows = ranked_df[(ranked_df["base_key"] == base_key) & (ranked_df["robust"])].head(5)
        finalist_keys.extend(str(candidate) for candidate in base_rows["candidate"].tolist())
    finalist_keys = list(dict.fromkeys(finalist_keys))
    stop = (pd.Timestamp(latest_date).date() + pd.Timedelta(days=1)).isoformat()
    for key in finalist_keys:
        trades = trades_by_key[key]
        for window, (start, end) in {
            "full": ("2016-01-01", stop),
            "post_2023": (seq.VALIDATION_START, stop),
            "holdout": (seq.HOLDOUT_START, stop),
        }.items():
            result = val.simulate_staggered_accounts(
                trades,
                start=start,
                end=end,
                cycle_days=14,
                payout_r=5.0,
                breach_r=-4.0,
            )
            rows.append(
                {
                    "candidate": key,
                    "window": window,
                    "profile": "normal_5payout_4breach",
                    "payout_r": 5.0,
                    "breach_r": -4.0,
                    **result,
                }
            )
    return rows


def write_report(
    *,
    latest_date: str,
    ranked: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    phase_one: list[dict[str, Any]],
) -> None:
    lines = [
        "# NQ NY LSI CISD Target Sweep",
        "",
        f"- Latest data date: `{latest_date}`.",
        "- Scope: target-only sweep on 3 frozen finalists; signal, entry, stop, sweep source, timeframe, DOW, and session cutoffs are unchanged.",
        f"- RR values: `{list(RR_VALUES)}`.",
        f"- TP1 ratio values: `{list(TP1_VALUES)}`; rows with `rr * tp1_ratio < 1.0` skipped.",
        "- Deployability for swept rows: `live_native`; exact replay still required before execution-config promotion.",
        "",
        "## Top Rows",
        "",
        "| Rank | Candidate | Robust | Full R/PF/DD | V R/PF | H R/PF | Post-2023 R/PF/DD | 2025 R | Neg Years |",
        "| ---: | --- | --- | --- | --- | --- | --- | ---: | ---: |",
    ]
    for idx, row in enumerate(ranked[:20], start=1):
        lines.append(
            f"| {idx} | `{row['candidate']}` | `{row['robust']}` | "
            f"{row['full_total_r']:.1f} / {row['full_pf']:.2f} / {row['full_dd']:.1f} | "
            f"{row['validation_total_r']:.1f} / {row['validation_pf']:.2f} | "
            f"{row['holdout_total_r']:.1f} / {row['holdout_pf']:.2f} | "
            f"{row['post_2023_total_r']:.1f} / {row['post_2023_pf']:.2f} / {row['post_2023_dd']:.1f} | "
            f"{row['r_2025']:.1f} | {row['negative_years']} |"
        )

    lines.extend(["", "## Best By Base", ""])
    ranked_df = pd.DataFrame(ranked)
    phase_df = pd.DataFrame(phase_one)
    for base_key in ranked_df["base_key"].unique():
        pool = ranked_df[(ranked_df["base_key"] == base_key) & (ranked_df["robust"])].head(5)
        if pool.empty:
            pool = ranked_df[ranked_df["base_key"] == base_key].head(5)
        lines.append(f"### {base_key}")
        for _, row in pool.iterrows():
            delta = next((d for d in deltas if d["candidate"] == row["candidate"]), None)
            dpost = f"{delta['delta_post_2023_r']:+.1f}R" if delta else "n/a"
            d2025 = f"{delta['delta_2025_r']:+.1f}R" if delta else "n/a"
            prop = phase_df[
                (phase_df["candidate"] == row["candidate"])
                & (phase_df["window"] == "post_2023")
            ]
            prop_txt = ""
            if not prop.empty:
                p = prop.iloc[0]
                prop_txt = f"; phase-one post-2023 payout `{p['payout_rate']:.1%}`, breach `{p['breach_rate']:.1%}`, EV `{p['ev_r']:.2f}R`"
            lines.append(
                f"- `rr={row['rr']:.2f}`, `tp1={row['tp1_ratio']:.2f}`: "
                f"post-2023 `{row['post_2023_total_r']:.1f}R` PF `{row['post_2023_pf']:.2f}` "
                f"DD `{row['post_2023_dd']:.1f}`; 2025 `{row['r_2025']:.1f}R`; "
                f"delta post-2023 `{dpost}`, delta 2025 `{d2025}`{prop_txt}."
            )
        lines.append("")

    lines.extend(["## Baseline Delta Summary", ""])
    delta_df = pd.DataFrame(deltas)
    for base_key in delta_df["base_key"].unique():
        lines.append(f"### {base_key}")
        pool = delta_df[delta_df["base_key"] == base_key].sort_values("delta_score", ascending=False).head(8)
        for _, row in pool.iterrows():
            lines.append(
                f"- `{row['candidate']}`: dScore `{row['delta_score']:+.2f}`, "
                f"dPost23 `{row['delta_post_2023_r']:+.1f}R`, dPF `{row['delta_post_2023_pf']:+.2f}`, "
                f"d2025 `{row['delta_2025_r']:+.1f}R`, dFullDD `{row['delta_full_dd']:+.1f}`."
            )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI/CISD target-only sweep", flush=True)
    print("=" * 88, flush=True)

    data = seq.load_timeframes()
    df = data["1m"]
    latest_date = df.index.max().date().isoformat()
    variants = build_variants()
    variant_by_name = {variant.config.name: variant for variant in variants}
    print(f"Loaded cached 1m data through {latest_date}", flush=True)
    print(f"Running {len(variants)} target rows", flush=True)

    def progress(done: int, total: int) -> None:
        if done == total or done % 10 == 0:
            print(f"  completed {done}/{total}", flush=True)

    results = run_sweep(
        df,
        [variant.config for variant in variants],
        n_workers=8,
        progress_fn=progress,
        signal_df_1m=data["1m"],
    )

    trades_by_key: dict[str, list[Any]] = {}
    variant_by_key: dict[str, TargetVariant] = {}
    for config, trades in results:
        variant = variant_by_name[config.name]
        trades_by_key[variant.key] = trades
        variant_by_key[variant.key] = variant

    periods = period_rows(trades_by_key, variant_by_key)
    years = year_rows(trades_by_key, variant_by_key)
    ranked = rank_rows(periods, years)
    deltas = baseline_delta_rows(ranked)
    phase_one = phase_one_rows(trades_by_key, ranked, latest_date)

    pd.DataFrame(periods).to_csv(OUTPUT_DIR / "period_scorecards.csv", index=False)
    pd.DataFrame(years).to_csv(OUTPUT_DIR / "year_scorecards.csv", index=False)
    pd.DataFrame(ranked).to_csv(OUTPUT_DIR / "ranked_targets.csv", index=False)
    pd.DataFrame(deltas).to_csv(OUTPUT_DIR / "baseline_deltas.csv", index=False)
    pd.DataFrame(phase_one).to_csv(OUTPUT_DIR / "phase_one_accounts.csv", index=False)
    save_json(
        OUTPUT_DIR / "summary.json",
        {
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "latest_data_date": latest_date,
            "rr_values": RR_VALUES,
            "tp1_values": TP1_VALUES,
            "rows": len(variants),
            "bases": [
                {
                    "key": base.key,
                    "base_key": base.base_key,
                    "label": base.label,
                }
                for base in base_variants()
            ],
            "ranked": ranked,
        },
    )
    write_report(latest_date=latest_date, ranked=ranked, deltas=deltas, phase_one=phase_one)

    print("\nTop rows:", flush=True)
    for row in ranked[:10]:
        print(
            f"  {row['candidate']:<80} post23 {row['post_2023_total_r']:.1f}R "
            f"PF {row['post_2023_pf']:.2f} DD {row['post_2023_dd']:.1f} "
            f"2025 {row['r_2025']:.1f}R",
            flush=True,
        )
    print(f"\nOutput: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
