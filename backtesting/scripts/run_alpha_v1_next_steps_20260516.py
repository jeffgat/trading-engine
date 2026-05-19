#!/usr/bin/env python3
"""ALPHA_V1 next-step packet for 2026-05-16.

Runs the three follow-up tests requested after the ES/NQ candidate comb-through:

1. Asia sleeve payoff geometry: NQ Asia + active ES Asia vs ES Asia-B.
2. NQ NY R11 entry-time 15m structure + VWAP gate proxy.
3. Hunter 0.25x sidecar against the current fee-aware five-leg ALPHA_V1 packet.

The script uses cached exact trade streams and writes a compact report plus
machine-readable CSV artifacts. It does not edit execution configs or search
new strategy parameters.
"""

from __future__ import annotations

import json
import math
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent

for path in (BT_ROOT / "src", SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orb_backtest.config import SessionConfig  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402
from orb_backtest.signals.daily_atr import compute_daily_atr  # noqa: E402
from orb_backtest.signals.orb import compute_orb_levels  # noqa: E402
from orb_backtest.signals.session import compute_session_days, compute_session_masks  # noqa: E402
from orb_backtest.signals.structure_15m import compute_all_15m_signals  # noqa: E402
from orb_backtest.signals.vwap import compute_session_vwap  # noqa: E402


RUN_SLUG = "alpha_v1_next_steps_20260516"
OUT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_NEXT_STEPS_20260516.md"

FEE_TRADES = BT_ROOT / "data/results/alpha_v1_fee_comparison_20260506/exact_trades.csv"
ES_ASIA_B_TRADES = BT_ROOT / "data/results/alpha_v1_es_asia_b_direct_compare_20260516/exact_trades.csv"
CURRENT_FEE_ALPHA_TRADES = BT_ROOT / "data/results/alpha_v1_payout_with_fees_20260507/exact_trades_by_profile.csv"
R11_TRADES = FEE_TRADES
HUNTER_TRADE_DIR = BT_ROOT / "data/results/hunter_classic_next_tests_20260502/selected_trades"

HUNTER_CANDIDATES = {
    "ema14_tol0_distnone__withTue__1055__rej100__stress": "10y-Safe Branch",
    "ema14_tol2_distnone__noTue__1055__rej20__stress": "Neutral Reference",
    "ema14_tol5_distnone__noTue__1055__rej100__stress": "Recent-Strength Branch",
}

FUNDED_MODEL = {
    "starting_balance_usd": 50_000.0,
    "trailing_drawdown_usd": 2_000.0,
    "max_trailing_breach_usd": 50_000.0,
    "first_payout_floor_usd": 52_500.0,
    "first_payout_withdrawal_usd": 500.0,
    "challenge_fee_usd": 150.0,
    "cohort_spacing_days": 14,
}

YEAR_WINDOWS = {
    "2024": ("2024-01-01", "2024-12-31"),
    "2025": ("2025-01-01", "2025-12-31"),
    "2026_YTD": ("2026-01-01", "2026-03-24"),
}

ASIA_RISKS = {
    "nq_asia_orb": 400.0,
    "es_asia_orb": 150.0,
    "es_asia_b": 150.0,
}

HUNTER_BASE_RISK_USD = 350.0
HUNTER_SCALE = 0.25
NY_TZ = "America/New_York"


@dataclass(frozen=True)
class TradeStream:
    key: str
    label: str
    trades: pd.DataFrame


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    return out if math.isfinite(out) else default


def _fmt(value: Any, digits: int = 1) -> str:
    if value is None:
        return "-"
    if isinstance(value, float) and not math.isfinite(value):
        return "-"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number) >= 100:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _fmt_r(value: Any, digits: int = 1) -> str:
    number = _safe_float(value, default=np.nan)
    if not math.isfinite(number):
        return "-"
    return f"{number:+,.{digits}f}R"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    number = _safe_float(value, default=np.nan)
    if not math.isfinite(number):
        return "-"
    return f"{number:,.{digits}f}%"


def _fmt_usd(value: Any, digits: int = 0) -> str:
    number = _safe_float(value, default=np.nan)
    if not math.isfinite(number):
        return "-"
    return f"${number:,.{digits}f}"


def md_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_No rows._"
    out = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        out.append("| " + " | ".join(str(x) for x in row) + " |")
    return "\n".join(out)


def max_drawdown(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return 0.0
    equity = np.concatenate([[0.0], np.cumsum(arr)])
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    if arr.size == 0:
        return 0.0
    wins = arr[arr > 0].sum()
    losses = arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def trade_metrics(df: pd.DataFrame, r_col: str = "net_r") -> dict[str, Any]:
    if df.empty:
        return {
            "trades": 0,
            "net_r": 0.0,
            "gross_r": 0.0,
            "win_rate_pct": 0.0,
            "pf": 0.0,
            "closed_dd_r": 0.0,
            "avg_r": 0.0,
            "full_target_pct": 0.0,
            "sl_pct": 0.0,
            "eod_pct": 0.0,
        }
    r = df[r_col].astype(float).to_numpy()
    gross = df["gross_r"].astype(float).to_numpy() if "gross_r" in df else r
    exit_types = df["exit_type"].fillna("").astype(str)
    full_target = exit_types.str.contains("tp1_tp2|tp2|full", regex=True).sum()
    sl = exit_types.str.contains("sl", regex=False).sum()
    eod = exit_types.str.contains("eod", regex=False).sum()
    return {
        "trades": int(len(df)),
        "net_r": float(np.sum(r)),
        "gross_r": float(np.sum(gross)),
        "win_rate_pct": float((r > 0).mean() * 100.0),
        "pf": profit_factor(r),
        "closed_dd_r": max_drawdown(r),
        "avg_r": float(np.mean(r)),
        "full_target_pct": float(full_target / len(df) * 100.0),
        "sl_pct": float(sl / len(df) * 100.0),
        "eod_pct": float(eod / len(df) * 100.0),
    }


def daily_metrics(daily: pd.Series) -> dict[str, Any]:
    d = daily.fillna(0.0).astype(float)
    monthly = d.resample("ME").sum() if len(d) else pd.Series(dtype=float)
    std = float(d.std(ddof=1)) if len(d) > 1 else 0.0
    sharpe = float(d.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0
    return {
        "days": int(len(d)),
        "net": float(d.sum()),
        "closed_dd": max_drawdown(d.to_numpy()),
        "sharpe": sharpe,
        "worst_day": float(d.min()) if len(d) else 0.0,
        "best_day": float(d.max()) if len(d) else 0.0,
        "worst_month": float(monthly.min()) if len(monthly) else 0.0,
        "best_month": float(monthly.max()) if len(monthly) else 0.0,
        "negative_months": int((monthly < 0).sum()) if len(monthly) else 0,
    }


def parse_trade_times(df: pd.DataFrame, *, entry_col: str = "entry_time", exit_col: str = "exit_time") -> pd.DataFrame:
    out = df.copy()
    out["entry_ts_utc"] = pd.to_datetime(out[entry_col], utc=True, errors="coerce")
    out["exit_ts_utc"] = pd.to_datetime(out[exit_col], utc=True, errors="coerce")
    out = out[out["exit_ts_utc"].notna()].copy()
    out["exit_day"] = out["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    out["entry_local"] = out["entry_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    return out


def normalize_exact_stream(
    df: pd.DataFrame,
    *,
    key: str,
    label: str,
    leg: str,
    r_col: str = "net_r_multiple",
    source: str,
) -> TradeStream:
    out = parse_trade_times(df)
    out["stream_key"] = key
    out["stream_label"] = label
    out["leg"] = leg
    out["source"] = source
    out["gross_r"] = out["r_multiple"].astype(float)
    out["net_r"] = out[r_col].astype(float) if r_col in out.columns else out["gross_r"]
    out["pnl_usd_model"] = out["net_r"] * out["leg"].map(lambda x: ASIA_RISKS.get(x, 1.0))
    return TradeStream(key=key, label=label, trades=out)


def daily_r(df: pd.DataFrame, value_col: str = "net_r") -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    grouped = df.groupby("exit_day")[value_col].sum().sort_index()
    idx = pd.date_range(grouped.index.min(), grouped.index.max(), freq="D")
    return grouped.reindex(idx, fill_value=0.0)


def daily_usd(df: pd.DataFrame, value_col: str = "pnl_usd_model") -> pd.Series:
    if df.empty:
        return pd.Series(dtype=float)
    grouped = df.groupby("exit_day")[value_col].sum().sort_index()
    idx = pd.date_range(grouped.index.min(), grouped.index.max(), freq="D")
    return grouped.reindex(idx, fill_value=0.0)


def _cohort_starts(start: str, end: str) -> list[pd.Timestamp]:
    return [
        ts.normalize()
        for ts in pd.date_range(
            pd.Timestamp(start).normalize(),
            pd.Timestamp(end).normalize(),
            freq=f"{int(FUNDED_MODEL['cohort_spacing_days'])}D",
        )
    ]


def simulate_accounts(trades: pd.DataFrame, *, start: str, end: str, pnl_col: str = "pnl_usd_model") -> pd.DataFrame:
    if trades.empty:
        return pd.DataFrame()
    subset = trades[
        (trades["exit_day"] >= pd.Timestamp(start))
        & (trades["exit_day"] <= pd.Timestamp(end))
    ].copy()
    subset = subset.sort_values(["exit_ts_utc", "leg", "entry_ts_utc"]).reset_index(drop=True)
    trade_tuples = [
        (
            pd.Timestamp(row.exit_ts_utc).tz_convert(NY_TZ).tz_localize(None),
            pd.Timestamp(row.exit_day),
            str(row.leg),
            float(getattr(row, pnl_col)),
        )
        for row in subset[["exit_ts_utc", "exit_day", "leg", pnl_col]].itertuples(index=False)
    ]
    rows: list[dict[str, Any]] = []
    for account_id, start_ts in enumerate(_cohort_starts(start, end), start=1):
        balance = float(FUNDED_MODEL["starting_balance_usd"])
        floor = balance - float(FUNDED_MODEL["trailing_drawdown_usd"])
        high_eod = balance
        current_day: pd.Timestamp | None = None
        outcome = "open"
        outcome_date = pd.Timestamp(end).normalize()
        trades_taken = 0
        leg_counts: Counter[str] = Counter()

        for exit_ts, trade_day, leg, pnl_usd in trade_tuples:
            if exit_ts < start_ts:
                continue
            if current_day is not None and trade_day != current_day:
                high_eod = max(high_eod, balance)
                floor = max(
                    floor,
                    min(
                        high_eod - float(FUNDED_MODEL["trailing_drawdown_usd"]),
                        float(FUNDED_MODEL["max_trailing_breach_usd"]),
                    ),
                )
            current_day = trade_day
            balance += pnl_usd
            trades_taken += 1
            leg_counts[leg] += 1
            if balance <= floor:
                outcome = "breach"
                outcome_date = trade_day
                break
            if balance >= float(FUNDED_MODEL["first_payout_floor_usd"]):
                outcome = "payout"
                outcome_date = trade_day
                break

        net_after_fee = (
            float(FUNDED_MODEL["first_payout_withdrawal_usd"]) - float(FUNDED_MODEL["challenge_fee_usd"])
            if outcome == "payout"
            else -float(FUNDED_MODEL["challenge_fee_usd"])
        )
        rows.append(
            {
                "account_id": account_id,
                "account_start": start_ts.date().isoformat(),
                "outcome": outcome,
                "outcome_date": outcome_date.date().isoformat(),
                "days_to_outcome": int((outcome_date - start_ts).days) + 1,
                "trades_to_outcome": trades_taken,
                "ending_balance_usd": round(balance, 2),
                "breach_floor_usd": round(floor, 2),
                "net_after_fee_usd": round(net_after_fee, 2),
                **{f"{leg}_trades": int(count) for leg, count in sorted(leg_counts.items())},
            }
        )
    return pd.DataFrame(rows)


def max_consecutive_outcome(outcomes: pd.DataFrame, outcome: str) -> int:
    if outcomes.empty:
        return 0
    run = 0
    best = 0
    for _, row in outcomes.sort_values("account_start").iterrows():
        if row["outcome"] == outcome:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def score_accounts(outcomes: pd.DataFrame) -> dict[str, Any]:
    if outcomes.empty:
        return {
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "resolved_payout_rate_pct": None,
            "resolved_breach_rate_pct": None,
            "start_payout_rate_pct": None,
            "start_breach_rate_pct": None,
            "open_rate_pct": None,
            "avg_days_to_payout": None,
            "median_days_to_payout": None,
            "max_consecutive_breaches": 0,
            "ev_per_start_usd": None,
        }
    total = len(outcomes)
    payouts = outcomes[outcomes["outcome"] == "payout"]
    breaches = outcomes[outcomes["outcome"] == "breach"]
    opens = outcomes[outcomes["outcome"] == "open"]
    resolved = len(payouts) + len(breaches)
    return {
        "accounts": int(total),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "resolved_payout_rate_pct": round(len(payouts) / resolved * 100.0, 2) if resolved else None,
        "resolved_breach_rate_pct": round(len(breaches) / resolved * 100.0, 2) if resolved else None,
        "start_payout_rate_pct": round(len(payouts) / total * 100.0, 2),
        "start_breach_rate_pct": round(len(breaches) / total * 100.0, 2),
        "open_rate_pct": round(len(opens) / total * 100.0, 2),
        "avg_days_to_payout": round(float(payouts["days_to_outcome"].mean()), 1) if len(payouts) else None,
        "median_days_to_payout": round(float(payouts["days_to_outcome"].median()), 1) if len(payouts) else None,
        "max_consecutive_breaches": max_consecutive_outcome(outcomes, "breach"),
        "ev_per_start_usd": round(float(outcomes["net_after_fee_usd"].mean()), 2),
    }


def run_asia_sleeve() -> dict[str, pd.DataFrame]:
    fee = pd.read_csv(FEE_TRADES)
    esb = pd.read_csv(ES_ASIA_B_TRADES)

    nq_asia = normalize_exact_stream(
        fee[fee["fee_compare_leg_key"] == "nq_asia_orb"].copy(),
        key="nq_asia",
        label="NQ Asia RR6",
        leg="nq_asia_orb",
        source="alpha_v1_fee_comparison_20260506",
    )
    active_es = normalize_exact_stream(
        esb[esb["candidate"] == "active_es_asia_rr1p5_tp0p7"].copy(),
        key="active_es_asia",
        label="Active ES Asia RR1.5",
        leg="es_asia_orb",
        source="alpha_v1_es_asia_b_direct_compare_20260516",
    )
    es_b_original = normalize_exact_stream(
        esb[esb["candidate"] == "es_asia_b_original_rr3_tp0p6"].copy(),
        key="es_asia_b_original",
        label="ES Asia-B original RR3",
        leg="es_asia_b",
        source="alpha_v1_es_asia_b_direct_compare_20260516",
    )
    es_b_constrained = normalize_exact_stream(
        esb[esb["candidate"] == "es_asia_b_constrained_rr2_tp0p75"].copy(),
        key="es_asia_b_constrained",
        label="ES Asia-B constrained RR2",
        leg="es_asia_b",
        source="alpha_v1_es_asia_b_direct_compare_20260516",
    )

    streams = [nq_asia, active_es, es_b_original, es_b_constrained]
    stream_rows = []
    for stream in streams:
        m = trade_metrics(stream.trades)
        stream_rows.append(
            {
                "stream": stream.key,
                "label": stream.label,
                "source": stream.trades["source"].iloc[0],
                **{k: _round(v, 3) if isinstance(v, float) else v for k, v in m.items()},
            }
        )

    variants = [
        ("nq_plus_active_es", "NQ Asia + active ES Asia", [nq_asia, active_es]),
        ("nq_plus_es_b_original", "NQ Asia + ES Asia-B original", [nq_asia, es_b_original]),
        ("nq_plus_es_b_constrained", "NQ Asia + ES Asia-B constrained", [nq_asia, es_b_constrained]),
    ]
    daily_rows = []
    overlap_rows = []
    account_rows = []
    account_details = []
    for variant_key, variant_label, parts in variants:
        combined = pd.concat([part.trades for part in parts], ignore_index=True)
        r_daily = daily_r(combined, "net_r")
        usd_daily = daily_usd(combined, "pnl_usd_model")
        dm_r = daily_metrics(r_daily)
        dm_usd = daily_metrics(usd_daily)
        daily_rows.append(
            {
                "variant": variant_key,
                "label": variant_label,
                "net_r": round(dm_r["net"], 3),
                "dd_r": round(dm_r["closed_dd"], 3),
                "sharpe_r": round(dm_r["sharpe"], 3),
                "worst_month_r": round(dm_r["worst_month"], 3),
                "best_month_r": round(dm_r["best_month"], 3),
                "weighted_net_usd": round(dm_usd["net"], 2),
                "weighted_dd_usd": round(dm_usd["closed_dd"], 2),
                "weighted_worst_month_usd": round(dm_usd["worst_month"], 2),
                "negative_months": dm_r["negative_months"],
            }
        )

        leg_a = daily_r(parts[0].trades, "net_r").reindex(r_daily.index, fill_value=0.0)
        leg_b = daily_r(parts[1].trades, "net_r").reindex(r_daily.index, fill_value=0.0)
        both = (leg_a != 0) & (leg_b != 0)
        overlap_rows.append(
            {
                "variant": variant_key,
                "corr": round(float(leg_a.corr(leg_b)), 4) if leg_a.std() > 0 and leg_b.std() > 0 else 0.0,
                "nq_active_days": int((leg_a != 0).sum()),
                "es_active_days": int((leg_b != 0).sum()),
                "both_active_days": int(both.sum()),
                "both_losing_days": int(((leg_a < 0) & (leg_b < 0)).sum()),
                "both_winning_days": int(((leg_a > 0) & (leg_b > 0)).sum()),
                "offset_days": int((both & ((leg_a > 0) != (leg_b > 0))).sum()),
                "worst_combined_overlap_r": round(float((leg_a[both] + leg_b[both]).min()), 3) if both.any() else 0.0,
            }
        )

        for year, (start, end) in YEAR_WINDOWS.items():
            outcomes = simulate_accounts(combined, start=start, end=end)
            detail = outcomes.copy()
            if not detail.empty:
                detail["variant"] = variant_key
                detail["label"] = variant_label
                detail["year"] = year
                account_details.append(detail)
            score = score_accounts(outcomes)
            account_rows.append(
                {
                    "variant": variant_key,
                    "label": variant_label,
                    "year": year,
                    **score,
                }
            )

    out = {
        "asia_stream_metrics": pd.DataFrame(stream_rows),
        "asia_daily_metrics": pd.DataFrame(daily_rows),
        "asia_overlap": pd.DataFrame(overlap_rows),
        "asia_account_scorecard": pd.DataFrame(account_rows),
        "asia_account_details": pd.concat(account_details, ignore_index=True) if account_details else pd.DataFrame(),
    }
    return out


def _r11_session() -> SessionConfig:
    return SessionConfig(
        name="NQ_NY_R11",
        orb_start="09:30",
        orb_end="09:50",
        entry_start="09:50",
        entry_end="12:00",
        flat_start="15:30",
        flat_end="16:00",
        stop_atr_pct=7.0,
        min_gap_atr_pct=2.5,
        min_stop_points=0.0,
        min_tp1_points=0.0,
    )


def _gate_eval(gate: str, sig: dict[str, np.ndarray], i: int, direction: int) -> bool:
    close = float(sig["close"][i])
    vwap = float(sig["vwap"][i])
    atr = float(sig["daily_atr"][i])
    if not math.isfinite(vwap) or not math.isfinite(atr) or atr <= 0:
        return False
    dist = (close - vwap) * direction
    dist_pct = dist / atr

    def struct(prefix: str) -> bool:
        suffix = "bull" if direction == 1 else "bear"
        return bool(sig[f"{prefix}_{suffix}"][i])

    if gate == "vwap_side_only":
        return dist > 0
    if gate == "vwap_d05_only":
        return dist_pct >= 0.05
    if gate == "vwap_d10_only":
        return dist_pct >= 0.10
    if gate == "vwap_d15_only":
        return dist_pct >= 0.15
    if gate == "hh_hl_2_vwap":
        return struct("hh_hl_2") and dist > 0
    if gate == "hh_hl_2_vwap_d05":
        return struct("hh_hl_2") and dist_pct >= 0.05
    if gate == "hh_or_hl_vwap":
        return struct("hh_or_hl") and dist > 0
    if gate == "hh_or_hl_vwap_d10":
        return struct("hh_or_hl") and dist_pct >= 0.10
    if gate == "any2of3_vwap":
        return struct("hh_hl_any2of3") and dist > 0
    if gate == "any2of3_vwap_d10":
        return struct("hh_hl_any2of3") and dist_pct >= 0.10
    if gate == "score_gte2_vwap":
        score = int(sig["bull_score"][i]) if direction == 1 else int(sig["bear_score"][i])
        return score >= 2 and dist > 0
    if gate == "score_gte2_d10":
        score = int(sig["bull_score"][i]) if direction == 1 else int(sig["bear_score"][i])
        return score >= 2 and dist_pct >= 0.10
    raise ValueError(f"Unknown R11 gate: {gate}")


R11_GATES = [
    "vwap_side_only",
    "vwap_d05_only",
    "vwap_d10_only",
    "vwap_d15_only",
    "hh_hl_2_vwap",
    "hh_hl_2_vwap_d05",
    "hh_or_hl_vwap",
    "hh_or_hl_vwap_d10",
    "any2of3_vwap",
    "any2of3_vwap_d10",
    "score_gte2_vwap",
    "score_gte2_d10",
]


def run_r11_structure_vwap() -> dict[str, pd.DataFrame]:
    trades = pd.read_csv(R11_TRADES)
    trades = trades[trades["fee_compare_leg_key"] == "nq_ny_orb_r11"].copy()
    trades = parse_trade_times(trades)
    trades["gross_r"] = trades["r_multiple"].astype(float)
    trades["net_r"] = trades["net_r_multiple"].astype(float)
    trades["direction_sign"] = np.where(trades["direction"].astype(str).str.lower() == "short", -1, 1)

    session = _r11_session()
    df_5m = load_5m_data("NQ_5m.parquet", start="2016-01-01", end="2026-03-25").sort_index()
    timestamps = df_5m.index
    masks = compute_session_masks(timestamps, session)
    new_day, session_day_id = compute_session_days(timestamps, session)
    high = df_5m["high"].values.astype(np.float64)
    low = df_5m["low"].values.astype(np.float64)
    close = df_5m["close"].values.astype(np.float64)
    volume = df_5m["volume"].values.astype(np.float64)
    vwap = compute_session_vwap(high, low, close, volume, session_day_id)
    daily_atr = compute_daily_atr(df_5m, 12)
    orb_high, orb_low, orb_ready = compute_orb_levels(df_5m, masks["in_orb"], masks["in_rth"], new_day)
    sig = compute_all_15m_signals(df_5m, session, vwap, daily_atr, orb_high, orb_low, orb_ready, session_day_id)

    index = df_5m.index
    gate_positions = []
    gate_times = []
    gate_close = []
    gate_vwap = []
    gate_dist_pct = []
    for entry in trades["entry_local"]:
        gate_ts = pd.Timestamp(entry).floor("5min") - pd.Timedelta(minutes=5)
        pos = int(index.searchsorted(gate_ts, side="right") - 1)
        if pos < 0:
            gate_positions.append(-1)
            gate_times.append(pd.NaT)
            gate_close.append(np.nan)
            gate_vwap.append(np.nan)
            gate_dist_pct.append(np.nan)
            continue
        gate_positions.append(pos)
        gate_times.append(index[pos])
        c = float(sig["close"][pos])
        v = float(sig["vwap"][pos])
        a = float(sig["daily_atr"][pos])
        gate_close.append(c)
        gate_vwap.append(v)
        gate_dist_pct.append((c - v) / a if math.isfinite(v) and math.isfinite(a) and a > 0 else np.nan)

    trades["gate_bar_time"] = gate_times
    trades["gate_bar_pos"] = gate_positions
    trades["gate_close"] = gate_close
    trades["gate_vwap"] = gate_vwap
    trades["gate_vwap_dist_atr"] = gate_dist_pct

    for gate in R11_GATES:
        values = []
        for pos, direction in zip(trades["gate_bar_pos"], trades["direction_sign"]):
            values.append(_gate_eval(gate, sig, int(pos), int(direction)) if int(pos) >= 0 else False)
        trades[gate] = values

    windows = {
        "full": (None, None),
        "pre_2025": (None, pd.Timestamp("2024-12-31")),
        "2024_plus": (pd.Timestamp("2024-01-01"), None),
        "2025_plus": (pd.Timestamp("2025-01-01"), None),
        "last_2y": (trades["exit_day"].max() - pd.DateOffset(years=2) + pd.Timedelta(days=1), None),
        "last_1y": (trades["exit_day"].max() - pd.DateOffset(years=1) + pd.Timedelta(days=1), None),
    }
    metric_rows = []
    fail_rows = []
    for window, (start, end) in windows.items():
        base = trades
        if start is not None:
            base = base[base["exit_day"] >= start]
        if end is not None:
            base = base[base["exit_day"] <= end]
        baseline_m = trade_metrics(base)
        metric_rows.append(
            {
                "window": window,
                "gate": "baseline",
                "deployability": "live_native_current",
                "keep_pct": 100.0,
                "delta_net_r_vs_baseline": 0.0,
                **{k: _round(v, 3) if isinstance(v, float) else v for k, v in baseline_m.items()},
            }
        )
        for gate in R11_GATES:
            kept = base[base[gate]].copy()
            failed = base[~base[gate]].copy()
            m = trade_metrics(kept)
            metric_rows.append(
                {
                    "window": window,
                    "gate": gate,
                    "deployability": "post_filter_only_entry_minus_5m_proxy",
                    "keep_pct": round(len(kept) / len(base) * 100.0, 2) if len(base) else 0.0,
                    "delta_net_r_vs_baseline": round(float(m["net_r"] - baseline_m["net_r"]), 3),
                    **{k: _round(v, 3) if isinstance(v, float) else v for k, v in m.items()},
                }
            )
            if window in {"full", "2025_plus", "last_1y"}:
                fm = trade_metrics(failed)
                fail_rows.append(
                    {
                        "window": window,
                        "gate": gate,
                        "fail_trades": fm["trades"],
                        "fail_net_r": round(fm["net_r"], 3),
                        "fail_pf": round(fm["pf"], 3),
                        "fail_dd_r": round(fm["closed_dd_r"], 3),
                    }
                )

    return {
        "r11_annotated_trades": trades,
        "r11_gate_metrics": pd.DataFrame(metric_rows),
        "r11_gate_fail_buckets": pd.DataFrame(fail_rows),
    }


def read_hunter_trades(candidate_id: str, label: str) -> pd.DataFrame:
    path = HUNTER_TRADE_DIR / f"{candidate_id}.csv"
    df = pd.read_csv(path)
    df["entry_ts_utc"] = pd.to_datetime(df["entry_dt"]).dt.tz_localize(NY_TZ).dt.tz_convert("UTC")
    df["exit_ts_utc"] = pd.to_datetime(df["exit_dt"]).dt.tz_localize(NY_TZ).dt.tz_convert("UTC")
    df["exit_day"] = df["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    df["leg"] = "hunter_025x"
    df["candidate_id"] = candidate_id
    df["candidate_label"] = label
    df["pnl_usd_model"] = df["r"].astype(float) * HUNTER_BASE_RISK_USD * HUNTER_SCALE
    return df.sort_values(["exit_ts_utc", "trade_no"]).reset_index(drop=True)


def normalize_current_alpha_profile(profile: str) -> pd.DataFrame:
    alpha = pd.read_csv(CURRENT_FEE_ALPHA_TRADES)
    alpha = alpha[alpha["profile"] == profile].copy()
    alpha["entry_ts_utc"] = pd.to_datetime(alpha["entry_ts"], utc=True, errors="coerce")
    alpha["exit_ts_utc"] = pd.to_datetime(alpha["exit_ts"], utc=True, errors="coerce")
    alpha = alpha[alpha["exit_ts_utc"].notna()].copy()
    alpha["exit_day"] = alpha["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    alpha["pnl_usd_model"] = alpha["net_pnl_usd"].astype(float)
    alpha["source"] = "alpha_v1_payout_with_fees_20260507"
    return alpha.sort_values(["exit_ts_utc", "leg", "entry_ts_utc"]).reset_index(drop=True)


def portfolio_usd_metrics(trades: pd.DataFrame) -> dict[str, Any]:
    if trades.empty:
        return {"net_usd": 0.0, "dd_usd": 0.0, "worst_month_usd": 0.0, "best_month_usd": 0.0}
    daily = trades.groupby("exit_day")["pnl_usd_model"].sum().sort_index()
    idx = pd.date_range(daily.index.min(), daily.index.max(), freq="D")
    daily = daily.reindex(idx, fill_value=0.0)
    monthly = daily.resample("ME").sum()
    return {
        "net_usd": float(daily.sum()),
        "dd_usd": max_drawdown(daily.to_numpy()),
        "worst_month_usd": float(monthly.min()) if len(monthly) else 0.0,
        "best_month_usd": float(monthly.max()) if len(monthly) else 0.0,
    }


def run_hunter_sidecar() -> dict[str, pd.DataFrame]:
    profile_labels = (
        pd.read_csv(CURRENT_FEE_ALPHA_TRADES)[["profile", "profile_label"]]
        .drop_duplicates()
        .set_index("profile")["profile_label"]
        .to_dict()
    )
    profiles = list(profile_labels)
    hunter_by_candidate = {
        candidate_id: read_hunter_trades(candidate_id, label)
        for candidate_id, label in HUNTER_CANDIDATES.items()
    }

    account_rows = []
    account_details = []
    portfolio_rows = []
    overlap_rows = []
    for profile in profiles:
        alpha = normalize_current_alpha_profile(profile)
        profile_label = profile_labels[profile]
        baseline_daily = alpha.groupby("exit_day")["pnl_usd_model"].sum().sort_index()
        idx = pd.date_range(baseline_daily.index.min(), baseline_daily.index.max(), freq="D")
        baseline_daily = baseline_daily.reindex(idx, fill_value=0.0)

        scenarios: list[tuple[str, str, str, pd.DataFrame]] = [
            ("baseline", "ALPHA_V1 fee-aware baseline", "", alpha)
        ]
        for candidate_id, hunter in hunter_by_candidate.items():
            combined = pd.concat([alpha, hunter], ignore_index=True, sort=False)
            scenarios.append(
                (
                    f"plus_{candidate_id}",
                    f"+ Hunter 0.25x {HUNTER_CANDIDATES[candidate_id]}",
                    candidate_id,
                    combined,
                )
            )

        for scenario, scenario_label, candidate_id, trades in scenarios:
            pm = portfolio_usd_metrics(trades)
            row = {
                "profile": profile,
                "profile_label": profile_label,
                "scenario": scenario,
                "scenario_label": scenario_label,
                "candidate_id": candidate_id,
                **{k: _round(v, 2) for k, v in pm.items()},
            }
            if candidate_id:
                hunter_daily = hunter_by_candidate[candidate_id].groupby("exit_day")["pnl_usd_model"].sum().sort_index()
                hunter_daily = hunter_daily.reindex(idx, fill_value=0.0)
                row["corr_to_alpha_daily"] = round(
                    float(hunter_daily.corr(baseline_daily)),
                    4,
                ) if hunter_daily.std() > 0 and baseline_daily.std() > 0 else 0.0
            else:
                row["corr_to_alpha_daily"] = 0.0
            portfolio_rows.append(row)

            for year, (start, end) in YEAR_WINDOWS.items():
                outcomes = simulate_accounts(trades, start=start, end=end)
                detail = outcomes.copy()
                if not detail.empty:
                    detail["profile"] = profile
                    detail["profile_label"] = profile_label
                    detail["scenario"] = scenario
                    detail["scenario_label"] = scenario_label
                    detail["candidate_id"] = candidate_id
                    detail["year"] = year
                    account_details.append(detail)
                score = score_accounts(outcomes)
                account_rows.append(
                    {
                        "profile": profile,
                        "profile_label": profile_label,
                        "scenario": scenario,
                        "scenario_label": scenario_label,
                        "candidate_id": candidate_id,
                        "year": year,
                        **score,
                    }
                )

        for candidate_id, hunter in hunter_by_candidate.items():
            hunter_daily = hunter.groupby("exit_day")["pnl_usd_model"].sum().sort_index().reindex(idx, fill_value=0.0)
            active = baseline_daily != 0
            hactive = hunter_daily != 0
            both = active & hactive
            overlap_rows.append(
                {
                    "profile": profile,
                    "profile_label": profile_label,
                    "candidate_id": candidate_id,
                    "candidate_label": HUNTER_CANDIDATES[candidate_id],
                    "corr_to_alpha_daily": round(float(hunter_daily.corr(baseline_daily)), 4)
                    if hunter_daily.std() > 0 and baseline_daily.std() > 0
                    else 0.0,
                    "alpha_active_days": int(active.sum()),
                    "hunter_active_days": int(hactive.sum()),
                    "both_active_days": int(both.sum()),
                    "both_losing_days": int(((baseline_daily < 0) & (hunter_daily < 0)).sum()),
                    "both_winning_days": int(((baseline_daily > 0) & (hunter_daily > 0)).sum()),
                    "offset_days": int((both & ((baseline_daily > 0) != (hunter_daily > 0))).sum()),
                    "worst_combined_overlap_usd": round(float((baseline_daily[both] + hunter_daily[both]).min()), 2)
                    if both.any()
                    else 0.0,
                }
            )

    return {
        "hunter_portfolio_metrics": pd.DataFrame(portfolio_rows),
        "hunter_account_scorecard": pd.DataFrame(account_rows),
        "hunter_account_details": pd.concat(account_details, ignore_index=True) if account_details else pd.DataFrame(),
        "hunter_overlap": pd.DataFrame(overlap_rows),
    }


def write_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        path = OUT_DIR / f"{name}.csv"
        df.to_csv(path, index=False)


def build_report(outputs: dict[str, pd.DataFrame], elapsed_sec: float) -> str:
    asia_stream = outputs["asia_stream_metrics"]
    asia_daily = outputs["asia_daily_metrics"]
    asia_overlap = outputs["asia_overlap"]
    asia_accounts = outputs["asia_account_scorecard"]
    r11 = outputs["r11_gate_metrics"]
    hunter_port = outputs["hunter_portfolio_metrics"]
    hunter_accounts = outputs["hunter_account_scorecard"]
    hunter_overlap = outputs["hunter_overlap"]

    asia_daily_rows = []
    for _, row in asia_daily.iterrows():
        asia_daily_rows.append(
            [
                row["label"],
                _fmt_r(row["net_r"]),
                _fmt_r(row["dd_r"]),
                _fmt(row["sharpe_r"], 2),
                _fmt_r(row["worst_month_r"]),
                _fmt_usd(row["weighted_net_usd"]),
                _fmt_usd(row["weighted_dd_usd"]),
            ]
        )

    asia_exit_rows = []
    for _, row in asia_stream.iterrows():
        asia_exit_rows.append(
            [
                row["label"],
                int(row["trades"]),
                _fmt_r(row["net_r"]),
                _fmt_r(row["closed_dd_r"]),
                _fmt_pct(row["win_rate_pct"]),
                _fmt_pct(row["full_target_pct"]),
                _fmt_pct(row["eod_pct"]),
                _fmt_pct(row["sl_pct"]),
            ]
        )

    asia_account_focus = asia_accounts[asia_accounts["year"].isin(["2024", "2025"])]
    asia_account_rows = []
    for _, row in asia_account_focus.iterrows():
        asia_account_rows.append(
            [
                row["label"],
                row["year"],
                int(row["accounts"]),
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    asia_overlap_rows = []
    for _, row in asia_overlap.iterrows():
        asia_overlap_rows.append(
            [
                row["variant"],
                _fmt(row["corr"], 2),
                int(row["both_active_days"]),
                int(row["both_losing_days"]),
                int(row["offset_days"]),
                _fmt_r(row["worst_combined_overlap_r"]),
            ]
        )

    r11_focus = r11[r11["window"].isin(["full", "2025_plus", "last_1y"])].copy()
    baseline_by_window = r11_focus[r11_focus["gate"] == "baseline"].set_index("window")
    # Pick the best full-history gates by net R with at least 35% retention.
    full_gates = r11[(r11["window"] == "full") & (r11["gate"] != "baseline")].copy()
    top_gates = full_gates[full_gates["keep_pct"] >= 35.0].sort_values(
        ["net_r", "closed_dd_r"], ascending=[False, False]
    ).head(6)["gate"].tolist()
    if "baseline" not in top_gates:
        selected_gates = ["baseline", *top_gates]
    else:
        selected_gates = ["baseline", *[g for g in top_gates if g != "baseline"]]

    r11_rows = []
    for gate in selected_gates:
        for window in ["full", "2025_plus", "last_1y"]:
            row = r11[(r11["window"] == window) & (r11["gate"] == gate)].iloc[0]
            base = baseline_by_window.loc[window]
            r11_rows.append(
                [
                    gate,
                    window,
                    int(row["trades"]),
                    _fmt_pct(row["keep_pct"]),
                    _fmt_r(row["net_r"]),
                    _fmt_r(row["net_r"] - base["net_r"]),
                    _fmt(row["pf"], 2),
                    _fmt_r(row["closed_dd_r"]),
                ]
            )

    hunter_focus = hunter_accounts[
        (hunter_accounts["profile"] == "aggressive_sprint")
        & (
            hunter_accounts["scenario"].isin(
                [
                    "baseline",
                    "plus_ema14_tol0_distnone__withTue__1055__rej100__stress",
                    "plus_ema14_tol2_distnone__noTue__1055__rej20__stress",
                    "plus_ema14_tol5_distnone__noTue__1055__rej100__stress",
                ]
            )
        )
        & (hunter_accounts["year"].isin(["2024", "2025"]))
    ]
    hunter_rows = []
    for _, row in hunter_focus.iterrows():
        hunter_rows.append(
            [
                row["scenario_label"],
                row["year"],
                int(row["accounts"]),
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    hunter_port_focus = hunter_port[hunter_port["profile"] == "aggressive_sprint"].copy()
    base_port = hunter_port_focus[hunter_port_focus["scenario"] == "baseline"].iloc[0]
    hunter_port_rows = []
    for _, row in hunter_port_focus.iterrows():
        hunter_port_rows.append(
            [
                row["scenario_label"],
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["net_usd"] - base_port["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt_usd(row["worst_month_usd"]),
                _fmt(row["corr_to_alpha_daily"], 2),
            ]
        )

    hunter_overlap_rows = []
    for _, row in hunter_overlap[hunter_overlap["profile"] == "aggressive_sprint"].iterrows():
        hunter_overlap_rows.append(
            [
                row["candidate_label"],
                _fmt(row["corr_to_alpha_daily"], 2),
                int(row["both_active_days"]),
                int(row["both_losing_days"]),
                int(row["offset_days"]),
                _fmt_usd(row["worst_combined_overlap_usd"]),
            ]
        )

    lines = [
        "# ALPHA_V1 Next-Step Packet (2026-05-16)",
        "",
        f"- Generated: `{pd.Timestamp.now().isoformat(timespec='seconds')}`",
        f"- Results packet: `{OUT_DIR.relative_to(ROOT)}`",
        f"- Repro script: `backtesting/scripts/{Path(__file__).name}`",
        f"- Runtime: `{elapsed_sec:.1f}s`",
        "",
        "## 1. Asia Sleeve Payoff Geometry",
        "",
        "The active ES Asia leg remains the cleaner sleeve fit. ES Asia-B is strong, especially recently, but as a sleeve replacement it turns the Asia pair into two farther-target profiles. The active ES leg supplies the near-target ballast beside NQ Asia's far runner.",
        "",
        "### Standalone Exit Geometry",
        "",
        md_table(
            ["Stream", "Trades", "Net R", "DD", "WR", "Full Target", "EOD", "SL"],
            asia_exit_rows,
        ),
        "",
        "### Sleeve Daily / Risk-Weighted View",
        "",
        "Risk-weighted rows use the current aggressive Asia risks: NQ Asia `$400`, ES Asia / ES Asia-B `$150`.",
        "",
        md_table(
            ["Sleeve", "Net R", "DD R", "Sharpe", "Worst Month R", "Weighted Net", "Weighted DD"],
            asia_daily_rows,
        ),
        "",
        "### Asia Pair Interaction",
        "",
        md_table(
            ["Variant", "Corr", "Both Active", "Both Losing", "Offset Days", "Worst Overlap R"],
            asia_overlap_rows,
        ),
        "",
        "### Asia-Only Phase-One Proxy",
        "",
        md_table(
            ["Sleeve", "Year", "Accounts", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            asia_account_rows,
        ),
        "",
        "## 2. NQ R11 15m Structure + VWAP Gate",
        "",
        "Deployability: `post_filter_only_entry_minus_5m_proxy`. The signals are live-native concepts, but this exact-trade CSV does not carry the original signal bar, so the test uses the previous completed 5m bar before exact entry. A true promotion still needs engine-level replay at signal time.",
        "",
        md_table(
            ["Gate", "Window", "Trades", "Keep", "Net R", "Delta", "PF", "DD"],
            r11_rows,
        ),
        "",
        "## 3. Hunter 0.25x Sidecar on Fee-Aware ALPHA_V1",
        "",
        "Rows below focus on the selected `aggressive_sprint` ALPHA_V1 fee-aware profile. Hunter 0.25x uses the prior downstream convention: Hunter trade R times `$350 * 0.25`.",
        "",
        "### Account Outcomes",
        "",
        md_table(
            ["Scenario", "Year", "Accounts", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            hunter_rows,
        ),
        "",
        "### Portfolio Fit",
        "",
        md_table(
            ["Scenario", "Net", "Delta Net", "DD", "Worst Month", "Corr"],
            hunter_port_rows,
        ),
        "",
        "### Hunter Overlap",
        "",
        md_table(
            ["Candidate", "Corr", "Both Active", "Both Losing", "Offset Days", "Worst Overlap"],
            hunter_overlap_rows,
        ),
        "",
        "## Read",
        "",
        "- Priority 1 does not justify replacing active ES Asia. Keep the current near-target ES Asia + far-runner NQ Asia sleeve logic.",
        "- Priority 2 is only promotable if a gate improves recent R11 quality without gutting trade count; use the table above to decide whether it deserves a true engine replay.",
        "- Priority 3 is a portfolio sidecar test, not a replacement test. If Hunter improves payout clustering without worsening breach clusters, it deserves a paper pilot as `research_only` until live execution parity is explicit.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    started = time.time()
    print("Running ALPHA_V1 next-step packet...", flush=True)

    print("[1/3] Asia sleeve payoff geometry", flush=True)
    outputs = run_asia_sleeve()

    print("[2/3] R11 15m structure + VWAP entry proxy", flush=True)
    outputs.update(run_r11_structure_vwap())

    print("[3/3] Hunter 0.25x sidecar on fee-aware ALPHA_V1", flush=True)
    outputs.update(run_hunter_sidecar())

    elapsed = time.time() - started
    write_outputs(outputs)
    report = build_report(outputs, elapsed)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "elapsed_sec": round(elapsed, 1),
        "paths": {
            "results": str(OUT_DIR),
            "report": str(REPORT_PATH),
        },
        "tables": {name: len(df) for name, df in outputs.items()},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
