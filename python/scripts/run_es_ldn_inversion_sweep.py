#!/usr/bin/env python3
"""ES London ORB Inversion — Direction sweep (both/long/short).

Tests inversion strategy across all 3 direction filters with param sweep.
BE offset=0, magnifier ON.
"""

import sys, time
sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
N_WORKERS = 8

PARAM_RANGES = {
    "rr": [1.5, 2.0, 2.5, 3.0, 3.5],
    "ldn_stop_atr_pct": [1.5, 2.0, 3.0, 5.0, 7.5],
    "ldn_min_gap_atr_pct": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
    "tp1_ratio": [0.1, 0.15, 0.2, 0.3, 0.5],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


def run_direction(df_5m, df_1m, direction):
    base = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="inversion",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction if direction != "both" else None,
        name=f"ES LDN Inversion {direction}",
    )
    configs = generate_param_grid(base, PARAM_RANGES)
    results = run_sweep(df_5m, configs, n_workers=N_WORKERS, start_date=START_DATE, df_1m=df_1m)
    rows = []
    for config, trades in results:
        m = compute_metrics(trades)
        if m["total_trades"] < 30:
            continue
        sess = config.sessions[0]
        rows.append({
            "dir": direction, "rr": config.rr, "stop": sess.stop_atr_pct,
            "gap": sess.min_gap_atr_pct, "tp1": config.tp1_ratio,
            "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
            "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
            "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
            "consec": m["max_consecutive_losses"],
        })
    return rows


def print_table(title, rows, n=20):
    sorted_rows = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
    print(f"\n{'='*125}")
    print(f"  {title} (top {n})")
    print(f"{'='*125}")
    print(f"{'#':>3} {'Dir':>6} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
    print("-" * 125)
    for i, r in enumerate(sorted_rows[:n], 1):
        print(f"{i:>3} {r['dir']:>6} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
              f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
              f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}")


def main():
    print(f"ES London ORB INVERSION — Direction Sweep")
    print(f"{'='*70}")
    print(f"Grid: {GRID_SIZE} combos x 3 directions = {GRID_SIZE * 3} total")
    print(f"BE offset: 0 | Magnifier: ON | Strategy: inversion")
    print(f"Params: {', '.join(f'{k}={v}' for k, v in PARAM_RANGES.items())}")

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s\n")

    all_rows = []
    for direction in ["both", "long", "short"]:
        print(f"Running {direction}...", flush=True)
        t0 = time.time()
        rows = run_direction(df_5m, df_1m, direction)
        print(f"  {direction}: {len(rows)} valid combos in {time.time() - t0:.0f}s")
        all_rows.extend(rows)

    # Per-direction tables
    for d in ["both", "long", "short"]:
        d_rows = [r for r in all_rows if r["dir"] == d]
        if d_rows:
            print_table(f"INVERSION {d.upper()} — BEST BY SHARPE", d_rows)

    # Combined best by Sharpe
    print_table("ALL DIRECTIONS — BEST BY SHARPE", all_rows, n=25)

    # Best by Calmar
    by_calmar = sorted(all_rows, key=lambda r: r["calmar"], reverse=True)
    print(f"\n{'='*125}")
    print(f"  ALL DIRECTIONS — BEST BY CALMAR (top 15)")
    print(f"{'='*125}")
    print(f"{'#':>3} {'Dir':>6} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
    print("-" * 125)
    for i, r in enumerate(by_calmar[:15], 1):
        print(f"{i:>3} {r['dir']:>6} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
              f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
              f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}")

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    for d in ["both", "long", "short"]:
        d_rows = [r for r in all_rows if r["dir"] == d]
        if not d_rows:
            print(f"  {d.upper()}: 0 valid combos")
            continue
        best = max(d_rows, key=lambda r: r["sharpe"])
        print(f"  {d.upper():>6}: {len(d_rows)} combos | Best Sharpe: {best['sharpe']:.2f} "
              f"(rr={best['rr']}, stop={best['stop']}, gap={best['gap']}, tp1={best['tp1']}) "
              f"| {best['trades']}t, {best['wr']:.0%} WR, PF {best['pf']:.2f}, "
              f"{best['total_r']:+.0f}R, DD {best['max_dd']:.1f}R")

    prop_ready = [r for r in all_rows if abs(r["max_dd"]) <= 10.0 and r["pf"] >= 1.0]
    print(f"\n  Prop-ready (DD<=10R, PF>=1.0): {len(prop_ready)}")
    if prop_ready:
        best_prop = max(prop_ready, key=lambda r: r["sharpe"])
        print(f"  Best prop: {best_prop['dir']} rr={best_prop['rr']}, stop={best_prop['stop']}, "
              f"gap={best_prop['gap']}, tp1={best_prop['tp1']} | "
              f"{best_prop['trades']}t, {best_prop['wr']:.0%} WR, Sharpe {best_prop['sharpe']:.2f}, "
              f"{best_prop['total_r']:+.0f}R, DD {best_prop['max_dd']:.1f}R")


if __name__ == "__main__":
    main()
