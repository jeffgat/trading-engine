#!/usr/bin/env python3
"""NQ Asia v3 — Round 16: Config variable re-validation at flat_start=00:00 anchor.

R13 swept config variables at flat_start=06:45. Now that flat_start=00:00 is established,
the structural change (midnight close removes overnight runners) may shift optimal values for:
  - ORB window: overnight hold removed, could change optimal ORB
  - ATR length: exit-independent, likely stable — confirm
  - Direction: flat=00:00 shortens short-trade runtime, may change direction balance
  - DOW excl: Mon/Wed/Fri not tested at flat=00:00 (Tue already confirmed non-additive in R14)

Already confirmed at flat=00:00 (don't re-test):
  - entry_end=23:00  (R14 Section C2)
  - excl-Tue doesn't help (R14 Section B)
  - max_gap_points: non-binding (R13)

Anchor (R15 confirmed):
  stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35
  ATR 5, ORB 10m, entry_end=23:00, flat_start=00:00, no-Thursday
  → Calmar 20.14, 18.3 R/yr, DD -10.1R, Sharpe 2.123 (0 neg years)

Sections:
  A. ORB window:  20:05, 20:10*, 20:15, 20:20, 20:30
  B. ATR length:  3, 5*, 7, 10, 14
  C. Direction:   both*, long, short
  D. DOW excl (beyond no-Thu): +Mon, +Wed, +Fri  (Tue already NO in R14)

Total: ~16 backtests. ~2-3 min.
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

ANCHOR_EXCL = {3}  # no-Thursday


def build_cfg(
    orb_end="20:10",
    entry_start="20:10",
    atr_length=5,
    direction_filter="both",
):
    asia = replace(
        ASIA_SESSION,
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end="23:00",
        flat_start="00:00",
        stop_atr_pct=3.7,
        min_gap_atr_pct=0.90,
    )
    cfg = default_config(NQ)
    return with_overrides(
        cfg,
        sessions=(asia,),
        rr=1.75,
        tp1_ratio=0.35,
        atr_length=atr_length,
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
    f"{'Label':<26} | {'Trades':>6} | {'WR':>6} | {'Net R':>7} | {'Avg/Yr':>7} | "
    f"{'DD R':>6} | {'Sharpe':>7} | {'Calmar':>7} | {'R/trd':>6} | NegFYr"
)
SEP = "-" * len(HDR)


def print_row(label, r, mark=""):
    if r is None:
        print(f"{label:<26} | {'<too few trades>':>72}")
        return
    neg = str(r["neg_detail"]) if r["neg_detail"] else "-"
    print(
        f"{label:<26} | {r['trades']:>6} | {r['wr']:>5.1%} | {r['net_r']:>7.1f} | "
        f"{r['avg_annual']:>7.1f} | {r['max_dd_r']:>6.1f} | {r['sharpe']:>7.3f} | "
        f"{r['calmar']:>7.2f} | {r['r_per_trade']:>6.4f} | {neg}{mark}"
    )


def section(title):
    print(f"\n{'='*72}")
    print(f"  {title}")
    print(f"{'='*72}")
    print(HDR)
    print(SEP)


def main():
    print("NQ Asia v3 — Round 16: Config Re-validation at flat_start=00:00")
    print("Anchor: stop=3.7%, gap=0.90%, maxgap=5%, rr=1.75, tp1=0.35, ATR 5, ORB 10m,")
    print("        entry≤23:00, flat_start=00:00, no-Thu → Calmar 20.14, DD -10.1R\n")

    t0 = time.time()
    print("Loading data...", flush=True)
    df    = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  {len(df):,} 5m | {len(df_1m):,} 1m [{time.time()-t0:.1f}s]\n")

    done = 0

    def run_p(label, cfg, excl=None, mark=""):
        nonlocal done
        r = run_one(cfg, df, df_1m, excl if excl is not None else ANCHOR_EXCL)
        done += 1
        print(f"\r  running {done}...", end="", flush=True)
        print("\r", end="")
        return label, r, mark

    # ── A. ORB window ────────────────────────────────────────────────────────
    section("A. ORB Window (orb_end = entry_start)  [flat_start=00:00]")
    rows = []
    for label, orb_end in [("20:05 (5m)",  "20:05"),
                            ("20:10 (10m)", "20:10"),
                            ("20:15 (15m)", "20:15"),
                            ("20:20 (20m)", "20:20"),
                            ("20:30 (30m)", "20:30")]:
        cfg = build_cfg(orb_end=orb_end, entry_start=orb_end)
        mark = " <-- anchor" if "10m" in label else ""
        rows.append(run_p(label, cfg, mark=mark))
    for label, r, mark in rows:
        print_row(label, r, mark)

    # ── B. ATR length ────────────────────────────────────────────────────────
    section("B. ATR Length  [flat_start=00:00]")
    rows = []
    for atr in [3, 5, 7, 10, 14]:
        cfg  = build_cfg(atr_length=atr)
        mark = " <-- anchor" if atr == 5 else ""
        rows.append(run_p(f"atr={atr}", cfg, mark=mark))
    for label, r, mark in rows:
        print_row(label, r, mark)

    # ── C. Direction ─────────────────────────────────────────────────────────
    section("C. Direction Filter  [flat_start=00:00]")
    rows = []
    for label, direction in [("both (anchor)", "both"),
                              ("long only",     "long"),
                              ("short only",    "short")]:
        cfg  = build_cfg(direction_filter=direction)
        mark = " <-- anchor" if direction == "both" else ""
        rows.append(run_p(label, cfg, mark=mark))
    for label, r, mark in rows:
        print_row(label, r, mark)

    # ── D. DOW exclusion (Mon/Wed/Fri — Tue already tested NO in R14) ────────
    section("D. Additional DOW Exclusion  [flat_start=00:00, Tue already NO]")
    rows = []
    dow_tests = [
        ("Thu only (anchor)",    {3}),
        ("+excl Mon",            {3, 0}),
        ("+excl Wed",            {3, 2}),
        ("+excl Fri",            {3, 4}),
        ("+excl Mon+Wed",        {3, 0, 2}),
        ("+excl Mon+Fri",        {3, 0, 4}),
    ]
    for label, excl in dow_tests:
        cfg  = build_cfg()
        mark = " <-- anchor" if excl == {3} else ""
        rows.append(run_p(label, cfg, excl=excl, mark=mark))
    for label, r, mark in rows:
        print_row(label, r, mark)

    print(f"\n{'='*72}")
    print(f"Total runtime: {time.time()-t0:.0f}s ({(time.time()-t0)/60:.1f}m)")
    print(f"\nAnchor: Calmar 20.14, 18.3 R/yr, DD -10.1R, Sharpe 2.123 (0 neg years)")
    print(f"R13 reference (flat=06:45): ORB 10m best, ATR 5 best, both-dir best, no-Thu only")


if __name__ == "__main__":
    main()
