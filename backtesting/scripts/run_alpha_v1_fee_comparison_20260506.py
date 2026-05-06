#!/usr/bin/env python3
"""Compare ALPHA_V1 R under old versus updated micro futures fees.

The fee model only changes trade accounting; it does not affect entry/exit
eligibility, contract sizing, or order lifecycle. This script therefore reruns
each leg once per engine path, then revalues the filled trade stream under:

- old fees: 0.05 USD per contract per side
- new fees: midpoint estimate from the May 2026 fee table
"""

from __future__ import annotations

import copy
import csv
import json
import math
import sys
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
BT_ROOT = SCRIPT_DIR.parent
ROOT = BT_ROOT.parent
EXEC_SRC = ROOT / "execution" / "src"

for path in (BT_ROOT / "src", SCRIPT_DIR, EXEC_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import run_alpha_v1_exit_structure_analysis as exit_struct  # noqa: E402
import run_alpha_v1_exit_target_mfe_sweep_20260505 as target_sweep  # noqa: E402
from orb_backtest.data.fees import estimated_commission_per_side  # noqa: E402
from orb_backtest.data.instruments import get_instrument  # noqa: E402
from orb_backtest.engine.simulator import EXIT_NO_FILL, run_backtest  # noqa: E402
from trader import historical_backtest as hb  # noqa: E402
from trader import main as trader_main  # noqa: E402
from trader.main import DEFAULT_CONFIG, ExecutionConfig, load_config, load_exec_configs  # noqa: E402


RUN_SLUG = "alpha_v1_fee_comparison_20260506"
RESULT_DIR = BT_ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = BT_ROOT / "learnings" / "reports" / "ALPHA_V1_FEE_COMPARISON_20260506.md"

FULL_START = "2016-04-17"
END_DATE = "2026-03-24"
END_EXCLUSIVE = "2026-03-25"

OLD_FEE_PER_SIDE = 0.05
NEW_FEE_BY_EXEC_CONTRACT = {
    "MNQ": estimated_commission_per_side("MNQ"),
    "MES": estimated_commission_per_side("MES"),
}
SIGNAL_TO_EXEC = {
    "NQ": "MNQ",
    "ES": "MES",
}


@dataclass(frozen=True)
class ExactLeg:
    key: str
    label: str
    signal_symbol: str
    profile_name: str
    session_key: str
    session_kind: str
    overrides: dict[str, Any]

    @property
    def exec_contract(self) -> str:
        return SIGNAL_TO_EXEC[self.signal_symbol]


def _round(value: Any, digits: int = 2) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(out):
        return 0.0
    return round(out, digits)


def _safe_json(data: Any) -> Any:
    if is_dataclass(data):
        return _safe_json(asdict(data))
    if isinstance(data, dict):
        return {str(k): _safe_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_safe_json(v) for v in data]
    if isinstance(data, float):
        return data if math.isfinite(data) else None
    if hasattr(data, "item"):
        return _safe_json(data.item())
    return data


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _micro_instrument(signal_symbol: str, fee_per_side: float):
    exec_contract = SIGNAL_TO_EXEC[signal_symbol]
    return replace(get_instrument(exec_contract), commission=fee_per_side)


def _point_value_for_exec_contract(exec_contract: str) -> float:
    return float(trader_main.INSTRUMENTS[exec_contract]["point_value"])


def _summarize_research_fee(trades: list[Any], *, point_value: float, fee_per_side: float) -> dict[str, float]:
    total_net_r = 0.0
    total_commission_usd = 0.0
    total_gross_r = 0.0
    filled_count = 0
    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL:
            continue
        risk_points = float(trade.risk_points)
        qty = float(trade.qty)
        gross_risk_usd = risk_points * qty * point_value
        if gross_risk_usd <= 0:
            continue
        gross_pnl_usd = float(trade.r_multiple) * gross_risk_usd
        commission_usd = 2.0 * qty * fee_per_side
        total_net_r += (gross_pnl_usd - commission_usd) / gross_risk_usd
        total_commission_usd += commission_usd
        total_gross_r += float(trade.r_multiple)
        filled_count += 1
    return {
        "trades": filled_count,
        "gross_r": total_gross_r,
        "net_r": total_net_r,
        "commission_usd": total_commission_usd,
    }


def _summarize_exact_fee(trades: list[dict[str, Any]], *, point_value: float, fee_per_side: float) -> dict[str, float]:
    total_net_r = 0.0
    total_commission_usd = 0.0
    total_gross_r = 0.0
    for trade in trades:
        risk_points = float(trade.get("risk_points", 0.0) or 0.0)
        qty = float(trade.get("qty", 0.0) or 0.0)
        gross_risk_usd = risk_points * qty * point_value
        if gross_risk_usd <= 0:
            continue
        gross_pnl_usd = float(trade.get("gross_pnl_usd", 0.0) or 0.0)
        commission_usd = 2.0 * qty * fee_per_side
        total_net_r += (gross_pnl_usd - commission_usd) / gross_risk_usd
        total_commission_usd += commission_usd
        total_gross_r += gross_pnl_usd / gross_risk_usd
    return {
        "trades": len(trades),
        "gross_r": total_gross_r,
        "net_r": total_net_r,
        "commission_usd": total_commission_usd,
    }


def _fee_row(*, scope: str, leg_key: str, leg_label: str, signal_symbol: str, exec_contract: str, old: dict[str, float], new: dict[str, float]) -> dict[str, Any]:
    return {
        "scope": scope,
        "leg_key": leg_key,
        "leg": leg_label,
        "signal_symbol": signal_symbol,
        "exec_contract": exec_contract,
        "old_fee_per_side": OLD_FEE_PER_SIDE,
        "new_fee_per_side": NEW_FEE_BY_EXEC_CONTRACT[exec_contract],
        "trades": int(new["trades"]),
        "gross_r": _round(new["gross_r"], 3),
        "old_fee_net_r": _round(old["net_r"], 3),
        "new_fee_net_r": _round(new["net_r"], 3),
        "delta_r": _round(new["net_r"] - old["net_r"], 3),
        "old_commission_usd": _round(old["commission_usd"], 2),
        "new_commission_usd": _round(new["commission_usd"], 2),
        "delta_commission_usd": _round(new["commission_usd"] - old["commission_usd"], 2),
    }


def _load_research_data(plans: list[Any]) -> dict[str, exit_struct.SymbolData]:
    symbols = sorted({plan.leg.symbol for plan in plans})
    out: dict[str, exit_struct.SymbolData] = {}
    for symbol in symbols:
        print(f"[research] loading {symbol} data", flush=True)
        out[symbol] = exit_struct.load_symbol_data(f"{symbol}_5m.parquet", start=FULL_START, end=END_EXCLUSIVE)
    return out


def run_research_rows() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plans = target_sweep.build_leg_plans()
    data_by_symbol = _load_research_data(plans)
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}

    for idx, plan in enumerate(plans, start=1):
        leg = plan.leg
        exec_contract = SIGNAL_TO_EXEC[leg.symbol]
        new_fee = NEW_FEE_BY_EXEC_CONTRACT[exec_contract]
        data = data_by_symbol[leg.symbol]
        config = replace(
            leg.config,
            instrument=_micro_instrument(leg.symbol, new_fee),
            name=f"ALPHA V1 Fee Compare {leg.label}",
        )
        print(f"[research {idx}/{len(plans)}] {leg.label}", flush=True)
        trades = run_backtest(
            data.df_5m,
            config,
            start_date=FULL_START,
            end_date=END_EXCLUSIVE,
            df_1m=data.df_1m,
            signal_df_1m=data.df_1m,
            df_1s=data.df_1s,
            _maps=data.maps,
        )
        point_value = _point_value_for_exec_contract(exec_contract)
        old = _summarize_research_fee(trades, point_value=point_value, fee_per_side=OLD_FEE_PER_SIDE)
        new = _summarize_research_fee(trades, point_value=point_value, fee_per_side=new_fee)
        row = _fee_row(
            scope="research",
            leg_key=leg.key,
            leg_label=leg.label,
            signal_symbol=leg.symbol,
            exec_contract=exec_contract,
            old=old,
            new=new,
        )
        rows.append(row)
        details[leg.key] = {
            "config": _safe_json(config.__dict__),
            "old": old,
            "new": new,
        }
        print(
            "  old={old:+.2f}R new={new:+.2f}R delta={delta:+.2f}R".format(
                old=row["old_fee_net_r"],
                new=row["new_fee_net_r"],
                delta=row["delta_r"],
            ),
            flush=True,
        )
    return rows, details


def _r11_overrides() -> dict[str, Any]:
    return {
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
        "rr": 3.5,
        "tp1_ratio": 0.4,
        "exit_mode": "split",
        "long_only": True,
        "short_only": False,
        "icf_enabled": False,
        "excluded_dow": [4],
        "fomc_exclusion": False,
        "min_stop_pts": 0.0,
        "min_tp1_pts": 0.0,
        "risk_usd": 250,
        "max_single_risk_usd": 375,
    }


def build_exact_legs(config: dict[str, Any]) -> list[ExactLeg]:
    alpha = {profile.name: profile for profile in load_exec_configs(config)}["ALPHA_V1-A"]
    return [
        ExactLeg(
            key="nq_ny_htf_lsi",
            label="HTF_LSI/NQ_NY-L24",
            signal_symbol="NQ",
            profile_name="FEE_ALPHA_NQ_NY_HTF_LSI",
            session_key="NQ_NY_LSI",
            session_kind="lsi",
            overrides=copy.deepcopy(alpha.lsi_session_overrides["NQ_NY_LSI"]),
        ),
        ExactLeg(
            key="nq_asia_orb",
            label="ORB/NQ_ASIA-RR6",
            signal_symbol="NQ",
            profile_name="FEE_ALPHA_NQ_ASIA_ORB",
            session_key="NQ_Asia",
            session_kind="orb",
            overrides=copy.deepcopy(alpha.session_overrides["NQ_Asia"]),
        ),
        ExactLeg(
            key="es_asia_cont",
            label="ORB/ES_ASIA-RR1.5",
            signal_symbol="ES",
            profile_name="FEE_ALPHA_ES_ASIA_ORB",
            session_key="ES_Asia",
            session_kind="orb",
            overrides=copy.deepcopy(alpha.session_overrides["ES_Asia"]),
        ),
        ExactLeg(
            key="es_ny_cont",
            label="ORB/ES_NY-RR5",
            signal_symbol="ES",
            profile_name="FEE_ALPHA_ES_NY_ORB",
            session_key="ES_NY",
            session_kind="orb",
            overrides=copy.deepcopy(alpha.session_overrides["ES_NY"]),
        ),
        ExactLeg(
            key="nq_ny_orb_r11",
            label="ORB/NQ_NY-R11",
            signal_symbol="NQ",
            profile_name="FEE_ALPHA_NQ_NY_ORB_R11",
            session_key="NQ_NY",
            session_kind="orb",
            overrides=_r11_overrides(),
        ),
    ]


def _profile_for_exact_leg(leg: ExactLeg) -> ExecutionConfig:
    sessions = {leg.session_key: copy.deepcopy(leg.overrides)} if leg.session_kind == "orb" else {}
    lsi_sessions = {leg.session_key: copy.deepcopy(leg.overrides)} if leg.session_kind == "lsi" else {}
    return ExecutionConfig(
        name=leg.profile_name,
        enabled=True,
        max_open_contracts=20,
        webhooks=[],
        session_overrides=sessions,
        lsi_session_overrides=lsi_sessions,
    )


@contextmanager
def _patched_exec_fees() -> Iterator[None]:
    originals = {
        contract: trader_main.INSTRUMENTS[contract]["commission"]
        for contract in NEW_FEE_BY_EXEC_CONTRACT
    }
    try:
        for contract, fee in NEW_FEE_BY_EXEC_CONTRACT.items():
            trader_main.INSTRUMENTS[contract]["commission"] = fee
        yield
    finally:
        for contract, fee in originals.items():
            trader_main.INSTRUMENTS[contract]["commission"] = fee


def _run_exact_leg(config: dict[str, Any], leg: ExactLeg) -> dict[str, Any]:
    profile = _profile_for_exact_leg(leg)
    original_loader = hb.load_exec_configs
    hb.load_exec_configs = lambda _config=None: [profile]
    try:
        return hb.run_profile_backtest_sync(
            config=config,
            profile_name=profile.name,
            start_date=FULL_START,
            end_date=END_DATE,
            label=f"ALPHA V1 Fee Compare Exact {leg.label} {FULL_START} to {END_DATE}",
        )
    finally:
        hb.load_exec_configs = original_loader


def run_exact_rows() -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    config = load_config(DEFAULT_CONFIG)
    legs = build_exact_legs(config)
    rows: list[dict[str, Any]] = []
    details: dict[str, Any] = {}
    all_trades: list[dict[str, Any]] = []

    with _patched_exec_fees():
        for idx, leg in enumerate(legs, start=1):
            print(f"[exact {idx}/{len(legs)}] {leg.label}", flush=True)
            result = _run_exact_leg(config, leg)
            trades = result["trades"]
            for trade in trades:
                trade["fee_compare_leg_key"] = leg.key
                trade["fee_compare_leg_label"] = leg.label
            all_trades.extend(trades)

            point_value = _point_value_for_exec_contract(leg.exec_contract)
            new_fee = NEW_FEE_BY_EXEC_CONTRACT[leg.exec_contract]
            old = _summarize_exact_fee(trades, point_value=point_value, fee_per_side=OLD_FEE_PER_SIDE)
            new = _summarize_exact_fee(trades, point_value=point_value, fee_per_side=new_fee)
            row = _fee_row(
                scope="exact_live",
                leg_key=leg.key,
                leg_label=leg.label,
                signal_symbol=leg.signal_symbol,
                exec_contract=leg.exec_contract,
                old=old,
                new=new,
            )
            rows.append(row)
            details[leg.key] = {
                "profile_name": leg.profile_name,
                "session_kind": leg.session_kind,
                "session_key": leg.session_key,
                "overrides": _safe_json(leg.overrides),
                "result_summary": result.get("summary", {}),
                "old": old,
                "new": new,
            }
            print(
                "  old={old:+.2f}R new={new:+.2f}R delta={delta:+.2f}R trades={trades}".format(
                    old=row["old_fee_net_r"],
                    new=row["new_fee_net_r"],
                    delta=row["delta_r"],
                    trades=row["trades"],
                ),
                flush=True,
            )
    return rows, details, all_trades


def _combined_row(scope: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    subset = [row for row in rows if row["scope"] == scope]
    return {
        "scope": scope,
        "leg_key": "combined",
        "leg": "Combined ALPHA_V1 legs",
        "signal_symbol": "NQ+ES",
        "exec_contract": "MNQ+MES",
        "old_fee_per_side": OLD_FEE_PER_SIDE,
        "new_fee_per_side": "",
        "trades": sum(int(row["trades"]) for row in subset),
        "gross_r": _round(sum(float(row["gross_r"]) for row in subset), 3),
        "old_fee_net_r": _round(sum(float(row["old_fee_net_r"]) for row in subset), 3),
        "new_fee_net_r": _round(sum(float(row["new_fee_net_r"]) for row in subset), 3),
        "delta_r": _round(sum(float(row["delta_r"]) for row in subset), 3),
        "old_commission_usd": _round(sum(float(row["old_commission_usd"]) for row in subset), 2),
        "new_commission_usd": _round(sum(float(row["new_commission_usd"]) for row in subset), 2),
        "delta_commission_usd": _round(sum(float(row["delta_commission_usd"]) for row in subset), 2),
    }


def _fmt(value: Any, digits: int = 2) -> str:
    if value == "":
        return ""
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return str(value)


def _write_report(rows: list[dict[str, Any]], elapsed_sec: float, *, reused_existing: bool = False) -> None:
    def table(scope: str) -> list[str]:
        lines = [
            "| Leg | Contract | Trades | Old fee net R | New fee net R | Delta R | Old comm | New comm |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for row in [r for r in rows if r["scope"] == scope]:
            lines.append(
                f"| {row['leg']} | {row['exec_contract']} | {row['trades']} | "
                f"{_fmt(row['old_fee_net_r'], 2)} | {_fmt(row['new_fee_net_r'], 2)} | {_fmt(row['delta_r'], 2)} | "
                f"${_fmt(row['old_commission_usd'], 2)} | ${_fmt(row['new_commission_usd'], 2)} |"
            )
        return lines

    lines = [
        "# ALPHA_V1 Fee Comparison",
        "",
        f"- Generated: `{datetime.now().isoformat(timespec='seconds')}`",
        f"- Window: `{FULL_START}` to `{END_DATE}`.",
        f"- Old fee: `${OLD_FEE_PER_SIDE:.2f}` per contract per side.",
        f"- New fee midpoint: MNQ/MES `${NEW_FEE_BY_EXEC_CONTRACT['MNQ']:.3f}` per contract per side.",
        "- Fees are accounting-only in both engines, so fills and exits do not change between old-fee and new-fee valuation.",
        "- Research rows use the ALPHA_V1 research configs but revalue them on the live micro contracts for fee realism.",
        "- Exact rows use isolated live-engine profiles for each ALPHA leg. NQ R11 uses the documented `09:30-09:50` ORB override because `ALPHA_V1-A` is not yet a freshly exported five-leg profile.",
        *(
            ["- This report was regenerated from cached completed rows after the full replay finished."]
            if reused_existing
            else []
        ),
        "",
        "## Research Engine",
        "",
        *table("research"),
        "",
        "## Exact Live Engine",
        "",
        *table("exact_live"),
        "",
        "## Read",
        "",
        "- The new fee model is a small but nonzero R haircut in research because those configs use a large nominal research risk.",
        "- The live-engine exact rows show the more relevant haircut because contract sizing and single-contract caps use the current ALPHA sprint risks.",
        (
            "- Runtime: cached rows reused for report generation."
            if reused_existing
            else f"- Elapsed runtime: `{elapsed_sec:.1f}s`."
        ),
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)

    rows_path = RESULT_DIR / "fee_comparison_rows.csv"
    trades_path = RESULT_DIR / "exact_trades.csv"
    reuse_existing = "--reuse-existing" in sys.argv and rows_path.exists()

    if reuse_existing:
        rows = pd.read_csv(rows_path).fillna("").to_dict("records")
        exact_trades = pd.read_csv(trades_path).fillna("").to_dict("records") if trades_path.exists() else []
        research_details: dict[str, Any] = {}
        exact_details: dict[str, Any] = {}
    else:
        research_rows, research_details = run_research_rows()
        exact_rows, exact_details, exact_trades = run_exact_rows()
        rows = [
            *research_rows,
            _combined_row("research", research_rows),
            *exact_rows,
            _combined_row("exact_live", exact_rows),
        ]

    elapsed = time.time() - started
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_slug": RUN_SLUG,
        "window": {"start": FULL_START, "end": END_DATE, "end_exclusive": END_EXCLUSIVE},
        "old_fee_per_side": OLD_FEE_PER_SIDE,
        "new_fee_by_exec_contract": NEW_FEE_BY_EXEC_CONTRACT,
        "reused_existing_rows": reuse_existing,
        "rows": rows,
        "research_details": research_details,
        "exact_details": exact_details,
        "paths": {
            "result_dir": str(RESULT_DIR),
            "summary_json": str(RESULT_DIR / "summary.json"),
            "rows_csv": str(RESULT_DIR / "fee_comparison_rows.csv"),
            "exact_trades_csv": str(RESULT_DIR / "exact_trades.csv"),
            "report": str(REPORT_PATH),
        },
        "elapsed_sec": round(elapsed, 1),
    }

    _write_csv(rows_path, rows)
    pd.DataFrame(exact_trades).to_csv(trades_path, index=False)
    (RESULT_DIR / "summary.json").write_text(json.dumps(_safe_json(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _write_report(rows, elapsed, reused_existing=reuse_existing)

    print(json.dumps(_safe_json({"rows": rows, "elapsed_sec": round(elapsed, 1), "report": str(REPORT_PATH)}), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
