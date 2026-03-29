#!/usr/bin/env python3
"""Build the funded-account paper-trade package for the bull-biased 2-leg route.

Selected route:
- bull_specialist_v1_winner
- nq_asia_lsi_rr1.75
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_nq_ny_regime_calendar,
    simulate_funded_first_payouts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult  # noqa: E402
from run_nq_bull_portfolio_addon_sweep import (  # noqa: E402
    build_funded_profile,
    make_bull_winner_config,
    run_bull_winner,
    run_general_leg,
)
from run_nq_bull_specialist_combo_resolution import HOLDOUT_START, merge_trade_streams  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_bull_biased_combo_papertrade_v1"
SELECTED_LEGS = ("bull_specialist_v1_winner", "nq_asia_lsi_rr1.75")
FORECAST_HORIZONS = (10, 15, 20, 30, 45, 60, 90)


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def make_nq_asia_lsi_rr175_config() -> StrategyConfig:
    session = SessionConfig(
        name="Asia",
        rth_start="20:00",
        entry_start="20:40",
        entry_end="23:30",
        flat_start="04:00",
        flat_end="07:00",
        min_gap_atr_pct=1.75,
    )
    return StrategyConfig(
        strategy="lsi",
        rr=1.75,
        tp1_ratio=0.7,
        atr_length=40,
        risk_usd=5000.0,
        sessions=(session,),
        instrument=NQ,
        direction_filter="long",
        lsi_n_left=8,
        lsi_n_right=2,
        lsi_fvg_window_left=15,
        lsi_fvg_window_right=2,
        lsi_entry_mode="close",
        name="nq_asia_lsi_rr1.75",
        notes="Bull-biased portfolio winner from the constrained combo sweep.",
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


def build_leg_summary(leg_trades: dict[str, list[TradeResult]], holdout_start: str) -> pd.DataFrame:
    rows = []
    for leg_name in SELECTED_LEGS:
        trades = [t for t in leg_trades[leg_name] if t.exit_type != EXIT_NO_FILL]
        holdout = [t for t in trades if t.date >= holdout_start]
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
    parser.add_argument("--start", default="2020-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("NQ Bull-Biased 2-Leg Paper-Trade Package")
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
    all_start_dates = trading_dates_from_calendar(regime_calendar, include_low_confidence=False)
    holdout_start_dates = [d for d in all_start_dates if pd.Timestamp(d) >= pd.Timestamp(args.holdout_start)]

    funded_profile = build_funded_profile()
    bull_config = make_bull_winner_config()
    asia_config = make_nq_asia_lsi_rr175_config()

    print("\nRunning selected leg backtests...", flush=True)
    leg_trades: dict[str, list[TradeResult]] = {}
    leg_trades["bull_specialist_v1_winner"] = run_bull_winner(
        bull_config,
        df_5m,
        df_1m,
        df_1s,
        regime_calendar,
    )

    from orb_backtest.engine.simulator import run_backtest  # noqa: E402

    raw_asia_trades = run_backtest(
        df_5m,
        asia_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    leg_trades["nq_asia_lsi_rr1.75"] = run_general_leg(asia_config, raw_asia_trades)

    print("\nCombining route...", flush=True)
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
    leg_summary = build_leg_summary(leg_trades, args.holdout_start)
    timeline_df = pd.DataFrame(forecast["timeline"])
    holdout_timeline_df = pd.DataFrame(holdout_forecast["timeline"])

    trade_df.to_csv(output_dir / "combo_trades.csv", index=False)
    leg_summary.to_csv(output_dir / "leg_summary.csv", index=False)
    timeline_df.to_csv(output_dir / "forecast_timeline.csv", index=False)
    holdout_timeline_df.to_csv(output_dir / "forecast_timeline_holdout.csv", index=False)

    package = {
        "selected_legs": list(SELECTED_LEGS),
        "start": args.start,
        "end": args.end,
        "holdout_start": args.holdout_start,
        "funded_profile": funded_profile.__dict__,
        "scorecard": scorecard,
        "holdout_scorecard": holdout_scorecard,
        "forecast": forecast,
        "holdout_forecast": holdout_forecast,
        "leg_configs": {
            "bull_specialist_v1_winner": {
                "rr": bull_config.rr,
                "tp1_ratio": bull_config.tp1_ratio,
                "atr_length": bull_config.atr_length,
                "entry_end": bull_config.sessions[0].entry_end,
                "stop_atr_pct": bull_config.sessions[0].stop_atr_pct,
                "regime_gate": "bull_no_low_confidence",
                "structure_gate": "none",
            },
            "nq_asia_lsi_rr1.75": {
                "rr": asia_config.rr,
                "tp1_ratio": asia_config.tp1_ratio,
                "atr_length": asia_config.atr_length,
                "entry_end": asia_config.sessions[0].entry_end,
                "min_gap_atr_pct": asia_config.sessions[0].min_gap_atr_pct,
            },
        },
    }
    write_json(output_dir / "combo_paper_trade_package.json", package)

    horizon20 = find_horizon_row(forecast, 20) or {}
    horizon30 = find_horizon_row(forecast, 30) or {}
    horizon45 = find_horizon_row(forecast, 45) or {}
    holdout20 = find_horizon_row(holdout_forecast, 20) or {}
    holdout30 = find_horizon_row(holdout_forecast, 30) or {}

    summary_lines = [
        "# NQ Bull-Biased 2-Leg Paper-Trade Package",
        "",
        "## Selected Route",
        "",
        "- `bull_specialist_v1_winner`",
        "- `nq_asia_lsi_rr1.75`",
        "",
        "## Funded-Account Model",
        "",
        f"- Challenge fee: `${funded_profile.challenge_fee}`.",
        f"- Starting balance: `${funded_profile.starting_balance_usd}`.",
        f"- Trailing drawdown: `${funded_profile.trailing_drawdown_usd}`.",
        f"- First payout floor: `${funded_profile.first_payout_floor_usd}`.",
        f"- Risk pre-payout: `${funded_profile.risk_pre_payout_usd}`.",
        f"- Risk post-payout: `${funded_profile.risk_post_payout_usd}`.",
        "",
        "## Full History",
        "",
        f"- Filled trades: `{len(trade_df)}`.",
        f"- Payout / breach / open: `{scorecard['payout_rate']}` / `{scorecard['breach_rate']}` / `{scorecard['open_rate']}`.",
        f"- Average days to payout: `{scorecard['average_days_to_payout']}`.",
        f"- Median days to payout: `{scorecard['median_days_to_payout']}`.",
        f"- Average trades to payout: `{scorecard['average_trades_to_payout']}`.",
        f"- Average first payout amount: `${scorecard['average_first_payout_amount_usd']}`.",
        f"- EV per start: `${scorecard['ev_per_start_usd']}`.",
        "",
        "## Forecast",
        "",
        f"- By day 20: payout `{horizon20.get('payout_rate_by_horizon')}` | breach `{horizon20.get('breach_rate_by_horizon')}` | resolved `{horizon20.get('resolved_rate_by_horizon')}`.",
        f"- By day 30: payout `{horizon30.get('payout_rate_by_horizon')}` | breach `{horizon30.get('breach_rate_by_horizon')}` | resolved `{horizon30.get('resolved_rate_by_horizon')}`.",
        f"- By day 45: payout `{horizon45.get('payout_rate_by_horizon')}` | breach `{horizon45.get('breach_rate_by_horizon')}` | resolved `{horizon45.get('resolved_rate_by_horizon')}`.",
        "",
        "## Holdout",
        "",
        f"- Holdout payout / breach / open: `{holdout_scorecard['payout_rate']}` / `{holdout_scorecard['breach_rate']}` / `{holdout_scorecard['open_rate']}`.",
        f"- Holdout average days to payout: `{holdout_scorecard['average_days_to_payout']}`.",
        f"- Holdout EV per start: `${holdout_scorecard['ev_per_start_usd']}`.",
        f"- Holdout by day 20: payout `{holdout20.get('payout_rate_by_horizon')}` | breach `{holdout20.get('breach_rate_by_horizon')}` | resolved `{holdout20.get('resolved_rate_by_horizon')}`.",
        f"- Holdout by day 30: payout `{holdout30.get('payout_rate_by_horizon')}` | breach `{holdout30.get('breach_rate_by_horizon')}` | resolved `{holdout30.get('resolved_rate_by_horizon')}`.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines) + "\n")

    print("\nSummary:")
    print((output_dir / "summary.md").read_text())


if __name__ == "__main__":
    main()
