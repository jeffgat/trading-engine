#!/usr/bin/env python3
"""NQ NY LSI Discovery — Step 1: Baseline sweep of all filter combinations.

Starting from the best previous candidate (NY LSI fvg_limit v2, Calmar 20.37)
with user overrides: RR=2.0, TP1=0.5.

Sweeps all combinations of the 4 LSI boolean filters:
  - lsi_first_fvg_only: [False, True]
  - lsi_clean_path: [False, True]
  - lsi_be_swing_n_left: [0, 5]   (0=off, 5=on)
  - lsi_cancel_on_swing: [False, True]  (only meaningful with fvg_limit + be_swing>0)

Cross with 2 entry modes:
  - "close" (market at inversion bar close)
  - "fvg_limit" (limit at FVG boundary)

Total: 16 filter combos × 2 entry modes = 32 configs.

Uses 1s magnifier for fill resolution.
Pre-holdout: 2016-01 to 2025-03-31 (holdout frozen at 2025-04-01).
"""

import dataclasses
import json
import sys
import time
from itertools import product
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Hold-out boundary ─────────────────────────────────────────────────────
HOLDOUT_START = "2025-04-01"
END_DATE = "2025-03-31"  # pre-holdout end

# ── Anchor: best previous candidate (NY LSI fvg_limit v2) with RR/TP1 overrides
NY_SESSION = SessionConfig(
    name="NY",
    rth_start="09:30",
    entry_start="09:35",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    min_gap_atr_pct=5.0,
)

ANCHOR = StrategyConfig(
    sessions=(NY_SESSION,),
    instrument=NQ,
    strategy="lsi",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=2.0,           # User override (was 3.0)
    tp1_ratio=0.5,    # User override (was 0.3)
    atr_length=10,
    lsi_n_left=8,
    lsi_n_right=60,
    lsi_fvg_window_left=20,
    lsi_fvg_window_right=5,
    lsi_stop_mode="absolute",
    lsi_entry_mode="fvg_limit",  # will be overridden per combo
    lsi_first_fvg_only=False,
    lsi_clean_path=False,
    lsi_be_swing_n_left=0,
    lsi_cancel_on_swing=False,
    excluded_days=(2, 3),  # Mon/Tue/Fri
)

# ── Filter combinations ───────────────────────────────────────────────────
FILTER_GRID = {
    "lsi_first_fvg_only": [False, True],
    "lsi_clean_path": [False, True],
    "lsi_be_swing_n_left": [0, 5],
    "lsi_cancel_on_swing": [False, True],
}

ENTRY_MODES = ["close", "fvg_limit"]


def build_configs() -> list[StrategyConfig]:
    """Generate all filter × entry mode combinations."""
    configs = []
    keys = list(FILTER_GRID.keys())
    values = list(FILTER_GRID.values())

    for entry_mode in ENTRY_MODES:
        for combo in product(*values):
            overrides = dict(zip(keys, combo))
            overrides["lsi_entry_mode"] = entry_mode

            # lsi_cancel_on_swing only meaningful with fvg_limit + be_swing>0
            if overrides["lsi_cancel_on_swing"] and (
                entry_mode != "fvg_limit" or overrides["lsi_be_swing_n_left"] == 0
            ):
                continue

            label_parts = [entry_mode]
            if overrides["lsi_first_fvg_only"]:
                label_parts.append("1stFVG")
            if overrides["lsi_clean_path"]:
                label_parts.append("clean")
            if overrides["lsi_be_swing_n_left"] > 0:
                label_parts.append(f"BE{overrides['lsi_be_swing_n_left']}")
            if overrides["lsi_cancel_on_swing"]:
                label_parts.append("cancelSw")

            name = f"NQ NY LSI RR2 TP0.5 {' '.join(label_parts)}"

            cfg = dataclasses.replace(ANCHOR, **overrides, name=name)
            configs.append(cfg)

    return configs


def config_label(cfg: StrategyConfig) -> str:
    parts = [cfg.lsi_entry_mode]
    if cfg.lsi_first_fvg_only:
        parts.append("1stFVG")
    if cfg.lsi_clean_path:
        parts.append("clean")
    if cfg.lsi_be_swing_n_left > 0:
        parts.append(f"BE{cfg.lsi_be_swing_n_left}")
    if cfg.lsi_cancel_on_swing:
        parts.append("cancelSw")
    return " ".join(parts) if len(parts) > 1 else parts[0]


def main():
    t0 = time.time()

    # ── Load data with 1s magnifier ───────────────────────────────────────
    print("Loading NQ data (5m + 1m + 1s)...")
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    print(f"  5m: {len(df_5m):,}")
    print(f"  1m: {len(df_1m):,}" if df_1m is not None else "  1m: not available")
    print(f"  1s: {len(df_1s):,}" if df_1s is not None else "  1s: not available")

    # Pre-build maps once for all configs
    print("Building bar maps (5m→1m→1s)...")
    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    print(f"  Maps built in {time.time() - t0:.1f}s")

    # ── Generate configs ──────────────────────────────────────────────────
    configs = build_configs()
    print(f"\n{len(configs)} filter combinations to test")
    print(f"Pre-holdout period: 2016 to {END_DATE}")
    print(f"Holdout frozen at: {HOLDOUT_START}")

    # ── Run backtests sequentially (small number of configs) ──────────────
    print(f"\nRunning {len(configs)} backtests...\n")

    rows = []
    for i, cfg in enumerate(configs):
        t1 = time.time()
        trades = run_backtest(
            df_5m, cfg,
            end_date=END_DATE,
            df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
        )
        elapsed = time.time() - t1
        m = compute_metrics(trades)

        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        from statistics import median
        med_stop_ticks = median(t.risk_points / NQ.min_tick for t in filled) if filled else 0

        label = config_label(cfg)
        row = {
            "label": label,
            "entry_mode": cfg.lsi_entry_mode,
            "first_fvg": cfg.lsi_first_fvg_only,
            "clean_path": cfg.lsi_clean_path,
            "be_swing": cfg.lsi_be_swing_n_left,
            "cancel_sw": cfg.lsi_cancel_on_swing,
            "trades": m["total_trades"],
            "win_rate": m["win_rate"],
            "net_r": m["total_r"],
            "max_dd_r": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"],
            "sharpe": m["sharpe_ratio"],
            "pf": m["profit_factor"],
            "avg_r": m["avg_r"],
            "r_per_yr": m.get("avg_annual_r", m["total_r"] / 9.25),  # ~9.25 years
            "med_stop_ticks": med_stop_ticks,
            "r_by_year": m.get("r_by_year", {}),
            "neg_years": sum(1 for v in m.get("r_by_year", {}).values() if v < 0),
        }
        rows.append(row)

        neg_yr_str = f" ({row['neg_years']} neg yr)" if row["neg_years"] > 0 else ""
        print(
            f"  [{i+1:>2}/{len(configs)}] {label:<30} "
            f"{m['total_trades']:>4}tr  {m['win_rate']:>5.1%}WR  "
            f"{m['total_r']:>+7.1f}R  DD {m['max_drawdown_r']:>6.1f}R  "
            f"Calm {m['calmar_ratio']:>6.2f}  Shrp {m['sharpe_ratio']:>5.2f}  "
            f"PF {m['profit_factor']:>4.2f}  "
            f"Med stop {med_stop_ticks:.0f}tk{neg_yr_str}  [{elapsed:.1f}s]"
        )

    # ── Sort and display ──────────────────────────────────────────────────
    rows_sorted = sorted(rows, key=lambda r: r["calmar"], reverse=True)

    print(f"\n{'=' * 140}")
    print("RESULTS RANKED BY CALMAR")
    print(f"{'=' * 140}")
    print(
        f"{'#':>3} {'Config':<30} {'Tr':>4} {'WR%':>6} {'NetR':>7} {'MaxDD':>7} "
        f"{'Calm':>7} {'Shrp':>6} {'PF':>5} {'R/yr':>6} {'MedSt':>6} {'NegYr':>5}"
    )
    print("-" * 140)

    for i, r in enumerate(rows_sorted):
        print(
            f"{i+1:>3} {r['label']:<30} {r['trades']:>4} {r['win_rate']:>5.1%} "
            f"{r['net_r']:>+7.1f} {r['max_dd_r']:>7.1f} {r['calmar']:>7.2f} "
            f"{r['sharpe']:>6.2f} {r['pf']:>5.2f} {r['r_per_yr']:>6.1f} "
            f"{r['med_stop_ticks']:>6.0f} {r['neg_years']:>5}"
        )

    # ── R by year for top 5 ───────────────────────────────────────────────
    print(f"\n{'=' * 140}")
    print("R BY YEAR — TOP 5 BY CALMAR")
    print(f"{'=' * 140}")

    for i, r in enumerate(rows_sorted[:5]):
        rby = r["r_by_year"]
        years_str = "  ".join(f"{yr}:{v:+.1f}" for yr, v in sorted(rby.items()))
        print(f"  #{i+1} {r['label']:<30} {years_str}")

    # ── Structurally alive check ──────────────────────────────────────────
    alive = [r for r in rows_sorted if r["trades"] >= 50 and r["neg_years"] <= 1 and r["calmar"] > 2.0]
    print(f"\nStructurally alive (>=50 trades, <=1 neg year, Calmar>2): {len(alive)}/{len(rows_sorted)}")

    for r in alive:
        print(f"  {r['label']:<30}  Calmar {r['calmar']:>6.2f}  {r['trades']} trades  {r['neg_years']} neg yr")

    # ── Save results ──────────────────────────────────────────────────────
    output_path = ROOT / "data" / "results" / "nq_ny_lsi_discovery_step1_baseline.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    save_data = {
        "info": {
            "description": "NQ NY LSI discovery step 1 — baseline filter sweep",
            "anchor": "NY LSI fvg_limit v2 (Calmar 20.37) with RR=2.0, TP1=0.5 overrides",
            "holdout_start": HOLDOUT_START,
            "end_date": END_DATE,
            "magnifier": "1s",
            "total_configs": len(configs),
            "structurally_alive": len(alive),
        },
        "results": [
            {k: v for k, v in r.items() if k != "r_by_year"}
            for r in rows_sorted
        ],
        "r_by_year": {r["label"]: r["r_by_year"] for r in rows_sorted},
    }

    def convert(obj):
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, tuple):
            return list(obj)
        raise TypeError(f"Not serializable: {type(obj)}")

    with open(output_path, "w") as f:
        json.dump(save_data, f, indent=2, default=convert)

    print(f"\nResults saved to {output_path}")
    print(f"Total time: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
