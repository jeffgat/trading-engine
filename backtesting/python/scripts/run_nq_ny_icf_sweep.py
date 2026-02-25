#!/usr/bin/env python3
"""NQ NY ORB — Impulse Close Filter (ICF) sweep on R20 anchor.

ICF was never tested for NQ NY across R16-R20. It's been tested on:
  - NQ Asia: beneficial at v3 anchor, not at R4
  - NQ LDN: adopted in R2, +0.64 Calmar delta

R20 anchor (converged, fine-tune winner):
  ORB: 09:30-09:50 (20m), entry until 15:30, flat 15:50
  stop=8.75%, min_gap=2.25%, max_gap=100pt
  rr=2.625, tp1=0.3, ATR=12, direction=both, continuation, 1s magnifier
  impulse_close_filter=False (current anchor)

Purpose: test ICF=OFF (baseline) vs ICF=ON, including directional breakdown.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2016-01-01"
DATA_YEARS = 10

ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",       # 20m ORB (stable)
    entry_start="09:50",
    entry_end="15:30",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=8.75,     # Fine-tune winner
    min_gap_atr_pct=2.25,  # Fine-tune winner
    max_gap_points=100.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="both",
    rr=2.625,              # Fine-tune winner
    tp1_ratio=0.3,         # Fine-tune winner
    atr_length=12,
    impulse_close_filter=False,
    name="NQ NY R20 ICF OFF",
)


def run_and_metric(df_5m, df_1m, df_1s, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    return trades, compute_metrics(trades)


HDR = (
    f"    {'#':>3} {'Variable':>20} {'Trades':>6} {'WR':>5} {'PF':>5} "
    f"{'Sharpe':>6} {'Net R':>7} {'R/yr':>6} {'MaxDD':>6} {'Calmar':>7}"
)


def print_header(title):
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")
    print(HDR)
    print(f"    {'─'*85}")


def print_row(i, label, m, is_base=False):
    marker = " <-- anchor" if is_base else ""
    r_yr = m["total_r"] / DATA_YEARS if m["total_trades"] > 0 else 0
    print(
        f"    {i:>3} {label:>20} {m['total_trades']:>6} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>5.2f} {m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_yr:>6.1f} {m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>7.2f}{marker}"
    )


def print_years(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"      R by year: {yr_str}")


def neg_year_set(m):
    if "r_by_year" not in m:
        return set()
    current_year = str(datetime.now().year)
    return {yr for yr, r in m["r_by_year"].items() if r < 0 and str(yr) != current_year}


def main():
    print("NQ NY ORB — Impulse Close Filter (ICF) sweep on R20 anchor")
    print("=" * 90)
    print(f"Anchor: dir=both, orb=20m, rr={ANCHOR.rr}, tp1={ANCHOR.tp1_ratio}, "
          f"stop={ANCHOR_SESSION.stop_atr_pct}%, gap={ANCHOR_SESSION.min_gap_atr_pct}%, "
          f"atr={ANCHOR.atr_length}, end={ANCHOR_SESSION.entry_end}, ICF=OFF")

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time() - t_start:.1f}s]")

    # ── 1. ICF SWEEP (both directions) ────────────────────────────────
    print_header("1. ICF SWEEP — direction=both")

    # ICF OFF (baseline / anchor)
    _, m_off = run_and_metric(df_5m, df_1m, df_1s, ANCHOR)
    print_row(1, "ICF=OFF", m_off, is_base=True)
    print_years(m_off)
    anchor_calmar = m_off["calmar_ratio"]
    anchor_neg = neg_year_set(m_off)
    print(f"      Negative years: {sorted(anchor_neg) if anchor_neg else 'none'}")

    # ICF ON
    config_on = replace(ANCHOR, impulse_close_filter=True, name="NQ NY R20 ICF ON")
    _, m_on = run_and_metric(df_5m, df_1m, df_1s, config_on)
    print_row(2, "ICF=ON", m_on)
    print_years(m_on)
    icf_neg = neg_year_set(m_on)
    print(f"      Negative years: {sorted(icf_neg) if icf_neg else 'none'}")

    icf_calmar_delta = m_on["calmar_ratio"] - anchor_calmar
    new_neg = icf_neg - anchor_neg
    print(f"\n      Calmar delta: {icf_calmar_delta:+.2f}")
    print(f"      New negative years: {sorted(new_neg) if new_neg else 'none'}")

    # ── 2. DIRECTIONAL BREAKDOWN ──────────────────────────────────────
    print_header("2. DIRECTIONAL BREAKDOWN — ICF OFF vs ON")

    dir_results = {}
    for direction in ["long", "short"]:
        for icf_val, icf_label in [(False, "OFF"), (True, "ON")]:
            label = f"{direction} ICF={icf_label}"
            config = replace(
                ANCHOR,
                direction_filter=direction,
                impulse_close_filter=icf_val,
                name=f"NQ NY R20 {label}",
            )
            _, m = run_and_metric(df_5m, df_1m, df_1s, config)
            idx = len(dir_results) + 1
            print_row(idx, label, m, is_base=(icf_label == "OFF"))
            print_years(m)
            dir_results[(direction, icf_label)] = m

    # Directional deltas
    print(f"\n    Directional Calmar deltas:")
    for direction in ["long", "short"]:
        off_cal = dir_results[(direction, "OFF")]["calmar_ratio"]
        on_cal = dir_results[(direction, "ON")]["calmar_ratio"]
        delta = on_cal - off_cal
        print(f"      {direction}: {off_cal:.2f} → {on_cal:.2f} (Δ = {delta:+.2f})")

    # ── 3. ADOPTION DECISION ──────────────────────────────────────────
    print(f"\n{'='*90}")
    print(f"  ADOPTION DECISION")
    print(f"{'='*90}")
    print(f"  ICF OFF (anchor) Calmar: {anchor_calmar:.2f}")
    print(f"  ICF ON Calmar:           {m_on['calmar_ratio']:.2f}")
    print(f"  Delta:                   {icf_calmar_delta:+.2f}")
    print(f"  Anchor neg years:        {sorted(anchor_neg) if anchor_neg else 'none'}")
    print(f"  ICF ON neg years:        {sorted(icf_neg) if icf_neg else 'none'}")
    print(f"  New neg years:           {sorted(new_neg) if new_neg else 'none'}")

    adopt = icf_calmar_delta > 0.3 and len(new_neg) == 0
    verdict = "YES — ADOPT ICF" if adopt else "NO — keep ICF=OFF"
    print(f"\n  Adopt ICF? {verdict}")
    print(f"  (Threshold: Calmar Δ > +0.3 AND no new negative full years)")

    if adopt:
        print(f"\n  ** ICF ADOPTED — all variable sweeps must be rerun as R21 **")
        print(f"  Update anchor: impulse_close_filter=True")
    else:
        print(f"\n  ** ICF NOT ADOPTED — R20 anchor unchanged, proceed to robust pipeline **")

    elapsed = time.time() - t_start
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
