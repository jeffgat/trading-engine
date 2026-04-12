#!/usr/bin/env python3
"""One-time holdout read for gated HTF-LSI count-expansion contenders."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(SCRIPT_DIR))

from htf_lsi_common import build_config, load_timeframe_data, save_json  # noqa: E402
from orb_backtest.analysis.alpha_v1_downside import filter_trades_by_combined_regime  # noqa: E402
from orb_backtest.analysis.regime_research import build_extended_regime_calendar  # noqa: E402
from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    build_funded_first_payout_forecast,
    build_funded_first_payout_scorecard,
    build_prop_scorecard,
    simulate_account_attempts,
    simulate_funded_first_payouts,
)
from orb_backtest.engine.simulator import build_maps, build_signal_cache, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402
from run_nq_ny_htf_lsi_phase_one import (  # noqa: E402
    FUNDED_PROFILE,
    HOLDOUT_START,
    PROP_PROFILE,
    metrics_snapshot,
    trading_dates_between,
)


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_htf_lsi_gated_count_holdout"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_GATED_COUNT_HOLDOUT.md"


def build_candidates() -> list[dict]:
    return [
        {
            "label": "HTF_LSI 5m lag24 ungated lead",
            "gate_label": "ungated",
            "exclude_regimes": set(),
            "config": build_config(
                timeframe="5m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=24,
                name="HTF_LSI 5m lag24 ungated lead",
            ),
        },
        {
            "label": "HTF_LSI 5m gap2.5 right2 lag0 skip bear_high_vol",
            "gate_label": "skip_bear_high_vol",
            "exclude_regimes": {"bear_high_vol"},
            "config": build_config(
                timeframe="5m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=2.5,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=2,
                max_fvg_to_inversion_bars=0,
                name="HTF_LSI 5m gap2.5 right2 lag0 skip bear_high_vol",
            ),
        },
        {
            "label": "HTF_LSI 5m gap2.5 right3 lag0 skip bear_high_vol",
            "gate_label": "skip_bear_high_vol",
            "exclude_regimes": {"bear_high_vol"},
            "config": build_config(
                timeframe="5m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=2.5,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=2,
                lsi_fvg_window_left=20,
                lsi_fvg_window_right=3,
                max_fvg_to_inversion_bars=0,
                name="HTF_LSI 5m gap2.5 right3 lag0 skip bear_high_vol",
            ),
        },
    ]


def _year_metrics(trades, year_start: str, year_end: str) -> dict:
    window = [trade for trade in trades if year_start <= trade.date < year_end]
    return metrics_snapshot(compute_metrics(window))


def _rank_key(row: dict) -> tuple:
    holdout_prop = row["holdout_prop_scorecard"]
    holdout_funded = row["holdout_funded_scorecard"]
    holdout_metrics = row["holdout_metrics"]
    return (
        float(holdout_funded.get("payout_rate", 0.0)),
        float(holdout_prop.get("first_payout_rate", 0.0)),
        float(holdout_metrics.get("profit_factor", 0.0)),
        float(holdout_metrics.get("avg_r", 0.0)),
        float(holdout_metrics.get("total_r", 0.0)),
    )


def write_report(payload: dict) -> None:
    lines = [
        "# NQ NY HTF-LSI Gated Count Holdout",
        "",
        f"- One-time holdout comparison window: `{payload['info']['holdout_start']}` to `{payload['info']['holdout_end_inclusive']}`.",
        "- Candidates were frozen before opening holdout: current ungated `lag24` operating lead plus the two `gap2.5 lag0 + skip bear_high_vol` gated count challengers.",
        "",
        "## Summary",
        "",
        "| Candidate | Holdout Trades | PF | Avg R | Total R | Calmar | Prop Payout | Funded Payout |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in payload["results"]:
        holdout = row["holdout_metrics"]
        prop_sc = row["holdout_prop_scorecard"]
        funded_sc = row["holdout_funded_scorecard"]
        lines.append(
            f"| `{row['label']}` | {holdout['total_trades']} | {holdout['profit_factor']:.3f} | "
            f"{holdout['avg_r']:.3f} | {holdout['total_r']:.3f} | {holdout['calmar_ratio']:.3f} | "
            f"{prop_sc['first_payout_rate']:.1%} | {funded_sc['payout_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## Candidate Details",
            "",
        ]
    )
    for row in payload["results"]:
        holdout = row["holdout_metrics"]
        prop_sc = row["holdout_prop_scorecard"]
        funded_sc = row["holdout_funded_scorecard"]
        lines.extend(
            [
                f"### {row['label']}",
                "",
                f"- gate: `{row['gate_label']}`",
                f"- config: `{row['config_summary']}`",
                (
                    f"- holdout raw: trades `{holdout['total_trades']}`, PF `{holdout['profit_factor']}`, "
                    f"avg R `{holdout['avg_r']}`, total R `{holdout['total_r']}`, "
                    f"Calmar `{holdout['calmar_ratio']}`, DD `{holdout['max_drawdown_r']}`"
                ),
                (
                    f"- holdout prop scorecard: payout `{prop_sc['first_payout_rate']:.1%}`, "
                    f"breach `{prop_sc['breach_rate']:.1%}`, open `{prop_sc['open_rate']:.1%}`, "
                    f"EV/attempt `${prop_sc['ev_per_attempt']}`"
                ),
                (
                    f"- holdout funded scorecard: payout `{funded_sc['payout_rate']:.1%}`, "
                    f"breach `{funded_sc['breach_rate']:.1%}`, open `{funded_sc['open_rate']:.1%}`, "
                    f"EV/start `${funded_sc['ev_per_start_usd']}`"
                ),
                f"- `2025-04-01` to `2025-12-31`: `{row['holdout_2025_metrics']}`",
                f"- `2026-01-01` to `{payload['info']['holdout_end_inclusive']}`: `{row['holdout_2026_ytd_metrics']}`",
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    holdout_end_inclusive = pd.Timestamp(df_base.index.max()).normalize().strftime("%Y-%m-%d")
    holdout_end_exclusive = (
        pd.Timestamp(df_base.index.max()).normalize() + pd.Timedelta(days=1)
    ).strftime("%Y-%m-%d")
    holdout_dates = trading_dates_between(df_base, HOLDOUT_START, holdout_end_exclusive)

    candidates = build_candidates()
    configs = [row["config"] for row in candidates]
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, configs, signal_df_1m=signal_df_1m)
    regime_calendar = build_extended_regime_calendar(df_base)

    results = []
    for row in candidates:
        config = row["config"]
        trades_holdout = run_backtest(
            df_base,
            config,
            start_date=HOLDOUT_START,
            end_date=holdout_end_exclusive,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        if row["exclude_regimes"]:
            trades_holdout = filter_trades_by_combined_regime(
                trades_holdout,
                regime_calendar,
                exclude=row["exclude_regimes"],
            )

        holdout_metrics = compute_metrics(trades_holdout)
        holdout_prop_outcomes = simulate_account_attempts(
            specialist_name=f"{row['label']}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=PROP_PROFILE,
            risk_per_r_usd=config.risk_usd,
        )
        holdout_prop_scorecard = build_prop_scorecard(holdout_prop_outcomes, PROP_PROFILE)
        holdout_funded_outcomes = simulate_funded_first_payouts(
            specialist_name=f"{row['label']}_holdout",
            trades=trades_holdout,
            trading_dates=holdout_dates,
            profile=FUNDED_PROFILE,
        )
        holdout_funded_scorecard = build_funded_first_payout_scorecard(
            holdout_funded_outcomes,
            FUNDED_PROFILE,
        )
        holdout_funded_forecast = build_funded_first_payout_forecast(holdout_funded_outcomes)

        session = config.sessions[0]
        results.append(
            {
                "label": row["label"],
                "gate_label": row["gate_label"],
                "config_summary": (
                    f"{config.direction_filter} {config.lsi_entry_mode} "
                    f"{session.entry_start}-{session.entry_end} "
                    f"rr{config.rr} tp{config.tp1_ratio} "
                    f"gap{session.min_gap_atr_pct} "
                    f"htf{config.htf_level_tf_minutes} n{config.htf_n_left} "
                    f"cap{config.htf_trade_max_per_session} "
                    f"fvgL{config.lsi_fvg_window_left} fvgR{config.lsi_fvg_window_right} "
                    f"lag{config.max_fvg_to_inversion_bars}"
                ),
                "holdout_metrics": metrics_snapshot(holdout_metrics),
                "holdout_prop_scorecard": holdout_prop_scorecard,
                "holdout_funded_scorecard": holdout_funded_scorecard,
                "holdout_funded_forecast": holdout_funded_forecast,
                "holdout_2025_metrics": _year_metrics(trades_holdout, "2025-04-01", "2026-01-01"),
                "holdout_2026_ytd_metrics": _year_metrics(trades_holdout, "2026-01-01", holdout_end_exclusive),
            }
        )

    results.sort(key=_rank_key, reverse=True)
    payload = {
        "info": {
            "holdout_start": HOLDOUT_START,
            "holdout_end_inclusive": holdout_end_inclusive,
            "holdout_end_exclusive": holdout_end_exclusive,
        },
        "results": results,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(OUTPUT_DIR / "holdout_compare.json", payload)
    write_report(payload)
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
