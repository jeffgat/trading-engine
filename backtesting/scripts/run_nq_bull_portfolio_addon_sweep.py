#!/usr/bin/env python3
"""Optimize add-on legs for a bull-focused NQ portfolio.

The current bull-specialist V1 winner is held fixed as the core leg.
We then test the former generalist portfolio legs as candidate add-ons:
- NQ Asia continuation
- NQ Asia LSI
- NQ NY LSI

Objective:
- preserve the bull-window profile (strong 2024+, weak 2022-2023)
- improve funded-account payout speed vs the single bull leg
- surface bull/bear regime contribution explicitly so we do not drift back
  into a disguised generalist payout stack
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from orb_backtest.analysis.gates import apply_dow_filter  # noqa: E402
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    DEFAULT_HOLDOUT_START,
    FundedFirstPayoutProfile,
    bull_market_rank_key,
    build_nq_ny_regime_calendar,
    evaluate_bull_market_windows,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult  # noqa: E402
from orb_backtest.optimize.parallel import run_sweep  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from run_nq_asia_4leg_combo_sweep import make_nq_asia_combo_candidates  # noqa: E402
from run_nq_asia_lsi_4leg_combo_sweep import make_nq_asia_lsi_combo_candidates  # noqa: E402
from run_nq_bull_specialist_combo_resolution import merge_trade_streams  # noqa: E402
from run_nq_ny_lsi_4leg_combo_sweep import make_nq_ny_lsi_combo_candidates  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_portfolio_addon_sweep"


def make_bull_winner_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:30",
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
        rr=3.0,
        tp1_ratio=0.5,
        atr_length=12,
        impulse_close_filter=False,
        excluded_days=(4,),
        name="bull_specialist_v1_winner",
        notes="Bull-specialist V1 winner routed through bull + no-low-confidence.",
    )


def build_funded_profile() -> FundedFirstPayoutProfile:
    return FundedFirstPayoutProfile(
        challenge_fee=150.0,
        starting_balance_usd=50_000.0,
        trailing_drawdown_usd=2_000.0,
        max_trailing_breach_usd=50_000.0,
        first_payout_floor_usd=52_000.0,
        risk_pre_payout_usd=500.0,
        risk_post_payout_usd=250.0,
    )


def build_candidate_book() -> tuple[list[StrategyConfig], dict[str, str], dict[str, str]]:
    configs: list[StrategyConfig] = []
    family_by_name: dict[str, str] = {}
    anchor_by_family = {
        "nq_asia": "nq_asia_cont",
        "nq_asia_lsi": "nq_asia_lsi_end2300",
        "nq_ny_lsi": "nq_ny_lsi_gap3.75",
    }

    family_builders = {
        "nq_asia": make_nq_asia_combo_candidates,
        "nq_asia_lsi": make_nq_asia_lsi_combo_candidates,
        "nq_ny_lsi": make_nq_ny_lsi_combo_candidates,
    }

    seen: set[str] = set()
    for family, builder in family_builders.items():
        for cfg in builder():
            if cfg.name in seen:
                continue
            seen.add(cfg.name)
            configs.append(cfg)
            family_by_name[cfg.name] = family

    return configs, family_by_name, anchor_by_family


def run_bull_winner(
    config: StrategyConfig,
    df_5m,
    df_1m,
    df_1s,
    regime_calendar: pd.DataFrame,
) -> list[TradeResult]:
    from orb_backtest.engine.simulator import run_backtest

    trades = run_backtest(
        df_5m,
        config,
        start_date="2020-01-01",
        df_1m=df_1m,
        df_1s=df_1s,
    )
    trades = apply_dow_filter(trades, set(config.excluded_days))
    trades = filter_trades_by_low_confidence(
        trades,
        regime_calendar,
        include_low_confidence=False,
    )
    trades = filter_trades_by_regime(
        trades,
        regime_calendar,
        include={"bull"},
    )
    return trades


def run_general_leg(
    config: StrategyConfig,
    trades: list[TradeResult],
) -> list[TradeResult]:
    if config.excluded_days:
        trades = apply_dow_filter(trades, set(config.excluded_days))
    return trades


def regime_contribution_summary(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
) -> dict[str, float]:
    summary: dict[str, float] = {}
    for regime in ("bull", "bear", "sideways"):
        subset = filter_trades_by_regime(trades, regime_calendar, include={regime})
        metrics = compute_metrics(subset)
        summary[f"{regime}_trades"] = int(metrics.get("total_trades", 0))
        summary[f"{regime}_net_r"] = round(float(metrics.get("total_r", 0.0)), 4)
        summary[f"{regime}_avg_r"] = round(float(metrics.get("avg_r", 0.0)), 4)
    summary["bull_minus_bear_net_r"] = round(summary["bull_net_r"] - summary["bear_net_r"], 4)
    return summary


def candidate_row(
    family: str,
    config: StrategyConfig,
    year_windows: dict,
    combined_trades: list[TradeResult],
    add_on_trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
) -> dict:
    holdout = year_windows["holdout_2025_latest"]
    combo_regime = regime_contribution_summary(combined_trades, regime_calendar)
    addon_regime = regime_contribution_summary(add_on_trades, regime_calendar)
    return {
        "family": family,
        "candidate_name": config.name,
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "atr_length": config.atr_length,
        "strategy": config.strategy,
        "direction_filter": config.direction_filter,
        "excluded_days": ",".join(str(v) for v in config.excluded_days) if config.excluded_days else "",
        "survives_bull_v1": year_windows["survives_bull_v1"],
        "acceptance_net_r": year_windows["acceptance_net_r"],
        "acceptance_trades": year_windows["acceptance_2024_latest"]["total_trades"],
        "rejection_net_r": year_windows["rejection_net_r"],
        "rejection_share_of_acceptance": year_windows["rejection_share_of_acceptance"],
        "acceptance_rejection_separation": year_windows["acceptance_rejection_separation"],
        "holdout_payout_rate": holdout["payout_rate"],
        "holdout_breach_rate": holdout["breach_rate"],
        "holdout_open_rate": holdout["open_rate"],
        "holdout_payout_minus_breach": round(
            float(holdout["payout_rate"] or 0.0) - float(holdout["breach_rate"] or 0.0),
            4,
        ),
        "holdout_average_days_to_payout": holdout["average_days_to_payout"],
        "holdout_average_trades_to_payout": holdout["average_trades_to_payout"],
        "holdout_ev_per_start_usd": holdout["ev_per_start_usd"],
        "combined_filled_trades": len([t for t in combined_trades if t.exit_type != EXIT_NO_FILL]),
        "addon_filled_trades": len([t for t in add_on_trades if t.exit_type != EXIT_NO_FILL]),
        **{f"combo_{k}": v for k, v in combo_regime.items()},
        **{f"addon_{k}": v for k, v in addon_regime.items()},
    }


def ranking_key(row: dict) -> tuple:
    year_windows_stub = {
        "survives_bull_v1": row["survives_bull_v1"],
        "acceptance_net_r": row["acceptance_net_r"],
        "acceptance_rejection_separation": row["acceptance_rejection_separation"],
        "holdout_2025_latest": {
            "payout_rate": row["holdout_payout_rate"],
            "breach_rate": row["holdout_breach_rate"],
            "average_days_to_payout": row["holdout_average_days_to_payout"],
        },
    }
    return (
        *bull_market_rank_key(year_windows_stub),
        float(row["combo_bull_minus_bear_net_r"]),
        float(row["holdout_ev_per_start_usd"] or 0.0),
    )


def write_summary(
    output_dir: Path,
    best_overall: dict,
    best_by_family: dict[str, dict],
    anchors: dict[str, dict],
    total_candidates: int,
) -> None:
    lines = [
        "# NQ Bull Portfolio Add-On Sweep",
        "",
        "## Setup",
        "",
        "- Fixed core: `bull_specialist_v1_winner`.",
        "- Candidate families seeded from the former generalist payout portfolio.",
        "- Scoring uses the bull-window framework: weak `2022-2023`, strong `2024+`, holdout `2025+` payout vs breach.",
        "- Ranking also surfaces bull-vs-bear regime contribution so add-ons do not quietly reintroduce generalist behavior.",
        "",
        "## Best Overall Add-On",
        "",
        f"- Family: `{best_overall['family']}`.",
        f"- Candidate: `{best_overall['candidate_name']}`.",
        f"- Acceptance net R: `{best_overall['acceptance_net_r']}`.",
        f"- Rejection net R: `{best_overall['rejection_net_r']}`.",
        f"- Holdout payout/breach: `{best_overall['holdout_payout_rate']}` / `{best_overall['holdout_breach_rate']}`.",
        f"- Holdout average days to payout: `{best_overall['holdout_average_days_to_payout']}`.",
        f"- Combo bull/bear/sideways net R: `{best_overall['combo_bull_net_r']}` / `{best_overall['combo_bear_net_r']}` / `{best_overall['combo_sideways_net_r']}`.",
        "",
        "## Family Leaders",
        "",
    ]

    for family in ("nq_asia", "nq_asia_lsi", "nq_ny_lsi"):
        best = best_by_family[family]
        anchor = anchors.get(family)
        lines.extend(
            [
                f"- `{family}` best: `{best['candidate_name']}` | holdout payout-breach `{best['holdout_payout_minus_breach']}` | acceptance/rejection `{best['acceptance_net_r']}` / `{best['rejection_net_r']}`.",
                (
                    f"- `{family}` generalist anchor: `{anchor['candidate_name']}` | holdout payout-breach `{anchor['holdout_payout_minus_breach']}` | acceptance/rejection `{anchor['acceptance_net_r']}` / `{anchor['rejection_net_r']}`."
                    if anchor is not None
                    else f"- `{family}` generalist anchor not found in candidate set."
                ),
            ]
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            f"- Total candidates tested: `{total_candidates}`.",
            "- This is a first pass from generalist seeds, not the final bull-specialist portfolio.",
            "- The important read is which add-on families improve speed while keeping 2022-2023 capped and avoiding large bear-regime contribution.",
        ]
    )
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull Portfolio Add-On Sweep")
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
    eligible_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=False)
    funded_profile = build_funded_profile()

    bull_config = make_bull_winner_config()
    print("\nRunning fixed bull winner...", flush=True)
    bull_trades = run_bull_winner(bull_config, df_5m, df_1m, df_1s, regime_calendar)

    candidate_configs, family_by_name, anchor_by_family = build_candidate_book()
    print(f"\nRunning add-on sweep ({len(candidate_configs)} candidates)...", flush=True)
    sweep_results = run_sweep(
        df_5m,
        candidate_configs,
        n_workers=max(1, args.workers),
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )

    rows = []
    rows_by_family: dict[str, list[dict]] = defaultdict(list)
    for config, raw_trades in sweep_results:
        family = family_by_name[config.name]
        addon_trades = run_general_leg(config, raw_trades)
        combined_trades = merge_trade_streams([bull_trades, addon_trades])
        year_windows = evaluate_bull_market_windows(
            specialist_name=f"bull_specialist_v1_winner + {config.name}",
            trades=combined_trades,
            trading_dates=eligible_dates,
            funded_profile=funded_profile,
            holdout_start=args.holdout_start,
        )
        row = candidate_row(family, config, year_windows, combined_trades, addon_trades, regime_calendar)
        rows.append(row)
        rows_by_family[family].append(row)

    ranking_rows = sorted(rows, key=ranking_key, reverse=True)
    ranking_df = pd.DataFrame(ranking_rows)
    ranking_df.to_csv(output_dir / "addon_ranking.csv", index=False)

    best_by_family: dict[str, dict] = {}
    anchors: dict[str, dict] = {}
    for family, family_rows in rows_by_family.items():
        ordered = sorted(family_rows, key=ranking_key, reverse=True)
        best_by_family[family] = ordered[0]
        anchor_name = anchor_by_family.get(family)
        if anchor_name is not None:
            anchor = next((row for row in family_rows if row["candidate_name"] == anchor_name), None)
            if anchor is not None:
                anchors[family] = anchor

    family_df = pd.DataFrame(
        [
            {
                "family": family,
                "best_candidate": best_by_family[family]["candidate_name"],
                "best_holdout_payout_minus_breach": best_by_family[family]["holdout_payout_minus_breach"],
                "best_acceptance_net_r": best_by_family[family]["acceptance_net_r"],
                "best_rejection_net_r": best_by_family[family]["rejection_net_r"],
                "best_combo_bull_net_r": best_by_family[family]["combo_bull_net_r"],
                "best_combo_bear_net_r": best_by_family[family]["combo_bear_net_r"],
                "anchor_candidate": anchors.get(family, {}).get("candidate_name"),
                "anchor_holdout_payout_minus_breach": anchors.get(family, {}).get("holdout_payout_minus_breach"),
                "anchor_acceptance_net_r": anchors.get(family, {}).get("acceptance_net_r"),
                "anchor_rejection_net_r": anchors.get(family, {}).get("rejection_net_r"),
            }
            for family in sorted(best_by_family)
        ]
    )
    family_df.to_csv(output_dir / "best_by_family.csv", index=False)

    best_overall = ranking_rows[0]
    (output_dir / "best_overall.json").write_text(json.dumps(best_overall, indent=2))
    write_summary(output_dir, best_overall, best_by_family, anchors, len(rows))

    print("\nTop candidates:")
    print(ranking_df.head(10).to_string(index=False))


if __name__ == "__main__":
    main()
