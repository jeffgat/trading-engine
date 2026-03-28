#!/usr/bin/env python3
"""Run round-1 NQ prop regime-specialist research.

Outputs a research package under backtesting/data/results/ by default:
- regime calendar + confusion log
- yearly regime sanity summary
- strategy mapping table
- specialist readouts
- account outcomes + prop scorecards
- one-page markdown summary and paper-trade shortlist
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, replace
from itertools import product
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    DEFAULT_HOLDOUT_START,
    PropFirmProfile,
    apply_bull_hh_hl_vwap_gate,
    build_nq_ny_regime_calendar,
    build_prop_scorecard,
    build_regime_confusion_log,
    build_regime_strategy_mapping,
    build_yearly_regime_summary,
    evaluate_specialist,
    simulate_account_attempts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig, ib_config
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.optimize.parallel_vwap import run_vwap_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides


OUTPUT_DIR = ROOT / "data" / "results" / "nq_prop_regime_specialists_round1"


def make_nq_ny_long_r11_config() -> StrategyConfig:
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
        name="NQ NY Cont Long R11 Final",
        notes="Round-1 bull specialist baseline.",
    )


def make_nq_ny_short_v2_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:55",
        entry_start="09:55",
        entry_end="11:00",
        flat_start="11:00",
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=0.0,
        stop_orb_pct=17.0,
        min_gap_orb_pct=5.0,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )
    return StrategyConfig(
        sessions=(session,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=2.0,
        tp1_ratio=0.3,
        atr_length=14,
        impulse_close_filter=False,
        excluded_days=(0,),
        name="NQ NY Short v2",
        notes="Round-1 bear specialist baseline.",
    )


def build_vwap_candidates():
    base = default_vwap_config(NQ)
    configs = []
    for deviation, rr, tp1, stop_atr, rejection_mode, direction in product(
        [20.0, 30.0, 40.0],
        [1.5, 2.0, 2.5],
        [0.3, 0.5],
        [0.0, 10.0],
        ["close", "pinbar"],
        ["both", "long", "short"],
    ):
        kwargs = {
            "rr": rr,
            "tp1_ratio": tp1,
            "direction_filter": direction,
            "ny_deviation_atr_pct": deviation,
            "ny_stop_atr_pct": stop_atr,
            "ny_rejection_mode": rejection_mode,
        }
        if rejection_mode == "pinbar":
            kwargs["ny_min_wick_atr_pct"] = 10.0
            kwargs["ny_max_body_atr_pct"] = 5.0
        cfg = with_vwap_overrides(base, **kwargs)
        cfg = replace(
            cfg,
            name=(
                f"NQ NY VWAP dev{deviation:.0f}_rr{rr:.2f}_tp1{tp1:.2f}_"
                f"stop{stop_atr:.0f}_{rejection_mode}_{direction}"
            ),
            notes="Round-1 sideways specialist bounded sweep.",
        )
        configs.append(cfg)
    return configs


def choose_best_vwap_candidate(
    df_5m: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    start_date: str,
    end_date: str | None,
    n_workers: int,
) -> tuple[object, list, dict]:
    configs = build_vwap_candidates()
    print(f"\nRunning bounded VWAP sweep ({len(configs)} configs)...", flush=True)
    t0 = time.time()
    results = run_vwap_sweep(
        df_5m,
        configs,
        n_workers=n_workers,
        start_date=start_date,
        end_date=end_date,
        df_1m=df_1m,
    )
    print(f"  VWAP sweep completed in {time.time() - t0:.1f}s")

    ranked = []
    for config, trades in results:
        metrics = compute_metrics(trades)
        ranked.append(
            {
                "config": config,
                "trades": trades,
                "metrics": metrics,
            }
        )

    viable = [
        item
        for item in ranked
        if item["metrics"]["avg_r"] > 0 and item["metrics"]["total_trades"] >= 150
    ]
    if not viable:
        best = max(ranked, key=lambda item: (item["metrics"]["avg_r"], item["metrics"]["calmar_ratio"]))
    else:
        best = max(viable, key=lambda item: (item["metrics"]["calmar_ratio"], item["metrics"]["total_r"]))
    return best["config"], best["trades"], best["metrics"]


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    parser.add_argument("--vwap-workers", type=int, default=4)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Prop Regime Specialists — Round 1")
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
        f"1s={len(df_1s) if df_1s is not None else 0:,} "
        f"[{time.time() - t0:.1f}s]"
    )

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)
    confusion_log = build_regime_confusion_log(regime_calendar)
    yearly_summary = build_yearly_regime_summary(regime_calendar)

    trading_dates = trading_dates_from_calendar(regime_calendar)
    print(
        f"  Calendar rows={len(regime_calendar):,} | "
        f"tradable rows={len(trading_dates):,} | "
        f"low-confidence={len(confusion_log):,}"
    )

    print("\nRunning bull baseline...", flush=True)
    bull_config = make_nq_ny_long_r11_config()
    bull_trades = run_backtest(
        df_5m,
        bull_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    bull_trades = apply_dow_filter(bull_trades, set(bull_config.excluded_days))
    bull_gated_trades = apply_bull_hh_hl_vwap_gate(bull_trades, df_5m, bull_config.sessions[0])

    print("\nRunning bear baseline...", flush=True)
    bear_config = make_nq_ny_short_v2_config()
    bear_trades = run_backtest(
        df_5m,
        bear_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    bear_trades = apply_dow_filter(bear_trades, set(bear_config.excluded_days))

    best_vwap_config, best_vwap_trades, best_vwap_metrics = choose_best_vwap_candidate(
        df_5m,
        df_1m,
        args.start,
        args.end,
        max(1, args.vwap_workers),
    )

    sideways_name = "nq_ny_sideways_vwap"
    sideways_source = "vwap_reversion"
    sideways_trades = best_vwap_trades
    sideways_risk = best_vwap_config.risk_usd
    if best_vwap_metrics["avg_r"] <= 0 or best_vwap_metrics["total_trades"] < 150:
        print("\nVWAP sweep did not clear the fallback bar; using IB mean-reversion instead.", flush=True)
        ib_base = ib_config(NQ)
        ib_cfg = replace(
            ib_base,
            risk_usd=5000.0,
            use_bar_magnifier=True,
            name="NQ NY IB Mean Reversion Fallback",
            notes="Fallback sideways specialist because VWAP baseline was not viable.",
        )
        sideways_trades = run_backtest(
            df_5m,
            ib_cfg,
            start_date=args.start,
            end_date=args.end,
            df_1m=df_1m,
            df_1s=df_1s,
        )
        best_vwap_config = ib_cfg
        sideways_source = "ib_fallback"
        sideways_risk = ib_cfg.risk_usd

    profile = PropFirmProfile()

    specialist_sets = [
        ("nq_ny_bull_long_r11", "bull", bull_trades, bull_config.risk_usd),
        ("nq_ny_bull_long_r11_hh_hl_vwap", "bull", bull_gated_trades, bull_config.risk_usd),
        ("nq_ny_bear_short_v2", "bear", bear_trades, bear_config.risk_usd),
        (sideways_name, "sideways", sideways_trades, sideways_risk),
    ]

    specialist_readouts = {}
    scorecards = {}
    all_outcomes = []
    ranking_rows = []

    for specialist_name, target_regime, trades, risk_per_r_usd in specialist_sets:
        print(f"\nEvaluating {specialist_name}...", flush=True)
        readout = evaluate_specialist(
            specialist_name=specialist_name,
            target_regime=target_regime,
            trades=trades,
            regime_calendar=regime_calendar,
            holdout_start=args.holdout_start,
        )
        outcomes = simulate_account_attempts(
            specialist_name=specialist_name,
            trades=trades,
            trading_dates=trading_dates,
            profile=profile,
            risk_per_r_usd=risk_per_r_usd,
        )
        scorecard = build_prop_scorecard(outcomes, profile)
        specialist_readouts[specialist_name] = readout
        scorecards[specialist_name] = scorecard

        if not outcomes.empty:
            all_outcomes.append(outcomes)

        ranking_rows.append(
            {
                "specialist_name": specialist_name,
                "target_regime": target_regime,
                "source": sideways_source if specialist_name == sideways_name else "baseline",
                "survives_round1": readout["survives_round1"],
                "ev_per_attempt": scorecard["ev_per_attempt"],
                "first_payout_rate": scorecard["first_payout_rate"],
                "pass_rate": scorecard["pass_rate"],
                "in_regime_avg_r": readout["in_regime"]["avg_r"],
                "out_of_regime_avg_r": readout["out_of_regime"]["avg_r"],
                "specialization_ratio": readout["specialization_ratio"],
                "total_trades": readout["full_history"]["total_trades"],
            }
        )

    ranking_df = pd.DataFrame(ranking_rows).sort_values(
        by=["survives_round1", "ev_per_attempt", "first_payout_rate"],
        ascending=[False, False, False],
    )
    shortlist_df = (
        ranking_df[ranking_df["survives_round1"]]
        .sort_values(by=["target_regime", "ev_per_attempt"], ascending=[True, False])
        .groupby("target_regime", as_index=False)
        .head(1)
        .reset_index(drop=True)
    )

    regime_calendar.to_csv(output_dir / "regime_calendar.csv", index=False)
    confusion_log.to_csv(output_dir / "confusion_log.csv", index=False)
    yearly_summary.to_csv(output_dir / "regime_yearly_summary.csv", index=False)
    build_regime_strategy_mapping().to_csv(output_dir / "strategy_mapping.csv", index=False)
    ranking_df.to_csv(output_dir / "specialist_ranking.csv", index=False)
    shortlist_df.to_csv(output_dir / "paper_trade_shortlist.csv", index=False)
    if all_outcomes:
        pd.concat(all_outcomes, ignore_index=True).to_csv(output_dir / "account_outcomes.csv", index=False)

    write_json(
        output_dir / "specialist_readouts.json",
        {
            "profile": asdict(profile),
            "best_vwap_config_name": best_vwap_config.name,
            "best_vwap_full_history_metrics": {
                key: round(float(val), 4) if isinstance(val, (int, float)) else val
                for key, val in best_vwap_metrics.items()
                if key in {
                    "total_trades",
                    "win_rate",
                    "profit_factor",
                    "avg_r",
                    "total_r",
                    "max_drawdown_r",
                    "sharpe_ratio",
                    "calmar_ratio",
                }
            },
            "specialists": specialist_readouts,
        },
    )
    write_json(output_dir / "prop_scorecards.json", scorecards)

    summary_lines = [
        "# NQ Prop Regime Specialists — Round 1",
        "",
        "## Regime Rules",
        "",
        "- `bull`: prior close >= +0.5% vs SMA20 and prior 5d return > 0.",
        "- `bear`: prior close <= -0.5% vs SMA20 and prior 5d return < 0.",
        "- `sideways`: everything else after warmup.",
        "- `low_confidence`: abs(close_vs_sma20) < 0.25% or abs(ret_5d) < 0.5%.",
        "",
        "## Sideways Specialist Selection",
        "",
        f"- Selected source: `{sideways_source}`.",
        f"- Selected config: `{best_vwap_config.name}`.",
        f"- VWAP full-history trades: `{best_vwap_metrics['total_trades']}`.",
        "",
        "## Paper-Trade Shortlist",
        "",
    ]
    if shortlist_df.empty:
        summary_lines.append("- No specialist cleared the round-1 survival rules.")
    else:
        for _, row in shortlist_df.iterrows():
            summary_lines.append(
                f"- `{row['target_regime']}`: `{row['specialist_name']}` | "
                f"EV/attempt `{row['ev_per_attempt']}` | payout rate `{row['first_payout_rate']}`"
            )
    summary_lines.extend(
        [
            "",
            "## Default Kill Switch",
            "",
            "- Disable after 2 consecutive breached account attempts.",
            "- Disable after rolling 20 filled trades turn negative expectancy.",
            "- Disable after live account drawdown exceeds the backtest block-bootstrap `p95` drawdown estimate.",
            "- Re-enable only after 20 fresh paper trades return to positive expectancy.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")
    if not shortlist_df.empty:
        print("\nPaper-trade shortlist:")
        for _, row in shortlist_df.iterrows():
            print(
                f"  {row['target_regime']:>9} | {row['specialist_name']:<34} | "
                f"EV/attempt {row['ev_per_attempt']:>10}"
            )


if __name__ == "__main__":
    main()
