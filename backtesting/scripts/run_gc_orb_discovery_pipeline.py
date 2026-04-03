#!/usr/bin/env python3
"""GC ORB Discovery Pipeline — 9 candidates (top 3 per session) walk-forward.

Candidates from 3-session sweep (run_gc_orb_discovery.py):
  Asia-1: 30m ORB, ORB 25%, RR=2.5, TP1=0.6, both, ungated  (Cal 11.71)
  Asia-2: 15m ORB, ORB 75%, RR=2.0, TP1=0.6, short, gated   (Cal 9.95)
  Asia-3: 30m ORB, ORB 75%, RR=2.0, TP1=0.5, short, ungated  (Cal 8.68)
  NY-1:   30m ORB, ATR 15%, RR=3.0, TP1=0.4, both, gated    (Cal 5.70)
  NY-2:   30m ORB, ATR 15%, RR=3.0, TP1=0.4, short, gated   (Cal 4.13)
  NY-3:   10m ORB, ATR 12%, RR=3.0, TP1=0.6, long, gated    (Cal 2.76)
  LDN-1:  10m ORB, ATR 5%, RR=3.0, TP1=0.5, short, gated    (Cal 5.09)
  LDN-2:  10m ORB, ORB 25%, RR=3.0, TP1=0.5, short, gated   (Cal 4.90)
  LDN-3:  10m ORB, ATR 8%, RR=2.0, TP1=0.5, short, gated    (Cal 2.91)

12m IS / 3m OOS / 3m step. Calmar objective. Local RR x TP1 grid per candidate.
Sequential with 1s magnifier.
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
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability

OUTPUT_DIR = ROOT / "data" / "results" / "gc_orb_discovery_pipeline"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

LOCAL_SWEEP = {"rr": [-0.5, 0.0, +0.5], "tp1_ratio": [-0.1, 0.0, +0.1]}


# ---------------------------------------------------------------------------
# 9 candidates
# ---------------------------------------------------------------------------

CANDIDATES = {
    # Asia Top 3
    "Asia-1": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:30",
            entry_start="20:30", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-1 30m ORB25 RR2.5 TP0.6 both"), False),

    "Asia-2": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.6, atr_length=14,
        name="GC Asia-2 15m ORB75 RR2.0 TP0.6 short gated"), True),

    "Asia-3": (StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:30",
            entry_start="20:30", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.5, atr_length=14,
        name="GC Asia-3 30m ORB75 RR2.0 TP0.5 short"), False),

    # NY Top 3
    "NY-1": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:00",
            entry_start="10:00", entry_end="13:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="both", rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="GC NY-1 30m ATR15 RR3.0 TP0.4 both gated"), True),

    "NY-2": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:00",
            entry_start="10:00", entry_end="13:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="GC NY-2 30m ATR15 RR3.0 TP0.4 short gated"), True),

    "NY-3": (StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="09:40",
            entry_start="09:40", entry_end="13:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="GC NY-3 10m ATR12 RR3.0 TP0.6 long gated"), True),

    # LDN Top 3
    "LDN-1": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:10",
            entry_start="03:10", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=5.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.5, atr_length=14,
        name="GC LDN-1 10m ATR5 RR3.0 TP0.5 short gated"), True),

    "LDN-2": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:10",
            entry_start="03:10", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=3.0, tp1_ratio=0.5, atr_length=14,
        name="GC LDN-2 10m ORB25 RR3.0 TP0.5 short gated"), True),

    "LDN-3": (StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:10",
            entry_start="03:10", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=GC, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="short", rr=2.0, tp1_ratio=0.5, atr_length=14,
        name="GC LDN-3 10m ATR8 RR2.0 TP0.5 short gated"), True),
}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def build_param_ranges(config):
    base_rr, base_tp1 = config.rr, config.tp1_ratio
    rr_cands = sorted(set([max(1.5, base_rr + d) for d in LOCAL_SWEEP["rr"]]))
    tp1_cands = sorted(set([round(max(0.2, min(1.0, base_tp1 + d)), 2) for d in LOCAL_SWEEP["tp1_ratio"]]))

    rr_vals, tp1_set = [], set()
    for r in rr_cands:
        valid = [t for t in tp1_cands if t * r >= 1.0]
        if valid:
            rr_vals.append(r)
            tp1_set.update(valid)
    tp1_vals = sorted(tp1_set)
    if rr_vals:
        tp1_vals = [t for t in tp1_vals if t >= 1.0 / min(rr_vals)]
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
    print("GC ORB Discovery Pipeline — 9 Candidates (1s magnifier)")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading GC data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data(GC.data_file)
    df_1m = load_1m_for_5m(GC.data_file)
    df_1s = load_1s_for_5m(GC.data_file)
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
            n_workers=1,
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
    print("WALK-FORWARD RANKING (1s magnifier)")
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

    # Promotion verdicts
    print(f"\n  PROMOTION VERDICTS:")
    verdicts = {}
    for i, r in enumerate(ranked):
        v = "PROMOTE" if r["oos_calmar"] >= 2.0 and r["wf_efficiency"] >= 0.3 and r["oos_net_r"] > 0 and (i < 3 or r["oos_calmar"] >= 3.0) else ("CHALLENGER" if r["oos_net_r"] > 0 and r["oos_calmar"] >= 1.0 else "REJECT")
        verdicts[r["name"]] = v
        print(f"    {r['name']:>8}: {v}")

    write_json(OUTPUT_DIR / "pipeline_results.json", {"summaries": summaries, "ranking": ranked, "verdicts": verdicts})
    print(f"\nTotal: {time.time() - t0:.0f}s | Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
