#!/usr/bin/env python3
"""ES LDN Continuation Both — Broad stop ATR% sweep (1s magnifier).

Previous fine-tune used stop_atr_pct 0.5-1.5%, which are unrealistically tight
for ES (0.30-0.90 points = 1-4 ticks). The engine has no slippage model, so
ultra-tight stops get inflated Calmars.

Realistic minimum: ~2% ATR (~1.0 point = 4 ticks).
This sweep covers 3%-12% in 1% steps, then fine-tune around the winner.

Structural config locked from variable sweeps:
  ORB 10m (03:00-03:10), flat 07:30, ATR 50, both dir, 1s magnifier
  rr=3.0, tp1=0.5, min_gap=1.25% (original anchor — NOT the 0.5% stop anchor)
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

BASE_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00",
    orb_end="03:10",       # 10m ORB (variable sweep winner)
    entry_start="03:10",
    entry_end="08:25",
    flat_start="07:30",    # variable sweep winner
    flat_end="08:25",
    stop_atr_pct=5.0,      # placeholder, overridden per combo
    min_gap_atr_pct=1.25,  # original anchor
    max_gap_points=50.0,
)

BASE_CONFIG = StrategyConfig(
    rr=3.0,                # original anchor
    tp1_ratio=0.5,         # original anchor
    risk_usd=5000.0,
    atr_length=50,         # variable sweep winner
    min_qty=1.0,
    qty_step=1.0,
    sessions=(BASE_SESSION,),
    instrument=ES,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
)

# -- Stop sweep values ---------------------------------------------------------

STOP_VALUES = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0]

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
    print("  ES LDN CONTINUATION — BROAD STOP SWEEP (1s magnifier)", flush=True)
    print(f"  Anchor: rr=3.0 | tp1=0.5 | gap=1.25%", flush=True)
    print(f"  Structural: ORB 10m | flat 07:30 | ATR 50 | both", flush=True)
    print(f"  Sweep: stop_atr_pct = {STOP_VALUES}", flush=True)
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

    # -- Run sweep ---------------------------------------------------------

    print(flush=True)
    print(f"  {'#':>3} {'Stop%':>6} {'StopPts':>8} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}", flush=True)
    print("  " + "-" * 105, flush=True)

    results = []
    t_start = time.time()

    for i, stop in enumerate(STOP_VALUES):
        sess = SessionConfig(
            name="LDN",
            orb_start="03:00",
            orb_end="03:10",
            entry_start="03:10",
            entry_end="08:25",
            flat_start="07:30",
            flat_end="08:25",
            stop_atr_pct=stop,
            min_gap_atr_pct=1.25,
            max_gap_points=50.0,
        )
        cfg = with_overrides(BASE_CONFIG, sessions=(sess,))

        trades = run_backtest(df, cfg, start_date=START_DATE,
                              df_1m=df_1m, df_1s=df_1s)
        m = compute_metrics(trades)

        ny = neg_years(m)

        # Estimate stop in points: stop_atr_pct/100 * typical ATR (~60 pts for ES)
        approx_pts = (stop / 100.0) * 60.0

        print(f"  {i+1:>3} {stop:>5.1f}% {approx_pts:>7.1f}p | "
              f"{m['total_trades']:>6} {m['win_rate']:>5.1%} {m['profit_factor']:>5.2f} "
              f"{m['total_r']:>8.1f} {r_per_year(m):>7.1f} {m['max_drawdown_r']:>8.1f} "
              f"{m['calmar_ratio']:>7.2f} {m['sharpe_ratio']:>7.3f} {ny:>5}", flush=True)

        results.append({
            "stop": stop, "approx_pts": approx_pts,
            "trades": m["total_trades"], "wr": m["win_rate"],
            "pf": m["profit_factor"], "net_r": m["total_r"],
            "r_yr": r_per_year(m), "dd": m["max_drawdown_r"],
            "calmar": m["calmar_ratio"], "sharpe": m["sharpe_ratio"],
            "neg_years": ny,
            "r_by_year": m.get("r_by_year", {}),
        })

    elapsed = time.time() - t_start
    print(f"\n  Sweep complete: {len(STOP_VALUES)} levels in {elapsed:.1f}s", flush=True)

    # -- Leaderboard -----------------------------------------------------------

    ranked = sorted(results, key=lambda x: x["calmar"], reverse=True)

    print(flush=True)
    print("=" * 70, flush=True)
    print("  RANKED BY CALMAR", flush=True)
    print("=" * 70, flush=True)
    print(f"  {'#':>3} {'Stop%':>6} {'~Pts':>5} | "
          f"{'Trades':>6} {'WR':>6} {'PF':>5} {'Net R':>8} {'R/yr':>7} {'Max DD':>8} "
          f"{'Calmar':>7} {'Sharpe':>7} {'NegYr':>5}", flush=True)
    print("  " + "-" * 100, flush=True)

    for i, r in enumerate(ranked):
        marker = " <-- BEST" if i == 0 else ""
        print(f"  {i+1:>3} {r['stop']:>5.1f}% {r['approx_pts']:>4.1f}p | "
              f"{r['trades']:>6} {r['wr']:>5.1%} {r['pf']:>5.2f} "
              f"{r['net_r']:>8.1f} {r['r_yr']:>7.1f} {r['dd']:>8.1f} "
              f"{r['calmar']:>7.2f} {r['sharpe']:>7.3f} {r['neg_years']:>5}{marker}", flush=True)

    # -- Year-by-year for best -------------------------------------------------

    best = ranked[0]
    print(flush=True)
    print("=" * 70, flush=True)
    print(f"  BEST: stop={best['stop']:.1f}% (~{best['approx_pts']:.1f} pts)", flush=True)
    print(f"  Calmar {best['calmar']:.2f} | Sharpe {best['sharpe']:.3f} | "
          f"Net R {best['net_r']:.1f} | DD {best['dd']:.1f}R | "
          f"R/yr {best['r_yr']:.1f}", flush=True)
    print("=" * 70, flush=True)
    rby = best.get("r_by_year", {})
    if rby:
        for y, r in sorted(rby.items()):
            flag = " <--" if r < 0 else ""
            print(f"    {y}: {r:>8.1f}R{flag}", flush=True)

    print(flush=True)
    print("=" * 70, flush=True)
    print("  DONE — Next: fine-tune around winning stop level.", flush=True)
    print("=" * 70, flush=True)
    print(flush=True)


if __name__ == "__main__":
    main()
