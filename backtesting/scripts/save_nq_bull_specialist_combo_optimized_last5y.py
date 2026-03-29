#!/usr/bin/env python3
"""Save the optimized NQ 4-leg combo 5-year package to the backtest DB."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_BE_SL,
    EXIT_EOD,
    EXIT_NAMES,
    EXIT_NO_FILL,
    EXIT_SL,
    EXIT_TP1_BE,
    EXIT_TP1_EOD,
    EXIT_TP1_TP2,
    EXIT_TP2_SINGLE,
    TradeResult,
)
from orb_backtest.results.export import save_backtest_result  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


DEFAULT_INPUT_DIR = ROOT / "data" / "results" / "nq_bull_specialist_combo_papertrade_optimized_last5y"

EXIT_NAME_TO_CODE = {name: code for code, name in EXIT_NAMES.items()}


def load_trade_results(path: Path) -> tuple[list[TradeResult], list[dict]]:
    trades: list[TradeResult] = []
    trade_dicts: list[dict] = []
    with path.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            exit_code = EXIT_NAME_TO_CODE[row["exit_type"]]
            trade = TradeResult(
                date=row["date"],
                session=row["session"],
                direction=int(float(row["direction"])),
                signal_bar=int(float(row["signal_bar"])),
                fill_bar=int(float(row["fill_bar"])),
                entry_price=float(row["entry_price"]),
                stop_price=float(row["stop_price"]),
                tp1_price=float(row["tp1_price"]),
                tp2_price=float(row["tp2_price"]),
                exit_type=exit_code,
                exit_bar=int(float(row["exit_bar"])),
                pnl_points=float(row["pnl_points"]),
                pnl_usd=float(row["pnl_usd"]),
                r_multiple=float(row["r_multiple"]),
                qty=float(row["qty"]),
                half_qty=float(row["half_qty"]),
                gap_size=float(row["gap_size"]),
                risk_points=float(row["risk_points"]),
                fill_time=row["fill_time"] or "",
                exit_time=row["exit_time"] or "",
            )
            trades.append(trade)
            trade_dicts.append(
                {
                    "date": trade.date,
                    "session": trade.session,
                    "direction": "long" if trade.direction == 1 else "short",
                    "entry_price": round(trade.entry_price, 4),
                    "stop_price": round(trade.stop_price, 4),
                    "tp1_price": round(trade.tp1_price, 4),
                    "tp2_price": round(trade.tp2_price, 4),
                    "exit_type": row["exit_type"],
                    "pnl_usd": round(trade.pnl_usd, 2),
                    "r_multiple": round(trade.r_multiple, 4),
                    "qty": trade.qty,
                    "gap_size": round(trade.gap_size, 4),
                    "risk_points": round(trade.risk_points, 4),
                    "leg_name": row["leg_name"],
                }
            )
    return trades, trade_dicts


def build_equity_curve(trades: list[TradeResult]) -> list[dict]:
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    equity_curve: list[dict] = []
    cumulative = 0.0
    for trade in filled:
        cumulative += trade.pnl_usd
        equity_curve.append(
            {
                "date": trade.date,
                "pnl_cumulative": round(cumulative, 2),
                "pnl_per_trade": round(trade.pnl_usd, 2),
            }
        )
    return equity_curve


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR))
    parser.add_argument(
        "--name",
        default="NQ 4-Leg Combo Optimized Last 5Y",
        help="Backtest name shown in dashboard",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    combo_trades_path = input_dir / "combo_trades.csv"
    package_path = input_dir / "combo_paper_trade_package.json"

    trades, trade_dicts = load_trade_results(combo_trades_path)
    metrics = compute_metrics(trades)
    equity_curve = build_equity_curve(trades)

    package = json.loads(package_path.read_text())
    funded_profile = package.get("funded_profile", {})
    scorecard = package.get("scorecard", {})
    holdout_scorecard = package.get("holdout_scorecard", {})

    result = {
        "name": args.name,
        "notes": (
            "Optimized NQ funded-account 4-leg combo, saved from the last-5-year package. "
            "Legs: bull_specialist + nq_asia + nq_asia_lsi_end2300 + nq_ny_lsi_gap3.75. "
            f"Funded payout model: challenge_fee=${funded_profile.get('challenge_fee')}, "
            f"start_balance=${funded_profile.get('starting_balance_usd')}, "
            f"trail_dd=${funded_profile.get('trailing_drawdown_usd')}, "
            f"risk_pre=${funded_profile.get('risk_pre_payout_usd')}, "
            f"risk_post=${funded_profile.get('risk_post_payout_usd')}. "
            f"Payout/Breach/Open={scorecard.get('payout_rate')}/{scorecard.get('breach_rate')}/{scorecard.get('open_rate')}. "
            f"Holdout payout/breach={holdout_scorecard.get('payout_rate')}/{holdout_scorecard.get('breach_rate')}."
        ),
        "config": {
            "instrument": "NQ",
            "strategy": "combo",
            "direction_filter": "long",
            "rr": None,
            "tp1_ratio": None,
            "risk_usd": 5000.0,
            "atr_length": None,
            "asia_entry_window": "20:15-23:00",
            "asia_flat_window": "00:00-07:00",
            "ny_entry_window": "09:35-15:30",
            "ny_flat_window": "15:50-16:00",
            "combo_legs": [
                "bull_specialist",
                "nq_asia",
                "nq_asia_lsi_end2300",
                "nq_ny_lsi_gap3.75",
            ],
            "combo_source_dir": str(input_dir),
            "combo_kind": "funded_account_route",
        },
        "summary": metrics,
        "equity_curve": equity_curve,
        "trades": trade_dicts,
    }

    result_id = save_backtest_result(result)
    print(result_id)


if __name__ == "__main__":
    main()
