#!/usr/bin/env python3
"""ES ORB Discovery Pipeline — Phases 3-5 for 8 candidates across 3 sessions.

Candidates from sweep:
  NY-A:   45m ORB, ATR 8% stop, RR=3.5, TP1=0.3, both, gated
  NY-B:   60m ORB, ATR 5% stop, RR=3.5, TP1=0.3, long, ungated
  NY-C:   60m ORB, ATR 8% stop, RR=2.5, TP1=0.5, long, gated
  Asia-A: 60m ORB, ORB 100% stop, RR=2.5, TP1=0.4, long, gated
  Asia-B: 15m ORB, ATR 12% stop, RR=3.0, TP1=0.6, long, gated
  Asia-C: 60m ORB, ATR 15% stop, RR=3.0, TP1=0.4, long, gated
  LDN-A:  45m ORB, ATR 15% stop, RR=3.5, TP1=0.3, short, gated
  LDN-B:  45m ORB, ATR 12% stop, RR=3.5, TP1=0.4, short, gated
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
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "es_orb_discovery_pipeline"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
N_WORKERS = 4

LOCAL_SWEEP = {"rr": [-0.5, 0.0, +0.5], "tp1_ratio": [-0.1, 0.0, +0.1]}


def _ny_a():
    return StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:15",
            entry_start="10:15", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="both", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES NY-A 45m ATR8 RR3.5 TP0.3 both gated")

def _ny_b():
    return StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:30",
            entry_start="10:30", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=5.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES NY-B 60m ATR5 RR3.5 TP0.3 long")

def _ny_c():
    return StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:30",
            entry_start="10:30", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.5, atr_length=14,
        name="ES NY-C 60m ATR8 RR2.5 TP0.5 long gated")

def _asia_a():
    return StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="21:00",
            entry_start="21:00", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="ES Asia-A 60m ORB100 RR2.5 TP0.4 long gated")

def _asia_b():
    return StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="ES Asia-B 15m ATR12 RR3.0 TP0.6 long gated")

def _asia_c():
    return StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="21:00",
            entry_start="21:00", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="ES Asia-C 60m ATR15 RR3.0 TP0.4 long gated")

def _ldn_a():
    return StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="short", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES LDN-A 45m ATR15 RR3.5 TP0.3 short gated")

def _ldn_b():
    return StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="short", rr=3.5, tp1_ratio=0.4, atr_length=14,
        name="ES LDN-B 45m ATR12 RR3.5 TP0.4 short gated")


CANDIDATES = {
    "NY-A": {"config_fn": _ny_a, "gated": True},
    "NY-B": {"config_fn": _ny_b, "gated": False},
    "NY-C": {"config_fn": _ny_c, "gated": True},
    "Asia-A": {"config_fn": _asia_a, "gated": True},
    "Asia-B": {"config_fn": _asia_b, "gated": True},
    "Asia-C": {"config_fn": _asia_c, "gated": True},
    "LDN-A": {"config_fn": _ldn_a, "gated": True},
    "LDN-B": {"config_fn": _ldn_b, "gated": True},
}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def run_candidate_wf(name, config, df_5m, gate_fn, use_gate):
    base_rr, base_tp1 = config.rr, config.tp1_ratio
    rr_cands = sorted(set([max(1.5, base_rr + d) for d in LOCAL_SWEEP["rr"]]))
    tp1_cands = sorted(set([round(max(0.2, min(1.0, base_tp1 + d)), 2) for d in LOCAL_SWEEP["tp1_ratio"]]))

    rr_values, tp1_set = [], set()
    for r in rr_cands:
        valid = [t for t in tp1_cands if t * r >= 1.0]
        if valid:
            rr_values.append(r)
            tp1_set.update(valid)
    tp1_values = sorted(tp1_set)
    if rr_values:
        tp1_values = [t for t in tp1_values if t >= 1.0 / min(rr_values)]
    if not rr_values or not tp1_values:
        for r in rr_cands:
            for t in tp1_cands:
                if t * r >= 1.0:
                    if r not in rr_values: rr_values.append(r)
                    if t not in tp1_values: tp1_values.append(t)
        rr_values.sort(); tp1_values.sort()
    if not rr_values or not tp1_values:
        rr_values, tp1_values = [base_rr], [base_tp1]

    print(f"    WF: {len(rr_values)} RR x {len(tp1_values)} TP1 | RR={rr_values} TP1={tp1_values}")
    wf = run_walkforward(df=df_5m, base_config=config,
        param_ranges={"rr": rr_values, "tp1_ratio": tp1_values},
        is_months=12, oos_months=3, step_months=3, objective="calmar",
        n_workers=N_WORKERS, start_date=df_5m.index[0].strftime("%Y-%m-%d"),
        gate_fn=gate_fn if use_gate else None)
    stab = analyze_parameter_stability(wf, {"rr": rr_values, "tp1_ratio": tp1_values})
    return wf, stab


def summarize(name, wf, stab):
    cm = wf.combined_oos_metrics
    filled = len([t for t in wf.combined_oos_trades if t.exit_type != EXIT_NO_FILL])
    print(f"\n    {name}: {len(wf.folds)} folds, {filled} OOS trades")
    print(f"    OOS: R={cm.get('total_r',0):+.1f} Cal={cm.get('calmar_ratio',0) or 0:.2f} "
          f"Shp={cm.get('sharpe_ratio',0) or 0:.2f} DD={cm.get('max_drawdown_r',0):.1f}R "
          f"WR={cm.get('win_rate',0):.1%}")
    print(f"    WFE={wf.walk_forward_efficiency:.3f} Stab={stab.overall_score:.3f} ({stab.interpretation})")
    return {
        "name": name, "n_folds": len(wf.folds), "oos_trades": filled,
        "oos_net_r": round(float(cm.get("total_r", 0)), 2),
        "oos_calmar": round(float(cm.get("calmar_ratio", 0) or 0), 4),
        "oos_sharpe": round(float(cm.get("sharpe_ratio", 0) or 0), 4),
        "oos_max_dd": round(float(cm.get("max_drawdown_r", 0)), 2),
        "oos_win_rate": round(float(cm.get("win_rate", 0)), 4),
        "wf_efficiency": round(wf.walk_forward_efficiency, 4),
        "stability_score": round(stab.overall_score, 4),
        "stability_interp": stab.interpretation,
    }


def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def main():
    print("ES ORB Discovery Pipeline — Phases 3-5")
    print("=" * 70)
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    df_5m = load_5m_data(ES.data_file)
    df_pre = df_5m.loc[:HOLDOUT_START]
    print(f"  ES 5m: {len(df_pre):,} pre-holdout bars")

    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    summaries = {}
    for name, info in CANDIDATES.items():
        print(f"\n{'='*60}\n  {name}\n{'='*60}")
        config = info["config_fn"]()
        t1 = time.time()
        wf, stab = run_candidate_wf(name, config, df_pre, gate_fn, info["gated"])
        s = summarize(name, wf, stab)
        s["gated"] = info["gated"]
        summaries[name] = s
        print(f"    [{time.time()-t1:.0f}s]")

    # Rank
    print(f"\n{'='*70}\nPROMOTION RANKING\n{'='*70}")
    ranked = []
    for name, s in summaries.items():
        score = 0.50*s["oos_calmar"] + 0.30*min(s["wf_efficiency"],2.0) + 0.20*s["stability_score"]*10
        if s["oos_net_r"] < 0: score -= 5.0
        ranked.append({**s, "promo_score": round(score, 4), "session": name.split("-")[0]})
    ranked.sort(key=lambda r: r["promo_score"], reverse=True)

    print(f"\n  {'#':>3} {'Name':>10} {'OOS R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} {'WFE':>5} {'Stab':>5} {'G':>2} {'Score':>6} {'Verdict':>10}")
    print(f"  {'-'*80}")
    verdicts = {}
    for i, r in enumerate(ranked):
        v = "PROMOTE" if r["oos_calmar"]>=2.0 and r["wf_efficiency"]>=0.3 and r["oos_net_r"]>0 and (i<3 or r["promo_score"]>2.0) else ("CHALLENGER" if r["oos_net_r"]>0 and r["oos_calmar"]>=1.0 else "REJECT")
        verdicts[r["name"]] = v
        print(f"  {i+1:3} {r['name']:>10} {r['oos_net_r']:+7.1f} {r['oos_calmar']:6.2f} {r['oos_sharpe']:5.2f} {r['oos_max_dd']:+6.1f} {r['wf_efficiency']:5.3f} {r['stability_score']:5.3f} {'Y' if r['gated'] else 'N':>2} {r['promo_score']:6.2f} {v:>10}")

    write_json(OUTPUT_DIR / "discovery_pipeline_results.json", {"candidates": summaries, "ranking": ranked, "verdicts": verdicts})
    print(f"\nTotal: {time.time()-t0:.0f}s | Output: {OUTPUT_DIR}")

if __name__ == "__main__":
    main()
