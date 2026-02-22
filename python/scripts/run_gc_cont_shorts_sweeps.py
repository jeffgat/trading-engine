#!/usr/bin/env python3
"""GC continuation shorts — combined best-of + variable sweeps.

Diagnostic showed positive signal at base R2 anchor (+41.7R). Best individual
dimensions: rr=5.0 (+71.5R), gap=5.0% (Calmar 0.34), entry→15:00 (+72.6R),
tp1=0.6 (+51.5R). This script tests compound combinations then, if positive,
runs full variable sweeps on the best anchor.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL, EXIT_NAMES
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")


def make_config(
    stop_atr_pct=4.0,
    min_gap_atr_pct=3.5,
    max_gap_atr_pct=30.0,
    max_gap_points=25.0,
    rr=4.0,
    tp1_ratio=0.5,
    atr_length=10,
    orb_start="09:30",
    orb_end="09:40",
    entry_end="11:00",
    flat_start="15:50",
):
    session = SessionConfig(
        name="NY",
        orb_start=orb_start, orb_end=orb_end,
        entry_start=orb_end, entry_end=entry_end,
        flat_start=flat_start, flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
        max_gap_points=max_gap_points,
        max_gap_atr_pct=max_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=atr_length,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=GC,
        strategy="continuation", direction_filter="short",
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


def stats(trades):
    if len(trades) < 5:
        return None
    m = compute_metrics(trades)
    yearly = defaultdict(list)
    monthly = defaultdict(list)
    for t in trades:
        yearly[t.date[:4]].append(t.r_multiple)
        monthly[t.date[:7]].append(t.r_multiple)
    wm = min((sum(v) for v in monthly.values()), default=0)
    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    n_yr = len(yearly)
    calmar = round(abs(nr / n_yr) / abs(dd), 2) if dd < 0 and n_yr > 0 else 999
    return {
        **m,
        "worst_month": round(wm, 1),
        "calmar": calmar,
        "yearly": {yr: round(sum(v), 1) for yr, v in yearly.items()},
        "trades_per_year": len(trades) / max(n_yr, 1),
        "neg_years": sum(1 for v in yearly.values() if sum(v) < 0),
    }


def print_row(label, trades, m):
    if m is None:
        print(f"  {label:<40} | <5 trades")
        return
    dd = round(m["max_drawdown_r"], 1)
    nr = round(m["total_r"], 1)
    print(f"  {label:<40} | {len(trades):>5} | {m['trades_per_year']:>5.1f} | "
          f"{m['win_rate']:>5.1%} | {nr:>7.1f} | {dd:>7.1f} | "
          f"{m['calmar']:>7.2f} | {m['sharpe_ratio']:>7.3f} | "
          f"{m['profit_factor']:>5.2f} | {m['neg_years']:>2}")


def print_header():
    print(f"  {'Config':<40} | {'Trd':>5} | {'T/yr':>5} | {'WR':>5} | "
          f"{'Net R':>7} | {'Max DD':>7} | {'Calmar':>7} | {'Sharpe':>7} | "
          f"{'PF':>5} | {'NY':>2}")
    print("  " + "-" * 125)


def run_one(df, df_1m, df_1s, cfg):
    trades = run_backtest(df, cfg, start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    m = stats(filled)
    return filled, m


def run_sweep(df, df_1m, df_1s, configs):
    results = []
    for name, cfg in configs:
        filled, m = run_one(df, df_1m, df_1s, cfg)
        results.append((name, filled, m))
    return results


def print_yearly(filled, m):
    if m is None:
        return
    years = sorted(m["yearly"].keys())
    yr_str = " | ".join(f"{yr}: {m['yearly'][yr]:+.1f}R" for yr in years)
    print(f"  Yearly: {yr_str}")
    exit_counts = defaultdict(int)
    for t in filled:
        exit_counts[EXIT_NAMES.get(t.exit_type, f"type_{t.exit_type}")] += 1
    exit_str = ", ".join(f"{n}: {c}" for n, c in sorted(exit_counts.items(), key=lambda x: -x[1]))
    print(f"  Exits: {exit_str}")


def main():
    print("=" * 140)
    print("GC CONTINUATION SHORTS — COMBINED BEST-OF + VARIABLE SWEEPS")
    print("=" * 140)
    print()

    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    bars_1m = f"{len(df_1m):,} 1m" if df_1m is not None else "no 1m"
    bars_1s = f"{len(df_1s):,} 1s" if df_1s is not None else "no 1s"
    print(f"Loaded {len(df):,} 5m bars, {bars_1m} bars, {bars_1s} bars\n")

    t0 = time.time()

    # ══════════════════════════════════════════════════════════════════════
    # PHASE A: COMPOUND COMBINATIONS
    # ══════════════════════════════════════════════════════════════════════
    print("=" * 140)
    print("PHASE A: COMPOUND COMBINATIONS — do edges stack?")
    print("=" * 140)
    print_header()

    combos = [
        ("Diag base (R2 anchor)",
         make_config()),
        ("rr=5.0 only",
         make_config(rr=5.0)),
        ("rr=5.0 + gap=5.0%",
         make_config(rr=5.0, min_gap_atr_pct=5.0)),
        ("rr=5.0 + gap=5.0% + tp1=0.6",
         make_config(rr=5.0, min_gap_atr_pct=5.0, tp1_ratio=0.6)),
        ("rr=5.0 + gap=5.0% + tp1=0.6 + entry→15",
         make_config(rr=5.0, min_gap_atr_pct=5.0, tp1_ratio=0.6, entry_end="15:00")),
        ("rr=5.0 + gap=5.0% + tp1=0.6 + entry→12",
         make_config(rr=5.0, min_gap_atr_pct=5.0, tp1_ratio=0.6, entry_end="12:00")),
        ("rr=5.0 + gap=5.0% + tp1=0.6 + entry→14",
         make_config(rr=5.0, min_gap_atr_pct=5.0, tp1_ratio=0.6, entry_end="14:00")),
        ("rr=4.5 + gap=5.0% + tp1=0.6",
         make_config(rr=4.5, min_gap_atr_pct=5.0, tp1_ratio=0.6)),
        ("rr=4.5 + gap=4.0% + tp1=0.6",
         make_config(rr=4.5, min_gap_atr_pct=4.0, tp1_ratio=0.6)),
        ("rr=5.0 + gap=4.0% + tp1=0.6",
         make_config(rr=5.0, min_gap_atr_pct=4.0, tp1_ratio=0.6)),
    ]

    best_calmar = -999
    best_combo = None
    best_filled = None
    best_m = None

    for name, cfg in combos:
        filled, m = run_one(df, df_1m, df_1s, cfg)
        print_row(name, filled, m)
        if m and m["calmar"] > best_calmar:
            best_calmar = m["calmar"]
            best_combo = (name, cfg)
            best_filled = filled
            best_m = m

    print()
    if best_m:
        print(f"  >>> Best compound: {best_combo[0]}")
        print_yearly(best_filled, best_m)

    # Check if edges compound — if best compound > base, proceed
    base_filled, base_m = run_one(df, df_1m, df_1s, make_config())
    if best_m is None or best_m["total_r"] <= 0:
        print("\n  NO COMPOUNDING — edges don't stack. Stopping here.")
        return

    print(f"\n  Edges compound: {best_m['total_r']:.1f}R (best) vs {base_m['total_r']:.1f}R (base)")
    print(f"  Proceeding to full variable sweeps on best anchor...\n")

    # ══════════════════════════════════════════════════════════════════════
    # Determine anchor from best compound
    # ══════════════════════════════════════════════════════════════════════
    anchor_cfg = best_combo[1]
    anchor_session = anchor_cfg.sessions[0]
    print(f"  ANCHOR: stop={anchor_session.stop_atr_pct}%, rr={anchor_cfg.rr}, "
          f"gap={anchor_session.min_gap_atr_pct}%, tp1={anchor_cfg.tp1_ratio}, "
          f"ATR {anchor_cfg.atr_length}, ORB {anchor_session.orb_start}-{anchor_session.orb_end}, "
          f"entry→{anchor_session.entry_end}")
    print()

    # Helper to make config with anchor overrides
    def anchor(**overrides):
        kw = dict(
            stop_atr_pct=anchor_session.stop_atr_pct,
            min_gap_atr_pct=anchor_session.min_gap_atr_pct,
            max_gap_atr_pct=anchor_session.max_gap_atr_pct,
            max_gap_points=anchor_session.max_gap_points,
            rr=anchor_cfg.rr,
            tp1_ratio=anchor_cfg.tp1_ratio,
            atr_length=anchor_cfg.atr_length,
            orb_start=anchor_session.orb_start,
            orb_end=anchor_session.orb_end,
            entry_end=anchor_session.entry_end,
            flat_start=anchor_session.flat_start,
        )
        kw.update(overrides)
        return make_config(**kw)

    # ══════════════════════════════════════════════════════════════════════
    # VARIABLE SWEEPS (Round 1)
    # ══════════════════════════════════════════════════════════════════════

    # ── Sweep 1: ORB window ──────────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 1: ORB WINDOW")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s, [
        ("ORB 5m (09:30-09:35)", anchor(orb_end="09:35")),
        ("ORB 8m (09:30-09:38)", anchor(orb_end="09:38")),
        ("ORB 10m (09:30-09:40)", anchor(orb_end="09:40")),
        ("ORB 15m (09:30-09:45)", anchor(orb_end="09:45")),
        ("ORB 20m (09:30-09:50)", anchor(orb_end="09:50")),
        ("ORB 30m (09:30-10:00)", anchor(orb_end="10:00")),
    ]):
        print_row(name, filled, m)
    print()

    # ── Sweep 2: ATR length ──────────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 2: ATR LENGTH")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"ATR {a}", anchor(atr_length=a)) for a in [5, 8, 10, 12, 14, 16, 18, 20, 25, 30, 40, 50]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 3: Entry end ───────────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 3: ENTRY END")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"entry→{e}", anchor(entry_end=e))
             for e in ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
                        "13:00", "13:30", "14:00", "14:30", "15:00", "15:30"]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 4: Flat start ──────────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 4: FLAT START")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"flat={f}", anchor(flat_start=f))
             for f in ["14:00", "14:30", "15:00", "15:30", "15:50", "16:00"]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 5: Direction (confirm short-only) ──────────────────────────
    print("=" * 140)
    print("SWEEP 5: DIRECTION CHECK")
    print("=" * 140)
    print_header()
    # Override strategy config direction — need to rebuild with both
    for dir_name in ["short", "long", "both"]:
        session = SessionConfig(
            name="NY",
            orb_start=anchor_session.orb_start, orb_end=anchor_session.orb_end,
            entry_start=anchor_session.orb_end, entry_end=anchor_session.entry_end,
            flat_start=anchor_session.flat_start, flat_end="16:00",
            stop_atr_pct=anchor_session.stop_atr_pct,
            min_gap_atr_pct=anchor_session.min_gap_atr_pct,
            max_gap_points=anchor_session.max_gap_points,
            max_gap_atr_pct=anchor_session.max_gap_atr_pct,
        )
        cfg = StrategyConfig(
            rr=anchor_cfg.rr, tp1_ratio=anchor_cfg.tp1_ratio, risk_usd=5000.0,
            atr_length=anchor_cfg.atr_length,
            min_qty=1.0, qty_step=1.0,
            sessions=(session,), instrument=GC,
            strategy="continuation", direction_filter=dir_name,
            use_bar_magnifier=True,
            half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
        )
        filled, m = run_one(df, df_1m, df_1s, cfg)
        print_row(f"direction={dir_name}", filled, m)
    print()

    # ── Sweep 6: DOW exclusion ───────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 6: DAY-OF-WEEK EXCLUSION")
    print("=" * 140)
    print_header()
    # Anchor (no exclusion)
    filled, m = run_one(df, df_1m, df_1s, anchor())
    print_row("No DOW exclusion (anchor)", filled, m)
    # Per-day exclusion — compute DOW for each trade
    anchor_trades = run_backtest(df, anchor(), start_date="2016-01-01", df_1m=df_1m, df_1s=df_1s)
    anchor_filled = [t for t in anchor_trades if t.exit_type != EXIT_NO_FILL]
    # Tag trades with DOW
    import pandas as pd
    dow_names = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
    for dow_num, dow_name in dow_names.items():
        kept = [t for t in anchor_filled
                if pd.Timestamp(t.date).dayofweek != dow_num]
        m = stats(kept)
        print_row(f"excl {dow_name}", kept, m)
    # Common combos
    for excl_days, label in [
        ({0, 4}, "excl Mon+Fri"),
        ({0}, "excl Mon"),
        ({4}, "excl Fri"),
        ({2}, "excl Wed"),
        ({3, 4}, "excl Thu+Fri"),
    ]:
        kept = [t for t in anchor_filled
                if pd.Timestamp(t.date).dayofweek not in excl_days]
        m = stats(kept)
        print_row(label, kept, m)
    print()

    # ── Sweep 7: Max gap points ──────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 7: MAX GAP POINTS")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"max_gap={g}pt", anchor(max_gap_points=g))
             for g in [10, 15, 20, 25, 30, 40, 50, 100]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 8: Max gap ATR % ───────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 8: MAX GAP ATR %")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"max_gap_atr={g}%", anchor(max_gap_atr_pct=g))
             for g in [0, 10, 15, 20, 25, 30, 40, 50]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 9: Stop (fine-tune around anchor) ──────────────────────────
    print("=" * 140)
    print("SWEEP 9: STOP ATR % (fine-tune)")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"stop={s}%", anchor(stop_atr_pct=s))
             for s in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 10: RR (fine-tune) ─────────────────────────────────────────
    print("=" * 140)
    print("SWEEP 10: R:R (fine-tune)")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"rr={r}", anchor(rr=r))
             for r in [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 6.5, 7.0, 8.0]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 11: Min gap (fine-tune) ────────────────────────────────────
    print("=" * 140)
    print("SWEEP 11: MIN GAP ATR % (fine-tune)")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"gap={g}%", anchor(min_gap_atr_pct=g))
             for g in [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0, 8.0]]):
        print_row(name, filled, m)
    print()

    # ── Sweep 12: TP1 ratio (fine-tune) ──────────────────────────────────
    print("=" * 140)
    print("SWEEP 12: TP1 RATIO (fine-tune)")
    print("=" * 140)
    print_header()
    for name, filled, m in run_sweep(df, df_1m, df_1s,
            [(f"tp1={t}", anchor(tp1_ratio=t))
             for t in [0.3, 0.4, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8]]):
        print_row(name, filled, m)
    print()

    elapsed = time.time() - t0
    print(f"\nTotal runtime: {elapsed:.0f}s")

    # ── Summary ──────────────────────────────────────────────────────────
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")
    print(f"  Anchor: stop={anchor_session.stop_atr_pct}%, rr={anchor_cfg.rr}, "
          f"gap={anchor_session.min_gap_atr_pct}%, tp1={anchor_cfg.tp1_ratio}, "
          f"ATR {anchor_cfg.atr_length}, ORB {anchor_session.orb_end}, "
          f"entry→{anchor_session.entry_end}")
    if best_m:
        print(f"  Anchor metrics: {len(best_filled)} trades, {best_m['win_rate']:.1%} WR, "
              f"{best_m['total_r']:.1f}R, {best_m['max_drawdown_r']:.1f}R DD, "
              f"Calmar {best_m['calmar']}, Sharpe {best_m['sharpe_ratio']:.3f}")
        print_yearly(best_filled, best_m)
    print(f"\n  Review sweep results above to identify anchor changes for Round 2.")


if __name__ == "__main__":
    main()
