#!/usr/bin/env python3
"""ES London ORB Continuation (Both) — tp1_ratio sweep.

Tests tp1_ratio values to find optimal partial take-profit ratio.

Anchored to best base params from prior sweep (stop=1.5%, gap=1.5%).
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

# Sweep tp1, cross with rr and gap around best prior results
PARAM_RANGES = {
    "rr": [2.0, 2.5, 3.0, 3.5],
    "ldn_stop_atr_pct": [1.5, 2.0],
    "ldn_min_gap_atr_pct": [1.25, 1.5, 2.0],
    "tp1_ratio": [0.10, 0.15, 0.20, 0.30, 0.40, 0.50],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


def main():
    print("ES LDN Continuation — tp1_ratio Sweep")
    print("=" * 70)
    print(f"Grid: {GRID_SIZE} combos | Magnifier: ON")
    print(f"Params: {', '.join(f'{k}={v}' for k, v in PARAM_RANGES.items())}")

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s\n")

    base_config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name="ES LDN tp1 sweep",
    )

    configs = generate_param_grid(base_config, PARAM_RANGES)
    print(f"Running {len(configs)} configs...", flush=True)
    t0 = time.time()
    results = run_sweep(df_5m, configs, n_workers=N_WORKERS, start_date=START_DATE, df_1m=df_1m)
    print(f"Done in {time.time() - t0:.0f}s")

    rows = []
    for config, trades in results:
        m = compute_metrics(trades)
        if m["total_trades"] < 50:
            continue
        sess = config.sessions[0]
        rows.append({
            "rr": config.rr, "stop": sess.stop_atr_pct,
            "gap": sess.min_gap_atr_pct, "tp1": config.tp1_ratio,
            "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
            "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
            "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
            "consec": m["max_consecutive_losses"],
        })

    print(f"\nValid combos: {len(rows)}/{GRID_SIZE}")

    def print_table(title, sorted_rows, n=25):
        print(f"\n{'='*130}")
        print(f"  {title} (top {n})")
        print(f"{'='*130}")
        print(f"{'#':>3} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
        print("-" * 125)
        for i, r in enumerate(sorted_rows[:n], 1):
            print(f"{i:>3} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
                  f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}")

    by_sharpe = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
    print_table("BEST BY SHARPE", by_sharpe)

    by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)
    print_table("BEST BY CALMAR", by_calmar)

    by_dd = sorted(rows, key=lambda r: abs(r["max_dd"]))
    print_table("LOWEST DRAWDOWN (PF>=1.0)", [r for r in by_dd if r["pf"] >= 1.0])

    # Summary
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    best_sharpe = by_sharpe[0]
    best_calmar = by_calmar[0]
    print(f"Best Sharpe: rr={best_sharpe['rr']}, stop={best_sharpe['stop']}, gap={best_sharpe['gap']}, "
          f"tp1={best_sharpe['tp1']}")
    print(f"  {best_sharpe['trades']}t, {best_sharpe['wr']:.0%} WR, PF {best_sharpe['pf']:.2f}, "
          f"Sharpe {best_sharpe['sharpe']:.2f}, {best_sharpe['total_r']:+.0f}R, DD {best_sharpe['max_dd']:.1f}R")
    print(f"Best Calmar: rr={best_calmar['rr']}, stop={best_calmar['stop']}, gap={best_calmar['gap']}, "
          f"tp1={best_calmar['tp1']}")
    print(f"  {best_calmar['trades']}t, {best_calmar['wr']:.0%} WR, PF {best_calmar['pf']:.2f}, "
          f"Sharpe {best_calmar['sharpe']:.2f}, {best_calmar['total_r']:+.0f}R, DD {best_calmar['max_dd']:.1f}R")


if __name__ == "__main__":
    main()
