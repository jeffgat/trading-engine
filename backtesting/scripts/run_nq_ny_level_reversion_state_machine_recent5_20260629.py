#!/usr/bin/env python3
"""Recent 5-year NQ NY level mean-reversion state-machine pass.

Second pass after the immediate-consolidation prototype:
extension first -> consolidation forms -> sweep/reclaim -> target mean.
Research artifact only; not wired to live execution.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402


RUN_SLUG = "nq_ny_level_reversion_state_machine_recent5_20260629"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LEVEL_REVERSION_STATE_MACHINE_RECENT5_20260629.md"

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
ENTRY_START = "09:45"
ENTRY_END = "15:00"
FLAT_TIME = "15:55"


@dataclass(frozen=True)
class PreparedDay:
    date: str
    timestamps: list[pd.Timestamp]
    times: list[str]
    opens: np.ndarray
    highs: np.ndarray
    lows: np.ndarray
    closes: np.ndarray
    vwap: np.ndarray
    day_mid: np.ndarray
    ib_mid_30: float
    atr: float


@dataclass(frozen=True)
class StateMachineConfig:
    mean_mode: str
    extension_atr_pct: float
    consolidation_bars: int
    consolidation_atr_pct: float
    setup_timeout_bars: int
    stop_buffer_atr_pct: float
    min_rr_to_mean: float
    cooldown_bars: int = 2
    max_trades_per_day: int = 3


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    return value


def _time_str(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


def _prepare_rth(df: pd.DataFrame) -> pd.DataFrame:
    rth = df.between_time("09:30", "16:00").copy()
    rth["date"] = rth.index.date.astype(str)
    typical = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    rth["_tpv"] = typical * rth["volume"].astype(float)
    grouped = rth.groupby("date", sort=True)
    rth["session_vwap"] = grouped["_tpv"].cumsum() / grouped["volume"].cumsum().replace(0, np.nan)

    daily = grouped.agg({"high": "max", "low": "min"})
    daily["range"] = daily["high"] - daily["low"]
    daily["atr14_prev"] = daily["range"].rolling(14, min_periods=5).mean().shift(1)
    fallback = float(daily["range"].median())
    rth["atr14_prev"] = rth["date"].map(daily["atr14_prev"]).fillna(fallback)
    return rth.drop(columns=["_tpv"])


def _prepare_days(rth: pd.DataFrame) -> list[PreparedDay]:
    days: list[PreparedDay] = []
    for date, day in rth.groupby("date", sort=True):
        timestamps = list(day.index)
        times = [_time_str(ts) for ts in timestamps]
        opens = day["open"].to_numpy(dtype=float)
        highs = day["high"].to_numpy(dtype=float)
        lows = day["low"].to_numpy(dtype=float)
        closes = day["close"].to_numpy(dtype=float)
        vwap = day["session_vwap"].to_numpy(dtype=float)
        day_mid = (np.maximum.accumulate(highs) + np.minimum.accumulate(lows)) / 2.0
        atr = float(day["atr14_prev"].iloc[0])
        ib_mask = [idx for idx, value in enumerate(times) if "09:30" <= value < "10:00"]
        ib_mid = float("nan")
        if ib_mask:
            ib_mid = (float(np.max(highs[ib_mask])) + float(np.min(lows[ib_mask]))) / 2.0
        if math.isfinite(atr) and atr > 0 and len(day) >= 20:
            days.append(
                PreparedDay(
                    date=str(date),
                    timestamps=timestamps,
                    times=times,
                    opens=opens,
                    highs=highs,
                    lows=lows,
                    closes=closes,
                    vwap=vwap,
                    day_mid=day_mid,
                    ib_mid_30=ib_mid,
                    atr=atr,
                )
            )
    return days


def _mean_level(day: PreparedDay, mode: str, idx: int) -> float | None:
    if mode == "vwap":
        value = float(day.vwap[idx])
        return value if math.isfinite(value) else None
    if mode == "ib_mid30":
        if day.times[idx] < "10:00" or not math.isfinite(day.ib_mid_30):
            return None
        return float(day.ib_mid_30)
    if mode == "day_mid":
        return float(day.day_mid[idx])
    raise ValueError(f"Unknown mean_mode: {mode}")


def _simulate_exit(
    day: PreparedDay,
    *,
    direction: int,
    entry_idx: int,
    entry: float,
    stop: float,
    target: float,
    risk: float,
) -> tuple[int, float, str, float]:
    exit_idx = len(day.timestamps) - 1
    exit_price = float(day.closes[-1])
    exit_type = "eod"
    for scan_idx in range(entry_idx, len(day.timestamps)):
        if day.times[scan_idx] > FLAT_TIME:
            exit_idx = scan_idx - 1 if scan_idx > entry_idx else scan_idx
            exit_price = float(day.closes[exit_idx])
            exit_type = "eod"
            break
        if direction == 1:
            stop_hit = day.lows[scan_idx] <= stop
            target_hit = day.highs[scan_idx] >= target
            if stop_hit:
                exit_idx = scan_idx
                exit_price = stop
                exit_type = "stop"
                break
            if target_hit:
                exit_idx = scan_idx
                exit_price = target
                exit_type = "target"
                break
        else:
            stop_hit = day.highs[scan_idx] >= stop
            target_hit = day.lows[scan_idx] <= target
            if stop_hit:
                exit_idx = scan_idx
                exit_price = stop
                exit_type = "stop"
                break
            if target_hit:
                exit_idx = scan_idx
                exit_price = target
                exit_type = "target"
                break

    pnl_points = (exit_price - entry) * direction
    r_multiple = pnl_points / risk if risk > 0 else 0.0
    return exit_idx, exit_price, exit_type, r_multiple


def _try_setup_from_extension(
    day: PreparedDay,
    config: StateMachineConfig,
    extension_idx: int,
    direction: int,
) -> tuple[dict[str, Any], int] | None:
    extension = config.extension_atr_pct * day.atr
    stop_buffer = config.stop_buffer_atr_pct * day.atr
    start_signal_idx = extension_idx + 1 + config.consolidation_bars
    end_signal_idx = min(
        len(day.timestamps) - 2,
        extension_idx + config.setup_timeout_bars,
    )
    if start_signal_idx > end_signal_idx:
        return None

    for signal_idx in range(start_signal_idx, end_signal_idx + 1):
        if day.times[signal_idx] < ENTRY_START or day.times[signal_idx] > ENTRY_END:
            continue
        mean = _mean_level(day, config.mean_mode, signal_idx)
        if mean is None:
            continue

        cons_slice = slice(signal_idx - config.consolidation_bars, signal_idx)
        cons_high = float(np.max(day.highs[cons_slice]))
        cons_low = float(np.min(day.lows[cons_slice]))
        cons_range = cons_high - cons_low
        if cons_range > config.consolidation_atr_pct * day.atr:
            continue

        if direction == 1:
            if cons_high >= mean or mean - cons_low < extension:
                continue
            swept = day.lows[signal_idx] < cons_low
            reclaimed = day.closes[signal_idx] > cons_low and day.closes[signal_idx] < mean
            if not (swept and reclaimed):
                continue
            entry_idx = signal_idx + 1
            entry = float(day.opens[entry_idx])
            stop = float(day.lows[signal_idx] - stop_buffer)
            target = float(mean)
            risk = entry - stop
            reward = target - entry
        else:
            if cons_low <= mean or cons_high - mean < extension:
                continue
            swept = day.highs[signal_idx] > cons_high
            reclaimed = day.closes[signal_idx] < cons_high and day.closes[signal_idx] > mean
            if not (swept and reclaimed):
                continue
            entry_idx = signal_idx + 1
            entry = float(day.opens[entry_idx])
            stop = float(day.highs[signal_idx] + stop_buffer)
            target = float(mean)
            risk = stop - entry
            reward = entry - target

        if risk <= 0 or reward <= 0 or reward / risk < config.min_rr_to_mean:
            continue

        exit_idx, exit_price, exit_type, r_multiple = _simulate_exit(
            day,
            direction=direction,
            entry_idx=entry_idx,
            entry=entry,
            stop=stop,
            target=target,
            risk=risk,
        )
        trade = {
            "date": day.date,
            "direction": "long" if direction == 1 else "short",
            "mean_mode": config.mean_mode,
            "extension_ts": day.timestamps[extension_idx].isoformat(),
            "signal_ts": day.timestamps[signal_idx].isoformat(),
            "entry_ts": day.timestamps[entry_idx].isoformat(),
            "exit_ts": day.timestamps[exit_idx].isoformat(),
            "entry": round(entry, 2),
            "stop": round(stop, 2),
            "target": round(target, 2),
            "exit_price": round(exit_price, 2),
            "exit_type": exit_type,
            "risk_points": round(risk, 2),
            "reward_points": round(reward, 2),
            "rr_to_mean": round(reward / risk, 4),
            "r_multiple": round(r_multiple, 4),
            "atr14_prev": round(day.atr, 2),
            "setup_wait_bars": signal_idx - extension_idx,
        }
        return trade, exit_idx

    return None


def _simulate_day(day: PreparedDay, config: StateMachineConfig) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    idx = 0
    extension = config.extension_atr_pct * day.atr
    while idx < len(day.timestamps) - 2 and len(trades) < config.max_trades_per_day:
        bar_time = day.times[idx]
        if bar_time < ENTRY_START or bar_time > ENTRY_END:
            idx += 1
            continue
        mean = _mean_level(day, config.mean_mode, idx)
        if mean is None:
            idx += 1
            continue

        direction = 0
        if day.closes[idx] < mean and mean - day.lows[idx] >= extension:
            direction = 1
        elif day.closes[idx] > mean and day.highs[idx] - mean >= extension:
            direction = -1
        else:
            idx += 1
            continue

        setup = _try_setup_from_extension(day, config, idx, direction)
        if setup is None:
            idx += 1
            continue

        trade, exit_idx = setup
        trades.append(trade)
        idx = exit_idx + config.cooldown_bars

    return trades


def _max_drawdown(values: list[float]) -> float:
    equity = np.cumsum(np.array(values, dtype=float))
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _score_trades(trades: list[dict[str, Any]], trading_days: int, config: StateMachineConfig) -> dict[str, Any]:
    rs = [float(row["r_multiple"]) for row in trades]
    wins = [value for value in rs if value > 0]
    losses = [value for value in rs if value < 0]
    by_day = pd.Series([row["date"] for row in trades]).value_counts() if trades else pd.Series(dtype=int)
    days_with_trade = int((by_day > 0).sum())
    days_1_to_3 = int(((by_day >= 1) & (by_day <= 3)).sum())
    avg_trades_per_day = len(trades) / trading_days if trading_days else 0.0
    pct_days_with_trade = days_with_trade / trading_days if trading_days else 0.0
    pct_days_1_to_3 = days_1_to_3 / trading_days if trading_days else 0.0
    total_r = float(sum(rs))
    profit_factor = (sum(wins) / abs(sum(losses))) if losses else (999.0 if wins else 0.0)
    max_dd = _max_drawdown(rs)
    frequency_penalty = abs(avg_trades_per_day - 1.5) * 18.0 + max(0.0, 0.70 - pct_days_with_trade) * 70.0
    rank_score = total_r + 25.0 * min(profit_factor, 2.0) + 80.0 * pct_days_1_to_3 + 0.25 * max_dd - frequency_penalty
    exits = pd.Series([row["exit_type"] for row in trades]).value_counts().to_dict() if trades else {}
    waits = [int(row["setup_wait_bars"]) for row in trades]
    return {
        **asdict(config),
        "variant_id": (
            f"{config.mean_mode}_ext{config.extension_atr_pct:g}_"
            f"cons{config.consolidation_bars}x{config.consolidation_atr_pct:g}_"
            f"timeout{config.setup_timeout_bars}_buf{config.stop_buffer_atr_pct:g}_"
            f"minrr{config.min_rr_to_mean:g}"
        ),
        "rank_score": round(rank_score, 4),
        "total_trades": len(trades),
        "trading_days": trading_days,
        "avg_trades_per_day": round(avg_trades_per_day, 4),
        "days_with_trade": days_with_trade,
        "pct_days_with_trade": round(pct_days_with_trade, 4),
        "pct_days_1_to_3_trades": round(pct_days_1_to_3, 4),
        "zero_trade_days": trading_days - days_with_trade,
        "total_r": round(total_r, 4),
        "avg_r": round(total_r / len(trades), 4) if trades else 0.0,
        "profit_factor": round(float(profit_factor), 4),
        "win_rate": round(len(wins) / len(trades), 4) if trades else 0.0,
        "max_drawdown_r": round(max_dd, 4),
        "target_exits": int(exits.get("target", 0)),
        "stop_exits": int(exits.get("stop", 0)),
        "eod_exits": int(exits.get("eod", 0)),
        "avg_setup_wait_bars": round(float(np.mean(waits)), 2) if waits else None,
        "deployability": "research_only",
        "live_support_notes": (
            "State-machine level-reversion prototype exists only in this research script; "
            "live execution and exact replay parity are not implemented."
        ),
        "exact_replay_required": "yes",
    }


def _make_grid() -> list[StateMachineConfig]:
    configs: list[StateMachineConfig] = []
    for mean_mode in ("day_mid", "ib_mid30", "vwap"):
        for extension_atr_pct in (0.025, 0.05, 0.075, 0.10, 0.15):
            for consolidation_bars in (4, 6):
                for consolidation_atr_pct in (0.10, 0.15, 0.20):
                    for setup_timeout_bars in (12, 24, 36):
                        for stop_buffer_atr_pct in (0.005, 0.01, 0.02):
                            for min_rr_to_mean in (0.20, 0.40):
                                configs.append(
                                    StateMachineConfig(
                                        mean_mode=mean_mode,
                                        extension_atr_pct=extension_atr_pct,
                                        consolidation_bars=consolidation_bars,
                                        consolidation_atr_pct=consolidation_atr_pct,
                                        setup_timeout_bars=setup_timeout_bars,
                                        stop_buffer_atr_pct=stop_buffer_atr_pct,
                                        min_rr_to_mean=min_rr_to_mean,
                                    )
                                )
    return configs


def main() -> None:
    started = time.time()
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print(f"Loading NQ 5m data {DATA_START} to {DATA_END_EXCLUSIVE}...")
    df = load_5m_data(NQ.data_file, start=DATA_START, end=DATA_END_EXCLUSIVE)
    days = _prepare_days(_prepare_rth(df))
    trading_days = len(days)
    print(f"Prepared {trading_days} RTH days; first={days[0].date} last={days[-1].date}")

    configs = _make_grid()
    print(f"Running {len(configs)} state-machine configs...")
    rows: list[dict[str, Any]] = []
    best_trades: list[dict[str, Any]] = []
    best_score = -1e18
    for idx, config in enumerate(configs, start=1):
        trades: list[dict[str, Any]] = []
        for day in days:
            trades.extend(_simulate_day(day, config))
        row = _score_trades(trades, trading_days, config)
        rows.append(row)
        if row["rank_score"] > best_score:
            best_score = float(row["rank_score"])
            best_trades = trades
        if idx % 100 == 0:
            print(f"  completed {idx}/{len(configs)}; best={best_score:.2f}", flush=True)

    ranked = pd.DataFrame(rows).sort_values(
        [
            "rank_score",
            "pct_days_with_trade",
            "avg_trades_per_day",
            "total_r",
            "profit_factor",
        ],
        ascending=[False, False, False, False, False],
    ).reset_index(drop=True)
    ranked.insert(0, "rank", np.arange(1, len(ranked) + 1))
    frequency_fit = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
        & (ranked["pct_days_with_trade"] >= 0.70)
    ].copy()
    high_coverage_positive = ranked[
        (ranked["pct_days_with_trade"] >= 0.80)
        & (ranked["total_r"] > 0)
    ].copy()

    ranked_path = RESULT_DIR / "ranked_candidates.csv"
    trades_path = RESULT_DIR / "top_candidate_trades.csv"
    summary_path = RESULT_DIR / "summary.json"
    ranked.to_csv(ranked_path, index=False)
    pd.DataFrame(best_trades).to_csv(trades_path, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "state_machine_frequency_screen",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "available_last_day": days[-1].date if days else None,
        "trading_days": trading_days,
        "raw_configs": len(configs),
        "frequency_fit_configs": int(len(frequency_fit)),
        "high_coverage_positive_configs": int(len(high_coverage_positive)),
        "top_rows": ranked.head(20).to_dict(orient="records"),
        "elapsed_seconds": round(time.time() - started, 2),
    }
    summary_path.write_text(json.dumps(_safe(summary), indent=2) + "\n")

    report_cols = [
        "rank",
        "variant_id",
        "total_trades",
        "avg_trades_per_day",
        "pct_days_with_trade",
        "pct_days_1_to_3_trades",
        "zero_trade_days",
        "total_r",
        "avg_r",
        "profit_factor",
        "win_rate",
        "max_drawdown_r",
        "target_exits",
        "stop_exits",
        "eod_exits",
        "avg_setup_wait_bars",
    ]
    top_freq = frequency_fit.head(15)[report_cols].to_markdown(index=False) if not frequency_fit.empty else "_None._"
    top_high_cov = (
        high_coverage_positive.head(15)[report_cols].to_markdown(index=False)
        if not high_coverage_positive.empty else "_None._"
    )
    report_lines = [
        "# NQ NY Level Mean-Reversion State-Machine Recent 5-Year Pass",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` using available NQ 5m bars",
        f"- Trading days: `{trading_days}`",
        "- Pattern: extension from mean first, then consolidation can form within a timeout, then sweep/reclaim targets the signal-time mean",
        "- Mean modes tested: `day_mid`, `ib_mid30`, `vwap`",
        f"- Entry window: `{ENTRY_START}` to `{ENTRY_END}`; flat by `{FLAT_TIME}`",
        "- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar",
        f"- Raw configs: `{len(configs)}`",
        f"- Frequency-fit configs (`1-3` trades/day and >=70% day coverage): `{len(frequency_fit)}`",
        f"- Positive configs with >=80% day coverage: `{len(high_coverage_positive)}`",
        "",
        "## Top Rows By Frequency-Aware Score",
        "",
        ranked.head(15)[report_cols].to_markdown(index=False),
        "",
        "## Top Frequency-Fit Rows",
        "",
        top_freq,
        "",
        "## Top Positive Rows With >=80% Day Coverage",
        "",
        top_high_cov,
        "",
        "## Read",
        "",
        "- This is a second-pass prototype, not a promotion packet. It still uses 5m conservative pathing and no live/exact replay support.",
        "- The state-machine pass tests whether separating extension from consolidation improves the edge/cadence tradeoff from the first pass.",
        "- Any survivor still needs 1m/1s path validation, train/validation split, and prop-firm risk scoring.",
        "",
        "## Artifacts",
        "",
        f"- Ranked candidates: `backtesting/data/results/{RUN_SLUG}/ranked_candidates.csv`",
        f"- Top candidate trades: `backtesting/data/results/{RUN_SLUG}/top_candidate_trades.csv`",
        f"- Summary JSON: `backtesting/data/results/{RUN_SLUG}/summary.json`",
    ]
    REPORT_PATH.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {ranked_path}")
    print(f"Wrote {trades_path}")
    print(f"Wrote {summary_path}")
    print(f"Wrote {REPORT_PATH}")
    print(f"Elapsed {summary['elapsed_seconds']}s")


if __name__ == "__main__":
    main()
