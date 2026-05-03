#!/usr/bin/env python3
"""Run CURRENT_STRATEGY_WORKFLOW discovery for stress-gated Hunter Classic ORB.

This script keeps the Hunter Classic mechanics fixed and searches only the
already-supported parity-engine knobs:

- 15m EMA length
- 15m EMA wrong-side tolerance
- optional EMA distance cap
- same-day re-entry policy
- same-bar win re-entry allowance

The final 2025+ holdout is reported but should not be used for workflow-valid
promotion. Last-1-year rankings are deliberately marked as tactical/hindsight
leaderboards, not promotion evidence.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from itertools import product
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from orb_backtest.validate.deflated_sharpe import (  # noqa: E402
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
)
from scripts.run_hunter_classic_orb_replication import (  # noqa: E402
    DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
    Candidate,
    SimTrade,
    build_candidates,
    can_take_candidate,
    load_1s,
    resample_5m,
    simulate_exit,
)


RISK_USD = 350.0
DEFAULT_EXCLUDED_REGIMES = ("bull_high_vol", "bear_high_vol", "bear_medium_vol")
HOLDOUT_START = pd.Timestamp("2025-01-01")
LAST_1Y_START = pd.Timestamp("2025-04-24")
FULL_START = pd.Timestamp("2016-04-25")
FULL_END = pd.Timestamp("2026-04-24")


@dataclass(frozen=True)
class VariantConfig:
    candidate_id: str
    ema15_length: int
    ema15_tolerance_points: float
    ema15_max_distance: float | None
    reentry_policy: str
    allow_same_bar_win_reentry: bool


def safe_name(value: float | None) -> str:
    if value is None:
        return "none"
    if float(value).is_integer():
        return str(int(value))
    return str(value).replace(".", "p")


def make_config(
    ema15_length: int,
    ema15_tolerance_points: float,
    ema15_max_distance: float | None,
    reentry_policy: str,
    allow_same_bar_win_reentry: bool,
) -> VariantConfig:
    reentry_short = {
        "legacy_one_reentry_after_loss": "legacy",
        "after_each_loss": "loss",
        "all_nonoverlap": "all",
    }[reentry_policy]
    candidate_id = (
        f"ema{ema15_length}_tol{safe_name(ema15_tolerance_points)}_"
        f"dist{safe_name(ema15_max_distance)}_re{reentry_short}_"
        f"samewin{int(allow_same_bar_win_reentry)}"
    )
    return VariantConfig(
        candidate_id=candidate_id,
        ema15_length=ema15_length,
        ema15_tolerance_points=ema15_tolerance_points,
        ema15_max_distance=ema15_max_distance,
        reentry_policy=reentry_policy,
        allow_same_bar_win_reentry=allow_same_bar_win_reentry,
    )


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def max_drawdown(values: list[float] | np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    arr = np.asarray(values, dtype=float)
    equity = np.cumsum(arr)
    peaks = np.maximum.accumulate(equity)
    return float(np.min(equity - peaks))


def profit_factor(values: list[float] | np.ndarray) -> float:
    arr = np.asarray(values, dtype=float)
    gross_profit = float(arr[arr > 0].sum())
    gross_loss = float(-arr[arr < 0].sum())
    if gross_loss <= 0:
        return float("inf") if gross_profit > 0 else float("nan")
    return gross_profit / gross_loss


def trade_r(trade: SimTrade) -> float:
    return float(trade.pnl_usd) / RISK_USD


def trade_date(trade: SimTrade) -> pd.Timestamp:
    return pd.Timestamp(trade.signal_dt).normalize()


def metric_packet(trades: list[SimTrade], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    selected = [trade for trade in trades if start <= trade_date(trade) <= end]
    values = np.asarray([trade_r(trade) for trade in selected], dtype=float)
    if len(values) == 0:
        return {
            "trades": 0,
            "net_r": 0.0,
            "wr": 0.0,
            "pf": float("nan"),
            "closed_dd_r": 0.0,
            "avg_r": 0.0,
            "return_dd": 0.0,
            "positive_years": 0,
            "negative_years": 0,
        }
    yearly: dict[int, float] = {}
    for trade, value in zip(selected, values):
        yearly.setdefault(trade_date(trade).year, 0.0)
        yearly[trade_date(trade).year] += float(value)
    positive_years = sum(v > 0 for v in yearly.values())
    negative_years = sum(v < 0 for v in yearly.values())
    dd = max_drawdown(values)
    net = float(values.sum())
    return_dd = net / abs(dd) if dd < 0 else float("inf")
    return {
        "trades": int(len(values)),
        "net_r": net,
        "wr": float((values > 0).mean() * 100.0),
        "pf": profit_factor(values),
        "closed_dd_r": dd,
        "avg_r": float(values.mean()),
        "return_dd": return_dd,
        "positive_years": int(positive_years),
        "negative_years": int(negative_years),
    }


def score_10y(metrics: dict[str, Any]) -> float:
    """Balanced full-history score: high net, controlled DD, no one-point peaks."""

    if metrics["trades"] < 500 or metrics["net_r"] <= 0:
        return -1e9
    pf_bonus = max(0.0, float(metrics["pf"]) - 1.0) * 25.0
    year_bonus = float(metrics["positive_years"]) * 2.0 - float(metrics["negative_years"]) * 4.0
    return float(metrics["net_r"]) - 0.70 * abs(float(metrics["closed_dd_r"])) + pf_bonus + year_bonus


def score_1y(metrics: dict[str, Any]) -> float:
    """Recent-performance score. This is intentionally not promotion-valid."""

    if metrics["trades"] < 40 or metrics["net_r"] <= 0:
        return -1e9
    pf_bonus = max(0.0, float(metrics["pf"]) - 1.0) * 15.0
    return float(metrics["net_r"]) - 0.35 * abs(float(metrics["closed_dd_r"])) + pf_bonus


def score_preholdout(metrics: dict[str, Any]) -> float:
    if metrics["trades"] < 350 or metrics["net_r"] <= 0:
        return -1e9
    pf_bonus = max(0.0, float(metrics["pf"]) - 1.0) * 20.0
    return float(metrics["net_r"]) - 0.80 * abs(float(metrics["closed_dd_r"])) + pf_bonus


def load_regime_lookup(path: Path) -> dict[str, str]:
    regime = pd.read_csv(path, parse_dates=["date"])
    return {
        row.date.strftime("%Y-%m-%d"): str(row.combined_regime)
        for row in regime.itertuples(index=False)
    }


def filter_stress_gate(
    trades: list[SimTrade],
    regime_lookup: dict[str, str],
    excluded_regimes: set[str],
) -> list[SimTrade]:
    kept = []
    for trade in trades:
        key = trade_date(trade).strftime("%Y-%m-%d")
        if regime_lookup.get(key) not in excluded_regimes:
            kept.append(trade)
    return kept


def select_trades(
    candidates_and_trades: list[tuple[Candidate, SimTrade | None]],
    config: VariantConfig,
) -> list[SimTrade]:
    by_day: dict[Any, list[tuple[Candidate, SimTrade | None]]] = {}
    for candidate, trade in candidates_and_trades:
        by_day.setdefault(candidate.entry_dt.date(), []).append((candidate, trade))

    selected: list[SimTrade] = []
    for day in sorted(by_day):
        day_trades: list[SimTrade] = []
        open_until: pd.Timestamp | None = None
        for candidate, trade in sorted(by_day[day], key=lambda item: item[0].entry_dt):
            if trade is None:
                continue
            if not can_take_candidate(
                candidate,
                day_trades,
                open_until,
                config.reentry_policy,
                allow_same_bar_win_reentry=config.allow_same_bar_win_reentry,
                same_bar_win_reentry_max_minutes=DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
            ):
                continue
            selected.append(trade)
            day_trades.append(trade)
            open_until = pd.Timestamp(trade.exit_dt)
    return selected


def trade_rows(candidate_id: str, trades: list[SimTrade]) -> list[dict[str, Any]]:
    rows = []
    for trade in trades:
        row = asdict(trade)
        row["candidate_id"] = candidate_id
        row["r"] = trade_r(trade)
        rows.append(row)
    return rows


def metric_row(config: VariantConfig, window: str, metrics: dict[str, Any], score: float) -> dict[str, Any]:
    return {
        **asdict(config),
        "window": window,
        **metrics,
        "score": score,
    }


def psr_dsr_packet(
    trades: list[SimTrade],
    all_trade_date_sets: list[set[str]],
    n_trials_raw: int,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> dict[str, Any]:
    selected = [trade for trade in trades if start <= trade_date(trade) <= end]
    r = np.asarray([trade_r(trade) for trade in selected], dtype=float)
    if len(r) < 3:
        return {"psr": None, "dsr": None, "n_trades": len(r)}
    effective = estimate_effective_trials(all_trade_date_sets)
    psr = compute_psr(r)
    dsr = compute_dsr(r, n_trials_raw=n_trials_raw, n_trials_effective=effective)
    return {
        "n_trades": len(r),
        "n_trials_raw": n_trials_raw,
        "n_trials_effective": effective,
        "psr": asdict(psr),
        "dsr": asdict(dsr),
    }


def find_local_neighbors(
    leaderboard: pd.DataFrame,
    selected: pd.Series,
    score_col: str,
    threshold: float = 0.80,
) -> dict[str, Any]:
    same_policy = leaderboard[
        (leaderboard["reentry_policy"] == selected["reentry_policy"])
        & (leaderboard["allow_same_bar_win_reentry"] == selected["allow_same_bar_win_reentry"])
    ].copy()
    lengths = sorted(leaderboard["ema15_length"].unique())
    tolerances = sorted(leaderboard["ema15_tolerance_points"].unique())
    distances = [None, 75.0, 100.0, 125.0, 150.0]

    def idx(seq: list[Any], value: Any) -> int:
        for i, item in enumerate(seq):
            if (pd.isna(value) and item is None) or item == value:
                return i
        return -999

    length_i = idx(lengths, selected["ema15_length"])
    tol_i = idx(tolerances, selected["ema15_tolerance_points"])
    dist_val = None if pd.isna(selected["ema15_max_distance"]) else float(selected["ema15_max_distance"])
    dist_i = idx(distances, dist_val)
    rows = []
    for row in same_policy.itertuples(index=False):
        row_dist = None if pd.isna(row.ema15_max_distance) else float(row.ema15_max_distance)
        if (
            abs(idx(lengths, row.ema15_length) - length_i) <= 1
            and abs(idx(tolerances, row.ema15_tolerance_points) - tol_i) <= 1
            and abs(idx(distances, row_dist) - dist_i) <= 1
        ):
            rows.append(row._asdict())
    neighbor_df = pd.DataFrame(rows)
    if neighbor_df.empty:
        return {"neighbors": 0, "robust_neighbors": 0, "median_score": None, "median_net_r": None}
    candidate_score = float(selected[score_col])
    robust = neighbor_df[neighbor_df[score_col] >= candidate_score * threshold]
    return {
        "neighbors": int(len(neighbor_df)),
        "robust_neighbors": int(len(robust)),
        "median_score": float(neighbor_df[score_col].median()),
        "median_net_r": float(neighbor_df["net_r"].median()),
    }


def format_r(value: float) -> str:
    return f"{value:+.1f}R"


def markdown_table(df: pd.DataFrame, limit: int = 5) -> str:
    rows = ["| Candidate | Trades | Net | WR | PF | DD | Score |", "|---|---:|---:|---:|---:|---:|---:|"]
    for row in df.head(limit).itertuples(index=False):
        rows.append(
            f"| `{row.candidate_id}` | {int(row.trades):,} | {format_r(row.net_r)} | "
            f"{row.wr:.1f}% | {row.pf:.2f} | {format_r(row.closed_dd_r)} | {row.score:.1f} |"
        )
    return "\n".join(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-1s", type=Path, default=Path("data/raw/NQ_1s.parquet"))
    parser.add_argument("--regime-calendar", type=Path, default=Path("data/results/hunter_classic_regime_gate_test_20260502/regime_calendar.csv"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/results/hunter_classic_stress_gate_strategy_workflow_20260502"))
    parser.add_argument("--start", default="2016-04-25")
    parser.add_argument("--end", default="2026-04-25")
    args = parser.parse_args()

    output_dir = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    regime_lookup = load_regime_lookup(args.regime_calendar)
    excluded_regimes = set(DEFAULT_EXCLUDED_REGIMES)

    df_1s = load_1s(args.data_1s, pd.Timestamp(args.start), pd.Timestamp(args.end))
    bars_5m = resample_5m(df_1s)

    ema_lengths = [10, 12, 14, 16, 20]
    tolerances = [0.0, 2.0, 5.0]
    distances: list[float | None] = [None, 75.0, 100.0, 125.0, 150.0]
    reentry_policies = ["legacy_one_reentry_after_loss", "after_each_loss", "all_nonoverlap"]
    same_win_flags = [False, True]

    all_configs = [
        make_config(length, tolerance, distance, reentry, same_win)
        for length, tolerance, distance, reentry, same_win in product(
            ema_lengths, tolerances, distances, reentry_policies, same_win_flags
        )
    ]

    cache: dict[int, list[tuple[Candidate, SimTrade | None]]] = {}
    metric_rows: list[dict[str, Any]] = []
    trade_sets_by_candidate: dict[str, list[SimTrade]] = {}
    trade_date_sets: list[set[str]] = []
    sim_counter = 0

    max_tolerance = max(tolerances)
    for length in ema_lengths:
        print(f"building candidate/exit cache length={length} tolerance={max_tolerance}", flush=True)
        candidates = build_candidates(
            bars_5m,
            ema15_close_bias_length=length,
            ema15_source="close",
            ema15_timing="confirmed_prev",
            ema15_tolerance_points=max_tolerance,
            ema15_max_distance=None,
        )
        cached: list[tuple[Candidate, SimTrade | None]] = []
        for idx, candidate in enumerate(candidates, start=1):
            trade = simulate_exit(candidate, df_1s, idx)
            cached.append((candidate, trade))
        cache[length] = cached

    for i, config in enumerate(all_configs, start=1):
        cached = cache[config.ema15_length]
        cached_for_config = []
        for candidate, trade in cached:
            if candidate.ema15_distance_points is None:
                continue
            if candidate.ema15_distance_points < -config.ema15_tolerance_points:
                continue
            if config.ema15_max_distance is not None and candidate.ema15_distance_points > config.ema15_max_distance:
                continue
            cached_for_config.append((candidate, trade))
        raw_trades = select_trades(cached_for_config, config)
        stress_trades = filter_stress_gate(raw_trades, regime_lookup, excluded_regimes)
        trade_sets_by_candidate[config.candidate_id] = stress_trades
        trade_date_sets.append({trade_date(trade).strftime("%Y-%m-%d") for trade in stress_trades})

        windows = {
            "pre_holdout": (FULL_START, HOLDOUT_START - pd.Timedelta(days=1), score_preholdout),
            "full_10y": (FULL_START, FULL_END, score_10y),
            "holdout_2025_plus": (HOLDOUT_START, FULL_END, score_1y),
            "last_1y": (LAST_1Y_START, FULL_END, score_1y),
        }
        for window_name, (start, end, scorer) in windows.items():
            metrics = metric_packet(stress_trades, start, end)
            metric_rows.append(metric_row(config, window_name, metrics, scorer(metrics)))

        if i % 50 == 0:
            print(f"scored {i}/{len(all_configs)} variants", flush=True)
        sim_counter += 1

    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(output_dir / "candidate_grid_metrics.csv", index=False)

    pre = metrics_df[metrics_df["window"] == "pre_holdout"].copy().sort_values("score", ascending=False)
    full = metrics_df[metrics_df["window"] == "full_10y"].copy().sort_values("score", ascending=False)
    last = metrics_df[metrics_df["window"] == "last_1y"].copy().sort_values("score", ascending=False)

    pre.to_csv(output_dir / "workflow_preholdout_ranked.csv", index=False)
    full.to_csv(output_dir / "top_10y_candidates.csv", index=False)
    last.to_csv(output_dir / "top_1y_candidates.csv", index=False)

    selected_ids = list(dict.fromkeys(
        full.head(5)["candidate_id"].tolist()
        + last.head(5)["candidate_id"].tolist()
        + pre.head(5)["candidate_id"].tolist()
    ))
    for candidate_id in selected_ids:
        write_csv(output_dir / "selected_trades" / f"{candidate_id}.csv", trade_rows(candidate_id, trade_sets_by_candidate[candidate_id]))

    diagnostics: dict[str, Any] = {
        "grid": {
            "raw_trials": len(all_configs),
            "ema_lengths": ema_lengths,
            "ema15_tolerance_points": tolerances,
            "ema15_max_distances": distances,
            "reentry_policies": reentry_policies,
            "same_bar_win_reentry": same_win_flags,
            "stress_gate_excludes": sorted(excluded_regimes),
            "holdout_start": HOLDOUT_START.strftime("%Y-%m-%d"),
        },
        "selected": {},
    }

    for label, ranked, score_col in [
        ("workflow_preholdout", pre, "score"),
        ("best_10y", full, "score"),
        ("best_1y", last, "score"),
    ]:
        top = ranked.head(3)
        diagnostics["selected"][label] = []
        for row in top.itertuples(index=False):
            row_dict = row._asdict()
            candidate_id = row_dict["candidate_id"]
            trades = trade_sets_by_candidate[candidate_id]
            start = FULL_START if label != "best_1y" else LAST_1Y_START
            end = FULL_END
            psr_dsr = psr_dsr_packet(trades, trade_date_sets, len(all_configs), start, end)
            plateau = find_local_neighbors(ranked, pd.Series(row_dict), score_col)
            diagnostics["selected"][label].append({
                "candidate": row_dict,
                "psr_dsr": psr_dsr,
                "local_plateau": plateau,
            })

    (output_dir / "selected_candidate_diagnostics.json").write_text(
        json.dumps(diagnostics, indent=2, default=str, allow_nan=True),
        encoding="utf-8",
    )

    summary_lines = [
        "# Hunter Classic Stress-Gated Strategy Workflow",
        "",
        f"Hold-out freeze: `{HOLDOUT_START.date()}` onward. Raw grid trials: `{len(all_configs)}`.",
        f"Stress gate excludes: `{', '.join(sorted(excluded_regimes))}`.",
        "",
        "## Workflow-Valid Pre-Holdout Ranking",
        "",
        markdown_table(pre),
        "",
        "These are the only candidates that can be treated as workflow-valid discovery outputs, because they are ranked before touching 2025+.",
        "",
        "## Best 10-Year Candidates",
        "",
        markdown_table(full),
        "",
        "This leaderboard uses the full 10-year window and is therefore useful for retrospective robustness, not pure discovery hygiene.",
        "",
        "## Best 1-Year Candidates",
        "",
        markdown_table(last),
        "",
        "This is explicitly a recent-regime/hindsight leaderboard. It should not be promoted without freezing and forward-validating.",
        "",
        "## Files",
        "",
        "- `candidate_grid_metrics.csv`",
        "- `workflow_preholdout_ranked.csv`",
        "- `top_10y_candidates.csv`",
        "- `top_1y_candidates.csv`",
        "- `selected_candidate_diagnostics.json`",
        "- `selected_trades/*.csv`",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "output_dir": str(output_dir),
        "variants": len(all_configs),
        "workflow_top": pre.head(3)["candidate_id"].tolist(),
        "top_10y": full.head(3)["candidate_id"].tolist(),
        "top_1y": last.head(3)["candidate_id"].tolist(),
    }, indent=2))


if __name__ == "__main__":
    main()
