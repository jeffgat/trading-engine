#!/usr/bin/env python3
"""NQ Asia v2 — Fine stop ATR% sweep (Round 10 equivalent).

Anchor (v2 CONDITIONAL base):
  ORB 10m, ATR 5, entry 20:10-23:00, gap=1.25%, maxgap=11.0%, tp1=0.20, no-Thursday

Sweep:
  stop_atr_pct: 3.5% to 6.5% in 0.1% steps  (31 values)
  rr:           [1.5, 1.75, 2.0, 2.5, 3.0]

Total: 31 × 5 = 155 combos

Objective: Calmar (R/yr ÷ Max DD).
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]

STOP_VALUES = [round(3.5 + i * 0.1, 1) for i in range(31)]  # 3.5 to 6.5
RR_VALUES   = [1.5, 1.75, 2.0, 2.5, 3.0]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(stop, rr):
    asia = replace(
        ASIA_SESSION,
        orb_end="20:10",
        entry_start="20:10",
        entry_end="23:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=1.25,
        max_gap_atr_pct=11.0,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=rr,
        tp1_ratio=0.20,
        use_bar_magnifier=True,
        atr_length=5,
    )


def main():
    print("NQ Asia v2 — Fine Stop Sweep (Round 10 equivalent)")
    print("Anchor: gap=1.25%, maxgap=11%, tp1=0.20, ATR 5, ORB 10m, entry≤23:00, no-Thu")
    print(f"Grid: {len(STOP_VALUES)} stops × {len(RR_VALUES)} rr = {len(STOP_VALUES)*len(RR_VALUES)} combos")
    print("Objective: Calmar")
    print()

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]\n")

    results = []
    total = len(STOP_VALUES) * len(RR_VALUES)
    done  = 0

    for stop in STOP_VALUES:
        for rr in RR_VALUES:
            cfg    = build_config(stop, rr)
            trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
            trades = no_thursday_gate(trades)
            filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
            done  += 1

            if len(filled) < 10:
                continue

            m = compute_metrics(trades)
            r_by_year   = m.get("r_by_year", {})
            full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
            avg_annual  = sum(full_year_r) / len(full_year_r) if full_year_r else 0
            neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                           if r < 0 and yr in FULL_YEARS}

            results.append({
                "stop":        stop,
                "rr":          rr,
                "trades":      m["total_trades"],
                "wr":          m["win_rate"],
                "net_r":       round(m["total_r"], 1),
                "avg_annual":  round(avg_annual, 1),
                "max_dd_r":    round(m["max_drawdown_r"], 1),
                "sharpe":      round(m["sharpe_ratio"], 3),
                "calmar":      round(m.get("calmar_ratio", 0), 2),
                "r_per_trade": round(m["avg_r"], 4),
                "neg_full":    len(neg_full),
                "neg_detail":  neg_full,
                "r_by_year":   r_by_year,
            })
            print(f"\r  {done}/{total}", end="", flush=True)

    print(f"\n  Done in {time.time()-t0:.1f}s\n")

    HDR = (f"{'stop%':>5} | {'rr':>4} | {'Trades':>6} | {'WR':>6} | "
           f"{'Net R':>7} | {'Avg/Yr':>7} | {'DD R':>6} | "
           f"{'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>7} | NegFYr")

    def marker(r):
        if r["stop"] == 5.8 and r["rr"] == 1.5:
            return "  <-- v2"
        return ""

    def print_table(rows, label, n=20):
        print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
        print(HDR)
        print("-" * len(HDR))
        for r in rows[:n]:
            neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
            print(f"{r['stop']:>5.1f} | {r['rr']:>4.2f} | {r['trades']:>6} | {r['wr']:>5.1%} | "
                  f"{r['net_r']:>7.1f} | {r['avg_annual']:>7.1f} | {r['max_dd_r']:>6.1f} | "
                  f"{r['sharpe']:>7.3f} | {r['calmar']:>7.2f} | {r['r_per_trade']:>7.4f} | "
                  f"{neg}{marker(r)}")

    by_calmar = sorted(results, key=lambda r: r["calmar"], reverse=True)
    by_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    clean     = sorted([r for r in results if r["neg_full"] == 0],
                       key=lambda r: r["calmar"], reverse=True)

    print_table(by_calmar, "Best Calmar")
    print_table(by_sharpe, "Best Sharpe")
    print_table(clean,     "0 Negative Full Years, by Calmar")

    # ----------------------------------------------------------------
    # Calmar heatmap: stop (rows) × rr (cols)
    # ----------------------------------------------------------------
    print(f"\n--- Calmar heatmap (stop × rr) ---")
    print(f"{'rr→':>7}", end="")
    for rr in RR_VALUES:
        print(f"  {rr:>5.2f}", end="")
    print()
    print("-" * (8 + 8 * len(RR_VALUES)))
    for stop in STOP_VALUES:
        v2_row = stop == 5.8
        print(f"s={stop:<5.1f}", end="")
        for rr in RR_VALUES:
            row = next((r for r in results if r["stop"] == stop and r["rr"] == rr), None)
            val = f"{row['calmar']:>7.2f}" if row else "    n/a"
            print(f" {val}", end="")
        suffix = "  <-- v2" if v2_row else ""
        print(suffix)

    # ----------------------------------------------------------------
    # Calmar by stop (marginal, best rr per stop)
    # ----------------------------------------------------------------
    print(f"\n--- Best Calmar per stop (across all rr) ---")
    print(f"{'stop%':>5} | {'best rr':>7} | {'Calmar':>7} | {'Avg/Yr':>7} | "
          f"{'DD R':>6} | {'Sharpe':>7} | NegFYr")
    print("-" * 65)
    for stop in STOP_VALUES:
        subset = [r for r in results if r["stop"] == stop]
        if not subset:
            continue
        best = max(subset, key=lambda r: r["calmar"])
        neg = str(best["neg_detail"]) if best["neg_detail"] else "-"
        v2_mark = "  <-- v2" if stop == 5.8 else ""
        print(f"{stop:>5.1f} | {best['rr']:>7.2f} | {best['calmar']:>7.2f} | "
              f"{best['avg_annual']:>7.1f} | {best['max_dd_r']:>6.1f} | "
              f"{best['sharpe']:>7.3f} | {neg}{v2_mark}")

    # ----------------------------------------------------------------
    # Year-by-year for top 3 by Calmar
    # ----------------------------------------------------------------
    print(f"\n--- Year-by-year: Top 3 by Calmar ---")
    for i, r in enumerate(by_calmar[:3], 1):
        print(f"\n  #{i}: stop={r['stop']}%, rr={r['rr']} — "
              f"Calmar={r['calmar']}, Avg/Yr={r['avg_annual']}, "
              f"DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        for yr, yr_r in sorted(r["r_by_year"].items()):
            flag = " *" if yr_r < 0 and yr in FULL_YEARS else ""
            print(f"    {yr}: {yr_r:>7.1f}R{flag}")

    print(f"\nTotal runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
