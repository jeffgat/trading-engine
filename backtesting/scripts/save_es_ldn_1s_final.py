#!/usr/bin/env python3
"""Save ES LDN Continuation Both final config to the main DB (post fill-bar fix).

Anchor (from robust pipeline, post fill-bar fix re-optimization):
  stop=5.2%, rr=2.0, gap=1.25%, tp1=0.40
  ORB 10m (03:00-03:10), flat 08:00-08:25, ATR 50
  Both directions, 1s bar magnifier

TODO: Update params below after Steps 2-5 converge. These are the pre-fix
pipeline values — replace with the final converged anchor before running.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

ES = get_instrument("ES")

LDN_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00", orb_end="03:10",
    entry_start="03:10", entry_end="08:25",
    flat_start="08:00", flat_end="08:25",
    stop_atr_pct=5.2,         # TODO: update after convergence
    min_gap_atr_pct=1.25,     # TODO: update after convergence
)

CONFIG = StrategyConfig(
    rr=2.0,                    # TODO: update after convergence
    tp1_ratio=0.40,            # TODO: update after convergence
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(LDN_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    name="ES LDN Continuation Both 2016-2026 [fill-bar fix]",
    notes="Post fill-bar-fix re-optimization. 1s magnifier. "
          "Params from converged sweep→fine-tune→pipeline loop. "
          "See run_es_ldn_robust_pipeline.py for pipeline verdict.",
)

START_DATE = "2016-01-01"

if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} bars [{time.time()-t0:.1f}s]")

    print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  Done in {time.time()-t0:.1f}s")

    m = compute_metrics(trades)
    filled = m["total_trades"]
    print(f"\n  Trades: {filled}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Net R: {m['total_r']:.1f}R")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  PF: {m['profit_factor']:.2f}")

    rby = m.get("r_by_year", {})
    if rby:
        print("\n  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")

    print("\nSaving to DB...")
    result = results_to_dict(trades, CONFIG, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    print("  View in dashboard -> Backtests tab")
