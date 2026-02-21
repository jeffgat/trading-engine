#!/usr/bin/env python3
"""ES London ORB Continuation — monthly loss cap sweep.

Applies a mechanical monthly loss stop post-hoc on the WF mode params:
  rr=3.0, stop=1.5%, gap=1.25%, tp1=0.5, be=0, both directions

Once cumulative monthly R hits -cap_r, all remaining trades that month are skipped.
Sweeps cap_r from 3R to 12R to find the optimal balance of DD reduction vs net R.
"""

import sys, time
from collections import defaultdict
sys.path.insert(0, "src")

import numpy as np

from orb_backtest.config import LDN_SESSION, StrategyConfig, with_overrides
from orb_backtest.data.instruments import ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics
from orb_backtest.analysis.gates import apply_monthly_loss_cap

START_DATE = "2016-01-01"
CAP_VALUES = [3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 12.0]


def get_metrics(trades):
    m = compute_metrics(trades)
    return {
        "trades": m["total_trades"], "wr": m["win_rate"], "pf": m["profit_factor"],
        "sharpe": m["sharpe_ratio"], "total_r": m["total_r"],
        "max_dd": m["max_drawdown_r"], "calmar": m["calmar_ratio"],
        "r_by_year": m.get("r_by_year", {}),
    }


def worst_month_r(trades):
    """Return worst single calendar month R from filled trades."""
    monthly = defaultdict(float)
    for t in trades:
        if t.exit_type != EXIT_NO_FILL:
            monthly[t.date[:7]] += t.r_multiple
    return min(monthly.values()) if monthly else 0.0


def months_halted(trades_base, trades_capped):
    """Count months where trading was halted by the cap."""
    filled_base = {t.date for t in trades_base if t.exit_type != EXIT_NO_FILL}
    filled_cap  = {t.date for t in trades_capped if t.exit_type != EXIT_NO_FILL}
    skipped_dates = filled_base - filled_cap
    return len({d[:7] for d in skipped_dates})


def main():
    print("ES LDN — Monthly Loss Cap Sweep")
    print("=" * 70)

    t0 = time.time()
    df_5m = load_5m_data("ES_5m.csv", start=None, end=None)
    df_1m = load_1m_for_5m("ES_5m.csv", start=None, end=None)
    print(f"Data loaded in {time.time() - t0:.1f}s")

    config = StrategyConfig(
        sessions=(LDN_SESSION,),
        instrument=ES,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        rr=3.0,
        tp1_ratio=0.5,
        name="ES LDN WF mode",
    )
    config = with_overrides(config, ldn_stop_atr_pct=1.5, ldn_min_gap_atr_pct=1.25)

    print("Running base backtest...", flush=True)
    t0 = time.time()
    base_trades = run_backtest(df_5m, config, start_date=START_DATE, df_1m=df_1m)
    print(f"Done in {time.time() - t0:.1f}s\n")

    base = get_metrics(base_trades)
    base_worst_month = worst_month_r(base_trades)

    print(f"Baseline: {base['trades']} trades, {base['wr']:.1%} WR, PF {base['pf']:.2f}, "
          f"Sharpe {base['sharpe']:.2f}, {base['total_r']:.1f}R, DD {base['max_dd']:.1f}R, "
          f"worst month {base_worst_month:.1f}R")

    # ── Cap sweep table ─────────────────────────────────────────────────
    print(f"\n{'='*130}")
    print(f"  MONTHLY LOSS CAP SWEEP")
    print(f"{'='*130}")
    print(f"{'Cap':>5} {'Trades':>7} {'Skipped':>8} {'Halted Mo':>10} {'WR':>6} {'PF':>6} "
          f"{'Sharpe':>7} {'Net R':>7} {'MaxDD':>7} {'Calmar':>7} {'Worst Mo':>9} {'vs Base':>8}")
    print("-" * 130)

    # Baseline row
    print(f"{'none':>5} {base['trades']:>7} {'0':>8} {'0':>10} {base['wr']:>5.1%} {base['pf']:>6.2f} "
          f"{base['sharpe']:>7.2f} {base['total_r']:>7.1f} {base['max_dd']:>7.1f} "
          f"{base['calmar']:>7.2f} {base_worst_month:>8.1f}R {'':>8}")

    rows = []
    for cap in CAP_VALUES:
        capped = apply_monthly_loss_cap(base_trades, cap_r=cap)
        m = get_metrics(capped)
        wm = worst_month_r(capped)
        skipped = base["trades"] - m["trades"]
        halted = months_halted(base_trades, capped)
        dd_delta = m["max_dd"] - base["max_dd"]

        print(f"{cap:>5.1f} {m['trades']:>7} {skipped:>8} {halted:>10} {m['wr']:>5.1%} {m['pf']:>6.2f} "
              f"{m['sharpe']:>7.2f} {m['total_r']:>7.1f} {m['max_dd']:>7.1f} "
              f"{m['calmar']:>7.2f} {wm:>8.1f}R {dd_delta:>+7.1f}R")
        rows.append({"cap": cap, "halted": halted, "skipped": skipped, "worst_month": wm, **m})

    # ── Annual R breakdown for key cap levels ───────────────────────────
    print(f"\n{'='*80}")
    print(f"  ANNUAL R BREAKDOWN — BASELINE vs BEST CAP CONFIGS")
    print(f"{'='*80}")

    key_caps = [None, 5.0, 6.0, 7.0]
    configs_to_show = []
    for cap in key_caps:
        if cap is None:
            configs_to_show.append(("Baseline", base_trades))
        else:
            configs_to_show.append((f"Cap={cap}R", apply_monthly_loss_cap(base_trades, cap_r=cap)))

    # Collect all years
    all_years = set()
    for _, t_list in configs_to_show:
        m = get_metrics(t_list)
        all_years.update(m["r_by_year"].keys())
    all_years = sorted(all_years)

    header = f"  {'Year':<6}" + "".join(f" {label:>12}" for label, _ in configs_to_show)
    print(header)
    print("  " + "-" * (6 + 13 * len(configs_to_show)))
    for year in all_years:
        row = f"  {year:<6}"
        for label, t_list in configs_to_show:
            m = get_metrics(t_list)
            r = m["r_by_year"].get(year, 0.0)
            row += f" {r:>+11.1f}R"
        print(row)

    # Totals
    row = f"  {'TOTAL':<6}"
    for label, t_list in configs_to_show:
        m = get_metrics(t_list)
        row += f" {m['total_r']:>+11.1f}R"
    print("  " + "-" * (6 + 13 * len(configs_to_show)))
    print(row)

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  SUMMARY")
    print(f"{'='*70}")
    print(f"  Baseline:  {base['trades']}t  Sharpe {base['sharpe']:.2f}  "
          f"DD {base['max_dd']:.1f}R  worst month {base_worst_month:.1f}R  Net R {base['total_r']:.1f}")

    best_sharpe = max(rows, key=lambda r: r["sharpe"])
    best_calmar = max(rows, key=lambda r: r["calmar"])
    best_dd     = max(rows, key=lambda r: r["max_dd"])  # least negative

    print(f"\n  Best Sharpe:  cap={best_sharpe['cap']}R → "
          f"Sharpe {best_sharpe['sharpe']:.2f}, DD {best_sharpe['max_dd']:.1f}R, "
          f"worst month {best_sharpe['worst_month']:.1f}R, {best_sharpe['trades']}t")
    print(f"  Best Calmar:  cap={best_calmar['cap']}R → "
          f"Calmar {best_calmar['calmar']:.2f}, DD {best_calmar['max_dd']:.1f}R, "
          f"worst month {best_calmar['worst_month']:.1f}R, {best_calmar['trades']}t")
    print(f"  Best DD:      cap={best_dd['cap']}R → "
          f"DD {best_dd['max_dd']:.1f}R, Sharpe {best_dd['sharpe']:.2f}, "
          f"worst month {best_dd['worst_month']:.1f}R, {best_dd['trades']}t")


if __name__ == "__main__":
    main()
