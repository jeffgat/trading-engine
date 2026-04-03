#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 2: Variable sweeps on 2 promoted anchors.

Anchors (from Step 1 baseline):
  A: fvg_limit (Calmar 13.94, 943 trades, 1 neg year)
  B: fvg_limit + 1stFVG (Calmar 12.17, 632 trades, 0 neg years)

Both use RR=2.0, TP1=0.5, gap=5.0%, ATR=10, n_left=8, n_right=60,
fvg_left=20, fvg_right=5, long-only, Mon/Tue/Fri, 1s magnifier.

Sweep dimensions (one at a time, holding others at anchor):
  1. rr: [1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5, 4.0]
  2. tp1_ratio: [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8]
  3. min_gap_atr_pct: [2.0, 3.0, 3.75, 5.0, 7.5, 10.0]
  4. atr_length: [5, 10, 14, 20, 30, 40]
  5. lsi_n_left: [3, 5, 8, 10, 15, 20, 25]
  6. lsi_n_right: [30, 45, 60, 78, 90, 120]
  7. lsi_fvg_window_left: [5, 10, 15, 20, 30]
  8. lsi_fvg_window_right: [2, 3, 5, 7, 10, 15]
  9. direction_filter: ["long", "short", "both"]
 10. excluded_days: [None, (2,3), (3,), (2,)]  (ALL, MTF, MTWF, MTRF)
 11. entry_end: ["12:00", "13:00", "14:00", "15:00", "15:30"]
 12. flat_start: ["14:00", "15:00", "15:30", "15:50", "16:00"]

Uses 1s magnifier. Pre-holdout: 2016 to 2025-03-31.
"""

import dataclasses
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

HOLDOUT_START = "2025-04-01"
END_DATE = "2025-03-31"

# ── Anchor configs ────────────────────────────────────────────────────────

NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

ANCHOR_A = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,
    tp1_ratio=0.5,
    atr_length=10,
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
    excluded_days=(2, 3),
    name="Anchor A (fvg_limit)",
)

ANCHOR_B = dataclasses.replace(ANCHOR_A, lsi_first_fvg_only=True, name="Anchor B (fvg_limit 1stFVG)")

ANCHORS = {"A": ANCHOR_A, "B": ANCHOR_B}

# ── Sweep dimensions ─────────────────────────────────────────────────────

SWEEPS = {
    "rr": [1.5, 1.75, 2.0, 2.25, 2.5, 3.0, 3.5, 4.0],
    "tp1_ratio": [0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    "ny_min_gap_atr_pct": [2.0, 3.0, 3.75, 5.0, 7.5, 10.0],
    "atr_length": [5, 10, 14, 20, 30, 40],
    "lsi_n_left": [3, 5, 8, 10, 15, 20, 25],
    "lsi_n_right": [30, 45, 60, 78, 90, 120],
    "lsi_fvg_window_left": [5, 10, 15, 20, 30],
    "lsi_fvg_window_right": [2, 3, 5, 7, 10, 15],
    "direction_filter": ["long", "short", "both"],
    "excluded_days": [(), (2, 3), (3,), (2,)],
    "ny_entry_end": ["12:00", "13:00", "14:00", "15:00", "15:30"],
    "ny_flat_start": ["14:00", "15:00", "15:30", "15:50", "16:00"],
}

DOW_LABELS = {(): "ALL", (2, 3): "MTF", (3,): "MTWF", (2,): "MTRF"}


def run_single(df_5m, cfg, maps, df_1m, df_1s):
    """Run one backtest and return metrics dict."""
    trades = run_backtest(df_5m, cfg, end_date=END_DATE, df_1m=df_1m, df_1s=df_1s, _maps=maps)
    m = compute_metrics(trades)
    rby = m.get("r_by_year", {})
    return {
        "trades": m["total_trades"],
        "win_rate": m["win_rate"],
        "net_r": m["total_r"],
        "max_dd_r": m["max_drawdown_r"],
        "calmar": m["calmar_ratio"],
        "sharpe": m["sharpe_ratio"],
        "pf": m["profit_factor"],
        "avg_r": m["avg_r"],
        "neg_years": sum(1 for v in rby.values() if v < 0),
        "r_by_year": rby,
    }


def main():
    t0 = time.time()

    print("Loading NQ data (5m + 1m + 1s)...")
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")

    print("Building bar maps...")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  Maps built in {time.time() - t0:.1f}s\n")

    all_results = {}
    total_runs = 0

    for anchor_name, anchor in ANCHORS.items():
        print(f"{'=' * 130}")
        print(f"ANCHOR {anchor_name}: {anchor.name}")
        print(f"  rr={anchor.rr} tp1={anchor.tp1_ratio} gap={anchor.sessions[0].min_gap_atr_pct}% "
              f"atr={anchor.atr_length} nl={anchor.lsi_n_left} nr={anchor.lsi_n_right} "
              f"fl={anchor.lsi_fvg_window_left} fr={anchor.lsi_fvg_window_right} "
              f"1stFVG={anchor.lsi_first_fvg_only}")
        print(f"{'=' * 130}")

        # Run anchor baseline first
        anchor_m = run_single(df_5m, anchor, maps, df_1m, df_1s)
        total_runs += 1
        print(f"\n  ANCHOR: {anchor_m['trades']}tr  {anchor_m['win_rate']:.1%}WR  "
              f"{anchor_m['net_r']:+.1f}R  DD {anchor_m['max_dd_r']:.1f}R  "
              f"Calmar {anchor_m['calmar']:.2f}  Sharpe {anchor_m['sharpe']:.2f}  "
              f"NegYr {anchor_m['neg_years']}\n")

        anchor_results = {"anchor": anchor_m, "sweeps": {}}

        for dim_name, values in SWEEPS.items():
            print(f"  ── {dim_name} ({'×'.join(str(v) for v in values)}) ──")
            dim_results = []

            for val in values:
                # Build config with this override
                val_label = DOW_LABELS.get(val, str(val)) if dim_name == "excluded_days" else str(val)
                try:
                    if dim_name == "excluded_days":
                        cfg = dataclasses.replace(anchor, excluded_days=val)
                    elif dim_name.startswith("ny_"):
                        cfg = with_overrides(anchor, **{dim_name: val})
                    else:
                        cfg = dataclasses.replace(anchor, **{dim_name: val})
                except ValueError as e:
                    print(f"    {val_label:<12} SKIPPED — {e}")
                    dim_results.append({"value": val_label, "trades": 0, "win_rate": 0, "net_r": 0,
                                        "max_dd_r": 0, "calmar": -999, "sharpe": 0, "pf": 0,
                                        "avg_r": 0, "neg_years": 99, "r_by_year": {}, "calmar_delta": -999})
                    continue

                t1 = time.time()
                m = run_single(df_5m, cfg, maps, df_1m, df_1s)
                total_runs += 1
                elapsed = time.time() - t1

                # Delta from anchor
                calmar_delta = m["calmar"] - anchor_m["calmar"]
                marker = ""
                if calmar_delta > 0.3 and m["neg_years"] <= anchor_m["neg_years"]:
                    marker = " ◄ CANDIDATE"
                elif calmar_delta < -2.0:
                    marker = " ✗"

                print(
                    f"    {val_label:<12} {m['trades']:>4}tr  {m['win_rate']:>5.1%}WR  "
                    f"{m['net_r']:>+7.1f}R  DD {m['max_dd_r']:>6.1f}R  "
                    f"Calm {m['calmar']:>7.2f} ({calmar_delta:>+.2f})  "
                    f"Shrp {m['sharpe']:>5.2f}  NegYr {m['neg_years']}{marker}  [{elapsed:.1f}s]"
                )

                dim_results.append({
                    "value": val_label,
                    **m,
                    "calmar_delta": calmar_delta,
                })

            anchor_results["sweeps"][dim_name] = dim_results
            print()

        all_results[anchor_name] = anchor_results

    # ── Summary: best value per dimension per anchor ──────────────────────
    print(f"\n{'=' * 130}")
    print("SUMMARY — BEST VALUE PER DIMENSION (by Calmar, 0-neg-years preferred)")
    print(f"{'=' * 130}")

    for anchor_name in ANCHORS:
        ar = all_results[anchor_name]
        anchor_calm = ar["anchor"]["calmar"]
        print(f"\n  Anchor {anchor_name} (baseline Calmar {anchor_calm:.2f}):")

        for dim_name, dim_results in ar["sweeps"].items():
            # Prefer 0 neg years, then highest calmar
            best = max(dim_results, key=lambda r: (-(r["neg_years"]), r["calmar"]))
            delta = best["calmar"] - anchor_calm
            adopt = "ADOPT" if delta > 0.3 and best["neg_years"] <= ar["anchor"]["neg_years"] else ""
            print(
                f"    {dim_name:<25} best={best['value']:<12} "
                f"Calmar {best['calmar']:>7.2f} ({delta:>+.2f})  "
                f"NegYr {best['neg_years']}  {adopt}"
            )

    # ── Save ──────────────────────────────────────────────────────────────
    output_path = ROOT / "data" / "results" / "nq_ny_lsi_discovery_step2_sweeps.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def convert(obj):
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(output_path, "w") as f:
        json.dump(all_results, f, indent=2, default=convert)

    print(f"\nTotal runs: {total_runs}")
    print(f"Results saved to {output_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
