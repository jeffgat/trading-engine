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
class FundedFirstPayoutProfile:
    """Funded-account model for optimizing time to the first withdrawable payout."""

    challenge_fee: float = 150.0
    starting_balance_usd: float = 50_000.0
    trailing_drawdown_usd: float = 2_000.0
    max_trailing_breach_usd: float = 50_000.0
    first_payout_floor_usd: float = 52_000.0
    risk_pre_payout_usd: float = 500.0
    risk_post_payout_usd: float = 250.0


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


@dataclass(frozen=True)
class FundedFirstPayoutOutcome:
    """Outcome of one funded account start under the trailing EOD drawdown rules."""

    specialist_name: str
    account_start: str
    outcome: str
    outcome_date: str
    calendar_days_to_outcome: int
    trades_to_outcome: int
    ending_balance_usd: float
    breach_balance_usd: float
    highest_eod_balance_usd: float
    first_payout_amount_usd: float
    net_payout_after_fee_usd: float


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


def filter_trades_by_low_confidence(
    trades: list[TradeResult],
    regime_calendar: pd.DataFrame,
    include_low_confidence: bool = True,
) -> list[TradeResult]:
    """Optionally remove trades that occur on low-confidence regime days."""

    if include_low_confidence:
        return list(trades)

    cal = regime_calendar.copy()
    cal["date_str"] = pd.to_datetime(cal["date"]).dt.strftime("%Y-%m-%d")
    low_conf_lookup = dict(zip(cal["date_str"], cal["low_confidence"].astype(bool)))
    return [t for t in trades if not low_conf_lookup.get(t.date, False)]


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


def build_structure_vwap_signals(
    df: pd.DataFrame,
    session: SessionConfig,
    atr_length: int,
) -> dict[str, np.ndarray]:
    """Build reusable 15m structure + VWAP signal arrays on the 5m index."""

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
    daily_atr = compute_daily_atr(df, length=atr_length)
    orb_high, orb_low, orb_ready = compute_orb_levels(df, masks["in_orb"], masks["in_rth"], new_day)
    return compute_all_15m_signals(
        df,
        session,
        vwap,
        daily_atr,
        orb_high,
        orb_low,
        orb_ready,
        session_day_id,
    )


def trade_passes_structure_vwap_gate(
    gate_name: str,
    trade: TradeResult,
    signals: dict[str, np.ndarray],
) -> bool:
    """Return whether one filled trade passes a structure + VWAP context gate."""

    close = signals["close"]
    vwap = signals["vwap"]
    atr = signals["daily_atr"]
    n = len(close)
    s = trade.signal_bar
    if s < 0 or s >= n:
        return False

    c = float(close[s])
    v = float(vwap[s])
    a = float(atr[s])
    if np.isnan(v) or np.isnan(a) or a <= 0:
        return False

    d = int(trade.direction)
    dist = (c - v) * d
    dist_pct = dist / a
    return _eval_structure_vwap_gate(gate_name, s, d, c, v, dist_pct, signals)


def apply_structure_vwap_gate(
    trades: list[TradeResult],
    signals: dict[str, np.ndarray],
    gate_name: str,
) -> list[TradeResult]:
    """Filter filled trades using a named 15m structure + VWAP gate."""

    kept: list[TradeResult] = []
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        if trade_passes_structure_vwap_gate(gate_name, trade, signals):
            kept.append(trade)
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


def simulate_funded_first_payouts(
    specialist_name: str,
    trades: list[TradeResult],
    trading_dates: Sequence[str | date | pd.Timestamp],
    profile: FundedFirstPayoutProfile,
) -> pd.DataFrame:
    """Replay starts for a funded account with trailing EOD drawdown until first payout."""

    filled = sorted(
        _filled_trades(trades),
        key=lambda t: (t.date, t.fill_time or "", t.fill_bar, t.exit_time or ""),
    )
    all_dates = _normalize_dates(trading_dates)
    if not all_dates:
        return pd.DataFrame(columns=list(asdict(FundedFirstPayoutOutcome(
            specialist_name="",
            account_start="",
            outcome="",
            outcome_date="",
            calendar_days_to_outcome=0,
            trades_to_outcome=0,
            ending_balance_usd=0.0,
            breach_balance_usd=0.0,
            highest_eod_balance_usd=0.0,
            first_payout_amount_usd=0.0,
            net_payout_after_fee_usd=0.0,
        )).keys()))

    day_to_rs: dict[pd.Timestamp, list[float]] = {}
    if filled:
        trade_rows = pd.DataFrame(
            {
                "date": [pd.Timestamp(t.date).normalize() for t in filled],
                "r_multiple": [float(t.r_multiple) for t in filled],
            }
        )
        for day, group in trade_rows.groupby("date"):
            day_to_rs[pd.Timestamp(day)] = [float(v) for v in group["r_multiple"].tolist()]

    outcomes: list[FundedFirstPayoutOutcome] = []
    starting_breach = min(
        profile.starting_balance_usd - profile.trailing_drawdown_usd,
        profile.max_trailing_breach_usd,
    )

    for start_day in all_dates:
        start_ts = pd.Timestamp(start_day).normalize()
        balance_usd = float(profile.starting_balance_usd)
        highest_eod_balance_usd = float(profile.starting_balance_usd)
        breach_balance_usd = float(starting_breach)
        risk_usd = float(profile.risk_pre_payout_usd)
        trades_taken = 0
        outcome = "open"
        outcome_day = start_ts
        first_payout_amount_usd = 0.0

        for cur_day in all_dates:
            cur_ts = pd.Timestamp(cur_day).normalize()
            if cur_ts < start_ts:
                continue

            for r_multiple in day_to_rs.get(cur_ts, []):
                balance_usd += r_multiple * risk_usd
                trades_taken += 1
                if balance_usd <= breach_balance_usd:
                    outcome = "breach"
                    outcome_day = cur_ts
                    break

            if outcome == "breach":
                break

            if balance_usd >= profile.first_payout_floor_usd:
                outcome = "payout"
                outcome_day = cur_ts
                first_payout_amount_usd = max(0.0, balance_usd - profile.first_payout_floor_usd)
                risk_usd = float(profile.risk_post_payout_usd)
                break

            highest_eod_balance_usd = max(highest_eod_balance_usd, balance_usd)
            breach_balance_usd = min(
                highest_eod_balance_usd - profile.trailing_drawdown_usd,
                profile.max_trailing_breach_usd,
            )
            outcome_day = cur_ts

        if outcome == "payout":
            net_after_fee = first_payout_amount_usd - profile.challenge_fee
        else:
            net_after_fee = -profile.challenge_fee

        outcomes.append(
            FundedFirstPayoutOutcome(
                specialist_name=specialist_name,
                account_start=start_ts.strftime("%Y-%m-%d"),
                outcome=outcome,
                outcome_date=outcome_day.strftime("%Y-%m-%d"),
                calendar_days_to_outcome=(outcome_day.date() - start_ts.date()).days + 1,
                trades_to_outcome=trades_taken,
                ending_balance_usd=round(balance_usd, 2),
                breach_balance_usd=round(breach_balance_usd, 2),
                highest_eod_balance_usd=round(highest_eod_balance_usd, 2),
                first_payout_amount_usd=round(first_payout_amount_usd, 2),
                net_payout_after_fee_usd=round(net_after_fee, 2),
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


def build_funded_first_payout_scorecard(
    outcomes: pd.DataFrame,
    profile: FundedFirstPayoutProfile,
) -> dict:
    """Summarize first-payout funded-account outcomes."""

    if outcomes.empty:
        return {
            "profile": asdict(profile),
            "total_starts": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "average_days_to_payout": None,
            "median_days_to_payout": None,
            "average_trades_to_payout": None,
            "average_first_payout_amount_usd": None,
            "average_net_after_fee_usd": 0.0,
            "ev_per_start_usd": 0.0,
        }

    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    opens = outcomes[outcomes["outcome"] == "open"].copy()
    total = int(len(outcomes))

    return {
        "profile": asdict(profile),
        "total_starts": total,
        "payout_rate": round(len(payouts) / total, 4) if total else 0.0,
        "breach_rate": round(len(breaches) / total, 4) if total else 0.0,
        "open_rate": round(len(opens) / total, 4) if total else 0.0,
        "average_days_to_payout": (
            round(float(payouts["calendar_days_to_outcome"].mean()), 2)
            if not payouts.empty else None
        ),
        "median_days_to_payout": (
            round(float(payouts["calendar_days_to_outcome"].median()), 2)
            if not payouts.empty else None
        ),
        "average_trades_to_payout": (
            round(float(payouts["trades_to_outcome"].mean()), 2)
            if not payouts.empty else None
        ),
        "average_first_payout_amount_usd": (
            round(float(payouts["first_payout_amount_usd"].mean()), 2)
            if not payouts.empty else None
        ),
        "average_net_after_fee_usd": (
            round(float(payouts["net_payout_after_fee_usd"].mean()), 2)
            if not payouts.empty else None
        ),
        "ev_per_start_usd": round(float(outcomes["net_payout_after_fee_usd"].mean()), 2),
    }


def build_funded_first_payout_forecast(
    outcomes: pd.DataFrame,
    horizons_days: Sequence[int] = (10, 15, 20, 30, 45, 60, 90),
) -> dict:
    """Summarize the timing distribution of payout, breach, and resolution."""

    horizons = tuple(sorted({int(day) for day in horizons_days if int(day) > 0}))
    if outcomes.empty:
        return {
            "total_starts": 0,
            "horizons_days": list(horizons),
            "payout_days_quantiles": {},
            "breach_days_quantiles": {},
            "resolution_days_quantiles": {},
            "timeline": [],
        }

    payouts = outcomes[outcomes["outcome"] == "payout"].copy()
    breaches = outcomes[outcomes["outcome"] == "breach"].copy()
    resolved = outcomes[outcomes["outcome"].isin(["payout", "breach"])].copy()
    total = int(len(outcomes))

    def _quantiles(frame: pd.DataFrame) -> dict[str, float | None]:
        if frame.empty:
            return {}
        values = frame["calendar_days_to_outcome"].astype(float)
        return {
            "p10": round(float(np.percentile(values, 10)), 2),
            "p25": round(float(np.percentile(values, 25)), 2),
            "p50": round(float(np.percentile(values, 50)), 2),
            "p75": round(float(np.percentile(values, 75)), 2),
            "p90": round(float(np.percentile(values, 90)), 2),
        }

    timeline = []
    for horizon in horizons:
        resolved_by_h = resolved[resolved["calendar_days_to_outcome"] <= horizon]
        payouts_by_h = payouts[payouts["calendar_days_to_outcome"] <= horizon]
        breaches_by_h = breaches[breaches["calendar_days_to_outcome"] <= horizon]
        resolved_count = int(len(resolved_by_h))
        timeline.append(
            {
                "horizon_days": horizon,
                "payout_rate_by_horizon": round(len(payouts_by_h) / total, 4),
                "breach_rate_by_horizon": round(len(breaches_by_h) / total, 4),
                "resolved_rate_by_horizon": round(resolved_count / total, 4),
                "payout_share_of_resolved_by_horizon": (
                    round(len(payouts_by_h) / resolved_count, 4) if resolved_count else None
                ),
                "open_rate_after_horizon": round(1.0 - (resolved_count / total), 4),
            }
        )

    return {
        "total_starts": total,
        "horizons_days": list(horizons),
        "payout_days_quantiles": _quantiles(payouts),
        "breach_days_quantiles": _quantiles(breaches),
        "resolution_days_quantiles": _quantiles(resolved),
        "timeline": timeline,
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


def trading_dates_from_calendar(
    regime_calendar: pd.DataFrame,
    include_low_confidence: bool = True,
) -> list[str]:
    """Return eligible trading dates as YYYY-MM-DD strings."""

    cal = regime_calendar[regime_calendar["regime"] != "warmup"].copy()
    if not include_low_confidence:
        cal = cal[~cal["low_confidence"]].copy()
    return [pd.Timestamp(d).strftime("%Y-%m-%d") for d in cal["date"].tolist()]


def evaluate_bull_market_windows(
    specialist_name: str,
    trades: list[TradeResult],
    trading_dates: Sequence[str | date | pd.Timestamp],
    funded_profile: FundedFirstPayoutProfile,
    *,
    diagnostic_start: str = "2021-01-01",
    diagnostic_end: str = "2021-12-31",
    rejection_start: str = "2022-01-01",
    rejection_end: str = "2023-12-31",
    acceptance_start: str = "2024-01-01",
    holdout_start: str = DEFAULT_HOLDOUT_START,
    min_acceptance_trades: int = 40,
) -> dict:
    """Score a bull specialist against fixed calendar windows.

    2021 is logged for diagnostics only and excluded from pass/fail.
    """

    diagnostic_trades = _filter_between(trades, diagnostic_start, diagnostic_end)
    rejection_trades = _filter_between(trades, rejection_start, rejection_end)
    acceptance_trades = _filter_between(trades, acceptance_start, None)
    holdout_trades = _filter_between(trades, holdout_start, None)

    acceptance_dates = [d for d in _normalize_dates(trading_dates) if pd.Timestamp(d) >= pd.Timestamp(acceptance_start)]
    holdout_dates = [d for d in _normalize_dates(trading_dates) if pd.Timestamp(d) >= pd.Timestamp(holdout_start)]

    acceptance_metrics = compute_metrics(acceptance_trades)
    rejection_metrics = compute_metrics(rejection_trades)
    diagnostic_metrics = compute_metrics(diagnostic_trades)
    holdout_outcomes = simulate_funded_first_payouts(
        specialist_name=specialist_name,
        trades=holdout_trades,
        trading_dates=holdout_dates,
        profile=funded_profile,
    )
    holdout_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, funded_profile)

    acceptance_net_r = float(acceptance_metrics.get("total_r", 0.0))
    rejection_net_r = float(rejection_metrics.get("total_r", 0.0))
    rejection_share = (
        rejection_net_r / acceptance_net_r
        if acceptance_net_r > 0.0 and rejection_net_r > 0.0
        else 0.0
    )
    separation = acceptance_net_r - max(rejection_net_r, 0.0)

    passes = {
        "acceptance_positive_net_r": acceptance_net_r > 0.0,
        "holdout_payout_gt_breach": float(holdout_scorecard.get("payout_rate") or 0.0)
        > float(holdout_scorecard.get("breach_rate") or 0.0),
        "rejection_window_capped": rejection_net_r <= 0.0 or rejection_share <= 0.25,
        "acceptance_min_trades": int(acceptance_metrics.get("total_trades", 0)) >= min_acceptance_trades,
    }

    return {
        "specialist_name": specialist_name,
        "diagnostic_2021": _metrics_snapshot(diagnostic_metrics),
        "rejection_2022_2023": _metrics_snapshot(rejection_metrics),
        "acceptance_2024_latest": _metrics_snapshot(acceptance_metrics),
        "holdout_2025_latest": holdout_scorecard,
        "acceptance_net_r": round(acceptance_net_r, 4),
        "rejection_net_r": round(rejection_net_r, 4),
        "rejection_share_of_acceptance": round(rejection_share, 4),
        "acceptance_rejection_separation": round(separation, 4),
        "passes_bull_v1": passes,
        "survives_bull_v1": all(passes.values()),
        "acceptance_trading_dates": len(acceptance_dates),
        "holdout_trading_dates": len(holdout_dates),
    }


def bull_market_rank_key(record: dict) -> tuple:
    """Stable ranking key for bull-specialist V1 candidates."""

    holdout = record["holdout_2025_latest"]
    avg_days = holdout.get("average_days_to_payout")
    avg_days_key = -float(avg_days) if avg_days is not None else float("-inf")
    return (
        bool(record["survives_bull_v1"]),
        float(holdout.get("payout_rate") or 0.0) - float(holdout.get("breach_rate") or 0.0),
        float(record.get("acceptance_net_r") or 0.0),
        float(record.get("acceptance_rejection_separation") or 0.0),
        avg_days_key,
    )


def evaluate_bear_market_windows(
    specialist_name: str,
    trades: list[TradeResult],
    trading_dates: Sequence[str | date | pd.Timestamp],
    funded_profile: FundedFirstPayoutProfile,
    *,
    diagnostic_start: str = "2021-01-01",
    diagnostic_end: str = "2021-12-31",
    acceptance_start: str = "2022-01-01",
    acceptance_end: str = "2023-12-31",
    holdout_start: str = "2023-01-01",
    holdout_end: str = "2023-12-31",
    rejection_start: str = "2024-01-01",
    rejection_end: str | None = None,
    min_acceptance_trades: int = 40,
) -> dict:
    """Score a bear specialist against fixed calendar windows.

    2021 is diagnostic only. The acceptance era is the 2022-2023 bear market
    window, with 2023 used as a funded-account quality holdout inside that era.
    2024+ is treated as the rejection era.
    """

    diagnostic_trades = _filter_between(trades, diagnostic_start, diagnostic_end)
    acceptance_trades = _filter_between(trades, acceptance_start, acceptance_end)
    holdout_trades = _filter_between(trades, holdout_start, holdout_end)
    rejection_trades = _filter_between(trades, rejection_start, rejection_end)

    normalized_dates = _normalize_dates(trading_dates)
    acceptance_dates = [
        d for d in normalized_dates
        if pd.Timestamp(acceptance_start) <= pd.Timestamp(d) <= pd.Timestamp(acceptance_end)
    ]
    holdout_dates = [
        d for d in normalized_dates
        if pd.Timestamp(holdout_start) <= pd.Timestamp(d) <= pd.Timestamp(holdout_end)
    ]
    rejection_dates = [
        d for d in normalized_dates
        if pd.Timestamp(d) >= pd.Timestamp(rejection_start)
        and (rejection_end is None or pd.Timestamp(d) <= pd.Timestamp(rejection_end))
    ]

    diagnostic_metrics = compute_metrics(diagnostic_trades)
    acceptance_metrics = compute_metrics(acceptance_trades)
    rejection_metrics = compute_metrics(rejection_trades)
    holdout_outcomes = simulate_funded_first_payouts(
        specialist_name=specialist_name,
        trades=holdout_trades,
        trading_dates=holdout_dates,
        profile=funded_profile,
    )
    holdout_scorecard = build_funded_first_payout_scorecard(holdout_outcomes, funded_profile)

    acceptance_net_r = float(acceptance_metrics.get("total_r", 0.0))
    rejection_net_r = float(rejection_metrics.get("total_r", 0.0))
    rejection_share = (
        rejection_net_r / acceptance_net_r
        if acceptance_net_r > 0.0 and rejection_net_r > 0.0
        else 0.0
    )
    separation = acceptance_net_r - max(rejection_net_r, 0.0)

    passes = {
        "acceptance_positive_net_r": acceptance_net_r > 0.0,
        "holdout_payout_gt_breach": float(holdout_scorecard.get("payout_rate") or 0.0)
        > float(holdout_scorecard.get("breach_rate") or 0.0),
        "rejection_window_capped": rejection_net_r <= 0.0 or rejection_share <= 0.25,
        "acceptance_min_trades": int(acceptance_metrics.get("total_trades", 0)) >= min_acceptance_trades,
    }

    return {
        "specialist_name": specialist_name,
        "diagnostic_2021": _metrics_snapshot(diagnostic_metrics),
        "acceptance_2022_2023": _metrics_snapshot(acceptance_metrics),
        "holdout_2023": holdout_scorecard,
        "rejection_2024_latest": _metrics_snapshot(rejection_metrics),
        "acceptance_net_r": round(acceptance_net_r, 4),
        "rejection_net_r": round(rejection_net_r, 4),
        "rejection_share_of_acceptance": round(rejection_share, 4),
        "acceptance_rejection_separation": round(separation, 4),
        "passes_bear_v1": passes,
        "survives_bear_v1": all(passes.values()),
        "acceptance_trading_dates": len(acceptance_dates),
        "holdout_trading_dates": len(holdout_dates),
        "rejection_trading_dates": len(rejection_dates),
    }


def bear_market_rank_key(record: dict) -> tuple:
    """Stable ranking key for bear-specialist V1 candidates."""

    holdout = record["holdout_2023"]
    avg_days = holdout.get("average_days_to_payout")
    avg_days_key = -float(avg_days) if avg_days is not None else float("-inf")
    return (
        bool(record["survives_bear_v1"]),
        float(holdout.get("payout_rate") or 0.0) - float(holdout.get("breach_rate") or 0.0),
        float(record.get("acceptance_net_r") or 0.0),
        float(record.get("acceptance_rejection_separation") or 0.0),
        avg_days_key,
    )


def _eval_structure_vwap_gate(
    gate_name: str,
    signal_bar: int,
    direction: int,
    close_value: float,
    vwap_value: float,
    dist_pct: float,
    signals: dict[str, np.ndarray],
) -> bool:
    """Evaluate a named 15m structure + VWAP gate at one signal index."""

    s = signal_bar
    d = direction

    if gate_name == "hh_hl_2_vwap":
        if d == 1:
            return bool(signals["hh_hl_2_bull"][s]) and close_value > vwap_value
        return bool(signals["hh_hl_2_bear"][s]) and close_value < vwap_value

    if gate_name == "hh_hl_3_vwap":
        if d == 1:
            return bool(signals["hh_hl_3_bull"][s]) and close_value > vwap_value
        return bool(signals["hh_hl_3_bear"][s]) and close_value < vwap_value

    if gate_name == "any2of3_vwap_d5":
        if d == 1:
            return bool(signals["hh_hl_any2of3_bull"][s]) and dist_pct >= 0.05
        return bool(signals["hh_hl_any2of3_bear"][s]) and dist_pct >= 0.05

    if gate_name == "score_gte_2":
        if d == 1:
            return int(signals["bull_score"][s]) >= 2
        return int(signals["bear_score"][s]) >= 2

    if gate_name == "score_eq_3":
        if d == 1:
            return int(signals["bull_score"][s]) == 3
        return int(signals["bear_score"][s]) == 3

    if gate_name == "regime_2d_vwap":
        if d == 1:
            return bool(signals["regime_2d_bull"][s]) and close_value > vwap_value
        return bool(signals["regime_2d_bear"][s]) and close_value < vwap_value

    if gate_name == "regime_2of3_vwap":
        if d == 1:
            return bool(signals["regime_2of3_bull"][s]) and close_value > vwap_value
        return bool(signals["regime_2of3_bear"][s]) and close_value < vwap_value

    if gate_name == "pullback_holds_vwap":
        if d == 1:
            return (
                bool(signals["hh_hl_2_bull"][s])
                and close_value > vwap_value
                and bool(signals["holds_vwap_bull"][s])
            )
        return (
            bool(signals["hh_hl_2_bear"][s])
            and close_value < vwap_value
            and bool(signals["holds_vwap_bear"][s])
        )

    if gate_name == "pullback_holds_vwap_orb":
        if d == 1:
            return (
                bool(signals["hh_hl_2_bull"][s])
                and close_value > vwap_value
                and bool(signals["holds_vwap_orb_bull"][s])
            )
        return (
            bool(signals["hh_hl_2_bear"][s])
            and close_value < vwap_value
            and bool(signals["holds_vwap_orb_bear"][s])
        )

    raise ValueError(f"Unknown structure/VWAP gate: {gate_name}")


def _filled_trades(trades: Iterable[TradeResult]) -> list[TradeResult]:
    return [t for t in trades if t.exit_type != EXIT_NO_FILL]


def _filter_by_start(trades: list[TradeResult], start_date: str) -> list[TradeResult]:
    return [t for t in trades if t.date >= start_date]


def _filter_between(
    trades: list[TradeResult],
    start_date: str | None,
    end_date: str | None,
) -> list[TradeResult]:
    filtered = trades
    if start_date is not None:
        filtered = [t for t in filtered if t.date >= start_date]
    if end_date is not None:
        filtered = [t for t in filtered if t.date <= end_date]
    return filtered


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
