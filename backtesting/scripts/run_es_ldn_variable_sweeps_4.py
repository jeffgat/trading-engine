#!/usr/bin/env python3
"""ES LDN Continuation Both — Variable Sweeps Round 4 (Full Optimization Step 2).

Updated anchor from R3 adoptions:
  ATR=3 (was 20, oscillating), gap=1.5% (was 1.0, oscillating), DOW excl Mon (new)
  Stop=10.0%, rr=2.5, tp1=0.5, ORB 15m, flat 08:20, both, ICF off.
  Stop sweep floor: 5.0% (10 ticks at typical ATR ~50).

NOTE: ATR and gap are oscillating (ATR: 14→3→20→3, gap: 1.0→1.5→1.0→1.5).
If they flip again in this round, declare convergence and let grid sweep resolve.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON, TUE, WED, THU, FRI

# -- Config -------------------------------------------------------------------

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# DOW exclusion: Monday
DOW_EXCLUDED = {MON}

ANCHOR_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:15",
    entry_start="03:15",
    entry_end="08:25",
    flat_start="08:20",
    flat_end="08:25",
    stop_atr_pct=10.0,
    min_gap_atr_pct=1.5,    # R3: 1.0 → 1.5 (oscillating)
)

ANCHOR = StrategyConfig(
    rr=2.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=3,            # R3: 20 → 3 (oscillating)
    sessions=(ANCHOR_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Helpers ------------------------------------------------------------------


def neg_year_set(m):
    rby = m.get("r_by_year", {})
    return {y for y, r in rby.items() if y in FULL_YEARS and r < 0}


def neg_years(m):
    return len(neg_year_set(m))


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def calmar(m):
    return m.get("calmar_ratio", 0.0)


def run_and_measure(df, config, df_1m, df_1s, dow_filter=None):
    trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    # Always apply DOW exclusion (Monday) unless overridden
    effective_dow = dow_filter if dow_filter is not None else DOW_EXCLUDED
    if effective_dow:
        trades = apply_dow_filter(trades, effective_dow)
    m = compute_metrics(trades)
    return trades, m


def print_sweep_table(results, dim_name, anchor_value):
    print(f"\n{'='*90}")
    print(f"  DIMENSION: {dim_name} (anchor = {anchor_value})")
    print(f"{'='*90}")
    print(f"  {'Value':<15s} {'Trades':>7s} {'WR':>7s} {'PF':>7s} {'Sharpe':>8s} "
          f"{'Net R':>8s} {'R/yr':>7s} {'MaxDD':>8s} {'Calmar':>8s} {'NegYr':>6s}")
    print(f"  {'-'*15} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*6}")

    for val, m in results:
        is_anchor = (str(val) == str(anchor_value))
        marker = " <<<" if is_anchor else ""
        print(f"  {str(val):<15s} {m['total_trades']:>7d} {m['win_rate']:>6.1%} "
              f"{m['profit_factor']:>7.2f} {m['sharpe_ratio']:>8.3f} "
              f"{m['total_r']:>7.1f}R {r_per_year(m):>6.1f}R "
              f"{m['max_drawdown_r']:>7.1f}R {calmar(m):>8.2f} "
              f"{neg_years(m):>5d}{marker}")


def best_by_calmar(results):
    best_val, best_cal, best_m = None, -999, None
    for val, m in results:
        c = calmar(m)
        if m["total_trades"] > 100 and c > best_cal:
            best_val, best_cal, best_m = val, c, m
    return best_val, best_cal, best_m


# -- Dimension Sweep Functions ------------------------------------------------


def sweep_stop(df, df_1m, df_1s):
    values = [5.0, 6.0, 7.5, 10.0, 12.0, 15.0]
    results = []
    for v in values:
        sess = replace(ANCHOR_SESSION, stop_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Stop ATR %", ANCHOR_SESSION.stop_atr_pct)
    return results


def sweep_orb_window(df, df_1m, df_1s):
    windows = [
        ("5m",  "03:00", "03:05", "03:05"),
        ("10m", "03:00", "03:10", "03:10"),
        ("15m", "03:00", "03:15", "03:15"),
        ("20m", "03:00", "03:20", "03:20"),
        ("25m", "03:00", "03:25", "03:25"),
        ("30m", "03:00", "03:30", "03:30"),
        ("45m", "03:00", "03:45", "03:45"),
    ]
    results = []
    for label, orb_s, orb_e, entry_s in windows:
        sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((label, m))
    print_sweep_table(results, "ORB Window", "15m")
    return results


def sweep_atr_length(df, df_1m, df_1s):
    values = [3, 5, 7, 10, 14, 20, 30, 50]
    results = []
    for v in values:
        cfg = replace(ANCHOR, atr_length=v)
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "ATR Length", ANCHOR.atr_length)
    return results


def sweep_entry_end(df, df_1m, df_1s):
    values = ["05:00", "06:00", "06:30", "07:00", "07:30", "08:00", "08:25"]
    results = []
    for v in values:
        sess = replace(ANCHOR_SESSION, entry_end=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Entry End", ANCHOR_SESSION.entry_end)
    return results


def sweep_flat_start(df, df_1m, df_1s):
    values = ["06:00", "06:30", "07:00", "07:30", "08:00", "08:20"]
    results = []
    for v in values:
        sess = replace(ANCHOR_SESSION, flat_start=v, flat_end="08:25")
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Flat Start", ANCHOR_SESSION.flat_start)
    return results


def sweep_direction(df, df_1m, df_1s):
    values = ["both", "long", "short"]
    results = []
    for v in values:
        cfg = replace(ANCHOR, direction_filter=v)
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Direction", ANCHOR.direction_filter)
    return results


def sweep_rr(df, df_1m, df_1s):
    values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    results = []
    for v in values:
        cfg = replace(ANCHOR, rr=v)
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "R:R", ANCHOR.rr)
    return results


def sweep_tp1(df, df_1m, df_1s):
    values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    results = []
    for v in values:
        cfg = replace(ANCHOR, tp1_ratio=v)
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "TP1 Ratio", ANCHOR.tp1_ratio)
    return results


def sweep_min_gap(df, df_1m, df_1s):
    values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
    results = []
    for v in values:
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=v)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Min Gap ATR %", ANCHOR_SESSION.min_gap_atr_pct)
    return results


def sweep_dow(df, df_1m, df_1s):
    """DOW sweep — test different exclusions ON TOP of the base (no DOW filter for this sweep)."""
    trades = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filters = {
        "none": set(),
        "Mon": {MON},
        "Tue": {TUE},
        "Wed": {WED},
        "Thu": {THU},
        "Fri": {FRI},
        "M+F": {MON, FRI},
        "Th+F": {THU, FRI},
    }
    results = []
    for label, excluded in filters.items():
        filtered = apply_dow_filter(trades, excluded) if excluded else trades
        m = compute_metrics(filtered)
        results.append((label, m))
    print_sweep_table(results, "DOW Exclusion", "Mon")
    return results


def sweep_max_gap(df, df_1m, df_1s):
    values = [("OFF", 0.0, 0.0), ("20pt", 20.0, 0.0), ("50pt", 50.0, 0.0),
              ("75pt", 75.0, 0.0), ("100pt", 100.0, 0.0),
              ("20%ATR", 0.0, 20.0), ("50%ATR", 0.0, 50.0), ("75%ATR", 0.0, 75.0),
              ("100%ATR", 0.0, 100.0), ("150%ATR", 0.0, 150.0)]
    results = []
    for label, pts, atr_pct in values:
        sess = replace(ANCHOR_SESSION, max_gap_points=pts, max_gap_atr_pct=atr_pct)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((label, m))
    print_sweep_table(results, "Max Gap Filter", "OFF")
    return results


def sweep_icf(df, df_1m, df_1s):
    values = [False, True]
    results = []
    for v in values:
        cfg = replace(ANCHOR, impulse_close_filter=v)
        _, m = run_and_measure(df, cfg, df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "ICF", ANCHOR.impulse_close_filter)
    return results


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 90)
    print("  ES LDN CONTINUATION BOTH — VARIABLE SWEEPS ROUND 4")
    print("=" * 90)
    print(f"  Anchor: stop={ANCHOR_SESSION.stop_atr_pct}%, rr={ANCHOR.rr}, "
          f"gap={ANCHOR_SESSION.min_gap_atr_pct}%, tp1={ANCHOR.tp1_ratio}, "
          f"ATR={ANCHOR.atr_length}, ORB 15m, flat {ANCHOR_SESSION.flat_start}, "
          f"dir={ANCHOR.direction_filter}, DOW excl Mon, ICF={ANCHOR.impulse_close_filter}")
    print(f"  R3 adoptions: ATR 20→3 (oscillating), gap 1.0→1.5 (oscillating), DOW excl Mon (new)")
    print(f"  NOTE: If ATR/gap flip again, declare convergence → grid sweep")
    print()

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time() - t0:.1f}s", flush=True)
    print()

    # Run anchor baseline (with DOW Mon excluded)
    print("  Running anchor baseline (DOW Mon excluded)...", flush=True)
    _, anchor_m = run_and_measure(df, ANCHOR, df_1m, df_1s)
    anchor_cal = calmar(anchor_m)
    anchor_neg = neg_year_set(anchor_m)
    print(f"  Anchor: Calmar={anchor_cal:.2f}, NegYrs={len(anchor_neg)} {anchor_neg}")

    rby = anchor_m.get("r_by_year", {})
    if rby:
        parts = [f"{y}:{r:+.1f}" for y, r in sorted(rby.items())]
        print(f"  R/yr: {', '.join(parts)}")
    print()

    # Sweep all 12 dimensions
    t_total = time.time()
    all_sweeps = {}

    sweeps = [
        ("Stop ATR %",   ANCHOR_SESSION.stop_atr_pct, sweep_stop),
        ("ORB Window",   "15m",                        sweep_orb_window),
        ("ATR Length",   ANCHOR.atr_length,             sweep_atr_length),
        ("Entry End",    ANCHOR_SESSION.entry_end,      sweep_entry_end),
        ("Flat Start",   ANCHOR_SESSION.flat_start,     sweep_flat_start),
        ("Direction",    ANCHOR.direction_filter,        sweep_direction),
        ("R:R",          ANCHOR.rr,                     sweep_rr),
        ("TP1 Ratio",    ANCHOR.tp1_ratio,              sweep_tp1),
        ("Min Gap ATR%", ANCHOR_SESSION.min_gap_atr_pct, sweep_min_gap),
        ("DOW Exclusion","Mon",                          sweep_dow),
        ("Max Gap",      "OFF",                          sweep_max_gap),
        ("ICF",          ANCHOR.impulse_close_filter,    sweep_icf),
    ]

    for dim_name, anchor_val, sweep_fn in sweeps:
        t_dim = time.time()
        results = sweep_fn(df, df_1m, df_1s)
        elapsed = time.time() - t_dim
        print(f"  [{dim_name}] completed in {elapsed:.1f}s", flush=True)

        best_val, best_cal, best_m = best_by_calmar(results)
        all_sweeps[dim_name] = {
            "anchor_val": anchor_val,
            "best_val": best_val,
            "best_calmar": best_cal,
            "best_neg_years": neg_year_set(best_m) if best_m else set(),
            "best_trades": best_m["total_trades"] if best_m else 0,
            "delta": best_cal - anchor_cal,
        }

    total_time = time.time() - t_total

    # Summary
    print(f"\n\n{'='*90}")
    print(f"  SUMMARY — Variable Sweeps Round 4")
    print(f"  Total time: {total_time:.0f}s")
    print(f"{'='*90}")
    print(f"  Anchor Calmar: {anchor_cal:.2f} | Anchor neg years: {len(anchor_neg)} {anchor_neg}")
    print()
    print(f"  {'Dimension':<16s} {'Anchor':<12s} {'Best':<12s} {'Calmar':>8s} {'Delta':>8s} "
          f"{'NegYr':>6s} {'Trades':>7s} {'Adopt?':>7s}")
    print(f"  {'-'*16} {'-'*12} {'-'*12} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*7}")

    adoptions = []
    oscillating = []
    for dim_name, info in all_sweeps.items():
        delta = info["delta"]
        new_neg = info["best_neg_years"] - anchor_neg
        adopt = (delta > 0.3
                 and len(new_neg) == 0
                 and info["best_trades"] > 100)

        # Check for oscillation on ATR and gap
        if dim_name == "ATR Length" and info["best_val"] == 20 and adopt:
            oscillating.append(f"ATR: 3→20 (4th flip)")
            adopt = False
        if dim_name == "Min Gap ATR%" and info["best_val"] == 1.0 and adopt:
            oscillating.append(f"Gap: 1.5→1.0 (4th flip)")
            adopt = False

        adopt_str = "YES" if adopt else ("OSCL" if dim_name in ["ATR Length", "Min Gap ATR%"]
                                          and str(info["best_val"]) != str(info["anchor_val"])
                                          and delta > 0.3 else "no")
        if adopt:
            adoptions.append((dim_name, info["best_val"], info["best_calmar"]))

        print(f"  {dim_name:<16s} {str(info['anchor_val']):<12s} {str(info['best_val']):<12s} "
              f"{info['best_calmar']:>8.2f} {delta:>+8.2f} "
              f"{len(info['best_neg_years']):>5d} {info['best_trades']:>7d} {adopt_str:>7s}")

    if oscillating:
        print(f"\n  OSCILLATION DETECTED:")
        for osc in oscillating:
            print(f"    {osc}")
        print(f"  → These dimensions will be resolved in the grid sweep.")

    print(f"\n  Adoptions (non-oscillating): {len(adoptions)}")
    for dim, val, cal in adoptions:
        print(f"    {dim}: {val} (Calmar {cal:.2f})")

    if adoptions:
        print(f"\n  >>> {len(adoptions)} adoption(s) — update anchor and re-sweep (round 5)")
    elif oscillating:
        print(f"\n  >>> CONVERGED (with oscillating dims). Include ATR + gap in grid sweep.")
        print(f"  >>> Grid anchor: stop=10%, rr=2.5, tp1=0.5, ORB 15m, flat 08:20, "
              f"both, DOW excl Mon")
        print(f"  >>> Grid dimensions: stop × rr × gap × tp1 + ATR (3 vs 20)")
    else:
        print(f"\n  >>> 0 adoptions — CONVERGED. Ready for grid sweep.")
