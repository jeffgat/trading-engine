#!/usr/bin/env python3
"""NQ Asia v3 — Round 14: Fine sweep on flat_start, entry_end, and DOW stacking.

R13 key findings at anchor (stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5,
ORB 10m, entry≤23:00, no-Thursday):
  - flat_start=00:00 (midnight close): Calmar 14.82 → 20.14, DD -13.0R → -10.1R  (MAJOR)
  - +excl Tue (no-Thu + no-Tue):       Calmar 14.82 → 16.98, DD -13.0R → -9.1R
  - entry_end=00:00 slightly extends R/yr but lowers Calmar slightly vs 23:00

Sections:
  A. flat_start fine sweep: 22:00 → 02:00 in 30-min steps
  B. flat_start=00:00 + excl-Tue stack
  C. entry_end fine sweep: 22:00 → 01:00 in 30-min steps (two variants: base + flat_start=00:00)
  D. Stacked best combos: find the optimum

Total: ~35 backtests. Sequential, ~3-4 min.
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import ASIA_SESSION, default_config, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.data.instruments import NQ
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
FULL_YEARS = [str(y) for y in range(2015, 2026)]

# ── Anchor ──────────────────────────────────────────────────────────────────
ANCHOR = dict(
    stop_atr_pct=3.7,
    min_gap_atr_pct=0.90,
    orb_end="20:10",
    entry_start="20:10",
    entry_end="23:00",
    flat_start="06:45",   # R13 anchor — best after flat_start sweep is 00:00
    atr_length=5,
    rr=1.75,
    tp1_ratio=0.35,
    direction_filter="both",
)
ANCHOR_EXCL = {3}        # no-Thursday
TUE_EXCL    = {3, 1}     # no-Thursday + no-Tuesday


def build_cfg(
    entry_end="23:00",
    flat_start="06:45",
    direction_filter="both",
):
    asia = replace(
        ASIA_SESSION,
        orb_end=ANCHOR["orb_end"],
        entry_start=ANCHOR["entry_start"],
        entry_end=entry_end,
        flat_start=flat_start,
        stop_atr_pct=ANCHOR["stop_atr_pct"],
        min_gap_atr_pct=ANCHOR["min_gap_atr_pct"],
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=ANCHOR["rr"],
        tp1_ratio=ANCHOR["tp1_ratio"],
        atr_length=ANCHOR["atr_length"],
        direction_filter=direction_filter,
        use_bar_magnifier=True,
    )


def dow_gate(trades, excl_days):
    return [t for t in trades if pd.Timestamp(t.date).dayofweek not in excl_days]


def run_one(cfg, df, df_1m, excl_days):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m)
    trades = dow_gate(trades, excl_days)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if len(filled) < 10:
        return None
    m = compute_metrics(trades)
    r_by_year   = m.get("r_by_year", {})
    full_year_r = [r for yr, r in r_by_year.items() if yr in FULL_YEARS]
    avg_annual  = round(sum(full_year_r) / len(full_year_r), 1) if full_year_r else 0
    neg_full    = {yr: round(r, 1) for yr, r in r_by_year.items()
                   if r < 0 and yr in FULL_YEARS}
    return {
        "trades":      m["total_trades"],
        "wr":          m["win_rate"],
        "net_r":       round(m["total_r"], 1),
        "avg_annual":  avg_annual,
        "max_dd_r":    round(m["max_drawdown_r"], 1),
        "sharpe":      round(m["sharpe_ratio"], 3),
        "calmar":      round(m.get("calmar_ratio", 0), 2),
        "r_per_trade": round(m["avg_r"], 4),
        "neg_full":    len(neg_full),
        "neg_detail":  neg_full,
    }


HDR = (
    f"{'Label':<30} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | NegFYr"
)
SEP = "-" * len(HDR)


def print_row(label, r, mark=""):
    if r is None:
        print(f"{label:<30} | {'<too few trades>':>72}")
        return
    neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
    print(
        f"{label:<30} | {r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | "
        f"{r['avg_annual']:>7.1f} | {r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | "
        f"{r['calmar']:>7.2f} | {r['r_per_trade']:>6.4f} | {neg}{mark}"
    )


def print_section(title):
    print(f"\n{'='*75}")
    print(f"  {title}")
    print(f"{'='*75}")
    print(HDR)
    print(SEP)


def main():
    print("NQ Asia v3 — Round 14: Fine Sweep on flat_start, entry_end, DOW stack")
    print("Anchor: stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5, ORB 10m, no-Thu")
    print("  flat_start=06:45 → 00:00 improved Calmar 14.82→20.14 (R13)")
    print("  +excl Tue improved Calmar 14.82→16.98 (R13)\n")

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]\n")

    done = 0

    def run_p(label, cfg, excl=None, mark=""):
        nonlocal done
        if excl is None:
            excl = ANCHOR_EXCL
        r = run_one(cfg, df, df_1m, excl)
        done += 1
        print(f"\r  running {done}...", end="", flush=True)
        print("\r", end="")
        return label, r, mark

    # ── A. flat_start fine sweep (no-Thu, entry_end=23:00) ──────────────────
    print_section("A. flat_start Fine Sweep (no-Thu, entry_end=23:00)")
    flat_times = ["22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00", "01:30", "02:00"]
    rows_A = []
    for ft in flat_times:
        mark = " <-- R13 anchor" if ft == "06:45" else (
               " <-- R13 best"   if ft == "00:00" else "")
        cfg = build_cfg(flat_start=ft)
        rows_A.append(run_p(f"flat_start={ft}", cfg, mark=mark))
    # also include original anchor for reference
    cfg = build_cfg(flat_start="06:45")
    rows_A.append(run_p("flat_start=06:45 (orig)", cfg, mark=" <-- orig anchor"))
    for label, r, mark in rows_A:
        print_row(label, r, mark)

    # ── B. +excl Tue sweep across flat_start values ──────────────────────────
    print_section("B. +excl Tue stack: flat_start sweep (no-Thu + no-Tue)")
    rows_B = []
    for ft in flat_times:
        cfg = build_cfg(flat_start=ft)
        mark = " <-- R13 best excl-Tue" if ft == "06:45" else ""
        rows_B.append(run_p(f"flat={ft} +excl-Tue", cfg, excl=TUE_EXCL, mark=mark))
    for label, r, mark in rows_B:
        print_row(label, r, mark)

    # ── C. entry_end fine sweep (two variants) ──────────────────────────────
    entry_times = ["22:00", "22:30", "23:00", "23:30", "00:00", "00:30", "01:00"]

    print_section("C1. entry_end Fine Sweep — flat_start=06:45 (baseline, no-Thu)")
    rows_C1 = []
    for et in entry_times:
        cfg  = build_cfg(entry_end=et, flat_start="06:45")
        mark = " <-- anchor" if et == "23:00" else ""
        rows_C1.append(run_p(f"entry_end={et}", cfg, mark=mark))
    for label, r, mark in rows_C1:
        print_row(label, r, mark)

    print_section("C2. entry_end Fine Sweep — flat_start=00:00 (no-Thu)")
    rows_C2 = []
    for et in entry_times:
        cfg  = build_cfg(entry_end=et, flat_start="00:00")
        rows_C2.append(run_p(f"entry_end={et}", cfg))
    for label, r, mark in rows_C2:
        print_row(label, r, mark)

    # ── D. Stacked best: flat_start=00:00 × entry_end × excl-Tue ───────────
    print_section("D. Stacked Best Combinations (flat_start=00:00 × entry_end × DOW)")

    # Best flat_start from A + excl Tue (from B)
    best_flat = "00:00"   # or whatever emerges from A — we'll hard-code to 00:00 as the known best
    # Try best entry_end candidates with/without excl-Tue at flat_start=00:00
    stacks = [
        ("flat=00:00 + ee=23:00 + no-Tue",  "23:00", "00:00", TUE_EXCL),
        ("flat=00:00 + ee=23:30 + no-Tue",  "23:30", "00:00", TUE_EXCL),
        ("flat=00:00 + ee=00:00 + no-Tue",  "00:00", "00:00", TUE_EXCL),
        ("flat=00:00 + ee=23:00 + Thu-only", "23:00", "00:00", ANCHOR_EXCL),
        ("flat=00:00 + ee=23:30 + Thu-only", "23:30", "00:00", ANCHOR_EXCL),
        ("flat=00:00 + ee=00:00 + Thu-only", "00:00", "00:00", ANCHOR_EXCL),
        ("R13 anchor (ref)",                 "23:00", "06:45", ANCHOR_EXCL),
    ]
    rows_D = []
    for label, ee, fs, excl in stacks:
        cfg = build_cfg(entry_end=ee, flat_start=fs)
        rows_D.append(run_p(label, cfg, excl=excl))
    for label, r, mark in rows_D:
        print_row(label, r, mark)

    # Year-by-year for best stacked config
    print(f"\n--- Year-by-year: Top stacked configs ---")
    stacked_results = [(label, r) for label, r, _ in rows_D if r is not None]
    stacked_results.sort(key=lambda x: x[1]["calmar"], reverse=True)
    for label, r in stacked_results[:3]:
        print(f"\n  {label}")
        print(f"  Calmar={r['calmar']}, R/yr={r['avg_annual']}, DD={r['max_dd_r']}R, Sharpe={r['sharpe']}")
        # re-run to get year breakdown (compute_metrics already called, but we didn't store r_by_year)
        # We'll just print what we have
        neg = str(r["neg_detail"]) if r["neg_detail"] else "all positive"
        print(f"  Neg years: {neg}")

    print(f"\n{'='*75}")
    print(f"Total runtime: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}m)")
    print(f"\nR13 anchor:     Calmar 14.82, 17.4 R/yr, DD -13.0R, Sharpe 1.964 (flat=06:45, no-Thu)")
    print(f"R13 flat=00:00: Calmar 20.14, 18.3 R/yr, DD -10.1R, Sharpe 2.123 (flat=00:00, no-Thu)")
    print(f"R13 excl-Tue:   Calmar 16.98, 13.8 R/yr, DD -9.1R,  Sharpe 2.064 (flat=06:45, no-Thu-Tue)")
    print(f"v2 reference:   Calmar 8.66,   7.7 R/yr, DD -9.7R,  Sharpe 1.254")


if __name__ == "__main__":
    main()
