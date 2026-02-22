#!/usr/bin/env python3
"""ES LDN Continuation Both — Variable Re-Sweep #3 (post fill-bar fix, 1s magnifier).

Anchor changed from robust pipeline (grid sweep confirmation + fill-bar engine fix).
All variable sweeps must be rerun.

New anchor (from robust pipeline, pre-fix):
  stop=5.2%, rr=2.0, gap=1.25%, tp1=0.40
  Calmar 14.57, Sharpe 1.383, Net R 171.8, DD -11.8R, 0 neg years

Structural config locked from sweep_2 + pipeline:
  ORB 10m (03:00-03:10), flat 08:00, ATR 50, both dir, 1s magnifier

Changes from sweep_2:
  - flat_start: 07:30 -> 08:00 (pipeline winner)
  - stop_atr_pct: 5.0 -> 5.2 (pipeline winner)
  - flat_start sweep values re-centered on 08:00

Sweeps each config dimension independently (all others held at anchor):
  1. ORB window      — 5m, 10m*, 15m, 20m, 30m, 45m
  2. ATR length      — 5, 7, 10, 14, 20, 30, 50*
  3. entry_end       — 05:00 to 08:25
  4. flat_start      — 07:30 to 08:25
  5. direction       — both*, long, short
  6. DOW exclusion   — none*, singles, common combos
  7. max_gap_points  — 10 to 100 + no limit
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

# -- Anchor config (from robust pipeline, post fill-bar fix) -------------------

ES_LDN_ANCHOR = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:10",        # 10m ORB (sweep_1 winner)
    entry_start="03:10",
    entry_end="08:25",
    flat_start="08:00",     # pipeline winner (was 07:30 in sweep_2)
    flat_end="08:25",
    stop_atr_pct=5.2,       # pipeline winner (was 5.0 in sweep_2)
    min_gap_atr_pct=1.25,   # fine-tune winner
    max_gap_points=50.0,
)

ANCHOR = StrategyConfig(
    rr=2.0,                 # fine-tune winner
    tp1_ratio=0.40,         # fine-tune winner
    risk_usd=5000.0,
    atr_length=50,          # sweep_1 winner
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
        f"  {'NegYr':>5s}",
        flush=True,
    )
    print("  " + "-" * 112, flush=True)


def section(title):
    print(flush=True)
    print("=" * 70, flush=True)
    print(f"  {title}", flush=True)
    print("=" * 70, flush=True)


def best_of(results):
    lbl, m = max(results, key=lambda x: x[1]["calmar_ratio"])
    delta_label = ""
    # Find anchor result if present
    anchor_calmar = None
    for l, mm in results:
        if "[anchor]" in l:
            anchor_calmar = mm["calmar_ratio"]
            break
    if anchor_calmar is not None:
        delta = m["calmar_ratio"] - anchor_calmar
        delta_label = f" (delta {delta:+.2f})"
    print(f"\n  Best Calmar: {lbl} -> Calmar {m['calmar_ratio']:.2f}, "
          f"Sharpe {m['sharpe_ratio']:.3f}, Net R {m['total_r']:.1f}R{delta_label}",
          flush=True)


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


# -- Sweep 1: ORB window ------------------------------------------------------

def sweep_orb_window():
    section("SWEEP 1: ORB WINDOW")
    header()
    configs = [
        ("5m  03:00-03:05",  "03:05", "03:05"),
        ("10m 03:00-03:10 [anchor]", "03:10", "03:10"),
        ("15m 03:00-03:15",  "03:15", "03:15"),
        ("20m 03:00-03:20",  "03:20", "03:20"),
        ("30m 03:00-03:30",  "03:30", "03:30"),
        ("45m 03:00-03:45",  "03:45", "03:45"),
    ]
    results = []
    for label, orb_end, entry_start in configs:
        sess = make_session(orb_end=orb_end, entry_start=entry_start)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 2: ATR length ------------------------------------------------------

def sweep_atr_length():
    section("SWEEP 2: ATR LENGTH")
    header()
    results = []
    for atr in [5, 7, 10, 14, 20, 30, 50]:
        label = f"ATR {atr}" + (" [anchor]" if atr == 50 else "")
        m = run(with_overrides(ANCHOR, atr_length=atr))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 3: entry_end -------------------------------------------------------

def sweep_entry_end():
    section("SWEEP 3: ENTRY END TIME")
    header()
    times = ["05:00", "05:30", "06:00", "06:30", "07:00", "07:30", "08:00", "08:25"]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "08:25" else "")
        sess = make_session(entry_end=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 4: flat_start ------------------------------------------------------

def sweep_flat_start():
    section("SWEEP 4: FLAT START TIME")
    header()
    times = ["07:30", "07:45", "08:00", "08:10", "08:15", "08:20", "08:25"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "08:00" else "")
        sess = make_session(flat_start=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 5: direction -------------------------------------------------------

def sweep_direction():
    section("SWEEP 5: DIRECTION FILTER")
    header()
    directions = [("both [anchor]", "both"), ("long", "long"), ("short", "short")]
    results = []
    for label, d in directions:
        m = run(with_overrides(ANCHOR, direction_filter=d))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 6: DOW exclusion --------------------------------------------------

def sweep_dow():
    section("SWEEP 6: DAY-OF-WEEK EXCLUSION")
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
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Sweep 7: max_gap_points -------------------------------------------------

def sweep_max_gap_points():
    section("SWEEP 7: MAX GAP POINTS")
    header()
    values = [0, 10, 20, 30, 50, 75, 100]
    results = []
    for v in values:
        label = f"max_gap_pts={v}" + (" [anchor]" if v == 50 else "") + (" (no limit)" if v == 0 else "")
        sess = make_session(max_gap_points=float(v) if v > 0 else 9999.0)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)


# -- Anchor summary -----------------------------------------------------------

def print_summary(m):
    section("ANCHOR METRICS (pipeline winner, post fill-bar fix, 1s magnifier)")
    print(f"  rr=2.0 | tp1=0.4 | stop=5.2% | gap=1.25% | ORB 10m | ATR 50 | both dir | flat 08:00 | 1s", flush=True)
    print(flush=True)
    print(f"  {'Trades':<20s} {m['total_trades']:>12d}", flush=True)
    print(f"  {'Win Rate':<20s} {m['win_rate']:>11.1%}", flush=True)
    print(f"  {'PF':<20s} {m['profit_factor']:>12.2f}", flush=True)
    print(f"  {'Net R':<20s} {m['total_r']:>11.1f}R", flush=True)
    print(f"  {'R/yr':<20s} {r_per_year(m):>11.1f}R", flush=True)
    print(f"  {'Max DD':<20s} {m['max_drawdown_r']:>11.1f}R", flush=True)
    print(f"  {'Calmar':<20s} {m['calmar_ratio']:>12.2f}", flush=True)
    print(f"  {'Sharpe':<20s} {m['sharpe_ratio']:>12.3f}", flush=True)
    print(f"  {'Neg full years':<20s} {neg_years(m):>12d}", flush=True)
    print(flush=True)
    rby = m.get("r_by_year", {})
    if rby:
        print(f"  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print(flush=True)
    print("=" * 70, flush=True)
    print("  ES LDN CONTINUATION BOTH — VARIABLE RE-SWEEP #3 (post fill-bar fix)", flush=True)
    print("  New anchor: rr=2.0 | tp1=0.4 | stop=5.2% | gap=1.25% | 10m ORB", flush=True)
    print("  Structural: ORB 10m | flat 08:00 | ATR 50 | both dir | 1s", flush=True)
    print("  From pipeline: Calmar 14.57, 0 neg years, DD -11.8R", flush=True)
    print("=" * 70, flush=True)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df = load_5m_data("ES_5m.csv")
    df_1m = load_1m_for_5m("ES_5m.csv")
    df_1s = load_1s_for_5m("ES_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})", flush=True)
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars", flush=True)
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars", flush=True)
    else:
        print("  1s: NOT FOUND — results will use 1m only (less accurate)", flush=True)
    print(f"  Loaded in {time.time() - t0:.1f}s", flush=True)

    print("\nRunning anchor config...", flush=True)
    t0 = time.time()
    anchor_m = run(ANCHOR)
    print(f"  Done in {time.time() - t0:.1f}s", flush=True)
    print_summary(anchor_m)

    t_start = time.time()
    sweep_orb_window()
    sweep_atr_length()
    sweep_entry_end()
    sweep_flat_start()
    sweep_direction()
    sweep_dow()
    sweep_max_gap_points()
    elapsed = time.time() - t_start

    print(flush=True)
    print("=" * 70, flush=True)
    print(f"  DONE — All 7 sweeps complete in {elapsed:.0f}s", flush=True)
    print("  Note: rr, tp1, stop, gap are NOT swept here — they come from the", flush=True)
    print("  fine-tune grid. Only structural variables are re-swept on the", flush=True)
    print("  post fill-bar-fix anchor.", flush=True)
    print("  Next: if any structural variable changed, update anchor and", flush=True)
    print("  re-run fine-tune grid. Otherwise proceed to robust pipeline.", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)
