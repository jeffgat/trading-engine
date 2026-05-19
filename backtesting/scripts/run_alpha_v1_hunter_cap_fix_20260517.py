#!/usr/bin/env python3
"""Rerun Hunter 0.25x after enforcing max_single_risk_usd sizing cap."""

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
    YEAR_WINDOWS,
    _fmt,
    _fmt_pct,
    _fmt_usd,
    max_drawdown,
    md_table,
    score_accounts,
    simulate_accounts,
)
from run_alpha_v1_priorities_1_5_20260516 import (  # noqa: E402
    ALPHA_CACHE_PROFILE,
    ALPHA_OLD_END,
    ALPHA_START,
    HUNTER_PROFILE,
    HUNTER_START,
    NY_TZ,
    _cached_alpha_frame,
    _exact_frame,
    _profit_factor,
    _round,
    _safe_div,
    run_priority_1_hunter_parity,
)
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402


RUN_SLUG = "alpha_v1_hunter_cap_fix_20260517"
OUT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_HUNTER_CAP_FIX_20260517.md"
OLD_PACKET_DIR = BT_ROOT / "data" / "results" / "alpha_v1_priorities_1_5_20260516"


def _raw_path() -> Path:
    return OUT_DIR / f"{HUNTER_PROFILE.replace('.', 'P')}_raw_result.json"


def _run_or_load_hunter(config: dict[str, Any], *, end_date: str, latest_data_ts) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = _raw_path()
    if path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
        print(
            f"{HUNTER_PROFILE}: loaded cached cap-fixed trades={result['summary']['total_trades']} "
            f"pnl={result['summary']['total_pnl_usd']:.2f}",
            flush=True,
        )
        return result
    result = run_profile_backtest_sync(
        config=config,
        profile_name=HUNTER_PROFILE,
        start_date=HUNTER_START,
        end_date=end_date,
        latest_data_ts=latest_data_ts,
        label=f"EXEC EXACT CAP-FIXED {HUNTER_PROFILE} {HUNTER_START} to {end_date}",
    )
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(
        f"{HUNTER_PROFILE}: ran cap-fixed trades={result['summary']['total_trades']} "
        f"pnl={result['summary']['total_pnl_usd']:.2f}",
        flush=True,
    )
    return result


def _trade_summary(df: pd.DataFrame, *, value_col: str = "pnl_usd_model", r_col: str | None = None) -> dict[str, Any]:
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


def _daily_metrics(df: pd.DataFrame) -> dict[str, Any]:
    if df.empty:
        return {"net_usd": 0.0, "dd_usd": 0.0, "worst_month_usd": 0.0, "sharpe": 0.0}
    daily = df.groupby("exit_day")["pnl_usd_model"].sum().sort_index()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0.0)
    monthly = daily.resample("ME").sum()
    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    return {
        "net_usd": float(daily.sum()),
        "dd_usd": max_drawdown(daily.to_numpy()),
        "worst_month_usd": float(monthly.min()) if len(monthly) else 0.0,
        "sharpe": float(daily.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0,
    }


def _subset(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df[(df["exit_day"] >= pd.Timestamp(start)) & (df["exit_day"] <= pd.Timestamp(end))].copy()


def _portfolio_rows(scenarios: list[tuple[str, str, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    portfolio_rows = []
    account_rows = []
    details = []
    for key, label, trades in scenarios:
        dm = _daily_metrics(trades)
        portfolio_rows.append({"scenario": key, "label": label, **{k: _round(v, 3) for k, v in dm.items()}})
        for year, (start, end) in YEAR_WINDOWS.items():
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


def _load_old_hunter() -> pd.DataFrame:
    df = pd.read_csv(OLD_PACKET_DIR / "hunter_live_exact_trades.csv")
    df["entry_ts_utc"] = pd.to_datetime(df["entry_ts_utc"], utc=True, errors="coerce")
    df["exit_ts_utc"] = pd.to_datetime(df["exit_ts_utc"], utc=True, errors="coerce")
    df["exit_day"] = pd.to_datetime(df["exit_day"], errors="coerce")
    df["pnl_usd_model"] = df["pnl_usd"].astype(float)
    df["net_r_model"] = df["net_r_model"].astype(float)
    return df


def _old_sidecar_rows() -> tuple[pd.DataFrame, pd.DataFrame]:
    portfolio = pd.read_csv(OLD_PACKET_DIR / "hunter_sidecar_portfolio.csv")
    accounts = pd.read_csv(OLD_PACKET_DIR / "hunter_sidecar_account_scorecard.csv")
    portfolio = portfolio[portfolio["scenario"].isin(["baseline", "plus_hunter_0.25"])].copy()
    accounts = accounts[accounts["scenario"].isin(["baseline", "plus_hunter_0.25"])].copy()
    portfolio["scenario"] = portfolio["scenario"].replace({"plus_hunter_0.25": "old_floor_hunter_0p25"})
    portfolio["label"] = portfolio["label"].replace(
        {"ALPHA_V1 + Hunter 0.25x actual engine sizing": "ALPHA_V1 + old floor Hunter 0.25x"}
    )
    accounts["scenario"] = accounts["scenario"].replace({"plus_hunter_0.25": "old_floor_hunter_0p25"})
    accounts["label"] = accounts["label"].replace(
        {"ALPHA_V1 + Hunter 0.25x actual engine sizing": "ALPHA_V1 + old floor Hunter 0.25x"}
    )
    return portfolio, accounts


def _same_setup_match(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
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

    old = keyed(left, "tp2_price")
    new = keyed(right, "tp2_price")
    return old.merge(new, on=["match_key", "match_n"], how="inner", suffixes=("_old", "_new"))


def build_report(outputs: dict[str, pd.DataFrame], *, elapsed_sec: float, hunter_end: str) -> str:
    exact = outputs["cap_fix_exact_comparison"]
    cap = outputs["cap_fix_risk_cap_summary"].iloc[0]
    parity = outputs["cap_fix_hunter_parity_summary"]
    parity_counts = outputs["cap_fix_hunter_parity_counts"].iloc[0]
    portfolio = outputs["cap_fix_sidecar_portfolio"]
    accounts = outputs["cap_fix_sidecar_account_scorecard"]

    exact_rows = []
    for _, row in exact.iterrows():
        exact_rows.append(
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

    base = portfolio[portfolio["scenario"] == "baseline"].iloc[0]
    portfolio_rows = []
    for _, row in portfolio.iterrows():
        portfolio_rows.append(
            [
                row["label"],
                _fmt_usd(row["net_usd"]),
                _fmt_usd(row["net_usd"] - base["net_usd"]),
                _fmt_usd(row["dd_usd"]),
                _fmt_usd(row["worst_month_usd"]),
                _fmt(row["sharpe"], 2),
            ]
        )

    account_rows = []
    for _, row in accounts[accounts["year"].isin(["2024", "2025", "2026_YTD"])].iterrows():
        account_rows.append(
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

    return "\n".join(
        [
            "# ALPHA_V1 Hunter Cap-Fix Rerun (2026-05-17)",
            "",
            f"- Generated: `{pd.Timestamp.now().isoformat(timespec='seconds')}`",
            f"- Results packet: `{OUT_DIR.relative_to(ROOT)}`",
            f"- Repro script: `backtesting/scripts/{Path(__file__).name}`",
            f"- Runtime: `{elapsed_sec:.1f}s`",
            f"- Hunter exact latest NQ end: `{hunter_end}`",
            "",
            "## Scope",
            "",
            (
                "Patched `HunterORBEngine._hunter_qty_for_risk()` so the Hunter path now follows the same "
                "`max_single_risk_usd` rule as standard ORB sizing: if one MNQ would exceed the configured "
                "single-contract cap, the setup is skipped instead of forced to `1` MNQ."
            ),
            "",
            "## Exact Replay Before / After",
            "",
            md_table(["Stream", "Trades", "Net", "DD", "PF", "Net R", "DD R", "WR"], exact_rows),
            "",
            (
                f"Old floor behavior had `{int(cap['old_over_cap_trades'])}` trades with effective risk above `$87.50`. "
                f"Cap-fixed replay has `{int(cap['new_over_cap_trades'])}` such trades. Same-setup old/new match count: "
                f"`{int(cap['old_new_same_setup_matches'])}`."
            ),
            "",
            "## Research Parity After Cap Fix",
            "",
            md_table(["Stream", "Trades", "Net", "DD", "PF", "Net R", "DD R", "WR"], parity_rows),
            "",
            (
                f"Research parity match after cap fix: `{int(parity_counts['fuzzy_matched_trades'])}` matched, "
                f"`{int(parity_counts['exact_only'])}` exact-only, `{int(parity_counts['research_only'])}` research-only."
            ),
            "",
            "## Sidecar Portfolio Fit",
            "",
            md_table(["Scenario", "Net", "Delta", "DD", "Worst Month", "Sharpe"], portfolio_rows),
            "",
            "## Sidecar Account Outcomes",
            "",
            md_table(["Scenario", "Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"], account_rows),
            "",
            "## Read",
            "",
            "- The sizing patch removes the silent over-risking from Hunter `0.25x`: over-cap trades dropped from `303` to `0`.",
            "- Standalone Hunter got smaller (`+$4.7k` old floor replay to `+$3.0k` cap-fixed replay), but the sidecar stayed additive in the current fee-aware ALPHA context.",
            "- Account fit is cleaner after the cap fix: 2024 improved from baseline `82.6% / 17.4%` payout/breach to `87.5% / 12.5%`, and 2025 improved from `73.1% / 26.9%` to `84.6% / 15.4%`.",
            "- Actionable read: keep cap-fixed Hunter as the cleaner no-webhook shadow candidate, but do not promote webhooks until the research/live signal-stream mismatch is explained.",
            "",
        ]
    )


def main() -> None:
    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    latest = latest_common_end(["NQ"])
    hunter_end = latest.date().isoformat()

    print("[1/3] Running/loading cap-fixed Hunter exact replay", flush=True)
    result = _run_or_load_hunter(config, end_date=hunter_end, latest_data_ts=latest)
    hunter_new = _exact_frame(result, profile=HUNTER_PROFILE, source=RUN_SLUG)
    hunter_new.to_csv(OUT_DIR / "hunter_cap_fixed_exact_trades.csv", index=False)
    hunter_old = _load_old_hunter()

    print("[2/3] Scoring parity and cap impact", flush=True)
    old_summary = _trade_summary(hunter_old, r_col="net_r_model")
    new_summary = _trade_summary(hunter_new, r_col="net_r_model")
    exact_comparison = pd.DataFrame(
        [
            {
                "stream": "old_floor_hunter_025",
                **{k: _round(v, 3) if isinstance(v, float) else v for k, v in old_summary.items()},
            },
            {
                "stream": "cap_fixed_hunter_025",
                **{k: _round(v, 3) if isinstance(v, float) else v for k, v in new_summary.items()},
            },
        ]
    )
    old_effective_risk = hunter_old["risk_points"].astype(float) * hunter_old["qty"].astype(float) * 2.0
    new_effective_risk = hunter_new["risk_points"].astype(float) * hunter_new["qty"].astype(float) * 2.0
    old_new_matches = _same_setup_match(hunter_old, hunter_new)
    cap_summary = pd.DataFrame(
        [
            {
                "old_trades": int(len(hunter_old)),
                "new_trades": int(len(hunter_new)),
                "old_over_cap_trades": int((old_effective_risk > 87.5 + 1e-9).sum()),
                "new_over_cap_trades": int((new_effective_risk > 87.5 + 1e-9).sum()),
                "old_avg_effective_risk_usd": round(float(old_effective_risk.mean()), 2),
                "new_avg_effective_risk_usd": round(float(new_effective_risk.mean()), 2),
                "old_new_same_setup_matches": int(len(old_new_matches)),
                "old_new_match_rate_vs_old_pct": round(_safe_div(len(old_new_matches), len(hunter_old)) * 100.0, 2),
                "old_new_match_rate_vs_new_pct": round(_safe_div(len(old_new_matches), len(hunter_new)) * 100.0, 2),
            }
        ]
    )
    parity_outputs = run_priority_1_hunter_parity(hunter_new)
    parity_outputs = {f"cap_fix_{key}": value for key, value in parity_outputs.items()}

    print("[3/3] Scoring cap-fixed sidecar against fee-aware ALPHA", flush=True)
    alpha = _cached_alpha_frame()
    hunter_window = _subset(hunter_new, ALPHA_START, ALPHA_OLD_END)
    cap_fixed_combined = pd.concat([alpha, hunter_window], ignore_index=True, sort=False)
    portfolio_new, accounts_new, details_new = _portfolio_rows(
        [
            ("baseline", "ALPHA_V1 cached fee-aware", alpha),
            ("cap_fixed_hunter_0p25", "ALPHA_V1 + cap-fixed Hunter 0.25x", cap_fixed_combined),
        ]
    )
    portfolio_old, accounts_old = _old_sidecar_rows()
    portfolio = pd.concat(
        [
            portfolio_new[portfolio_new["scenario"] == "baseline"],
            portfolio_old[portfolio_old["scenario"] == "old_floor_hunter_0p25"],
            portfolio_new[portfolio_new["scenario"] == "cap_fixed_hunter_0p25"],
        ],
        ignore_index=True,
        sort=False,
    )
    accounts = pd.concat(
        [
            accounts_new[accounts_new["scenario"] == "baseline"],
            accounts_old[accounts_old["scenario"] == "old_floor_hunter_0p25"],
            accounts_new[accounts_new["scenario"] == "cap_fixed_hunter_0p25"],
        ],
        ignore_index=True,
        sort=False,
    )

    outputs = {
        "cap_fix_exact_comparison": exact_comparison,
        "cap_fix_risk_cap_summary": cap_summary,
        "cap_fix_old_new_same_setup_matches": old_new_matches,
        **parity_outputs,
        "cap_fix_sidecar_portfolio": portfolio,
        "cap_fix_sidecar_account_scorecard": accounts,
        "cap_fix_sidecar_account_details": details_new,
    }
    for name, frame in outputs.items():
        frame.to_csv(OUT_DIR / f"{name}.csv", index=False)

    elapsed = time.time() - started
    report = build_report(outputs, elapsed_sec=elapsed, hunter_end=hunter_end)
    REPORT_PATH.write_text(report + "\n", encoding="utf-8")
    summary = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "elapsed_sec": round(elapsed, 1),
        "hunter_end": hunter_end,
        "paths": {"results": str(OUT_DIR), "report": str(REPORT_PATH)},
        "tables": {name: int(len(frame)) for name, frame in outputs.items()},
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
