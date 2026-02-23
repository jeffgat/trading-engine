#!/usr/bin/env python3
"""GC NY Continuation Longs — Round 4 Parameter Grid.

Locked config (from R1-R3 variable sweeps + ATR fine-tune):
  ATR 9, entry_end=14:30, flat_start=15:00
  excl Wed+Fri, 5m ORB (09:30-09:35), long-only

Sweeps: stop_atr_pct × min_gap_atr_pct × rr × tp1_ratio
  stop:    [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]      7 values
  min_gap: [0.5, 1.0, 1.5, 2.0, 2.5]                 5 values
  rr:      [2.0, 2.5, 3.0, 3.5, 4.0]                 5 values
  tp1:     [0.20, 0.25, 0.30, 0.35, 0.40]             5 values

Total: 875 combos, parallel via multiprocessing.

Scoring: Calmar (primary), 0 neg full years required for "clean" configs.
Reports:
  - Top 20 by Calmar (clean: 0 neg years)
  - Top 20 by Calmar (all configs)
  - Marginal analysis per dimension
  - Calmar heatmap: stop vs rr (averaged over gap/tp1)
"""

import sys
import itertools
from pathlib import Path
from datetime import datetime
from multiprocessing import Pool
from collections import defaultdict

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

# ── Locked session config ─────────────────────────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",
    entry_start="09:35",
    entry_end="14:30",
    flat_start="15:00",
    flat_end="16:00",
    stop_atr_pct=4.0,         # overridden per combo
    min_gap_atr_pct=1.0,      # overridden per combo
)

BASE = StrategyConfig(
    rr=3.0,                   # overridden per combo
    tp1_ratio=0.3,            # overridden per combo
    risk_usd=5000.0,
    atr_length=9,
    min_qty=1.0, qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

# ── Grid ──────────────────────────────────────────────────────────────────────

STOPS    = [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0]
MIN_GAPS = [0.5, 1.0, 1.5, 2.0, 2.5]
RRS      = [2.0, 2.5, 3.0, 3.5, 4.0]
TP1S     = [0.20, 0.25, 0.30, 0.35, 0.40]

COMBOS = list(itertools.product(STOPS, MIN_GAPS, RRS, TP1S))


# ── Worker ────────────────────────────────────────────────────────────────────

def _worker(args):
    stop, gap, rr, tp1 = args
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:35",
        entry_start="09:35",
        entry_end="14:30",
        flat_start="15:00",
        flat_end="16:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=gap,
    )
    cfg = with_overrides(BASE, rr=rr, tp1_ratio=tp1, sessions=(sess,))
    trades = run_backtest(df_g, cfg, start_date=START_DATE, df_1m=df_1m_g)
    trades = [
        t for t in trades
        if t.exit_type == EXIT_NO_FILL
        or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in EXCL_WED_FRI
    ]
    m = compute_metrics(trades)
    return (stop, gap, rr, tp1, m)


# ── Global data for workers ───────────────────────────────────────────────────

df_g = None
df_1m_g = None


def init_worker(df, df_1m):
    global df_g, df_1m_g
    df_g = df
    df_1m_g = df_1m


# ── Helpers ───────────────────────────────────────────────────────────────────

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


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def table_header():
    print(
        f"  {'':5s}"
        f"  {'stop':>6s}  {'gap':>5s}  {'rr':>5s}  {'tp1':>6s}"
        f"  {'Trades':>5s}  {'  WR':>6s}  {'   PF':>5s}"
        f"  {'  Net R':>8s}  {' R/yr':>7s}  {' Max DD':>8s}"
        f"  {'Calmar':>7s}  {' Sharpe':>7s}  {'NegYr':>5s}"
    )
    print("  " + "-" * 115)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time

    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — ROUND 4 PARAMETER GRID")
    print("  Locked: ATR 9 | entry→14:30 | flat=15:00 | excl Wed+Fri | 5m ORB")
    print(f"  Grid: {len(STOPS)} stops × {len(MIN_GAPS)} gaps × {len(RRS)} rr × {len(TP1S)} tp1 = {len(COMBOS)} combos")
    print("=" * 70)

    print("\nLoading data...")
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars")

    # Print anchor for reference
    anchor_sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:35",
        entry_start="09:35", entry_end="14:30",
        flat_start="15:00", flat_end="16:00",
        stop_atr_pct=4.0, min_gap_atr_pct=1.0, max_gap_points=25.0,
    )
    anchor_cfg = with_overrides(BASE, rr=3.0, tp1_ratio=0.3, sessions=(anchor_sess,))
    trades_a = run_backtest(df, anchor_cfg, start_date=START_DATE, df_1m=df_1m)
    trades_a = [
        t for t in trades_a
        if t.exit_type == EXIT_NO_FILL
        or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in EXCL_WED_FRI
    ]
    anchor_m = compute_metrics(trades_a)
    print(f"\n  Anchor (stop=4.0, gap=1.0, rr=3.0, tp1=0.30):")
    print(f"    Trades={anchor_m['total_trades']}  WR={anchor_m['win_rate']:.1%}  "
          f"Net R={anchor_m['total_r']:.1f}R  R/yr={r_per_year(anchor_m):.1f}R  "
          f"DD={anchor_m['max_drawdown_r']:.1f}R  Calmar={anchor_m['calmar_ratio']:.2f}  "
          f"Sharpe={anchor_m['sharpe_ratio']:.3f}  NegYrs={neg_years(anchor_m)}")

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

    # ── Analysis ──────────────────────────────────────────────────────────────

    all_r = [(stop, gap, rr, tp1, m) for stop, gap, rr, tp1, m in results]
    clean_r = [(stop, gap, rr, tp1, m) for stop, gap, rr, tp1, m in results if neg_years(m) == 0]

    all_r.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)
    clean_r.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)

    section(f"TOP 20 BY CALMAR — CLEAN CONFIGS (0 neg years) [{len(clean_r)}/{len(COMBOS)} clean]")
    table_header()
    for i, (stop, gap, rr, tp1, m) in enumerate(clean_r[:20]):
        print(result_row(stop, gap, rr, tp1, m, rank=i+1))

    section("TOP 20 BY CALMAR — ALL CONFIGS")
    table_header()
    for i, (stop, gap, rr, tp1, m) in enumerate(all_r[:20]):
        neg = neg_years(m)
        flag = f" ({neg} neg)" if neg else ""
        print(result_row(stop, gap, rr, tp1, m, rank=i+1) + flag)

    # ── Marginal analysis ─────────────────────────────────────────────────────

    section("MARGINAL ANALYSIS — AVG CALMAR BY DIMENSION")

    def marginal(key_fn, key_vals, label):
        print(f"\n  {label}:")
        for kv in key_vals:
            subset = [m for s, g, r, t, m in results if key_fn(s, g, r, t) == kv]
            clean_subset = [m for m in subset if neg_years(m) == 0]
            avg_calmar = sum(m["calmar_ratio"] for m in subset) / len(subset) if subset else 0
            avg_calmar_clean = sum(m["calmar_ratio"] for m in clean_subset) / len(clean_subset) if clean_subset else 0
            print(f"    {kv:>6}: avg Calmar {avg_calmar:>6.2f}  (clean only: {avg_calmar_clean:>6.2f}, n={len(clean_subset)}/{len(subset)})")

    marginal(lambda s, g, r, t: s, STOPS,    "stop_atr_pct")
    marginal(lambda s, g, r, t: g, MIN_GAPS, "min_gap_atr_pct")
    marginal(lambda s, g, r, t: r, RRS,      "rr")
    marginal(lambda s, g, r, t: t, TP1S,     "tp1_ratio")

    # ── Calmar heatmap: stop vs rr ────────────────────────────────────────────

    section("HEATMAP: STOP vs RR (avg Calmar, all gap/tp1)")
    hdr = "stop \\ rr"
    print(f"\n  {hdr:>10s}", end="")
    for rr in RRS:
        print(f"  {rr:>6.1f}", end="")
    print()
    print("  " + "-" * (12 + 9 * len(RRS)))

    for stop in STOPS:
        print(f"  {stop:>10.1f}", end="")
        for rr in RRS:
            subset = [m["calmar_ratio"] for s, g, r, t, m in results if s == stop and r == rr]
            avg = sum(subset) / len(subset) if subset else 0
            print(f"  {avg:>6.1f}", end="")
        print()

    # ── Best configs year breakdown ───────────────────────────────────────────

    section("YEAR BREAKDOWN — TOP 3 CLEAN CONFIGS")
    for i, (stop, gap, rr, tp1, m) in enumerate(clean_r[:3]):
        print(f"\n  #{i+1}: stop={stop} gap={gap} rr={rr} tp1={tp1} → "
              f"Calmar {m['calmar_ratio']:.2f}, DD {m['max_drawdown_r']:.1f}R, Sharpe {m['sharpe_ratio']:.3f}")
        for y, r in sorted(m.get("r_by_year", {}).items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")

    print()
    print("=" * 70)
    print("  DONE — Review top configs. Next: fine-tune stop, then re-run full grid.")
    print("=" * 70)
    print()
