#!/usr/bin/env python3
"""NQ NY Short v2 — Overnight Mega Grid.

Comprehensive grid covering all key dimensions in one shot.
Based on partial R1 findings:
  - flat=13:00 is a game-changer (Calmar 1.40→3.10)
  - ORB=25m better than 20m (1.40→1.75)
  - entry_end=11:00 strong but low trades (Calmar 2.67)
  - ATR length insensitive (fix at 14)
  - ATR-based stops weaker than ORB-based

Grid structure:
  Phase 1: Main grid (~1,800 combos, ~7.5 hours)
    - ORB window: 20m, 25m, 30m
    - orbstop: 10%, 15%, 20%
    - entry_end × flat_start (constrained: entry_end ≤ flat_start)
    - rr: 2.0, 2.5, 3.0, 3.5, 4.0
    - tp1: 0.3, 0.4, 0.5, 0.6

  Phase 2: Refinement on top 30 (~30 min)
    - ICF ON vs OFF
    - DOW exclusions (post-filter, fast)
    - orbgap variants (5%, 7%, 10%)

All with dual 10pt floors (min_stop=10, min_tp1=10).
"""

import sys
import time
from collections import Counter
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


def median_stop_ticks(trades):
    filled = [t for t in trades if t.risk_points > 0]
    if not filled:
        return 0.0
    return median(t.risk_points / INSTRUMENT.min_tick for t in filled)


def neg_year_set(m):
    current_year = str(datetime.now().year)
    return {yr for yr, r in m.get("r_by_year", {}).items() if r < 0 and str(yr) != current_year}


def build_combos():
    """Generate all grid combos with entry_end <= flat_start constraint."""
    combos = []

    # Flat × entry_end pairs (entry_end must be <= flat_start to be meaningful)
    flat_entry_pairs = [
        ("13:00", ["11:00", "12:00", "13:00"]),
        ("14:00", ["11:00", "13:00", "14:00"]),
        ("15:00", ["13:00", "15:00"]),
        ("15:50", ["13:00", "15:00"]),
    ]

    orb_windows = [
        ("20m", "09:50", "09:50"),  # (label, orb_end, entry_start)
        ("25m", "09:55", "09:55"),
        ("30m", "10:00", "10:00"),
    ]

    orbstops = [10.0, 15.0, 20.0]
    rrs = [2.0, 2.5, 3.0, 3.5, 4.0]
    tp1s = [0.3, 0.4, 0.5, 0.6]

    for flat_start, entry_ends in flat_entry_pairs:
        for entry_end in entry_ends:
            for orb_label, orb_end, entry_start in orb_windows:
                for orbstop in orbstops:
                    for rr in rrs:
                        for tp1 in tp1s:
                            combos.append({
                                "orb_label": orb_label,
                                "orb_end": orb_end,
                                "entry_start": entry_start,
                                "entry_end": entry_end,
                                "flat_start": flat_start,
                                "orbstop": orbstop,
                                "rr": rr,
                                "tp1": tp1,
                            })
    return combos


def run_combo(df_5m, df_1m, df_1s, combo):
    """Run a single grid combo and return metrics dict."""
    sess = SessionConfig(
        name="NY",
        orb_start="09:30",
        orb_end=combo["orb_end"],
        entry_start=combo["entry_start"],
        entry_end=combo["entry_end"],
        flat_start=combo["flat_start"],
        flat_end="16:00",
        stop_atr_pct=5.0,
        min_gap_atr_pct=2.0,
        stop_orb_pct=combo["orbstop"],
        min_gap_orb_pct=7.0,
        min_stop_points=10.0,
        min_tp1_points=10.0,
    )

    cfg = StrategyConfig(
        sessions=(sess,),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="short",
        rr=combo["rr"],
        tp1_ratio=combo["tp1"],
        atr_length=14,
        impulse_close_filter=False,
    )

    trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    m = compute_metrics(trades)
    med_ticks = median_stop_ticks(trades)
    neg = neg_year_set(m)

    label = (f"ORB={combo['orb_label']} os={combo['orbstop']:.0f}% "
             f"ee={combo['entry_end']} fl={combo['flat_start']} "
             f"rr={combo['rr']} tp1={combo['tp1']}")

    return {
        "label": label,
        "combo": combo,
        "trades": m["total_trades"],
        "wr": m["win_rate"],
        "pf": m["profit_factor"],
        "sharpe": m["sharpe_ratio"],
        "net_r": m["total_r"],
        "r_yr": m["total_r"] / DATA_YEARS,
        "max_dd": m["max_drawdown_r"],
        "calmar": m["calmar_ratio"],
        "med_ticks": med_ticks,
        "neg_years": neg,
        "n_neg": len(neg),
        "r_by_year": m.get("r_by_year", {}),
        "raw_trades": trades,
        "config": cfg,
        "session": sess,
    }


def print_top(results, title, n=30, filter_fn=None):
    """Print top N results by Calmar."""
    filtered = [r for r in results if filter_fn(r)] if filter_fn else results
    if not filtered:
        print(f"\n  {title}: no results")
        return filtered

    sorted_r = sorted(filtered, key=lambda x: x["calmar"], reverse=True)[:n]

    print(f"\n  {title} (top {min(n, len(sorted_r))} of {len(filtered)})")
    print(f"  {'#':>3} {'Config':<55} {'Trd':>5} {'WR':>5} {'PF':>5} "
          f"{'Shrp':>6} {'NetR':>6} {'R/yr':>5} {'MaxDD':>6} {'Calm':>6} {'NY':>2}")
    print(f"  {'─' * 115}")

    for i, r in enumerate(sorted_r):
        print(f"  {i+1:>3} {r['label']:<55} {r['trades']:>5} {r['wr']:>5.1%} "
              f"{r['pf']:>5.2f} {r['sharpe']:>6.2f} {r['net_r']:>6.1f} "
              f"{r['r_yr']:>5.1f} {r['max_dd']:>6.1f} {r['calmar']:>6.2f} {r['n_neg']:>2}")

    # Print R by year for top 5
    print(f"\n  R by year for top 5:")
    for i, r in enumerate(sorted_r[:5]):
        yr_str = " ".join(f"{yr}:{v:+.0f}" for yr, v in sorted(r["r_by_year"].items()))
        print(f"    #{i+1}: {yr_str}")

    return sorted_r


def main():
    print("NQ NY Short v2 — Overnight Mega Grid")
    print("=" * 80)
    print("  Dual floors: min_stop=10pt, min_tp1=10pt")
    print("  Direction: short only")

    print("\nLoading data...", flush=True)
    t0 = time.time()
    df_5m = load_5m_data("NQ_5m.csv")
    try:
        df_1m = load_1m_for_5m("NQ_5m.csv")
    except FileNotFoundError:
        df_1m = None
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time() - t0:.1f}s]", flush=True)

    # ════════════════════════════════════════════════════════════════
    # PHASE 1: Main Grid
    # ════════════════════════════════════════════════════════════════
    combos = build_combos()
    total = len(combos)
    print(f"\n  PHASE 1: Main Grid — {total} combos")
    print(f"  Estimated runtime: {total * 15 / 3600:.1f} hours")
    print(f"{'=' * 80}")

    results = []
    skipped = 0
    t_grid = time.time()

    for i, combo in enumerate(combos):
        r = run_combo(df_5m, df_1m, df_1s, combo)

        if r["med_ticks"] < 10:
            skipped += 1
            continue

        # Don't store raw trades in results list (memory)
        r_clean = {k: v for k, v in r.items() if k != "raw_trades"}
        results.append(r_clean)

        # Progress every 100 combos
        if (i + 1) % 100 == 0 or i == total - 1:
            elapsed = time.time() - t_grid
            rate = (i + 1) / elapsed
            eta_s = (total - i - 1) / rate if rate > 0 else 0
            best_so_far = max(results, key=lambda x: x["calmar"]) if results else None
            best_str = f"best Calmar={best_so_far['calmar']:.2f}" if best_so_far else ""
            print(f"  [{i+1:>5}/{total}] {elapsed/60:.1f}m elapsed, "
                  f"ETA {eta_s/60:.1f}m, {rate:.1f}/s, "
                  f"valid={len(results)}, skip={skipped}, {best_str}",
                  flush=True)

    grid_time = time.time() - t_grid
    print(f"\n  Grid complete: {len(results)} valid, {skipped} skipped, {grid_time/60:.1f}m")

    # ── Top results ──
    print(f"\n{'=' * 80}")
    print("  PHASE 1 RESULTS")
    print(f"{'=' * 80}")

    all_top = print_top(results, "TOP 30 — All combos", 30)
    zero_neg = print_top(results, "TOP 30 — 0 negative full years", 30,
                         filter_fn=lambda r: r["n_neg"] == 0)
    low_neg = print_top(results, "TOP 30 — ≤2 negative full years", 30,
                        filter_fn=lambda r: r["n_neg"] <= 2)

    # Summary stats
    profitable = [r for r in results if r["pf"] > 1.0]
    zero_neg_all = [r for r in results if r["n_neg"] == 0]
    print(f"\n  Grid summary:")
    print(f"    Total combos: {total}")
    print(f"    Valid (med stop ≥ 10t): {len(results)}")
    print(f"    Skipped (<10t stop): {skipped}")
    print(f"    Profitable (PF > 1.0): {len(profitable)} ({100*len(profitable)/max(len(results),1):.0f}%)")
    print(f"    0 neg full years: {len(zero_neg_all)} ({100*len(zero_neg_all)/max(len(results),1):.0f}%)")

    # ── Marginal analysis ──
    print(f"\n  Marginal analysis (avg Calmar by dimension):")
    dims = {
        "ORB window": lambda r: r["combo"]["orb_label"],
        "orbstop": lambda r: f"{r['combo']['orbstop']:.0f}%",
        "entry_end": lambda r: r["combo"]["entry_end"],
        "flat_start": lambda r: r["combo"]["flat_start"],
        "rr": lambda r: f"{r['combo']['rr']:.1f}",
        "tp1": lambda r: f"{r['combo']['tp1']:.1f}",
    }
    for dim_name, key_fn in dims.items():
        buckets = {}
        for r in results:
            k = key_fn(r)
            buckets.setdefault(k, []).append(r["calmar"])
        avg_by_val = {k: sum(v)/len(v) for k, v in buckets.items()}
        sorted_vals = sorted(avg_by_val.items(), key=lambda x: x[1], reverse=True)
        vals_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted_vals)
        print(f"    {dim_name}: {vals_str}")

    # ════════════════════════════════════════════════════════════════
    # PHASE 2: Refinement on top 30
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print("  PHASE 2: Refinement — ICF, DOW, OrbGap on top 30")
    print(f"{'=' * 80}")

    # Get unique top 30 configs (from all_top)
    top_configs = all_top[:30] if all_top else []
    if not top_configs:
        print("  No configs to refine.")
        elapsed = time.time() - t0
        print(f"\n  Total runtime: {elapsed/60:.1f}m ({elapsed/3600:.1f}h)")
        return

    # ── 2a: ICF refinement ──
    print(f"\n  2a. ICF ON vs OFF for top 30")
    print(f"  {'#':>3} {'Config':<55} {'OFF':>7} {'ON':>7} {'Δ':>6}")
    print(f"  {'─' * 85}")

    icf_improvements = []
    for i, r in enumerate(top_configs):
        combo = r["combo"]
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end=combo["orb_end"],
            entry_start=combo["entry_start"],
            entry_end=combo["entry_end"],
            flat_start=combo["flat_start"],
            flat_end="16:00",
            stop_atr_pct=5.0,
            min_gap_atr_pct=2.0,
            stop_orb_pct=combo["orbstop"],
            min_gap_orb_pct=7.0,
            min_stop_points=10.0,
            min_tp1_points=10.0,
        )
        cfg_icf = StrategyConfig(
            sessions=(sess,),
            instrument=NQ,
            strategy="continuation",
            use_bar_magnifier=True,
            risk_usd=5000.0,
            direction_filter="short",
            rr=combo["rr"],
            tp1_ratio=combo["tp1"],
            atr_length=14,
            impulse_close_filter=True,
        )
        trades_icf = run_backtest(df_5m, cfg_icf, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
        m_icf = compute_metrics(trades_icf)
        calmar_icf = m_icf["calmar_ratio"]
        neg_icf = neg_year_set(m_icf)
        delta = calmar_icf - r["calmar"]
        print(f"  {i+1:>3} {r['label']:<55} {r['calmar']:>7.2f} {calmar_icf:>7.2f} {delta:>+5.2f}")
        icf_improvements.append({
            "idx": i, "calmar_off": r["calmar"], "calmar_on": calmar_icf,
            "delta": delta, "neg_icf": neg_icf, "label": r["label"],
        })

    # ── 2b: DOW exclusion (post-filter) for top 30 ──
    print(f"\n  2b. DOW Exclusion for top 30 (post-filter)")
    print(f"  {'#':>3} {'Config':<45} {'none':>6} {'Mon':>6} {'Tue':>6} "
          f"{'Wed':>6} {'Thu':>6} {'Fri':>6} {'Best':>8}")
    print(f"  {'─' * 100}")

    dow_labels = ["none", "Mon", "Tue", "Wed", "Thu", "Fri"]
    dow_sets = [set(), {0}, {1}, {2}, {3}, {4}]

    for i, r in enumerate(top_configs):
        combo = r["combo"]
        # Re-run to get raw trades
        sess = SessionConfig(
            name="NY",
            orb_start="09:30",
            orb_end=combo["orb_end"],
            entry_start=combo["entry_start"],
            entry_end=combo["entry_end"],
            flat_start=combo["flat_start"],
            flat_end="16:00",
            stop_atr_pct=5.0,
            min_gap_atr_pct=2.0,
            stop_orb_pct=combo["orbstop"],
            min_gap_orb_pct=7.0,
            min_stop_points=10.0,
            min_tp1_points=10.0,
        )
        cfg = StrategyConfig(
            sessions=(sess,),
            instrument=NQ,
            strategy="continuation",
            use_bar_magnifier=True,
            risk_usd=5000.0,
            direction_filter="short",
            rr=combo["rr"],
            tp1_ratio=combo["tp1"],
            atr_length=14,
            impulse_close_filter=False,
        )
        trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)

        calmars = []
        for dow_excl in dow_sets:
            filtered = apply_dow_filter(trades, dow_excl) if dow_excl else trades
            m = compute_metrics(filtered)
            calmars.append(m["calmar_ratio"])

        best_dow_idx = max(range(len(calmars)), key=lambda j: calmars[j])
        best_dow = dow_labels[best_dow_idx]
        calmar_strs = " ".join(f"{c:>6.2f}" for c in calmars)
        short_label = (f"ORB={combo['orb_label']} os={combo['orbstop']:.0f} "
                       f"ee={combo['entry_end']} fl={combo['flat_start']}")
        print(f"  {i+1:>3} {short_label:<45} {calmar_strs} {best_dow:>8}")

    # ── 2c: OrbGap refinement for top 30 ──
    print(f"\n  2c. OrbGap % for top 30")
    print(f"  {'#':>3} {'Config':<45} {'3%':>6} {'5%':>6} {'7%':>6} {'10%':>6} {'15%':>6} {'Best':>8}")
    print(f"  {'─' * 100}")

    orbgap_vals = [3.0, 5.0, 7.0, 10.0, 15.0]
    for i, r in enumerate(top_configs):
        combo = r["combo"]
        calmars = []
        for orbgap in orbgap_vals:
            sess = SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end=combo["orb_end"],
                entry_start=combo["entry_start"],
                entry_end=combo["entry_end"],
                flat_start=combo["flat_start"],
                flat_end="16:00",
                stop_atr_pct=5.0,
                min_gap_atr_pct=2.0,
                stop_orb_pct=combo["orbstop"],
                min_gap_orb_pct=orbgap,
                min_stop_points=10.0,
                min_tp1_points=10.0,
            )
            cfg = StrategyConfig(
                sessions=(sess,),
                instrument=NQ,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="short",
                rr=combo["rr"],
                tp1_ratio=combo["tp1"],
                atr_length=14,
                impulse_close_filter=False,
            )
            trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
            m = compute_metrics(trades)
            calmars.append(m["calmar_ratio"])

        best_gap_idx = max(range(len(calmars)), key=lambda j: calmars[j])
        best_gap = f"{orbgap_vals[best_gap_idx]:.0f}%"
        calmar_strs = " ".join(f"{c:>6.2f}" for c in calmars)
        short_label = (f"ORB={combo['orb_label']} os={combo['orbstop']:.0f} "
                       f"ee={combo['entry_end']} fl={combo['flat_start']}")
        print(f"  {i+1:>3} {short_label:<45} {calmar_strs} {best_gap:>8}")

    # ════════════════════════════════════════════════════════════════
    # FINAL SUMMARY
    # ════════════════════════════════════════════════════════════════
    print(f"\n{'=' * 80}")
    print("  FINAL SUMMARY")
    print(f"{'=' * 80}")

    if all_top:
        winner = all_top[0]
        print(f"\n  Best overall: {winner['label']}")
        print(f"    Calmar: {winner['calmar']:.2f}  PF: {winner['pf']:.2f}  "
              f"Sharpe: {winner['sharpe']:.2f}  Net R: {winner['net_r']:.1f}  "
              f"R/yr: {winner['r_yr']:.1f}  MaxDD: {winner['max_dd']:.1f}R")
        print(f"    Neg years: {winner['n_neg']} {sorted(winner['neg_years'])}")
        yr_str = " ".join(f"{yr}:{v:+.0f}" for yr, v in sorted(winner["r_by_year"].items()))
        print(f"    R by year: {yr_str}")

    if zero_neg:
        winner_0 = zero_neg[0]
        print(f"\n  Best 0-neg-year: {winner_0['label']}")
        print(f"    Calmar: {winner_0['calmar']:.2f}  PF: {winner_0['pf']:.2f}  "
              f"Sharpe: {winner_0['sharpe']:.2f}  Net R: {winner_0['net_r']:.1f}  "
              f"R/yr: {winner_0['r_yr']:.1f}  MaxDD: {winner_0['max_dd']:.1f}R")
        yr_str = " ".join(f"{yr}:{v:+.0f}" for yr, v in sorted(winner_0["r_by_year"].items()))
        print(f"    R by year: {yr_str}")

    elapsed = time.time() - t0
    print(f"\n  Total runtime: {elapsed/60:.1f}m ({elapsed/3600:.1f}h)")


if __name__ == "__main__":
    main()
