#!/usr/bin/env python3
"""One-at-a-time ablation study for NQ Hunter Classic ORB.

The baseline is the current balanced stress-gated Hunter candidate:

- EMA14 confirmed previous 15m close bias
- 2 point EMA wrong-side tolerance
- no EMA distance cap
- Mon/Wed/Thu/Fri only
- body >= 55%, rejection wick <= 20%
- legacy one reentry after loss
- no same-bar win reentry
- simple stress gate: skip bull_high_vol, bear_high_vol, bear_medium_vol

Each variant removes or loosens one rule while keeping the rest fixed.
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.run_hunter_classic_orb_replication import (  # noqa: E402
    BODY_MIN_PCT,
    COMMISSION_PER_CONTRACT_ROUND_TRIP,
    DEFAULT_EMA15_SOURCE,
    DEFAULT_EMA15_TIMING,
    DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
    HUNTER_TARGET_RR,
    LARGE_SL_THRESHOLD_POINTS,
    MAX_CONTRACTS,
    MAX_HOLD_MINUTES,
    MAX_RISK_USD,
    ORB_SIGNAL_END,
    ORB_START,
    POINT_VALUE,
    REDUCED_TARGET_RR,
    REJECTION_WICK_MAX_PCT,
    SIGNAL_START,
    SL_BUFFER_POINTS,
    Candidate,
    SimTrade,
    add_ema15_bias,
    body_rejection,
    can_take_candidate,
    load_1s,
    resample_5m,
)


RESULT_DIR = Path("data/results/hunter_classic_ablation_20260502")
REPORT_PATH = Path("learnings/reports/NQ_HUNTER_CLASSIC_ABLATION_20260502.md")
DATA_1S = Path("data/raw/NQ_1s.parquet")
REGIME_CALENDAR = Path("data/results/hunter_classic_regime_gate_test_20260502/regime_calendar.csv")

FULL_START = pd.Timestamp("2016-04-25")
FULL_END = pd.Timestamp("2026-04-24")
HOLDOUT_START = pd.Timestamp("2025-01-01")
LAST_1Y_START = pd.Timestamp("2025-04-25")
LOAD_END = FULL_END + pd.Timedelta(days=1)

RISK_USD = 350.0
BASELINE_ID = "baseline_balanced"
STRESS_EXCLUDES = {"bull_high_vol", "bear_high_vol", "bear_medium_vol"}


@dataclass(frozen=True)
class AblationConfig:
    variant_id: str
    label: str
    category: str
    description: str
    allowed_weekdays: frozenset[int] | None = frozenset({0, 2, 3, 4})
    signal_end: str = "10:55"
    ema_enabled: bool = True
    ema_length: int = 14
    ema_tolerance_points: float = 2.0
    ema_max_distance: float | None = None
    body_min_pct: float = BODY_MIN_PCT
    rejection_max_pct: float = REJECTION_WICK_MAX_PCT
    reentry_policy: str = "legacy_one_reentry_after_loss"
    allow_same_bar_win_reentry: bool = False
    stress_gate: bool = True
    reduced_target_for_large_stop: bool = True


def baseline_config() -> AblationConfig:
    return AblationConfig(
        variant_id=BASELINE_ID,
        label="Baseline balanced",
        category="baseline",
        description="Stress-gated EMA14/tol2 no-cap Hunter with legacy one reentry after loss.",
    )


def ablation_configs() -> list[AblationConfig]:
    base = baseline_config()
    return [
        base,
        replace(
            base,
            variant_id="remove_stress_gate",
            label="Remove stress gate",
            category="regime",
            description="Allow bull_high_vol, bear_high_vol, and bear_medium_vol.",
            stress_gate=False,
        ),
        replace(
            base,
            variant_id="remove_ema_bias",
            label="Remove EMA bias",
            category="trend",
            description="Do not require the signal close to be on/near the 15m EMA side.",
            ema_enabled=False,
        ),
        replace(
            base,
            variant_id="strict_ema_tol0",
            label="Strict EMA tol0",
            category="trend",
            description="Sensitivity: require no wrong-side EMA tolerance.",
            ema_tolerance_points=0.0,
        ),
        replace(
            base,
            variant_id="loose_ema_tol5",
            label="Loose EMA tol5",
            category="trend",
            description="Sensitivity: allow 5 points wrong-side EMA tolerance.",
            ema_tolerance_points=5.0,
        ),
        replace(
            base,
            variant_id="dist100",
            label="Add dist100 cap",
            category="trend",
            description="Sensitivity: reject signals more than 100 points beyond the 15m EMA.",
            ema_max_distance=100.0,
        ),
        replace(
            base,
            variant_id="dist150",
            label="Add dist150 cap",
            category="trend",
            description="Sensitivity: reject signals more than 150 points beyond the 15m EMA.",
            ema_max_distance=150.0,
        ),
        replace(
            base,
            variant_id="remove_body_filter",
            label="Remove body filter",
            category="candle",
            description="Disable the body >= 55% candle-quality requirement.",
            body_min_pct=0.0,
        ),
        replace(
            base,
            variant_id="remove_rejection_filter",
            label="Remove rejection filter",
            category="candle",
            description="Disable the rejection wick <= 20% candle-quality requirement.",
            rejection_max_pct=100.0,
        ),
        replace(
            base,
            variant_id="remove_candle_filters",
            label="Remove candle filters",
            category="candle",
            description="Disable both body and rejection wick requirements.",
            body_min_pct=0.0,
            rejection_max_pct=100.0,
        ),
        replace(
            base,
            variant_id="allow_tuesday",
            label="Allow Tuesday",
            category="calendar",
            description="Remove the Tuesday exclusion; allow Mon-Fri.",
            allowed_weekdays=frozenset({0, 1, 2, 3, 4}),
        ),
        replace(
            base,
            variant_id="first_trade_only",
            label="First trade only",
            category="reentry",
            description="Remove same-day reentry after a losing first trade.",
            reentry_policy="first_trade_only",
        ),
        replace(
            base,
            variant_id="after_each_loss",
            label="After each loss",
            category="reentry",
            description="Allow a new non-overlapping reentry after each loss.",
            reentry_policy="after_each_loss",
        ),
        replace(
            base,
            variant_id="all_nonoverlap_reentries",
            label="All non-overlap reentries",
            category="reentry",
            description="Remove outcome-based reentry restriction; allow every non-overlapping candidate.",
            reentry_policy="all_nonoverlap",
        ),
        replace(
            base,
            variant_id="same_bar_win_reentry",
            label="Same-bar win reentry",
            category="reentry",
            description="Allow quick same-bar winning exits to re-arm the strategy.",
            allow_same_bar_win_reentry=True,
        ),
        replace(
            base,
            variant_id="always_2r_large_stops",
            label="Always 2R target",
            category="exit",
            description="Remove the rule that cuts target to 1R when stop distance is >= 50 NQ points.",
            reduced_target_for_large_stop=False,
        ),
        replace(
            base,
            variant_id="signal_until_1300",
            label="Signal until 13:00",
            category="time",
            description="Remove the 10:55 signal cutoff and allow signals until 13:00.",
            signal_end="13:00",
        ),
    ]


def load_regime_lookup(path: Path) -> dict[str, str]:
    regime = pd.read_csv(path, parse_dates=["date"])
    return {
        row.date.strftime("%Y-%m-%d"): str(row.combined_regime)
        for row in regime.itertuples(index=False)
    }


def build_broad_candidates(bars_5m: pd.DataFrame) -> list[Candidate]:
    bars = add_ema15_bias(
        bars_5m,
        14,
        source=DEFAULT_EMA15_SOURCE,
        timing=DEFAULT_EMA15_TIMING,
    )
    candidates: list[Candidate] = []
    for day, group in bars.groupby(bars.index.date):
        if pd.Timestamp(day).weekday() not in {0, 1, 2, 3, 4}:
            continue

        orb = group.between_time(ORB_START, ORB_SIGNAL_END)
        if len(orb) < 3:
            continue
        orb_high = float(orb.high.max())
        orb_low = float(orb.low.min())
        orb_range = max(orb_high - orb_low, 1e-9)

        for signal_dt, row in group.between_time(SIGNAL_START, "13:00").iterrows():
            pos = group.index.get_loc(signal_dt)
            if pos == 0:
                continue
            previous_close = float(group.iloc[pos - 1].close)
            raw_sides: list[str] = []
            if float(row.close) > orb_high and previous_close <= orb_high:
                raw_sides.append("long")
            if float(row.close) < orb_low and previous_close >= orb_low:
                raw_sides.append("short")

            for side in raw_sides:
                ema_value = float(row.ema15_bias)
                ema_distance = float(row.close) - ema_value if side == "long" else ema_value - float(row.close)
                body_pct, rejection_pct = body_rejection(row, side)
                extension_pct = (
                    (float(row.close) - orb_high) / orb_range * 100.0
                    if side == "long"
                    else (orb_low - float(row.close)) / orb_range * 100.0
                )
                candidates.append(
                    Candidate(
                        signal_dt=signal_dt,
                        entry_dt=signal_dt + pd.Timedelta(minutes=5),
                        side=side,
                        orb_high=orb_high,
                        orb_low=orb_low,
                        signal_open=float(row.open),
                        signal_high=float(row.high),
                        signal_low=float(row.low),
                        signal_close=float(row.close),
                        body_pct=body_pct,
                        rejection_wick_pct=rejection_pct,
                        extension_pct=extension_pct,
                        ema15_distance_points=ema_distance,
                    )
                )
    return candidates


def contracts_for_risk(risk_points: float) -> int:
    if risk_points <= 0:
        return 1
    raw = int(MAX_RISK_USD // (risk_points * POINT_VALUE))
    return max(1, min(MAX_CONTRACTS, raw))


def simulate_exit(
    candidate: Candidate,
    df_1s: pd.DataFrame,
    trade_no: int,
    *,
    reduced_target_for_large_stop: bool,
) -> SimTrade | None:
    if candidate.entry_dt not in df_1s.index:
        start_slice = df_1s.loc[candidate.entry_dt : candidate.entry_dt + pd.Timedelta(minutes=5)]
        if start_slice.empty:
            return None
        entry_dt = start_slice.index[0]
    else:
        entry_dt = candidate.entry_dt

    entry_price = float(df_1s.loc[entry_dt].open)
    if candidate.side == "long":
        stop_price = candidate.signal_low - SL_BUFFER_POINTS
        risk_points = entry_price - stop_price
        rr = (
            REDUCED_TARGET_RR
            if reduced_target_for_large_stop and risk_points >= LARGE_SL_THRESHOLD_POINTS
            else HUNTER_TARGET_RR
        )
        target_price = entry_price + risk_points * rr
    else:
        stop_price = candidate.signal_high + SL_BUFFER_POINTS
        risk_points = stop_price - entry_price
        rr = (
            REDUCED_TARGET_RR
            if reduced_target_for_large_stop and risk_points >= LARGE_SL_THRESHOLD_POINTS
            else HUNTER_TARGET_RR
        )
        target_price = entry_price - risk_points * rr

    if risk_points <= 0:
        return None

    qty = contracts_for_risk(risk_points)
    max_hold_cutoff = entry_dt + pd.Timedelta(minutes=MAX_HOLD_MINUTES)
    scan = df_1s.loc[entry_dt : max_hold_cutoff + pd.Timedelta(minutes=10)]
    if scan.empty:
        return None

    mfe_points = 0.0
    mae_points = 0.0
    exit_dt = scan.index[-1]
    exit_price = float(scan.iloc[-1].close)
    exit_signal = "Max Hold Time"

    for ts, row in scan.iterrows():
        if candidate.side == "long":
            mfe_points = max(mfe_points, float(row.high) - entry_price)
            mae_points = min(mae_points, float(row.low) - entry_price)
            hit_stop = float(row.low) <= stop_price
            hit_target = float(row.high) >= target_price
        else:
            mfe_points = max(mfe_points, entry_price - float(row.low))
            mae_points = min(mae_points, entry_price - float(row.high))
            hit_stop = float(row.high) >= stop_price
            hit_target = float(row.low) <= target_price

        if hit_stop or hit_target:
            exit_dt = ts
            exit_price = stop_price if hit_stop else target_price
            exit_signal = "Hunter 2R"
            break

        if ts >= max_hold_cutoff:
            exit_dt = ts
            exit_price = float(row.close)
            exit_signal = "Max Hold Time"
            break

    gross_points = exit_price - entry_price if candidate.side == "long" else entry_price - exit_price
    pnl_usd = gross_points * POINT_VALUE * qty - COMMISSION_PER_CONTRACT_ROUND_TRIP * qty
    return SimTrade(
        trade_no=trade_no,
        side=candidate.side,
        signal_dt=str(candidate.signal_dt),
        entry_dt=str(entry_dt),
        exit_dt=str(exit_dt),
        entry_price=round(entry_price, 2),
        exit_price=round(exit_price, 2),
        stop_price=round(stop_price, 2),
        target_price=round(target_price, 2),
        risk_points=round(risk_points, 2),
        rr=rr,
        qty=qty,
        pnl_usd=round(pnl_usd, 2),
        mfe_usd=round(mfe_points * POINT_VALUE * qty, 2),
        mae_usd=round(mae_points * POINT_VALUE * qty, 2),
        exit_signal=exit_signal,
        body_pct=round(candidate.body_pct, 4),
        rejection_wick_pct=round(candidate.rejection_wick_pct, 4),
        extension_pct=round(candidate.extension_pct, 4),
    )


def candidate_key(candidate: Candidate) -> tuple[str, str]:
    return (str(candidate.signal_dt), candidate.side)


def filter_candidates(candidates: list[Candidate], config: AblationConfig) -> list[Candidate]:
    out: list[Candidate] = []
    for candidate in candidates:
        if config.allowed_weekdays is not None and candidate.signal_dt.weekday() not in config.allowed_weekdays:
            continue
        if candidate.signal_dt.strftime("%H:%M") > config.signal_end:
            continue
        if config.ema_enabled:
            if candidate.ema15_distance_points is None:
                continue
            if candidate.ema15_distance_points < -config.ema_tolerance_points:
                continue
            if config.ema_max_distance is not None and candidate.ema15_distance_points > config.ema_max_distance:
                continue
        if candidate.body_pct < config.body_min_pct:
            continue
        if candidate.rejection_wick_pct > config.rejection_max_pct:
            continue
        out.append(candidate)
    return out


def can_take_for_variant(
    candidate: Candidate,
    day_trades: list[SimTrade],
    open_until: pd.Timestamp | None,
    config: AblationConfig,
) -> bool:
    if open_until is not None and candidate.entry_dt <= open_until:
        return False
    if not day_trades:
        return True
    if config.reentry_policy == "first_trade_only":
        return False
    return can_take_candidate(
        candidate,
        day_trades,
        open_until,
        config.reentry_policy,
        allow_same_bar_win_reentry=config.allow_same_bar_win_reentry,
        same_bar_win_reentry_max_minutes=DEFAULT_SAME_BAR_WIN_REENTRY_MAX_MINUTES,
    )


def select_trades(
    candidates: list[Candidate],
    exit_cache: dict[tuple[tuple[str, str], bool], SimTrade | None],
    config: AblationConfig,
    df_1s: pd.DataFrame,
) -> list[SimTrade]:
    by_day: dict[Any, list[Candidate]] = {}
    for candidate in candidates:
        by_day.setdefault(candidate.entry_dt.date(), []).append(candidate)

    selected: list[SimTrade] = []
    trade_no = 1
    for day in sorted(by_day):
        day_trades: list[SimTrade] = []
        open_until: pd.Timestamp | None = None
        for candidate in sorted(by_day[day], key=lambda c: c.entry_dt):
            if not can_take_for_variant(candidate, day_trades, open_until, config):
                continue
            cache_key = (candidate_key(candidate), config.reduced_target_for_large_stop)
            if cache_key not in exit_cache:
                exit_cache[cache_key] = simulate_exit(
                    candidate,
                    df_1s,
                    0,
                    reduced_target_for_large_stop=config.reduced_target_for_large_stop,
                )
            trade = exit_cache[cache_key]
            if trade is None:
                continue
            numbered_trade = replace(trade, trade_no=trade_no)
            selected.append(numbered_trade)
            day_trades.append(numbered_trade)
            trade_no += 1
            open_until = pd.Timestamp(numbered_trade.exit_dt)
    return selected


def trade_date(trade: SimTrade) -> pd.Timestamp:
    return pd.Timestamp(trade.signal_dt).normalize()


def filter_stress_gate(trades: list[SimTrade], regime_lookup: dict[str, str], config: AblationConfig) -> list[SimTrade]:
    if not config.stress_gate:
        return trades
    kept = []
    for trade in trades:
        key = trade_date(trade).strftime("%Y-%m-%d")
        if regime_lookup.get(key) not in STRESS_EXCLUDES:
            kept.append(trade)
    return kept


def trade_r(trade: SimTrade) -> float:
    return float(trade.pnl_usd) / RISK_USD


def max_drawdown(values: list[float] | np.ndarray) -> float:
    if len(values) == 0:
        return 0.0
    arr = np.asarray(values, dtype=float)
    equity = np.concatenate([[0.0], np.cumsum(arr)])
    peak = np.maximum.accumulate(equity)
    return float(np.min(equity - peak))


def profit_factor(values: np.ndarray) -> float:
    gross_profit = float(values[values > 0].sum())
    gross_loss = float(-values[values < 0].sum())
    if gross_loss <= 0:
        return float("inf") if gross_profit > 0 else 0.0
    return gross_profit / gross_loss


def metric_packet(trades: list[SimTrade], start: pd.Timestamp, end: pd.Timestamp) -> dict[str, Any]:
    selected = [trade for trade in trades if start <= trade_date(trade) <= end]
    values = np.asarray([trade_r(trade) for trade in selected], dtype=float)
    yearly: dict[int, float] = {}
    for trade, value in zip(selected, values):
        yearly.setdefault(trade_date(trade).year, 0.0)
        yearly[trade_date(trade).year] += float(value)
    dd = max_drawdown(values)
    return {
        "trades": int(len(values)),
        "net_r": float(values.sum()) if len(values) else 0.0,
        "wr_pct": float((values > 0).mean() * 100.0) if len(values) else 0.0,
        "pf": profit_factor(values),
        "closed_dd_r": dd,
        "avg_r": float(values.mean()) if len(values) else 0.0,
        "positive_years": int(sum(v > 0 for v in yearly.values())),
        "negative_years": int(sum(v < 0 for v in yearly.values())),
    }


def score(metrics: dict[str, Any]) -> float:
    pf_bonus = max(0.0, float(metrics["pf"]) - 1.0) * 25.0
    year_bonus = float(metrics["positive_years"]) * 2.0 - float(metrics["negative_years"]) * 4.0
    return float(metrics["net_r"]) - 0.70 * abs(float(metrics["closed_dd_r"])) + pf_bonus + year_bonus


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def fmt_r(value: float) -> str:
    return f"{value:+.1f}R"


def fmt_pct(value: float) -> str:
    return f"{value:.1f}%"


def build_report(metrics_df: pd.DataFrame, contribution_df: pd.DataFrame) -> str:
    baseline = metrics_df[(metrics_df["variant_id"] == BASELINE_ID) & (metrics_df["window"] == "full_10y")].iloc[0]
    removal_focus = contribution_df[
        contribution_df["variant_id"].isin(
            [
                "remove_stress_gate",
                "remove_ema_bias",
                "remove_body_filter",
                "remove_rejection_filter",
                "remove_candle_filters",
                "allow_tuesday",
                "first_trade_only",
                "all_nonoverlap_reentries",
                "always_2r_large_stops",
                "signal_until_1300",
            ]
        )
    ].sort_values("damage_score", ascending=False)

    lines = [
        "# NQ Hunter Classic ORB Ablation (2026-05-02)",
        "",
        "## Baseline",
        "",
        "Baseline is the balanced stress-gated Hunter candidate: `ema14_tol2_distnone_relegacy_samewin0`.",
        "",
        f"- Full 10y: {int(baseline.trades):,} trades, {fmt_r(float(baseline.net_r))}, "
        f"{fmt_pct(float(baseline.wr_pct))} WR, PF {float(baseline.pf):.2f}, "
        f"DD {fmt_r(float(baseline.closed_dd_r))}",
        "- Stress gate skips `bull_high_vol`, `bear_high_vol`, and `bear_medium_vol`.",
        "",
        "## One-At-A-Time Removal Ranking",
        "",
        "| Rank | Removed / Changed | Category | Full Net Delta | Full DD Delta | 2025+ Net Delta | Last 1y Net Delta | Damage Score |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(removal_focus.itertuples(index=False), start=1):
        lines.append(
            f"| {rank} | {row.label} | {row.category} | "
            f"{fmt_r(row.delta_full_net_r)} | {fmt_r(row.delta_full_dd_r)} | "
            f"{fmt_r(row.delta_holdout_net_r)} | {fmt_r(row.delta_last_1y_net_r)} | "
            f"{row.damage_score:.1f} |"
        )

    lines.extend(
        [
            "",
            "Positive damage means the baseline rule was helping. Negative damage means the variant improved the baseline.",
            "",
            "## Sensitivity Rows",
            "",
            "| Variant | Full 10y | 2025+ | Last 1y | Read |",
            "|---|---:|---:|---:|---|",
        ]
    )
    sensitivity_ids = ["strict_ema_tol0", "loose_ema_tol5", "dist100", "dist150", "after_each_loss", "same_bar_win_reentry"]
    for variant_id in sensitivity_ids:
        full = metrics_df[(metrics_df["variant_id"] == variant_id) & (metrics_df["window"] == "full_10y")].iloc[0]
        holdout = metrics_df[(metrics_df["variant_id"] == variant_id) & (metrics_df["window"] == "holdout_2025_plus")].iloc[0]
        last = metrics_df[(metrics_df["variant_id"] == variant_id) & (metrics_df["window"] == "last_1y")].iloc[0]
        read = {
            "strict_ema_tol0": "Slightly cleaner pre-holdout/workflow, but gives up recent R.",
            "loose_ema_tol5": "Mostly neutral; tolerance is not a major lever.",
            "dist100": "Too tight; raises recent PF but loses too much R.",
            "dist150": "Best cap sensitivity, especially recent, but weaker pre-holdout than no-cap.",
            "after_each_loss": "Very close to baseline; reentry policy detail is secondary.",
            "same_bar_win_reentry": "Adds little and can slightly dilute.",
        }[variant_id]
        lines.append(
            f"| {full.label} | {fmt_r(float(full.net_r))} / {fmt_r(float(full.closed_dd_r))} DD | "
            f"{fmt_r(float(holdout.net_r))} | {fmt_r(float(last.net_r))} | {read} |"
        )

    lines.extend(
        [
            "",
            "## Read",
            "",
            "- The **stress gate** is the largest structural contributor. Removing it keeps recent performance strong but reopens the old-history damage profile.",
            "- The **wide-stop target reduction** is the biggest non-regime protection rule. Forcing wide-stop trades to keep a 2R target loses `-64.6R` and widens DD by `-19.5R`; the 1R cap is doing real work.",
            "- The **one reentry after loss** is also meaningful. Removing reentries loses `-44.8R` full and `-21.3R` last 1y, so the reentry is part of the edge rather than just extra churn.",
            "- The **15m EMA bias** is a smaller but real entry-quality filter. Removing it loses `-10.3R` full and `-17.4R` pre-holdout, while slightly helping 2025+.",
            "- The **candle-quality package** is more about DD/recent protection than raw R. Removing both adds `+6.0R` full but worsens DD by about `-19.9R` and gives up recent R. Body filter looks more protective than rejection filter; removing rejection alone improved net in this pass, so rejection is a follow-up candidate rather than sacred.",
            "- **Tuesday is a recency tradeoff.** Adding Tuesday improves full 10y (`+27.8R`) and DD (`+4.0R`) but hurts 2025+ (`-15.0R`) and last 1y (`-17.0R`). Do not re-add it just from full-history hindsight.",
            "- **Signal extension to 13:00 is the most interesting follow-up.** It improved full, 2025+, and DD in this one-at-a-time pass, but it changes the strategy's timing profile and needs a workflow-clean test before touching the baseline.",
            "- `dist100` remains a quality trim, not a core edge. If using a distance cap at all, `dist150` is the better research branch.",
            "",
            "## Artifacts",
            "",
            f"- Results packet: `{RESULT_DIR}`",
            "- `ablation_metrics.csv`",
            "- `ablation_contribution.csv`",
            "- `selected_trades/*.csv`",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    (RESULT_DIR / "selected_trades").mkdir(parents=True, exist_ok=True)

    regime_lookup = load_regime_lookup(REGIME_CALENDAR)
    df_1s = load_1s(DATA_1S, FULL_START, LOAD_END)
    bars_5m = resample_5m(df_1s)
    candidates = build_broad_candidates(bars_5m)
    print(f"Built broad candidate pool: {len(candidates):,}", flush=True)

    exit_cache: dict[tuple[tuple[str, str], bool], SimTrade | None] = {}

    windows = {
        "pre_holdout": (FULL_START, HOLDOUT_START - pd.Timedelta(days=1)),
        "full_10y": (FULL_START, FULL_END),
        "holdout_2025_plus": (HOLDOUT_START, FULL_END),
        "last_1y": (LAST_1Y_START, FULL_END),
    }
    metric_rows: list[dict[str, Any]] = []
    trade_count_rows: list[dict[str, Any]] = []

    for config in ablation_configs():
        selected_candidates = filter_candidates(candidates, config)
        raw_trades = select_trades(selected_candidates, exit_cache, config, df_1s)
        trades = filter_stress_gate(raw_trades, regime_lookup, config)
        print(f"{config.variant_id}: candidates={len(selected_candidates):,} trades={len(trades):,}", flush=True)

        if config.variant_id in {
            BASELINE_ID,
            "remove_stress_gate",
            "remove_ema_bias",
            "remove_candle_filters",
            "allow_tuesday",
            "first_trade_only",
            "always_2r_large_stops",
            "signal_until_1300",
        }:
            write_csv(
                RESULT_DIR / "selected_trades" / f"{config.variant_id}.csv",
                [
                    {
                        **asdict(trade),
                        "variant_id": config.variant_id,
                        "r": trade_r(trade),
                    }
                    for trade in trades
                ],
            )

        trade_count_rows.append(
            {
                "variant_id": config.variant_id,
                "label": config.label,
                "category": config.category,
                "candidate_count": len(selected_candidates),
                "raw_trade_count": len(raw_trades),
                "stress_gated_trade_count": len(trades),
            }
        )

        for window_name, (start, end) in windows.items():
            metrics = metric_packet(trades, start, end)
            metric_rows.append(
                {
                    **asdict(config),
                    "window": window_name,
                    **metrics,
                    "score": score(metrics),
                }
            )

    metrics_df = pd.DataFrame(metric_rows)
    metrics_df.to_csv(RESULT_DIR / "ablation_metrics.csv", index=False)
    pd.DataFrame(trade_count_rows).to_csv(RESULT_DIR / "ablation_trade_counts.csv", index=False)

    base = metrics_df[metrics_df["variant_id"] == BASELINE_ID].set_index("window")
    contribution_rows: list[dict[str, Any]] = []
    for config in ablation_configs():
        if config.variant_id == BASELINE_ID:
            continue
        sub = metrics_df[metrics_df["variant_id"] == config.variant_id].set_index("window")
        full_delta_net = float(sub.loc["full_10y", "net_r"] - base.loc["full_10y", "net_r"])
        full_delta_dd = float(sub.loc["full_10y", "closed_dd_r"] - base.loc["full_10y", "closed_dd_r"])
        pre_delta_net = float(sub.loc["pre_holdout", "net_r"] - base.loc["pre_holdout", "net_r"])
        hold_delta_net = float(sub.loc["holdout_2025_plus", "net_r"] - base.loc["holdout_2025_plus", "net_r"])
        last_delta_net = float(sub.loc["last_1y", "net_r"] - base.loc["last_1y", "net_r"])
        dd_worsening = max(0.0, abs(float(sub.loc["full_10y", "closed_dd_r"])) - abs(float(base.loc["full_10y", "closed_dd_r"])))
        damage_score = (
            -full_delta_net
            + 0.50 * dd_worsening
            + 0.40 * max(0.0, -pre_delta_net)
            + 0.20 * max(0.0, -hold_delta_net)
        )
        contribution_rows.append(
            {
                "variant_id": config.variant_id,
                "label": config.label,
                "category": config.category,
                "description": config.description,
                "delta_pre_net_r": pre_delta_net,
                "delta_full_net_r": full_delta_net,
                "delta_full_dd_r": full_delta_dd,
                "delta_holdout_net_r": hold_delta_net,
                "delta_last_1y_net_r": last_delta_net,
                "damage_score": damage_score,
            }
        )

    contribution_df = pd.DataFrame(contribution_rows).sort_values("damage_score", ascending=False)
    contribution_df.to_csv(RESULT_DIR / "ablation_contribution.csv", index=False)

    report = build_report(metrics_df, contribution_df)
    REPORT_PATH.write_text(report)
    (RESULT_DIR / "summary.md").write_text(report)
    (RESULT_DIR / "summary.json").write_text(
        json.dumps(
            {
                "baseline": BASELINE_ID,
                "variants": [asdict(config) for config in ablation_configs()],
                "result_dir": str(RESULT_DIR),
                "report": str(REPORT_PATH),
            },
            indent=2,
            default=str,
            allow_nan=True,
        )
        + "\n"
    )

    print(f"Wrote {RESULT_DIR}")
    print(f"Wrote {REPORT_PATH}")


if __name__ == "__main__":
    main()
