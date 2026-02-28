#!/usr/bin/env python3
"""Save ES LDN Continuation Both — R12 converged anchor to DB.

R12 anchor (NO-GO 2/5 in pipeline, saving for reference):
  stop=6.0%, rr=4.0, gap=1.0%, tp1=0.75, ATR=14, max_gap=20%ATR
  ORB 10m, entry 08:25, flat 08:00, both, DOW excl Mon, ICF off, 1s mag
  In-sample: Calmar 10.18, 1 neg year (2016:-0.8R), 206.7R net, -20.3R DD
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON

START_DATE = "2016-01-01"
DOW_EXCLUDED = {MON}


def make_config():
    sess = SessionConfig(
        name="LDN",
        orb_start="03:00",
        orb_end="03:10",
        entry_start="03:10",
        entry_end="08:25",
        flat_start="08:00",
        flat_end="08:25",
        stop_atr_pct=6.0,
        min_gap_atr_pct=1.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=4.0,
        tp1_ratio=0.75,
        atr_length=14,
        name="ES LDN Continuation Both 2016-2026 Full Opt R12",
        notes=(
            "Full optimization R12: 12 variable sweep rounds, 2 grid sweeps. "
            "Converged Calmar 10.18, 1 neg year (2016:-0.8R) in-sample. "
            "Pipeline NO-GO (2/5): WFE 0.591 PASS, MC ruin 92%, holdout Sharpe 0.21. "
            "DOW excl Mon applied post-backtest. 1s magnifier. "
            "Changes from R11: tp1 0.5→0.75, flat 08:20→08:00."
        ),
    )


def main():
    print("Loading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data(ES.data_file)
    df_1m = load_1m_for_5m(ES.data_file)
    df_1s = load_1s_for_5m(ES.data_file)
    print(f"  Loaded in {time.time() - t0:.1f}s", flush=True)

    config = make_config()

    print("Running backtest...", flush=True)
    t0 = time.time()
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, DOW_EXCLUDED)
    print(f"  Backtest in {time.time() - t0:.1f}s", flush=True)

    m = compute_metrics(trades)
    print(f"\n  Trades:    {m['total_trades']}")
    print(f"  Win Rate:  {m['win_rate']:.1%}")
    print(f"  PF:        {m['profit_factor']:.2f}")
    print(f"  Net R:     {m['total_r']:.1f}R")
    print(f"  Sharpe:    {m['sharpe_ratio']:.3f}")
    print(f"  Max DD:    {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar:    {m['calmar_ratio']:.2f}")

    rby = m.get("r_by_year", {})
    if rby:
        parts = [f"{y}:{r:+.0f}" for y, r in sorted(rby.items())]
        print(f"  R/yr:      {', '.join(parts)}")

    print("\nSaving to DB...", flush=True)
    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved as: {result_id}")


if __name__ == "__main__":
    main()
