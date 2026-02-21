#!/usr/bin/env python3
"""Save NQ Asia Wide Sharpe 22:30 pipeline phase results to DB.

Saves:
  1. Full-history base config (be=0) — Phase 1 stats
  2. Hold-out config (WF mode params, 2025+) — Phase 4 stats
"""

import sys
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.export import results_to_dict, save_backtest_result

START_DATE = "2015-01-01"
HOLDOUT    = "2025-01-01"

# WF mode params from Phase 2 stability analysis
MODE_PARAMS = {
    "asia_stop_atr_pct":    6.0,
    "asia_min_gap_atr_pct": 1.75,
    "asia_max_gap_atr_pct": 3.0,
    "rr":                   1.25,
    "tp1_ratio":            0.2,
}


def no_thursday_gate(trades):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek != 3]


def base_asia():
    return replace(
        ASIA_SESSION,
        orb_start="20:00",
        orb_end="20:10",
        entry_start="20:10",
        entry_end="22:30",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.50,
        max_gap_atr_pct=5.0,
        max_gap_points=0.0,
    )


def base_config():
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(base_asia(),),
        rr=1.25,
        tp1_ratio=0.10,
        use_bar_magnifier=True,
        atr_length=14,
    )


def save(trades, name, notes):
    cfg_named = with_overrides(base_config(), name=name, notes=notes)
    result = results_to_dict(trades, cfg_named, include_equity_curve=True)
    rid = save_backtest_result(result)
    print(f"  {rid}")
    print(f"  {name}\n")
    return rid


def main():
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m bars | {len(df_1m):,} 1m bars\n")

    # ------------------------------------------------------------------
    # 1. Full-history base config (Phase 1)
    # ------------------------------------------------------------------
    print("Running full-history (Phase 1)...")
    cfg = base_config()
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
    trades = no_thursday_gate(trades)

    save(
        trades,
        "NQ ASIA 2015-2026 Wide 22:30 BE=0 Pipeline Phase1",
        (
            "Robust pipeline Phase 1. Config: stop=5.0%, gap=1.50%, maxgap=5.0%, "
            "rr=1.25, tp1=0.10, ORB 10m, ATR 14, entry≤22:30, both dirs, no-Thursday, be=0. "
            "1417 trades, 87.2% WR, 61.5R, -6.4R DD, Sharpe 1.521, PF 1.36. "
            "Negative years: 2015 (-3.0R). "
            "Phase 2 WF OOS: 603 trades, 81.8% WR, 28.6R, -9.3R DD, Sharpe 1.345, eff=0.552, stab=0.700. "
            "Phase 3: annual R FAIL (~5R/yr vs 24R threshold). "
            "Phase 4 hold-out: 87 trades, 77.0% WR, 0.9R, Sharpe 0.265. "
            "Phase 5 MC: 67.1% survival, 32.9% ruin @10R. "
            "VERDICT: NO-GO (annual R structurally too low for prop; ~6R/yr full-history)."
        ),
    )

    # ------------------------------------------------------------------
    # 2. Hold-out with WF mode params (Phase 4)
    # ------------------------------------------------------------------
    print("Running hold-out (Phase 4 mode params, 2025+)...")
    cfg_mode = base_config()
    cfg_mode = with_overrides(cfg_mode, **MODE_PARAMS)
    trades_ho = run_backtest(df, cfg_mode, start_date=HOLDOUT, df_1m=df_1m)
    trades_ho = no_thursday_gate(trades_ho)

    save(
        trades_ho,
        "NQ ASIA 2025-2026 Wide 22:30 WF-Mode Pipeline Phase4",
        (
            "Robust pipeline Phase 4 hold-out. "
            "WF mode params: stop=6.0%, gap=1.75%, maxgap=3.0%, rr=1.25, tp1=0.20, be=0. "
            "87 trades, 77.0% WR, 0.9R, -7.3R DD, Sharpe 0.265, PF 1.04. "
            "2025: +0.8R, 2026: +0.1R. FAIL (Sharpe < 0.5)."
        ),
    )


if __name__ == "__main__":
    main()
