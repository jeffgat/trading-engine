#!/usr/bin/env python3
"""Step 1: Baseline — GC NY Continuation Longs (fresh re-optimization).

Conservative defaults from GC-optimization skill Phase 1.
This establishes the initial anchor for variable sweeps.

Pass criteria: >100 trades AND profit factor >1.0.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

# ── Config ────────────────────────────────────────────────────────────────────

START_DATE = "2016-01-01"
DATA_YEARS = 10.15  # 2016-01 to 2026-02

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",      # 5m ORB (default starting point)
    entry_start="09:35",
    entry_end="12:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=4.5,
    min_gap_atr_pct=2.5,
)

CONFIG = StrategyConfig(
    rr=4.0,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=50,          # conservative default — variable sweeps will improve
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=FOMC_DATES,
    name="GC NY Cont Long Baseline",
)

# ── Data ──────────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(GC.data_file, start=START_DATE)
df_1m = load_1m_for_5m(GC.data_file, start=START_DATE)
df_1s = load_1s_for_5m(GC.data_file, start=START_DATE)
print(f"  5m: {len(df_5m):,} bars")
print(f"  1m: {len(df_1m):,} bars" if df_1m is not None else "  1m: not found")
print(f"  1s: {len(df_1s):,} bars" if df_1s is not None else "  1s: not found")
print(f"  Loaded in {time.time() - t0:.1f}s")

# ── Run backtest ──────────────────────────────────────────────────────────────

print("\nRunning baseline backtest...")
t0 = time.time()
trades = run_backtest(df_5m, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
elapsed = time.time() - t0

filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
print(f"  {len(filled)} filled trades ({len(trades)} signals) in {elapsed:.1f}s")

# ── Metrics ───────────────────────────────────────────────────────────────────

m = compute_metrics(trades)

print("\n" + "=" * 70)
print("GC NY CONTINUATION LONGS — BASELINE")
print("=" * 70)

print(f"\n{'Metric':<25} {'Value':>12}")
print("-" * 40)
print(f"{'Trades':<25} {m['total_trades']:>12}")
print(f"{'Win Rate':<25} {m['win_rate']:>11.1%}")
print(f"{'Profit Factor':<25} {m['profit_factor']:>12.2f}")
print(f"{'Sharpe':<25} {m['sharpe_ratio']:>12.3f}")
print(f"{'Net R':<25} {m['total_r']:>12.1f}")
print(f"{'R/yr':<25} {m['total_r']/DATA_YEARS:>12.1f}")
print(f"{'Max DD (R)':<25} {m['max_drawdown_r']:>12.1f}")
print(f"{'Calmar':<25} {m['calmar_ratio']:>12.2f}")
print(f"{'Avg R':<25} {m['avg_r']:>12.3f}")
print(f"{'Avg Win R':<25} {m['avg_win_r']:>12.3f}")
print(f"{'Avg Loss R':<25} {m['avg_loss_r']:>12.3f}")
print(f"{'Max Consec Losses':<25} {m['max_consecutive_losses']:>12}")

# R by year
print(f"\n{'Year':<8} {'R':>8}")
print("-" * 18)
r_by_year = m.get("r_by_year", {})
neg_full_years = 0
for year, r_val in sorted(r_by_year.items()):
    flag = " ←NEG" if r_val < 0 else ""
    print(f"{year:<8} {r_val:>+8.1f}{flag}")
    # Count negative FULL calendar years (exclude 2026 partial)
    if r_val < 0 and year != "2026":
        neg_full_years += 1
print(f"\nNegative full years: {neg_full_years}")

# Exit breakdown
print(f"\n{'Exit Type':<20} {'Count':>8} {'Pct':>8}")
print("-" * 38)
for exit_type, count in sorted(m["exit_breakdown"].items(), key=lambda x: -x[1]):
    pct = count / m["total_signals"] * 100
    print(f"{exit_type:<20} {count:>8} {pct:>7.1f}%")

# ── Pass/Fail ─────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("BASELINE PASS CRITERIA")
print("=" * 70)
trades_pass = m["total_trades"] > 100
pf_pass = m["profit_factor"] > 1.0
print(f"  Trades > 100:      {'PASS' if trades_pass else 'FAIL'} ({m['total_trades']})")
print(f"  Profit Factor > 1: {'PASS' if pf_pass else 'FAIL'} ({m['profit_factor']:.2f})")

if trades_pass and pf_pass:
    print("\n✓ BASELINE PASSED — proceed to Step 2 (Variable Sweeps)")
    print(f"\nInitial anchor config:")
    print(f"  stop_atr_pct  = {GC_NY.stop_atr_pct}")
    print(f"  rr            = {CONFIG.rr}")
    print(f"  tp1_ratio     = {CONFIG.tp1_ratio}")
    print(f"  atr_length    = {CONFIG.atr_length}")
    print(f"  min_gap_atr   = {GC_NY.min_gap_atr_pct}")
    print(f"  max_gap_pts   = {GC_NY.max_gap_points}")
    print(f"  ORB           = {GC_NY.orb_start}-{GC_NY.orb_end}")
    print(f"  entry_end     = {GC_NY.entry_end}")
    print(f"  flat_start    = {GC_NY.flat_start}")
    print(f"  direction     = {CONFIG.direction_filter}")
    print(f"  FOMC excluded = True")
else:
    print("\n✗ BASELINE FAILED — record as NO-GO in learnings")
