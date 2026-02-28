#!/usr/bin/env python3
"""GC continuation shorts — R:R sweep with MC survival analysis.

Sweep R:R from 2.0 to 10.0 at the converged anchor to find the WR / Calmar / MC
survival tradeoff curve. Goal: find a sweet spot where WR is high enough for
MC survival (>=60% at -25R) while Calmar stays reasonable.

Anchor: stop=3.0%, gap=5.5%, tp1=0.7, ATR 10, 15m ORB, entry→15:00,
        max_gap_atr=30%, short-only, FOMC excluded.
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

# ── Fixed anchor params ──────────────────────────────────────────────────────

GC_NY = SessionConfig(
    name="NY",
    orb_start="09:30",
    orb_end="09:45",
    entry_start="09:45",
    entry_end="15:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=3.0,
    min_gap_atr_pct=5.5,
)

# ── R:R values to sweep ─────────────────────────────────────────────────────

RR_VALUES = [2.0, 2.5, 3.0, 3.5, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0]

# ── MC config ────────────────────────────────────────────────────────────────

MC_SIMS = 5000
MC_RUIN_R = 25.0


def make_config(rr, tp1_ratio=0.7):
    return StrategyConfig(
        rr=rr,
        tp1_ratio=tp1_ratio,
        risk_usd=5000.0,
        atr_length=10,
        min_qty=1.0,
        qty_step=1.0,
        sessions=(GC_NY,),
        instrument=INSTRUMENT,
        strategy="continuation",
        direction_filter="short",
        use_bar_magnifier=True,
        half_days=HALF_DAYS,
        excluded_dates=FOMC_DATES,
    )


def mc_survival(trades, ruin_r=MC_RUIN_R, n_sims=MC_SIMS):
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    r_arr = np.array([t.r_multiple for t in filled])
    n = len(r_arr)
    if n < 10:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(42)
    paths = r_arr[rng.integers(0, n, size=(n_sims, n))]
    equity = np.cumsum(paths, axis=1)
    max_dd = np.min(equity - np.maximum.accumulate(equity, axis=1), axis=1)
    survival = float(np.mean(max_dd >= -ruin_r))
    dd_p50 = float(np.percentile(max_dd, 50))
    dd_p5 = float(np.percentile(max_dd, 5))
    return survival, dd_p50, dd_p5


# ── Load data ────────────────────────────────────────────────────────────────

print("Loading data...")
t0 = time.time()
df_5m = load_5m_data(INSTRUMENT.data_file)
df_1m = load_1m_for_5m(INSTRUMENT.data_file)
df_1s = load_1s_for_5m(INSTRUMENT.data_file)
print(f"  5m: {len(df_5m):,} | 1m: {len(df_1m):,} | 1s: {len(df_1s):,}")
print(f"  Loaded in {time.time() - t0:.1f}s\n")

# ── Sweep ────────────────────────────────────────────────────────────────────

print("=" * 140)
print("R:R SWEEP — GC NY Continuation Shorts (tp1=0.7 fixed)")
print("  Goal: find WR / Calmar / MC survival sweet spot")
print("=" * 140)
print()

results = []

for rr in RR_VALUES:
    cfg = make_config(rr)
    trades = run_backtest(df_5m, cfg, start_date=START_DATE, df_1m=df_1m, df_1s=df_1s)
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    m = compute_metrics(filled)

    yearly = defaultdict(float)
    for t in filled:
        yearly[t.date[:4]] += t.r_multiple

    nr = m["total_r"]
    dd = m["max_drawdown_r"]
    avg_annual = nr / DATA_YEARS
    calmar = abs(avg_annual / dd) if dd < 0 else 999.0
    neg_yrs = sum(1 for yr, r in yearly.items() if yr != CURRENT_YEAR and r < 0)

    survival, dd_p50, dd_p5 = mc_survival(filled)

    results.append({
        "rr": rr, "trades": len(filled), "wr": m["win_rate"],
        "pf": m["profit_factor"], "nr": nr, "r_yr": avg_annual,
        "dd": dd, "calmar": calmar, "sharpe": m["sharpe_ratio"],
        "neg_years": neg_yrs, "mc_surv": survival,
        "mc_dd_p50": dd_p50, "mc_dd_p5": dd_p5,
        "yearly": {yr: round(r, 1) for yr, r in sorted(yearly.items())},
    })
    print(f"  rr={rr:>4.1f} | Trades={len(filled):>4} | WR={m['win_rate']:>5.1%} | "
          f"PF={m['profit_factor']:>5.2f} | Net R={nr:>7.1f} | R/yr={avg_annual:>6.1f} | "
          f"DD={dd:>6.1f} | Calmar={calmar:>6.2f} | Sharpe={m['sharpe_ratio']:>6.3f} | "
          f"NY={neg_yrs} | MC={survival:>5.1%} | MC_DD50={dd_p50:>6.1f} | MC_DD5={dd_p5:>6.1f}")

# ── Summary table ────────────────────────────────────────────────────────────

print()
print("=" * 140)
print("SUMMARY TABLE")
print("=" * 140)
print(f"  {'R:R':>4} | {'Trd':>4} | {'WR':>6} | {'PF':>5} | {'Net R':>7} | {'R/yr':>6} | "
      f"{'MaxDD':>6} | {'Calmar':>7} | {'Sharpe':>7} | {'NY':>2} | "
      f"{'MC Surv':>7} | {'MC DD50':>7} | {'MC DD5':>7} | {'Verdict':>12}")
print("  " + "-" * 120)

for r in results:
    if r["mc_surv"] >= 0.60:
        verdict = "PASS"
    elif r["mc_surv"] >= 0.40:
        verdict = "MARGINAL"
    else:
        verdict = "FAIL"

    print(f"  {r['rr']:>4.1f} | {r['trades']:>4} | {r['wr']:>5.1%} | {r['pf']:>5.2f} | "
          f"{r['nr']:>7.1f} | {r['r_yr']:>6.1f} | {r['dd']:>6.1f} | {r['calmar']:>7.2f} | "
          f"{r['sharpe']:>7.3f} | {r['neg_years']:>2} | {r['mc_surv']:>6.1%} | "
          f"{r['mc_dd_p50']:>7.1f} | {r['mc_dd_p5']:>7.1f} | {verdict:>12}")

# ── R by year for key configs ────────────────────────────────────────────────

print()
print("=" * 140)
print("R BY YEAR — Key configs")
print("=" * 140)
for r in results:
    if r["rr"] in [2.0, 3.0, 4.0, 5.0, 8.0]:
        yrs = "  ".join(f"{yr}:{v:>6.1f}" for yr, v in sorted(r["yearly"].items()))
        print(f"  rr={r['rr']:>4.1f}: {yrs}")
