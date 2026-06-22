#!/usr/bin/env python3
"""Cross-asset neutral ORB base-parameter discovery matrix.

This generalizes the NQ NY ALPHA_V2 ORB discovery lineage:
- fixed neutral ORB continuation anchor
- RR/direction comparison
- causal DOW / prior rolling ATR / ORB range gates
- top-three discovery shortlist per asset/session
- holdout and first-payout diagnostics for the shortlisted candidates

The search uses only the last-five-year research window:
2021-2024 for discovery and 2025+ as the untouched holdout read.
"""

from __future__ import annotations

import json
import math
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
)
from orb_backtest.config import (  # noqa: E402
    ASIA_SESSION,
    LDN_SESSION,
    NY_SESSION,
    SessionConfig,
    default_config,
)
from orb_backtest.data.instruments import get_instrument  # noqa: E402
from orb_backtest.data.loader import load_1m_for_5m, load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    TradeResult,
    build_maps,
    build_signal_cache,
    run_backtest,
)
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from orb_backtest.validate.deflated_sharpe import (  # noqa: E402
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
)


RUN_ID = "cross_asset_orb_base_matrix_20260612"
RESULT_DIR = ROOT / "data" / "results" / RUN_ID
REPORT_PATH = ROOT / "learnings" / "reports" / "CROSS_ASSET_ORB_BASE_MATRIX_20260612.md"

ASSETS = ("NQ", "ES", "GC", "SI", "RTY", "YM")
SESSIONS = ("NY", "Asia", "LDN")
RR_VALUES = (1.0, 1.25, 1.5, 2.0)
DIRECTIONS = ("long", "short", "both")
ATR_GATES = ("none", "low_or_mid_atr", "low_atr_only")
ORB_GATES = ("none", "small_or_mid_orb", "small_orb_only", "large_orb_only")
DOW_EXCLUSIONS: tuple[int | None, ...] = (None, 0, 1, 2, 3, 4)
DOW_LABELS = {None: "none", 0: "no_mon", 1: "no_tue", 2: "no_wed", 3: "no_thu", 4: "no_fri"}
DOW_NAMES = {None: "None", 0: "Monday", 1: "Tuesday", 2: "Wednesday", 3: "Thursday", 4: "Friday"}

DATA_START = "2021-01-01"
DISCOVERY_START = "2021-01-01"
DISCOVERY_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"
MIN_DISCOVERY_TRADES = 40
TOP_MARKET_ROWS_FOR_PAYOUT = 18
TOP_ROWS_PER_SLEEVE = 3

BASE_RISK_USD = 5000.0
BASE_STOP_ATR_PCT = 10.0
BASE_MIN_GAP_ATR_PCT = 2.0
BASE_ATR_LENGTH = 14

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)
FIRST_PAYOUT_WITHDRAWAL_USD = 500.0
ACCOUNT_START_STEP_DAYS = 14

SESSION_TEMPLATES: dict[str, SessionConfig] = {
    "NY": NY_SESSION,
    "Asia": ASIA_SESSION,
    "LDN": LDN_SESSION,
}


@dataclass(frozen=True)
class CandidateRule:
    """One research candidate after the neutral anchor is fixed."""

    asset: str
    session: str
    rr: float
    direction: str
    excluded_dow: int | None
    atr_gate: str
    orb_gate: str

    @property
    def rule_id(self) -> str:
        parts = [
            self.asset.lower(),
            self.session.lower(),
            f"rr{str(self.rr).replace('.', 'p')}",
            self.direction,
            DOW_LABELS[self.excluded_dow],
        ]
        if self.atr_gate != "none":
            parts.append(self.atr_gate)
        if self.orb_gate != "none":
            parts.append(self.orb_gate)
        return "__".join(parts)

    @property
    def excluded_days_tuple(self) -> tuple[int, ...]:
        return () if self.excluded_dow is None else (self.excluded_dow,)

    @property
    def native_supported(self) -> bool:
        # max prior rolling ATR and max ORB range are native. A large-ORB-only
        # lower-bound gate is not currently expressible in StrategyConfig/live config.
        return self.orb_gate != "large_orb_only"

    @property
    def deployability(self) -> str:
        return "live_native" if self.native_supported else "post_filter_only"

    @property
    def live_support_notes(self) -> str:
        if self.native_supported:
            return (
                "RR, direction, DOW exclusion, max prior rolling ATR, and max ORB range "
                "are StrategyConfig/live-config expressible; exact execution replay is required."
            )
        return (
            "Uses a large-ORB lower-bound filter that is causal but not currently a native "
            "live pre-trade config field; add a min_orb_range_pct gate before deployment."
        )


def _json_default(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        if math.isnan(float(value)):
            return None
        return float(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _data_file_for(symbol: str) -> Path:
    if symbol == "NQ":
        return ROOT / "data" / "cache" / "nq_ny_lsi_cisd_sequence" / "NQ_5m.parquet"
    return ROOT / "data" / "raw" / f"{symbol}_5m.parquet"


def _load_asset_data(symbol: str) -> tuple[Path, pd.DataFrame, pd.DataFrame | None]:
    data_file = _data_file_for(symbol)
    df = load_5m_data(str(data_file), start=DATA_START)
    try:
        df_1m = load_1m_for_5m(str(data_file), start=DATA_START)
    except FileNotFoundError:
        df_1m = None
    return data_file, df, df_1m


def _base_session(session_name: str) -> SessionConfig:
    template = SESSION_TEMPLATES[session_name]
    return replace(
        template,
        stop_atr_pct=BASE_STOP_ATR_PCT,
        min_gap_atr_pct=BASE_MIN_GAP_ATR_PCT,
        max_prior_rolling_atr_pct=0.0,
        max_orb_range_pct=0.0,
    )


def _threshold_value(thresholds: dict[str, float], gate: str, kind: str) -> float:
    if kind == "atr":
        if gate == "low_or_mid_atr":
            return thresholds["atr_p66"]
        if gate == "low_atr_only":
            return thresholds["atr_p33"]
    if kind == "orb":
        if gate == "small_or_mid_orb":
            return thresholds["orb_p66"]
        if gate == "small_orb_only":
            return thresholds["orb_p33"]
    return 0.0


def _config_for_rule(symbol: str, rule: CandidateRule, thresholds: dict[str, float] | None = None):
    inst = get_instrument(symbol)
    session = _base_session(rule.session)
    if thresholds and rule.native_supported:
        session = replace(
            session,
            max_prior_rolling_atr_pct=_threshold_value(thresholds, rule.atr_gate, "atr"),
            max_orb_range_pct=_threshold_value(thresholds, rule.orb_gate, "orb"),
        )
    cfg = default_config(inst)
    return replace(
        cfg,
        sessions=(session,),
        risk_usd=BASE_RISK_USD,
        rr=rule.rr,
        tp1_ratio=1.0,
        exit_mode="single_target",
        atr_length=BASE_ATR_LENGTH,
        strategy="continuation",
        direction_filter=rule.direction,
        excluded_days=rule.excluded_days_tuple,
        continuation_fvg_selection="first",
        orb_trade_max_per_session=1,
        impulse_close_filter=False,
        use_bar_magnifier=True,
        name=rule.rule_id,
    )


def _stream_config(symbol: str, session_name: str, rr: float, direction: str):
    rule = CandidateRule(
        asset=symbol,
        session=session_name,
        rr=rr,
        direction=direction,
        excluded_dow=None,
        atr_gate="none",
        orb_gate="none",
    )
    return _config_for_rule(symbol, rule, thresholds=None)


def _session_context(df: pd.DataFrame, session_name: str) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    daily = (
        df.resample("1D")
        .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
        .dropna(subset=["open", "high", "low", "close"])
        .copy()
    )
    prev_close = daily["close"].shift(1)
    true_range = pd.concat(
        [
            daily["high"] - daily["low"],
            (daily["high"] - prev_close).abs(),
            (daily["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    daily["atr14"] = true_range.rolling(BASE_ATR_LENGTH, min_periods=BASE_ATR_LENGTH).mean()
    daily["prior_atr14_pct"] = (daily["atr14"] / daily["close"] * 100.0).shift(1)
    daily["date"] = daily.index.date

    session = _base_session(session_name)
    start_t = pd.Timestamp(session.orb_start).time()
    end_t = pd.Timestamp(session.orb_end).time()
    times = df.index.time
    if start_t < end_t:
        mask = [(t >= start_t and t < end_t) for t in times]
    else:
        mask = [(t >= start_t or t < end_t) for t in times]
    intraday = df.loc[mask]

    orb_rows: list[dict[str, Any]] = []
    for session_date, group in intraday.groupby(intraday.index.date):
        if group.empty:
            continue
        orb_open = float(group["open"].iloc[0])
        if not np.isfinite(orb_open) or orb_open <= 0:
            continue
        orb_high = float(group["high"].max())
        orb_low = float(group["low"].min())
        orb_rows.append({"date": session_date, "orb_range_pct": (orb_high - orb_low) / orb_open * 100.0})
    orb = pd.DataFrame(orb_rows)
    context = daily[["date", "prior_atr14_pct"]].merge(orb, on="date", how="left")

    discovery = context[
        (context["date"] >= datetime.fromisoformat(DISCOVERY_START).date())
        & (context["date"] <= datetime.fromisoformat(DISCOVERY_END).date())
    ]
    thresholds = {
        "atr_p33": float(discovery["prior_atr14_pct"].quantile(1 / 3)),
        "atr_p66": float(discovery["prior_atr14_pct"].quantile(2 / 3)),
        "orb_p33": float(discovery["orb_range_pct"].quantile(1 / 3)),
        "orb_p66": float(discovery["orb_range_pct"].quantile(2 / 3)),
    }
    atr_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["prior_atr14_pct"], strict=False)
        if pd.notna(v)
    }
    orb_by_date = {
        d.isoformat(): float(v)
        for d, v in zip(context["date"], context["orb_range_pct"], strict=False)
        if pd.notna(v)
    }
    return thresholds, atr_by_date, orb_by_date


def _period_trades(trades: list[TradeResult], start: str, end: str | None) -> list[TradeResult]:
    if end is None:
        return [trade for trade in trades if trade.date >= start]
    return [trade for trade in trades if start <= trade.date <= end]


def _filled(trades: list[TradeResult]) -> list[TradeResult]:
    return [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]


def _r_multiples(trades: list[TradeResult]) -> np.ndarray:
    return np.asarray(
        [
            float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
            for trade in trades
            if trade.exit_type != EXIT_NO_FILL
        ],
        dtype=float,
    )


def _trade_dates(trades: list[TradeResult]) -> set[str]:
    return {trade.date for trade in trades if trade.exit_type != EXIT_NO_FILL}


def _passes_gate(
    trade: TradeResult,
    rule: CandidateRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> bool:
    if rule.excluded_dow is not None and datetime.strptime(trade.date, "%Y-%m-%d").weekday() == rule.excluded_dow:
        return False

    atr_value = atr_by_date.get(trade.date)
    if rule.atr_gate != "none":
        if atr_value is None or not np.isfinite(atr_value):
            return False
        if rule.atr_gate == "low_or_mid_atr" and atr_value > thresholds["atr_p66"]:
            return False
        if rule.atr_gate == "low_atr_only" and atr_value > thresholds["atr_p33"]:
            return False

    orb_value = orb_by_date.get(trade.date)
    if rule.orb_gate != "none":
        if orb_value is None or not np.isfinite(orb_value):
            return False
        if rule.orb_gate == "small_or_mid_orb" and orb_value > thresholds["orb_p66"]:
            return False
        if rule.orb_gate == "small_orb_only" and orb_value > thresholds["orb_p33"]:
            return False
        if rule.orb_gate == "large_orb_only" and orb_value <= thresholds["orb_p66"]:
            return False

    return True


def _apply_rule(
    trades: list[TradeResult],
    rule: CandidateRule,
    thresholds: dict[str, float],
    atr_by_date: dict[str, float],
    orb_by_date: dict[str, float],
) -> list[TradeResult]:
    return [trade for trade in trades if _passes_gate(trade, rule, thresholds, atr_by_date, orb_by_date)]


def _metrics_summary(trades: list[TradeResult], *, years: tuple[int, ...]) -> dict[str, Any]:
    metrics = compute_metrics(trades)
    r_values = _r_multiples(trades)
    psr = compute_psr(r_values)
    r_by_year = {str(year): round(float(metrics.get("r_by_year", {}).get(str(year), 0.0)), 4) for year in years}
    month_r = _r_by_month(trades)
    return {
        "total_signals": int(metrics.get("total_signals", 0)),
        "total_trades": int(metrics.get("total_trades", 0)),
        "total_r": round(float(metrics.get("total_r", 0.0)), 4),
        "avg_r": round(float(metrics.get("avg_r", 0.0)), 4),
        "win_rate_pct": round(float(metrics.get("win_rate", 0.0)) * 100.0, 2),
        "profit_factor": round(float(metrics.get("profit_factor", 0.0)), 4),
        "max_drawdown_r": round(float(metrics.get("max_drawdown_r", 0.0)), 4),
        "calmar": round(float(metrics.get("calmar_ratio", 0.0)), 4),
        "sharpe": round(float(metrics.get("sharpe_ratio", 0.0)), 4),
        "max_consecutive_losses": int(metrics.get("max_consecutive_losses", 0)),
        "r_by_year": r_by_year,
        "positive_years": int(sum(1 for value in r_by_year.values() if value > 0)),
        "min_year_r": round(min(r_by_year.values()) if r_by_year else 0.0, 4),
        "worst_month_r": round(min(month_r.values()) if month_r else 0.0, 4),
        "psr": psr.psr,
        "observed_sharpe_psr": psr.observed_sharpe,
        "exit_breakdown": metrics.get("exit_breakdown", {}),
    }


def _r_by_month(trades: list[TradeResult]) -> dict[str, float]:
    rows = defaultdict(float)
    for trade in _filled(trades):
        rows[trade.date[:7]] += float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple)
    return {key: round(value, 4) for key, value in rows.items()}


def _account_start_dates(all_dates: list[pd.Timestamp]) -> list[pd.Timestamp]:
    if not all_dates:
        return []
    starts = [all_dates[0]]
    next_target = all_dates[0] + pd.Timedelta(days=ACCOUNT_START_STEP_DAYS)
    for day in all_dates[1:]:
        if day >= next_target:
            starts.append(day)
            next_target = day + pd.Timedelta(days=ACCOUNT_START_STEP_DAYS)
    return starts


def _funded_scorecard(
    name: str,
    trades: list[TradeResult],
    trading_dates: list[pd.Timestamp],
) -> dict[str, Any]:
    dates = [pd.Timestamp(day).normalize() for day in trading_dates]
    if not dates:
        return {
            "model": "14_day_staggered_first_payout",
            "specialist_name": name,
            "total_starts": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "ev_per_start_usd": 0.0,
            "median_days_to_payout": None,
            "median_trades_to_payout": None,
            "max_consecutive_breaches": 0,
        }

    day_to_rs: dict[pd.Timestamp, list[float]] = defaultdict(list)
    for trade in sorted(_filled(trades), key=lambda t: (t.date, t.fill_time or "", t.exit_time or "")):
        day_to_rs[pd.Timestamp(trade.date).normalize()].append(float(getattr(trade, "net_r_multiple", 0.0) or trade.r_multiple))

    outcomes: list[dict[str, Any]] = []
    starts = _account_start_dates(dates)
    starting_breach = min(
        FUNDED_PROFILE.starting_balance_usd - FUNDED_PROFILE.trailing_drawdown_usd,
        FUNDED_PROFILE.max_trailing_breach_usd,
    )

    for start_day in starts:
        balance = float(FUNDED_PROFILE.starting_balance_usd)
        highest_eod = float(FUNDED_PROFILE.starting_balance_usd)
        breach_floor = float(starting_breach)
        trades_taken = 0
        outcome = "open"
        outcome_day = start_day

        for cur_day in dates:
            if cur_day < start_day:
                continue

            for r_multiple in day_to_rs.get(cur_day, []):
                balance += r_multiple * FUNDED_PROFILE.risk_pre_payout_usd
                trades_taken += 1
                if balance <= breach_floor:
                    outcome = "breach"
                    outcome_day = cur_day
                    break

            if outcome == "breach":
                break

            if balance >= FUNDED_PROFILE.first_payout_floor_usd:
                outcome = "payout"
                outcome_day = cur_day
                break

            highest_eod = max(highest_eod, balance)
            breach_floor = min(highest_eod - FUNDED_PROFILE.trailing_drawdown_usd, FUNDED_PROFILE.max_trailing_breach_usd)
            outcome_day = cur_day

        if outcome == "payout":
            net = FIRST_PAYOUT_WITHDRAWAL_USD - FUNDED_PROFILE.challenge_fee
        elif outcome == "breach":
            net = -FUNDED_PROFILE.challenge_fee
        else:
            net = -FUNDED_PROFILE.challenge_fee

        outcomes.append(
            {
                "account_start": start_day.strftime("%Y-%m-%d"),
                "outcome": outcome,
                "outcome_date": outcome_day.strftime("%Y-%m-%d"),
                "calendar_days_to_outcome": (outcome_day.date() - start_day.date()).days + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": round(balance, 2),
                "net_payout_after_fee_usd": round(net, 2),
            }
        )

    if not outcomes:
        return {
            "model": "14_day_staggered_first_payout",
            "specialist_name": name,
            "total_starts": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "open_rate": 0.0,
            "ev_per_start_usd": 0.0,
            "median_days_to_payout": None,
            "median_trades_to_payout": None,
            "max_consecutive_breaches": 0,
        }

    outcome_df = pd.DataFrame(outcomes)
    payouts = outcome_df[outcome_df["outcome"] == "payout"]
    breaches = outcome_df[outcome_df["outcome"] == "breach"]
    opens = outcome_df[outcome_df["outcome"] == "open"]
    breach_mask = [row["outcome"] == "breach" for row in outcomes]
    max_consec_breaches = _max_consecutive_bool(breach_mask)
    total = len(outcome_df)
    return {
        "model": "14_day_staggered_first_payout",
        "specialist_name": name,
        "total_starts": int(total),
        "payout_rate": round(float(len(payouts) / total), 4),
        "breach_rate": round(float(len(breaches) / total), 4),
        "open_rate": round(float(len(opens) / total), 4),
        "ev_per_start_usd": round(float(outcome_df["net_payout_after_fee_usd"].mean()), 2),
        "median_days_to_payout": (
            round(float(payouts["calendar_days_to_outcome"].median()), 2) if not payouts.empty else None
        ),
        "median_trades_to_payout": (
            round(float(payouts["trades_to_outcome"].median()), 2) if not payouts.empty else None
        ),
        "max_consecutive_breaches": int(max_consec_breaches),
        "outcome_counts": {str(k): int(v) for k, v in outcome_df["outcome"].value_counts().to_dict().items()},
    }


def _max_consecutive_bool(values: list[bool]) -> int:
    best = 0
    cur = 0
    for value in values:
        if value:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _date_index(df: pd.DataFrame, start: str, end: str | None) -> list[pd.Timestamp]:
    days = pd.Index(df.index.normalize().unique()).sort_values()
    start_ts = pd.Timestamp(start)
    if end is not None:
        end_ts = pd.Timestamp(end)
        days = days[(days >= start_ts) & (days <= end_ts)]
    else:
        days = days[days >= start_ts]
    return [pd.Timestamp(day).normalize() for day in days]


def _market_rank_key(row: dict[str, Any]) -> tuple:
    m = row["discovery_metrics"]
    min_trade_ok = m["total_trades"] >= MIN_DISCOVERY_TRADES
    edge_ok = m["total_r"] > 0 and m["profit_factor"] > 1.0
    annual_ok = m["min_year_r"] >= 0.0
    psr_ok = m["psr"] >= 0.85
    r_2022_2023 = float(m["r_by_year"].get("2022", 0.0)) + float(m["r_by_year"].get("2023", 0.0))
    return (
        int(min_trade_ok),
        int(edge_ok),
        int(annual_ok),
        int(psr_ok),
        m["positive_years"],
        round(r_2022_2023, 4),
        -abs(m["max_drawdown_r"]),
        m["calmar"],
        m["total_r"],
    )


def _final_rank_key(row: dict[str, Any]) -> tuple:
    m = row["discovery_metrics"]
    p = row.get("discovery_payout", {})
    h = row.get("holdout_metrics", {})
    hp = row.get("holdout_payout", {})
    r_2022_2023 = float(m["r_by_year"].get("2022", 0.0)) + float(m["r_by_year"].get("2023", 0.0))
    discovery_core = (
        m["total_trades"] >= MIN_DISCOVERY_TRADES
        and m["total_r"] > 0
        and m["profit_factor"] > 1.0
        and m["psr"] >= 0.85
        and row.get("dsr", 0.0) >= 0.50
    )
    annual_ok = m["min_year_r"] >= 0.0
    prop_ok = float(p.get("ev_per_start_usd", 0.0)) > 0.0 and float(p.get("payout_rate", 0.0)) > float(p.get("breach_rate", 0.0))
    holdout_ok = h.get("total_trades", 0) >= 5 and h.get("total_r", 0.0) > 0.0 and h.get("profit_factor", 0.0) > 1.0
    holdout_prop_ok = float(hp.get("ev_per_start_usd", 0.0)) >= 0.0
    return (
        int(row["deployability"] == "live_native"),
        int(discovery_core),
        int(annual_ok),
        int(prop_ok),
        int(holdout_ok),
        int(holdout_prop_ok),
        m["positive_years"],
        round(r_2022_2023, 4),
        float(p.get("ev_per_start_usd", 0.0)),
        -abs(m["max_drawdown_r"]),
        m["calmar"],
        h.get("total_r", 0.0),
    )


def _verdict(row: dict[str, Any]) -> str:
    key = _final_rank_key(row)
    discovery_core = bool(key[1])
    annual_ok = bool(key[2])
    prop_ok = bool(key[3])
    holdout_ok = bool(key[4])
    live_native = row["deployability"] == "live_native"
    if live_native and discovery_core and annual_ok and prop_ok and holdout_ok:
        return "PROMOTE_TO_EXACT_REPLAY"
    if live_native and discovery_core and prop_ok:
        return "CHALLENGER"
    if not live_native and discovery_core and prop_ok:
        return "IMPLEMENTATION_REQUIRED"
    return "REJECT"


def _evaluate_sleeve(
    symbol: str,
    session_name: str,
    df: pd.DataFrame,
    df_1m: pd.DataFrame | None,
) -> dict[str, Any]:
    thresholds, atr_by_date, orb_by_date = _session_context(df, session_name)

    stream_configs = {
        (rr, direction): _stream_config(symbol, session_name, rr, direction)
        for rr in RR_VALUES
        for direction in DIRECTIONS
    }
    maps = build_maps(df, df_1m=df_1m)
    cache = build_signal_cache(df, list(stream_configs.values()), signal_df_1m=df_1m)
    streams: dict[tuple[float, str], list[TradeResult]] = {}
    for key, cfg in stream_configs.items():
        streams[key] = run_backtest(
            df,
            cfg,
            start_date=DISCOVERY_START,
            df_1m=df_1m,
            signal_df_1m=df_1m,
            _maps=maps,
            _signal_cache=cache,
        )

    rules = [
        CandidateRule(symbol, session_name, rr, direction, dow, atr_gate, orb_gate)
        for rr in RR_VALUES
        for direction in DIRECTIONS
        for dow in DOW_EXCLUSIONS
        for atr_gate in ATR_GATES
        for orb_gate in ORB_GATES
    ]

    trade_date_sets: list[set[str]] = []
    rows: list[dict[str, Any]] = []
    discovery_trades_by_rule: dict[str, list[TradeResult]] = {}
    holdout_trades_by_rule: dict[str, list[TradeResult]] = {}
    for rule in rules:
        stream = streams[(rule.rr, rule.direction)]
        candidate_trades = _apply_rule(stream, rule, thresholds, atr_by_date, orb_by_date)
        discovery_trades = _period_trades(candidate_trades, DISCOVERY_START, DISCOVERY_END)
        holdout_trades = _period_trades(candidate_trades, HOLDOUT_START, None)
        discovery_trades_by_rule[rule.rule_id] = discovery_trades
        holdout_trades_by_rule[rule.rule_id] = holdout_trades
        trade_date_sets.append(_trade_dates(discovery_trades))
        rows.append(
            {
                "asset": symbol,
                "session": session_name,
                "rule_id": rule.rule_id,
                "rr": rule.rr,
                "direction": rule.direction,
                "excluded_dow": DOW_NAMES[rule.excluded_dow],
                "atr_gate": rule.atr_gate,
                "orb_gate": rule.orb_gate,
                "deployability": rule.deployability,
                "live_support_notes": rule.live_support_notes,
                "exact_replay_required": True,
                "native_supported": rule.native_supported,
                "discovery_metrics": _metrics_summary(discovery_trades, years=(2021, 2022, 2023, 2024)),
                "holdout_metrics_preview": _metrics_summary(holdout_trades, years=(2025, 2026)),
            }
        )

    n_trials_raw = len(rows)
    n_trials_effective = estimate_effective_trials(trade_date_sets)
    for row in rows:
        r_values = _r_multiples(discovery_trades_by_rule[row["rule_id"]])
        dsr = compute_dsr(r_values, n_trials_raw=n_trials_raw, n_trials_effective=n_trials_effective)
        row["dsr"] = dsr.dsr
        row["expected_max_sharpe"] = dsr.expected_max_sharpe
        row["n_trials_raw"] = n_trials_raw
        row["n_trials_effective"] = n_trials_effective

    market_shortlist = sorted(rows, key=_market_rank_key, reverse=True)[:TOP_MARKET_ROWS_FOR_PAYOUT]
    discovery_dates = _date_index(df, DISCOVERY_START, DISCOVERY_END)
    holdout_dates = _date_index(df, HOLDOUT_START, None)

    for row in market_shortlist:
        row["discovery_payout"] = _funded_scorecard(
            row["rule_id"],
            discovery_trades_by_rule[row["rule_id"]],
            discovery_dates,
        )
        row["holdout_payout_preview"] = _funded_scorecard(
            row["rule_id"],
            holdout_trades_by_rule[row["rule_id"]],
            holdout_dates,
        )

    top3 = sorted(market_shortlist, key=_final_rank_key, reverse=True)[:TOP_ROWS_PER_SLEEVE]
    top3_native: list[dict[str, Any]] = []
    for row in top3:
        rule = CandidateRule(
            asset=symbol,
            session=session_name,
            rr=float(row["rr"]),
            direction=str(row["direction"]),
            excluded_dow=None if row["excluded_dow"] == "None" else {v: k for k, v in DOW_NAMES.items()}[row["excluded_dow"]],
            atr_gate=str(row["atr_gate"]),
            orb_gate=str(row["orb_gate"]),
        )
        if rule.native_supported:
            native_cfg = _config_for_rule(symbol, rule, thresholds=thresholds)
            native_cache = build_signal_cache(df, [native_cfg], signal_df_1m=df_1m)
            native_trades_all = run_backtest(
                df,
                native_cfg,
                start_date=DISCOVERY_START,
                df_1m=df_1m,
                signal_df_1m=df_1m,
                _maps=maps,
                _signal_cache=native_cache,
            )
            native_discovery = _period_trades(native_trades_all, DISCOVERY_START, DISCOVERY_END)
            native_holdout = _period_trades(native_trades_all, HOLDOUT_START, None)
            row["native_rerun"] = {
                "performed": True,
                "discovery_metrics": _metrics_summary(native_discovery, years=(2021, 2022, 2023, 2024)),
                "holdout_metrics": _metrics_summary(native_holdout, years=(2025, 2026)),
                "discovery_delta_trades": int(
                    _metrics_summary(native_discovery, years=(2021, 2022, 2023, 2024))["total_trades"]
                    - row["discovery_metrics"]["total_trades"]
                ),
                "discovery_delta_r": round(
                    float(_metrics_summary(native_discovery, years=(2021, 2022, 2023, 2024))["total_r"])
                    - float(row["discovery_metrics"]["total_r"]),
                    4,
                ),
            }
            row["holdout_metrics"] = row["native_rerun"]["holdout_metrics"]
            row["holdout_payout"] = _funded_scorecard(row["rule_id"], native_holdout, holdout_dates)
        else:
            row["native_rerun"] = {
                "performed": False,
                "reason": "large_orb_only requires a native lower-bound ORB range gate.",
            }
            row["holdout_metrics"] = row["holdout_metrics_preview"]
            row["holdout_payout"] = row.get("holdout_payout_preview", {})
        row["verdict"] = _verdict(row)
        top3_native.append(row)

    top3_native = sorted(top3_native, key=_final_rank_key, reverse=True)
    sleeve_best = top3_native[0] if top3_native else None

    return {
        "asset": symbol,
        "session": session_name,
        "thresholds": thresholds,
        "trial_counts": {
            "n_trials_raw": n_trials_raw,
            "n_trials_effective": n_trials_effective,
            "min_discovery_trades": MIN_DISCOVERY_TRADES,
        },
        "data": {
            "rows_5m": int(len(df)),
            "has_1m": df_1m is not None,
            "start": DATA_START,
            "latest": df.index.max().date().isoformat() if len(df) else None,
            "discovery_start": DISCOVERY_START,
            "discovery_end": DISCOVERY_END,
            "holdout_start": HOLDOUT_START,
        },
        "anchor_config": _anchor_config_payload(session_name),
        "all_candidate_rows": rows,
        "top3": top3_native,
        "best": sleeve_best,
    }


def _anchor_config_payload(session_name: str) -> dict[str, Any]:
    session = _base_session(session_name)
    return {
        "strategy": "continuation",
        "session": session_name,
        "orb_window": f"{session.orb_start}-{session.orb_end}",
        "entry_window": f"{session.entry_start}-{session.entry_end}",
        "flat_window": f"{session.flat_start}-{session.flat_end}",
        "stop_atr_pct": BASE_STOP_ATR_PCT,
        "min_gap_atr_pct": BASE_MIN_GAP_ATR_PCT,
        "atr_length": BASE_ATR_LENGTH,
        "rr_values": list(RR_VALUES),
        "tp1_ratio": 1.0,
        "exit_mode": "single_target",
        "continuation_fvg_selection": "first",
        "orb_trade_max_per_session": 1,
        "impulse_close_filter": False,
    }


def _flatten_candidate(row: dict[str, Any], *, rank: int | None = None) -> dict[str, Any]:
    d = row["discovery_metrics"]
    h = row.get("holdout_metrics") or row.get("holdout_metrics_preview") or {}
    p = row.get("discovery_payout", {})
    hp = row.get("holdout_payout") or row.get("holdout_payout_preview") or {}
    flat = {
        "rank": rank,
        "asset": row["asset"],
        "session": row["session"],
        "rule_id": row["rule_id"],
        "verdict": row.get("verdict"),
        "deployability": row["deployability"],
        "rr": row["rr"],
        "direction": row["direction"],
        "excluded_dow": row["excluded_dow"],
        "atr_gate": row["atr_gate"],
        "orb_gate": row["orb_gate"],
        "trades": d["total_trades"],
        "r": d["total_r"],
        "pf": d["profit_factor"],
        "dd_r": d["max_drawdown_r"],
        "calmar": d["calmar"],
        "sharpe": d["sharpe"],
        "min_year_r": d["min_year_r"],
        "positive_years": d["positive_years"],
        "r_2021": d["r_by_year"].get("2021", 0.0),
        "r_2022": d["r_by_year"].get("2022", 0.0),
        "r_2023": d["r_by_year"].get("2023", 0.0),
        "r_2024": d["r_by_year"].get("2024", 0.0),
        "psr": d["psr"],
        "dsr": row.get("dsr"),
        "disc_payout_rate": p.get("payout_rate"),
        "disc_breach_rate": p.get("breach_rate"),
        "disc_ev_per_start": p.get("ev_per_start_usd"),
        "holdout_trades": h.get("total_trades"),
        "holdout_r": h.get("total_r"),
        "holdout_pf": h.get("profit_factor"),
        "holdout_dd_r": h.get("max_drawdown_r"),
        "holdout_payout_rate": hp.get("payout_rate"),
        "holdout_breach_rate": hp.get("breach_rate"),
        "holdout_ev_per_start": hp.get("ev_per_start_usd"),
        "native_rerun": (row.get("native_rerun") or {}).get("performed", False),
        "exact_replay_required": row.get("exact_replay_required", True),
    }
    return flat


def _markdown_table(rows: list[dict[str, Any]], columns: list[tuple[str, str]]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(label for label, _ in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    body = []
    for row in rows:
        values = []
        for _, key in columns:
            value = row.get(key)
            if value is None:
                values.append("")
            elif isinstance(value, float):
                values.append(f"{value:.2f}")
            else:
                values.append(str(value))
        body.append("| " + " | ".join(values) + " |")
    return "\n".join([header, sep, *body])


def _render_report(payload: dict[str, Any]) -> str:
    best = payload["best_overall"]
    lines = [
        "# Cross-Asset Neutral ORB Base Matrix",
        "",
        "## Executive Read",
        "",
        (
            "This scan reused the ALPHA_V2 NQ_NY-RR2 neutral ORB anchor across "
            "NQ, ES, GC, SI, RTY, and YM for NY, Asia, and London sessions. "
            "Discovery used 2021-2024 only; 2025+ was evaluated after each sleeve shortlist was frozen."
        ),
        "",
        (
            "The ranking is deliberately multi-factor: enough trades, positive edge, annual consistency, "
            "2022-2023 survivability, PSR/DSR, first-payout EV, drawdown, Calmar, and holdout behavior. "
            "Calmar is reported but is not the sole optimizer."
        ),
        "",
    ]
    if best:
        lines.extend(
            [
                f"**Best promotion candidate:** `{best['rule_id']}`",
                "",
                (
                    f"- Verdict: `{best['verdict']}`; deployability `{best['deployability']}`; "
                    f"exact execution replay required."
                ),
                (
                    f"- Discovery: {best['trades']} trades, {best['r']:.2f}R, PF {best['pf']:.2f}, "
                    f"DD {best['dd_r']:.2f}R, Calmar {best['calmar']:.2f}, "
                    f"PSR {best['psr']:.4f}, DSR {best['dsr']:.4f}."
                ),
                (
                    f"- Discovery payout model: payout {best.get('disc_payout_rate', 0):.1%}, "
                    f"breach {best.get('disc_breach_rate', 0):.1%}, EV/start ${best.get('disc_ev_per_start', 0):.2f}."
                ),
                (
                    f"- Holdout: {best.get('holdout_trades', 0)} trades, {best.get('holdout_r', 0):.2f}R, "
                    f"PF {best.get('holdout_pf', 0):.2f}, DD {best.get('holdout_dd_r', 0):.2f}R."
                ),
                "",
            ]
        )
    else:
        lines.extend(["No promotion candidate cleared the report ranking.", ""])

    top_cols = [
        ("Rank", "overall_rank"),
        ("Asset", "asset"),
        ("Sess", "session"),
        ("Rule", "rule_id"),
        ("Verdict", "verdict"),
        ("Trades", "trades"),
        ("R", "r"),
        ("PF", "pf"),
        ("DD", "dd_r"),
        ("Cal", "calmar"),
        ("DSR", "dsr"),
        ("Pay%", "disc_payout_rate"),
        ("EV", "disc_ev_per_start"),
        ("HO R", "holdout_r"),
        ("HO PF", "holdout_pf"),
    ]
    lines.extend(
        [
            "## Overall Top Candidates",
            "",
            _markdown_table(payload["overall_top"], top_cols),
            "",
            "## Top 3 By Asset And Session",
            "",
        ]
    )

    sleeve_cols = [
        ("Rank", "rank"),
        ("Rule", "rule_id"),
        ("Verdict", "verdict"),
        ("Dir", "direction"),
        ("RR", "rr"),
        ("DOW", "excluded_dow"),
        ("ATR", "atr_gate"),
        ("ORB", "orb_gate"),
        ("Trades", "trades"),
        ("R", "r"),
        ("PF", "pf"),
        ("DD", "dd_r"),
        ("Cal", "calmar"),
        ("DSR", "dsr"),
        ("Pay%", "disc_payout_rate"),
        ("EV", "disc_ev_per_start"),
        ("HO R", "holdout_r"),
    ]
    for sleeve in payload["sleeve_reports"]:
        lines.extend(
            [
                f"### {sleeve['asset']} {sleeve['session']}",
                "",
                f"- Trials: raw `{sleeve['trial_counts']['n_trials_raw']}`, effective `{sleeve['trial_counts']['n_trials_effective']}`.",
                (
                    f"- Gates calibrated on market-only 2021-2024 distributions: "
                    f"ATR p33 `{sleeve['thresholds']['atr_p33']:.4f}`, "
                    f"ATR p66 `{sleeve['thresholds']['atr_p66']:.4f}`, "
                    f"ORB p33 `{sleeve['thresholds']['orb_p33']:.4f}`, "
                    f"ORB p66 `{sleeve['thresholds']['orb_p66']:.4f}`."
                ),
                "",
                _markdown_table(sleeve["top3_flat"], sleeve_cols),
                "",
            ]
        )

    lines.extend(
        [
            "## Method Notes",
            "",
            f"- Data window: `{DISCOVERY_START}` to `{payload['latest_data_date']}` loaded; discovery `{DISCOVERY_START}`-`{DISCOVERY_END}`; holdout `{HOLDOUT_START}` onward.",
            "- Anchor: 15m session ORB, first 5m continuation FVG outside range, ATR14, 10% ATR stop, 2% ATR gap, one trade per session day, single-target exits.",
            f"- RR/direction grid: RR `{list(RR_VALUES)}`, direction `{list(DIRECTIONS)}`.",
            "- Causal filters: no single weekday, low/low-mid prior rolling ATR, small/small-mid/large ORB range.",
            f"- First-payout model: $50k start, $2k trailing DD capped at $50k, $52.5k payout trigger, $500 first withdrawal, ${FUNDED_PROFILE.challenge_fee:.0f} challenge fee, $500/R, 14-day staggered account starts.",
            "- PBO/CSCV is not implemented in this scan. PSR/DSR/effective trials are reported for multiple-testing discipline.",
            "- `PROMOTE_TO_EXACT_REPLAY` means promotion to exact execution replay / paper-candidate review, not live deployment.",
            "",
            "## Artifacts",
            "",
            f"- `{RESULT_DIR / 'summary.json'}`",
            f"- `{RESULT_DIR / 'top3_candidates.csv'}`",
            f"- `{RESULT_DIR / 'all_candidates.csv'}`",
            f"- `{RESULT_DIR / 'report.md'}`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    sleeve_reports: list[dict[str, Any]] = []
    all_flat_rows: list[dict[str, Any]] = []
    top3_flat_rows: list[dict[str, Any]] = []
    latest_dates: list[str] = []

    for symbol in ASSETS:
        data_file, df, df_1m = _load_asset_data(symbol)
        if df.empty:
            raise RuntimeError(f"No data loaded for {symbol} from {data_file}")
        latest_dates.append(df.index.max().date().isoformat())
        print(f"[{symbol}] loaded {len(df):,} 5m rows; 1m={'yes' if df_1m is not None else 'no'}; latest={latest_dates[-1]}", flush=True)
        for session_name in SESSIONS:
            print(f"  [{symbol} {session_name}] evaluating sleeve", flush=True)
            sleeve = _evaluate_sleeve(symbol, session_name, df, df_1m)
            top3_flat = [_flatten_candidate(row, rank=i + 1) for i, row in enumerate(sleeve["top3"])]
            sleeve_reports.append(
                {
                    "asset": symbol,
                    "session": session_name,
                    "thresholds": sleeve["thresholds"],
                    "trial_counts": sleeve["trial_counts"],
                    "data": sleeve["data"],
                    "anchor_config": sleeve["anchor_config"],
                    "top3": sleeve["top3"],
                    "top3_flat": top3_flat,
                    "best": sleeve["best"],
                }
            )
            for row in sleeve["all_candidate_rows"]:
                all_flat_rows.append(_flatten_candidate(row))
            top3_flat_rows.extend(top3_flat)
            best_rule = top3_flat[0]["rule_id"] if top3_flat else "none"
            print(f"  [{symbol} {session_name}] best={best_rule}", flush=True)

    top3_ranked = sorted(top3_flat_rows, key=lambda row: _final_rank_key(_inflate_flat_for_sort(row)), reverse=True)
    for idx, row in enumerate(top3_ranked, start=1):
        row["overall_rank"] = idx
    best_overall = top3_ranked[0] if top3_ranked else None

    payload = {
        "run_id": RUN_ID,
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "latest_data_date": max(latest_dates) if latest_dates else None,
        "data_window": {
            "data_start": DATA_START,
            "discovery_start": DISCOVERY_START,
            "discovery_end": DISCOVERY_END,
            "holdout_start": HOLDOUT_START,
        },
        "assets": list(ASSETS),
        "sessions": list(SESSIONS),
        "funded_profile": {
            **asdict(FUNDED_PROFILE),
            "first_payout_withdrawal_usd": FIRST_PAYOUT_WITHDRAWAL_USD,
            "account_start_step_days": ACCOUNT_START_STEP_DAYS,
        },
        "sleeve_reports": sleeve_reports,
        "overall_top": top3_ranked[:12],
        "best_overall": best_overall,
        "pbo_cscv": {
            "implemented": False,
            "note": "This workflow computes PSR/DSR/effective trials; CSCV/PBO is not implemented here.",
        },
    }

    summary_path = RESULT_DIR / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    pd.DataFrame(all_flat_rows).to_csv(RESULT_DIR / "all_candidates.csv", index=False)
    pd.DataFrame(top3_ranked).to_csv(RESULT_DIR / "top3_candidates.csv", index=False)

    report = _render_report(payload)
    (RESULT_DIR / "report.md").write_text(report + "\n")
    REPORT_PATH.write_text(report + "\n")

    print(
        json.dumps(
            {
                "success": True,
                "summary": str(summary_path),
                "report": str(REPORT_PATH),
                "best_overall": best_overall["rule_id"] if best_overall else None,
            },
            indent=2,
        )
    )
    return 0


def _inflate_flat_for_sort(row: dict[str, Any]) -> dict[str, Any]:
    """Recreate the nested fields needed by _final_rank_key for flat rows."""
    return {
        "deployability": row.get("deployability"),
        "dsr": row.get("dsr") or 0.0,
        "discovery_metrics": {
            "total_trades": row.get("trades") or 0,
            "total_r": row.get("r") or 0.0,
            "profit_factor": row.get("pf") or 0.0,
            "psr": row.get("psr") or 0.0,
            "min_year_r": row.get("min_year_r") if row.get("min_year_r") is not None else -999.0,
            "positive_years": row.get("positive_years") or 0,
            "r_by_year": {
                "2021": row.get("r_2021") or 0.0,
                "2022": row.get("r_2022") or 0.0,
                "2023": row.get("r_2023") or 0.0,
                "2024": row.get("r_2024") or 0.0,
            },
            "max_drawdown_r": row.get("dd_r") or 0.0,
            "calmar": row.get("calmar") or 0.0,
        },
        "discovery_payout": {
            "ev_per_start_usd": row.get("disc_ev_per_start") or 0.0,
            "payout_rate": row.get("disc_payout_rate") or 0.0,
            "breach_rate": row.get("disc_breach_rate") or 0.0,
        },
        "holdout_metrics": {
            "total_trades": row.get("holdout_trades") or 0,
            "total_r": row.get("holdout_r") or 0.0,
            "profit_factor": row.get("holdout_pf") or 0.0,
        },
        "holdout_payout": {
            "ev_per_start_usd": row.get("holdout_ev_per_start") or 0.0,
        },
    }


if __name__ == "__main__":
    raise SystemExit(main())
