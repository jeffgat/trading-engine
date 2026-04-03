#!/usr/bin/env python3
"""Compare all 9 NQ ORB candidates: ungated vs regime-gated.

Runs each candidate on pre-holdout + holdout with and without the
medium-vol avoidance gate. Prints side-by-side comparison.

Purpose: check whether regime gating helps NY and LDN (which were
already gated/ungated in the original WF run).
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_START,
    REGIME_RESEARCH_HOLDOUT_END,
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
HOLDOUT_END = REGIME_RESEARCH_HOLDOUT_END
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# ── 9 candidates (same configs as run_nq_orb_wf_9candidates_mag.py) ──

def _ny(rr, tp1, name):
    return StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="09:45",
            entry_start="09:45", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=rr, tp1_ratio=tp1, atr_length=14,
        name=name)

def _asia(rr, tp1, name):
    return StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=rr, tp1_ratio=tp1, atr_length=14,
        name=name)

def _ldn(stop_atr, stop_orb, rr, tp1, name):
    kw = {}
    if stop_atr is not None:
        kw["stop_atr_pct"] = stop_atr
    if stop_orb is not None:
        kw["stop_orb_pct"] = stop_orb
    return StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            min_gap_atr_pct=1.0, **kw),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=rr, tp1_ratio=tp1, atr_length=14,
        name=name)


CANDIDATES = {
    "NY-1":   _ny(2.5, 0.6, "NY-1 RR2.5 TP0.6"),
    "NY-2":   _ny(3.5, 0.6, "NY-2 RR3.5 TP0.6"),
    "NY-3":   _ny(3.5, 0.4, "NY-3 RR3.5 TP0.4"),
    "Asia-1": _asia(3.0, 0.6, "Asia-1 RR3.0 TP0.6"),
    "Asia-2": _asia(3.5, 0.6, "Asia-2 RR3.5 TP0.6"),
    "Asia-3": _asia(3.5, 0.5, "Asia-3 RR3.5 TP0.5"),
    "LDN-1":  _ldn(5.0, None, 2.0, 0.6, "LDN-1 ATR5 RR2.0 TP0.6"),
    "LDN-2":  _ldn(None, 100.0, 3.5, 0.6, "LDN-2 ORB100 RR3.5 TP0.6"),
    "LDN-3":  _ldn(8.0, None, 3.5, 0.4, "LDN-3 ATR8 RR3.5 TP0.4"),
}

# Original WF gate status
ORIG_GATED = {"Asia-1": True, "Asia-2": True, "Asia-3": True,
              "LDN-1": True, "LDN-2": True, "LDN-3": True,
              "NY-1": False, "NY-2": False, "NY-3": False}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL
                or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def run_and_metrics(df_5m, config, end_date, df_1m=None, df_1s=None, gate_fn=None):
    trades = run_backtest(df_5m, config, end_date=end_date, df_1m=df_1m, df_1s=df_1s)
    filled_raw = _filled_trades(trades)
    m_raw = compute_metrics(trades) if filled_raw else {}

    if gate_fn is not None:
        gated = gate_fn(trades)
        filled_g = _filled_trades(gated)
        m_gated = compute_metrics(gated) if filled_g else {}
    else:
        filled_g = filled_raw
        m_gated = m_raw

    return {
        "raw": {"n": len(filled_raw), **m_raw},
        "gated": {"n": len(filled_g), **m_gated},
    }


def fmt(m, key, decimals=2):
    v = m.get(key, 0) or 0
    if key == "win_rate":
        return f"{v:.1%}"
    return f"{v:+.{decimals}f}" if "r" in key or key == "total_r" else f"{v:.{decimals}f}"


def main():
    t0 = time.time()
    print("NQ ORB — Regime Gate Comparison (all 9 candidates)")
    print("=" * 80)
    print(f"Avoid buckets: {AVOID_BUCKETS}")
    print(f"Pre-holdout: start → {HOLDOUT_START}")
    print(f"Holdout: {HOLDOUT_START} → {HOLDOUT_END}")

    print("\nLoading data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    df_1m = load_1m_for_5m(NQ.data_file)
    df_1s = load_1s_for_5m(NQ.data_file)
    print(f"  5m: {len(df_5m):,} bars [{time.time() - t0:.1f}s]")

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    # ── Pre-holdout ──
    print(f"\n{'=' * 80}")
    print("PRE-HOLDOUT (training data)")
    print(f"{'=' * 80}")
    print(f"\n  {'Name':>8} │ {'--- Ungated ---':^30} │ {'--- Gated ---':^30} │ {'Orig':>4}")
    print(f"  {'':>8} │ {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} │ {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} │ {'Gate':>4}")
    print(f"  {'─' * 85}")

    pre_results = {}
    for name, config in CANDIDATES.items():
        t1 = time.time()
        r = run_and_metrics(df_5m, config, end_date=HOLDOUT_START,
                            df_1m=df_1m, df_1s=df_1s, gate_fn=gate_fn)
        pre_results[name] = r
        raw, gated = r["raw"], r["gated"]

        print(f"  {name:>8} │ {raw['n']:4} {raw.get('total_r',0) or 0:+7.1f} "
              f"{raw.get('calmar_ratio',0) or 0:6.2f} {raw.get('sharpe_ratio',0) or 0:5.2f} "
              f"{raw.get('max_drawdown_r',0) or 0:+6.1f} │ "
              f"{gated['n']:4} {gated.get('total_r',0) or 0:+7.1f} "
              f"{gated.get('calmar_ratio',0) or 0:6.2f} {gated.get('sharpe_ratio',0) or 0:5.2f} "
              f"{gated.get('max_drawdown_r',0) or 0:+6.1f} │ "
              f"{'Y' if ORIG_GATED[name] else 'N':>4}  [{time.time()-t1:.0f}s]")

    # ── Holdout ──
    print(f"\n{'=' * 80}")
    print("HOLDOUT")
    print(f"{'=' * 80}")
    print(f"\n  {'Name':>8} │ {'--- Ungated ---':^30} │ {'--- Gated ---':^30} │ {'Orig':>4}")
    print(f"  {'':>8} │ {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} │ {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} │ {'Gate':>4}")
    print(f"  {'─' * 85}")

    # Build holdout slice
    df_ho = df_5m.loc[HOLDOUT_START:HOLDOUT_END]
    df_1m_ho = df_1m.loc[HOLDOUT_START:HOLDOUT_END] if df_1m is not None else None
    df_1s_ho = df_1s.loc[HOLDOUT_START:HOLDOUT_END] if df_1s is not None else None

    ho_results = {}
    for name, config in CANDIDATES.items():
        t1 = time.time()
        r = run_and_metrics(df_5m, config, end_date=HOLDOUT_END,
                            df_1m=df_1m, df_1s=df_1s, gate_fn=gate_fn)
        # We want holdout-only trades, so run full and subtract pre-holdout
        # Actually, easier: run with start_date=HOLDOUT_START
        # But run_backtest doesn't have start_date filter for trades.
        # Instead run on full range and filter trades by date >= HOLDOUT_START
        trades_full = run_backtest(df_5m, config, end_date=HOLDOUT_END,
                                   df_1m=df_1m, df_1s=df_1s)
        trades_ho = [t for t in trades_full if t.date >= HOLDOUT_START]
        filled_raw = _filled_trades(trades_ho)
        m_raw = compute_metrics(trades_ho) if filled_raw else {}

        trades_gated = gate_fn(trades_ho)
        filled_g = _filled_trades(trades_gated)
        m_gated = compute_metrics(trades_gated) if filled_g else {}

        ho_results[name] = {"raw": {"n": len(filled_raw), **m_raw},
                            "gated": {"n": len(filled_g), **m_gated}}

        raw, gated = ho_results[name]["raw"], ho_results[name]["gated"]
        print(f"  {name:>8} │ {raw['n']:4} {raw.get('total_r',0) or 0:+7.1f} "
              f"{raw.get('calmar_ratio',0) or 0:6.2f} {raw.get('sharpe_ratio',0) or 0:5.2f} "
              f"{raw.get('max_drawdown_r',0) or 0:+6.1f} │ "
              f"{gated['n']:4} {gated.get('total_r',0) or 0:+7.1f} "
              f"{gated.get('calmar_ratio',0) or 0:6.2f} {gated.get('sharpe_ratio',0) or 0:5.2f} "
              f"{gated.get('max_drawdown_r',0) or 0:+6.1f} │ "
              f"{'Y' if ORIG_GATED[name] else 'N':>4}  [{time.time()-t1:.0f}s]")

    # ── Delta summary (gated minus ungated) ──
    print(f"\n{'=' * 80}")
    print("GATE IMPACT — Holdout Δ(gated − ungated)")
    print(f"{'=' * 80}")
    print(f"\n  {'Name':>8} │ {'ΔTr':>4} {'ΔNet R':>7} {'ΔCal':>7} {'ΔShp':>6} {'ΔDD':>7} │ {'Helps?':>6}")
    print(f"  {'─' * 55}")

    for name in CANDIDATES:
        raw = ho_results[name]["raw"]
        gated = ho_results[name]["gated"]
        d_tr = gated["n"] - raw["n"]
        d_r = (gated.get("total_r", 0) or 0) - (raw.get("total_r", 0) or 0)
        d_cal = (gated.get("calmar_ratio", 0) or 0) - (raw.get("calmar_ratio", 0) or 0)
        d_shp = (gated.get("sharpe_ratio", 0) or 0) - (raw.get("sharpe_ratio", 0) or 0)
        d_dd = (gated.get("max_drawdown_r", 0) or 0) - (raw.get("max_drawdown_r", 0) or 0)
        helps = "YES" if d_cal > 0 else "no"
        print(f"  {name:>8} │ {d_tr:+4} {d_r:+7.1f} {d_cal:+7.2f} {d_shp:+6.2f} {d_dd:+7.1f} │ {helps:>6}")

    print(f"\nTotal elapsed: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
