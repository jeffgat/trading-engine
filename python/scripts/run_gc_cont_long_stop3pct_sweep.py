#!/usr/bin/env python3
"""GC NY Continuation Longs — Best config with stop >= 3% ATR.

User constraint: minimum stop of 3% ATR (more conservative execution assumption).
Sweep stop [3.0, 3.5, 4.0, 4.5, 5.0, 6.0] with extended rr and tp1 ranges.

Locked: ATR 9, entry→14:30, flat=15:00, excl Wed+Fri, 5m ORB, long-only.
"""

import sys
import itertools
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool

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

BASE = StrategyConfig(
    rr=3.0, tp1_ratio=0.3, risk_usd=5000.0, atr_length=9,
    min_qty=1.0, qty_step=1.0,
    sessions=(SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="14:30",
        flat_start="15:00", flat_end="16:00",
        stop_atr_pct=4.0, min_gap_atr_pct=1.0, max_gap_points=25.0,
    ),),
    instrument=GC, strategy="continuation", direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

STOPS    = [3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
MIN_GAPS = [0.5, 1.0, 1.5, 2.0]
RRS      = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5]
TP1S     = [0.25, 0.30, 0.35, 0.40, 0.45, 0.50]

COMBOS = list(itertools.product(STOPS, MIN_GAPS, RRS, TP1S))

df_g = None
df_1m_g = None


def init_worker(df, df_1m):
    global df_g, df_1m_g
    df_g = df
    df_1m_g = df_1m


def _worker(args):
    stop, gap, rr, tp1 = args
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="14:30",
        flat_start="15:00", flat_end="16:00",
        stop_atr_pct=stop, min_gap_atr_pct=gap, max_gap_points=25.0,
    )
    cfg = with_overrides(BASE, rr=rr, tp1_ratio=tp1, sessions=(sess,))
    trades = run_backtest(df_g, cfg, start_date=START_DATE, df_1m=df_1m_g)
    trades = [
        t for t in trades
        if t.exit_type == EXIT_NO_FILL
        or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in EXCL_WED_FRI
    ]
    return (stop, gap, rr, tp1, compute_metrics(trades))


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def result_row(stop, gap, rr, tp1, m, rank=None):
    prefix = f"  #{rank:<3d}" if rank else "      "
    return (
        f"{prefix}"
        f"  stop={stop:<4.1f}  gap={gap:<4.1f}  rr={rr:<4.1f}  tp1={tp1:<4.2f}"
        f"  {m['total_trades']:>5d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {r_per_year(m):>7.1f}"
        f"  {m['max_drawdown_r']:>8.1f}"
        f"  {m['calmar_ratio']:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {neg_years(m):>5d}"
    )


def table_header():
    print(
        f"  {'':5s}"
        f"  {'stop':>6s}  {'gap':>5s}  {'rr':>5s}  {'tp1':>6s}"
        f"  {'Trades':>5s}  {'  WR':>6s}  {'   PF':>5s}"
        f"  {'  Net R':>8s}  {' R/yr':>7s}  {' Max DD':>8s}"
        f"  {'Calmar':>7s}  {' Sharpe':>7s}  {'NegYr':>5s}"
    )
    print("  " + "-" * 117)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


if __name__ == "__main__":
    import time

    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — BEST CONFIG WITH STOP >= 3% ATR")
    print("  Locked: ATR 9 | entry→14:30 | flat=15:00 | excl Wed+Fri | 5m ORB")
    print(f"  Grid: {len(STOPS)} stops × {len(MIN_GAPS)} gaps × {len(RRS)} rr × {len(TP1S)} tp1 = {len(COMBOS)} combos")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    print(f"\nRunning {len(COMBOS)} combos with 8 workers...")
    t0 = time.time()

    with Pool(8, initializer=init_worker, initargs=(df, df_1m)) as pool:
        results = []
        for i, res in enumerate(pool.imap_unordered(_worker, COMBOS, chunksize=5)):
            results.append(res)
            if (i + 1) % 50 == 0:
                elapsed = time.time() - t0
                rate = (i + 1) / elapsed
                remaining = (len(COMBOS) - i - 1) / rate
                print(f"\r  {i+1}/{len(COMBOS)} done [{elapsed:.0f}s, ~{remaining:.0f}s left]    ", end="", flush=True)

    elapsed = time.time() - t0
    print(f"\r  {len(COMBOS)}/{len(COMBOS)} done [{elapsed:.0f}s]                    ")

    clean = [(s, g, r, t, m) for s, g, r, t, m in results if neg_years(m) == 0]
    all_r = list(results)
    clean.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)
    all_r.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)

    section(f"TOP 20 BY CALMAR — CLEAN (0 neg years) [{len(clean)}/{len(COMBOS)} clean]")
    table_header()
    for i, (s, g, r, t, m) in enumerate(clean[:20]):
        print(result_row(s, g, r, t, m, rank=i+1))

    section("MARGINAL ANALYSIS")

    def marginal(key_fn, key_vals, label):
        print(f"\n  {label}:")
        for kv in key_vals:
            subset = [m for s, g, r, t, m in results if abs(key_fn(s, g, r, t) - kv) < 0.001]
            clean_s = [m for m in subset if neg_years(m) == 0]
            avg = sum(m["calmar_ratio"] for m in subset) / len(subset) if subset else 0
            avg_c = sum(m["calmar_ratio"] for m in clean_s) / len(clean_s) if clean_s else 0
            print(f"    {kv:>5.1f}: avg Calmar {avg:>6.2f}  (clean: {avg_c:>6.2f}, n={len(clean_s)}/{len(subset)})")

    marginal(lambda s, g, r, t: s, STOPS,    "stop_atr_pct")
    marginal(lambda s, g, r, t: g, MIN_GAPS, "min_gap_atr_pct")
    marginal(lambda s, g, r, t: r, RRS,      "rr")
    marginal(lambda s, g, r, t: t, TP1S,     "tp1_ratio")

    section("YEAR BREAKDOWN — TOP 3 CLEAN CONFIGS")
    for i, (s, g, r, t, m) in enumerate(clean[:3]):
        print(f"\n  #{i+1}: stop={s} gap={g} rr={r} tp1={t} → "
              f"Calmar {m['calmar_ratio']:.2f}, DD {m['max_drawdown_r']:.1f}R, "
              f"Sharpe {m['sharpe_ratio']:.3f}, WR {m['win_rate']:.1%}")
        for y, rv in sorted(m.get("r_by_year", {}).items()):
            flag = " <--" if rv < 0 else ""
            print(f"    {y}: {rv:>8.1f}R{flag}")

    print()
    print("=" * 70)
    print("  DONE")
    print("=" * 70)
