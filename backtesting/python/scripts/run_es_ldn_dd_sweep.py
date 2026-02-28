#!/usr/bin/env python3
"""ES LDN Continuation Both — DD reduction sweep across key dimensions.

Anchor (R11): stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, max_gap=20%ATR,
ORB 10m, entry 08:25, flat 08:20, DOW excl Mon, ICF off, 1s mag.
Calmar 9.18, DD -20.9R, 0 neg years.

Goal: find which dimensions compress max DD without destroying Calmar.
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
    stop_atr_pct=6.0, min_gap_atr_pct=1.0, max_gap_points=0.0,
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
    if effective_dow:
        trades = apply_dow_filter(trades, effective_dow)
    return trades, compute_metrics(trades)

def print_sweep_table(results, dim_name, anchor_value):
    print(f"\n{'='*100}")
    print(f"  DIMENSION: {dim_name} (anchor = {anchor_value})")
    print(f"{'='*100}")
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
        rby = m.get("r_by_year", {})
        if rby:
            parts = [f"{y}:{r:+.0f}" for y, r in sorted(rby.items())]
            print(f"                  R/yr: {', '.join(parts)}")


# ── 1. TP1 Ratio ──────────────────────────────────────────────────────────────
def sweep_tp1(df, df_1m, df_1s):
    results = []
    for v in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
        _, m = run_and_measure(df, replace(ANCHOR, tp1_ratio=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "TP1 Ratio", 0.5)
    return results

# ── 2. R:R ─────────────────────────────────────────────────────────────────────
def sweep_rr(df, df_1m, df_1s):
    results = []
    for v in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        _, m = run_and_measure(df, replace(ANCHOR, rr=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "R:R", 4.0)
    return results

# ── 3. Flat Start ──────────────────────────────────────────────────────────────
def sweep_flat(df, df_1m, df_1s):
    results = []
    for v in ["05:00", "05:30", "06:00", "06:30", "07:00", "07:30", "08:00", "08:20"]:
        sess = replace(ANCHOR_SESSION, flat_start=v, flat_end="08:25")
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Flat Start", "08:20")
    return results

# ── 4. Entry End ───────────────────────────────────────────────────────────────
def sweep_entry_end(df, df_1m, df_1s):
    results = []
    for v in ["04:00", "05:00", "06:00", "07:00", "07:30", "08:00", "08:25"]:
        sess = replace(ANCHOR_SESSION, entry_end=v)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Entry End", "08:25")
    return results

# ── 5. Direction ───────────────────────────────────────────────────────────────
def sweep_dir(df, df_1m, df_1s):
    results = []
    for v in ["both", "long", "short"]:
        _, m = run_and_measure(df, replace(ANCHOR, direction_filter=v), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Direction", "both")
    return results

# ── 6. DOW Exclusion ──────────────────────────────────────────────────────────
def sweep_dow(df, df_1m, df_1s):
    trades = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filters = {
        "none": set(), "Mon": {MON}, "Tue": {TUE}, "Wed": {WED},
        "Thu": {THU}, "Fri": {FRI}, "M+T": {MON, TUE}, "M+F": {MON, FRI},
        "M+W": {MON, WED}, "M+Th": {MON, THU},
    }
    results = []
    for label, excl in filters.items():
        filtered = apply_dow_filter(trades, excl) if excl else trades
        results.append((label, compute_metrics(filtered)))
    print_sweep_table(results, "DOW Exclusion", "Mon")
    return results

# ── 7. Min Gap ATR % ──────────────────────────────────────────────────────────
def sweep_gap(df, df_1m, df_1s):
    results = []
    for v in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]:
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=v)
        _, m = run_and_measure(df, replace(ANCHOR, sessions=(sess,)), df_1m, df_1s)
        results.append((v, m))
    print_sweep_table(results, "Min Gap ATR %", 1.0)
    return results


if __name__ == "__main__":
    print("=" * 100)
    print("  ES LDN CONTINUATION BOTH — DD REDUCTION SWEEP")
    print("=" * 100)
    print(f"  Anchor (R11): stop=6.0%, rr=4.0, gap=1.0%, tp1=0.5, ATR=14, max_gap=20%ATR")
    print(f"  ORB 10m, entry 08:25, flat 08:20, DOW excl Mon, 1s mag")
    print(f"  Baseline: Calmar 9.18, DD -20.9R, 0 neg years\n")

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time()-t0:.1f}s\n", flush=True)

    # Run anchor baseline
    print("  Running anchor baseline...", flush=True)
    _, anchor_m = run_and_measure(df, ANCHOR, df_1m, df_1s)
    anchor_dd = anchor_m["max_drawdown_r"]
    anchor_cal = calmar(anchor_m)
    print(f"  Anchor: Calmar={anchor_cal:.2f}, DD={anchor_dd:.1f}R, NegYrs={neg_years(anchor_m)}\n")

    t_total = time.time()

    sweeps = [
        ("TP1 Ratio", 0.5, sweep_tp1),
        ("R:R", 4.0, sweep_rr),
        ("Flat Start", "08:20", sweep_flat),
        ("Entry End", "08:25", sweep_entry_end),
        ("Direction", "both", sweep_dir),
        ("DOW Exclusion", "Mon", sweep_dow),
        ("Min Gap ATR%", 1.0, sweep_gap),
    ]

    summary = []
    for dim_name, anchor_val, sweep_fn in sweeps:
        t_dim = time.time()
        results = sweep_fn(df, df_1m, df_1s)
        print(f"  [{dim_name}] completed in {time.time()-t_dim:.1f}s\n", flush=True)

        # Find best DD with Calmar >= 5.0 and 0 neg years
        best_dd_val, best_dd, best_cal = None, anchor_dd, anchor_cal
        for val, m in results:
            dd = m["max_drawdown_r"]
            c = calmar(m)
            if dd > best_dd and c >= 5.0 and neg_years(m) <= 1:
                best_dd_val, best_dd, best_cal = val, dd, c

        # Also find overall best DD (any Calmar)
        lowest_dd_val, lowest_dd, lowest_cal = None, anchor_dd, anchor_cal
        for val, m in results:
            dd = m["max_drawdown_r"]
            if dd > lowest_dd:
                lowest_dd_val, lowest_dd, lowest_cal = val, dd, calmar(m)

        summary.append({
            "dim": dim_name, "anchor_val": anchor_val,
            "best_dd_val": best_dd_val, "best_dd": best_dd, "best_cal": best_cal,
            "lowest_dd_val": lowest_dd_val, "lowest_dd": lowest_dd, "lowest_cal": lowest_cal,
        })

    total_time = time.time() - t_total
    print(f"\n\n{'='*100}")
    print(f"  SUMMARY — DD Reduction Sweep ({total_time:.0f}s)")
    print(f"{'='*100}")
    print(f"  Anchor: Calmar {anchor_cal:.2f}, DD {anchor_dd:.1f}R\n")
    print(f"  {'Dimension':<16s} {'Anchor':<10s} {'Best DD val':<12s} {'DD':>8s} {'DD Δ':>8s} {'Calmar':>8s}"
          f"  |  {'Low DD val':<12s} {'DD':>8s} {'Calmar':>8s}")
    print(f"  {'-'*16} {'-'*10} {'-'*12} {'-'*8} {'-'*8} {'-'*8}  |  {'-'*12} {'-'*8} {'-'*8}")

    for s in summary:
        dd_delta = s["best_dd"] - anchor_dd if s["best_dd_val"] else 0
        bv = str(s["best_dd_val"]) if s["best_dd_val"] else "—"
        lv = str(s["lowest_dd_val"]) if s["lowest_dd_val"] else "—"
        print(f"  {s['dim']:<16s} {str(s['anchor_val']):<10s} {bv:<12s} {s['best_dd']:>7.1f}R {dd_delta:>+7.1f}R {s['best_cal']:>8.2f}"
              f"  |  {lv:<12s} {s['lowest_dd']:>7.1f}R {s['lowest_cal']:>8.2f}")
