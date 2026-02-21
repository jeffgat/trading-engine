#!/usr/bin/env python3
"""Comprehensive variable sweeps on GC Inversion Longs v8 (GO config).

Tests 5 variables:
  1. ORB window duration (3, 5, 7, 10, 15 min)
  2. Flat time (15:00, 15:15, 15:30, 15:45, 15:50)
  3. Time-of-day R breakdown (by entry hour)
  4. Day-of-week R breakdown
  5. Qualifying move / sweep depth (0%, 2%, 5%, 8%, 10%, 15% of ATR)

Base config: GC NY Inversion Longs v8 (GO)
  rr=3.5, tp1=0.2, atr=50, be=10, stop=9.0%, gap=1.0%,
  ORB 09:30-09:35, entry to 15:00, flat 15:50, magnifier ON
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.engine.qualifying_move import run_backtest_qm
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")

# ── v8 baseline ──────────────────────────────────────────────────────────────

HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
EXCLUDED = ("20241218",)
START = "2016-01-01"


def build_session(orb_end="09:35", entry_end="15:00", flat_start="15:50",
                  stop_atr_pct=9.0, min_gap_atr_pct=1.0, max_gap_points=25.0,
                  qualifying_move_atr_pct=0.0):
    return SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=orb_end,  # entry starts when ORB ends
        entry_end=entry_end,
        flat_start=flat_start,
        flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
        max_gap_points=max_gap_points,
        qualifying_move_atr_pct=qualifying_move_atr_pct,
    )


def build_config(session=None, **kwargs):
    if session is None:
        session = build_session(**{k: v for k, v in kwargs.items()
                                   if k in build_session.__code__.co_varnames})
    return StrategyConfig(
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
        half_days=HALF_DAYS,
        excluded_dates=EXCLUDED,
    )


def print_header(title):
    print(f"\n{'='*75}")
    print(f"  {title}")
    print(f"{'='*75}")


def print_row_header():
    print(f"  {'Value':>12s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Sharpe':>7s} {'PF':>6s} {'Max DD':>7s} {'Calmar':>7s}")
    print(f"  {'─'*60}")


def print_row(label, m, is_baseline=False):
    marker = " <── base" if is_baseline else ""
    print(
        f"  {str(label):>12s} {m['total_trades']:>7d} {m['win_rate']:>5.1%} "
        f"{m['total_r']:>7.1f} {m['sharpe_ratio']:>7.3f} {m['profit_factor']:>6.2f} "
        f"{m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def main():
    print("Loading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # ══════════════════════════════════════════════════════════════════════
    # SWEEP 1: ORB Window Duration
    # ══════════════════════════════════════════════════════════════════════
    print_header("SWEEP 1: ORB Window Duration (baseline = 5 min / 09:35)")
    print_row_header()

    orb_ends = [
        ("3 min", "09:33"),
        ("5 min", "09:35"),
        ("7 min", "09:37"),
        ("10 min", "09:40"),
        ("15 min", "09:45"),
    ]
    t0 = time.time()
    for label, orb_end in orb_ends:
        config = build_config(orb_end=orb_end)
        trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
        m = compute_metrics(trades)
        print_row(label, m, is_baseline=(orb_end == "09:35"))
    print(f"  ({time.time() - t0:.1f}s)")

    # ══════════════════════════════════════════════════════════════════════
    # SWEEP 2: Flat Time
    # ══════════════════════════════════════════════════════════════════════
    print_header("SWEEP 2: Flat Time (baseline = 15:50)")
    print_row_header()

    flat_starts = ["15:00", "15:15", "15:30", "15:45", "15:50"]
    t0 = time.time()
    for fs in flat_starts:
        config = build_config(flat_start=fs)
        trades = run_backtest(df, config, start_date=START, df_1m=df_1m)
        m = compute_metrics(trades)
        print_row(fs, m, is_baseline=(fs == "15:50"))
    print(f"  ({time.time() - t0:.1f}s)")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 3: Time-of-Day Breakdown
    # ══════════════════════════════════════════════════════════════════════
    print_header("ANALYSIS 3: R by Entry Hour (v8 baseline trades)")

    config = build_config()
    trades = run_backtest(df, config, start_date=START, df_1m=df_1m)

    # Group filled trades by entry hour
    from orb_backtest.engine.simulator import EXIT_NO_FILL
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    hour_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "r_sum": 0.0, "r_list": []})
    for t in filled:
        if t.fill_time:
            hour = int(t.fill_time[11:13])  # extract HH from ISO timestamp
            hour_stats[hour]["trades"] += 1
            hour_stats[hour]["r_sum"] += t.r_multiple
            hour_stats[hour]["r_list"].append(t.r_multiple)
            if t.r_multiple > 0:
                hour_stats[hour]["wins"] += 1

    print(f"  {'Hour':>6s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Avg R':>7s} {'Med R':>7s}")
    print(f"  {'─'*45}")
    import statistics
    for hour in sorted(hour_stats):
        s = hour_stats[hour]
        wr = s["wins"] / s["trades"] if s["trades"] > 0 else 0
        avg_r = s["r_sum"] / s["trades"] if s["trades"] > 0 else 0
        med_r = statistics.median(s["r_list"]) if s["r_list"] else 0
        print(f"  {hour:>4d}:00 {s['trades']:>7d} {wr:>5.1%} {s['r_sum']:>7.1f} {avg_r:>7.3f} {med_r:>7.3f}")

    total_r = sum(s["r_sum"] for s in hour_stats.values())
    print(f"  {'TOTAL':>6s} {len(filled):>7d}             {total_r:>7.1f}")

    # ══════════════════════════════════════════════════════════════════════
    # ANALYSIS 4: Day-of-Week Breakdown
    # ══════════════════════════════════════════════════════════════════════
    print_header("ANALYSIS 4: R by Day of Week (v8 baseline trades)")

    from datetime import datetime
    dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    dow_stats = defaultdict(lambda: {"trades": 0, "wins": 0, "r_sum": 0.0, "r_list": []})

    for t in filled:
        dt = datetime.strptime(t.date, "%Y-%m-%d")
        dow = dt.weekday()  # 0=Mon, 6=Sun
        dow_stats[dow]["trades"] += 1
        dow_stats[dow]["r_sum"] += t.r_multiple
        dow_stats[dow]["r_list"].append(t.r_multiple)
        if t.r_multiple > 0:
            dow_stats[dow]["wins"] += 1

    print(f"  {'Day':>6s} {'Trades':>7s} {'WR':>6s} {'Net R':>7s} {'Avg R':>7s} {'Med R':>7s} {'R/Trade':>7s}")
    print(f"  {'─'*50}")
    for dow in sorted(dow_stats):
        s = dow_stats[dow]
        wr = s["wins"] / s["trades"] if s["trades"] > 0 else 0
        avg_r = s["r_sum"] / s["trades"] if s["trades"] > 0 else 0
        med_r = statistics.median(s["r_list"]) if s["r_list"] else 0
        print(f"  {dow_names[dow]:>6s} {s['trades']:>7d} {wr:>5.1%} {s['r_sum']:>7.1f} {avg_r:>7.3f} {med_r:>7.3f} {avg_r:>7.3f}")

    # ══════════════════════════════════════════════════════════════════════
    # SWEEP 5: Qualifying Move / Sweep Depth
    # ══════════════════════════════════════════════════════════════════════
    print_header("SWEEP 5: Qualifying Sweep Depth (% of ATR, baseline = 0% / disabled)")
    print(f"  Requires price to sweep below ORB low by (pct/100)*ATR before accepting long")
    print()
    print_row_header()

    qm_pcts = [0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 20.0]
    t0 = time.time()
    for pct in qm_pcts:
        session = build_session(qualifying_move_atr_pct=pct)
        config = build_config(session=session)
        trades = run_backtest_qm(df, config, start_date=START, df_1m=df_1m)
        m = compute_metrics(trades)
        print_row(f"{pct:.0f}%", m, is_baseline=(pct == 0.0))
    print(f"  ({time.time() - t0:.1f}s)")

    print()


if __name__ == "__main__":
    main()
