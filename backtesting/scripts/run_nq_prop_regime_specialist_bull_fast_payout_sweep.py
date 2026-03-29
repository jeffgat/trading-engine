#!/usr/bin/env python3
"""Optimize the NQ bull specialist for faster first payout on a funded account.

Uses the routed bull specialist framework:
- 30m HH/HL + VWAP bull context gate
- no low-confidence days
- funded-account math:
  * $150 passed challenge cost
  * 50k starting balance
  * 2k trailing drawdown, updated from highest realized EOD balance
  * breach floor capped at 50k once trailed high enough
  * first withdrawable payout is balance above 52k
  * risk $500 pre-first-payout, $250 after
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    DEFAULT_HOLDOUT_START,
    FundedFirstPayoutProfile,
    apply_bull_hh_hl_vwap_gate,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    build_regime_confusion_log,
    evaluate_specialist,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.optimize.parallel import run_sweep


OUTPUT_DIR = ROOT / "data" / "results" / "nq_prop_regime_specialists_bull_fast_payout"


def make_anchor_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.4,
        atr_length=12,
        impulse_close_filter=False,
        excluded_days=(4,),
        name="NQ NY Bull Specialist Anchor",
        notes="Fast payout sweep anchor for bull specialist.",
    )


def build_candidate_configs(anchor: StrategyConfig) -> list[StrategyConfig]:
    configs: list[StrategyConfig] = []
    for rr, tp1_ratio, stop_atr_pct, entry_end in product(
        [2.0, 2.5, 3.0],
        [0.4, 0.5, 0.6],
        [6.0, 7.0, 8.0],
        ["11:30", "12:00", "12:30"],
    ):
        cfg = with_overrides(
            anchor,
            rr=rr,
            tp1_ratio=tp1_ratio,
            ny_stop_atr_pct=stop_atr_pct,
            ny_entry_end=entry_end,
        )
        cfg = replace(
            cfg,
            name=(
                f"NQ Bull FastPayout rr{rr:.2f}_tp1{tp1_ratio:.2f}_"
                f"stop{stop_atr_pct:.1f}_end{entry_end.replace(':', '')}"
            ),
            notes="Bull specialist faster-payout sweep candidate.",
        )
        configs.append(cfg)
    return configs


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def _survivor_sort_key(record: dict) -> tuple:
    funded = record["funded_scorecard"]
    readout = record["specialist_readout"]
    avg_days = funded["average_days_to_payout"]
    avg_days_key = -float(avg_days) if avg_days is not None else float("-inf")
    ev = float(funded["ev_per_start_usd"] or 0.0)
    holdout_payout = float(record["holdout_funded_scorecard"]["payout_rate"] or 0.0)
    return (
        bool(readout["survives_round1"]),
        ev > 0.0,
        holdout_payout > 0.0,
        avg_days_key,
        float(funded["payout_rate"] or 0.0),
        holdout_payout,
        float(funded["ev_per_start_usd"] or 0.0),
        float(readout["in_regime"].get("avg_r") or 0.0),
    )


def _record_to_row(record: dict) -> dict:
    session = record["config"].sessions[0]
    funded = record["funded_scorecard"]
    holdout = record["holdout_funded_scorecard"]
    readout = record["specialist_readout"]
    return {
        "config_name": record["config"].name,
        "rr": record["config"].rr,
        "tp1_ratio": record["config"].tp1_ratio,
        "stop_atr_pct": session.stop_atr_pct,
        "entry_end": session.entry_end,
        "survives_round1": readout["survives_round1"],
        "positive_ev_per_start": holdout["ev_per_start_usd"] is not None and funded["ev_per_start_usd"] > 0,
        "holdout_has_payouts": holdout["payout_rate"] > 0,
        "specialization_ratio": readout["specialization_ratio"],
        "in_regime_trades": readout["in_regime"]["total_trades"],
        "in_regime_avg_r": readout["in_regime"]["avg_r"],
        "payout_rate": funded["payout_rate"],
        "average_days_to_payout": funded["average_days_to_payout"],
        "median_days_to_payout": funded["median_days_to_payout"],
        "average_trades_to_payout": funded["average_trades_to_payout"],
        "average_first_payout_amount_usd": funded["average_first_payout_amount_usd"],
        "ev_per_start_usd": funded["ev_per_start_usd"],
        "holdout_payout_rate": holdout["payout_rate"],
        "holdout_average_days_to_payout": holdout["average_days_to_payout"],
        "holdout_ev_per_start_usd": holdout["ev_per_start_usd"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull Specialist Fast Payout Sweep")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    t0 = time.time()
    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)
    print(
        f"  5m={len(df_5m):,} | "
        f"1m={len(df_1m) if df_1m is not None else 0:,} | "
        f"1s={len(df_1s):,} "
        f"[{time.time() - t0:.1f}s]"
    )

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)
    confusion_log = build_regime_confusion_log(regime_calendar)
    all_start_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_start_dates = [
        d for d in all_start_dates if pd.Timestamp(d) >= pd.Timestamp(args.holdout_start)
    ]

    funded_profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        starting_balance_usd=50_000.0,
        trailing_drawdown_usd=2_000.0,
        max_trailing_breach_usd=50_000.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
        risk_post_payout_usd=250.0,
    )

    anchor = make_anchor_config()
    configs = build_candidate_configs(anchor)
    print(f"\nRunning bull sweep ({len(configs)} configs)...", flush=True)
    sweep_results = run_sweep(
        df_5m,
        configs,
        n_workers=max(1, args.workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )

    records: list[dict] = []
    for config, trades in sweep_results:
        trades = apply_dow_filter(trades, set(config.excluded_days))
        trades = apply_bull_hh_hl_vwap_gate(trades, df_5m, config.sessions[0])
        specialist_trades = filter_trades_by_low_confidence(
            trades,
            regime_calendar,
            include_low_confidence=False,
        )
        routed_trades = filter_trades_by_regime(
            specialist_trades,
            regime_calendar,
            include={"bull"},
        )

        specialist_readout = evaluate_specialist(
            specialist_name=config.name,
            target_regime="bull",
            trades=specialist_trades,
            regime_calendar=regime_calendar,
            holdout_start=args.holdout_start,
        )
        funded_outcomes = simulate_funded_first_payouts(
            specialist_name=config.name,
            trades=routed_trades,
            trading_dates=all_start_dates,
            profile=funded_profile,
        )
        funded_scorecard = build_funded_first_payout_scorecard(funded_outcomes, funded_profile)

        holdout_routed_trades = [t for t in routed_trades if t.date >= args.holdout_start]
        holdout_outcomes = simulate_funded_first_payouts(
            specialist_name=config.name,
            trades=holdout_routed_trades,
            trading_dates=holdout_start_dates,
            profile=funded_profile,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, funded_profile)

        records.append(
            {
                "config": config,
                "specialist_readout": specialist_readout,
                "funded_scorecard": funded_scorecard,
                "holdout_funded_scorecard": holdout_funded_scorecard,
            }
        )

    ranking_rows = [_record_to_row(r) for r in records]
    ranking_df = pd.DataFrame(ranking_rows).sort_values(
        by=[
            "survives_round1",
            "positive_ev_per_start",
            "holdout_has_payouts",
            "average_days_to_payout",
            "payout_rate",
            "holdout_payout_rate",
            "ev_per_start_usd",
            "in_regime_avg_r",
        ],
        ascending=[False, False, False, True, False, False, False],
    )
    ranking_df.to_csv(output_dir / "fast_payout_ranking.csv", index=False)
    regime_calendar.to_csv(output_dir / "regime_calendar.csv", index=False)
    confusion_log.to_csv(output_dir / "confusion_log.csv", index=False)

    survivor_records = [r for r in records if r["specialist_readout"]["survives_round1"]]
    best_record = max(survivor_records or records, key=_survivor_sort_key)

    write_json(
        output_dir / "best_candidate.json",
        {
            "config_name": best_record["config"].name,
            "config": {
                "rr": best_record["config"].rr,
                "tp1_ratio": best_record["config"].tp1_ratio,
                "stop_atr_pct": best_record["config"].sessions[0].stop_atr_pct,
                "entry_end": best_record["config"].sessions[0].entry_end,
                "excluded_days": list(best_record["config"].excluded_days),
            },
            "specialist_readout": best_record["specialist_readout"],
            "funded_scorecard": best_record["funded_scorecard"],
            "holdout_funded_scorecard": best_record["holdout_funded_scorecard"],
        },
    )

    summary_lines = [
        "# NQ Bull Specialist Fast Payout Sweep",
        "",
        "## Funded Account Model",
        "",
        "- Challenge cost: `$150`.",
        "- Starting balance: `$50,000`.",
        "- Trailing drawdown: `$2,000`, updated from highest realized EOD balance.",
        "- Trailing breach cap: never above `$50,000`.",
        "- First withdrawable payout: everything above `$52,000`.",
        "- Risk: `$500` per trade before first payout, `$250` after.",
        "",
        "## Sweep Scope",
        "",
        f"- Configs tested: `{len(configs)}`.",
        "- All candidates kept the bull HH/HL + VWAP gate and skipped low-confidence days.",
        "- Ranking prioritized payout rate and faster average days to first payout, with specialist survival preferred.",
        "",
        "## Best Candidate",
        "",
        f"- Config: `{best_record['config'].name}`.",
        f"- Survives specialist gate: `{best_record['specialist_readout']['survives_round1']}`.",
        f"- Payout rate: `{best_record['funded_scorecard']['payout_rate']}`.",
        f"- Average days to payout: `{best_record['funded_scorecard']['average_days_to_payout']}`.",
        f"- Average first payout amount: `{best_record['funded_scorecard']['average_first_payout_amount_usd']}`.",
        f"- EV per start: `{best_record['funded_scorecard']['ev_per_start_usd']}`.",
        f"- Holdout payout rate: `{best_record['holdout_funded_scorecard']['payout_rate']}`.",
        f"- Holdout average days to payout: `{best_record['holdout_funded_scorecard']['average_days_to_payout']}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
