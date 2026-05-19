#!/usr/bin/env python3
"""Save GC Inversion Longs v9 GO result to main DB."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.results.export import results_to_dict, save_backtest_result

GC = get_instrument("GC")

session = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",
    entry_start="09:35",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=1.0,
    qualifying_move_atr_pct=10.0,
)

config = StrategyConfig(
    rr=3.5,
    tp1_ratio=0.2,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(session,),
    instrument=GC,
    strategy="inversion",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
    name="GC NY Inversion Longs v9 GO",
    notes="v8 + 10% qualifying sweep depth. QM=10% confirmed optimal via full sweep (0-30% tested). "
          "Beats no-gate (74.7R vs 74.4R, R/DD 14.4 vs 14.3). All 5 pipeline phases pass. "
          "250 trades, 56.8% WR, 74.7R, -5.2R DD, Sharpe 3.80, Calmar 14.45. "
          "WF efficiency 0.82, stability 0.85, hold-out 9.7R/40 trades, MC survival 82.2%.",
)

print("Loading data...")
df = load_5m_data("GC_5m.csv")
df_1m = load_1m_for_5m("GC_5m.csv")

print("Running backtest...")
trades = run_backtest_qm(df, config, start_date="2016-01-01", df_1m=df_1m)

result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
result_id = save_backtest_result(result)

m = result["summary"]
print(f"Saved: {result_id}")
print(f"Trades: {m['total_trades']}, WR: {m['win_rate']:.1%}, Net R: {m['total_r']:.1f}, DD: {m['max_drawdown_r']:.1f}")
