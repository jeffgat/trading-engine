#!/usr/bin/env python3
"""NQ Asia Wide Sharpe — variable sweep for untested dimensions.

Base config (Wide Sharpe PRE-PIPELINE):
  stop=5.0%, gap=1.50%, maxgap=5.0%, rr=1.25, tp1=0.10, ORB 10m, ATR 14

Variables tested (not covered in original dual-sweep):
  1. ORB window end:  20:05, 20:10*, 20:15, 20:20, 20:30  (* = base)
  2. Max gap tighter: 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0*
  3. Entry end time:  21:00, 21:30, 22:00, 22:30, 23:00*
  4. Direction:       both*, long, short

Total: 5 × 8 × 5 × 3 = 600 combos
"""

import sys
import time
from dataclasses import replace
from itertools import product
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"

# Base Wide Sharpe config
BASE = dict(stop=5.0, gap=1.50, rr=1.25, tp1=0.10, atr_length=14)

# Sweep dimensions
ORB_ENDS     = ["20:05", "20:10", "20:15", "20:20", "20:30"]
MAX_GAPS     = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
ENTRY_ENDS   = ["21:00", "21:30", "22:00", "22:30", "23:00"]
DIRECTIONS   = ["both", "long", "short"]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(orb_end, maxgap, entry_end, direction):
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end=orb_end,
        entry_start=orb_end,       # always matches orb_end
        entry_end=entry_end,
        stop_atr_pct=BASE["stop"],
        min_gap_atr_pct=BASE["gap"],
        max_gap_atr_pct=maxgap,
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=BASE["rr"],
        tp1_ratio=BASE["tp1"],
        use_bar_magnifier=True,
        atr_length=BASE["atr_length"],
        direction_filter=direction,
    )


def extract_row(orb_end, maxgap, entry_end, direction, metrics):
    return {
        "orb_end": orb_end,
        "maxgap": maxgap,
        "entry_end": entry_end,
        "direction": direction,
        "trades": metrics["total_trades"],
        "wr": metrics["win_rate"],
        "net_r": round(metrics["total_r"], 1),
        "max_dd_r": round(metrics["max_drawdown_r"], 1),
        "sharpe": round(metrics["sharpe_ratio"], 3),
        "pf": round(metrics["profit_factor"], 2),
        "calmar": round(metrics.get("calmar_ratio", 0), 2),
        "r_per_trade": round(metrics["avg_r"], 4),
        "long_wr": metrics.get("long_win_rate", 0),
        "short_wr": metrics.get("short_win_rate", 0),
        "r_by_year": metrics.get("r_by_year", {}),
    }


def print_header(title):
    print(f"\n{'=' * 110}")
    print(title)
    print("=" * 110)


HDR = (
    f"{'#':>3} | {'ORB':>5} | {'maxg%':>5} | {'entry_end':>9} | {'dir':>5} | "
    f"{'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'DD R':>6} | "
    f"{'Sharpe':>7} | {'PF':>5} | {'Calmar':>7} | {'R/trd':>6}"
)


def print_table(rows, label, n=10):
    print(f"\n--- {label} (Top {min(n, len(rows))}) ---")
    print(HDR)
    print("-" * len(HDR))
    for i, r in enumerate(rows[:n], 1):
        print(
            f"{i:>3} | {r['orb_end']:>5} | {r['maxgap']:>5.1f} | {r['entry_end']:>9} | {r['direction']:>5} | "
            f"{r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | {r['max_dd_r']:>6.1f} | "
            f"{r['sharpe']:>7.3f} | {r['pf']:>5.2f} | {r['calmar']:>7.2f} | {r['r_per_trade']:>6.4f}"
        )


def marginal_analysis(results, var_key, var_label, values):
    """Average metrics across each value of a variable, marginalising over the rest."""
    print(f"\n--- Marginal: {var_label} ---")
    header = f"  {'Value':>9} | {'Configs':>7} | {'Sharpe':>7} | {'Net R':>7} | {'DD R':>6} | {'WR':>6} | {'R/trd':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for val in values:
        subset = [r for r in results if r[var_key] == val]
        if not subset:
            continue
        avg_sharpe = sum(r["sharpe"] for r in subset) / len(subset)
        avg_net_r = sum(r["net_r"] for r in subset) / len(subset)
        avg_dd = sum(r["max_dd_r"] for r in subset) / len(subset)
        avg_wr = sum(r["wr"] for r in subset) / len(subset)
        avg_rpt = sum(r["r_per_trade"] for r in subset) / len(subset)
        marker = " <--" if avg_sharpe == max(
            sum(r["sharpe"] for r in [x for x in results if x[var_key] == v]) /
            len([x for x in results if x[var_key] == v])
            for v in values if [x for x in results if x[var_key] == v]
        ) else ""
        print(f"  {str(val):>9} | {len(subset):>7} | {avg_sharpe:>7.3f} | "
              f"{avg_net_r:>7.1f} | {avg_dd:>6.1f} | {avg_wr:>5.1%} | {avg_rpt:>6.4f}{marker}")


def main():
    print("NQ Asia Wide Sharpe — Variable Sweeps")
    print("=" * 60)
    print(f"Base: stop={BASE['stop']}%, gap={BASE['gap']}%, rr={BASE['rr']}, "
          f"tp1={BASE['tp1']}, ATR {BASE['atr_length']}")
    print(f"Sweep: {len(ORB_ENDS)} ORB ends × {len(MAX_GAPS)} maxgaps × "
          f"{len(ENTRY_ENDS)} entry ends × {len(DIRECTIONS)} directions = "
          f"{len(ORB_ENDS) * len(MAX_GAPS) * len(ENTRY_ENDS) * len(DIRECTIONS)} combos")

    # Load data
    print("\nLoading data...", flush=True)
    t_start = time.time()
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # Build all configs
    all_params = list(product(ORB_ENDS, MAX_GAPS, ENTRY_ENDS, DIRECTIONS))
    configs = [build_config(*p) for p in all_params]
    print(f"\nBuilt {len(configs)} configs. Running with 8 workers...", flush=True)

    # Run sweep
    t1 = time.time()
    raw = run_sweep(
        df, configs, n_workers=8, start_date=START_DATE, df_1m=df_1m,
        progress_fn=lambda done, total: print(
            f"\r  {done}/{total}", end="", flush=True
        ) if done % 50 == 0 or done == total else None,
    )
    print(f"\n  Sweep done in {time.time() - t1:.0f}s", flush=True)

    # Process results
    results = []
    for (orb_end, maxgap, entry_end, direction), (cfg, trades) in zip(all_params, raw):
        gated = no_thursday_gate(trades)
        filled = [t for t in gated if t.exit_type != EXIT_NO_FILL]
        if len(filled) < 10:
            continue
        m = compute_metrics(gated)
        results.append(extract_row(orb_end, maxgap, entry_end, direction, m))

    print(f"  Valid results: {len(results)} / {len(all_params)}")

    # Rankings
    by_sharpe = sorted(results, key=lambda r: r["sharpe"], reverse=True)
    by_net_r  = sorted(results, key=lambda r: r["net_r"], reverse=True)
    by_dd     = sorted(results, key=lambda r: r["max_dd_r"], reverse=True)
    prop      = sorted(
        [r for r in results if r["sharpe"] >= 1.5 and r["max_dd_r"] > -10],
        key=lambda r: r["net_r"], reverse=True,
    )

    print_header("RANKINGS")
    print_table(by_sharpe, "Best Sharpe")
    print_table(by_net_r,  "Best Net R")
    print_table(by_dd,     "Lowest DD")
    print_table(prop,      "Prop Viable (Sharpe≥1.5, DD>-10R)", n=10)

    # Marginal analysis — what does each variable contribute on average?
    print_header("MARGINAL ANALYSIS (avg metrics per variable value)")
    marginal_analysis(results, "orb_end",   "ORB End Time",   ORB_ENDS)
    marginal_analysis(results, "maxgap",    "Max Gap %",      MAX_GAPS)
    marginal_analysis(results, "entry_end", "Entry End Time", ENTRY_ENDS)
    marginal_analysis(results, "direction", "Direction",      DIRECTIONS)

    # Year-by-year for #1 Sharpe
    if by_sharpe:
        r = by_sharpe[0]
        print_header(f"YEAR-BY-YEAR: #1 SHARPE CONFIG")
        print(f"  orb_end={r['orb_end']}, maxgap={r['maxgap']:.1f}%, "
              f"entry_end={r['entry_end']}, direction={r['direction']}")
        print(f"  {r['trades']} trades, {r['wr']:.1%} WR, {r['net_r']:.1f}R, "
              f"{r['max_dd_r']:.1f}R DD, Sharpe {r['sharpe']:.3f}")
        for yr, yr_r in sorted(r.get("r_by_year", {}).items()):
            print(f"    {yr}: {yr_r:>7.1f}R")
        print(f"  Long WR: {r['long_wr']:.1%}, Short WR: {r['short_wr']:.1%}")

    # Save best configs
    print_header("SAVING TOP CONFIGS")

    saved = []

    def save_winner(row, name, notes):
        cfg = build_config(row["orb_end"], row["maxgap"], row["entry_end"], row["direction"])
        cfg = with_overrides(cfg, name=name, notes=notes)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)
        result = results_to_dict(trades, cfg, include_equity_curve=True)
        rid = save_backtest_result(result)
        print(f"  {rid} — {name}")
        saved.append((name, rid, row))

    if by_sharpe:
        r = by_sharpe[0]
        save_winner(
            r,
            f"NQ ASIA 2015-2026 Wide Sharpe VarSweep PRE-PIPELINE",
            f"Variable sweep winner (best Sharpe). "
            f"orb_end={r['orb_end']}, maxgap={r['maxgap']:.1f}%, "
            f"entry_end={r['entry_end']}, dir={r['direction']}. "
            f"{r['trades']} trades, {r['wr']:.1%} WR, {r['net_r']:.1f}R, "
            f"{r['max_dd_r']:.1f}R DD, Sharpe {r['sharpe']:.3f}.",
        )

    # Best prop-viable if different from top Sharpe
    if prop and (not by_sharpe or prop[0] != by_sharpe[0]):
        r = prop[0]
        save_winner(
            r,
            f"NQ ASIA 2015-2026 Wide Prop VarSweep PRE-PIPELINE",
            f"Variable sweep prop winner (Sharpe≥1.5, DD>-10R, best Net R). "
            f"orb_end={r['orb_end']}, maxgap={r['maxgap']:.1f}%, "
            f"entry_end={r['entry_end']}, dir={r['direction']}. "
            f"{r['trades']} trades, {r['wr']:.1%} WR, {r['net_r']:.1f}R, "
            f"{r['max_dd_r']:.1f}R DD, Sharpe {r['sharpe']:.3f}.",
        )

    # Final summary
    print_header("SUMMARY")
    elapsed = time.time() - t_start
    print(f"Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"Configs run: {len(all_params)}, valid: {len(results)}")
    print()
    for name, rid, r in saved:
        print(f"  {name}")
        print(f"    ID:  {rid}")
        print(f"    Key: orb={r['orb_end']}, maxgap={r['maxgap']:.1f}%, "
              f"entry_end={r['entry_end']}, dir={r['direction']}")
        print(f"    Perf: {r['trades']} trades, {r['wr']:.1%} WR, "
              f"{r['net_r']:.1f}R, {r['max_dd_r']:.1f}R DD, Sharpe {r['sharpe']:.3f}")


if __name__ == "__main__":
    main()
