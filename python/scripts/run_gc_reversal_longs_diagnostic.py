#!/usr/bin/env python3
"""GC ORB reversal longs with inversion confirmation — clean 1s data.

Setup: price breaks below ORB low → bearish FVG forms → price closes ABOVE
the FVG top (inversion = reversal confirmation) → enter LONG.

This is strategy="inversion" + direction_filter="long". The FVG invalidation
acts as confirmation that the breakdown has failed before entering.

Prior inversion longs tests used old v8/v9 params (stop=9%, rr=3.5).
This diagnostic uses R2 continuation anchor params on clean 1s data.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")


def make_config(
    stop_atr_pct=4.0,
    min_gap_atr_pct=3.5,
    max_gap_atr_pct=30.0,
    max_gap_points=25.0,
    rr=4.0,
    tp1_ratio=0.5,
    atr_length=10,
    orb_start="09:30",
    orb_end="09:40",
    entry_end="11:00",
    flat_start="15:50",
):
    session = SessionConfig(
        name="NY",
        orb_start=orb_start, orb_end=orb_end,
        entry_start=orb_end, entry_end=entry_end,
        flat_start=flat_start, flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
        max_gap_points=max_gap_points,
        max_gap_atr_pct=max_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=atr_length,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="inversion", direction_filter="long",
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
    calmar = round(abs(nr / n_yr) / abs(dd), 2) if dd < 0 and n_yr > 0 else 999
    return {
        **m,
        "worst_month": round(wm, 1),
        "calmar": calmar,
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        "trades_per_year": len(trades) / max(n_yr, 1),
        "neg_years": sum(1 for v in yearly.values() if sum(v) < 0),
    }


def print_row(label, trades, m):
    if m is None:
        print(f"  {label:<30} | <5 trades")
        return
    dd = round(m["max_drawdown_r"], 1)
    nr = round(m["total_r"], 1)
    print(f"  {label:<30} | {len(trades):>5} | {m['trades_per_year']:>5.1f} | "
          f"{m['win_rate']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | "
          f"{m['calmar']:>7.2f} | {m['sharpe_ratio']:>7.3f} | "
          f"{m['profit_factor']:>5.2f} | {m['neg_years']:>2}")


def print_header():
    print(f"  {'Config':<30} | {'Trd':>5} | {'T/yr':>5} | {'WR':>5} | "
          f"{'Net R':>7} | {'Max DD':>7} | {'Calmar':>7} | {'Sharpe':>7} | "
          f"{'PF':>5} | {'NY':>2}")
    print("  " + "-" * 115)


def run_sweep(df, df_1m, df_1s, label, configs):
    """Run a parameter sweep, return list of (label, trades, metrics)."""
    results = []
    for name, cfg in configs:
        trades = run_backtest(df, cfg, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m = stats(filled)
        results.append((name, filled, m))
    return results


def main():
    print("=" * 130)
    print("GC ORB REVERSAL LONGS (INVERSION ENTRY) — DIAGNOSTIC ON CLEAN 1s DATA")
    print("=" * 130)
    print("Strategy: ORB low breakdown → bearish FVG → close above FVG top (inversion) → enter LONG")
    print("Base: R2 continuation anchor (stop=4%, rr=4.0, gap=3.5%, tp1=0.5, ATR 10, 10m ORB, entry→11:00)")
    print("Magnifier: hierarchical 5m→1m→1s")
    print()

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    bars_1m = f"{len(df_1m):,} 1m" if df_1m is not None else "no 1m"
    bars_1s = f"{len(df_1s):,} 1s" if df_1s is not None else "no 1s"
    print(f"Loaded {len(df):,} 5m bars, {bars_1m} bars, {bars_1s} bars\n")

    t0 = time.time()

    # ── Phase 1: Base config ─────────────────────────────────────────────
    print("=" * 130)
    print("PHASE 1: BASE CONFIG (R2 continuation anchor as reversal)")
    print("=" * 130)
    print_header()
    base_cfg = make_config()
    trades = run_backtest(df, base_cfg, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    base_m = stats(filled)
    print_row("Base (R2 anchor)", filled, base_m)
    print()

    if base_m:
        years = sorted(base_m["yearly"].keys())
        yr_str = " | ".join(f"{yr}: {base_m['yearly'][yr]:+.1f}R" for yr in years)
        print(f"  Yearly: {yr_str}")

        # Exit type breakdown
        exit_counts = defaultdict(int)
        for t in filled:
            exit_counts[EXIT_NAMES.get(t.exit_type, f"type_{t.exit_type}")] += 1
        exit_str = ", ".join(f"{n}: {c}" for n, c in sorted(exit_counts.items(), key=lambda x: -x[1]))
        print(f"  Exits: {exit_str}")
    print()

    # ── Phase 2: Stop sweep ──────────────────────────────────────────────
    print("=" * 130)
    print("PHASE 2: STOP ATR % SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"stop={s}%", make_config(stop_atr_pct=s)) for s in [2, 3, 4, 5, 6, 8, 10, 12]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "stop", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 3: RR sweep ────────────────────────────────────────────────
    print("=" * 130)
    print("PHASE 3: R:R SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"rr={r}", make_config(rr=r)) for r in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "rr", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 4: Entry end sweep ─────────────────────────────────────────
    print("=" * 130)
    print("PHASE 4: ENTRY END SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"entry→{e}", make_config(entry_end=e))
               for e in ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00"]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "entry_end", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 5: ORB window sweep ────────────────────────────────────────
    print("=" * 130)
    print("PHASE 5: ORB WINDOW SWEEP")
    print("=" * 130)
    print_header()
    configs = [
        ("ORB 5m (09:30-09:35)", make_config(orb_end="09:35")),
        ("ORB 10m (09:30-09:40)", make_config(orb_end="09:40")),
        ("ORB 15m (09:30-09:45)", make_config(orb_end="09:45")),
        ("ORB 30m (09:30-10:00)", make_config(orb_end="10:00")),
    ]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "orb", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 6: Min gap sweep ───────────────────────────────────────────
    print("=" * 130)
    print("PHASE 6: MIN GAP ATR % SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"gap={g}%", make_config(min_gap_atr_pct=g)) for g in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "gap", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 7: ATR length sweep ────────────────────────────────────────
    print("=" * 130)
    print("PHASE 7: ATR LENGTH SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"ATR {a}", make_config(atr_length=a)) for a in [5, 8, 10, 14, 16, 20, 30, 50]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "atr", configs):
        print_row(name, filled, m)
    print()

    # ── Phase 8: TP1 ratio sweep ─────────────────────────────────────────
    print("=" * 130)
    print("PHASE 8: TP1 RATIO SWEEP")
    print("=" * 130)
    print_header()
    configs = [(f"tp1={t}", make_config(tp1_ratio=t)) for t in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]]
    for name, filled, m in run_sweep(df, df_1m, df_1s, "tp1", configs):
        print_row(name, filled, m)
    print()

    elapsed = time.time() - t0
    print(f"Total runtime: {elapsed:.0f}s")

    # ── Reference ────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("REFERENCE")
    print(f"{'='*80}")
    print(f"  GC Cont Longs R2: 492 trades, 42.7% WR, 131.8R, -10.1R DD, Calmar 13.10")
    print(f"  Old inversion longs (v8 params, 1m mag): -386R; no magnifier: -40.6R (1411 trades, 56.3% WR)")
    print(f"  If base config shows positive signal → proceed to full variable sweeps")
    print(f"  If all sweeps negative → confirm NO-GO, update learnings")


if __name__ == "__main__":
    main()
