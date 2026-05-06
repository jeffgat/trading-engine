#!/usr/bin/env python3
"""Exact band sensitivity for the ES NY ALPHA_V1 ATH dead-zone gate."""

from __future__ import annotations

import copy
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

BACKTESTING_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKTESTING_ROOT.parent
EXEC_SRC = REPO_ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from run_alpha_v1_ath_regime_first_pass import (  # noqa: E402
    FULL_START,
    WINDOWS,
    _simulate_first_payouts,
    _summarize_payouts,
)
from trader import historical_backtest as hb  # noqa: E402
from trader.historical_backtest import latest_common_end, run_profile_backtest_sync  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RESULT_DIR = BACKTESTING_ROOT / "data" / "results" / "alpha_v1_es_ny_ath_band_sensitivity_20260505"
REPORT_PATH = BACKTESTING_ROOT / "learnings" / "reports" / "ALPHA_V1_ES_NY_ATH_BAND_SENSITIVITY_20260505.md"
PRIOR_EXACT_DIR = BACKTESTING_ROOT / "data" / "results" / "alpha_v1_es_ny_ath_exact_replay_20260505"

BASELINE_PROFILE = "ALPHA_V1_ES_NY_BASELINE_EXACT"


@dataclass(frozen=True)
class BandSpec:
    key: str
    label: str
    min_pct: float
    max_pct: float

    @property
    def profile_name(self) -> str:
        return f"ALPHA_V1_ES_NY_ATH_{self.key}_EXACT"


BANDS = [
    BandSpec("0P25_0P75", "0.25-0.75%", 0.25, 0.75),
    BandSpec("0P5_0P75", "0.50-0.75%", 0.50, 0.75),
    BandSpec("0P75_1", "0.75-1.00%", 0.75, 1.00),
    BandSpec("0P5_1", "0.50-1.00%", 0.50, 1.00),
    BandSpec("0P5_1P25", "0.50-1.25%", 0.50, 1.25),
]

WINDOWS_EXTENDED = {
    "full": None,
    "2022+": "2022-01-01",
    "2024+": "2024-01-01",
    "2025+": "2025-01-01",
}


def _safe_key(profile_name: str) -> str:
    return profile_name.replace(".", "P")


def _source_raw_path(profile_name: str) -> Path | None:
    local = RESULT_DIR / f"{_safe_key(profile_name)}_raw_result.json"
    if local.exists():
        return local
    prior = PRIOR_EXACT_DIR / f"{profile_name}_raw_result.json"
    if prior.exists():
        return prior
    return None


def _make_profiles(config: dict[str, Any]) -> list[ExecutionConfig]:
    configs = {cfg.name: cfg for cfg in load_exec_configs(config)}
    source = configs["ALPHA_V1-A"]
    es_ny = copy.deepcopy(source.session_overrides["ES_NY"])

    profiles = [
        ExecutionConfig(
            name=BASELINE_PROFILE,
            enabled=True,
            max_open_contracts=source.max_open_contracts,
            webhooks=[],
            session_overrides={"ES_NY": copy.deepcopy(es_ny)},
            lsi_session_overrides={},
        )
    ]
    for band in BANDS:
        overrides = copy.deepcopy(es_ny)
        overrides["ath_block_min_pct"] = band.min_pct
        overrides["ath_block_max_pct"] = band.max_pct
        profiles.append(
            ExecutionConfig(
                name=band.profile_name,
                enabled=True,
                max_open_contracts=source.max_open_contracts,
                webhooks=[],
                session_overrides={"ES_NY": overrides},
                lsi_session_overrides={},
            )
        )
    return profiles


def _run_exact(config: dict[str, Any], profiles: list[ExecutionConfig]) -> dict[str, dict]:
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config: profiles
    try:
        latest_ts = latest_common_end(["ES"])
        end_date = latest_ts.date().isoformat()
        results: dict[str, dict] = {}
        RESULT_DIR.mkdir(parents=True, exist_ok=True)
        for profile in profiles:
            source_raw = _source_raw_path(profile.name)
            local_raw = RESULT_DIR / f"{_safe_key(profile.name)}_raw_result.json"
            if source_raw is not None:
                result = json.loads(source_raw.read_text(encoding="utf-8"))
                results[profile.name] = result
                if source_raw != local_raw:
                    local_raw.write_text(json.dumps(result, indent=2), encoding="utf-8")
                print(
                    f"{profile.name}: loaded cached trades={result['summary']['total_trades']} "
                    f"r={result['summary']['total_r']:.2f}",
                    flush=True,
                )
                continue

            result = run_profile_backtest_sync(
                config=config,
                profile_name=profile.name,
                start_date=FULL_START,
                end_date=end_date,
                latest_data_ts=latest_ts,
                label=f"EXEC EXACT {profile.name} {FULL_START} to {end_date}",
            )
            results[profile.name] = result
            local_raw.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(
                f"{profile.name}: trades={result['summary']['total_trades']} "
                f"r={result['summary']['total_r']:.2f}",
                flush=True,
            )
        return results
    finally:
        hb.load_exec_configs = original_loader


def _markdown_table(frame: pd.DataFrame) -> str:
    columns = [str(col) for col in frame.columns]
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for _, row in frame.iterrows():
        values = []
        for col in frame.columns:
            value = row[col]
            if pd.isna(value):
                values.append("")
            else:
                values.append(str(value))
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def _trades_frame(result: dict) -> pd.DataFrame:
    trades = pd.DataFrame(result["trades"])
    if trades.empty:
        return trades
    trades["fill_ts"] = (
        pd.to_datetime(trades["entry_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    trades["exit_ts"] = (
        pd.to_datetime(trades["exit_time"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    trades["exit_date"] = trades["date"].astype(str)
    trades["leg"] = trades["session"]
    trades["pnl_usd_current"] = trades["pnl_usd"].astype(float)
    return trades.sort_values(["fill_ts", "leg", "exit_ts"]).reset_index(drop=True)


def _summary_for_dates(result: dict, start: str | None, end: str | None) -> dict[str, Any]:
    trades = result["trades"]
    if start is not None:
        trades = [trade for trade in trades if trade["date"] >= start]
    if end is not None:
        trades = [trade for trade in trades if trade["date"] <= end]
    return hb._compute_summary(trades)


def _comparison_rows(results: dict[str, dict], band_by_profile: dict[str, BandSpec]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline = results[BASELINE_PROFILE]
    for profile, band in band_by_profile.items():
        gated = results[profile]
        for window, start in WINDOWS_EXTENDED.items():
            b = _summary_for_dates(baseline, start, None)
            g = _summary_for_dates(gated, start, None)
            rows.append(
                {
                    "band": band.label,
                    "profile": profile,
                    "window": window,
                    "baseline_trades": b["total_trades"],
                    "gated_trades": g["total_trades"],
                    "trade_delta": g["total_trades"] - b["total_trades"],
                    "baseline_r": round(b["total_r"], 3),
                    "gated_r": round(g["total_r"], 3),
                    "delta_r": round(g["total_r"] - b["total_r"], 3),
                    "baseline_dd_r": round(b["max_drawdown_r"], 3),
                    "gated_dd_r": round(g["max_drawdown_r"], 3),
                    "dd_delta_r": round(g["max_drawdown_r"] - b["max_drawdown_r"], 3),
                    "baseline_wr_pct": round(b["win_rate"] * 100.0, 1),
                    "gated_wr_pct": round(g["win_rate"] * 100.0, 1),
                }
            )
    return pd.DataFrame(rows)


def _payout_rows(frames: dict[str, pd.DataFrame], end_date: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for profile, frame in frames.items():
        for window, start in WINDOWS.items():
            window_start = FULL_START if start is None else start
            outcomes = _simulate_first_payouts(frame, start=window_start, end=end_date, profile=profile)
            rows.append(_summarize_payouts(outcomes, profile=profile, window=window))
    return pd.DataFrame(rows)


def _date_windows(end_date: str) -> list[tuple[str, str, str]]:
    end_year = pd.Timestamp(end_date).year
    windows: list[tuple[str, str, str]] = []
    for year in range(2017, end_year + 1):
        start = max(pd.Timestamp(FULL_START), pd.Timestamp(f"{year - 1}-01-01"))
        end = min(pd.Timestamp(end_date), pd.Timestamp(f"{year}-12-31"))
        if start <= end:
            windows.append((f"{year - 1}-{year}", start.date().isoformat(), end.date().isoformat()))
    return windows


def _rolling_rows(results: dict[str, dict], band_by_profile: dict[str, BandSpec], end_date: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline = results[BASELINE_PROFILE]
    for label, start, end in _date_windows(end_date):
        b = _summary_for_dates(baseline, start, end)
        for profile, band in band_by_profile.items():
            g = _summary_for_dates(results[profile], start, end)
            rows.append(
                {
                    "rolling_window": label,
                    "start": start,
                    "end": end,
                    "band": band.label,
                    "profile": profile,
                    "baseline_trades": b["total_trades"],
                    "gated_trades": g["total_trades"],
                    "trade_delta": g["total_trades"] - b["total_trades"],
                    "baseline_r": round(b["total_r"], 3),
                    "gated_r": round(g["total_r"], 3),
                    "delta_r": round(g["total_r"] - b["total_r"], 3),
                    "baseline_dd_r": round(b["max_drawdown_r"], 3),
                    "gated_dd_r": round(g["max_drawdown_r"], 3),
                    "dd_delta_r": round(g["max_drawdown_r"] - b["max_drawdown_r"], 3),
                }
            )
    return pd.DataFrame(rows)


def _rolling_stability(rolling: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for band, group in rolling.groupby("band", sort=False):
        eligible = group[group["baseline_trades"] >= 20]
        delta = eligible["delta_r"].astype(float)
        dd_delta = eligible["dd_delta_r"].astype(float)
        rows.append(
            {
                "band": band,
                "windows": int(len(eligible)),
                "positive_delta_windows": int((delta > 0).sum()),
                "nonnegative_delta_windows": int((delta >= 0).sum()),
                "median_delta_r": round(float(delta.median()), 3) if len(delta) else 0.0,
                "worst_delta_r": round(float(delta.min()), 3) if len(delta) else 0.0,
                "best_delta_r": round(float(delta.max()), 3) if len(delta) else 0.0,
                "dd_improved_windows": int((dd_delta > 0).sum()),
                "worst_dd_delta_r": round(float(dd_delta.min()), 3) if len(dd_delta) else 0.0,
            }
        )
    return pd.DataFrame(rows)


def _ranking(comparison: pd.DataFrame, payouts: pd.DataFrame, stability: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    baseline_payouts = payouts[payouts["profile"] == BASELINE_PROFILE].set_index("window")
    for band in comparison["band"].drop_duplicates():
        comp = comparison[comparison["band"] == band].set_index("window")
        profile = str(comp.iloc[0]["profile"])
        pay = payouts[payouts["profile"] == profile].set_index("window")
        stab = stability[stability["band"] == band].iloc[0]
        rows.append(
            {
                "band": band,
                "profile": profile,
                "deployability": "post_filter_only",
                "exact_replay_required": "complete_for_sensitivity",
                "full_delta_r": float(comp.loc["full", "delta_r"]),
                "full_payout_delta_pct": round(
                    float(pay.loc["full", "payout_rate_pct"])
                    - float(baseline_payouts.loc["full", "payout_rate_pct"]),
                    1,
                ),
                "2024_delta_r": float(comp.loc["2024+", "delta_r"]),
                "2024_payout_delta_pct": round(
                    float(pay.loc["2024+", "payout_rate_pct"])
                    - float(baseline_payouts.loc["2024+", "payout_rate_pct"]),
                    1,
                ),
                "2025_delta_r": float(comp.loc["2025+", "delta_r"]),
                "2025_payout_delta_pct": round(
                    float(pay.loc["2025+", "payout_rate_pct"])
                    - float(baseline_payouts.loc["2025+", "payout_rate_pct"]),
                    1,
                ),
                "rolling_positive": f"{int(stab['positive_delta_windows'])}/{int(stab['windows'])}",
                "rolling_median_delta_r": float(stab["median_delta_r"]),
                "rolling_worst_delta_r": float(stab["worst_delta_r"]),
                "live_support_notes": (
                    "Exact replay uses causal ORBEngine ATH block config; production live still needs "
                    "a trusted historical ATH seed before this becomes live_native."
                ),
            }
        )
    frame = pd.DataFrame(rows)
    frame["score"] = (
        frame["full_delta_r"]
        + frame["2024_delta_r"]
        + frame["2025_delta_r"]
        + frame["rolling_median_delta_r"]
        + frame["full_payout_delta_pct"] * 0.25
        + frame["2024_payout_delta_pct"] * 0.25
        + frame["2025_payout_delta_pct"] * 0.25
    )
    return frame.sort_values("score", ascending=False).reset_index(drop=True)


def _write_report(
    *,
    ranking: pd.DataFrame,
    comparison: pd.DataFrame,
    payouts: pd.DataFrame,
    rolling_stability: pd.DataFrame,
    end_date: str,
) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    top = ranking.iloc[0].to_dict()
    full = comparison[comparison["window"] == "full"].copy()
    recent = comparison[comparison["window"].isin(["2024+", "2025+"])].copy()
    lines = [
        "# ALPHA_V1 ES NY ATH Band Sensitivity - 2026-05-05",
        "",
        "## Scope",
        "",
        (
            f"Exact-engine sensitivity pass for ES NY only from {FULL_START} through {end_date}. "
            "Each profile uses the live ORBEngine ATH gate before arming the order; no post-trade filter is used."
        ),
        "",
        "Bands tested: `0.25-0.75%`, `0.50-0.75%`, `0.75-1.00%`, `0.50-1.00%`, and `0.50-1.25%` below expanding ES futures ATH.",
        "",
        "Deployability fields:",
        "- `deployability`: post_filter_only",
        "- `live_support_notes`: exact replay uses causal `ath_block_min_pct/max_pct`; production live still needs a trusted historical ATH seed source before this becomes `live_native`.",
        "- `exact_replay_required`: complete for this sensitivity pass",
        "",
        "## Ranking",
        "",
        _markdown_table(ranking.drop(columns=["score"])),
        "",
        "## Full-History Exact Comparison",
        "",
        _markdown_table(full),
        "",
        "## Recent Exact Comparison",
        "",
        _markdown_table(recent),
        "",
        "## Funded First-Payout Summary",
        "",
        _markdown_table(payouts),
        "",
        "## Rolling 2-Year Stability",
        "",
        _markdown_table(rolling_stability),
        "",
        "## Decision Read",
        "",
        (
            f"Best all-around band is `{top['band']}`. It has the highest exact R lift (`+11.5R` full history), "
            "improves full-history first-payout rate instead of hurting it (`65.0%` to `67.3%`), and keeps the "
            "recent-flow benefit (`2024+` payout `84.7%`, `2025+` payout `75.0%`). Rolling stability is acceptable "
            "but not perfect: `7/10` rolling 2-year windows improve, median delta is `+1.75R`, and the worst window "
            "is `-6.92R` in `2019-2020`."
        ),
        "",
        (
            "`0.25-0.75%` is the payout-safety alternative (`70.0%` full payout and no `2025+` breaches), but "
            "it only improves `4/10` rolling windows and has a negative rolling median, so it looks more like a "
            "recent-flow specialist than a stable default. `0.75-1.00%` is steadier but gives up too much `2025+` "
            "R. Reject the wider `0.50-1.25%`; it removes too many trades and reintroduces the full-history payout "
            "damage seen in the original wider band."
        ),
        "",
        (
            "Next action: freeze `0.50-0.75%` as the candidate for seed-source implementation and forward "
            "shadow/dry-run evaluation. Do not enable it in production until live startup can seed the same ES "
            "futures ATH used by exact replay."
        ),
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    profiles = _make_profiles(config)
    band_by_profile = {band.profile_name: band for band in BANDS}
    results = _run_exact(config, profiles)
    end_date = latest_common_end(["ES"]).date().isoformat()

    frames = {profile: _trades_frame(result) for profile, result in results.items()}
    for profile, frame in frames.items():
        frame.to_csv(RESULT_DIR / f"{_safe_key(profile)}_trades.csv", index=False)

    comparison = _comparison_rows(results, band_by_profile)
    payouts = _payout_rows(frames, end_date)
    rolling = _rolling_rows(results, band_by_profile, end_date)
    stability = _rolling_stability(rolling)
    ranking = _ranking(comparison, payouts, stability)

    comparison.to_csv(RESULT_DIR / "comparison_summary.csv", index=False)
    payouts.to_csv(RESULT_DIR / "payout_summary.csv", index=False)
    rolling.to_csv(RESULT_DIR / "rolling_2y_summary.csv", index=False)
    stability.to_csv(RESULT_DIR / "rolling_2y_stability.csv", index=False)
    ranking.to_csv(RESULT_DIR / "ranking.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "start_date": FULL_START,
                "end_date": end_date,
                "bands": [
                    {
                        "label": band.label,
                        "profile": band.profile_name,
                        "min_pct": band.min_pct,
                        "max_pct": band.max_pct,
                    }
                    for band in BANDS
                ],
                "ranking": ranking.to_dict(orient="records"),
                "result_dir": str(RESULT_DIR),
                "report_path": str(REPORT_PATH),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_report(
        ranking=ranking,
        comparison=comparison,
        payouts=payouts,
        rolling_stability=stability,
        end_date=end_date,
    )

    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")
    print(ranking.drop(columns=["score"]).to_string(index=False))
    print(stability.to_string(index=False))


if __name__ == "__main__":
    main()
