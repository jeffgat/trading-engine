#!/usr/bin/env python3
"""NQ Asia R5 Baseline — Re-run R4 Final config post same-candle SL/TP bug fix.

A major simulator bug was fixed: stops and take-profits that fire on the same
candle as entry were previously not counted. This changes trade outcomes — some
trades that were EOD/TP1_EOD will now correctly register as SL, TP1_TP2, or
TP1_BE on the entry candle.

Config: Exact R4 params (stop=3.7%, rr=1.75, gap=0.90%, tp1=0.35, ORB=10m,
        entry<=01:00, flat=00:00, ATR=5, both, no-Thu, ICF=OFF, 1s magnifier)

R4 reference: 1,593 trades, 66.8% WR, PF 1.43, Sharpe 2.53, 211.2R (21.1 R/yr),
              DD -8.9R, Calmar 23.85, 0 negative years
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD, EXIT_NO_FILL
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {3}  # no-Thursday

# R4 reference metrics for comparison
R4_REF = {
    "trades": 1593,
    "wr": 0.668,
    "pf": 1.43,
    "sharpe": 2.53,
    "net_r": 211.2,
    "r_yr": 21.1,
    "dd": -8.9,
    "calmar": 23.85,
}


def make_config():
    sess = SessionConfig(
        name="Asia",
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="01:00",
        flat_start="00:00",
        flat_end="07:00",
        stop_atr_pct=3.7,
        min_gap_atr_pct=0.90,
        max_gap_points=0.0,
        max_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=1.75,
        tp1_ratio=0.35,
        atr_length=5,
        name="NQ Asia R5 Baseline (post-bugfix)",
        notes=(
            "Re-baseline of R4 Final config after same-candle SL/TP bug fix in simulator. "
            "Config unchanged: stop=3.7% rr=1.75 gap=0.90% tp1=0.35, ORB=10m (20:00-20:10), "
            "entry<=01:00, flat=00:00, ATR=5, both, no-Thursday, ICF=OFF, 1s magnifier."
        ),
    )


def main():
    print("NQ Asia R5 Baseline — Post same-candle SL/TP bug fix")
    print("=" * 80)
    print("Config: stop=3.7% rr=1.75 gap=0.90% tp1=0.35")
    print("ORB=10m, entry<=01:00, flat=00:00, ATR=5, both, no-Thu, ICF=OFF, 1s magnifier")

    print("\nLoading data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t0:.1f}s]")

    config = make_config()
    print("\nRunning backtest...")
    t_bt = time.time()
    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCL)
    print(f"  Done [{time.time() - t_bt:.1f}s]")

    m = compute_metrics(trades)
    data_years = 10

    # ── R5 BASELINE RESULTS ─────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  R5 BASELINE (POST-BUGFIX) RESULTS")
    print(f"{'='*80}")
    print(f"  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  R/yr: {m['total_r'] / data_years:.1f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    calmar = m['calmar_ratio']
    print(f"  Calmar: {calmar:.2f}")

    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"  R by year: {yr_str}")
        neg_years = [yr for yr, r in years if r < 0 and str(yr) != "2026"]
        print(f"  Negative full years: {neg_years if neg_years else 'none'}")

    # ── EXIT TYPE BREAKDOWN ─────────────────────────────────────────
    exit_counts = {}
    for t in trades:
        exit_counts[t.exit_type] = exit_counts.get(t.exit_type, 0) + 1

    exit_names = {
        EXIT_NO_FILL: "NO_FILL",
        EXIT_SL: "SL",
        EXIT_TP1_TP2: "TP1_TP2",
        EXIT_TP1_BE: "TP1_BE",
        EXIT_TP1_EOD: "TP1_EOD",
        EXIT_EOD: "EOD",
    }

    print(f"\n  Exit type breakdown:")
    total_filled = sum(v for k, v in exit_counts.items() if k != EXIT_NO_FILL)
    for etype in [EXIT_SL, EXIT_TP1_TP2, EXIT_TP1_BE, EXIT_TP1_EOD, EXIT_EOD]:
        count = exit_counts.get(etype, 0)
        pct = count / total_filled * 100 if total_filled > 0 else 0
        print(f"    {exit_names.get(etype, str(etype)):>10}: {count:>5} ({pct:>5.1f}%)")

    # ── COMPARISON VS R4 ───────────────────────────────────────────
    print(f"\n{'='*80}")
    print(f"  COMPARISON: R4 Final vs R5 Baseline (post-bugfix)")
    print(f"{'='*80}")
    r5 = {
        "trades": m["total_trades"],
        "wr": m["win_rate"],
        "pf": m["profit_factor"],
        "sharpe": m["sharpe_ratio"],
        "net_r": m["total_r"],
        "r_yr": m["total_r"] / data_years,
        "dd": m["max_drawdown_r"],
        "calmar": calmar,
    }

    fmt = "  {:<12} {:>10} {:>10} {:>10}"
    print(fmt.format("Metric", "R4", "R5", "Delta"))
    print(f"  {'─'*45}")
    print(fmt.format("Trades", str(R4_REF["trades"]), str(r5["trades"]),
                      f"{r5['trades'] - R4_REF['trades']:+d}"))
    print(fmt.format("Win Rate", f"{R4_REF['wr']:.1%}", f"{r5['wr']:.1%}",
                      f"{(r5['wr'] - R4_REF['wr'])*100:+.1f}pp"))
    print(fmt.format("PF", f"{R4_REF['pf']:.2f}", f"{r5['pf']:.2f}",
                      f"{r5['pf'] - R4_REF['pf']:+.2f}"))
    print(fmt.format("Sharpe", f"{R4_REF['sharpe']:.2f}", f"{r5['sharpe']:.2f}",
                      f"{r5['sharpe'] - R4_REF['sharpe']:+.2f}"))
    print(fmt.format("Net R", f"{R4_REF['net_r']:.1f}", f"{r5['net_r']:.1f}",
                      f"{r5['net_r'] - R4_REF['net_r']:+.1f}"))
    print(fmt.format("R/yr", f"{R4_REF['r_yr']:.1f}", f"{r5['r_yr']:.1f}",
                      f"{r5['r_yr'] - R4_REF['r_yr']:+.1f}"))
    print(fmt.format("Max DD", f"{R4_REF['dd']:.1f}R", f"{r5['dd']:.1f}R",
                      f"{r5['dd'] - R4_REF['dd']:+.1f}"))
    print(fmt.format("Calmar", f"{R4_REF['calmar']:.2f}", f"{r5['calmar']:.2f}",
                      f"{r5['calmar'] - R4_REF['calmar']:+.2f}"))

    # ── SAVE TO DB ──────────────────────────────────────────────────
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"\n  Saved as: {result_id}")

    elapsed = time.time() - t0
    print(f"  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
