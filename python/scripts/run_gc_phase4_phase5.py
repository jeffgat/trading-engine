#!/usr/bin/env python3
"""GC Robust Pipeline — Phases 4 & 5 only (reusing WF results from Phase 2).

WF mode params: rr=4.5, tp1=0.5, stop=3.5%, min_gap=2.5%
"""

import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

GC_NY = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="11:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.0, min_gap_atr_pct=2.5, max_gap_points=25.0,
)

BASE = StrategyConfig(
    rr=4.5, tp1_ratio=0.5, risk_usd=5000.0, atr_length=16,
    min_qty=1.0, qty_step=1.0, sessions=(GC_NY,), instrument=GC,
    strategy="continuation", direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
)

print("Loading data...")
df = load_5m_data("GC_5m.csv")
df_1m = load_1m_for_5m("GC_5m.csv")
df_1s = load_1s_for_5m("GC_5m.csv")
print(f"  5m={len(df):,}  1m={len(df_1m):,}  1s={len(df_1s):,}")

# ── Phase 4: Hold-out OOS ────────────────────────────────────────────────────
print()
print("=" * 70)
print("  PHASE 4: HOLD-OUT OOS (2025-01-01 → 2026-02-19)")
print("=" * 70)
print("  WF Mode params: rr=4.5 | tp1=0.5 | stop=3.5% | min_gap=2.5%")
print()

holdout_cfg = with_overrides(BASE, rr=4.5, tp1_ratio=0.5,
                             ny_stop_atr_pct=3.5, ny_min_gap_atr_pct=2.5)

holdout_df = df.loc["2024-11-01":]
holdout_1m = df_1m.loc["2024-11-01":]
holdout_1s = df_1s.loc["2024-11-01":]

t0 = time.time()
trades = run_backtest(holdout_df, holdout_cfg, start_date="2025-01-01",
                      df_1m=holdout_1m, df_1s=holdout_1s)
m = compute_metrics(trades)
print(f"  Completed in {time.time() - t0:.1f}s")
print(f"  Signals: {m['total_signals']} | Filled: {m['total_trades']}")
print()
print(f"  Net R:    {m['total_r']:.1f}R")
print(f"  Win Rate: {m['win_rate']:.1%}")
print(f"  Sharpe:   {m['sharpe_ratio']:.3f}")
print(f"  PF:       {m['profit_factor']:.2f}")
print(f"  Max DD:   {m['max_drawdown_r']:.1f}R  [INFO]")
print(f"  Avg R:    {m['avg_r']:.3f}")
print()

rby = m.get("r_by_year", {})
for y in sorted(rby):
    print(f"    {y}: {rby[y]:>8.1f}R")

p4_pass = (m["total_trades"] >= 40 and m["sharpe_ratio"] > 0.3 and
           m["profit_factor"] > 1.0 and m["total_r"] > 0)

print()
checks = [
    ("Trades", m["total_trades"], ">= 40", m["total_trades"] >= 40),
    ("Sharpe", f"{m['sharpe_ratio']:.3f}", "> 0.3", m["sharpe_ratio"] > 0.3),
    ("PF", f"{m['profit_factor']:.2f}", "> 1.0", m["profit_factor"] > 1.0),
    ("Net R", f"{m['total_r']:.1f}", "> 0", m["total_r"] > 0),
]
for label, val, thresh, passed in checks:
    status = "PASS" if passed else "** FAIL **"
    print(f"  {label:<25s} {str(val):>10s} {thresh:>12s} {status:>10s}")
print(f"\n  Phase 4 result: {'PASS' if p4_pass else 'FAIL'}")

# ── Phase 5: Monte Carlo ─────────────────────────────────────────────────────
print()
print("=" * 70)
print("  PHASE 5: MONTE CARLO SURVIVAL")
print("=" * 70)

# Run full-history backtest with WF mode params for MC trade sample
mc_cfg = holdout_cfg  # same WF mode params
t0 = time.time()
mc_trades = run_backtest(df, mc_cfg, start_date="2016-01-01",
                         df_1m=df_1m, df_1s=df_1s)
filled = [t for t in mc_trades if t.exit_type != EXIT_NO_FILL]
r_arr = np.array([t.r_multiple for t in filled])
n = len(r_arr)

MC_SIMS = 5000
MC_RUIN = 25.0

print(f"  Trades: {n} | Sims: {MC_SIMS:,} | Ruin: -{MC_RUIN}R")

rng = np.random.default_rng(42)
paths = r_arr[rng.integers(0, n, size=(MC_SIMS, n))]
equity = np.cumsum(paths, axis=1)
final = equity[:, -1]
max_dd = np.min(equity - np.maximum.accumulate(equity, axis=1), axis=1)

survival = float(np.mean(max_dd >= -MC_RUIN))


def p(arr, pct):
    return float(np.percentile(arr, pct))


print(f"  Completed in {time.time() - t0:.1f}s")
print()
print(f"  Final PnL (R):  p5={p(final,5):.1f}  p25={p(final,25):.1f}  "
      f"p50={p(final,50):.1f}  p75={p(final,75):.1f}  p95={p(final,95):.1f}")
print(f"  Max DD (R):     p5={p(max_dd,5):.1f}  p25={p(max_dd,25):.1f}  "
      f"p50={p(max_dd,50):.1f}  p75={p(max_dd,75):.1f}  p95={p(max_dd,95):.1f}")

band = ("STRONG" if survival >= 0.80 else
        "ACCEPTABLE" if survival >= 0.70 else
        "CONDITIONAL" if survival >= 0.50 else "NO-GO")
p5_pass = survival >= 0.60

print(f"\n  Survival at -{MC_RUIN}R: {survival:.1%} ({band})")
print(f"  Threshold: >= 60%")
print(f"\n  Phase 5 result: {'PASS' if p5_pass else 'FAIL'}")

# ── Final Verdict ─────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("  FINAL VERDICT (all 5 phases)")
print("=" * 70)
print(f"  Phase 1 (Structural):    PASS")
print(f"  Phase 2 (Walk-Forward):  PASS  (WF Eff=0.33, Stability=0.95)")
print(f"  Phase 3 (Prop Firm):     CAUTION  (11.7R/yr vs 12.0 threshold)")
print(f"  Phase 4 (Hold-Out):      {'PASS' if p4_pass else 'FAIL'}")
print(f"  Phase 5 (Monte Carlo):   {'PASS' if p5_pass else 'FAIL'}  ({survival:.1%} survival, {band})")
print()
if p4_pass and p5_pass:
    if band in ("STRONG", "ACCEPTABLE"):
        print("  >>> CONDITIONAL GO — Phase 3 marginal (11.7 vs 12.0 threshold).")
        print("  >>> 2021 structural flat year drags OOS annual average.")
        print("  >>> Tradeable with slight position size reduction. <<<")
    else:
        print("  >>> CONDITIONAL — MC survival marginal. Review sizing. <<<")
else:
    failed = []
    if not p4_pass:
        failed.append("Phase 4")
    if not p5_pass:
        failed.append("Phase 5")
    print(f"  >>> NO-GO — Failed: {', '.join(failed)} <<<")
print()
print("=" * 70)
