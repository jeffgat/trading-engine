#!/usr/bin/env python3
"""NQ LDN Continuation — Fixed-param Walk-Forward + Hold-out.

Tests both the grid winner and R2 anchor to see which performs better OOS.

Grid winner: stop=8.0%, rr=2.5, gap=1.5%, tp1=0.5 (Calmar 1.13, neg: [2016])
R2 anchor:   stop=10.0%, rr=2.0, gap=1.0%, tp1=0.5 (Calmar 1.12, neg: [2016])

Common: ORB=15m, entry≤08:25, flat=08:20, ATR=14, both, ICF=ON, no DOW excl, 1s magnifier

6 folds (OOS 2019-2024, each 12 months), hold-out 2025+.
GO criteria: all 6 folds profitable, hold-out Sharpe>0.5 + PF>1.0 + totalR>0
"""

import sys
import time
from dataclasses import replace

sys.path.insert(0, "src")

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

# -- Configs -------------------------------------------------------------------

BASE_SESSION = SessionConfig(
    name="LDN",
    orb_start="03:00", orb_end="03:15", entry_start="03:15",
    entry_end="08:25", flat_start="08:20", flat_end="08:25",
    stop_atr_pct=10.0, min_gap_atr_pct=1.0, max_gap_points=20.0, max_gap_atr_pct=0.0,
)

BASE = StrategyConfig(
    sessions=(BASE_SESSION,), instrument=NQ, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
    rr=2.0, tp1_ratio=0.5, atr_length=14, impulse_close_filter=True,
)

CONFIGS = {
    "R2 Anchor (s10/rr2.0/g1.0/tp0.5)": BASE,
    "Grid Winner (s8/rr2.5/g1.5/tp0.5)": replace(
        BASE,
        sessions=(replace(BASE_SESSION, stop_atr_pct=8.0, min_gap_atr_pct=1.5),),
        rr=2.5,
    ),
    "Grid #2 (s8/rr2.25/g1.5/tp0.6)": replace(
        BASE,
        sessions=(replace(BASE_SESSION, stop_atr_pct=8.0, min_gap_atr_pct=1.5),),
        rr=2.25, tp1_ratio=0.6,
    ),
}

FOLDS = [
    ("2019", "2019-01-01", "2019-12-31"),
    ("2020", "2020-01-01", "2020-12-31"),
    ("2021", "2021-01-01", "2021-12-31"),
    ("2022", "2022-01-01", "2022-12-31"),
    ("2023", "2023-01-01", "2023-12-31"),
    ("2024", "2024-01-01", "2024-12-31"),
]


def run_oos_fold(df_5m, df_1m, df_1s, config, oos_start, oos_end):
    trades = run_backtest(df_5m, config, start_date=oos_start, df_1m=df_1m, df_1s=df_1s)
    trades = [t for t in trades if t.date >= oos_start and t.date <= oos_end]
    return trades


def main():
    print("NQ LDN Continuation — Walk-Forward + Hold-out")
    print("=" * 100)

    t0 = time.time()
    print("\nLoading data...", flush=True)
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time()-t0:.1f}s]")

    for cfg_name, config in CONFIGS.items():
        print(f"\n\n{'='*100}")
        print(f"  {cfg_name}")
        print(f"{'='*100}")

        hdr = "  Fold   OOS Period   Trades    WR     PF  Sharpe   Net R      DD"
        sep = "  " + "-" * 72
        print(f"\n  Walk-Forward (6 folds, OOS 2019-2024)")
        print(hdr)
        print(sep)

        all_oos_trades = []
        fold_results = []
        for name, oos_start, oos_end in FOLDS:
            trades = run_oos_fold(df_5m, df_1m, df_1s, config, oos_start, oos_end)
            m = compute_metrics(trades)
            all_oos_trades.extend(trades)
            fold_results.append((name, m))
            print(f"  {name:>4}   {oos_start[:4]}         {m['total_trades']:>6}  {m['win_rate']:>5.1%}  "
                  f"{m['profit_factor']:>5.2f}  {m['sharpe_ratio']:>6.2f}  {m['total_r']:>6.1f}  {m['max_drawdown_r']:>7.1f}")

        # Combined OOS
        m_comb = compute_metrics(all_oos_trades)
        r_yr = m_comb["total_r"] / 6
        calmar_oos = r_yr / abs(m_comb["max_drawdown_r"]) if m_comb["max_drawdown_r"] != 0 else 0
        print(sep)
        print(f"  Comb   2019-2024    {m_comb['total_trades']:>6}  {m_comb['win_rate']:>5.1%}  "
              f"{m_comb['profit_factor']:>5.2f}  {m_comb['sharpe_ratio']:>6.2f}  {m_comb['total_r']:>6.1f}  {m_comb['max_drawdown_r']:>7.1f}")
        print(f"  R/yr={r_yr:.1f}  Calmar={calmar_oos:.2f}")

        # Hold-out (2025+)
        print(f"\n  Hold-out (2025+)")
        ho_trades = run_oos_fold(df_5m, df_1m, df_1s, config, "2025-01-01", "2026-12-31")
        m_ho = compute_metrics(ho_trades)
        print(f"  Trades: {m_ho['total_trades']} | WR: {m_ho['win_rate']:.1%} | PF: {m_ho['profit_factor']:.2f} | "
              f"Sharpe: {m_ho['sharpe_ratio']:.2f} | Net R: {m_ho['total_r']:.1f} | DD: {m_ho['max_drawdown_r']:.1f}")

        # Verdict
        all_profitable = all(m["total_r"] > 0 for _, m in fold_results)
        ho_pass = m_ho["sharpe_ratio"] > 0.5 and m_ho["profit_factor"] > 1.0 and m_ho["total_r"] > 0
        failed_folds = [name for name, m in fold_results if m["total_r"] <= 0]

        print(f"\n  VERDICT:")
        print(f"    All 6 folds profitable: {all_profitable}", end="")
        if failed_folds:
            print(f"  (FAILED: {', '.join(failed_folds)})")
        else:
            print()
        print(f"    Hold-out PASS: {ho_pass} (Sharpe={m_ho['sharpe_ratio']:.2f}, PF={m_ho['profit_factor']:.2f}, R={m_ho['total_r']:.1f})")
        verdict = "GO" if all_profitable and ho_pass else "NO-GO"
        print(f"    ** {verdict} **")

    print(f"\n\n  Total runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
