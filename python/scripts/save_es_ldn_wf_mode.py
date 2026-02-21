#!/usr/bin/env python3
"""Save ES LDN WF-mode params to DB.

WF mode params from robust pipeline (2026-02-18):
  rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0, both directions, magnifier
  Phase 1: 2086 trades, 48.3% WR, PF 1.49, Sharpe 2.63, DD -19.7R
  Phase 4 hold-out (2025): Sharpe 2.27, PF 1.43, +61.2R
"""

import sys
sys.path.insert(0, "src")

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result

df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)

config = StrategyConfig(
    sessions=(LDN_SESSION,),
    instrument=ES,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    rr=3.0,
    tp1_ratio=0.5,
    name="ES LDN 2016-2026 Continuation Both WF Mode",
)
config = with_overrides(config, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)

trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m)

result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
result_id = save_backtest_result(result)
print(f"Saved: {result_id}")
