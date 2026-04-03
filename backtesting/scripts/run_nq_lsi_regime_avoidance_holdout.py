#!/usr/bin/env python3
"""Holdout confirmation: LSI medium-vol avoidance gate on untouched 2024-03 to 2026-02.

Single run on frozen configs + frozen gate. No retuning.
Compares baseline vs gated for both LSI Close Both and LSI FVGLimit Both.
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
    REGIME_RESEARCH_HOLDOUT_END,
    REGIME_RESEARCH_HOLDOUT_START,
    build_extended_regime_calendar,
    _filled_trades,
    _metrics_snapshot,
    _regime_lookup,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "nq_regime_research"

HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
HOLDOUT_END = REGIME_RESEARCH_HOLDOUT_END
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}


# ---------------------------------------------------------------------------
# Configs (identical to walk-forward script)
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


def make_lsi_fvg_limit_both():
    return StrategyConfig(
        sessions=(_make_lsi_session(),),
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
# Gate
# ---------------------------------------------------------------------------

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")

    def gate(trades):
        return [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS
        ]
    return gate


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def evaluate(name, trades_baseline, trades_gated):
    filled_b = _filled_trades(trades_baseline)
    filled_g = _filled_trades(trades_gated)
    metrics_b = compute_metrics(trades_baseline)
    metrics_g = compute_metrics(trades_gated)

    removed = len(filled_b) - len(filled_g)
    pct = removed / len(filled_b) * 100 if filled_b else 0

    print(f"\n  {name}")
    print(f"  {'':30s} {'Baseline':>10s} {'Gated':>10s} {'Diff':>10s}")
    print(f"  {'-' * 62}")
    print(f"  {'Trades':30s} {len(filled_b):10d} {len(filled_g):10d} {-removed:+10d} ({pct:.1f}% removed)")

    for key in ["total_r", "avg_r", "win_rate", "sharpe_ratio", "calmar_ratio", "max_drawdown_r", "profit_factor"]:
        bv = metrics_b.get(key)
        gv = metrics_g.get(key)
        if bv is not None and gv is not None:
            diff = gv - bv
            print(f"  {key:30s} {bv:10.4f} {gv:10.4f} {diff:+10.4f}")

    # Per-year breakdown
    print(f"\n  Per-year Net R:")
    r_by_year_b = metrics_b.get("r_by_year", {})
    r_by_year_g = metrics_g.get("r_by_year", {})
    all_years = sorted(set(list(r_by_year_b.keys()) + list(r_by_year_g.keys())))
    for year in all_years:
        bv = r_by_year_b.get(year, 0.0)
        gv = r_by_year_g.get(year, 0.0)
        print(f"    {year}: baseline={bv:+.2f}  gated={gv:+.2f}  diff={gv - bv:+.2f}")

    return {
        "name": name,
        "baseline_metrics": _metrics_snapshot(metrics_b),
        "gated_metrics": _metrics_snapshot(metrics_g),
        "baseline_trades": len(filled_b),
        "gated_trades": len(filled_g),
        "trades_removed": removed,
        "pct_removed": round(pct, 2),
    }


def main():
    print("NQ LSI Regime Avoidance Gate — HOLDOUT Confirmation")
    print("=" * 70)
    print(f"Holdout period: {HOLDOUT_START} to {HOLDOUT_END}")
    print(f"Avoidance buckets: {sorted(AVOID_BUCKETS)}")
    print("This is a single untouched run. No retuning.")

    t0 = time.time()
    print("\nLoading NQ data...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    try:
        df_1m = load_1m_for_5m(NQ.data_file)
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m(NQ.data_file)
    print(f"  5m={len(df_5m):,} [{time.time() - t0:.1f}s]")

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_calendar)

    # Show holdout regime distribution
    cal = regime_calendar.copy()
    cal["_date_ts"] = pd.to_datetime(cal["date"])
    holdout_cal = cal[
        (cal["_date_ts"] >= pd.Timestamp(HOLDOUT_START))
        & (cal["_date_ts"] <= pd.Timestamp(HOLDOUT_END))
        & (cal["warmup_ok"] == True)
    ]
    print(f"\n  Holdout regime distribution ({len(holdout_cal)} days):")
    for bucket, count in holdout_cal["combined_regime"].value_counts().sort_index().items():
        pct = count / len(holdout_cal) * 100
        avoided = " <-- AVOIDED" if bucket in AVOID_BUCKETS else ""
        print(f"    {bucket:25s} {count:4d} ({pct:5.1f}%){avoided}")

    results = {}

    # --- LSI Close Both ---
    print("\n[1/2] LSI Close Both...", flush=True)
    t1 = time.time()
    config_close = make_lsi_close_both()
    trades_close = run_backtest(
        df_5m, config_close,
        start_date=HOLDOUT_START, end_date=HOLDOUT_END,
        df_1m=df_1m, df_1s=df_1s,
    )
    trades_close_gated = gate_fn(trades_close)
    results["lsi_close_both"] = evaluate("LSI Close Both — HOLDOUT", trades_close, trades_close_gated)
    print(f"  [{time.time() - t1:.1f}s]")

    # --- LSI FVGLimit Both ---
    print("\n[2/2] LSI FVGLimit Both...", flush=True)
    t2 = time.time()
    config_fvg = make_lsi_fvg_limit_both()
    trades_fvg = run_backtest(
        df_5m, config_fvg,
        start_date=HOLDOUT_START, end_date=HOLDOUT_END,
        df_1m=df_1m, df_1s=df_1s,
    )
    trades_fvg_gated = gate_fn(trades_fvg)
    results["lsi_fvg_limit_both"] = evaluate("LSI FVGLimit Both — HOLDOUT", trades_fvg, trades_fvg_gated)
    print(f"  [{time.time() - t2:.1f}s]")

    # Save
    write_json(OUTPUT_DIR / "lsi_regime_avoidance_holdout.json", results)

    print(f"\nTotal time: {time.time() - t0:.1f}s")
    print(f"Output: {OUTPUT_DIR / 'lsi_regime_avoidance_holdout.json'}")


if __name__ == "__main__":
    main()
