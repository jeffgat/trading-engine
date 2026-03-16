#!/usr/bin/env python3
"""FAST_V2 DOW Exclusion Comparison — With vs Without Skip Days.

Compares two variants over the last 2 years (2024-03-15 to 2026-03-15):
  A) No DOW exclusions (exec_configs.json as-is)
  B) With DOW exclusions (live production: NQ_NY skip Fri, NQ_Asia skip Tue)

Runs all 5 legs for each variant, merges trades, prints side-by-side metrics.
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.results.metrics import compute_metrics

START = "2024-03-15"
END = "2026-03-15"

# ── Shared leg configs (no DOW exclusions) ───────────────────────────────

NQ_NY_BASE = StrategyConfig(
    sessions=(SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=8.0, min_gap_atr_pct=2.25,
    ),),
    instrument=NQ, strategy="continuation",
    direction_filter="both", use_bar_magnifier=True,
    rr=2.5, tp1_ratio=0.3, atr_length=14, risk_usd=400.0,
)

NQ_ASIA_BASE = StrategyConfig(
    sessions=(SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_atr_pct=4.0, stop_orb_pct=150.0,
        min_gap_atr_pct=0.9, min_gap_orb_pct=15.0,
    ),),
    instrument=NQ, strategy="continuation",
    direction_filter="long", use_bar_magnifier=True,
    rr=5.0, tp1_ratio=0.25, atr_length=5, risk_usd=400.0,
    excluded_dates=("20241218",),
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
)

ES_ASIA = StrategyConfig(
    sessions=(SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:10",
        entry_start="20:10", entry_end="03:00",
        flat_start="06:45", flat_end="07:00",
        stop_atr_pct=2.5, min_gap_atr_pct=1.0,
    ),),
    instrument=ES, strategy="continuation",
    direction_filter="long", use_bar_magnifier=True,
    rr=1.75, tp1_ratio=0.3, atr_length=5, risk_usd=200.0,
    excluded_dates=("20241218",),
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
)

NQ_ASIA_LSI = StrategyConfig(
    sessions=(SessionConfig(
        name="ASIA", rth_start="20:00",
        entry_start="20:45", entry_end="22:00",
        flat_start="00:00", flat_end="01:00",
        stop_atr_pct=0.0, min_gap_atr_pct=1.75,
    ),),
    instrument=NQ, strategy="lsi",
    direction_filter="both", use_bar_magnifier=True,
    rr=1.75, tp1_ratio=0.7, atr_length=40, risk_usd=400.0,
    lsi_n_left=3, lsi_n_right=3,
    lsi_fvg_window_left=10, lsi_fvg_window_right=10,
    lsi_stop_mode="absolute", lsi_entry_mode="close",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
)

NQ_NY_LSI = StrategyConfig(
    sessions=(SessionConfig(
        name="NY", rth_start="09:30",
        entry_start="10:10", entry_end="14:30",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=0.0, min_gap_atr_pct=3.75,
    ),),
    instrument=NQ, strategy="lsi",
    direction_filter="both", use_bar_magnifier=True,
    rr=2.5, tp1_ratio=0.2, atr_length=10, risk_usd=400.0,
    lsi_n_left=5, lsi_n_right=60,
    lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),  # Wed, Thu — same in both variants
)

# ── Build two variants ───────────────────────────────────────────────────

VARIANT_A = {
    "label": "No DOW Skips",
    "legs": {
        "NQ_NY":       {"config": NQ_NY_BASE,   "data": "NQ"},
        "NQ_Asia":     {"config": NQ_ASIA_BASE,  "data": "NQ"},
        "ES_Asia":     {"config": ES_ASIA,       "data": "ES"},
        "NQ_Asia_LSI": {"config": NQ_ASIA_LSI,   "data": "NQ"},
        "NQ_NY_LSI":   {"config": NQ_NY_LSI,     "data": "NQ"},
    },
}

VARIANT_B = {
    "label": "With DOW Skips (Fri on NQ_NY, Tue on NQ_Asia)",
    "legs": {
        "NQ_NY":       {"config": replace(NQ_NY_BASE, excluded_days=(4,)),  "data": "NQ"},
        "NQ_Asia":     {"config": replace(NQ_ASIA_BASE, excluded_days=(1,)), "data": "NQ"},
        "ES_Asia":     {"config": ES_ASIA,       "data": "ES"},
        "NQ_Asia_LSI": {"config": NQ_ASIA_LSI,   "data": "NQ"},
        "NQ_NY_LSI":   {"config": NQ_NY_LSI,     "data": "NQ"},
    },
}


def run_variant(variant: dict, data_cache: dict) -> dict:
    """Run all legs, return {leg_name: filled_trades} and merged list."""
    per_leg = {}
    all_trades = []
    for leg_name, leg in variant["legs"].items():
        sym = leg["data"]
        cfg = leg["config"]
        df_5m, df_1m = data_cache[sym]
        trades = run_backtest(df_5m, cfg,
                              start_date=START, end_date=END, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        # Apply DOW exclusion (post-trade filter, same as production)
        if cfg.excluded_days:
            filled = apply_dow_filter(filled, set(cfg.excluded_days))
        per_leg[leg_name] = filled
        all_trades.extend(filled)
    all_trades.sort(key=lambda t: t.date)
    return {"per_leg": per_leg, "all": all_trades}


def print_metrics_comparison(label_a, metrics_a, label_b, metrics_b):
    """Side-by-side metrics table."""
    rows = [
        ("Trades",           "total_trades",     "d"),
        ("Win Rate",         "win_rate",         ".1%"),
        ("Net R",            "total_r",          ".1f"),
        ("Avg R",            "avg_r",            ".3f"),
        ("Sharpe",           "sharpe_ratio",     ".3f"),
        ("Sortino",          "sortino_ratio",    ".3f"),
        ("Calmar",           "calmar_ratio",     ".3f"),
        ("Profit Factor",    "profit_factor",    ".2f"),
        ("Max DD (R)",       "max_drawdown_r",   ".1f"),
        ("Max DD ($)",       "max_drawdown_usd", ",.0f"),
        ("Avg Win R",        "avg_win_r",        ".3f"),
        ("Avg Loss R",       "avg_loss_r",       ".3f"),
        ("Max Consec Wins",  "max_consecutive_wins",  "d"),
        ("Max Consec Losses","max_consecutive_losses", "d"),
    ]

    w = max(len(label_a), len(label_b), 20)
    print(f"\n  {'Metric':<22s}  {label_a:>{w}s}  {label_b:>{w}s}  {'Delta':>10s}")
    print(f"  {'-'*22}  {'-'*w}  {'-'*w}  {'-'*10}")

    for label, key, fmt in rows:
        va = metrics_a.get(key, 0)
        vb = metrics_b.get(key, 0)
        sa = f"{va:{fmt}}"
        sb = f"{vb:{fmt}}"

        # Delta
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            delta = vb - va
            if "%" in fmt:
                sd = f"{delta:+.1%}"
            elif "f" in fmt:
                sd = f"{delta:+.2f}"
            elif "d" in fmt:
                sd = f"{delta:+d}"
            else:
                sd = f"{delta:+,.0f}"
        else:
            sd = ""

        print(f"  {label:<22s}  {sa:>{w}s}  {sb:>{w}s}  {sd:>10s}")


def print_per_leg_comparison(result_a, result_b, variant_a_label, variant_b_label):
    """Per-leg trade count and R comparison."""
    print(f"\n  Per-Leg Breakdown:")
    print(f"  {'Leg':<16s}  {'Trades A':>9s}  {'Net R A':>8s}  "
          f"{'Trades B':>9s}  {'Net R B':>8s}  {'R Delta':>8s}")
    print(f"  {'-'*16}  {'-'*9}  {'-'*8}  {'-'*9}  {'-'*8}  {'-'*8}")

    all_legs = list(VARIANT_A["legs"].keys())
    for leg in all_legs:
        trades_a = result_a["per_leg"].get(leg, [])
        trades_b = result_b["per_leg"].get(leg, [])
        r_a = sum(t.r_multiple for t in trades_a)
        r_b = sum(t.r_multiple for t in trades_b)
        delta = r_b - r_a
        print(f"  {leg:<16s}  {len(trades_a):>9d}  {r_a:>8.1f}  "
              f"{len(trades_b):>9d}  {r_b:>8.1f}  {delta:>+8.1f}")


def main():
    t0 = time.time()

    print()
    print("=" * 72)
    print("  FAST_V2 DOW Exclusion Comparison")
    print(f"  Date range: {START} to {END}")
    print("=" * 72)
    print(f"\n  A: {VARIANT_A['label']}")
    print(f"  B: {VARIANT_B['label']}")

    # Load data
    print("\nLoading data...")
    data_cache = {}
    for sym in ("NQ", "ES"):
        df_5m = load_5m_data(f"{sym}_5m")
        df_1m = load_1m_for_5m(f"{sym}_5m")
        data_cache[sym] = (df_5m, df_1m)

    # Run variant A
    print(f"\nRunning variant A ({VARIANT_A['label']})...")
    result_a = run_variant(VARIANT_A, data_cache)
    metrics_a = compute_metrics(result_a["all"])
    print(f"  {len(result_a['all']):,} trades")

    # Run variant B
    print(f"\nRunning variant B ({VARIANT_B['label']})...")
    result_b = run_variant(VARIANT_B, data_cache)
    metrics_b = compute_metrics(result_b["all"])
    print(f"  {len(result_b['all']):,} trades")

    # Compare
    print_metrics_comparison("A: No Skips", metrics_a,
                             "B: With Skips", metrics_b)
    print_per_leg_comparison(result_a, result_b,
                             VARIANT_A["label"], VARIANT_B["label"])

    # Skipped-day analysis: what's the R on the excluded days?
    print("\n  Excluded-day P&L (what the skips remove):")
    # NQ_NY Fridays
    ny_fri = [t for t in result_a["per_leg"]["NQ_NY"]
              if _weekday(t.date) == 4]
    ny_fri_r = sum(t.r_multiple for t in ny_fri)
    print(f"    NQ_NY Fridays:   {len(ny_fri):>3d} trades, "
          f"Net R: {ny_fri_r:>+7.1f}, "
          f"WR: {_wr(ny_fri)}")

    # NQ_Asia Tuesdays
    asia_tue = [t for t in result_a["per_leg"]["NQ_Asia"]
                if _weekday(t.date) == 1]
    asia_tue_r = sum(t.r_multiple for t in asia_tue)
    print(f"    NQ_Asia Tuesdays: {len(asia_tue):>2d} trades, "
          f"Net R: {asia_tue_r:>+7.1f}, "
          f"WR: {_wr(asia_tue)}")

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s\n")


def _weekday(date_str: str) -> int:
    """0=Mon, 4=Fri."""
    from datetime import datetime
    return datetime.strptime(date_str, "%Y-%m-%d").weekday()


def _wr(trades: list) -> str:
    if not trades:
        return "N/A"
    wins = sum(1 for t in trades if t.r_multiple > 0)
    return f"{wins/len(trades):.1%}"


if __name__ == "__main__":
    main()
