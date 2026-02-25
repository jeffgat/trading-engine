#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 13a: re-validate config variables with new anchor.

Anchor: g=3.0 rr=2.25 tp1=0.7 stop=9.0% long-only 20m ORB entry 09:50-15:00

Variables not tested since the anchor changed:
  1. ORB window (5m to 30m) — last tested Round 3 with stop=10%, rr=2.0
  2. ATR length (5 to 30) — last tested Round 1 with stop=10%, rr=2.0
  3. Flat window (flat_start) — NEVER tested
  4. Max gap ATR % (upper FVG size filter) — NEVER tested
  5. Max gap points (upper FVG size filter) — NEVER tested
  6. DOW exclusion — last tested Round 2-3 with old base
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON, TUE, WED, THU, FRI, DOW_NAMES

START_DATE = "2015-01-01"
DATA_YEARS = 11

# Current anchor
ANCHOR = dict(
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=3.0,
    max_gap_atr_pct=0.0,
    max_gap_points=100.0,
)


def make_config(orb_end="09:50", entry_start=None, entry_end="15:00",
                flat_start="15:50", flat_end="16:00",
                stop=9.0, gap=3.0, max_gap_atr=0.0, max_gap_pts=100.0,
                atr_length=14):
    if entry_start is None:
        entry_start = orb_end  # entry starts when ORB ends
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=orb_end,
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start=flat_start,
        flat_end=flat_end,
        stop_atr_pct=stop,
        min_gap_atr_pct=gap,
        max_gap_points=max_gap_pts,
        max_gap_atr_pct=max_gap_atr,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=2.25,
        tp1_ratio=0.7,
        atr_length=atr_length,
        name="NQ NY Config Sweep R13a",
    )


from orb_backtest.config import SessionConfig


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return trades, compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>40} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*105}")
    print(f"  {title}")
    print(f"{'='*105}")
    print(HDR)
    print("-" * 105)


def print_row(i, label, m, marker=""):
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>40} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def main():
    print("NQ NY ORB — Round 13a: Config Variable Re-Validation")
    print("Anchor: g=3.0 rr=2.25 tp1=0.7 stop=9% long-only 20m ORB 09:50-15:00")
    print("=" * 105)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    best_per_sweep = {}

    # ── 0. BASELINE ──────────────────────────────────────────────────────
    print_header("0. BASELINE (current anchor)")
    config = make_config()
    _, m_base = run_and_metric(df_5m, df_1m, config)
    print_row(1, "g3.0 rr2.25 tp0.7 stop=9% 20m", m_base, " <-- anchor")
    print_year_breakdown(m_base)

    # ── 1. ORB WINDOW ────────────────────────────────────────────────────
    # orb_end determines ORB window size (start is always 09:30)
    orb_ends = [
        ("5m",  "09:35"),
        ("10m", "09:40"),
        ("15m", "09:45"),
        ("20m", "09:50"),
        ("25m", "09:55"),
        ("30m", "10:00"),
    ]
    print_header("1. ORB WINDOW (5m-30m)")
    best_calmar = -999
    for i, (label, orb_end) in enumerate(orb_ends, 1):
        config = make_config(orb_end=orb_end)
        _, m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if orb_end == "09:50" else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['orb'] = (label, orb_end, m)
        print_row(i, f"ORB {label} (end={orb_end})", m, marker)
        print_year_breakdown(m)
    bo = best_per_sweep['orb']
    print(f"\n  >> Best ORB: {bo[0]} (Calmar {bo[2]['calmar_ratio']:.2f})")

    # ── 2. ATR LENGTH ────────────────────────────────────────────────────
    atr_values = [5, 7, 10, 14, 20, 30]
    print_header("2. ATR LENGTH")
    best_calmar = -999
    for i, atr in enumerate(atr_values, 1):
        config = make_config(atr_length=atr)
        _, m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if atr == 14 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['atr'] = (atr, m)
        print_row(i, f"atr_length={atr}", m, marker)
        print_year_breakdown(m)
    ba = best_per_sweep['atr']
    print(f"\n  >> Best ATR length: {ba[0]} (Calmar {ba[1]['calmar_ratio']:.2f})")

    # ── 3. FLAT WINDOW ───────────────────────────────────────────────────
    # flat_start = when to force-close open positions. Currently 15:50.
    # Testing earlier flat times to see if cutting losers earlier helps DD
    flat_starts = ["15:00", "15:15", "15:30", "15:40", "15:50", "15:55"]
    print_header("3. FLAT WINDOW (flat_start: when to force-close)")
    best_calmar = -999
    for i, fs in enumerate(flat_starts, 1):
        config = make_config(flat_start=fs)
        _, m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if fs == "15:50" else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['flat'] = (fs, m)
        print_row(i, f"flat_start={fs}", m, marker)
        print_year_breakdown(m)
    bf = best_per_sweep['flat']
    print(f"\n  >> Best flat_start: {bf[0]} (Calmar {bf[1]['calmar_ratio']:.2f})")

    # ── 4. MAX GAP ATR % (upper FVG size filter) ─────────────────────────
    # Currently 0 (no limit). A max gap filter removes very wide FVGs
    # which tend to have wider stops and worse R:R
    max_gap_atr_values = [0.0, 8.0, 10.0, 12.0, 15.0, 18.0, 20.0, 25.0, 30.0]
    print_header("4. MAX GAP ATR % (upper FVG size filter, 0 = no limit)")
    best_calmar = -999
    for i, mg in enumerate(max_gap_atr_values, 1):
        config = make_config(max_gap_atr=mg)
        _, m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if mg == 0.0 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['max_gap_atr'] = (mg, m)
        label = "no limit" if mg == 0.0 else f"max_gap_atr={mg:.0f}%"
        print_row(i, label, m, marker)
        if mg == 0.0 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    bmga = best_per_sweep['max_gap_atr']
    print(f"\n  >> Best max_gap_atr: {'no limit' if bmga[0] == 0.0 else f'{bmga[0]:.0f}%'} "
          f"(Calmar {bmga[1]['calmar_ratio']:.2f})")

    # ── 5. MAX GAP POINTS (upper FVG size filter) ────────────────────────
    max_gap_pts_values = [0.0, 25.0, 50.0, 75.0, 100.0, 150.0, 200.0, 300.0]
    print_header("5. MAX GAP POINTS (upper FVG size filter, 0 = no limit)")
    best_calmar = -999
    for i, mgp in enumerate(max_gap_pts_values, 1):
        config = make_config(max_gap_pts=mgp)
        _, m = run_and_metric(df_5m, df_1m, config)
        marker = " <-- current" if mgp == 100.0 else ""
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['max_gap_pts'] = (mgp, m)
        label = "no limit" if mgp == 0.0 else f"max_gap_pts={mgp:.0f}"
        print_row(i, label, m, marker)
        if mgp == 100.0 or m['calmar_ratio'] == best_calmar:
            print_year_breakdown(m)
    bmgp = best_per_sweep['max_gap_pts']
    print(f"\n  >> Best max_gap_pts: {'no limit' if bmgp[0] == 0.0 else f'{bmgp[0]:.0f}'} "
          f"(Calmar {bmgp[1]['calmar_ratio']:.2f})")

    # ── 6. DOW EXCLUSION (post-trade filter) ─────────────────────────────
    print_header("6. DAY-OF-WEEK EXCLUSION")
    # First run the baseline trades once
    config = make_config()
    base_trades, m_all = run_and_metric(df_5m, df_1m, config)

    # No exclusion
    print_row(1, "no exclusion", m_all, " <-- current")
    print_year_breakdown(m_all)
    best_calmar = m_all['calmar_ratio']
    best_per_sweep['dow'] = ("none", m_all)

    # Exclude one day at a time
    for i, (day_int, day_name) in enumerate(DOW_NAMES.items(), 2):
        filtered = apply_dow_filter(base_trades, excluded_days={day_int})
        m = compute_metrics(filtered)
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['dow'] = (f"excl-{day_name}", m)
        print_row(i, f"excl-{day_name}", m)
        print_year_breakdown(m)

    # Exclude pairs
    pairs = [
        ({MON, FRI}, "excl-Mon+Fri"),
        ({THU, FRI}, "excl-Thu+Fri"),
        ({WED, THU}, "excl-Wed+Thu"),
    ]
    for j, (days, label) in enumerate(pairs, 7):
        filtered = apply_dow_filter(base_trades, excluded_days=days)
        m = compute_metrics(filtered)
        if m['calmar_ratio'] > best_calmar:
            best_calmar = m['calmar_ratio']
            best_per_sweep['dow'] = (label, m)
        print_row(j, label, m)
        print_year_breakdown(m)

    bd = best_per_sweep['dow']
    print(f"\n  >> Best DOW: {bd[0]} (Calmar {bd[1]['calmar_ratio']:.2f})")

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print(f"\n{'='*105}")
    print(f"  SUMMARY — Best per variable vs anchor")
    print(f"{'='*105}")
    base_calmar = m_base['calmar_ratio']
    print(f"  Anchor: Calmar {base_calmar:.2f}\n")
    print(f"  {'Variable':<18} {'Current':>12} {'Best':>12} {'Best Calmar':>12} {'Delta':>8}")
    print(f"  {'-'*65}")

    summary = [
        ("ORB window", "20m", best_per_sweep['orb'][0], best_per_sweep['orb'][2]),
        ("ATR length", "14", str(best_per_sweep['atr'][0]), best_per_sweep['atr'][1]),
        ("Flat start", "15:50", best_per_sweep['flat'][0], best_per_sweep['flat'][1]),
        ("Max gap ATR%", "no limit",
         "no limit" if best_per_sweep['max_gap_atr'][0] == 0.0 else f"{best_per_sweep['max_gap_atr'][0]:.0f}%",
         best_per_sweep['max_gap_atr'][1]),
        ("Max gap pts", "100",
         "no limit" if best_per_sweep['max_gap_pts'][0] == 0.0 else f"{best_per_sweep['max_gap_pts'][0]:.0f}",
         best_per_sweep['max_gap_pts'][1]),
        ("DOW exclusion", "none", best_per_sweep['dow'][0], best_per_sweep['dow'][1]),
    ]

    for var, current, best, m in summary:
        delta = m['calmar_ratio'] - base_calmar
        changed = " *" if str(current) != str(best) else ""
        print(f"  {var:<18} {current:>12} {best:>12} {m['calmar_ratio']:>12.2f} {delta:>+7.2f}{changed}")

    elapsed = time.time() - t_start
    print(f"\n{'='*105}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*105}")


if __name__ == "__main__":
    main()
