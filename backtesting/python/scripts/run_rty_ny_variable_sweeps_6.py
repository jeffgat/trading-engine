#!/usr/bin/env python3
"""RTY NY Continuation — Variable Sweeps Round 6.

R6 anchor: Starting from R2 grid winner but with stop floor of 3.0%.
  stop=3.0% (min allowed), rr=6.0, gap=1.0%, tp1=0.6, entry≤15:30
  direction=long, ATR=14, 15m ORB, flat=15:50
  1s bar magnifier

User constraint: stop must be ≥ 3.0%. Re-sweep all dimensions to find
the best baseline before the fine-tune grid.

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
    entry_end="15:30",         # R2 grid winner
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,          # MIN ALLOWED (user constraint)
    min_gap_atr_pct=1.0,       # R2 grid winner
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=RTY,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="long",
    rr=6.0,                    # R2 grid winner
    tp1_ratio=0.6,             # R2 grid winner
    atr_length=14,
    impulse_close_filter=False,
    name="RTY NY R6 Anchor",
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
    print("  ANCHOR (R6: stop=3.0% floor, rr=6.0, gap=1.0%, tp1=0.6, entry≤15:30)")
    print("=" * 100)
    _, m_anchor = run_and_metric(df, df_1m, df_1s, ANCHOR)
    print(HDR)
    print(fmt(0, "ANCHOR", m_anchor))
    print()
    print("  R by year:")
    print_r_by_year(m_anchor)
    print()

    # ── 1. Stop ATR % (≥3.0% only) ──
    print("=" * 100)
    print("  SWEEP 1: Stop ATR % (floor=3.0%)")
    print("=" * 100)
    print(HDR)
    for i, s in enumerate([3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0, 10.0], 1):
        cfg = with_overrides(ANCHOR, ny_stop_atr_pct=s)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"stop={s}%", m))
    print()

    # ── 2. R:R ──
    print("=" * 100)
    print("  SWEEP 2: Risk-Reward Ratio")
    print("=" * 100)
    print(HDR)
    for i, rr in enumerate([3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0], 1):
        cfg = with_overrides(ANCHOR, rr=rr)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"rr={rr}", m))
    print()

    # ── 3. Min Gap ATR % ──
    print("=" * 100)
    print("  SWEEP 3: Min Gap ATR %")
    print("=" * 100)
    print(HDR)
    for i, g in enumerate([0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0], 1):
        cfg = with_overrides(ANCHOR, ny_min_gap_atr_pct=g)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"gap={g}%", m))
    print()

    # ── 4. TP1 Ratio ──
    print("=" * 100)
    print("  SWEEP 4: TP1 Ratio")
    print("=" * 100)
    print(HDR)
    for i, tp in enumerate([0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7], 1):
        cfg = with_overrides(ANCHOR, tp1_ratio=tp)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"tp1={tp}", m))
    print()

    # ── 5. Entry End Time ──
    print("=" * 100)
    print("  SWEEP 5: Entry End Time")
    print("=" * 100)
    print(HDR)
    for i, ee in enumerate(["11:00", "12:00", "13:00", "14:00", "15:00", "15:30"], 1):
        sess = replace(ANCHOR_SESSION, entry_end=ee)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"entry≤{ee}", m))
    print()

    # ── 6. ORB Window ──
    print("=" * 100)
    print("  SWEEP 6: ORB Window")
    print("=" * 100)
    print(HDR)
    orb_windows = [
        ("10m", "09:30", "09:40", "09:40"),
        ("15m", "09:30", "09:45", "09:45"),
        ("20m", "09:30", "09:50", "09:50"),
        ("30m", "09:30", "10:00", "10:00"),
    ]
    for i, (label, os, oe, es) in enumerate(orb_windows, 1):
        sess = replace(ANCHOR_SESSION, orb_start=os, orb_end=oe, entry_start=es)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"ORB {label}", m))
    print()

    # ── 7. ATR Length ──
    print("=" * 100)
    print("  SWEEP 7: ATR Length")
    print("=" * 100)
    print(HDR)
    for i, atr in enumerate([10, 12, 14, 16, 20, 30], 1):
        cfg = with_overrides(ANCHOR, atr_length=atr)
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"ATR={atr}", m))
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

    # ── 9. Flat Start ──
    print("=" * 100)
    print("  SWEEP 9: Flat Start Time")
    print("=" * 100)
    print(HDR)
    for i, fs in enumerate(["14:00", "14:30", "15:00", "15:30", "15:50"], 1):
        fe = "16:00" if fs >= "15:00" else f"{int(fs[:2])+1:02d}:00"
        sess = replace(ANCHOR_SESSION, flat_start=fs, flat_end=fe)
        cfg = replace(ANCHOR, sessions=(sess,))
        _, m = run_and_metric(df, df_1m, df_1s, cfg)
        print(fmt(i, f"flat={fs}", m))
    print()

    print("=" * 100)
    print("  R6 COMPLETE — Adopt changes, then fine-tune grid with 1s magnifier.")
    print("=" * 100)


if __name__ == "__main__":
    main()
