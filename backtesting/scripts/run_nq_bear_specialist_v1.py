#!/usr/bin/env python3
"""Bear-market specialist V1 research runner.

Goal:
- strong performance in 2022-2023
- specifically funded-account-viable in 2023
- weak or inactive performance in 2024-latest
- 2021 logged for diagnostics only
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    FundedFirstPayoutProfile,
    apply_structure_vwap_gate,
    bear_market_rank_key,
    build_nq_ny_regime_calendar,
    build_regime_confusion_log,
    build_structure_vwap_signals,
    evaluate_bear_market_windows,
    evaluate_specialist,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult
from orb_backtest.optimize.parallel import run_sweep


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bear_specialist_v1"
GATE_NAMES = (
    "none",
    "hh_hl_3_vwap",
    "regime_2of3_vwap",
    "pullback_holds_vwap",
    "pullback_holds_vwap_orb",
    "score_eq_3",
)


def make_base_config() -> StrategyConfig:
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
        name="NQ Bear Specialist V1 Base",
        notes="Bear-market specialist V1 base config.",
    )


def build_candidate_specs() -> list[dict[str, object]]:
    specs: list[dict[str, object]] = []

    # Existing short baseline and strongest earlier context gates.
    for gate_name in GATE_NAMES:
        specs.append(
            {
                "rr": 2.0,
                "tp1_ratio": 0.3,
                "stop_orb_pct": 17.0,
                "min_gap_orb_pct": 5.0,
                "entry_end": "11:00",
                "gate_name": gate_name,
            }
        )

    for rr in (1.75, 2.0):
        for tp1_ratio in (0.2, 0.3):
            for stop_orb_pct in (15.0, 17.0, 20.0):
                for min_gap_orb_pct in (0.0, 5.0):
                    for entry_end in ("10:45", "11:00"):
                        for gate_name in GATE_NAMES:
                            specs.append(
                                {
                                    "rr": rr,
                                    "tp1_ratio": tp1_ratio,
                                    "stop_orb_pct": stop_orb_pct,
                                    "min_gap_orb_pct": min_gap_orb_pct,
                                    "entry_end": entry_end,
                                    "gate_name": gate_name,
                                }
                            )

    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, ...]] = set()
    for spec in specs:
        key = (
            spec["rr"],
            spec["tp1_ratio"],
            spec["stop_orb_pct"],
            spec["min_gap_orb_pct"],
            spec["entry_end"],
            spec["gate_name"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(spec)
    return deduped


def build_candidate_configs(base: StrategyConfig) -> list[tuple[StrategyConfig, str]]:
    configs: list[tuple[StrategyConfig, str]] = []
    for spec in build_candidate_specs():
        cfg = with_overrides(
            base,
            rr=float(spec["rr"]),
            tp1_ratio=float(spec["tp1_ratio"]),
            ny_stop_orb_pct=float(spec["stop_orb_pct"]),
            ny_min_gap_orb_pct=float(spec["min_gap_orb_pct"]),
            ny_entry_end=str(spec["entry_end"]),
        )
        gate_name = str(spec["gate_name"])
        gate_label = gate_name if gate_name != "none" else "ungated"
        cfg = replace(
            cfg,
            name=(
                f"NQ Bear V1 rr{cfg.rr:.2f}_tp1{cfg.tp1_ratio:.2f}_"
                f"stoporb{cfg.sessions[0].stop_orb_pct:.1f}_"
                f"gaporb{cfg.sessions[0].min_gap_orb_pct:.1f}_"
                f"end{cfg.sessions[0].entry_end.replace(':', '')}_{gate_label}"
            ),
            notes=f"Bear V1 candidate with {gate_label} context filter.",
        )
        configs.append((cfg, gate_name))
    return configs


def build_regime_attribution(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["regime", "filled_trades", "net_r", "avg_r"])

    cal = regime_calendar.copy()
    cal["date_key"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    regime_lookup = dict(zip(cal["date_key"], cal["regime"]))

    rows = []
    for regime in ("bull", "bear", "sideways"):
        subset = [
            trade for trade in trades
            if trade.exit_type != EXIT_NO_FILL and regime_lookup.get(trade.date) == regime
        ]
        net_r = sum(float(trade.r_multiple) for trade in subset)
        avg_r = (net_r / len(subset)) if subset else 0.0
        rows.append(
            {
                "regime": regime,
                "filled_trades": len(subset),
                "net_r": round(net_r, 4),
                "avg_r": round(avg_r, 4),
            }
        )
    return pd.DataFrame(rows)


def record_to_row(record: dict) -> dict:
    year_windows = record["year_windows"]
    holdout = year_windows["holdout_2023"]
    specialist = record["specialist_readout"]
    return {
        "config_name": record["config"].name,
        "gate_name": record["gate_name"],
        "rr": record["config"].rr,
        "tp1_ratio": record["config"].tp1_ratio,
        "stop_orb_pct": record["config"].sessions[0].stop_orb_pct,
        "min_gap_orb_pct": record["config"].sessions[0].min_gap_orb_pct,
        "entry_end": record["config"].sessions[0].entry_end,
        "survives_bear_v1": year_windows["survives_bear_v1"],
        "survives_round1_specialist": specialist["survives_round1"],
        "acceptance_net_r": year_windows["acceptance_net_r"],
        "acceptance_trades": year_windows["acceptance_2022_2023"]["total_trades"],
        "rejection_net_r": year_windows["rejection_net_r"],
        "rejection_share_of_acceptance": year_windows["rejection_share_of_acceptance"],
        "holdout_payout_rate": holdout["payout_rate"],
        "holdout_breach_rate": holdout["breach_rate"],
        "holdout_payout_minus_breach": round(
            float(holdout["payout_rate"] or 0.0) - float(holdout["breach_rate"] or 0.0),
            4,
        ),
        "holdout_average_days_to_payout": holdout["average_days_to_payout"],
        "specialization_ratio": specialist["specialization_ratio"],
        "in_regime_avg_r": specialist["in_regime"]["avg_r"],
        "out_of_regime_avg_r": specialist["out_of_regime"]["avg_r"],
    }


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def write_summary(
    output_dir: Path,
    selected: dict,
    all_records: list[dict],
    confusion_log: pd.DataFrame,
) -> None:
    year_windows = selected["year_windows"]
    specialist = selected["specialist_readout"]
    holdout = year_windows["holdout_2023"]
    status = (
        "true bear specialist"
        if year_windows["survives_bear_v1"] and specialist["survives_round1"]
        else "still too generalist"
    )
    lines = [
        "# NQ Bear Specialist V1",
        "",
        "## Outcome",
        "",
        f"- Selected config: `{selected['config'].name}`",
        f"- Gate: `{selected['gate_name']}`",
        f"- Classification: `{status}`",
        f"- Candidates tested: `{len(all_records)}`",
        f"- Low-confidence diagnostic days: `{len(confusion_log)}`",
        "",
        "## Fixed Windows",
        "",
        "- `2021`: diagnostic only",
        "- `2022-2023`: acceptance window",
        "- `2023`: funded-account holdout inside the acceptance era",
        "- `2024+`: rejection window",
        "",
        "## Selected Scorecard",
        "",
        f"- Acceptance net R: `{year_windows['acceptance_net_r']}`",
        f"- Acceptance trades: `{year_windows['acceptance_2022_2023']['total_trades']}`",
        f"- Rejection net R: `{year_windows['rejection_net_r']}`",
        f"- Rejection share of acceptance: `{year_windows['rejection_share_of_acceptance']}`",
        f"- 2023 holdout payout/breach: `{holdout['payout_rate']}` / `{holdout['breach_rate']}`",
        f"- 2023 holdout avg days to payout: `{holdout['average_days_to_payout']}`",
        f"- Round-1 specialization ratio: `{specialist['specialization_ratio']}`",
        f"- In-regime avg R: `{specialist['in_regime']['avg_r']}`",
        f"- Out-of-regime avg R: `{specialist['out_of_regime']['avg_r']}`",
        "",
        "## Interpretation",
        "",
    ]
    if status == "true bear specialist":
        lines.extend(
            [
                "- The selected route cleared both the bear-market window test and the original specialist readout.",
                "- It is strong in the 2022-2023 acceptance era and meaningfully weaker in the 2024+ rejection window.",
            ]
        )
    else:
        lines.extend(
            [
                "- The selected route improved the bear-window profile, but it still does not fully satisfy the stricter specialist intent.",
                "- Treat it as an interim bear-biased route rather than a finished regime-specialist deployment.",
            ]
        )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bear Specialist V1")
    print("=" * 72)
    print(f"Output dir: {output_dir}")

    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file, start=args.start, end=args.end)
    try:
        df_1m = load_1m_for_5m(NQ.data_file, start=args.start, end=args.end)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file, start=args.start, end=args.end)

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_nq_ny_regime_calendar(df_5m, start_date=args.start, end_date=args.end)
    confusion_log = build_regime_confusion_log(regime_calendar)
    eligible_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=False)

    funded_profile = FundedFirstPayoutProfile(
        challenge_fee=150.0,
        starting_balance_usd=50_000.0,
        trailing_drawdown_usd=2_000.0,
        max_trailing_breach_usd=50_000.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
        risk_post_payout_usd=250.0,
    )

    base = make_base_config()
    candidates = build_candidate_configs(base)
    configs = [cfg for cfg, _ in candidates]
    gate_lookup = {cfg.name: gate_name for cfg, gate_name in candidates}

    print(f"\nRunning sweep ({len(configs)} configs)...", flush=True)
    sweep_results = run_sweep(
        df_5m,
        configs,
        n_workers=max(1, args.workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )

    signal_cache = build_structure_vwap_signals(df_5m, base.sessions[0], atr_length=base.atr_length)

    records: list[dict] = []
    for config, trades in sweep_results:
        gate_name = gate_lookup[config.name]
        trades = apply_dow_filter(trades, set(config.excluded_days))
        if gate_name != "none":
            trades = apply_structure_vwap_gate(trades, signal_cache, gate_name)

        specialist_trades = filter_trades_by_low_confidence(
            trades,
            regime_calendar,
            include_low_confidence=False,
        )
        routed_trades = filter_trades_by_regime(
            specialist_trades,
            regime_calendar,
            include={"bear"},
        )

        specialist_readout = evaluate_specialist(
            specialist_name=config.name,
            target_regime="bear",
            trades=specialist_trades,
            regime_calendar=regime_calendar,
            holdout_start="2024-01-01",
        )
        year_windows = evaluate_bear_market_windows(
            specialist_name=config.name,
            trades=routed_trades,
            trading_dates=eligible_dates,
            funded_profile=funded_profile,
        )

        records.append(
            {
                "config": config,
                "gate_name": gate_name,
                "specialist_readout": specialist_readout,
                "year_windows": year_windows,
                "specialist_trades": specialist_trades,
            }
        )

    ranked = sorted(records, key=lambda record: bear_market_rank_key(record["year_windows"]), reverse=True)
    ranking_df = pd.DataFrame([record_to_row(record) for record in ranked])
    ranking_df.to_csv(output_dir / "candidate_ranking.csv", index=False)

    year_window_rows = []
    for record in ranked:
        score = record["year_windows"]
        holdout = score["holdout_2023"]
        year_window_rows.append(
            {
                "config_name": record["config"].name,
                "gate_name": record["gate_name"],
                "diagnostic_2021_trades": score["diagnostic_2021"]["total_trades"],
                "acceptance_2022_2023_trades": score["acceptance_2022_2023"]["total_trades"],
                "acceptance_2022_2023_net_r": score["acceptance_net_r"],
                "holdout_2023_payout_rate": holdout["payout_rate"],
                "holdout_2023_breach_rate": holdout["breach_rate"],
                "holdout_2023_average_days_to_payout": holdout["average_days_to_payout"],
                "rejection_2024_latest_trades": score["rejection_2024_latest"]["total_trades"],
                "rejection_2024_latest_net_r": score["rejection_net_r"],
                "acceptance_rejection_separation": score["acceptance_rejection_separation"],
                "survives_bear_v1": score["survives_bear_v1"],
            }
        )
    pd.DataFrame(year_window_rows).to_csv(output_dir / "year_window_scorecards.csv", index=False)

    selected = ranked[0]
    selected_attribution = build_regime_attribution(selected["specialist_trades"], regime_calendar)
    selected_attribution.to_csv(output_dir / "selected_candidate_regime_attribution.csv", index=False)
    write_json(output_dir / "selected_candidate_specialist_readout.json", selected["specialist_readout"])
    write_json(output_dir / "selected_candidate_year_windows.json", selected["year_windows"])
    confusion_log.to_csv(output_dir / "regime_confusion_log.csv", index=False)
    write_summary(output_dir, selected, ranked, confusion_log)

    print("\nTop candidate:")
    print(ranking_df.head(1).to_string(index=False))


if __name__ == "__main__":
    main()
