#!/usr/bin/env python3
"""GC continuation shorts — grid sweep R1.

4D grid over continuous parameters around converged R2 anchor:
  stop=3.0%, rr=7.0, gap=5.0%, tp1=0.5, ATR 10, 15m ORB, entry→15:00, max_gap_atr=30%
  Calmar 0.45, 1 neg year (2024)

Grid: stop × rr × gap × tp1 = 5 × 5 × 5 × 4 = 500 combos
10-tick minimum stop: WAIVED for GC shorts.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import GC
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.data.news_dates import FOMC_DATES
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

INSTRUMENT = GC
START_DATE = "2016-01-01"
DATA_YEARS = 10.15
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")
CURRENT_YEAR = "2026"

# ── Fixed anchor params (not in grid) ────────────────────────────────────────

ATR_LENGTH = 10
ORB_END = "09:45"      # 15m
ENTRY_END = "15:00"
FLAT_START = "15:50"
MAX_GAP_ATR = 30.0
MAX_GAP_PTS = 25.0
ICF = False

# ── Grid dimensions ──────────────────────────────────────────────────────────

STOP_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0]
RR_VALUES   = [5.0, 6.0, 7.0, 8.0, 10.0]
GAP_VALUES  = [4.0, 4.5, 5.0, 5.5, 6.0]
TP1_VALUES  = [0.4, 0.5, 0.6, 0.7]

TOTAL_COMBOS = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)


def median_stop_ticks(trades, instrument):
    stops = [t.risk_points / instrument.min_tick for t in trades if t.exit_type != EXIT_NO_FILL]
    return median(stops) if stops else 0.0


def make_config(stop_atr_pct, rr, min_gap_atr_pct, tp1_ratio):
    session = SessionConfig(
        name="NY",
        orb_start="09:30", orb_end=ORB_END,
        entry_start=ORB_END, entry_end=ENTRY_END,
        flat_start=FLAT_START, flat_end="16:00",
        stop_atr_pct=stop_atr_pct,
        min_gap_atr_pct=min_gap_atr_pct,
    )
    return StrategyConfig(
        rr=rr, tp1_ratio=tp1_ratio, risk_usd=5000.0,
        atr_length=ATR_LENGTH,
        min_qty=1.0, qty_step=1.0,
        sessions=(session,), instrument=INSTRUMENT,
        strategy="continuation", direction_filter="short",
        impulse_close_filter=ICF,
        use_bar_magnifier=True,
        half_days=HALF_DAYS, excluded_dates=FOMC_DATES,
    )


# ── Load data ────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s\n")

# ── Run grid ─────────────────────────────────────────────────────────────────

print("=" * 130)
print(f"GRID SWEEP R1: GC NY Continuation Shorts — {TOTAL_COMBOS} combos")
print(f"  stop: {STOP_VALUES}")
print(f"  rr:   {RR_VALUES}")
print(f"  gap:  {GAP_VALUES}")
print(f"  tp1:  {TP1_VALUES}")
print(f"  Fixed: ATR {ATR_LENGTH}, 15m ORB, entry→{ENTRY_END}, max_gap_atr={MAX_GAP_ATR}%")
print("=" * 130)

results = []
t_start = time.time()

for i, stop in enumerate(STOP_VALUES):
    for rr in RR_VALUES:
        for gap in GAP_VALUES:
            for tp1 in TP1_VALUES:
                cfg = make_config(stop, rr, gap, tp1)
                trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
                filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

                if len(filled) < 5:
                    continue

                m = compute_metrics(filled)
                yearly = defaultdict(float)
                for t in filled:
                    yearly[t.date[:4]] += t.r_multiple

                nr = m["total_r"]
                dd = m["max_drawdown_r"]
                avg_annual = nr / DATA_YEARS
                calmar = abs(avg_annual / dd) if dd < 0 else 999.0
                neg_yrs = sum(1 for yr, r in yearly.items() if yr != CURRENT_YEAR and r < 0)
                med_stop = median_stop_ticks(filled, INSTRUMENT)

                results.append({
                    "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
                    "trades": len(filled), "wr": m["win_rate"],
                    "pf": m["profit_factor"], "nr": nr, "r_yr": avg_annual,
                    "dd": dd, "calmar": calmar, "sharpe": m["sharpe_ratio"],
                    "neg_years": neg_yrs, "med_stop": med_stop,
                    "yearly": {yr: round(r, 1) for yr, r in sorted(yearly.items())},
                })

                n_done = len(results)
                if n_done % 50 == 0:
                    elapsed = time.time() - t_start
                    rate = n_done / elapsed
                    eta = (TOTAL_COMBOS - n_done) / rate if rate > 0 else 0
                    print(f"  [{n_done}/{TOTAL_COMBOS}] {elapsed:.0f}s elapsed, {rate:.1f} combos/s, ETA {eta:.0f}s")

elapsed_total = time.time() - t_start
print(f"\n  Grid complete: {len(results)} combos in {elapsed_total:.0f}s ({len(results)/elapsed_total:.1f} combos/s)\n")

# ── Sort by Calmar ───────────────────────────────────────────────────────────

results.sort(key=lambda r: r["calmar"], reverse=True)

# ── Top 20 (all combos) ─────────────────────────────────────────────────────

print("=" * 130)
print("TOP 20 BY CALMAR (all combos)")
print("=" * 130)
print(f"  {'#':>3} | {'stop':>5} | {'rr':>4} | {'gap':>4} | {'tp1':>4} | {'Trd':>5} | "
      f"{'WR':>5} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | "
      f"{'Calmar':>7} | {'Sharpe':>7} | {'MedSt':>5} | {'NY':>2}")
print("  " + "-" * 115)

for i, r in enumerate(results[:20]):
    anchor_marker = " <<<" if r["stop"] == 3.0 and r["rr"] == 7.0 and r["gap"] == 5.0 and r["tp1"] == 0.5 else ""
    print(f"  {i+1:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | {r['gap']:>4.1f} | {r['tp1']:>4.1f} | "
          f"{r['trades']:>5} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | {r['nr']:>7.1f} | "
          f"{r['r_yr']:>6.1f} | {r['dd']:>7.1f} | {r['calmar']:>7.2f} | {r['sharpe']:>7.3f} | "
          f"{r['med_stop']:>5.1f} | {r['neg_years']:>2}{anchor_marker}")

# ── Top 20 (0 negative full years only) ─────────────────────────────────────

zero_neg = [r for r in results if r["neg_years"] == 0]
print(f"\n{'=' * 130}")
print(f"TOP 20 BY CALMAR (0 negative full years only — {len(zero_neg)} combos)")
print("=" * 130)
if zero_neg:
    print(f"  {'#':>3} | {'stop':>5} | {'rr':>4} | {'gap':>4} | {'tp1':>4} | {'Trd':>5} | "
          f"{'WR':>5} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | "
          f"{'Calmar':>7} | {'Sharpe':>7} | {'MedSt':>5}")
    print("  " + "-" * 105)
    for i, r in enumerate(zero_neg[:20]):
        anchor_marker = " <<<" if r["stop"] == 3.0 and r["rr"] == 7.0 and r["gap"] == 5.0 and r["tp1"] == 0.5 else ""
        print(f"  {i+1:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | {r['gap']:>4.1f} | {r['tp1']:>4.1f} | "
              f"{r['trades']:>5} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | {r['nr']:>7.1f} | "
              f"{r['r_yr']:>6.1f} | {r['dd']:>7.1f} | {r['calmar']:>7.2f} | {r['sharpe']:>7.3f} | "
              f"{r['med_stop']:>5.1f}{anchor_marker}")
else:
    print("  No combos with 0 negative full years.")

# ── Grid summary ─────────────────────────────────────────────────────────────

n_profitable = sum(1 for r in results if r["nr"] > 0)
n_zero_neg = len(zero_neg)
print(f"\n{'=' * 130}")
print("GRID SUMMARY")
print("=" * 130)
print(f"  Total combos:          {len(results)}")
print(f"  Profitable (R > 0):    {n_profitable} ({n_profitable/len(results)*100:.1f}%)")
print(f"  0 neg full years:      {n_zero_neg} ({n_zero_neg/len(results)*100:.1f}%)")

# Find anchor rank
anchor_rank = None
for i, r in enumerate(results):
    if r["stop"] == 3.0 and r["rr"] == 7.0 and r["gap"] == 5.0 and r["tp1"] == 0.5:
        anchor_rank = i + 1
        anchor_calmar = r["calmar"]
        break

winner = results[0]
if anchor_rank:
    delta = winner["calmar"] - anchor_calmar
    print(f"\n  Anchor rank: #{anchor_rank}/{len(results)} (Calmar {anchor_calmar:.2f})")
    print(f"  Grid winner: stop={winner['stop']}, rr={winner['rr']}, gap={winner['gap']}, tp1={winner['tp1']} "
          f"(Calmar {winner['calmar']:.2f})")
    print(f"  Delta: {delta:+.2f}")
    if delta > 0.5:
        print(f"\n  >>> Grid winner differs from anchor by >{0.5} Calmar. ADOPT new anchor → return to variable sweeps.")
    else:
        print(f"\n  >>> Grid winner close to anchor (Δ < 0.5). Convergence confirmed → proceed to robust pipeline.")
else:
    print(f"\n  Anchor not found in grid results (may have <5 trades)")
    print(f"  Grid winner: stop={winner['stop']}, rr={winner['rr']}, gap={winner['gap']}, tp1={winner['tp1']} "
          f"(Calmar {winner['calmar']:.2f})")

# Print R by year for winner and anchor
print(f"\n  Grid winner R by year: {winner['yearly']}")
if anchor_rank:
    anchor_r = results[anchor_rank - 1]
    print(f"  Anchor R by year:      {anchor_r['yearly']}")
