#!/usr/bin/env python3
"""Build the routed paper-trade package for the shortlisted NQ bull specialist.

This step turns the round-2 winner into an actual deployment route:
- trade only the shortlisted bull specialist
- only on bull regime days
- skip low-confidence days
- export an eligibility calendar, routed trade ledger, and prop scorecard
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

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.prop_regime_specialist import (
    DEFAULT_HOLDOUT_START,
    PropFirmProfile,
    apply_bull_hh_hl_vwap_gate,
    build_nq_ny_regime_calendar,
    build_prop_scorecard,
    evaluate_specialist,
    filter_trades_by_low_confidence,
    filter_trades_by_regime,
    simulate_account_attempts,
    trading_dates_from_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import EXIT_NAMES, EXIT_NO_FILL, TradeResult, run_backtest


ROUND2_DIR = ROOT / "data" / "results" / "nq_prop_regime_specialists_round2"
OUTPUT_DIR = ROOT / "data" / "results" / "nq_prop_regime_specialists_papertrade_bull"
SPECIALIST_NAME = "nq_ny_bull_long_r11_hh_hl_vwap__no_low_confidence"


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
        notes="Bull specialist paper-trade package anchor.",
    )


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def load_selected_candidate(path: Path) -> dict:
    payload = json.loads(path.read_text())
    shortlist = payload.get("paper_trade_shortlist", [])
    for item in shortlist:
        if item.get("specialist_name") == SPECIALIST_NAME:
            return item
    raise ValueError(f"Could not find shortlisted candidate {SPECIALIST_NAME!r} in {path}")


def trades_to_frame(trades: list[TradeResult]) -> pd.DataFrame:
    rows = []
    for trade in trades:
        rows.append(
            {
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


def build_eligibility_calendar(regime_calendar: pd.DataFrame) -> pd.DataFrame:
    cal = regime_calendar.copy()
    cal["date"] = pd.to_datetime(cal["date"])
    cal["paper_trade_active"] = (
        cal["warmup_ok"] & ~cal["low_confidence"] & (cal["regime"] == "bull")
    )
    cal["route_reason"] = "inactive"
    cal.loc[~cal["warmup_ok"], "route_reason"] = "warmup"
    cal.loc[cal["low_confidence"], "route_reason"] = "low_confidence"
    cal.loc[cal["warmup_ok"] & ~cal["low_confidence"] & (cal["regime"] != "bull"), "route_reason"] = (
        "not_bull_regime"
    )
    cal.loc[cal["paper_trade_active"], "route_reason"] = "bull_specialist_active"
    return cal


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default=None)
    parser.add_argument("--holdout-start", default=DEFAULT_HOLDOUT_START)
    parser.add_argument("--output-dir", default=str(OUTPUT_DIR))
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    candidate = load_selected_candidate(ROUND2_DIR / "selected_candidates.json")
    profile = PropFirmProfile()

    print("NQ Bull Specialist Paper-Trade Package")
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
    eligibility_calendar = build_eligibility_calendar(regime_calendar)

    print("\nRunning bull specialist anchor...", flush=True)
    bull_config = make_nq_ny_long_r11_config()
    trades = run_backtest(
        df_5m,
        bull_config,
        start_date=args.start,
        end_date=args.end,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    trades = apply_dow_filter(trades, set(bull_config.excluded_days))
    trades = apply_bull_hh_hl_vwap_gate(trades, df_5m, bull_config.sessions[0])

    print("\nApplying routed paper-trade policy...", flush=True)
    trades = filter_trades_by_low_confidence(trades, regime_calendar, include_low_confidence=False)
    trades = filter_trades_by_regime(trades, regime_calendar, include={"bull"})
    trading_dates = [
        pd.Timestamp(d).strftime("%Y-%m-%d")
        for d in eligibility_calendar.loc[eligibility_calendar["paper_trade_active"], "date"].tolist()
    ]

    readout = evaluate_specialist(
        specialist_name="nq_ny_bull_long_r11_hh_hl_vwap__bull_only_no_low_confidence",
        target_regime="bull",
        trades=trades,
        regime_calendar=regime_calendar,
        holdout_start=args.holdout_start,
    )
    outcomes = simulate_account_attempts(
        specialist_name=readout["specialist_name"],
        trades=trades,
        trading_dates=trading_dates,
        profile=profile,
        risk_per_r_usd=bull_config.risk_usd,
    )
    scorecard = build_prop_scorecard(outcomes, profile)

    trade_df = trades_to_frame([t for t in trades if t.exit_type != EXIT_NO_FILL])
    trade_df.to_csv(output_dir / "paper_trade_trades.csv", index=False)
    eligibility_calendar.to_csv(output_dir / "eligibility_calendar.csv", index=False)
    outcomes.to_csv(output_dir / "account_outcomes.csv", index=False)

    recent_cutoff = pd.Timestamp(args.holdout_start)
    recent_eligibility = eligibility_calendar[eligibility_calendar["date"] >= recent_cutoff].copy()
    recent_eligibility.to_csv(output_dir / "eligibility_calendar_holdout.csv", index=False)
    if not trade_df.empty:
        trade_df[pd.to_datetime(trade_df["date"]) >= recent_cutoff].to_csv(
            output_dir / "paper_trade_trades_holdout.csv",
            index=False,
        )

    write_json(
        output_dir / "paper_trade_package.json",
        {
            "selected_candidate_from_round2": candidate,
            "paper_trade_route": {
                "target_regime": "bull",
                "include_low_confidence": False,
                "route_name": "bull_only_no_low_confidence",
                "trade_only_when": [
                    "round-2 shortlisted bull specialist signal fires",
                    "daily regime is bull",
                    "day is not low_confidence",
                ],
                "kill_switch": {
                    "disable_after_consecutive_breaches": 2,
                    "disable_after_rolling_20_trades_negative_expectancy": True,
                    "disable_after_live_drawdown_exceeds_bootstrap_p95_r": scorecard["bootstrap"].get("drawdown_p95_r"),
                    "re_enable_after_fresh_paper_trades": 20,
                },
            },
            "config": asdict(bull_config),
            "profile": asdict(profile),
            "readout": readout,
            "scorecard": scorecard,
        },
    )

    summary_lines = [
        "# NQ Bull Specialist Paper-Trade Package",
        "",
        "## Source Candidate",
        "",
        f"- Round-2 shortlist source: `{candidate['specialist_name']}`.",
        f"- Round-2 route policy: `{candidate['route_policy']}`.",
        "",
        "## Deployment Route",
        "",
        "- Trade only the bull specialist.",
        "- Trade only on `bull` regime days.",
        "- Skip all `low_confidence` days.",
        "",
        "## Routed Results",
        "",
        f"- Routed full-history trades: `{readout['full_history']['total_trades']}`.",
        f"- Routed in-regime avg R: `{readout['in_regime']['avg_r']}`.",
        f"- Routed holdout in-regime avg R: `{readout['holdout_in_regime']['avg_r']}`.",
        f"- EV/attempt: `{scorecard['ev_per_attempt']}`.",
        f"- First payout rate: `{scorecard['first_payout_rate']}`.",
        f"- Average days to payout: `{scorecard['average_days_to_payout']}`.",
        "",
        "## Kill Switch",
        "",
        "- Disable after 2 consecutive breached account attempts.",
        "- Disable after rolling 20 filled trades turn negative expectancy.",
        f"- Disable after live drawdown exceeds `{scorecard['bootstrap'].get('drawdown_p95_r')}` R.",
        "- Re-enable only after 20 fresh paper trades return to positive expectancy.",
    ]
    (output_dir / "summary.md").write_text("\n".join(summary_lines))

    print("\nDone.")
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
