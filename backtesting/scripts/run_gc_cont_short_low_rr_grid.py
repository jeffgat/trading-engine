#!/usr/bin/env python3
"""GC continuation shorts — low R:R grid sweep.

Explore whether a profitable config exists at rr=2.0-3.0 where MC survival
is viable. Grid over stop × rr × gap × tp1 centered on the low R:R zone.

Fixed: ATR 10, 15m ORB, entry→15:00, max_gap_atr=30%, short-only, FOMC excl.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path
from statistics import median

import numpy as np

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
CURRENT_YEAR = "2026"
HALF_DAYS = ("20250703", "20251128", "20251224", "20250109", "20260119")

# ── Grid dimensions ──────────────────────────────────────────────────────────

STOP_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0]
RR_VALUES   = [1.5, 2.0, 2.5, 3.0, 3.5]
GAP_VALUES  = [3.0, 4.0, 5.0, 5.5, 6.0, 7.0]
TP1_VALUES  = [0.3, 0.4, 0.5, 0.6, 0.7]

TOTAL_COMBOS = len(STOP_VALUES) * len(RR_VALUES) * len(GAP_VALUES) * len(TP1_VALUES)

# ── MC config ────────────────────────────────────────────────────────────────

MC_SIMS = 2000
MC_RUIN_R = 25.0

# ── Fixed params ─────────────────────────────────────────────────────────────

ATR_LENGTH = 10
ORB_END = "09:45"
ENTRY_END = "15:00"
FLAT_START = "15:50"
MAX_GAP_ATR = 30.0
MAX_GAP_PTS = 25.0
ICF = False


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


def mc_survival(trades, ruin_r=MC_RUIN_R, n_sims=MC_SIMS):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    r_arr = np.array([t.r_multiple for t in filled])
    n = len(r_arr)
    if n < 10:
        return 0.0, 0.0
    rng = np.random.default_rng(42)
    paths = r_arr[rng.integers(0, n, size=(n_sims, n))]
    equity = np.cumsum(paths, axis=1)
    max_dd = np.min(equity - np.maximum.accumulate(equity, axis=1), axis=1)
    survival = float(np.mean(max_dd >= -ruin_r))
    dd_p50 = float(np.percentile(max_dd, 50))
    return survival, dd_p50


# ── Load data ────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s\n")

# ── Run grid ─────────────────────────────────────────────────────────────────

print("=" * 140)
print(f"LOW R:R GRID SWEEP: GC NY Continuation Shorts — {TOTAL_COMBOS} combos")
print(f"  stop: {STOP_VALUES}")
print(f"  rr:   {RR_VALUES}")
print(f"  gap:  {GAP_VALUES}")
print(f"  tp1:  {TP1_VALUES}")
print(f"  Fixed: ATR {ATR_LENGTH}, 15m ORB, entry→{ENTRY_END}, max_gap_atr={MAX_GAP_ATR}%")
print("=" * 140)

results = []
t_start = time.time()

for stop in STOP_VALUES:
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

                survival, dd_p50 = mc_survival(filled)

                results.append({
                    "stop": stop, "rr": rr, "gap": gap, "tp1": tp1,
                    "trades": len(filled), "wr": m["win_rate"],
                    "pf": m["profit_factor"], "nr": nr, "r_yr": avg_annual,
                    "dd": dd, "calmar": calmar, "sharpe": m["sharpe_ratio"],
                    "neg_years": neg_yrs, "mc_surv": survival, "mc_dd50": dd_p50,
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

# ── Top 20 by Calmar (all) ──────────────────────────────────────────────────

print("=" * 150)
print("TOP 20 BY CALMAR (all combos)")
print("=" * 150)
print(f"  {'#':>3} | {'stop':>5} | {'rr':>4} | {'gap':>4} | {'tp1':>4} | {'Trd':>5} | "
      f"{'WR':>6} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | "
      f"{'Calmar':>7} | {'Sharpe':>7} | {'NY':>2} | {'MC%':>6} | {'MC DD50':>7}")
print("  " + "-" * 130)

for i, r in enumerate(results[:20]):
    print(f"  {i+1:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | {r['gap']:>4.1f} | {r['tp1']:>4.1f} | "
          f"{r['trades']:>5} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | {r['nr']:>7.1f} | "
          f"{r['r_yr']:>6.1f} | {r['dd']:>7.1f} | {r['calmar']:>7.2f} | {r['sharpe']:>7.3f} | "
          f"{r['neg_years']:>2} | {r['mc_surv']:>5.1%} | {r['mc_dd50']:>7.1f}")

# ── Top 20 by MC survival (profitable only) ─────────────────────────────────

profitable = [r for r in results if r["nr"] > 0]
profitable.sort(key=lambda r: r["mc_surv"], reverse=True)

print()
print("=" * 150)
print(f"TOP 20 BY MC SURVIVAL (profitable combos only — {len(profitable)} combos)")
print("=" * 150)
print(f"  {'#':>3} | {'stop':>5} | {'rr':>4} | {'gap':>4} | {'tp1':>4} | {'Trd':>5} | "
      f"{'WR':>6} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | "
      f"{'Calmar':>7} | {'Sharpe':>7} | {'NY':>2} | {'MC%':>6} | {'MC DD50':>7}")
print("  " + "-" * 130)

for i, r in enumerate(profitable[:20]):
    print(f"  {i+1:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | {r['gap']:>4.1f} | {r['tp1']:>4.1f} | "
          f"{r['trades']:>5} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | {r['nr']:>7.1f} | "
          f"{r['r_yr']:>6.1f} | {r['dd']:>7.1f} | {r['calmar']:>7.2f} | {r['sharpe']:>7.3f} | "
          f"{r['neg_years']:>2} | {r['mc_surv']:>5.1%} | {r['mc_dd50']:>7.1f}")

# ── Top 20 by MC survival (MC >= 60% only) ──────────────────────────────────

mc_pass = [r for r in results if r["mc_surv"] >= 0.60 and r["nr"] > 0]
mc_pass.sort(key=lambda r: r["calmar"], reverse=True)

print()
print("=" * 150)
print(f"TOP 20 BY CALMAR (MC survival >= 60% AND profitable — {len(mc_pass)} combos)")
print("=" * 150)

if mc_pass:
    print(f"  {'#':>3} | {'stop':>5} | {'rr':>4} | {'gap':>4} | {'tp1':>4} | {'Trd':>5} | "
          f"{'WR':>6} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | {'MaxDD':>7} | "
          f"{'Calmar':>7} | {'Sharpe':>7} | {'NY':>2} | {'MC%':>6} | {'MC DD50':>7}")
    print("  " + "-" * 130)
    for i, r in enumerate(mc_pass[:20]):
        print(f"  {i+1:>3} | {r['stop']:>5.1f} | {r['rr']:>4.1f} | {r['gap']:>4.1f} | {r['tp1']:>4.1f} | "
              f"{r['trades']:>5} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | {r['nr']:>7.1f} | "
              f"{r['r_yr']:>6.1f} | {r['dd']:>7.1f} | {r['calmar']:>7.2f} | {r['sharpe']:>7.3f} | "
              f"{r['neg_years']:>2} | {r['mc_surv']:>5.1%} | {r['mc_dd50']:>7.1f}")

    # R by year for top 3
    print()
    print("  R by year for top 3 MC-passing configs:")
    for i, r in enumerate(mc_pass[:3]):
        yrs = "  ".join(f"{yr}:{v:>6.1f}" for yr, v in sorted(r["yearly"].items()))
        print(f"  #{i+1} rr={r['rr']} stop={r['stop']} gap={r['gap']} tp1={r['tp1']}: {yrs}")
else:
    print("  No combos with MC survival >= 60% AND profitable.")

# ── Grid summary ─────────────────────────────────────────────────────────────

print()
print("=" * 150)
print("GRID SUMMARY")
print("=" * 150)
print(f"  Total combos:          {len(results)}")
print(f"  Profitable (R > 0):    {len(profitable)} ({len(profitable)/len(results)*100:.1f}%)")
print(f"  MC >= 60%:             {sum(1 for r in results if r['mc_surv'] >= 0.60)} ({sum(1 for r in results if r['mc_surv'] >= 0.60)/len(results)*100:.1f}%)")
print(f"  MC >= 60% & profit:    {len(mc_pass)} ({len(mc_pass)/len(results)*100:.1f}%)")
