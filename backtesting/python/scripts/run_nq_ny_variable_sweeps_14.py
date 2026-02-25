#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 14: re-optimize shorts + combined L+S.

Round 8 tested combined L+S with old long params (rr=2.75, tp0.6, stop=10%).
The long anchor has since changed to rr=2.25, tp1=0.7, stop=9%.

This round:
  Phase A: Short-only sweep at stop=9% to find optimal short params
  Phase B: Combine best long + best short trade lists
  Phase C: Test whether combined Calmar justifies the DD increase

Long anchor: g=3.0 rr=2.25 tp1=0.7 stop=9.0% (16.5 R/yr, DD -10.6R, Calmar 17.17)
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11


def make_config(direction="long", gap=3.0, rr=2.25, tp1=0.7, stop=9.0,
                entry_end="15:00"):
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        stop_atr_pct=stop,
        min_gap_atr_pct=gap,
        max_gap_points=100.0,
    )
    return StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction,
        rr=rr,
        tp1_ratio=tp1,
        atr_length=14,
        name=f"NQ NY R14 {direction}",
    )


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return trades, compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>45} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*110}")
    print(f"  {title}")
    print(f"{'='*110}")
    print(HDR)
    print("-" * 110)


def print_row(i, label, m, marker=""):
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>45} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
        f"{m['profit_factor']:>6.2f} {m['total_r']:>7.1f} "
        f"{r_per_yr:>6.1f} {m['max_drawdown_r']:>7.1f} {m['calmar_ratio']:>7.2f} "
        f"{m['avg_r']:>7.4f}{marker}"
    )


def print_year_breakdown(m):
    if "r_by_year" in m:
        years = sorted(m["r_by_year"].items())
        yr_str = "  ".join(f"{yr}:{r:+.0f}" for yr, r in years)
        print(f"    R by year: {yr_str}")


def combine_trades(long_trades, short_trades):
    """Merge long and short trade lists, keeping only one trade per session-day.

    When both a long and short exist on the same day, keep the first to fill
    (earlier fill_bar). This matches the engine's one-trade-per-day rule.
    """
    # Filter to filled trades only
    long_filled = [t for t in long_trades if t.exit_type != EXIT_NO_FILL]
    short_filled = [t for t in short_trades if t.exit_type != EXIT_NO_FILL]

    # Index by date
    long_by_date = {t.date: t for t in long_filled}
    short_by_date = {t.date: t for t in short_filled}

    all_dates = sorted(set(long_by_date.keys()) | set(short_by_date.keys()))

    combined = []
    for d in all_dates:
        lt = long_by_date.get(d)
        st = short_by_date.get(d)

        if lt and st:
            # Both exist — keep the first to fill
            if lt.fill_bar <= st.fill_bar:
                combined.append(lt)
            else:
                combined.append(st)
        elif lt:
            combined.append(lt)
        elif st:
            combined.append(st)

    return sorted(combined, key=lambda t: t.date)


def main():
    print("NQ NY ORB — Round 14: Re-Optimize Shorts + Combined L+S")
    print("Long anchor: g=3.0 rr=2.25 tp1=0.7 stop=9% (16.5 R/yr, DD -10.6R)")
    print("=" * 110)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ── 0. LONG BASELINE ─────────────────────────────────────────────────
    print_header("0. LONG BASELINE (current anchor)")
    long_config = make_config(direction="long")
    long_trades, m_long = run_and_metric(df_5m, df_1m, long_config)
    print_row(1, "LONG g3.0 rr2.25 tp0.7 stop=9%", m_long, " <-- anchor")
    print_year_breakdown(m_long)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE A: SHORT-ONLY OPTIMIZATION AT STOP=9%
    # ══════════════════════════════════════════════════════════════════════

    # A1: Short RR sweep (shorts historically need lower RR)
    rr_values = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0]
    print_header("A1. SHORT-ONLY: RR SWEEP (tp1=0.5, gap=3.0, stop=9%)")
    best_short_calmar = -999
    best_short_rr = None
    for i, rr in enumerate(rr_values, 1):
        config = make_config(direction="short", rr=rr, tp1=0.5)
        _, m = run_and_metric(df_5m, df_1m, config)
        if m['calmar_ratio'] > best_short_calmar:
            best_short_calmar = m['calmar_ratio']
            best_short_rr = rr
        print_row(i, f"SHORT rr={rr:.2f}", m)
        print_year_breakdown(m)
    print(f"\n  >> Best short RR: {best_short_rr:.2f} (Calmar {best_short_calmar:.2f})")

    # A2: Short TP1 sweep at best RR
    tp1_values = [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    print_header(f"A2. SHORT-ONLY: TP1 SWEEP (rr={best_short_rr:.2f}, gap=3.0, stop=9%)")
    best_short_tp1_calmar = -999
    best_short_tp1 = None
    for i, tp1 in enumerate(tp1_values, 1):
        config = make_config(direction="short", rr=best_short_rr, tp1=tp1)
        _, m = run_and_metric(df_5m, df_1m, config)
        if m['calmar_ratio'] > best_short_tp1_calmar:
            best_short_tp1_calmar = m['calmar_ratio']
            best_short_tp1 = tp1
        print_row(i, f"SHORT rr={best_short_rr:.2f} tp1={tp1:.1f}", m)
        print_year_breakdown(m)
    print(f"\n  >> Best short TP1: {best_short_tp1:.2f} (Calmar {best_short_tp1_calmar:.2f})")

    # A3: Short GAP sweep at best RR + TP1
    gap_values = [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    print_header(f"A3. SHORT-ONLY: GAP SWEEP (rr={best_short_rr:.2f}, tp1={best_short_tp1:.2f}, stop=9%)")
    best_short_gap_calmar = -999
    best_short_gap = None
    for i, gap in enumerate(gap_values, 1):
        config = make_config(direction="short", rr=best_short_rr, tp1=best_short_tp1, gap=gap)
        _, m = run_and_metric(df_5m, df_1m, config)
        if m['calmar_ratio'] > best_short_gap_calmar:
            best_short_gap_calmar = m['calmar_ratio']
            best_short_gap = gap
        print_row(i, f"SHORT g={gap:.1f} rr={best_short_rr:.2f} tp1={best_short_tp1:.2f}", m)
        print_year_breakdown(m)
    print(f"\n  >> Best short gap: {best_short_gap:.1f}% (Calmar {best_short_gap_calmar:.2f})")

    # A4: Short STOP sweep at best RR + TP1 + GAP
    stop_values = [6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0, 14.0]
    print_header(f"A4. SHORT-ONLY: STOP SWEEP (rr={best_short_rr:.2f}, tp1={best_short_tp1:.2f}, gap={best_short_gap:.1f})")
    best_short_stop_calmar = -999
    best_short_stop = None
    for i, stop in enumerate(stop_values, 1):
        config = make_config(direction="short", rr=best_short_rr, tp1=best_short_tp1,
                             gap=best_short_gap, stop=stop)
        _, m = run_and_metric(df_5m, df_1m, config)
        if m['calmar_ratio'] > best_short_stop_calmar:
            best_short_stop_calmar = m['calmar_ratio']
            best_short_stop = stop
        print_row(i, f"SHORT stop={stop:.0f}%", m)
        print_year_breakdown(m)
    print(f"\n  >> Best short stop: {best_short_stop:.0f}% (Calmar {best_short_stop_calmar:.2f})")

    # A5: Short ENTRY END sweep
    entry_ends = ["12:00", "13:00", "14:00", "15:00"]
    print_header(f"A5. SHORT-ONLY: ENTRY END SWEEP")
    best_short_ee_calmar = -999
    best_short_ee = None
    for i, ee in enumerate(entry_ends, 1):
        config = make_config(direction="short", rr=best_short_rr, tp1=best_short_tp1,
                             gap=best_short_gap, stop=best_short_stop, entry_end=ee)
        _, m = run_and_metric(df_5m, df_1m, config)
        if m['calmar_ratio'] > best_short_ee_calmar:
            best_short_ee_calmar = m['calmar_ratio']
            best_short_ee = ee
        print_row(i, f"SHORT end={ee}", m)
        print_year_breakdown(m)
    print(f"\n  >> Best short entry_end: {best_short_ee} (Calmar {best_short_ee_calmar:.2f})")

    # ── Best short config summary
    print(f"\n{'='*110}")
    print(f"  BEST SHORT CONFIG:")
    print(f"  rr={best_short_rr:.2f}, tp1={best_short_tp1:.2f}, gap={best_short_gap:.1f}%, "
          f"stop={best_short_stop:.0f}%, entry_end={best_short_ee}")
    print(f"{'='*110}")

    best_short_config = make_config(
        direction="short", rr=best_short_rr, tp1=best_short_tp1,
        gap=best_short_gap, stop=best_short_stop, entry_end=best_short_ee,
    )
    short_trades, m_short = run_and_metric(df_5m, df_1m, best_short_config)
    print_row(1, "BEST SHORT", m_short)
    print_year_breakdown(m_short)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE B: COMBINED L+S WITH INDEPENDENT PARAMS
    # ══════════════════════════════════════════════════════════════════════
    print_header("PHASE B: COMBINED LONG + SHORT (independent params)")

    # B1: Best long + best short
    combined = combine_trades(long_trades, short_trades)
    m_combined = compute_metrics(combined)
    print_row(1, "COMBINED: best L + best S", m_combined)
    print_year_breakdown(m_combined)

    # B2: Long-only reference
    print_row(2, "LONG ONLY (reference)", m_long, " <-- anchor")
    print_year_breakdown(m_long)

    # B3: Short-only reference
    print_row(3, "SHORT ONLY (reference)", m_short)
    print_year_breakdown(m_short)

    # B4: Same-params both direction at long anchor settings
    both_config = make_config(direction="both")
    _, m_both = run_and_metric(df_5m, df_1m, both_config)
    print_row(4, "BOTH (same params as long anchor)", m_both)
    print_year_breakdown(m_both)

    # B5: Test a few short RR variants combined with the long anchor
    print_header("PHASE B2: COMBINED — varying short RR (long anchor fixed)")
    short_rr_tests = [1.0, 1.25, 1.5, 1.75, 2.0, 2.25]
    for i, srr in enumerate(short_rr_tests, 1):
        s_config = make_config(
            direction="short", rr=srr, tp1=best_short_tp1,
            gap=best_short_gap, stop=best_short_stop, entry_end=best_short_ee,
        )
        s_trades, _ = run_and_metric(df_5m, df_1m, s_config)
        comb = combine_trades(long_trades, s_trades)
        m_comb = compute_metrics(comb)
        marker = " <-- best short RR" if abs(srr - best_short_rr) < 0.01 else ""
        print_row(i, f"L(anchor) + S(rr={srr:.2f})", m_comb, marker)
        print_year_breakdown(m_comb)

    # ══════════════════════════════════════════════════════════════════════
    # PHASE C: CALMAR COMPARISON
    # ══════════════════════════════════════════════════════════════════════
    print(f"\n{'='*110}")
    print(f"  PHASE C: IS COMBINED WORTH IT?")
    print(f"{'='*110}")
    print(f"\n  {'Config':<40s} {'R/yr':>7s} {'DD':>7s} {'Calmar':>8s} {'Trades':>7s}")
    print(f"  {'-'*72}")

    configs_summary = [
        ("Long only (anchor)", m_long),
        ("Short only (best)", m_short),
        ("Combined L+S (independent)", m_combined),
        ("Both direction (same params)", m_both),
    ]

    for label, m in configs_summary:
        ryr = m['total_r'] / DATA_YEARS
        print(f"  {label:<40s} {ryr:>7.1f} {m['max_drawdown_r']:>7.1f} "
              f"{m['calmar_ratio']:>8.2f} {m['total_trades']:>7d}")

    # The key question: does R/yr increase proportionally more than DD?
    long_ryr = m_long['total_r'] / DATA_YEARS
    comb_ryr = m_combined['total_r'] / DATA_YEARS
    long_dd = abs(m_long['max_drawdown_r'])
    comb_dd = abs(m_combined['max_drawdown_r'])

    ryr_pct_gain = (comb_ryr - long_ryr) / long_ryr * 100
    dd_pct_gain = (comb_dd - long_dd) / long_dd * 100

    print(f"\n  R/yr change: {long_ryr:.1f} → {comb_ryr:.1f} ({ryr_pct_gain:+.0f}%)")
    print(f"  DD change:   {-long_dd:.1f} → {-comb_dd:.1f} ({dd_pct_gain:+.0f}%)")
    print(f"  Calmar:      {m_long['calmar_ratio']:.2f} → {m_combined['calmar_ratio']:.2f}")

    if ryr_pct_gain > dd_pct_gain:
        print(f"\n  >> R/yr grew faster than DD — combined is WORTH considering")
    else:
        print(f"\n  >> DD grew faster than R/yr — long-only is BETTER risk-adjusted")

    elapsed = time.time() - t_start
    print(f"\n{'='*110}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*110}")


if __name__ == "__main__":
    main()
