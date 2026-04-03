#!/usr/bin/env python3
"""Expanded regime attribution: VWAP sideways + LSI strategies across regime buckets.

Tests each strategy with direction filters aligned to regime logic:
- VWAP mean-reversion: both directions (sideways specialist candidate)
- LSI close-entry: long, short, and both
- LSI fvg_limit-entry: long, short, and both

Attribution maps every trade to its 3x3 regime bucket to measure
whether any strategy/direction pair shows genuine regime separation.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_START,
    attribute_strategy_by_regime,
    build_extended_regime_calendar,
    compute_bucket_metrics,
    build_attribution_summary,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.engine.vwap_simulator import run_vwap_backtest
from orb_backtest.vwap_config import default_vwap_config, with_vwap_overrides

OUTPUT_DIR = ROOT / "data" / "results" / "nq_regime_research"


# ---------------------------------------------------------------------------
# VWAP sideways candidate (both directions — mean-reversion)
# ---------------------------------------------------------------------------

def make_vwap_sideways_config():
    """VWAP mean-reversion, both directions, based on round-1 sweep winner region."""
    base = default_vwap_config(NQ)
    return with_vwap_overrides(
        base,
        rr=2.0,
        tp1_ratio=0.5,
        direction_filter="both",
        ny_deviation_atr_pct=30.0,
        ny_stop_atr_pct=10.0,
        ny_rejection_mode="close",
        name="NQ NY VWAP Sideways Both",
    )


# ---------------------------------------------------------------------------
# LSI close-entry variants (long / short / both)
# Based on NQ NY LSI R1 final config from learnings
# ---------------------------------------------------------------------------

def _make_lsi_session():
    return SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )


def make_lsi_close_long():
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        lsi_n_left=10,
        lsi_n_right=65,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        lsi_stop_mode="absolute",
        lsi_entry_mode="close",
        excluded_days=(2, 3),  # Mon/Tue/Fri only
        name="NQ NY LSI Close Long",
    )


def make_lsi_close_short():
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        lsi_n_left=10,
        lsi_n_right=65,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        lsi_stop_mode="absolute",
        lsi_entry_mode="close",
        excluded_days=(2, 3),
        name="NQ NY LSI Close Short",
    )


def make_lsi_close_both():
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=1.5,
        tp1_ratio=0.7,
        atr_length=14,
        lsi_n_left=10,
        lsi_n_right=65,
        lsi_fvg_window_left=20,
        lsi_fvg_window_right=3,
        lsi_stop_mode="absolute",
        lsi_entry_mode="close",
        excluded_days=(2, 3),
        name="NQ NY LSI Close Both",
    )


# ---------------------------------------------------------------------------
# LSI fvg_limit-entry variants (long / short / both)
# Based on NQ NY LSI fvg_limit v2 DOW from learnings
# ---------------------------------------------------------------------------

def _make_lsi_fvg_limit_session():
    return SessionConfig(
        name="NY",
        rth_start="09:30",
        entry_start="09:35",
        entry_end="15:30",
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=5.0,
    )


def make_lsi_fvg_limit_long():
    return StrategyConfig(
        sessions=(_make_lsi_fvg_limit_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.4,
        atr_length=10,
        lsi_n_left=10,
        lsi_n_right=120,
        lsi_fvg_window_left=30,
        lsi_fvg_window_right=15,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        excluded_days=(2, 3),
        name="NQ NY LSI FVGLimit Long",
    )


def make_lsi_fvg_limit_short():
    return StrategyConfig(
        sessions=(_make_lsi_fvg_limit_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=3.0,
        tp1_ratio=0.4,
        atr_length=10,
        lsi_n_left=10,
        lsi_n_right=120,
        lsi_fvg_window_left=30,
        lsi_fvg_window_right=15,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        excluded_days=(2, 3),
        name="NQ NY LSI FVGLimit Short",
    )


def make_lsi_fvg_limit_both():
    return StrategyConfig(
        sessions=(_make_lsi_fvg_limit_session(),),
        instrument=NQ,
        strategy="lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="both",
        rr=3.0,
        tp1_ratio=0.4,
        atr_length=10,
        lsi_n_left=10,
        lsi_n_right=120,
        lsi_fvg_window_left=30,
        lsi_fvg_window_right=15,
        lsi_stop_mode="absolute",
        lsi_entry_mode="fvg_limit",
        excluded_days=(2, 3),
        name="NQ NY LSI FVGLimit Both",
    )


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------

STRATEGIES = {
    # VWAP mean-reversion (sideways candidate)
    "vwap_sideways_both": {
        "config_fn": make_vwap_sideways_config,
        "engine": "vwap",
    },
    # LSI close-entry variants
    "lsi_close_long": {
        "config_fn": make_lsi_close_long,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
    "lsi_close_short": {
        "config_fn": make_lsi_close_short,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
    "lsi_close_both": {
        "config_fn": make_lsi_close_both,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
    # LSI fvg_limit-entry variants
    "lsi_fvg_limit_long": {
        "config_fn": make_lsi_fvg_limit_long,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
    "lsi_fvg_limit_short": {
        "config_fn": make_lsi_fvg_limit_short,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
    "lsi_fvg_limit_both": {
        "config_fn": make_lsi_fvg_limit_both,
        "engine": "orb",
        "excluded_days": {2, 3},
    },
}


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def main() -> None:
    print("NQ Regime Attribution — Expanded (VWAP + LSI)")
    print("=" * 70)

    t0 = time.time()
    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    try:
        df_1m = load_1m_for_5m(NQ.data_file)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file)
    print(
        f"  5m={len(df_5m):,} | "
        f"1m={len(df_1m) if df_1m is not None else 0:,} | "
        f"1s={len(df_1s) if df_1s is not None else 0:,} "
        f"[{time.time() - t0:.1f}s]"
    )

    print("\nBuilding extended regime calendar...", flush=True)
    regime_calendar = build_extended_regime_calendar(df_5m)

    attributions: dict[str, pd.DataFrame] = {}
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    for strategy_name, info in STRATEGIES.items():
        print(f"\n  Running {strategy_name}...", flush=True)
        t1 = time.time()
        config = info["config_fn"]()

        if info.get("engine") == "vwap":
            trades = run_vwap_backtest(df_5m, config, df_1m=df_1m, df_1s=df_1s)
        else:
            trades = run_backtest(df_5m, config, df_1m=df_1m, df_1s=df_1s)

        # DOW filter is already applied via excluded_days in config for LSI
        # VWAP doesn't use excluded_days in the same way

        attr_df = attribute_strategy_by_regime(trades, regime_calendar)
        attr_df.to_csv(output_dir / f"attribution_{strategy_name}.csv", index=False)
        attributions[strategy_name] = attr_df

        n_trades = len(attr_df)
        total_r = attr_df["r_multiple"].sum() if not attr_df.empty else 0.0
        elapsed = time.time() - t1
        print(f"    Trades: {n_trades} | Total R: {total_r:+.1f} [{elapsed:.1f}s]")

        # Print per-bucket summary
        if not attr_df.empty:
            bucket_metrics = compute_bucket_metrics(attr_df)
            print(f"    {'Bucket':25s} {'N':>5s} {'AvgR':>7s} {'TotR':>8s} {'WR':>6s}")
            for _, row in bucket_metrics.iterrows():
                print(
                    f"    {row['bucket']:25s} {row['trade_count']:5d} "
                    f"{row['avg_r']:+7.3f} {row['total_r']:+8.2f} {row['win_rate']:5.1%}"
                )

    # Save combined summary
    attr_summary = build_attribution_summary(attributions)
    write_json(output_dir / "strategy_attribution_expanded.json", attr_summary)

    print(f"\nDone. Total time: {time.time() - t0:.1f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
