#!/usr/bin/env python3
"""Frozen validation packet for NQ NY LSI/CISD candidates.

This is the promotion-discipline pass after the initial CISD discovery:

1. Re-run the frozen candidates.
2. Slice by period, year, month, weekday, time, direction, and confirmation type.
3. Stress execution assumptions for level-limit entries.
4. Run fixed-parameter walk-forward scorecards.
5. Run a tight fragility grid around the frozen values.
6. Run Monte Carlo/bootstrap and simple phase-one account simulations.

No new winner is selected by tuning inside this script. The fragility grid is
only used to judge whether each frozen candidate sits on a plateau.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import run_nq_ny_lsi_cisd_sequence as seq

sys.path.insert(0, str(seq.ROOT / "src"))

from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NAMES,
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


OUTPUT_DIR = seq.ROOT / "data" / "results" / "nq_ny_lsi_cisd_candidate_validation_20260503"
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_CISD_CANDIDATE_VALIDATION_20260503.md"
N_SEARCH_TRIALS = 242  # 149 initial sequence rows + 93 survivor-refinement rows.

PERIODS = {
    "full": ("2016-01-01", None),
    "discovery": (seq.DISCOVERY_START, seq.DISCOVERY_END),
    "validation": (seq.VALIDATION_START, seq.VALIDATION_END),
    "holdout": (seq.HOLDOUT_START, None),
    "post_2023": (seq.VALIDATION_START, None),
}


@dataclasses.dataclass(frozen=True)
class CandidateSpec:
    key: str
    label: str
    timeframe: str
    source: str
    strategy: str
    confirmation: str
    entry_mode: str
    stop_mode: str
    stop_atr_pct: float
    cisd_min_leg_bars: int
    cisd_min_leg_atr_pct: float


CANDIDATES = (
    CandidateSpec(
        key="add_1m_classic_atr10_b3_a7p5",
        label="1m additive classic swing, limit, ATR10 stop, CISD 3 bars / 7.5% ATR",
        timeframe="1m",
        source="classic_swing",
        strategy="lsi",
        confirmation="inversion_or_cisd",
        entry_mode="level_limit",
        stop_mode="atr_pct",
        stop_atr_pct=10.0,
        cisd_min_leg_bars=3,
        cisd_min_leg_atr_pct=7.5,
    ),
    CandidateSpec(
        key="pure_1m_classic_atr15_b2_a7p5",
        label="1m pure CISD classic swing, limit, ATR15 stop, CISD 2 bars / 7.5% ATR",
        timeframe="1m",
        source="classic_swing",
        strategy="lsi",
        confirmation="cisd",
        entry_mode="level_limit",
        stop_mode="atr_pct",
        stop_atr_pct=15.0,
        cisd_min_leg_bars=2,
        cisd_min_leg_atr_pct=7.5,
    ),
    CandidateSpec(
        key="add_3m_hourly_atr12p5_b3_a7p5",
        label="3m additive hourly sweep, limit, ATR12.5 stop, CISD 3 bars / 7.5% ATR",
        timeframe="3m",
        source="hourly_htf",
        strategy="htf_lsi",
        confirmation="inversion_or_cisd",
        entry_mode="level_limit",
        stop_mode="atr_pct",
        stop_atr_pct=12.5,
        cisd_min_leg_bars=3,
        cisd_min_leg_atr_pct=7.5,
    ),
)


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def cfg_for(spec: CandidateSpec, *, label: str | None = None, **overrides: Any) -> seq.StrategyConfig:
    params = dataclasses.asdict(spec)
    params.update(overrides)
    return seq.base_config(
        label=label or spec.key,
        timeframe=str(params["timeframe"]),
        strategy=str(params["strategy"]),
        source=str(params["source"]),
        confirmation=str(params["confirmation"]),
        entry_mode=str(params["entry_mode"]),
        stop_mode=str(params["stop_mode"]),
        stop_atr_pct=float(params["stop_atr_pct"]),
        cisd_min_leg_bars=int(params["cisd_min_leg_bars"]),
        cisd_min_leg_atr_pct=float(params["cisd_min_leg_atr_pct"]),
    )


def run_frozen_candidates(
    data: dict[str, pd.DataFrame],
    specs: tuple[CandidateSpec, ...],
) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    by_tf: dict[str, list[CandidateSpec]] = {}
    for spec in specs:
        by_tf.setdefault(spec.timeframe, []).append(spec)

    for timeframe, tf_specs in sorted(by_tf.items()):
        df = data[timeframe]
        df_1m = data["1m"] if timeframe != "1m" else None
        maps = build_maps(df, df_1m=df_1m)
        configs = [cfg_for(spec) for spec in tf_specs]
        cache = build_signal_cache(df, configs, signal_df_1m=data["1m"])
        for spec, cfg in zip(tf_specs, configs, strict=True):
            t0 = time.time()
            trades = run_backtest(
                df,
                cfg,
                df_1m=df_1m,
                signal_df_1m=data["1m"],
                _maps=maps,
                _signal_cache=cache,
            )
            out[spec.key] = trades
            filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            print(
                f"  frozen {spec.key:<36} {len(filled):>4} fills "
                f"[{time.time() - t0:.1f}s]",
                flush=True,
            )
    return out


def in_period(trade: Any, start: str | None, end: str | None) -> bool:
    return (start is None or trade.date >= start) and (end is None or trade.date < end)


def filled_trades(
    trades: list[Any],
    *,
    start: str | None = None,
    end: str | None = None,
) -> list[Any]:
    return [
        trade for trade in trades
        if trade.exit_type != EXIT_NO_FILL and in_period(trade, start, end)
    ]


def r_metrics(r_values: list[float] | np.ndarray) -> dict[str, float | int]:
    r = np.asarray(r_values, dtype=float)
    if len(r) == 0:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "total_r": 0.0,
            "avg_r": 0.0,
            "max_dd_r": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "calmar": 0.0,
            "max_consec_losses": 0,
        }
    wins = r > 0
    losses = r < 0
    gross_win = float(r[wins].sum()) if wins.any() else 0.0
    gross_loss = float(r[losses].sum()) if losses.any() else 0.0
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(dd.min()) if len(dd) else 0.0
    std = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    avg = float(r.mean())
    sharpe = avg / std * math.sqrt(252) if std > 0 else 0.0
    loss_runs = []
    current = 0
    for value in r:
        if value < 0:
            current += 1
        else:
            if current:
                loss_runs.append(current)
            current = 0
    if current:
        loss_runs.append(current)
    return {
        "trades": int(len(r)),
        "win_rate": float(wins.mean()),
        "total_r": float(equity[-1]),
        "avg_r": avg,
        "max_dd_r": max_dd,
        "profit_factor": abs(gross_win / gross_loss) if gross_loss else 0.0,
        "sharpe": sharpe,
        "calmar": float(equity[-1] / abs(max_dd)) if max_dd else 0.0,
        "max_consec_losses": int(max(loss_runs) if loss_runs else 0),
    }


def row_from_r(candidate: str, section: str, name: str, trades: list[Any], r_values: list[float]) -> dict[str, Any]:
    row = {
        "candidate": candidate,
        "section": section,
        "name": name,
    }
    row.update(r_metrics(r_values))
    if trades:
        row["long_trades"] = sum(1 for t in trades if t.direction == 1)
        row["short_trades"] = sum(1 for t in trades if t.direction == -1)
        row["cisd_trades"] = sum(1 for t in trades if t.lsi_confirmation_type == "cisd")
        row["inversion_trades"] = sum(1 for t in trades if t.lsi_confirmation_type == "inversion")
    else:
        row.update({"long_trades": 0, "short_trades": 0, "cisd_trades": 0, "inversion_trades": 0})
    return row


def scorecard_rows(trades_by_candidate: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate, trades in trades_by_candidate.items():
        for period, (start, end) in PERIODS.items():
            subset = filled_trades(trades, start=start, end=end)
            rows.append(row_from_r(candidate, "period", period, subset, [t.r_multiple for t in subset]))
    return rows


def split_rows(trades_by_candidate: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def add_group(candidate: str, section: str, groups: dict[str, list[Any]]) -> None:
        for name, group in sorted(groups.items()):
            rows.append(row_from_r(candidate, section, name, group, [t.r_multiple for t in group]))

    for candidate, trades in trades_by_candidate.items():
        filled = filled_trades(trades)
        by_year: dict[str, list[Any]] = {}
        by_month: dict[str, list[Any]] = {}
        by_dow: dict[str, list[Any]] = {}
        by_tod: dict[str, list[Any]] = {}
        by_direction = {"long": [], "short": []}
        by_confirmation: dict[str, list[Any]] = {}
        for trade in filled:
            by_year.setdefault(trade.date[:4], []).append(trade)
            by_month.setdefault(trade.date[:7], []).append(trade)
            dow_name = dt.date.fromisoformat(trade.date).strftime("%a")
            by_dow.setdefault(dow_name, []).append(trade)
            by_direction["long" if trade.direction == 1 else "short"].append(trade)
            by_confirmation.setdefault(trade.lsi_confirmation_type or "unknown", []).append(trade)
            bucket = "unknown"
            if trade.fill_time:
                ts = pd.Timestamp(trade.fill_time)
                minute = ts.hour * 60 + ts.minute
                if minute < 10 * 60 + 30:
                    bucket = "0930_1029"
                elif minute < 12 * 60:
                    bucket = "1030_1159"
                elif minute < 13 * 60 + 30:
                    bucket = "1200_1329"
                else:
                    bucket = "1330_close"
            by_tod.setdefault(bucket, []).append(trade)

        add_group(candidate, "year", by_year)
        add_group(candidate, "month", by_month)
        add_group(candidate, "dow", by_dow)
        add_group(candidate, "time_of_day", by_tod)
        add_group(candidate, "direction", by_direction)
        add_group(candidate, "confirmation", by_confirmation)
    return rows


def adjusted_for_slippage(trades: list[Any], ticks_per_side: float) -> list[float]:
    tick = seq.NQ.min_tick
    round_trip_points = 2.0 * ticks_per_side * tick
    return [
        trade.r_multiple - (round_trip_points / trade.risk_points if trade.risk_points > 0 else 0.0)
        for trade in trades
    ]


def adjusted_for_extra_commission(trades: list[Any], usd_per_side: float) -> list[float]:
    point_value = seq.NQ.point_value
    return [
        trade.r_multiple - ((2.0 * usd_per_side) / (trade.risk_points * point_value) if trade.risk_points > 0 else 0.0)
        for trade in trades
    ]


def bar_for_trade_fill(trade: Any, spec: CandidateSpec, data: dict[str, pd.DataFrame]) -> pd.Series | None:
    if not trade.fill_time:
        return None
    df = data["1m"] if spec.timeframe != "1m" else data[spec.timeframe]
    ts = pd.Timestamp(trade.fill_time)
    if ts in df.index:
        return df.loc[ts]
    pos = df.index.searchsorted(ts)
    if pos >= len(df.index):
        return None
    if abs((df.index[pos] - ts).total_seconds()) <= 60:
        return df.iloc[pos]
    return None


def penetration_filtered(
    trades: list[Any],
    spec: CandidateSpec,
    data: dict[str, pd.DataFrame],
    ticks: int,
) -> list[Any]:
    tick = seq.NQ.min_tick
    kept: list[Any] = []
    for trade in trades:
        bar = bar_for_trade_fill(trade, spec, data)
        if bar is None:
            continue
        if trade.direction == 1:
            if float(bar["low"]) <= trade.entry_price - ticks * tick:
                kept.append(trade)
        else:
            if float(bar["high"]) >= trade.entry_price + ticks * tick:
                kept.append(trade)
    return kept


def stress_rows(
    trades_by_candidate: dict[str, list[Any]],
    spec_by_key: dict[str, CandidateSpec],
    data: dict[str, pd.DataFrame],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    stress_periods = {
        "full": ("2016-01-01", None),
        "validation": (seq.VALIDATION_START, seq.VALIDATION_END),
        "holdout": (seq.HOLDOUT_START, None),
        "post_2023": (seq.VALIDATION_START, None),
    }
    for candidate, trades in trades_by_candidate.items():
        spec = spec_by_key[candidate]
        for period, (start, end) in stress_periods.items():
            subset = filled_trades(trades, start=start, end=end)
            stress_sets: list[tuple[str, list[Any], list[float]]] = [
                ("baseline", subset, [t.r_multiple for t in subset]),
                ("slip_0p5t_per_side", subset, adjusted_for_slippage(subset, 0.5)),
                ("slip_1t_per_side", subset, adjusted_for_slippage(subset, 1.0)),
                ("slip_2t_per_side", subset, adjusted_for_slippage(subset, 2.0)),
                ("extra_comm_1p25_side", subset, adjusted_for_extra_commission(subset, 1.25)),
                ("extra_comm_2p50_side", subset, adjusted_for_extra_commission(subset, 2.50)),
            ]
            penetration = penetration_filtered(subset, spec, data, ticks=1)
            delayed = [t for t in subset if t.fill_bar > t.signal_bar + 1]
            stress_sets.extend(
                [
                    ("require_1tick_penetration", penetration, [t.r_multiple for t in penetration]),
                    ("skip_first_eligible_parent_bar", delayed, [t.r_multiple for t in delayed]),
                    (
                        "penetration_plus_1t_slip",
                        penetration,
                        adjusted_for_slippage(penetration, 1.0),
                    ),
                ]
            )
            for stress_name, stress_trades, r_values in stress_sets:
                row = row_from_r(candidate, f"stress_{period}", stress_name, stress_trades, r_values)
                row["period"] = period
                rows.append(row)
    return rows


def walk_forward_rows(trades_by_candidate: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    latest_year = 2026
    for candidate, trades in trades_by_candidate.items():
        for year in range(2019, latest_year + 1):
            is_start = f"{year - 3}-01-01"
            is_end = f"{year}-01-01"
            oos_start = f"{year}-01-01"
            oos_end = None if year == latest_year else f"{year + 1}-01-01"
            is_trades = filled_trades(trades, start=is_start, end=is_end)
            oos_trades = filled_trades(trades, start=oos_start, end=oos_end)
            row = {
                "candidate": candidate,
                "fold": str(year),
                "is_start": is_start,
                "is_end": is_end,
                "oos_start": oos_start,
                "oos_end": oos_end or "",
            }
            for prefix, group in (("is", is_trades), ("oos", oos_trades)):
                metrics = r_metrics([t.r_multiple for t in group])
                row.update({f"{prefix}_{key}": value for key, value in metrics.items()})
            row["oos_pass"] = (
                row["oos_trades"] >= 10
                and row["oos_total_r"] > 0
                and row["oos_profit_factor"] > 1.0
            )
            rows.append(row)
    return rows


def fragility_specs() -> list[tuple[str, str, str, seq.StrategyConfig]]:
    specs: list[tuple[str, str, str, seq.StrategyConfig]] = []
    seen = set()
    for spec in CANDIDATES:
        bars_values = sorted({max(2, spec.cisd_min_leg_bars - 1), spec.cisd_min_leg_bars, spec.cisd_min_leg_bars + 1})
        cisd_atr_values = sorted({max(0.0, spec.cisd_min_leg_atr_pct - 2.5), spec.cisd_min_leg_atr_pct, spec.cisd_min_leg_atr_pct + 2.5})
        if spec.stop_mode == "atr_pct":
            stop_values = sorted({max(5.0, spec.stop_atr_pct - 2.5), spec.stop_atr_pct, spec.stop_atr_pct + 2.5})
        else:
            stop_values = [spec.stop_atr_pct]
        for bars in bars_values:
            for cisd_atr in cisd_atr_values:
                for stop_atr in stop_values:
                    label = (
                        f"{spec.timeframe}|fragility|{spec.key}|bars{bars}|"
                        f"cisd_atr{cisd_atr:g}|stop{stop_atr:g}"
                    )
                    key = (spec.key, bars, cisd_atr, stop_atr)
                    if key in seen:
                        continue
                    seen.add(key)
                    cfg = cfg_for(
                        spec,
                        label=label,
                        cisd_min_leg_bars=bars,
                        cisd_min_leg_atr_pct=cisd_atr,
                        stop_atr_pct=stop_atr,
                    )
                    specs.append((label, spec.source, spec.strategy, cfg))
    return specs


def summarize_fragility(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    df = pd.DataFrame(rows)
    if df.empty:
        return out
    for spec in CANDIDATES:
        pool = df[df["label"].str.contains(spec.key, regex=False)].copy()
        if pool.empty:
            continue
        pool["bars"] = pool["label"].str.extract(r"\|bars(\d+)\|").astype(int)
        pool = pool[pool["bars"] >= 2]
        if pool.empty:
            continue
        robust = pool[
            (pool["validation_trades"] >= 30)
            & (pool["holdout_trades"] >= 20)
            & (pool["validation_profit_factor"] > 1.0)
            & (pool["holdout_profit_factor"] > 1.0)
        ]
        out.append(
            {
                "candidate": spec.key,
                "neighbors": int(len(pool)),
                "robust_neighbors": int(len(robust)),
                "robust_neighbor_pct": float(len(robust) / len(pool)) if len(pool) else 0.0,
                "median_validation_pf": float(pool["validation_profit_factor"].median()),
                "median_holdout_pf": float(pool["holdout_profit_factor"].median()),
                "median_validation_calmar": float(pool["validation_calmar"].median()),
                "median_holdout_calmar": float(pool["holdout_calmar"].median()),
                "best_neighbor_label": str(pool.sort_values(["holdout_calmar", "validation_calmar"], ascending=False).iloc[0]["label"]),
            }
        )
    return out


def monte_carlo_rows(trades_by_candidate: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate, trades in trades_by_candidate.items():
        for period, (start, end) in {
            "full": ("2016-01-01", None),
            "post_2023": (seq.VALIDATION_START, None),
            "holdout": (seq.HOLDOUT_START, None),
        }.items():
            subset = filled_trades(trades, start=start, end=end)
            if len(subset) < 10:
                continue
            for method in ("bootstrap", "block_bootstrap", "shuffle"):
                result = run_monte_carlo(
                    subset,
                    MonteCarloConfig(n_simulations=2000, method=method, seed=42, block_length=None),
                    ruin_threshold=-10.0,
                )
                row = {
                    "candidate": candidate,
                    "period": period,
                    **mc_result_to_dict(result),
                }
                rows.append(row)
    return rows


def psr_dsr_rows(trades_by_candidate: dict[str, list[Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate, trades in trades_by_candidate.items():
        for period, (start, end) in {
            "full": ("2016-01-01", None),
            "post_2023": (seq.VALIDATION_START, None),
            "holdout": (seq.HOLDOUT_START, None),
        }.items():
            subset = filled_trades(trades, start=start, end=end)
            if len(subset) < 10:
                continue
            packet = annotate_trades(
                np.asarray([t.r_multiple for t in subset], dtype=float),
                n_trials_raw=N_SEARCH_TRIALS,
            )
            rows.append(
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
    return rows


def simulate_staggered_accounts(
    trades: list[Any],
    *,
    start: str,
    end: str,
    cycle_days: int,
    payout_r: float,
    breach_r: float,
) -> dict[str, Any]:
    filled = sorted(
        [
            {"date": dt.date.fromisoformat(t.date), "r": t.r_multiple}
            for t in trades
            if t.exit_type != EXIT_NO_FILL and start <= t.date < end
        ],
        key=lambda row: row["date"],
    )
    if not filled:
        return {
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "ev_r": 0.0,
        }

    d_start = dt.date.fromisoformat(start)
    d_end = dt.date.fromisoformat(end)
    account_starts = []
    current = d_start
    while current <= d_end:
        account_starts.append(current)
        current += dt.timedelta(days=cycle_days)

    results = []
    for account_start in account_starts:
        cum_r = 0.0
        outcome = "open"
        outcome_date = account_start
        trades_taken = 0
        for trade in filled:
            if trade["date"] < account_start:
                continue
            cum_r += trade["r"]
            trades_taken += 1
            if cum_r >= payout_r:
                outcome = "payout"
                outcome_date = trade["date"]
                break
            if cum_r <= breach_r:
                outcome = "breach"
                outcome_date = trade["date"]
                break
            outcome_date = trade["date"]
        results.append(
            {
                "outcome": outcome,
                "final_r": cum_r,
                "trades_taken": trades_taken,
                "calendar_days": (outcome_date - account_start).days + 1,
            }
        )

    payouts = [row for row in results if row["outcome"] == "payout"]
    breaches = [row for row in results if row["outcome"] == "breach"]
    opens = [row for row in results if row["outcome"] == "open"]
    capped = [
        payout_r if row["outcome"] == "payout"
        else breach_r if row["outcome"] == "breach"
        else row["final_r"]
        for row in results
    ]
    total = len(results)
    return {
        "accounts": total,
        "payouts": len(payouts),
        "breaches": len(breaches),
        "open": len(opens),
        "payout_rate": len(payouts) / total if total else 0.0,
        "breach_rate": len(breaches) / total if total else 0.0,
        "ev_r": float(np.mean(capped)) if capped else 0.0,
        "avg_days_payout": float(np.mean([row["calendar_days"] for row in payouts])) if payouts else 0.0,
        "avg_days_breach": float(np.mean([row["calendar_days"] for row in breaches])) if breaches else 0.0,
        "avg_trades_payout": float(np.mean([row["trades_taken"] for row in payouts])) if payouts else 0.0,
    }


def prop_rows(trades_by_candidate: dict[str, list[Any]], latest_date: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    end = (dt.date.fromisoformat(latest_date) + dt.timedelta(days=1)).isoformat()
    windows = {
        "full": ("2016-01-01", end),
        "post_2023": (seq.VALIDATION_START, end),
        "holdout": (seq.HOLDOUT_START, end),
    }
    profiles = {
        "normal_5payout_4breach": (5.0, -4.0),
        "aggressive_2p5payout_2breach": (2.5, -2.0),
    }
    for candidate, trades in trades_by_candidate.items():
        for window, (start, stop) in windows.items():
            for profile, (payout, breach) in profiles.items():
                result = simulate_staggered_accounts(
                    trades,
                    start=start,
                    end=stop,
                    cycle_days=14,
                    payout_r=payout,
                    breach_r=breach,
                )
                rows.append(
                    {
                        "candidate": candidate,
                        "window": window,
                        "profile": profile,
                        "payout_r": payout,
                        "breach_r": breach,
                        **result,
                    }
                )
    return rows


def write_report(
    *,
    latest_date: str,
    scorecards: list[dict[str, Any]],
    wf_rows: list[dict[str, Any]],
    stress: list[dict[str, Any]],
    fragility_summary: list[dict[str, Any]],
    mc_rows_: list[dict[str, Any]],
    prop: list[dict[str, Any]],
    psr_dsr: list[dict[str, Any]],
) -> None:
    def fmt_metric(row: dict[str, Any]) -> str:
        return (
            f"{int(row['trades'])} tr, PF {row['profit_factor']:.2f}, "
            f"R {row['total_r']:.1f}, DD {row['max_dd_r']:.1f}, Calmar {row['calmar']:.2f}"
        )

    score_df = pd.DataFrame(scorecards)
    stress_df = pd.DataFrame(stress)
    wf_df = pd.DataFrame(wf_rows)
    prop_df = pd.DataFrame(prop)
    mc_df = pd.DataFrame(mc_rows_)
    psr_df = pd.DataFrame(psr_dsr)

    lines = [
        "# NQ NY LSI CISD Candidate Validation",
        "",
        f"- Latest data date: `{latest_date}`.",
        "- Candidates are frozen from the CISD survivor-refinement sequence.",
        "- Targets remain fixed at `rr=2.0`, `tp1_ratio=0.5`.",
        "- Search-trial count used for DSR: `242`.",
        "",
        "## Frozen Candidates",
        "",
    ]
    for spec in CANDIDATES:
        lines.append(f"- `{spec.key}`: {spec.label}")

    lines.extend(["", "## Period Scorecard", ""])
    for spec in CANDIDATES:
        lines.append(f"### {spec.key}")
        for period in ("discovery", "validation", "holdout", "post_2023", "full"):
            row = score_df[(score_df["candidate"] == spec.key) & (score_df["name"] == period)].iloc[0].to_dict()
            lines.append(f"- `{period}`: {fmt_metric(row)}")
        lines.append("")

    lines.extend(["## Walk-Forward", ""])
    for spec in CANDIDATES:
        pool = wf_df[wf_df["candidate"] == spec.key]
        valid = pool[pool["oos_trades"] >= 10]
        pass_rate = float(valid["oos_pass"].mean()) if len(valid) else 0.0
        lines.append(
            f"- `{spec.key}`: {int(valid['oos_pass'].sum())}/{len(valid)} OOS folds passed, "
            f"median OOS PF `{valid['oos_profit_factor'].median():.2f}`, "
            f"median OOS Calmar `{valid['oos_calmar'].median():.2f}`."
        )
        if pass_rate < 0.5:
            lines.append("  - Warning: fold stability is weak.")

    lines.extend(["", "## Execution Stress", ""])
    for spec in CANDIDATES:
        holdout = stress_df[
            (stress_df["candidate"] == spec.key)
            & (stress_df["period"] == "holdout")
            & (stress_df["section"] == "stress_holdout")
        ]
        lines.append(f"### {spec.key} Holdout")
        for name in (
            "baseline",
            "slip_1t_per_side",
            "slip_2t_per_side",
            "require_1tick_penetration",
            "skip_first_eligible_parent_bar",
            "penetration_plus_1t_slip",
        ):
            row = holdout[holdout["name"] == name]
            if not row.empty:
                lines.append(f"- `{name}`: {fmt_metric(row.iloc[0].to_dict())}")
        lines.append("")

    lines.extend(["## Fragility", ""])
    for row in fragility_summary:
        lines.append(
            f"- `{row['candidate']}`: `{row['robust_neighbors']}/{row['neighbors']}` "
            f"neighbors robust (`{row['robust_neighbor_pct']:.1%}`); "
            f"median validation PF `{row['median_validation_pf']:.2f}`, "
            f"median holdout PF `{row['median_holdout_pf']:.2f}`."
        )

    lines.extend(["", "## Monte Carlo", ""])
    for spec in CANDIDATES:
        pool = mc_df[
            (mc_df["candidate"] == spec.key)
            & (mc_df["period"] == "post_2023")
            & (mc_df["method"] == "block_bootstrap")
        ]
        if not pool.empty:
            row = pool.iloc[0]
            lines.append(
                f"- `{spec.key}` post-2023 block bootstrap: final R p5 "
                f"`{row['final_pnl_percentiles']['p5']}`, max DD p5 "
                f"`{row['max_dd_percentiles']['p5']}`, ruin(-10R) "
                f"`{row['ruin_probability']:.1%}`."
            )

    lines.extend(["", "## PSR / DSR", ""])
    for spec in CANDIDATES:
        pool = psr_df[(psr_df["candidate"] == spec.key) & (psr_df["period"] == "post_2023")]
        if not pool.empty:
            row = pool.iloc[0]
            lines.append(
                f"- `{spec.key}` post-2023: PSR `{row['psr']:.4f}` "
                f"({row['psr_interpretation']}), DSR `{row['dsr']:.4f}` "
                f"({row['dsr_interpretation']})."
            )

    lines.extend(["", "## Phase-One Style Accounts", ""])
    for spec in CANDIDATES:
        pool = prop_df[
            (prop_df["candidate"] == spec.key)
            & (prop_df["window"] == "post_2023")
            & (prop_df["profile"] == "normal_5payout_4breach")
        ]
        if not pool.empty:
            row = pool.iloc[0]
            lines.append(
                f"- `{spec.key}` post-2023 normal profile: payout "
                f"`{row['payout_rate']:.1%}`, breach `{row['breach_rate']:.1%}`, "
                f"EV `{row['ev_r']:.2f}R` per 14-day staggered account."
            )

    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI/CISD frozen-candidate validation", flush=True)
    print("=" * 88, flush=True)

    data = seq.load_timeframes()
    latest_date = max(df.index.max() for df in data.values()).date().isoformat()
    print(f"Loaded cached data through {latest_date}", flush=True)

    spec_by_key = {spec.key: spec for spec in CANDIDATES}
    trades_by_candidate = run_frozen_candidates(data, CANDIDATES)

    scorecards = scorecard_rows(trades_by_candidate)
    splits = split_rows(trades_by_candidate)
    stress = stress_rows(trades_by_candidate, spec_by_key, data)
    wf = walk_forward_rows(trades_by_candidate)
    mc = monte_carlo_rows(trades_by_candidate)
    psr = psr_dsr_rows(trades_by_candidate)
    prop = prop_rows(trades_by_candidate, latest_date)

    print("\nRunning fragility grid...", flush=True)
    fragility = seq.run_stage(stage="fragility", data=data, specs=fragility_specs())
    fragility_summary = summarize_fragility(fragility)

    pd.DataFrame(scorecards).to_csv(OUTPUT_DIR / "frozen_scorecards.csv", index=False)
    pd.DataFrame(splits).to_csv(OUTPUT_DIR / "split_scorecards.csv", index=False)
    pd.DataFrame(stress).to_csv(OUTPUT_DIR / "execution_stress.csv", index=False)
    pd.DataFrame(wf).to_csv(OUTPUT_DIR / "walk_forward.csv", index=False)
    pd.DataFrame(fragility).to_csv(OUTPUT_DIR / "fragility_rows.csv", index=False)
    pd.DataFrame(fragility_summary).to_csv(OUTPUT_DIR / "fragility_summary.csv", index=False)
    pd.DataFrame(mc).to_json(OUTPUT_DIR / "monte_carlo.json", orient="records", indent=2)
    pd.DataFrame(psr).to_csv(OUTPUT_DIR / "psr_dsr.csv", index=False)
    pd.DataFrame(prop).to_csv(OUTPUT_DIR / "phase_one_accounts.csv", index=False)

    summary = {
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "latest_data_date": latest_date,
        "candidates": [dataclasses.asdict(spec) for spec in CANDIDATES],
        "scorecards": scorecards,
        "fragility_summary": fragility_summary,
        "psr_dsr": psr,
    }
    save_json(OUTPUT_DIR / "summary.json", summary)
    write_report(
        latest_date=latest_date,
        scorecards=scorecards,
        wf_rows=wf,
        stress=stress,
        fragility_summary=fragility_summary,
        mc_rows_=mc,
        prop=prop,
        psr_dsr=psr,
    )

    print("\nTop period rows:", flush=True)
    for row in scorecards:
        if row["name"] in {"validation", "holdout", "post_2023"}:
            print(
                f"  {row['candidate']:<36} {row['name']:<10} "
                f"{row['trades']:>3}tr PF {row['profit_factor']:.2f} "
                f"R {row['total_r']:.1f} DD {row['max_dd_r']:.1f} Calmar {row['calmar']:.2f}",
                flush=True,
            )
    print("\nFragility:", flush=True)
    for row in fragility_summary:
        print(
            f"  {row['candidate']:<36} {row['robust_neighbors']:>2}/{row['neighbors']} "
            f"robust neighbors ({row['robust_neighbor_pct']:.1%})",
            flush=True,
        )

    print(f"\nOutput: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)
    print(f"Total time: {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
