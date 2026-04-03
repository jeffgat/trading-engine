#!/usr/bin/env python3
"""CL ORB Discovery Pipeline — top candidates from 3-session sweep.

Candidates from run_cl_orb_discovery.py (pre-holdout <2025-01):
  LDN-1: 30m ORB, ATR 8%, RR=3.5, TP1=0.6, long  (Cal  9.27, 0 neg, Score 5.73)
  LDN-2: 30m ORB, ATR 8%, RR=3.0, TP1=0.6, long  (Cal  8.94, 0 neg, Score 5.69)
  LDN-3: 30m ORB, ATR 8%, RR=3.5, TP1=0.5, long  (Cal  9.10, 0 neg, Score 5.64)
  LDN-4: 10m ORB, ORB 25%, RR=3.5, TP1=0.6, long (Cal  6.61, 0 neg, Score 4.87)
  Asia-1:  5m ORB, ATR 8%, RR=3.5, TP1=0.3, long (Cal  6.42, 1 neg, Score 2.57)
  Asia-2:  5m ORB, ORB 75%, RR=2.5, TP1=0.4, long(Cal  4.33, 1 neg, Score 1.58)

NY too weak (2-3 neg years, scores <0.6). Not included.

12m IS / 3m OOS / 3m step. Calmar objective. Local RR x TP1 grid per candidate.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import CL
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability

OUTPUT_DIR = ROOT / "data" / "results" / "cl_orb_discovery_pipeline"
HOLDOUT_START = "2025-01-01"

LOCAL_SWEEP = {"rr": [-0.5, 0.0, +0.5], "tp1_ratio": [-0.1, 0.0, +0.1]}


CANDIDATES = {
    "LDN-1": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-1 30m ATR8 RR3.5 TP0.6 long"),

    "LDN-2": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-2 30m ATR8 RR3.0 TP0.6 long"),

    "LDN-3": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:30",
            entry_start="03:30", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.5, atr_length=14,
        name="CL LDN-3 30m ATR8 RR3.5 TP0.5 long"),

    "LDN-4": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:10",
            entry_start="03:10", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="CL LDN-4 10m ORB25 RR3.5 TP0.6 long"),

    "Asia-1": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:05",
            entry_start="20:05", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="CL Asia-1 5m ATR8 RR3.5 TP0.3 long"),

    "Asia-2": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:05",
            entry_start="20:05", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=75.0, min_gap_atr_pct=1.0),),
        instrument=CL, strategy="continuation", use_bar_magnifier=True,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="CL Asia-2 5m ORB75 RR2.5 TP0.4 long"),
}


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
        rr_vals, tp1_vals = [base_rr], [base_tp1]
    return {"rr": rr_vals, "tp1_ratio": tp1_vals}


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def main():
    print("CL ORB Discovery Pipeline — 6 Candidates (1m magnifier)")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("\nLoading CL data (5m + 1m)...", flush=True)
    df_5m = load_5m_data(CL.data_file)
    df_1m = load_1m_for_5m(CL.data_file)
    df_pre = df_5m.loc[:HOLDOUT_START]
    df_1m_pre = df_1m.loc[:HOLDOUT_START] if df_1m is not None else None
    print(f"  5m={len(df_pre):,} pre-holdout [{time.time() - t0:.1f}s]")

    summaries = {}
    for name, config in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  {name}: {config.name}")
        print(f"{'=' * 60}")

        param_ranges = build_param_ranges(config)
        n_configs = len(param_ranges["rr"]) * len(param_ranges["tp1_ratio"])
        print(f"    WF: {len(param_ranges['rr'])} RR x {len(param_ranges['tp1_ratio'])} TP1 = {n_configs} configs")
        print(f"    RR={param_ranges['rr']} TP1={param_ranges['tp1_ratio']}")

        t1 = time.time()
        wf = run_walkforward(
            df=df_pre, base_config=config, param_ranges=param_ranges,
            is_months=12, oos_months=3, step_months=3, objective="calmar",
            n_workers=8, start_date=df_pre.index[0].strftime("%Y-%m-%d"),
            df_1m=df_1m_pre,
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

        r_by_year = cm.get("r_by_year", {})
        if r_by_year:
            yr_str = " | ".join(f"{k}:{float(v):+.1f}" for k, v in sorted(r_by_year.items()))
            print(f"    R by year: {yr_str}")

        summaries[name] = {
            "name": name, "config": config.name,
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
            "r_by_year": {str(k): round(float(v), 2) for k, v in r_by_year.items()},
            "elapsed_s": round(elapsed, 1),
        }

    print(f"\n{'=' * 70}")
    print("WALK-FORWARD RANKING")
    print(f"{'=' * 70}")

    ranked = sorted(summaries.values(),
        key=lambda s: 0.50 * s["oos_calmar"] + 0.30 * min(s["wf_efficiency"], 2.0) + 0.20 * s["stability_score"] * 10 - (5.0 if s["oos_net_r"] < 0 else 0),
        reverse=True)

    print(f"\n  {'#':>3} {'Name':>8} {'OOS R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} {'WFE':>5} {'Stab':>5} {'Tr':>5}")
    print(f"  {'-' * 55}")
    for i, r in enumerate(ranked):
        print(f"  {i+1:3} {r['name']:>8} {r['oos_net_r']:+7.1f} {r['oos_calmar']:6.2f} "
              f"{r['oos_sharpe']:5.2f} {r['oos_max_dd']:+6.1f} {r['wf_efficiency']:5.3f} "
              f"{r['stability_score']:5.3f} {r['oos_trades']:5}")

    print(f"\n  PROMOTION VERDICTS:")
    verdicts = {}
    for i, r in enumerate(ranked):
        if r["oos_calmar"] >= 2.0 and r["wf_efficiency"] >= 0.3 and r["oos_net_r"] > 0 and i < 3:
            v = "PROMOTE"
        elif r["oos_net_r"] > 0 and r["oos_calmar"] >= 1.0:
            v = "CHALLENGER"
        else:
            v = "REJECT"
        verdicts[r["name"]] = v
        print(f"    {r['name']:>8}: {v}")

    write_json(OUTPUT_DIR / "pipeline_results.json", {"summaries": summaries, "ranking": ranked, "verdicts": verdicts})
    print(f"\nTotal: {time.time() - t0:.0f}s | Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
