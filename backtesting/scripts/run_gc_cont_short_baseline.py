#!/usr/bin/env python3
"""GC continuation shorts — baseline with generic defaults.

Re-optimization from scratch. Uses standard StrategyConfig/SessionConfig
defaults with direction_filter="short" to establish whether a structural
edge exists before any parameter tuning.

Pass criteria: >100 trades AND PF >1.0 AND median stop >= 10 ticks.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = GC
START_DATE = "2016-01-01"
DATA_YEARS = 10.15
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")


def median_stop_ticks(trades, instrument):
    """Compute median stop distance in ticks for filled trades."""
    stops = [t.risk_points / instrument.min_tick for t in trades if t.exit_type != EXIT_NO_FILL]
    return median(stops) if stops else 0.0


# ── Session config (generic defaults) ───────────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",        # 15m ORB (default)
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=7.5,
    min_gap_atr_pct=2.25,
    max_gap_atr_pct=0.0,    # off
)

BASELINE = StrategyConfig(
    rr=2.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=14,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=INSTRUMENT,
    strategy="continuation",
    direction_filter="short",
    use_bar_magnifier=True,
    half_days=HALF_DAYS,
    excluded_dates=FOMC_DATES,
    name="GC NY Cont Short Baseline v2",
    notes="Re-optimization from scratch with generic defaults.",
)

# ── Load data ────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  5m: {len(df_5m):,} bars")
print(f"  1m: {len(df_1m):,} bars" if df_1m is not None else "  1m: not found")
print(f"  1s: {len(df_1s):,} bars" if df_1s is not None else "  1s: not found")
print(f"  Loaded in {time.time() - t0:.1f}s\n")

# ── Run backtest ─────────────────────────────────────────────────────────────

print("Running baseline backtest...")
t0 = time.time()
trades = run_backtest(df_5m, BASELINE, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
elapsed = time.time() - t0
print(f"  Completed in {elapsed:.1f}s\n")

# ── Metrics ──────────────────────────────────────────────────────────────────

metrics = compute_metrics(filled)
med_stop = median_stop_ticks(filled, INSTRUMENT)

# Yearly breakdown
yearly = defaultdict(list)
for t in filled:
    yearly[t.date[:4]].append(t.r_multiple)

# Count negative full calendar years (exclude current partial year 2026)
current_year = "2026"
neg_years = sum(
    1 for yr, rs in yearly.items()
    if yr != current_year and sum(rs) < 0
)

nr = metrics["total_r"]
dd = metrics["max_drawdown_r"]
n_full_years = len([yr for yr in yearly if yr != current_year])
avg_annual = nr / DATA_YEARS if DATA_YEARS > 0 else 0
calmar = abs(avg_annual / dd) if dd < 0 else 999.0

print("=" * 80)
print("BASELINE RESULTS: GC NY Continuation Shorts")
print("=" * 80)
print(f"  Trades:          {len(filled)}")
print(f"  Win Rate:        {metrics['win_rate']:.1%}")
print(f"  Profit Factor:   {metrics['profit_factor']:.2f}")
print(f"  Net R:           {nr:.1f}")
print(f"  Avg Annual R:    {avg_annual:.1f}")
print(f"  Max DD (R):      {dd:.1f}")
print(f"  Calmar:          {calmar:.2f}")
print(f"  Sharpe:          {metrics['sharpe_ratio']:.3f}")
print(f"  Median Stop:     {med_stop:.1f} ticks")
print(f"  Neg Full Years:  {neg_years}")
print()

# Exit type breakdown
print("Exit Breakdown:")
from collections import Counter
exit_counts = Counter(t.exit_type for t in filled)
for etype, count in sorted(exit_counts.items()):
    name = EXIT_NAMES.get(etype, f"type_{etype}")
    pct = count / len(filled) * 100
    print(f"  {name:<20} {count:>5} ({pct:>5.1f}%)")
print()

# R by year
print("R by Year:")
for yr in sorted(yearly.keys()):
    yr_r = sum(yearly[yr])
    n = len(yearly[yr])
    marker = " <-- NEGATIVE" if yr != current_year and yr_r < 0 else ""
    partial = " (partial)" if yr == current_year else ""
    print(f"  {yr}: {yr_r:>+8.1f}R  ({n} trades){partial}{marker}")
print()

# ── Pass/Fail ────────────────────────────────────────────────────────────────

pass_trades = len(filled) > 100
pass_pf = metrics["profit_factor"] > 1.0
pass_stop = med_stop >= 10.0

print("PASS CRITERIA:")
print(f"  Trades > 100:      {'PASS' if pass_trades else 'FAIL'} ({len(filled)})")
print(f"  PF > 1.0:          {'PASS' if pass_pf else 'FAIL'} ({metrics['profit_factor']:.2f})")
print(f"  Med stop >= 10t:   {'PASS' if pass_stop else 'FAIL'} ({med_stop:.1f})")
print()

if pass_trades and pass_pf and pass_stop:
    print(">>> BASELINE PASS — proceed to Step 2 (Variable Sweeps)")
    print(f"    Initial anchor: rr={BASELINE.rr}, tp1={BASELINE.tp1_ratio}, "
          f"ATR={BASELINE.atr_length}, stop={GC_NY.stop_atr_pct}%, "
          f"gap={GC_NY.min_gap_atr_pct}%")
else:
    print(">>> BASELINE FAIL — record as NO-GO in learnings")
