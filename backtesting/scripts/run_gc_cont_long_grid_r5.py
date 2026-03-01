#!/usr/bin/env python3
"""GC NY Continuation Longs — Round 5 Grid Sweep (1s magnifier).

Fine-tune findings:
  - ATR 14: Calmar 8.83 (on 10m ORB base)
  - 5m ORB: Calmar 8.02 (on ATR 10 base)
  - ATR 14 + 5m ORB cross not yet tested — done first below

Phase A: Structural check — ATR 14 + ORB (5m vs 10m)
Phase B: Full grid sweep — stop × rr × min_gap × tp1
         stop: 3.0, 3.5, 4.0, 4.5, 5.0, 5.5
         rr:   3.0, 3.5, 4.0, 4.5, 5.0
         min_gap: 1.5, 2.0, 2.5, 3.0, 3.5
         tp1: 0.3, 0.4, 0.5
         = 6 × 5 × 5 × 3 = 450 combos (sequential, ~50 min with 1s)

Uses n_workers=1 (1s data maps passed by reference, no IPC overhead).
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.experiments import log_sweep_runs
from orb_backtest.results.export import grid_results_to_dict, save_optimization_result

GC = get_instrument("GC")
START_DATE = "2016-01-01"
END_DATE = "2026-02-15"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# Grid sweep params — focused around known good region
PARAM_RANGES = {
    "ny_stop_atr_pct":  [3.0, 3.5, 4.0, 4.5, 5.0, 5.5],
    "rr":               [3.0, 3.5, 4.0, 4.5, 5.0],
    "ny_min_gap_atr_pct": [1.5, 2.0, 2.5, 3.0, 3.5],
    "tp1_ratio":        [0.3, 0.4, 0.5],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)

df = None
df_1m = None
df_1s = None


def make_session(orb_end, entry_start, stop=4.5, min_gap=2.5):
    return SessionConfig(
        name="NY", orb_start="09:30", orb_end=orb_end,
        entry_start=entry_start, entry_end="12:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=stop, min_gap_atr_pct=min_gap, max_gap_points=25.0,
    )


def make_config(atr, orb_end, entry_start, stop=4.5, min_gap=2.5):
    return StrategyConfig(
        rr=4.0, tp1_ratio=0.5, risk_usd=5000.0,
        atr_length=atr, min_qty=1.0, qty_step=1.0,
        sessions=(make_session(orb_end, entry_start, stop, min_gap),),
        instrument=GC, strategy="continuation", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",),
    )


def run_single(cfg):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return compute_metrics(trades)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def print_metrics(label, m):
    rpy = r_per_year(m)
    print(f"  {label:<38s}  T={m['total_trades']:>4d}  WR={m['win_rate']:.1%}"
          f"  NetR={m['total_r']:>7.1f}  R/yr={rpy:>6.1f}"
          f"  DD={m['max_drawdown_r']:>7.1f}  Calmar={m['calmar_ratio']:>6.2f}"
          f"  Sharpe={m['sharpe_ratio']:>6.3f}  NegYr={neg_years(m)}")


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ── Phase A: structural check ─────────────────────────────────────────────────

def phase_a():
    section("PHASE A: STRUCTURAL CHECK — ATR 14 + ORB combination")

    combos = [
        ("ATR 10 + 5m ORB (Round 2 winner)",  10, "09:35", "09:35"),
        ("ATR 14 + 10m ORB (fine-tune winner)", 14, "09:40", "09:40"),
        ("ATR 14 + 5m ORB  (cross test)",       14, "09:35", "09:35"),
        ("ATR 12 + 5m ORB  (close to 14)",      12, "09:35", "09:35"),
        ("ATR 16 + 5m ORB  (right of 14)",      16, "09:35", "09:35"),
    ]

    results = []
    for label, atr, orb_end, entry_start in combos:
        cfg = make_config(atr, orb_end, entry_start)
        m = run_single(cfg)
        print_metrics(label, m)
        results.append((label, atr, orb_end, entry_start, m))

    best = max(results, key=lambda x: x[4]["calmar_ratio"])
    print(f"\n  Winner: {best[0]} → Calmar {best[4]['calmar_ratio']:.2f}")
    return best  # (label, atr, orb_end, entry_start, m)


# ── Phase B: full grid sweep ──────────────────────────────────────────────────

def phase_b(atr, orb_end, entry_start):
    section(f"PHASE B: GRID SWEEP — {GRID_SIZE} combos (stop × rr × min_gap × tp1)")
    print(f"  Structural config: ATR {atr}, ORB end={orb_end}")
    print(f"  Grid:")
    for k, v in PARAM_RANGES.items():
        print(f"    {k}: {v}")
    print()

    base = make_config(atr, orb_end, entry_start)
    configs = generate_param_grid(base, PARAM_RANGES)

    t0 = time.time()

    def progress(done, total):
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        print(f"\r  [{done}/{total}] {done/total:.0%} | {rate:.1f}/s | ETA {eta:.0f}s", end="", flush=True)

    results = run_sweep(df, configs, n_workers=1, progress_fn=progress,
                        start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.0f}s ({GRID_SIZE/elapsed:.1f} runs/s)")

    # Score all
    scored = []
    for config, trades in results:
        if not trades:
            continue
        m = compute_metrics(trades)
        if m["total_trades"] > 0:
            scored.append((config, trades, m))

    # Sort by Calmar
    scored.sort(key=lambda x: x[2]["calmar_ratio"], reverse=True)

    print()
    print(f"  Top 15 by Calmar:")
    print(f"  {'Rank':<5s} {'stop':>6s} {'rr':>5s} {'min_gap':>8s} {'tp1':>5s}"
          f"  {'Trades':>6s} {'WR':>6s} {'NetR':>8s} {'R/yr':>7s}"
          f"  {'MaxDD':>8s} {'Calmar':>7s} {'Sharpe':>7s} {'NegYr':>6s}")
    print("  " + "-" * 110)

    for rank, (cfg, trades, m) in enumerate(scored[:15], 1):
        sess = cfg.sessions[0]
        rpy = r_per_year(m)
        neg = neg_years(m)
        print(f"  {rank:<5d} {sess.stop_atr_pct:>6.1f} {cfg.rr:>5.1f} {sess.min_gap_atr_pct:>8.1f}"
              f" {cfg.tp1_ratio:>5.2f}"
              f"  {m['total_trades']:>6d} {m['win_rate']:>6.1%} {m['total_r']:>8.1f}"
              f" {rpy:>7.1f}  {m['max_drawdown_r']:>8.1f} {m['calmar_ratio']:>7.2f}"
              f" {m['sharpe_ratio']:>7.3f} {neg:>6d}")

    best_cfg, best_trades, best_m = scored[0]
    best_sess = best_cfg.sessions[0]
    print()
    print(f"  Grid winner:")
    print(f"    stop={best_sess.stop_atr_pct}%, rr={best_cfg.rr}, min_gap={best_sess.min_gap_atr_pct}%, tp1={best_cfg.tp1_ratio}")
    print(f"    Trades={best_m['total_trades']}, WR={best_m['win_rate']:.1%}, Net R={best_m['total_r']:.1f}R")
    print(f"    Calmar={best_m['calmar_ratio']:.2f}, Sharpe={best_m['sharpe_ratio']:.3f}, DD={best_m['max_drawdown_r']:.1f}R")
    print(f"    Neg years={neg_years(best_m)}")

    # Save to experiment DB
    grid_dict = grid_results_to_dict(results, swept_params=PARAM_RANGES)
    grid_dict["name"] = f"GC NY cont long grid r5 ATR{atr} {orb_end.replace(':','')}ORB"
    result_id = save_optimization_result(grid_dict)
    try:
        n_logged = log_sweep_runs(results, result_id)
        print(f"\n  Logged {n_logged} experiment rows → {result_id}")
    except Exception as e:
        print(f"\n  Warning: experiment logging failed: {e}")

    return best_cfg, best_m


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT LONGS — ROUND 5 GRID SWEEP (1s magnifier)")
    print("  ATR fine-tune winner: ATR 14 (Calmar 8.83 on 10m ORB)")
    print("  Phase A: cross-check ATR 14 + 5m ORB")
    print("  Phase B: full grid sweep with winning structural config")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # Phase A
    best_label, best_atr, best_orb_end, best_entry_start, phase_a_m = phase_a()

    # Phase B — grid sweep using Phase A winner
    phase_b(best_atr, best_orb_end, best_entry_start)

    print()
    print("=" * 70)
    print("  DONE. Review top configs above.")
    print("  Next: run robust pipeline on grid winner.")
    print("=" * 70)
    print()
