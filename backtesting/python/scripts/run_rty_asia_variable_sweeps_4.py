#!/usr/bin/env python3
"""RTY Asia Continuation — Variable Sweeps Round 4.

R1 adopted: direction=long (Calmar -0.52 → 2.55)
R2 adopted: excl Tue (Calmar 2.55 → 3.32)
R3 adopted: stop=4.0% (Calmar 3.32 → 5.32), tp1=0.4 (3.32 → 4.83)

R4 anchor:
  ORB: 20:00-20:15 (15m), entry until 23:15, flat 06:45-07:00
  stop=4.0%, min_gap_atr=0.9%, max_gap_pts=50, max_gap_atr=0 (off)
  rr=2.0, tp1=0.4, ATR=14, direction=LONG, ICF=OFF, continuation, 1s magnifier
  DOW gate: excl Tue

Adoption rule: Calmar Δ > +0.3 AND no NEW negative full years.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import RTY
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",
    entry_start="20:15",
    entry_end="23:15",
    flat_start="06:45",
    flat_end="07:00",
    stop_atr_pct=4.0,         # ← R3 adoption
    min_gap_atr_pct=0.9,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.4,             # ← R3 adoption
    atr_length=14,
    impulse_close_filter=False,
    name="RTY Asia R4 Anchor",
)

ANCHOR_DOW_EXCL = {1}  # excl Tue


def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    return trades, compute_metrics(trades)


def run_dow_filtered(trades_all, excluded_days):
    filtered = apply_dow_filter(trades_all, excluded_days)
    return compute_metrics(filtered)


HDR = (
    f"    {'#':>3} {'Variable':>20} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print(f"    {'─'*85}")


def print_row(i, label, m, is_base=False):
    marker = " <-- anchor" if is_base else ""
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>20} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def print_years(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"      R by year: {yr_str}")


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    print("RTY Asia ORB — Round 4: stop=4.0% + tp1=0.4 adopted from R3")
    print("=" * 90)
    print(f"Anchor: rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, "
          f"stop={ANCHOR_SESSION.stop_atr_pct}%, gap={ANCHOR_SESSION.min_gap_atr_pct}%")
    print(f"ORB=15m (20:00-20:15), entry≤23:15, flat=06:45, ATR={ANCHOR.atr_length}, "
          f"dir={ANCHOR.direction_filter}, DOW excl=Tue, ICF=OFF")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = load_1s_for_5m("RTY_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    all_results = []

    # ── 0. ANCHOR BASELINE ────────────────────────────────────────────
    print_header("0. ANCHOR BASELINE")
    anchor_trades_raw, _ = run_and_metric(df_5m, df_1m, df_1s, ANCHOR, dow_excl=set())
    anchor_trades, m_anchor = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    print_row(0, "ANCHOR", m_anchor, is_base=True)
    print_years(m_anchor)
    anchor_calmar = m_anchor["calmar_ratio"]
    anchor_neg = neg_year_set(m_anchor)
    print(f"      Negative years: {sorted(anchor_neg) if anchor_neg else 'none'}")

    # ── 1. STOP ATR % ────────────────────────────────────────────────
    stop_values = [2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0]
    print_header("1. STOP ATR % (anchor=4.0%)")
    for i, s in enumerate(stop_values, 1):
        sess = replace(ANCHOR_SESSION, stop_atr_pct=s)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"stop={s}%", m, is_base=(abs(s - 4.0) < 0.01))
        print_years(m)
        all_results.append(("stop_atr_pct", s, m))

    # ── 2. ORB WINDOW ────────────────────────────────────────────────
    orb_windows = [
        ("5m",  "20:00", "20:05", "20:05"),
        ("10m", "20:00", "20:10", "20:10"),
        ("15m", "20:00", "20:15", "20:15"),
        ("20m", "20:00", "20:20", "20:20"),
        ("30m", "20:00", "20:30", "20:30"),
    ]
    print_header("2. ORB WINDOW (anchor=15m)")
    for i, (label, orb_s, orb_e, entry_s) in enumerate(orb_windows, 1):
        sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"orb={label}", m, is_base=(label == "15m"))
        print_years(m)
        all_results.append(("orb_window", label, m))

    # ── 3. ATR LENGTH ────────────────────────────────────────────────
    atr_values = [3, 5, 7, 10, 12, 14, 20, 30]
    print_header("3. ATR LENGTH (anchor=14)")
    for i, atr in enumerate(atr_values, 1):
        config = replace(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"atr={atr}", m, is_base=(atr == 14))
        print_years(m)
        all_results.append(("atr_length", atr, m))

    # ── 4. ENTRY END TIME ────────────────────────────────────────────
    entry_ends = ["21:00", "22:00", "23:00", "23:15", "00:00", "01:00", "02:00", "03:00", "04:00"]
    print_header("4. ENTRY END TIME (anchor=23:15)")
    for i, ee in enumerate(entry_ends, 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"end={ee}", m, is_base=(ee == "23:15"))
        print_years(m)
        all_results.append(("entry_end", ee, m))

    # ── 5. FLAT START ────────────────────────────────────────────────
    flat_starts = ["02:00", "03:00", "04:00", "05:00", "06:00", "06:45"]
    print_header("5. FLAT START (anchor=06:45)")
    for i, fs in enumerate(flat_starts, 1):
        sess = replace(ANCHOR_SESSION, flat_start=fs)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"flat={fs}", m, is_base=(fs == "06:45"))
        all_results.append(("flat_start", fs, m))

    # ── 6. REWARD:RISK ───────────────────────────────────────────────
    rr_values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    print_header("6. REWARD:RISK (anchor=2.0)")
    for i, rr in enumerate(rr_values, 1):
        config = replace(ANCHOR, rr=rr)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"rr={rr}", m, is_base=(abs(rr - 2.0) < 0.01))
        print_years(m)
        all_results.append(("rr", rr, m))

    # ── 7. TP1 RATIO ─────────────────────────────────────────────────
    tp1_values = [0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6]
    print_header("7. TP1 RATIO (anchor=0.4)")
    for i, tp1 in enumerate(tp1_values, 1):
        config = replace(ANCHOR, tp1_ratio=tp1)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"tp1={tp1}", m, is_base=(abs(tp1 - 0.4) < 0.01))
        all_results.append(("tp1_ratio", tp1, m))

    # ── 8. MIN GAP ATR % ─────────────────────────────────────────────
    gap_values = [0.25, 0.5, 0.75, 0.9, 1.0, 1.5, 2.0, 2.5]
    print_header("8. MIN GAP ATR % (anchor=0.9%)")
    for i, g in enumerate(gap_values, 1):
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=g)
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        print_row(i, f"gap={g}%", m, is_base=(abs(g - 0.9) < 0.01))
        all_results.append(("min_gap_atr_pct", g, m))

    # ── 9. DOW EXCLUSION ─────────────────────────────────────────────
    dow_sets = [
        ("Tue only",    {1}),
        ("Tue+Mon",     {0, 1}),
        ("Tue+Wed",     {1, 2}),
        ("Tue+Thu",     {1, 3}),
    ]
    print_header("9. DOW EXCLUSION (anchor=excl Tue)")
    for i, (label, excluded) in enumerate(dow_sets, 1):
        m = run_dow_filtered(anchor_trades_raw, excluded)
        print_row(i, label, m, is_base=(excluded == {1}))
        print_years(m)
        all_results.append(("dow_exclusion", label, m))

    # ── 10. MAX GAP ATR % ────────────────────────────────────────────
    maxgap_atr_values = [0, 10, 15, 20, 25, 30]
    print_header("10. MAX GAP ATR % (anchor=0/off)")
    for i, mga in enumerate(maxgap_atr_values, 1):
        sess = replace(ANCHOR_SESSION, max_gap_atr_pct=float(mga))
        config = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        label = f"maxgap_atr={mga}%" if mga > 0 else "maxgap_atr=OFF"
        print_row(i, label, m, is_base=(mga == 0))
        all_results.append(("max_gap_atr_pct", mga if mga > 0 else "OFF", m))

    # ── 11. ICF ───────────────────────────────────────────────────────
    print_header("11. IMPULSE CLOSE FILTER (anchor=OFF)")
    for i, icf in enumerate([False, True], 1):
        config = replace(ANCHOR, impulse_close_filter=icf)
        _, m = run_and_metric(df_5m, df_1m, df_1s, config)
        label = "ICF=ON" if icf else "ICF=OFF"
        print_row(i, label, m, is_base=(not icf))
        all_results.append(("icf", icf, m))

    # ══════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════
    print(f"\n{'='*90}")
    print(f"  SUMMARY — Best value per dimension (by Calmar)")
    print(f"  Anchor Calmar: {anchor_calmar:.2f} | Anchor neg years: {sorted(anchor_neg) if anchor_neg else 'none'}")
    print(f"{'='*90}")
    print(f"  {'Variable':<20} {'Best Value':>12} {'Calmar':>8} {'Δ':>6} {'R/yr':>6} "
          f"{'DD':>6} {'NewNeg':>6} {'Adopt?':>8}")
    print(f"  {'─'*80}")

    from collections import defaultdict
    by_var = defaultdict(list)
    for var, val, m in all_results:
        by_var[var].append((val, m))

    dimension_order = [
        "stop_atr_pct", "orb_window", "atr_length", "entry_end", "flat_start",
        "rr", "tp1_ratio", "min_gap_atr_pct", "dow_exclusion",
        "max_gap_atr_pct", "icf",
    ]

    any_adopted = False
    for var in dimension_order:
        if var not in by_var:
            continue
        best_val, best_m = max(by_var[var], key=lambda x: x[1]["calmar_ratio"])
        delta = best_m["calmar_ratio"] - anchor_calmar
        r_yr = best_m["total_r"] / DATA_YEARS
        best_neg = neg_year_set(best_m)
        new_neg = best_neg - anchor_neg
        adopt = "YES" if delta > 0.3 and len(new_neg) == 0 else "no"
        if adopt == "YES":
            any_adopted = True
        new_neg_str = str(sorted(new_neg)) if new_neg else "none"
        print(f"  {var:<20} {str(best_val):>12} {best_m['calmar_ratio']:>8.2f} "
              f"{delta:>+6.2f} {r_yr:>6.1f} {best_m['max_drawdown_r']:>6.1f} "
              f"{new_neg_str:>6} {adopt:>8}")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")

    if not any_adopted:
        print(f"\n  ** CONVERGED — No dimensions pass adoption threshold **")
        print(f"  Ready for grid sweep on stop × rr × gap × tp1.")
    else:
        print(f"\n  ** NOT CONVERGED — Update anchor and re-sweep as R5 **")


if __name__ == "__main__":
    main()
