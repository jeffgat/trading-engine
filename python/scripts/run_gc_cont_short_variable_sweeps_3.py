#!/usr/bin/env python3
"""GC continuation shorts — variable sweeps R3 (post-grid R1).

Anchor adopted from grid #2:
  stop=3.0%, rr=8.0, gap=5.5%, tp1=0.7, ATR 10, 15m ORB, entry→15:00, max_gap_atr=30%
  Calmar 0.85, 190.0R, 1 neg year

Sweep 12 dimensions. Adoption: Δ > 0.15 AND no new neg years AND trades >100.
"""

import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.analysis.gates import apply_dow_filter, MON, TUE, WED, THU, FRI
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = GC
START_DATE = "2016-01-01"
DATA_YEARS = 10.15
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
CURRENT_YEAR = "2026"

# ── Anchor config (grid R1 #2) ──────────────────────────────────────────────

ANCHOR_STOP = 3.0
ANCHOR_RR = 8.0
ANCHOR_TP1 = 0.7
ANCHOR_ATR = 10
ANCHOR_GAP = 5.5
ANCHOR_MAX_GAP_ATR = 30.0
ANCHOR_MAX_GAP_PTS = 25.0
ANCHOR_ORB_END = "09:45"  # 15m
ANCHOR_ENTRY_END = "15:00"
ANCHOR_FLAT = "15:50"
ANCHOR_ICF = False

ADOPT_DELTA = 0.15


def median_stop_ticks(trades, instrument):
    stops = [t.risk_points / instrument.min_tick for t in trades if t.exit_type != EXIT_NO_FILL]
    return median(stops) if stops else 0.0


def make_config(
    stop_atr_pct=ANCHOR_STOP, min_gap_atr_pct=ANCHOR_GAP,
    rr=ANCHOR_RR, tp1_ratio=ANCHOR_TP1, atr_length=ANCHOR_ATR,
    orb_end=ANCHOR_ORB_END, entry_end=ANCHOR_ENTRY_END,
    flat_start=ANCHOR_FLAT, impulse_close_filter=ANCHOR_ICF,
):
    session = SessionConfig(
        name="NY", orb_start="09:30", orb_end=orb_end,
        entry_start=orb_end, entry_end=entry_end,
        flat_start=flat_start, flat_end="16:00",
        stop_atr_pct=stop_atr_pct, min_gap_atr_pct=min_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=atr_length, min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=INSTRUMENT,
        strategy="continuation", direction_filter="short",
        impulse_close_filter=impulse_close_filter,
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


def neg_year_set(trades):
    yearly = defaultdict(float)
    for t in trades:
        yearly[t.date[:4]] += t.r_multiple
    return {yr for yr, r in yearly.items() if yr != CURRENT_YEAR and r < 0}


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    yearly = defaultdict(list)
    for t in trades:
        yearly[t.date[:4]].append(t.r_multiple)
    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    avg_annual = nr / DATA_YEARS if DATA_YEARS > 0 else 0
    calmar = abs(avg_annual / dd) if dd < 0 else 999.0
    return {
        "trades": len(trades), "wr": m["win_rate"], "pf": m["profit_factor"],
        "nr": nr, "r_yr": avg_annual, "dd": dd, "calmar": calmar,
        "sharpe": m["sharpe_ratio"], "neg_years": len(neg_year_set(trades)),
        "neg_year_set": neg_year_set(trades),
        "med_stop": median_stop_ticks(trades, INSTRUMENT),
        "yearly": {yr: round(sum(v), 1) for yr, v in sorted(yearly.items())},
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
    print(f"  {label:<35} | {s['trades']:>5} | {s['wr']:>5.1%} | {s['pf']:>5.2f} | "
          f"{s['nr']:>7.1f} | {s['r_yr']:>6.1f} | {s['dd']:>7.1f} | "
          f"{s['calmar']:>7.2f} | {s['sharpe']:>7.3f} | {s['med_stop']:>5.1f} | "
          f"{s['neg_years']:>2}")


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

# ── Anchor ───────────────────────────────────────────────────────────────────

print("=" * 130)
print("VARIABLE SWEEPS R3: GC NY Continuation Shorts (post-grid R1)")
print(f"Anchor: stop={ANCHOR_STOP}%, rr={ANCHOR_RR}, gap={ANCHOR_GAP}%, tp1={ANCHOR_TP1}, "
      f"ATR {ANCHOR_ATR}, 15m ORB, entry→{ANCHOR_ENTRY_END}, max_gap_atr={ANCHOR_MAX_GAP_ATR}%")
print(f"Adoption threshold: Calmar Δ > {ADOPT_DELTA}")
print("=" * 130)

anchor_cfg = make_config()
anchor_filled, anchor_s = run_one(df_5m, df_1m, df_1s, anchor_cfg)
print("\n--- ANCHOR ---")
print_header()
print_row("ANCHOR", anchor_s)
if anchor_s:
    print(f"  R by year: {anchor_s['yearly']}")
    print(f"  Neg years: {anchor_s['neg_year_set']}")
    anchor_neg_years = anchor_s["neg_year_set"]
    anchor_calmar = anchor_s["calmar"]
print()

adoptions = []

# ── Dimension 1: Stop ATR % ─────────────────────────────────────────────────
print("\n--- 1. Stop ATR % ---")
print_header()
best_1 = ("anchor", anchor_s)
for stop in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 7.5, 10.0]:
    cfg = make_config(stop_atr_pct=stop)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if stop == ANCHOR_STOP else ""
    print_row(f"stop={stop}%{marker}", s)
    if s and s["calmar"] > best_1[1]["calmar"]:
        best_1 = (f"stop={stop}%", s)
print(f"  >>> Best: {best_1[0]} (Calmar {best_1[1]['calmar']:.2f})")

# ── Dimension 2: ORB Window ─────────────────────────────────────────────────
print("\n--- 2. ORB Window ---")
print_header()
best_2 = ("anchor", anchor_s)
for orb_min, orb_end in [(5, "09:35"), (10, "09:40"), (15, "09:45"), (20, "09:50"),
                          (25, "09:55"), (30, "10:00"), (45, "10:15")]:
    cfg = make_config(orb_end=orb_end)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if orb_end == ANCHOR_ORB_END else ""
    print_row(f"ORB {orb_min}m{marker}", s)
    if s and s["calmar"] > best_2[1]["calmar"]:
        best_2 = (f"ORB {orb_min}m", s)
print(f"  >>> Best: {best_2[0]} (Calmar {best_2[1]['calmar']:.2f})")

# ── Dimension 3: ATR Length ──────────────────────────────────────────────────
print("\n--- 3. ATR Length ---")
print_header()
best_3 = ("anchor", anchor_s)
for atr in [3, 5, 7, 10, 14, 20, 30, 50]:
    cfg = make_config(atr_length=atr)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if atr == ANCHOR_ATR else ""
    print_row(f"ATR {atr}{marker}", s)
    if s and s["calmar"] > best_3[1]["calmar"]:
        best_3 = (f"ATR {atr}", s)
print(f"  >>> Best: {best_3[0]} (Calmar {best_3[1]['calmar']:.2f})")

# ── Dimension 4: Entry End ──────────────────────────────────────────────────
print("\n--- 4. Entry End ---")
print_header()
best_4 = ("anchor", anchor_s)
for ee in ["10:00", "10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "15:30"]:
    cfg = make_config(entry_end=ee)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if ee == ANCHOR_ENTRY_END else ""
    print_row(f"entry→{ee}{marker}", s)
    if s and s["calmar"] > best_4[1]["calmar"]:
        best_4 = (f"entry→{ee}", s)
print(f"  >>> Best: {best_4[0]} (Calmar {best_4[1]['calmar']:.2f})")

# ── Dimension 5: Flat Start ─────────────────────────────────────────────────
print("\n--- 5. Flat Start ---")
print_header()
best_5 = ("anchor", anchor_s)
for flat in ["13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "15:50"]:
    cfg = make_config(flat_start=flat)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if flat == ANCHOR_FLAT else ""
    print_row(f"flat={flat}{marker}", s)
    if s and s["calmar"] > best_5[1]["calmar"]:
        best_5 = (f"flat={flat}", s)
print(f"  >>> Best: {best_5[0]} (Calmar {best_5[1]['calmar']:.2f})")

# ── Dimension 6: Direction ──────────────────────────────────────────────────
print("\n--- 6. Direction ---")
print_header()
best_6 = ("anchor", anchor_s)
for d in ["both", "long", "short"]:
    session = SessionConfig(
        name="NY", orb_start="09:30", orb_end=ANCHOR_ORB_END,
        entry_start=ANCHOR_ORB_END, entry_end=ANCHOR_ENTRY_END,
        flat_start=ANCHOR_FLAT, flat_end="16:00",
        stop_atr_pct=ANCHOR_STOP, min_gap_atr_pct=ANCHOR_GAP,
    )
    cfg = StrategyConfig(
        rr=ANCHOR_RR, tp1_ratio=ANCHOR_TP1, risk_usd=5000.0,
        atr_length=ANCHOR_ATR, min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=INSTRUMENT,
        strategy="continuation", direction_filter=d,
        use_bar_magnifier=True, half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if d == "short" else ""
    print_row(f"dir={d}{marker}", s)
    if s and s["calmar"] > best_6[1]["calmar"]:
        best_6 = (f"dir={d}", s)
print(f"  >>> Best: {best_6[0]} (Calmar {best_6[1]['calmar']:.2f})")

# ── Dimension 7: R:R ────────────────────────────────────────────────────────
print("\n--- 7. R:R ---")
print_header()
best_7 = ("anchor", anchor_s)
for rr in [2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]:
    cfg = make_config(rr=rr)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if rr == ANCHOR_RR else ""
    print_row(f"rr={rr}{marker}", s)
    if s and s["calmar"] > best_7[1]["calmar"]:
        best_7 = (f"rr={rr}", s)
print(f"  >>> Best: {best_7[0]} (Calmar {best_7[1]['calmar']:.2f})")

# ── Dimension 8: TP1 Ratio ──────────────────────────────────────────────────
print("\n--- 8. TP1 Ratio ---")
print_header()
best_8 = ("anchor", anchor_s)
for tp1 in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
    cfg = make_config(tp1_ratio=tp1)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if tp1 == ANCHOR_TP1 else ""
    print_row(f"tp1={tp1}{marker}", s)
    if s and s["calmar"] > best_8[1]["calmar"]:
        best_8 = (f"tp1={tp1}", s)
print(f"  >>> Best: {best_8[0]} (Calmar {best_8[1]['calmar']:.2f})")

# ── Dimension 9: Min Gap ATR % ──────────────────────────────────────────────
print("\n--- 9. Min Gap ATR % ---")
print_header()
best_9 = ("anchor", anchor_s)
for gap in [1.0, 2.0, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0]:
    cfg = make_config(min_gap_atr_pct=gap)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if gap == ANCHOR_GAP else ""
    print_row(f"gap={gap}%{marker}", s)
    if s and s["calmar"] > best_9[1]["calmar"]:
        best_9 = (f"gap={gap}%", s)
print(f"  >>> Best: {best_9[0]} (Calmar {best_9[1]['calmar']:.2f})")

# ── Dimension 10: DOW Exclusion ──────────────────────────────────────────────
print("\n--- 10. DOW Exclusion ---")
print_header()
best_10 = ("anchor", anchor_s)
dow_configs = [
    ("none", set()), ("excl Mon", {MON}), ("excl Tue", {TUE}),
    ("excl Wed", {WED}), ("excl Thu", {THU}), ("excl Fri", {FRI}),
    ("excl M+F", {MON, FRI}), ("excl Th+F", {THU, FRI}),
]
for label, excl in dow_configs:
    filled, _ = run_one(df_5m, df_1m, df_1s, anchor_cfg)
    if excl:
        filled = apply_dow_filter(filled, excl)
        filled = [t for t in filled if t.exit_type != EXIT_NO_FILL]
    s = stats(filled)
    marker = " (anchor)" if not excl else ""
    print_row(f"{label}{marker}", s)
    if s and s["calmar"] > best_10[1]["calmar"]:
        best_10 = (label, s)
print(f"  >>> Best: {best_10[0]} (Calmar {best_10[1]['calmar']:.2f})")

# ── Dimension 11: Max Gap ATR % ─────────────────────────────────────────────
print("\n--- 11. Max Gap ATR % ---")
print_header()
best_11 = ("anchor", anchor_s)
for mga in [0.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 50.0, 75.0]:
    label = "OFF" if mga == 0.0 else f"{mga:.0f}%"
    cfg = make_config(max_gap_atr_pct=mga)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if mga == ANCHOR_MAX_GAP_ATR else ""
    print_row(f"max_gap_atr={label}{marker}", s)
    if s and s["calmar"] > best_11[1]["calmar"]:
        best_11 = (f"max_gap_atr={label}", s)
print(f"  >>> Best: {best_11[0]} (Calmar {best_11[1]['calmar']:.2f})")

# ── Dimension 12: Impulse Close Filter ──────────────────────────────────────
print("\n--- 12. Impulse Close Filter ---")
print_header()
best_12 = ("anchor", anchor_s)
for icf in [False, True]:
    cfg = make_config(impulse_close_filter=icf)
    filled, s = run_one(df_5m, df_1m, df_1s, cfg)
    marker = " (anchor)" if icf == ANCHOR_ICF else ""
    print_row(f"ICF={icf}{marker}", s)
    if s and s["calmar"] > best_12[1]["calmar"]:
        best_12 = (f"ICF={icf}", s)
print(f"  >>> Best: {best_12[0]} (Calmar {best_12[1]['calmar']:.2f})")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 130)
print("R3 SUMMARY")
print("=" * 130)
print(f"  {'Dimension':<25} | {'Best Value':<25} | {'Calmar':>7} | {'Δ Calmar':>8} | {'Neg Yrs':>7} | {'New NY?':>7} | {'Adopt?':>6}")
print("  " + "-" * 100)

all_bests = [
    ("1. Stop ATR %", best_1), ("2. ORB Window", best_2),
    ("3. ATR Length", best_3), ("4. Entry End", best_4),
    ("5. Flat Start", best_5), ("6. Direction", best_6),
    ("7. R:R", best_7), ("8. TP1 Ratio", best_8),
    ("9. Min Gap ATR %", best_9), ("10. DOW Exclusion", best_10),
    ("11. Max Gap ATR %", best_11), ("12. ICF", best_12),
]

for dim_name, (val, s) in all_bests:
    if s is None:
        print(f"  {dim_name:<25} | {val:<25} | {'N/A':>7} | {'N/A':>8} | {'N/A':>7} | {'N/A':>7} | {'N/A':>6}")
        continue
    delta = s["calmar"] - anchor_calmar
    new_neg = s["neg_year_set"] - anchor_neg_years
    has_new_neg = len(new_neg) > 0
    adopt = delta > ADOPT_DELTA and not has_new_neg and s["trades"] > 100
    adopt_str = "YES" if adopt else "no"
    if adopt:
        adoptions.append((dim_name, val, s))
    print(f"  {dim_name:<25} | {val:<25} | {s['calmar']:>7.2f} | {delta:>+8.2f} | {s['neg_years']:>7} | "
          f"{'YES '+str(new_neg) if has_new_neg else 'no':>7} | {adopt_str:>6}")

print(f"\n  Anchor Calmar: {anchor_calmar:.2f}")
print(f"  Anchor neg years: {anchor_neg_years}")
print(f"  Adoption threshold: Δ > {ADOPT_DELTA}")
print(f"\n  Total adoptions: {len(adoptions)}")

if adoptions:
    print("\n  ADOPTED CHANGES:")
    for dim_name, val, s in adoptions:
        print(f"    {dim_name}: {val} (Calmar {s['calmar']:.2f}, Δ={s['calmar'] - anchor_calmar:+.2f})")
    print("\n  >>> Anchor changed. Re-sweep all 12 dimensions in next round.")
else:
    print("\n  >>> No adoptions. Anchor converged. Ready for grid sweep R2 or pipeline.")
