#!/usr/bin/env python3
"""ES LDN Continuation Both — Variable Sweeps Round 10 (Post Grid R2).

Grid R2 winner adopted: stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14
Structural: ORB 10m, entry 08:25, flat 08:20, both, DOW excl Mon, ICF off, 1s mag.
Calmar 8.47, 0 neg years, 193.6R net, -22.9R DD.
"""

import sys, time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON, TUE, WED, THU, FRI

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]
DOW_EXCLUDED = {MON}

ANCHOR_SESSION = SessionConfig(
    name="LDN", orb_start="03:00", orb_end="03:10", entry_start="03:10",
    entry_end="08:25", flat_start="08:20", flat_end="08:25",
    stop_atr_pct=6.0, min_gap_atr_pct=1.0, max_gap_points=50.0,
)
ANCHOR = StrategyConfig(
    rr=4.0, tp1_ratio=0.5, risk_usd=5000.0, atr_length=14,
    sessions=(ANCHOR_SESSION,), instrument=ES, strategy="continuation",
    direction_filter="both", use_bar_magnifier=True,
)

def neg_year_set(m):
    rby = m.get("r_by_year", {})
    return {y for y, r in rby.items() if y in FULL_YEARS and r < 0}
def neg_years(m): return len(neg_year_set(m))
def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0
def calmar(m): return m.get("calmar_ratio", 0.0)

def run_and_measure(df, config, df_1m, df_1s, dow_filter=None):
    trades = run_backtest(df, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    effective_dow = dow_filter if dow_filter is not None else DOW_EXCLUDED
    if effective_dow: trades = apply_dow_filter(trades, effective_dow)
    return trades, compute_metrics(trades)

def print_sweep_table(results, dim_name, anchor_value):
    print(f"\n{'='*90}")
    print(f"  DIMENSION: {dim_name} (anchor = {anchor_value})")
    print(f"{'='*90}")
    print(f"  {'Value':<15s} {'Trades':>7s} {'WR':>7s} {'PF':>7s} {'Sharpe':>8s} "
          f"{'Net R':>8s} {'R/yr':>7s} {'MaxDD':>8s} {'Calmar':>8s} {'NegYr':>6s}")
    print(f"  {'-'*15} {'-'*7} {'-'*7} {'-'*7} {'-'*8} {'-'*8} {'-'*7} {'-'*8} {'-'*8} {'-'*6}")
    for val, m in results:
        marker = " <<<" if str(val) == str(anchor_value) else ""
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

def sweep_stop(df, df_1m, df_1s):
    results = []
    for v in [5.0, 6.0, 7.5, 10.0, 12.0, 15.0]:
        sess = replace(ANCHOR_SESSION, stop_atr_pct=v)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Stop ATR %", 6.0); return results

def sweep_orb(df, df_1m, df_1s):
    results = []
    for label, os, oe, es in [("5m","03:00","03:05","03:05"),("10m","03:00","03:10","03:10"),
        ("15m","03:00","03:15","03:15"),("20m","03:00","03:20","03:20"),("30m","03:00","03:30","03:30"),("45m","03:00","03:45","03:45")]:
        sess = replace(ANCHOR_SESSION, orb_start=os, orb_end=oe, entry_start=es)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((label, m))
    print_sweep_table(results, "ORB Window", "10m"); return results

def sweep_atr(df, df_1m, df_1s):
    results = []
    for v in [3, 5, 7, 10, 14, 20, 30, 50]:
        _, m = run_and_measure(df, replace(ANCHOR, atr_length=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "ATR Length", 14); return results

def sweep_entry_end(df, df_1m, df_1s):
    results = []
    for v in ["05:00","06:00","07:00","07:30","08:00","08:25"]:
        sess = replace(ANCHOR_SESSION, entry_end=v)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Entry End", "08:25"); return results

def sweep_flat(df, df_1m, df_1s):
    results = []
    for v in ["06:00","06:30","07:00","07:30","08:00","08:20"]:
        sess = replace(ANCHOR_SESSION, flat_start=v, flat_end="08:25")
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Flat Start", "08:20"); return results

def sweep_dir(df, df_1m, df_1s):
    results = []
    for v in ["both","long","short"]:
        _, m = run_and_measure(df, replace(ANCHOR, direction_filter=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Direction", "both"); return results

def sweep_rr(df, df_1m, df_1s):
    results = []
    for v in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        _, m = run_and_measure(df, replace(ANCHOR, rr=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "R:R", 4.0); return results

def sweep_tp1(df, df_1m, df_1s):
    results = []
    for v in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        _, m = run_and_measure(df, replace(ANCHOR, tp1_ratio=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "TP1 Ratio", 0.5); return results

def sweep_gap(df, df_1m, df_1s):
    results = []
    for v in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=v)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Min Gap ATR %", 1.0); return results

def sweep_dow(df, df_1m, df_1s):
    trades = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filters = {"none":set(),"Mon":{MON},"Tue":{TUE},"Wed":{WED},"Thu":{THU},"Fri":{FRI},"M+F":{MON,FRI},"Th+F":{THU,FRI}}
    results = []
    for label, excl in filters.items():
        filtered = apply_dow_filter(trades, excl) if excl else trades
        results.append((label, compute_metrics(filtered)))
    print_sweep_table(results, "DOW Exclusion", "Mon"); return results

def sweep_max_gap(df, df_1m, df_1s):
    values = [("OFF",0,0),("20pt",20,0),("50pt",50,0),("20%ATR",0,20),("50%ATR",0,50),("100%ATR",0,100)]
    results = []
    for label, pts, atr_pct in values:
        sess = replace(ANCHOR_SESSION, max_gap_points=float(pts), max_gap_atr_pct=float(atr_pct))
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((label, m))
    print_sweep_table(results, "Max Gap Filter", "OFF"); return results

def sweep_icf(df, df_1m, df_1s):
    results = []
    for v in [False, True]:
        _, m = run_and_measure(df, replace(ANCHOR, impulse_close_filter=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "ICF", False); return results

if __name__ == "__main__":
    print("=" * 90)
    print("  ES LDN CONTINUATION BOTH — VARIABLE SWEEPS ROUND 10 (POST GRID R2)")
    print("=" * 90)
    print(f"  Anchor: stop=6%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, ORB 10m")
    print(f"  Flat 08:20, entry 08:25, both, DOW excl Mon, ICF off, 1s mag")
    print(f"  Grid R2 winner adopted\n")

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time()-t0:.1f}s\n", flush=True)

    print("  Running anchor baseline...", flush=True)
    _, anchor_m = run_and_measure(df, ANCHOR, df_1m, df_1s)
    anchor_cal = calmar(anchor_m)
    anchor_neg = neg_year_set(anchor_m)
    print(f"  Anchor: Calmar={anchor_cal:.2f}, NegYrs={len(anchor_neg)} {anchor_neg}")
    rby = anchor_m.get("r_by_year", {})
    if rby:
        parts = [f"{y}:{r:+.1f}" for y, r in sorted(rby.items())]
        print(f"  R/yr: {', '.join(parts)}\n")

    t_total = time.time()
    all_sweeps = {}
    sweeps = [
        ("Stop ATR %", 6.0, sweep_stop), ("ORB Window", "10m", sweep_orb),
        ("ATR Length", 14, sweep_atr), ("Entry End", "08:25", sweep_entry_end),
        ("Flat Start", "08:20", sweep_flat), ("Direction", "both", sweep_dir),
        ("R:R", 4.0, sweep_rr), ("TP1 Ratio", 0.5, sweep_tp1),
        ("Min Gap ATR%", 1.0, sweep_gap), ("DOW Exclusion", "Mon", sweep_dow),
        ("Max Gap", "OFF", sweep_max_gap), ("ICF", False, sweep_icf),
    ]
    for dim_name, anchor_val, sweep_fn in sweeps:
        t_dim = time.time()
        results = sweep_fn(df, df_1m, df_1s)
        print(f"  [{dim_name}] completed in {time.time()-t_dim:.1f}s", flush=True)
        best_val, best_cal, best_m = best_by_calmar(results)
        all_sweeps[dim_name] = {
            "anchor_val": anchor_val, "best_val": best_val, "best_calmar": best_cal,
            "best_neg_years": neg_year_set(best_m) if best_m else set(),
            "best_trades": best_m["total_trades"] if best_m else 0,
            "delta": best_cal - anchor_cal,
        }

    total_time = time.time() - t_total
    print(f"\n\n{'='*90}")
    print(f"  SUMMARY — Variable Sweeps Round 10 ({total_time:.0f}s)")
    print(f"{'='*90}")
    print(f"  Anchor Calmar: {anchor_cal:.2f} | Neg years: {len(anchor_neg)} {anchor_neg}\n")
    print(f"  {'Dimension':<16s} {'Anchor':<12s} {'Best':<12s} {'Calmar':>8s} {'Delta':>8s} "
          f"{'NegYr':>6s} {'Trades':>7s} {'Adopt?':>7s}")
    print(f"  {'-'*16} {'-'*12} {'-'*12} {'-'*8} {'-'*8} {'-'*6} {'-'*7} {'-'*7}")

    adoptions = []
    for dim_name, info in all_sweeps.items():
        delta = info["delta"]
        new_neg = info["best_neg_years"] - anchor_neg
        adopt = delta > 0.3 and len(new_neg) == 0 and info["best_trades"] > 100
        adopt_str = "YES" if adopt else "no"
        if adopt: adoptions.append((dim_name, info["best_val"], info["best_calmar"]))
        print(f"  {dim_name:<16s} {str(info['anchor_val']):<12s} {str(info['best_val']):<12s} "
              f"{info['best_calmar']:>8.2f} {delta:>+8.2f} "
              f"{len(info['best_neg_years']):>5d} {info['best_trades']:>7d} {adopt_str:>7s}")

    print(f"\n  Adoptions: {len(adoptions)}")
    for dim, val, cal in adoptions: print(f"    {dim}: {val} (Calmar {cal:.2f})")

    if not adoptions:
        print(f"\n  >>> CONVERGED. Ready for robust pipeline.")
        print(f"\n  Final anchor: stop=6%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14")
        print(f"    ORB 10m, entry 08:25, flat 08:20, both, DOW excl Mon, 1s mag")
    else:
        print(f"\n  >>> {len(adoptions)} adoption(s) — update anchor and re-sweep")
