#!/usr/bin/env python3
"""Phase-One Robust Pipeline — NQ NY reference_lsi 3m promoted candidates.

Evaluates the frozen 3m discovery shortlist for first-payout economics:
  1. both 13:00 far gap9 inv12 rr3.0 tp0.7
  2. both 12:00 near gap6 inv12 rr3.0 tp0.8
  3. both 13:00 near gap6 inv12 rr2.5 tp0.8

Workflow:
  0. Model freeze
  1. Structural viability on full pre-holdout
  2. Reconstruct the stitched discovery walk-forward OOS stream
  3. First-payout scorecard on the combined OOS stream
  4. First-payout holdout read on 2025-01-01+
  5. Cohort EV summary
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    PropFirmProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

DISCOVERY_RESULTS_PATH = (
    ROOT / "data" / "results" / "nq_ny_reference_lsi_discovery_3m" / "discovery_results.json"
)
OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_reference_lsi_3m_phase_one"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_3M_PHASE_ONE.md"

RESEARCH_START = "2016-01-01"
HOLDOUT_START = "2025-01-01"
WF_IS_MONTHS = 36
WF_OOS_MONTHS = 12
WF_STEP_MONTHS = 12


FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0,
    reset_fee=50.0,
    payout_split=0.80,
    payout_target_r=5.0,
    breach_limit_r=-4.0,
    daily_loss_limit_r=-2.0,
    min_trading_days=5,
    cohort_sizes=(10, 25, 50),
    block_size_days=20,
)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(rule, label="left", closed="left").agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        }
    )


def load_3m_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df_1m = load_5m_data("NQ_1m.parquet")
    df_1s = load_5m_data("NQ_1s.parquet")
    df_3m = _resample_ohlcv(df_1m, "3min")
    return df_3m, df_1m, df_1s


def build_session(entry_end: str) -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        entry_start="08:30",
        entry_end=entry_end,
        flat_start="14:00",
        flat_end="14:05",
        min_gap_atr_pct=5.0,
    )


def build_config(row: dict) -> StrategyConfig:
    return StrategyConfig(
        instrument=NQ,
        sessions=(build_session(row["entry_end"]),),
        strategy="reference_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter=row["direction_filter"],
        rr=float(row["rr"]),
        tp1_ratio=float(row["tp1_ratio"]),
        atr_length=10,
        ref_lsi_gap_lookback_bars=int(row["gap_lookback"]),
        ref_lsi_inversion_max_bars=int(row["inversion_max"]),
        ref_lsi_gap_entry_edge=row["gap_entry_edge"],
        name=row["label"],
    )


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def metrics_snapshot(metrics: dict) -> dict:
    keep = {
        "total_trades",
        "total_r",
        "calmar_ratio",
        "sharpe_ratio",
        "max_drawdown_r",
        "win_rate",
        "profit_factor",
        "avg_r",
    }
    snap: dict[str, float | int | None] = {}
    for key, value in metrics.items():
        if key not in keep:
            continue
        if isinstance(value, (int, float)):
            snap[key] = round(float(value), 4)
        else:
            snap[key] = value
    return snap


def print_metrics(label: str, metrics: dict) -> None:
    print(
        f"  {label}: {metrics.get('total_trades', 0)} trades | "
        f"Net R: {metrics.get('total_r', 0):+.1f} | "
        f"Calmar: {metrics.get('calmar_ratio', 0) or 0:.2f} | "
        f"Sharpe: {metrics.get('sharpe_ratio', 0) or 0:.2f} | "
        f"DD: {metrics.get('max_drawdown_r', 0):.2f}R | "
        f"WR: {metrics.get('win_rate', 0):.1%} | "
        f"PF: {metrics.get('profit_factor', 0) or 0:.2f}"
    )


def print_scorecard(label: str, scorecard: dict) -> None:
    print(f"\n  {label}")
    print(f"    Attempts: {scorecard.get('total_starts', scorecard.get('total_attempts', 0))}")
    payout_rate = scorecard.get("payout_rate", scorecard.get("first_payout_rate", 0.0))
    breach_rate = scorecard.get("breach_rate", 0.0)
    open_rate = scorecard.get("open_rate", 0.0)
    print(f"    Payout rate: {payout_rate:.1%} | Breach rate: {breach_rate:.1%} | Open: {open_rate:.1%}")
    ev = scorecard.get("ev_per_start_usd", scorecard.get("ev_per_attempt", 0.0))
    print(f"    EV per attempt: ${ev}")
    days = scorecard.get("average_days_to_payout", scorecard.get("median_days_to_payout"))
    if days:
        print(f"    Avg days to payout: {days:.0f}")


def trading_dates_between(
    df: pd.DataFrame,
    start: str,
    end_exclusive: str,
) -> list[str]:
    idx = df.index[(df.index >= start) & (df.index < end_exclusive)]
    if len(idx) == 0:
        return []
    dates = pd.Index(pd.to_datetime(idx.normalize()).unique()).sort_values()
    return [d.strftime("%Y-%m-%d") for d in dates]


def reconstruct_combined_oos_trades(
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    config: StrategyConfig,
) -> list:
    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    combined = []
    for window in windows:
        trades = run_backtest(
            df_base,
            config,
            start_date=window.oos_start,
            end_date=window.oos_end,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        combined.extend(trades)
    return combined


def load_promoted_candidates() -> list[dict]:
    payload = json.loads(DISCOVERY_RESULTS_PATH.read_text())
    promoted = payload["promotion"]["promoted"]
    roles = ["LEADER"] + ["CHALLENGER"] * max(0, len(promoted) - 1)
    rows = []
    for role, row in zip(roles, promoted, strict=False):
        rows.append(
            {
                "role": role,
                "label": row["label"],
                "direction_filter": row["direction_filter"],
                "entry_end": row["entry_end"],
                "gap_entry_edge": row["gap_entry_edge"],
                "gap_lookback": row["gap_lookback"],
                "inversion_max": row["inversion_max"],
                "rr": row["rr"],
                "tp1_ratio": row["tp1_ratio"],
                "discovery_row": row,
            }
        )
    return rows


def verdict_from_scorecards(prop_scorecard: dict, holdout_prop_scorecard: dict) -> str:
    payout_rate = float(prop_scorecard.get("first_payout_rate", 0.0))
    ev_per_attempt = float(prop_scorecard.get("ev_per_attempt", 0.0))
    holdout_payout_rate = float(holdout_prop_scorecard.get("first_payout_rate", 0.0))

    if payout_rate >= 0.60 and ev_per_attempt > 0.0 and holdout_payout_rate >= 0.40:
        return "STRONG"
    if payout_rate >= 0.40 and ev_per_attempt > 0.0:
        return "CONDITIONAL"
    return "NO-GO"


def write_report(payload: dict, holdout_end_inclusive: str) -> None:
    lines = [
        "# NQ NY Reference LSI 3m Phase One",
        "",
        f"- Frozen shortlist source: [NQ_NY_REFERENCE_LSI_DISCOVERY_3M.md]({(ROOT / 'learnings' / 'reports' / 'NQ_NY_REFERENCE_LSI_DISCOVERY_3M.md').as_posix()})",
        f"- Holdout opened once for phase one: `{HOLDOUT_START}` to `{holdout_end_inclusive}`.",
        f"- Phase 3 payout scorecards use the stitched discovery OOS trade stream (`2019-01-01` to `2024-12-31`).",
        "",
        "## Summary",
        "",
    ]

    summary_rows = payload["results"]
    for row in summary_rows:
        prop_sc = row["oos_prop_scorecard"]
        holdout_prop = row["holdout_prop_scorecard"]
        funded_sc = row["oos_funded_scorecard"]
        holdout_funded = row["holdout_funded_scorecard"]
        lines.append(
            f"- `{row['name']}` ({row['role']}): verdict `{row['verdict']}`, "
            f"OOS prop payout `{prop_sc['first_payout_rate']:.1%}`, "
            f"OOS funded payout `{funded_sc['payout_rate']:.1%}`, "
            f"holdout prop payout `{holdout_prop['first_payout_rate']:.1%}`, "
            f"holdout funded payout `{holdout_funded['payout_rate']:.1%}`"
        )

    lines.extend(["", "## Candidate Details", ""])

    for row in summary_rows:
        lines.extend(
            [
                f"### {row['name']}",
                "",
                f"- role: `{row['role']}`",
                f"- verdict: `{row['verdict']}`",
                f"- config: `{row['config_summary']}`",
                f"- discovery PSR / DSR: `{row['discovery_psr']}` / `{row['discovery_dsr']}`",
                f"- pre-holdout structural metrics: trades `{row['pre_holdout_metrics']['total_trades']}`, PF `{row['pre_holdout_metrics']['profit_factor']}`, avgR `{row['pre_holdout_metrics']['avg_r']}`, totalR `{row['pre_holdout_metrics']['total_r']}`",
                f"- stitched OOS metrics: trades `{row['oos_metrics']['total_trades']}`, PF `{row['oos_metrics']['profit_factor']}`, avgR `{row['oos_metrics']['avg_r']}`, totalR `{row['oos_metrics']['total_r']}`",
                f"- OOS prop scorecard: payout `{row['oos_prop_scorecard']['first_payout_rate']:.1%}`, breach `{row['oos_prop_scorecard']['breach_rate']:.1%}`, EV `${row['oos_prop_scorecard']['ev_per_attempt']}`",
                f"- OOS funded scorecard: payout `{row['oos_funded_scorecard']['payout_rate']:.1%}`, breach `{row['oos_funded_scorecard']['breach_rate']:.1%}`, EV `${row['oos_funded_scorecard']['ev_per_start_usd']}`",
                f"- holdout metrics: trades `{row['holdout_metrics']['total_trades']}`, PF `{row['holdout_metrics']['profit_factor']}`, avgR `{row['holdout_metrics']['avg_r']}`, totalR `{row['holdout_metrics']['total_r']}`",
                f"- holdout prop scorecard: payout `{row['holdout_prop_scorecard']['first_payout_rate']:.1%}`, breach `{row['holdout_prop_scorecard']['breach_rate']:.1%}`, EV `${row['holdout_prop_scorecard']['ev_per_attempt']}`",
                f"- holdout funded scorecard: payout `{row['holdout_funded_scorecard']['payout_rate']:.1%}`, breach `{row['holdout_funded_scorecard']['breach_rate']:.1%}`, EV `${row['holdout_funded_scorecard']['ev_per_start_usd']}`",
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    print("Phase-One Robust Pipeline — NQ NY reference_lsi 3m", flush=True)
    print("=" * 72, flush=True)

    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    promoted_rows = load_promoted_candidates()
    configs = [build_config(row) for row in promoted_rows]

    print("\n[Phase 0] Model freeze", flush=True)
    print(f"  Holdout start: {HOLDOUT_START}", flush=True)
    print(
        f"  Funded model: ${FUNDED_PROFILE.starting_balance_usd:,.0f} start, "
        f"${FUNDED_PROFILE.trailing_drawdown_usd:,.0f} trailing DD, "
        f"payout at ${FUNDED_PROFILE.first_payout_floor_usd:,.0f}",
        flush=True,
    )
    print(
        f"  Prop model: +{PROP_PROFILE.payout_target_r}R payout, "
        f"{PROP_PROFILE.breach_limit_r}R breach, {PROP_PROFILE.daily_loss_limit_r}R daily limit",
        flush=True,
    )

    print("\nLoading NQ 3m data (3m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s = load_3m_data()
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    print(f"  3m bars: {len(df_base):,}", flush=True)
    print(f"  1m bars: {len(df_1m):,}", flush=True)
    print(f"  1s bars: {len(df_1s):,}", flush=True)
    print(f"  Holdout end: {holdout_end_inclusive}", flush=True)

    print("\nBuilding maps + signal cache...", flush=True)
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs)

    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    oos_start = windows[0].oos_start
    oos_dates = trading_dates_between(df_base, oos_start, HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    payload: dict[str, object] = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "oos_stream_start": oos_start,
            "oos_stream_end_exclusive": HOLDOUT_START,
            "funded_profile": asdict(FUNDED_PROFILE),
            "prop_profile": asdict(PROP_PROFILE),
            "discovery_source": str(DISCOVERY_RESULTS_PATH),
        },
        "results": [],
    }

    for row, config in zip(promoted_rows, configs, strict=False):
        print(f"\n{'=' * 60}", flush=True)
        print(f"  CANDIDATE: {row['label']} ({row['role']})", flush=True)
        print(f"{'=' * 60}", flush=True)

        print("\n  [Phase 1] Structural viability", flush=True)
        trades_pre = run_backtest(
            df_base,
            config,
            end_date=HOLDOUT_START,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        pre_metrics = compute_metrics(trades_pre)
        print_metrics("Pre-holdout", pre_metrics)

        viable = (
            pre_metrics.get("total_trades", 0) >= 100
            and pre_metrics.get("profit_factor", 0) > 1.0
            and pre_metrics.get("avg_r", 0) > 0.0
        )
        print(f"  Viable: {viable}", flush=True)
        if not viable:
            payload["results"].append(
                {
                    "name": row["label"],
                    "role": row["role"],
                    "verdict": "NO-GO",
                    "reason": "structural viability failed",
                }
            )
            continue

        print("\n  [Phase 2] Reconstructed walk-forward OOS stream", flush=True)
        trades_oos = reconstruct_combined_oos_trades(
            df_base,
            df_1m,
            df_1s,
            maps,
            signal_cache,
            config,
        )
        oos_metrics = compute_metrics(trades_oos)
        print_metrics("Combined OOS", oos_metrics)
        print(
            f"  Discovery reference: WF avgR {row['discovery_row']['walkforward']['combined']['avg_r']} | "
            f"WF PF {row['discovery_row']['walkforward']['combined']['pf']}",
            flush=True,
        )

        print("\n  [Phase 3] First-payout scorecard (stitched OOS stream)", flush=True)
        oos_prop_outcomes = simulate_account_attempts(
            specialist_name=row["label"],
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
        print_scorecard("Prop model (R-based)", oos_prop_scorecard)

        oos_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=row["label"],
            trades=trades_oos,
            trading_dates=oos_dates,
            profile=FUNDED_PROFILE,
        )
        oos_funded_scorecard = build_funded_first_payout_scorecard(oos_funded_outcomes, FUNDED_PROFILE)
        oos_funded_forecast = build_funded_first_payout_forecast(oos_funded_outcomes)
        print_scorecard("Funded model (USD)", oos_funded_scorecard)

        print("\n  [Phase 4] Holdout confirmation", flush=True)
        trades_holdout = run_backtest(
            df_base,
            config,
            start_date=HOLDOUT_START,
            end_date=holdout_end_exclusive,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        holdout_metrics = compute_metrics(trades_holdout)
        print_metrics("Holdout", holdout_metrics)

        holdout_prop_outcomes = simulate_account_attempts(
            specialist_name=f"{row['label']}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
        print_scorecard("Holdout prop model", holdout_prop_scorecard)

        holdout_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=f"{row['label']}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=FUNDED_PROFILE,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(
            holdout_funded_outcomes,
            FUNDED_PROFILE,
        )
        holdout_funded_forecast = build_funded_first_payout_forecast(holdout_funded_outcomes)
        print_scorecard("Holdout funded model", holdout_funded_scorecard)

        print("\n  [Phase 5] Cohort EV", flush=True)
        for cohort_size in PROP_PROFILE.cohort_sizes:
            cohort_ev = float(oos_prop_scorecard.get("ev_per_attempt", 0.0)) * cohort_size
            funded_cohort_ev = float(oos_funded_scorecard.get("ev_per_start_usd", 0.0)) * cohort_size
            print(
                f"    Cohort {cohort_size}: prop EV ${cohort_ev:+.0f} | funded EV ${funded_cohort_ev:+.0f}",
                flush=True,
            )

        verdict = verdict_from_scorecards(oos_prop_scorecard, holdout_prop_scorecard)
        print(f"\n  VERDICT: {verdict}", flush=True)

        payload["results"].append(
            {
                "name": row["label"],
                "role": row["role"],
                "verdict": verdict,
                "config_summary": (
                    f"{row['direction_filter']} {row['entry_end']} {row['gap_entry_edge']} "
                    f"gap{row['gap_lookback']} inv{row['inversion_max']} rr{row['rr']} tp{row['tp1_ratio']}"
                ),
                "pre_holdout_metrics": metrics_snapshot(pre_metrics),
                "oos_metrics": metrics_snapshot(oos_metrics),
                "holdout_metrics": metrics_snapshot(holdout_metrics),
                "discovery_psr": row["discovery_row"]["psr"]["psr"],
                "discovery_dsr": row["discovery_row"]["dsr"]["dsr"],
                "discovery_walkforward": row["discovery_row"]["walkforward"]["combined"],
                "oos_prop_scorecard": oos_prop_scorecard,
                "oos_funded_scorecard": oos_funded_scorecard,
                "oos_funded_forecast": oos_funded_forecast,
                "holdout_prop_scorecard": holdout_prop_scorecard,
                "holdout_funded_scorecard": holdout_funded_scorecard,
                "holdout_funded_forecast": holdout_funded_forecast,
            }
        )

    print(f"\n{'=' * 72}", flush=True)
    print("PHASE-ONE SUMMARY — NQ NY reference_lsi 3m", flush=True)
    print(f"{'=' * 72}", flush=True)
    print(
        f"\n  {'Candidate':>38s} {'Verdict':>12s} {'OOS PR':>8s} {'HO PR':>8s} {'OOS EV':>10s}",
        flush=True,
    )
    print(f"  {'-' * 82}", flush=True)
    for row in payload["results"]:
        if "oos_prop_scorecard" not in row:
            print(f"  {row['name'][:38]:>38s} {row['verdict']:>12s} {'(skipped)':>28s}", flush=True)
            continue
        oos_prop = row["oos_prop_scorecard"]
        ho_prop = row["holdout_prop_scorecard"]
        print(
            f"  {row['name'][:38]:>38s} {row['verdict']:>12s} "
            f"{oos_prop['first_payout_rate']:7.1%} {ho_prop['first_payout_rate']:7.1%} "
            f"${oos_prop['ev_per_attempt']:>9.0f}",
            flush=True,
        )

    write_json(OUTPUT_DIR / "phase_one_results.json", payload)
    write_report(payload, holdout_end_inclusive)
    print(f"\nTotal time: {time.time() - t0:.0f}s", flush=True)
    print(f"Output: {OUTPUT_DIR}", flush=True)
    print(f"Report: {REPORT_PATH}", flush=True)


if __name__ == "__main__":
    main()
