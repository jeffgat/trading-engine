#!/usr/bin/env python3
"""NQ Asia Continuation SHORT — Baseline Exploration.

Fresh short-specific optimization. The long config (15m ORB, stop=4%, rr=3.0,
tp1=0.6, ICF=ON, excl-Tue) should NOT be assumed optimal for shorts.

Sweep key structural dimensions broadly to find the best short anchor:
  1. Stop ATR %: 2-10%
  2. R:R ratio: 1.5-5.0
  3. ORB window: 5m, 10m, 15m, 20m, 25m, 30m
  4. TP1 ratio: 0.2-0.7
  5. Entry end: 22:00-03:00
  6. Flat start: 23:00-06:00
  7. ATR length: 3, 5, 7, 10, 14
  8. ICF: ON/OFF
  9. Gap: 0.5-2.0%

Start with direction=short, continuation strategy.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT_NAME = "NQ"
SESSION_NAME = "Asia"
START_DATE = "2016-01-01"

# Starting anchor — reasonable defaults for shorts
ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00",
    orb_end="20:15",
    entry_start="20:15",
    entry_end="23:00",
    flat_start="04:00",
    flat_end="07:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=1.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="short",
    rr=2.5,
    tp1_ratio=0.5,
    atr_length=5,
    impulse_close_filter=False,
    name="NQ Asia Short Baseline",
)

MIN_TP1_RATIO = 0.2


# -- Helpers -------------------------------------------------------------------

HDR = (
    f"    {'#':>3} {'Variable':>24} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} "
    f"{'NegYrs':>6}"
)
SEP = f"    {'-'*100}"


def neg_year_set(rby: dict) -> set:
    current_year = str(datetime.now().year)
    return {yr for yr, r in rby.items() if r < 0 and str(yr) != current_year}


def print_row(rank, label, m, rby=None):
    if rby is None:
        rby = m.get("r_by_year", {})
    full = {y: r for y, r in rby.items() if y not in ("2016", str(datetime.now().year))}
    neg = sum(1 for r in full.values() if r < 0)
    neg_list = ",".join(y for y, r in sorted(full.items()) if r < 0)
    n_years = max(len(full), 1)
    print(
        f"    {rank:>3} {label:>24} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.3f} "
        f"{m['total_r']:>7.1f} {m['total_r']/n_years:>6.1f} "
        f"{m['max_drawdown_r']:>6.1f} {m.get('calmar_ratio', 0):>7.2f} "
        f"{neg:>3} {neg_list}"
    )


def print_r_by_year(m):
    rby = m.get("r_by_year", {})
    years = sorted(rby.items())
    yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
    print(f"          R by year: {yr_str}")


def run_sweep(df_5m, df_1m, df_1s, dim_name, configs_with_labels):
    """Run a sweep over (label, config) pairs and print results."""
    print(f"\n  === {dim_name} ===")
    print(HDR)
    print(SEP)

    results = []
    for label, cfg in configs_with_labels:
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)
        results.append((label, m))

    # Sort by Calmar
    results.sort(key=lambda x: x[1].get("calmar_ratio", 0), reverse=True)

    for rank, (label, m) in enumerate(results, 1):
        print_row(rank, label, m)
        if rank <= 3:
            print_r_by_year(m)

    # Return best
    return results[0] if results else None


def main():
    print(f"{INSTRUMENT_NAME} {SESSION_NAME} SHORT — Baseline Exploration")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    # ---- 0. Anchor baseline ----
    print("\n  === ANCHOR (defaults) ===")
    print(HDR)
    print(SEP)
    trades = run_backtest(df_5m, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m_anchor = compute_metrics(trades)
    print_row(1, "anchor", m_anchor)
    print_r_by_year(m_anchor)

    # ---- 1. Stop ATR % ----
    stops = [2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 10.0, 12.0, 15.0]
    configs = []
    for s in stops:
        sess = replace(ANCHOR_SESSION, stop_atr_pct=s)
        cfg = replace(ANCHOR, sessions=(sess,))
        configs.append((f"stop={s:.1f}%", cfg))
    best_stop = run_sweep(df_5m, df_1m, df_1s, "Stop ATR %", configs)

    # ---- 2. ORB Window ----
    orb_configs = [
        ("5m",  "20:00", "20:05", "20:05"),
        ("10m", "20:00", "20:10", "20:10"),
        ("15m", "20:00", "20:15", "20:15"),
        ("20m", "20:00", "20:20", "20:20"),
        ("25m", "20:00", "20:25", "20:25"),
        ("30m", "20:00", "20:30", "20:30"),
        ("45m", "20:00", "20:45", "20:45"),
    ]
    configs = []
    for label, orb_s, orb_e, entry_s in orb_configs:
        sess = replace(ANCHOR_SESSION, orb_start=orb_s, orb_end=orb_e, entry_start=entry_s)
        cfg = replace(ANCHOR, sessions=(sess,))
        configs.append((f"ORB={label}", cfg))
    best_orb = run_sweep(df_5m, df_1m, df_1s, "ORB Window", configs)

    # ---- 3. R:R Ratio ----
    rrs = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
    configs = [(f"rr={r:.1f}", replace(ANCHOR, rr=r)) for r in rrs]
    best_rr = run_sweep(df_5m, df_1m, df_1s, "R:R Ratio", configs)

    # ---- 4. TP1 Ratio ----
    tp1s = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    configs = [(f"tp1={t:.2f}", replace(ANCHOR, tp1_ratio=t)) for t in tp1s]
    best_tp1 = run_sweep(df_5m, df_1m, df_1s, "TP1 Ratio", configs)

    # ---- 5. ATR Length ----
    atrs = [3, 5, 7, 10, 14, 20, 30]
    configs = [(f"ATR={a}", replace(ANCHOR, atr_length=a)) for a in atrs]
    best_atr = run_sweep(df_5m, df_1m, df_1s, "ATR Length", configs)

    # ---- 6. Entry End ----
    entry_ends = ["21:30", "22:00", "22:30", "23:00", "23:30", "00:00",
                  "00:30", "01:00", "02:00", "03:00"]
    configs = []
    for ee in entry_ends:
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        cfg = replace(ANCHOR, sessions=(sess,))
        configs.append((f"entry<={ee}", cfg))
    best_entry = run_sweep(df_5m, df_1m, df_1s, "Entry End", configs)

    # ---- 7. Flat Start ----
    flat_starts = ["23:00", "00:00", "01:00", "02:00", "03:00", "04:00",
                   "05:00", "06:00"]
    configs = []
    for fs in flat_starts:
        sess = replace(ANCHOR_SESSION, flat_start=fs)
        cfg = replace(ANCHOR, sessions=(sess,))
        configs.append((f"flat={fs}", cfg))
    best_flat = run_sweep(df_5m, df_1m, df_1s, "Flat Start", configs)

    # ---- 8. Min Gap ATR % ----
    gaps = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
    configs = []
    for g in gaps:
        sess = replace(ANCHOR_SESSION, min_gap_atr_pct=g)
        cfg = replace(ANCHOR, sessions=(sess,))
        configs.append((f"gap={g:.2f}%", cfg))
    best_gap = run_sweep(df_5m, df_1m, df_1s, "Min Gap ATR %", configs)

    # ---- 9. ICF ----
    configs = [
        ("ICF=OFF", replace(ANCHOR, impulse_close_filter=False)),
        ("ICF=ON", replace(ANCHOR, impulse_close_filter=True)),
    ]
    best_icf = run_sweep(df_5m, df_1m, df_1s, "ICF", configs)

    # ---- 10. Max Gap Points ----
    max_gaps = [0, 25, 50, 75, 100, 150, 200]
    configs = []
    for mg in max_gaps:
        sess = replace(ANCHOR_SESSION, max_gap_points=float(mg) if mg > 0 else 0.0)
        cfg = replace(ANCHOR, sessions=(sess,))
        label = f"maxgap={mg}pts" if mg > 0 else "maxgap=OFF"
        configs.append((label, cfg))
    best_maxgap = run_sweep(df_5m, df_1m, df_1s, "Max Gap Points", configs)

    # ---- 11. Strategy type ----
    configs = [
        ("continuation", replace(ANCHOR, strategy="continuation")),
        ("reversal", replace(ANCHOR, strategy="reversal")),
    ]
    best_strat = run_sweep(df_5m, df_1m, df_1s, "Strategy Type", configs)

    # ---- Summary ----
    print(f"\n{'='*110}")
    print("  SUMMARY — Best per dimension (by Calmar)")
    print(f"{'='*110}")
    bests = [
        ("Stop ATR %", best_stop),
        ("ORB Window", best_orb),
        ("R:R Ratio", best_rr),
        ("TP1 Ratio", best_tp1),
        ("ATR Length", best_atr),
        ("Entry End", best_entry),
        ("Flat Start", best_flat),
        ("Min Gap %", best_gap),
        ("ICF", best_icf),
        ("Max Gap Pts", best_maxgap),
        ("Strategy", best_strat),
    ]
    for dim, best in bests:
        if best:
            label, m = best
            cal = m.get("calmar_ratio", 0)
            rby = m.get("r_by_year", {})
            full = {y: r for y, r in rby.items() if y not in ("2016", str(datetime.now().year))}
            neg = sum(1 for r in full.values() if r < 0)
            print(f"    {dim:<15} {label:<24} Calmar={cal:.2f}  Sharpe={m['sharpe_ratio']:.3f}  "
                  f"Trades={m['total_trades']}  NegYrs={neg}")

    print("\n  Use these findings to construct the initial short anchor for variable sweeps.")


if __name__ == "__main__":
    main()
