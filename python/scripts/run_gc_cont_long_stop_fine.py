#!/usr/bin/env python3
"""GC NY Continuation Longs — Stop fine sweep.

R5 found bimodal stop structure: 0.50 and 1.00 both peak, valley at 0.75.
Fine-sweep stop 0.40–1.50 in 0.1 steps to resolve the true peak.

Anchor: ATR 9, entry→14:30, flat=15:00, excl Wed+Fri, gap=1.0
Sweep at two rr levels: rr=5.0 and rr=5.5 (both near ceiling)
tp1=0.45 (robust across both)
"""

import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]
EXCL_WED_FRI = {2, 4}

BASE_SESS = SessionConfig(
    name="NY", orb_start="09:30", orb_end="09:35",
    entry_start="09:35", entry_end="14:30",
    flat_start="15:00", flat_end="16:00",
    stop_atr_pct=1.0, min_gap_atr_pct=1.0, max_gap_points=25.0,
)

BASE = StrategyConfig(
    rr=5.5, tp1_ratio=0.45, risk_usd=5000.0, atr_length=9,
    min_qty=1.0, qty_step=1.0, sessions=(BASE_SESS,), instrument=GC,
    strategy="continuation", direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

STOPS = [0.40, 0.50, 0.60, 0.70, 0.75, 0.80, 0.85, 0.90,
         0.95, 1.00, 1.05, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50]


def run(stop, rr):
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="14:30",
        flat_start="15:00", flat_end="16:00",
        stop_atr_pct=stop, min_gap_atr_pct=1.0, max_gap_points=25.0,
    )
    cfg = with_overrides(BASE, rr=rr, sessions=(sess,))
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
    trades = [
        t for t in trades
        if t.exit_type == EXIT_NO_FILL
        or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in EXCL_WED_FRI
    ]
    return compute_metrics(trades)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def row(stop, m):
    marker = " <-- peak?" if m["calmar_ratio"] > 70 else ""
    return (
        f"  stop={stop:<5.2f}"
        f"  {m['total_trades']:>5d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {r_per_year(m):>7.1f}"
        f"  {m['max_drawdown_r']:>8.1f}"
        f"  {m['calmar_ratio']:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {neg_years(m):>5d}"
        + marker
    )


def header():
    print(
        f"  {'stop':<7s}"
        f"  {'Trades':>5s}  {'  WR':>6s}  {'   PF':>5s}"
        f"  {'  Net R':>8s}  {' R/yr':>7s}  {' Max DD':>8s}"
        f"  {'Calmar':>7s}  {' Sharpe':>7s}  {'NegYr':>5s}"
    )
    print("  " + "-" * 90)


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — STOP FINE SWEEP")
    print("  ATR 9 | entry→14:30 | flat=15:00 | excl Wed+Fri | gap=1.0 | tp1=0.45")
    print("  Testing stop 0.40–1.50 at rr=5.0 and rr=5.5")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    for rr in [5.0, 5.5]:
        print()
        print(f"  ── rr={rr} ──────────────────────────────────────────────────────────")
        header()
        results = []
        for stop in STOPS:
            m = run(stop, rr)
            print(row(stop, m))
            results.append((stop, m))
        best_stop, best_m = max(results, key=lambda x: x[1]["calmar_ratio"])
        print(f"\n  Best Calmar at rr={rr}: stop={best_stop} → "
              f"Calmar {best_m['calmar_ratio']:.2f}, Sharpe {best_m['sharpe_ratio']:.3f}, "
              f"DD {best_m['max_drawdown_r']:.1f}R, WR {best_m['win_rate']:.1%}, NegYrs {neg_years(best_m)}")

    print()
    print("=" * 70)
    print("  DONE — Lock in stop anchor → final full grid or proceed to pipeline.")
    print("=" * 70)
