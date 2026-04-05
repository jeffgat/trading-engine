#!/usr/bin/env python3
"""
ALPHA V1 Portfolio Regime Analysis — HMM + LSTM + Rule-Based

Runs all 4 ALPHA_V1 legs, then discovers latent market regimes via:
  1. Gaussian HMM on daily NQ features
  2. LSTM Autoencoder + K-Means on daily NQ features
  3. Existing rule-based regime (trend x vol 3x3 grid from REGIME.md)

Maps per-leg and combined portfolio daily R to each regime system to answer:
  "When does this portfolio perform best and worst?"
"""

import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from hmmlearn.hmm import GaussianHMM
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score, adjusted_rand_score

from orb_backtest.config import StrategyConfig, SessionConfig
from orb_backtest.data.instruments import get_instrument
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import run_backtest, build_maps, EXIT_NO_FILL

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "results"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

NQ = get_instrument("NQ")
ES = get_instrument("ES")

# ═══════════════════════════════════════════════════════════════════════
# 1. ALPHA V1 LEG CONFIGS (exact production configs)
# ═══════════════════════════════════════════════════════════════════════

LEG1_CONFIG = StrategyConfig(
    sessions=(SessionConfig(
        name="NY", rth_start="09:30", entry_start="09:35", entry_end="15:30",
        flat_start="15:50", flat_end="16:00", min_gap_atr_pct=5.0,
    ),),
    instrument=NQ, strategy="lsi",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=3.0, tp1_ratio=0.34, atr_length=10,
    lsi_n_left=8, lsi_n_right=60, lsi_fvg_window_left=20, lsi_fvg_window_right=5,
    lsi_stop_mode="absolute", lsi_entry_mode="fvg_limit",
    lsi_first_fvg_only=False, lsi_clean_path=False,
    lsi_be_swing_n_left=0, lsi_cancel_on_swing=False,
    excluded_days=(2, 3),
)

LEG2_CONFIG = StrategyConfig(
    sessions=(SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="22:30",
        flat_start="04:00", flat_end="07:00",
        stop_orb_pct=100.0, min_gap_orb_pct=10.0,
    ),),
    instrument=NQ, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=6.0, tp1_ratio=0.3, atr_length=5,
    excluded_days=(1,),
)

LEG3_CONFIG = StrategyConfig(
    sessions=(SessionConfig(
        name="Asia", orb_start="20:00", orb_end="20:15",
        entry_start="20:15", entry_end="03:00",
        flat_start="07:00", flat_end="07:00",
        stop_orb_pct=125.0, min_gap_atr_pct=0.5,
        min_stop_points=3.0, min_tp1_points=3.0,
    ),),
    instrument=ES, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=1.5, tp1_ratio=0.7, atr_length=14,
)

LEG4_CONFIG = StrategyConfig(
    sessions=(SessionConfig(
        name="NY", orb_start="09:30", orb_end="09:45",
        entry_start="09:45", entry_end="13:00",
        flat_start="15:50", flat_end="16:00",
        stop_atr_pct=5.0, min_gap_atr_pct=0.25,
        min_stop_points=3.0, min_tp1_points=3.0,
    ),),
    instrument=ES, strategy="continuation",
    use_bar_magnifier=True, risk_usd=5000.0, direction_filter="long",
    rr=5.0, tp1_ratio=0.2, atr_length=7,
    excluded_days=(3,),
)

LEGS = [
    ("NQ_NY_LSI",    LEG1_CONFIG, "NQ"),
    ("NQ_ASIA_ORB",  LEG2_CONFIG, "NQ"),
    ("ES_ASIA_CONT", LEG3_CONFIG, "ES"),
    ("ES_NY_CONT",   LEG4_CONFIG, "ES"),
]


# ═══════════════════════════════════════════════════════════════════════
# 2. LOAD DATA & RUN BACKTESTS
# ═══════════════════════════════════════════════════════════════════════

def load_and_run():
    data_dir = Path(__file__).resolve().parent.parent.parent / "data" / "raw"
    data = {}
    maps_cache = {}

    for symbol in ("NQ", "ES"):
        print(f"Loading {symbol}...")
        t0 = time.time()
        df = load_5m_data(str(data_dir / f"{symbol}_5m.csv"))
        df_1m = load_1m_for_5m(str(data_dir / f"{symbol}_5m.csv"))
        try:
            df_1s = load_1s_for_5m(str(data_dir / f"{symbol}_5m.csv"))
        except Exception:
            df_1s = None
        data[symbol] = {"5m": df, "1m": df_1m, "1s": df_1s}
        maps_cache[symbol] = build_maps(df, df_1m=df_1m, df_1s=df_1s)
        print(f"  {len(df):,} bars [{time.time()-t0:.1f}s]")

    leg_trades = {}
    for leg_name, config, symbol in LEGS:
        print(f"Running {leg_name}...", end=" ")
        t0 = time.time()
        d = data[symbol]
        trades = run_backtest(d["5m"], config, df_1m=d["1m"], df_1s=d["1s"],
                              _maps=maps_cache[symbol])
        filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
        leg_trades[leg_name] = filled
        net_r = sum(t.r_multiple for t in filled)
        print(f"{len(filled)} trades, {net_r:+.1f}R [{time.time()-t0:.1f}s]")

    return data, leg_trades


# ═══════════════════════════════════════════════════════════════════════
# 3. BUILD DAILY FEATURES (NQ as macro driver)
# ═══════════════════════════════════════════════════════════════════════

def build_daily_features(df_5m):
    daily = df_5m.resample("1D").agg({
        "open": "first", "high": "max", "low": "min",
        "close": "last", "volume": "sum",
    }).dropna(subset=["open"])
    daily = daily[daily["volume"] > 0].copy()

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
    daily["volume_zscore"] = (
        (daily["volume"] - daily["volume"].rolling(63).mean()) /
        daily["volume"].rolling(63).std()
    )
    daily["close_vs_sma20"] = daily["close"] / daily["close"].rolling(20).mean() - 1
    daily["close_vs_sma50"] = daily["close"] / daily["close"].rolling(50).mean() - 1
    daily["ret_5d"] = daily["close"].pct_change(5)
    daily["high_low_ratio"] = daily["high"] / daily["low"] - 1
    daily["gk_vol"] = np.sqrt(
        0.5 * np.log(daily["high"] / daily["low"])**2 -
        (2 * np.log(2) - 1) * np.log(daily["close"] / daily["open"])**2
    )
    daily["gk_vol_5d"] = daily["gk_vol"].rolling(5).mean()
    daily["gk_vol_21d"] = daily["gk_vol"].rolling(21).mean()
    daily["up_vol_ratio"] = (
        daily["returns"].clip(lower=0).rolling(21).std() /
        daily["returns"].clip(upper=0).abs().rolling(21).std()
    )
    daily.replace([np.inf, -np.inf], np.nan, inplace=True)
    daily.dropna(inplace=True)
    return daily


# ═══════════════════════════════════════════════════════════════════════
# 4. RULE-BASED REGIME (from REGIME.md — frozen thresholds)
# ═══════════════════════════════════════════════════════════════════════

def assign_rule_based_regime(daily):
    """Assign 3x3 trend x vol regime using frozen thresholds from REGIME.md."""
    d = daily.copy()

    # Trend axis (shifted by 1 session)
    cvs = d["close_vs_sma20"].shift(1)
    r5 = d["ret_5d"].shift(1)
    vol = d["realized_vol_21d"].shift(1)

    trend = pd.Series("sideways", index=d.index)
    trend[(cvs >= 0.005) & (r5 > 0)] = "bull"
    trend[(cvs <= -0.005) & (r5 < 0)] = "bear"

    # Vol axis — frozen tercile thresholds from pre-holdout
    vol_bucket = pd.Series("medium_vol", index=d.index)
    vol_bucket[vol <= 0.1252] = "low_vol"
    vol_bucket[vol > 0.2040] = "high_vol"

    d["trend"] = trend
    d["vol_bucket"] = vol_bucket
    d["rule_regime"] = trend + "_" + vol_bucket

    # Low confidence flag
    d["low_confidence"] = (cvs.abs() < 0.0025) | (r5.abs() < 0.005)
    return d


# ═══════════════════════════════════════════════════════════════════════
# 5. HMM REGIME DETECTION
# ═══════════════════════════════════════════════════════════════════════

def fit_hmm(daily):
    print("\n[HMM] Fitting Gaussian HMM (2-4 states)...")
    feature_cols = ["realized_vol_21d", "range_pct", "abs_return", "atr_pct"]
    X = daily[feature_cols].values
    X_mean, X_std = X.mean(axis=0), X.std(axis=0)
    X_scaled = (X - X_mean) / X_std

    best_model, best_bic, best_n = None, np.inf, 0
    for n_states in [2, 3, 4]:
        for seed in range(10):
            try:
                model = GaussianHMM(n_components=n_states, covariance_type="full",
                                    n_iter=200, random_state=seed, tol=1e-4)
                model.fit(X_scaled)
                ll = model.score(X_scaled)
                n_p = n_states * (len(feature_cols) + len(feature_cols) * (len(feature_cols)+1) // 2) + n_states**2
                bic = -2 * ll + n_p * np.log(len(X_scaled))
                if bic < best_bic:
                    best_bic, best_model, best_n = bic, model, n_states
            except Exception:
                continue

    states = best_model.predict(X_scaled)

    # Sort by mean realized vol
    temp = daily.copy()
    temp["_hmm_raw"] = states
    vol_order = temp.groupby("_hmm_raw")["realized_vol_21d"].mean().sort_values()
    label_map = {old: new for new, old in enumerate(vol_order.index)}
    daily["hmm_regime"] = temp["_hmm_raw"].map(label_map)

    hmm_names = {}
    for r in sorted(daily["hmm_regime"].unique()):
        vol = daily.loc[daily["hmm_regime"] == r, "realized_vol_21d"].mean()
        tags = {0: "Low", 1: "Med", 2: "High", 3: "Extreme"}
        tag = tags.get(r, f"R{r}")
        hmm_names[r] = f"HMM-{tag} ({vol:.1%})"

    print(f"  Best: {best_n} states (BIC={best_bic:.0f})")
    for r in sorted(daily["hmm_regime"].unique()):
        n = (daily["hmm_regime"] == r).sum()
        print(f"  {hmm_names[r]:25s}  {n} days ({n/len(daily):.1%})")

    return daily, hmm_names, best_model


# ═══════════════════════════════════════════════════════════════════════
# 6. LSTM AUTOENCODER REGIME DETECTION
# ═══════════════════════════════════════════════════════════════════════

LOOKBACK = 21
LATENT_DIM = 8
HIDDEN_DIM = 32
NUM_LAYERS = 2
EPOCHS = 80
BATCH_SIZE = 128


class LSTMAutoencoder(nn.Module):
    def __init__(self, input_dim, hidden_dim, latent_dim, seq_len, num_layers):
        super().__init__()
        self.encoder_lstm = nn.LSTM(input_dim, hidden_dim, num_layers,
                                     batch_first=True, dropout=0.1)
        self.encoder_fc = nn.Linear(hidden_dim, latent_dim)
        self.decoder_fc = nn.Linear(latent_dim, hidden_dim)
        self.decoder_lstm = nn.LSTM(hidden_dim, hidden_dim, num_layers,
                                     batch_first=True, dropout=0.1)
        self.decoder_out = nn.Linear(hidden_dim, input_dim)
        self.seq_len = seq_len

    def forward(self, x):
        _, (h_n, _) = self.encoder_lstm(x)
        z = self.encoder_fc(h_n[-1])
        h = self.decoder_fc(z).unsqueeze(1).repeat(1, self.seq_len, 1)
        lstm_out, _ = self.decoder_lstm(h)
        x_hat = self.decoder_out(lstm_out)
        return x_hat, z


def fit_lstm(daily):
    print("\n[LSTM] Training autoencoder...")
    feature_cols = [
        "returns", "abs_return", "range_pct", "atr_pct",
        "realized_vol_5d", "realized_vol_21d",
        "volume_zscore", "close_vs_sma20", "close_vs_sma50",
        "high_low_ratio", "gk_vol_5d", "gk_vol_21d", "up_vol_ratio",
    ]
    scaler = StandardScaler()
    scaled = scaler.fit_transform(daily[feature_cols].values)

    # Sliding windows
    sequences = []
    for i in range(LOOKBACK, len(scaled)):
        sequences.append(scaled[i - LOOKBACK:i])
    X_seq = np.array(sequences)
    seq_dates = daily.index[LOOKBACK:]

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    print(f"  Device: {device}, {len(X_seq)} sequences")

    model = LSTMAutoencoder(
        input_dim=len(feature_cols), hidden_dim=HIDDEN_DIM,
        latent_dim=LATENT_DIM, seq_len=LOOKBACK, num_layers=NUM_LAYERS,
    ).to(device)

    X_tensor = torch.FloatTensor(X_seq).to(device)
    dataset = TensorDataset(X_tensor, X_tensor)
    loader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
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
        if (epoch + 1) % 20 == 0:
            print(f"  Epoch {epoch+1:>3d}/{EPOCHS}  loss={total_loss/len(dataset):.6f}")

    model.eval()
    with torch.no_grad():
        _, latent_vectors = model(X_tensor)
        latent_np = latent_vectors.cpu().numpy()

    # Cluster latent vectors
    best_k, best_score, best_labels = 0, -1, None
    for k in [2, 3, 4, 5]:
        km = KMeans(n_clusters=k, n_init=20, random_state=42)
        labels = km.fit_predict(latent_np)
        score = silhouette_score(latent_np, labels)
        print(f"  K={k}: silhouette={score:.3f}")
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels
    print(f"  Selected K={best_k}")

    # Sort by vol
    lstm_df = daily.loc[seq_dates].copy()
    lstm_df["_lstm_raw"] = best_labels
    vol_order = lstm_df.groupby("_lstm_raw")["realized_vol_21d"].mean().sort_values()
    label_map = {old: new for new, old in enumerate(vol_order.index)}
    lstm_df["lstm_regime"] = lstm_df["_lstm_raw"].map(label_map)

    # Write back to main daily (NaN for warmup days)
    daily["lstm_regime"] = np.nan
    daily.loc[seq_dates, "lstm_regime"] = lstm_df["lstm_regime"].values

    lstm_names = {}
    for r in sorted(lstm_df["lstm_regime"].unique()):
        vol = lstm_df.loc[lstm_df["lstm_regime"] == r, "realized_vol_21d"].mean()
        rng = lstm_df.loc[lstm_df["lstm_regime"] == r, "range_pct"].mean()
        sma = lstm_df.loc[lstm_df["lstm_regime"] == r, "close_vs_sma20"].mean()
        n = (lstm_df["lstm_regime"] == r).sum()
        tags = {0: "Low", 1: "Med-Low", 2: "Med", 3: "Med-High", 4: "High"}
        tag = tags.get(r, f"R{r}")
        lstm_names[r] = f"LSTM-{tag} ({vol:.1%})"

    for r in sorted(lstm_df["lstm_regime"].unique()):
        n = (lstm_df["lstm_regime"] == r).sum()
        print(f"  {lstm_names[r]:25s}  {n} days ({n/len(lstm_df):.1%})")

    return daily, lstm_names, latent_np, seq_dates


# ═══════════════════════════════════════════════════════════════════════
# 7. MAP TRADES TO REGIMES
# ═══════════════════════════════════════════════════════════════════════

def build_trade_df(leg_trades):
    """Build per-leg and combined daily R DataFrames."""
    rows = []
    for leg_name, trades in leg_trades.items():
        for t in trades:
            rows.append({
                "date": pd.Timestamp(str(t.date)[:10]),
                "leg": leg_name,
                "r_pnl": t.r_multiple,
                "direction": "long" if t.direction == 1 else "short",
            })
    tdf = pd.DataFrame(rows)
    tdf["date_norm"] = tdf["date"].dt.normalize()
    return tdf


def merge_regimes(tdf, daily):
    """Merge regime labels onto trades."""
    regime_cols = ["hmm_regime", "lstm_regime", "rule_regime", "trend", "vol_bucket"]
    lookup = daily[regime_cols].copy()
    lookup.index = lookup.index.normalize()
    tdf = tdf.merge(lookup, left_on="date_norm", right_index=True, how="left")
    return tdf


# ═══════════════════════════════════════════════════════════════════════
# 8. ANALYSIS & REPORTING
# ═══════════════════════════════════════════════════════════════════════

def regime_perf_table(tdf, regime_col, regime_names, title):
    """Print performance breakdown by regime."""
    print(f"\n{'='*90}")
    print(f"  {title}")
    print(f"{'='*90}")

    valid = tdf.dropna(subset=[regime_col])
    regimes = sorted(valid[regime_col].unique())

    print(f"\n  {'Regime':30s}  {'Trades':>6s}  {'WR':>6s}  {'Avg R':>7s}  {'Total R':>8s}  {'PF':>6s}  {'Best Leg':>15s}  {'Worst Leg':>15s}")
    print("  " + "-" * 105)

    for r in regimes:
        s = valid[valid[regime_col] == r]
        total_r = s["r_pnl"].sum()
        avg_r = s["r_pnl"].mean()
        wr = (s["r_pnl"] > 0).mean()
        gw = s.loc[s["r_pnl"] > 0, "r_pnl"].sum()
        gl = abs(s.loc[s["r_pnl"] <= 0, "r_pnl"].sum())
        pf = gw / gl if gl > 0 else float("inf")

        # Per-leg breakdown
        leg_r = s.groupby("leg")["r_pnl"].sum()
        best_leg = leg_r.idxmax() if len(leg_r) > 0 else "—"
        worst_leg = leg_r.idxmin() if len(leg_r) > 0 else "—"
        best_val = leg_r.max() if len(leg_r) > 0 else 0
        worst_val = leg_r.min() if len(leg_r) > 0 else 0

        name = regime_names.get(r, str(r)) if isinstance(regime_names, dict) else str(r)
        print(f"  {name:30s}  {len(s):>6d}  {wr:>5.1%}  {avg_r:>+6.3f}  {total_r:>+7.1f}R  {pf:>5.2f}"
              f"  {best_leg:>9s}({best_val:+.0f})  {worst_leg:>9s}({worst_val:+.0f})")

    # Total row
    total_r = valid["r_pnl"].sum()
    print("  " + "-" * 105)
    print(f"  {'TOTAL':30s}  {len(valid):>6d}  {(valid['r_pnl']>0).mean():>5.1%}  "
          f"{valid['r_pnl'].mean():>+6.3f}  {total_r:>+7.1f}R")


def per_leg_regime_table(tdf, regime_col, regime_names, title):
    """Print per-leg x regime grid."""
    print(f"\n{'='*90}")
    print(f"  {title} — PER-LEG DETAIL")
    print(f"{'='*90}")

    valid = tdf.dropna(subset=[regime_col])
    regimes = sorted(valid[regime_col].unique())
    legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]

    # Header
    header = f"  {'Regime':30s}"
    for leg in legs:
        short = leg.replace("_", " ")[:12]
        header += f"  {short:>14s}"
    header += f"  {'PORTFOLIO':>12s}"
    print(header)
    print("  " + "-" * (30 + 15 * (len(legs) + 1)))

    for r in regimes:
        s = valid[valid[regime_col] == r]
        name = regime_names.get(r, str(r)) if isinstance(regime_names, dict) else str(r)
        row = f"  {name:30s}"
        for leg in legs:
            ls = s[s["leg"] == leg]
            if len(ls) > 0:
                tr = ls["r_pnl"].sum()
                wr = (ls["r_pnl"] > 0).mean()
                row += f"  {tr:>+6.1f}R({wr:.0%})"
            else:
                row += f"  {'—':>14s}"
        port_r = s["r_pnl"].sum()
        row += f"  {port_r:>+7.1f}R"
        print(row)

    # Total
    row = f"  {'TOTAL':30s}"
    for leg in legs:
        ls = valid[valid["leg"] == leg]
        row += f"  {ls['r_pnl'].sum():>+6.1f}R({(ls['r_pnl']>0).mean():.0%})"
    row += f"  {valid['r_pnl'].sum():>+7.1f}R"
    print(row)


def yearly_regime_table(daily, tdf, regime_col, regime_names, title):
    """Show yearly regime composition vs portfolio R."""
    print(f"\n{'='*90}")
    print(f"  {title} — YEARLY COMPOSITION")
    print(f"{'='*90}")

    valid = tdf.dropna(subset=[regime_col])
    d = daily.dropna(subset=[regime_col])
    d_year = d.copy()
    d_year["year"] = d_year.index.year
    valid["year"] = valid["date"].dt.year

    regimes = sorted(d[regime_col].unique())
    years = sorted(d_year["year"].unique())

    # Build composition
    yearly_comp = d_year.groupby(["year", regime_col]).size().unstack(fill_value=0)
    yearly_pct = yearly_comp.div(yearly_comp.sum(axis=1), axis=0)

    header = f"  {'Year':>6s}"
    for r in regimes:
        name = regime_names.get(r, str(r)) if isinstance(regime_names, dict) else str(r)
        short = name[:10]
        header += f"  {short:>10s}"
    header += f"  {'Port R':>8s}"
    print(header)
    print("  " + "-" * (6 + 11 * len(regimes) + 10))

    for year in years:
        row = f"  {year:>6d}"
        for r in regimes:
            pct = yearly_pct.loc[year, r] if (year in yearly_pct.index and r in yearly_pct.columns) else 0
            row += f"  {pct:>9.0%} "
        yr_r = valid[valid["year"] == year]["r_pnl"].sum()
        row += f"  {yr_r:>+7.1f}R"
        print(row)


# ═══════════════════════════════════════════════════════════════════════
# 9. PLOTS
# ═══════════════════════════════════════════════════════════════════════

DARK_BG = "#0d0d1a"
PANEL_BG = "#1a1a2e"
COLORS = ["#2ecc71", "#f1c40f", "#e67e22", "#e74c3c", "#8e44ad",
          "#3498db", "#1abc9c", "#e91e63", "#9b59b6", "#00bcd4"]


def plot_portfolio_regimes(daily, tdf, regime_col, regime_names, method_name):
    """Multi-panel: price + regime overlay, per-leg equity, combined equity."""
    valid = tdf.dropna(subset=[regime_col]).sort_values("date")
    regimes = sorted(daily[regime_col].dropna().unique())
    n_regimes = len(regimes)
    colors = COLORS[:n_regimes]

    fig, axes = plt.subplots(4, 1, figsize=(20, 18),
                             gridspec_kw={"height_ratios": [3, 1.5, 2, 2]})

    # Panel 1: NQ price with regime overlay
    ax = axes[0]
    ax.plot(daily.index, daily["close"], color="white", linewidth=0.5, alpha=0.8)
    for i, r in enumerate(regimes):
        mask = daily[regime_col] == r
        name = regime_names.get(r, str(r)) if isinstance(regime_names, dict) else str(r)
        ax.fill_between(daily.index, daily["close"].min(), daily["close"].max(),
                        where=mask, alpha=0.15, color=colors[i], label=name)
    ax.set_title(f"NQ Price with {method_name} Regimes", fontsize=14, color="white")
    ax.set_ylabel("NQ Price", color="white")
    ax.legend(loc="upper left", fontsize=8, facecolor=PANEL_BG, edgecolor="gray",
              labelcolor="white")
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors="white")

    # Panel 2: realized vol colored by regime
    ax = axes[1]
    for i, r in enumerate(regimes):
        mask = daily[regime_col] == r
        ax.scatter(daily.index[mask], daily.loc[mask, "realized_vol_21d"],
                   s=2, c=colors[i], alpha=0.6)
    ax.set_ylabel("21d Vol", color="white")
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors="white")

    # Panel 3: per-leg equity curves
    ax = axes[2]
    leg_colors = {"NQ_NY_LSI": "#3498db", "NQ_ASIA_ORB": "#e74c3c",
                  "ES_ASIA_CONT": "#2ecc71", "ES_NY_CONT": "#f39c12"}
    for leg_name in ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]:
        leg_data = valid[valid["leg"] == leg_name].sort_values("date")
        if len(leg_data) == 0:
            continue
        cum_r = leg_data["r_pnl"].cumsum()
        ax.plot(leg_data["date"].values, cum_r.values,
                color=leg_colors[leg_name], linewidth=1, alpha=0.8,
                label=f"{leg_name} ({cum_r.iloc[-1]:+.0f}R)")
    ax.set_ylabel("Leg Cumulative R", color="white")
    ax.legend(loc="upper left", fontsize=8, facecolor=PANEL_BG, edgecolor="gray",
              labelcolor="white")
    ax.axhline(0, color="gray", linewidth=0.3)
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors="white")

    # Panel 4: combined portfolio equity colored by regime
    ax = axes[3]
    port_daily = valid.groupby("date")["r_pnl"].sum().sort_index().cumsum()
    ax.plot(port_daily.index, port_daily.values, color="white", linewidth=1.2)

    # Color dots by regime
    port_regime = valid.groupby("date").agg({
        "r_pnl": "sum", regime_col: "first"
    }).sort_index()
    port_regime["cum_r"] = port_regime["r_pnl"].cumsum()
    for i, r in enumerate(regimes):
        mask = port_regime[regime_col] == r
        ax.scatter(port_regime.index[mask], port_regime.loc[mask, "cum_r"],
                   s=6, c=colors[i], alpha=0.7, zorder=5)
    ax.set_ylabel("Portfolio Cumulative R", color="white")
    ax.set_xlabel("Date", color="white")
    ax.axhline(0, color="gray", linewidth=0.3)
    ax.set_facecolor(PANEL_BG)
    ax.tick_params(colors="white")

    fig.patch.set_facecolor(DARK_BG)
    plt.tight_layout()
    fname = OUTPUT_DIR / f"alpha_v1_{method_name.lower().replace(' ', '_')}_regimes.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    print(f"  Saved: {fname}")
    plt.close(fig)


def plot_regime_comparison_heatmap(tdf, daily):
    """Heatmap: per-leg avg R across all 3 regime systems."""
    fig, axes = plt.subplots(1, 3, figsize=(24, 8))
    legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT"]

    configs = [
        ("hmm_regime", "HMM Regimes"),
        ("lstm_regime", "LSTM Regimes"),
        ("rule_regime", "Rule-Based (3x3)"),
    ]

    for ax, (col, title) in zip(axes, configs):
        valid = tdf.dropna(subset=[col])
        regimes = sorted(valid[col].unique())

        grid = np.zeros((len(legs), len(regimes)))
        for i, leg in enumerate(legs):
            for j, r in enumerate(regimes):
                s = valid[(valid["leg"] == leg) & (valid[col] == r)]
                grid[i, j] = s["r_pnl"].sum() if len(s) > 0 else 0

        im = ax.imshow(grid, cmap="RdYlGn", aspect="auto",
                       vmin=-max(abs(grid.min()), abs(grid.max())),
                       vmax=max(abs(grid.min()), abs(grid.max())))

        ax.set_yticks(range(len(legs)))
        ax.set_yticklabels([l.replace("_", "\n") for l in legs], fontsize=8, color="white")
        ax.set_xticks(range(len(regimes)))
        xlabels = [str(r)[:12] for r in regimes]
        ax.set_xticklabels(xlabels, fontsize=7, rotation=45, ha="right", color="white")
        ax.set_title(title, fontsize=12, color="white")
        ax.set_facecolor(PANEL_BG)

        # Annotate cells
        for i in range(len(legs)):
            for j in range(len(regimes)):
                val = grid[i, j]
                color = "white" if abs(val) > grid.max() * 0.5 else "black"
                ax.text(j, i, f"{val:+.0f}", ha="center", va="center",
                        fontsize=8, color=color, fontweight="bold")

    fig.patch.set_facecolor(DARK_BG)
    plt.tight_layout()
    fname = OUTPUT_DIR / "alpha_v1_regime_heatmap.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    print(f"  Saved: {fname}")
    plt.close(fig)


def plot_drawdown_by_regime(tdf, regime_col, regime_names, method_name):
    """Show portfolio drawdown periods colored by dominant regime."""
    valid = tdf.dropna(subset=[regime_col]).sort_values("date")
    port_daily = valid.groupby("date").agg({
        "r_pnl": "sum", regime_col: "first"
    }).sort_index()
    port_daily["cum_r"] = port_daily["r_pnl"].cumsum()
    port_daily["peak"] = port_daily["cum_r"].cummax()
    port_daily["dd"] = port_daily["cum_r"] - port_daily["peak"]

    regimes = sorted(port_daily[regime_col].dropna().unique())
    colors = COLORS[:len(regimes)]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(18, 10),
                                    gridspec_kw={"height_ratios": [2, 1]})

    # Equity curve
    ax1.plot(port_daily.index, port_daily["cum_r"], color="white", linewidth=1)
    for i, r in enumerate(regimes):
        mask = port_daily[regime_col] == r
        name = regime_names.get(r, str(r)) if isinstance(regime_names, dict) else str(r)
        ax1.scatter(port_daily.index[mask], port_daily.loc[mask, "cum_r"],
                    s=8, c=colors[i], alpha=0.7, label=name, zorder=5)
    ax1.set_ylabel("Cumulative R", color="white")
    ax1.set_title(f"ALPHA V1 Portfolio — Equity & Drawdown by {method_name}", fontsize=13, color="white")
    ax1.legend(loc="upper left", fontsize=8, facecolor=PANEL_BG, edgecolor="gray",
               labelcolor="white")
    ax1.set_facecolor(PANEL_BG)
    ax1.tick_params(colors="white")

    # Drawdown colored by regime
    for i, r in enumerate(regimes):
        mask = port_daily[regime_col] == r
        ax2.bar(port_daily.index[mask], port_daily.loc[mask, "dd"],
                color=colors[i], alpha=0.7, width=2)
    ax2.set_ylabel("Drawdown (R)", color="white")
    ax2.set_xlabel("Date", color="white")
    ax2.set_facecolor(PANEL_BG)
    ax2.tick_params(colors="white")

    fig.patch.set_facecolor(DARK_BG)
    plt.tight_layout()
    fname = OUTPUT_DIR / f"alpha_v1_{method_name.lower().replace(' ', '_')}_drawdown.png"
    fig.savefig(fname, dpi=150, bbox_inches="tight", facecolor=DARK_BG)
    print(f"  Saved: {fname}")
    plt.close(fig)


# ═══════════════════════════════════════════════════════════════════════
# 10. CROSS-METHOD AGREEMENT
# ═══════════════════════════════════════════════════════════════════════

def regime_agreement(daily):
    """Compare HMM vs LSTM vs rule-based regime labels."""
    print(f"\n{'='*90}")
    print(f"  REGIME METHOD AGREEMENT")
    print(f"{'='*90}")

    d = daily.dropna(subset=["hmm_regime", "lstm_regime"]).copy()
    d["hmm_int"] = d["hmm_regime"].astype(int)
    d["lstm_int"] = d["lstm_regime"].astype(int)

    ari_hl = adjusted_rand_score(d["hmm_int"], d["lstm_int"])
    print(f"\n  HMM vs LSTM:       ARI = {ari_hl:.3f}")

    # Map rule-based to integers for ARI
    rule_map = {r: i for i, r in enumerate(sorted(d["rule_regime"].unique()))}
    d["rule_int"] = d["rule_regime"].map(rule_map)

    ari_hr = adjusted_rand_score(d["hmm_int"], d["rule_int"])
    ari_lr = adjusted_rand_score(d["lstm_int"], d["rule_int"])
    print(f"  HMM vs Rule-based: ARI = {ari_hr:.3f}")
    print(f"  LSTM vs Rule-based: ARI = {ari_lr:.3f}")
    print(f"\n  (ARI: 1.0 = perfect agreement, 0.0 = random)")


# ═══════════════════════════════════════════════════════════════════════
# 11. BEST / WORST CONDITIONS SUMMARY
# ═══════════════════════════════════════════════════════════════════════

def best_worst_summary(tdf):
    """Identify the best and worst conditions for each leg and portfolio."""
    print(f"\n{'='*90}")
    print(f"  BEST / WORST CONDITIONS SUMMARY")
    print(f"{'='*90}")

    legs = ["NQ_NY_LSI", "NQ_ASIA_ORB", "ES_ASIA_CONT", "ES_NY_CONT", "PORTFOLIO"]

    for regime_col, label in [("hmm_regime", "HMM"), ("lstm_regime", "LSTM"),
                               ("rule_regime", "Rule-Based")]:
        print(f"\n  --- {label} ---")
        print(f"  {'Leg':20s}  {'Best Regime':30s}  {'Avg R':>7s}  {'Worst Regime':30s}  {'Avg R':>7s}")
        print("  " + "-" * 100)

        valid = tdf.dropna(subset=[regime_col])

        for leg in legs:
            if leg == "PORTFOLIO":
                s = valid
            else:
                s = valid[valid["leg"] == leg]

            if len(s) == 0:
                continue

            by_regime = s.groupby(regime_col)["r_pnl"].agg(["mean", "sum", "count"])
            # Filter to regimes with at least 20 trades
            by_regime = by_regime[by_regime["count"] >= 20]

            if len(by_regime) == 0:
                continue

            best = by_regime["mean"].idxmax()
            worst = by_regime["mean"].idxmin()
            print(f"  {leg:20s}  {str(best):30s}  {by_regime.loc[best, 'mean']:>+6.3f}"
                  f"  {str(worst):30s}  {by_regime.loc[worst, 'mean']:>+6.3f}")


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    print("=" * 90)
    print("  ALPHA V1 PORTFOLIO REGIME ANALYSIS — HMM + LSTM + RULE-BASED")
    print("=" * 90)

    # Load data & run backtests
    data, leg_trades = load_and_run()

    # Build daily features from NQ (macro driver for all legs)
    print("\nBuilding daily features from NQ...")
    daily = build_daily_features(data["NQ"]["5m"])
    print(f"  {len(daily)} trading days")

    # Assign rule-based regime
    print("\nAssigning rule-based regimes...")
    daily = assign_rule_based_regime(daily)
    print(f"  9 buckets: {daily['rule_regime'].value_counts().to_dict()}")

    # Fit HMM
    daily, hmm_names, hmm_model = fit_hmm(daily)

    # Fit LSTM
    daily, lstm_names, latent_np, seq_dates = fit_lstm(daily)

    # Build trade DataFrame and merge regimes
    print("\nMapping trades to regimes...")
    tdf = build_trade_df(leg_trades)
    tdf = merge_regimes(tdf, daily)
    print(f"  {len(tdf)} total trades across all legs")

    # ── ANALYSIS ──

    # Rule-based regime (the one you already use)
    rule_regime_names = {r: r for r in sorted(daily["rule_regime"].unique())}
    regime_perf_table(tdf, "rule_regime", rule_regime_names, "RULE-BASED REGIME (3x3 Trend x Vol)")
    per_leg_regime_table(tdf, "rule_regime", rule_regime_names, "RULE-BASED REGIME")

    # HMM regime
    regime_perf_table(tdf, "hmm_regime", hmm_names, "HMM VOLATILITY REGIMES")
    per_leg_regime_table(tdf, "hmm_regime", hmm_names, "HMM REGIMES")

    # LSTM regime
    regime_perf_table(tdf, "lstm_regime", lstm_names, "LSTM AUTOENCODER REGIMES")
    per_leg_regime_table(tdf, "lstm_regime", lstm_names, "LSTM REGIMES")

    # Yearly breakdowns
    yearly_regime_table(daily, tdf, "hmm_regime", hmm_names, "HMM REGIMES")

    # Agreement between methods
    regime_agreement(daily)

    # Best/worst summary
    best_worst_summary(tdf)

    # ── PLOTS ──
    print("\nGenerating plots...")
    plot_portfolio_regimes(daily, tdf, "hmm_regime", hmm_names, "HMM")
    plot_portfolio_regimes(daily, tdf, "lstm_regime", lstm_names, "LSTM")
    plot_portfolio_regimes(daily, tdf, "rule_regime", rule_regime_names, "Rule Based")
    plot_regime_comparison_heatmap(tdf, daily)
    plot_drawdown_by_regime(tdf, "hmm_regime", hmm_names, "HMM")
    plot_drawdown_by_regime(tdf, "lstm_regime", lstm_names, "LSTM")
    plot_drawdown_by_regime(tdf, "rule_regime", rule_regime_names, "Rule Based")

    print(f"\nTotal runtime: {time.time()-t0:.1f}s")
    print("Done.")


if __name__ == "__main__":
    main()
