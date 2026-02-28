#!/usr/bin/env python3
"""ES LDN Continuation Both — Variable Sweep with 1s magnifier.

Previous ES LDN optimization was done with 1m magnifier only. Now that 1s
data is available (ES_1s.parquet), we re-sweep all config dimensions to find
the new optimal surface. 1s resolution may change results for tight stops
(1-3% ATR) where 1m bars could span entry+stop simultaneously.

Anchor config (accepted from prior pipeline, 1m magnifier):
  strategy=continuation, direction=both, London session
  rr=3.0, tp1=0.5, stop=1.5%, min_gap=1.25%, atr_length=14
  ORB 15m (03:00-03:15), entry_end=08:25, flat=08:20-08:25
  be=0, magnifier ON

Sweeps each config dimension independently (all others held at anchor):
  1. stop_atr_pct    — 1.0 to 8.0 (tight stops now accurate with 1s)
  2. ORB window      — 5m, 10m, 15m*, 20m, 30m, 45m
  3. ATR length      — 5, 7, 10, 14*, 20, 30, 50
  4. entry_end       — 05:00 to 08:25 (8 values)
  5. flat_start      — 07:00 to 08:20 (6 values)
  6. direction       — both*, long, short
  7. rr              — 1.5 to 5.0 (8 values)
  8. tp1_ratio       — 0.1 to 0.7 (7 values)
  9. min_gap_atr_pct — 0.5 to 4.0 (8 values)
  10. DOW exclusion  — none*, Mon-Fri singles, common combos
  11. max_gap_points — 10 to 100 + no limit

Scoring: Calmar ratio (primary), then Sharpe.
*=anchor value
"""

import sys
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# -- Instrument ----------------------------------------------------------------

ES = get_instrument("ES")
START_DATE = "2016-01-01"
END_DATE = "2026-02-15"

# -- Anchor config (accepted from prior 1m pipeline) --------------------------

ES_LDN_ANCHOR = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:15",        # 15m ORB
    entry_start="03:15",
    entry_end="08:25",
    flat_start="08:20",
    flat_end="08:25",
    stop_atr_pct=1.5,
    min_gap_atr_pct=1.25,
)

ANCHOR = StrategyConfig(
    rr=3.0,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=14,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(ES_LDN_ANCHOR,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Module-level data (set in main, used in run()) ---------------------------

df = None
df_1m = None
df_1s = None

# -- Helpers -------------------------------------------------------------------

FULL_YEARS = [str(y) for y in range(2016, 2026)]


def run(cfg, excluded_dow=None):
    trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    if excluded_dow:
        trades = [
            t for t in trades
            if t.exit_type == EXIT_NO_FILL
            or datetime.strptime(t.date, "%Y-%m-%d").weekday() not in excluded_dow
        ]
    return compute_metrics(trades)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def row(label, m):
    return (
        f"  {label:<32s}"
        f"  {m['total_trades']:>6d}"
        f"  {m['win_rate']:>6.1%}"
        f"  {m['profit_factor']:>5.2f}"
        f"  {m['total_r']:>8.1f}"
        f"  {r_per_year(m):>7.1f}"
        f"  {m['max_drawdown_r']:>8.1f}"
        f"  {m['calmar_ratio']:>7.2f}"
        f"  {m['sharpe_ratio']:>7.3f}"
        f"  {neg_years(m):>5d}"
    )


def header():
    print(
        f"  {'Config':<32s}"
        f"  {'Trades':>6s}"
        f"  {'  WR':>6s}"
        f"  {'   PF':>5s}"
        f"  {'  Net R':>8s}"
        f"  {' R/yr':>7s}"
        f"  {' Max DD':>8s}"
        f"  {'Calmar':>7s}"
        f"  {' Sharpe':>7s}"
        f"  {'NegYr':>5s}"
    )
    print("  " + "-" * 112)


def section(title):
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


def best_of(results):
    lbl, m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {lbl} -> Calmar {m['calmar_ratio']:.2f}, "
          f"Sharpe {m['sharpe_ratio']:.3f}, Net R {m['total_r']:.1f}R")


def make_session(**overrides):
    """Create a new session config from anchor with overrides."""
    d = {
        "name": "LDN",
        "orb_start": ES_LDN_ANCHOR.orb_start,
        "orb_end": ES_LDN_ANCHOR.orb_end,
        "entry_start": ES_LDN_ANCHOR.entry_start,
        "entry_end": ES_LDN_ANCHOR.entry_end,
        "flat_start": ES_LDN_ANCHOR.flat_start,
        "flat_end": ES_LDN_ANCHOR.flat_end,
        "stop_atr_pct": ES_LDN_ANCHOR.stop_atr_pct,
        "min_gap_atr_pct": ES_LDN_ANCHOR.min_gap_atr_pct,
        "max_gap_points": ES_LDN_ANCHOR.max_gap_points,
    }
    d.update(overrides)
    return SessionConfig(**d)


# -- Sweep 1: stop_atr_pct (core variable, most affected by 1s data) ----------

def sweep_stop():
    section("SWEEP 1: STOP ATR% (core variable -- 1s enables tight stops)")
    header()
    values = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0]
    results = []
    for v in values:
        label = f"stop={v:.1f}%" + (" [anchor]" if v == 1.5 else "")
        sess = make_session(stop_atr_pct=v)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 2: ORB window ------------------------------------------------------

def sweep_orb_window():
    section("SWEEP 2: ORB WINDOW")
    header()
    configs = [
        ("5m  03:00-03:05",  "03:05", "03:05"),
        ("10m 03:00-03:10",  "03:10", "03:10"),
        ("15m 03:00-03:15 [anchor]", "03:15", "03:15"),
        ("20m 03:00-03:20",  "03:20", "03:20"),
        ("30m 03:00-03:30",  "03:30", "03:30"),
        ("45m 03:00-03:45",  "03:45", "03:45"),
    ]
    results = []
    for label, orb_end, entry_start in configs:
        sess = make_session(orb_end=orb_end, entry_start=entry_start)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 3: ATR length ------------------------------------------------------

def sweep_atr_length():
    section("SWEEP 3: ATR LENGTH")
    header()
    results = []
    for atr in [5, 7, 10, 14, 20, 30, 50]:
        label = f"ATR {atr}" + (" [anchor]" if atr == 14 else "")
        m = run(with_overrides(ANCHOR, atr_length=atr))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 4: entry_end -------------------------------------------------------

def sweep_entry_end():
    section("SWEEP 4: ENTRY END TIME")
    header()
    times = ["05:00", "05:30", "06:00", "06:30", "07:00", "07:30", "08:00", "08:25"]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "08:25" else "")
        sess = make_session(entry_end=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 5: flat_start ------------------------------------------------------

def sweep_flat_start():
    section("SWEEP 5: FLAT START TIME")
    header()
    times = ["07:00", "07:30", "07:45", "08:00", "08:10", "08:20"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "08:20" else "")
        sess = make_session(flat_start=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 6: direction -------------------------------------------------------

def sweep_direction():
    section("SWEEP 6: DIRECTION FILTER")
    header()
    directions = [("both [anchor]", "both"), ("long", "long"), ("short", "short")]
    results = []
    for label, d in directions:
        m = run(with_overrides(ANCHOR, direction_filter=d))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 7: rr --------------------------------------------------------------

def sweep_rr():
    section("SWEEP 7: RISK:REWARD RATIO")
    header()
    values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    results = []
    for v in values:
        label = f"rr={v:.1f}" + (" [anchor]" if v == 3.0 else "")
        m = run(with_overrides(ANCHOR, rr=v))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 8: tp1_ratio -------------------------------------------------------

def sweep_tp1():
    section("SWEEP 8: TP1 RATIO")
    header()
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    results = []
    for v in values:
        label = f"tp1={v:.1f}" + (" [anchor]" if v == 0.5 else "")
        m = run(with_overrides(ANCHOR, tp1_ratio=v))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 9: min_gap_atr_pct -------------------------------------------------

def sweep_min_gap():
    section("SWEEP 9: MIN GAP ATR%")
    header()
    values = [0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0]
    results = []
    for v in values:
        label = f"gap={v:.2f}%" + (" [anchor]" if v == 1.25 else "")
        sess = make_session(min_gap_atr_pct=v)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 10: DOW exclusion --------------------------------------------------

def sweep_dow():
    section("SWEEP 10: DAY-OF-WEEK EXCLUSION")
    header()
    dow_configs = [
        ("none [anchor]",  set()),
        ("excl Monday",    {0}),
        ("excl Tuesday",   {1}),
        ("excl Wednesday", {2}),
        ("excl Thursday",  {3}),
        ("excl Friday",    {4}),
        ("excl Mon+Fri",   {0, 4}),
        ("excl Thu+Fri",   {3, 4}),
    ]
    results = []
    for label, excl in dow_configs:
        m = run(ANCHOR, excluded_dow=excl if excl else None)
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Sweep 11: max_gap_points -------------------------------------------------

def sweep_max_gap_points():
    section("SWEEP 11: MAX GAP POINTS")
    header()
    values = [0, 10, 20, 30, 50, 75, 100]
    results = []
    for v in values:
        label = f"max_gap_pts={v}" + (" [anchor]" if v == 50 else "") + (" (no limit)" if v == 0 else "")
        sess = make_session(max_gap_points=float(v) if v > 0 else 9999.0)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m))
        results.append((label, m))
    best_of(results)


# -- Anchor summary -----------------------------------------------------------

def print_summary(m):
    section("ANCHOR METRICS (accepted config, now with 1s magnifier)")
    print(f"  rr=3.0 | tp1=0.5 | stop=1.5% | gap=1.25% | ORB 15m | ATR 14 | both dir | 1s")
    print()
    print(f"  {'Trades':<20s} {m['total_trades']:>12d}")
    print(f"  {'Win Rate':<20s} {m['win_rate']:>11.1%}")
    print(f"  {'PF':<20s} {m['profit_factor']:>12.2f}")
    print(f"  {'Net R':<20s} {m['total_r']:>11.1f}R")
    print(f"  {'R/yr':<20s} {r_per_year(m):>11.1f}R")
    print(f"  {'Max DD':<20s} {m['max_drawdown_r']:>11.1f}R")
    print(f"  {'Calmar':<20s} {m['calmar_ratio']:>12.2f}")
    print(f"  {'Sharpe':<20s} {m['sharpe_ratio']:>12.3f}")
    print(f"  {'Neg full years':<20s} {neg_years(m):>12d}")
    print()
    rby = m.get("r_by_year", {})
    if rby:
        print(f"  R by year:")
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}")


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  ES LDN CONTINUATION BOTH — VARIABLE SWEEP (1s magnifier)")
    print("  Anchor: rr=3.0 | tp1=0.5 | stop=1.5% | gap=1.25% | 15m ORB")
    print("  Accepted config from prior 1m pipeline (CONDITIONAL GO)")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})")
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars")
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars")
    else:
        print("  1s: NOT FOUND — results will use 1m only (less accurate)")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print("\nRunning anchor config...")
    t0 = time.time()
    anchor_m = run(ANCHOR)
    print(f"  Done in {time.time() - t0:.1f}s")
    print_summary(anchor_m)

    sweep_stop()
    sweep_orb_window()
    sweep_atr_length()
    sweep_entry_end()
    sweep_flat_start()
    sweep_direction()
    sweep_rr()
    sweep_tp1()
    sweep_min_gap()
    sweep_dow()
    sweep_max_gap_points()

    print()
    print("=" * 70)
    print("  DONE — Review each sweep for best Calmar.")
    print("  Compare 1s anchor vs prior 1m results:")
    print("    Prior 1m: 2328 trades, 48% WR, PF 1.51, Sharpe 2.51, DD -17.8R")
    print("  Next: update anchor to winning values, run fine-tune grid.")
    print("=" * 70)
    print()
