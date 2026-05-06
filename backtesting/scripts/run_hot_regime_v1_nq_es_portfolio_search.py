#!/usr/bin/env python3
"""Exact NQ+ES-only portfolio search for HOT_REGIME_V1.

The search is intentionally compact and portfolio-level: every row is replayed
through the production execution engines with the live contract cap. It uses
real session names so production overlap hooks remain active.
"""

from __future__ import annotations

import copy
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader import main as tm  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config  # noqa: E402


RUN_SLUG = "hot_regime_v1_nq_es_portfolio_search_20260505"
RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "HOT_REGIME_V1_NQ_ES_PORTFOLIO_SEARCH_20260505.md"

START_DATE = "2025-03-24"
END_DATE = "2026-03-24"
BASE_PROFILE_NAME = "HOT_REGIME_V1"

NQ_ES_LEGS = ["NQ_NY", "NQ_Asia", "NQ_NY_LSI", "ES_NY", "ES_Asia", "ES_NY_LSI"]
CORE_NO_ES_LSI = ["NQ_NY", "NQ_Asia", "NQ_NY_LSI", "ES_NY", "ES_Asia"]
CORE_NO_NQ_ORB_ES_LSI = ["NQ_Asia", "NQ_NY_LSI", "ES_NY", "ES_Asia"]

SESSION_LEGS = {"NQ_NY", "NQ_Asia", "ES_NY", "ES_Asia"}
LSI_LEGS = {"NQ_NY_LSI", "ES_NY_LSI"}

CONSTRAINED_BEST = {
    "NQ_NY": (3.0, 0.50),
    "NQ_Asia": (2.0, 0.70),
    "NQ_NY_LSI": (1.5, 1.00),
    "ES_NY": (3.0, 0.50),
    "ES_Asia": (2.5, 0.60),
    "ES_NY_LSI": (1.5, 1.00),
}

ALT = {
    "NQ_NY": {
        "rr25_tp06": (2.5, 0.60),
        "rr2_tp075": (2.0, 0.75),
    },
    "NQ_Asia": {
        "lowdd_rr2_tp05": (2.0, 0.50),
        "rr2_tp067": (2.0, 0.67),
    },
    "NQ_NY_LSI": {
        "rr3_tp05": (3.0, 0.50),
        "rr15_tp09": (1.5, 0.90),
    },
    "ES_NY": {
        "lowdd_rr2_tp075": (2.0, 0.75),
        "pf_rr3_tp04": (3.0, 0.40),
    },
    "ES_Asia": {
        "rr3_tp05": (3.0, 0.50),
        "current_rr2_tp07": (2.0, 0.70),
    },
    "ES_NY_LSI": {
        "constrained_rr15_tp1": (1.5, 1.00),
    },
}


def _round(value: Any, digits: int = 2) -> float:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return 0.0


def _metrics(trades: list[dict[str, Any]]) -> dict[str, Any]:
    summary = hb._compute_summary(trades)
    return {
        "trades": int(summary.get("total_trades", 0) or 0),
        "net_r": _round(summary.get("total_r", 0.0), 2),
        "wr_pct": _round(float(summary.get("win_rate", 0.0) or 0.0) * 100.0, 2),
        "pf": _round(summary.get("profit_factor", 0.0), 3),
        "dd_r": _round(summary.get("max_drawdown_r", 0.0), 2),
        "sharpe": _round(summary.get("sharpe_ratio", 0.0), 3),
        "calmar": _round(summary.get("calmar_ratio", 0.0), 3),
    }


def _profile_symbols(profile: ExecutionConfig) -> list[str]:
    symbols = set()
    for session_name, overrides in profile.session_overrides.items():
        merged = {**tm.SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(str(merged.get("instrument", "NQ")))
    for session_name, overrides in profile.lsi_session_overrides.items():
        merged = {**tm.LSI_SESSION_CONFIGS.get(session_name, {}), **overrides}
        symbols.add(str(merged.get("instrument", "NQ")))
    return sorted(symbols)


def _with_target(overrides: dict[str, Any], target: tuple[float, float] | None) -> dict[str, Any]:
    out = copy.deepcopy(overrides)
    if target is None:
        return out
    rr, tp1 = target
    out["rr"] = rr
    out["tp1_ratio"] = tp1
    if float(out.get("wide_stop_target_rr", 0.0) or 0.0) > rr:
        out["wide_stop_target_rr"] = rr
    return out


def _build_profile(
    *,
    name: str,
    base_profile: ExecutionConfig,
    legs: list[str],
    targets: dict[str, tuple[float, float]] | None,
) -> ExecutionConfig:
    targets = targets or {}
    sessions: dict[str, dict[str, Any]] = {}
    lsi_sessions: dict[str, dict[str, Any]] = {}
    for leg in legs:
        if leg in SESSION_LEGS:
            sessions[leg] = _with_target(base_profile.session_overrides[leg], targets.get(leg))
        elif leg in LSI_LEGS:
            lsi_sessions[leg] = _with_target(base_profile.lsi_session_overrides[leg], targets.get(leg))
        else:
            raise KeyError(leg)
    return ExecutionConfig(
        name=name,
        enabled=True,
        max_open_contracts=20.0,
        webhooks=[],
        session_overrides=sessions,
        lsi_session_overrides=lsi_sessions,
    )


def _run_profile(config: dict[str, Any], profile: ExecutionConfig, label: str) -> dict[str, Any]:
    original_hb_loader = hb.load_exec_configs
    original_tm_loader = tm.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    tm.load_exec_configs = lambda _config=None: [profile]
    try:
        latest = hb.latest_common_end(_profile_symbols(profile))
        return hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=START_DATE,
            end_date=END_DATE,
            latest_data_ts=latest,
            label=label,
        )
    finally:
        hb.load_exec_configs = original_hb_loader
        tm.load_exec_configs = original_tm_loader


def _by_leg_metrics(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        grouped[str(trade.get("session", ""))].append(trade)
    return [{"leg": leg, **_metrics(items)} for leg, items in sorted(grouped.items())]


def _targets_with(*updates: tuple[str, tuple[float, float]]) -> dict[str, tuple[float, float]]:
    targets = dict(CONSTRAINED_BEST)
    for leg, target in updates:
        targets[leg] = target
    return targets


def _specs() -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = [
        {"name": "current_nq_es_all6", "legs": NQ_ES_LEGS, "targets": {}},
        {"name": "current_nq_es_no_es_lsi", "legs": CORE_NO_ES_LSI, "targets": {}},
        {"name": "constrained_nq_es_all6", "legs": NQ_ES_LEGS, "targets": CONSTRAINED_BEST},
        {"name": "constrained_nq_es_no_es_lsi", "legs": CORE_NO_ES_LSI, "targets": CONSTRAINED_BEST},
        {"name": "constrained_no_nq_orb_no_es_lsi", "legs": CORE_NO_NQ_ORB_ES_LSI, "targets": CONSTRAINED_BEST},
        {"name": "constrained_no_nq_lsi_no_es_lsi", "legs": ["NQ_NY", "NQ_Asia", "ES_NY", "ES_Asia"], "targets": CONSTRAINED_BEST},
        {"name": "constrained_no_es_ny_no_es_lsi", "legs": ["NQ_NY", "NQ_Asia", "NQ_NY_LSI", "ES_Asia"], "targets": CONSTRAINED_BEST},
        {"name": "constrained_no_es_asia_no_es_lsi", "legs": ["NQ_NY", "NQ_Asia", "NQ_NY_LSI", "ES_NY"], "targets": CONSTRAINED_BEST},
        {"name": "nq_only_current", "legs": ["NQ_NY", "NQ_Asia", "NQ_NY_LSI"], "targets": {}},
        {"name": "nq_only_constrained", "legs": ["NQ_NY", "NQ_Asia", "NQ_NY_LSI"], "targets": CONSTRAINED_BEST},
        {"name": "es_only_current", "legs": ["ES_NY", "ES_Asia", "ES_NY_LSI"], "targets": {}},
        {"name": "es_only_constrained_no_es_lsi", "legs": ["ES_NY", "ES_Asia"], "targets": CONSTRAINED_BEST},
        {"name": "asia_pair_plus_nq_lsi", "legs": ["NQ_Asia", "ES_Asia", "NQ_NY_LSI"], "targets": CONSTRAINED_BEST},
        {"name": "asia_pair_only", "legs": ["NQ_Asia", "ES_Asia"], "targets": CONSTRAINED_BEST},
    ]

    for leg, variants in ALT.items():
        if leg == "ES_NY_LSI":
            continue
        for variant_name, target in variants.items():
            specs.append(
                {
                    "name": f"alt_{leg.lower()}_{variant_name}",
                    "legs": CORE_NO_ES_LSI,
                    "targets": _targets_with((leg, target)),
                }
            )

    combo_targets = _targets_with(
        ("NQ_Asia", ALT["NQ_Asia"]["lowdd_rr2_tp05"]),
        ("ES_NY", ALT["ES_NY"]["lowdd_rr2_tp075"]),
    )
    specs.append({"name": "combo_nq_asia_lowdd_es_ny_lowdd", "legs": CORE_NO_ES_LSI, "targets": combo_targets})
    specs.append({"name": "combo_no_nq_orb_nqasia_lowdd_esny_lowdd", "legs": CORE_NO_NQ_ORB_ES_LSI, "targets": combo_targets})

    combo_targets_2 = _targets_with(
        ("NQ_Asia", ALT["NQ_Asia"]["lowdd_rr2_tp05"]),
        ("ES_NY", ALT["ES_NY"]["lowdd_rr2_tp075"]),
        ("ES_Asia", ALT["ES_Asia"]["rr3_tp05"]),
    )
    specs.append({"name": "combo_clean_targets_core5", "legs": CORE_NO_ES_LSI, "targets": combo_targets_2})
    specs.append({"name": "combo_clean_targets_no_nq_orb", "legs": CORE_NO_NQ_ORB_ES_LSI, "targets": combo_targets_2})

    combo_targets_3 = _targets_with(
        ("NQ_NY", ALT["NQ_NY"]["rr25_tp06"]),
        ("NQ_Asia", ALT["NQ_Asia"]["lowdd_rr2_tp05"]),
        ("NQ_NY_LSI", ALT["NQ_NY_LSI"]["rr3_tp05"]),
        ("ES_NY", ALT["ES_NY"]["lowdd_rr2_tp075"]),
        ("ES_Asia", ALT["ES_Asia"]["rr3_tp05"]),
    )
    specs.append({"name": "combo_all_cleaner_core5", "legs": CORE_NO_ES_LSI, "targets": combo_targets_3})
    specs.append({"name": "combo_all_cleaner_no_nq_orb", "legs": CORE_NO_NQ_ORB_ES_LSI, "targets": combo_targets_3})
    return specs


def _write_report(payload: dict[str, Any]) -> None:
    lines = [
        "# HOT_REGIME_V1 NQ+ES Portfolio Search",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Exact window: `{START_DATE}` to `{END_DATE}`",
        "- Scope: NQ and ES only; GC excluded.",
        "- Method: production exact replay with live `max_open_contracts=20` and real session names.",
        "",
        "## Ranked Portfolios",
        "",
        "| Rank | Portfolio | Legs | Trades | Net R | WR | PF | DD | Sharpe | Calmar |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(payload["ranked"], 1):
        m = row["metrics"]
        lines.append(
            f"| {idx} | `{row['name']}` | {len(row['legs'])} | {m['trades']} | {m['net_r']:.2f} | "
            f"{m['wr_pct']:.2f}% | {m['pf']:.3f} | {m['dd_r']:.2f} | {m['sharpe']:.3f} | {m['calmar']:.3f} |"
        )
    best = payload["ranked"][0]
    lines.extend(
        [
            "",
            "## Best By Leg",
            "",
            f"- Best by net R: `{best['name']}`.",
            "",
            "| Leg | Trades | Net R | WR | PF | DD |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in best["by_leg"]:
        lines.append(
            f"| {row['leg']} | {row['trades']} | {row['net_r']:.2f} | {row['wr_pct']:.2f}% | "
            f"{row['pf']:.3f} | {row['dd_r']:.2f} |"
        )
    lines.extend(["", "## Best Target Map", "", "```json", json.dumps(best["targets"], indent=2, sort_keys=True), "```"])
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    logging.getLogger("trader.gates").setLevel(logging.ERROR)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    base_profile = {profile.name: profile for profile in tm.load_exec_configs(config)}[BASE_PROFILE_NAME]
    specs = _specs()
    rows: list[dict[str, Any]] = []
    print(f"Running {len(specs)} NQ+ES exact portfolio profiles ({START_DATE} to {END_DATE})", flush=True)
    for idx, spec in enumerate(specs, 1):
        started = time.time()
        profile = _build_profile(
            name=f"NQES_PORT_{idx:02d}_{spec['name']}"[:120],
            base_profile=base_profile,
            legs=spec["legs"],
            targets=spec.get("targets") or {},
        )
        print(f"[{idx}/{len(specs)}] {spec['name']} legs={len(spec['legs'])}", flush=True)
        result = _run_profile(config, profile, f"HOT NQ+ES portfolio search {spec['name']}")
        trades = result.get("trades", [])
        row = {
            "name": spec["name"],
            "profile_name": profile.name,
            "legs": spec["legs"],
            "targets": spec.get("targets") or {},
            "metrics": _metrics(trades),
            "summary": result.get("summary", {}),
            "by_leg": _by_leg_metrics(trades),
            "elapsed_sec": round(time.time() - started, 1),
        }
        rows.append(row)
        print(
            "  -> trades={trades} net={net:+.2f}R pf={pf:.3f} dd={dd:.2f}R elapsed={elapsed:.1f}s".format(
                trades=row["metrics"]["trades"],
                net=row["metrics"]["net_r"],
                pf=row["metrics"]["pf"],
                dd=row["metrics"]["dd_r"],
                elapsed=row["elapsed_sec"],
            ),
            flush=True,
        )
    ranked = sorted(rows, key=lambda r: (r["metrics"]["net_r"], r["metrics"]["pf"], r["metrics"]["dd_r"]), reverse=True)
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "window": {"start": START_DATE, "end": END_DATE},
        "scope": "NQ and ES only",
        "rows": rows,
        "ranked": ranked,
        "paths": {"summary_json": str(RESULT_DIR / "summary.json"), "report": str(REPORT_PATH)},
    }
    (RESULT_DIR / "summary.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    _write_report(payload)
    print("SUMMARY_JSON", RESULT_DIR / "summary.json", flush=True)
    print("REPORT", REPORT_PATH, flush=True)
    print("TOP5")
    for row in ranked[:5]:
        print(json.dumps({"name": row["name"], **row["metrics"]}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
