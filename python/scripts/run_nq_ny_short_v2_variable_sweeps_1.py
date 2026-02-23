#!/usr/bin/env python3
"""NQ NY Short v2 — Variable Sweeps R1.

Anchor: ORB 20m, orbstop=15%, orbgap=7%, rr=3.0, tp1=0.3, ATR=14,
        short-only, ICF=OFF, dual floors (10pt stop + 10pt tp1).
Calmar: 1.40 | 967 trades | 4 neg years (2016, 2017, 2019, 2023)

NOTE: Previous R1-R10 sweeps were corrupted by tp1=0.2 artifact.
This is a clean restart with dual floors. We test BOTH ATR-based
and ORB-based stops/gaps since the ORB convergence was also an
artifact of the tp1=0.2 optimization.

12 dimensions swept one at a time, all others held at anchor.
"""

import sys
import time
from dataclasses import replace
from datetime import datetime
from statistics import median

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = NQ
START_DATE = "2016-01-01"
DATA_YEARS = 10

# ── Anchor config ──
ANCHOR_SESSION = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:50",
    entry_start="09:50",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=5.0,
    min_gap_atr_pct=2.0,
    stop_orb_pct=15.0,
    min_gap_orb_pct=7.0,
    min_stop_points=10.0,
    min_tp1_points=10.0,
)

ANCHOR_CONFIG = StrategyConfig(
    sessions=(ANCHOR_SESSION,),
    instrument=NQ,
    strategy="continuation",
    use_bar_magnifier=True,
    risk_usd=5000.0,
    direction_filter="short",
    rr=3.0,
    tp1_ratio=0.3,
    atr_length=14,
    impulse_close_filter=False,
)

ANCHOR_DOW = set()  # no exclusion
ANCHOR_CALMAR = 1.40
ANCHOR_NEG = {"2016", "2017", "2019", "2023"}
ADOPTION_DELTA = 0.3


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / INSTRUMENT.min_tick for t in filled)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def run_one(df_5m, df_1m, df_1s, config, dow_excl=None, label=""):
    """Run backtest, return metrics dict or None if skip."""
    trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    if dow_excl:
        trades = apply_dow_filter(trades, dow_excl)
    m = compute_metrics(trades)
    med_ticks = median_stop_ticks(trades)
    neg = neg_year_set(m)
    r_yr = m["total_r"] / DATA_YEARS

    if med_ticks < 10:
        print(f"  {label:<35} SKIP (median stop {med_ticks:.0f} ticks < 10)")
        return None

    marker = " *" if m["calmar_ratio"] > 1.0 and m["profit_factor"] > 1.0 and len(neg) <= 3 else ""
    print(f"  {label:<35} {m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
          f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>5.1f} "
          f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>6.2f} {med_ticks:>5.0f}t "
          f"{len(neg):>2}{marker}")
    if marker:
        yr_str = " ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(m.get("r_by_year", {}).items()))
        print(f"    R/yr: {yr_str}")

    return {
        "label": label, "trades": m["total_trades"], "calmar": m["calmar_ratio"],
        "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"], "net_r": m["total_r"],
        "max_dd": m["max_drawdown_r"], "neg_years": neg, "med_ticks": med_ticks,
        "r_yr": r_yr,
    }


def hdr():
    print(f"  {'Config':<35} {'Trd':>5} {'WR':>5} {'PF':>5} {'Shrp':>6} {'NetR':>7} "
          f"{'R/yr':>5} {'MaxDD':>6} {'Calm':>6} {'MdSt':>5} {'NY':>2}")
    print(f"  {'─' * 105}")


def dim_header(n, name):
    print(f"\n{'=' * 80}")
    print(f"  DIM {n}: {name}")
    print(f"{'=' * 80}")
    hdr()


def main():
    print("NQ NY Short v2 — Variable Sweeps R1")
    print("=" * 80)
    print("  NOTE: Previous R1-R10 corrupted by tp1=0.2 artifact.")
    print("  This is a clean restart with dual 10pt floors.")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]")

    adoptions = []

    # ── Anchor reference ──
    print("\n  ANCHOR: orbstop=15%, orbgap=7%, rr=3.0, tp1=0.3, ATR=14, short, 20m ORB, Calmar=1.40")
    hdr()
    run_one(df_5m, df_1m, df_1s, ANCHOR_CONFIG, ANCHOR_DOW, "ANCHOR")

    # ═══════════════════════════════════════════════════════════════
    # DIM 1: Stop Mechanism — ATR-based vs ORB-based
    # ═══════════════════════════════════════════════════════════════
    dim_header(1, "Stop Mechanism (ATR-based vs ORB-based)")
    dim1 = []

    # ATR-based stops (zero out ORB stop fields)
    for stop_atr in [3.0, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0]:
        sess = replace(ANCHOR_SESSION, stop_orb_pct=0.0, stop_atr_pct=stop_atr)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ATR stop={stop_atr}%")
        if r:
            dim1.append(r)

    # ORB-based stops
    for orbstop in [5.0, 10.0, 12.5, 15.0, 17.5, 20.0, 25.0, 30.0]:
        sess = replace(ANCHOR_SESSION, stop_orb_pct=orbstop)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ORB stop={orbstop}%")
        if r:
            dim1.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 2: ORB Window
    # ═══════════════════════════════════════════════════════════════
    dim_header(2, "ORB Window")
    dim2 = []
    for label, orb_e, entry_s in [
        ("5m",  "09:35", "09:35"), ("10m", "09:40", "09:40"),
        ("15m", "09:45", "09:45"), ("20m", "09:50", "09:50"),
        ("25m", "09:55", "09:55"), ("30m", "10:00", "10:00"),
        ("45m", "10:15", "10:15"),
    ]:
        sess = replace(ANCHOR_SESSION, orb_end=orb_e, entry_start=entry_s)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ORB={label}")
        if r:
            dim2.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 3: ATR Length
    # ═══════════════════════════════════════════════════════════════
    dim_header(3, "ATR Length")
    dim3 = []
    for atr in [3, 5, 7, 10, 14, 20, 30, 50]:
        cfg = replace(ANCHOR_CONFIG, atr_length=atr)
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ATR={atr}")
        if r:
            dim3.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 4: Entry End Time
    # ═══════════════════════════════════════════════════════════════
    dim_header(4, "Entry End Time")
    dim4 = []
    for entry_end in ["10:30", "11:00", "11:30", "12:00", "13:00", "14:00", "15:00", "15:30"]:
        sess = replace(ANCHOR_SESSION, entry_end=entry_end)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"entry_end={entry_end}")
        if r:
            dim4.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 5: Flat Start Time
    # ═══════════════════════════════════════════════════════════════
    dim_header(5, "Flat Start Time")
    dim5 = []
    for flat_start in ["13:00", "13:30", "14:00", "14:30", "15:00", "15:30", "15:50"]:
        sess = replace(ANCHOR_SESSION, flat_start=flat_start)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"flat={flat_start}")
        if r:
            dim5.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 6: Direction
    # ═══════════════════════════════════════════════════════════════
    dim_header(6, "Direction")
    dim6 = []
    for direction in ["short", "long", "both"]:
        cfg = replace(ANCHOR_CONFIG, direction_filter=direction)
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"dir={direction}")
        if r:
            dim6.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 7: R:R Ratio
    # ═══════════════════════════════════════════════════════════════
    dim_header(7, "R:R Ratio")
    dim7 = []
    for rr in [1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 5.0]:
        cfg = replace(ANCHOR_CONFIG, rr=rr)
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"rr={rr}")
        if r:
            dim7.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 8: TP1 Ratio
    # ═══════════════════════════════════════════════════════════════
    dim_header(8, "TP1 Ratio")
    dim8 = []
    for tp1 in [0.2, 0.3, 0.4, 0.5, 0.6, 0.7]:
        cfg = replace(ANCHOR_CONFIG, tp1_ratio=tp1)
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"tp1={tp1}")
        if r:
            dim8.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 9: Gap Mechanism — ATR-based vs ORB-based
    # ═══════════════════════════════════════════════════════════════
    dim_header(9, "Gap Mechanism (ATR-based vs ORB-based)")
    dim9 = []

    # ATR-based gaps (zero out ORB gap, keep ORB stop)
    for gap_atr in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]:
        sess = replace(ANCHOR_SESSION, min_gap_orb_pct=0.0, min_gap_atr_pct=gap_atr)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ATR gap={gap_atr}%")
        if r:
            dim9.append(r)

    # ORB-based gaps
    for orbgap in [3.0, 5.0, 7.0, 9.0, 11.0, 15.0, 20.0]:
        sess = replace(ANCHOR_SESSION, min_gap_orb_pct=orbgap)
        cfg = replace(ANCHOR_CONFIG, sessions=(sess,))
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ORB gap={orbgap}%")
        if r:
            dim9.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 10: DOW Exclusion
    # ═══════════════════════════════════════════════════════════════
    dim_header(10, "DOW Exclusion")
    dim10 = []
    dow_options = [
        ("none", set()), ("excl Mon", {0}), ("excl Tue", {1}),
        ("excl Wed", {2}), ("excl Thu", {3}), ("excl Fri", {4}),
        ("excl M+F", {0, 4}), ("excl Th+F", {3, 4}),
    ]
    for label, dow_set in dow_options:
        r = run_one(df_5m, df_1m, df_1s, ANCHOR_CONFIG, dow_set, label)
        if r:
            r["dow_excl"] = dow_set
            dim10.append(r)

    # ═══════════════════════════════════════════════════════════════
    # DIM 11: Max Gap Points (post-filter)
    # ═══════════════════════════════════════════════════════════════
    dim_header(11, "Max Gap Points (post-filter)")
    dim11 = []
    all_trades = run_backtest(df_5m, ANCHOR_CONFIG, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    for max_gap in [0, 25, 50, 75, 100, 150]:
        if max_gap == 0:
            filtered = all_trades
            lbl = "maxgap=OFF"
        else:
            filtered = [t for t in all_trades if t.exit_type == 0 or abs(t.gap_size) <= max_gap]
            lbl = f"maxgap={max_gap}pt"

        m = compute_metrics(filtered)
        med_ticks = median_stop_ticks(filtered)
        neg = neg_year_set(m)
        r_yr = m["total_r"] / DATA_YEARS
        marker = " *" if m["calmar_ratio"] > 1.0 and m["profit_factor"] > 1.0 and len(neg) <= 3 else ""
        print(f"  {lbl:<35} {m['total_trades']:>5} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['sharpe_ratio']:>6.2f} {m['total_r']:>7.1f} {r_yr:>5.1f} "
              f"{m['max_drawdown_r']:>6.1f} {m['calmar_ratio']:>6.2f} {med_ticks:>5.0f}t "
              f"{len(neg):>2}{marker}")
        if marker:
            yr_str = " ".join(f"{yr}:{r:+.0f}" for yr, r in sorted(m.get("r_by_year", {}).items()))
            print(f"    R/yr: {yr_str}")
        dim11.append({
            "label": lbl, "trades": m["total_trades"], "calmar": m["calmar_ratio"],
            "pf": m["profit_factor"], "net_r": m["total_r"], "neg_years": neg,
            "med_ticks": med_ticks, "r_yr": r_yr,
        })

    # ═══════════════════════════════════════════════════════════════
    # DIM 12: ICF
    # ═══════════════════════════════════════════════════════════════
    dim_header(12, "Impulse Close Filter (ICF)")
    dim12 = []
    for icf in [False, True]:
        cfg = replace(ANCHOR_CONFIG, impulse_close_filter=icf)
        r = run_one(df_5m, df_1m, df_1s, cfg, ANCHOR_DOW, f"ICF={'ON' if icf else 'OFF'}")
        if r:
            dim12.append(r)

    # ═══════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print("  ADOPTION SUMMARY — R1")
    print(f"{'=' * 80}")
    print(f"\n  Anchor Calmar: {ANCHOR_CALMAR:.2f}")
    print(f"  Anchor neg years: {sorted(ANCHOR_NEG)}")
    print(f"  Adoption rule: Δ Calmar > +{ADOPTION_DELTA:.1f}, no new neg years, trades > 100, med stop >= 10t\n")

    all_dims = [
        ("1. Stop Mechanism", dim1), ("2. ORB Window", dim2), ("3. ATR Length", dim3),
        ("4. Entry End", dim4), ("5. Flat Start", dim5), ("6. Direction", dim6),
        ("7. R:R Ratio", dim7), ("8. TP1 Ratio", dim8), ("9. Gap Mechanism", dim9),
        ("10. DOW Excl", dim10), ("11. Max Gap Pts", dim11), ("12. ICF", dim12),
    ]

    print(f"  {'Dimension':<22} {'Best Value':<30} {'Calmar':>7} {'Δ':>6} {'NegYrs':>6} {'Adopt':>6}")
    print(f"  {'─' * 85}")

    for dim_name, results in all_dims:
        if not results:
            print(f"  {dim_name:<22} {'(no valid results)':<30}")
            continue

        best = max(results, key=lambda x: x["calmar"])
        delta = best["calmar"] - ANCHOR_CALMAR
        new_neg = best["neg_years"] - ANCHOR_NEG
        adopt = (
            delta > ADOPTION_DELTA
            and len(new_neg) == 0
            and best["trades"] > 100
            and best["med_ticks"] >= 10
        )

        print(f"  {dim_name:<22} {best['label']:<30} {best['calmar']:>7.2f} "
              f"{delta:>+5.2f} {len(best['neg_years']):>5} "
              f"{'YES' if adopt else 'no':>6}")

        if adopt:
            adoptions.append({
                "dim": dim_name, "label": best["label"],
                "calmar": best["calmar"], "delta": delta,
                "neg_years": best["neg_years"],
            })

    print(f"\n  Total adoptions: {len(adoptions)}")
    if adoptions:
        for a in adoptions:
            print(f"    {a['dim']}: {a['label']} (Δ+{a['delta']:.2f})")
        print(f"\n  → Need R2 sweep with updated anchor.")
    else:
        print(f"\n  → CONVERGED. Ready for grid sweep.")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed:.0f}s ({elapsed / 60:.1f}m)")


if __name__ == "__main__":
    main()
