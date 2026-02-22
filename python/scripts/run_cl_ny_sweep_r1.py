#!/usr/bin/env python3
"""CL NY — Full Variable Sweep + 4D Grid Optimization (Round 1).

Starting fresh with corrected data. Previous CL learnings invalidated.

Two parts:
  Part A: Variable sweeps — 12 dimensions swept independently (~90 runs)
    1. stop_atr_pct    — 1.0 to 15.0 (10 values)
    2. ORB window      — 5m, 10m, 15m, 20m, 30m (5)
    3. ATR length      — 5, 7, 10, 14, 20, 30, 50 (7)
    4. entry_end       — 10:30 to 14:00 (8)
    5. flat_start      — 13:00 to 15:50 (7)
    6. direction       — both, long, short (3)
    7. strategy        — continuation, reversal (2)
    8. rr              — 1.5 to 5.0 (8)
    9. tp1_ratio       — 0.1 to 0.7 (7)
    10. min_gap_atr_pct — 0.5 to 5.0 (9)
    11. DOW exclusion  — none, Mon-Fri singles, common combos (8)
    12. max_gap_points — various + no limit (7)

  Part B: 4D grid — stop x rr x gap x tp1 (~880 combos)
    stop:  [2.0, 4.0, 6.0, 7.5, 10.0, 12.0]       = 6
    rr:    [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]     = 7
    gap:   [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]     = 7
    tp1:   [0.3, 0.5, 0.7]                           = 3
    Total: 882 combos

Anchor: CL NY defaults — rr=2.5, tp1=0.5, stop=7.5%, gap=2.25%
        ORB 15m (09:30-09:45), entry_end=13:00, flat=15:50-16:00
        ATR 14, direction=both, continuation, 1s magnifier

Total: ~970 backtests. Estimated runtime: 3-5 hours with 1s magnifier.
Scoring: Calmar (primary), 0 negative full years (secondary).
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

CL = get_instrument("CL")
START_DATE = "2016-01-01"

# -- Anchor config (CL NY defaults) -------------------------------------------

CL_NY_ANCHOR = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",       # 15m ORB
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=7.5,
    min_gap_atr_pct=2.25,
    max_gap_points=100.0,
)

ANCHOR = StrategyConfig(
    rr=2.5,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=14,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(CL_NY_ANCHOR,),
    instrument=CL,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Module-level data (set in main) ------------------------------------------

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
    if not results:
        return None, None
    lbl, m = max(results, key=lambda x: x[1]["calmar_ratio"])
    print(f"\n  Best Calmar: {lbl} -> Calmar {m['calmar_ratio']:.2f}, "
          f"Sharpe {m['sharpe_ratio']:.3f}, Net R {m['total_r']:.1f}R", flush=True)
    return lbl, m


def make_session(**overrides):
    """Create a new session config from anchor with overrides."""
    d = {
        "name": "NY",
        "orb_start": CL_NY_ANCHOR.orb_start,
        "orb_end": CL_NY_ANCHOR.orb_end,
        "entry_start": CL_NY_ANCHOR.entry_start,
        "entry_end": CL_NY_ANCHOR.entry_end,
        "flat_start": CL_NY_ANCHOR.flat_start,
        "flat_end": CL_NY_ANCHOR.flat_end,
        "stop_atr_pct": CL_NY_ANCHOR.stop_atr_pct,
        "min_gap_atr_pct": CL_NY_ANCHOR.min_gap_atr_pct,
        "max_gap_points": CL_NY_ANCHOR.max_gap_points,
    }
    d.update(overrides)
    return SessionConfig(**d)


# ==============================================================================
# PART A: VARIABLE SWEEPS
# ==============================================================================


def sweep_stop():
    section("SWEEP 1: STOP ATR%")
    header()
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.5, 9.0, 12.0, 15.0]
    results = []
    for v in values:
        label = f"stop={v:.1f}%" + (" [anchor]" if v == 7.5 else "")
        sess = make_session(stop_atr_pct=v)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_orb_window():
    section("SWEEP 2: ORB WINDOW")
    header()
    configs = [
        ("5m  09:30-09:35",  "09:35", "09:35"),
        ("10m 09:30-09:40",  "09:40", "09:40"),
        ("15m 09:30-09:45 [anchor]", "09:45", "09:45"),
        ("20m 09:30-09:50",  "09:50", "09:50"),
        ("30m 09:30-10:00",  "10:00", "10:00"),
    ]
    results = []
    for label, orb_end, entry_start in configs:
        sess = make_session(orb_end=orb_end, entry_start=entry_start)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_atr_length():
    section("SWEEP 3: ATR LENGTH")
    header()
    results = []
    for atr in [5, 7, 10, 14, 20, 30, 50]:
        label = f"ATR {atr}" + (" [anchor]" if atr == 14 else "")
        m = run(with_overrides(ANCHOR, atr_length=atr))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_entry_end():
    section("SWEEP 4: ENTRY END TIME")
    header()
    times = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"]
    results = []
    for t in times:
        label = f"entry_end={t}" + (" [anchor]" if t == "13:00" else "")
        sess = make_session(entry_end=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_flat_start():
    section("SWEEP 5: FLAT START TIME")
    header()
    times = ["13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "15:50"]
    results = []
    for t in times:
        label = f"flat_start={t}" + (" [anchor]" if t == "15:50" else "")
        sess = make_session(flat_start=t)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_direction():
    section("SWEEP 6: DIRECTION FILTER")
    header()
    directions = [("both [anchor]", "both"), ("long", "long"), ("short", "short")]
    results = []
    for label, d in directions:
        m = run(with_overrides(ANCHOR, direction_filter=d))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_strategy():
    section("SWEEP 7: STRATEGY TYPE")
    header()
    strategies = [("continuation [anchor]", "continuation"), ("reversal", "reversal")]
    results = []
    for label, s in strategies:
        m = run(with_overrides(ANCHOR, strategy=s))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_rr():
    section("SWEEP 8: RISK:REWARD RATIO")
    header()
    values = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
    results = []
    for v in values:
        label = f"rr={v:.1f}" + (" [anchor]" if v == 2.5 else "")
        m = run(with_overrides(ANCHOR, rr=v))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_tp1():
    section("SWEEP 9: TP1 RATIO")
    header()
    values = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    results = []
    for v in values:
        label = f"tp1={v:.1f}" + (" [anchor]" if v == 0.5 else "")
        m = run(with_overrides(ANCHOR, tp1_ratio=v))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_min_gap():
    section("SWEEP 10: MIN GAP ATR%")
    header()
    values = [0.5, 0.75, 1.0, 1.5, 2.0, 2.25, 2.5, 3.0, 4.0]
    results = []
    for v in values:
        label = f"gap={v:.2f}%" + (" [anchor]" if v == 2.25 else "")
        sess = make_session(min_gap_atr_pct=v)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


def sweep_dow():
    section("SWEEP 11: DAY-OF-WEEK EXCLUSION")
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
    return results


def sweep_max_gap_points():
    section("SWEEP 12: MAX GAP POINTS")
    header()
    # CL: 1 point = $1/barrel. Typical daily range $1-3.
    # FVG sizes: $0.05 to $0.50. Use CL-appropriate values.
    values = [0.25, 0.50, 1.0, 1.5, 2.0, 3.0, 0]
    results = []
    for v in values:
        if v == 0:
            label = "no limit"
            pts = 9999.0
        else:
            label = f"max_gap_pts=${v:.2f}" + (" [anchor ~no limit]" if v == 3.0 else "")
            pts = v
        sess = make_session(max_gap_points=pts)
        m = run(with_overrides(ANCHOR, sessions=(sess,)))
        print(row(label, m), flush=True)
        results.append((label, m))
    best_of(results)
    return results


# ==============================================================================
# PART B: 4D GRID SWEEP
# ==============================================================================

STOP_VALUES = [2.0, 4.0, 6.0, 7.5, 10.0, 12.0]
RR_VALUES = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
GAP_VALUES = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]
TP1_VALUES = [0.3, 0.5, 0.7]

TOTAL_GRID = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)


def run_grid():
    section(f"PART B: 4D GRID SWEEP — {TOTAL_GRID} combos")
    print(f"  Structural: ORB 15m | entry_end 13:00 | flat 15:50 | ATR 14 | both | continuation", flush=True)
    print(f"  Grid: {len(STOP_VALUES)} stops x {len(RR_VALUES)} rr x "
          f"{len(GAP_VALUES)} gaps x {len(TP1_VALUES)} tp1 = {TOTAL_GRID}", flush=True)
    print(flush=True)

    print(f"  {'#':>5} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}", flush=True)
    print("  " + "-" * 115, flush=True)

    results = []
    t_start = time.time()

    for stop in STOP_VALUES:
        for rr in RR_VALUES:
            for gap in GAP_VALUES:
                for tp1 in TP1_VALUES:
                    idx = len(results) + 1

                    sess = SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:45",
                        entry_start="09:45",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_atr_pct=stop,
                        min_gap_atr_pct=gap,
                        max_gap_points=100.0,
                    )
                    cfg = with_overrides(ANCHOR, rr=rr, tp1_ratio=tp1, sessions=(sess,))

                    trades = run_backtest(df, cfg, start_date=START_DATE,
                                          df_1m=df_1m, df_1s=df_1s)
                    m = compute_metrics(trades)

                    ny = neg_years(m)

                    print(f"  {idx:>5} {stop:>5.1f} {rr:>5.1f} {gap:>5.2f} {tp1:>5.2f} | "
                          f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
                          f"{m['total_r']:>8.1f} {r_per_year(m):>7.1f} {m['max_drawdown_r']:>8.1f} "
                          f"{m['calmar_ratio']:>7.2f} {m['sharpe_ratio']:>7.3f} {ny:>5}", flush=True)

                    results.append({
                        "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
                        "trades": m["total_trades"], "wr": m["win_rate"],
                        "pf": m["profit_factor"], "net_r": m["total_r"],
                        "r_yr": r_per_year(m), "dd": m["max_drawdown_r"],
                        "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"],
                        "neg_years": ny,
                        "neg_detail": [f"{y}:{r:+.1f}" for y, r in sorted(m.get("r_by_year", {}).items())
                                       if y in FULL_YEARS and r < 0],
                        "r_by_year": m.get("r_by_year", {}),
                    })

        # Progress after each stop level
        elapsed = time.time() - t_start
        done = len(results)
        rate = done / elapsed if elapsed > 0 else 0
        remaining = (TOTAL_GRID - done) / rate if rate > 0 else 0
        print(f"  --- stop={stop:.1f}% done ({done}/{TOTAL_GRID}, "
              f"{elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining) ---", flush=True)

    elapsed = time.time() - t_start
    print(f"\n  Grid complete: {TOTAL_GRID} combos in {elapsed:.1f}s "
          f"({elapsed/60:.1f} min)", flush=True)

    # -- Leaderboard -----------------------------------------------------------

    ranked = sorted(results, key=lambda x: x["calmar"], reverse=True)

    print(flush=True)
    print("=" * 70, flush=True)
    print("  GRID TOP 20 BY CALMAR", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}", flush=True)
    print("  " + "-" * 115, flush=True)

    for i, r in enumerate(ranked[:20]):
        print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} | "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f} {r['neg_years']:>5}", flush=True)

    # Top with 0 neg years
    clean = [r for r in ranked if r["neg_years"] == 0]
    if clean:
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  GRID TOP 20 BY CALMAR (0 neg years) — {len(clean)}/{len(results)} clean", flush=True)
        print("=" * 70, flush=True)
        print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} | "
              f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
              f"{'Calmar':>7} {'Sharpe':>7}", flush=True)
        print("  " + "-" * 110, flush=True)

        for i, r in enumerate(clean[:20]):
            print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.1f} {r['gap']:>5.2f} {r['tp1']:>5.2f} | "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
                  f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
                  f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f}", flush=True)

    # -- Marginal analysis (avg Calmar per dimension) --------------------------

    print(flush=True)
    print("=" * 70, flush=True)
    print("  GRID MARGINAL ANALYSIS (avg Calmar per level)", flush=True)
    print("=" * 70, flush=True)

    for dim_name, dim_values, dim_key in [
        ("stop_atr_pct", STOP_VALUES, "stop"),
        ("rr", RR_VALUES, "rr"),
        ("min_gap_atr_pct", GAP_VALUES, "gap"),
        ("tp1_ratio", TP1_VALUES, "tp1"),
    ]:
        print(f"\n  {dim_name}:", flush=True)
        for v in dim_values:
            subset = [r for r in results if r[dim_key] == v]
            avg_calmar = sum(r["calmar"] for r in subset) / len(subset)
            avg_sharpe = sum(r["sharpe"] for r in subset) / len(subset)
            n_clean = sum(1 for r in subset if r["neg_years"] == 0)
            print(f"    {v:>6.2f}: avg Calmar {avg_calmar:>7.2f} | "
                  f"avg Sharpe {avg_sharpe:>6.3f} | "
                  f"clean {n_clean:>3}/{len(subset)}", flush=True)

    # -- Year-by-year for top configs ------------------------------------------

    for label, src in [("GRID TOP OVERALL", ranked[0] if ranked else None),
                        ("GRID TOP CLEAN", clean[0] if clean else None)]:
        if src is None:
            continue
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  {label}: stop={src['stop']:.1f}% rr={src['rr']:.1f} "
              f"gap={src['gap']:.2f}% tp1={src['tp1']:.2f}", flush=True)
        print(f"  Calmar {src['calmar']:.2f} | Sharpe {src['sharpe']:.3f} | "
              f"Net R {src['net_r']:.1f} | DD {src['dd']:.1f}R | "
              f"R/yr {src['r_yr']:.1f}", flush=True)
        print("=" * 70, flush=True)
        rby = src.get("r_by_year", {})
        if rby:
            for y, r in sorted(rby.items()):
                flag = " <--" if r < 0 else ""
                print(f"    {y}: {r:>8.1f}R{flag}", flush=True)

    return results, ranked, clean


# ==============================================================================
# MAIN
# ==============================================================================

if __name__ == "__main__":
    t_global = time.time()

    print(flush=True)
    print("=" * 70, flush=True)
    print("  CL NY — FULL VARIABLE SWEEP + 4D GRID (Round 1)", flush=True)
    print("  Fresh start with corrected data. 1s magnifier.", flush=True)
    print("  Anchor: rr=2.5 | tp1=0.5 | stop=7.5% | gap=2.25%", flush=True)
    print("  Structural: ORB 15m | entry_end 13:00 | flat 15:50 | ATR 14", flush=True)
    print("=" * 70, flush=True)

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df = load_5m_data("CL_5m.csv")
    df_1m = load_1m_for_5m("CL_5m.csv")
    df_1s = load_1s_for_5m("CL_5m.csv")
    print(f"  5m: {len(df):,} bars ({df.index[0].date()} to {df.index[-1].date()})", flush=True)
    if df_1m is not None:
        print(f"  1m: {len(df_1m):,} bars", flush=True)
    if df_1s is not None:
        print(f"  1s: {len(df_1s):,} bars", flush=True)
    else:
        print("  1s: NOT FOUND — using 1m only", flush=True)
    print(f"  Loaded in {time.time() - t0:.1f}s", flush=True)

    # -- Anchor baseline -------------------------------------------------------

    print("\nRunning anchor baseline...", flush=True)
    t0 = time.time()
    anchor_m = run(ANCHOR)
    print(f"  Done in {time.time() - t0:.1f}s", flush=True)

    section("ANCHOR BASELINE (CL NY defaults)")
    print(f"  rr=2.5 | tp1=0.5 | stop=7.5% | gap=2.25% | ORB 15m | ATR 14 | both dir | 1s", flush=True)
    print(f"\n  {'Trades':<20s} {anchor_m['total_trades']:>12d}", flush=True)
    print(f"  {'Win Rate':<20s} {anchor_m['win_rate']:>11.1%}", flush=True)
    print(f"  {'PF':<20s} {anchor_m['profit_factor']:>12.2f}", flush=True)
    print(f"  {'Net R':<20s} {anchor_m['total_r']:>11.1f}R", flush=True)
    print(f"  {'R/yr':<20s} {r_per_year(anchor_m):>11.1f}R", flush=True)
    print(f"  {'Max DD':<20s} {anchor_m['max_drawdown_r']:>11.1f}R", flush=True)
    print(f"  {'Calmar':<20s} {anchor_m['calmar_ratio']:>12.2f}", flush=True)
    print(f"  {'Sharpe':<20s} {anchor_m['sharpe_ratio']:>12.3f}", flush=True)
    print(f"  {'Neg full years':<20s} {neg_years(anchor_m):>12d}", flush=True)
    rby = anchor_m.get("r_by_year", {})
    if rby:
        print(f"\n  R by year:", flush=True)
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)

    # -- Part A: Variable Sweeps -----------------------------------------------

    section("PART A: VARIABLE SWEEPS (12 dimensions)")
    t_part_a = time.time()

    sweep_stop()
    sweep_orb_window()
    sweep_atr_length()
    sweep_entry_end()
    sweep_flat_start()
    sweep_direction()
    sweep_strategy()
    sweep_rr()
    sweep_tp1()
    sweep_min_gap()
    sweep_dow()
    sweep_max_gap_points()

    elapsed_a = time.time() - t_part_a
    section(f"PART A COMPLETE — {elapsed_a:.0f}s ({elapsed_a/60:.1f} min)")

    # -- Part B: 4D Grid -------------------------------------------------------

    grid_results, grid_ranked, grid_clean = run_grid()

    # -- Final Summary ---------------------------------------------------------

    total_elapsed = time.time() - t_global

    print(flush=True)
    print("=" * 70, flush=True)
    print("  CL NY ROUND 1 COMPLETE", flush=True)
    print(f"  Total time: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min, "
          f"{total_elapsed/3600:.1f} hr)", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)
    print("  Next steps:", flush=True)
    print("    1. Review variable sweep winners — identify structural config", flush=True)
    print("    2. Update anchor to winning structural params", flush=True)
    print("    3. Re-run variable sweeps on updated anchor (if changed significantly)", flush=True)
    print("    4. Fine-tune grid around best combo", flush=True)
    print("    5. Run robust pipeline on final candidate", flush=True)
    print(flush=True)
