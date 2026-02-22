#!/usr/bin/env python3
"""ES LDN Continuation Both — Grid Sweep R2 (Post R9 Convergence).

Confirmation grid around converged anchor from R8-R9 variable sweeps:
  stop=5%, rr=3.0, gap=1.0%, tp1=0.6, ATR=10
  ORB 10m, entry_end 08:25, flat 08:20, both, DOW excl Mon, ICF off, 1s mag.
  Calmar 6.85, 0 neg years.

Grid dimensions:
  Stop: [5.0, 6.0, 7.5, 10.0]          = 4 values
  RR:   [2.5, 3.0, 3.5, 4.0]           = 4 values
  Gap:  [0.5, 1.0, 1.5]                 = 3 values
  TP1:  [0.5, 0.6, 0.7]                 = 3 values
  ATR:  [7, 10, 14]                     = 3 values
  Total: 4 × 4 × 3 × 3 × 3 = 432 combos
"""

import sys
import time
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_dow_filter, MON

# -- Config -------------------------------------------------------------------

START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2016, 2026)]
DOW_EXCLUDED = {MON}

BASE_SESSION = SessionConfig(
    name="LDN", orb_start="03:00", orb_end="03:10", entry_start="03:10",
    entry_end="08:25", flat_start="08:20", flat_end="08:25",
    stop_atr_pct=5.0, min_gap_atr_pct=1.0, max_gap_points=50.0,
)
BASE_CFG = StrategyConfig(
    rr=3.0, tp1_ratio=0.6, risk_usd=5000.0, atr_length=10,
    sessions=(BASE_SESSION,), instrument=ES, strategy="continuation",
    direction_filter="both", use_bar_magnifier=True,
)

# Grid values
STOP_VALUES = [5.0, 6.0, 7.5, 10.0]
RR_VALUES = [2.5, 3.0, 3.5, 4.0]
GAP_VALUES = [0.5, 1.0, 1.5]
TP1_VALUES = [0.5, 0.6, 0.7]
ATR_VALUES = [7, 10, 14]

TOTAL = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES) * len(ATR_VALUES)

# -- Helpers ------------------------------------------------------------------


def neg_year_set(m):
    rby = m.get("r_by_year", {})
    return {y for y, r in rby.items() if y in FULL_YEARS and r < 0}

def neg_years(m): return len(neg_year_set(m))

def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0

def calmar(m): return m.get("calmar_ratio", 0.0)


# -- Main ---------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 100)
    print("  ES LDN CONTINUATION BOTH — GRID SWEEP R2")
    print("=" * 100)
    print(f"  Grid: stop[{len(STOP_VALUES)}] × rr[{len(RR_VALUES)}] × gap[{len(GAP_VALUES)}] "
          f"× tp1[{len(TP1_VALUES)}] × atr[{len(ATR_VALUES)}] = {TOTAL} combos")
    print(f"  Structural: ORB 10m, flat 08:20, entry 08:25, both, DOW excl Mon, 1s mag")
    print()

    print("  Loading data...", flush=True)
    t0 = time.time()
    df = load_5m_data(ES.data_file, start=START_DATE)
    df_1m = load_1m_for_5m(ES.data_file, start=START_DATE)
    df_1s = load_1s_for_5m(ES.data_file, start=START_DATE)
    print(f"  Data loaded in {time.time() - t0:.1f}s\n", flush=True)

    results = []
    t_start = time.time()

    for i_stop, stop in enumerate(STOP_VALUES):
        for i_rr, rr in enumerate(RR_VALUES):
            for i_gap, gap in enumerate(GAP_VALUES):
                for i_tp1, tp1 in enumerate(TP1_VALUES):
                    for i_atr, atr in enumerate(ATR_VALUES):
                        idx = len(results)
                        sess = replace(BASE_SESSION, stop_atr_pct=stop, min_gap_atr_pct=gap)
                        cfg = replace(BASE_CFG, rr=rr, tp1_ratio=tp1, atr_length=atr, sessions=(sess,))

                        trades = run_backtest(df, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
                        trades = apply_dow_filter(trades, DOW_EXCLUDED)
                        m = compute_metrics(trades)

                        results.append({
                            "stop": stop, "rr": rr, "gap": gap, "tp1": tp1, "atr": atr,
                            "trades": m["total_trades"], "wr": m["win_rate"],
                            "pf": m["profit_factor"], "sharpe": m["sharpe_ratio"],
                            "net_r": m["total_r"], "r_yr": r_per_year(m),
                            "max_dd": m["max_drawdown_r"], "calmar": calmar(m),
                            "neg_yr": neg_years(m), "neg_yr_set": neg_year_set(m),
                            "r_by_year": m.get("r_by_year", {}),
                        })

                        # Progress every 50
                        if (idx + 1) % 50 == 0 or idx == TOTAL - 1:
                            elapsed = time.time() - t_start
                            rate = (idx + 1) / elapsed
                            eta = (TOTAL - idx - 1) / rate if rate > 0 else 0
                            print(f"  [{idx+1}/{TOTAL}] {elapsed:.0f}s elapsed, "
                                  f"{rate:.1f} combos/s, ETA {eta:.0f}s", flush=True)

    total_time = time.time() - t_start

    # Sort by Calmar
    results.sort(key=lambda r: r["calmar"], reverse=True)

    # Top 20 overall
    print(f"\n\n{'='*100}")
    print(f"  TOP 20 BY CALMAR (ALL COMBOS)")
    print(f"{'='*100}")
    print(f"  {'#':>3s} {'Stop':>5s} {'RR':>4s} {'Gap':>5s} {'TP1':>5s} {'ATR':>4s} "
          f"{'Trades':>7s} {'WR':>7s} {'PF':>6s} {'Sharpe':>7s} "
          f"{'NetR':>7s} {'R/yr':>6s} {'MaxDD':>7s} {'Calmar':>7s} {'NegYr':>6s}")
    print(f"  {'---':>3s} {'-----':>5s} {'----':>4s} {'-----':>5s} {'-----':>5s} {'----':>4s} "
          f"{'-------':>7s} {'-------':>7s} {'------':>6s} {'-------':>7s} "
          f"{'-------':>7s} {'------':>6s} {'-------':>7s} {'-------':>7s} {'------':>6s}")
    for i, r in enumerate(results[:20]):
        print(f"  {i+1:>3d} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.1f} {r['atr']:>4d} "
              f"{r['trades']:>7d} {r['wr']:>6.1%} {r['pf']:>6.2f} {r['sharpe']:>7.3f} "
              f"{r['net_r']:>6.1f}R {r['r_yr']:>5.1f}R {r['max_dd']:>6.1f}R "
              f"{r['calmar']:>7.2f} {r['neg_yr']:>5d}")

    # Top 20 with 0 neg years
    clean = [r for r in results if r["neg_yr"] == 0]
    print(f"\n{'='*100}")
    print(f"  TOP 20 BY CALMAR (0 NEGATIVE FULL YEARS ONLY) — {len(clean)}/{TOTAL} clean combos")
    print(f"{'='*100}")
    print(f"  {'#':>3s} {'Stop':>5s} {'RR':>4s} {'Gap':>5s} {'TP1':>5s} {'ATR':>4s} "
          f"{'Trades':>7s} {'WR':>7s} {'PF':>6s} {'Sharpe':>7s} "
          f"{'NetR':>7s} {'R/yr':>6s} {'MaxDD':>7s} {'Calmar':>7s}")
    print(f"  {'---':>3s} {'-----':>5s} {'----':>4s} {'-----':>5s} {'-----':>5s} {'----':>4s} "
          f"{'-------':>7s} {'-------':>7s} {'------':>6s} {'-------':>7s} "
          f"{'-------':>7s} {'------':>6s} {'-------':>7s} {'-------':>7s}")
    for i, r in enumerate(clean[:20]):
        print(f"  {i+1:>3d} {r['stop']:>5.1f} {r['rr']:>4.1f} {r['gap']:>5.1f} {r['tp1']:>5.1f} {r['atr']:>4d} "
              f"{r['trades']:>7d} {r['wr']:>6.1%} {r['pf']:>6.2f} {r['sharpe']:>7.3f} "
              f"{r['net_r']:>6.1f}R {r['r_yr']:>5.1f}R {r['max_dd']:>6.1f}R "
              f"{r['calmar']:>7.2f}")

    # Print R by year for top 5 clean
    if clean:
        print(f"\n  R by year for top 5 clean combos:")
        for i, r in enumerate(clean[:5]):
            rby = r["r_by_year"]
            parts = [f"{y}:{v:+.0f}" for y, v in sorted(rby.items())]
            print(f"    #{i+1} (s{r['stop']}/rr{r['rr']}/g{r['gap']}/tp{r['tp1']}/a{r['atr']}): "
                  f"{', '.join(parts)}")

    # Grid summary
    n_profitable = sum(1 for r in results if r["net_r"] > 0)
    n_clean = len(clean)
    print(f"\n{'='*100}")
    print(f"  GRID SUMMARY")
    print(f"{'='*100}")
    print(f"  Total combos:         {TOTAL}")
    print(f"  Profitable (Net R>0): {n_profitable} ({100*n_profitable/TOTAL:.0f}%)")
    print(f"  0 neg years:          {n_clean} ({100*n_clean/TOTAL:.0f}%)")
    print(f"  Total time:           {total_time:.0f}s ({total_time/TOTAL:.1f}s/combo)")
    print()

    # Anchor position
    anchor_rank = next((i+1 for i, r in enumerate(results)
                        if r["stop"]==5.0 and r["rr"]==3.0 and r["gap"]==1.0
                        and r["tp1"]==0.6 and r["atr"]==10), None)
    anchor_clean_rank = next((i+1 for i, r in enumerate(clean)
                              if r["stop"]==5.0 and r["rr"]==3.0 and r["gap"]==1.0
                              and r["tp1"]==0.6 and r["atr"]==10), None)
    print(f"  Anchor rank (all):   #{anchor_rank}/{TOTAL}")
    print(f"  Anchor rank (clean): #{anchor_clean_rank}/{n_clean}" if anchor_clean_rank else "  Anchor not in clean set")

    # Decision
    if clean:
        winner = clean[0]
        anchor = next((r for r in results if r["stop"]==5.0 and r["rr"]==3.0
                        and r["gap"]==1.0 and r["tp1"]==0.6 and r["atr"]==10), None)
        if anchor:
            delta = winner["calmar"] - anchor["calmar"]
            print(f"\n  Grid winner Calmar: {winner['calmar']:.2f}")
            print(f"  Anchor Calmar:      {anchor['calmar']:.2f}")
            print(f"  Delta:              {delta:+.2f}")
            if delta > 0.5:
                print(f"\n  >>> Grid winner differs by >{0.5:.1f} Calmar — adopt new anchor, return to variable sweeps")
            else:
                print(f"\n  >>> Grid confirms anchor (delta <0.5). Proceed to Step 4: Robust Pipeline.")
