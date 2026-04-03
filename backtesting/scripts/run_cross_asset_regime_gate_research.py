#!/usr/bin/env python3
"""Cross-asset regime-gate research on the revised shortlist.

Compares ungated vs NQ-style medium-vol avoidance gating across the current
best candidates from the latest per-asset learnings.

Protocol:
- Shared pre-holdout: through 2024-02-29
- Shared holdout: 2024-03-01 to 2026-02-28
- Revised shortlist only (no demoted legacy controls)
- Outputs: machine-readable JSON + short markdown memo
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.analysis.prop_regime_specialist import (  # noqa: E402
    PropFirmProfile,
    build_prop_scorecard,
    simulate_account_attempts,
)
from orb_backtest.analysis.regime_research import (  # noqa: E402
    REGIME_RESEARCH_HOLDOUT_END,
    REGIME_RESEARCH_HOLDOUT_START,
    _filled_trades,
    _regime_lookup,
    build_extended_regime_calendar,
)
from orb_backtest.config import SessionConfig, StrategyConfig  # noqa: E402
from orb_backtest.data.instruments import CL, ES, GC, NQ, RTY, SI  # noqa: E402
from orb_backtest.data.loader import (  # noqa: E402
    load_1m_for_5m,
    load_1s_for_5m,
    load_5m_data,
)
from orb_backtest.engine.simulator import EXIT_NO_FILL, TradeResult, run_backtest  # noqa: E402
from orb_backtest.results.metrics import compute_metrics  # noqa: E402

OUTPUT_DIR = ROOT / "data" / "results" / "cross_asset_regime_gate_research"
PRE_HOLDOUT_END = "2024-02-29"
HOLDOUT_START = REGIME_RESEARCH_HOLDOUT_START
HOLDOUT_END = REGIME_RESEARCH_HOLDOUT_END
AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

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


@dataclass(frozen=True)
class CandidateSpec:
    asset: str
    candidate_id: str
    candidate_name: str
    session: str
    direction: str
    config: StrategyConfig
    magnifier: str
    preferred_gate_mode: str
    notes: str = ""
    post_trade_filters: tuple[Callable[[list[TradeResult]], list[TradeResult]], ...] = field(
        default_factory=tuple
    )


@dataclass
class InstrumentBundle:
    asset: str
    df_5m: pd.DataFrame
    df_1m: pd.DataFrame | None
    df_1s: pd.DataFrame | None
    regime_calendar: pd.DataFrame
    regime_lookup: dict[str, str]
    pre_dates: list[str]
    holdout_dates: list[str]
    first_warmup_date: str


def make_avoidance_gate(regime_calendar: pd.DataFrame) -> Callable[[list[TradeResult]], list[TradeResult]]:
    lookup = _regime_lookup(regime_calendar, "combined_regime")

    def gate(trades: list[TradeResult]) -> list[TradeResult]:
        return [
            t
            for t in trades
            if t.exit_type == EXIT_NO_FILL or lookup.get(t.date) not in AVOID_BUCKETS
        ]

    return gate


def round_or_none(value: object, digits: int = 4) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value, digits)
    return None


def metric_snapshot(trades: list[TradeResult], scorecard: dict | None = None) -> dict:
    metrics = compute_metrics(trades)
    total_trades = int(metrics.get("total_trades", 0) or 0)
    snapshot = {
        "trades": total_trades,
        "net_r": round_or_none(metrics.get("total_r"), 2),
        "calmar": round_or_none(metrics.get("calmar_ratio"), 3),
        "sharpe": round_or_none(metrics.get("sharpe_ratio"), 3),
        "max_drawdown_r": round_or_none(metrics.get("max_drawdown_r"), 2),
        "win_rate": round_or_none(metrics.get("win_rate"), 4),
        "profit_factor": round_or_none(metrics.get("profit_factor"), 3),
    }
    if scorecard is not None:
        snapshot["payout_rate"] = round_or_none(scorecard.get("first_payout_rate"), 4)
        snapshot["breach_rate"] = round_or_none(scorecard.get("breach_rate"), 4)
        snapshot["ev_per_attempt"] = round_or_none(scorecard.get("ev_per_attempt"), 2)
        snapshot["total_attempts"] = int(scorecard.get("total_attempts", 0) or 0)
    else:
        snapshot["payout_rate"] = None
        snapshot["breach_rate"] = None
        snapshot["ev_per_attempt"] = None
        snapshot["total_attempts"] = 0
    return snapshot


def simulate_prop_scorecard(
    candidate: CandidateSpec,
    trades: list[TradeResult],
    trading_dates: list[str],
) -> dict:
    outcomes = simulate_account_attempts(
        specialist_name=candidate.candidate_id,
        trades=trades,
        trading_dates=trading_dates,
        profile=PROP_PROFILE,
        risk_per_r_usd=candidate.config.risk_usd,
    )
    return build_prop_scorecard(outcomes, PROP_PROFILE)


def apply_post_trade_filters(
    trades: list[TradeResult],
    candidate: CandidateSpec,
) -> list[TradeResult]:
    filtered = list(trades)
    for filter_fn in candidate.post_trade_filters:
        filtered = filter_fn(filtered)
    return filtered


def build_candidates() -> list[CandidateSpec]:
    return [
        CandidateSpec(
            asset="NQ",
            candidate_id="nq_asia_2",
            candidate_name="Asia-2",
            session="Asia",
            direction="long",
            config=StrategyConfig(
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
                name="NQ Asia-2 15m ORB100 RR3.5 TP0.6",
            ),
            magnifier="1s",
            preferred_gate_mode="gated",
            notes="2026-04-01 discovery winner; reference case for regime-aware Asia continuation.",
        ),
        CandidateSpec(
            asset="ES",
            candidate_id="es_asia_b",
            candidate_name="Asia-B",
            session="Asia",
            direction="long",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:15",
                        entry_start="20:15",
                        entry_end="23:15",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_atr_pct=12.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=ES,
                strategy="continuation",
                use_bar_magnifier=False,
                risk_usd=5000.0,
                direction_filter="long",
                rr=3.0,
                tp1_ratio=0.6,
                atr_length=14,
                name="ES Asia-B 15m ATR12 RR3.0 TP0.6",
            ),
            magnifier="none",
            preferred_gate_mode="ungated",
            notes="Latest ES leader; newer learnings say ungated is the production preference.",
        ),
        CandidateSpec(
            asset="GC",
            candidate_id="gc_asia_1",
            candidate_name="Asia-1",
            session="Asia",
            direction="both",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:30",
                        entry_start="20:30",
                        entry_end="23:15",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_orb_pct=25.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=GC,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=2.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="GC Asia-1 30m ORB25 RR2.5 TP0.6",
            ),
            magnifier="1s",
            preferred_gate_mode="gated",
            notes="Latest GC regime-era winner; gated variant preferred for production.",
        ),
        CandidateSpec(
            asset="RTY",
            candidate_id="rty_ny_1",
            candidate_name="NY-1",
            session="NY",
            direction="both",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:40",
                        entry_start="09:40",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_orb_pct=75.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=RTY,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=3.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="RTY NY-1 10m ORB75 RR3.5 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Runner-up included for best DSR and best holdout R.",
        ),
        CandidateSpec(
            asset="RTY",
            candidate_id="rty_ny_2",
            candidate_name="NY-2",
            session="NY",
            direction="both",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:40",
                        entry_start="09:40",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_orb_pct=100.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=RTY,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=3.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="RTY NY-2 10m ORB100 RR3.5 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Runner-up included for best holdout payout rate.",
        ),
        CandidateSpec(
            asset="RTY",
            candidate_id="rty_ny_4",
            candidate_name="NY-4",
            session="NY",
            direction="both",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="NY",
                        orb_start="09:30",
                        orb_end="09:40",
                        entry_start="09:40",
                        entry_end="13:00",
                        flat_start="15:50",
                        flat_end="16:00",
                        stop_orb_pct=100.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=RTY,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="both",
                rr=3.0,
                tp1_ratio=0.4,
                atr_length=14,
                name="RTY NY-4 10m ORB100 RR3.0 TP0.4",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Current RTY deployment leader from the revised shortlist.",
        ),
        CandidateSpec(
            asset="SI",
            candidate_id="si_asia_1",
            candidate_name="Asia-1",
            session="Asia",
            direction="short",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:30",
                        entry_start="20:30",
                        entry_end="23:15",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_orb_pct=75.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=SI,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="short",
                rr=2.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="SI Asia-1 30m ORB75 RR2.5 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Included for highest DSR and pre-holdout payout strength.",
        ),
        CandidateSpec(
            asset="SI",
            candidate_id="si_asia_3",
            candidate_name="Asia-3",
            session="Asia",
            direction="short",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="Asia",
                        orb_start="20:00",
                        orb_end="20:30",
                        entry_start="20:30",
                        entry_end="23:15",
                        flat_start="04:00",
                        flat_end="07:00",
                        stop_orb_pct=75.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=SI,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="short",
                rr=3.0,
                tp1_ratio=0.6,
                atr_length=14,
                name="SI Asia-3 30m ORB75 RR3.0 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Included for strongest holdout result on SI.",
        ),
        CandidateSpec(
            asset="CL",
            candidate_id="cl_ldn_1",
            candidate_name="LDN-1",
            session="LDN",
            direction="long",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="LDN",
                        orb_start="03:00",
                        orb_end="03:30",
                        entry_start="03:30",
                        entry_end="07:00",
                        flat_start="08:20",
                        flat_end="08:25",
                        stop_atr_pct=8.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=CL,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=3.5,
                tp1_ratio=0.6,
                atr_length=14,
                name="CL LDN-1 30m ATR8 RR3.5 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Included for best CL holdout R.",
        ),
        CandidateSpec(
            asset="CL",
            candidate_id="cl_ldn_2",
            candidate_name="LDN-2",
            session="LDN",
            direction="long",
            config=StrategyConfig(
                sessions=(
                    SessionConfig(
                        name="LDN",
                        orb_start="03:00",
                        orb_end="03:30",
                        entry_start="03:30",
                        entry_end="07:00",
                        flat_start="08:20",
                        flat_end="08:25",
                        stop_atr_pct=8.0,
                        min_gap_atr_pct=1.0,
                    ),
                ),
                instrument=CL,
                strategy="continuation",
                use_bar_magnifier=True,
                risk_usd=5000.0,
                direction_filter="long",
                rr=3.0,
                tp1_ratio=0.6,
                atr_length=14,
                name="CL LDN-2 30m ATR8 RR3.0 TP0.6",
            ),
            magnifier="1m",
            preferred_gate_mode="ungated",
            notes="Included for best CL DSR and holdout payout rate.",
        ),
    ]


def bundle_for_asset(asset: str, candidates: list[CandidateSpec]) -> InstrumentBundle:
    instrument = candidates[0].config.instrument
    requires_1m = any(spec.magnifier in {"1m", "1s"} for spec in candidates)
    requires_1s = any(spec.magnifier == "1s" for spec in candidates)

    df_5m = load_5m_data(instrument.data_file)
    df_1m = load_1m_for_5m(instrument.data_file) if requires_1m else None
    df_1s = load_1s_for_5m(instrument.data_file) if requires_1s else None

    regime_calendar = build_extended_regime_calendar(df_5m)
    lookup = _regime_lookup(regime_calendar, "combined_regime")

    warm = regime_calendar[regime_calendar["warmup_ok"] == True].copy()
    if warm.empty:
        raise RuntimeError(f"{asset}: regime calendar never reaches warmup.")
    warm["_date_str"] = pd.to_datetime(warm["date"]).dt.strftime("%Y-%m-%d")
    first_warmup_date = str(warm["_date_str"].iloc[0])

    pre_dates = warm[warm["_date_str"] <= PRE_HOLDOUT_END]["_date_str"].tolist()
    holdout_dates = warm[
        (warm["_date_str"] >= HOLDOUT_START) & (warm["_date_str"] <= HOLDOUT_END)
    ]["_date_str"].tolist()

    return InstrumentBundle(
        asset=asset,
        df_5m=df_5m,
        df_1m=df_1m,
        df_1s=df_1s,
        regime_calendar=regime_calendar,
        regime_lookup=lookup,
        pre_dates=pre_dates,
        holdout_dates=holdout_dates,
        first_warmup_date=first_warmup_date,
    )


def validate_mapping(
    asset: str,
    candidate: CandidateSpec,
    trades: list[TradeResult],
    bundle: InstrumentBundle,
) -> None:
    missing = sorted(
        {
            t.date
            for t in _filled_trades(trades)
            if t.date >= bundle.first_warmup_date and t.date not in bundle.regime_lookup
        }
    )
    if missing:
        sample = ", ".join(missing[:5])
        raise RuntimeError(
            f"{asset} {candidate.candidate_name}: missing regime labels after warmup for {sample}"
        )


def delta(lhs: dict, rhs: dict, key: str, digits: int = 3) -> float | None:
    left = lhs.get(key)
    right = rhs.get(key)
    if left is None or right is None:
        return None
    return round(float(lhs[key]) - float(rhs[key]), digits)


def classify_recommendation(ungated_holdout: dict, gated_holdout: dict) -> str:
    ungated_r = float(ungated_holdout.get("net_r") or 0.0)
    gated_r = float(gated_holdout.get("net_r") or 0.0)
    ungated_cal = float(ungated_holdout.get("calmar") or 0.0)
    gated_cal = float(gated_holdout.get("calmar") or 0.0)
    ungated_dd = float(ungated_holdout.get("max_drawdown_r") or 0.0)
    gated_dd = float(gated_holdout.get("max_drawdown_r") or 0.0)

    calmar_delta = gated_cal - ungated_cal
    dd_improvement = gated_dd - ungated_dd

    if max(ungated_r, gated_r) <= 0.0 or max(ungated_cal, gated_cal) <= 0.0:
        return "no_edge"
    if calmar_delta >= 0.25 and dd_improvement >= 1.0 and gated_r >= 0.0:
        return "supports_gate"
    if calmar_delta <= -0.25 and ungated_r > 0.0:
        return "rejects_gate"
    return "mixed"


def run_candidate(
    candidate: CandidateSpec,
    bundle: InstrumentBundle,
    gate_fn: Callable[[list[TradeResult]], list[TradeResult]],
) -> dict:
    base_pre = run_backtest(
        bundle.df_5m,
        candidate.config,
        end_date=PRE_HOLDOUT_END,
        df_1m=bundle.df_1m,
        df_1s=bundle.df_1s,
    )
    base_pre = apply_post_trade_filters(base_pre, candidate)

    base_holdout = run_backtest(
        bundle.df_5m,
        candidate.config,
        start_date=HOLDOUT_START,
        end_date=HOLDOUT_END,
        df_1m=bundle.df_1m,
        df_1s=bundle.df_1s,
    )
    base_holdout = apply_post_trade_filters(base_holdout, candidate)

    validate_mapping(bundle.asset, candidate, base_pre, bundle)
    validate_mapping(bundle.asset, candidate, base_holdout, bundle)

    variants: dict[str, dict] = {}
    for gate_mode in ("ungated", "gated"):
        pre_trades = list(base_pre) if gate_mode == "ungated" else gate_fn(base_pre)
        holdout_trades = list(base_holdout) if gate_mode == "ungated" else gate_fn(base_holdout)

        pre_scorecard = simulate_prop_scorecard(candidate, pre_trades, bundle.pre_dates)
        holdout_scorecard = simulate_prop_scorecard(candidate, holdout_trades, bundle.holdout_dates)

        variants[gate_mode] = {
            "pre_holdout": metric_snapshot(pre_trades, pre_scorecard),
            "holdout": metric_snapshot(holdout_trades, holdout_scorecard),
        }

    ungated_holdout = variants["ungated"]["holdout"]
    gated_holdout = variants["gated"]["holdout"]
    gate_effect = {
        "holdout": {
            "delta_trades": delta(gated_holdout, ungated_holdout, "trades", digits=0),
            "delta_net_r": delta(gated_holdout, ungated_holdout, "net_r", digits=2),
            "delta_calmar": delta(gated_holdout, ungated_holdout, "calmar", digits=3),
            "delta_sharpe": delta(gated_holdout, ungated_holdout, "sharpe", digits=3),
            "delta_max_drawdown_r": delta(
                gated_holdout, ungated_holdout, "max_drawdown_r", digits=2
            ),
            "delta_payout_rate": delta(gated_holdout, ungated_holdout, "payout_rate", digits=4),
        }
    }

    recommendation = classify_recommendation(ungated_holdout, gated_holdout)

    return {
        "asset": candidate.asset,
        "candidate_id": candidate.candidate_id,
        "candidate_name": candidate.candidate_name,
        "session": candidate.session,
        "direction": candidate.direction,
        "preferred_gate_mode": candidate.preferred_gate_mode,
        "notes": candidate.notes,
        "config": {
            "strategy": candidate.config.strategy,
            "use_bar_magnifier": candidate.config.use_bar_magnifier,
            "risk_usd": candidate.config.risk_usd,
            "rr": candidate.config.rr,
            "tp1_ratio": candidate.config.tp1_ratio,
            "atr_length": candidate.config.atr_length,
            "stop_atr_pct": candidate.config.sessions[0].stop_atr_pct,
            "stop_orb_pct": candidate.config.sessions[0].stop_orb_pct,
            "min_gap_atr_pct": candidate.config.sessions[0].min_gap_atr_pct,
            "orb_start": candidate.config.sessions[0].orb_start,
            "orb_end": candidate.config.sessions[0].orb_end,
            "entry_start": candidate.config.sessions[0].entry_start,
            "entry_end": candidate.config.sessions[0].entry_end,
            "flat_start": candidate.config.sessions[0].flat_start,
            "flat_end": candidate.config.sessions[0].flat_end,
        },
        "variants": variants,
        "gate_effect": gate_effect,
        "recommendation": recommendation,
    }


def sort_key(result: dict) -> tuple[float, float]:
    gated = result["variants"]["gated"]["holdout"]
    ungated = result["variants"]["ungated"]["holdout"]
    best_calmar = max(float(gated.get("calmar") or 0.0), float(ungated.get("calmar") or 0.0))
    best_r = max(float(gated.get("net_r") or 0.0), float(ungated.get("net_r") or 0.0))
    return (best_calmar, best_r)


def build_memo(results: list[dict]) -> str:
    label_groups = {
        "supports_gate": [],
        "rejects_gate": [],
        "mixed": [],
        "no_edge": [],
    }
    for result in sorted(results, key=sort_key, reverse=True):
        label_groups[result["recommendation"]].append(result)

    lines = [
        "# Cross-Asset Regime-Gate Research Memo",
        "",
        "## Protocol",
        f"- Shared pre-holdout through {PRE_HOLDOUT_END}",
        f"- Shared holdout {HOLDOUT_START} to {HOLDOUT_END}",
        f"- Avoid buckets: {', '.join(sorted(AVOID_BUCKETS))}",
        "- Revised shortlist only; YM excluded by design",
        "",
        "## Headline",
        "- This memo compares whether the NQ-style medium-vol avoidance gate transfers to the revised cross-asset shortlist.",
        "- NQ remains the reference case because its 2026-04-01 regime-era pipeline already validated a gated Asia continuation winner; this script tests transferability, not whether NQ still needs a full dedicated pipeline.",
        "",
        "## Supports Gate",
    ]

    if label_groups["supports_gate"]:
        for result in label_groups["supports_gate"]:
            gated = result["variants"]["gated"]["holdout"]
            ungated = result["variants"]["ungated"]["holdout"]
            delta_cal = result["gate_effect"]["holdout"]["delta_calmar"]
            delta_dd = result["gate_effect"]["holdout"]["delta_max_drawdown_r"]
            lines.append(
                f"- {result['asset']} {result['candidate_name']}: gated holdout Calmar {gated['calmar']} vs {ungated['calmar']}, "
                f"DD delta {delta_dd}R, net R {gated['net_r']} vs {ungated['net_r']}."
            )
    else:
        lines.append("- No candidate met the support threshold in this first pass.")

    lines.extend(["", "## Rejects Gate"])
    if label_groups["rejects_gate"]:
        for result in label_groups["rejects_gate"]:
            gated = result["variants"]["gated"]["holdout"]
            ungated = result["variants"]["ungated"]["holdout"]
            lines.append(
                f"- {result['asset']} {result['candidate_name']}: ungated holdout Calmar {ungated['calmar']} vs gated {gated['calmar']}, "
                f"net R {ungated['net_r']} vs {gated['net_r']}."
            )
    else:
        lines.append("- No candidate clearly rejected the gate.")

    lines.extend(["", "## Mixed Or Weak"])
    mixed_weak = label_groups["mixed"] + label_groups["no_edge"]
    if mixed_weak:
        for result in mixed_weak:
            gated = result["variants"]["gated"]["holdout"]
            ungated = result["variants"]["ungated"]["holdout"]
            lines.append(
                f"- {result['asset']} {result['candidate_name']} ({result['recommendation']}): "
                f"ungated Calmar {ungated['calmar']}, gated Calmar {gated['calmar']}, "
                f"ungated net R {ungated['net_r']}, gated net R {gated['net_r']}."
            )
    else:
        lines.append("- None.")

    second_round = [
        result
        for result in sorted(results, key=sort_key, reverse=True)
        if result["recommendation"] in {"supports_gate", "mixed"}
        and max(
            float(result["variants"]["ungated"]["holdout"].get("net_r") or 0.0),
            float(result["variants"]["gated"]["holdout"].get("net_r") or 0.0),
        )
        > 0.0
    ]

    lines.extend(["", "## Second-Round Expansion Candidates"])
    if second_round:
        for result in second_round:
            preferred = result["preferred_gate_mode"]
            lines.append(
                f"- {result['asset']} {result['candidate_name']} ({result['recommendation']}), preferred baseline {preferred}."
            )
    else:
        lines.append("- No candidate cleared the threshold for expansion.")

    lines.extend(
        [
            "",
            "## Exclusions",
            "- YM was excluded from this phase because the latest learnings treat it as structurally non-deployable and selection-bias-sensitive.",
        ]
    )

    return "\n".join(lines) + "\n"


def main() -> None:
    print("Cross-Asset Regime-Gate Research — Revised Shortlist")
    print("=" * 72)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    candidates = build_candidates()
    by_asset: dict[str, list[CandidateSpec]] = {}
    for candidate in candidates:
        by_asset.setdefault(candidate.asset, []).append(candidate)

    bundles: dict[str, InstrumentBundle] = {}
    for asset, asset_candidates in by_asset.items():
        print(f"\nLoading {asset} data and regime calendar...", flush=True)
        bundle = bundle_for_asset(asset, asset_candidates)
        bundles[asset] = bundle
        print(
            f"  5m bars={len(bundle.df_5m):,}"
            f" | 1m={'yes' if bundle.df_1m is not None else 'no'}"
            f" | 1s={'yes' if bundle.df_1s is not None else 'no'}"
            f" | first_warmup={bundle.first_warmup_date}"
        )

    all_results: list[dict] = []
    for asset in sorted(by_asset):
        bundle = bundles[asset]
        gate_fn = make_avoidance_gate(bundle.regime_calendar)
        print(f"\n{'=' * 72}")
        print(f"{asset} Candidates")
        print(f"{'=' * 72}")
        for candidate in by_asset[asset]:
            print(f"\nRunning {candidate.asset} {candidate.candidate_name}...", flush=True)
            candidate_t0 = time.time()
            result = run_candidate(candidate, bundle, gate_fn)
            all_results.append(result)
            gated = result["variants"]["gated"]["holdout"]
            ungated = result["variants"]["ungated"]["holdout"]
            print(
                f"  Holdout ungated: R {ungated['net_r']:+.2f} | Cal {ungated['calmar'] or 0:.3f} | DD {ungated['max_drawdown_r']:+.2f}"
            )
            print(
                f"  Holdout gated:   R {gated['net_r']:+.2f} | Cal {gated['calmar'] or 0:.3f} | DD {gated['max_drawdown_r']:+.2f}"
            )
            print(
                f"  Recommendation: {result['recommendation']} [{time.time() - candidate_t0:.1f}s]"
            )

    payload = {
        "protocol": {
            "pre_holdout_end": PRE_HOLDOUT_END,
            "holdout_start": HOLDOUT_START,
            "holdout_end": HOLDOUT_END,
            "avoid_buckets": sorted(AVOID_BUCKETS),
            "profile": "revised_shortlist_only",
        },
        "excluded_assets": [
            {
                "asset": "YM",
                "reason": "Excluded by design; latest learnings say the edge is too thin or overfit.",
            }
        ],
        "results": sorted(all_results, key=sort_key, reverse=True),
    }

    memo = build_memo(payload["results"])
    json_path = OUTPUT_DIR / "regime_gate_results.json"
    memo_path = OUTPUT_DIR / "regime_gate_memo.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=str))
    memo_path.write_text(memo)

    print(f"\nSaved JSON: {json_path}")
    print(f"Saved memo: {memo_path}")
    print(f"Elapsed: {time.time() - t0:.1f}s")


if __name__ == "__main__":
    main()
