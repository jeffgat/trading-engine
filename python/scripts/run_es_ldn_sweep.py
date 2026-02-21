#!/usr/bin/env python3
"""ES London ORB — Comprehensive parameter sweep.

Goal: Find param combos that minimize drawdown while maintaining edge.
BE offset fixed at 0. Bar magnifier ON.

Sweeps: rr, stop_atr, min_gap_atr, tp1_ratio
Ranks by: Sharpe, Prop-readiness (Sharpe with DD < 10R gate)
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics

# ── Configuration ──────────────────────────────────────────────────────────
START_DATE = "2016-01-01"
N_WORKERS = 8

PARAM_RANGES = {
    "rr": [1.5, 2.0, 2.5, 2.75, 3.0, 3.5],
    "ldn_stop_atr_pct": [1.5, 2.0, 2.5, 3.0, 4.0, 5.0],
    "ldn_min_gap_atr_pct": [0.5, 0.75, 1.0, 1.25, 1.5, 2.0],
    "tp1_ratio": [0.15, 0.2, 0.25, 0.3, 0.4, 0.5],
}

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


def main():
    print(f"ES London ORB — Parameter Sweep")
    print(f"{'='*70}")
    print(f"Grid: {GRID_SIZE} combos x {N_WORKERS} workers")
    print(f"BE offset: 0 ticks | Magnifier: ON")
    print(f"Params: {', '.join(f'{k}={v}' for k, v in PARAM_RANGES.items())}")
    print()

    # ── Load data ──────────────────────────────────────────────────────
    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded: {len(df_5m):,} 5m bars, {len(df_1m):,} 1m bars ({time.time() - t0:.1f}s)")

    # Base config
    base_config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        name="ES LDN Sweep",
    )

    # ── Generate grid and run sweep ──────────────────────────────────
    configs = generate_param_grid(base_config, PARAM_RANGES)
    print(f"\nRunning sweep ({len(configs)} configs)...")
    t0 = time.time()
    results = run_sweep(
        df_5m,
        configs,
        n_workers=N_WORKERS,
        start_date=START_DATE,
        df_1m=df_1m,
    )
    elapsed = time.time() - t0
    print(f"Sweep completed in {elapsed:.0f}s ({elapsed/60:.1f}m)")

    # ── Compute metrics for all combos ─────────────────────────────────
    rows = []
    for config, trades in results:
        m = compute_metrics(trades)
        if m["total_trades"] < 50:
            continue
        # Extract the swept params
        sess = config.sessions[0]
        rows.append({
            "rr": config.rr,
            "stop": sess.stop_atr_pct,
            "gap": sess.min_gap_atr_pct,
            "tp1": config.tp1_ratio,
            "trades": m["total_trades"],
            "wr": m["win_rate"],
            "pf": m["profit_factor"],
            "sharpe": m["sharpe_ratio"],
            "total_r": m["total_r"],
            "max_dd": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"],
            "consec": m["max_consecutive_losses"],
        })

    print(f"\nValid combos (>50 trades): {len(rows)}/{GRID_SIZE}")

    # ── Sort and display ───────────────────────────────────────────────
    def print_table(title, sorted_rows, n=20):
        print(f"\n{'='*110}")
        print(f"  {title} (top {n})")
        print(f"{'='*110}")
        print(f"{'#':>3} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
        print("-" * 110)
        for i, r in enumerate(sorted_rows[:n], 1):
            dd_flag = " *" if abs(r["max_dd"]) <= 10.0 else ""
            print(f"{i:>3} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
                  f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}{dd_flag}")

    # Best by Sharpe
    by_sharpe = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
    print_table("BEST BY SHARPE", by_sharpe)

    # Best for prop: Sharpe with DD <= 10R
    prop_ready = [r for r in rows if abs(r["max_dd"]) <= 10.0 and r["pf"] >= 1.0]
    by_prop = sorted(prop_ready, key=lambda r: r["sharpe"], reverse=True)
    print_table("BEST FOR PROP (DD <= 10R, PF >= 1.0)", by_prop)

    # Best by Net R with DD <= 10R
    by_net_r = sorted(prop_ready, key=lambda r: r["total_r"], reverse=True)
    print_table("BEST BY NET R (DD <= 10R)", by_net_r)

    # Best by Calmar
    by_calmar = sorted(rows, key=lambda r: r["calmar"], reverse=True)
    print_table("BEST BY CALMAR", by_calmar)

    # Summary stats
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"Total combos tested: {GRID_SIZE}")
    print(f"Valid combos (>50 trades): {len(rows)}")
    print(f"Prop-ready (DD<=10R, PF>=1.0): {len(prop_ready)}")
    if prop_ready:
        best = by_prop[0]
        print(f"\nBest prop candidate: rr={best['rr']}, stop={best['stop']}%, gap={best['gap']}%, tp1={best['tp1']}")
        print(f"  {best['trades']} trades, {best['wr']:.1%} WR, PF {best['pf']:.2f}, "
              f"Sharpe {best['sharpe']:.2f}, {best['total_r']:+.1f}R, DD {best['max_dd']:.1f}R")


if __name__ == "__main__":
    main()
