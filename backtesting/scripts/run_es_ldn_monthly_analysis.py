#!/usr/bin/env python3
"""ES LDN — seasonal/monthly pattern analysis.

Shows R by calendar month across all years to identify seasonal DD patterns.
Uses WF mode params: rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0.
"""

import sys
sys.path.insert(0, "src")

from collections import defaultdict
import numpy as np

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]

def main():
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)

    config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        rr=3.0,
        tp1_ratio=0.5,
    )
    config = with_overrides(config, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    # Build year×month R grid
    monthly_r = defaultdict(lambda: defaultdict(float))   # [year][month_num] -> R
    monthly_t = defaultdict(lambda: defaultdict(int))     # [year][month_num] -> trade count
    monthly_wins = defaultdict(lambda: defaultdict(int))

    for t in filled:
        year = t.date[:4]
        month = int(t.date[5:7])
        monthly_r[year][month] += t.r_multiple
        monthly_t[year][month] += 1
        if t.r_multiple > 0:
            monthly_wins[year][month] += 1

    years = sorted(monthly_r.keys())

    # ── Year × Month heatmap ────────────────────────────────────────────
    print("\n" + "="*100)
    print("  R BY CALENDAR MONTH (each cell = net R for that month)")
    print("="*100)
    print(f"  {'Year':<6}", end="")
    for m in MONTHS:
        print(f" {m:>7}", end="")
    print(f" {'Total':>8}")
    print("  " + "-"*96)

    col_totals = defaultdict(float)
    col_counts = defaultdict(int)

    for year in years:
        total = sum(monthly_r[year].values())
        print(f"  {year:<6}", end="")
        for mn in range(1, 13):
            r = monthly_r[year].get(mn, None)
            if r is None:
                print(f" {'---':>7}", end="")
            else:
                marker = " " if r >= 0 else "*"
                print(f" {r:>+6.1f}{marker}", end="")
                col_totals[mn] += r
                col_counts[mn] += 1
        print(f" {total:>+7.1f}R")

    # Averages row
    print("  " + "-"*96)
    print(f"  {'Avg':<6}", end="")
    for mn in range(1, 13):
        if col_counts[mn]:
            avg = col_totals[mn] / col_counts[mn]
            print(f" {avg:>+6.1f} ", end="")
        else:
            print(f" {'---':>7}", end="")
    print()

    # ── Per-calendar-month summary ──────────────────────────────────────
    print("\n" + "="*85)
    print("  PER CALENDAR MONTH SUMMARY (aggregated across all years)")
    print("="*85)
    print(f"  {'Month':<6} {'Years':>6} {'Trades':>7} {'WR':>6} {'Net R':>8} {'Avg R':>7} "
          f"{'Neg Yrs':>8} {'Avg neg':>8} {'Best':>7} {'Worst':>7}")
    print("  " + "-"*83)

    month_rows = []
    for mn in range(1, 13):
        r_vals = [monthly_r[y][mn] for y in years if mn in monthly_r[y]]
        t_vals = [monthly_t[y][mn] for y in years if mn in monthly_t[y]]
        w_vals = [monthly_wins[y][mn] for y in years if mn in monthly_wins[y]]

        if not r_vals:
            continue

        total_r = sum(r_vals)
        total_t = sum(t_vals)
        total_w = sum(w_vals)
        wr = total_w / total_t if total_t else 0
        avg_r = total_r / len(r_vals)
        neg_years = [r for r in r_vals if r < 0]
        avg_neg = sum(neg_years) / len(neg_years) if neg_years else 0.0
        best = max(r_vals)
        worst = min(r_vals)

        month_rows.append({
            "mn": mn, "name": MONTHS[mn-1], "years": len(r_vals),
            "trades": total_t, "wr": wr, "total_r": total_r, "avg_r": avg_r,
            "neg_count": len(neg_years), "avg_neg": avg_neg,
            "best": best, "worst": worst,
        })

        print(f"  {MONTHS[mn-1]:<6} {len(r_vals):>6} {total_t:>7} {wr:>5.1%} {total_r:>+7.1f}R "
              f"{avg_r:>+6.2f}R {len(neg_years):>8} {avg_neg:>+7.1f}R {best:>+6.1f}R {worst:>+6.1f}R")

    # ── Ranked by worst avg ─────────────────────────────────────────────
    print("\n" + "="*60)
    print("  MONTHS RANKED BY AVERAGE R (worst first)")
    print("="*60)
    for i, r in enumerate(sorted(month_rows, key=lambda x: x["avg_r"]), 1):
        bar_len = max(0, min(30, int(abs(r["avg_r"]) * 2)))
        bar = ("█" * bar_len) if r["avg_r"] >= 0 else ("▓" * bar_len)
        sign = "+" if r["avg_r"] >= 0 else "-"
        print(f"  {i:>2}. {r['name']:<4} avg {r['avg_r']:>+5.2f}R  "
              f"neg {r['neg_count']}/{r['years']} yrs  worst {r['worst']:>+5.1f}R  {bar}")

    # ── Q4 / month clusters ─────────────────────────────────────────────
    quarters = {"Q1":[1,2,3],"Q2":[4,5,6],"Q3":[7,8,9],"Q4":[10,11,12]}
    print("\n" + "="*60)
    print("  QUARTERLY SUMMARY")
    print("="*60)
    print(f"  {'Qtr':<4} {'Avg R/mo':>9} {'Total R':>9} {'Neg Mos':>8}")
    print("  " + "-"*38)
    for qname, mnums in quarters.items():
        q_rows = [r for r in month_rows if r["mn"] in mnums]
        q_avg = np.mean([r["avg_r"] for r in q_rows]) if q_rows else 0
        q_tot = sum(r["total_r"] for r in q_rows)
        q_neg = sum(r["neg_count"] for r in q_rows)
        q_total_mos = sum(r["years"] for r in q_rows)
        print(f"  {qname:<4} {q_avg:>+8.2f}R {q_tot:>+8.1f}R {q_neg:>5}/{q_total_mos}")


if __name__ == "__main__":
    main()
