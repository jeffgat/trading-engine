"""Round-1 prop regime-specialist research helpers.

This module keeps the research workflow reusable:
- Build a point-in-time NQ NY regime calendar.
- Evaluate strategy specialists in/out of their target regime.
- Apply the 30m HH/HL + VWAP bull subvariant gate.
- Convert trade streams into prop-account attempt outcomes and EV scorecards.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

from ..config import SessionConfig
from ..engine.simulator import EXIT_NO_FILL, TradeResult
from ..results.metrics import compute_metrics
from ..signals.daily_atr import compute_daily_atr
from ..signals.orb import compute_orb_levels
from ..signals.session import compute_session_days, compute_session_masks
from ..signals.structure_15m import compute_all_15m_signals
from ..signals.vwap import compute_session_vwap


DEFAULT_HOLDOUT_START = "2025-01-01"


@dataclass(frozen=True)
class PropFirmProfile:
    """Configurable prop-account model used by the research workflow."""

    account_fee: float = 50.0
    reset_fee: float = 50.0
    payout_split: float = 0.80
    payout_target_r: float = 5.0
    breach_limit_r: float = -4.0
    daily_loss_limit_r: float = -2.0
    min_trading_days: int = 5
    cohort_sizes: tuple[int, ...] = (10, 25, 50)
    block_size_days: int = 20


@dataclass(frozen=True)
class AccountAttemptOutcome:
    """Result of replaying one account start through a dated trade stream."""

    specialist_name: str
    account_start: str
    outcome: str
    outcome_date: str
    days_to_outcome: int
    trades_to_outcome: int
    trading_days_to_outcome: int
    final_r: float
    peak_r: float
    trough_r: float
    net_payout: float
    breach_reason: str


def build_nq_ny_regime_calendar(
    df: pd.DataFrame,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """Build the round-1 daily regime calendar using only prior-day features."""

    daily = (
        df.resample("1D")
        .agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        })
        .dropna(subset=["close"])
        .copy()
    )
    daily = daily[daily["volume"] > 0].copy()

    close = daily["close"]
    log_returns = np.log(close / close.shift(1))
    realized_vol_21d = log_returns.rolling(21).std() * np.sqrt(252)
    close_vs_sma20 = close / close.rolling(20).mean() - 1.0
    ret_5d = close.pct_change(5)

    # Shift by one session so every row uses information known before that day opens.
    cal = pd.DataFrame(
        {
            "date": daily.index.normalize(),
            "close_vs_sma20": close_vs_sma20.shift(1),
            "ret_5d": ret_5d.shift(1),
            "realized_vol_21d": realized_vol_21d.shift(1),
        }
    )
    cal["warmup_ok"] = cal[["close_vs_sma20", "ret_5d", "realized_vol_21d"]].notna().all(axis=1)
    cal["low_confidence"] = cal["warmup_ok"] & (
        (cal["close_vs_sma20"].abs() < 0.0025) | (cal["ret_5d"].abs() < 0.005)
    )

    bull_mask = cal["warmup_ok"] & (cal["close_vs_sma20"] >= 0.005) & (cal["ret_5d"] > 0.0)
    bear_mask = cal["warmup_ok"] & (cal["close_vs_sma20"] <= -0.005) & (cal["ret_5d"] < 0.0)

    cal["regime"] = "sideways"
    cal.loc[bull_mask, "regime"] = "bull"
    cal.loc[bear_mask, "regime"] = "bear"
    cal.loc[~cal["warmup_ok"], "regime"] = "warmup"

    if start_date is not None:
        cal = cal[cal["date"] >= pd.Timestamp(start_date)]
    if end_date is not None:
        cal = cal[cal["date"] <= pd.Timestamp(end_date)]

    return cal.reset_index(drop=True)


def build_regime_confusion_log(regime_calendar: pd.DataFrame) -> pd.DataFrame:
    """Return low-confidence days from the regime calendar."""

    cols = [
        "date",
        "regime",
        "close_vs_sma20",
        "ret_5d",
        "realized_vol_21d",
        "warmup_ok",
        "low_confidence",
    ]
    return regime_calendar.loc[regime_calendar["low_confidence"], cols].reset_index(drop=True)


def build_yearly_regime_summary(regime_calendar: pd.DataFrame) -> pd.DataFrame:
    """Summarize regime counts by year for quick sanity checks."""

    cal = regime_calendar[regime_calendar["warmup_ok"]].copy()
    if cal.empty:
        return pd.DataFrame(columns=["year", "bull", "bear", "sideways", "total"])

    cal["year"] = pd.to_datetime(cal["date"]).dt.year.astype(str)
    summary = (
        cal.groupby(["year", "regime"])
        .size()
        .unstack(fill_value=0)
        .reset_index()
    )
    for regime in ("bull", "bear", "sideways"):
        if regime not in summary.columns:
            summary[regime] = 0
    summary["total"] = summary[["bull", "bear", "sideways"]].sum(axis=1)
    return summary[["year", "bull", "bear", "sideways", "total"]]


def apply_bull_hh_hl_vwap_gate(
    trades: list[TradeResult],
    df: pd.DataFrame,
    session: SessionConfig,
) -> list[TradeResult]:
    """Apply the existing 30m HH/HL + VWAP gate as a bull-family subvariant."""

    if not trades:
        return []

    ts = df.index
    masks = compute_session_masks(ts, session)
    new_day, session_day_id = compute_session_days(ts, session)
    vwap = compute_session_vwap(
        df["high"].values.astype(np.float64),
        df["low"].values.astype(np.float64),
        df["close"].values.astype(np.float64),
        df["volume"].values.astype(np.float64),
        session_day_id,
    )
    daily_atr = compute_daily_atr(df, length=12)
    orb_high, orb_low, orb_ready = compute_orb_levels(df, masks["in_orb"], masks["in_rth"], new_day)
    sig = compute_all_15m_signals(df, session, vwap, daily_atr, orb_high, orb_low, orb_ready, session_day_id)

    kept: list[TradeResult] = []
    for t in trades:
        s = t.signal_bar
        if s < 0 or s >= len(df):
            continue
        close_val = float(sig["close"][s])
        vwap_val = float(sig["vwap"][s])
        if np.isnan(vwap_val):
            continue

        if t.direction == 1:
            keep = bool(sig["hh_hl_2_bull"][s]) and close_val > vwap_val
        else:
            keep = bool(sig["hh_hl_2_bear"][s]) and close_val < vwap_val

        if keep:
            kept.append(t)

    return kept


def evaluate_specialist(
    specialist_name: str,
    target_regime: str,
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    holdout_start: str = DEFAULT_HOLDOUT_START,
) -> dict:
    """Produce the full/in/out/holdout specialist readout and round-1 pass flags."""

    full_filled = _filled_trades(trades)
    in_regime = filter_trades_by_regime(trades, regime_calendar, include={target_regime})
    out_regime = filter_trades_by_regime(trades, regime_calendar, exclude={target_regime, "warmup"})
    holdout = _filter_by_start(trades, holdout_start)
    holdout_in = filter_trades_by_regime(holdout, regime_calendar, include={target_regime})

    full_metrics = compute_metrics(trades)
    in_metrics = compute_metrics(in_regime)
    out_metrics = compute_metrics(out_regime)
    holdout_metrics = compute_metrics(holdout)
    holdout_in_metrics = compute_metrics(holdout_in)

    in_avg_r = float(in_metrics.get("avg_r", 0.0))
    out_avg_r = float(out_metrics.get("avg_r", 0.0))
    if out_metrics.get("total_trades", 0) == 0:
        specialization_ratio = float("inf") if in_avg_r > 0 else 0.0
    elif out_avg_r <= 0 and in_avg_r > 0:
        specialization_ratio = float("inf")
    else:
        specialization_ratio = in_avg_r / max(abs(out_avg_r), 1e-9)

    dominant_year_share = _dominant_year_share(in_metrics)
    passes = {
        "positive_in_regime_expectancy": in_avg_r > 0,
        "specialization_ratio_gte_1_5": specialization_ratio >= 1.5,
        "min_in_regime_trades": in_metrics.get("total_trades", 0) >= 75,
        "not_single_year_dominated": dominant_year_share <= 0.50,
    }

    mapped = _map_trade_dates_to_regimes(full_filled, regime_calendar)
    regime_counts = (
        pd.Series(mapped["trade_regime"])
        .value_counts(dropna=False)
        .to_dict()
        if not mapped.empty
        else {}
    )

    return {
        "specialist_name": specialist_name,
        "target_regime": target_regime,
        "full_history": _metrics_snapshot(full_metrics),
        "in_regime": _metrics_snapshot(in_metrics),
        "out_of_regime": _metrics_snapshot(out_metrics),
        "holdout_2025_2026": _metrics_snapshot(holdout_metrics),
        "holdout_in_regime": _metrics_snapshot(holdout_in_metrics),
        "specialization_ratio": _json_number(specialization_ratio),
        "dominant_year_share": round(dominant_year_share, 4),
        "passes_round1": passes,
        "survives_round1": all(passes.values()),
        "trade_regime_counts": {str(k): int(v) for k, v in regime_counts.items()},
    }


def filter_trades_by_regime(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
) -> list[TradeResult]:
    """Filter trades by daily regime label."""

    include = include or set()
    exclude = exclude or set()
    mapping = _regime_lookup(regime_calendar)
    filtered: list[TradeResult] = []

    for t in trades:
        regime = mapping.get(t.date)
        if regime is None:
            continue
        if include and regime not in include:
            continue
        if exclude and regime in exclude:
            continue
        filtered.append(t)

    return filtered


def simulate_account_attempts(
    specialist_name: str,
    trades: list[TradeResult],
    trading_dates: Sequence[str | date | pd.Timestamp],
    profile: PropFirmProfile,
    risk_per_r_usd: float,
) -> pd.DataFrame:
    """Replay one account attempt for each trading-date start."""

    filled = sorted(_filled_trades(trades), key=lambda t: (t.date, t.signal_bar, t.fill_bar))
    all_dates = _normalize_dates(trading_dates)
    if not all_dates:
        return pd.DataFrame(columns=list(asdict(AccountAttemptOutcome(
            specialist_name="",
            account_start="",
            outcome="",
            outcome_date="",
            days_to_outcome=0,
            trades_to_outcome=0,
            trading_days_to_outcome=0,
            final_r=0.0,
            peak_r=0.0,
            trough_r=0.0,
            net_payout=0.0,
            breach_reason="",
        )).keys()))

    trade_rows = pd.DataFrame(
        {
            "date": [pd.Timestamp(t.date).normalize() for t in filled],
            "r_multiple": [float(t.r_multiple) for t in filled],
        }
    )
    day_to_rs: dict[pd.Timestamp, list[float]] = {}
    if not trade_rows.empty:
        for day, group in trade_rows.groupby("date"):
            day_to_rs[pd.Timestamp(day)] = [float(v) for v in group["r_multiple"].tolist()]

    outcomes: list[AccountAttemptOutcome] = []
    for start_day in all_dates:
        start_ts = pd.Timestamp(start_day).normalize()
        cum_r = 0.0
        peak_r = 0.0
        trough_r = 0.0
        trades_taken = 0
        trading_days_taken = 0
        outcome = "open"
        breach_reason = ""
        outcome_day = start_ts

        for cur_day in all_dates:
            cur_ts = pd.Timestamp(cur_day).normalize()
            if cur_ts < start_ts:
                continue

            day_rs = day_to_rs.get(cur_ts, [])
            if day_rs:
                trading_days_taken += 1

            day_r = 0.0
            for r_mult in day_rs:
                day_r += r_mult
                cum_r += r_mult
                trades_taken += 1
                peak_r = max(peak_r, cum_r)
                trough_r = min(trough_r, cum_r)

            if day_rs and day_r <= profile.daily_loss_limit_r:
                outcome = "breach"
                breach_reason = "daily_loss_limit"
                outcome_day = cur_ts
                break

            if cum_r <= profile.breach_limit_r:
                outcome = "breach"
                breach_reason = "max_drawdown"
                outcome_day = cur_ts
                break

            if cum_r >= profile.payout_target_r and trading_days_taken >= profile.min_trading_days:
                outcome = "payout"
                outcome_day = cur_ts
                break

            outcome_day = cur_ts

        if outcome == "payout":
            gross = profile.payout_target_r * risk_per_r_usd * profile.payout_split
            net_payout = gross - profile.account_fee
        elif outcome == "breach":
            net_payout = -(profile.account_fee + profile.reset_fee)
        else:
            net_payout = -profile.account_fee

        outcomes.append(
            AccountAttemptOutcome(
                specialist_name=specialist_name,
                account_start=start_ts.strftime("%Y-%m-%d"),
                outcome=outcome,
                outcome_date=outcome_day.strftime("%Y-%m-%d"),
                days_to_outcome=(outcome_day.date() - start_ts.date()).days + 1,
                trades_to_outcome=trades_taken,
                trading_days_to_outcome=trading_days_taken,
                final_r=round(cum_r, 4),
                peak_r=round(peak_r, 4),
                trough_r=round(trough_r, 4),
                net_payout=round(net_payout, 2),
                breach_reason=breach_reason,
            )
        )

    return pd.DataFrame(asdict(row) for row in outcomes)


def build_prop_scorecard(
    outcomes: pd.DataFrame,
    profile: PropFirmProfile,
) -> dict:
    """Summarize account-attempt outcomes into a scorecard."""

    if outcomes.empty:
        return {
            "profile": asdict(profile),
            "total_attempts": 0,
            "pass_rate": 0.0,
            "first_payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "average_net_payout": 0.0,
            "average_resets_per_payout": 0.0,
            "average_days_to_payout": None,
            "average_trades_to_payout": None,
            "ev_per_attempt": 0.0,
            "ev_by_cohort": {str(n): 0.0 for n in profile.cohort_sizes},
            "worst_monthly_cluster_net": 0.0,
            "worst_monthly_cluster_breaches": 0,
            "bootstrap": {},
        }

    total = int(len(outcomes))
    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    resolved = len(payouts) + len(breaches)
    pass_rate = len(payouts) / resolved if resolved else 0.0
    first_payout_rate = len(payouts) / total if total else 0.0
    breach_rate = len(breaches) / total if total else 0.0
    open_rate = len(opens) / total if total else 0.0

    month_key = pd.to_datetime(outcomes["account_start"]).dt.strftime("%Y-%m")
    monthly_net = outcomes.groupby(month_key)["net_payout"].sum()
    monthly_breaches = outcomes.assign(_month=month_key).groupby("_month").apply(
        lambda g: int((g["outcome"] == "breach").sum())
    )

    bootstrap = block_bootstrap_outcomes(outcomes, block_size=profile.block_size_days, seed=42)

    ev_per_attempt = round(float(outcomes["net_payout"].mean()), 2)
    return {
        "profile": asdict(profile),
        "total_attempts": total,
        "pass_rate": round(pass_rate, 4),
        "first_payout_rate": round(first_payout_rate, 4),
        "breach_rate": round(breach_rate, 4),
        "open_rate": round(open_rate, 4),
        "average_net_payout": ev_per_attempt,
        "average_resets_per_payout": round(len(breaches) / len(payouts), 4) if len(payouts) else None,
        "average_days_to_payout": round(float(payouts["days_to_outcome"].mean()), 2) if not payouts.empty else None,
        "average_trades_to_payout": round(float(payouts["trades_to_outcome"].mean()), 2) if not payouts.empty else None,
        "ev_per_attempt": ev_per_attempt,
        "ev_by_cohort": {str(n): round(ev_per_attempt * n, 2) for n in profile.cohort_sizes},
        "worst_monthly_cluster_net": round(float(monthly_net.min()), 2) if not monthly_net.empty else 0.0,
        "worst_monthly_cluster_breaches": int(monthly_breaches.max()) if not monthly_breaches.empty else 0,
        "bootstrap": bootstrap,
    }


def block_bootstrap_outcomes(
    outcomes: pd.DataFrame,
    block_size: int = 20,
    n_sims: int = 250,
    seed: int = 42,
) -> dict:
    """Stress-test account outcomes with contiguous-block resampling."""

    if outcomes.empty:
        return {}

    ordered = outcomes.sort_values("account_start").reset_index(drop=True)
    block_size = max(1, min(block_size, len(ordered)))
    windows = [ordered.iloc[i:i + block_size].copy() for i in range(len(ordered) - block_size + 1)]
    if not windows:
        windows = [ordered.copy()]

    rng = np.random.default_rng(seed)
    evs: list[float] = []
    pass_rates: list[float] = []
    breach_rates: list[float] = []
    trough_samples: list[float] = []

    for _ in range(n_sims):
        sampled_parts: list[pd.DataFrame] = []
        while sum(len(part) for part in sampled_parts) < len(ordered):
            sampled_parts.append(windows[int(rng.integers(0, len(windows)))])
        sampled = pd.concat(sampled_parts, ignore_index=True).iloc[:len(ordered)].copy()
        payouts = int((sampled["outcome"] == "payout").sum())
        breaches = int((sampled["outcome"] == "breach").sum())
        resolved = payouts + breaches

        evs.append(float(sampled["net_payout"].mean()))
        pass_rates.append(payouts / resolved if resolved else 0.0)
        breach_rates.append(breaches / len(sampled) if len(sampled) else 0.0)
        trough_samples.extend(np.abs(sampled["trough_r"].astype(float)).tolist())

    return {
        "seed": seed,
        "n_sims": n_sims,
        "block_size": block_size,
        "ev_per_attempt_p5": round(float(np.percentile(evs, 5)), 2),
        "ev_per_attempt_p50": round(float(np.percentile(evs, 50)), 2),
        "ev_per_attempt_p95": round(float(np.percentile(evs, 95)), 2),
        "pass_rate_p5": round(float(np.percentile(pass_rates, 5)), 4),
        "pass_rate_p50": round(float(np.percentile(pass_rates, 50)), 4),
        "pass_rate_p95": round(float(np.percentile(pass_rates, 95)), 4),
        "breach_rate_p95": round(float(np.percentile(breach_rates, 95)), 4),
        "drawdown_p95_r": round(float(np.percentile(trough_samples, 95)), 4) if trough_samples else 0.0,
    }


def build_regime_strategy_mapping() -> pd.DataFrame:
    """Return the round-1 specialist mapping table."""

    rows = [
        {
            "specialist_name": "nq_ny_bull_long_r11",
            "target_regime": "bull",
            "strategy_family": "continuation_long",
            "notes": "Post-fix NQ NY long R11 Final baseline.",
        },
        {
            "specialist_name": "nq_ny_bull_long_r11_hh_hl_vwap",
            "target_regime": "bull",
            "strategy_family": "continuation_long_context_gated",
            "notes": "Bull subvariant using 30m HH/HL + VWAP context gate.",
        },
        {
            "specialist_name": "nq_ny_bear_short_v2",
            "target_regime": "bear",
            "strategy_family": "continuation_short",
            "notes": "NQ NY short v2 baseline with Monday exclusion.",
        },
        {
            "specialist_name": "nq_ny_sideways_vwap",
            "target_regime": "sideways",
            "strategy_family": "vwap_reversion",
            "notes": "Bounded sweep winner from NY VWAP reversion.",
        },
    ]
    return pd.DataFrame(rows)


def trading_dates_from_calendar(regime_calendar: pd.DataFrame) -> list[str]:
    """Return non-warmup trading dates as YYYY-MM-DD strings."""

    cal = regime_calendar[regime_calendar["regime"] != "warmup"].copy()
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in cal["date"].tolist()]


def _filled_trades(trades: Iterable[TradeResult]) -> list[TradeResult]:
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def _filter_by_start(trades: list[TradeResult], start_date: str) -> list[TradeResult]:
    return [t for t in trades if t.date >= start_date]


def _regime_lookup(regime_calendar: pd.DataFrame) -> dict[str, str]:
    cal = regime_calendar.copy()
    cal["date_str"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    return dict(zip(cal["date_str"], cal["regime"]))


def _map_trade_dates_to_regimes(trades: list[TradeResult], regime_calendar: pd.DataFrame) -> pd.DataFrame:
    if not trades:
        return pd.DataFrame(columns=["date", "trade_regime"])
    mapping = _regime_lookup(regime_calendar)
    return pd.DataFrame(
        {
            "date": [t.date for t in trades],
            "trade_regime": [mapping.get(t.date) for t in trades],
        }
    )


def _metrics_snapshot(metrics: dict) -> dict:
    keys = [
        "total_signals",
        "total_trades",
        "win_rate",
        "profit_factor",
        "avg_r",
        "total_r",
        "max_drawdown_r",
        "sharpe_ratio",
        "calmar_ratio",
        "max_consecutive_losses",
        "r_by_year",
    ]
    snap = {key: metrics.get(key) for key in keys}
    for key in ("win_rate", "profit_factor", "avg_r", "total_r", "max_drawdown_r", "sharpe_ratio", "calmar_ratio"):
        if snap.get(key) is not None:
            snap[key] = round(float(snap[key]), 4)
    if snap.get("r_by_year"):
        snap["r_by_year"] = {str(k): round(float(v), 4) for k, v in snap["r_by_year"].items()}
    return snap


def _dominant_year_share(in_metrics: dict) -> float:
    total_r = float(in_metrics.get("total_r", 0.0))
    yearly = in_metrics.get("r_by_year", {}) or {}
    if total_r <= 0 or not yearly:
        return 1.0 if total_r <= 0 else 0.0
    max_year = max(float(v) for v in yearly.values())
    return max_year / total_r if total_r else 0.0


def _json_number(value: float) -> float | str:
    if np.isinf(value):
        return "inf"
    return round(float(value), 4)


def _normalize_dates(values: Sequence[str | date | pd.Timestamp]) -> list[pd.Timestamp]:
    normalized = sorted({pd.Timestamp(v).normalize() for v in values})
    return normalized
