#!/usr/bin/env python3
"""ES London ORB Continuation (Both) — SMA20 trend gate sweep.

Applies the SMA20 trend gate post-hoc across top param combos from prior sweep.
Longs only when prev_close > SMA20, shorts only when prev_close < SMA20.
Shows before/after comparison across SMA periods (10, 20, 50).
BE offset=0, magnifier ON.
"""

import sys, time
sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.optimize.grid import generate_param_grid
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.analysis.gates import apply_sma_trend_gate
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
N_WORKERS = 8

# Top params from the original 1296 sweep (best Sharpe/Calmar combos)
PARAM_RANGES = {
    "rr": [2.5, 3.0, 3.5],
    "ldn_stop_atr_pct": [1.5, 2.0],
    "ldn_min_gap_atr_pct": [1.0, 1.25, 1.5, 2.0],
    "tp1_ratio": [0.3, 0.4, 0.5],
}

SMA_PERIODS = [10, 20, 50]

GRID_SIZE = 1
for v in PARAM_RANGES.values():
    GRID_SIZE *= len(v)


def main():
    print("ES LDN Continuation — SMA Trend Gate Sweep")
    print("=" * 70)
    print(f"Grid: {GRID_SIZE} base combos x {len(SMA_PERIODS)} SMA periods")
    print(f"SMA periods: {SMA_PERIODS} | BE offset: 0 | Magnifier: ON")

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
        name="ES LDN SMA gate",
    )

    # Run all base configs once
    configs = generate_param_grid(base_config, PARAM_RANGES)
    print(f"Running {len(configs)} base configs...", flush=True)
    t0 = time.time()
    results = run_sweep(df_5m, configs, n_workers=N_WORKERS, start_date=START_DATE, df_1m=df_1m)
    print(f"Base sweep done in {time.time() - t0:.0f}s\n")

    def get_metrics(trades):
        m = compute_metrics(trades)
        return {
            "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
            "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
            "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
            "consec": m["max_consecutive_losses"],
        }

    def print_table(title, rows, n=20):
        sorted_rows = sorted(rows, key=lambda r: r["sharpe"], reverse=True)
        print(f"\n{'='*135}")
        print(f"  {title} (top {n})")
        print(f"{'='*135}")
        print(f"{'#':>3} {'SMA':>4} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Consec':>7}")
        print("-" * 135)
        for i, r in enumerate(sorted_rows[:n], 1):
            print(f"{i:>3} {r['sma']:>4} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
                  f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f} {r['consec']:>7}")

    # Apply gate at each SMA period and collect results
    all_gated = []
    ungated_rows = []

    for config, trades in results:
        sess = config.sessions[0]
        base_row = {
            "sma": 0, "rr": config.rr, "stop": sess.stop_atr_pct,
            "gap": sess.min_gap_atr_pct, "tp1": config.tp1_ratio,
        }
        m = get_metrics(trades)
        if m["trades"] < 30:
            continue
        ungated_rows.append({**base_row, **m})

        for sma_period in SMA_PERIODS:
            gated = apply_sma_trend_gate(trades, df_5m, sma_period=sma_period)
            gm = get_metrics(gated)
            if gm["trades"] < 30:
                continue
            all_gated.append({**base_row, "sma": sma_period, **gm})

    print(f"Base combos (ungated): {len(ungated_rows)}")
    print(f"Gated combos: {len(all_gated)}")

    # Ungated baseline
    print_table("UNGATED BASELINE — BEST BY SHARPE", ungated_rows)

    # Gated results per SMA period
    for sma in SMA_PERIODS:
        sma_rows = [r for r in all_gated if r["sma"] == sma]
        print_table(f"SMA{sma} GATED — BEST BY SHARPE", sma_rows)

    # Best by calmar per SMA period
    print(f"\n{'='*135}")
    print(f"  BEST BY CALMAR PER SMA PERIOD (top 5 each)")
    print(f"{'='*135}")
    print(f"{'#':>3} {'SMA':>4} {'RR':>5} {'Stop':>5} {'Gap':>5} {'TP1':>5} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7}")
    print("-" * 115)
    for sma in SMA_PERIODS:
        sma_rows = sorted([r for r in all_gated if r["sma"] == sma],
                          key=lambda r: r["calmar"], reverse=True)
        for i, r in enumerate(sma_rows[:5], 1):
            print(f"{i:>3} {r['sma']:>4} {r['rr']:>5.2f} {r['stop']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} "
                  f"{r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} {r['sharpe']:>7.2f} "
                  f"{r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f}")
        print()

    # Before/after comparison for the single best base combo (by Sharpe)
    best_base = max(ungated_rows, key=lambda r: r["sharpe"])
    print(f"\n{'='*70}")
    print(f"  BEFORE/AFTER — Best base: rr={best_base['rr']}, stop={best_base['stop']}, gap={best_base['gap']}, tp1={best_base['tp1']}")
    print(f"{'='*70}")
    print(f"{'SMA':>6} {'Trades':>7} {'WR':>6} {'PF':>6} {'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7}")
    print("-" * 60)
    best_ungated = next(r for r in ungated_rows
                        if r["rr"] == best_base["rr"] and r["stop"] == best_base["stop"]
                        and r["gap"] == best_base["gap"] and r["tp1"] == best_base["tp1"])
    print(f"{'none':>6} {best_ungated['trades']:>7} {best_ungated['wr']:>5.1%} {best_ungated['pf']:>6.2f} "
          f"{best_ungated['sharpe']:>7.2f} {best_ungated['total_r']:>7.1f} {best_ungated['max_dd']:>7.1f} "
          f"{best_ungated['calmar']:>7.2f}")
    for sma in SMA_PERIODS:
        match = [r for r in all_gated if r["sma"] == sma and r["rr"] == best_base["rr"]
                 and r["stop"] == best_base["stop"] and r["gap"] == best_base["gap"]
                 and r["tp1"] == best_base["tp1"]]
        if match:
            r = match[0]
            print(f"{'SMA'+str(sma):>6} {r['trades']:>7} {r['wr']:>5.1%} {r['pf']:>6.2f} "
                  f"{r['sharpe']:>7.2f} {r['total_r']:>7.1f} {r['max_dd']:>7.1f} {r['calmar']:>7.2f}")


if __name__ == "__main__":
    main()
