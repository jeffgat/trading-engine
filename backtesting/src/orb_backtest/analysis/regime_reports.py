"""Regime report builder for saved backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np
import pandas as pd

from ..data.instruments import get_instrument
from ..data.loader import load_5m_data
from ..experiments import get_backtest_result


@dataclass(frozen=True)
class RegimeReportConfig:
    method: str = "both"  # "hmm" | "lstm" | "both"
    start_pad_days: int = 80
    end_pad_days: int = 5
    lstm_lookback: int = 21


def build_regime_report(backtest_result_id: str, config: RegimeReportConfig | None = None) -> dict:
    """Build a regime report for a saved backtest result id."""
    cfg = config or RegimeReportConfig()
    result = get_backtest_result(backtest_result_id)
    if result is None:
        raise ValueError(f"backtest result not found: {backtest_result_id}")

    trades_df = _load_filled_trades(result)
    if trades_df.empty:
        raise ValueError("backtest has no filled trades")

    meta = _build_meta(result, trades_df, backtest_result_id)
    daily = _load_daily_features(meta["instrument"], meta["date_start"], meta["date_end"], cfg)

    report: dict[str, Any] = {
        "meta": meta,
        "summary": {
            "methods": [],
            "trade_count": int(len(trades_df)),
        },
    }

    if cfg.method in ("hmm", "both"):
        hmm = _run_hmm_regimes(daily, trades_df)
        report["hmm"] = hmm
        report["summary"]["methods"].append("hmm")

    if cfg.method in ("lstm", "both"):
        lstm = _run_lstm_regimes(daily, trades_df, lookback=cfg.lstm_lookback)
        report["lstm"] = lstm
        report["summary"]["methods"].append("lstm")

    report["summary"]["methods"] = sorted(report["summary"]["methods"])
    _attach_summary_rollups(report)
    return report


def _load_filled_trades(result: dict) -> pd.DataFrame:
    trades = pd.DataFrame(result.get("trades", []))
    if trades.empty:
        return trades
    trades["date"] = pd.to_datetime(trades["date"])
    trades = trades[trades["exit_type"] != "no_fill"].copy()
    risk = float(result.get("config", {}).get("risk_usd", 1.0) or 1.0)
    trades["r_pnl"] = trades["pnl_usd"] / risk
    return trades


def _build_meta(result: dict, trades_df: pd.DataFrame, backtest_result_id: str) -> dict:
    cfg = result.get("config", {})
    sessions = sorted({str(s).upper() for s in trades_df.get("session", []).dropna().unique()})
    date_start = trades_df["date"].min().strftime("%Y-%m-%d")
    date_end = trades_df["date"].max().strftime("%Y-%m-%d")
    return {
        "backtest_result_id": backtest_result_id,
        "backtest_name": result.get("name"),
        "instrument": cfg.get("instrument", "NQ"),
        "sessions": "+".join(sessions),
        "date_start": date_start,
        "date_end": date_end,
    }


def _load_daily_features(instrument: str, start_date: str, end_date: str, cfg: RegimeReportConfig) -> pd.DataFrame:
    inst = get_instrument(instrument)
    start = pd.Timestamp(start_date) - timedelta(days=cfg.start_pad_days)
    end = pd.Timestamp(end_date) + timedelta(days=cfg.end_pad_days)
    df = load_5m_data(inst.data_file, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"))

    daily = df.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna(subset=["open"])
    daily = daily[daily["volume"] > 0].copy()

    daily["returns"] = daily["close"].pct_change()
    daily["log_returns"] = np.log(daily["close"] / daily["close"].shift(1))
    daily["range_pct"] = (daily["high"] - daily["low"]) / daily["close"]
    daily["true_range"] = np.maximum(
        daily["high"] - daily["low"],
        np.maximum(
            abs(daily["high"] - daily["close"].shift(1)),
            abs(daily["low"] - daily["close"].shift(1)),
        ),
    )
    daily["atr_pct"] = daily["true_range"].rolling(14).mean() / daily["close"]
    daily["realized_vol_5d"] = daily["log_returns"].rolling(5).std() * np.sqrt(252)
    daily["realized_vol_21d"] = daily["log_returns"].rolling(21).std() * np.sqrt(252)
    daily["abs_return"] = daily["returns"].abs()
    daily["volume_ma_ratio"] = daily["volume"] / daily["volume"].rolling(21).mean()
    daily["volume_zscore"] = (daily["volume"] - daily["volume"].rolling(63).mean()) / daily["volume"].rolling(63).std()
    daily["close_vs_sma20"] = daily["close"] / daily["close"].rolling(20).mean() - 1
    daily["close_vs_sma50"] = daily["close"] / daily["close"].rolling(50).mean() - 1
    daily["high_low_ratio"] = daily["high"] / daily["low"] - 1
    daily["gk_vol"] = np.sqrt(
        0.5 * np.log(daily["high"] / daily["low"]) ** 2
        - (2 * np.log(2) - 1) * np.log(daily["close"] / daily["open"]) ** 2
    )
    daily["gk_vol_5d"] = daily["gk_vol"].rolling(5).mean()
    daily["gk_vol_21d"] = daily["gk_vol"].rolling(21).mean()
    daily["up_vol_ratio"] = (
        daily["returns"].clip(lower=0).rolling(21).std()
        / daily["returns"].clip(upper=0).abs().rolling(21).std()
    )
    daily.replace([np.inf, -np.inf], np.nan, inplace=True)
    daily.dropna(inplace=True)
    return daily


def _run_hmm_regimes(daily: pd.DataFrame, trades_df: pd.DataFrame) -> dict:
    from hmmlearn.hmm import GaussianHMM

    feature_cols = ["realized_vol_21d", "range_pct", "abs_return", "atr_pct"]
    X = daily[feature_cols].values
    X_scaled = (X - X.mean(axis=0)) / X.std(axis=0)

    best_model = None
    best_bic = np.inf
    best_n = 0
    for n_states in (2, 3, 4):
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
                log_likelihood = model.score(X_scaled)
                n_params = n_states * (len(feature_cols) + len(feature_cols) * (len(feature_cols) + 1) // 2) + n_states**2
                bic = -2 * log_likelihood + n_params * np.log(len(X_scaled))
                if bic < best_bic:
                    best_bic = bic
                    best_model = model
                    best_n = n_states
            except Exception:
                continue

    states = best_model.predict(X_scaled)
    hmm_daily = daily[["realized_vol_21d", "range_pct", "abs_return", "atr_pct"]].copy()
    hmm_daily["regime"] = states
    order = hmm_daily.groupby("regime")["realized_vol_21d"].mean().sort_values().index.tolist()
    map_h = {old: new for new, old in enumerate(order)}
    hmm_daily["regime"] = hmm_daily["regime"].map(map_h)

    mapped, coverage = _map_trades_to_regimes(trades_df, hmm_daily)
    stats = _regime_stats(mapped, hmm_daily)

    # Add per-regime feature fingerprint
    feature_fingerprint = _build_feature_fingerprint(
        hmm_daily, feature_cols, regime_col="regime"
    )
    for s in stats:
        r = s["regime"]
        if r in feature_fingerprint:
            s["features"] = feature_fingerprint[r]
            s["label"] = _label_hmm_regime(s)

    return {
        "states": best_n,
        "bic": float(best_bic),
        "coverage": coverage,
        "regime_stats": stats,
        "feature_cols": feature_cols,
        "description": "Gaussian HMM on 4 volatility features. States ordered by mean 21d realized vol (low to high).",
    }


def _run_lstm_regimes(daily: pd.DataFrame, trades_df: pd.DataFrame, lookback: int) -> dict:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset
    from sklearn.cluster import KMeans
    from sklearn.metrics import silhouette_score
    from sklearn.preprocessing import StandardScaler

    feature_cols = [
        "returns",
        "abs_return",
        "range_pct",
        "atr_pct",
        "realized_vol_5d",
        "realized_vol_21d",
        "volume_zscore",
        "close_vs_sma20",
        "close_vs_sma50",
        "high_low_ratio",
        "gk_vol_5d",
        "gk_vol_21d",
        "up_vol_ratio",
    ]
    scaler = StandardScaler()
    features_scaled = scaler.fit_transform(daily[feature_cols].values)

    X_seq = np.array([features_scaled[i - lookback:i] for i in range(lookback, len(features_scaled))])
    seq_dates = daily.index[lookback:]

    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    torch.manual_seed(42)
    np.random.seed(42)

    latent_dim = 8
    hidden_dim = 32
    num_layers = 2
    epochs = 80
    batch_size = 128
    lr = 1e-3

    class _Encoder(nn.Module):
        def __init__(self, inp, hid, lat, layers):
            super().__init__()
            self.lstm = nn.LSTM(inp, hid, layers, batch_first=True, dropout=0.1)
            self.fc = nn.Linear(hid, lat)

        def forward(self, x):
            _, (h_n, _) = self.lstm(x)
            return self.fc(h_n[-1])

    class _Decoder(nn.Module):
        def __init__(self, lat, hid, out, seq_len, layers):
            super().__init__()
            self.seq_len = seq_len
            self.fc = nn.Linear(lat, hid)
            self.lstm = nn.LSTM(hid, hid, layers, batch_first=True, dropout=0.1)
            self.out = nn.Linear(hid, out)

        def forward(self, z):
            h = self.fc(z).unsqueeze(1).repeat(1, self.seq_len, 1)
            out, _ = self.lstm(h)
            return self.out(out)

    class _Autoencoder(nn.Module):
        def __init__(self, inp, hid, lat, seq_len, layers):
            super().__init__()
            self.encoder = _Encoder(inp, hid, lat, layers)
            self.decoder = _Decoder(lat, hid, inp, seq_len, layers)

        def forward(self, x):
            z = self.encoder(x)
            x_hat = self.decoder(z)
            return x_hat, z

    model = _Autoencoder(len(feature_cols), hidden_dim, latent_dim, lookback, num_layers).to(device)
    X_tensor = torch.FloatTensor(X_seq).to(device)
    loader = DataLoader(TensorDataset(X_tensor, X_tensor), batch_size=batch_size, shuffle=True)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
    criterion = nn.MSELoss()

    for _ in range(epochs):
        model.train()
        for batch_x, _ in loader:
            optimizer.zero_grad()
            x_hat, _ = model(batch_x)
            loss = criterion(x_hat, batch_x)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
        scheduler.step()

    model.eval()
    with torch.no_grad():
        _, latent = model(X_tensor)
    latent_np = latent.cpu().numpy()

    best_k, best_score, best_labels = 0, -1, None
    for k in (2, 3, 4, 5):
        km = KMeans(n_clusters=k, n_init=20, random_state=42)
        labels = km.fit_predict(latent_np)
        score = silhouette_score(latent_np, labels)
        if score > best_score:
            best_k, best_score, best_labels = k, score, labels

    lstm_daily = daily.loc[seq_dates, feature_cols].copy()
    lstm_daily["regime"] = best_labels
    order = lstm_daily.groupby("regime")["realized_vol_21d"].mean().sort_values().index.tolist()
    map_l = {old: new for new, old in enumerate(order)}
    lstm_daily["regime"] = lstm_daily["regime"].map(map_l)

    mapped, coverage = _map_trades_to_regimes(trades_df, lstm_daily)
    stats = _regime_stats(mapped, lstm_daily)

    # Add per-regime feature fingerprint
    feature_fingerprint = _build_feature_fingerprint(
        lstm_daily, feature_cols, regime_col="regime"
    )
    for s in stats:
        r = s["regime"]
        if r in feature_fingerprint:
            s["features"] = feature_fingerprint[r]
            s["label"] = _label_lstm_regime(s)

    return {
        "clusters": int(best_k),
        "silhouette": float(best_score),
        "device": str(device),
        "coverage": coverage,
        "regime_stats": stats,
        "feature_cols": feature_cols,
        "description": "LSTM autoencoder (8D latent) + K-Means on 13 market features. Clusters ordered by mean 21d realized vol.",
    }


def _map_trades_to_regimes(trades_df: pd.DataFrame, daily_regimes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    mapped = trades_df.copy()
    mapped["date_norm"] = mapped["date"].dt.normalize()
    lookup = daily_regimes[["regime"]].copy()
    lookup.index = lookup.index.normalize()
    mapped = mapped.merge(lookup, left_on="date_norm", right_index=True, how="left")
    coverage = {
        "mapped": int(mapped["regime"].notna().sum()),
        "unmapped": int(mapped["regime"].isna().sum()),
        "total": int(len(mapped)),
    }
    mapped = mapped.dropna(subset=["regime"]).copy()
    mapped["regime"] = mapped["regime"].astype(int)
    return mapped, coverage


def _regime_stats(mapped: pd.DataFrame, daily_regimes: pd.DataFrame | None = None) -> list[dict]:
    stats = []
    # Build per-regime volatility profile from daily data
    vol_profile = {}
    if daily_regimes is not None and "regime" in daily_regimes.columns:
        total_days = len(daily_regimes)
        for r in sorted(daily_regimes["regime"].unique()):
            rd = daily_regimes[daily_regimes["regime"] == r]
            vol_profile[int(r)] = {
                "days": int(len(rd)),
                "pct_days": float(len(rd) / total_days) if total_days > 0 else 0.0,
                "mean_vol": float(rd["realized_vol_21d"].mean()) if "realized_vol_21d" in rd.columns else None,
                "mean_range_pct": float(rd["range_pct"].mean()) if "range_pct" in rd.columns else None,
            }

    for r in sorted(mapped["regime"].unique()):
        subset = mapped[mapped["regime"] == r]
        win_rate = float((subset["r_pnl"] > 0).mean())
        gross_win = subset.loc[subset["r_pnl"] > 0, "r_pnl"].sum()
        gross_loss = abs(subset.loc[subset["r_pnl"] <= 0, "r_pnl"].sum())
        pf = float(gross_win / gross_loss) if gross_loss > 0 else float("inf")
        row: dict = {
            "regime": int(r),
            "trades": int(len(subset)),
            "win_rate": win_rate,
            "total_r": float(subset["r_pnl"].sum()),
            "avg_r": float(subset["r_pnl"].mean()),
            "pf": pf,
            "long_trades": int((subset["direction"] == "long").sum()) if "direction" in subset else 0,
            "short_trades": int((subset["direction"] == "short").sum()) if "direction" in subset else 0,
        }
        if int(r) in vol_profile:
            row.update(vol_profile[int(r)])
        stats.append(row)
    return stats


def _build_feature_fingerprint(
    daily_regimes: pd.DataFrame, feature_cols: list[str], regime_col: str = "regime"
) -> dict[int, dict[str, float]]:
    """Compute mean feature values per regime for display."""
    result = {}
    for r in sorted(daily_regimes[regime_col].unique()):
        rd = daily_regimes[daily_regimes[regime_col] == r]
        means = {}
        for col in feature_cols:
            if col in rd.columns:
                means[col] = float(rd[col].mean())
        result[int(r)] = means
    return result


# Human-readable labels for regimes based on vol characteristics
_VOL_LABELS = ["Low Vol", "Moderate Vol", "Elevated Vol", "High Vol", "Extreme Vol"]


def _label_hmm_regime(stat: dict) -> str:
    """Generate a label for an HMM regime based on vol level."""
    vol = stat.get("mean_vol")
    if vol is None:
        return f"Regime {stat['regime']}"
    if vol < 0.10:
        return "Quiet"
    elif vol < 0.15:
        return "Low Vol"
    elif vol < 0.22:
        return "Normal"
    elif vol < 0.30:
        return "Elevated"
    else:
        return "Crisis / High Vol"


def _label_lstm_regime(stat: dict) -> str:
    """Generate a label for an LSTM regime from its feature fingerprint."""
    f = stat.get("features", {})
    if not f:
        return f"Cluster {stat['regime']}"

    parts = []
    # Trend: close vs SMA50
    sma50 = f.get("close_vs_sma50", 0)
    if sma50 > 0.02:
        parts.append("Trending Up")
    elif sma50 < -0.02:
        parts.append("Trending Down")
    else:
        parts.append("Range-Bound")

    # Vol character
    vol = f.get("realized_vol_21d", 0)
    if vol > 0.25:
        parts.append("High Vol")
    elif vol < 0.12:
        parts.append("Low Vol")

    # Volume
    vz = f.get("volume_zscore", 0)
    if vz > 0.5:
        parts.append("Heavy Volume")
    elif vz < -0.3:
        parts.append("Thin Volume")

    # Skew
    up_ratio = f.get("up_vol_ratio", 1.0)
    if up_ratio > 1.3:
        parts.append("Bullish Skew")
    elif up_ratio < 0.7:
        parts.append("Bearish Skew")

    return " / ".join(parts) if parts else f"Cluster {stat['regime']}"


def _attach_summary_rollups(report: dict) -> None:
    summary = report.get("summary", {})
    if "hmm" in report:
        hmm = report["hmm"]
        hmm_total = sum(r["total_r"] for r in hmm["regime_stats"]) if hmm.get("regime_stats") else 0.0
        summary["hmm_total_r"] = float(hmm_total)
        summary["hmm_best_pf"] = max((r["pf"] for r in hmm["regime_stats"]), default=None)
    if "lstm" in report:
        lstm = report["lstm"]
        lstm_total = sum(r["total_r"] for r in lstm["regime_stats"]) if lstm.get("regime_stats") else 0.0
        summary["lstm_total_r"] = float(lstm_total)
        summary["lstm_best_pf"] = max((r["pf"] for r in lstm["regime_stats"]), default=None)
    report["summary"] = summary
