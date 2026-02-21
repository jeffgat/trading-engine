#!/usr/bin/env python3
"""ES LDN Continuation Both — 3-way grid sweep: stop × rr × min_gap (1s magnifier).

Structural config locked to variable sweep winners:
  ORB 10m (03:00-03:10), flat_start=07:30, ATR 50, tp1=0.7, direction=both
  stop=1.5% (anchor), 1s magnifier ON

Grid:
  stop_atr_pct:    [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]      = 7
  rr:              [3.0, 3.5, 4.0, 4.5, 5.0]                  = 5
  min_gap_atr_pct: [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]           = 6
  Total: 210 combos

Scoring: Calmar (primary), 0 negative full years (secondary).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# -- Instrument ----------------------------------------------------------------

ES = get_instrument("ES")
START_DATE = "2016-01-01"

# -- Structural config (variable sweep winners) --------------------------------

ES_LDN_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:10",        # 10m ORB (winner)
    entry_start="03:10",
    entry_end="08:25",
    flat_start="07:30",     # earlier flat (winner)
    flat_end="08:25",
    stop_atr_pct=1.5,       # swept in grid
    min_gap_atr_pct=1.25,   # swept in grid
    max_gap_points=50.0,
)

BASE_CONFIG = StrategyConfig(
    rr=3.0,                 # swept in grid
    tp1_ratio=0.7,          # winner from sweep
    risk_usd=5000.0,
    atr_length=50,          # winner from sweep
    min_qty=1.0,
    qty_step=1.0,
    sessions=(ES_LDN_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Grid values ---------------------------------------------------------------

STOP_VALUES = [1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
RR_VALUES = [3.0, 3.5, 4.0, 4.5, 5.0]
GAP_VALUES = [1.0, 1.25, 1.5, 2.0, 2.5, 3.0]

TOTAL_COMBOS = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES)

# -- Helpers -------------------------------------------------------------------

FULL_YEARS = [str(y) for y in range(2016, 2026)]


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


def neg_year_list(m):
    rby = m.get("r_by_year", {})
    return [f"{y}:{r:+.1f}" for y, r in sorted(rby.items()) if y in FULL_YEARS and r < 0]


# -- Main ----------------------------------------------------------------------

def main():
    print()
    print("=" * 70)
    print("  ES LDN CONTINUATION — 3-WAY GRID: stop x rr x min_gap (1s)")
    print(f"  Structural: ORB 10m | flat 07:30 | ATR 50 | tp1=0.7 | both")
    print(f"  Grid: {len(STOP_VALUES)} stops x {len(RR_VALUES)} rr x {len(GAP_VALUES)} gaps = {TOTAL_COMBOS} combos")
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
        print("  1s: NOT FOUND")
    print(f"  Loaded in {time.time() - t0:.1f}s")

    # -- Run grid --------------------------------------------------------------

    print()
    print(f"  {'#':>4} {'Stop':>5} {'RR':>5} {'Gap':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5} | Neg Year Detail")
    print("  " + "-" * 130)

    results = []
    t_start = time.time()

    for i, stop in enumerate(STOP_VALUES):
        for rr in RR_VALUES:
            for gap in GAP_VALUES:
                idx = len(results) + 1

                sess = SessionConfig(
                    name="LDN",
                    orb_start="03:00",
                    orb_end="03:10",
                    entry_start="03:10",
                    entry_end="08:25",
                    flat_start="07:30",
                    flat_end="08:25",
                    stop_atr_pct=stop,
                    min_gap_atr_pct=gap,
                    max_gap_points=50.0,
                )
                cfg = with_overrides(BASE_CONFIG, rr=rr, sessions=(sess,))

                trades = run_backtest(df, cfg, start_date=START_DATE,
                                      df_1m=df_1m, df_1s=df_1s)
                m = compute_metrics(trades)

                ny = neg_years(m)
                nyl = neg_year_list(m)
                nyl_str = ", ".join(nyl) if nyl else ""

                print(f"  {idx:>4} {stop:>5.1f} {rr:>5.1f} {gap:>5.2f} | "
                      f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
                      f"{m['total_r']:>8.1f} {r_per_year(m):>7.1f} {m['max_drawdown_r']:>8.1f} "
                      f"{m['calmar_ratio']:>7.2f} {m['sharpe_ratio']:>7.3f} {ny:>5} | {nyl_str}")

                results.append({
                    "stop": stop, "rr": rr, "gap": gap,
                    "trades": m["total_trades"], "wr": m["win_rate"],
                    "pf": m["profit_factor"], "net_r": m["total_r"],
                    "r_yr": r_per_year(m), "dd": m["max_drawdown_r"],
                    "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"],
                    "neg_years": ny, "neg_detail": nyl_str,
                    "r_by_year": m.get("r_by_year", {}),
                })

        # Progress after each stop level
        elapsed = time.time() - t_start
        done = len(results)
        rate = done / elapsed if elapsed > 0 else 0
        remaining = (TOTAL_COMBOS - done) / rate if rate > 0 else 0
        print(f"  --- stop={stop:.1f}% done ({done}/{TOTAL_COMBOS}, "
              f"{elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining) ---")

    elapsed = time.time() - t_start
    print(f"\n  Grid complete: {TOTAL_COMBOS} combos in {elapsed:.1f}s")

    # -- Leaderboard -----------------------------------------------------------

    # Sort by Calmar
    ranked = sorted(results, key=lambda x: x["calmar"], reverse=True)

    print()
    print("=" * 70)
    print("  TOP 15 BY CALMAR")
    print("=" * 70)
    print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}")
    print("  " + "-" * 105)

    for i, r in enumerate(ranked[:15]):
        print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.1f} {r['gap']:>5.2f} | "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f} {r['neg_years']:>5}")

    # Top with 0 neg years
    clean = [r for r in ranked if r["neg_years"] == 0]
    if clean:
        print()
        print("=" * 70)
        print("  TOP 15 BY CALMAR (0 negative full years)")
        print("=" * 70)
        print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} | "
              f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
              f"{'Calmar':>7} {'Sharpe':>7}")
        print("  " + "-" * 100)

        for i, r in enumerate(clean[:15]):
            print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.1f} {r['gap']:>5.2f} | "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
                  f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
                  f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f}")

    # -- Marginal analysis (average Calmar per dimension) ----------------------

    print()
    print("=" * 70)
    print("  MARGINAL ANALYSIS (avg Calmar per level)")
    print("=" * 70)

    for dim_name, dim_values, dim_key in [
        ("stop_atr_pct", STOP_VALUES, "stop"),
        ("rr", RR_VALUES, "rr"),
        ("min_gap_atr_pct", GAP_VALUES, "gap"),
    ]:
        print(f"\n  {dim_name}:")
        for v in dim_values:
            subset = [r for r in results if r[dim_key] == v]
            avg_calmar = sum(r["calmar"] for r in subset) / len(subset)
            avg_sharpe = sum(r["sharpe"] for r in subset) / len(subset)
            n_clean = sum(1 for r in subset if r["neg_years"] == 0)
            print(f"    {v:>6.2f}: avg Calmar {avg_calmar:>7.2f} | "
                  f"avg Sharpe {avg_sharpe:>6.3f} | "
                  f"clean {n_clean:>2}/{len(subset)}")

    # -- Year-by-year for top config -------------------------------------------

    if ranked:
        top = ranked[0]
        print()
        print("=" * 70)
        print(f"  TOP CONFIG: stop={top['stop']:.1f}% rr={top['rr']:.1f} gap={top['gap']:.2f}%")
        print(f"  Calmar {top['calmar']:.2f} | Sharpe {top['sharpe']:.3f} | "
              f"Net R {top['net_r']:.1f} | DD {top['dd']:.1f}R")
        print("=" * 70)
        rby = top.get("r_by_year", {})
        if rby:
            for y, r in sorted(rby.items()):
                flag = " <--" if r < 0 else ""
                print(f"    {y}: {r:>8.1f}R{flag}")

    if clean:
        top_clean = clean[0]
        print()
        print("=" * 70)
        print(f"  TOP CLEAN CONFIG: stop={top_clean['stop']:.1f}% rr={top_clean['rr']:.1f} gap={top_clean['gap']:.2f}%")
        print(f"  Calmar {top_clean['calmar']:.2f} | Sharpe {top_clean['sharpe']:.3f} | "
              f"Net R {top_clean['net_r']:.1f} | DD {top_clean['dd']:.1f}R")
        print("=" * 70)
        rby = top_clean.get("r_by_year", {})
        if rby:
            for y, r in sorted(rby.items()):
                flag = " <--" if r < 0 else ""
                print(f"    {y}: {r:>8.1f}R{flag}")

    print()
    print("=" * 70)
    print("  DONE — Next: fine-tune around top combo, then re-sweep variables.")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
