#!/usr/bin/env python3
"""ALPHA_V1 priorities 1-5 follow-up packet for 2026-05-16.

Priority order:
1. Hunter live-engine parity.
2. Hunter sidecar sizing around 0.25x.
3. Hunter + ES_NY ATH gate interaction.
4. Updated post-2026-03-24 exact ALPHA_V1 replay.
5. Asia sleeve risk balance.
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
EXEC_SRC = ROOT / "execution" / "src"

for path in (BT_ROOT / "src", SCRIPT_DIR, EXEC_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from run_alpha_v1_next_steps_20260516 import (  # noqa: E402
    FUNDED_MODEL,
    YEAR_WINDOWS,
    _fmt,
    _fmt_pct,
    _fmt_usd,
    max_drawdown,
    md_table,
    score_accounts,
    simulate_accounts,
)
from trader import historical_backtest as hb  # noqa: E402
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, INSTRUMENTS, load_config  # noqa: E402


RUN_SLUG = "alpha_v1_priorities_1_5_20260516"
OUT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_PRIORITIES_1_5_20260516.md"

CURRENT_FEE_ALPHA_TRADES = BT_ROOT / "data/results/alpha_v1_payout_with_fees_20260507/exact_trades_by_profile.csv"
HUNTER_RESEARCH_TRADES = (
    BT_ROOT
    / "data/results/hunter_classic_next_tests_20260502/selected_trades"
    / "ema14_tol0_distnone__withTue__1055__rej100__stress.csv"
)
ATH_0P5_0P75_TRADES = (
    BT_ROOT
    / "data/results/alpha_v1_es_ny_ath_band_sensitivity_20260505"
    / "ALPHA_V1_ES_NY_ATH_0P5_0P75_EXACT_trades.csv"
)

NY_TZ = "America/New_York"
HUNTER_PROFILE = "ALPHA_V1-HUNTER-SAFE-025-SHADOW"
ALPHA_PROFILE = "ALPHA_V1-A"
ALPHA_CACHE_PROFILE = "aggressive_sprint"
ALPHA_START = "2023-01-01"
ALPHA_OLD_END = "2026-03-24"
HUNTER_START = "2016-04-17"
HUNTER_BASE_RISK = 350.0
HUNTER_POINT_VALUE = 2.0
HUNTER_COMMISSION = float(INSTRUMENTS["MNQ"]["commission"])
MES_POINT_VALUE = 5.0
MES_COMMISSION = float(INSTRUMENTS["MES"]["commission"])
MNQ_POINT_VALUE = 2.0
MNQ_COMMISSION = float(INSTRUMENTS["MNQ"]["commission"])

SIDE_CAR_SCALES = [0.125, 0.25, 0.375, 0.50]
NQ_ASIA_RISKS = [250.0, 300.0, 350.0, 400.0, 450.0]
ES_ASIA_RISKS = [100.0, 150.0, 200.0, 250.0]


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _safe_div(num: float, den: float) -> float:
    return float(num / den) if den else 0.0


def _profit_factor(values: Iterable[float]) -> float:
    arr = np.asarray(list(values), dtype=float)
    wins = arr[arr > 0].sum()
    losses = arr[arr < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _raw_path(profile_name: str) -> Path:
    return OUT_DIR / f"{profile_name.replace('.', 'P')}_raw_result.json"


def _run_or_load_exact(
    *,
    config: dict[str, Any],
    profile_name: str,
    start_date: str,
    end_date: str,
    latest_data_ts,
    label: str,
) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _raw_path(profile_name)
    if path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
        print(
            f"{profile_name}: loaded cached trades={result['summary']['total_trades']} "
            f"pnl={result['summary']['total_pnl_usd']:.2f}",
            flush=True,
        )
        return result

    result = run_profile_backtest_sync(
        config=config,
        profile_name=profile_name,
        start_date=start_date,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        label=label,
    )
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"{profile_name}: ran exact trades={result['summary']['total_trades']} "
        f"pnl={result['summary']['total_pnl_usd']:.2f}",
        flush=True,
    )
    return result


def _exact_frame(result: dict[str, Any], *, profile: str, source: str) -> pd.DataFrame:
    df = pd.DataFrame(result["trades"])
    if df.empty:
        return df
    df["profile"] = profile
    df["source"] = source
    df["entry_ts_utc"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
    df["exit_ts_utc"] = pd.to_datetime(df["exit_time"], utc=True, errors="coerce")
    df = df[df["exit_ts_utc"].notna()].copy()
    df["entry_local"] = df["entry_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    df["exit_local"] = df["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    df["exit_day"] = df["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    df["leg"] = df["session"].astype(str)
    df["pnl_usd_model"] = df["pnl_usd"].astype(float)
    df["net_r_model"] = df.get("net_r_multiple", df["r_multiple"]).astype(float)
    return df.sort_values(["entry_ts_utc", "exit_ts_utc", "session"]).reset_index(drop=True)


def _cached_alpha_frame() -> pd.DataFrame:
    df = pd.read_csv(CURRENT_FEE_ALPHA_TRADES)
    df = df[df["profile"] == ALPHA_CACHE_PROFILE].copy()
    df["entry_ts_utc"] = pd.to_datetime(df["entry_ts"], utc=True, errors="coerce")
    df["exit_ts_utc"] = pd.to_datetime(df["exit_ts"], utc=True, errors="coerce")
    df = df[df["exit_ts_utc"].notna()].copy()
    df["entry_local"] = df["entry_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    df["exit_local"] = df["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    df["exit_day"] = df["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    df["pnl_usd_model"] = df["net_pnl_usd"].astype(float)
    df["net_r_model"] = df["net_r_multiple"].astype(float)
    df["source"] = "alpha_v1_payout_with_fees_20260507"
    return df.sort_values(["entry_ts_utc", "exit_ts_utc", "leg"]).reset_index(drop=True)


def _trade_summary(
    df: pd.DataFrame,
    *,
    value_col: str = "pnl_usd_model",
    r_col: str | None = None,
) -> dict[str, Any]:
    if df.empty:
        return {
            "trades": 0,
            "net_usd": 0.0,
            "dd_usd": 0.0,
            "pf_usd": 0.0,
            "win_rate_pct": 0.0,
            "net_r": 0.0,
            "dd_r": 0.0,
        }
    values = df[value_col].astype(float).to_numpy()
    out = {
        "trades": int(len(df)),
        "net_usd": float(values.sum()),
        "dd_usd": max_drawdown(values),
        "pf_usd": _profit_factor(values),
        "win_rate_pct": float((values > 0).mean() * 100.0),
        "net_r": 0.0,
        "dd_r": 0.0,
    }
    if r_col and r_col in df.columns:
        r = df[r_col].astype(float).to_numpy()
        out["net_r"] = float(r.sum())
        out["dd_r"] = max_drawdown(r)
    return out


def _daily_metrics(df: pd.DataFrame, *, value_col: str = "pnl_usd_model") -> dict[str, Any]:
    if df.empty:
        return {
            "net_usd": 0.0,
            "dd_usd": 0.0,
            "worst_month_usd": 0.0,
            "best_month_usd": 0.0,
            "sharpe": 0.0,
        }
    daily = df.groupby("exit_day")[value_col].sum().sort_index()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0.0)
    monthly = daily.resample("ME").sum()
    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    return {
        "net_usd": float(daily.sum()),
        "dd_usd": max_drawdown(daily.to_numpy()),
        "worst_month_usd": float(monthly.min()) if len(monthly) else 0.0,
        "best_month_usd": float(monthly.max()) if len(monthly) else 0.0,
        "sharpe": float(daily.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0,
    }


def _subset(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df[(df["exit_day"] >= pd.Timestamp(start)) & (df["exit_day"] <= pd.Timestamp(end))].copy()


def _sizing_qty(
    risk_points: float,
    *,
    risk_usd: float,
    point_value: float,
    max_single_risk_usd: float,
    max_contracts: float = 20.0,
    min_qty: float = 1.0,
    qty_step: float = 1.0,
) -> float:
    if risk_points <= 0:
        return 0.0
    raw = risk_usd / (risk_points * point_value)
    qty = math.floor(raw / qty_step) * qty_step
    if qty < min_qty:
        single_risk = risk_points * point_value * min_qty
        if single_risk <= max_single_risk_usd:
            qty = min_qty
        else:
            return 0.0
    return min(max_contracts, qty)


def _hunter_live_qty(risk_points: float, *, risk_usd: float, max_contracts: float) -> float:
    if risk_points <= 0:
        return 0.0
    raw_qty = math.floor(risk_usd / (risk_points * HUNTER_POINT_VALUE))
    qty = max(1.0, float(raw_qty))
    return min(max_contracts, qty)


def _revalue_hunter(df: pd.DataFrame, *, scale: float) -> pd.DataFrame:
    risk_usd = HUNTER_BASE_RISK * scale
    max_contracts = math.ceil(20.0 * scale)
    out = df.copy()
    qtys = []
    strict_qtys = []
    effective_risks = []
    strict_dropped = []
    pnls = []
    for row in out.itertuples(index=False):
        risk_points = float(row.risk_points)
        qty = _hunter_live_qty(risk_points, risk_usd=risk_usd, max_contracts=max_contracts)
        strict_qty = _sizing_qty(
            risk_points,
            risk_usd=risk_usd,
            point_value=HUNTER_POINT_VALUE,
            max_single_risk_usd=risk_usd,
            max_contracts=max_contracts,
        )
        gross = float(row.r_multiple) * risk_points * qty * HUNTER_POINT_VALUE
        commission = 2.0 * qty * HUNTER_COMMISSION
        pnl = gross - commission
        qtys.append(qty)
        strict_qtys.append(strict_qty)
        effective_risks.append(risk_points * qty * HUNTER_POINT_VALUE)
        strict_dropped.append(strict_qty <= 0)
        pnls.append(pnl)
    out["scale"] = scale
    out["risk_usd_intended"] = risk_usd
    out["max_contracts_model"] = max_contracts
    out["qty_model"] = qtys
    out["strict_qty_model"] = strict_qtys
    out["strict_would_drop"] = strict_dropped
    out["effective_risk_usd"] = effective_risks
    out["pnl_usd_model"] = pnls
    out["leg"] = f"hunter_{str(scale).replace('.', 'p')}"
    out["net_r_intended"] = out["pnl_usd_model"] / risk_usd
    return out


def _revalue_ath_current(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["entry_ts_utc"] = pd.to_datetime(out["entry_time"], utc=True, errors="coerce")
    out["exit_ts_utc"] = pd.to_datetime(out["exit_time"], utc=True, errors="coerce")
    out = out[out["exit_ts_utc"].notna()].copy()
    out["entry_local"] = out["entry_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    out["exit_local"] = out["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.tz_localize(None)
    out["exit_day"] = out["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    risk_usd = 300.0
    max_single = 450.0
    qtys = []
    pnls = []
    net_rs = []
    for row in out.itertuples(index=False):
        risk_points = float(row.risk_points)
        qty = _sizing_qty(
            risk_points,
            risk_usd=risk_usd,
            point_value=MES_POINT_VALUE,
            max_single_risk_usd=max_single,
            max_contracts=20.0,
        )
        gross_risk = risk_points * qty * MES_POINT_VALUE
        gross = float(row.r_multiple) * gross_risk
        commission = 2.0 * qty * MES_COMMISSION
        pnl = gross - commission
        qtys.append(qty)
        pnls.append(pnl)
        net_rs.append(pnl / gross_risk if gross_risk > 0 else 0.0)
    out["qty_current_risk"] = qtys
    out["pnl_usd_model"] = pnls
    out["net_r_model"] = net_rs
    out["leg"] = "es_ny_ath_0p5_0p75"
    out["source"] = "alpha_v1_es_ny_ath_band_sensitivity_20260505_revalued_to_300_fee"
    return out[out["qty_current_risk"] > 0].sort_values(["entry_ts_utc", "exit_ts_utc"]).reset_index(drop=True)


def _revalue_orb_leg(
    df: pd.DataFrame,
    *,
    risk_usd: float,
    point_value: float,
    commission: float,
    leg_name: str,
) -> pd.DataFrame:
    out = df.copy()
    max_single = 1.5 * risk_usd
    qtys = []
    pnls = []
    kept = []
    for row in out.itertuples(index=False):
        risk_points = float(row.risk_points)
        qty = _sizing_qty(
            risk_points,
            risk_usd=risk_usd,
            point_value=point_value,
            max_single_risk_usd=max_single,
            max_contracts=20.0,
        )
        gross_risk = risk_points * qty * point_value
        pnl = float(row.r_multiple) * gross_risk - 2.0 * qty * commission
        qtys.append(qty)
        pnls.append(pnl)
        kept.append(qty > 0)
    out["leg"] = leg_name
    out["qty_model"] = qtys
    out["pnl_usd_model"] = pnls
    out["risk_usd_model"] = risk_usd
    return out[kept].copy()


def run_priority_1_hunter_parity(hunter_exact: pd.DataFrame) -> dict[str, pd.DataFrame]:
    research = pd.read_csv(HUNTER_RESEARCH_TRADES)
    research["entry_local"] = pd.to_datetime(research["entry_dt"], errors="coerce")
    research["exit_local"] = pd.to_datetime(research["exit_dt"], errors="coerce")
    research = research[research["exit_local"].notna()].copy()
    research["entry_ts_utc"] = research["entry_local"].dt.tz_localize(NY_TZ).dt.tz_convert("UTC")
    research["exit_ts_utc"] = research["exit_local"].dt.tz_localize(NY_TZ).dt.tz_convert("UTC")
    research["exit_day"] = research["exit_ts_utc"].dt.tz_convert(NY_TZ).dt.normalize().dt.tz_localize(None)
    research["date"] = research["entry_local"].dt.date.astype(str)
    research["direction"] = research["side"].str.lower().map({"long": "long", "short": "short"})
    research["original_pnl_usd"] = research["pnl_usd"].astype(float)
    research["net_r_model"] = research["r"].astype(float)
    research["pnl_usd_model"] = research["net_r_model"] * HUNTER_BASE_RISK * 0.25
    research["leg"] = "hunter_research_10y_safe"

    overlap_start = max(pd.Timestamp(hunter_exact["entry_local"].min()).date().isoformat(), research["date"].min())
    overlap_end = min(pd.Timestamp(hunter_exact["entry_local"].max()).date().isoformat(), research["date"].max())

    exact_overlap = hunter_exact[
        (hunter_exact["entry_local"] >= pd.Timestamp(overlap_start))
        & (hunter_exact["entry_local"] <= pd.Timestamp(overlap_end) + pd.Timedelta(days=1))
    ].copy()
    research_overlap = research[(research["date"] >= overlap_start) & (research["date"] <= overlap_end)].copy()

    def keyed(frame: pd.DataFrame, target_col: str) -> pd.DataFrame:
        out = frame.copy()
        out["entry_price_key"] = out["entry_price"].astype(float).round(2)
        out["stop_price_key"] = out["stop_price"].astype(float).round(2)
        out["target_key"] = out[target_col].astype(float).round(2)
        out["key_date"] = pd.to_datetime(out["entry_local"]).dt.date.astype(str)
        out["match_key"] = (
            out["key_date"]
            + "|"
            + out["direction"].astype(str)
            + "|"
            + out["entry_price_key"].astype(str)
            + "|"
            + out["stop_price_key"].astype(str)
            + "|"
            + out["target_key"].astype(str)
        )
        out["match_n"] = out.groupby("match_key").cumcount()
        return out

    exact_keyed = keyed(exact_overlap, "tp2_price")
    research_keyed = keyed(research_overlap, "target_price")
    match_cols = ["match_key", "match_n"]
    matched = exact_keyed.merge(
        research_keyed,
        on=match_cols,
        how="inner",
        suffixes=("_exact", "_research"),
    )
    exact_keys = exact_keyed[match_cols + ["entry_local", "direction", "entry_price", "stop_price", "tp2_price"]]
    research_keys = research_keyed[match_cols + ["entry_local", "direction", "entry_price", "stop_price", "target_price"]]
    exact_only = exact_keys.merge(research_keyed[match_cols], on=match_cols, how="left", indicator=True)
    exact_only = exact_only[exact_only["_merge"] == "left_only"].drop(columns=["_merge"])
    research_only = research_keys.merge(exact_keyed[match_cols], on=match_cols, how="left", indicator=True)
    research_only = research_only[research_only["_merge"] == "left_only"].drop(columns=["_merge"])

    rows = []
    for label, frame, value_col, r_col in [
        ("live_engine_exact_shadow_025", exact_overlap, "pnl_usd_model", "net_r_model"),
        ("research_selected_10y_safe", research_overlap, "pnl_usd_model", "net_r_model"),
    ]:
        m = _trade_summary(frame, value_col=value_col, r_col=r_col)
        rows.append(
            {
                "stream": label,
                "start": overlap_start,
                "end": overlap_end,
                "trades": m["trades"],
                "net_usd": round(m["net_usd"], 2),
                "dd_usd": round(m["dd_usd"], 2),
                "pf_usd": round(m["pf_usd"], 3),
                "net_r": round(m["net_r"], 3),
                "dd_r": round(m["dd_r"], 3),
                "win_rate_pct": round(m["win_rate_pct"], 2),
            }
        )
    rows.append(
        {
            "stream": "fuzzy_same_setup_match",
            "start": overlap_start,
            "end": overlap_end,
            "trades": int(len(matched)),
            "net_usd": 0.0,
            "dd_usd": 0.0,
            "pf_usd": 0.0,
            "net_r": 0.0,
            "dd_r": 0.0,
            "win_rate_pct": round(_safe_div(len(matched), len(research_overlap)) * 100.0, 2),
        }
    )
    parity = pd.DataFrame(rows)
    counts = pd.DataFrame(
        [
            {
                "overlap_start": overlap_start,
                "overlap_end": overlap_end,
                "exact_trades": int(len(exact_overlap)),
                "research_trades": int(len(research_overlap)),
                "fuzzy_matched_trades": int(len(matched)),
                "exact_only": int(len(exact_only)),
                "research_only": int(len(research_only)),
                "match_rate_vs_research_pct": round(_safe_div(len(matched), len(research_overlap)) * 100.0, 2),
                "match_rate_vs_exact_pct": round(_safe_div(len(matched), len(exact_overlap)) * 100.0, 2),
            }
        ]
    )
    return {
        "hunter_parity_summary": parity,
        "hunter_parity_counts": counts,
        "hunter_parity_matched": matched,
        "hunter_parity_exact_only": exact_only.head(500),
        "hunter_parity_research_only": research_only.head(500),
        "hunter_research_normalized": research,
    }


def _portfolio_score_rows(
    scenarios: list[tuple[str, str, pd.DataFrame]],
    *,
    windows: dict[str, tuple[str, str]],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    portfolio_rows = []
    account_rows = []
    details = []
    for key, label, trades in scenarios:
        dm = _daily_metrics(trades)
        portfolio_rows.append(
            {
                "scenario": key,
                "label": label,
                **{name: _round(value, 3) for name, value in dm.items()},
            }
        )
        for year, (start, end) in windows.items():
            outcomes = simulate_accounts(trades, start=start, end=end)
            if not outcomes.empty:
                detail = outcomes.copy()
                detail["scenario"] = key
                detail["label"] = label
                detail["year"] = year
                details.append(detail)
            account_rows.append({"scenario": key, "label": label, "year": year, **score_accounts(outcomes)})
    return (
        pd.DataFrame(portfolio_rows),
        pd.DataFrame(account_rows),
        pd.concat(details, ignore_index=True) if details else pd.DataFrame(),
    )


def run_priority_2_hunter_sizing(
    *,
    hunter_exact: pd.DataFrame,
    alpha_cached: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    sizing_rows = []
    revalued_parts = []
    scenarios = [("baseline", "ALPHA_V1 cached fee-aware", alpha_cached)]
    for scale in SIDE_CAR_SCALES:
        hunter = _revalue_hunter(hunter_exact, scale=scale)
        revalued_parts.append(hunter)
        m = _trade_summary(hunter, value_col="pnl_usd_model", r_col="net_r_intended")
        sizing_rows.append(
            {
                "scale": scale,
                "risk_usd_intended": HUNTER_BASE_RISK * scale,
                "max_contracts": int(math.ceil(20.0 * scale)),
                "trades": m["trades"],
                "net_usd": round(m["net_usd"], 2),
                "dd_usd": round(m["dd_usd"], 2),
                "pf_usd": round(m["pf_usd"], 3),
                "net_intended_r": round(m["net_r"], 3),
                "dd_intended_r": round(m["dd_r"], 3),
                "avg_effective_risk_usd": round(float(hunter["effective_risk_usd"].mean()), 2),
                "p95_effective_risk_usd": round(float(hunter["effective_risk_usd"].quantile(0.95)), 2),
                "max_effective_risk_usd": round(float(hunter["effective_risk_usd"].max()), 2),
                "over_intended_risk_pct": round(
                    float((hunter["effective_risk_usd"] > hunter["risk_usd_intended"]).mean() * 100.0),
                    2,
                ),
                "strict_cap_would_drop_pct": round(float(hunter["strict_would_drop"].mean() * 100.0), 2),
            }
        )
        combined = pd.concat([alpha_cached, _subset(hunter, ALPHA_START, ALPHA_OLD_END)], ignore_index=True, sort=False)
        scenarios.append((f"plus_hunter_{scale}", f"ALPHA_V1 + Hunter {scale:.3g}x actual engine sizing", combined))

    portfolio, accounts, details = _portfolio_score_rows(scenarios, windows=YEAR_WINDOWS)
    return {
        "hunter_sizing_grid": pd.DataFrame(sizing_rows),
        "hunter_revalued_trades": pd.concat(revalued_parts, ignore_index=True) if revalued_parts else pd.DataFrame(),
        "hunter_sidecar_portfolio": portfolio,
        "hunter_sidecar_account_scorecard": accounts,
        "hunter_sidecar_account_details": details,
    }


def run_priority_3_hunter_ath_interaction(
    *,
    alpha_cached: pd.DataFrame,
    hunter_025: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    ath_raw = pd.read_csv(ATH_0P5_0P75_TRADES)
    ath = _revalue_ath_current(ath_raw)
    ath = _subset(ath, ALPHA_START, ALPHA_OLD_END)
    hunter = _subset(hunter_025, ALPHA_START, ALPHA_OLD_END)
    alpha_no_esny = alpha_cached[alpha_cached["leg"] != "es_ny_orb"].copy()
    ath_replacement = pd.concat([alpha_no_esny, ath], ignore_index=True, sort=False)

    scenarios = [
        ("baseline", "ALPHA_V1 cached fee-aware", alpha_cached),
        ("plus_hunter_025", "ALPHA_V1 + Hunter 0.25x actual", pd.concat([alpha_cached, hunter], ignore_index=True, sort=False)),
        ("esny_ath_replacement", "ALPHA_V1 with ES_NY ATH 0.50-0.75 replacement", ath_replacement),
        (
            "esny_ath_replacement_plus_hunter_025",
            "ALPHA_V1 ES_NY ATH replacement + Hunter 0.25x actual",
            pd.concat([ath_replacement, hunter], ignore_index=True, sort=False),
        ),
    ]
    portfolio, accounts, details = _portfolio_score_rows(scenarios, windows=YEAR_WINDOWS)

    esny_base = alpha_cached[alpha_cached["leg"] == "es_ny_orb"].copy()
    leg_rows = []
    for label, frame in [("current_es_ny", esny_base), ("ath_0p5_0p75_revalued", ath)]:
        m = _trade_summary(frame, value_col="pnl_usd_model", r_col="net_r_model")
        leg_rows.append(
            {
                "stream": label,
                "trades": m["trades"],
                "net_usd": round(m["net_usd"], 2),
                "dd_usd": round(m["dd_usd"], 2),
                "pf_usd": round(m["pf_usd"], 3),
                "net_r": round(m["net_r"], 3),
                "dd_r": round(m["dd_r"], 3),
                "win_rate_pct": round(m["win_rate_pct"], 2),
            }
        )
    return {
        "esny_ath_revalued_trades": ath,
        "esny_ath_leg_comparison": pd.DataFrame(leg_rows),
        "hunter_ath_portfolio": portfolio,
        "hunter_ath_account_scorecard": accounts,
        "hunter_ath_account_details": details,
    }


def run_priority_4_updated_replay(
    *,
    alpha_updated: pd.DataFrame,
    alpha_cached: pd.DataFrame,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    windows = {
        "cached_overlap": (alpha_cached, ALPHA_START, ALPHA_OLD_END, "cached_fee_20260507"),
        "updated_overlap": (alpha_updated, ALPHA_START, ALPHA_OLD_END, "updated_exact"),
        "updated_post_2026_03_24": (alpha_updated, "2026-03-25", end_date, "updated_exact"),
        "updated_full": (alpha_updated, ALPHA_START, end_date, "updated_exact"),
    }
    rows = []
    leg_rows = []
    for window, (frame, start, end, source) in windows.items():
        subset = _subset(frame, start, end)
        m = _trade_summary(subset, value_col="pnl_usd_model", r_col="net_r_model")
        rows.append(
            {
                "window": window,
                "source": source,
                "start": start,
                "end": end,
                "trades": m["trades"],
                "net_usd": round(m["net_usd"], 2),
                "dd_usd": round(m["dd_usd"], 2),
                "pf_usd": round(m["pf_usd"], 3),
                "net_r": round(m["net_r"], 3),
                "dd_r": round(m["dd_r"], 3),
                "win_rate_pct": round(m["win_rate_pct"], 2),
            }
        )
        for leg, group in subset.groupby("leg", sort=True):
            lm = _trade_summary(group, value_col="pnl_usd_model", r_col="net_r_model")
            leg_rows.append(
                {
                    "window": window,
                    "source": source,
                    "leg": leg,
                    "trades": lm["trades"],
                    "net_usd": round(lm["net_usd"], 2),
                    "dd_usd": round(lm["dd_usd"], 2),
                    "pf_usd": round(lm["pf_usd"], 3),
                    "net_r": round(lm["net_r"], 3),
                    "dd_r": round(lm["dd_r"], 3),
                }
            )

    updated_windows = {
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026_updated": ("2026-01-01", end_date),
    }
    scenarios = [("updated_alpha", f"Updated ALPHA_V1 exact through {end_date}", alpha_updated)]
    portfolio, accounts, details = _portfolio_score_rows(scenarios, windows=updated_windows)
    return {
        "alpha_updated_window_summary": pd.DataFrame(rows),
        "alpha_updated_leg_summary": pd.DataFrame(leg_rows),
        "alpha_updated_portfolio": portfolio,
        "alpha_updated_account_scorecard": accounts,
        "alpha_updated_account_details": details,
    }


def run_priority_5_asia_risk_balance(
    *,
    alpha_updated: pd.DataFrame,
    end_date: str,
) -> dict[str, pd.DataFrame]:
    base = alpha_updated.copy()
    fixed = base[~base["session"].isin(["NQ_Asia", "ES_Asia"])].copy()
    nq_asia = base[base["session"] == "NQ_Asia"].copy()
    es_asia = base[base["session"] == "ES_Asia"].copy()

    windows = {
        "2024": ("2024-01-01", "2024-12-31"),
        "2025": ("2025-01-01", "2025-12-31"),
        "2026_updated": ("2026-01-01", end_date),
    }

    grid_rows = []
    account_rows = []
    details = []
    for nq_risk in NQ_ASIA_RISKS:
        for es_risk in ES_ASIA_RISKS:
            nq_leg = _revalue_orb_leg(
                nq_asia,
                risk_usd=nq_risk,
                point_value=MNQ_POINT_VALUE,
                commission=MNQ_COMMISSION,
                leg_name="nq_asia_orb",
            )
            es_leg = _revalue_orb_leg(
                es_asia,
                risk_usd=es_risk,
                point_value=MES_POINT_VALUE,
                commission=MES_COMMISSION,
                leg_name="es_asia_orb",
            )
            combined = pd.concat([fixed, nq_leg, es_leg], ignore_index=True, sort=False)
            dm = _daily_metrics(combined)
            combo = f"nq{int(nq_risk)}_es{int(es_risk)}"
            grid_rows.append(
                {
                    "combo": combo,
                    "nq_asia_risk": nq_risk,
                    "es_asia_risk": es_risk,
                    "net_usd": round(dm["net_usd"], 2),
                    "dd_usd": round(dm["dd_usd"], 2),
                    "worst_month_usd": round(dm["worst_month_usd"], 2),
                    "sharpe": round(dm["sharpe"], 3),
                    "nq_trades": int(len(nq_leg)),
                    "es_trades": int(len(es_leg)),
                }
            )
            for year, (start, end) in windows.items():
                outcomes = simulate_accounts(combined, start=start, end=end)
                if not outcomes.empty:
                    detail = outcomes.copy()
                    detail["combo"] = combo
                    detail["nq_asia_risk"] = nq_risk
                    detail["es_asia_risk"] = es_risk
                    detail["year"] = year
                    details.append(detail)
                account_rows.append(
                    {
                        "combo": combo,
                        "nq_asia_risk": nq_risk,
                        "es_asia_risk": es_risk,
                        "year": year,
                        **score_accounts(outcomes),
                    }
                )

    grid = pd.DataFrame(grid_rows)
    accounts = pd.DataFrame(account_rows)
    rank_rows = []
    for combo, group in accounts.groupby("combo", sort=False):
        focus = group[group["year"].isin(["2024", "2025"])]
        row = grid[grid["combo"] == combo].iloc[0].to_dict()
        payout = focus["resolved_payout_rate_pct"].astype(float)
        breach = focus["resolved_breach_rate_pct"].astype(float)
        days = focus["avg_days_to_payout"].dropna().astype(float)
        row.update(
            {
                "avg_2024_2025_payout_pct": round(float(payout.mean()), 2),
                "max_2024_2025_breach_pct": round(float(breach.max()), 2),
                "avg_2024_2025_days_to_payout": round(float(days.mean()), 1) if len(days) else None,
                "avg_2024_2025_ev_per_start": round(float(focus["ev_per_start_usd"].astype(float).mean()), 2),
            }
        )
        row["rank_score"] = (
            row["avg_2024_2025_payout_pct"]
            - row["max_2024_2025_breach_pct"] * 1.5
            - _safe_div(row["avg_2024_2025_days_to_payout"] or 250.0, 10.0)
            + _safe_div(row["net_usd"], 10_000.0)
        )
        rank_rows.append(row)
    ranking = pd.DataFrame(rank_rows).sort_values(
        ["rank_score", "avg_2024_2025_payout_pct", "net_usd"],
        ascending=[False, False, False],
    )
    return {
        "asia_risk_grid": grid,
        "asia_risk_account_scorecard": accounts,
        "asia_risk_account_details": pd.concat(details, ignore_index=True) if details else pd.DataFrame(),
        "asia_risk_ranking": ranking,
    }


def write_outputs(outputs: dict[str, pd.DataFrame]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, df in outputs.items():
        df.to_csv(OUT_DIR / f"{name}.csv", index=False)


def build_report(outputs: dict[str, pd.DataFrame], *, elapsed_sec: float, alpha_end: str, hunter_end: str) -> str:
    parity = outputs["hunter_parity_summary"]
    parity_counts = outputs["hunter_parity_counts"].iloc[0]
    sizing = outputs["hunter_sizing_grid"]
    sidecar_port = outputs["hunter_sidecar_portfolio"]
    sidecar_acct = outputs["hunter_sidecar_account_scorecard"]
    ath_leg = outputs["esny_ath_leg_comparison"]
    ath_port = outputs["hunter_ath_portfolio"]
    ath_acct = outputs["hunter_ath_account_scorecard"]
    updated = outputs["alpha_updated_window_summary"]
    updated_leg = outputs["alpha_updated_leg_summary"]
    updated_acct = outputs["alpha_updated_account_scorecard"]
    asia_rank = outputs["asia_risk_ranking"]
    asia_acct = outputs["asia_risk_account_scorecard"]

    parity_rows = []
    for _, row in parity.iterrows():
        parity_rows.append(
            [
                row["stream"],
                int(row["trades"]),
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt(row["pf_usd"], 2),
                _fmt(row["net_r"], 1),
                _fmt(row["dd_r"], 1),
                _fmt_pct(row["win_rate_pct"]),
            ]
        )

    sizing_rows = []
    for _, row in sizing.iterrows():
        sizing_rows.append(
            [
                f"{row['scale']:.3g}x",
                _fmt_usd(row["risk_usd_intended"], 2),
                int(row["max_contracts"]),
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt(row["pf_usd"], 2),
                _fmt_usd(row["avg_effective_risk_usd"], 2),
                _fmt_usd(row["p95_effective_risk_usd"], 2),
                _fmt_pct(row["over_intended_risk_pct"]),
                _fmt_pct(row["strict_cap_would_drop_pct"]),
            ]
        )

    sidecar_rows = []
    base_port = sidecar_port[sidecar_port["scenario"] == "baseline"].iloc[0]
    focus_scenarios = {"baseline", "plus_hunter_0.125", "plus_hunter_0.25", "plus_hunter_0.375", "plus_hunter_0.5"}
    for _, row in sidecar_port[sidecar_port["scenario"].isin(focus_scenarios)].iterrows():
        sidecar_rows.append(
            [
                row["label"],
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["net_usd"] - base_port["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt_usd(row["worst_month_usd"]),
                _fmt(row["sharpe"], 2),
            ]
        )

    sidecar_acct_rows = []
    for _, row in sidecar_acct[
        sidecar_acct["scenario"].isin(["baseline", "plus_hunter_0.25"])
        & sidecar_acct["year"].isin(["2024", "2025", "2026_YTD"])
    ].iterrows():
        sidecar_acct_rows.append(
            [
                row["label"],
                row["year"],
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    ath_leg_rows = []
    for _, row in ath_leg.iterrows():
        ath_leg_rows.append(
            [
                row["stream"],
                int(row["trades"]),
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt(row["pf_usd"], 2),
                _fmt(row["net_r"], 1),
                _fmt(row["dd_r"], 1),
            ]
        )

    ath_port_rows = []
    base_ath = ath_port[ath_port["scenario"] == "baseline"].iloc[0]
    for _, row in ath_port.iterrows():
        ath_port_rows.append(
            [
                row["label"],
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["net_usd"] - base_ath["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt_usd(row["worst_month_usd"]),
                _fmt(row["sharpe"], 2),
            ]
        )

    ath_acct_rows = []
    for _, row in ath_acct[
        ath_acct["scenario"].isin(["baseline", "esny_ath_replacement", "esny_ath_replacement_plus_hunter_025"])
        & ath_acct["year"].isin(["2024", "2025"])
    ].iterrows():
        ath_acct_rows.append(
            [
                row["label"],
                row["year"],
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    updated_rows = []
    for _, row in updated.iterrows():
        updated_rows.append(
            [
                row["window"],
                row["source"],
                int(row["trades"]),
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt(row["pf_usd"], 2),
                _fmt(row["net_r"], 1),
            ]
        )

    updated_leg_focus = updated_leg[updated_leg["window"].isin(["updated_post_2026_03_24", "updated_full"])]
    updated_leg_rows = []
    for _, row in updated_leg_focus.iterrows():
        updated_leg_rows.append(
            [
                row["window"],
                row["leg"],
                int(row["trades"]),
                _fmt_usd(row["net_usd"]),
                _fmt(row["pf_usd"], 2),
                _fmt(row["net_r"], 1),
            ]
        )

    updated_acct_rows = []
    for _, row in updated_acct.iterrows():
        updated_acct_rows.append(
            [
                row["year"],
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    asia_rows = []
    for _, row in asia_rank.head(8).iterrows():
        asia_rows.append(
            [
                row["combo"],
                _fmt_usd(row["nq_asia_risk"], 0),
                _fmt_usd(row["es_asia_risk"], 0),
                _fmt_pct(row["avg_2024_2025_payout_pct"]),
                _fmt_pct(row["max_2024_2025_breach_pct"]),
                _fmt(row["avg_2024_2025_days_to_payout"], 1),
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["dd_usd"]),
            ]
        )
    current_combo = "nq400_es150"
    asia_current_rows = []
    for _, row in asia_acct[asia_acct["combo"] == current_combo].iterrows():
        asia_current_rows.append(
            [
                row["year"],
                _fmt_pct(row["resolved_payout_rate_pct"]),
                _fmt_pct(row["resolved_breach_rate_pct"]),
                _fmt(row["avg_days_to_payout"], 1),
                int(row["max_consecutive_breaches"]),
                _fmt_usd(row["ev_per_start_usd"]),
            ]
        )

    lines = [
        "# ALPHA_V1 Priorities 1-5 Packet (2026-05-16)",
        "",
        f"- Generated: `{pd.Timestamp.now().isoformat(timespec='seconds')}`",
        f"- Results packet: `{OUT_DIR.relative_to(ROOT)}`",
        f"- Repro script: `backtesting/scripts/{Path(__file__).name}`",
        f"- Runtime: `{elapsed_sec:.1f}s`",
        f"- Hunter exact latest NQ end: `{hunter_end}`",
        f"- Updated ALPHA exact latest common NQ/ES end: `{alpha_end}`",
        "",
        "## 1. Hunter Live-Engine Parity",
        "",
        (
            "The live `hunter_orb` replay does not match the original research-selected Hunter stream closely enough "
            "to treat the prior downstream read as confirmed parity."
        ),
        "",
        md_table(
            ["Stream", "Trades", "Net", "DD", "PF", "Net R", "DD R", "WR"],
            parity_rows,
        ),
        "",
        (
            f"Fuzzy same-setup match: `{int(parity_counts['fuzzy_matched_trades'])}` matched, "
            f"`{int(parity_counts['exact_only'])}` exact-only, `{int(parity_counts['research_only'])}` research-only "
            f"over `{parity_counts['overlap_start']}` to `{parity_counts['overlap_end']}`."
        ),
        "",
        "Deployability: `live_native` for the shadow engine profile, but `exact_replay_required=failed_parity_investigation` before sizing decisions should lean on the old research CSV.",
        "",
        "## 2. Hunter Sidecar Sizing Around 0.25x",
        "",
        (
            "This uses actual current Hunter engine sizing behavior. The important artifact is the contract floor: "
            "`risk_usd=$87.50` can still trade 1 MNQ even when the stop risk is wider than the intended risk."
        ),
        "",
        md_table(
            ["Scale", "Intended Risk", "Max C", "Net", "DD", "PF", "Avg Eff Risk", "P95 Eff Risk", "Over Intended", "Strict Drops"],
            sizing_rows,
        ),
        "",
        "### Cached ALPHA_V1 Portfolio Fit",
        "",
        md_table(
            ["Scenario", "Net", "Delta", "DD", "Worst Month", "Sharpe"],
            sidecar_rows,
        ),
        "",
        "### 0.25x Account Outcomes",
        "",
        md_table(
            ["Scenario", "Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            sidecar_acct_rows,
        ),
        "",
        "## 3. Hunter + ES_NY ATH Gate Interaction",
        "",
        (
            "The ATH leg was revalued to current ALPHA_V1 ES_NY risk (`$300`) with current MES fees before replacing "
            "the baseline ES_NY stream."
        ),
        "",
        md_table(
            ["ES_NY Stream", "Trades", "Net", "DD", "PF", "Net R", "DD R"],
            ath_leg_rows,
        ),
        "",
        md_table(
            ["Scenario", "Net", "Delta", "DD", "Worst Month", "Sharpe"],
            ath_port_rows,
        ),
        "",
        md_table(
            ["Scenario", "Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            ath_acct_rows,
        ),
        "",
        "## 4. Updated Post-2026-03-24 Exact Replay",
        "",
        (
            "Post-March replay is bounded by local ES data availability: `latest_common_end(['NQ', 'ES'])` "
            f"returned `{alpha_end}`. NQ has newer local data, but the combined ALPHA exact path cannot move past ES."
        ),
        "",
        md_table(
            ["Window", "Source", "Trades", "Net", "DD", "PF", "Net R"],
            updated_rows,
        ),
        "",
        md_table(
            ["Window", "Leg", "Trades", "Net", "PF", "Net R"],
            updated_leg_rows,
        ),
        "",
        md_table(
            ["Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            updated_acct_rows,
        ),
        "",
        "## 5. Asia Sleeve Risk Balance",
        "",
        (
            "Grid varies only the Asia risks on the updated exact ALPHA stream. Other legs remain fixed. "
            "Ranking emphasizes 2024-2025 payout quality, breach control, and payout speed."
        ),
        "",
        md_table(
            ["Combo", "NQ Asia", "ES Asia", "24-25 Payout", "Max Breach", "Avg PayD", "Net", "DD"],
            asia_rows,
        ),
        "",
        "Current combo (`NQ Asia $400 / ES Asia $150`) account read:",
        "",
        md_table(
            ["Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"],
            asia_current_rows,
        ),
        "",
        "## Read",
        "",
        "- Priority 1 is the gating result: Hunter is still interesting, but the prior research stream and live engine stream are not the same thing.",
        "- Priority 2 says the `0.25x` label is not a clean proportional risk label under current Hunter sizing because of the 1-MNQ floor.",
        "- Priority 3 should be judged on the revalued portfolio/account tables, not the old `$400` ATH file.",
        "- Priority 4 gives the current exact ALPHA reference through the latest common local data.",
        "- Priority 5 keeps the Asia-risk question bounded to risk balance only; no Asia parameter changes were searched.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)

    print("[1/5] Running/loading Hunter live-engine exact replay", flush=True)
    hunter_latest = latest_common_end(["NQ"])
    hunter_end = hunter_latest.date().isoformat()
    hunter_result = _run_or_load_exact(
        config=config,
        profile_name=HUNTER_PROFILE,
        start_date=HUNTER_START,
        end_date=hunter_end,
        latest_data_ts=hunter_latest,
        label=f"EXEC EXACT {HUNTER_PROFILE} {HUNTER_START} to {hunter_end}",
    )
    hunter_exact = _exact_frame(hunter_result, profile=HUNTER_PROFILE, source=RUN_SLUG)
    hunter_exact.to_csv(OUT_DIR / "hunter_live_exact_trades.csv", index=False)
    outputs = run_priority_1_hunter_parity(hunter_exact)

    alpha_cached = _cached_alpha_frame()
    print("[2/5] Scoring Hunter sidecar sizing around 0.25x", flush=True)
    outputs.update(run_priority_2_hunter_sizing(hunter_exact=hunter_exact, alpha_cached=alpha_cached))

    hunter_025 = outputs["hunter_revalued_trades"][outputs["hunter_revalued_trades"]["scale"] == 0.25].copy()
    print("[3/5] Scoring Hunter + ES_NY ATH interaction", flush=True)
    outputs.update(run_priority_3_hunter_ath_interaction(alpha_cached=alpha_cached, hunter_025=hunter_025))

    print("[4/5] Running/loading updated ALPHA_V1 exact replay", flush=True)
    alpha_latest = latest_common_end(["NQ", "ES"])
    alpha_end = alpha_latest.date().isoformat()
    alpha_result = _run_or_load_exact(
        config=config,
        profile_name=ALPHA_PROFILE,
        start_date=ALPHA_START,
        end_date=alpha_end,
        latest_data_ts=alpha_latest,
        label=f"EXEC EXACT {ALPHA_PROFILE} {ALPHA_START} to {alpha_end}",
    )
    alpha_updated = _exact_frame(alpha_result, profile=ALPHA_PROFILE, source=RUN_SLUG)
    session_to_leg = {
        "NQ_NY": "nq_ny_orb_r11",
        "NQ_Asia": "nq_asia_orb",
        "ES_Asia": "es_asia_orb",
        "ES_NY": "es_ny_orb",
        "NQ_NY_LSI": "nq_ny_htf_lsi",
    }
    alpha_updated["leg"] = alpha_updated["session"].map(session_to_leg).fillna(alpha_updated["session"])
    alpha_updated.to_csv(OUT_DIR / "alpha_v1_updated_exact_trades.csv", index=False)
    outputs.update(run_priority_4_updated_replay(alpha_updated=alpha_updated, alpha_cached=alpha_cached, end_date=alpha_end))

    print("[5/5] Sweeping Asia sleeve risk balance", flush=True)
    outputs.update(run_priority_5_asia_risk_balance(alpha_updated=alpha_updated, end_date=alpha_end))

    write_outputs(outputs)
    elapsed = time.time() - started
    report = build_report(outputs, elapsed_sec=elapsed, alpha_end=alpha_end, hunter_end=hunter_end)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    summary = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "elapsed_sec": round(elapsed, 1),
        "paths": {
            "results": str(OUT_DIR),
            "report": str(REPORT_PATH),
        },
        "hunter_end": hunter_end,
        "alpha_end": alpha_end,
        "tables": {name: int(len(df)) for name, df in outputs.items()},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
