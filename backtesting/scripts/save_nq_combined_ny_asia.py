#!/usr/bin/env python3
"""Run and save NQ Combined: NY R20 + Asia R9 Restart.

Runs both strategies independently (different global params), merges trade lists
chronologically, and saves as a single combined DB entry.

NY R20:   stop=8.75% rr=2.625 gap=2.25% tp1=0.3, ORB=20m, ATR=12, both, ICF=OFF
Asia R9:  stop=4.0% rr=3.0 gap=0.90% tp1=0.6, ORB=15m, ATR=5, long, excl-Tue, ICF=ON

Combined (2016-2026): ~2,664 trades, ~388.7R, 0 negative full years.
"""

import sys
import time

import numpy as np

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter, TUE
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics


def make_ny_config():
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=8.75,
        min_gap_atr_pct=2.25,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=2.625,
        tp1_ratio=0.3,
        atr_length=12,
    )


def make_asia_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:15",
        entry_start="20:15",
        entry_end="22:30",
        flat_start="04:00",
        flat_end="07:00",
        stop_atr_pct=4.0,
        min_gap_atr_pct=0.90,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
    )


def main():
    print("NQ Combined: NY R20 + Asia R9 Restart")
    print("=" * 60)

    # ── Load data once ─────────────────────────────────────────────────────
    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    start_date = "2016-01-01"

    # ── Run NY R20 ─────────────────────────────────────────────────────────
    print("\nRunning NY R20 (both, rr=2.625, stop=8.75%, ATR=12)...")
    ny_config = make_ny_config()
    ny_trades = run_backtest(df_5m, ny_config, start_date=start_date, df_1m=df_1m, df_1s=df_1s)

    ny_m = compute_metrics(ny_trades)
    print(f"  NY: {ny_m['total_trades']} trades, {ny_m['win_rate']:.1%} WR, "
          f"{ny_m['total_r']:.1f}R, DD {ny_m['max_drawdown_r']:.1f}R, "
          f"Calmar {ny_m['calmar_ratio']:.2f}")

    # ── Run Asia R9 Restart + DOW filter ───────────────────────────────────
    print("\nRunning Asia R9 Restart (long, rr=3.0, stop=4.0%, ATR=5, excl-Tue, ICF)...")
    asia_config = make_asia_config()
    asia_trades = run_backtest(df_5m, asia_config, start_date=start_date, df_1m=df_1m, df_1s=df_1s)
    asia_trades = apply_dow_filter(asia_trades, {TUE})

    asia_m = compute_metrics(asia_trades)
    print(f"  Asia: {asia_m['total_trades']} trades, {asia_m['win_rate']:.1%} WR, "
          f"{asia_m['total_r']:.1f}R, DD {asia_m['max_drawdown_r']:.1f}R, "
          f"Calmar {asia_m['calmar_ratio']:.2f}")

    # ── Merge chronologically ──────────────────────────────────────────────
    all_trades = ny_trades + asia_trades
    all_trades.sort(key=lambda t: t.date)

    combined_m = compute_metrics(all_trades)

    print("\n" + "=" * 60)
    print("COMBINED METRICS")
    print("=" * 60)
    print(f"  Trades: {combined_m['total_trades']}")
    print(f"  Win Rate: {combined_m['win_rate']:.1%}")
    print(f"  PF: {combined_m['profit_factor']:.2f}")
    print(f"  Sharpe: {combined_m['sharpe_ratio']:.2f}")
    print(f"  Net R: {combined_m['total_r']:.1f}")
    print(f"  Avg R/yr: {combined_m['total_r'] / 10:.1f}")
    print(f"  Max DD: {combined_m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {combined_m['calmar_ratio']:.2f}")

    if "r_by_year" in combined_m:
        years = sorted(combined_m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")
        neg_years = [yr for yr, r in years if r < 0 and yr not in ("2026",)]
        print(f"  Negative full years: {len(neg_years)}")

    # ── Save combined result ───────────────────────────────────────────────
    # Build a combined config that captures both sessions' params
    combined_config = StrategyConfig(
        sessions=(make_ny_config().sessions[0], make_asia_config().sessions[0]),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=0.0,  # placeholder — per-session rr differs
        tp1_ratio=0.0,  # placeholder — per-session tp1 differs
        atr_length=0,  # placeholder — per-session ATR differs
        name="NQ NY+Asia Combined (R20 + R9 Restart Final)",
        notes=(
            "Combined NQ: NY R20 (both, rr=2.625, tp1=0.3, stop=8.75%, gap=2.25%, "
            "ATR=12, ORB=20m, entry<=15:30, ICF=OFF) + "
            "Asia R9 Restart (long, rr=3.0, tp1=0.6, stop=4.0%, gap=0.90%, "
            "ATR=5, ORB=15m, entry<=22:30, flat=04:00, excl-Tue, ICF=ON, "
            "max_gap_pts=75). "
            "Both GO from robust pipeline. Trades merged chronologically. "
            "NY DB: bt-nq-ny-r20-final-fa2e40. "
            "Asia DB: bt-nq-asia-cont-long-2016-2026-final-r9-res-4489d8."
        ),
    )

    result = results_to_dict(
        all_trades, combined_config,
        include_trades=True, include_equity_curve=True,
    )
    result_id = save_backtest_result(result)

    print(f"\n  Saved as: {result_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
