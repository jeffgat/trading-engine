#!/usr/bin/env python3
"""Diagnose exit type breakdown for suspicious low R:R configs.

Confirms whether the high WR is driven by degenerate TP1+BE exits
where TP1 is very close to entry.
"""

import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import (
    run_backtest, EXIT_NO_FILL, EXIT_SL, EXIT_TP1_TP2,
    EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD, EXIT_TP2_SINGLE,
)

INSTRUMENT = GC
START_DATE = "2016-01-01"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")

EXIT_NAMES = {
    EXIT_NO_FILL: "NO_FILL", EXIT_SL: "SL", EXIT_TP1_TP2: "TP1+TP2",
    EXIT_TP1_BE: "TP1+BE", EXIT_TP1_EOD: "TP1+EOD", EXIT_EOD: "EOD",
    EXIT_TP2_SINGLE: "TP2_SINGLE",
}

CONFIGS = [
    # Grid #1: rr=1.5, stop=5.0, gap=6.0, tp1=0.3  (86.5% WR, suspicious)
    {"label": "#1 rr=1.5 stop=5.0 gap=6.0 tp1=0.3", "stop": 5.0, "rr": 1.5, "gap": 6.0, "tp1": 0.3},
    # Grid #5: rr=2.0, stop=4.0, gap=5.0, tp1=0.3  (81.2% WR)
    {"label": "#5 rr=2.0 stop=4.0 gap=5.0 tp1=0.3", "stop": 4.0, "rr": 2.0, "gap": 5.0, "tp1": 0.3},
    # For comparison: high R:R anchor  (20.5% WR)
    {"label": "Anchor rr=8.0 stop=3.0 gap=5.5 tp1=0.7", "stop": 3.0, "rr": 8.0, "gap": 5.5, "tp1": 0.7},
]


def make_config(stop, rr, gap, tp1):
    session = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=stop, min_gap_atr_pct=gap,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1, risk_usd=5000.0, atr_length=10,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=INSTRUMENT,
        strategy="continuation", direction_filter="short",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  Loaded in {time.time() - t0:.1f}s\n")

for c in CONFIGS:
    cfg = make_config(c["stop"], c["rr"], c["gap"], c["tp1"])
    trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    # TP1 distance analysis
    tp1_dist_as_risk = c["rr"] * c["tp1"]  # TP1 distance in R units
    tp1_pct_of_stop = tp1_dist_as_risk * 100  # as % of stop distance

    print("=" * 80)
    print(f"  {c['label']}")
    print(f"  TP1 distance: {tp1_dist_as_risk:.3f}R from entry ({tp1_pct_of_stop:.1f}% of stop)")
    print("=" * 80)

    # Exit type breakdown
    exit_counts = Counter(t.exit_type for t in filled)
    print(f"\n  Exit Type Breakdown ({len(filled)} filled trades):")
    print(f"  {'Exit Type':<15s} {'Count':>6s} {'%':>7s} {'Avg R':>8s} {'Total R':>8s}")
    print(f"  {'-'*44}")

    for exit_type in [EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD, EXIT_TP2_SINGLE]:
        subset = [t for t in filled if t.exit_type == exit_type]
        if not subset:
            continue
        count = len(subset)
        pct = count / len(filled) * 100
        avg_r = sum(t.r_multiple for t in subset) / count
        total_r = sum(t.r_multiple for t in subset)
        print(f"  {EXIT_NAMES[exit_type]:<15s} {count:>6d} {pct:>6.1f}% {avg_r:>8.3f} {total_r:>8.1f}")

    # Overall
    total_r = sum(t.r_multiple for t in filled)
    avg_r = total_r / len(filled)
    wins = sum(1 for t in filled if t.r_multiple > 0)
    wr = wins / len(filled)
    print(f"\n  Total R: {total_r:.1f}  |  Avg R: {avg_r:.3f}  |  WR: {wr:.1%}")

    # Distribution of R-multiples
    r_vals = sorted([t.r_multiple for t in filled])
    print(f"\n  R-multiple distribution:")
    print(f"    Min:  {r_vals[0]:.3f}")
    print(f"    p10:  {r_vals[int(len(r_vals)*0.10)]:.3f}")
    print(f"    p25:  {r_vals[int(len(r_vals)*0.25)]:.3f}")
    print(f"    p50:  {r_vals[int(len(r_vals)*0.50)]:.3f}")
    print(f"    p75:  {r_vals[int(len(r_vals)*0.75)]:.3f}")
    print(f"    p90:  {r_vals[int(len(r_vals)*0.90)]:.3f}")
    print(f"    Max:  {r_vals[-1]:.3f}")
    print()
