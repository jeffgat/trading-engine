#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 9: fine-grained stop ATR % sweep.

Stop has always been tested in coarse steps (7.5, 10, 12.5, 15).
This round tests 3-14% in 1% increments against the top long-only configs.

Configs tested:
  1. g=3.5 rr=2.50 tp1=0.4  (R7 best Calmar, 14.97)
  2. g=3.0 rr=2.50 tp1=0.4  (R6 best Calmar, 14.86)
  3. g=3.5 rr=3.00 tp1=0.3  (R7 lowest DD, -8.8R)
  4. g=3.0 rr=2.00 tp1=0.5  (R5 base, 14.56)
  5. g=3.0 rr=2.75 tp1=0.5  (best R/yr long, 14.7)
  6. g=3.0 rr=2.75 tp1=0.6  (R7 #5 Calmar, 13.88)
  7. g=3.0 rr=2.25 tp1=0.6  (R7 #6 Calmar, 13.83)

Base: long-only, 20m ORB, entry 09:50-15:00, magnifier
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(entry_start="09:50", entry_end="15:00", gap=3.0,
                rr=2.0, tp1=0.5, stop=10.0, direction="long", **extra):
    sess = replace(NY_20M,
                   entry_start=entry_start,
                   entry_end=entry_end,
                   min_gap_atr_pct=gap,
                   stop_atr_pct=stop)
    config = StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction,
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY Stop Sweep",
    )
    if extra:
        config = with_overrides(config, **extra)
    return config


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>45} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*110}")
    print(f"  {title}")
    print(f"{'='*110}")
    print(HDR)
    print("-" * 110)


def print_row(i, label, m, marker=""):
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>45} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 9: Fine-Grained Stop ATR % Sweep (3-14%)")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    stops = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 13.0, 14.0]

    configs_to_test = [
        # (label, gap, rr, tp1)
        ("g3.5 rr2.50 tp0.4", 3.5, 2.50, 0.4),
        ("g3.0 rr2.50 tp0.4", 3.0, 2.50, 0.4),
        ("g3.5 rr3.00 tp0.3", 3.5, 3.00, 0.3),
        ("g3.0 rr2.00 tp0.5", 3.0, 2.00, 0.5),
        ("g3.0 rr2.75 tp0.5", 3.0, 2.75, 0.5),
        ("g3.0 rr2.75 tp0.6", 3.0, 2.75, 0.6),
        ("g3.0 rr2.25 tp0.6", 3.0, 2.25, 0.6),
    ]

    all_results = []  # (config_label, stop, metrics)

    for cfg_idx, (cfg_label, gap, rr, tp1) in enumerate(configs_to_test, 1):
        print_header(f"{cfg_idx}. STOP SWEEP: {cfg_label} (stop=3-14%)")
        best_calmar = -999
        best_stop = None
        for i, stop in enumerate(stops, 1):
            config = make_config(rr=rr, gap=gap, tp1=tp1, stop=stop)
            m = run_and_metric(df_5m, df_1m, config)
            label = f"{cfg_label} stop={stop:.0f}%"
            marker = " <-- current" if stop == 10.0 else ""
            if m['calmar_ratio'] > best_calmar:
                best_calmar = m['calmar_ratio']
                best_stop = stop
            all_results.append((cfg_label, stop, m))
            print_row(i, label, m, marker)
            if stop in (10.0,) or m['calmar_ratio'] == best_calmar:
                print_year_breakdown(m)
        print(f"\n  >> Best stop for {cfg_label}: {best_stop:.0f}% (Calmar {best_calmar:.2f})")

    # ── SUMMARY: BEST STOP PER CONFIG ────────────────────────────────────
    print(f"\n{'='*110}")
    print(f"  SUMMARY — Best stop per config (by Calmar)")
    print(f"{'='*110}")
    print(f"  {'Config':<25} {'Best Stop':>10} {'R/yr':>7} {'DD':>7} {'Calmar':>8} {'vs stop=10%':>12}")
    print(f"  {'-'*75}")

    for cfg_label, _, _, _ in configs_to_test:
        cfg_results = [(s, m) for cl, s, m in all_results if cl == cfg_label]
        best = max(cfg_results, key=lambda x: x[1]['calmar_ratio'])
        at_10 = next((m for s, m in cfg_results if s == 10.0), None)

        best_stop, best_m = best
        best_ryr = best_m['total_r'] / DATA_YEARS
        delta = ""
        if at_10:
            at_10_calmar = at_10['calmar_ratio']
            diff = best_m['calmar_ratio'] - at_10_calmar
            delta = f"{diff:+.2f}" if best_stop != 10.0 else "baseline"

        print(f"  {cfg_label:<25} {best_stop:>9.0f}% {best_ryr:>7.1f} "
              f"{best_m['max_drawdown_r']:>7.1f} {best_m['calmar_ratio']:>8.2f} {delta:>12}")

    # ── OVERALL TOP 10 BY CALMAR ─────────────────────────────────────────
    print_header("OVERALL TOP 10 BY CALMAR (all configs × all stops)")
    all_sorted = sorted(all_results, key=lambda x: x[2]['calmar_ratio'], reverse=True)
    for i, (cfg_label, stop, m) in enumerate(all_sorted[:10], 1):
        label = f"{cfg_label} stop={stop:.0f}%"
        print_row(i, label, m)
        print_year_breakdown(m)

    # ── OVERALL TOP 10 BY CALMAR WHERE DD < 10R ─────────────────────────
    print_header("OVERALL TOP 10 BY CALMAR WHERE DD < 10R")
    low_dd = [(cl, s, m) for cl, s, m in all_results if abs(m['max_drawdown_r']) < 10.0]
    low_dd_sorted = sorted(low_dd, key=lambda x: x[2]['calmar_ratio'], reverse=True)
    for i, (cfg_label, stop, m) in enumerate(low_dd_sorted[:10], 1):
        label = f"{cfg_label} stop={stop:.0f}%"
        print_row(i, label, m)
        print_year_breakdown(m)

    elapsed = time.time() - t_start
    print(f"\n{'='*110}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
