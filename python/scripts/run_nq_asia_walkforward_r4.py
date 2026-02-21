#!/usr/bin/env python3
"""NQ Asia ORB — Fixed-param walk-forward + hold-out test on R4 anchor.

Config: stop=3.7%, rr=1.75, gap=0.90%, tp1=0.35, ORB=10m, entry≤01:00,
        flat=00:00, ATR=5, direction=both, no-Thursday, ICF=OFF, 1s magnifier
"""

import sys
import time

sys.path.insert(0, "src")

from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest
from orb_backtest.results.metrics import compute_metrics

DOW_EXCL = {3}

ANCHOR_SESSION = SessionConfig(
    name="Asia",
    orb_start="20:00", orb_end="20:10", entry_start="20:10",
    entry_end="01:00", flat_start="00:00", flat_end="07:00",
    stop_atr_pct=3.7, min_gap_atr_pct=0.90, max_gap_points=0.0, max_gap_atr_pct=5.0,
)

ANCHOR = StrategyConfig(
    sessions=(ANCHOR_SESSION,), instrument=NQ, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="both",
    rr=1.75, tp1_ratio=0.35, atr_length=5, name="NQ Asia R4 Final",
)


def run_oos_fold(df_5m, df_1m, df_1s, oos_start, oos_end):
    """Run backtest and filter to OOS window."""
    trades = run_backtest(df_5m, ANCHOR, start_date=oos_start, df_1m=df_1m, df_1s=df_1s)
    trades = [t for t in trades if t.date >= oos_start and t.date <= oos_end]
    trades = apply_dow_filter(trades, DOW_EXCL)
    return trades


def main():
    print("NQ Asia ORB — Fixed-param Walk-Forward + Hold-out")
    print("Config: stop=3.7% rr=1.75 gap=0.90% tp1=0.35")
    print("ORB=10m, entry<=01:00, flat=00:00, ATR=5, both, no-Thu, ICF=OFF")
    print("=" * 90)

    t0 = time.time()
    print("\nLoading data...", flush=True)
    df_5m = load_5m_data("NQ_5m.csv")
    df_1m = load_1m_for_5m("NQ_5m.csv")
    df_1s = load_1s_for_5m("NQ_5m.csv")
    print(f"  Loaded [{time.time()-t0:.1f}s]")

    folds = [
        ("2019", "2019-01-01", "2019-12-31"),
        ("2020", "2020-01-01", "2020-12-31"),
        ("2021", "2021-01-01", "2021-12-31"),
        ("2022", "2022-01-01", "2022-12-31"),
        ("2023", "2023-01-01", "2023-12-31"),
        ("2024", "2024-01-01", "2024-12-31"),
    ]

    hdr = "  Fold   OOS Period   Trades    WR     PF  Sharpe   Net R      DD"
    sep = "  " + "-" * 72
    print(f"\nFixed-param Walk-Forward (6 folds, OOS 2019-2024)")
    print("=" * 90)
    print(hdr)
    print(sep)

    all_oos_trades = []
    fold_results = []
    for name, oos_start, oos_end in folds:
        trades = run_oos_fold(df_5m, df_1m, df_1s, oos_start, oos_end)
        m = compute_metrics(trades)
        all_oos_trades.extend(trades)
        fold_results.append((name, m))
        oos_yr = oos_start[:4]
        print(f"  {name:>4}   {oos_yr}         {m['total_trades']:>6}  {m['win_rate']:>5.1%}  "
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
    print(f"\nHold-out (2025+)")
    print("=" * 90)
    ho_trades = run_oos_fold(df_5m, df_1m, df_1s, "2025-01-01", "2026-12-31")
    m_ho = compute_metrics(ho_trades)
    print(f"  Trades: {m_ho['total_trades']} | WR: {m_ho['win_rate']:.1%} | PF: {m_ho['profit_factor']:.2f} | "
          f"Sharpe: {m_ho['sharpe_ratio']:.2f} | Net R: {m_ho['total_r']:.1f} | DD: {m_ho['max_drawdown_r']:.1f}")

    # Verdict
    all_profitable = all(m["total_r"] > 0 for _, m in fold_results)
    ho_pass = m_ho["sharpe_ratio"] > 0.5 and m_ho["profit_factor"] > 1.0 and m_ho["total_r"] > 0

    print(f"\nVERDICT")
    print("=" * 90)
    print(f"  All 6 folds profitable: {all_profitable}")
    for name, m in fold_results:
        status = "+" if m["total_r"] > 0 else "FAIL"
        print(f"    {name}: {m['total_r']:+.1f}R ({status})")
    print(f"  Combined OOS Calmar: {calmar_oos:.2f}")
    print(f"  Hold-out PASS: {ho_pass} (Sharpe={m_ho['sharpe_ratio']:.2f}, PF={m_ho['profit_factor']:.2f})")

    verdict = "GO" if all_profitable and ho_pass else "NO-GO"
    print(f"\n  ** VERDICT: {verdict} **")
    print(f"  Config: stop=3.7% rr=1.75 gap=0.90% tp1=0.35")
    print(f"  ORB=10m, entry<=01:00, flat=00:00, ATR=5, both, no-Thu, ICF=OFF")
    print(f"  Full-history: Calmar 23.85, 21.1 R/yr, DD -8.9R, 0 neg years")
    print(f"\n  Total runtime: {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
