#!/usr/bin/env python3
"""HMM-based volatility regime analysis for NQ.

Fits a Gaussian HMM to daily NQ features (returns, realized vol, ATR, range)
to discover latent volatility regimes, then maps backtest performance to each regime.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from hmmlearn.hmm import GaussianHMM
from dataclasses import replace

from orb_backtest.config import NY_SESSION, default_config, with_overrides
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL


# ── 1. Load data and build daily features ─────────────────────────────

print("Loading NQ 5m data...")
df = load_5m_data(NQ.data_file, start="2016-01-01", end="2026-03-07")
print(f"  {len(df):,} bars ({df.index[0].date()} → {df.index[-1].date()})")

# Resample to daily OHLCV
daily = df.resample("1D").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna(subset=["open"])

# Filter to trading days only (non-zero volume or meaningful price action)
daily = daily[daily["volume"] > 0].copy()

# Daily features for HMM
daily["returns"] = daily["close"].pct_change()
daily["log_returns"] = np.log(daily["close"] / daily["close"].shift(1))
daily["range_pct"] = (daily["high"] - daily["low"]) / daily["close"]  # intraday range
daily["true_range"] = np.maximum(
    daily["high"] - daily["low"],
    np.maximum(
        abs(daily["high"] - daily["close"].shift(1)),
        abs(daily["low"] - daily["close"].shift(1))
    )
)
daily["atr_pct"] = daily["true_range"].rolling(14).mean() / daily["close"]  # 14d ATR as % of price
daily["realized_vol_5d"] = daily["log_returns"].rolling(5).std() * np.sqrt(252)
daily["realized_vol_21d"] = daily["log_returns"].rolling(21).std() * np.sqrt(252)
daily["abs_return"] = daily["returns"].abs()
daily["volume_ma_ratio"] = daily["volume"] / daily["volume"].rolling(21).mean()

daily.dropna(inplace=True)
print(f"  {len(daily)} trading days with features")


# ── 2. Fit HMM ────────────────────────────────────────────────────────

# Features: realized vol, range, absolute return, volume ratio
feature_cols = ["realized_vol_21d", "range_pct", "abs_return", "atr_pct"]
X = daily[feature_cols].values

# Standardize for HMM fitting
X_mean = X.mean(axis=0)
X_std = X.std(axis=0)
X_scaled = (X - X_mean) / X_std

print("\nFitting Gaussian HMM (2-4 states, selecting best BIC)...")
best_model = None
best_bic = np.inf
best_n = 0

for n_states in [2, 3, 4]:
    # Multiple random restarts to avoid local optima
    for seed in range(10):
        try:
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=200,
                random_state=seed,
                tol=1e-4,
            )
            model.fit(X_scaled)
            # BIC = -2*logL + k*ln(n)
            log_likelihood = model.score(X_scaled)
            n_params = n_states * (len(feature_cols) + len(feature_cols) * (len(feature_cols) + 1) // 2) + n_states**2
            bic = -2 * log_likelihood + n_params * np.log(len(X_scaled))
            if bic < best_bic:
                best_bic = bic
                best_model = model
                best_n = n_states
        except Exception:
            continue

print(f"  Best model: {best_n} states (BIC={best_bic:.1f})")

# Decode states
states = best_model.predict(X_scaled)
daily["regime"] = states

# ── 3. Label regimes by volatility level ──────────────────────────────

# Sort regimes by mean realized vol so regime 0 = lowest vol
regime_vol = daily.groupby("regime")["realized_vol_21d"].mean().sort_values()
label_map = {old: new for new, old in enumerate(regime_vol.index)}
daily["regime"] = daily["regime"].map(label_map)

regime_names = {}
for r in sorted(daily["regime"].unique()):
    vol = daily.loc[daily["regime"] == r, "realized_vol_21d"].mean()
    if vol < 0.15:
        regime_names[r] = f"R{r}: Low Vol ({vol:.1%})"
    elif vol < 0.25:
        regime_names[r] = f"R{r}: Med Vol ({vol:.1%})"
    elif vol < 0.35:
        regime_names[r] = f"R{r}: High Vol ({vol:.1%})"
    else:
        regime_names[r] = f"R{r}: Extreme Vol ({vol:.1%})"

print("\nRegime Summary:")
print("-" * 80)
for r in sorted(daily["regime"].unique()):
    subset = daily[daily["regime"] == r]
    print(f"  {regime_names[r]:30s}  "
          f"days={len(subset):>5d}  "
          f"vol_21d={subset['realized_vol_21d'].mean():.1%}  "
          f"range={subset['range_pct'].mean():.2%}  "
          f"atr%={subset['atr_pct'].mean():.2%}  "
          f"avg_ret={subset['returns'].mean():.4%}")


# ── 4. Run backtest and map trades to regimes ─────────────────────────

print("\nRunning backtest (same config as last run)...")
custom_ny = replace(NY_SESSION,
    orb_end="09:45",
    entry_start="09:45",
    entry_end="13:00",
    flat_start="15:50",
    flat_end="16:00",
    stop_atr_pct=9.0,
    min_gap_atr_pct=2.25,
)
config = default_config(NQ)
config = replace(config,
    sessions=(custom_ny,),
    rr=2.0,
    tp1_ratio=0.7,
    direction_filter="both",
    atr_length=14,
    risk_usd=5000,
    strategy="continuation",
    use_bar_magnifier=True,
    name="HMM regime analysis",
)

trades = run_backtest(df, config, start_date="2016-03-07")
filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
print(f"  {len(filled)} filled trades")

# Build trade DataFrame
trade_data = []
for t in filled:
    trade_data.append({
        "date": t.date,
        "direction": "long" if t.direction == 1 else "short",
        "r_pnl": t.pnl_usd / config.risk_usd,
        "pnl_usd": t.pnl_usd,
        "exit_type": t.exit_type,
    })
trades_df = pd.DataFrame(trade_data)
trades_df["date"] = pd.to_datetime(trades_df["date"])

# Map each trade to its regime (use trade date to look up regime)
daily_regime = daily[["regime"]].copy()
daily_regime.index = daily_regime.index.normalize()
trades_df["date_norm"] = trades_df["date"].dt.normalize()
trades_df = trades_df.merge(daily_regime, left_on="date_norm", right_index=True, how="left")
trades_df.dropna(subset=["regime"], inplace=True)
trades_df["regime"] = trades_df["regime"].astype(int)


# ── 5. Performance by regime ──────────────────────────────────────────

print("\n" + "=" * 80)
print("PERFORMANCE BY VOLATILITY REGIME")
print("=" * 80)

for r in sorted(trades_df["regime"].unique()):
    subset = trades_df[trades_df["regime"] == r]
    total_r = subset["r_pnl"].sum()
    avg_r = subset["r_pnl"].mean()
    wr = (subset["r_pnl"] > 0).mean()
    wins = (subset["r_pnl"] > 0).sum()
    losses = (subset["r_pnl"] <= 0).sum()
    gross_win = subset.loc[subset["r_pnl"] > 0, "r_pnl"].sum()
    gross_loss = abs(subset.loc[subset["r_pnl"] <= 0, "r_pnl"].sum())
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")

    # Long vs short breakdown
    longs = subset[subset["direction"] == "long"]
    shorts = subset[subset["direction"] == "short"]

    print(f"\n  {regime_names[r]}")
    print(f"    Trades:    {len(subset):>5d}   (L:{len(longs)} / S:{len(shorts)})")
    print(f"    Win Rate:  {wr:>6.1%}   (L:{(longs['r_pnl']>0).mean():.1%} / S:{(shorts['r_pnl']>0).mean() if len(shorts)>0 else 0:.1%})")
    print(f"    Total R:   {total_r:>+7.1f}R  (L:{longs['r_pnl'].sum():>+.1f} / S:{shorts['r_pnl'].sum():>+.1f})")
    print(f"    Avg R:     {avg_r:>+7.3f}R")
    print(f"    PF:        {pf:>6.2f}")


# ── 6. Regime composition by year ─────────────────────────────────────

print("\n" + "=" * 80)
print("REGIME COMPOSITION BY YEAR")
print("=" * 80)

daily["year"] = daily.index.year
yearly_regime = daily.groupby(["year", "regime"]).size().unstack(fill_value=0)
yearly_regime_pct = yearly_regime.div(yearly_regime.sum(axis=1), axis=0)

# Also compute yearly trade R by regime
trades_df["year"] = trades_df["date"].dt.year

header = f"{'Year':>6s}"
for r in sorted(daily["regime"].unique()):
    short_name = regime_names[r].split(":")[1].strip().split("(")[0].strip()
    header += f"  {short_name:>10s}"
header += "  | Total R"
print(header)
print("-" * len(header))

for year in sorted(daily["year"].unique()):
    row = f"{year:>6d}"
    for r in sorted(daily["regime"].unique()):
        if r in yearly_regime_pct.columns:
            pct = yearly_regime_pct.loc[year, r] if year in yearly_regime_pct.index else 0
            row += f"  {pct:>9.0%} "
        else:
            row += f"  {'--':>10s}"

    year_trades = trades_df[trades_df["year"] == year]
    total_r = year_trades["r_pnl"].sum()
    row += f"  | {total_r:>+7.1f}R"
    print(row)


# ── 7. Monthly regime + R heatmap ─────────────────────────────────────

print("\n" + "=" * 80)
print("MONTHLY DOMINANT REGIME + TRADE R")
print("=" * 80)

daily["month"] = daily.index.to_period("M")
trades_df["month"] = trades_df["date"].dt.to_period("M")

monthly_regime = daily.groupby("month")["regime"].agg(lambda x: x.mode().iloc[0])
monthly_r = trades_df.groupby("month")["r_pnl"].sum()
monthly_vol = daily.groupby("month")["realized_vol_21d"].mean()

combined = pd.DataFrame({
    "regime": monthly_regime,
    "r": monthly_r,
    "vol": monthly_vol,
}).dropna()

print(f"{'Month':>10s}  {'Regime':>12s}  {'Vol':>6s}  {'R':>8s}")
print("-" * 45)

# Show last 24 months for brevity
for month in combined.index[-36:]:
    r_val = combined.loc[month, "r"]
    vol_val = combined.loc[month, "vol"]
    reg = int(combined.loc[month, "regime"])
    short_name = regime_names[reg].split(":")[1].strip().split("(")[0].strip()
    r_str = f"{r_val:>+7.1f}R"
    print(f"  {str(month):>10s}  {short_name:>12s}  {vol_val:>5.1%}  {r_str}")


# ── 8. Transition matrix ─────────────────────────────────────────────

print("\n" + "=" * 80)
print("REGIME TRANSITION MATRIX (daily)")
print("=" * 80)
print("  (row = from, col = to)")

transmat = best_model.transmat_
# Remap transition matrix to match sorted regimes
n = best_n
remap = [label_map[i] for i in range(n)]
reordered = np.zeros_like(transmat)
for i in range(n):
    for j in range(n):
        reordered[remap[i], remap[j]] = transmat[i, j]

header = "        "
for r in range(n):
    short = regime_names[r].split(":")[1].strip()[:8]
    header += f"  {short:>10s}"
print(header)

for i in range(n):
    short = regime_names[i].split(":")[1].strip()[:8]
    row = f"  {short:>6s}"
    for j in range(n):
        row += f"  {reordered[i, j]:>9.1%} "
    print(row)

# Expected duration in each state
print("\n  Expected regime duration (days):")
for i in range(n):
    duration = 1.0 / (1.0 - reordered[i, i]) if reordered[i, i] < 1 else float("inf")
    print(f"    {regime_names[i]:30s}  ~{duration:.0f} days")


# ── 9. Plots ──────────────────────────────────────────────────────────

output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "results"
output_dir.mkdir(parents=True, exist_ok=True)

colors = ["#2ecc71", "#f39c12", "#e74c3c", "#8e44ad"]

# Plot 1: Price with regime overlay
fig, axes = plt.subplots(3, 1, figsize=(18, 14), gridspec_kw={"height_ratios": [3, 1, 1]})

ax1 = axes[0]
ax1.plot(daily.index, daily["close"], color="white", linewidth=0.5, alpha=0.8)
for r in sorted(daily["regime"].unique()):
    mask = daily["regime"] == r
    ax1.fill_between(daily.index, daily["close"].min(), daily["close"].max(),
                     where=mask, alpha=0.15, color=colors[r], label=regime_names[r])
ax1.set_title("NQ Price with HMM Volatility Regimes", fontsize=14, color="white")
ax1.set_ylabel("Price", color="white")
ax1.legend(loc="upper left", fontsize=9)
ax1.set_facecolor("#1a1a2e")
ax1.tick_params(colors="white")

# Plot 2: Realized vol colored by regime
ax2 = axes[1]
for r in sorted(daily["regime"].unique()):
    mask = daily["regime"] == r
    ax2.scatter(daily.index[mask], daily.loc[mask, "realized_vol_21d"],
                s=2, c=colors[r], alpha=0.6, label=regime_names[r])
ax2.set_ylabel("21d Realized Vol", color="white")
ax2.set_facecolor("#1a1a2e")
ax2.tick_params(colors="white")

# Plot 3: Cumulative R colored by regime
ax3 = axes[2]
trades_sorted = trades_df.sort_values("date")
cum_r = trades_sorted["r_pnl"].cumsum()
ax3.plot(trades_sorted["date"].values, cum_r.values, color="white", linewidth=1)
for r in sorted(trades_df["regime"].unique()):
    mask = trades_sorted["regime"] == r
    ax3.scatter(trades_sorted.loc[mask, "date"].values, cum_r[mask].values,
                s=8, c=colors[r], alpha=0.7, zorder=5)
ax3.set_ylabel("Cumulative R", color="white")
ax3.set_xlabel("Date", color="white")
ax3.set_facecolor("#1a1a2e")
ax3.tick_params(colors="white")

fig.patch.set_facecolor("#0d0d1a")
plt.tight_layout()
fig.savefig(output_dir / "hmm_regimes_overview.png", dpi=150, bbox_inches="tight",
            facecolor="#0d0d1a")
print(f"\nPlot saved: {output_dir / 'hmm_regimes_overview.png'}")

# Plot 2: Regime performance boxplot
fig2, ax = plt.subplots(figsize=(10, 6))
data_by_regime = [trades_df.loc[trades_df["regime"] == r, "r_pnl"].values
                  for r in sorted(trades_df["regime"].unique())]
labels = [regime_names[r] for r in sorted(trades_df["regime"].unique())]
bp = ax.boxplot(data_by_regime, labels=[l.split(":")[1].strip() for l in labels],
                patch_artist=True, showfliers=False)
for i, patch in enumerate(bp["boxes"]):
    patch.set_facecolor(colors[i])
    patch.set_alpha(0.7)
ax.axhline(y=0, color="gray", linestyle="--", alpha=0.5)
ax.set_ylabel("R per trade", color="white")
ax.set_title("Trade R Distribution by Volatility Regime", fontsize=13, color="white")
ax.set_facecolor("#1a1a2e")
fig2.patch.set_facecolor("#0d0d1a")
ax.tick_params(colors="white")
plt.tight_layout()
fig2.savefig(output_dir / "hmm_regime_boxplot.png", dpi=150, bbox_inches="tight",
             facecolor="#0d0d1a")
print(f"Plot saved: {output_dir / 'hmm_regime_boxplot.png'}")

# Plot 3: Annual R stacked by regime
fig3, ax = plt.subplots(figsize=(12, 6))
years = sorted(trades_df["year"].unique())
regimes = sorted(trades_df["regime"].unique())
bottom_pos = np.zeros(len(years))
bottom_neg = np.zeros(len(years))

for r in regimes:
    r_vals = []
    for y in years:
        subset = trades_df[(trades_df["year"] == y) & (trades_df["regime"] == r)]
        r_vals.append(subset["r_pnl"].sum())
    r_vals = np.array(r_vals)

    pos = np.maximum(r_vals, 0)
    neg = np.minimum(r_vals, 0)

    short_name = regime_names[r].split(":")[1].strip()
    ax.bar(years, pos, bottom=bottom_pos, color=colors[r], alpha=0.8, label=short_name)
    ax.bar(years, neg, bottom=bottom_neg, color=colors[r], alpha=0.8)

    bottom_pos += pos
    bottom_neg += neg

ax.axhline(y=0, color="gray", linewidth=0.5)
ax.set_ylabel("Total R", color="white")
ax.set_title("Annual R Contribution by Volatility Regime", fontsize=13, color="white")
ax.legend(loc="upper left", fontsize=9)
ax.set_facecolor("#1a1a2e")
fig3.patch.set_facecolor("#0d0d1a")
ax.tick_params(colors="white")
ax.set_xticks(years)
plt.tight_layout()
fig3.savefig(output_dir / "hmm_annual_regime_r.png", dpi=150, bbox_inches="tight",
             facecolor="#0d0d1a")
print(f"Plot saved: {output_dir / 'hmm_annual_regime_r.png'}")

print("\nDone.")
