#!/usr/bin/env python3
"""NQ ORB Walk-Forward — 9 candidates (top 3 per session) WITH bar magnifier.

12m IS / 3m OOS / 3m step. Calmar objective. Local RR x TP1 grid per candidate.
Sequential with pre-built maps for speed.
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
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability

OUTPUT_DIR = ROOT / "data" / "results" / "nq_orb_wf_9candidates_mag"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

LOCAL_SWEEP = {"rr": [-0.5, 0.0, +0.5], "tp1_ratio": [-0.1, 0.0, +0.1]}


# ---------------------------------------------------------------------------
# 9 candidates: top 3 per session from magnifier sweep
# ---------------------------------------------------------------------------

CANDIDATES = {
    # NY Top 3 (all ungated, 15m ORB, ATR 12% stop)
    "NY-1": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="09:45",
            entry_start="09:45", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="NY-1 15m ATR12 RR2.5 TP0.6"), False),

    "NY-2": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="09:45",
            entry_start="09:45", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="NY-2 15m ATR12 RR3.5 TP0.6"), False),

    "NY-3": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="09:45",
            entry_start="09:45", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.4, atr_length=14,
        name="NY-3 15m ATR12 RR3.5 TP0.4"), False),

    # Asia Top 3 (all gated, 15m ORB, ORB 100% stop)
    "Asia-1": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="Asia-1 15m ORB100 RR3.0 TP0.6 gated"), True),

    "Asia-2": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="Asia-2 15m ORB100 RR3.5 TP0.6 gated"), True),

    "Asia-3": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.5, atr_length=14,
        name="Asia-3 15m ORB100 RR3.5 TP0.5 gated"), True),

    # LDN Top 3 (all gated, 45m ORB)
    "LDN-1": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=5.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=2.0, tp1_ratio=0.6, atr_length=14,
        name="LDN-1 45m ATR5 RR2.0 TP0.6 gated"), True),

    "LDN-2": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="LDN-2 45m ORB100 RR3.5 TP0.6 gated"), True),

    "LDN-3": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.4, atr_length=14,
        name="LDN-3 45m ATR8 RR3.5 TP0.4 gated"), True),
}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def build_param_ranges(config):
    """Build valid RR x TP1 local grid around the candidate's anchor."""
    base_rr, base_tp1 = config.rr, config.tp1_ratio
    rr_cands = sorted(set([max(1.5, base_rr + d) for d in LOCAL_SWEEP["rr"]]))
    tp1_cands = sorted(set([round(max(0.2, min(1.0, base_tp1 + d)), 2) for d in LOCAL_SWEEP["tp1_ratio"]]))

    # Only keep combos where ALL rr x tp1 pairs satisfy tp1 * rr >= 1.0
    rr_vals, tp1_set = [], set()
    for r in rr_cands:
        valid = [t for t in tp1_cands if t * r >= 1.0]
        if valid:
            rr_vals.append(r)
            tp1_set.update(valid)
    tp1_vals = sorted(tp1_set)
    if rr_vals:
        tp1_vals = [t for t in tp1_vals if t >= 1.0 / min(rr_vals)]

    # Fallback
    if not rr_vals or not tp1_vals:
        for r in rr_cands:
            for t in tp1_cands:
                if t * r >= 1.0:
                    if r not in rr_vals: rr_vals.append(r)
                    if t not in tp1_vals: tp1_vals.append(t)
        rr_vals.sort(); tp1_vals.sort()
    if not rr_vals or not tp1_vals:
        rr_vals, tp1_vals = [base_rr], [base_tp1]

    return {"rr": rr_vals, "tp1_ratio": tp1_vals}


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def main():
    print("NQ ORB Walk-Forward — 9 Candidates WITH Bar Magnifier")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    df_1m = load_1m_for_5m(NQ.data_file)
    df_1s = load_1s_for_5m(NQ.data_file)
    df_pre = df_5m.loc[:HOLDOUT_START]
    df_1m_pre = df_1m.loc[:HOLDOUT_START] if df_1m is not None else None
    df_1s_pre = df_1s.loc[:HOLDOUT_START] if df_1s is not None else None
    print(f"  5m={len(df_pre):,} pre-holdout [{time.time() - t0:.1f}s]")

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    summaries = {}
    for name, (config, use_gate) in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  {name}: {config.name}")
        print(f"{'=' * 60}")

        param_ranges = build_param_ranges(config)
        n_configs = len(param_ranges["rr"]) * len(param_ranges["tp1_ratio"])
        print(f"    WF: {len(param_ranges['rr'])} RR x {len(param_ranges['tp1_ratio'])} TP1 = {n_configs} configs")
        print(f"    RR={param_ranges['rr']} TP1={param_ranges['tp1_ratio']}")
        print(f"    Gated: {use_gate} | Magnifier: ON")

        t1 = time.time()
        wf = run_walkforward(
            df=df_pre, base_config=config, param_ranges=param_ranges,
            is_months=12, oos_months=3, step_months=3, objective="calmar",
            n_workers=1,  # sequential — magnifier maps too large for pickle
            start_date=df_pre.index[0].strftime("%Y-%m-%d"),
            gate_fn=gate_fn if use_gate else None,
            df_1m=df_1m_pre, df_1s=df_1s_pre,
        )
        stab = analyze_parameter_stability(wf, param_ranges)
        elapsed = time.time() - t1

        cm = wf.combined_oos_metrics
        filled = len([t for t in wf.combined_oos_trades if t.exit_type != EXIT_NO_FILL])

        print(f"\n    Results ({len(wf.folds)} folds, {filled} OOS trades) [{elapsed:.0f}s]")
        print(f"    OOS: R={cm.get('total_r',0):+.1f} Cal={cm.get('calmar_ratio',0) or 0:.2f} "
              f"Shp={cm.get('sharpe_ratio',0) or 0:.2f} DD={cm.get('max_drawdown_r',0):.1f}R "
              f"WR={cm.get('win_rate',0):.1%} PF={cm.get('profit_factor',0) or 0:.2f}")
        print(f"    WFE={wf.walk_forward_efficiency:.3f} Stab={stab.overall_score:.3f} ({stab.interpretation})")

        summaries[name] = {
            "name": name, "config": config.name, "gated": use_gate,
            "n_folds": len(wf.folds), "oos_trades": filled,
            "oos_net_r": round(float(cm.get("total_r", 0)), 2),
            "oos_calmar": round(float(cm.get("calmar_ratio", 0) or 0), 4),
            "oos_sharpe": round(float(cm.get("sharpe_ratio", 0) or 0), 4),
            "oos_max_dd": round(float(cm.get("max_drawdown_r", 0)), 2),
            "oos_win_rate": round(float(cm.get("win_rate", 0)), 4),
            "oos_pf": round(float(cm.get("profit_factor", 0) or 0), 4),
            "wf_efficiency": round(wf.walk_forward_efficiency, 4),
            "stability_score": round(stab.overall_score, 4),
            "stability_interp": stab.interpretation,
            "elapsed_s": round(elapsed, 1),
        }

    # Ranking
    print(f"\n{'=' * 70}")
    print("WALK-FORWARD RANKING (bar magnifier ON)")
    print(f"{'=' * 70}")

    ranked = sorted(summaries.values(),
        key=lambda s: 0.50 * s["oos_calmar"] + 0.30 * min(s["wf_efficiency"], 2.0) + 0.20 * s["stability_score"] * 10 - (5.0 if s["oos_net_r"] < 0 else 0),
        reverse=True)

    print(f"\n  {'#':>3} {'Name':>8} {'OOS R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} {'WFE':>5} {'Stab':>5} {'G':>2} {'Tr':>5}")
    print(f"  {'-' * 60}")
    for i, r in enumerate(ranked):
        print(f"  {i+1:3} {r['name']:>8} {r['oos_net_r']:+7.1f} {r['oos_calmar']:6.2f} "
              f"{r['oos_sharpe']:5.2f} {r['oos_max_dd']:+6.1f} {r['wf_efficiency']:5.3f} "
              f"{r['stability_score']:5.3f} {'Y' if r['gated'] else 'N':>2} {r['oos_trades']:5}")

    write_json(OUTPUT_DIR / "wf_results.json", {"summaries": summaries, "ranking": ranked})
    print(f"\nTotal: {time.time() - t0:.0f}s | Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
