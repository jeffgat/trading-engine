#!/usr/bin/env python3
"""Compare ES ORB candidates: ungated vs regime-gated on holdout.

Runs all 8 pipeline candidates (NY-A/B/C, Asia-A/B/C, LDN-A/B) on
pre-holdout + holdout with and without medium-vol avoidance gate.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.regime_research import (
    REGIME_RESEARCH_HOLDOUT_START,
    REGIME_RESEARCH_HOLDOUT_END,
    build_extended_regime_calendar,
    _regime_lookup,
    _filled_trades,
)
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
HOLDOUT_END = REGIME_RESEARCH_HOLDOUT_END
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

# ── 8 candidates (from run_es_orb_discovery_pipeline.py) ──

CANDIDATES = {
    "NY-A": StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:15",
            entry_start="10:15", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="both", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES NY-A 45m ATR8 RR3.5 TP0.3 both"),
    "NY-B": StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:30",
            entry_start="10:30", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=5.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES NY-B 60m ATR5 RR3.5 TP0.3 long"),
    "NY-C": StrategyConfig(
        sessions=(SessionConfig(name="NY", orb_start="09:30", orb_end="10:30",
            entry_start="10:30", entry_end="12:00", flat_start="15:50", flat_end="16:00",
            stop_atr_pct=8.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.5, atr_length=14,
        name="ES NY-C 60m ATR8 RR2.5 TP0.5 long"),
    "Asia-A": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="21:00",
            entry_start="21:00", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_orb_pct=100.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=2.5, tp1_ratio=0.4, atr_length=14,
        name="ES Asia-A 60m ORB100 RR2.5 TP0.4 long"),
    "Asia-B": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="20:15",
            entry_start="20:15", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.6, atr_length=14,
        name="ES Asia-B 15m ATR12 RR3.0 TP0.6 long"),
    "Asia-C": StrategyConfig(
        sessions=(SessionConfig(name="Asia", orb_start="20:00", orb_end="21:00",
            entry_start="21:00", entry_end="23:15", flat_start="04:00", flat_end="07:00",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="long", rr=3.0, tp1_ratio=0.4, atr_length=14,
        name="ES Asia-C 60m ATR15 RR3.0 TP0.4 long"),
    "LDN-A": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=15.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="short", rr=3.5, tp1_ratio=0.3, atr_length=14,
        name="ES LDN-A 45m ATR15 RR3.5 TP0.3 short"),
    "LDN-B": StrategyConfig(
        sessions=(SessionConfig(name="LDN", orb_start="03:00", orb_end="03:45",
            entry_start="03:45", entry_end="07:00", flat_start="08:20", flat_end="08:25",
            stop_atr_pct=12.0, min_gap_atr_pct=1.0),),
        instrument=ES, strategy="continuation", use_bar_magnifier=False,
        risk_usd=5000.0, direction_filter="short", rr=3.5, tp1_ratio=0.4, atr_length=14,
        name="ES LDN-B 45m ATR12 RR3.5 TP0.4 short"),
}

# Original gate status from pipeline
ORIG_GATED = {
    "NY-A": True, "NY-B": False, "NY-C": True,
    "Asia-A": True, "Asia-B": True, "Asia-C": True,
    "LDN-A": True, "LDN-B": True,
}


def make_avoidance_gate(regime_calendar):
    lookup = _regime_lookup(regime_calendar, "combined_regime")
    def gate(trades):
        return [t for t in trades if t.exit_type == EXIT_NO_FILL
                or lookup.get(t.date) not in AVOID_BUCKETS]
    return gate


def print_section(title, df_5m, gate_fn, end_date, start_filter=None):
    print(f"\n{'=' * 80}")
    print(title)
    print(f"{'=' * 80}")
    print(f"\n  {'Name':>8} | {'--- Ungated ---':^30} | {'--- Gated ---':^30} | {'Orig':>4}")
    print(f"  {'':>8} | {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} | {'Tr':>4} {'Net R':>7} {'Cal':>6} {'Shp':>5} {'DD':>6} | {'Gate':>4}")
    print(f"  {'─' * 85}")

    results = {}
    for name, config in CANDIDATES.items():
        t1 = time.time()
        trades = run_backtest(df_5m, config, end_date=end_date)
        if start_filter:
            trades = [t for t in trades if t.date >= start_filter]

        filled_raw = _filled_trades(trades)
        m_raw = compute_metrics(trades) if filled_raw else {}

        gated_trades = gate_fn(trades)
        filled_g = _filled_trades(gated_trades)
        m_gated = compute_metrics(gated_trades) if filled_g else {}

        results[name] = {
            "raw": {"n": len(filled_raw), **m_raw},
            "gated": {"n": len(filled_g), **m_gated},
        }

        raw, gated = results[name]["raw"], results[name]["gated"]
        print(f"  {name:>8} | {raw['n']:4} {raw.get('total_r',0) or 0:+7.1f} "
              f"{raw.get('calmar_ratio',0) or 0:6.2f} {raw.get('sharpe_ratio',0) or 0:5.2f} "
              f"{raw.get('max_drawdown_r',0) or 0:+6.1f} | "
              f"{gated['n']:4} {gated.get('total_r',0) or 0:+7.1f} "
              f"{gated.get('calmar_ratio',0) or 0:6.2f} {gated.get('sharpe_ratio',0) or 0:5.2f} "
              f"{gated.get('max_drawdown_r',0) or 0:+6.1f} | "
              f"{'Y' if ORIG_GATED[name] else 'N':>4}  [{time.time()-t1:.0f}s]")

    return results


def main():
    t0 = time.time()
    print("ES ORB — Regime Gate Comparison (all 8 candidates)")
    print("=" * 80)
    print(f"Avoid buckets: {AVOID_BUCKETS}")
    print(f"Pre-holdout: start → {HOLDOUT_START}")
    print(f"Holdout: {HOLDOUT_START} → {HOLDOUT_END}")

    print("\nLoading ES data (5m only)...", flush=True)
    df_5m = load_5m_data(ES.data_file)
    print(f"  5m: {len(df_5m):,} bars [{time.time() - t0:.1f}s]")

    print("Building regime calendar...", flush=True)
    regime_cal = build_extended_regime_calendar(df_5m)
    gate_fn = make_avoidance_gate(regime_cal)

    pre_results = print_section("PRE-HOLDOUT (training data)", df_5m, gate_fn, end_date=HOLDOUT_START)
    ho_results = print_section("HOLDOUT", df_5m, gate_fn, end_date=HOLDOUT_END, start_filter=HOLDOUT_START)

    # Delta summary
    print(f"\n{'=' * 80}")
    print("GATE IMPACT — Holdout Δ(gated − ungated)")
    print(f"{'=' * 80}")
    print(f"\n  {'Name':>8} | {'ΔTr':>4} {'ΔNet R':>7} {'ΔCal':>7} {'ΔShp':>6} {'ΔDD':>7} | {'Helps?':>6}")
    print(f"  {'─' * 55}")

    for name in CANDIDATES:
        raw = ho_results[name]["raw"]
        gated = ho_results[name]["gated"]
        d_tr = gated["n"] - raw["n"]
        d_r = (gated.get("total_r", 0) or 0) - (raw.get("total_r", 0) or 0)
        d_cal = (gated.get("calmar_ratio", 0) or 0) - (raw.get("calmar_ratio", 0) or 0)
        d_shp = (gated.get("sharpe_ratio", 0) or 0) - (raw.get("sharpe_ratio", 0) or 0)
        d_dd = (gated.get("max_drawdown_r", 0) or 0) - (raw.get("max_drawdown_r", 0) or 0)
        helps = "YES" if d_cal > 0 else "no"
        print(f"  {name:>8} | {d_tr:+4} {d_r:+7.1f} {d_cal:+7.2f} {d_shp:+6.2f} {d_dd:+7.1f} | {helps:>6}")

    print(f"\nTotal elapsed: {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
