#!/usr/bin/env python3
"""Save NQ Asia dual-model PRE-PIPELINE configs to DB with proper names.

Configs from dual-sweep results (ORB 10m, ATR 14, bar magnifier ON, no-Thursday):

  Aggressive: stop=3.0%, gap=1.25%, maxgap=5.0%, rr=2.5, tp1=0.30
              1,656 trades, 61.2% WR, 197R, -14.5R DD, Sharpe 1.933

  Wide (Best Sharpe): stop=5.0%, gap=1.50%, maxgap=5.0%, rr=1.25, tp1=0.10
                      1,518 trades, 87.0% WR, 117.8R, -7.9R DD, Sharpe 2.796

  Wide (Prop Viable): stop=4.5%, gap=1.25%, maxgap=5.0%, rr=1.25, tp1=0.25
                      1,656 trades, 78.3% WR, 139.1R, -9.3R DD, Sharpe 2.216
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"

CONFIGS = [
    dict(
        name="NQ ASIA 2015-2026 Aggressive PRE-PIPELINE",
        notes=(
            "Dual-sweep winner: tight stop, medium RR, unexpectedly high WR (61%) at rr=2.5. "
            "Best Sharpe from 2,000-combo aggressive grid. "
            "No prop-viable configs found (best DD just misses -10R threshold). "
            "Next step: DD reduction sweep before pipeline."
        ),
        stop=3.0, gap=1.25, maxgap=5.0, rr=2.5, tp1=0.30,
    ),
    dict(
        name="NQ ASIA 2015-2026 Wide Sharpe PRE-PIPELINE",
        notes=(
            "Dual-sweep winner: wide stop, low RR, 87% WR. "
            "Best Sharpe (2.796) from 2,500-combo wide grid. "
            "Profitable every year 2015-2026. -7.9R DD. "
            "Next step: robust pipeline."
        ),
        stop=5.0, gap=1.50, maxgap=5.0, rr=1.25, tp1=0.10,
    ),
    dict(
        name="NQ ASIA 2015-2026 Wide Prop PRE-PIPELINE",
        notes=(
            "Dual-sweep winner: wide stop, low RR, 78% WR. "
            "Best prop-viable config (Sharpe>1.5, DD>-10R) from wide grid: "
            "Sharpe 2.216, -9.3R DD, 139R net. More trades than Sharpe variant. "
            "Next step: robust pipeline."
        ),
        stop=4.5, gap=1.25, maxgap=5.0, rr=1.25, tp1=0.25,
    ),
]


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def build_config(params):
    asia = replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="23:00",
        stop_atr_pct=params["stop"],
        min_gap_atr_pct=params["gap"],
        max_gap_atr_pct=params["maxgap"],
        max_gap_points=0.0,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=params["rr"],
        tp1_ratio=params["tp1"],
        use_bar_magnifier=True,
        atr_length=14,
        name=params["name"],
        notes=params["notes"],
    )


def main():
    print("Loading NQ data...", flush=True)
    df = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars\n")

    for params in CONFIGS:
        name = params["name"]
        print(f"Running: {name}")

        cfg = build_config(params)
        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
        trades = no_thursday_gate(trades)

        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        m = compute_metrics(trades)

        result = results_to_dict(trades, cfg, include_equity_curve=True)
        rid = save_backtest_result(result)

        print(f"  ID:     {rid}")
        print(f"  Config: stop={params['stop']:.1f}%, gap={params['gap']:.2f}%, "
              f"maxgap={params['maxgap']:.1f}%, rr={params['rr']:.2f}, tp1={params['tp1']:.2f}")
        print(f"  Perf:   {m['total_trades']} trades, {m['win_rate']:.1%} WR, "
              f"{m['total_r']:.1f}R, {m['max_drawdown_r']:.1f}R DD, Sharpe {m['sharpe_ratio']:.3f}")
        print()


if __name__ == "__main__":
    main()
