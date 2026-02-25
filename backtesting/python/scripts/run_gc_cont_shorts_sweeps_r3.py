#!/usr/bin/env python3
"""GC continuation shorts — Round 3 variable sweeps (post-grid).

Grid R1 winner: stop=3.0%, rr=6.0, gap=5.5%, tp1=0.6
  → Calmar 10.94, Sharpe 2.149, 190.4R, -17.4R DD, 1 neg year
  → Anchor shifted from R2 (stop=4.0, rr=5.0, gap=5.0, tp1=0.5)

Re-sweep all dimensions on new anchor to confirm convergence.
If all confirmed → grid R2 → pipeline.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# R3 anchor = grid R1 winner
R3 = dict(
    stop_atr_pct=3.0, min_gap_atr_pct=5.5, max_gap_atr_pct=30.0,
    max_gap_points=25.0, rr=6.0, tp1_ratio=0.6, atr_length=10,
    orb_start="09:30", orb_end="09:45", entry_end="15:00", flat_start="15:50",
)


def make_config(**overrides):
    kw = {**R3, **overrides}
    session = SessionConfig(
        name="NY",
        orb_start=kw["orb_start"], orb_end=kw["orb_end"],
        entry_start=kw["orb_end"], entry_end=kw["entry_end"],
        flat_start=kw["flat_start"], flat_end="16:00",
        stop_atr_pct=kw["stop_atr_pct"],
        min_gap_atr_pct=kw["min_gap_atr_pct"],
        max_gap_points=kw["max_gap_points"],
        max_gap_atr_pct=kw["max_gap_atr_pct"],
    )
    return StrategyConfig(
        rr=kw["rr"], tp1_ratio=kw["tp1_ratio"], risk_usd=5000.0,
        atr_length=kw["atr_length"],
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="continuation", direction_filter="short",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    yearly = defaultdict(list)
    monthly = defaultdict(list)
    for t in trades:
        yearly[t.date[:4]].append(t.r_multiple)
        monthly[t.date[:7]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    n_yr = len(yearly)
    rby = m.get("r_by_year", {})
    neg = sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)
    r_yr = sum(r for y, r in rby.items() if y in FULL_YEARS) / len(FULL_YEARS) if rby else 0
    calmar = round(abs(r_yr) / abs(dd), 2) if dd < 0 else 999
    return {
        **m,
        "worst_month": round(wm, 1),
        "calmar": calmar,
        "calmar_raw": m.get("calmar_ratio", 0),
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        "trades_per_year": len(trades) / max(n_yr, 1),
        "neg_years": neg,
        "r_per_year": round(r_yr, 1),
    }


def print_row(label, trades, m):
    if m is None:
        print(f"  {label:<40} | <5 trades")
        return
    dd = round(m["max_drawdown_r"], 1)
    nr = round(m["total_r"], 1)
    print(f"  {label:<40} | {len(trades):>5} | {m['trades_per_year']:>5.1f} | "
          f"{m['win_rate']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | "
          f"{m['calmar_raw']:>7.2f} | {m['sharpe_ratio']:>7.3f} | "
          f"{m['profit_factor']:>5.2f} | {m['neg_years']:>2}")


def print_header():
    print(f"  {'Config':<40} | {'Trd':>5} | {'T/yr':>5} | {'WR':>5} | "
          f"{'Net R':>7} | {'Max DD':>7} | {'Calmar':>7} | {'Sharpe':>7} | "
          f"{'PF':>5} | {'NY':>2}")
    print("  " + "-" * 125)


def run_one(df, df_1m, df_1s, cfg):
    trades = run_backtest(df, cfg, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    return filled, stats(filled)


def run_sweep(df, df_1m, df_1s, configs):
    return [(n, *run_one(df, df_1m, df_1s, c)) for n, c in configs]


def print_yearly(filled, m):
    if m is None:
        return
    years = sorted(m["yearly"].keys())
    yr_str = " | ".join(f"{yr}: {m['yearly'][yr]:+.1f}R" for yr in years)
    print(f"  Yearly: {yr_str}")
    exit_counts = defaultdict(int)
    for t in filled:
        exit_counts[EXIT_NAMES.get(t.exit_type, f"type_{t.exit_type}")] += 1
    exit_str = ", ".join(f"{n}: {c}" for n, c in sorted(exit_counts.items(), key=lambda x: -x[1]))
    print(f"  Exits: {exit_str}")


def main():
    print("=" * 140)
    print("GC CONTINUATION SHORTS — R3 VARIABLE SWEEPS (POST-GRID)")
    print("=" * 140)
    print(f"R3 anchor (grid winner): stop={R3['stop_atr_pct']}%, rr={R3['rr']}, "
          f"gap={R3['min_gap_atr_pct']}%, tp1={R3['tp1_ratio']}, "
          f"ATR {R3['atr_length']}, ORB {R3['orb_end']}, entry→{R3['entry_end']}")
    print()

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"Loaded {len(df):,} 5m, {len(df_1m):,} 1m, {len(df_1s):,} 1s bars\n")

    t0 = time.time()

    # ── Anchor baseline ──────────────────────────────────────────────────
    print("=" * 140)
    print("R3 ANCHOR BASELINE")
    print("=" * 140)
    print_header()
    filled, m = run_one(df, df_1m, df_1s, make_config())
    print_row("R3 anchor (grid winner)", filled, m)
    print()
    if m:
        print_yearly(filled, m)
    print()

    sweeps = [
        ("ORB WINDOW", [
            ("ORB 5m", dict(orb_end="09:35")),
            ("ORB 10m", dict(orb_end="09:40")),
            ("ORB 15m (anchor)", dict()),
            ("ORB 20m", dict(orb_end="09:50")),
            ("ORB 30m", dict(orb_end="10:00")),
        ]),
        ("ATR LENGTH", [(f"ATR {a}", dict(atr_length=a))
            for a in [5, 8, 10, 12, 14, 16, 20, 30, 50]]),
        ("ENTRY END", [(f"entry→{e}", dict(entry_end=e))
            for e in ["10:30", "11:00", "12:00", "13:00", "14:00", "15:00", "15:30"]]),
        ("FLAT START", [(f"flat={f}", dict(flat_start=f))
            for f in ["14:00", "14:30", "15:00", "15:30", "15:50"]]),
        ("MAX GAP ATR %", [(f"max_gap_atr={g}%", dict(max_gap_atr_pct=g))
            for g in [0, 10, 15, 20, 25, 30, 40, 50]]),
        ("STOP ATR %", [(f"stop={s}%", dict(stop_atr_pct=s))
            for s in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0]]),
        ("R:R", [(f"rr={r}", dict(rr=r))
            for r in [4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0]]),
        ("MIN GAP ATR %", [(f"gap={g}%", dict(min_gap_atr_pct=g))
            for g in [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0]]),
        ("TP1 RATIO", [(f"tp1={t}", dict(tp1_ratio=t))
            for t in [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8]]),
    ]

    for sweep_name, configs in sweeps:
        print("=" * 140)
        print(f"SWEEP: {sweep_name}")
        print("=" * 140)
        print_header()
        for name, overrides in configs:
            filled, m = run_one(df, df_1m, df_1s, make_config(**overrides))
            print_row(name, filled, m)
        print()

    # DOW exclusion (post-hoc filter)
    print("=" * 140)
    print("SWEEP: DAY-OF-WEEK EXCLUSION")
    print("=" * 140)
    print_header()
    anchor_trades = run_backtest(df, make_config(), start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    anchor_filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    filled, m = run_one(df, df_1m, df_1s, make_config())
    print_row("No exclusion (anchor)", filled, m)
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    for dow_num, dow_name in dow_names.items():
        kept = [t for t in anchor_filled if pd.Timestamp(t.date).dayofweek != dow_num]
        m = stats(kept)
        print_row(f"excl {dow_name}", kept, m)
    print()

    elapsed = time.time() - t0
    print(f"\nTotal runtime: {elapsed:.0f}s")
    print(f"\n{'='*80}")
    print("DECISION: If all dimensions confirmed → anchor converged → proceed to pipeline")
    print(f"{'='*80}")


if __name__ == "__main__":
    main()
