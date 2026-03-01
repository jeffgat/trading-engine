#!/usr/bin/env python3
"""GC NY Cont Longs — FOMC vs Wednesday exclusion diagnostic.

Compares exclusion strategies to determine whether the Wednesday benefit
comes from FOMC days specifically or from a general day-of-week effect.

Anchor: stop=4.0%, rr=4.5, min_gap=2.5%, tp1=0.5, ATR 16, 10m ORB, entry→11:00

Exclusion variants tested:
  1. No exclusion (anchor)
  2. Excl all Wednesdays
  3. Excl FOMC dates only
  4. Excl NFP dates only
  5. Excl CPI dates only
  6. Excl FOMC + NFP
  7. Excl FOMC + CPI
  8. Excl all events (FOMC + NFP + CPI)
  9. Excl FOMC Wednesdays only (FOMC dates that fall on Wednesday)
 10. Excl non-FOMC Wednesdays (Wednesdays that are NOT FOMC days)

The decomposition (9 vs 10) tells us whether it's FOMC-driven or a pure
Wednesday structural effect.
"""

import sys
import time
from pathlib import Path
from datetime import datetime
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES, NFP_DATES, CPI_DATES, FOMC_SET, NFP_SET, CPI_SET
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
END_DATE = "2026-02-15"
FULL_YEARS = [str(y) for y in range(2016, 2026)]

# ── Anchor ────────────────────────────────────────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30", orb_end="09:40",
    entry_start="09:40", entry_end="11:00",
    flat_start="15:50", flat_end="16:00",
    stop_atr_pct=4.0, min_gap_atr_pct=2.5, max_gap_points=25.0,
)

ANCHOR = StrategyConfig(
    rr=4.5, tp1_ratio=0.5, risk_usd=5000.0, atr_length=16,
    min_qty=1.0, qty_step=1.0,
    sessions=(GC_NY,), instrument=GC,
    strategy="continuation", direction_filter="long",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",),
)

df = df_1m = df_1s = None

# ── Helpers ───────────────────────────────────────────────────────────────────

def run_base():
    return run_backtest(df, ANCHOR, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)


def filter_trades(trades, excluded_date_set):
    """Keep NO_FILL trades (unchosen days still counted), exclude filled trades on event days."""
    return [
        t for t in trades
        if t.exit_type == EXIT_NO_FILL
        or t.date.replace("-", "") not in excluded_date_set
    ]


def metrics(trades):
    return compute_metrics(trades)


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def row(label, m, n_excluded=None):
    excl_str = f" ({n_excluded} excl)" if n_excluded is not None else ""
    return (
        f"  {label:<38s}"
        f"  {m['total_trades']:>5d}{excl_str:<12s}"
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
        f"  {'Config':<38s}"
        f"  {'Trades':>5s}{'':12s}"
        f"  {'  WR':>6s}"
        f"  {'   PF':>5s}"
        f"  {'  Net R':>8s}"
        f"  {' R/yr':>7s}"
        f"  {' Max DD':>8s}"
        f"  {'Calmar':>7s}"
        f"  {' Sharpe':>7s}"
        f"  {'NegYr':>5s}"
    )
    print("  " + "-" * 118)


def r_by_year_summary(trades, label):
    rby = defaultdict(float)
    for t in trades:
        if t.exit_type != EXIT_NO_FILL:
            rby[t.date[:4]] += t.r_multiple
    print(f"\n  {label} — R by year:")
    for y in sorted(rby):
        flag = " <--" if rby[y] < 0 else ""
        print(f"    {y}: {rby[y]:>8.1f}R{flag}")


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print()
    print("=" * 80)
    print("  GC NY FOMC vs WEDNESDAY EXCLUSION DIAGNOSTIC")
    print("  Anchor: stop=4.0% | rr=4.5 | min_gap=2.5% | tp1=0.5 | ATR 16 | 10m ORB | entry→11:00")
    print("=" * 80)

    print("\nLoading data...")
    t0 = time.time()
    df = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} bars | 1m: {len(df_1m):,} bars | 1s: {len(df_1s):,} bars")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    print("\nRunning all trades (base)...")
    t0 = time.time()
    all_trades = run_base()
    filled = [t for t in all_trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {len(filled)} filled trades in {time.time() - t0:.1f}s")

    # Build derived exclusion sets
    fomc_set = FOMC_SET
    nfp_set = NFP_SET
    cpi_set = CPI_SET
    fomc_nfp_set = frozenset(FOMC_SET | NFP_SET)
    fomc_cpi_set = frozenset(FOMC_SET | CPI_SET)
    all_event_set = frozenset(FOMC_SET | NFP_SET | CPI_SET)

    # All Wednesday dates in data range
    wed_dates = frozenset(
        t.date.replace("-", "")
        for t in filled
        if datetime.strptime(t.date, "%Y-%m-%d").weekday() == 2  # Wednesday=2
    )

    # FOMC dates that are Wednesdays vs non-FOMC Wednesdays
    fomc_wed_set = frozenset(d for d in FOMC_SET if d in wed_dates)
    non_fomc_wed_set = frozenset(d for d in wed_dates if d not in FOMC_SET)

    print(f"\n  Date set sizes:")
    print(f"    All Wednesdays in data:     {len(wed_dates)}")
    print(f"    FOMC dates (total):         {len(fomc_set)}")
    print(f"    FOMC dates on Wednesday:    {len(fomc_wed_set)}")
    print(f"    Non-FOMC Wednesdays:        {len(non_fomc_wed_set)}")
    print(f"    NFP dates:                  {len(nfp_set)}")
    print(f"    CPI dates:                  {len(cpi_set)}")
    print(f"    All events combined:        {len(all_event_set)}")

    # Compute metrics for each variant
    configs = [
        ("No exclusion [anchor]",       all_trades,                                   None),
        ("Excl all Wednesdays",          filter_trades(all_trades, wed_dates),          len(wed_dates)),
        ("Excl FOMC only",               filter_trades(all_trades, fomc_set),           len(fomc_set)),
        ("Excl NFP only",                filter_trades(all_trades, nfp_set),            len(nfp_set)),
        ("Excl CPI only",                filter_trades(all_trades, cpi_set),            len(cpi_set)),
        ("Excl FOMC+NFP",                filter_trades(all_trades, fomc_nfp_set),       len(fomc_nfp_set)),
        ("Excl FOMC+CPI",                filter_trades(all_trades, fomc_cpi_set),       len(fomc_cpi_set)),
        ("Excl FOMC+NFP+CPI",            filter_trades(all_trades, all_event_set),      len(all_event_set)),
        ("Excl FOMC-Wednesdays only",    filter_trades(all_trades, fomc_wed_set),       len(fomc_wed_set)),
        ("Excl non-FOMC Wednesdays",     filter_trades(all_trades, non_fomc_wed_set),   len(non_fomc_wed_set)),
    ]

    print()
    print("=" * 80)
    print("  EXCLUSION COMPARISON")
    print("=" * 80)
    header()

    results = []
    for label, trades, n_excl in configs:
        m = metrics(trades)
        print(row(label, m, n_excl))
        results.append((label, trades, m))

    # Decomposition insight
    print()
    print("=" * 80)
    print("  DECOMPOSITION: What drives the Wednesday effect?")
    print("=" * 80)
    anchor_m = results[0][2]
    wed_m    = results[1][2]
    fomc_m   = results[2][2]
    fomcwed_m = results[8][2]
    nonfomcwed_m = results[9][2]

    print(f"\n  Anchor (no excl):             Calmar {anchor_m['calmar_ratio']:.2f}  Sharpe {anchor_m['sharpe_ratio']:.3f}  DD {anchor_m['max_drawdown_r']:.1f}R")
    print(f"  Excl all Wednesdays:          Calmar {wed_m['calmar_ratio']:.2f}  Sharpe {wed_m['sharpe_ratio']:.3f}  DD {wed_m['max_drawdown_r']:.1f}R  (Δ Calmar {wed_m['calmar_ratio'] - anchor_m['calmar_ratio']:+.2f})")
    print(f"  Excl FOMC only:               Calmar {fomc_m['calmar_ratio']:.2f}  Sharpe {fomc_m['sharpe_ratio']:.3f}  DD {fomc_m['max_drawdown_r']:.1f}R  (Δ Calmar {fomc_m['calmar_ratio'] - anchor_m['calmar_ratio']:+.2f})")
    print(f"  Excl FOMC-Wednesdays only:    Calmar {fomcwed_m['calmar_ratio']:.2f}  Sharpe {fomcwed_m['sharpe_ratio']:.3f}  DD {fomcwed_m['max_drawdown_r']:.1f}R  (Δ Calmar {fomcwed_m['calmar_ratio'] - anchor_m['calmar_ratio']:+.2f})")
    print(f"  Excl non-FOMC Wednesdays:     Calmar {nonfomcwed_m['calmar_ratio']:.2f}  Sharpe {nonfomcwed_m['sharpe_ratio']:.3f}  DD {nonfomcwed_m['max_drawdown_r']:.1f}R  (Δ Calmar {nonfomcwed_m['calmar_ratio'] - anchor_m['calmar_ratio']:+.2f})")
    print()

    # Show event-day trade performance
    fomc_filled = [t for t in filled if t.date.replace("-", "") in fomc_set]
    nfp_filled  = [t for t in filled if t.date.replace("-", "") in nfp_set]
    cpi_filled  = [t for t in filled if t.date.replace("-", "") in cpi_set]
    wed_filled  = [t for t in filled if datetime.strptime(t.date, "%Y-%m-%d").weekday() == 2]
    fomc_wed_filled = [t for t in filled if t.date.replace("-", "") in fomc_wed_set]
    non_fomc_wed_filled = [t for t in filled if t.date.replace("-", "") in non_fomc_wed_set]

    def event_summary(label, event_trades):
        if not event_trades:
            print(f"  {label:<35s}  0 trades")
            return
        wr = sum(1 for t in event_trades if t.r_multiple > 0) / len(event_trades)
        avg_r = sum(t.r_multiple for t in event_trades) / len(event_trades)
        total_r = sum(t.r_multiple for t in event_trades)
        print(f"  {label:<35s}  {len(event_trades):>4d} trades  WR {wr:.1%}  Avg R {avg_r:+.3f}  Total R {total_r:+.1f}")

    print("  Event-day trade quality (filled trades on those dates):")
    print()
    event_summary("All Wednesdays",         wed_filled)
    event_summary("FOMC dates",             fomc_filled)
    event_summary("FOMC Wednesdays",        fomc_wed_filled)
    event_summary("Non-FOMC Wednesdays",    non_fomc_wed_filled)
    event_summary("NFP dates",              nfp_filled)
    event_summary("CPI dates",              cpi_filled)
    event_summary("All trades (baseline)",  filled)

    print()
    print("  Interpretation guide:")
    print("  - If FOMC-Wednesdays ≈ Wednesday gain → FOMC is the driver, adopt FOMC exclusion")
    print("  - If non-FOMC Wednesdays ≈ Wednesday gain → structural DOW effect, broader exclusion needed")
    print("  - If neither dominates → Wednesday effect is diffuse, skip exclusion entirely")
    print()
