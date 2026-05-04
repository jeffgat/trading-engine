#!/usr/bin/env python3
"""Restricted finalist pass for NQ NY LSI/CISD.

This follows the frozen-candidate validation result. It tests only the
pre-registered structural restrictions suggested by the decomposition:

- both directions vs long-only
- all weekdays vs no Thursday
- normal NY fill window vs cutoff at 12:00 ET

No broader parameter search is performed.
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
import run_nq_ny_lsi_cisd_sequence as seq

sys.path.insert(0, str(seq.ROOT / "src"))

from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.simulate.monte_carlo import (  # noqa: E402
    MonteCarloConfig,
    mc_result_to_dict,
    run_monte_carlo,
)
from orb_backtest.validate.deflated_sharpe import annotate_trades  # noqa: E402


OUTPUT_DIR = seq.ROOT / "data" / "results" / "nq_ny_lsi_cisd_restricted_finalists_20260503"
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_RESTRICTED_FINALISTS_20260503.md"
N_SEARCH_TRIALS = 258  # 242 prior rows + 16 pre-registered restriction rows.


@dataclasses.dataclass(frozen=True)
class VariantSpec:
    key: str
    base_key: str
    label: str
    direction_filter: str
    no_thursday: bool
    noon_cutoff: bool
    config: seq.StrategyConfig


BASE_SPECS = (
    val.CANDIDATES[0],  # primary additive 1m
    val.CANDIDATES[1],  # pure CISD 1m
)


def make_variant(base: val.CandidateSpec, *, direction: str, no_thursday: bool, noon_cutoff: bool) -> VariantSpec:
    label_parts = [
        "1m",
        "restricted",
        base.key,
        direction,
        "noThu" if no_thursday else "allDOW",
        "cut1200" if noon_cutoff else "cut1530",
    ]
    key = "__".join(label_parts[2:])
    label = "|".join(label_parts)
    cfg = val.cfg_for(base, label=label)
    session = cfg.sessions[0]
    if noon_cutoff:
        session = dataclasses.replace(session, entry_end="12:00")
    cfg = dataclasses.replace(
        cfg,
        direction_filter=direction,
        excluded_days=(3,) if no_thursday else (),
        sessions=(session,),
        name=label,
    )
    human = (
        f"{base.key} / {direction} / "
        f"{'no Thursday' if no_thursday else 'all weekdays'} / "
        f"{'entry cutoff 12:00' if noon_cutoff else 'entry cutoff 15:30'}"
    )
    return VariantSpec(
        key=key,
        base_key=base.key,
        label=human,
        direction_filter=direction,
        no_thursday=no_thursday,
        noon_cutoff=noon_cutoff,
        config=cfg,
    )


def build_variants() -> tuple[VariantSpec, ...]:
    variants: list[VariantSpec] = []
    for base in BASE_SPECS:
        for direction in ("both", "long"):
            for no_thursday in (False, True):
                for noon_cutoff in (False, True):
                    variants.append(
                        make_variant(
                            base,
                            direction=direction,
                            no_thursday=no_thursday,
                            noon_cutoff=noon_cutoff,
                        )
                    )
    return tuple(variants)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def run_variants(data: dict[str, pd.DataFrame], variants: tuple[VariantSpec, ...]) -> dict[str, list[Any]]:
    df = data["1m"]
    maps = build_maps(df, df_1m=None)
    configs = [variant.config for variant in variants]
    cache = build_signal_cache(df, configs, signal_df_1m=data["1m"])
    out: dict[str, list[Any]] = {}
    for idx, variant in enumerate(variants, start=1):
        t0 = time.time()
        trades = run_backtest(
            df,
            variant.config,
            df_1m=None,
            signal_df_1m=data["1m"],
            _maps=maps,
            _signal_cache=cache,
        )
        filled = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
        out[variant.key] = trades
        print(
            f"  [{idx:>2}/{len(variants)}] {variant.key:<70} "
            f"{len(filled):>4} fills [{time.time() - t0:.1f}s]",
            flush=True,
        )
    return out


def period_rows(trades_by_variant: dict[str, list[Any]], variant_by_key: dict[str, VariantSpec]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, trades in trades_by_variant.items():
        variant = variant_by_key[key]
        for period, (start, end) in val.PERIODS.items():
            subset = val.filled_trades(trades, start=start, end=end)
            row = val.row_from_r(key, "period", period, subset, [trade.r_multiple for trade in subset])
            row.update(
                {
                    "base_key": variant.base_key,
                    "direction_filter": variant.direction_filter,
                    "no_thursday": variant.no_thursday,
                    "noon_cutoff": variant.noon_cutoff,
                }
            )
            rows.append(row)
    return rows


def restriction_delta_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(rows)
    out: list[dict[str, Any]] = []
    for base_key in df["base_key"].unique():
        base = df[
            (df["base_key"] == base_key)
            & (df["direction_filter"] == "both")
            & (~df["no_thursday"])
            & (~df["noon_cutoff"])
            & (df["name"] == "post_2023")
        ]
        if base.empty:
            continue
        base_row = base.iloc[0]
        for _, row in df[(df["base_key"] == base_key) & (df["name"] == "post_2023")].iterrows():
            out.append(
                {
                    "variant": row["candidate"],
                    "base_key": base_key,
                    "direction_filter": row["direction_filter"],
                    "no_thursday": bool(row["no_thursday"]),
                    "noon_cutoff": bool(row["noon_cutoff"]),
                    "delta_trades": int(row["trades"] - base_row["trades"]),
                    "delta_total_r": float(row["total_r"] - base_row["total_r"]),
                    "delta_max_dd_r": float(row["max_dd_r"] - base_row["max_dd_r"]),
                    "delta_profit_factor": float(row["profit_factor"] - base_row["profit_factor"]),
                    "delta_calmar": float(row["calmar"] - base_row["calmar"]),
                }
            )
    return out


def rank_variants(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    df = pd.DataFrame(rows)
    wide = {}
    for _, row in df.iterrows():
        wide.setdefault(row["candidate"], {})[row["name"]] = row.to_dict()
    ranked: list[dict[str, Any]] = []
    for candidate, periods in wide.items():
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
        score = (
            min(validation["calmar"], holdout["calmar"], post["calmar"])
            + 0.25 * min(validation["profit_factor"], holdout["profit_factor"], post["profit_factor"])
            + 0.02 * post["trades"]
        )
        ranked.append(
            {
                "candidate": candidate,
                "base_key": post["base_key"],
                "direction_filter": post["direction_filter"],
                "no_thursday": bool(post["no_thursday"]),
                "noon_cutoff": bool(post["noon_cutoff"]),
                "robust": robust,
                "score": score,
                "full_trades": full["trades"],
                "full_total_r": full["total_r"],
                "full_pf": full["profit_factor"],
                "full_dd": full["max_dd_r"],
                "validation_trades": validation["trades"],
                "validation_total_r": validation["total_r"],
                "validation_pf": validation["profit_factor"],
                "validation_calmar": validation["calmar"],
                "holdout_trades": holdout["trades"],
                "holdout_total_r": holdout["total_r"],
                "holdout_pf": holdout["profit_factor"],
                "holdout_calmar": holdout["calmar"],
                "post_2023_trades": post["trades"],
                "post_2023_total_r": post["total_r"],
                "post_2023_pf": post["profit_factor"],
                "post_2023_dd": post["max_dd_r"],
                "post_2023_calmar": post["calmar"],
            }
        )
    return sorted(ranked, key=lambda row: (row["robust"], row["score"]), reverse=True)


def selected_finalists(ranked: list[dict[str, Any]], n: int = 6) -> list[str]:
    robust = [row for row in ranked if row["robust"]]
    return [row["candidate"] for row in robust[:n]]


def diagnostics(
    trades_by_variant: dict[str, list[Any]],
    finalists: list[str],
    latest_date: str,
) -> dict[str, list[dict[str, Any]]]:
    mc_rows: list[dict[str, Any]] = []
    psr_rows: list[dict[str, Any]] = []
    prop_rows: list[dict[str, Any]] = []
    stress_rows: list[dict[str, Any]] = []

    for candidate in finalists:
        trades = trades_by_variant[candidate]
        for period, (start, end) in {
            "full": ("2016-01-01", None),
            "post_2023": (seq.VALIDATION_START, None),
            "holdout": (seq.HOLDOUT_START, None),
        }.items():
            subset = val.filled_trades(trades, start=start, end=end)
            if len(subset) >= 10:
                packet = annotate_trades(
                    np.asarray([trade.r_multiple for trade in subset], dtype=float),
                    n_trials_raw=N_SEARCH_TRIALS,
                )
                psr_rows.append(
                    {
                        "candidate": candidate,
                        "period": period,
                        "trades": len(subset),
                        "psr": packet["psr"]["value"],
                        "psr_interpretation": packet["psr"]["interpretation"],
                        "dsr": packet["dsr"]["value"],
                        "dsr_interpretation": packet["dsr"]["interpretation"],
                        "expected_max_sharpe_null": packet["dsr"]["expected_max_sharpe_null"],
                    }
                )
                for method in ("bootstrap", "block_bootstrap"):
                    mc = run_monte_carlo(
                        subset,
                        MonteCarloConfig(n_simulations=2000, method=method, seed=42),
                        ruin_threshold=-10.0,
                    )
                    mc_rows.append(
                        {
                            "candidate": candidate,
                            "period": period,
                            **mc_result_to_dict(mc),
                        }
                    )

        for period, (start, end) in {
            "validation": (seq.VALIDATION_START, seq.VALIDATION_END),
            "holdout": (seq.HOLDOUT_START, None),
            "post_2023": (seq.VALIDATION_START, None),
        }.items():
            subset = val.filled_trades(trades, start=start, end=end)
            for name, r_values in (
                ("baseline", [trade.r_multiple for trade in subset]),
                ("slip_1t_per_side", val.adjusted_for_slippage(subset, 1.0)),
                ("slip_2t_per_side", val.adjusted_for_slippage(subset, 2.0)),
            ):
                row = val.row_from_r(candidate, f"stress_{period}", name, subset, r_values)
                row["period"] = period
                stress_rows.append(row)

        stop = (pd.Timestamp(latest_date).date() + pd.Timedelta(days=1)).isoformat()
        for window, (start, end) in {
            "full": ("2016-01-01", stop),
            "post_2023": (seq.VALIDATION_START, stop),
            "holdout": (seq.HOLDOUT_START, stop),
        }.items():
            for profile, payout, breach in (
                ("normal_5payout_4breach", 5.0, -4.0),
                ("aggressive_2p5payout_2breach", 2.5, -2.0),
            ):
                result = val.simulate_staggered_accounts(
                    trades,
                    start=start,
                    end=end,
                    cycle_days=14,
                    payout_r=payout,
                    breach_r=breach,
                )
                prop_rows.append(
                    {
                        "candidate": candidate,
                        "window": window,
                        "profile": profile,
                        "payout_r": payout,
                        "breach_r": breach,
                        **result,
                    }
                )

    return {
        "monte_carlo": mc_rows,
        "psr_dsr": psr_rows,
        "phase_one_accounts": prop_rows,
        "execution_stress": stress_rows,
    }


def write_report(
    *,
    latest_date: str,
    ranked: list[dict[str, Any]],
    deltas: list[dict[str, Any]],
    diag: dict[str, list[dict[str, Any]]],
) -> None:
    lines = [
        "# NQ NY LSI CISD Restricted Finalists",
        "",
        f"- Latest data date: `{latest_date}`.",
        "- Scope: pre-registered restrictions only: long-only, no Thursday, and entry cutoff at 12:00 ET.",
        "- Base candidates: primary additive 1m and pure CISD 1m.",
        f"- DSR search-trial count: `{N_SEARCH_TRIALS}`.",
        "",
        "## Top Restricted Rows",
        "",
        "| Rank | Candidate | Robust | Full R | Full PF | Full DD | Validation R/PF | Holdout R/PF | Post-2023 R/PF/DD |",
        "| ---: | --- | --- | ---: | ---: | ---: | --- | --- | --- |",
    ]
    for idx, row in enumerate(ranked[:12], start=1):
        lines.append(
            f"| {idx} | `{row['candidate']}` | `{row['robust']}` | "
            f"{row['full_total_r']:.1f} | {row['full_pf']:.2f} | {row['full_dd']:.1f} | "
            f"{row['validation_total_r']:.1f} / {row['validation_pf']:.2f} | "
            f"{row['holdout_total_r']:.1f} / {row['holdout_pf']:.2f} | "
            f"{row['post_2023_total_r']:.1f} / {row['post_2023_pf']:.2f} / {row['post_2023_dd']:.1f} |"
        )

    lines.extend(["", "## Restriction Deltas", ""])
    delta_df = pd.DataFrame(deltas)
    for base_key in delta_df["base_key"].unique():
        lines.append(f"### {base_key} Post-2023 vs Unrestricted")
        pool = delta_df[delta_df["base_key"] == base_key].sort_values("delta_total_r", ascending=False)
        for _, row in pool.iterrows():
            lines.append(
                f"- `{row['variant']}`: dR `{row['delta_total_r']:+.1f}`, "
                f"dPF `{row['delta_profit_factor']:+.2f}`, dDD `{row['delta_max_dd_r']:+.1f}`, "
                f"dCalmar `{row['delta_calmar']:+.2f}`."
            )
        lines.append("")

    psr_df = pd.DataFrame(diag["psr_dsr"])
    mc_df = pd.DataFrame(diag["monte_carlo"])
    prop_df = pd.DataFrame(diag["phase_one_accounts"])
    stress_df = pd.DataFrame(diag["execution_stress"])

    lines.extend(["## Finalist Diagnostics", ""])
    for candidate in [row["candidate"] for row in ranked if row["robust"]][:6]:
        lines.append(f"### {candidate}")
        psr = psr_df[(psr_df["candidate"] == candidate) & (psr_df["period"] == "post_2023")]
        if not psr.empty:
            row = psr.iloc[0]
            lines.append(
                f"- PSR/DSR post-2023: `{row['psr']:.4f}` / `{row['dsr']:.4f}` "
                f"({row['dsr_interpretation']})."
            )
        mc = mc_df[
            (mc_df["candidate"] == candidate)
            & (mc_df["period"] == "post_2023")
            & (mc_df["method"] == "block_bootstrap")
        ]
        if not mc.empty:
            row = mc.iloc[0]
            lines.append(
                f"- MC post-2023 block bootstrap: final-R p5 `{row['final_pnl_percentiles']['p5']}`, "
                f"DD p5 `{row['max_dd_percentiles']['p5']}`, ruin(-10R) `{row['ruin_probability']:.1%}`."
            )
        prop = prop_df[
            (prop_df["candidate"] == candidate)
            & (prop_df["window"] == "post_2023")
            & (prop_df["profile"] == "normal_5payout_4breach")
        ]
        if not prop.empty:
            row = prop.iloc[0]
            lines.append(
                f"- Phase-one post-2023 normal: payout `{row['payout_rate']:.1%}`, "
                f"breach `{row['breach_rate']:.1%}`, EV `{row['ev_r']:.2f}R`."
            )
        stress = stress_df[
            (stress_df["candidate"] == candidate)
            & (stress_df["period"] == "post_2023")
        ]
        for stress_name in ("baseline", "slip_1t_per_side", "slip_2t_per_side"):
            row = stress[stress["name"] == stress_name]
            if not row.empty:
                r = row.iloc[0]
                lines.append(
                    f"- `{stress_name}` post-2023: `{int(r['trades'])}` tr, PF `{r['profit_factor']:.2f}`, "
                    f"R `{r['total_r']:.1f}`, DD `{r['max_dd_r']:.1f}`."
                )
        lines.append("")

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI/CISD restricted finalist pass", flush=True)
    print("=" * 88, flush=True)

    data = seq.load_timeframes()
    latest_date = max(df.index.max() for df in data.values()).date().isoformat()
    print(f"Loaded cached data through {latest_date}", flush=True)

    variants = build_variants()
    variant_by_key = {variant.key: variant for variant in variants}
    trades_by_variant = run_variants(data, variants)

    rows = period_rows(trades_by_variant, variant_by_key)
    deltas = restriction_delta_rows(rows)
    ranked = rank_variants(rows)
    finalists = selected_finalists(ranked)
    print("\nSelected finalists:", flush=True)
    for row in ranked[:8]:
        print(
            f"  {row['candidate']:<70} robust={row['robust']} "
            f"post23 R {row['post_2023_total_r']:.1f} PF {row['post_2023_pf']:.2f} "
            f"DD {row['post_2023_dd']:.1f}",
            flush=True,
        )

    diag = diagnostics(trades_by_variant, finalists, latest_date)

    pd.DataFrame(rows).to_csv(OUTPUT_DIR / "period_scorecards.csv", index=False)
    pd.DataFrame(deltas).to_csv(OUTPUT_DIR / "restriction_deltas.csv", index=False)
    pd.DataFrame(ranked).to_csv(OUTPUT_DIR / "ranked_variants.csv", index=False)
    pd.DataFrame(diag["psr_dsr"]).to_csv(OUTPUT_DIR / "psr_dsr.csv", index=False)
    pd.DataFrame(diag["phase_one_accounts"]).to_csv(OUTPUT_DIR / "phase_one_accounts.csv", index=False)
    pd.DataFrame(diag["execution_stress"]).to_csv(OUTPUT_DIR / "execution_stress.csv", index=False)
    pd.DataFrame(diag["monte_carlo"]).to_json(OUTPUT_DIR / "monte_carlo.json", orient="records", indent=2)
    save_json(
        OUTPUT_DIR / "summary.json",
        {
            "generated_at": pd.Timestamp.now("UTC").isoformat(),
            "latest_data_date": latest_date,
            "variants": [
                {
                    "key": variant.key,
                    "base_key": variant.base_key,
                    "label": variant.label,
                    "direction_filter": variant.direction_filter,
                    "no_thursday": variant.no_thursday,
                    "noon_cutoff": variant.noon_cutoff,
                }
                for variant in variants
            ],
            "ranked": ranked,
            "finalists": finalists,
        },
    )
    write_report(latest_date=latest_date, ranked=ranked, deltas=deltas, diag=diag)

    print(f"\nOutput: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
