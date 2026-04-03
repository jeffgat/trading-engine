#!/usr/bin/env python3
"""NQ ORB Discovery Pipeline — Phases 1-5 for 8 candidates across 3 sessions.

Phase 0: Hold-out frozen at 2024-03-01
Phase 1: Structural screen (already done in sweep — candidates passed)
Phase 2: Discovery search (already done — 1296 configs/session)
Phase 3: Walk-forward ranking (12m IS / 3m OOS / 3m step)
Phase 4: Local stability check (narrow sweep around each candidate)
Phase 5: Promotion packet

Candidates:
  NY-A:  15m ORB, ATR 12% stop, RR=2.5, TP1=0.6, long
  NY-B:  30m ORB, ORB 25% stop, RR=2.5, TP1=0.4, long
  NY-C:  45m ORB, ATR 8% stop, RR=2.5, TP1=0.4, long, gated
  Asia-A: 15m ORB, ORB 100% stop, RR=3.0, TP1=0.6, long, gated
  Asia-B: 15m ORB, ORB 100% stop, RR=3.5, TP1=0.6, long, gated
  Asia-C: 30m ORB, ORB 100% stop, RR=2.0, TP1=0.5, long, gated
  LDN-A: 45m ORB, ATR 5% stop, RR=2.0, TP1=0.6, long, gated
  LDN-B: 45m ORB, ORB 100% stop, RR=3.5, TP1=0.6, long, gated
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
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.optimize.walkforward import run_walkforward
from orb_backtest.optimize.stability import analyze_parameter_stability
from orb_backtest.results.metrics import compute_metrics

OUTPUT_DIR = ROOT / "data" / "results" / "nq_orb_discovery_pipeline"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
N_WORKERS = 4


# ---------------------------------------------------------------------------
# Candidate configs
# ---------------------------------------------------------------------------

def _ny_a():
    """NY-A: 15m ORB, ATR 12% stop, RR=2.5, TP1=0.6, long"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="09:45",
            entry_start="09:45", entry_end="12:00",
            flat_start="15:50", flat_end="16:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.5, tp1_ratio=0.6, atr_length=14,
        name="NY-A 15m ATR12 RR2.5 TP0.6",
    )

def _ny_b():
    """NY-B: 30m ORB, ORB 25% stop, RR=2.5, TP1=0.4, long"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="10:00",
            entry_start="10:00", entry_end="12:00",
            flat_start="15:50", flat_end="16:00",
            stop_orb_pct=25.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="NY-B 30m ORB25 RR2.5 TP0.4",
    )

def _ny_c():
    """NY-C: 45m ORB, ATR 8% stop, RR=2.5, TP1=0.4, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="NY", orb_start="09:30", orb_end="10:15",
            entry_start="10:15", entry_end="12:00",
            flat_start="15:50", flat_end="16:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="NY-C 45m ATR8 RR2.5 TP0.4 gated",
    )

def _asia_a():
    """Asia-A: 15m ORB, ORB 100% stop, RR=3.0, TP1=0.6, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="Asia-A 15m ORB100 RR3.0 TP0.6 gated",
    )

def _asia_b():
    """Asia-B: 15m ORB, ORB 100% stop, RR=3.5, TP1=0.6, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15",
            flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="Asia-B 15m ORB100 RR3.5 TP0.6 gated",
    )

def _asia_c():
    """Asia-C: 30m ORB, ORB 100% stop, RR=2.0, TP1=0.5, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="Asia", orb_start="20:00", orb_end="20:30",
            entry_start="20:30", entry_end="23:15",
            flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.0, tp1_ratio=0.5, atr_length=14,
        name="Asia-C 30m ORB100 RR2.0 TP0.5 gated",
    )

def _ldn_a():
    """LDN-A: 45m ORB, ATR 5% stop, RR=2.0, TP1=0.6, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00",
            flat_start="08:20", flat_end="08:25",
            stop_atr_pct=5.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=2.0, tp1_ratio=0.6, atr_length=14,
        name="LDN-A 45m ATR5 RR2.0 TP0.6 gated",
    )

def _ldn_b():
    """LDN-B: 45m ORB, ORB 100% stop, RR=3.5, TP1=0.6, long (gated)"""
    return StrategyConfig(
        sessions=(SessionConfig(
            name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00",
            flat_start="08:20", flat_end="08:25",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0,
        ),),
        instrument=NQ, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long",
        rr=3.5, tp1_ratio=0.6, atr_length=14,
        name="LDN-B 45m ORB100 RR3.5 TP0.6 gated",
    )


CANDIDATES = {
    "NY-A": {"config_fn": _ny_a, "gated": False},
    "NY-B": {"config_fn": _ny_b, "gated": False},
    "NY-C": {"config_fn": _ny_c, "gated": True},
    "Asia-A": {"config_fn": _asia_a, "gated": True},
    "Asia-B": {"config_fn": _asia_b, "gated": True},
    "Asia-C": {"config_fn": _asia_c, "gated": True},
    "LDN-A": {"config_fn": _ldn_a, "gated": True},
    "LDN-B": {"config_fn": _ldn_b, "gated": True},
}

# Local sweep ranges for Phase 4 stability check
# Narrow ±1 step around each candidate's key params
LOCAL_SWEEP = {
    "rr": [-0.5, 0.0, +0.5],        # offsets from base
    "tp1_ratio": [-0.1, 0.0, +0.1],  # offsets from base
}


# ---------------------------------------------------------------------------
# Gate
# ---------------------------------------------------------------------------

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


# ---------------------------------------------------------------------------
# Phase 3: Walk-forward
# ---------------------------------------------------------------------------

def run_candidate_walkforward(name, config, df_5m, gate_fn, use_gate):
    """Run walk-forward for a single candidate with its local param neighborhood."""
    prefix = config.sessions[0].name.lower()

    # Build param ranges for WF sweep around the candidate's values
    # We sweep RR and TP1 in a narrow range around the anchor
    base_rr = config.rr
    base_tp1 = config.tp1_ratio

    rr_candidates = sorted(set([
        max(1.5, base_rr + d) for d in LOCAL_SWEEP["rr"]
    ]))
    tp1_candidates = sorted(set([
        round(max(0.2, min(1.0, base_tp1 + d)), 2) for d in LOCAL_SWEEP["tp1_ratio"]
    ]))

    # Only keep combos where tp1 * rr >= 1.0 — generate_param_grid will fail otherwise
    # Find the valid subset: for each rr, keep tp1 values that satisfy constraint
    rr_values = []
    tp1_values_set = set()
    for r in rr_candidates:
        valid_tp1s = [t for t in tp1_candidates if t * r >= 1.0]
        if valid_tp1s:
            rr_values.append(r)
            tp1_values_set.update(valid_tp1s)
    tp1_values = sorted(tp1_values_set)

    # Final safety: ensure ALL combos in the grid are valid
    # If some rr/tp1 combos are still invalid, we need to restrict further
    # Simplest: set tp1 floor = ceil(1.0 / min_rr * 100) / 100
    min_rr = min(rr_values) if rr_values else 2.0
    tp1_floor = 1.0 / min_rr
    tp1_values = [t for t in tp1_values if t >= tp1_floor]

    if not rr_values or not tp1_values:
        # Fallback: build valid combos from candidates directly
        rr_values = []
        tp1_values = []
        for r in rr_candidates:
            for t in tp1_candidates:
                if t * r >= 1.0:
                    if r not in rr_values:
                        rr_values.append(r)
                    if t not in tp1_values:
                        tp1_values.append(t)
        rr_values.sort()
        tp1_values.sort()

    if not rr_values or not tp1_values:
        # Last resort: base values only
        rr_values = [base_rr]
        tp1_values = [base_tp1]

    param_ranges = {
        "rr": rr_values,
        "tp1_ratio": tp1_values,
    }

    n_configs = len(rr_values) * len(tp1_values)
    print(f"    WF sweep: {len(rr_values)} RR x {len(tp1_values)} TP1 = {n_configs} configs", flush=True)
    print(f"    RR: {rr_values} | TP1: {tp1_values}", flush=True)

    gate_fn_to_use = gate_fn if use_gate else None

    wf_result = run_walkforward(
        df=df_5m,
        base_config=config,
        param_ranges=param_ranges,
        is_months=12,
        oos_months=3,
        step_months=3,
        objective="calmar",
        n_workers=N_WORKERS,
        start_date=df_5m.index[0].strftime("%Y-%m-%d"),
        gate_fn=gate_fn_to_use,
    )

    stability = analyze_parameter_stability(wf_result, param_ranges)

    return wf_result, stability


def summarize_wf(name, wf_result, stability):
    """Print walk-forward summary for one candidate."""
    cm = wf_result.combined_oos_metrics
    n_folds = len(wf_result.folds)
    filled_oos = len([t for t in wf_result.combined_oos_trades if t.exit_type != EXIT_NO_FILL])

    print(f"\n    {name} — Walk-Forward Summary")
    print(f"    Folds: {n_folds} | OOS trades: {filled_oos}")
    print(f"    Combined OOS: Net R={cm.get('total_r', 0):+.1f} | Calmar={cm.get('calmar_ratio', 0) or 0:.2f} | "
          f"Sharpe={cm.get('sharpe_ratio', 0) or 0:.2f} | DD={cm.get('max_drawdown_r', 0):.1f}R | "
          f"WR={cm.get('win_rate', 0):.1%}")
    print(f"    WF Efficiency: {wf_result.walk_forward_efficiency:.3f}")
    print(f"    Stability: {stability.overall_score:.3f} ({stability.interpretation})")

    # Per-fold OOS
    print(f"    Per-fold OOS Net R:", flush=True)
    for fold in wf_result.folds:
        fm = fold.oos_metrics
        net_r = fm.get("total_r", 0)
        trades = fm.get("total_trades", 0)
        print(f"      Fold {fold.fold_index}: {fold.oos_start}–{fold.oos_end} | "
              f"{net_r:+.1f}R ({trades} trades) | best={fold.best_params}")

    return {
        "name": name,
        "n_folds": n_folds,
        "oos_trades": filled_oos,
        "oos_net_r": round(float(cm.get("total_r", 0)), 2),
        "oos_calmar": round(float(cm.get("calmar_ratio", 0) or 0), 4),
        "oos_sharpe": round(float(cm.get("sharpe_ratio", 0) or 0), 4),
        "oos_max_dd": round(float(cm.get("max_drawdown_r", 0)), 2),
        "oos_win_rate": round(float(cm.get("win_rate", 0)), 4),
        "oos_pf": round(float(cm.get("profit_factor", 0) or 0), 4),
        "wf_efficiency": round(wf_result.walk_forward_efficiency, 4),
        "stability_score": round(stability.overall_score, 4),
        "stability_interp": stability.interpretation,
        "r_by_year": cm.get("r_by_year", {}),
        "folds": [
            {
                "oos_start": f.oos_start,
                "oos_end": f.oos_end,
                "oos_net_r": round(float(f.oos_metrics.get("total_r", 0)), 2),
                "best_params": f.best_params,
            }
            for f in wf_result.folds
        ],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def write_json(path, payload):
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def main():
    print("NQ ORB Discovery Pipeline — Phases 3-5")
    print("=" * 70)
    print(f"Hold-out: {HOLDOUT_START}+ (untouched)")
    print(f"WF: 12m IS / 3m OOS / 3m step | Objective: Calmar")
    print(f"Workers: {N_WORKERS} | Candidates: {len(CANDIDATES)}")

    t0 = time.time()
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print("\nLoading NQ 5m data...", flush=True)
    df_5m = load_5m_data(NQ.data_file)
    # Slice to pre-holdout
    df_pre = df_5m.loc[:HOLDOUT_START]
    print(f"  5m bars: {len(df_pre):,} (pre-holdout) [{time.time() - t0:.1f}s]")

    print("\nBuilding regime calendar...", flush=True)
    regime_calendar = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_calendar)

    # Phase 3 + 4: Walk-forward + stability for each candidate
    all_summaries = {}

    for cand_name, cand_info in CANDIDATES.items():
        print(f"\n{'=' * 60}")
        print(f"  CANDIDATE: {cand_name}")
        print(f"{'=' * 60}")

        config = cand_info["config_fn"]()
        use_gate = cand_info["gated"]
        print(f"    Config: {config.name}")
        print(f"    Gated: {use_gate}")

        t1 = time.time()
        wf_result, stability = run_candidate_walkforward(
            cand_name, config, df_pre, gate_fn, use_gate,
        )
        elapsed = time.time() - t1

        summary = summarize_wf(cand_name, wf_result, stability)
        summary["elapsed_s"] = round(elapsed, 1)
        summary["gated"] = use_gate
        all_summaries[cand_name] = summary

        print(f"    [{elapsed:.0f}s]")

    # Phase 5: Promotion ranking
    print(f"\n{'=' * 70}")
    print("PROMOTION RANKING")
    print(f"{'=' * 70}")

    # Sort by composite: 50% OOS Calmar + 30% WF efficiency + 20% stability
    ranked = []
    for name, s in all_summaries.items():
        promo_score = (
            0.50 * s["oos_calmar"]
            + 0.30 * min(s["wf_efficiency"], 2.0)  # cap efficiency contribution
            + 0.20 * s["stability_score"] * 10  # scale stability to ~0-10 range
        )
        # Penalty for negative OOS
        if s["oos_net_r"] < 0:
            promo_score -= 5.0

        session = name.split("-")[0]
        ranked.append({**s, "promo_score": round(promo_score, 4), "session": session})

    ranked.sort(key=lambda r: r["promo_score"], reverse=True)

    print(f"\n  {'#':>3s} {'Name':>10s} {'OOS R':>7s} {'Cal':>6s} {'Shp':>5s} {'DD':>6s} {'WFE':>5s} {'Stab':>5s} {'Gated':>5s} {'Score':>6s} {'Verdict':>10s}")
    print(f"  {'-' * 85}")

    verdicts = {}
    for i, r in enumerate(ranked):
        # Promotion logic
        if r["oos_calmar"] >= 2.0 and r["wf_efficiency"] >= 0.3 and r["oos_net_r"] > 0:
            verdict = "PROMOTE" if i < 3 or r["promo_score"] > 2.0 else "CHALLENGER"
        elif r["oos_net_r"] > 0 and r["oos_calmar"] >= 1.0:
            verdict = "CHALLENGER"
        else:
            verdict = "REJECT"

        verdicts[r["name"]] = verdict

        print(
            f"  {i+1:3d} {r['name']:>10s} {r['oos_net_r']:+7.1f} {r['oos_calmar']:6.2f} "
            f"{r['oos_sharpe']:5.2f} {r['oos_max_dd']:+6.1f} {r['wf_efficiency']:5.3f} "
            f"{r['stability_score']:5.3f} {'Yes' if r['gated'] else 'No':>5s} "
            f"{r['promo_score']:6.2f} {verdict:>10s}"
        )

    # Save everything
    write_json(output_dir / "discovery_pipeline_results.json", {
        "candidates": all_summaries,
        "ranking": ranked,
        "verdicts": verdicts,
        "holdout_start": HOLDOUT_START,
        "trial_note": (
            "8 candidates from 3888-config sweep. Each tested with 12m/3m/3m walk-forward "
            "on a 3x3 RR x TP1 local grid (max 9 configs/fold). "
            "Bailey-style PBO/DSR not implemented; verdicts are heuristic."
        ),
    })

    print(f"\nTotal time: {time.time() - t0:.0f}s")
    print(f"Output: {output_dir}")


if __name__ == "__main__":
    main()
