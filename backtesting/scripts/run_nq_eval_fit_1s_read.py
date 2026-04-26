#!/usr/bin/env python3
"""Exact 1-second eval-fit read for the top NQ pass candidates.

This script answers a narrow practical question:

- Which current NQ branches are the best fit for one- or two-shot eval passes?
- How often do they truly reach 1.2R / 1.5R on exact 1-second paths?
- Once they hit those levels, how often do they give the move back?

Method:
- Re-run the top three NQ candidates on the recent window.
- Use 5m signals with 1m/1s magnifier enabled for the trade stream itself.
- For each filled trade, infer the earliest 1-second touch of the limit price
  inside the recorded fill bar, then walk the exact 1-second path to session
  flat.
- Record exact MFE/MAE plus first-passage outcomes to 1.2R and 1.5R.

This is a diagnostic research packet, not a promotion workflow.
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.gates import TUE, apply_dow_filter  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar, _regime_lookup  # noqa: E402
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import DATA_DIR  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, build_maps, run_backtest  # noqa: E402


WARMUP_START = "2024-01-01"
START_DATE = "2024-04-01"
END_DATE = "2026-03-25"  # exclusive for backtest start-date filtering
DATA_END_DATE = "2026-03-26"  # includes overnight flat bars after END_DATE-1 entries

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}
TARGETS_R = (1.2, 1.5)

OUTPUT_DIR = ROOT / "data" / "results" / "nq_eval_fit_1s_read"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_EVAL_FIT_1S_READ.md"


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    config: StrategyConfig
    gate_fn: Callable[[list[TradeResult]], list[TradeResult]] | None = None
    dow_filter: set[int] | None = None


def _load_filtered_ohlcv(filename: str, start: str, end: str) -> pd.DataFrame:
    """Load parquet/csv data with date filtering at read time when possible."""
    stem = (DATA_DIR / filename).with_suffix("")
    parquet = stem.with_suffix(".parquet")
    csv = stem.with_suffix(".csv")

    if parquet.exists():
        filters = [
            ("datetime", ">=", pd.Timestamp(start)),
            ("datetime", "<", pd.Timestamp(end)),
        ]
        return pd.read_parquet(parquet, filters=filters)

    if csv.exists():
        df = pd.read_csv(csv, parse_dates=["datetime"], index_col="datetime")
        return df[(df.index >= start) & (df.index < end)]

    raise FileNotFoundError(f"No parquet/csv found for {stem}")


def make_medium_vol_gate(df_5m: pd.DataFrame) -> Callable[[list[TradeResult]], list[TradeResult]]:
    lookup = _regime_lookup(build_extended_regime_calendar(df_5m), "combined_regime")

    def gate(trades: list[TradeResult]) -> list[TradeResult]:
        return [
            trade
            for trade in trades
            if trade.exit_type == EXIT_NO_FILL or lookup.get(trade.date) not in AVOID_BUCKETS
        ]

    return gate


def build_candidates(df_5m: pd.DataFrame) -> list[Candidate]:
    medium_vol_gate = make_medium_vol_gate(df_5m)

    alpha_v1_asia = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="07:00",
                stop_orb_pct=100.0,
                min_gap_orb_pct=10.0,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        direction_filter="long",
        use_bar_magnifier=True,
        rr=6.0,
        tp1_ratio=0.3,
        atr_length=5,
        risk_usd=5000.0,
        excluded_days=(1,),
        name="NQ Asia ORB ALPHA_V1 Eval Read",
    )

    asia_r9 = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="22:30",
                flat_start="04:00",
                flat_end="07:00",
                stop_atr_pct=4.0,
                min_gap_atr_pct=0.90,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.0,
        tp1_ratio=0.6,
        atr_length=5,
        impulse_close_filter=True,
        name="NQ Asia R9 Restart Eval Read",
    )

    asia_phase_one = StrategyConfig(
        sessions=(
            SessionConfig(
                name="Asia",
                orb_start="20:00",
                orb_end="20:15",
                entry_start="20:15",
                entry_end="23:15",
                flat_start="04:00",
                flat_end="07:00",
                stop_orb_pct=100.0,
                min_gap_atr_pct=1.0,
            ),
        ),
        instrument=NQ,
        strategy="continuation",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        direction_filter="long",
        rr=3.5,
        tp1_ratio=0.6,
        atr_length=14,
        name="NQ Asia-2 Phase-One Winner Eval Read",
    )

    return [
        Candidate(
            key="alpha_v1_asia",
            label="NQ Asia ORB ALPHA_V1",
            config=alpha_v1_asia,
            dow_filter={TUE},
        ),
        Candidate(
            key="asia_r9",
            label="NQ Asia R9 Restart",
            config=asia_r9,
            dow_filter={TUE},
        ),
        Candidate(
            key="asia_phase1",
            label="NQ Asia-2 phase-one winner",
            config=asia_phase_one,
            gate_fn=medium_vol_gate,
        ),
    ]


def session_flat_timestamp(entry_ts: pd.Timestamp, flat_start: str) -> pd.Timestamp:
    hh, mm = map(int, flat_start.split(":"))
    flat_ts = pd.Timestamp(
        year=entry_ts.year,
        month=entry_ts.month,
        day=entry_ts.day,
        hour=hh,
        minute=mm,
    )
    if flat_ts <= entry_ts:
        flat_ts += pd.Timedelta(days=1)
    return flat_ts


def infer_exact_fill_time(trade: TradeResult, df_1s: pd.DataFrame) -> pd.Timestamp:
    """Infer the earliest 1-second touch of the entry price inside the 5m fill bar."""
    fill_bar_ts = pd.Timestamp(trade.fill_time)
    window_end = fill_bar_ts + pd.Timedelta(minutes=5)
    window = df_1s.loc[fill_bar_ts:window_end - pd.Timedelta(seconds=1)]
    if window.empty:
        return fill_bar_ts

    if trade.direction == 1:
        touched = window[window["low"] <= trade.entry_price]
    else:
        touched = window[window["high"] >= trade.entry_price]

    return touched.index[0] if not touched.empty else fill_bar_ts


def first_passage_outcome(
    path: pd.DataFrame,
    *,
    direction: int,
    entry_price: float,
    stop_price: float,
    risk_points: float,
    target_r: float,
    fill_ts: pd.Timestamp,
) -> tuple[str, pd.Timestamp | None]:
    """Return the first exact 1-second outcome toward target_r.

    Outcomes:
    - target: target touched before stop/flat
    - stop: stop touched before target/flat
    - flat: session flat reached first
    - ambiguous: same 1s bar can support multiple orderings
    """
    target_price = entry_price + direction * target_r * risk_points

    for ts, row in path.iterrows():
        if direction == 1:
            stop_hit = row.low <= stop_price
            target_hit = row.high >= target_price
        else:
            stop_hit = row.high >= stop_price
            target_hit = row.low <= target_price

        # On the inferred fill second we do not know the within-second ordering.
        if ts == fill_ts and (stop_hit or target_hit):
            return "ambiguous", ts
        if stop_hit and target_hit:
            return "ambiguous", ts
        if target_hit:
            return "target", ts
        if stop_hit:
            return "stop", ts

    return "flat", None


def worst_future_r(
    path_after_hit: pd.DataFrame,
    *,
    direction: int,
    entry_price: float,
    risk_points: float,
) -> float | None:
    if path_after_hit.empty:
        return None
    if direction == 1:
        return float(((path_after_hit["low"] - entry_price) / risk_points).min())
    return float(((entry_price - path_after_hit["high"]) / risk_points).min())


def analyze_trade_path(
    candidate_key: str,
    trade: TradeResult,
    df_1s: pd.DataFrame,
    flat_start: str,
) -> dict | None:
    if trade.exit_type == EXIT_NO_FILL or not trade.fill_time:
        return None

    exact_fill_ts = infer_exact_fill_time(trade, df_1s)
    flat_ts = session_flat_timestamp(exact_fill_ts, flat_start)
    path = df_1s.loc[exact_fill_ts:flat_ts]
    if path.empty:
        return None

    direction = int(trade.direction)
    entry_price = float(trade.entry_price)
    stop_price = float(trade.stop_price)
    risk_points = float(trade.risk_points)

    if direction == 1:
        mfe_r = float(((path["high"] - entry_price) / risk_points).max())
        mae_r = float(((entry_price - path["low"]) / risk_points).max())
    else:
        mfe_r = float(((entry_price - path["low"]) / risk_points).max())
        mae_r = float(((path["high"] - entry_price) / risk_points).max())

    row = {
        "candidate_key": candidate_key,
        "date": trade.date,
        "entry_time": trade.fill_time,
        "exact_fill_time": exact_fill_ts.isoformat(),
        "exit_time": trade.exit_time,
        "direction": "long" if direction == 1 else "short",
        "entry_price": entry_price,
        "stop_price": stop_price,
        "risk_points": risk_points,
        "backtest_r_multiple": float(trade.r_multiple),
        "mfe_r_exact": mfe_r,
        "mae_r_exact": mae_r,
    }

    for target_r in TARGETS_R:
        key = f"{target_r:.1f}".replace(".", "p")
        outcome, hit_ts = first_passage_outcome(
            path,
            direction=direction,
            entry_price=entry_price,
            stop_price=stop_price,
            risk_points=risk_points,
            target_r=target_r,
            fill_ts=exact_fill_ts,
        )
        row[f"outcome_{key}"] = outcome
        row[f"hit_{key}"] = outcome == "target"

        if hit_ts is not None and outcome == "target":
            future_path = path.loc[hit_ts:].iloc[1:]
            worst_r = worst_future_r(
                future_path,
                direction=direction,
                entry_price=entry_price,
                risk_points=risk_points,
            )
            row[f"post_hit_worst_r_{key}"] = worst_r
            row[f"retrace_be_or_worse_{key}"] = (worst_r is not None) and (worst_r <= 0.0)
        else:
            row[f"post_hit_worst_r_{key}"] = None
            row[f"retrace_be_or_worse_{key}"] = False

    return row


def summarize_candidate(candidate: Candidate, trade_rows: pd.DataFrame) -> dict:
    if trade_rows.empty:
        return {
            "candidate_key": candidate.key,
            "label": candidate.label,
            "trades": 0,
        }

    days = (pd.Timestamp(END_DATE) - pd.Timestamp(START_DATE)).days
    trades_per_month = len(trade_rows) / (days / 30.4375)
    summary = {
        "candidate_key": candidate.key,
        "label": candidate.label,
        "trades": int(len(trade_rows)),
        "trade_days": int(trade_rows["date"].nunique()),
        "trades_per_month": float(trades_per_month),
        "rr": float(candidate.config.rr),
        "tp1_ratio": float(candidate.config.tp1_ratio),
        "tp1_r": float(candidate.config.rr * candidate.config.tp1_ratio),
        "avg_mfe_r_exact": float(trade_rows["mfe_r_exact"].mean()),
        "median_mfe_r_exact": float(trade_rows["mfe_r_exact"].median()),
        "avg_mae_r_exact": float(trade_rows["mae_r_exact"].mean()),
        "median_mae_r_exact": float(trade_rows["mae_r_exact"].median()),
    }

    for target_r in TARGETS_R:
        key = f"{target_r:.1f}".replace(".", "p")
        hit_mask = trade_rows[f"hit_{key}"]
        hit_count = int(hit_mask.sum())
        summary[f"pass_rate_{key}"] = float(hit_mask.mean())
        summary[f"days_per_hit_{key}"] = (days / hit_count) if hit_count else math.inf
        summary[f"stop_before_{key}"] = float((trade_rows[f"outcome_{key}"] == "stop").mean())
        summary[f"flat_before_{key}"] = float((trade_rows[f"outcome_{key}"] == "flat").mean())
        summary[f"ambiguous_{key}"] = float((trade_rows[f"outcome_{key}"] == "ambiguous").mean())
        if hit_count:
            worst = trade_rows.loc[hit_mask, f"post_hit_worst_r_{key}"].dropna()
            summary[f"retrace_be_or_worse_{key}"] = float(
                trade_rows.loc[hit_mask, f"retrace_be_or_worse_{key}"].mean()
            )
            summary[f"median_post_hit_worst_r_{key}"] = float(worst.median()) if not worst.empty else None
        else:
            summary[f"retrace_be_or_worse_{key}"] = 0.0
            summary[f"median_post_hit_worst_r_{key}"] = None

    p_15 = summary["pass_rate_1p5"]
    summary["lucid_two_wins_before_two_losses_1p5"] = float(p_15 * p_15 * (3.0 - 2.0 * p_15))
    return summary


def write_report(summary_df: pd.DataFrame) -> None:
    lines = [
        "# NQ Eval Fit 1s Read",
        "",
        "- Objective: test which current NQ branches are the cleanest fits for Lucid / Apex-style eval passes.",
        f"- Window: `{START_DATE}` to `{pd.Timestamp(END_DATE) - pd.Timedelta(days=1):%Y-%m-%d}`.",
        "- Targets tested on exact 1-second paths: `1.2R` and `1.5R`.",
        "- Fill handling: each trade's exact fill was inferred as the earliest `1s` touch of the limit price inside the recorded `5m` fill bar.",
        "- Ambiguity handling: if the fill second or any later `1s` bar could support multiple orderings (for example stop and target in the same second), that target read is marked `ambiguous` rather than forced.",
        "",
        "## Candidate Summary",
        "",
        "| Candidate | Trades | Trades / Month | TP1 in R | Pass 1.2R | Pass 1.5R | Lucid 2-win approx | Retrace <= BE after 1.2R | Retrace <= BE after 1.5R | Median worst R after 1.2R hit | Median worst R after 1.5R hit |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    for _, row in summary_df.iterrows():
        lines.append(
            "| "
            + " | ".join(
                [
                    row["label"],
                    str(int(row["trades"])),
                    f"{row['trades_per_month']:.2f}",
                    f"{row['tp1_r']:.2f}",
                    f"{row['pass_rate_1p2']:.1%}",
                    f"{row['pass_rate_1p5']:.1%}",
                    f"{row['lucid_two_wins_before_two_losses_1p5']:.1%}",
                    f"{row['retrace_be_or_worse_1p2']:.1%}",
                    f"{row['retrace_be_or_worse_1p5']:.1%}",
                    "NA"
                    if pd.isna(row["median_post_hit_worst_r_1p2"])
                    else f"{row['median_post_hit_worst_r_1p2']:.2f}",
                    "NA"
                    if pd.isna(row["median_post_hit_worst_r_1p5"])
                    else f"{row['median_post_hit_worst_r_1p5']:.2f}",
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            "- `NQ Asia ORB ALPHA_V1` is the cleanest `1.5R` pass branch. It has the best exact `1.5R` hit rate and the best giveback profile of the top two Asia candidates.",
            "- `NQ Asia R9 Restart` is the raw `1.2R` leader, but it gives back the most after hitting target. That makes it attractive only if the eval plan explicitly locks the win near the target instead of letting the trade breathe.",
            "- `NQ Asia-2 phase-one winner` is the higher-flow backup. It trails the top two on pass rate, but it resolves more often because it trades more frequently.",
            "",
        ]
    )

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    print("NQ Eval Fit 1s Read")
    print("=" * 60)
    print("Loading filtered NQ data...")

    df_5m = _load_filtered_ohlcv("NQ_5m.parquet", WARMUP_START, DATA_END_DATE)
    df_1m = _load_filtered_ohlcv("NQ_1m.parquet", WARMUP_START, DATA_END_DATE)
    df_1s = _load_filtered_ohlcv("NQ_1s.parquet", WARMUP_START, DATA_END_DATE)

    print(f"  5m bars: {len(df_5m):,}")
    print(f"  1m bars: {len(df_1m):,}")
    print(f"  1s bars: {len(df_1s):,}")

    maps = build_maps(df_5m, df_1m=df_1m, df_1s=df_1s)
    candidates = build_candidates(df_5m)

    all_trade_rows: list[dict] = []
    summary_rows: list[dict] = []

    for candidate in candidates:
        print(f"\nRunning {candidate.label}...")
        trades = run_backtest(
            df_5m,
            candidate.config,
            start_date=START_DATE,
            end_date=END_DATE,
            df_1m=df_1m,
            signal_df_1m=df_1m,
            df_1s=df_1s,
            _maps=maps,
        )
        if candidate.gate_fn is not None:
            trades = candidate.gate_fn(trades)
        if candidate.dow_filter:
            trades = apply_dow_filter(trades, candidate.dow_filter)

        rows = [
            analyze_trade_path(candidate.key, trade, df_1s, candidate.config.sessions[0].flat_start)
            for trade in trades
        ]
        candidate_trade_df = pd.DataFrame([row for row in rows if row is not None])
        all_trade_rows.extend(candidate_trade_df.to_dict(orient="records"))

        summary = summarize_candidate(candidate, candidate_trade_df)
        summary_rows.append(summary)
        print(
            "  "
            f"trades={summary['trades']} | "
            f"pass1.2={summary['pass_rate_1p2']:.1%} | "
            f"pass1.5={summary['pass_rate_1p5']:.1%}"
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(
        ["pass_rate_1p5", "pass_rate_1p2", "trades_per_month"],
        ascending=False,
    )
    trade_df = pd.DataFrame(all_trade_rows)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(OUTPUT_DIR / "candidate_summary.csv", index=False)
    trade_df.to_csv(OUTPUT_DIR / "trade_path_summary.csv", index=False)
    payload = {
        "window": {
            "warmup_start": WARMUP_START,
            "start": START_DATE,
            "end_exclusive": END_DATE,
            "data_end_exclusive": DATA_END_DATE,
        },
        "targets_r": list(TARGETS_R),
        "summary": summary_df.to_dict(orient="records"),
    }
    (OUTPUT_DIR / "summary.json").write_text(json.dumps(payload, indent=2))

    write_report(summary_df)

    print("\nTop line:")
    for _, row in summary_df.iterrows():
        print(
            f"  {row['label']}: "
            f"1.2R={row['pass_rate_1p2']:.1%}, "
            f"1.5R={row['pass_rate_1p5']:.1%}, "
            f"giveback_after_1.5R={row['retrace_be_or_worse_1p5']:.1%}"
        )

    print(f"\nSaved summary to {OUTPUT_DIR}")
    print(f"Saved report to {REPORT_PATH}")


if __name__ == "__main__":
    main()
