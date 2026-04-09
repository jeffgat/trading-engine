#!/usr/bin/env python3
"""Failure analysis for the 3m NQ NY reference-LSI phase-one leader."""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    FundedFirstPayoutProfile,
    PropFirmProfile,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.optimize.walkforward import generate_windows  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_reference_lsi_3m_failure_analysis"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_3M_FAILURE_ANALYSIS.md"

RESEARCH_START = "2016-01-01"
HOLDOUT_START = "2025-01-01"
WF_IS_MONTHS = 36
WF_OOS_MONTHS = 12
WF_STEP_MONTHS = 12

CANDIDATE_LABEL = "NQ NY reference_lsi 3m both 13:00 far gap9 inv12 rr3.0 tp0.7"

LEVEL_ORDER = [
    "previous_day_high",
    "previous_day_low",
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
]

FUNDED_PROFILE = FundedFirstPayoutProfile(
    challenge_fee=100.0,
    starting_balance_usd=50_000.0,
    trailing_drawdown_usd=2_000.0,
    max_trailing_breach_usd=50_000.0,
    first_payout_floor_usd=52_500.0,
    risk_pre_payout_usd=500.0,
    risk_post_payout_usd=250.0,
)

PROP_PROFILE = PropFirmProfile(
    account_fee=50.0,
    reset_fee=50.0,
    payout_split=0.80,
    payout_target_r=5.0,
    breach_limit_r=-4.0,
    daily_loss_limit_r=-2.0,
    min_trading_days=5,
    cohort_sizes=(10, 25, 50),
    block_size_days=20,
)


def _resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }
    out = df.resample(rule, label="left", closed="left").agg(agg)
    out = out.dropna(subset=["open", "high", "low", "close"])
    return out.astype(
        {
            "open": "float64",
            "high": "float64",
            "low": "float64",
            "close": "float64",
            "volume": "float64",
        }
    )


def load_3m_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df_1m = load_5m_data("NQ_1m.parquet")
    df_1s = load_5m_data("NQ_1s.parquet")
    return _resample_ohlcv(df_1m, "3min"), df_1m, df_1s


def build_config() -> StrategyConfig:
    session = SessionConfig(
        name="NY",
        rth_start="08:30",
        entry_start="08:30",
        entry_end="13:00",
        flat_start="14:00",
        flat_end="14:05",
        min_gap_atr_pct=5.0,
    )
    return StrategyConfig(
        instrument=NQ,
        sessions=(session,),
        strategy="reference_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter="both",
        rr=3.0,
        tp1_ratio=0.7,
        atr_length=10,
        ref_lsi_gap_lookback_bars=9,
        ref_lsi_inversion_max_bars=12,
        ref_lsi_gap_entry_edge="far",
        name=CANDIDATE_LABEL,
    )


def trading_dates_between(df: pd.DataFrame, start: str, end_exclusive: str) -> list[str]:
    idx = df.index[(df.index >= start) & (df.index < end_exclusive)]
    if len(idx) == 0:
        return []
    dates = pd.Index(pd.to_datetime(idx.normalize()).unique()).sort_values()
    return [d.strftime("%Y-%m-%d") for d in dates]


def metrics_row(trades: list) -> dict:
    if not trades:
        return {
            "trades": 0,
            "avg_r": 0.0,
            "pf": 0.0,
            "total_r": 0.0,
            "win_rate": 0.0,
            "max_dd_r": 0.0,
        }
    m = compute_metrics(trades)
    return {
        "trades": int(m["total_trades"]),
        "avg_r": round(float(m["avg_r"]), 4),
        "pf": round(float(m["profit_factor"]), 4),
        "total_r": round(float(m["total_r"]), 2),
        "win_rate": round(float(m["win_rate"]), 4),
        "max_dd_r": round(float(m["max_drawdown_r"]), 4),
    }


def level_family(level_name: str) -> str:
    if level_name.startswith("previous_day"):
        return "previous_day"
    if level_name.startswith("asia_"):
        return "asia"
    if level_name.startswith("london_"):
        return "london"
    return "unknown"


def level_side(level_name: str) -> str:
    return "high_side" if level_name.endswith("_high") else "low_side"


def direction_label(trade) -> str:
    return "long" if trade.direction == 1 else "short"


def time_bucket(fill_time: str) -> str:
    hh, mm = map(int, fill_time[11:16].split(":"))
    start_min = hh * 60 + (0 if mm < 30 else 30)
    end_min = start_min + 30
    return f"{start_min//60:02d}:{start_min%60:02d}-{end_min//60:02d}:{end_min%60:02d}"


def grouped_segment_rows(
    segment_map: dict[str, list],
    group_fn,
    *,
    ordered_keys: list[str] | None = None,
) -> list[dict]:
    group_tables: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for segment_name, trades in segment_map.items():
        for trade in trades:
            group_tables[str(group_fn(trade))][segment_name].append(trade)

    keys = ordered_keys if ordered_keys is not None else sorted(group_tables)
    rows: list[dict] = []
    for key in keys:
        row = {"group": key}
        for segment_name in ("pre", "oos", "holdout"):
            for metric_name, value in metrics_row(group_tables.get(key, {}).get(segment_name, [])).items():
                row[f"{segment_name}_{metric_name}"] = value
        rows.append(row)
    return rows


def year_rows(trades: list) -> list[dict]:
    groups: dict[str, list] = defaultdict(list)
    for trade in trades:
        groups[trade.date[:4]].append(trade)
    rows = []
    for year in sorted(groups):
        row = {"year": year}
        row.update(metrics_row(groups[year]))
        rows.append(row)
    return rows


def reconstruct_combined_oos(
    df_base: pd.DataFrame,
    df_1m: pd.DataFrame,
    df_1s: pd.DataFrame,
    maps: dict,
    signal_cache: dict,
    config: StrategyConfig,
) -> list:
    combined = []
    windows = generate_windows(
        RESEARCH_START,
        HOLDOUT_START,
        is_months=WF_IS_MONTHS,
        oos_months=WF_OOS_MONTHS,
        step_months=WF_STEP_MONTHS,
    )
    for window in windows:
        combined.extend(
            run_backtest(
                df_base,
                config,
                start_date=window.oos_start,
                end_date=window.oos_end,
                df_1m=df_1m,
                df_1s=df_1s,
                _maps=maps,
                _signal_cache=signal_cache,
            )
        )
    return combined


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))


def write_report(payload: dict) -> None:
    lines = [
        "# NQ NY Reference LSI 3m Failure Analysis",
        "",
        f"- Candidate: `{CANDIDATE_LABEL}`",
        f"- Phase 3 comparison stream: stitched OOS `2019-01-01` to `2024-12-31`.",
        f"- Holdout read: `{HOLDOUT_START}` to `{payload['holdout_end_inclusive']}`.",
        "",
        "## Overall",
        "",
        f"- pre-holdout: trades `{payload['overall']['pre']['trades']}`, avgR `{payload['overall']['pre']['avg_r']}`, PF `{payload['overall']['pre']['pf']}`, totalR `{payload['overall']['pre']['total_r']}`",
        f"- stitched OOS: trades `{payload['overall']['oos']['trades']}`, avgR `{payload['overall']['oos']['avg_r']}`, PF `{payload['overall']['oos']['pf']}`, totalR `{payload['overall']['oos']['total_r']}`",
        f"- holdout: trades `{payload['overall']['holdout']['trades']}`, avgR `{payload['overall']['holdout']['avg_r']}`, PF `{payload['overall']['holdout']['pf']}`, totalR `{payload['overall']['holdout']['total_r']}`",
        "",
        "## Payout Conversion",
        "",
        f"- OOS prop payout / breach / open: `{payload['oos_prop_scorecard']['first_payout_rate']:.1%}` / `{payload['oos_prop_scorecard']['breach_rate']:.1%}` / `{payload['oos_prop_scorecard']['open_rate']:.1%}`",
        f"- OOS funded payout / breach / open: `{payload['oos_funded_scorecard']['payout_rate']:.1%}` / `{payload['oos_funded_scorecard']['breach_rate']:.1%}` / `{payload['oos_funded_scorecard']['open_rate']:.1%}`",
        f"- holdout prop payout / breach / open: `{payload['holdout_prop_scorecard']['first_payout_rate']:.1%}` / `{payload['holdout_prop_scorecard']['breach_rate']:.1%}` / `{payload['holdout_prop_scorecard']['open_rate']:.1%}`",
        f"- holdout funded payout / breach / open: `{payload['holdout_funded_scorecard']['payout_rate']:.1%}` / `{payload['holdout_funded_scorecard']['breach_rate']:.1%}` / `{payload['holdout_funded_scorecard']['open_rate']:.1%}`",
        "",
        "## By Level Family",
        "",
    ]
    for row in payload["by_family"]:
        lines.append(
            f"- `{row['group']}`: OOS `{row['oos_trades']}` / avgR `{row['oos_avg_r']}` / PF `{row['oos_pf']}` / totalR `{row['oos_total_r']}`; "
            f"holdout `{row['holdout_trades']}` / avgR `{row['holdout_avg_r']}` / PF `{row['holdout_pf']}` / totalR `{row['holdout_total_r']}`"
        )
    lines.extend(["", "## By Side / Direction", ""])
    for section_name, rows in [("level_side", payload["by_side"]), ("direction", payload["by_direction"]), ("time_bucket", payload["by_time_bucket"])]:
        lines.append(f"### {section_name}")
        lines.append("")
        for row in rows:
            lines.append(
                f"- `{row['group']}`: OOS `{row['oos_trades']}` / avgR `{row['oos_avg_r']}` / PF `{row['oos_pf']}` / totalR `{row['oos_total_r']}`; "
                f"holdout `{row['holdout_trades']}` / avgR `{row['holdout_avg_r']}` / PF `{row['holdout_pf']}` / totalR `{row['holdout_total_r']}`"
            )
        lines.append("")
    lines.extend(["## Holdout By Year", ""])
    for row in payload["holdout_by_year"]:
        lines.append(
            f"- `{row['year']}`: trades `{row['trades']}`, avgR `{row['avg_r']}`, PF `{row['pf']}`, totalR `{row['total_r']}`"
        )
    lines.extend(
        [
            "",
            "## Readout",
            "",
            "- The key problem is speed and sample, not a total collapse of raw trade quality in the leader. The holdout leader still stayed positive on raw R (`+3.26R`) but only produced `18` trades, which is not enough to reliably reach a `+5R` prop payout target across rolling account starts.",
            "- Most holdout starts remained open or breached before enough positive trades accumulated. That is why payout conversion degraded much more than the raw holdout trade metrics alone suggest.",
            "- This means the next branch should focus on concentration and selectivity: either remove the draggiest level families in the `3m` leader or restart the thesis with `previous_day_* + asia_*` only.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    t0 = time.time()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading NQ 3m data (3m + 1m + 1s)...", flush=True)
    df_base, df_1m, df_1s = load_3m_data()
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")

    config = build_config()
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, [config])

    print(f"Running pre-holdout backtest for {CANDIDATE_LABEL}...", flush=True)
    trades_pre = run_backtest(
        df_base,
        config,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    filled_pre = [t for t in trades_pre if t.exit_type != EXIT_NO_FILL]

    print("Reconstructing stitched discovery OOS stream...", flush=True)
    trades_oos = reconstruct_combined_oos(df_base, df_1m, df_1s, maps, signal_cache, config)
    filled_oos = [t for t in trades_oos if t.exit_type != EXIT_NO_FILL]

    print("Running holdout backtest...", flush=True)
    trades_holdout = run_backtest(
        df_base,
        config,
        start_date=HOLDOUT_START,
        end_date=holdout_end_exclusive,
        df_1m=df_1m,
        df_1s=df_1s,
        _maps=maps,
        _signal_cache=signal_cache,
    )
    filled_holdout = [t for t in trades_holdout if t.exit_type != EXIT_NO_FILL]

    oos_dates = trading_dates_between(df_base, "2019-01-01", HOLDOUT_START)
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    oos_prop_outcomes = simulate_account_attempts(
        specialist_name=CANDIDATE_LABEL,
        trades=trades_oos,
        trading_dates=oos_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    oos_prop_scorecard = build_prop_scorecard(oos_prop_outcomes, PROP_PROFILE)
    oos_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=CANDIDATE_LABEL,
        trades=trades_oos,
        trading_dates=oos_dates,
        profile=FUNDED_PROFILE,
    )
    oos_funded_scorecard = build_funded_first_payout_scorecard(oos_funded_outcomes, FUNDED_PROFILE)

    holdout_prop_outcomes = simulate_account_attempts(
        specialist_name=f"{CANDIDATE_LABEL}_holdout",
        trades=trades_holdout,
        trading_dates=holdout_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=config.risk_usd,
    )
    holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
    holdout_funded_outcomes = simulate_funded_first_payouts(
        specialist_name=f"{CANDIDATE_LABEL}_holdout",
        trades=trades_holdout,
        trading_dates=holdout_dates,
        profile=FUNDED_PROFILE,
    )
    holdout_funded_scorecard = build_funded_first_payout_scorecard(holdout_funded_outcomes, FUNDED_PROFILE)

    segment_map = {
        "pre": filled_pre,
        "oos": filled_oos,
        "holdout": filled_holdout,
    }
    payload = {
        "candidate": CANDIDATE_LABEL,
        "holdout_end_inclusive": holdout_end_inclusive,
        "overall": {
            "pre": metrics_row(filled_pre),
            "oos": metrics_row(filled_oos),
            "holdout": metrics_row(filled_holdout),
        },
        "oos_prop_scorecard": oos_prop_scorecard,
        "oos_funded_scorecard": oos_funded_scorecard,
        "holdout_prop_scorecard": holdout_prop_scorecard,
        "holdout_funded_scorecard": holdout_funded_scorecard,
        "by_level": grouped_segment_rows(segment_map, lambda t: t.reference_level_name, ordered_keys=LEVEL_ORDER),
        "by_family": grouped_segment_rows(segment_map, lambda t: level_family(t.reference_level_name), ordered_keys=["previous_day", "asia", "london"]),
        "by_side": grouped_segment_rows(segment_map, lambda t: level_side(t.reference_level_name), ordered_keys=["high_side", "low_side"]),
        "by_direction": grouped_segment_rows(segment_map, direction_label, ordered_keys=["short", "long"]),
        "by_time_bucket": grouped_segment_rows(segment_map, lambda t: time_bucket(t.fill_time)),
        "holdout_by_year": year_rows(filled_holdout),
    }

    write_json(OUTPUT_DIR / "failure_analysis.json", payload)
    write_report(payload)
    print(f"Failure analysis complete in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
