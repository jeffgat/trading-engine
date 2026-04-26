"""Run the engine-backed ALPHA_V1 ORB cap=2 conditioned re-entry study.

This is the follow-through to the cap=2 frontier packet:
- add the re-entry policy directly to the ORB engine
- rerun the same 2-year ALPHA_V1 ORB sleeve
- recheck regime correlation on the actual conditioned re-entry stream
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from orb_backtest.analysis.alpha_v1_downside import (
    DataCache,
    build_alpha_v1_legs,
    filled_trades,
    filter_trades_by_combined_regime,
    portfolio_daily_frame,
    summarize_daily_returns,
)
from orb_backtest.analysis.gates import apply_dow_filter
from orb_backtest.analysis.regime_research import attribute_strategy_by_regime, compute_bucket_metrics
from orb_backtest.config import StrategyConfig, with_overrides
from orb_backtest.engine.simulator import TradeResult
from orb_backtest.optimize.parallel import run_sweep
from orb_backtest.results.metrics import compute_metrics


ROOT = Path(__file__).resolve().parent.parent
RESULT_DIR = ROOT / "data" / "results" / "alpha_v1_orb_cap2_conditioned_2y"
REPORT_PATH = ROOT / "learnings" / "reports" / "ALPHA_V1_ORB_CAP2_CONDITIONED_2Y.md"

START_DATE = "2024-04-17"
END_DATE = "2026-04-17"
HOLDOUT_START = "2025-01-01"

ORB_LEG_KEYS = (
    "nq_asia_orb_long",
    "es_asia_orb_long",
    "es_ny_orb_long",
)
VARIANTS = {
    "cap1_baseline": {
        "trade_cap": 1,
        "reentry_policy": "any_reentry",
        "label": "cap=1 baseline",
    },
    "cap2_any_reentry": {
        "trade_cap": 2,
        "reentry_policy": "any_reentry",
        "label": "cap=2 any re-entry",
    },
    "cap2_after_nonpositive_first": {
        "trade_cap": 2,
        "reentry_policy": "after_nonpositive_first",
        "label": "cap=2 after nonpositive first trade",
    },
}
REENTRY_GATE_SETS = {
    "bull_high_vol": ("bull_high_vol",),
    "bull_medium_or_high_vol": ("bull_medium_vol", "bull_high_vol"),
    "bull_expansion_plus_sideways_high_vol": (
        "bull_medium_vol",
        "bull_high_vol",
        "sideways_high_vol",
    ),
    "all_high_vol": ("bear_high_vol", "bull_high_vol", "sideways_high_vol"),
}


def _round(value: float | int | None, digits: int = 2) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    if not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _pct(value: float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) * 100.0, 2)


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "-"
        if abs(value) >= 100 or value == int(value):
            return f"{value:.0f}"
        return f"{value:.2f}"
    return str(value)


def _markdown_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |")
    return "\n".join([header, sep, *body]) if body else "\n".join([header, sep])


def _daily_sleeve_summary(named_streams: dict[str, list[TradeResult]]) -> dict[str, Any]:
    filled_streams = {name: filled_trades(trades) for name, trades in named_streams.items()}
    daily = portfolio_daily_frame(filled_streams)
    total_series = daily.sum(axis=1) if not daily.empty else pd.Series(dtype=float)
    summary = summarize_daily_returns(total_series)
    fill_count = sum(len(stream) for stream in filled_streams.values())
    return {
        "fills": fill_count,
        "total_r": _round(summary["total_r"], 2),
        "max_drawdown_r": _round(summary["max_drawdown_r"], 2),
        "sharpe_ratio": _round(summary["sharpe_ratio"], 2),
        "calmar_ratio": _round(summary["calmar_ratio"], 2),
        "negative_days": int(summary["negative_days"]),
    }


def _run_configs(cache: DataCache, configs: list[StrategyConfig]) -> dict[str, list[TradeResult]]:
    instrument = configs[0].instrument
    market = cache.get(instrument)
    results = run_sweep(
        market.df_5m,
        configs,
        n_workers=min(3, len(configs)),
        start_date=START_DATE,
        end_date=END_DATE,
        df_1m=market.df_1m,
        df_1s=market.df_1s,
    )
    by_name: dict[str, list[TradeResult]] = {}
    for config, trades in results:
        if config.excluded_days:
            trades = apply_dow_filter(trades, set(config.excluded_days))
        by_name[config.name] = trades
    return by_name


def _session_anchor_time(config: StrategyConfig) -> str:
    session = config.sessions[0]
    return session.orb_start or session.rth_start or session.entry_start


def _session_crosses_midnight(config: StrategyConfig) -> bool:
    session = config.sessions[0]
    start_time = _session_anchor_time(config)
    end_time = session.flat_end or session.entry_end
    return bool(start_time and end_time and end_time < start_time)


def _session_day_key(trade: TradeResult, config: StrategyConfig) -> tuple[str, str]:
    session_name = config.sessions[0].name
    ts_str = trade.fill_time or trade.exit_time
    if not ts_str:
        return session_name, trade.date

    ts = pd.Timestamp(ts_str)
    session_date = ts.date()
    if _session_crosses_midnight(config):
        anchor_time = _session_anchor_time(config)
        if ts.strftime("%H:%M") < anchor_time:
            session_date = (ts - pd.Timedelta(days=1)).date()
    return session_name, session_date.isoformat()


def _trade_ordinals(trades: list[TradeResult], config: StrategyConfig) -> list[dict[str, Any]]:
    rows = []
    ordinal_by_day: dict[tuple[str, str], int] = defaultdict(int)
    for trade in sorted(
        filled_trades(trades),
        key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar),
    ):
        key = _session_day_key(trade, config)
        ordinal_by_day[key] += 1
        rows.append(
            {
                "trade": trade,
                "date": key[1],
                "session": key[0],
                "ordinal": ordinal_by_day[key],
            }
        )
    return rows


def _trade_count_distribution(ordinal_rows: list[dict[str, Any]]) -> dict[str, int]:
    per_day = Counter((row["date"], row["session"]) for row in ordinal_rows)
    return {str(k): int(v) for k, v in sorted(Counter(per_day.values()).items())}


def _reentry_split(trades: list[TradeResult], config: StrategyConfig) -> dict[str, Any]:
    rows = _trade_ordinals(trades, config)
    first_trades = [row["trade"] for row in rows if row["ordinal"] == 1]
    reentry_trades = [row["trade"] for row in rows if row["ordinal"] >= 2]
    reentry_days = len({(row["date"], row["session"]) for row in rows if row["ordinal"] >= 2})
    max_trades_per_day = max((row["ordinal"] for row in rows), default=0)
    return {
        "rows": rows,
        "first_trades": first_trades,
        "reentry_trades": reentry_trades,
        "reentry_days": reentry_days,
        "max_trades_per_day": max_trades_per_day,
        "trade_count_distribution": _trade_count_distribution(rows),
    }


def _metrics_snapshot(metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "signals": int(metrics.get("total_signals", 0)),
        "fills": int(metrics.get("total_trades", 0)),
        "no_fills": int(metrics.get("no_fills", 0)),
        "win_rate_pct": _pct(metrics.get("win_rate")),
        "avg_r": _round(metrics.get("avg_r"), 2),
        "total_r": _round(metrics.get("total_r"), 2),
        "profit_factor": _round(metrics.get("profit_factor"), 2),
        "sharpe_ratio": _round(metrics.get("sharpe_ratio"), 2),
        "calmar_ratio": _round(metrics.get("calmar_ratio"), 2),
        "max_drawdown_r": _round(metrics.get("max_drawdown_r"), 2),
    }


def _top_regime_rows(attr: pd.DataFrame, min_trades: int = 3, limit: int = 5) -> list[dict[str, Any]]:
    if attr.empty:
        return []
    table = compute_bucket_metrics(attr, "combined_regime")
    table = table[table["trade_count"] >= min_trades]
    if table.empty:
        return []
    rows: list[dict[str, Any]] = []
    for _, row in table.head(limit).iterrows():
        rows.append(
            {
                "bucket": str(row["bucket"]),
                "trades": int(row["trade_count"]),
                "avg_r": _round(row["avg_r"], 2),
                "total_r": _round(row["total_r"], 2),
                "win_rate_pct": _pct(row["win_rate"]),
                "profit_factor": _round(row["profit_factor"], 2),
                "max_drawdown_r": _round(row["max_drawdown_r"], 2),
            }
        )
    return rows


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    cache = DataCache(start_date=START_DATE, end_date=END_DATE)
    legs = build_alpha_v1_legs()
    orb_legs = {key: legs[key] for key in ORB_LEG_KEYS}

    variant_streams: dict[str, dict[str, list[TradeResult]]] = {variant: {} for variant in VARIANTS}
    leg_variant_tables: dict[str, list[dict[str, Any]]] = {}
    conditioned_reentry_summaries: dict[str, dict[str, Any]] = {}
    combined_conditioned_attr_frames: list[pd.DataFrame] = []

    for leg_key, leg in orb_legs.items():
        configs = []
        config_names: dict[str, str] = {}
        for variant, spec in VARIANTS.items():
            name = (
                f"{leg.config.instrument.symbol} {leg.session} 2024-04-17 to 2026-04-17 "
                f"ALPHA_V1 ORB {variant}"
            )
            config_names[variant] = name
            configs.append(
                with_overrides(
                    leg.config,
                    name=name,
                    notes=(
                        "ALPHA_V1 ORB engine-backed cap=2 conditioned re-entry study over the last two years; "
                        f"orb_trade_max_per_session={spec['trade_cap']}, "
                        f"orb_reentry_policy={spec['reentry_policy']}."
                    ),
                    orb_trade_max_per_session=spec["trade_cap"],
                    orb_reentry_policy=spec["reentry_policy"],
                )
            )

        results = _run_configs(cache, configs)
        market = cache.get(leg.config.instrument)

        variant_rows: list[dict[str, Any]] = []
        for variant, spec in VARIANTS.items():
            trades = results[config_names[variant]]
            variant_streams[variant][leg_key] = trades
            metrics = compute_metrics(trades)
            split = _reentry_split(trades, leg.config)
            variant_rows.append(
                {
                    "variant": variant,
                    "cap": spec["trade_cap"],
                    "reentry_policy": spec["reentry_policy"],
                    "signals": metrics["total_signals"],
                    "fills": metrics["total_trades"],
                    "reentry_fills": len(split["reentry_trades"]),
                    "reentry_days": split["reentry_days"],
                    "max_trades_day": split["max_trades_per_day"],
                    "win_rate_pct": _pct(metrics["win_rate"]),
                    "avg_r": _round(metrics["avg_r"], 2),
                    "total_r": _round(metrics["total_r"], 2),
                    "sharpe_ratio": _round(metrics["sharpe_ratio"], 2),
                    "max_drawdown_r": _round(metrics["max_drawdown_r"], 2),
                }
            )

            if variant == "cap2_after_nonpositive_first":
                first_metrics = _metrics_snapshot(compute_metrics(split["first_trades"]))
                reentry_metrics = _metrics_snapshot(compute_metrics(split["reentry_trades"]))
                reentry_attr = attribute_strategy_by_regime(
                    split["reentry_trades"],
                    market.regime_calendar,
                    holdout_start=HOLDOUT_START,
                )
                if not reentry_attr.empty:
                    reentry_attr = reentry_attr.copy()
                    reentry_attr["leg"] = leg_key
                    combined_conditioned_attr_frames.append(reentry_attr)
                conditioned_reentry_summaries[leg_key] = {
                    "first_metrics": first_metrics,
                    "reentry_metrics": reentry_metrics,
                    "reentry_days": split["reentry_days"],
                    "max_trades_per_day": split["max_trades_per_day"],
                    "trade_count_distribution": split["trade_count_distribution"],
                    "top_reentry_regimes": _top_regime_rows(reentry_attr, min_trades=2, limit=5),
                    "first_trades": split["first_trades"],
                    "reentry_trades": split["reentry_trades"],
                    "regime_calendar": market.regime_calendar,
                }

        leg_variant_tables[leg_key] = variant_rows

    sleeve_rows: list[dict[str, Any]] = []
    baseline_total_r = None
    cap2_any_total_r = None
    for variant in VARIANTS:
        sleeve = _daily_sleeve_summary(variant_streams[variant])
        if variant == "cap1_baseline":
            baseline_total_r = sleeve["total_r"]
        if variant == "cap2_any_reentry":
            cap2_any_total_r = sleeve["total_r"]
        sleeve_rows.append(
            {
                "variant": variant,
                "cap": VARIANTS[variant]["trade_cap"],
                "reentry_policy": VARIANTS[variant]["reentry_policy"],
                **sleeve,
                "delta_vs_cap1_r": _round(sleeve["total_r"] - baseline_total_r, 2) if baseline_total_r is not None else 0.0,
                "delta_vs_cap2_any_r": _round(sleeve["total_r"] - cap2_any_total_r, 2) if cap2_any_total_r is not None else None,
            }
        )

    gate_rows: list[dict[str, Any]] = []
    gated_payload: dict[str, Any] = {}
    conditioned_total_r = next(
        (row["total_r"] for row in sleeve_rows if row["variant"] == "cap2_after_nonpositive_first"),
        None,
    )
    for gate_name, regimes in REENTRY_GATE_SETS.items():
        gated_streams: dict[str, list[TradeResult]] = {}
        for leg_key in ORB_LEG_KEYS:
            leg_summary = conditioned_reentry_summaries[leg_key]
            gated_reentries = filter_trades_by_combined_regime(
                leg_summary["reentry_trades"],
                leg_summary["regime_calendar"],
                include=set(regimes),
            )
            gated_streams[leg_key] = sorted(
                [*leg_summary["first_trades"], *gated_reentries],
                key=lambda t: (t.date, t.session, t.fill_bar, t.signal_bar, t.exit_bar),
            )
        sleeve = _daily_sleeve_summary(gated_streams)
        delta_vs_cap1 = None if baseline_total_r is None else sleeve["total_r"] - baseline_total_r
        delta_vs_conditioned = None if conditioned_total_r is None else sleeve["total_r"] - conditioned_total_r
        gate_rows.append(
            {
                "gate": gate_name,
                "regimes": ", ".join(regimes),
                "fills": sleeve["fills"],
                "total_r": sleeve["total_r"],
                "delta_vs_cap1_r": _round(delta_vs_cap1, 2) if delta_vs_cap1 is not None else None,
                "delta_vs_conditioned_r": _round(delta_vs_conditioned, 2) if delta_vs_conditioned is not None else None,
                "sharpe_ratio": sleeve["sharpe_ratio"],
                "max_drawdown_r": sleeve["max_drawdown_r"],
                "negative_days": sleeve["negative_days"],
            }
        )
        gated_payload[gate_name] = {
            "regimes": list(regimes),
            "sleeve": sleeve,
            "delta_vs_cap1_r": _round(delta_vs_cap1, 2) if delta_vs_cap1 is not None else None,
            "delta_vs_conditioned_r": _round(delta_vs_conditioned, 2) if delta_vs_conditioned is not None else None,
        }

    combined_conditioned_table = _top_regime_rows(
        pd.concat(combined_conditioned_attr_frames, ignore_index=True)
        if combined_conditioned_attr_frames
        else pd.DataFrame(),
        min_trades=3,
        limit=8,
    )

    report_lines = [
        "# ALPHA_V1 ORB Cap=2 Conditioned Re-Entry",
        "",
        f"- Window: `{START_DATE}` to `{END_DATE}`",
        "- Scope: the three ORB legs in `ALPHA_V1` only (`NQ Asia`, `ES Asia`, `ES NY`)",
        "- Engine rule under test: `orb_trade_max_per_session=2` plus `orb_reentry_policy=after_nonpositive_first`",
        "- Comparison set: `cap=1` baseline, `cap=2` any re-entry, and the conditioned `cap=2` engine variant",
        "- Regime lens: causal combined trend x vol buckets, then conditioned-re-entry-only gates",
        "",
        "## Combined ORB Sleeve",
        "",
        _markdown_table(
            sleeve_rows,
            [
                "variant",
                "cap",
                "reentry_policy",
                "fills",
                "total_r",
                "delta_vs_cap1_r",
                "delta_vs_cap2_any_r",
                "sharpe_ratio",
                "max_drawdown_r",
                "calmar_ratio",
                "negative_days",
            ],
        ),
        "",
    ]

    for leg_key in ORB_LEG_KEYS:
        report_lines.extend(
            [
                f"## {leg_key}",
                "",
                _markdown_table(
                    leg_variant_tables[leg_key],
                    [
                        "variant",
                        "cap",
                        "reentry_policy",
                        "signals",
                        "fills",
                        "reentry_fills",
                        "reentry_days",
                        "max_trades_day",
                        "win_rate_pct",
                        "avg_r",
                        "total_r",
                        "sharpe_ratio",
                        "max_drawdown_r",
                    ],
                ),
                "",
                "### Conditioned First Trade vs Re-Entries",
                "",
                _markdown_table(
                    [
                        {
                            "bucket": "first_trades",
                            **conditioned_reentry_summaries[leg_key]["first_metrics"],
                        },
                        {
                            "bucket": "reentries_only",
                            **conditioned_reentry_summaries[leg_key]["reentry_metrics"],
                        },
                    ],
                    [
                        "bucket",
                        "fills",
                        "win_rate_pct",
                        "avg_r",
                        "total_r",
                        "profit_factor",
                        "sharpe_ratio",
                        "max_drawdown_r",
                    ],
                ),
                "",
                f"- Re-entry days: `{conditioned_reentry_summaries[leg_key]['reentry_days']}`",
                f"- Max trades in one session-day: `{conditioned_reentry_summaries[leg_key]['max_trades_per_day']}`",
                f"- Trades-per-day distribution: `{conditioned_reentry_summaries[leg_key]['trade_count_distribution']}`",
                "",
                "### Top Conditioned Re-Entry Regimes",
                "",
                _markdown_table(
                    conditioned_reentry_summaries[leg_key]["top_reentry_regimes"],
                    [
                        "bucket",
                        "trades",
                        "avg_r",
                        "total_r",
                        "win_rate_pct",
                        "profit_factor",
                        "max_drawdown_r",
                    ],
                ),
                "",
            ]
        )

    report_lines.extend(
        [
            "## Conditioned Re-Entry Regime Correlation",
            "",
            _markdown_table(
                combined_conditioned_table,
                [
                    "bucket",
                    "trades",
                    "avg_r",
                    "total_r",
                    "win_rate_pct",
                    "profit_factor",
                    "max_drawdown_r",
                ],
            ),
            "",
            "## Conditioned Re-Entry-Only Gate Tests",
            "",
            _markdown_table(
                gate_rows,
                [
                    "gate",
                    "regimes",
                    "fills",
                    "total_r",
                    "delta_vs_cap1_r",
                    "delta_vs_conditioned_r",
                    "sharpe_ratio",
                    "max_drawdown_r",
                    "negative_days",
                ],
            ),
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    payload = {
        "window": {"start": START_DATE, "end": END_DATE, "holdout_start": HOLDOUT_START},
        "combined_sleeve": sleeve_rows,
        "per_leg": leg_variant_tables,
        "conditioned_reentry": {
            leg_key: {
                "first_metrics": conditioned_reentry_summaries[leg_key]["first_metrics"],
                "reentry_metrics": conditioned_reentry_summaries[leg_key]["reentry_metrics"],
                "reentry_days": conditioned_reentry_summaries[leg_key]["reentry_days"],
                "max_trades_per_day": conditioned_reentry_summaries[leg_key]["max_trades_per_day"],
                "trade_count_distribution": conditioned_reentry_summaries[leg_key]["trade_count_distribution"],
                "top_reentry_regimes": conditioned_reentry_summaries[leg_key]["top_reentry_regimes"],
            }
            for leg_key in ORB_LEG_KEYS
        },
        "combined_conditioned_regimes": combined_conditioned_table,
        "gate_tests": gate_rows,
        "gate_payload": gated_payload,
        "report_path": str(REPORT_PATH),
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("ALPHA_V1 ORB CAP=2 CONDITIONED RE-ENTRY")
    print(f"Window: {START_DATE} to {END_DATE}")
    print("")
    print(_markdown_table(
        sleeve_rows,
        [
            "variant",
            "fills",
            "total_r",
            "delta_vs_cap1_r",
            "delta_vs_cap2_any_r",
            "sharpe_ratio",
            "max_drawdown_r",
            "negative_days",
        ],
    ))
    print("")
    print(f"Report written to: {REPORT_PATH}")
    print(f"Summary JSON written to: {RESULT_DIR / 'summary.json'}")


if __name__ == "__main__":
    main()
