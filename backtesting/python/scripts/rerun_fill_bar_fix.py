#!/usr/bin/env python3
"""Re-run all 7 saved DB entries with corrected simulator (fill-bar fix).

The fill-bar fix includes the fill bar in exit scanning (SL/TP can hit on
the same bar as fill). Previous results skipped the fill bar entirely.

Old entries are deleted after new ones are saved.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.experiments import delete_backtest_run
from orb_backtest.results.export import results_to_dict, save_backtest_result
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
TAG = " [fill-bar fix]"

# Old DB entry IDs to delete
OLD_IDS = [
    "bt-es-asia-r5-final-24b408",
    "bt-gc-ny-cont-shorts-final-structural-7cf468",
    "bt-nq-asia-r4-final-7d15f0",
    "bt-nq-ny-r20-robust-anchor-02ff68",
    "bt-es-ldn-continuation-both-2016-2026-edc1e8",
    "bt-gc-ny-cont-longs-r2-final-wf-mode-a234c8",
]


def print_metrics(m, label):
    print(f"\n  [{label}]")
    print(f"  Trades: {m['total_trades']}")
    print(f"  Win Rate: {m['win_rate']:.1%}")
    print(f"  PF: {m['profit_factor']:.2f}")
    print(f"  Sharpe: {m['sharpe_ratio']:.3f}")
    print(f"  Net R: {m['total_r']:.1f}R")
    print(f"  Max DD: {m['max_drawdown_r']:.1f}R")
    print(f"  Calmar: {m['calmar_ratio']:.2f}")
    rby = m.get("r_by_year", {})
    if rby:
        neg = sum(1 for r in rby.values() if r < 0)
        print(f"  Neg years: {neg}")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")


# ── 1. ES Asia R5 Final ──────────────────────────────────────────────────────

def run_es_asia():
    sess = SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:10",
        entry_start="20:10", entry_end="03:00",
        flat_start="06:45", flat_end="07:00",
        stop_atr_pct=3.0, min_gap_atr_pct=0.5,
        max_gap_points=50.0, max_gap_atr_pct=0.0,
    )
    config = StrategyConfig(
        sessions=(sess,), instrument=ES, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
        rr=2.0, tp1_ratio=0.5, atr_length=5,
        name="ES Asia R5 Final" + TAG,
        notes="Re-run with fill-bar fix (exits checked on fill bar). Original: bt-es-asia-r5-final-24b408.",
    )

    df_5m = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")

    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, {3})

    m = compute_metrics(trades)
    print_metrics(m, "ES Asia R5 Final")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── 2. GC NY Cont Shorts Final (Structural) ──────────────────────────────────

def run_gc_shorts():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="15:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=2.5, min_gap_atr_pct=5.5,
        max_gap_points=25.0, max_gap_atr_pct=25.0,
    )
    config = StrategyConfig(
        rr=7.0, tp1_ratio=0.6, risk_usd=5000.0, atr_length=10,
        min_qty=1.0, qty_step=1.0, sessions=(sess,), instrument=GC,
        strategy="continuation", direction_filter="short",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=FOMC_DATES,
        name="GC NY Cont Shorts Final (Structural)" + TAG,
        notes="Re-run with fill-bar fix. Original: bt-gc-ny-cont-shorts-final-structural-7cf468.",
    )

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")

    trades = run_backtest(df, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    print_metrics(m, "GC NY Cont Shorts Final")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── 3. NQ Asia R4 Final ──────────────────────────────────────────────────────

def run_nq_asia():
    sess = SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:10",
        entry_start="20:10", entry_end="01:00",
        flat_start="00:00", flat_end="07:00",
        stop_atr_pct=3.7, min_gap_atr_pct=0.90,
        max_gap_points=0.0, max_gap_atr_pct=5.0,
    )
    config = StrategyConfig(
        sessions=(sess,), instrument=NQ, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
        rr=1.75, tp1_ratio=0.35, atr_length=5,
        name="NQ Asia R4 Final" + TAG,
        notes="Re-run with fill-bar fix. Original: bt-nq-asia-r4-final-7d15f0.",
    )

    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")

    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    trades = apply_dow_filter(trades, {3})

    m = compute_metrics(trades)
    print_metrics(m, "NQ Asia R4 Final")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── 4. NQ NY R20 Robust Anchor ───────────────────────────────────────────────

def run_nq_ny():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:50",
        entry_start="09:50", entry_end="15:30",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=8.75, min_gap_atr_pct=2.25,
        max_gap_points=100.0,
    )
    config = StrategyConfig(
        sessions=(sess,), instrument=NQ, strategy="continuation",
        use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
        rr=2.625, tp1_ratio=0.3, atr_length=12,
        name="NQ NY R20 Robust Anchor" + TAG,
        notes="Re-run with fill-bar fix. Original: bt-nq-ny-r20-robust-anchor-02ff68.",
    )

    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")

    trades = run_backtest(df_5m, config, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    print_metrics(m, "NQ NY R20 Robust Anchor")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── 5. ES LDN Continuation Both ──────────────────────────────────────────────

def run_es_ldn():
    sess = SessionConfig(
        name="LDN", orb_start="03:00", orb_end="03:10",
        entry_start="03:10", entry_end="08:25",
        flat_start="08:00", flat_end="08:25",
        stop_atr_pct=5.2, min_gap_atr_pct=1.25,
        max_gap_points=50.0,
    )
    config = StrategyConfig(
        rr=2.0, tp1_ratio=0.40, risk_usd=5000.0, atr_length=50,
        min_qty=1.0, qty_step=1.0, sessions=(sess,), instrument=ES,
        strategy="continuation", direction_filter="both",
        use_bar_magnifier=True,
        name="ES LDN Continuation Both 2016-2026" + TAG,
        notes="Re-run with fill-bar fix. Original: bt-es-ldn-continuation-both-2016-2026-edc1e8.",
    )

    df = load_5m_data("ES_5m.csv", start="2016-03-02", end="2026-02-18")
    df_1m = load_1m_for_5m("ES_5m.csv", start="2016-03-02", end="2026-02-18")
    df_1s = load_1s_for_5m("ES_5m.csv", start="2016-03-02", end="2026-02-18")

    trades = run_backtest(df, config, start_date="2016-03-02", df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    print_metrics(m, "ES LDN Continuation Both")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── 6. GC NY Cont Longs R2 Final (WF Mode) ───────────────────────────────────

def run_gc_longs():
    sess = SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:40",
        entry_start="09:40", entry_end="11:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=3.0, min_gap_atr_pct=3.5,
        max_gap_points=25.0, max_gap_atr_pct=30.0,
    )
    config = StrategyConfig(
        rr=4.5, tp1_ratio=0.5, risk_usd=5000.0, atr_length=10,
        min_qty=1.0, qty_step=1.0, sessions=(sess,), instrument=GC,
        strategy="continuation", direction_filter="long",
        use_bar_magnifier=True,
        half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        excluded_dates=("20241218",) + FOMC_DATES,
        name="GC NY Cont Longs R2 Final (WF Mode)" + TAG,
        notes="Re-run with fill-bar fix. Original: bt-gc-ny-cont-longs-r2-final-wf-mode-a234c8.",
    )

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")

    trades = run_backtest(df, config, start_date="2017-02-01", df_1m=df_1m, df_1s=df_1s)

    m = compute_metrics(trades)
    print_metrics(m, "GC NY Cont Longs R2 Final (WF Mode)")

    result = results_to_dict(trades, config, include_trades=True, include_equity_curve=True)
    result_id = save_backtest_result(result)
    print(f"  Saved: {result_id}")
    return result_id


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    t0 = time.time()
    print("=" * 70)
    print("  RE-RUNNING ALL SAVED ENTRIES WITH FILL-BAR FIX")
    print("  (exits now checked on fill bar — SL/TP can hit same bar as fill)")
    print("=" * 70)

    new_ids = []

    # Run all 6 standard entries
    runners = [
        ("1/6", run_es_asia),
        ("2/6", run_gc_shorts),
        ("3/6", run_nq_asia),
        ("4/6", run_nq_ny),
        ("5/6", run_es_ldn),
        ("6/6", run_gc_longs),
    ]

    for label, fn in runners:
        print(f"\n{'=' * 70}")
        print(f"  [{label}] Running {fn.__name__}...")
        print("=" * 70)
        t1 = time.time()
        rid = fn()
        new_ids.append(rid)
        print(f"  Done in {time.time() - t1:.1f}s")

    # Delete old entries
    print(f"\n{'=' * 70}")
    print("  DELETING OLD ENTRIES")
    print("=" * 70)
    for old_id in OLD_IDS:
        ok = delete_backtest_run(old_id)
        status = "deleted" if ok else "NOT FOUND"
        print(f"  {old_id}: {status}")

    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print("=" * 70)
    print(f"  New entries saved: {len(new_ids)}")
    for rid in new_ids:
        print(f"    {rid}")
    print(f"  Old entries deleted: {len(OLD_IDS)}")
    print(f"\n  NOTE: NQ+ES ASIA portfolio (bt-nqes.asia.cond-5b7473) must be")
    print(f"  re-run separately via: uv run python scripts/run_nq_es_asia_correlation.py --save")
    print(f"\n  Total time: {time.time() - t0:.1f}s")
