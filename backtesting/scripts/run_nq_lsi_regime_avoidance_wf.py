#!/usr/bin/env python3
"""Walk-forward test: LSI with medium-vol regime avoidance gate.

Tests whether filtering out bull_medium_vol + sideways_medium_vol days
improves LSI performance in walk-forward (12m IS / 3m OOS / 3m step).

Compares:
1. LSI Close Both — no gate (baseline)
2. LSI Close Both — medium-vol avoidance gate
3. LSI FVGLimit Both — no gate (baseline)
4. LSI FVGLimit Both — medium-vol avoidance gate
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
    build_extended_regime_calendar,
    make_regime_gate,
    _filled_trades,
    _metrics_snapshot,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m, load_1s_for_5m, load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.optimize.walkforward import generate_windows

OUTPUT_DIR = ROOT / "data" / "results" / "nq_regime_research"

HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START

# Medium-vol buckets to avoid
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}


# ---------------------------------------------------------------------------
# Configs
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
# Avoidance gate
# ---------------------------------------------------------------------------

def make_medium_vol_avoidance_gate(regime_calendar, regime_col="combined_regime"):
    """Gate that REMOVES trades on medium-vol days (bull_medium_vol, sideways_medium_vol)."""
    from orb_backtest.analysis.regime_research import _regime_lookup
    lookup = _regime_lookup(regime_calendar, regime_col)

    def gate(trades):
        return [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS
        ]
    return gate


# ---------------------------------------------------------------------------
# Walk-forward runner (manual fold loop — no param sweep, just gate comparison)
# ---------------------------------------------------------------------------

def run_gated_walkforward(
    df_5m, config, regime_calendar, gate_fn,
    is_months=12, oos_months=3, step_months=3,
    df_1m=None, df_1s=None,
):
    """Run walk-forward with a fixed config and optional gate.

    No parameter optimization — just replays the frozen config on each OOS fold
    and applies the gate. Returns combined OOS metrics.
    """
    data_start = df_5m.index[0].strftime("%Y-%m-%d")
    windows = generate_windows(data_start, HOLDOUT_START, is_months, oos_months, step_months)

    all_oos_trades = []
    fold_results = []

    for fold_idx, window in enumerate(windows):
        # Run backtest on OOS window
        warmup_start = (
            pd.Timestamp(window.oos_start) - pd.Timedelta(days=30)
        ).strftime("%Y-%m-%d")

        trades = run_backtest(
            df_5m, config,
            start_date=window.oos_start,
            end_date=window.oos_end,
            df_1m=df_1m, df_1s=df_1s,
        )

        # Apply gate
        if gate_fn is not None:
            gated = gate_fn(trades)
        else:
            gated = trades

        filled = _filled_trades(gated)
        metrics = compute_metrics(gated)

        fold_results.append({
            "fold_idx": fold_idx,
            "oos_start": window.oos_start,
            "oos_end": window.oos_end,
            "trades_before_gate": len(_filled_trades(trades)),
            "trades_after_gate": len(filled),
            "net_r": round(float(metrics.get("total_r", 0)), 4),
            "avg_r": round(float(metrics.get("avg_r", 0)), 4),
            "win_rate": round(float(metrics.get("win_rate", 0)), 4),
        })

        all_oos_trades.extend(gated)

    combined_metrics = compute_metrics(all_oos_trades)
    combined_filled = _filled_trades(all_oos_trades)

    return {
        "folds": fold_results,
        "n_folds": len(fold_results),
        "combined_oos_trades": len(combined_filled),
        "combined_oos_metrics": _metrics_snapshot(combined_metrics),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def print_comparison(name, baseline, gated):
    bm = baseline["combined_oos_metrics"]
    gm = gated["combined_oos_metrics"]

    b_trades = baseline["combined_oos_trades"]
    g_trades = gated["combined_oos_trades"]
    removed = b_trades - g_trades
    pct_removed = removed / b_trades * 100 if b_trades > 0 else 0

    print(f"\n  {name}")
    print(f"  {'':30s} {'Baseline':>10s} {'Gated':>10s} {'Diff':>10s}")
    print(f"  {'-'*62}")
    print(f"  {'Trades':30s} {b_trades:10d} {g_trades:10d} {-removed:+10d} ({pct_removed:.1f}% removed)")

    for key in ["total_r", "avg_r", "win_rate", "sharpe_ratio", "calmar_ratio", "max_drawdown_r", "profit_factor"]:
        bv = bm.get(key)
        gv = gm.get(key)
        if bv is not None and gv is not None:
            diff = gv - bv
            print(f"  {key:30s} {bv:10.4f} {gv:10.4f} {diff:+10.4f}")

    # Per-fold comparison
    print(f"\n  Per-fold OOS Net R:")
    print(f"  {'Fold':>6s} {'Period':>25s} {'Base':>8s} {'Gated':>8s} {'Diff':>8s} {'Removed':>8s}")
    for bf, gf in zip(baseline["folds"], gated["folds"]):
        diff = gf["net_r"] - bf["net_r"]
        removed = bf["trades_before_gate"] - gf["trades_after_gate"]
        print(
            f"  {bf['fold_idx']:6d} {bf['oos_start']:>12s}–{bf['oos_end']:>10s} "
            f"{bf['net_r']:+8.2f} {gf['net_r']:+8.2f} {diff:+8.2f} {removed:8d}"
        )


def main():
    print("NQ LSI Regime Avoidance Gate — Walk-Forward Test")
    print("=" * 70)
    print(f"Avoidance buckets: {sorted(AVOID_BUCKETS)}")
    print(f"WF: 12m IS / 3m OOS / 3m step, pre-holdout only (<{HOLDOUT_START})")

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
    gate_fn = make_medium_vol_avoidance_gate(regime_calendar)

    results = {}

    # --- LSI Close Both ---
    print("\n[1/4] LSI Close Both — baseline...", flush=True)
    t1 = time.time()
    config_close = make_lsi_close_both()
    baseline_close = run_gated_walkforward(
        df_5m, config_close, regime_calendar, gate_fn=None,
        df_1m=df_1m, df_1s=df_1s,
    )
    print(f"  Done [{time.time() - t1:.1f}s]")

    print("[2/4] LSI Close Both — medium-vol avoidance gate...", flush=True)
    t2 = time.time()
    gated_close = run_gated_walkforward(
        df_5m, config_close, regime_calendar, gate_fn=gate_fn,
        df_1m=df_1m, df_1s=df_1s,
    )
    print(f"  Done [{time.time() - t2:.1f}s]")

    print_comparison("LSI Close Both", baseline_close, gated_close)
    results["lsi_close_both_baseline"] = baseline_close
    results["lsi_close_both_gated"] = gated_close

    # --- LSI FVGLimit Both ---
    print("\n[3/4] LSI FVGLimit Both — baseline...", flush=True)
    t3 = time.time()
    config_fvg = make_lsi_fvg_limit_both()
    baseline_fvg = run_gated_walkforward(
        df_5m, config_fvg, regime_calendar, gate_fn=None,
        df_1m=df_1m, df_1s=df_1s,
    )
    print(f"  Done [{time.time() - t3:.1f}s]")

    print("[4/4] LSI FVGLimit Both — medium-vol avoidance gate...", flush=True)
    t4 = time.time()
    gated_fvg = run_gated_walkforward(
        df_5m, config_fvg, regime_calendar, gate_fn=gate_fn,
        df_1m=df_1m, df_1s=df_1s,
    )
    print(f"  Done [{time.time() - t4:.1f}s]")

    print_comparison("LSI FVGLimit Both", baseline_fvg, gated_fvg)
    results["lsi_fvg_limit_both_baseline"] = baseline_fvg
    results["lsi_fvg_limit_both_gated"] = gated_fvg

    # Save
    write_json(OUTPUT_DIR / "lsi_regime_avoidance_wf.json", results)

    print(f"\nTotal time: {time.time() - t0:.1f}s")
    print(f"Output: {OUTPUT_DIR / 'lsi_regime_avoidance_wf.json'}")


if __name__ == "__main__":
    main()
