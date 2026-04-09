#!/usr/bin/env python3
"""Attribution study for the frozen NQ NY reference_lsi winner."""

from __future__ import annotations

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest
from orb_backtest.results.metrics import compute_metrics


OUTPUT_DIR = ROOT / "data" / "results" / "nq_ny_reference_lsi_attribution"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_REFERENCE_LSI_ATTRIBUTION.md"

RESEARCH_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2024-12-31"
HOLDOUT_START = "2025-01-01"

CANDIDATE_LABEL = "NQ NY reference_lsi both 11:00 near gap6 inv15 rr3.0 tp0.8"

LEVEL_ORDER = [
    "previous_day_high",
    "previous_day_low",
    "asia_high",
    "asia_low",
    "london_high",
    "london_low",
]

HYPOTHESES = {
    "high_side_only": lambda t: t.reference_level_name.endswith("_high"),
    "exclude_london": lambda t: not t.reference_level_name.startswith("london_"),
    "high_side_exclude_london": (
        lambda t: t.reference_level_name.endswith("_high")
        and not t.reference_level_name.startswith("london_")
    ),
    "previous_day_only": lambda t: t.reference_level_name.startswith("previous_day"),
    "asia_only": lambda t: t.reference_level_name.startswith("asia_"),
    "previous_day_high_plus_asia_high": (
        lambda t: t.reference_level_name in ("previous_day_high", "asia_high")
    ),
}


def build_session() -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        entry_start="08:30",
        entry_end="11:00",
        flat_start="14:00",
        flat_end="14:05",
        min_gap_atr_pct=5.0,
    )


def build_config() -> StrategyConfig:
    return StrategyConfig(
        instrument=NQ,
        sessions=(build_session(),),
        strategy="reference_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter="both",
        rr=3.0,
        tp1_ratio=0.8,
        atr_length=10,
        ref_lsi_gap_lookback_bars=6,
        ref_lsi_inversion_max_bars=15,
        ref_lsi_gap_entry_edge="near",
        name=CANDIDATE_LABEL,
    )


def slice_trades(
    trades: list[TradeResult],
    start: str | None = None,
    end: str | None = None,
) -> list[TradeResult]:
    return [
        t for t in trades
        if (start is None or t.date >= start)
        and (end is None or t.date < end)
    ]


def metrics_row(trades: list[TradeResult]) -> dict:
    if not trades:
        return {
            "trades": 0,
            "avg_r": 0.0,
            "pf": 0.0,
            "total_r": 0.0,
            "win_rate": 0.0,
        }
    m = compute_metrics(trades)
    return {
        "trades": int(m["total_trades"]),
        "avg_r": round(float(m["avg_r"]), 4),
        "pf": round(float(m["profit_factor"]), 4),
        "total_r": round(float(m["total_r"]), 2),
        "win_rate": round(float(m["win_rate"]), 4),
    }


def prefixed_metrics(prefix: str, trades: list[TradeResult]) -> dict:
    return {f"{prefix}_{k}": v for k, v in metrics_row(trades).items()}


def split_metrics(trades: list[TradeResult]) -> dict:
    return {
        **prefixed_metrics("pre", trades),
        **prefixed_metrics("discovery", slice_trades(trades, RESEARCH_START, VALIDATION_START)),
        **prefixed_metrics("validation", slice_trades(trades, VALIDATION_START, HOLDOUT_START)),
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


def direction_label(t: TradeResult) -> str:
    return "long" if t.direction == 1 else "short"


def time_bucket(fill_time: str) -> str:
    hh, mm = map(int, fill_time[11:16].split(":"))
    start_min = hh * 60 + (0 if mm < 30 else 30)
    end_min = start_min + 30
    return f"{start_min//60:02d}:{start_min%60:02d}-{end_min//60:02d}:{end_min%60:02d}"


def grouped_rows(
    trades: list[TradeResult],
    group_fn,
    *,
    ordered_keys: list[str] | None = None,
) -> list[dict]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for trade in trades:
        groups[str(group_fn(trade))].append(trade)

    keys = ordered_keys if ordered_keys is not None else sorted(groups)
    rows: list[dict] = []
    total_trades = len(trades)
    total_r = sum(t.r_multiple for t in trades)
    for key in keys:
        subset = groups.get(key, [])
        row = {"group": key}
        row.update(split_metrics(subset))
        row["share_trades"] = round((len(subset) / total_trades) if total_trades else 0.0, 4)
        row["share_total_r"] = round((sum(t.r_multiple for t in subset) / total_r) if total_r else 0.0, 4)
        rows.append(row)
    return rows


def year_rows(trades: list[TradeResult]) -> list[dict]:
    groups: dict[str, list[TradeResult]] = defaultdict(list)
    for trade in trades:
        groups[trade.date[:4]].append(trade)
    rows = []
    for year in sorted(groups):
        row = {"year": year}
        row.update(metrics_row(groups[year]))
        rows.append(row)
    return rows


def hypothesis_rows(trades: list[TradeResult]) -> list[dict]:
    rows = []
    for name, predicate in HYPOTHESES.items():
        subset = [t for t in trades if predicate(t)]
        row = {"hypothesis": name}
        row.update(split_metrics(subset))
        rows.append(row)
    rows.sort(
        key=lambda row: (
            row["discovery_avg_r"],
            row["validation_avg_r"],
            row["pre_total_r"],
        ),
        reverse=True,
    )
    return rows


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False))


def format_summary_line(label: str, row: dict) -> str:
    return (
        f"- `{label}`: trades `{row['trades']}`, avgR `{row['avg_r']}`, "
        f"PF `{row['pf']}`, totalR `{row['total_r']}`, WR `{row['win_rate']}`"
    )


def write_report(payload: dict) -> None:
    overall = payload["overall"]
    lines = [
        "# NQ NY Reference LSI Attribution",
        "",
        f"- Candidate: `{CANDIDATE_LABEL}`",
        f"- Holdout frozen at `{HOLDOUT_START}` and not used.",
        f"- Discovery `{RESEARCH_START}` to `{DISCOVERY_END}`.",
        f"- Validation `{VALIDATION_START}` to `{VALIDATION_END}`.",
        "",
        "## Overall",
        "",
        format_summary_line("pre-holdout", overall["pre"]),
        format_summary_line("discovery", overall["discovery"]),
        format_summary_line("validation", overall["validation"]),
        "",
        "## Exact Levels",
        "",
    ]
    for row in payload["by_level"]:
        lines.append(
            f"- `{row['group']}`: pre `{row['pre_trades']}` / avgR `{row['pre_avg_r']}` / PF `{row['pre_pf']}` / totalR `{row['pre_total_r']}`; "
            f"validation `{row['validation_trades']}` / avgR `{row['validation_avg_r']}` / PF `{row['validation_pf']}` / totalR `{row['validation_total_r']}`"
        )
    lines.extend(["", "## Families And Sides", ""])
    for section_name, rows in [
        ("level_family", payload["by_family"]),
        ("level_side", payload["by_side"]),
        ("direction", payload["by_direction"]),
        ("time_bucket", payload["by_time_bucket"]),
    ]:
        lines.append(f"### {section_name}")
        lines.append("")
        for row in rows:
            lines.append(
                f"- `{row['group']}`: pre `{row['pre_trades']}` / avgR `{row['pre_avg_r']}` / PF `{row['pre_pf']}` / totalR `{row['pre_total_r']}`; "
                f"validation `{row['validation_trades']}` / avgR `{row['validation_avg_r']}` / PF `{row['validation_pf']}` / totalR `{row['validation_total_r']}`"
            )
        lines.append("")

    lines.extend(["## By Year", ""])
    for row in payload["by_year"]:
        lines.append(
            f"- `{row['year']}`: trades `{row['trades']}`, avgR `{row['avg_r']}`, PF `{row['pf']}`, totalR `{row['total_r']}`"
        )

    lines.extend(["", "## Simplification Hypotheses", ""])
    for row in payload["hypotheses"]:
        lines.append(
            f"- `{row['hypothesis']}`: pre `{row['pre_trades']}` / avgR `{row['pre_avg_r']}` / PF `{row['pre_pf']}` / totalR `{row['pre_total_r']}`; "
            f"discovery `{row['discovery_trades']}` / avgR `{row['discovery_avg_r']}` / PF `{row['discovery_pf']}` / totalR `{row['discovery_total_r']}`; "
            f"validation `{row['validation_trades']}` / avgR `{row['validation_avg_r']}` / PF `{row['validation_pf']}` / totalR `{row['validation_total_r']}`"
        )

    lines.extend(
        [
            "",
            "## Readout",
            "",
            "- `London` is the clear drag. It is negative across the full pre-holdout sample and negative in discovery, even though the validation slice is modestly positive.",
            "- `high-side / short` sweeps carry most of the edge. They are positive in both discovery and validation, while `low-side / long` is nearly flat across the full pre-holdout sample and negative in discovery.",
            "- `previous_day` and `asia` are the useful level families. Both are positive in discovery and validation. `previous_day_high` is exceptionally strong in validation, but too thin to elevate on its own.",
            "- The strongest balanced simplification hypothesis is `exclude_london`. It keeps both directions from `previous_day` and `asia`, stays positive in discovery and validation, and materially improves the pre-holdout profile versus the all-level candidate.",
            "- `high_side_exclude_london` is even stronger, but the validation sample is only 5 trades. Treat it as a challenger thesis, not the primary restart.",
            "",
            "## Recommendation",
            "",
            "- Next fresh thesis: restart discovery with `reference_lsi` restricted to `previous_day_*` and `asia_*` only, keeping the current candidate otherwise frozen as the baseline anchor.",
            "- Secondary challenger thesis: restrict to `previous_day_high` plus `asia_high` only.",
            "- Do not open the `2025-01-01+` holdout for the current all-level candidate.",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines))


def main() -> None:
    t0 = time.time()
    config = build_config()

    print("Loading NQ data (5m + 1m + 1s)...", flush=True)
    df_5m = load_5m_data("NQ_5m.parquet")
    df_1m = load_1m_for_5m("NQ_5m.parquet")
    df_1s = load_1s_for_5m("NQ_5m.parquet")

    print(f"Running attribution backtest for {CANDIDATE_LABEL}...", flush=True)
    trades = run_backtest(
        df_5m,
        config,
        start_date=RESEARCH_START,
        end_date=HOLDOUT_START,
        df_1m=df_1m,
        df_1s=df_1s,
    )
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]

    payload = {
        "candidate": CANDIDATE_LABEL,
        "overall": {
            "pre": metrics_row(filled),
            "discovery": metrics_row(slice_trades(filled, RESEARCH_START, VALIDATION_START)),
            "validation": metrics_row(slice_trades(filled, VALIDATION_START, HOLDOUT_START)),
        },
        "by_level": grouped_rows(filled, lambda t: t.reference_level_name, ordered_keys=LEVEL_ORDER),
        "by_family": grouped_rows(filled, lambda t: level_family(t.reference_level_name), ordered_keys=["previous_day", "asia", "london"]),
        "by_side": grouped_rows(filled, lambda t: level_side(t.reference_level_name), ordered_keys=["high_side", "low_side"]),
        "by_direction": grouped_rows(filled, direction_label, ordered_keys=["short", "long"]),
        "by_time_bucket": grouped_rows(filled, lambda t: time_bucket(t.fill_time)),
        "by_year": year_rows(filled),
        "hypotheses": hypothesis_rows(filled),
    }

    write_json(OUTPUT_DIR / "attribution_results.json", payload)
    write_report(payload)
    print(f"Attribution complete in {time.time() - t0:.1f}s", flush=True)


if __name__ == "__main__":
    main()
