#!/usr/bin/env python3
"""RTY NY Continuation — Variable Sweeps Round 7 (fine-tune, 0.1 increments).

R7 anchor (fine-tune grid winner):
  stop=3.0%, rr=5.5, gap=1.0%, tp1=0.45, entry≤15:30
  direction=long, ATR=14, 15m ORB, flat=15:50
  1s bar magnifier

Fine-tune with 0.1 step increments around each winning value.
Adoption rule: Calmar Δ > +0.3 AND no NEW negative full years.
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig, with_overrides
from orb_backtest.data.instruments import RTY
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=1.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=5.5,                    # GRID WINNER
    tp1_ratio=0.45,            # GRID WINNER
    atr_length=14,
    impulse_close_filter=False,
    name="RTY NY R7 Anchor",
)

ANCHOR_DOW_EXCL = set()


def run_and_metric(df_5m, df_1m, df_1s, config, dow_excl=None):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    excl = dow_excl if dow_excl is not None else ANCHOR_DOW_EXCL
    if excl:
        trades = apply_dow_filter(trades, excl)
    return trades, compute_metrics(trades)


HDR = (
    f"    {'#':>3} {'Variable':>20} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7} {'NegYrs':>6}"
)


def fmt(idx, label, m):
    rby = m.get("r_by_year", {})
    full_years = {y: r for y, r in rby.items() if y not in ("2016", "2026")}
    neg_yrs = sum(1 for r in full_years.values() if r < 0)
    neg_list = ",".join(y for y, r in sorted(full_years.items()) if r < 0)
    n_years = max(len(full_years), 1)
    avg_annual = m["total_r"] / n_years
    calmar = avg_annual / abs(m["max_drawdown_r"]) if m["max_drawdown_r"] != 0 else 0
    return (
        f"    {idx:>3} {label:>20} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.3f} {m['total_r']:>7.1f} "
        f"{avg_annual:>6.1f} {m['max_drawdown_r']:>6.1f} {calmar:>7.2f} "
        f"{neg_yrs:>3} {neg_list}"
    )


def print_r_by_year(m, indent="      "):
    rby = m.get("r_by_year", {})
    for y in sorted(rby):
        flag = " <--" if rby[y] < 0 else ""
        print(f"{indent}{y}: {rby[y]:>8.1f}R{flag}")


def main():
    print("Loading data (including 1s)...")
    t0 = time.time()
    df = load_5m_data("RTY_5m.csv")
    df_1m = load_1m_for_5m("RTY_5m.csv")
    df_1s = load_1s_for_5m("RTY_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time()-t0:.1f}s")
    print()

    # ── Anchor ──
    print("=" * 100)
    print("  ANCHOR (R7: stop=3.0%, rr=5.5, gap=1.0%, tp1=0.45, entry≤15:30)")
    print("=" * 100)
    _, m_anchor = run_and_metric(df, df_1m, df_1s, ANCHOR)
    print(HDR)
    print(fmt(0, "ANCHOR", m_anchor))
    print()
    print("  R by year:")
    print_r_by_year(m_anchor)
    print()

    # ── 1. Stop ATR % (0.1 step, ≥3.0%) ──
    print("=" * 100)
    print("  SWEEP 1: Stop ATR % (0.1 step)")
    print("=" * 100)
    print(HDR)
    for i, s in enumerate([3.0, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 4.0, 4.5, 5.0, 5.5, 6.0], 1):
        cfg = with_overrides(ANCHOR, ny_stop_atr_pct=s)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"stop={s:.1f}%", m))
    print()

    # ── 2. R:R (0.1 step) ──
    print("=" * 100)
    print("  SWEEP 2: Risk-Reward Ratio (0.1 step)")
    print("=" * 100)
    print(HDR)
    for i, rr in enumerate([4.5, 4.6, 4.7, 4.8, 4.9, 5.0, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 6.0, 6.5], 1):
        cfg = with_overrides(ANCHOR, rr=rr)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"rr={rr:.1f}", m))
    print()

    # ── 3. Min Gap ATR % (0.1 step) ──
    print("=" * 100)
    print("  SWEEP 3: Min Gap ATR % (0.1 step)")
    print("=" * 100)
    print(HDR)
    for i, g in enumerate([0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5], 1):
        cfg = with_overrides(ANCHOR, ny_min_gap_atr_pct=g)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"gap={g:.1f}%", m))
    print()

    # ── 4. TP1 Ratio (0.05 step) ──
    print("=" * 100)
    print("  SWEEP 4: TP1 Ratio (0.05 step)")
    print("=" * 100)
    print(HDR)
    for i, tp in enumerate([0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65], 1):
        cfg = with_overrides(ANCHOR, tp1_ratio=tp)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"tp1={tp:.2f}", m))
    print()

    # ── 5. Entry End Time ──
    print("=" * 100)
    print("  SWEEP 5: Entry End Time")
    print("=" * 100)
    print(HDR)
    for i, ee in enumerate(["11:00", "12:00", "13:00", "13:30", "14:00", "14:30", "15:00", "15:15", "15:30"], 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"entry≤{ee}", m))
    print()

    # ── 6. ATR Length ──
    print("=" * 100)
    print("  SWEEP 6: ATR Length")
    print("=" * 100)
    print(HDR)
    for i, atr in enumerate([10, 12, 14, 16, 18, 20], 1):
        cfg = with_overrides(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"ATR={atr}", m))
    print()

    # ── 7. ORB Window ──
    print("=" * 100)
    print("  SWEEP 7: ORB Window")
    print("=" * 100)
    print(HDR)
    orb_windows = [
        ("10m", "09:30", "09:40", "09:40"),
        ("15m", "09:30", "09:45", "09:45"),
        ("20m", "09:30", "09:50", "09:50"),
    ]
    for i, (label, os, oe, es) in enumerate(orb_windows, 1):
        sess = replace(ANCHOR_SESSION, orb_start=os, orb_end=oe, entry_start=es)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"ORB {label}", m))
    print()

    # ── 8. DOW Exclusion ──
    print("=" * 100)
    print("  SWEEP 8: DOW Exclusion")
    print("=" * 100)
    trades_raw = run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    print(HDR)
    days = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    for i, (d, name) in enumerate(days.items(), 1):
        m = compute_metrics(apply_dow_filter(trades_raw, {d}))
        print(fmt(i, f"excl {name}", m))
    print()

    print("=" * 100)
    print("  R7 COMPLETE — Fine-tune sweeps done. Adopt and proceed to pipeline or grid R2.")
    print("=" * 100)


if __name__ == "__main__":
    main()
