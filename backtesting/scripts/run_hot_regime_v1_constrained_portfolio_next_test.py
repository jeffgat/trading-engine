#!/usr/bin/env python3
"""Portfolio-level exact replay for constrained HOT_REGIME_V1 target variants.

This intentionally uses the real session names in each replay profile so the
production overlap wiring, especially NQ_NY vs NQ_NY_LSI, stays active.
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


RUN_SLUG = "hot_regime_v1_constrained_portfolio_next_test_20260505"
RESULT_DIR = ROOT / "backtesting" / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "backtesting" / "learnings" / "reports" / "HOT_REGIME_V1_CONSTRAINED_PORTFOLIO_NEXT_TEST_20260505.md"

START_DATE = "2025-03-24"
END_DATE = "2026-03-24"
BASE_PROFILE_NAME = "HOT_REGIME_V1"

BEST_TARGETS: dict[str, tuple[float, float]] = {
    "NQ_NY": (3.0, 0.50),
    "NQ_Asia": (2.0, 0.70),
    "NQ_NY_LSI": (1.5, 1.00),
    "ES_NY": (3.0, 0.50),
    "ES_Asia": (2.5, 0.60),
    "ES_NY_LSI": (1.5, 1.00),
    "GC_NY": (2.0, 0.60),
    "GC_Asia": (3.0, 0.34),
    "GC_NY_LSI": (1.5, 1.00),
}

ALT_TARGETS: dict[str, dict[str, tuple[float, float]]] = {
    "NQ_NY": {
        "rr2_tp075": (2.0, 0.75),
        "rr25_tp06": (2.5, 0.60),
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
        "pf_rr3_tp04": (3.0, 0.40),
        "lowdd_rr2_tp075": (2.0, 0.75),
    },
    "ES_Asia": {
        "rr3_tp05": (3.0, 0.50),
        "rr2_tp07": (2.0, 0.70),
    },
    "GC_NY": {
        "lowdd_rr3_tp034": (3.0, 0.34),
        "tie_rr3_tp04": (3.0, 0.40),
    },
    "GC_Asia": {
        "rr3_tp04": (3.0, 0.40),
        "rr3_tp05": (3.0, 0.50),
    },
    "GC_NY_LSI": {
        "rr15_tp09": (1.5, 0.90),
        "rr2_tp075": (2.0, 0.75),
    },
}

SESSION_LEGS = {"NQ_NY", "NQ_Asia", "ES_NY", "ES_Asia", "GC_NY", "GC_Asia"}
LSI_LEGS = {"NQ_NY_LSI", "ES_NY_LSI", "GC_NY_LSI"}
ALL_LEGS = [
    "NQ_NY",
    "NQ_Asia",
    "NQ_NY_LSI",
    "ES_NY",
    "ES_Asia",
    "ES_NY_LSI",
    "GC_NY",
    "GC_Asia",
    "GC_NY_LSI",
]


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


def _with_target(overrides: dict[str, Any], target: tuple[float, float]) -> dict[str, Any]:
    rr, tp1 = target
    out = copy.deepcopy(overrides)
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
    targets: dict[str, tuple[float, float]] | None = None,
) -> ExecutionConfig:
    targets = targets or {}
    session_overrides: dict[str, dict[str, Any]] = {}
    lsi_overrides: dict[str, dict[str, Any]] = {}
    for leg in legs:
        if leg in SESSION_LEGS:
            base = base_profile.session_overrides[leg]
            override = _with_target(base, targets[leg]) if leg in targets else copy.deepcopy(base)
            session_overrides[leg] = override
        elif leg in LSI_LEGS:
            base = base_profile.lsi_session_overrides[leg]
            override = _with_target(base, targets[leg]) if leg in targets else copy.deepcopy(base)
            lsi_overrides[leg] = override
        else:
            raise KeyError(f"Unknown leg {leg!r}")
    return ExecutionConfig(
        name=name,
        enabled=True,
        max_open_contracts=20.0,
        webhooks=[],
        session_overrides=session_overrides,
        lsi_session_overrides=lsi_overrides,
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
    return [
        {"leg": leg, **_metrics(leg_trades)}
        for leg, leg_trades in sorted(grouped.items())
    ]


def _specs() -> list[dict[str, Any]]:
    best_no_es_lsi = {k: v for k, v in BEST_TARGETS.items() if k != "ES_NY_LSI"}
    legs_no_es_lsi = [leg for leg in ALL_LEGS if leg != "ES_NY_LSI"]

    specs: list[dict[str, Any]] = [
        {"name": "current_hot_all9", "legs": ALL_LEGS, "targets": {}},
        {"name": "best_constrained_all9", "legs": ALL_LEGS, "targets": BEST_TARGETS},
        {"name": "best_constrained_no_es_ny_lsi", "legs": legs_no_es_lsi, "targets": best_no_es_lsi},
        {"name": "no_nq_ny_orb", "legs": [leg for leg in legs_no_es_lsi if leg != "NQ_NY"], "targets": best_no_es_lsi},
        {"name": "no_nq_ny_lsi", "legs": [leg for leg in legs_no_es_lsi if leg != "NQ_NY_LSI"], "targets": best_no_es_lsi},
        {"name": "no_gc_ny_orb", "legs": [leg for leg in legs_no_es_lsi if leg != "GC_NY"], "targets": best_no_es_lsi},
        {"name": "no_gc_ny_lsi", "legs": [leg for leg in legs_no_es_lsi if leg != "GC_NY_LSI"], "targets": best_no_es_lsi},
        {
            "name": "asia_core_plus_nq_lsi_es_ny",
            "legs": ["NQ_Asia", "ES_Asia", "GC_Asia", "NQ_NY_LSI", "ES_NY"],
            "targets": best_no_es_lsi,
        },
    ]

    for leg, variants in ALT_TARGETS.items():
        if leg == "ES_NY_LSI":
            continue
        for variant_name, target in variants.items():
            targets = {**best_no_es_lsi, leg: target}
            specs.append(
                {
                    "name": f"alt_{leg.lower()}_{variant_name}",
                    "legs": legs_no_es_lsi,
                    "targets": targets,
                }
            )

    clean_mix = {
        **best_no_es_lsi,
        "NQ_NY": ALT_TARGETS["NQ_NY"]["rr2_tp075"],
        "NQ_Asia": ALT_TARGETS["NQ_Asia"]["lowdd_rr2_tp05"],
        "ES_NY": ALT_TARGETS["ES_NY"]["pf_rr3_tp04"],
        "ES_Asia": ALT_TARGETS["ES_Asia"]["rr3_tp05"],
        "GC_NY": ALT_TARGETS["GC_NY"]["lowdd_rr3_tp034"],
        "GC_NY_LSI": ALT_TARGETS["GC_NY_LSI"]["rr15_tp09"],
    }
    specs.extend(
        [
            {"name": "clean_mix_no_es_lsi", "legs": legs_no_es_lsi, "targets": clean_mix},
            {
                "name": "clean_core_no_nq_orb_gc_ny",
                "legs": ["NQ_Asia", "NQ_NY_LSI", "ES_NY", "ES_Asia", "GC_Asia"],
                "targets": clean_mix,
            },
            {
                "name": "three_asia_plus_nq_lsi",
                "legs": ["NQ_Asia", "ES_Asia", "GC_Asia", "NQ_NY_LSI"],
                "targets": clean_mix,
            },
        ]
    )
    return specs


def _write_report(payload: dict[str, Any]) -> None:
    ranked = payload["ranked"]
    lines = [
        "# HOT_REGIME_V1 Constrained Portfolio Next Test",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Exact window: `{START_DATE}` to `{END_DATE}`",
        "- Constraint: `rr <= 3.0` and `1.0R <= rr * tp1_ratio <= 1.5R`.",
        "- Method: exact production-engine replay with live `max_open_contracts=20`; profiles use real session names to preserve production overlap wiring.",
        "",
        "## Ranked Portfolios",
        "",
        "| Rank | Portfolio | Legs | Trades | Net R | WR | PF | DD | Sharpe | Calmar |",
        "| ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for idx, row in enumerate(ranked, 1):
        lines.append(
            f"| {idx} | `{row['name']}` | {len(row['legs'])} | {row['metrics']['trades']} | "
            f"{row['metrics']['net_r']:.2f} | {row['metrics']['wr_pct']:.2f}% | "
            f"{row['metrics']['pf']:.3f} | {row['metrics']['dd_r']:.2f} | "
            f"{row['metrics']['sharpe']:.3f} | {row['metrics']['calmar']:.3f} |"
        )
    lines.extend(["", "## Best Portfolio By Leg", ""])
    best = ranked[0]
    lines.extend(
        [
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
    lines.extend(["", "## Target Map", "", "```json", json.dumps(best["targets"], indent=2, sort_keys=True), "```"])
    REPORT_PATH.write_text("\n".join(lines) + "\n")


def main() -> None:
    logging.getLogger("trader.gates").setLevel(logging.ERROR)
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    base_profile = {profile.name: profile for profile in tm.load_exec_configs(config)}[BASE_PROFILE_NAME]
    rows: list[dict[str, Any]] = []

    specs = _specs()
    print(f"Running {len(specs)} portfolio exact profiles ({START_DATE} to {END_DATE})", flush=True)
    for idx, spec in enumerate(specs, 1):
        started = time.time()
        profile = _build_profile(
            name=f"HOT_PORT_NEXT_{idx:02d}_{spec['name']}"[:120],
            base_profile=base_profile,
            legs=spec["legs"],
            targets=spec.get("targets") or {},
        )
        print(f"[{idx}/{len(specs)}] {spec['name']} legs={len(spec['legs'])}", flush=True)
        result = _run_profile(config, profile, f"HOT constrained portfolio next test {spec['name']}")
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
        "constraint": {"rr_max": 3.0, "tp1_r_min": 1.0, "tp1_r_max": 1.5},
        "rows": rows,
        "ranked": ranked,
        "paths": {
            "summary_json": str(RESULT_DIR / "summary.json"),
            "report": str(REPORT_PATH),
        },
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
