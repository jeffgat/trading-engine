#!/usr/bin/env python3
"""NQ NY ORB backtest matching FAST:NQ_NY exec config with user overrides.

From exec config: ORB 09:30-09:45, Entry 09:45-12:00, Flat 15:30-16:00,
Gap ATR% 2.5%, Risk $200, MNQ point value $2, max single risk $300.

User overrides: R:R=2, TP1=0.5, Stop ATR%=15%, both directions, no skip days.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

def main():
    # MNQ for sizing ($2/pt), but NQ data
    inst = get_instrument("MNQ")

    session = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:45",
        entry_start="09:45",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=15.0,       # user override (was 7%)
        min_gap_atr_pct=2.5,     # from exec config
    )

    config = StrategyConfig(
        rr=2.0,                  # user override (was 3.5)
        tp1_ratio=0.5,           # user override (was 0.4)
        atr_length=14,           # default
        risk_usd=200.0,          # from exec config
        min_qty=1,
        sessions=(session,),
        instrument=inst,
        direction_filter="both", # both directions
        name="NQ NY Exec Config RR2 Stop15",
    )

    # Load NQ data (use NQ 5m data, MNQ sizing)
    data_file = DATA_DIR / "NQ_5m.parquet"
    if not data_file.exists():
        data_file = DATA_DIR / "NQ_5m.csv"

    print("=" * 70)
    print("NQ NY ORB — Exec Config Test (MNQ sizing)")
    print("=" * 70)
    print(f"  R:R = {config.rr}, TP1 = {config.tp1_ratio}, Stop ATR% = {session.stop_atr_pct}%")
    print(f"  Gap ATR% = {session.min_gap_atr_pct}%, ATR length = {config.atr_length}")
    print(f"  Risk = ${config.risk_usd}, Direction = {config.direction_filter}")
    print(f"  ORB = {session.orb_start}-{session.orb_end}, Entry = {session.entry_start}-{session.entry_end}")
    print(f"  Flat = {session.flat_start}-{session.flat_end}")
    print(f"  No skip days")
    print()

    t0 = time.time()
    print(f"Loading data: {data_file.name}")
    df = load_5m_data(str(data_file), start="2021-01-01", end="2026-01-01")
    print(f"  {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()}) [{time.time()-t0:.1f}s]")
    print()

    t0 = time.time()
    trades = run_backtest(df, config, start_date="2021-01-01")
    elapsed = time.time() - t0

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"Trades: {len(filled)} filled / {len(trades)} total [{elapsed:.1f}s]")
    print()

    metrics = compute_metrics(trades)

    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"  Trades:           {metrics['total_trades']}")
    print(f"  Win Rate:         {metrics['win_rate']:.1%}")
    print(f"  Total R:          {metrics['total_r']:.1f}")
    print(f"  Avg R:            {metrics['avg_r']:.3f}")
    print(f"  Profit Factor:    {metrics['profit_factor']:.2f}")
    print(f"  Sharpe:           {metrics['sharpe_ratio']:.3f}")
    print(f"  Sortino:          {metrics['sortino_ratio']:.3f}")
    print(f"  Calmar:           {metrics['calmar_ratio']:.2f}")
    print(f"  Max DD:           {metrics['max_drawdown_r']:.1f}R")
    print(f"  Max Consec Wins:  {metrics['max_consecutive_wins']}")
    print(f"  Max Consec Loss:  {metrics['max_consecutive_losses']}")

    # Exit breakdown
    print(f"\n  Exit Breakdown:")
    for exit_type, count in sorted(metrics.get("exit_breakdown", {}).items()):
        print(f"    {exit_type:<20} {count:>5}")

    # R by year
    if metrics.get("r_by_year"):
        print(f"\n  R by Year:")
        for year, r in sorted(metrics["r_by_year"].items()):
            print(f"    {year}: {r:>+8.1f}R")

    # R by month
    if metrics.get("r_by_month"):
        print(f"\n  R by Month:")
        for month, r in sorted(metrics["r_by_month"].items()):
            print(f"    {month}: {r:>+8.1f}R")

    # Save to DB (dual-write: local + remote)
    result_dict = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result_dict)
    print(f"\n  Saved to DB: {result_id}")
    print("=" * 70)


if __name__ == "__main__":
    main()
