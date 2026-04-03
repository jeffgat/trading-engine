#!/usr/bin/env python3
"""NQ NY LSI — RR × TP1 grid sweep + risk/reward param sweeps.

Runs on the final 5m winner config (RR=2.0, TP1=0.5, ATR=14, Thu excl,
medium-vol regime gate) and sweeps:

  Phase A: RR × TP1 full 2D grid (the main event)
  Phase B: ATR length sweep (re-verify at final anchor)
  Phase C: min_gap_atr_pct sweep
  Phase D: entry_end sweep
  Phase E: entry_mode (close vs fvg_limit)

All sweeps apply Thu exclusion + medium-vol regime gate.
Pre-holdout: 2016-01 to 2025-03-31.
"""

import dataclasses
import json
import sys
import time
from pathlib import Path
from statistics import median

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Constants ────────────────────────────────────────────────────────────
HOLDOUT_START = "2025-04-01"
END_DATE = "2025-03-31"
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# ── Session ──────────────────────────────────────────────────────────────
NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

# ── Anchor: exact 5m winner ─────────────────────────────────────────────
ANCHOR = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(3,),  # Thu only
    name="NQ NY LSI Anchor",
)

# ── Sweep grids ──────────────────────────────────────────────────────────

# Phase A: RR × TP1 — constrained by tp1_ratio * rr >= 1.0
RR_VALUES = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0, 3.5, 4.0, 4.5, 5.0]
TP1_VALUES = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 0.9, 1.0]

# Phase B: ATR length
ATR_VALUES = [5, 7, 10, 12, 14, 16, 18, 20, 25, 30]

# Phase C: gap pct
GAP_VALUES = [0.0, 1.0, 2.0, 3.0, 3.75, 4.0, 4.5, 5.0, 5.5, 6.0, 7.5, 10.0]

# Phase D: entry_end
ENTRY_END_VALUES = ["11:00", "12:00", "13:00", "14:00", "15:00", "15:30"]

# Phase E: entry mode
ENTRY_MODES = ["close", "fvg_limit"]


# ── Helpers ──────────────────────────────────────────────────────────────

def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def run_one(df, config, gate_fn, maps, df_1m, df_1s):
    """Run backtest + regime gate, return metrics dict."""
    trades_raw = run_backtest(df, config, end_date=END_DATE,
                              df_1m=df_1m, df_1s=df_1s, _maps=maps)
    trades = gate_fn(trades_raw)
    m = compute_metrics(trades)
    filled = _filled_trades(trades)
    raw_filled = _filled_trades(trades_raw)
    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    return {
        "trades": m["total_trades"],
        "trades_raw": len(raw_filled),
        "win_rate": m["win_rate"],
        "net_r": m["total_r"],
        "max_dd_r": m["max_drawdown_r"],
        "calmar": m["calmar_ratio"],
        "sharpe": m["sharpe_ratio"],
        "pf": m["profit_factor"],
        "avg_r": m["avg_r"],
        "r_per_yr": m.get("avg_annual_r", m["total_r"] / 9.25),
        "med_stop_ticks": med_stop,
        "r_by_year": m.get("r_by_year", {}),
        "neg_years": sum(1 for v in m.get("r_by_year", {}).values() if v < 0),
    }


def print_row(idx, total, label, r, anchor_calmar=None, elapsed=None):
    neg_str = f" ({r['neg_years']} neg yr)" if r["neg_years"] > 0 else ""
    delta_str = f" ({r['calmar'] - anchor_calmar:>+.2f})" if anchor_calmar is not None else ""
    elapsed_str = f"  [{elapsed:.1f}s]" if elapsed else ""
    print(
        f"  [{idx:>3}/{total}] {label:<35} "
        f"{r['trades']:>4}tr  {r['win_rate']:>5.1%}WR  "
        f"{r['net_r']:>+7.1f}R  DD {r['max_dd_r']:>6.1f}R  "
        f"Calm {r['calmar']:>7.2f}{delta_str}  Shrp {r['sharpe']:>5.2f}  "
        f"PF {r['pf']:>4.2f}{neg_str}{elapsed_str}",
        flush=True,
    )


def print_ranked(title, rows, top_n=None):
    rows_sorted = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)
    if top_n:
        rows_sorted = rows_sorted[:top_n]
    print(f"\n{'=' * 145}", flush=True)
    print(f"  {title}", flush=True)
    print(f"{'=' * 145}", flush=True)
    print(
        f"  {'#':>3} {'Config':<35} {'Tr':>4} {'WR%':>6} {'NetR':>7} {'MaxDD':>7} "
        f"{'Calm':>7} {'Shrp':>6} {'PF':>5} {'R/yr':>6} {'NegYr':>5}",
        flush=True,
    )
    print(f"  {'-' * 139}", flush=True)
    for i, (label, r) in enumerate(rows_sorted):
        print(
            f"  {i+1:>3} {label:<35} {r['trades']:>4} {r['win_rate']:>5.1%} "
            f"{r['net_r']:>+7.1f} {r['max_dd_r']:>7.1f} {r['calmar']:>7.2f} "
            f"{r['sharpe']:>6.2f} {r['pf']:>5.2f} {r['r_per_yr']:>6.1f} "
            f"{r['neg_years']:>5}",
            flush=True,
        )

    # R by year for top 3
    print(f"\n  R by year — top 3:", flush=True)
    for i, (label, r) in enumerate(rows_sorted[:3]):
        rby = r["r_by_year"]
        years_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in sorted(rby.items()))
        print(f"    #{i+1} {label:<35} {years_str}", flush=True)

    return rows_sorted


def main():
    t_start = time.time()

    print("=" * 80, flush=True)
    print("NQ NY LSI — RR × TP1 GRID SWEEP + RISK/REWARD PARAMS", flush=True)
    print("=" * 80, flush=True)
    print(f"Anchor: RR=2.0, TP1=0.5, ATR=14, gap=5.0%, Thu excl, medium-vol gate", flush=True)
    print(f"Anchor performance: 588 tr, 61.1% WR, +126.4R, DD -7.6R, Calmar 16.72", flush=True)
    print(f"Pre-holdout: 2016 to {END_DATE}", flush=True)
    print(flush=True)

    # ── Load data ────────────────────────────────────────────────────────
    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}", flush=True)

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)
    print(f"  Setup complete in {time.time() - t_start:.1f}s\n", flush=True)

    # ── Anchor baseline ──────────────────────────────────────────────────
    print("Running anchor baseline...", flush=True)
    t1 = time.time()
    anchor_r = run_one(df_5m, ANCHOR, gate_fn, maps, df_1m, df_1s)
    anchor_calmar = anchor_r["calmar"]
    print_row(1, 1, "ANCHOR (RR=2.0 TP1=0.5)", anchor_r, elapsed=time.time() - t1)
    print(flush=True)

    all_results = {"anchor": anchor_r}

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE A: RR × TP1 2D grid
    # ═══════════════════════════════════════════════════════════════════════
    print(f"{'─' * 80}", flush=True)
    print("PHASE A: RR × TP1 2D Grid", flush=True)
    print(f"  RR: {RR_VALUES}", flush=True)
    print(f"  TP1: {TP1_VALUES}", flush=True)
    print(f"  Constraint: tp1_ratio * rr >= 1.0", flush=True)
    print(f"{'─' * 80}", flush=True)

    # Count valid combos
    valid_combos = [(rr, tp1) for rr in RR_VALUES for tp1 in TP1_VALUES if tp1 * rr >= 1.0]
    total = len(valid_combos)
    print(f"  {total} valid combinations (out of {len(RR_VALUES) * len(TP1_VALUES)})", flush=True)

    grid_rows = []
    idx = 0
    for rr, tp1 in valid_combos:
        idx += 1
        label = f"RR={rr:.2f} TP1={tp1:.2f}"
        try:
            cfg = dataclasses.replace(ANCHOR, rr=rr, tp1_ratio=tp1,
                                       name=f"NQ NY LSI RR{rr} TP{tp1}")
        except ValueError:
            continue

        t1 = time.time()
        r = run_one(df_5m, cfg, gate_fn, maps, df_1m, df_1s)
        grid_rows.append((label, r))
        print_row(idx, total, label, r, anchor_calmar, time.time() - t1)

    all_results["rr_tp1_grid"] = grid_rows
    grid_sorted = print_ranked("PHASE A: RR × TP1 GRID — TOP 30", grid_rows, top_n=30)

    # Print the full grid as a heatmap
    print(f"\n  CALMAR HEATMAP (RR rows × TP1 columns):", flush=True)
    grid_dict = {(rr, tp1): r["calmar"] for (label, r) in grid_rows
                 for rr, tp1 in [tuple(float(x.split("=")[1]) for x in label.split())]}

    # Header
    header = f"  {'RR↓ TP1→':>10}"
    for tp1 in TP1_VALUES:
        header += f"  {tp1:>5.2f}"
    print(header, flush=True)
    print(f"  {'-' * (12 + 7 * len(TP1_VALUES))}", flush=True)

    for rr in RR_VALUES:
        row_str = f"  {rr:>10.2f}"
        for tp1 in TP1_VALUES:
            if tp1 * rr < 1.0:
                row_str += "      -"
            elif (rr, tp1) in grid_dict:
                calm = grid_dict[(rr, tp1)]
                row_str += f"  {calm:>5.1f}"
            else:
                row_str += "      ?"
        print(row_str, flush=True)

    # Extract best RR/TP1
    best_grid_label, best_grid_r = grid_sorted[0]
    parts = best_grid_label.split()
    best_rr = float(parts[0].split("=")[1])
    best_tp1 = float(parts[1].split("=")[1])
    print(f"\n  → Best RR×TP1: RR={best_rr}, TP1={best_tp1} (Calmar {best_grid_r['calmar']:.2f})", flush=True)

    # Also highlight all 0-neg-year combos
    zero_neg = [(l, r) for l, r in grid_rows if r["neg_years"] == 0]
    if zero_neg:
        print(f"\n  0-negative-year combos ({len(zero_neg)}):", flush=True)
        for l, r in sorted(zero_neg, key=lambda x: x[1]["calmar"], reverse=True):
            print(f"    {l:<35} Calmar {r['calmar']:>7.2f}  {r['trades']}tr  {r['net_r']:+.1f}R  DD {r['max_dd_r']:.1f}R", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE B: ATR length at best RR/TP1
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE B: ATR length sweep (at RR={best_rr}, TP1={best_tp1})", flush=True)
    print(f"{'─' * 80}", flush=True)

    atr_rows = []
    total = len(ATR_VALUES)
    for idx, atr in enumerate(ATR_VALUES, 1):
        label = f"ATR={atr}"
        cfg = dataclasses.replace(ANCHOR, rr=best_rr, tp1_ratio=best_tp1,
                                   atr_length=atr, name=f"NQ NY LSI ATR{atr}")
        t1 = time.time()
        r = run_one(df_5m, cfg, gate_fn, maps, df_1m, df_1s)
        atr_rows.append((label, r))
        print_row(idx, total, label, r, anchor_calmar, time.time() - t1)

    all_results["atr"] = atr_rows
    atr_sorted = print_ranked("PHASE B: ATR LENGTH SWEEP", atr_rows)

    best_atr_label, best_atr_r = atr_sorted[0]
    best_atr = int(best_atr_label.split("=")[1])
    print(f"\n  → Best ATR: {best_atr} (Calmar {best_atr_r['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE C: min_gap_atr_pct at best RR/TP1/ATR
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE C: min_gap_atr_pct sweep (at RR={best_rr}, TP1={best_tp1}, ATR={best_atr})", flush=True)
    print(f"{'─' * 80}", flush=True)

    gap_rows = []
    total = len(GAP_VALUES)
    for idx, gap in enumerate(GAP_VALUES, 1):
        label = f"gap={gap:.1f}%"
        ny_sess = dataclasses.replace(NY_SESSION, min_gap_atr_pct=gap)
        cfg = dataclasses.replace(ANCHOR, sessions=(ny_sess,), rr=best_rr,
                                   tp1_ratio=best_tp1, atr_length=best_atr,
                                   name=f"NQ NY LSI gap{gap}")
        t1 = time.time()
        r = run_one(df_5m, cfg, gate_fn, maps, df_1m, df_1s)
        gap_rows.append((label, r))
        print_row(idx, total, label, r, anchor_calmar, time.time() - t1)

    all_results["gap"] = gap_rows
    gap_sorted = print_ranked("PHASE C: MIN_GAP_ATR_PCT SWEEP", gap_rows)

    best_gap_label, best_gap_r = gap_sorted[0]
    best_gap = float(best_gap_label.split("=")[1].rstrip("%"))
    print(f"\n  → Best gap: {best_gap}% (Calmar {best_gap_r['calmar']:.2f})", flush=True)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE D: entry_end sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE D: entry_end sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    ee_rows = []
    total = len(ENTRY_END_VALUES)
    for idx, ee in enumerate(ENTRY_END_VALUES, 1):
        label = f"entry_end={ee}"
        ny_sess = dataclasses.replace(NY_SESSION, entry_end=ee, min_gap_atr_pct=best_gap)
        cfg = dataclasses.replace(ANCHOR, sessions=(ny_sess,), rr=best_rr,
                                   tp1_ratio=best_tp1, atr_length=best_atr,
                                   name=f"NQ NY LSI ee{ee}")
        t1 = time.time()
        r = run_one(df_5m, cfg, gate_fn, maps, df_1m, df_1s)
        ee_rows.append((label, r))
        print_row(idx, total, label, r, anchor_calmar, time.time() - t1)

    all_results["entry_end"] = ee_rows
    print_ranked("PHASE D: ENTRY_END SWEEP", ee_rows)

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE E: entry mode (close vs fvg_limit)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}", flush=True)
    print(f"PHASE E: entry mode sweep", flush=True)
    print(f"{'─' * 80}", flush=True)

    em_rows = []
    total = len(ENTRY_MODES)
    for idx, em in enumerate(ENTRY_MODES, 1):
        label = f"entry_mode={em}"
        ny_sess = dataclasses.replace(NY_SESSION, min_gap_atr_pct=best_gap)
        cfg = dataclasses.replace(ANCHOR, sessions=(ny_sess,), rr=best_rr,
                                   tp1_ratio=best_tp1, atr_length=best_atr,
                                   lsi_entry_mode=em,
                                   name=f"NQ NY LSI em={em}")
        t1 = time.time()
        r = run_one(df_5m, cfg, gate_fn, maps, df_1m, df_1s)
        em_rows.append((label, r))
        print_row(idx, total, label, r, anchor_calmar, time.time() - t1)

    all_results["entry_mode"] = em_rows
    print_ranked("PHASE E: ENTRY MODE SWEEP", em_rows)

    # ═══════════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}", flush=True)
    print("FINAL SUMMARY", flush=True)
    print(f"{'=' * 80}", flush=True)
    print(f"\n  Anchor: RR=2.0, TP1=0.5, ATR=14, gap=5.0% → Calmar {anchor_calmar:.2f}", flush=True)
    print(flush=True)

    # Best from each phase
    for phase_name, rows in [(k, v) for k, v in all_results.items() if k != "anchor"]:
        best = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)[0]
        label, r = best
        delta = r["calmar"] - anchor_calmar
        print(
            f"  Best {phase_name:<15}: {label:<35} "
            f"Calmar {r['calmar']:>7.2f} ({delta:>+.2f})  "
            f"{r['trades']}tr  {r['net_r']:+.1f}R  DD {r['max_dd_r']:.1f}R  "
            f"Sharpe {r['sharpe']:.2f}  NegYr {r['neg_years']}",
            flush=True,
        )

    # ── Save ─────────────────────────────────────────────────────────────
    output_path = ROOT / "data" / "results" / "nq_ny_lsi_rr_tp1_grid_sweep.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def convert(obj):
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    save_data = {
        "info": {
            "description": "NQ NY LSI RR×TP1 grid + risk/reward param sweeps on final 5m config",
            "anchor": "RR=2.0, TP1=0.5, ATR=14, gap=5.0%, Thu excl, medium-vol gate, Calmar 16.72",
            "holdout_start": HOLDOUT_START,
            "end_date": END_DATE,
        },
        "phases": {
            phase: [{"label": l, **{k: v for k, v in r.items() if k != "r_by_year"}}
                    for l, r in rows]
            for phase, rows in all_results.items() if phase != "anchor"
        },
        "anchor": {k: v for k, v in anchor_r.items() if k != "r_by_year"},
    }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}", flush=True)
    print(f"Total time: {time.time() - t_start:.1f}s", flush=True)


if __name__ == "__main__":
    main()
