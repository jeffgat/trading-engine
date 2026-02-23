#!/usr/bin/env python3
"""NQ Asia v3 — Round 13: Config variable broad sweep at new anchor.

Anchor (R12 best, 0 neg years):
  stop=3.7%, gap=0.90%, maxgap=5.0%, rr=1.75, tp1=0.35
  ATR 5, ORB 10m (entry_start=20:10), entry_end=23:00, no-Thursday
  → Calmar 14.82, 17.4 R/yr, DD -13.0R, Sharpe 1.964

Variables swept (one at a time, anchor held fixed for all others):
  A. ORB window (orb_end = entry_start): 20:05, 20:10*, 20:15, 20:20, 20:30
  B. entry_end:  21:00, 22:00, 23:00*, 00:00, 01:00, 02:00
  C. atr_length: 3, 5*, 7, 10, 14
  D. direction:  both*, long, short
  E. flat_start: 00:00, 01:00, 02:00, 03:00, 04:00, 06:45*
  F. max_gap_pts: 0*(disabled), 25, 50, 75, 100
  G. DOW excl (in addition to no-Thu): none*, +Mon, +Tue, +Wed, +Fri

  * = anchor value

Total: ~34 backtests. Sequential, ~3-5 min.
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
    flat_start="06:45",
    atr_length=5,
    rr=1.75,
    tp1_ratio=0.35,
    direction_filter="both",
)
ANCHOR_DOW_EXCL = {3}  # Thursday


def build_cfg(
    orb_end="20:10",
    entry_start="20:10",
    entry_end="23:00",
    flat_start="06:45",
    atr_length=5,
    rr=1.75,
    tp1_ratio=0.35,
    direction_filter="both",
):
    asia = replace(
        ASIA_SESSION,
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start=flat_start,
        stop_atr_pct=ANCHOR["stop_atr_pct"],
        min_gap_atr_pct=ANCHOR["min_gap_atr_pct"],
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=rr,
        tp1_ratio=tp1_ratio,
        atr_length=atr_length,
        direction_filter=direction_filter,
        use_bar_magnifier=True,
    )


def dow_gate(trades, excl_days):
    """excl_days: set of weekday ints (Mon=0 … Sun=6)"""
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
    f"{'Label':<22} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | NegFYr"
)
SEP = "-" * len(HDR)


def print_row(label, r, anchor_calmar=None):
    if r is None:
        print(f"{label:<22} | {'<too few trades>':>72}")
        return
    neg  = str(r["neg_detail"]) if r["neg_detail"] else "-"
    mark = " <-- anchor" if (
        anchor_calmar is not None and abs(r["calmar"] - anchor_calmar) < 0.01
    ) else ""
    print(
        f"{label:<22} | {r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | "
        f"{r['avg_annual']:>7.1f} | {r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | "
        f"{r['calmar']:>7.2f} | {r['r_per_trade']:>6.4f} | {neg}{mark}"
    )


def print_section(title):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")
    print(HDR)
    print(SEP)


def main():
    print("NQ Asia v3 — Round 13: Config Variable Broad Sweep")
    print(f"Anchor: stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5, ORB 10m, entry≤23:00, no-Thu")
    print(f"→ Calmar 14.82, 17.4 R/yr, DD -13.0R, Sharpe 1.964 (0 neg years)\n")

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]\n")

    done, total = 0, 34

    def run_and_print(label, cfg, excl_days=None):
        nonlocal done
        if excl_days is None:
            excl_days = ANCHOR_DOW_EXCL
        r = run_one(cfg, df, df_1m, excl_days)
        done += 1
        print(f"\r  running... {done}/{total}", end="", flush=True)
        print("\r", end="")
        return r

    # ── A. ORB window ────────────────────────────────────────────────────────
    print_section("A. ORB Window (orb_end = entry_start)")
    anchor_r_A = None
    orb_sweep = [("20:05 (5m)",  "20:05", "20:05"),
                 ("20:10 (10m)", "20:10", "20:10"),   # anchor
                 ("20:15 (15m)", "20:15", "20:15"),
                 ("20:20 (20m)", "20:20", "20:20"),
                 ("20:30 (30m)", "20:30", "20:30")]
    rows_A = []
    for label, orb_end, entry_start in orb_sweep:
        cfg = build_cfg(orb_end=orb_end, entry_start=entry_start)
        r   = run_and_print(label, cfg)
        rows_A.append((label, r))
        if "10m" in label:
            anchor_r_A = r["calmar"] if r else None
    for label, r in rows_A:
        print_row(label, r, anchor_r_A)

    # ── B. entry_end ─────────────────────────────────────────────────────────
    print_section("B. Entry End Time")
    anchor_r_B = None
    entry_sweep = [("21:00", "21:00"), ("22:00", "22:00"),
                   ("23:00", "23:00"),  # anchor
                   ("00:00", "00:00"), ("01:00", "01:00"), ("02:00", "02:00")]
    rows_B = []
    for label, entry_end in entry_sweep:
        cfg = build_cfg(entry_end=entry_end)
        r   = run_and_print(label, cfg)
        rows_B.append((label, r))
        if label == "23:00":
            anchor_r_B = r["calmar"] if r else None
    for label, r in rows_B:
        print_row(label, r, anchor_r_B)

    # ── C. ATR length ────────────────────────────────────────────────────────
    print_section("C. ATR Length")
    anchor_r_C = None
    atr_sweep = [3, 5, 7, 10, 14]
    rows_C = []
    for atr in atr_sweep:
        cfg = build_cfg(atr_length=atr)
        r   = run_and_print(f"atr={atr}", cfg)
        rows_C.append((f"atr={atr}", r))
        if atr == 5:
            anchor_r_C = r["calmar"] if r else None
    for label, r in rows_C:
        print_row(label, r, anchor_r_C)

    # ── D. Direction filter ──────────────────────────────────────────────────
    print_section("D. Direction Filter")
    anchor_r_D = None
    dir_sweep = [("both (longs+shorts)", "both"),
                 ("long only",           "long"),
                 ("short only",          "short")]
    rows_D = []
    for label, direction in dir_sweep:
        cfg = build_cfg(direction_filter=direction)
        r   = run_and_print(label, cfg)
        rows_D.append((label, r))
        if direction == "both":
            anchor_r_D = r["calmar"] if r else None
    for label, r in rows_D:
        print_row(label, r, anchor_r_D)

    # ── E. flat_start (how long to allow trades to run) ─────────────────────
    print_section("E. Flat Start (position close cutoff)")
    anchor_r_E = None
    flat_sweep = [("00:00", "00:00"), ("01:00", "01:00"), ("02:00", "02:00"),
                  ("03:00", "03:00"), ("04:00", "04:00"), ("06:45", "06:45")]
    rows_E = []
    for label, flat_start in flat_sweep:
        cfg = build_cfg(flat_start=flat_start)
        r   = run_and_print(label, cfg)
        rows_E.append((label, r))
        if label == "06:45":
            anchor_r_E = r["calmar"] if r else None
    for label, r in rows_E:
        print_row(label, r, anchor_r_E)

    # ── F. max_gap_points ────────────────────────────────────────────────────
    print_section("F. Max Gap Points (0 = no limit)")
    anchor_r_F = None
    pts_sweep = [(0, "0 (disabled)"), (25, "25"), (50, "50"), (75, "75"), (100, "100")]
    rows_F = []
    for pts, label in pts_sweep:
        cfg = build_cfg(max_gap_points=float(pts))
        r   = run_and_print(label, cfg)
        rows_F.append((label, r))
        if pts == 0:
            anchor_r_F = r["calmar"] if r else None
    for label, r in rows_F:
        print_row(label, r, anchor_r_F)

    # ── G. DOW exclusion (always keep no-Thursday) ───────────────────────────
    print_section("G. Day-of-Week Exclusion (Thu always excluded)")
    anchor_r_G = None
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 4: "Fri"}
    dow_sweep = [("Thu only (anchor)",   {3}),
                 ("+excl Mon",           {3, 0}),
                 ("+excl Tue",           {3, 1}),
                 ("+excl Wed",           {3, 2}),
                 ("+excl Fri",           {3, 4})]
    rows_G = []
    for label, excl in dow_sweep:
        cfg = build_cfg()
        r   = run_and_print(label, cfg, excl_days=excl)
        rows_G.append((label, r))
        if "anchor" in label:
            anchor_r_G = r["calmar"] if r else None
    for label, r in rows_G:
        print_row(label, r, anchor_r_G)

    print(f"\n{'='*70}")
    print(f"Total runtime: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}m)")
    print(f"\nAnchor summary: Calmar 14.82, 17.4 R/yr, DD -13.0R, Sharpe 1.964 (0 neg years)")
    print(f"v2 reference:   Calmar 8.66,   7.7 R/yr, DD -9.7R,  Sharpe 1.254")


if __name__ == "__main__":
    main()
