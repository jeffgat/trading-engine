#!/usr/bin/env python3
"""GC continuation shorts — diagnostic sweep to find viable starting anchor.

Sweeps 6 key dimensions independently from a moderate starting config.
Goal: identify which parameter regions produce positive expectancy for shorts.
"""

import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = GC
START_DATE = "2016-01-01"
DATA_YEARS = 10.15
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
CURRENT_YEAR = "2026"


def median_stop_ticks(trades, instrument):
    stops = [t.risk_points / instrument.min_tick for t in trades if t.exit_type != EXIT_NO_FILL]
    return median(stops) if stops else 0.0


def make_config(
    stop_atr_pct=4.0,
    min_gap_atr_pct=3.0,
    rr=4.0,
    tp1_ratio=0.5,
    atr_length=14,
    orb_end="09:45",
    entry_end="13:00",
    flat_start="15:50",
):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end=orb_end,
        entry_start=orb_end, entry_end=entry_end,
        flat_start=flat_start, flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=atr_length,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=INSTRUMENT,
        strategy="continuation", direction_filter="short",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    yearly = defaultdict(list)
    for t in trades:
        yearly[t.date[:4]].append(t.r_multiple)
    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    n_full = len([yr for yr in yearly if yr != CURRENT_YEAR])
    avg_annual = nr / DATA_YEARS if DATA_YEARS > 0 else 0
    calmar = abs(avg_annual / dd) if dd < 0 else 999.0
    neg_years = sum(1 for yr, rs in yearly.items() if yr != CURRENT_YEAR and sum(rs) < 0)
    med_stop = median_stop_ticks(trades, INSTRUMENT)
    return {
        "trades": len(trades),
        "wr": m["win_rate"],
        "pf": m["profit_factor"],
        "nr": nr,
        "r_yr": avg_annual,
        "dd": dd,
        "calmar": calmar,
        "sharpe": m["sharpe_ratio"],
        "neg_years": neg_years,
        "med_stop": med_stop,
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
    }


def print_header():
    print(f"  {'Config':<35} | {'Trd':>5} | {'WR':>5} | {'PF':>5} | "
          f"{'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | {'Calmar':>7} | "
          f"{'Sharpe':>7} | {'MedSt':>5} | {'NY':>2}")
    print("  " + "-" * 120)


def print_row(label, s):
    if s is None:
        print(f"  {label:<35} | <5 trades")
        return
    flag = " ***" if s["calmar"] > 0.3 and s["nr"] > 0 else ""
    print(f"  {label:<35} | {s['trades']:>5} | {s['wr']:>5.1%} | {s['pf']:>5.2f} | "
          f"{s['nr']:>7.1f} | {s['r_yr']:>6.1f} | {s['dd']:>7.1f} | "
          f"{s['calmar']:>7.2f} | {s['sharpe']:>7.3f} | {s['med_stop']:>5.1f} | "
          f"{s['neg_years']:>2}{flag}")


def run_one(df, df_1m, df_1s, cfg):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    return filled, stats(filled)


# ── Load data ────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s\n")

# ── Anchor baseline ─────────────────────────────────────────────────────────

print("=" * 80)
print("DIAGNOSTIC SWEEP: GC NY Continuation Shorts")
print("Anchor: stop=4.0%, rr=4.0, gap=3.0%, tp1=0.5, ATR 14, 15m ORB, entry→13:00")
print("=" * 80)

anchor_cfg = make_config()
anchor_filled, anchor_s = run_one(df_5m, df_1m, df_1s, anchor_cfg)
print("\n--- Anchor ---")
print_header()
print_row("ANCHOR (defaults)", anchor_s)
if anchor_s:
    print(f"\n  R by year: {anchor_s['yearly']}")
print()

# ── Sweep 1: Stop ATR % ─────────────────────────────────────────────────────

print("\n--- 1. Stop ATR % ---")
print_header()
for stop in [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, 15.0]:
    cfg = make_config(stop_atr_pct=stop)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if stop == 4.0 else ""
    print_row(f"stop={stop}%{marker}", s)

# ── Sweep 2: R:R ─────────────────────────────────────────────────────────────

print("\n--- 2. R:R ---")
print_header()
for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]:
    cfg = make_config(rr=rr)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if rr == 4.0 else ""
    print_row(f"rr={rr}{marker}", s)

# ── Sweep 3: Min Gap ATR % ──────────────────────────────────────────────────

print("\n--- 3. Min Gap ATR % ---")
print_header()
for gap in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0]:
    cfg = make_config(min_gap_atr_pct=gap)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if gap == 3.0 else ""
    print_row(f"gap={gap}%{marker}", s)

# ── Sweep 4: Entry End ──────────────────────────────────────────────────────

print("\n--- 4. Entry End ---")
print_header()
for ee in ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "15:30"]:
    cfg = make_config(entry_end=ee)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if ee == "13:00" else ""
    print_row(f"entry→{ee}{marker}", s)

# ── Sweep 5: ORB Window ─────────────────────────────────────────────────────

print("\n--- 5. ORB Window ---")
print_header()
for orb_min, orb_end in [(5, "09:35"), (10, "09:40"), (15, "09:45"), (20, "09:50"),
                          (25, "09:55"), (30, "10:00"), (45, "10:15")]:
    cfg = make_config(orb_end=orb_end)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if orb_min == 15 else ""
    print_row(f"ORB {orb_min}m{marker}", s)

# ── Sweep 6: ATR Length ──────────────────────────────────────────────────────

print("\n--- 6. ATR Length ---")
print_header()
for atr in [3, 5, 7, 10, 14, 20, 30, 50]:
    cfg = make_config(atr_length=atr)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if atr == 14 else ""
    print_row(f"ATR {atr}{marker}", s)

# ── Sweep 7: TP1 Ratio ──────────────────────────────────────────────────────

print("\n--- 7. TP1 Ratio ---")
print_header()
for tp1 in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
    cfg = make_config(tp1_ratio=tp1)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if tp1 == 0.5 else ""
    print_row(f"tp1={tp1}{marker}", s)

# ── Best compound: try best-of from each dimension ──────────────────────────

print("\n" + "=" * 80)
print("COMPOUND TESTS — combining best values from each dimension")
print("(Choose best from each sweep above, combine them)")
print("=" * 80)

# We'll test a few targeted compounds based on what we know from previous optimization
compounds = [
    ("stop=2.5 rr=7.0 gap=5.0 entry→15:00",
     dict(stop_atr_pct=2.5, rr=7.0, min_gap_atr_pct=5.0, entry_end="15:00")),
    ("stop=3.0 rr=6.0 gap=5.0 entry→15:00",
     dict(stop_atr_pct=3.0, rr=6.0, min_gap_atr_pct=5.0, entry_end="15:00")),
    ("stop=2.0 rr=8.0 gap=5.0 entry→15:00",
     dict(stop_atr_pct=2.0, rr=8.0, min_gap_atr_pct=5.0, entry_end="15:00")),
    ("stop=3.0 rr=5.0 gap=4.0 entry→14:00",
     dict(stop_atr_pct=3.0, rr=5.0, min_gap_atr_pct=4.0, entry_end="14:00")),
    ("stop=4.0 rr=5.0 gap=5.0 entry→15:00",
     dict(stop_atr_pct=4.0, rr=5.0, min_gap_atr_pct=5.0, entry_end="15:00")),
    ("stop=2.5 rr=7.0 gap=5.5 entry→15:00",
     dict(stop_atr_pct=2.5, rr=7.0, min_gap_atr_pct=5.5, entry_end="15:00")),
    ("stop=3.0 rr=7.0 gap=5.0 entry→15:00 ATR10",
     dict(stop_atr_pct=3.0, rr=7.0, min_gap_atr_pct=5.0, entry_end="15:00", atr_length=10)),
    ("stop=2.5 rr=7.0 gap=5.0 entry→15:00 ATR10",
     dict(stop_atr_pct=2.5, rr=7.0, min_gap_atr_pct=5.0, entry_end="15:00", atr_length=10)),
]

print_header()
for label, kwargs in compounds:
    cfg = make_config(**kwargs)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    print_row(label, s)
    if s and s["nr"] > 50:
        print(f"    R by year: {s['yearly']}")

print("\n>>> Review results above and pick the best starting anchor for variable sweeps.")
