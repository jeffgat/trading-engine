#!/usr/bin/env python3
"""GC NY Continuation Both — R3 Grid Sweep R1 (post fill-bar fix).

Converged structural anchor after R3 variable sweeps (4 rounds):
  ATR 5, 5m ORB (09:30-09:35), entry→11:00, flat_start=15:50
  max_gap_points=25.0, max_gap_atr=25%
  Both directions, 1s magnifier, FOMC dates excluded

Grid sweep: stop × rr × min_gap × tp1 = 450 combos
  stop:    [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
  rr:      [3.0, 3.5, 4.0, 4.5, 5.0]
  min_gap: [2.0, 2.5, 3.0, 3.5, 4.0]
  tp1:     [0.4, 0.5, 0.6]

Anchor: stop=3.0%, rr=4.5, min_gap=3.5%, tp1=0.5 (Calmar 9.59)
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig, with_overrides
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

GC = get_instrument("GC")
START_DATE = "2016-01-01"
FULL_YEARS = [str(y) for y in range(2017, 2026)]

# ── Structural anchor (fixed during grid) ───────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:35",          # 5m ORB
    entry_start="09:35",
    entry_end="11:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,         # swept
    min_gap_atr_pct=3.5,      # swept
)

BASE = StrategyConfig(
    rr=4.5,                    # swept
    tp1_ratio=0.5,             # swept
    risk_usd=5000.0,
    atr_length=5,
    min_qty=1.0,
    qty_step=1.0,
    sessions=(GC_NY,),
    instrument=GC,
    strategy="continuation",
    direction_filter="both",
    use_bar_magnifier=True,
    half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
    excluded_dates=("20241218",) + FOMC_DATES,
)

# ── Grid dimensions ─────────────────────────────────────────────────────────

STOPS    = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
RRS      = [3.0, 3.5, 4.0, 4.5, 5.0]
GAPS     = [2.0, 2.5, 3.0, 3.5, 4.0]
TP1S     = [0.4, 0.5, 0.6]
TOTAL    = len(STOPS) * len(RRS) * len(GAPS) * len(TP1S)

ANCHOR_STOP = 3.0
ANCHOR_RR   = 4.5
ANCHOR_GAP  = 3.5
ANCHOR_TP1  = 0.5


def r_per_year(m):
    rby = m.get("r_by_year", {})
    full = [r for y, r in rby.items() if y in FULL_YEARS]
    return sum(full) / len(full) if full else 0.0


def neg_years(m):
    rby = m.get("r_by_year", {})
    return sum(1 for y, r in rby.items() if y in FULL_YEARS and r < 0)


if __name__ == "__main__":
    print()
    print("=" * 70)
    print("  GC NY CONT BOTH — R3 GRID SWEEP R1 (post fill-bar fix)")
    print(f"  {TOTAL} combos: stop({len(STOPS)}) × rr({len(RRS)}) × gap({len(GAPS)}) × tp1({len(TP1S)})")
    print("  Structural: ATR 5 | 5m ORB | entry→11:00 | both dirs | gap_atr=25%")
    print("  Anchor: stop=3.0% | rr=4.5 | min_gap=3.5% | tp1=0.5 (Calmar 9.59)")
    print("=" * 70)

    print("\nLoading data...")
    t0 = time.time()
    df    = load_5m_data("GC_5m.csv")
    df_1m = load_1m_for_5m("GC_5m.csv")
    df_1s = load_1s_for_5m("GC_5m.csv")
    print(f"  5m: {len(df):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,} [{time.time()-t0:.1f}s]")

    print(f"\nRunning {TOTAL} combos...")
    t0 = time.time()

    results = []
    done = 0

    for stop in STOPS:
        for rr in RRS:
            for gap in GAPS:
                for tp1 in TP1S:
                    sess = SessionConfig(
                        name="NY", orb_start="09:30", orb_end="09:35",
                        entry_start="09:35", entry_end="11:00",
                        flat_start="15:50", flat_end="16:00",
                        stop_atr_pct=stop, min_gap_atr_pct=gap,
                    )
                    cfg = with_overrides(BASE, rr=rr, tp1_ratio=tp1, sessions=(sess,))
                    trades = run_backtest(df, cfg, start_date=START_DATE,
                                          df_1m=df_1m, df_1s=df_1s)
                    m = compute_metrics(trades)
                    results.append((stop, rr, gap, tp1, m))
                    done += 1
                    if done % 50 == 0 or done == TOTAL:
                        elapsed = time.time() - t0
                        eta = elapsed / done * (TOTAL - done) if done > 0 else 0
                        print(f"\r  {done}/{TOTAL} ({done/TOTAL:.0%}) "
                              f"[{elapsed:.0f}s, ETA {eta:.0f}s]          ",
                              end="", flush=True)

    elapsed = time.time() - t0
    print(f"\n  Completed {TOTAL} combos in {elapsed:.0f}s ({elapsed/TOTAL:.1f}s/combo)")

    # ── Sort by Calmar and display top 20 ────────────────────────────────────

    results.sort(key=lambda x: x[4]["calmar_ratio"], reverse=True)

    print()
    print("=" * 70)
    print("  TOP 20 BY CALMAR")
    print("=" * 70)
    print(f"  {'Rank':>4s}  {'stop':>5s}  {'rr':>4s}  {'gap':>4s}  {'tp1':>4s}"
          f"  {'Trades':>6s}  {'WR':>5s}  {'Net R':>7s}  {'R/yr':>6s}"
          f"  {'DD':>7s}  {'Calmar':>7s}  {'Sharpe':>7s}  {'NegYr':>5s}")
    print("  " + "-" * 95)

    anchor_rank = None
    for i, (stop, rr, gap, tp1, m) in enumerate(results[:20]):
        is_anchor = (stop == ANCHOR_STOP and rr == ANCHOR_RR and
                     gap == ANCHOR_GAP and tp1 == ANCHOR_TP1)
        marker = " *" if is_anchor else ""
        if is_anchor:
            anchor_rank = i + 1
        print(f"  {i+1:>4d}  {stop:>5.1f}  {rr:>4.1f}  {gap:>4.1f}  {tp1:>4.1f}"
              f"  {m['total_trades']:>6d}  {m['win_rate']:>4.1%}  {m['total_r']:>7.1f}"
              f"  {r_per_year(m):>6.1f}  {m['max_drawdown_r']:>7.1f}"
              f"  {m['calmar_ratio']:>7.2f}  {m['sharpe_ratio']:>7.3f}"
              f"  {neg_years(m):>5d}{marker}")

    # Find anchor rank if not in top 20
    if anchor_rank is None:
        for i, (stop, rr, gap, tp1, m) in enumerate(results):
            if (stop == ANCHOR_STOP and rr == ANCHOR_RR and
                    gap == ANCHOR_GAP and tp1 == ANCHOR_TP1):
                anchor_rank = i + 1
                print(f"\n  Anchor at rank #{anchor_rank}/{TOTAL}:")
                print(f"  {anchor_rank:>4d}  {stop:>5.1f}  {rr:>4.1f}  {gap:>4.1f}  {tp1:>4.1f}"
                      f"  {m['total_trades']:>6d}  {m['win_rate']:>4.1%}  {m['total_r']:>7.1f}"
                      f"  {r_per_year(m):>6.1f}  {m['max_drawdown_r']:>7.1f}"
                      f"  {m['calmar_ratio']:>7.2f}  {m['sharpe_ratio']:>7.3f}"
                      f"  {neg_years(m):>5d} *")
                break

    # ── Top 20 with 0 neg years ──────────────────────────────────────────────

    zero_neg = [(s, rr, g, tp1, m) for s, rr, g, tp1, m in results if neg_years(m) == 0]
    print()
    print("=" * 70)
    print(f"  TOP 20 BY CALMAR (0 negative full years only) — {len(zero_neg)}/{TOTAL} combos")
    print("=" * 70)
    print(f"  {'Rank':>4s}  {'stop':>5s}  {'rr':>4s}  {'gap':>4s}  {'tp1':>4s}"
          f"  {'Trades':>6s}  {'WR':>5s}  {'Net R':>7s}  {'R/yr':>6s}"
          f"  {'DD':>7s}  {'Calmar':>7s}  {'Sharpe':>7s}")
    print("  " + "-" * 85)

    for i, (stop, rr, gap, tp1, m) in enumerate(zero_neg[:20]):
        is_anchor = (stop == ANCHOR_STOP and rr == ANCHOR_RR and
                     gap == ANCHOR_GAP and tp1 == ANCHOR_TP1)
        marker = " *" if is_anchor else ""
        print(f"  {i+1:>4d}  {stop:>5.1f}  {rr:>4.1f}  {gap:>4.1f}  {tp1:>4.1f}"
              f"  {m['total_trades']:>6d}  {m['win_rate']:>4.1%}  {m['total_r']:>7.1f}"
              f"  {r_per_year(m):>6.1f}  {m['max_drawdown_r']:>7.1f}"
              f"  {m['calmar_ratio']:>7.2f}  {m['sharpe_ratio']:>7.3f}{marker}")

    # ── Parameter frequency in top 20 ────────────────────────────────────────

    print()
    print("=" * 70)
    print("  PARAMETER FREQUENCY IN TOP 20 (0 neg years)")
    print("=" * 70)

    for param_name, param_idx, values in [("stop", 0, STOPS), ("rr", 1, RRS),
                                           ("gap", 2, GAPS), ("tp1", 3, TP1S)]:
        counts = {}
        for v in values:
            counts[v] = sum(1 for x in zero_neg[:20] if x[param_idx] == v)
        print(f"  {param_name}: " + ", ".join(f"{v}→{c}" for v, c in counts.items() if c > 0))

    # ── Winner vs anchor delta ───────────────────────────────────────────────

    if zero_neg:
        ws, wrr, wg, wtp1, wm = zero_neg[0]
        am = None
        for s, r, g, t, m in results:
            if (s == ANCHOR_STOP and r == ANCHOR_RR and
                    g == ANCHOR_GAP and t == ANCHOR_TP1):
                am = m
                break

        print()
        print("=" * 70)
        print("  WINNER vs ANCHOR (0 neg years)")
        print("=" * 70)
        if am:
            print(f"  Winner: stop={ws} rr={wrr} gap={wg} tp1={wtp1}"
                  f"  Calmar {wm['calmar_ratio']:.2f}  Sharpe {wm['sharpe_ratio']:.3f}")
            print(f"  Anchor: stop={ANCHOR_STOP} rr={ANCHOR_RR} gap={ANCHOR_GAP} tp1={ANCHOR_TP1}"
                  f"  Calmar {am['calmar_ratio']:.2f}  Sharpe {am['sharpe_ratio']:.3f}")
            print(f"  Δ Calmar: {wm['calmar_ratio'] - am['calmar_ratio']:+.2f}")
            print(f"  Anchor rank: #{anchor_rank}/{TOTAL}")

    print()
    print("=" * 70)
    print("  GRID SWEEP COMPLETE")
    if anchor_rank and anchor_rank <= 3:
        print(f"  Anchor in top 3 (#{anchor_rank}) → CONVERGED. Proceed to pipeline.")
    elif anchor_rank and anchor_rank <= 10:
        print(f"  Anchor at #{anchor_rank} → Consider adopting winner if Δ > 0.5.")
    else:
        print(f"  Anchor at #{anchor_rank} → Adopt winner, re-sweep required.")
    print("=" * 70)
    print()
