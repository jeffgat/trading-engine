#!/usr/bin/env python3
"""ES LDN — Direction filter sweep (long-only vs short-only vs both).
Tests top param combos from prior sweep in each direction."""

import sys, time
sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

# Top combos from prior sweep to test in each direction
TOP_PARAMS = {
    "rr": [2.0, 2.5, 2.75, 3.0, 3.5],
    "ldn_stop_atr_pct": [1.5, 2.0],
    "ldn_min_gap_atr_pct": [1.0, 1.25, 1.5, 2.0],
    "tp1_ratio": [0.3, 0.4, 0.5],
}

def run_direction(df_5m, df_1m, direction):
    base = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction if direction != "both" else None,
        name=f"ES LDN {direction}",
    )
    configs = generate_param_grid(base, TOP_PARAMS)
    results = run_sweep(df_5m, configs, n_workers=8, start_date=START_DATE, df_1m=df_1m)
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

def print_table(title, rows, n=15):
    sorted_rows = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
    print(f"\n{'='*120}")
    print(f"  {title} (top {n})")
    print(f"{'='*120}")
    print(f"{'#':>3} {'Dir':>6} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
    print("-" * 120)
    for i, r in enumerate(sorted_rows[:n], 1):
        print(f"{i:>3} {r['dir']:>6} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
              f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
              f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}")

def main():
    print("ES LDN — Direction Filter Sweep")
    print("=" * 70)

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s")

    grid_size = 1
    for v in TOP_PARAMS.values():
        grid_size *= len(v)
    print(f"Grid: {grid_size} combos x 3 directions = {grid_size * 3} total")

    all_rows = []
    for direction in ["both", "long", "short"]:
        print(f"\nRunning {direction}...", flush=True)
        t0 = time.time()
        rows = run_direction(df_5m, df_1m, direction)
        print(f"  {direction}: {len(rows)} valid combos in {time.time() - t0:.0f}s")
        all_rows.extend(rows)

    # Print by direction
    for d in ["both", "long", "short"]:
        d_rows = [r for r in all_rows if r["dir"] == d]
        print_table(f"DIRECTION: {d.upper()}", d_rows)

    # Combined best
    print_table("ALL DIRECTIONS — BEST BY SHARPE", all_rows, n=20)

    # Best by calmar
    by_calmar = sorted(all_rows, key=lambda r: r["calmar"], reverse=True)
    print(f"\n{'='*120}")
    print(f"  ALL DIRECTIONS — BEST BY CALMAR (top 10)")
    print(f"{'='*120}")
    print(f"{'#':>3} {'Dir':>6} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7}")
    print("-" * 110)
    for i, r in enumerate(by_calmar[:10], 1):
        print(f"{i:>3} {r['dir']:>6} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
              f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
              f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f}")

if __name__ == "__main__":
    main()
