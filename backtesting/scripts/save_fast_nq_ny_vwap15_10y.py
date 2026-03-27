#!/usr/bin/env python3
"""Save the 10-year FAST NQ_NY 15% ATR VWAP-distance research backtest to DB."""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest, EXIT_NO_FILL
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

from run_fast_v2_nq_context_filters import build_profile_legs

START_DATE = "2016-01-01"
END_DATE = "2025-12-31"
VWAP_DISTANCE_ATR_PCT = 15.0


def main() -> None:
    print("Saving FAST NQ_NY 15% ATR VWAP-distance 10-year research backtest")
    print("=" * 72)

    leg = build_profile_legs("FAST")["NQ_NY"]
    cfg = with_overrides(
        leg.config,
        min_vwap_distance_atr_pct=VWAP_DISTANCE_ATR_PCT,
        name="FAST NQ_NY 15% ATR VWAP Distance Research (2016-2025)",
        notes=(
            "Research-only backtest. FAST NQ_NY leg with min_vwap_distance_atr_pct=15.0, "
            "using the merged FAST config basis and session VWAP-distance gate as a local "
            "trend / acceptance filter. 10-year run from 2016-01-01 through 2025-12-31. "
            "Not approved for live use."
        ),
    )

    print("\nLoading NQ data...")
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.parquet", start=START_DATE, end=END_DATE)
    df_1m = load_1m_for_5m("NQ_5m.parquet", start=START_DATE, end=END_DATE)
    maps = build_maps(df_5m, df_1m)
    signal_cache = build_signal_cache(df_5m, [cfg])
    print(f"  5m={len(df_5m):,} | 1m={len(df_1m):,} [{time.time() - t0:.1f}s]")

    print("\nRunning backtest...")
    t0 = time.time()
    trades = run_backtest(
        df_5m,
        cfg,
        start_date=START_DATE,
        end_date=END_DATE,
        df_1m=df_1m,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    if leg.excluded_dow:
        trades = apply_dow_filter(trades, set(leg.excluded_dow))
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    m = compute_metrics(filled)
    print(f"  Completed in {time.time() - t0:.1f}s")

    print(f"\n  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  Net R: {m['total_r']:.1f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.2f}")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")

    print("\nSaving to DB...")
    result = results_to_dict(filled, cfg, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)

    print(f"  Saved! Result ID: {result_id}")
    print(f"  Experiment name: {cfg.name}")


if __name__ == "__main__":
    main()
