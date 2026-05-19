#!/usr/bin/env python3
"""Save GC R6 pipeline results to the main DB.

Saves two runs:
  1. Full-history IS (base config, stop=4.0%)
  2. Hold-out OOS 2025-2026 (WF mode params, stop=3.5%)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result

GC = get_instrument("GC")

GC_NY_BASE = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="11:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.0,
    min_gap_atr_pct=2.5,
)

BASE_CONFIG = StrategyConfig(
    rr=4.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=16,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_BASE,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
    name="GC NY R6 Full History IS",
    notes=(
        "R6 anchor config (grid sweep winner). stop=4.0% ATR, rr=4.5, min_gap=2.5%, "
        "tp1=0.5, ATR 16, 10m ORB, entry→11:00, FOMC excluded. "
        "Phase 1 of robust pipeline: Calmar 14.10, Sharpe 2.570, 0 neg years."
    ),
)

# WF mode params: stop=3.5% (mode across 5 folds), all others identical
GC_NY_MODE = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="11:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=3.5,
    min_gap_atr_pct=2.5,
)

MODE_CONFIG = StrategyConfig(
    rr=4.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=16,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY_MODE,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
    name="GC NY R6 Hold-Out OOS 2025-2026",
    notes=(
        "R6 mode config from WF stability analysis (stop=3.5% ATR — WF mode vs grid anchor 4.0%). "
        "Hold-out: 2025-01-01 to 2026-02-15. "
        "Phase 4 result: 63 trades, Sharpe 2.795, PF 1.51, 19.3R, 0 neg years. MC survival 95.3%."
    ),
)

print("Loading data...")
df    = load_5m_data("GC_5m.csv")
df_1m = load_1m_for_5m("GC_5m.csv")
df_1s = load_1s_for_5m("GC_5m.csv")
print(f"  {len(df):,} 5m bars loaded\n")

# ── Run 1: full history IS ────────────────────────────────────────────────────
print("Running Phase 1 (full history IS, stop=4.0%)...")
trades_is = run_backtest(df, BASE_CONFIG, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
result_is = results_to_dict(trades_is, BASE_CONFIG, include_trades=True, include_equity_curve=True)
id_is = save_backtest_result(result_is)
print(f"  Saved: {id_is}")
print(f"  Trades: {result_is['summary']['total_trades']} | "
      f"Calmar: {result_is['summary']['calmar_ratio']:.2f} | "
      f"Sharpe: {result_is['summary']['sharpe_ratio']:.3f}\n")

# ── Run 2: hold-out OOS 2025-2026 (mode params) ───────────────────────────────
print("Running Phase 4 (hold-out OOS 2025-2026, stop=3.5%)...")
df_ho    = df.loc["2024-11-01":]
df_1m_ho = df_1m.loc["2024-11-01":] if df_1m is not None else None
df_1s_ho = df_1s.loc["2024-11-01":] if df_1s is not None else None
trades_ho = run_backtest(df_ho, MODE_CONFIG, start_date="2025-01-01", df_1m=df_1m_ho, df_1s=df_1s_ho)
result_ho = results_to_dict(trades_ho, MODE_CONFIG, include_trades=True, include_equity_curve=True)
id_ho = save_backtest_result(result_ho)
print(f"  Saved: {id_ho}")
print(f"  Trades: {result_ho['summary']['total_trades']} | "
      f"Sharpe: {result_ho['summary']['sharpe_ratio']:.3f} | "
      f"PF: {result_ho['summary']['profit_factor']:.2f} | "
      f"Net R: {result_ho['summary']['total_r']:.1f}R\n")

print("Done.")
