#!/usr/bin/env python3
"""Portfolio-layer proxy test for the additive EQHL NQ leg inside ALPHA_V1.

Important posture:
- Other legs (`NQ_Asia`, `ES_Asia`, `ES_NY`) are exact execution replays.
- The control NQ leg (`HTF_LSI_5M_LAG24`) is also exact execution replay.
- The additive EQHL NQ leg is run through the research backtester because the
  live execution engine does not yet support EQHL additive fields.

So this is a mixed exact/proxy portfolio test, not a pure exact replay.
It is still useful as a portfolio-layer decision aid because only the swapped
NQ leg is approximated while the other three legs stay exact and fixed.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKTEST_ROOT = ROOT / "backtesting"
EXEC_SRC = ROOT / "execution" / "src"
BACKTEST_SRC = BACKTEST_ROOT / "src"
BACKTEST_SCRIPTS = BACKTEST_ROOT / "scripts"
NUMBA_CACHE_DIR = BACKTEST_ROOT / ".numba_cache" / "alpha_v1_eqhl_additive_portfolio_proxy"
NUMBA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("NUMBA_CACHE_DIR", str(NUMBA_CACHE_DIR))
for path in (EXEC_SRC, BACKTEST_SRC, BACKTEST_SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from orb_backtest.engine.simulator import EXIT_NO_FILL, build_maps, build_signal_cache, run_backtest  # noqa: E402
from run_alpha_v1_htf_stagger_policy_frontier import (  # noqa: E402
    ACCOUNT_R_USD,
    BREACH_USD,
    PAYOUT_USD,
    POLICIES,
    START,
    END,
    backtest_to_daily_usd,
    build_single_leg_profile,
    evaluate_policy,
    run_exact_profile,
)
from htf_lsi_common import build_current_nq_ny_htf_lsi_lag24_config, load_timeframe_data  # noqa: E402


OUTPUT_DIR = BACKTEST_ROOT / "data" / "results" / "alpha_v1_eqhl_additive_portfolio_proxy"
REPORT_PATH = BACKTEST_ROOT / "learnings" / "reports" / "ALPHA_V1_EQHL_ADDITIVE_PORTFOLIO_PROXY.md"

FIXED_OTHER_LEGS = {
    "NQ_Asia": 250,
    "ES_Asia": 250,
    "ES_NY": 400,
}
NQ_RISKS = (250, 300, 350, 400, 450)


def merge_daily_streams(streams: list[list[tuple[str, float]]]) -> list[tuple[str, float]]:
    daily: dict[str, float] = defaultdict(float)
    for stream in streams:
        for date_str, pnl in stream:
            daily[date_str] += float(pnl)
    return sorted(daily.items())


def research_backtest_to_daily_usd(trades) -> list[tuple[str, float]]:
    daily: dict[str, float] = defaultdict(float)
    for trade in trades:
        if getattr(trade, "exit_type", EXIT_NO_FILL) == EXIT_NO_FILL:
            continue
        daily[str(trade.date)] += float(getattr(trade, "pnl_usd", 0.0))
    return sorted(daily.items())


def build_additive_config(risk_usd: int):
    return replace(
        build_current_nq_ny_htf_lsi_lag24_config(
            name=f"NQ NY HTF_LSI 5m lag24 + EQHL15m tol1 risk{risk_usd}",
        ),
        htf_lsi_include_eqhl_levels=True,
        eqhl_level_tf_minutes=15,
        eqhl_n_left=2,
        eqhl_tolerance_ticks=1,
        eqhl_min_touches=2,
        eqhl_lookback_bars=48,
        risk_usd=float(risk_usd),
    )


def build_control_config(risk_usd: int):
    return replace(
        build_current_nq_ny_htf_lsi_lag24_config(
            name=f"NQ NY HTF_LSI 5m lag24 control risk{risk_usd}",
        ),
        risk_usd=float(risk_usd),
    )


def run_research_nq_streams() -> dict[str, dict[int, list[tuple[str, float]]]]:
    df_base, df_1m, df_1s, signal_df_1m = load_timeframe_data("5m")
    additive_configs = [build_additive_config(risk) for risk in NQ_RISKS]
    control_configs = [build_control_config(risk) for risk in NQ_RISKS]
    all_configs = additive_configs + control_configs
    maps = build_maps(df_base, df_1m=df_1m, df_1s=df_1s)
    signal_cache = build_signal_cache(df_base, all_configs, signal_df_1m=signal_df_1m)

    out: dict[str, dict[int, list[tuple[str, float]]]] = {
        "additive_proxy": {},
        "control_research": {},
    }
    for risk, config in zip(NQ_RISKS, additive_configs):
        print(f"Research NQ additive risk={risk}...", flush=True)
        trades = run_backtest(
            df_base,
            config,
            start_date=START,
            end_date=END,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        out["additive_proxy"][risk] = research_backtest_to_daily_usd(trades)

    for risk, config in zip(NQ_RISKS, control_configs):
        print(f"Research NQ control risk={risk}...", flush=True)
        trades = run_backtest(
            df_base,
            config,
            start_date=START,
            end_date=END,
            df_1m=df_1m,
            signal_df_1m=signal_df_1m,
            df_1s=df_1s,
            _maps=maps,
            _signal_cache=signal_cache,
        )
        out["control_research"][risk] = research_backtest_to_daily_usd(trades)
    return out


def run_exact_fixed_leg_streams() -> dict[str, list[tuple[str, float]]]:
    streams: dict[str, list[tuple[str, float]]] = {}
    for leg_key, risk in FIXED_OTHER_LEGS.items():
        backtest = run_exact_profile(
            build_single_leg_profile(leg_key, risk),
            profile_name="TEMP",
            label=f"{leg_key} fixed risk {risk}",
        )
        streams[leg_key] = backtest_to_daily_usd(backtest)
        print(f"Exact fixed leg {leg_key} risk={risk} trades={len(backtest['trades'])}", flush=True)
    return streams


def run_exact_control_nq_streams() -> dict[int, list[tuple[str, float]]]:
    streams: dict[int, list[tuple[str, float]]] = {}
    for risk in NQ_RISKS:
        backtest = run_exact_profile(
            build_single_leg_profile("HTF_LSI", risk),
            profile_name="TEMP",
            label=f"HTF_LSI control risk {risk}",
        )
        streams[risk] = backtest_to_daily_usd(backtest)
        print(f"Exact NQ control risk={risk} trades={len(backtest['trades'])}", flush=True)
    return streams


def evaluate_variant_rows(
    *,
    variant_name: str,
    nq_streams: dict[int, list[tuple[str, float]]],
    fixed_streams: dict[str, list[tuple[str, float]]],
) -> list[dict]:
    rows: list[dict] = []
    for risk, nq_stream in nq_streams.items():
        combined = merge_daily_streams([nq_stream, *fixed_streams.values()])
        for policy in POLICIES:
            stats = evaluate_policy(combined, policy)
            stats["variant"] = variant_name
            stats["nq_risk"] = int(risk)
            stats["nq_leg_type"] = variant_name
            stats["fixed_other_legs"] = dict(FIXED_OTHER_LEGS)
            rows.append(stats)
    return rows


def candidate_sort_key(row: dict) -> tuple[float, float, float]:
    avg_days = row["avg_payout_days"] if row["avg_payout_days"] is not None else 10**9
    return (avg_days, -row["payout_rate"], row["breach_rate"])


def best_rows(rows: list[dict], *, threshold: float = 80.0) -> dict[str, dict | None]:
    eligible = [row for row in rows if row["payout_rate"] >= threshold]
    return {
        "best_ge_threshold": min(eligible, key=candidate_sort_key) if eligible else None,
        "absolute_fastest": min(rows, key=candidate_sort_key) if rows else None,
    }


def write_report(payload: dict) -> None:
    lines = [
        "# ALPHA_V1 EQHL Additive Portfolio Proxy",
        "",
        "- Objective: test the frozen `5m lag24 + 15m EQHL tol1` NQ leg inside the practical ALPHA_V1-style portfolio layer.",
        "- Other legs stay fixed and exact: `NQ_Asia=250`, `ES_Asia=250`, `ES_NY=400`.",
        "- NQ leg risk sweep: `250,300,350,400,450`.",
        "- Stagger policies: same calendar and R-trigger menu used in the prior HTF replacement work.",
        "- Important caveat: the NQ additive EQHL leg is a research-side replay proxy because the live execution engine does not yet support EQHL additive fields. The control HTF leg and the other three legs are exact execution replays.",
        "",
        "## Best Rows",
        "",
    ]
    for variant in ("control_exact", "additive_proxy"):
        winner = payload["winners"][variant]["best_ge_threshold"]
        fastest = payload["winners"][variant]["absolute_fastest"]
        lines.append(f"### {variant}")
        if winner:
            lines.append(
                f"- Best `>=80%` payout row: risk `{winner['nq_risk']}`, policy `{winner['policy']}`, "
                f"payout `{winner['payout_rate']:.1f}%`, breach `{winner['breach_rate']:.1f}%`, "
                f"avg payout `{winner['avg_payout_days']:.1f}d`."
            )
        if fastest:
            lines.append(
                f"- Absolute fastest row: risk `{fastest['nq_risk']}`, policy `{fastest['policy']}`, "
                f"payout `{fastest['payout_rate']:.1f}%`, breach `{fastest['breach_rate']:.1f}%`, "
                f"avg payout `{fastest['avg_payout_days']:.1f}d`."
            )
        lines.append("")

    lines.extend(
        [
            "## Full Frontier",
            "",
            "| Variant | Risk | Policy | Payout % | Breach % | Avg Payout Days | Fastest | Slowest | Starts |",
            "| --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in payload["rows"]:
        lines.append(
            f"| {row['variant']} | {row['nq_risk']} | {row['policy']} | "
            f"{row['payout_rate']:.1f} | {row['breach_rate']:.1f} | "
            f"{(row['avg_payout_days'] if row['avg_payout_days'] is not None else float('nan')):.1f} | "
            f"{row['fastest_payout_days'] if row['fastest_payout_days'] is not None else ''} | "
            f"{row['slowest_payout_days'] if row['slowest_payout_days'] is not None else ''} | "
            f"{row['starts']} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    fixed_streams = run_exact_fixed_leg_streams()
    control_exact_streams = run_exact_control_nq_streams()
    research_streams = run_research_nq_streams()

    rows = []
    rows.extend(
        evaluate_variant_rows(
            variant_name="control_exact",
            nq_streams=control_exact_streams,
            fixed_streams=fixed_streams,
        )
    )
    rows.extend(
        evaluate_variant_rows(
            variant_name="additive_proxy",
            nq_streams=research_streams["additive_proxy"],
            fixed_streams=fixed_streams,
        )
    )
    rows = sorted(rows, key=lambda row: (row["variant"], row["nq_risk"], row["policy"]))

    winners = {
        "control_exact": best_rows([row for row in rows if row["variant"] == "control_exact"]),
        "additive_proxy": best_rows([row for row in rows if row["variant"] == "additive_proxy"]),
    }
    payload = {
        "start": START,
        "end": END,
        "payout_usd": PAYOUT_USD,
        "breach_usd": BREACH_USD,
        "account_r_usd_for_r_trigger": ACCOUNT_R_USD,
        "fixed_other_legs": FIXED_OTHER_LEGS,
        "nq_risks": list(NQ_RISKS),
        "rows": rows,
        "winners": winners,
    }

    (OUTPUT_DIR / "portfolio_proxy.json").write_text(json.dumps(payload, indent=2))
    write_report(payload)
    print(f"Saved proxy frontier to {OUTPUT_DIR}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
