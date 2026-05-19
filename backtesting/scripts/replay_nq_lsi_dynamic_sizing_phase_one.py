#!/usr/bin/env python3
"""No-fetch phase-one account replay for NQ NY LSI dynamic sizing overlays."""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RUN_SLUG = "nq_ny_lsi_dynamic_sizing_phase_one_20260515"
DEFAULT_OUTPUT_DIR = ROOT / "data" / "results" / RUN_SLUG
DEFAULT_REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LSI_DYNAMIC_SIZING_PHASE_ONE_20260515.md"
ORDERBOOK_REPLAY = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_orderbook_risk_tiers_20260515"
    / "trade_risk_tier_replay.csv"
)
SWEEP_RECLAIM_REPLAY = (
    ROOT
    / "data"
    / "results"
    / "nq_ny_lsi_sweep_reclaim_velocity_20260515"
    / "trade_risk_tier_replay.csv"
)

PAYOUT_R = 5.0
BREACH_R = -4.0
CYCLE_DAYS = 14


SELECTED_OVERLAYS = (
    {
        "source": "orderbook",
        "key": "allDOW_additive_pre_confirm_pressure",
        "candidate": "add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530",
        "feature": "pre_confirm_30s_pressure_score",
        "thesis": "1m additive MBP-10 pressure survivor.",
    },
    {
        "source": "orderbook",
        "key": "noThu_additive_pre_confirm_pressure",
        "candidate": "add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530",
        "feature": "pre_confirm_30s_pressure_score",
        "thesis": "1m no-Thursday additive MBP-10 pressure survivor.",
    },
    {
        "source": "orderbook",
        "key": "pure_1m_long_confirm_last_velocity",
        "candidate": "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
        "feature": "confirm_last_10s_mid_velocity_ticks_per_second",
        "thesis": "Pure 1m long MBP-10 confirm-last velocity survivor.",
    },
    {
        "source": "sweep_reclaim",
        "key": "3m_trapped_reversal_confirm",
        "candidate": "add_3m_hourly_atr12p5_b3_a7p5",
        "feature": "trapped_reversal_confirm_score",
        "thesis": "3m no-fetch 1s trapped-reversal price-action survivor.",
    },
    {
        "source": "sweep_reclaim",
        "key": "3m_confirm_reclaim_velocity",
        "candidate": "add_3m_hourly_atr12p5_b3_a7p5",
        "feature": "confirm_reclaim_velocity_ticks_per_second",
        "thesis": "3m no-fetch 1s reclaim-velocity secondary signal.",
    },
)

PROFILES = ("tier_0p5_1_1p5", "tier_0p75_1_1p25", "tier_0_1_1p5")
WINDOWS = {
    "post_2023": ("2023-01-01", "2026-05-02"),
    "holdout": ("2025-04-01", "2026-05-02"),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    return parser.parse_args()


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def load_replays() -> pd.DataFrame:
    frames = []
    for source, path in (("orderbook", ORDERBOOK_REPLAY), ("sweep_reclaim", SWEEP_RECLAIM_REPLAY)):
        frame = pd.read_csv(path)
        frame["source"] = source
        if "overlay" not in frame.columns:
            frame["overlay"] = frame["candidate"] + "__" + frame["feature"]
        if "feature_timing" not in frame.columns:
            frame["feature_timing"] = "orderbook_entry_or_signal_safe"
        frames.append(frame)
    data = pd.concat(frames, ignore_index=True)
    data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date.astype(str)
    data["signal_ts"] = pd.to_datetime(data["signal_start"], errors="coerce")
    data["r_multiple"] = pd.to_numeric(data["r_multiple"], errors="coerce")
    data["weighted_r"] = pd.to_numeric(data["weighted_r"], errors="coerce")
    data["risk_weight"] = pd.to_numeric(data["risk_weight"], errors="coerce")
    return data.dropna(subset=["date", "signal_ts", "r_multiple", "weighted_r"]).copy()


def simulate_accounts(
    trades: pd.DataFrame,
    *,
    r_column: str,
    start: str,
    end: str,
) -> tuple[dict[str, Any], pd.DataFrame]:
    filled = trades[(trades["date"] >= start) & (trades["date"] < end)].copy()
    filled = filled.sort_values(["signal_ts", "candidate", "feature"])
    if filled.empty:
        empty = {
            "accounts": 0,
            "payouts": 0,
            "breaches": 0,
            "open": 0,
            "payout_rate": 0.0,
            "breach_rate": 0.0,
            "ev_r": 0.0,
            "avg_days_payout": 0.0,
            "avg_days_breach": 0.0,
            "avg_trades_payout": 0.0,
            "avg_trades_breach": 0.0,
            "avg_final_r_open": 0.0,
            "max_consec_breaches": 0,
        }
        return empty, pd.DataFrame()

    trade_rows = [
        {
            "date": dt.date.fromisoformat(str(row.date)),
            "signal_ts": row.signal_ts,
            "r": float(getattr(row, r_column)),
        }
        for row in filled.itertuples(index=False)
    ]

    d_start = dt.date.fromisoformat(start)
    d_end = dt.date.fromisoformat(end)
    account_starts = []
    current = d_start
    while current <= d_end:
        account_starts.append(current)
        current += dt.timedelta(days=CYCLE_DAYS)

    outcomes = []
    for account_start in account_starts:
        cum_r = 0.0
        outcome = "open"
        outcome_date = account_start
        trades_taken = 0
        for trade in trade_rows:
            if trade["date"] < account_start:
                continue
            cum_r += trade["r"]
            trades_taken += 1
            outcome_date = trade["date"]
            if cum_r >= PAYOUT_R:
                outcome = "payout"
                break
            if cum_r <= BREACH_R:
                outcome = "breach"
                break
        outcomes.append(
            {
                "account_start": account_start.isoformat(),
                "outcome": outcome,
                "final_r": float(cum_r),
                "trades_taken": int(trades_taken),
                "calendar_days": int((outcome_date - account_start).days + 1),
            }
        )

    out = pd.DataFrame(outcomes)
    payouts = out[out["outcome"] == "payout"]
    breaches = out[out["outcome"] == "breach"]
    opens = out[out["outcome"] == "open"]
    capped = np.where(
        out["outcome"].eq("payout"),
        PAYOUT_R,
        np.where(out["outcome"].eq("breach"), BREACH_R, out["final_r"]),
    )

    consec = 0
    max_consec = 0
    for outcome in out["outcome"]:
        if outcome == "breach":
            consec += 1
            max_consec = max(max_consec, consec)
        elif outcome == "payout":
            consec = 0

    summary = {
        "accounts": int(len(out)),
        "payouts": int(len(payouts)),
        "breaches": int(len(breaches)),
        "open": int(len(opens)),
        "payout_rate": float(len(payouts) / len(out)) if len(out) else 0.0,
        "breach_rate": float(len(breaches) / len(out)) if len(out) else 0.0,
        "ev_r": float(np.mean(capped)) if len(capped) else 0.0,
        "avg_days_payout": float(payouts["calendar_days"].mean()) if len(payouts) else 0.0,
        "avg_days_breach": float(breaches["calendar_days"].mean()) if len(breaches) else 0.0,
        "avg_trades_payout": float(payouts["trades_taken"].mean()) if len(payouts) else 0.0,
        "avg_trades_breach": float(breaches["trades_taken"].mean()) if len(breaches) else 0.0,
        "avg_final_r_open": float(opens["final_r"].mean()) if len(opens) else 0.0,
        "max_consec_breaches": int(max_consec),
    }
    return summary, out


def build_account_replay(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    summary_rows: list[dict[str, Any]] = []
    outcome_frames: list[pd.DataFrame] = []

    for spec in SELECTED_OVERLAYS:
        subset = data[
            (data["source"] == spec["source"])
            & (data["candidate"] == spec["candidate"])
            & (data["feature"] == spec["feature"])
            & (data["weight_profile"].isin(PROFILES))
        ].copy()
        if subset.empty:
            continue
        for profile, profile_df in subset.groupby("weight_profile"):
            for window, (start, end) in WINDOWS.items():
                profile_window = profile_df[(profile_df["date"] >= start) & (profile_df["date"] < end)]
                if profile_window.empty:
                    continue
                for mode, r_column in (("baseline", "r_multiple"), ("tiered", "weighted_r")):
                    account_summary, outcomes = simulate_accounts(
                        profile_window,
                        r_column=r_column,
                        start=start,
                        end=end,
                    )
                    row = {
                        "source": spec["source"],
                        "overlay_key": spec["key"],
                        "candidate": spec["candidate"],
                        "feature": spec["feature"],
                        "thesis": spec["thesis"],
                        "weight_profile": profile,
                        "window": window,
                        "mode": mode,
                        "start": start,
                        "end": end,
                        "trade_rows": int(len(profile_window)),
                        "total_r": float(profile_window[r_column].sum()),
                        "avg_r": float(profile_window[r_column].mean()),
                        "avg_risk_weight": float(profile_window["risk_weight"].mean()),
                        "deployability": "research_only",
                        "exact_replay_required": True,
                    }
                    row.update(account_summary)
                    summary_rows.append(row)
                    if not outcomes.empty:
                        outcomes = outcomes.assign(
                            source=spec["source"],
                            overlay_key=spec["key"],
                            candidate=spec["candidate"],
                            feature=spec["feature"],
                            weight_profile=profile,
                            window=window,
                            mode=mode,
                        )
                        outcome_frames.append(outcomes)

    summary = pd.DataFrame(summary_rows)
    outcomes = pd.concat(outcome_frames, ignore_index=True) if outcome_frames else pd.DataFrame()

    if not summary.empty:
        baseline = summary[summary["mode"] == "baseline"].copy()
        tiered = summary[summary["mode"] == "tiered"].copy()
        keys = ["source", "overlay_key", "candidate", "feature", "weight_profile", "window"]
        compare = tiered.merge(
            baseline[
                keys
                + [
                    "payout_rate",
                    "breach_rate",
                    "ev_r",
                    "avg_days_payout",
                    "total_r",
                    "avg_r",
                ]
            ],
            on=keys,
            how="left",
            suffixes=("", "_baseline"),
        )
        for _, row in compare.iterrows():
            mask = (
                (summary["source"] == row["source"])
                & (summary["overlay_key"] == row["overlay_key"])
                & (summary["candidate"] == row["candidate"])
                & (summary["feature"] == row["feature"])
                & (summary["weight_profile"] == row["weight_profile"])
                & (summary["window"] == row["window"])
                & (summary["mode"] == "tiered")
            )
            summary.loc[mask, "delta_payout_rate"] = row["payout_rate"] - row["payout_rate_baseline"]
            summary.loc[mask, "delta_breach_rate"] = row["breach_rate"] - row["breach_rate_baseline"]
            summary.loc[mask, "delta_ev_r"] = row["ev_r"] - row["ev_r_baseline"]
            summary.loc[mask, "delta_total_r"] = row["total_r"] - row["total_r_baseline"]
    return summary, outcomes


def write_report(report_path: Path, summary: pd.DataFrame, output_dir: Path) -> None:
    tiered = summary[summary["mode"] == "tiered"].copy()
    post = tiered[tiered["window"] == "post_2023"].copy()
    post = post.sort_values(["delta_ev_r", "payout_rate", "breach_rate"], ascending=[False, False, True])
    holdout = tiered[tiered["window"] == "holdout"].copy()
    holdout = holdout.sort_values(["delta_ev_r", "payout_rate", "breach_rate"], ascending=[False, False, True])

    lines = [
        "# NQ NY LSI Dynamic Sizing Phase-One Replay",
        "",
        "- Objective: no-fetch account-objective replay for the orderbook and sweep-reclaim dynamic sizing overlays.",
        "- Model: stagger a new account every 14 calendar days; payout at `+5R`; breach at `-4R`.",
        "- Inputs: existing trade-level baseline R and weighted R from prior overlay replay CSVs; no new market data fetch.",
        "- Caveat: this is not yet exact engine execution. It is a trade-level account replay to rank which overlays deserve exact replay.",
        "",
        "## Post-2023 Tiered Results",
        "",
        "| Source | Overlay | Profile | Trades | Total R | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for _, row in post.iterrows():
        lines.append(
            f"| {row['source']} | `{row['overlay_key']}` | `{row['weight_profile']}` | "
            f"{int(row['trade_rows'])} | {row['total_r']:.2f} | {row['payout_rate']:.1%} | "
            f"{row['breach_rate']:.1%} | {row['ev_r']:.2f}R | "
            f"{row.get('delta_ev_r', 0.0):+.2f}R | {row.get('delta_payout_rate', 0.0):+.1%} | "
            f"{row.get('delta_breach_rate', 0.0):+.1%} |"
        )

    lines.extend(
        [
            "",
            "## Holdout Tiered Results",
            "",
            "| Source | Overlay | Profile | Trades | Total R | Payout | Breach | EV/account | Delta EV | Delta Payout | Delta Breach |",
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for _, row in holdout.iterrows():
        lines.append(
            f"| {row['source']} | `{row['overlay_key']}` | `{row['weight_profile']}` | "
            f"{int(row['trade_rows'])} | {row['total_r']:.2f} | {row['payout_rate']:.1%} | "
            f"{row['breach_rate']:.1%} | {row['ev_r']:.2f}R | "
            f"{row.get('delta_ev_r', 0.0):+.2f}R | {row.get('delta_payout_rate', 0.0):+.1%} | "
            f"{row.get('delta_breach_rate', 0.0):+.1%} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Favor overlays that improve EV/account without raising breach rate materially.",
            "- Aggregate R can improve while payout behavior worsens; this table is the account-objective check before exact replay.",
            "- Use the conservative profile first when account EV is close, because it is less likely to overstate capacity.",
            "",
            "## Output Files",
            "",
            f"- `{output_dir / 'account_summary.csv'}`",
            f"- `{output_dir / 'account_outcomes.csv'}`",
            f"- `{output_dir / 'summary.json'}`",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines))


def main() -> int:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = load_replays()
    summary, outcomes = build_account_replay(data)
    summary_path = args.output_dir / "account_summary.csv"
    outcomes_path = args.output_dir / "account_outcomes.csv"
    summary.to_csv(summary_path, index=False)
    outcomes.to_csv(outcomes_path, index=False)
    save_json(
        args.output_dir / "summary.json",
        {
            "run_slug": RUN_SLUG,
            "payout_r": PAYOUT_R,
            "breach_r": BREACH_R,
            "cycle_days": CYCLE_DAYS,
            "orderbook_replay": str(ORDERBOOK_REPLAY),
            "sweep_reclaim_replay": str(SWEEP_RECLAIM_REPLAY),
            "outputs": {
                "account_summary": str(summary_path),
                "account_outcomes": str(outcomes_path),
                "report": str(args.report_path),
            },
        },
    )
    write_report(args.report_path, summary, args.output_dir)
    print(f"Wrote {summary_path}", flush=True)
    print(f"Wrote {args.report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
