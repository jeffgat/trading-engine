#!/usr/bin/env python3
"""Build the funded-account paper-trade package for the balanced NQ combo.

The selected combo is:
- bull_specialist
- nq_asia
- nq_asia_lsi
- nq_ny_lsi

This step exports the combined routed trade ledger plus a funded-account
forecast so the combo can be judged by how quickly it tends to resolve.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult  # noqa: E402
from run_nq_bull_specialist_combo_resolution import (  # noqa: E402
    HOLDOUT_START,
    OUTPUT_DIR as COMBO_RESOLUTION_DIR,
    apply_g5_gate,
    make_bull_specialist_config,
    make_nq_asia_config,
    make_nq_asia_lsi_config,
    make_nq_ldn_config,
    make_nq_ny_lsi_config,
    merge_trade_streams,
    run_leg,
)


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_papertrade_balanced"
SELECTED_LEGS = ("bull_specialist", "nq_asia", "nq_asia_lsi", "nq_ny_lsi")
FORECAST_HORIZONS = (10, 15, 20, 30, 45, 60, 90)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


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


def collect_labeled_trades(leg_trades: dict[str, list[TradeResult]]) -> list[tuple[str, TradeResult]]:
    labeled: list[tuple[str, TradeResult]] = []
    for leg_name in SELECTED_LEGS:
        for trade in leg_trades[leg_name]:
            if trade.exit_type == EXIT_NO_FILL:
                continue
            labeled.append((leg_name, trade))
    return sorted(
        labeled,
        key=lambda item: (
            item[1].date,
            item[1].fill_time or "",
            item[1].signal_bar,
            item[1].fill_bar,
            item[1].exit_time or "",
            item[0],
        ),
    )


def trades_to_frame(labeled_trades: list[tuple[str, TradeResult]]) -> pd.DataFrame:
    rows = []
    for leg_name, trade in labeled_trades:
        rows.append(
            {
                "leg_name": leg_name,
                "date": trade.date,
                "session": trade.session,
                "direction": trade.direction,
                "signal_bar": trade.signal_bar,
                "fill_bar": trade.fill_bar,
                "entry_price": trade.entry_price,
                "stop_price": trade.stop_price,
                "tp1_price": trade.tp1_price,
                "tp2_price": trade.tp2_price,
                "exit_type": EXIT_NAMES.get(trade.exit_type, str(trade.exit_type)),
                "exit_bar": trade.exit_bar,
                "pnl_points": trade.pnl_points,
                "pnl_usd": trade.pnl_usd,
                "r_multiple": trade.r_multiple,
                "qty": trade.qty,
                "half_qty": trade.half_qty,
                "gap_size": trade.gap_size,
                "risk_points": trade.risk_points,
                "fill_time": trade.fill_time,
                "exit_time": trade.exit_time,
            }
        )
    return pd.DataFrame(rows)


def build_leg_summary(leg_trades: dict[str, list[TradeResult]]) -> pd.DataFrame:
    rows = []
    for leg_name in SELECTED_LEGS:
        trades = [t for t in leg_trades[leg_name] if t.exit_type != EXIT_NO_FILL]
        holdout = [t for t in trades if t.date >= HOLDOUT_START]
        avg_r = round(sum(float(t.r_multiple) for t in trades) / len(trades), 4) if trades else None
        holdout_avg_r = round(sum(float(t.r_multiple) for t in holdout) / len(holdout), 4) if holdout else None
        rows.append(
            {
                "leg_name": leg_name,
                "filled_trades": len(trades),
                "holdout_filled_trades": len(holdout),
                "avg_r": avg_r,
                "holdout_avg_r": holdout_avg_r,
            }
        )
    return pd.DataFrame(rows)


def find_horizon_row(forecast: dict, horizon_days: int) -> dict | None:
    for row in forecast.get("timeline", []):
        if int(row["horizon_days"]) == int(horizon_days):
            return row
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull Specialist Balanced Combo Paper-Trade Package")
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
    all_start_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=True)
    holdout_start_dates = [d for d in all_start_dates if pd.Timestamp(d) >= pd.Timestamp(args.holdout_start)]

    funded_profile = build_funded_profile()
    leg_configs = {
        "bull_specialist": make_bull_specialist_config(),
        "nq_asia": make_nq_asia_config(),
        "nq_ldn": make_nq_ldn_config(),
        "nq_asia_lsi": make_nq_asia_lsi_config(),
        "nq_ny_lsi": make_nq_ny_lsi_config(),
    }

    print("\nRunning selected leg backtests...", flush=True)
    leg_trades: dict[str, list[TradeResult]] = {}
    for leg_name, config in leg_configs.items():
        if leg_name not in SELECTED_LEGS and leg_name != "nq_ldn":
            continue
        leg_trades[leg_name] = run_leg(leg_name, config, df_5m, df_1m, df_1s, regime_calendar)

    if "nq_ldn" in leg_trades:
        asia_reference_streams = [
            leg_trades[name] for name in ("nq_asia", "nq_asia_lsi") if name in leg_trades
        ]
        leg_trades["nq_ldn"] = apply_g5_gate(leg_trades["nq_ldn"], asia_reference_streams)

    print("\nCombining balanced route...", flush=True)
    combined_trades = merge_trade_streams([leg_trades[name] for name in SELECTED_LEGS])
    combined_holdout = [trade for trade in combined_trades if trade.date >= args.holdout_start]

    outcomes = simulate_funded_first_payouts(
        specialist_name=" + ".join(SELECTED_LEGS),
        trades=combined_trades,
        trading_dates=all_start_dates,
        profile=funded_profile,
    )
    holdout_outcomes = simulate_funded_first_payouts(
        specialist_name=" + ".join(SELECTED_LEGS),
        trades=combined_holdout,
        trading_dates=holdout_start_dates,
        profile=funded_profile,
    )
    scorecard = build_funded_first_payout_scorecard(outcomes, funded_profile)
    holdout_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, funded_profile)
    forecast = build_funded_first_payout_forecast(outcomes, horizons_days=FORECAST_HORIZONS)
    holdout_forecast = build_funded_first_payout_forecast(holdout_outcomes, horizons_days=FORECAST_HORIZONS)

    labeled_trades = collect_labeled_trades(leg_trades)
    trade_df = trades_to_frame(labeled_trades)
    holdout_trade_df = trade_df[pd.to_datetime(trade_df["date"]) >= pd.Timestamp(args.holdout_start)].copy()
    leg_summary_df = build_leg_summary(leg_trades)

    trade_df.to_csv(output_dir / "combo_trades.csv", index=False)
    holdout_trade_df.to_csv(output_dir / "combo_trades_holdout.csv", index=False)
    leg_summary_df.to_csv(output_dir / "leg_summary.csv", index=False)
    outcomes.to_csv(output_dir / "account_outcomes.csv", index=False)
    holdout_outcomes.to_csv(output_dir / "account_outcomes_holdout.csv", index=False)
    pd.DataFrame(forecast["timeline"]).to_csv(output_dir / "forecast_timeline.csv", index=False)
    pd.DataFrame(holdout_forecast["timeline"]).to_csv(output_dir / "forecast_timeline_holdout.csv", index=False)

    summary_20 = find_horizon_row(forecast, 20) or {}
    summary_30 = find_horizon_row(forecast, 30) or {}
    holdout_20 = find_horizon_row(holdout_forecast, 20) or {}
    holdout_30 = find_horizon_row(holdout_forecast, 30) or {}

    write_json(
        output_dir / "combo_paper_trade_package.json",
        {
            "selected_combo": {
                "combo_name": " + ".join(SELECTED_LEGS),
                "legs": list(SELECTED_LEGS),
                "source_combo_ranking": str(COMBO_RESOLUTION_DIR / "combo_ranking.csv"),
            },
            "funded_profile": asdict(funded_profile),
            "leg_configs": {
                leg_name: asdict(leg_configs[leg_name])
                for leg_name in SELECTED_LEGS
            },
            "scorecard": scorecard,
            "holdout_scorecard": holdout_scorecard,
            "forecast": forecast,
            "holdout_forecast": holdout_forecast,
        },
    )

    summary_lines = [
        "# NQ Bull Specialist Balanced Combo Paper-Trade Package",
        "",
        "## Selected Route",
        "",
        "- Combo: `bull_specialist + nq_asia + nq_asia_lsi + nq_ny_lsi`.",
        "- Why this route: much faster resolution than the standalone bull leg without jumping to the 5-leg max-speed stack.",
        "- Bull specialist still keeps its bull-only + no-low-confidence gate inside the combo.",
        "",
        "## Funded Account Model",
        "",
        "- Challenge cost: `$150`.",
        "- Starting balance: `$50,000`.",
        "- Trailing drawdown: `$2,000` EOD realized, capped so breach never rises above `$50,000`.",
        "- First withdrawable payout: everything above `$52,000`.",
        "- Risk: `$500` per trade before first payout, `$250` after.",
        "",
        "## Full-History Outcome",
        "",
        f"- Payout rate: `{scorecard['payout_rate']}` | breach rate `{scorecard['breach_rate']}` | open rate `{scorecard['open_rate']}`.",
        f"- Average days to payout: `{scorecard['average_days_to_payout']}` | median `{scorecard['median_days_to_payout']}`.",
        f"- Average trades to payout: `{scorecard['average_trades_to_payout']}`.",
        f"- Average first payout amount: `${scorecard['average_first_payout_amount_usd']}` | EV/start `${scorecard['ev_per_start_usd']}`.",
        "",
        "## Forecast",
        "",
        f"- By day 20: payout `{summary_20.get('payout_rate_by_horizon')}` | breach `{summary_20.get('breach_rate_by_horizon')}` | resolved `{summary_20.get('resolved_rate_by_horizon')}`.",
        f"- By day 30: payout `{summary_30.get('payout_rate_by_horizon')}` | breach `{summary_30.get('breach_rate_by_horizon')}` | resolved `{summary_30.get('resolved_rate_by_horizon')}`.",
        f"- Payout day quantiles: `{forecast.get('payout_days_quantiles')}`.",
        f"- Resolution day quantiles: `{forecast.get('resolution_days_quantiles')}`.",
        "",
        "## Holdout 2025-2026",
        "",
        f"- Holdout payout rate: `{holdout_scorecard['payout_rate']}` | breach rate `{holdout_scorecard['breach_rate']}`.",
        f"- Holdout average days to payout: `{holdout_scorecard['average_days_to_payout']}`.",
        f"- Holdout EV/start: `${holdout_scorecard['ev_per_start_usd']}`.",
        f"- Holdout by day 20 resolved: `{holdout_20.get('resolved_rate_by_horizon')}` | by day 30 resolved: `{holdout_30.get('resolved_rate_by_horizon')}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
