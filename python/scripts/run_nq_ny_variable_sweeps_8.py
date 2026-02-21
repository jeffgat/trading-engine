#!/usr/bin/env python3
"""NQ NY ORB — Variable sweeps round 8: separate short-only optimization + combined.

Hypothesis: shorts drag down Calmar when forced to use long-optimized params.
If we optimize short params independently, then merge long+short trade lists,
we may get higher R/yr without proportional DD increase.

Phase A: Short-only sweep (independent optimization)
  - gap: 1.0, 1.5, 2.0, 2.5, 3.0
  - rr: 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0
  - tp1: 0.3, 0.4, 0.5, 0.6
  - stop: 7.5, 10.0, 12.5
  - entry_end: 12:00, 13:00, 14:00, 15:00

Phase B: Combine best short configs with top long configs
  - Merge trade lists, compute combined metrics
  - Compare combined vs long-only and vs same-params-both

Base long: 20m ORB, gap=3%, rr=2.0-2.75, tp1=0.4-0.5, stop=10%, magnifier
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import NY_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

START_DATE = "2015-01-01"
DATA_YEARS = 11

NY_20M = replace(
    NY_SESSION,
    orb_end="09:50",
    entry_start="09:50",
)


def make_config(entry_start="09:50", entry_end="15:00", gap=3.0,
                rr=2.0, tp1=0.5, stop=10.0, direction="long", **extra):
    sess = replace(NY_20M,
                   entry_start=entry_start,
                   entry_end=entry_end,
                   min_gap_atr_pct=gap,
                   stop_atr_pct=stop)
    config = StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter=direction,
        rr=rr,
        tp1_ratio=tp1,
        name="NQ NY Short Opt",
    )
    if extra:
        config = with_overrides(config, **extra)
    return config


def run_and_metric(df_5m, df_1m, config):
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    return trades, compute_metrics(trades)


HDR = (
    f"{'#':>3} {'Config':>50} {'Trades':>7} {'WR':>6} {'PF':>6} "
    f"{'Net R':>7} {'R/yr':>6} {'MaxDD':>7} {'Calmar':>7} {'R/trd':>7}"
)


def print_header(title):
    print(f"\n{'='*115}")
    print(f"  {title}")
    print(f"{'='*115}")
    print(HDR)
    print("-" * 115)


def print_row(i, label, m, marker=""):
    r_per_yr = m['total_r'] / DATA_YEARS
    print(
        f"{i:>3} {label:>50} {m['total_trades']:>7} {m['win_rate']:>5.1%} "
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
    print("NQ NY ORB — Round 8: Separate Short Optimization + Combined")
    print("=" * 115)

    print("\nLoading data...", flush=True)
    t_start = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} [{time.time() - t_start:.1f}s]")

    # ═══════════════════════════════════════════════════════════════════════
    #  PHASE A: SHORT-ONLY SWEEPS
    # ═══════════════════════════════════════════════════════════════════════

    # ── A1. SHORT RR × GAP GRID ─────────────────────────────────────────
    gaps = [1.0, 1.5, 2.0, 2.5, 3.0]
    rrs = [1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0]
    short_results = []

    print_header(f"A1. SHORT-ONLY: GAP × RR (tp1=0.5, stop=10%, end=15:00) — {len(gaps)*len(rrs)} combos")
    idx = 1
    for gap in gaps:
        for rr in rrs:
            config = make_config(rr=rr, gap=gap, direction="short")
            trades, m = run_and_metric(df_5m, df_1m, config)
            label = f"short g={gap} rr={rr:.2f}"
            r_yr = m['total_r'] / DATA_YEARS
            short_results.append({
                'label': label, 'gap': gap, 'rr': rr, 'tp1': 0.5,
                'stop': 10.0, 'entry_end': '15:00',
                'trades': trades, 'metrics': m, 'r_yr': r_yr,
            })
            print_row(idx, label, m)
            idx += 1
        print()

    # ── A2. SHORT TP1 SWEEP (with best gap/rr from A1) ──────────────────
    # Sort A1 by Calmar to find best short gap/rr
    a1_positive = [r for r in short_results if r['metrics']['total_r'] > 0]
    if a1_positive:
        a1_by_calmar = sorted(a1_positive, key=lambda x: x['metrics']['calmar_ratio'], reverse=True)
        best_short_gap = a1_by_calmar[0]['gap']
        best_short_rr = a1_by_calmar[0]['rr']
    else:
        # fallback
        a1_by_calmar = sorted(short_results, key=lambda x: x['r_yr'], reverse=True)
        best_short_gap = a1_by_calmar[0]['gap']
        best_short_rr = a1_by_calmar[0]['rr']

    print(f"\n  >> Best short from A1: gap={best_short_gap}%, rr={best_short_rr}")

    tp1s = [0.3, 0.4, 0.5, 0.6, 0.7]
    print_header(f"A2. SHORT-ONLY: TP1 SWEEP (gap={best_short_gap}%, rr={best_short_rr})")
    for i, tp1 in enumerate(tp1s, 1):
        config = make_config(rr=best_short_rr, gap=best_short_gap, tp1=tp1, direction="short")
        trades, m = run_and_metric(df_5m, df_1m, config)
        label = f"short g={best_short_gap} rr={best_short_rr} tp1={tp1}"
        r_yr = m['total_r'] / DATA_YEARS
        short_results.append({
            'label': label, 'gap': best_short_gap, 'rr': best_short_rr,
            'tp1': tp1, 'stop': 10.0, 'entry_end': '15:00',
            'trades': trades, 'metrics': m, 'r_yr': r_yr,
        })
        print_row(i, label, m)

    # ── A3. SHORT STOP SWEEP ────────────────────────────────────────────
    stops = [7.5, 10.0, 12.5, 15.0]
    print_header(f"A3. SHORT-ONLY: STOP SWEEP (gap={best_short_gap}%, rr={best_short_rr})")
    for i, stop in enumerate(stops, 1):
        config = make_config(rr=best_short_rr, gap=best_short_gap, stop=stop, direction="short")
        trades, m = run_and_metric(df_5m, df_1m, config)
        label = f"short g={best_short_gap} rr={best_short_rr} stop={stop}%"
        r_yr = m['total_r'] / DATA_YEARS
        short_results.append({
            'label': label, 'gap': best_short_gap, 'rr': best_short_rr,
            'tp1': 0.5, 'stop': stop, 'entry_end': '15:00',
            'trades': trades, 'metrics': m, 'r_yr': r_yr,
        })
        print_row(i, label, m)

    # ── A4. SHORT ENTRY END SWEEP ───────────────────────────────────────
    ends = ["11:00", "12:00", "13:00", "14:00", "15:00"]
    print_header(f"A4. SHORT-ONLY: ENTRY END SWEEP (gap={best_short_gap}%, rr={best_short_rr})")
    for i, ee in enumerate(ends, 1):
        config = make_config(rr=best_short_rr, gap=best_short_gap, entry_end=ee, direction="short")
        trades, m = run_and_metric(df_5m, df_1m, config)
        label = f"short g={best_short_gap} rr={best_short_rr} end={ee}"
        r_yr = m['total_r'] / DATA_YEARS
        short_results.append({
            'label': label, 'gap': best_short_gap, 'rr': best_short_rr,
            'tp1': 0.5, 'stop': 10.0, 'entry_end': ee,
            'trades': trades, 'metrics': m, 'r_yr': r_yr,
        })
        print_row(i, label, m)

    # ── A5. TOP 10 SHORT CONFIGS ────────────────────────────────────────
    print_header("A5. TOP 10 SHORT CONFIGS BY CALMAR (positive R only)")
    short_positive = [r for r in short_results if r['metrics']['total_r'] > 0]
    short_by_calmar = sorted(short_positive, key=lambda x: x['metrics']['calmar_ratio'], reverse=True)
    for i, r in enumerate(short_by_calmar[:10], 1):
        print_row(i, r['label'], r['metrics'])
        print_year_breakdown(r['metrics'])

    # ═══════════════════════════════════════════════════════════════════════
    #  PHASE B: COMBINE BEST SHORT + BEST LONG
    # ═══════════════════════════════════════════════════════════════════════

    # Top long configs from Round 6
    long_configs = [
        ("L: g3 rr2.0 tp0.5",  3.0, 2.0,  0.5, 10.0, "15:00"),
        ("L: g3 rr2.5 tp0.4",  3.0, 2.5,  0.4, 10.0, "15:00"),
        ("L: g3 rr2.5 tp0.5",  3.0, 2.5,  0.5, 10.0, "15:00"),
        ("L: g3 rr2.75 tp0.5", 3.0, 2.75, 0.5, 10.0, "15:00"),
        ("L: g3 rr3.0 tp0.3",  3.0, 3.0,  0.3, 10.0, "15:00"),
    ]

    # Take top 5 short configs
    top_shorts = short_by_calmar[:5] if len(short_by_calmar) >= 5 else short_by_calmar

    # Run all long configs and cache trades
    print_header("B1. LONG CONFIGS (reference)")
    long_cache = []
    for i, (l_label, l_gap, l_rr, l_tp1, l_stop, l_ee) in enumerate(long_configs, 1):
        config = make_config(rr=l_rr, gap=l_gap, tp1=l_tp1, stop=l_stop, entry_end=l_ee, direction="long")
        trades, m = run_and_metric(df_5m, df_1m, config)
        long_cache.append((l_label, trades, m))
        print_row(i, l_label, m)
        print_year_breakdown(m)

    # ── B2. COMBINED (long trades + short trades merged) ────────────────
    print_header(f"B2. COMBINED: BEST LONG + BEST SHORT (merged trade lists)")
    idx = 1
    combined_results = []
    for l_label, l_trades, l_m in long_cache:
        for s_res in top_shorts:
            s_label = s_res['label']
            s_trades = s_res['trades']
            # Merge and sort by date
            merged = sorted(l_trades + s_trades, key=lambda t: t.date)
            cm = compute_metrics(merged)
            combo_label = f"{l_label} + {s_label}"
            r_yr = cm['total_r'] / DATA_YEARS
            combined_results.append((combo_label, cm, r_yr))
            print_row(idx, combo_label, cm)
            idx += 1
        print()

    # ── B3. COMBINED TOP 10 BY CALMAR ───────────────────────────────────
    print_header("B3. TOP 10 COMBINED BY CALMAR")
    combined_by_calmar = sorted(combined_results, key=lambda x: x[1]['calmar_ratio'], reverse=True)
    for i, (label, m, r_yr) in enumerate(combined_by_calmar[:10], 1):
        print_row(i, label, m)
        print_year_breakdown(m)

    # ── B4. COMBINED TOP 10 BY R/YEAR ───────────────────────────────────
    print_header("B4. TOP 10 COMBINED BY R/YEAR")
    combined_by_ryr = sorted(combined_results, key=lambda x: x[2], reverse=True)
    for i, (label, m, r_yr) in enumerate(combined_by_ryr[:10], 1):
        print_row(i, label, m)
        print_year_breakdown(m)

    # ── B5. COMPARE: LONG-ONLY vs COMBINED vs SAME-PARAMS-BOTH ─────────
    # For each long config, show: long-only, best combined, same-params-both
    print_header("B5. COMPARISON: LONG vs COMBINED vs BOTH (same params)")
    idx = 1
    for l_label, l_trades, l_m in long_cache:
        # Long only
        print_row(idx, f"[LONG] {l_label}", l_m)
        print_year_breakdown(l_m)
        idx += 1

        # Best combined for this long
        best_combo_for_long = None
        best_combo_calmar = -999
        for combo_label, cm, r_yr in combined_results:
            if combo_label.startswith(l_label) and cm['calmar_ratio'] > best_combo_calmar:
                best_combo_for_long = (combo_label, cm)
                best_combo_calmar = cm['calmar_ratio']
        if best_combo_for_long:
            print_row(idx, f"[COMB] {best_combo_for_long[0]}", best_combo_for_long[1])
            print_year_breakdown(best_combo_for_long[1])
            idx += 1

        # Same params both direction
        # Extract params from l_label
        l_cfg_idx = long_configs[[c[0] for c in long_configs].index(l_label)]
        _, l_gap, l_rr, l_tp1, l_stop, l_ee = l_cfg_idx
        config = make_config(rr=l_rr, gap=l_gap, tp1=l_tp1, stop=l_stop,
                             entry_end=l_ee, direction="both")
        _, bm = run_and_metric(df_5m, df_1m, config)
        print_row(idx, f"[BOTH] both g={l_gap} rr={l_rr} tp1={l_tp1}", bm)
        print_year_breakdown(bm)
        idx += 1
        print()

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print(f"\n{'='*115}")
    print(f"  SUMMARY")
    print(f"{'='*115}")

    if short_by_calmar:
        bs = short_by_calmar[0]
        print(f"\n  Best short:      {bs['label']:>50}  "
              f"R/yr={bs['r_yr']:.1f}  DD={bs['metrics']['max_drawdown_r']:.1f}  "
              f"Calmar={bs['metrics']['calmar_ratio']:.2f}")

    if combined_by_calmar:
        bc = combined_by_calmar[0]
        print(f"  Best combined:   {bc[0]:>50}  "
              f"R/yr={bc[2]:.1f}  DD={bc[1]['max_drawdown_r']:.1f}  "
              f"Calmar={bc[1]['calmar_ratio']:.2f}")

    if combined_by_ryr:
        br = combined_by_ryr[0]
        print(f"  Best R/yr combo: {br[0]:>50}  "
              f"R/yr={br[2]:.1f}  DD={br[1]['max_drawdown_r']:.1f}  "
              f"Calmar={br[1]['calmar_ratio']:.2f}")

    # Best long reference
    best_long = max(long_cache, key=lambda x: x[2]['calmar_ratio'])
    print(f"  Best long ref:   {best_long[0]:>50}  "
          f"R/yr={best_long[2]['total_r']/DATA_YEARS:.1f}  DD={best_long[2]['max_drawdown_r']:.1f}  "
          f"Calmar={best_long[2]['calmar_ratio']:.2f}")

    elapsed = time.time() - t_start
    print(f"\n{'='*115}")
    print(f"  ALL SWEEPS COMPLETE — {elapsed:.0f}s ({elapsed / 60:.1f}m)")
    print(f"{'='*115}")


if __name__ == "__main__":
    main()
