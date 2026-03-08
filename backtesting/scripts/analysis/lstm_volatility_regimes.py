#!/usr/bin/env python3
"""LSTM Autoencoder regime detection for NQ volatility analysis.

Architecture:
  - Input: sliding windows of daily market features (lookback=21 trading days)
  - Encoder: LSTM → latent vector (dim=8)
  - Decoder: LSTM → reconstruct input sequence
  - Regime detection: K-Means on latent vectors
  - Comparison: phase_1 vs defaults performance per regime
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from dataclasses import replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from orb_backtest.config import NY_SESSION, default_config
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data
from orb_backtest.engine.simulator import run_backtest, EXIT_NO_FILL


# ══════════════════════════════════════════════════════════════════════
# 1. DATA PREPARATION
# ══════════════════════════════════════════════════════════════════════

print("=" * 70)
print("LSTM AUTOENCODER REGIME DETECTION")
print("=" * 70)

print("\n[1/6] Loading NQ data and building features...")
df = load_5m_data(NQ.data_file, start="2016-01-01", end="2026-03-07")

daily = df.resample("1D").agg({
    "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"
}).dropna(subset=["open"])
daily = daily[daily["volume"] > 0].copy()

# Features (richer than HMM — neural nets can handle more dimensions)
daily["returns"] = daily["close"].pct_change()
daily["log_returns"] = np.log(daily["close"] / daily["close"].shift(1))
daily["range_pct"] = (daily["high"] - daily["low"]) / daily["close"]
daily["true_range"] = np.maximum(
    daily["high"] - daily["low"],
    np.maximum(abs(daily["high"] - daily["close"].shift(1)),
               abs(daily["low"] - daily["close"].shift(1))))
daily["atr_pct"] = daily["true_range"].rolling(14).mean() / daily["close"]
daily["realized_vol_5d"] = daily["log_returns"].rolling(5).std() * np.sqrt(252)
daily["realized_vol_21d"] = daily["log_returns"].rolling(21).std() * np.sqrt(252)
daily["abs_return"] = daily["returns"].abs()
daily["volume_zscore"] = (daily["volume"] - daily["volume"].rolling(63).mean()) / daily["volume"].rolling(63).std()
daily["close_vs_sma20"] = daily["close"] / daily["close"].rolling(20).mean() - 1
daily["close_vs_sma50"] = daily["close"] / daily["close"].rolling(50).mean() - 1
daily["high_low_ratio"] = daily["high"] / daily["low"] - 1
# Garman-Klass volatility estimator (more efficient than close-to-close)
daily["gk_vol"] = np.sqrt(
    0.5 * np.log(daily["high"] / daily["low"])**2 -
    (2 * np.log(2) - 1) * np.log(daily["close"] / daily["open"])**2
)
daily["gk_vol_5d"] = daily["gk_vol"].rolling(5).mean()
daily["gk_vol_21d"] = daily["gk_vol"].rolling(21).mean()
# Up/down asymmetry
daily["up_vol_ratio"] = (
    daily["returns"].clip(lower=0).rolling(21).std() /
    daily["returns"].clip(upper=0).abs().rolling(21).std()
)

daily.replace([np.inf, -np.inf], np.nan, inplace=True)
daily.dropna(inplace=True)

feature_cols = [
    "returns", "abs_return", "range_pct", "atr_pct",
    "realized_vol_5d", "realized_vol_21d",
    "volume_zscore", "close_vs_sma20", "close_vs_sma50",
    "high_low_ratio", "gk_vol_5d", "gk_vol_21d", "up_vol_ratio",
]

scaler = StandardScaler()
features_scaled = scaler.fit_transform(daily[feature_cols].values)
print(f"  {len(daily)} trading days, {len(feature_cols)} features")


# ══════════════════════════════════════════════════════════════════════
# 2. BUILD SLIDING WINDOWS
# ══════════════════════════════════════════════════════════════════════

LOOKBACK = 21  # 1 month of trading days

def create_sequences(data, lookback):
    sequences = []
    for i in range(lookback, len(data)):
        sequences.append(data[i - lookback:i])
    return np.array(sequences)

X_seq = create_sequences(features_scaled, LOOKBACK)
# Dates aligned to the last day of each window
seq_dates = daily.index[LOOKBACK:]
print(f"  {len(X_seq)} sequences (lookback={LOOKBACK})")


# ══════════════════════════════════════════════════════════════════════
# 3. LSTM AUTOENCODER
# ══════════════════════════════════════════════════════════════════════

print("\n[2/6] Training LSTM Autoencoder...")

LATENT_DIM = 8
HIDDEN_DIM = 32
NUM_LAYERS = 2
EPOCHS = 80
BATCH_SIZE = 128
LR = 1e-3

device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"  Device: {device}")


class LSTMEncoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, latent_dim, num_layers):
        super().__init__()
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers,
                            batch_first=True, dropout=0.1)
        self.fc = nn.Linear(hidden_dim, latent_dim)

    def forward(self, x):
        _, (h_n, _) = self.lstm(x)
        # Use last layer hidden state
        latent = self.fc(h_n[-1])
        return latent


class LSTMDecoder(nn.Module):
    def __init__(self, latent_dim, hidden_dim, output_dim, seq_len, num_layers):
        super().__init__()
        self.seq_len = seq_len
        self.fc = nn.Linear(latent_dim, hidden_dim)
        self.lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers,
                            batch_first=True, dropout=0.1)
        self.out = nn.Linear(hidden_dim, output_dim)

    def forward(self, z):
        h = self.fc(z).unsqueeze(1).repeat(1, self.seq_len, 1)
        lstm_out, _ = self.lstm(h)
        return self.out(lstm_out)


class LSTMAutoencoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, latent_dim, seq_len, num_layers):
        super().__init__()
        self.encoder = LSTMEncoder(input_dim, hidden_dim, latent_dim, num_layers)
        self.decoder = LSTMDecoder(latent_dim, hidden_dim, input_dim, seq_len, num_layers)

    def forward(self, x):
        z = self.encoder(x)
        x_hat = self.decoder(z)
        return x_hat, z


model = LSTMAutoencoder(
    input_dim=len(feature_cols),
    hidden_dim=HIDDEN_DIM,
    latent_dim=LATENT_DIM,
    seq_len=LOOKBACK,
    num_layers=NUM_LAYERS,
).to(device)

X_tensor = torch.FloatTensor(X_seq).to(device)
dataset = TensorDataset(X_tensor, X_tensor)
loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)

optimizer = torch.optim.Adam(model.parameters(), lr=LR)
scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=EPOCHS)
criterion = nn.MSELoss()

for epoch in range(EPOCHS):
    model.train()
    total_loss = 0
    for batch_x, _ in loader:
        optimizer.zero_grad()
        x_hat, z = model(batch_x)
        loss = criterion(x_hat, batch_x)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        total_loss += loss.item() * batch_x.size(0)
    scheduler.step()
    avg_loss = total_loss / len(dataset)
    if (epoch + 1) % 20 == 0:
        print(f"  Epoch {epoch+1:>3d}/{EPOCHS}  loss={avg_loss:.6f}  lr={scheduler.get_last_lr()[0]:.6f}")


# ══════════════════════════════════════════════════════════════════════
# 4. EXTRACT LATENT VECTORS & CLUSTER
# ══════════════════════════════════════════════════════════════════════

print("\n[3/6] Extracting latent representations & clustering...")

model.eval()
with torch.no_grad():
    _, latent_vectors = model(X_tensor)
    latent_np = latent_vectors.cpu().numpy()

# Try 2-4 clusters, pick best silhouette score
from sklearn.metrics import silhouette_score

best_k, best_score, best_labels = 0, -1, None
for k in [2, 3, 4, 5]:
    km = KMeans(n_clusters=k, n_init=20, random_state=42)
    labels = km.fit_predict(latent_np)
    score = silhouette_score(latent_np, labels)
    print(f"  K={k}: silhouette={score:.3f}")
    if score > best_score:
        best_k, best_score, best_labels = k, score, labels

print(f"  Selected K={best_k} (silhouette={best_score:.3f})")

# Assign regimes to the daily dataframe (aligned to seq_dates)
regime_series = pd.Series(best_labels, index=seq_dates, name="regime")

# Sort regimes by mean realized vol
temp_df = daily.loc[seq_dates].copy()
temp_df["regime"] = best_labels
regime_vol = temp_df.groupby("regime")["realized_vol_21d"].mean().sort_values()
label_map = {old: new for new, old in enumerate(regime_vol.index)}
temp_df["regime"] = temp_df["regime"].map(label_map)

regime_names = {}
for r in sorted(temp_df["regime"].unique()):
    vol = temp_df.loc[temp_df["regime"] == r, "realized_vol_21d"].mean()
    rng = temp_df.loc[temp_df["regime"] == r, "range_pct"].mean()
    gk = temp_df.loc[temp_df["regime"] == r, "gk_vol_21d"].mean()
    sma_dist = temp_df.loc[temp_df["regime"] == r, "close_vs_sma20"].mean()
    n_days = (temp_df["regime"] == r).sum()

    if vol < 0.10:
        tag = "Very Low"
    elif vol < 0.17:
        tag = "Low"
    elif vol < 0.28:
        tag = "Medium"
    else:
        tag = "High"
    regime_names[r] = f"R{r}: {tag} Vol ({vol:.1%})"

print("\nLSTM Regime Summary:")
print("-" * 90)
print(f"  {'Regime':35s}  {'Days':>5s}  {'21d Vol':>7s}  {'Range%':>7s}  {'GK Vol':>7s}  {'vs SMA20':>8s}")
for r in sorted(temp_df["regime"].unique()):
    s = temp_df[temp_df["regime"] == r]
    print(f"  {regime_names[r]:35s}  {len(s):>5d}  {s['realized_vol_21d'].mean():>6.1%}  "
          f"{s['range_pct'].mean():>6.2%}  {s['gk_vol_21d'].mean():>6.3f}  "
          f"{s['close_vs_sma20'].mean():>+7.1%}")


# ══════════════════════════════════════════════════════════════════════
# 5. RUN BOTH BACKTESTS & MAP TO REGIMES
# ══════════════════════════════════════════════════════════════════════

print("\n[4/6] Running backtests...")

# Phase_1 config
custom_ny = replace(NY_SESSION,
    orb_end="09:50", entry_start="09:50", entry_end="12:00",
    flat_start="15:30", stop_atr_pct=7.0, min_gap_atr_pct=2.5,
)
config_p1 = replace(default_config(NQ),
    sessions=(custom_ny,), rr=3.5, tp1_ratio=0.4,
    direction_filter="long", atr_length=12, risk_usd=5000,
    strategy="continuation", use_bar_magnifier=True,
    name="LSTM regime - phase_1",
)

# Defaults config
default_ny = replace(NY_SESSION, stop_atr_pct=9.0, min_gap_atr_pct=2.25)
config_def = replace(default_config(NQ),
    sessions=(default_ny,), rr=2.0, tp1_ratio=0.7,
    direction_filter="both", atr_length=14, risk_usd=5000,
    strategy="continuation", use_bar_magnifier=True,
    name="LSTM regime - defaults",
)

def run_and_map(config, label):
    trades = run_backtest(df, config, start_date="2016-03-07")
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    print(f"  {label}: {len(filled)} filled trades")

    rows = []
    for t in filled:
        rows.append({
            "date": pd.Timestamp(t.date),
            "direction": "long" if t.direction == 1 else "short",
            "r_pnl": t.pnl_usd / config.risk_usd,
            "exit_type": t.exit_type,
        })
    tdf = pd.DataFrame(rows)
    tdf["date_norm"] = tdf["date"].dt.normalize()
    regime_lookup = temp_df[["regime"]].copy()
    regime_lookup.index = regime_lookup.index.normalize()
    tdf = tdf.merge(regime_lookup, left_on="date_norm", right_index=True, how="left")
    tdf.dropna(subset=["regime"], inplace=True)
    tdf["regime"] = tdf["regime"].astype(int)
    tdf["year"] = tdf["date"].dt.year
    return tdf

tdf_p1 = run_and_map(config_p1, "Phase_1")
tdf_def = run_and_map(config_def, "Defaults")


# ══════════════════════════════════════════════════════════════════════
# 6. RESULTS
# ══════════════════════════════════════════════════════════════════════

print("\n[5/6] Analyzing regime performance...")

def print_regime_perf(tdf, label):
    print(f"\n{'─' * 70}")
    print(f"  {label}")
    print(f"{'─' * 70}")
    for r in sorted(tdf["regime"].unique()):
        s = tdf[tdf["regime"] == r]
        total_r = s["r_pnl"].sum()
        wr = (s["r_pnl"] > 0).mean()
        gw = s.loc[s["r_pnl"] > 0, "r_pnl"].sum()
        gl = abs(s.loc[s["r_pnl"] <= 0, "r_pnl"].sum())
        pf = gw / gl if gl > 0 else float("inf")
        longs = s[s["direction"] == "long"]
        shorts = s[s["direction"] == "short"]
        print(f"\n  {regime_names[r]}")
        print(f"    Trades: {len(s):>5d}  (L:{len(longs)} / S:{len(shorts)})")
        print(f"    WR:     {wr:>5.1%}   Total R: {total_r:>+7.1f}R   Avg R: {s['r_pnl'].mean():>+.3f}R   PF: {pf:.2f}")
        if len(longs) > 0:
            print(f"    Longs:  {(longs['r_pnl']>0).mean():>5.1%} WR  {longs['r_pnl'].sum():>+7.1f}R")
        if len(shorts) > 0:
            print(f"    Shorts: {(shorts['r_pnl']>0).mean():>5.1%} WR  {shorts['r_pnl'].sum():>+7.1f}R")
    total = tdf["r_pnl"].sum()
    print(f"\n    TOTAL:  {total:>+7.1f}R  ({len(tdf)} trades)")

print("\n" + "=" * 70)
print("LSTM AUTOENCODER — PERFORMANCE BY REGIME")
print("=" * 70)

print_regime_perf(tdf_def, "DEFAULTS (RR 2.0, both directions, stop 9%)")
print_regime_perf(tdf_p1, "PHASE_1 (RR 3.5, long only, stop 7%)")

# ── Side-by-side comparison ──
print("\n" + "=" * 70)
print("SIDE-BY-SIDE COMPARISON")
print("=" * 70)
print(f"\n  {'Regime':35s}  {'Defaults':>22s}  {'Phase_1':>22s}")
print("  " + "-" * 82)
for r in sorted(set(tdf_def["regime"].unique()) | set(tdf_p1["regime"].unique())):
    s1 = tdf_def[tdf_def["regime"] == r]
    s2 = tdf_p1[tdf_p1["regime"] == r]
    r1_r = s1["r_pnl"].sum() if len(s1) > 0 else 0
    r2_r = s2["r_pnl"].sum() if len(s2) > 0 else 0
    r1_wr = (s1["r_pnl"]>0).mean() if len(s1)>0 else 0
    r2_wr = (s2["r_pnl"]>0).mean() if len(s2)>0 else 0
    r1_str = f"{r1_r:>+.1f}R ({len(s1)}t, {r1_wr:.0%}WR)"
    r2_str = f"{r2_r:>+.1f}R ({len(s2)}t, {r2_wr:.0%}WR)"
    name = regime_names.get(r, f"R{r}")
    print(f"  {name:35s}  {r1_str:>22s}  {r2_str:>22s}")

t1 = tdf_def["r_pnl"].sum()
t2 = tdf_p1["r_pnl"].sum()
print(f"  {'TOTAL':35s}  {t1:>+.1f}R ({len(tdf_def)}t){'':>10s}  {t2:>+.1f}R ({len(tdf_p1)}t)")

# ── Year breakdown ──
print("\n" + "=" * 70)
print("ANNUAL REGIME COMPOSITION + R (LSTM)")
print("=" * 70)

temp_df["year"] = temp_df.index.year
yearly_regime = temp_df.groupby(["year", "regime"]).size().unstack(fill_value=0)
yearly_regime_pct = yearly_regime.div(yearly_regime.sum(axis=1), axis=0)

header = f"{'Year':>6s}"
for r in sorted(temp_df["regime"].unique()):
    short = regime_names[r].split(":")[1].strip()[:8]
    header += f"  {short:>8s}"
header += f"  | {'Defaults':>10s}  {'Phase_1':>10s}"
print(header)
print("-" * len(header))

for year in sorted(temp_df["year"].unique()):
    row = f"{year:>6d}"
    for r in sorted(temp_df["regime"].unique()):
        pct = yearly_regime_pct.loc[year, r] if (year in yearly_regime_pct.index and r in yearly_regime_pct.columns) else 0
        row += f"  {pct:>7.0%} "
    yd = tdf_def[tdf_def["year"] == year]["r_pnl"].sum()
    yp = tdf_p1[tdf_p1["year"] == year]["r_pnl"].sum()
    row += f"  | {yd:>+9.1f}R  {yp:>+9.1f}R"
    print(row)


# ══════════════════════════════════════════════════════════════════════
# 7. PLOTS
# ══════════════════════════════════════════════════════════════════════

print("\n[6/6] Generating plots...")
output_dir = Path(__file__).resolve().parent.parent.parent / "data" / "results"
output_dir.mkdir(parents=True, exist_ok=True)

colors = ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c", "#8e44ad"][:best_k]

# ── Plot 1: Price with LSTM regimes + equity curves ──
fig, axes = plt.subplots(3, 1, figsize=(18, 14), gridspec_kw={"height_ratios": [3, 1.5, 1.5]})

ax1 = axes[0]
ax1.plot(daily.index, daily["close"], color="white", linewidth=0.5, alpha=0.8)
for r in sorted(temp_df["regime"].unique()):
    mask = temp_df["regime"] == r
    ax1.fill_between(temp_df.index, daily["close"].min(), daily["close"].max(),
                     where=mask, alpha=0.15, color=colors[r], label=regime_names[r])
ax1.set_title("NQ Price with LSTM Autoencoder Volatility Regimes", fontsize=14, color="white")
ax1.set_ylabel("Price", color="white")
ax1.legend(loc="upper left", fontsize=9)
ax1.set_facecolor("#1a1a2e")
ax1.tick_params(colors="white")

# Equity curves
for ax, tdf_plot, label, color in [
    (axes[1], tdf_def, "Defaults (RR2, both)", "#f39c12"),
    (axes[2], tdf_p1, "Phase_1 (RR3.5, long)", "#2ecc71"),
]:
    ts = tdf_plot.sort_values("date")
    cum_r = ts["r_pnl"].cumsum()
    ax.plot(ts["date"].values, cum_r.values, color=color, linewidth=1.2, label=label)
    for r in sorted(tdf_plot["regime"].unique()):
        mask = ts["regime"] == r
        ax.scatter(ts.loc[mask, "date"].values, cum_r[mask].values,
                   s=6, c=colors[r], alpha=0.7, zorder=5)
    ax.set_ylabel("Cumulative R", color="white")
    ax.legend(loc="upper left", fontsize=9, facecolor="#1a1a2e", edgecolor="gray",
              labelcolor="white")
    ax.set_facecolor("#1a1a2e")
    ax.tick_params(colors="white")
    ax.axhline(y=0, color="gray", linewidth=0.3)

axes[2].set_xlabel("Date", color="white")
fig.patch.set_facecolor("#0d0d1a")
plt.tight_layout()
fig.savefig(output_dir / "lstm_regimes_overview.png", dpi=150, bbox_inches="tight",
            facecolor="#0d0d1a")
print(f"  Saved: {output_dir / 'lstm_regimes_overview.png'}")

# ── Plot 2: Annual stacked R by regime for both configs ──
fig2, (ax_l, ax_r) = plt.subplots(1, 2, figsize=(18, 7), sharey=True)

for ax, tdf_plot, title in [
    (ax_l, tdf_def, "Defaults (RR2, both dirs)"),
    (ax_r, tdf_p1, "Phase_1 (RR3.5, long only)"),
]:
    years = sorted(tdf_plot["year"].unique())
    regimes = sorted(tdf_plot["regime"].unique())
    bottom_pos = np.zeros(len(years))
    bottom_neg = np.zeros(len(years))

    for r in regimes:
        r_vals = []
        for y in years:
            subset = tdf_plot[(tdf_plot["year"] == y) & (tdf_plot["regime"] == r)]
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
    ax.set_title(title, fontsize=12, color="white")
    ax.set_ylabel("Total R", color="white")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_facecolor("#1a1a2e")
    ax.tick_params(colors="white")
    ax.set_xticks(years)

fig2.patch.set_facecolor("#0d0d1a")
fig2.suptitle("Annual R by LSTM Regime", fontsize=14, color="white", y=1.02)
plt.tight_layout()
fig2.savefig(output_dir / "lstm_annual_regime_r.png", dpi=150, bbox_inches="tight",
             facecolor="#0d0d1a")
print(f"  Saved: {output_dir / 'lstm_annual_regime_r.png'}")

# ── Plot 3: Latent space visualization (t-SNE) ──
from sklearn.manifold import TSNE

print("  Computing t-SNE embedding of latent space...")
tsne = TSNE(n_components=2, perplexity=50, random_state=42, max_iter=1000)
latent_2d = tsne.fit_transform(latent_np)

fig3, ax = plt.subplots(figsize=(10, 8))
for r in sorted(temp_df["regime"].unique()):
    mask = temp_df["regime"].values == r
    ax.scatter(latent_2d[mask, 0], latent_2d[mask, 1],
               s=8, c=colors[r], alpha=0.6, label=regime_names[r])
ax.set_title("LSTM Latent Space (t-SNE projection)", fontsize=13, color="white")
ax.legend(loc="upper right", fontsize=9)
ax.set_facecolor("#1a1a2e")
fig3.patch.set_facecolor("#0d0d1a")
ax.tick_params(colors="white")
ax.set_xlabel("t-SNE 1", color="white")
ax.set_ylabel("t-SNE 2", color="white")
plt.tight_layout()
fig3.savefig(output_dir / "lstm_latent_tsne.png", dpi=150, bbox_inches="tight",
             facecolor="#0d0d1a")
print(f"  Saved: {output_dir / 'lstm_latent_tsne.png'}")

# ── HMM vs LSTM regime agreement ──
print("\n" + "=" * 70)
print("HMM vs LSTM REGIME AGREEMENT")
print("=" * 70)
print("(How much do the two methods agree on market state?)")

# Refit HMM for comparison
from hmmlearn.hmm import GaussianHMM

hmm_features = ["realized_vol_21d", "range_pct", "abs_return", "atr_pct"]
X_hmm = daily.loc[seq_dates, hmm_features].values
X_hmm_scaled = (X_hmm - X_hmm.mean(axis=0)) / X_hmm.std(axis=0)

best_hmm = None
best_hmm_bic = np.inf
for seed in range(10):
    try:
        m = GaussianHMM(n_components=4, covariance_type="full", n_iter=200, random_state=seed)
        m.fit(X_hmm_scaled)
        ll = m.score(X_hmm_scaled)
        n_p = 4 * (4 + 4*5//2) + 16
        bic = -2*ll + n_p*np.log(len(X_hmm_scaled))
        if bic < best_hmm_bic:
            best_hmm_bic = bic
            best_hmm = m
    except: continue

hmm_states = best_hmm.predict(X_hmm_scaled)
hmm_vol = pd.Series(hmm_states, index=seq_dates).to_frame("hmm_regime")
hmm_regime_vol = daily.loc[seq_dates].assign(hmm=hmm_states).groupby("hmm")["realized_vol_21d"].mean().sort_values()
hmm_map = {old: new for new, old in enumerate(hmm_regime_vol.index)}
hmm_states_sorted = np.array([hmm_map[s] for s in hmm_states])

# Cross-tabulation
from sklearn.metrics import adjusted_rand_score
ari = adjusted_rand_score(hmm_states_sorted, temp_df["regime"].values)
print(f"  Adjusted Rand Index: {ari:.3f} (1.0 = perfect agreement, 0.0 = random)")

cross = pd.crosstab(
    pd.Series(hmm_states_sorted, name="HMM"),
    pd.Series(temp_df["regime"].values, name="LSTM"),
    margins=True,
)
print(f"\n  Cross-tabulation (HMM rows × LSTM cols):")
print(cross.to_string())

print("\nDone.")
