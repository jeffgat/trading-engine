#!/usr/bin/env python3
"""FAST_V2 Portfolio — Alpha & Beta vs NQ Buy-and-Hold.

Runs all 5 FAST_V2 execution legs, combines daily PnL, and regresses
against NQ daily returns to measure market correlation.

Analysis windows:
  - 2-year  (2024-01-01 to 2025-12-31)
  - 10-year (2016-01-01 to 2025-12-31)

Metrics: beta, alpha (daily + annualized), R-squared, Pearson correlation,
up/down-market beta, rolling 60-day beta, per-leg beta breakdown.
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ, ES
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL
from orb_backtest.results.metrics import compute_metrics

# ── Date ranges ──────────────────────────────────────────────────────────

FULL_START = "2016-01-01"
FULL_END = "2025-12-31"

WINDOW_2YR = ("2024-01-01", "2025-12-31")
WINDOW_10YR = ("2016-01-01", "2025-12-31")

# ── FAST_V2 production configs (from exec_configs.json) ──────────────────

LEGS: dict[str, dict] = {
    "NQ_NY": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                orb_start="09:30",
                orb_end="09:45",
                entry_start="09:45",
                entry_end="13:00",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=8.0,
                min_gap_atr_pct=2.25,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.3,
            atr_length=14,
            risk_usd=400.0,
        ),
        "data": "NQ",
    },
    "NQ_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="07:00",
                stop_atr_pct=4.0,
                stop_orb_pct=150.0,
                min_gap_atr_pct=0.9,
                min_gap_orb_pct=15.0,
            ),),
            instrument=NQ,
            strategy="continuation",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=5.0,
            tp1_ratio=0.25,
            atr_length=5,
            risk_usd=400.0,
            excluded_dates=("20241218",),
            half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        ),
        "data": "NQ",
    },
    "ES_Asia": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:10",
                entry_start="20:10",
                entry_end="03:00",
                flat_start="06:45",
                flat_end="07:00",
                stop_atr_pct=2.5,
                min_gap_atr_pct=1.0,
            ),),
            instrument=ES,
            strategy="continuation",
            direction_filter="long",
            use_bar_magnifier=True,
            rr=1.75,
            tp1_ratio=0.3,
            atr_length=5,
            risk_usd=200.0,
            excluded_dates=("20241218",),
            half_days=("20250703", "20251128", "20251224", "20250109", "20260119"),
        ),
        "data": "ES",
    },
    "NQ_Asia_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="ASIA",
                rth_start="20:00",
                entry_start="20:45",
                entry_end="22:00",
                flat_start="00:00",
                flat_end="01:00",
                stop_atr_pct=0.0,
                min_gap_atr_pct=1.75,
            ),),
            instrument=NQ,
            strategy="lsi",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=1.75,
            tp1_ratio=0.7,
            atr_length=40,
            risk_usd=400.0,
            lsi_n_left=3,
            lsi_n_right=3,
            lsi_fvg_window_left=10,
            lsi_fvg_window_right=10,
            lsi_stop_mode="absolute",
            lsi_entry_mode="close",
            lsi_first_fvg_only=False,
            lsi_clean_path=False,
            lsi_be_swing_n_left=0,
            lsi_cancel_on_swing=False,
        ),
        "data": "NQ",
    },
    "NQ_NY_LSI": {
        "config": StrategyConfig(
            sessions=(SessionConfig(
                name="NY",
                rth_start="09:30",
                entry_start="10:10",
                entry_end="14:30",
                flat_start="15:50",
                flat_end="16:00",
                stop_atr_pct=0.0,
                min_gap_atr_pct=3.75,
            ),),
            instrument=NQ,
            strategy="lsi",
            direction_filter="both",
            use_bar_magnifier=True,
            rr=2.5,
            tp1_ratio=0.2,
            atr_length=10,
            risk_usd=400.0,
            lsi_n_left=5,
            lsi_n_right=60,
            lsi_fvg_window_left=20,
            lsi_fvg_window_right=5,
            lsi_stop_mode="absolute",
            lsi_entry_mode="fvg_limit",
            lsi_first_fvg_only=False,
            lsi_clean_path=False,
            lsi_be_swing_n_left=0,
            lsi_cancel_on_swing=False,
            excluded_days=(2, 3),  # Wed, Thu
        ),
        "data": "NQ",
    },
}

TOTAL_RISK = sum(leg["config"].risk_usd for leg in LEGS.values())  # $1,800


# ── Helpers ──────────────────────────────────────────────────────────────


def run_all_legs(
    data_cache: dict[str, tuple],
    start_date: str,
    end_date: str,
) -> dict[str, list]:
    """Run all 5 FAST_V2 legs. Returns {leg_name: [filled trades]}."""
    results = {}
    for leg_name, leg in LEGS.items():
        sym = leg["data"]
        df_5m, df_1m = data_cache[sym]
        cfg = leg["config"]
        trades = run_backtest(df_5m, cfg, start_date=start_date,
                              end_date=end_date, df_1m=df_1m)
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        results[leg_name] = filled
        print(f"  {leg_name:16s}  {len(filled):>5d} trades")
    return results


def compute_nq_daily_returns(df_5m: pd.DataFrame,
                             start: str, end: str) -> pd.Series:
    """NQ daily close-to-close returns from 5m data (RTH close at 15:55 bar)."""
    mask = (df_5m.index >= start) & (df_5m.index <= end)
    df = df_5m.loc[mask].copy()

    # Take the last bar at or before 16:00 each day as the daily close
    df["date"] = df.index.date
    df["time"] = df.index.time
    from datetime import time as dt_time
    rth_close = dt_time(15, 55)
    rth = df[df["time"] <= rth_close]
    daily_close = rth.groupby("date")["close"].last()
    daily_close = daily_close.dropna()
    daily_close.index = pd.DatetimeIndex(daily_close.index)

    returns = daily_close.pct_change().dropna()
    return returns


def compute_strategy_daily_returns(
    leg_results: dict[str, list],
    start: str,
    end: str,
) -> pd.Series:
    """Combine all legs into daily PnL, return as % of total risk."""
    daily_pnl: dict[str, float] = defaultdict(float)
    for leg_name, trades in leg_results.items():
        for t in trades:
            if t.date >= start and t.date <= end:
                daily_pnl[t.date] += t.pnl_usd

    if not daily_pnl:
        return pd.Series(dtype=float)

    s = pd.Series(daily_pnl)
    s.index = pd.DatetimeIndex(s.index)
    s = s.sort_index()
    # Convert to return-on-risk
    s = s / TOTAL_RISK
    return s


def align_returns(
    strat: pd.Series,
    market: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Align strategy and market returns. Fill missing strategy days with 0."""
    # Reindex strategy to all market trading days, fill with 0
    strat_aligned = strat.reindex(market.index, fill_value=0.0)
    return strat_aligned, market


def compute_alpha_beta(strat: pd.Series, mkt: pd.Series) -> dict:
    """OLS regression: strategy = alpha + beta * market + epsilon."""
    if len(strat) < 10:
        return {"beta": np.nan, "alpha_daily": np.nan, "alpha_annual": np.nan,
                "r_squared": np.nan, "correlation": np.nan,
                "up_beta": np.nan, "down_beta": np.nan,
                "n_days": len(strat), "active_days": int((strat != 0).sum())}

    slope, intercept, r_value, p_value, std_err = stats.linregress(mkt, strat)

    # Up-market beta (market > 0)
    up_mask = mkt > 0
    if up_mask.sum() >= 10:
        up_slope, *_ = stats.linregress(mkt[up_mask], strat[up_mask])
    else:
        up_slope = np.nan

    # Down-market beta (market < 0)
    down_mask = mkt < 0
    if down_mask.sum() >= 10:
        down_slope, *_ = stats.linregress(mkt[down_mask], strat[down_mask])
    else:
        down_slope = np.nan

    return {
        "beta": slope,
        "alpha_daily": intercept,
        "alpha_annual": intercept * 252,
        "r_squared": r_value ** 2,
        "correlation": r_value,
        "p_value": p_value,
        "std_err": std_err,
        "up_beta": up_slope,
        "down_beta": down_slope,
        "n_days": len(strat),
        "active_days": int((strat != 0).sum()),
    }


def compute_rolling_beta(strat: pd.Series, mkt: pd.Series,
                         window: int = 60) -> pd.Series:
    """Rolling OLS beta over a sliding window."""
    betas = []
    dates = []
    for i in range(window, len(strat)):
        s = strat.iloc[i - window:i]
        m = mkt.iloc[i - window:i]
        if m.std() == 0:
            betas.append(np.nan)
        else:
            slope, *_ = stats.linregress(m, s)
            betas.append(slope)
        dates.append(strat.index[i])
    return pd.Series(betas, index=dates, name="rolling_beta")


def compute_per_leg_beta(
    leg_results: dict[str, list],
    market: pd.Series,
    start: str,
    end: str,
) -> dict[str, dict]:
    """Compute alpha/beta for each leg individually."""
    per_leg = {}
    for leg_name, trades in leg_results.items():
        risk = LEGS[leg_name]["config"].risk_usd
        daily_pnl: dict[str, float] = defaultdict(float)
        for t in trades:
            if t.date >= start and t.date <= end:
                daily_pnl[t.date] += t.pnl_usd
        if not daily_pnl:
            per_leg[leg_name] = {"beta": np.nan, "correlation": np.nan,
                                 "trades": 0}
            continue
        s = pd.Series(daily_pnl)
        s.index = pd.DatetimeIndex(s.index)
        s = s.sort_index() / risk
        s_aligned = s.reindex(market.index, fill_value=0.0)
        result = compute_alpha_beta(s_aligned, market)
        result["trades"] = len(trades)
        per_leg[leg_name] = result
    return per_leg


# ── Output ───────────────────────────────────────────────────────────────


def print_header():
    print()
    print("=" * 72)
    print("  FAST_V2 PORTFOLIO — Alpha & Beta vs NQ Buy-and-Hold")
    print("=" * 72)
    print()
    print(f"  Total daily risk: ${TOTAL_RISK:,.0f}  "
          f"({len(LEGS)} legs)")
    for name, leg in LEGS.items():
        cfg = leg["config"]
        print(f"    {name:16s}  ${cfg.risk_usd:>6,.0f}  "
              f"{cfg.strategy:13s}  RR {cfg.rr}")
    print()


def print_comparison(res_2yr: dict, res_10yr: dict):
    print()
    print("-" * 72)
    print(f"  {'Metric':<28s}  {'2-Year (2024-2025)':>20s}  "
          f"{'10-Year (2016-2025)':>20s}")
    print("-" * 72)

    rows = [
        ("Beta",           "beta",         ".4f"),
        ("Alpha (daily)",  "alpha_daily",  ".4%"),
        ("Alpha (annualized)", "alpha_annual", ".2%"),
        ("R-squared",      "r_squared",    ".4f"),
        ("Correlation",    "correlation",  ".4f"),
        ("p-value",        "p_value",      ".2e"),
        ("Up-Market Beta", "up_beta",      ".4f"),
        ("Down-Market Beta", "down_beta",  ".4f"),
        ("Trading Days",   "n_days",       "d"),
        ("Strategy Active Days", "active_days", "d"),
    ]

    for label, key, fmt in rows:
        v2 = res_2yr.get(key, np.nan)
        v10 = res_10yr.get(key, np.nan)
        if isinstance(v2, float) and np.isnan(v2):
            s2 = "N/A"
        else:
            s2 = f"{v2:{fmt}}"
        if isinstance(v10, float) and np.isnan(v10):
            s10 = "N/A"
        else:
            s10 = f"{v10:{fmt}}"
        print(f"  {label:<28s}  {s2:>20s}  {s10:>20s}")

    print("-" * 72)


def print_rolling_beta_stats(rolling: pd.Series):
    print()
    print("  Rolling 60-day Beta (10-year):")
    clean = rolling.dropna()
    if len(clean) == 0:
        print("    No data")
        return
    print(f"    Mean: {clean.mean():.4f}   "
          f"Std: {clean.std():.4f}   "
          f"Min: {clean.min():.4f}   "
          f"Max: {clean.max():.4f}")
    # Quartiles
    print(f"    P25:  {clean.quantile(0.25):.4f}   "
          f"P50: {clean.quantile(0.50):.4f}   "
          f"P75: {clean.quantile(0.75):.4f}")


def print_per_leg(per_leg_2yr: dict, per_leg_10yr: dict):
    print()
    print("-" * 72)
    print("  Per-Leg Beta Breakdown")
    print("-" * 72)
    print(f"  {'Leg':<16s}  {'Beta (2yr)':>10s}  {'Corr (2yr)':>10s}  "
          f"{'Beta (10yr)':>11s}  {'Corr (10yr)':>11s}  {'Trades':>7s}")
    print(f"  {'-'*16}  {'-'*10}  {'-'*10}  {'-'*11}  {'-'*11}  {'-'*7}")
    for leg_name in LEGS:
        r2 = per_leg_2yr.get(leg_name, {})
        r10 = per_leg_10yr.get(leg_name, {})
        b2 = r2.get("beta", np.nan)
        c2 = r2.get("correlation", np.nan)
        b10 = r10.get("beta", np.nan)
        c10 = r10.get("correlation", np.nan)
        n = r10.get("trades", 0)
        print(f"  {leg_name:<16s}  "
              f"{b2:>10.4f}  {c2:>10.4f}  "
              f"{b10:>11.4f}  {c10:>11.4f}  {n:>7d}")
    print("-" * 72)


def save_plot(strat_2yr, mkt_2yr, strat_10yr, mkt_10yr, rolling_beta):
    """Save scatter + rolling beta plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n  (matplotlib not available — skipping plot)")
        return

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle("FAST_V2 Alpha & Beta vs NQ Buy-and-Hold", fontsize=14)

    # Scatter: 2-year
    ax = axes[0, 0]
    ax.scatter(mkt_2yr * 100, strat_2yr * 100, alpha=0.3, s=8, c="steelblue")
    slope, intercept, *_ = stats.linregress(mkt_2yr, strat_2yr)
    x_line = np.linspace(mkt_2yr.min(), mkt_2yr.max(), 100)
    ax.plot(x_line * 100, (intercept + slope * x_line) * 100,
            "r-", linewidth=1.5, label=f"beta={slope:.3f}")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.axvline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_xlabel("NQ Daily Return (%)")
    ax.set_ylabel("Strategy Daily Return (%)")
    ax.set_title("2-Year (2024-2025)")
    ax.legend()

    # Scatter: 10-year
    ax = axes[0, 1]
    ax.scatter(mkt_10yr * 100, strat_10yr * 100, alpha=0.15, s=6, c="steelblue")
    slope, intercept, *_ = stats.linregress(mkt_10yr, strat_10yr)
    x_line = np.linspace(mkt_10yr.min(), mkt_10yr.max(), 100)
    ax.plot(x_line * 100, (intercept + slope * x_line) * 100,
            "r-", linewidth=1.5, label=f"beta={slope:.3f}")
    ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.axvline(0, color="gray", linewidth=0.5, linestyle="--")
    ax.set_xlabel("NQ Daily Return (%)")
    ax.set_ylabel("Strategy Daily Return (%)")
    ax.set_title("10-Year (2016-2025)")
    ax.legend()

    # Rolling beta
    ax = axes[1, 0]
    clean = rolling_beta.dropna()
    if len(clean) > 0:
        ax.plot(clean.index, clean.values, linewidth=0.8, color="steelblue")
        ax.axhline(0, color="gray", linewidth=0.5, linestyle="--")
        ax.axhline(clean.mean(), color="red", linewidth=1, linestyle="--",
                   alpha=0.7, label=f"mean={clean.mean():.3f}")
        ax.fill_between(clean.index,
                        clean.mean() - clean.std(),
                        clean.mean() + clean.std(),
                        alpha=0.1, color="red")
    ax.set_title("Rolling 60-day Beta")
    ax.set_ylabel("Beta")
    ax.legend()

    # Cumulative returns comparison
    ax = axes[1, 1]
    cum_strat = (1 + strat_10yr).cumprod() - 1
    cum_mkt = (1 + mkt_10yr).cumprod() - 1
    ax.plot(cum_strat.index, cum_strat.values * 100,
            linewidth=1, color="steelblue", label="FAST_V2")
    ax.plot(cum_mkt.index, cum_mkt.values * 100,
            linewidth=1, color="gray", alpha=0.7, label="NQ B&H")
    ax.set_title("Cumulative Returns (10-Year)")
    ax.set_ylabel("Return (%)")
    ax.legend()

    plt.tight_layout()
    out_path = Path(__file__).resolve().parent.parent / "data" / "results" / "fast_v2_alpha_beta.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.savefig(out_path, dpi=150)
    print(f"\n  Plot saved to {out_path}")
    plt.close()


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    t0 = time.time()
    print_header()

    # Load data
    print("Loading data...")
    data_cache: dict[str, tuple] = {}
    for sym in ("NQ", "ES"):
        df_5m = load_5m_data(f"{sym}_5m")
        df_1m = load_1m_for_5m(f"{sym}_5m")
        data_cache[sym] = (df_5m, df_1m)
        print(f"  {sym}: {len(df_5m):,} 5m bars, "
              f"{len(df_1m):,} 1m bars, "
              f"{df_5m.index[0].date()} to {df_5m.index[-1].date()}")

    # Run all legs
    print(f"\nRunning backtests ({FULL_START} to {FULL_END})...")
    leg_results = run_all_legs(data_cache, FULL_START, FULL_END)
    total_trades = sum(len(v) for v in leg_results.values())
    print(f"  Total filled trades: {total_trades:,}")

    # Compute NQ daily returns (benchmark)
    print("\nComputing NQ daily returns...")
    nq_5m = data_cache["NQ"][0]
    nq_daily = compute_nq_daily_returns(nq_5m, FULL_START, FULL_END)
    print(f"  {len(nq_daily):,} trading days, "
          f"mean daily return: {nq_daily.mean():.4%}, "
          f"std: {nq_daily.std():.4%}")

    # Compute strategy daily returns (combined)
    strat_daily = compute_strategy_daily_returns(leg_results, FULL_START, FULL_END)
    print(f"  Strategy: {len(strat_daily):,} active days, "
          f"mean daily return: {strat_daily.mean():.4%}")

    # ── 2-year window ────────────────────────────────────────────────────
    start_2, end_2 = WINDOW_2YR
    mkt_2yr = nq_daily[(nq_daily.index >= start_2) & (nq_daily.index <= end_2)]
    strat_2yr_raw = compute_strategy_daily_returns(leg_results, start_2, end_2)
    strat_2yr, mkt_2yr = align_returns(strat_2yr_raw, mkt_2yr)
    res_2yr = compute_alpha_beta(strat_2yr, mkt_2yr)

    # ── 10-year window ───────────────────────────────────────────────────
    start_10, end_10 = WINDOW_10YR
    mkt_10yr = nq_daily[(nq_daily.index >= start_10) & (nq_daily.index <= end_10)]
    strat_10yr_raw = compute_strategy_daily_returns(leg_results, start_10, end_10)
    strat_10yr, mkt_10yr = align_returns(strat_10yr_raw, mkt_10yr)
    res_10yr = compute_alpha_beta(strat_10yr, mkt_10yr)

    # Rolling beta (10-year)
    rolling = compute_rolling_beta(strat_10yr, mkt_10yr, window=60)

    # Per-leg breakdown
    per_leg_2yr = compute_per_leg_beta(leg_results, mkt_2yr, start_2, end_2)
    per_leg_10yr = compute_per_leg_beta(leg_results, mkt_10yr, start_10, end_10)

    # ── Print results ────────────────────────────────────────────────────
    print_comparison(res_2yr, res_10yr)
    print_rolling_beta_stats(rolling)
    print_per_leg(per_leg_2yr, per_leg_10yr)

    # Interpretation
    print()
    print("  Interpretation:")
    b = res_10yr["beta"]
    r2 = res_10yr["r_squared"]
    if abs(b) < 0.05:
        print(f"    Beta ~ 0 ({b:.4f}): strategy is market-neutral")
    elif b > 0:
        print(f"    Beta > 0 ({b:.4f}): strategy has slight long bias / "
              f"tends to profit when NQ rises")
    else:
        print(f"    Beta < 0 ({b:.4f}): strategy tends to profit when "
              f"NQ falls (contrarian)")

    if r2 < 0.01:
        print(f"    R-squared ~ 0 ({r2:.4f}): market explains almost none "
              f"of strategy variance")
    elif r2 < 0.10:
        print(f"    R-squared low ({r2:.4f}): weak market dependence")
    else:
        print(f"    R-squared {r2:.4f}: moderate-to-strong market dependence")

    elapsed = time.time() - t0
    print(f"\n  Completed in {elapsed:.1f}s")

    # Plot
    save_plot(strat_2yr, mkt_2yr, strat_10yr, mkt_10yr, rolling)

    print()


if __name__ == "__main__":
    main()
