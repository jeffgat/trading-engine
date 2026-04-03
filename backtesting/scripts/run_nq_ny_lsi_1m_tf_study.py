#!/usr/bin/env python3
"""NQ NY LSI — 1-minute timeframe study.

Tests whether the proven NQ NY LSI RR2/TP0.5 edge survives on 1m candles.
Uses the exact winning config from the 5m study as the anchor, with swing
params scaled to preserve the same real-time window (5h = 300 bars at 1m
vs 60 bars at 5m).

Phases:
  A) Baseline: 5m-equivalent params on 1m bars (sanity check)
  B) Swing param sweep: n_left × n_right grid (the primary question)
  C) FVG window sweep: fvg_window_left × fvg_window_right
  D) DOW filter sweep: all exclusion combos
  E) min_gap_atr_pct sweep

Regime gate (skip bull_medium_vol + sideways_medium_vol) and Thu exclusion
from the 5m winner are applied as the default. DOW sweep tests alternatives.

Pre-holdout: 2016-01 to 2025-03-31 (holdout frozen at 2025-04-01).

NOTE: 1m data is ~5x larger than 5m. Each backtest takes longer.
No 1s magnifier is used — 1m resolution is already fine enough for
fill/exit simulation. This reduces memory and runtime significantly.
"""

import dataclasses
import json
import sys
import time
from itertools import product
from pathlib import Path
from statistics import median

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Constants ────────────────────────────────────────────────────────────
HOLDOUT_START = "2025-04-01"
END_DATE = "2025-03-31"
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# ── Session config (same as 5m winner) ───────────────────────────────────
NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

# ── Anchor config: 5m winner with params scaled for 1m bars ─────────────
# Time-equivalent scaling:
#   5m n_left=8   → 1m n_left=40  (8 * 5 = 40)
#   5m n_right=60 → 1m n_right=300 (60 * 5 = 300)
#   5m fvg_window_left=20  → 1m fvg_window_left=100  (20 * 5)
#   5m fvg_window_right=5  → 1m fvg_window_right=25  (5 * 5)
ANCHOR_1M = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=False,  # No magnifier needed — 1m is fine enough
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=14,
    lsi_n_left=40,            # time-scaled from 8
    lsi_n_right=300,           # time-scaled from 60
    lsi_fvg_window_left=100,   # time-scaled from 20
    lsi_fvg_window_right=25,   # time-scaled from 5
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(3,),        # Thu excluded (same as 5m winner)
    name="NQ NY LSI 1m Baseline",
)


# ── Helpers ──────────────────────────────────────────────────────────────

def make_avoidance_gate(regime_calendar):
    """Build a regime gate function that removes trades on avoided regimes."""
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades
                if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def run_one(df_1m, config, gate_fn, maps=None):
    """Run a single backtest, apply regime gate, return metrics dict."""
    trades_raw = run_backtest(
        df_1m, config,
        end_date=END_DATE,
        _maps=maps,
    )
    trades = gate_fn(trades_raw)
    m = compute_metrics(trades)
    filled = _filled_trades(trades)
    raw_filled = _filled_trades(trades_raw)
    removed = len(raw_filled) - len(filled)
    med_stop = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0
    return {
        "trades": m["total_trades"],
        "trades_raw": len(raw_filled),
        "removed": removed,
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


def print_row(idx, total, label, r, elapsed=None):
    """Print a formatted result row."""
    neg_str = f" ({r['neg_years']} neg yr)" if r["neg_years"] > 0 else ""
    elapsed_str = f"  [{elapsed:.1f}s]" if elapsed else ""
    print(
        f"  [{idx:>3}/{total}] {label:<45} "
        f"{r['trades']:>4}tr  {r['win_rate']:>5.1%}WR  "
        f"{r['net_r']:>+7.1f}R  DD {r['max_dd_r']:>6.1f}R  "
        f"Calm {r['calmar']:>6.2f}  Shrp {r['sharpe']:>5.2f}  "
        f"PF {r['pf']:>4.2f}  "
        f"Med stop {r['med_stop_ticks']:.0f}tk{neg_str}{elapsed_str}"
    )


def print_section(title, rows):
    """Print a ranked section."""
    rows_sorted = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)
    print(f"\n{'=' * 140}")
    print(f"  {title}")
    print(f"{'=' * 140}")
    print(
        f"  {'#':>3} {'Config':<45} {'Tr':>4} {'WR%':>6} {'NetR':>7} {'MaxDD':>7} "
        f"{'Calm':>7} {'Shrp':>6} {'PF':>5} {'R/yr':>6} {'MedSt':>6} {'NegYr':>5}"
    )
    print(f"  {'-' * 134}")
    for i, (label, r) in enumerate(rows_sorted):
        print(
            f"  {i+1:>3} {label:<45} {r['trades']:>4} {r['win_rate']:>5.1%} "
            f"{r['net_r']:>+7.1f} {r['max_dd_r']:>7.1f} {r['calmar']:>7.2f} "
            f"{r['sharpe']:>6.2f} {r['pf']:>5.2f} {r['r_per_yr']:>6.1f} "
            f"{r['med_stop_ticks']:>6.0f} {r['neg_years']:>5}"
        )

    # R by year for top 3
    print(f"\n  R by year — top 3:")
    for i, (label, r) in enumerate(rows_sorted[:3]):
        rby = r["r_by_year"]
        years_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in sorted(rby.items()))
        print(f"    #{i+1} {label:<45} {years_str}")

    return rows_sorted


def main():
    t_start = time.time()

    print("=" * 80)
    print("NQ NY LSI — 1-MINUTE TIMEFRAME STUDY")
    print("=" * 80)
    print(f"Anchor: NQ NY LSI RR2/TP0.5 + Thu excl + medium-vol gate (5m Calmar 16.72)")
    print(f"Pre-holdout: 2016 to {END_DATE}")
    print(f"Holdout frozen: {HOLDOUT_START}")
    print()

    # ── Load data ────────────────────────────────────────────────────────
    print("Loading NQ 1m data...", flush=True)
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    print(f"  1m bars: {len(df_1m):,}")

    # No magnifier needed for 1m — resolution is already fine
    # Build empty maps (no sub-bar data)
    maps = build_maps(df_1m)

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_1m)
    gate_fn = make_avoidance_gate(regime_cal)

    all_results = {}

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE A: Baseline — 5m-equivalent params on 1m
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}")
    print("PHASE A: Baseline (5m-equivalent params on 1m)")
    print(f"{'─' * 80}")

    t1 = time.time()
    r = run_one(df_1m, ANCHOR_1M, gate_fn, maps)
    print_row(1, 1, "1m baseline (time-equiv)", r, time.time() - t1)
    all_results["baseline"] = [("1m baseline (time-equiv)", r)]

    # Also run with exact 5m bar counts (no scaling) — very fine pivots
    exact_5m_cfg = dataclasses.replace(
        ANCHOR_1M,
        lsi_n_left=8, lsi_n_right=60,
        lsi_fvg_window_left=20, lsi_fvg_window_right=5,
        name="NQ NY LSI 1m Exact5mParams",
    )
    t1 = time.time()
    r2 = run_one(df_1m, exact_5m_cfg, gate_fn, maps)
    print_row(2, 2, "1m exact-5m-params (micro pivots)", r2, time.time() - t1)
    all_results["baseline"].append(("1m exact-5m-params (micro pivots)", r2))

    print_section("PHASE A: BASELINE COMPARISON", all_results["baseline"])

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE B: Swing param sweep (n_left × n_right)
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}")
    print("PHASE B: Swing param sweep (n_left × n_right)")
    print(f"{'─' * 80}")

    # 1m bars → need larger bar counts to span same time windows
    # Test both small (micro-structure) and large (macro-structure) pivots
    N_LEFT_VALUES = [8, 15, 20, 30, 40, 50, 60, 80]
    # n_right: range from ~30 min to ~10 hours
    N_RIGHT_VALUES = [30, 60, 100, 150, 200, 300, 400]

    swing_rows = []
    total = len(N_LEFT_VALUES) * len(N_RIGHT_VALUES)
    idx = 0
    for nl in N_LEFT_VALUES:
        for nr in N_RIGHT_VALUES:
            idx += 1
            label = f"nL={nl} nR={nr}"
            cfg = dataclasses.replace(ANCHOR_1M, lsi_n_left=nl, lsi_n_right=nr,
                                       name=f"NQ NY LSI 1m nL{nl} nR{nr}")
            t1 = time.time()
            r = run_one(df_1m, cfg, gate_fn, maps)
            swing_rows.append((label, r))
            print_row(idx, total, label, r, time.time() - t1)

    all_results["swing"] = swing_rows
    swing_sorted = print_section("PHASE B: SWING PARAM SWEEP (n_left × n_right)", swing_rows)

    # Extract best swing params
    best_swing_label, best_swing_r = swing_sorted[0]
    parts = best_swing_label.split()
    best_nl = int(parts[0].split("=")[1])
    best_nr = int(parts[1].split("=")[1])
    print(f"\n  → Best swing: n_left={best_nl}, n_right={best_nr} (Calmar {best_swing_r['calmar']:.2f})")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE C: FVG window sweep at best swing params
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}")
    print(f"PHASE C: FVG window sweep (at n_left={best_nl}, n_right={best_nr})")
    print(f"{'─' * 80}")

    FVG_LEFT_VALUES = [20, 40, 60, 80, 100, 130, 160]
    FVG_RIGHT_VALUES = [5, 10, 15, 25, 35, 50]

    fvg_rows = []
    total = len(FVG_LEFT_VALUES) * len(FVG_RIGHT_VALUES)
    idx = 0
    for fl in FVG_LEFT_VALUES:
        for fr in FVG_RIGHT_VALUES:
            idx += 1
            label = f"fvgL={fl} fvgR={fr}"
            cfg = dataclasses.replace(
                ANCHOR_1M,
                lsi_n_left=best_nl, lsi_n_right=best_nr,
                lsi_fvg_window_left=fl, lsi_fvg_window_right=fr,
                name=f"NQ NY LSI 1m fvgL{fl} fvgR{fr}",
            )
            t1 = time.time()
            r = run_one(df_1m, cfg, gate_fn, maps)
            fvg_rows.append((label, r))
            print_row(idx, total, label, r, time.time() - t1)

    all_results["fvg"] = fvg_rows
    fvg_sorted = print_section("PHASE C: FVG WINDOW SWEEP", fvg_rows)

    best_fvg_label, best_fvg_r = fvg_sorted[0]
    parts = best_fvg_label.split()
    best_fl = int(parts[0].split("=")[1])
    best_fr = int(parts[1].split("=")[1])
    print(f"\n  → Best FVG: fvg_left={best_fl}, fvg_right={best_fr} (Calmar {best_fvg_r['calmar']:.2f})")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE D: DOW filter sweep at best swing + FVG params
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}")
    print(f"PHASE D: DOW filter sweep (at nL={best_nl}, nR={best_nr}, fvgL={best_fl}, fvgR={best_fr})")
    print(f"{'─' * 80}")

    DOW_COMBOS = {
        "No filter": (),
        "Thu excl": (3,),
        "Wed+Thu excl": (2, 3),
        "Mon excl": (0,),
        "Mon+Thu excl": (0, 3),
        "Mon+Wed+Thu excl": (0, 2, 3),
        "MTF only": (2, 3),          # Mon/Tue/Fri
        "Tue+Fri only": (0, 2, 3),   # Tue+Fri
        "Fri only": (0, 1, 2, 3),    # Fri only
    }

    dow_rows = []
    total = len(DOW_COMBOS)
    for idx, (label, excl_days) in enumerate(DOW_COMBOS.items(), 1):
        cfg = dataclasses.replace(
            ANCHOR_1M,
            lsi_n_left=best_nl, lsi_n_right=best_nr,
            lsi_fvg_window_left=best_fl, lsi_fvg_window_right=best_fr,
            excluded_days=excl_days,
            name=f"NQ NY LSI 1m DOW {label}",
        )
        t1 = time.time()
        r = run_one(df_1m, cfg, gate_fn, maps)
        dow_rows.append((label, r))
        print_row(idx, total, label, r, time.time() - t1)

    all_results["dow"] = dow_rows
    dow_sorted = print_section("PHASE D: DOW FILTER SWEEP", dow_rows)

    best_dow_label, best_dow_r = dow_sorted[0]
    best_excl = DOW_COMBOS[best_dow_label]
    print(f"\n  → Best DOW: {best_dow_label} (Calmar {best_dow_r['calmar']:.2f})")

    # ═══════════════════════════════════════════════════════════════════════
    # PHASE E: min_gap_atr_pct sweep
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'─' * 80}")
    print(f"PHASE E: min_gap_atr_pct sweep")
    print(f"{'─' * 80}")

    GAP_VALUES = [0.0, 1.0, 2.0, 3.0, 3.75, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]

    gap_rows = []
    total = len(GAP_VALUES)
    for idx, gap in enumerate(GAP_VALUES, 1):
        label = f"gap={gap:.1f}%"
        ny_sess = dataclasses.replace(NY_SESSION, min_gap_atr_pct=gap)
        cfg = dataclasses.replace(
            ANCHOR_1M,
            sessions=(ny_sess,),
            lsi_n_left=best_nl, lsi_n_right=best_nr,
            lsi_fvg_window_left=best_fl, lsi_fvg_window_right=best_fr,
            excluded_days=best_excl,
            name=f"NQ NY LSI 1m gap{gap}",
        )
        t1 = time.time()
        r = run_one(df_1m, cfg, gate_fn, maps)
        gap_rows.append((label, r))
        print_row(idx, total, label, r, time.time() - t1)

    all_results["gap"] = gap_rows
    gap_sorted = print_section("PHASE E: MIN_GAP_ATR_PCT SWEEP", gap_rows)

    # ═══════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print("FINAL SUMMARY — 1m TIMEFRAME STUDY")
    print(f"{'=' * 80}")
    print(f"\n  5m reference: 588 tr, 61.1% WR, +126.4R, DD -7.6R, Calmar 16.72, Sharpe 3.646")
    print()

    # Best from each phase
    for phase_name, rows in all_results.items():
        best = sorted(rows, key=lambda x: x[1]["calmar"], reverse=True)[0]
        label, r = best
        print(
            f"  Best {phase_name:<12}: {label:<45} "
            f"{r['trades']}tr  {r['win_rate']:.1%}WR  {r['net_r']:+.1f}R  "
            f"DD {r['max_dd_r']:.1f}R  Calmar {r['calmar']:.2f}  Sharpe {r['sharpe']:.2f}"
        )

    # ── Save results ─────────────────────────────────────────────────────
    output_path = ROOT / "data" / "results" / "nq_ny_lsi_1m_tf_study.json"
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
            "description": "NQ NY LSI 1m timeframe study",
            "reference_5m": "Calmar 16.72, 588 tr, +126.4R, Sharpe 3.646",
            "holdout_start": HOLDOUT_START,
            "end_date": END_DATE,
        },
        "phases": {
            phase: [{"label": l, **{k: v for k, v in r.items() if k != "r_by_year"}}
                    for l, r in rows]
            for phase, rows in all_results.items()
        },
    }

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}")
    print(f"Total time: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
