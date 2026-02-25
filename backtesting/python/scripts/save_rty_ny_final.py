#!/usr/bin/env python3
"""Save RTY NY Continuation Longs final config to the experiment DB.

Converged config from 7 rounds of variable sweeps + fine-tune grid (6,272 combos):
  stop=3.0%, rr=5.5, gap=1.0%, tp1=0.45, ATR 14, 15m ORB (09:30-09:45),
  entry≤15:30, flat=15:50, long-only, no DOW exclusion, 1s magnifier

Full-history (2016-2026): 1,012 trades, 33.7% WR, PF 1.32, Sharpe 1.811,
  217.2R (21.7 R/yr), DD -20.0R, Calmar 10.87, 0 negative full years

Pipeline verdict: NO-GO
  Phase 1 (structural): PASS
  Phase 2 (walk-forward): FAIL — WF efficiency 0.17, 3/5 OOS folds negative
  Phase 3 (prop constraints): FAIL — avg annual R 11.9 (need ≥12)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

RTY = get_instrument("RTY")

NY_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=1.0,
    max_gap_points=50.0,
    max_gap_atr_pct=0.0,
)

CONFIG = StrategyConfig(
    rr=5.5,
    tp1_ratio=0.45,
    risk_usd=5000.0,
    atr_length=14,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(NY_SESSION,),
    instrument=RTY,
    strategy="continuation",
    direction_filter="long",
    use_bar_magnifier=True,
    impulse_close_filter=False,
    name="RTY NY Cont Longs Final (NO-GO)",
    notes=(
        "NO-GO — Pipeline P1 PASS, P2 FAIL (WF eff 0.17, 3/5 OOS folds negative), "
        "P3 FAIL (avg annual R 11.9, need ≥12). "
        "Converged from 7 rounds variable sweeps + fine-tune grid (6,272 combos, 1s magnifier). "
        "Structural metrics look excellent (Calmar 10.87, 0 neg years) but WF confirms overfitting. "
        "Config: stop=3.0% rr=5.5 gap=1.0% tp1=0.45, 15m ORB (09:30-09:45), "
        "entry≤15:30, flat=15:50, ATR=14, long only, 1s magnifier."
    ),
)

START_DATE = "2016-01-01"

if __name__ == "__main__":
    print("Loading data...")
    t0 = time.time()
    df = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = load_1s_for_5m("RTY_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} bars [{time.time()-t0:.1f}s]")

    print("Running backtest...")
    t0 = time.time()
    trades = run_backtest(df, CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(f"  Done in {time.time()-t0:.1f}s")

    m = compute_metrics(trades)
    print(f"\n  Trades: {m['total_trades']}")
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
    print("  View in dashboard → Backtests tab")
