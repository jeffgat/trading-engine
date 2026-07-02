"""Reusable prop-firm account lifecycle simulation helpers.

The helpers are intentionally strategy-agnostic. Pass filled trade objects or
dict rows with at least date/exit_time and pnl_usd fields.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PropFirmRiskProfile:
    """Dollar-denominated prop model with first payout then survival-to-bust."""

    trailing_drawdown_usd: float = 2_000.0
    pass_target_usd: float = 3_000.0
    first_payout_usd: float = 1_500.0
    floor_cap_delta_usd: float = 0.0
    challenge_fee_usd: float = 0.0
    account_start_spacing_days: int = 14


def make_account_starts(
    start: str | pd.Timestamp,
    end_exclusive: str | pd.Timestamp,
    spacing_days: int = 14,
) -> list[pd.Timestamp]:
    """Return normalized staggered account start dates."""

    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end_exclusive).normalize() - pd.Timedelta(days=1),
            freq=f"{int(spacing_days)}D",
        )
    ]


def _get(row: Any, key: str, default: Any = None) -> Any:
    if isinstance(row, dict):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_trade_rows(
    trades: Iterable[Any],
    *,
    no_fill_exit_types: set[Any] | None = None,
) -> list[dict[str, Any]]:
    """Normalize filled trades into sorted rows with day, exit_ts, and pnl_usd."""

    no_fill_exit_types = no_fill_exit_types or {0, "0", "no_fill", "EXIT_NO_FILL"}
    rows: list[dict[str, Any]] = []
    for trade in trades:
        exit_type = _get(trade, "exit_type")
        fill_bar = _get(trade, "fill_bar", 0)
        if exit_type in no_fill_exit_types or fill_bar == -1:
            continue

        raw_ts = _get(trade, "exit_ts") or _get(trade, "exit_time") or _get(trade, "date")
        if raw_ts is None:
            raise ValueError("Trade row is missing exit_ts, exit_time, and date")
        pnl_usd = _get(trade, "pnl_usd")
        if pnl_usd is None:
            raise ValueError("Trade row is missing pnl_usd")

        ts = pd.Timestamp(raw_ts)
        rows.append(
            {
                "day": ts.normalize(),
                "exit_ts": ts,
                "pnl_usd": float(pnl_usd),
                "r_multiple": float(_get(trade, "r_multiple", 0.0) or 0.0),
            }
        )

    rows.sort(key=lambda row: (row["exit_ts"], row["day"]))
    return rows


def _ratchet_floor_delta(
    highest_eod_delta_usd: float,
    current_floor_delta_usd: float,
    profile: PropFirmRiskProfile,
) -> float:
    candidate = highest_eod_delta_usd - profile.trailing_drawdown_usd
    capped = min(candidate, profile.floor_cap_delta_usd)
    return max(current_floor_delta_usd, capped)


def simulate_prop_firm_risk(
    *,
    variant_id: str,
    trades: Iterable[Any],
    account_starts: Sequence[str | pd.Timestamp],
    profile: PropFirmRiskProfile | None = None,
    end_exclusive: str | pd.Timestamp | None = None,
    no_fill_exit_types: set[Any] | None = None,
) -> pd.DataFrame:
    """Replay staggered account starts through first payout and survival-to-bust.

    Outcomes are one row per account start. `net_realized_usd` counts completed
    withdrawals minus challenge fees. `marked_terminal_usd` additionally credits
    positive open account equity at data end.
    """

    profile = profile or PropFirmRiskProfile()
    starts = [pd.Timestamp(day).normalize() for day in account_starts]
    rows = _as_trade_rows(trades, no_fill_exit_types=no_fill_exit_types)
    columns = [
        "variant_id",
        "account_start",
        "outcome",
        "first_payout_hit",
        "first_payout_date",
        "outcome_date",
        "days_to_first_payout",
        "days_to_outcome",
        "trades_to_first_payout",
        "trades_to_outcome",
        "payout_usd",
        "net_realized_usd",
        "marked_terminal_usd",
        "ending_balance_delta_usd",
        "floor_delta_usd",
        "highest_eod_delta_usd",
        "min_cushion_usd",
    ]
    if not starts:
        return pd.DataFrame(columns=columns)

    if end_exclusive is not None:
        end_day = pd.Timestamp(end_exclusive).normalize() - pd.Timedelta(days=1)
    elif rows:
        end_day = max(row["day"] for row in rows)
    else:
        end_day = max(starts)

    outcomes: list[dict[str, Any]] = []
    for start_day in starts:
        balance_delta = 0.0
        floor_delta = -float(profile.trailing_drawdown_usd)
        highest_eod_delta = 0.0
        min_cushion = float(profile.trailing_drawdown_usd)
        current_day: pd.Timestamp | None = None
        outcome = "open_pre_payout"
        outcome_day = end_day
        first_payout_hit = False
        first_payout_day: pd.Timestamp | None = None
        days_to_first_payout: int | None = None
        trades_to_first_payout: int | None = None
        trades_taken = 0
        payout_usd = 0.0
        future_seen = False

        for row in rows:
            trade_day = pd.Timestamp(row["day"]).normalize()
            if trade_day < start_day:
                continue
            future_seen = True

            if current_day is not None and trade_day != current_day:
                highest_eod_delta = max(highest_eod_delta, balance_delta)
                floor_delta = _ratchet_floor_delta(highest_eod_delta, floor_delta, profile)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                if balance_delta <= floor_delta:
                    outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                    outcome_day = current_day
                    break

            current_day = trade_day
            balance_delta += float(row["pnl_usd"])
            trades_taken += 1
            min_cushion = min(min_cushion, balance_delta - floor_delta)

            if balance_delta <= floor_delta:
                outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                outcome_day = trade_day
                break

            if not first_payout_hit and balance_delta >= profile.pass_target_usd:
                first_payout_hit = True
                first_payout_day = trade_day
                days_to_first_payout = int((trade_day.date() - start_day.date()).days) + 1
                trades_to_first_payout = trades_taken
                payout_usd += profile.first_payout_usd
                balance_delta -= profile.first_payout_usd
                floor_delta = max(floor_delta, profile.floor_cap_delta_usd)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                outcome = "open_post_payout"

            outcome_day = trade_day
        else:
            if current_day is not None:
                highest_eod_delta = max(highest_eod_delta, balance_delta)
                floor_delta = _ratchet_floor_delta(highest_eod_delta, floor_delta, profile)
                min_cushion = min(min_cushion, balance_delta - floor_delta)
                if balance_delta <= floor_delta:
                    outcome = "bust_post_payout" if first_payout_hit else "bust_pre_payout"
                    outcome_day = current_day
                else:
                    outcome = "open_post_payout" if first_payout_hit else "open_pre_payout"
                    outcome_day = current_day
            elif not future_seen:
                outcome = "open_pre_payout"
                outcome_day = end_day

        net_realized = payout_usd - profile.challenge_fee_usd
        marked_terminal = net_realized + max(0.0, balance_delta)
        outcomes.append(
            {
                "variant_id": variant_id,
                "account_start": start_day.date().isoformat(),
                "outcome": outcome,
                "first_payout_hit": bool(first_payout_hit),
                "first_payout_date": first_payout_day.date().isoformat() if first_payout_day is not None else "",
                "outcome_date": outcome_day.date().isoformat(),
                "days_to_first_payout": days_to_first_payout,
                "days_to_outcome": int((outcome_day.date() - start_day.date()).days) + 1,
                "trades_to_first_payout": trades_to_first_payout,
                "trades_to_outcome": trades_taken,
                "payout_usd": round(payout_usd, 2),
                "net_realized_usd": round(net_realized, 2),
                "marked_terminal_usd": round(marked_terminal, 2),
                "ending_balance_delta_usd": round(balance_delta, 2),
                "floor_delta_usd": round(floor_delta, 2),
                "highest_eod_delta_usd": round(highest_eod_delta, 2),
                "min_cushion_usd": round(min_cushion, 2),
            }
        )

    return pd.DataFrame(outcomes, columns=columns)


def score_prop_firm_outcomes(outcomes: pd.DataFrame) -> dict[str, Any]:
    """Summarize account lifecycle outcomes into prop-risk metrics."""

    if outcomes.empty:
        return {
            "total_starts": 0,
            "first_payout_rate": 0.0,
            "bust_rate": 0.0,
            "pre_payout_bust_rate": 0.0,
            "post_payout_bust_rate": 0.0,
            "open_rate": 0.0,
            "open_post_payout_rate": 0.0,
            "ev_per_start_usd": 0.0,
            "marked_ev_per_start_usd": 0.0,
            "avg_days_to_first_payout": None,
            "median_days_to_first_payout": None,
            "avg_trades_to_first_payout": None,
            "median_min_cushion_usd": None,
            "worst_min_cushion_usd": None,
        }

    total = int(len(outcomes))
    first = outcomes[outcomes["first_payout_hit"]].copy()
    bust_pre = outcomes[outcomes["outcome"] == "bust_pre_payout"].copy()
    bust_post = outcomes[outcomes["outcome"] == "bust_post_payout"].copy()
    opens = outcomes[outcomes["outcome"].astype(str).str.startswith("open")].copy()
    open_post = outcomes[outcomes["outcome"] == "open_post_payout"].copy()

    def pct(count: int) -> float:
        return round(float(count) / float(total), 4) if total else 0.0

    return {
        "total_starts": total,
        "first_payout_rate": pct(len(first)),
        "bust_rate": pct(len(bust_pre) + len(bust_post)),
        "pre_payout_bust_rate": pct(len(bust_pre)),
        "post_payout_bust_rate": pct(len(bust_post)),
        "open_rate": pct(len(opens)),
        "open_post_payout_rate": pct(len(open_post)),
        "ev_per_start_usd": round(float(outcomes["net_realized_usd"].mean()), 2),
        "marked_ev_per_start_usd": round(float(outcomes["marked_terminal_usd"].mean()), 2),
        "avg_days_to_first_payout": (
            round(float(first["days_to_first_payout"].dropna().mean()), 2)
            if not first.empty else None
        ),
        "median_days_to_first_payout": (
            round(float(first["days_to_first_payout"].dropna().median()), 2)
            if not first.empty else None
        ),
        "avg_trades_to_first_payout": (
            round(float(first["trades_to_first_payout"].dropna().mean()), 2)
            if not first.empty else None
        ),
        "median_min_cushion_usd": round(float(outcomes["min_cushion_usd"].median()), 2),
        "worst_min_cushion_usd": round(float(outcomes["min_cushion_usd"].min()), 2),
    }


def max_consecutive_outcomes(outcomes: pd.DataFrame, outcome_name: str) -> int:
    """Return the max consecutive run of an outcome by account_start order."""

    if outcomes.empty:
        return 0
    max_run = 0
    run = 0
    ordered = outcomes.sort_values("account_start")
    for value in ordered["outcome"].astype(str):
        if value == outcome_name:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    return int(max_run)


def profile_to_dict(profile: PropFirmRiskProfile) -> dict[str, Any]:
    """Serialize a profile for summary JSON files."""

    return asdict(profile)


def safe_json(value: Any) -> Any:
    """Convert pandas/numpy values into JSON-safe Python primitives."""

    if isinstance(value, dict):
        return {str(k): safe_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_json(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value
