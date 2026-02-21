#!/usr/bin/env python3
"""ES LDN Continuation Both — Fine-tune stop around broad sweep winner (1s magnifier).

Broad sweep found stop=3-5% ATR optimal (Calmar ~5.9).
Fine-tune grid:
  stop_atr_pct:    [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]     = 8
  rr:              [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]            = 7
  min_gap_atr_pct: [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]         = 7
  tp1_ratio:       [0.3, 0.4, 0.5, 0.6, 0.7]                      = 5
  Total: 1,960 combos

Structural config locked from variable sweeps:
  ORB 10m (03:00-03:10), flat 07:30, ATR 50, both dir, 1s magnifier
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

# -- Structural config (locked from variable sweeps) ---------------------------

BASE_CONFIG = StrategyConfig(
    rr=3.0,
    tp1_ratio=0.5,
    risk_usd=5000.0,
    atr_length=50,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(SessionConfig(
        name="LDN",
        orb_start="03:00",
        orb_end="03:10",
        entry_start="03:10",
        entry_end="08:25",
        flat_start="07:30",
        flat_end="08:25",
        stop_atr_pct=5.0,
        min_gap_atr_pct=1.25,
        max_gap_points=50.0,
    ),),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Fine-tune grid values -----------------------------------------------------

STOP_VALUES = [2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
RR_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0]
GAP_VALUES = [0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0]
TP1_VALUES = [0.3, 0.4, 0.5, 0.6, 0.7]

TOTAL_COMBOS = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)

# -- Helpers -------------------------------------------------------------------

FULL_YEARS = [str(y) for y in range(2016, 2026)]


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


# -- Main ----------------------------------------------------------------------

def main():
    print(flush=True)
    print("=" * 70, flush=True)
    print("  ES LDN CONTINUATION — STOP FINE-TUNE (1s magnifier)", flush=True)
    print(f"  Structural: ORB 10m | flat 07:30 | ATR 50 | both", flush=True)
    print(f"  Grid: {len(STOP_VALUES)}s x {len(RR_VALUES)}rr x "
          f"{len(GAP_VALUES)}g x {len(TP1_VALUES)}tp1 = {TOTAL_COMBOS} combos", flush=True)
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
    print(f"  Loaded in {time.time() - t0:.1f}s", flush=True)

    # -- Run grid --------------------------------------------------------------

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
                    cfg = with_overrides(BASE_CONFIG, rr=rr, tp1_ratio=tp1,
                                         sessions=(sess,))

                    trades = run_backtest(df, cfg, start_date=START_DATE,
                                          df_1m=df_1m, df_1s=df_1s)
                    m = compute_metrics(trades)

                    ny = neg_years(m)

                    print(f"  {idx:>5} {stop:>5.1f} {rr:>5.2f} {gap:>5.2f} {tp1:>5.2f} | "
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
                        "r_by_year": m.get("r_by_year", {}),
                    })

        # Progress after each stop level
        elapsed = time.time() - t_start
        done = len(results)
        rate = done / elapsed if elapsed > 0 else 0
        remaining = (TOTAL_COMBOS - done) / rate if rate > 0 else 0
        print(f"  --- stop={stop:.1f}% done ({done}/{TOTAL_COMBOS}, "
              f"{elapsed:.0f}s elapsed, ~{remaining:.0f}s remaining) ---", flush=True)

    elapsed = time.time() - t_start
    print(f"\n  Grid complete: {TOTAL_COMBOS} combos in {elapsed:.1f}s", flush=True)

    # -- Leaderboard -----------------------------------------------------------

    ranked = sorted(results, key=lambda x: x["calmar"], reverse=True)

    print(flush=True)
    print("=" * 70, flush=True)
    print("  TOP 20 BY CALMAR", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}", flush=True)
    print("  " + "-" * 115, flush=True)

    for i, r in enumerate(ranked[:20]):
        print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.2f} {r['gap']:>5.2f} {r['tp1']:>5.2f} | "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f} {r['neg_years']:>5}", flush=True)

    # Top with 0 neg years
    clean = [r for r in ranked if r["neg_years"] == 0]
    if clean:
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  TOP 20 BY CALMAR (0 negative full years) — {len(clean)}/{len(results)} clean", flush=True)
        print("=" * 70, flush=True)
        print(f"  {'#':>3} {'Stop':>5} {'RR':>5} {'Gap':>5} {'TP1':>5} | "
              f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
              f"{'Calmar':>7} {'Sharpe':>7}", flush=True)
        print("  " + "-" * 110, flush=True)

        for i, r in enumerate(clean[:20]):
            print(f"  {i+1:>3} {r['stop']:>5.1f} {r['rr']:>5.2f} {r['gap']:>5.2f} {r['tp1']:>5.2f} | "
                  f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
                  f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
                  f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f}", flush=True)

    # -- Marginal analysis -----------------------------------------------------

    print(flush=True)
    print("=" * 70, flush=True)
    print("  MARGINAL ANALYSIS (avg Calmar per level)", flush=True)
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

    for label, src in [("TOP OVERALL", ranked[0]),
                        ("TOP CLEAN", clean[0] if clean else None)]:
        if src is None:
            continue
        print(flush=True)
        print("=" * 70, flush=True)
        print(f"  {label}: stop={src['stop']:.1f}% rr={src['rr']:.2f} "
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

    print(flush=True)
    print("=" * 70, flush=True)
    print("  DONE — Next: re-sweep variables on winning anchor, then pipeline.", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)


if __name__ == "__main__":
    main()
