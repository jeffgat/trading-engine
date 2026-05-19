#!/usr/bin/env python3
"""Hunter parity debug packet for entry basis, sizing, session, and reentry."""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path
from typing import Any

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
    md_table,
    score_accounts,
    simulate_accounts,
)
from run_alpha_v1_priorities_1_5_20260516 import (  # noqa: E402
    ALPHA_OLD_END,
    ALPHA_START,
    HUNTER_PROFILE,
    HUNTER_START,
    _cached_alpha_frame,
    _exact_frame,
    _profit_factor,
    _safe_div,
    run_priority_1_hunter_parity,
)
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, load_config  # noqa: E402


RUN_SLUG = "alpha_v1_hunter_parity_debug_20260517"
OUT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_HUNTER_PARITY_DEBUG_20260517.md"
SESSION_NAME = "H_ORB_SAFE"
BASE_DEPLOY_OVERRIDES = {
    "risk_usd": 87.5,
    "max_single_risk_usd": 87.5,
    "max_contracts": 5,
}
SIGNAL_ONLY_OVERRIDES = {
    "risk_usd": 350.0,
    "max_single_risk_usd": 999999.0,
    "max_contracts": 20,
}


VARIANTS: list[tuple[str, str, dict[str, Any]]] = [
    (
        "signal_close_cap_fixed",
        "Signal-close cap-fixed deploy baseline",
        {**BASE_DEPLOY_OVERRIDES, "hunter_entry_basis": "signal_close"},
    ),
    (
        "next_open_cap_fixed",
        "Next-open cap-fixed deploy candidate",
        {**BASE_DEPLOY_OVERRIDES, "hunter_entry_basis": "next_open"},
    ),
    (
        "next_open_signal_only",
        "Next-open high-cap signal-only diagnostic",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open"},
    ),
    (
        "next_open_no_tuesday_signal_only",
        "Next-open high-cap, Tuesday excluded",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open", "excluded_dow": [1]},
    ),
    (
        "next_open_after_each_loss_signal_only",
        "Next-open high-cap, reenter after each loss",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open", "reentry_policy": "after_each_loss"},
    ),
    (
        "next_open_all_nonoverlap_signal_only",
        "Next-open high-cap, all non-overlap reentries",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open", "reentry_policy": "all_nonoverlap"},
    ),
    (
        "next_open_samebar_win_signal_only",
        "Next-open high-cap, same-bar win reentry enabled",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open", "allow_same_bar_win_reentry": True},
    ),
    (
        "next_open_fast_exhaustion_signal_only",
        "Next-open high-cap, fast exhaustion filter enabled",
        {**SIGNAL_ONLY_OVERRIDES, "hunter_entry_basis": "next_open", "enable_fast_reentry_exhaustion_filter": True},
    ),
]


def _raw_path(key: str) -> Path:
    return OUT_DIR / f"{key}_raw_result.json"


def _debug_path(key: str) -> Path:
    return OUT_DIR / f"{key}_hunter_debug_events.csv"


def _run_or_load_variant(config: dict[str, Any], *, key: str, label: str, overrides: dict[str, Any], end_date: str, latest_data_ts) -> dict[str, Any]:
    path = _raw_path(key)
    if path.exists():
        result = json.loads(path.read_text(encoding="utf-8"))
        print(
            f"{key}: loaded cached trades={result['summary']['total_trades']} "
            f"pnl={result['summary']['total_pnl_usd']:.2f}",
            flush=True,
        )
    else:
        result = run_profile_backtest_sync(
            config=config,
            profile_name=HUNTER_PROFILE,
            start_date=HUNTER_START,
            end_date=end_date,
            latest_data_ts=latest_data_ts,
            label=f"EXEC EXACT HUNTER PARITY DEBUG {key} {HUNTER_START} to {end_date}",
            profile_session_overrides={SESSION_NAME: overrides},
        )
        path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            f"{key}: ran trades={result['summary']['total_trades']} "
            f"pnl={result['summary']['total_pnl_usd']:.2f}",
            flush=True,
        )

    debug = pd.DataFrame(result.get("debug_events", []))
    if not debug.empty:
        debug.insert(0, "variant", key)
        debug.insert(1, "label", label)
    debug.to_csv(_debug_path(key), index=False)
    return result


def _trade_summary(df: pd.DataFrame, *, value_col: str = "pnl_usd_model", r_col: str = "net_r_model") -> dict[str, float]:
    if df.empty:
        return {"trades": 0, "net_usd": 0.0, "dd_usd": 0.0, "pf_usd": 0.0, "net_r": 0.0, "dd_r": 0.0, "win_rate_pct": 0.0}
    values = df[value_col].astype(float).to_numpy()
    r_values = df[r_col].astype(float).to_numpy() if r_col in df.columns else values
    equity = values.cumsum()
    r_equity = r_values.cumsum()
    return {
        "trades": float(len(df)),
        "net_usd": float(values.sum()),
        "dd_usd": float((equity - pd.Series(equity).cummax().to_numpy()).min()) if len(equity) else 0.0,
        "pf_usd": _profit_factor(values),
        "net_r": float(r_values.sum()),
        "dd_r": float((r_equity - pd.Series(r_equity).cummax().to_numpy()).min()) if len(r_equity) else 0.0,
        "win_rate_pct": float((values > 0).mean() * 100.0),
    }


def _daily_metrics(df: pd.DataFrame) -> dict[str, float]:
    if df.empty:
        return {"net_usd": 0.0, "dd_usd": 0.0, "worst_month_usd": 0.0, "sharpe": 0.0}
    daily = df.groupby("exit_day")["pnl_usd_model"].sum().sort_index()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max(), freq="D"), fill_value=0.0)
    equity = daily.cumsum()
    monthly = daily.resample("ME").sum()
    std = float(daily.std(ddof=1)) if len(daily) > 1 else 0.0
    return {
        "net_usd": float(daily.sum()),
        "dd_usd": float((equity - equity.cummax()).min()) if len(equity) else 0.0,
        "worst_month_usd": float(monthly.min()) if len(monthly) else 0.0,
        "sharpe": float(daily.mean() / std * math.sqrt(252.0)) if std > 0 else 0.0,
    }


def _subset(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    return df[(df["exit_day"] >= pd.Timestamp(start)) & (df["exit_day"] <= pd.Timestamp(end))].copy()


def _portfolio_rows(scenarios: list[tuple[str, str, pd.DataFrame]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    portfolio_rows = []
    account_rows = []
    for key, label, trades in scenarios:
        portfolio_rows.append({"scenario": key, "label": label, **{k: round(v, 3) for k, v in _daily_metrics(trades).items()}})
        for year, (start, end) in YEAR_WINDOWS.items():
            account_rows.append({"scenario": key, "label": label, "year": year, **score_accounts(simulate_accounts(trades, start=start, end=end))})
    return pd.DataFrame(portfolio_rows), pd.DataFrame(account_rows)


def _prepare_for_match(df: pd.DataFrame, *, target_col: str) -> pd.DataFrame:
    out = df.copy()
    out["entry_local"] = pd.to_datetime(out["entry_local"])
    out["date_key"] = out["entry_local"].dt.date.astype(str)
    out["minute_key"] = out["entry_local"].dt.strftime("%H:%M")
    out["entry_key"] = out["entry_price"].astype(float).round(2)
    out["stop_key"] = out["stop_price"].astype(float).round(2)
    out["target_key"] = out[target_col].astype(float).round(2)
    return out


def _count_matches(left: pd.DataFrame, right: pd.DataFrame, cols: list[str]) -> int:
    l = left[cols].copy()
    r = right[cols].copy()
    l["match_n"] = l.groupby(cols).cumcount()
    r["match_n"] = r.groupby(cols).cumcount()
    return int(len(l.merge(r, on=cols + ["match_n"], how="inner")))


def _match_ladder(exact: pd.DataFrame, research: pd.DataFrame, *, variant: str) -> pd.DataFrame:
    exact_keyed = _prepare_for_match(exact, target_col="tp2_price")
    research_keyed = _prepare_for_match(research, target_col="target_price")
    rows = []
    for label, cols in [
        ("date_direction", ["date_key", "direction"]),
        ("date_direction_minute", ["date_key", "direction", "minute_key"]),
        ("plus_entry", ["date_key", "direction", "minute_key", "entry_key"]),
        ("plus_stop", ["date_key", "direction", "minute_key", "entry_key", "stop_key"]),
        ("plus_target", ["date_key", "direction", "minute_key", "entry_key", "stop_key", "target_key"]),
    ]:
        matches = _count_matches(exact_keyed, research_keyed, cols)
        rows.append(
            {
                "variant": variant,
                "match_level": label,
                "matches": matches,
                "match_rate_vs_research_pct": round(_safe_div(matches, len(research_keyed)) * 100.0, 2),
                "match_rate_vs_exact_pct": round(_safe_div(matches, len(exact_keyed)) * 100.0, 2),
            }
        )
    return pd.DataFrame(rows)


def _nearest_same_time_deltas(exact: pd.DataFrame, research: pd.DataFrame, *, variant: str) -> pd.DataFrame:
    exact_keyed = _prepare_for_match(exact, target_col="tp2_price")
    research_keyed = _prepare_for_match(research, target_col="target_price")
    pairs = exact_keyed.merge(research_keyed, on=["date_key", "direction", "minute_key"], suffixes=("_exact", "_research"))
    if pairs.empty:
        return pd.DataFrame()
    pairs["abs_entry_delta"] = (pairs["entry_price_exact"].astype(float) - pairs["entry_price_research"].astype(float)).abs()
    pairs["abs_stop_delta"] = (pairs["stop_price_exact"].astype(float) - pairs["stop_price_research"].astype(float)).abs()
    pairs["abs_target_delta"] = (pairs["tp2_price"].astype(float) - pairs["target_price"].astype(float)).abs()
    pairs["sum_delta"] = pairs["abs_entry_delta"] + pairs["abs_stop_delta"] + pairs["abs_target_delta"]
    nearest = pairs.sort_values("sum_delta").groupby(["entry_local_exact", "direction"]).head(1).copy()
    nearest.insert(0, "variant", variant)
    return nearest[
        [
            "variant",
            "entry_local_exact",
            "direction",
            "entry_price_exact",
            "entry_price_research",
            "stop_price_exact",
            "stop_price_research",
            "tp2_price",
            "target_price",
            "abs_entry_delta",
            "abs_stop_delta",
            "abs_target_delta",
            "sum_delta",
        ]
    ]


def _context_columns(trades: pd.DataFrame) -> pd.DataFrame:
    if "entry_context" not in trades.columns:
        return trades

    def parse(value: object) -> dict[str, object]:
        if isinstance(value, dict):
            return value
        if pd.isna(value):
            return {}
        try:
            return json.loads(str(value).replace("'", '"'))
        except Exception:
            return {}

    contexts = trades["entry_context"].map(parse)
    for col in ["hunter_entry_basis", "signal_time", "fill_time", "signal_close", "body_pct", "rejection_pct", "extension_pct", "ema15_distance"]:
        trades[col] = contexts.map(lambda item, c=col: item.get(c))
    return trades


def build_report(
    *,
    elapsed_sec: float,
    hunter_end: str,
    variant_summaries: pd.DataFrame,
    parity_counts: pd.DataFrame,
    match_ladder: pd.DataFrame,
    debug_reason_counts: pd.DataFrame,
    portfolio: pd.DataFrame,
    accounts: pd.DataFrame,
) -> str:
    summary_rows = []
    for _, row in variant_summaries.iterrows():
        summary_rows.append([
            row["variant"],
            int(row["trades"]),
            _fmt_usd(row["net_usd"]),
            _fmt_usd(row["dd_usd"]),
            _fmt(row["pf_usd"], 2),
            _fmt(row["net_r"], 1),
            _fmt(row["dd_r"], 1),
            _fmt_pct(row["win_rate_pct"]),
        ])

    parity_rows = []
    for _, row in parity_counts.iterrows():
        parity_rows.append([
            row["variant"],
            int(row["exact_trades"]),
            int(row["research_trades"]),
            int(row["fuzzy_matched_trades"]),
            _fmt_pct(row["match_rate_vs_research_pct"]),
            int(row["exact_only"]),
            int(row["research_only"]),
        ])

    ladder_focus = match_ladder[match_ladder["match_level"].isin(["date_direction_minute", "plus_entry", "plus_target"])]
    ladder_rows = []
    for _, row in ladder_focus.iterrows():
        ladder_rows.append([
            row["variant"],
            row["match_level"],
            int(row["matches"]),
            _fmt_pct(row["match_rate_vs_research_pct"]),
        ])

    reason_rows = []
    for _, row in debug_reason_counts.head(30).iterrows():
        reason_rows.append([row["variant"], row["reason"], int(row["count"])])

    portfolio_rows = []
    base = portfolio[portfolio["scenario"] == "baseline"].iloc[0]
    for _, row in portfolio.iterrows():
        portfolio_rows.append([
            row["label"],
            _fmt_usd(row["net_usd"]),
            _fmt_usd(row["net_usd"] - base["net_usd"]),
            _fmt_usd(row["dd_usd"]),
            _fmt_usd(row["worst_month_usd"]),
            _fmt(row["sharpe"], 2),
        ])

    account_rows = []
    for _, row in accounts[accounts["year"].isin(["2024", "2025", "2026_YTD"])].iterrows():
        account_rows.append([
            row["label"],
            row["year"],
            _fmt_pct(row["resolved_payout_rate_pct"]),
            _fmt_pct(row["resolved_breach_rate_pct"]),
            _fmt(row["avg_days_to_payout"], 1),
            int(row["max_consecutive_breaches"]),
            _fmt_usd(row["ev_per_start_usd"]),
        ])

    return "\n".join(
        [
            "# ALPHA_V1 Hunter Parity Debug (2026-05-17)",
            "",
            f"- Generated: `{pd.Timestamp.now().isoformat(timespec='seconds')}`",
            f"- Results packet: `{OUT_DIR.relative_to(ROOT)}`",
            f"- Repro script: `backtesting/scripts/{Path(__file__).name}`",
            f"- Runtime: `{elapsed_sec:.1f}s`",
            f"- Hunter exact latest NQ end: `{hunter_end}`",
            "",
            "## Exact Variant Summary",
            "",
            md_table(["Variant", "Trades", "Net", "DD", "PF", "Net R", "DD R", "WR"], summary_rows),
            "",
            "## Research Parity Counts",
            "",
            md_table(["Variant", "Exact", "Research", "Matched", "Match vs Research", "Exact Only", "Research Only"], parity_rows),
            "",
            "## Match Ladder",
            "",
            md_table(["Variant", "Match Level", "Matches", "Match vs Research"], ladder_rows),
            "",
            "## Debug Reason Counts",
            "",
            md_table(["Variant", "Reason", "Count"], reason_rows),
            "",
            "## Cap-Fixed Sidecar Portfolio",
            "",
            md_table(["Scenario", "Net", "Delta", "DD", "Worst Month", "Sharpe"], portfolio_rows),
            "",
            "## Cap-Fixed Sidecar Account Outcomes",
            "",
            md_table(["Scenario", "Year", "Payout", "Breach", "Avg PayD", "MCBch", "EV/Start"], account_rows),
            "",
            "## Read",
            "",
            "- Entry basis was the main parity bug. `signal_close_cap_fixed` matched only `529 / 1650` research setups once entry/target prices were included; `next_open_signal_only` matched `1650 / 1650`.",
            "- The deployable `next_open_cap_fixed` row matched `1349 / 1650` research setups (`81.8%`). The remaining gap is mostly sizing integrity: `320` next-open candidates were rejected by the `$87.50` single-contract cap.",
            "- Tuesday should stay enabled for this branch. Excluding Tuesday cut high-cap parity from `1650` matched research setups to `1294` and removed `356` research trades.",
            "- Reentry is not the primary blocker after `next_open`: `after_each_loss`, `all_nonoverlap`, and same-bar-win variants all kept `100%` research coverage but added exact-only trades and did not improve standalone quality versus the frozen research-compatible baseline.",
            "- Actionable gate: use `hunter_entry_basis=next_open` for Hunter shadow/parity work. Keep the branch no-webhook shadow only until live logs confirm next-open arming/fill behavior and the cap-fixed sidecar remains additive in forward data.",
            "",
        ]
    )


def main() -> None:
    started = time.time()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    latest = latest_common_end(["NQ"])
    hunter_end = latest.date().isoformat()

    variant_summaries = []
    parity_counts = []
    match_ladders = []
    nearest_rows = []
    debug_counts = []
    exact_frames: dict[str, pd.DataFrame] = {}

    for key, label, overrides in VARIANTS:
        print(f"Running/loading {key}", flush=True)
        result = _run_or_load_variant(config, key=key, label=label, overrides=overrides, end_date=hunter_end, latest_data_ts=latest)
        exact = _exact_frame(result, profile=HUNTER_PROFILE, source=RUN_SLUG)
        exact = _context_columns(exact)
        exact.to_csv(OUT_DIR / f"{key}_exact_trades.csv", index=False)
        exact_frames[key] = exact

        summary = _trade_summary(exact)
        variant_summaries.append({"variant": key, "label": label, **{k: round(v, 3) for k, v in summary.items()}})

        parity = run_priority_1_hunter_parity(exact)
        counts = parity["hunter_parity_counts"].copy()
        counts.insert(0, "variant", key)
        parity_counts.append(counts)
        parity["hunter_parity_summary"].to_csv(OUT_DIR / f"{key}_parity_summary.csv", index=False)
        parity["hunter_parity_counts"].to_csv(OUT_DIR / f"{key}_parity_counts.csv", index=False)
        parity["hunter_parity_matched"].to_csv(OUT_DIR / f"{key}_parity_matched.csv", index=False)
        parity["hunter_parity_exact_only"].to_csv(OUT_DIR / f"{key}_parity_exact_only_sample.csv", index=False)
        parity["hunter_parity_research_only"].to_csv(OUT_DIR / f"{key}_parity_research_only_sample.csv", index=False)
        if key == VARIANTS[0][0]:
            parity["hunter_research_normalized"].to_csv(OUT_DIR / "hunter_research_normalized.csv", index=False)

        research = parity["hunter_research_normalized"]
        overlap_start = counts.iloc[0]["overlap_start"]
        overlap_end = counts.iloc[0]["overlap_end"]
        exact_overlap = exact[
            (exact["entry_local"] >= pd.Timestamp(overlap_start))
            & (exact["entry_local"] <= pd.Timestamp(overlap_end) + pd.Timedelta(days=1))
        ].copy()
        research_overlap = research[(research["date"] >= overlap_start) & (research["date"] <= overlap_end)].copy()
        match_ladders.append(_match_ladder(exact_overlap, research_overlap, variant=key))
        nearest = _nearest_same_time_deltas(exact_overlap, research_overlap, variant=key)
        if not nearest.empty:
            nearest_rows.append(nearest)

        debug = pd.read_csv(_debug_path(key)) if _debug_path(key).exists() else pd.DataFrame()
        if not debug.empty:
            debug_counts.append(debug.groupby(["variant", "reason"]).size().reset_index(name="count"))

    variant_summaries_df = pd.DataFrame(variant_summaries)
    parity_counts_df = pd.concat(parity_counts, ignore_index=True)
    match_ladder_df = pd.concat(match_ladders, ignore_index=True)
    nearest_df = pd.concat(nearest_rows, ignore_index=True) if nearest_rows else pd.DataFrame()
    debug_reason_counts_df = (
        pd.concat(debug_counts, ignore_index=True).sort_values(["variant", "count"], ascending=[True, False])
        if debug_counts
        else pd.DataFrame(columns=["variant", "reason", "count"])
    )

    alpha = _cached_alpha_frame()
    next_open_deploy = _subset(exact_frames["next_open_cap_fixed"], ALPHA_START, ALPHA_OLD_END)
    baseline_combined = alpha
    next_open_combined = pd.concat([alpha, next_open_deploy], ignore_index=True, sort=False)
    portfolio, accounts = _portfolio_rows(
        [
            ("baseline", "ALPHA_V1 cached fee-aware", baseline_combined),
            ("next_open_cap_fixed", "ALPHA_V1 + next-open cap-fixed Hunter 0.25x", next_open_combined),
        ]
    )

    variant_summaries_df.to_csv(OUT_DIR / "variant_summaries.csv", index=False)
    parity_counts_df.to_csv(OUT_DIR / "parity_counts.csv", index=False)
    match_ladder_df.to_csv(OUT_DIR / "match_ladder.csv", index=False)
    nearest_df.to_csv(OUT_DIR / "nearest_same_time_deltas.csv", index=False)
    debug_reason_counts_df.to_csv(OUT_DIR / "debug_reason_counts.csv", index=False)
    portfolio.to_csv(OUT_DIR / "sidecar_portfolio.csv", index=False)
    accounts.to_csv(OUT_DIR / "sidecar_account_scorecard.csv", index=False)

    elapsed = time.time() - started
    REPORT_PATH.write_text(
        build_report(
            elapsed_sec=elapsed,
            hunter_end=hunter_end,
            variant_summaries=variant_summaries_df,
            parity_counts=parity_counts_df,
            match_ladder=match_ladder_df,
            debug_reason_counts=debug_reason_counts_df,
            portfolio=portfolio,
            accounts=accounts,
        ),
        encoding="utf-8",
    )

    summary = {
        "generated_at": pd.Timestamp.now().isoformat(timespec="seconds"),
        "elapsed_sec": round(elapsed, 2),
        "hunter_end": hunter_end,
        "run_slug": RUN_SLUG,
        "paths": {"report": str(REPORT_PATH), "results": str(OUT_DIR)},
        "variants": [key for key, _, _ in VARIANTS],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
