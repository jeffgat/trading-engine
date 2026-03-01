#!/usr/bin/env python3
"""NQ NY Continuation — ORB-Based Stop & Gap Test (Longs-Only).

Tests stop_orb_pct and min_gap_orb_pct as alternatives to ATR-based params.
When > 0, these override the ATR-based equivalents:
  stop_orb_pct: stop distance = (pct/100) * ORB_range (instead of ATR-based)
  min_gap_orb_pct: min FVG size = (pct/100) * ORB_range (instead of ATR-based)

Base anchor (from R8 / grid winner):
  stop=7.0% ATR, gap=2.5% ATR, rr=3.25, tp1=0.45, ATR=20, 20m ORB,
  entry<=12:00, flat=15:30, ICF=ON, excl Fri, long-only

Sweeps:
  1. stop_orb_pct: 10%, 15%, 20%, 25%, 30%, 40%, 50%, 60%, 75% (ATR stop=7% as baseline)
  2. min_gap_orb_pct: 3%, 5%, 7%, 10%, 15%, 20%, 25%, 30% (ATR gap=2.5% as baseline)
  3. Combined best stop_orb + best gap_orb (if both improve)
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="12:00",
    flat_start="15:30",
    flat_end="16:00",
    stop_atr_pct=7.0,
    min_gap_atr_pct=2.5,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=3.25,
    tp1_ratio=0.45,
    atr_length=20,
    impulse_close_filter=True,
    name="NQ NY Long ORB-pct Test",
)

DOW_EXCL = {4}


def run_and_metric(df_5m, df_1m, df_1s, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    return trades, compute_metrics(trades)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def median_stop_ticks(trades):
    from statistics import median
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / NQ.min_tick for t in filled)


HDR = (
    f"    {'#':>3} {'Variable':>28} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'MedTk':>6}"
)


def print_header(title):
    print(f"\n{'='*100}")
    print(f"  {title}")
    print(f"{'='*100}")
    print(HDR)
    print(f"    {'---'*34}")


def print_row(i, label, m, med_ticks, is_base=False):
    marker = " <<<" if is_base else ""
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>28} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f} "
        f"{med_ticks:>6.1f}{marker}"
    )


def print_years(m):
    rby = m.get("r_by_year", {})
    if rby:
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(rby.items()))
        print(f"      R by year: {yr_str}")


def main():
    print("NQ NY ORB — Stop & Gap as % of ORB Range Test")
    print("=" * 100)
    print(f"Baseline: stop_atr=7.0%, gap_atr=2.5%, rr=3.25, tp1=0.45, ATR=20")
    print(f"ORB=09:30-09:50 (20m), entry<=12:00, flat=15:30, ICF=ON, excl Fri, long-only")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m) if df_1m is not None else 0:,} | "
          f"1s: {len(df_1s) if df_1s is not None else 0:,} [{time.time()-t0:.1f}s]")

    # -- 0. ATR BASELINE -------------------------------------------------------
    print_header("0. ATR BASELINE (stop=7% ATR, gap=2.5% ATR)")
    trades_base, m_base = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    med_base = median_stop_ticks(trades_base)
    print_row(0, "ATR baseline", m_base, med_base, is_base=True)
    print_years(m_base)
    base_cal = m_base["calmar_ratio"]
    base_neg = neg_year_set(m_base)
    print(f"      Neg years: {sorted(base_neg) if base_neg else 'none'}")

    # -- 1. STOP as % of ORB RANGE --------------------------------------------
    stop_orb_vals = [10, 15, 20, 25, 30, 40, 50, 60, 75, 100]
    print_header("1. STOP as % of ORB RANGE (gap stays ATR-based 2.5%)")
    best_stop_cal, best_stop_lbl, best_stop_val = base_cal, "ATR baseline", 0
    best_stop_m, best_stop_trades = m_base, trades_base
    for i, sopct in enumerate(stop_orb_vals, 1):
        sess = replace(ANCHOR_SESSION, stop_orb_pct=float(sopct))
        cfg = replace(ANCHOR, sessions=(sess,))
        trades, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        med = median_stop_ticks(trades)
        if med < 10:
            print(f"    {i:>3} {'stop_orb=' + str(sopct) + '%':>28}  SKIP (median stop {med:.1f} ticks < 10)")
            continue
        print_row(i, f"stop_orb={sopct}%", m, med)
        print_years(m)
        neg = neg_year_set(m)
        new_neg = neg - base_neg
        delta = m["calmar_ratio"] - base_cal
        tag = "BETTER" if delta > 0.3 and len(new_neg) == 0 and m["total_trades"] > 100 else ""
        if tag:
            print(f"      ** {tag}: delta {delta:+.2f}, no new neg years")
        if m["calmar_ratio"] > best_stop_cal and len(new_neg) == 0 and m["total_trades"] > 100:
            best_stop_cal = m["calmar_ratio"]
            best_stop_lbl = f"stop_orb={sopct}%"
            best_stop_val = sopct
            best_stop_m = m
            best_stop_trades = trades

    delta_stop = best_stop_cal - base_cal
    print(f"\n    Best stop_orb: {best_stop_lbl} (Calmar {best_stop_cal:.2f}, delta {delta_stop:+.2f})")

    # -- 2. GAP as % of ORB RANGE ---------------------------------------------
    gap_orb_vals = [3, 5, 7, 10, 15, 20, 25, 30]
    print_header("2. MIN GAP as % of ORB RANGE (stop stays ATR-based 7%)")
    best_gap_cal, best_gap_lbl, best_gap_val = base_cal, "ATR baseline", 0
    best_gap_m = m_base
    for i, gopct in enumerate(gap_orb_vals, 1):
        sess = replace(ANCHOR_SESSION, min_gap_orb_pct=float(gopct))
        cfg = replace(ANCHOR, sessions=(sess,))
        trades, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
        med = median_stop_ticks(trades)
        print_row(i, f"gap_orb={gopct}%", m, med)
        print_years(m)
        neg = neg_year_set(m)
        new_neg = neg - base_neg
        delta = m["calmar_ratio"] - base_cal
        tag = "BETTER" if delta > 0.3 and len(new_neg) == 0 and m["total_trades"] > 100 else ""
        if tag:
            print(f"      ** {tag}: delta {delta:+.2f}, no new neg years")
        if m["calmar_ratio"] > best_gap_cal and len(new_neg) == 0 and m["total_trades"] > 100:
            best_gap_cal = m["calmar_ratio"]
            best_gap_lbl = f"gap_orb={gopct}%"
            best_gap_val = gopct
            best_gap_m = m

    delta_gap = best_gap_cal - base_cal
    print(f"\n    Best gap_orb: {best_gap_lbl} (Calmar {best_gap_cal:.2f}, delta {delta_gap:+.2f})")

    # -- 3. COMBINED: best stop_orb + best gap_orb ----------------------------
    if best_stop_val > 0 or best_gap_val > 0:
        print_header("3. COMBINED — Best ORB-based stop + gap together")

        combos = []
        # best stop_orb alone
        if best_stop_val > 0:
            combos.append((f"stop_orb={best_stop_val}% only", best_stop_val, 0))
        # best gap_orb alone
        if best_gap_val > 0:
            combos.append((f"gap_orb={best_gap_val}% only", 0, best_gap_val))
        # both together
        if best_stop_val > 0 and best_gap_val > 0:
            combos.append((f"stop_orb={best_stop_val}% + gap_orb={best_gap_val}%", best_stop_val, best_gap_val))
        # a few extra combos around the bests
        if best_stop_val > 0 and best_gap_val > 0:
            for sv in [max(10, best_stop_val - 10), best_stop_val, min(100, best_stop_val + 10)]:
                for gv in [max(3, best_gap_val - 5), best_gap_val, min(30, best_gap_val + 5)]:
                    label = f"stop_orb={sv}% + gap_orb={gv}%"
                    if not any(c[0] == label for c in combos):
                        combos.append((label, sv, gv))

        for i, (label, sv, gv) in enumerate(combos, 1):
            sess = replace(ANCHOR_SESSION,
                           stop_orb_pct=float(sv) if sv > 0 else 0.0,
                           min_gap_orb_pct=float(gv) if gv > 0 else 0.0)
            cfg = replace(ANCHOR, sessions=(sess,))
            trades, m = run_and_metric(df_5m, df_1m, df_1s, cfg)
            med = median_stop_ticks(trades)
            if med < 10:
                print(f"    {i:>3} {label:>28}  SKIP (median stop {med:.1f} ticks < 10)")
                continue
            neg = neg_year_set(m)
            new_neg = neg - base_neg
            is_clean = len(new_neg) == 0 and m["total_trades"] > 100
            print_row(i, label, m, med)
            print_years(m)
            delta = m["calmar_ratio"] - base_cal
            tag = "BETTER" if delta > 0.3 and is_clean else ""
            if tag:
                print(f"      ** {tag}: delta {delta:+.2f}, neg_yrs={sorted(neg) if neg else 'none'}")

    # -- SUMMARY ---------------------------------------------------------------
    elapsed = time.time() - t0
    print(f"\n{'='*100}")
    print(f"  SUMMARY — ORB-Based Stop & Gap Test")
    print(f"  ATR baseline: Calmar {base_cal:.2f} (stop=7% ATR, gap=2.5% ATR)")
    print(f"  Best stop_orb: {best_stop_lbl} (Calmar {best_stop_cal:.2f}, delta {delta_stop:+.2f})")
    print(f"  Best gap_orb: {best_gap_lbl} (Calmar {best_gap_cal:.2f}, delta {delta_gap:+.2f})")
    print(f"  Runtime: {elapsed:.0f}s ({elapsed/60:.1f}m)")
    print(f"{'='*100}")

    if delta_stop > 0.3 or delta_gap > 0.3:
        print(f"\n  ** ORB-based params show improvement — consider adopting into variable sweep loop **")
    else:
        print(f"\n  ** ATR-based params remain better — keep current anchor **")


if __name__ == "__main__":
    main()
