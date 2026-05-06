#!/usr/bin/env python3
"""Compare exact single-target candidates against exact split counterparts."""

from __future__ import annotations

import copy
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
EXEC_SRC = ROOT / "execution" / "src"
if str(EXEC_SRC) not in sys.path:
    sys.path.insert(0, str(EXEC_SRC))

from trader import historical_backtest as hb  # noqa: E402
from trader.main import DEFAULT_CONFIG, SESSION_CONFIGS, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_single_vs_split_exact_compare_20260506"
SINGLE_RUN_SLUG = "alpha_v1_single_target_exact_prop_20260506"
BASE_PROFILE = "ALPHA_V1-A"
FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
LAST_1Y_START = "2025-03-24"
LAST_2Y_START = "2024-03-24"

RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
SINGLE_RESULT_DIR = BT_ROOT / "data" / "results" / SINGLE_RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_SINGLE_VS_SPLIT_EXACT_COMPARE_20260506.md"


@dataclass(frozen=True)
class PairSpec:
    key: str
    label: str
    session_key: str
    single_key: str
    single_label: str
    split_rr: float
    split_tp1_ratio: float
    split_source: str
    full_overrides: dict[str, Any] | None = None

    @property
    def split_profile_name(self) -> str:
        return f"EXACT_{self.key}_SPLIT".upper()[:120]

    @property
    def single_cache_path(self) -> Path:
        return SINGLE_RESULT_DIR / f"exact_{self.single_key}.json"


PAIRS = (
    PairSpec(
        key="es_ny_orb",
        label="ES NY ORB",
        session_key="ES_NY",
        single_key="es_ny_orb_single_1r",
        single_label="single 1.0R",
        split_rr=5.0,
        split_tp1_ratio=0.2,
        split_source=f"{BASE_PROFILE} ES_NY split",
    ),
    PairSpec(
        key="nq_ny_orb_r11",
        label="NQ NY ORB R11",
        session_key="NQ_NY",
        single_key="nq_ny_orb_r11_single_1p4r",
        single_label="single 1.4R",
        split_rr=3.5,
        split_tp1_ratio=0.4,
        split_source="research NQ_NY R11 split branch",
        full_overrides={
            "orb_start": "09:30",
            "orb_end": "09:50",
            "entry_start": "09:50",
            "entry_end": "12:00",
            "flat_start": "15:30",
            "flat_end": "16:00",
            "stop_basis": "atr",
            "stop_atr_pct": 7.0,
            "stop_orb_pct": 0.0,
            "gap_filter_basis": "atr",
            "min_gap_atr_pct": 2.5,
            "max_gap_atr_pct": 0,
            "instrument": "NQ",
            "atr_length": 12,
            "long_only": True,
            "short_only": False,
            "icf_enabled": False,
            "excluded_dow": [4],
            "fomc_exclusion": False,
            "min_stop_pts": 0.0,
            "min_tp1_pts": 0.0,
            "risk_usd": 400,
            "max_single_risk_usd": 400,
        },
    ),
    PairSpec(
        key="es_asia_orb",
        label="ES Asia ORB",
        session_key="ES_Asia",
        single_key="es_asia_orb_single_1p25r",
        single_label="single 1.25R",
        split_rr=1.5,
        split_tp1_ratio=0.7,
        split_source=f"{BASE_PROFILE} ES_Asia split",
    ),
)


def _round(value: Any, digits: int = 2) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return round(out, digits)


def _pct(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator) * 100.0, 2) if denominator else 0.0


def _json_default(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _safe_json(data: Any) -> Any:
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    if isinstance(data, (np.integer,)):
        return int(data)
    if isinstance(data, (np.floating,)):
        out = float(data)
        return out if math.isfinite(out) else None
    return data


def _fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "inf" if value > 0 else "-"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"
    return str(value)


def _split_overrides(pair: PairSpec, alpha: ExecutionConfig) -> dict[str, Any]:
    if pair.full_overrides is not None:
        overrides = copy.deepcopy(pair.full_overrides)
    elif pair.session_key in alpha.session_overrides:
        overrides = copy.deepcopy(alpha.session_overrides[pair.session_key])
    else:
        overrides = copy.deepcopy(SESSION_CONFIGS[pair.session_key])
    overrides.update(
        {
            "rr": pair.split_rr,
            "tp1_ratio": pair.split_tp1_ratio,
            "exit_mode": "split",
        }
    )
    return overrides


def _profile_for(pair: PairSpec, alpha: ExecutionConfig) -> ExecutionConfig:
    return ExecutionConfig(
        name=pair.split_profile_name,
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides={pair.session_key: _split_overrides(pair, alpha)},
        lsi_session_overrides={},
    )


def _run_split_exact(config: dict[str, Any], pair: PairSpec, profile: ExecutionConfig) -> dict[str, Any]:
    cache_path = RESULT_DIR / f"exact_{pair.key}_split.json"
    if cache_path.exists():
        print(f"[split cache] {pair.label}", flush=True)
        return json.loads(cache_path.read_text())

    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        result = hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"ALPHA V1 Exact Split {pair.label} {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader

    result_id = hb.save_profile_backtest(result)
    payload = {
        "pair": pair.__dict__,
        "profile_name": profile.name,
        "profile_session_overrides": _safe_json(profile.session_overrides),
        "result_id": result_id,
        "result": result,
    }
    cache_path.write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True, default=_json_default) + "\n")
    return payload


def _load_single(pair: PairSpec) -> dict[str, Any]:
    if not pair.single_cache_path.exists():
        raise FileNotFoundError(f"Missing single exact cache: {pair.single_cache_path}")
    return json.loads(pair.single_cache_path.read_text())


def _slice(trades: list[dict[str, Any]], start: str, end: str) -> list[dict[str, Any]]:
    return [trade for trade in trades if start <= str(trade.get("date", "")) <= end]


def _metrics(
    *,
    pair: PairSpec,
    structure: str,
    label: str,
    target_label: str,
    result_id: str,
    trades: list[dict[str, Any]],
    window: str,
    start: str,
) -> dict[str, Any]:
    selected = _slice(trades, start, END_DATE)
    summary = hb._compute_summary(selected)
    exits = dict(summary.get("exit_breakdown") or {})
    total = int(summary.get("total_trades") or 0)
    full_target = int(exits.get("tp2_direct", 0) + exits.get("tp1_tp2", 0))
    tp1_be = int(exits.get("tp1_be", 0))
    tp1_eod = int(exits.get("tp1_eod", 0))
    sl = int(exits.get("sl", 0))
    eod = int(exits.get("eod", 0))
    return {
        "leg": pair.label,
        "structure": structure,
        "label": label,
        "target": target_label,
        "window": window,
        "start": start,
        "end": END_DATE,
        "result_id": result_id,
        "trades": total,
        "net_r": _round(summary.get("total_r"), 3),
        "profit_factor": _round(summary.get("profit_factor"), 4),
        "win_rate_pct": _round(float(summary.get("win_rate") or 0.0) * 100.0, 2),
        "max_dd_r": _round(abs(float(summary.get("max_drawdown_r") or 0.0)), 3),
        "target_count": full_target,
        "target_rate_pct": _pct(full_target, total),
        "tp1_be_count": tp1_be,
        "tp1_be_rate_pct": _pct(tp1_be, total),
        "tp1_eod_count": tp1_eod,
        "tp1_eod_rate_pct": _pct(tp1_eod, total),
        "sl_count": sl,
        "sl_rate_pct": _pct(sl, total),
        "eod_count": eod,
        "eod_rate_pct": _pct(eod, total),
        "exit_breakdown": exits,
    }


def _delta_rows(metric_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {(row["leg"], row["window"], row["structure"]): row for row in metric_rows}
    rows = []
    for pair in PAIRS:
        for window in ("full", "last_2y", "last_1y"):
            single = by_key[(pair.label, window, "single")]
            split = by_key[(pair.label, window, "split")]
            rows.append(
                {
                    "leg": pair.label,
                    "window": window,
                    "single_target": single["target"],
                    "split_target": split["target"],
                    "single_trades": single["trades"],
                    "split_trades": split["trades"],
                    "delta_trades": single["trades"] - split["trades"],
                    "single_net_r": single["net_r"],
                    "split_net_r": split["net_r"],
                    "delta_r": _round(float(single["net_r"] or 0.0) - float(split["net_r"] or 0.0), 3),
                    "single_pf": single["profit_factor"],
                    "split_pf": split["profit_factor"],
                    "delta_pf": _round(float(single["profit_factor"] or 0.0) - float(split["profit_factor"] or 0.0), 4),
                    "single_dd_r": single["max_dd_r"],
                    "split_dd_r": split["max_dd_r"],
                    "delta_dd_r": _round(float(single["max_dd_r"] or 0.0) - float(split["max_dd_r"] or 0.0), 3),
                    "single_target_pct": single["target_rate_pct"],
                    "split_full_target_pct": split["target_rate_pct"],
                    "split_tp1_be_pct": split["tp1_be_rate_pct"],
                    "single_sl_pct": single["sl_rate_pct"],
                    "split_sl_pct": split["sl_rate_pct"],
                    "single_result_id": single["result_id"],
                    "split_result_id": split["result_id"],
                }
            )
    return rows


def _md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return "_No rows._"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = ["| " + " | ".join(_fmt(row.get(col)) for col in columns) + " |" for row in rows]
    return "\n".join([header, sep, *body])


def _write_report(delta_rows: list[dict[str, Any]], metric_rows: list[dict[str, Any]]) -> None:
    full = [row for row in delta_rows if row["window"] == "full"]
    lines = [
        "# ALPHA_V1 Exact Single vs Split Target Comparison",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Window: `{FULL_START}` to `{END_DATE}`",
        "- Engine path: `execution/src/trader/historical_backtest.py`; all rows are single-leg exact live-engine replays.",
        "- Split counterparts use the same session/stop/gap definitions as the single-target candidates, with only `exit_mode`, `rr`, and `tp1_ratio` reverted to the split structure.",
        "",
        "## Full-Window Delta",
        "",
        _md_table(
            full,
            [
                "leg",
                "single_target",
                "split_target",
                "single_trades",
                "split_trades",
                "single_net_r",
                "split_net_r",
                "delta_r",
                "single_pf",
                "split_pf",
                "delta_pf",
                "single_dd_r",
                "split_dd_r",
                "delta_dd_r",
                "single_target_pct",
                "split_full_target_pct",
                "split_tp1_be_pct",
            ],
        ),
        "",
        "## All Windows",
        "",
        _md_table(
            delta_rows,
            [
                "leg",
                "window",
                "single_net_r",
                "split_net_r",
                "delta_r",
                "single_pf",
                "split_pf",
                "single_dd_r",
                "split_dd_r",
                "single_target_pct",
                "split_full_target_pct",
                "split_tp1_be_pct",
            ],
        ),
        "",
        "## Read",
        "",
        "- ES NY does not validate as a single-target upgrade: exact split is stronger on net R, PF, and DD, although it gets there with the same uncomfortable TP1/BE-heavy behavior.",
        "- NQ R11 is also better as split on exact edge: single target greatly increases clean target exits, but gives up R/PF for almost no DD benefit.",
        "- ES Asia is the only true exact single-target upgrade on R/PF, but it expands DD and lowers WR, so it is still a tradeoff rather than a free replacement.",
        "",
        "## Result IDs",
        "",
        _md_table(
            full,
            ["leg", "single_result_id", "split_result_id"],
        ),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    config = load_config(DEFAULT_CONFIG)
    alpha = {profile.name: profile for profile in load_exec_configs(config)}[BASE_PROFILE]

    metric_rows: list[dict[str, Any]] = []
    exact_payloads: list[dict[str, Any]] = []
    all_split_trades: list[dict[str, Any]] = []

    for idx, pair in enumerate(PAIRS, start=1):
        print(f"[{idx}/{len(PAIRS)}] {pair.label}", flush=True)
        single_payload = _load_single(pair)
        single_result = single_payload["result"]
        single_trades = single_result.get("trades", [])
        single_result_id = str(single_payload.get("result_id", ""))

        profile = _profile_for(pair, alpha)
        split_payload = _run_split_exact(config, pair, profile)
        split_result = split_payload["result"]
        split_trades = split_result.get("trades", [])
        split_result_id = str(split_payload.get("result_id", ""))

        for trade in split_trades:
            trade["comparison_leg"] = pair.key
        all_split_trades.extend(split_trades)
        exact_payloads.append({key: value for key, value in split_payload.items() if key != "result"})

        for window, start in (("full", FULL_START), ("last_2y", LAST_2Y_START), ("last_1y", LAST_1Y_START)):
            metric_rows.append(
                _metrics(
                    pair=pair,
                    structure="single",
                    label=f"{pair.label} {pair.single_label}",
                    target_label=pair.single_label,
                    result_id=single_result_id,
                    trades=single_trades,
                    window=window,
                    start=start,
                )
            )
            metric_rows.append(
                _metrics(
                    pair=pair,
                    structure="split",
                    label=f"{pair.label} split rr {pair.split_rr:g} tp1 {pair.split_tp1_ratio:g}",
                    target_label=f"split rr {pair.split_rr:g} / tp1 {pair.split_tp1_ratio:g}",
                    result_id=split_result_id,
                    trades=split_trades,
                    window=window,
                    start=start,
                )
            )
        print(
            "  single={single:+.2f}R split={split:+.2f}R split_id={rid}".format(
                single=float(single_result["summary"].get("total_r") or 0.0),
                split=float(split_result["summary"].get("total_r") or 0.0),
                rid=split_result_id,
            ),
            flush=True,
        )

    deltas = _delta_rows(metric_rows)
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "window": {"start": FULL_START, "end": END_DATE},
        "single_source_run": SINGLE_RUN_SLUG,
        "split_exact_payloads": exact_payloads,
        "metric_rows": metric_rows,
        "delta_rows": deltas,
        "paths": {
            "result_dir": str(RESULT_DIR),
            "summary_json": str(RESULT_DIR / "summary.json"),
            "split_trades_csv": str(RESULT_DIR / "split_exact_trades.csv"),
            "metrics_csv": str(RESULT_DIR / "metrics.csv"),
            "deltas_csv": str(RESULT_DIR / "deltas.csv"),
            "report": str(REPORT_PATH),
        },
        "elapsed_sec": round(time.time() - started, 1),
    }
    pd.DataFrame(all_split_trades).to_csv(RESULT_DIR / "split_exact_trades.csv", index=False)
    pd.DataFrame(metric_rows).to_csv(RESULT_DIR / "metrics.csv", index=False)
    pd.DataFrame(deltas).to_csv(RESULT_DIR / "deltas.csv", index=False)
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(summary), indent=2, sort_keys=True, default=_json_default) + "\n")
    _write_report(deltas, metric_rows)

    print("REPORT", REPORT_PATH, flush=True)
    print("DELTAS")
    for row in [row for row in deltas if row["window"] == "full"]:
        print(json.dumps(row, sort_keys=True, default=_json_default), flush=True)
    print(f"Elapsed {summary['elapsed_sec']:.1f}s", flush=True)


if __name__ == "__main__":
    main()
