#!/usr/bin/env python3
"""Recent 5-year NQ NY level mean-reversion prototype.

Tests extension -> consolidation -> sweep/reclaim -> mean target patterns.
Research artifact only; not wired to live execution.
"""

from __future__ import annotations

import json
import math
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(ROOT / "src"))

from orb_backtest.data.instruments import NQ  # noqa: E402
from orb_backtest.data.loader import load_5m_data  # noqa: E402


RUN_SLUG = "nq_ny_level_reversion_recent5_20260629"
RESULT_DIR = ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_LEVEL_REVERSION_RECENT5_20260629.md"

DATA_START = "2021-06-05"
DATA_END_EXCLUSIVE = "2026-06-06"
ENTRY_START = "09:45"
ENTRY_END = "15:00"
FLAT_TIME = "15:55"


@dataclass(frozen=True)
class LevelReversionConfig:
    mean_mode: str
    extension_atr_pct: float
    consolidation_bars: int
    consolidation_atr_pct: float
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


def _r2(value: Any) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(value, 2) if math.isfinite(value) else 0.0


def _time_str(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


def _prepare_rth(df: pd.DataFrame) -> pd.DataFrame:
    rth = df.between_time("09:30", "16:00").copy()
    rth["date"] = rth.index.date.astype(str)
    typical = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    rth["_tpv"] = typical * rth["volume"].astype(float)
    grouped = rth.groupby("date", sort=True)
    rth["session_vwap"] = grouped["_tpv"].cumsum() / grouped["volume"].cumsum().replace(0, np.nan)

    daily = grouped.agg({"high": "max", "low": "min", "close": "last"})
    daily["range"] = daily["high"] - daily["low"]
    daily["atr14_prev"] = daily["range"].rolling(14, min_periods=5).mean().shift(1)
    fallback = float(daily["range"].median())
    rth["atr14_prev"] = rth["date"].map(daily["atr14_prev"]).fillna(fallback)
    return rth.drop(columns=["_tpv"])


def _mean_level(
    mode: str,
    idx: int,
    opens: np.ndarray,
    highs: np.ndarray,
    lows: np.ndarray,
    vwap: np.ndarray,
    times: list[str],
    ib_mid_30: float,
) -> float | None:
    if mode == "vwap":
        return float(vwap[idx]) if math.isfinite(float(vwap[idx])) else None
    if mode == "ny_open":
        return float(opens[0])
    if mode == "ib_mid30":
        if times[idx] < "10:00" or not math.isfinite(ib_mid_30):
            return None
        return ib_mid_30
    if mode == "day_mid":
        return float((np.max(highs[: idx + 1]) + np.min(lows[: idx + 1])) / 2.0)
    raise ValueError(f"Unknown mean_mode: {mode}")


def _simulate_day(day: pd.DataFrame, config: LevelReversionConfig) -> list[dict[str, Any]]:
    if len(day) < 20:
        return []

    timestamps = list(day.index)
    times = [_time_str(ts) for ts in timestamps]
    opens = day["open"].to_numpy(dtype=float)
    highs = day["high"].to_numpy(dtype=float)
    lows = day["low"].to_numpy(dtype=float)
    closes = day["close"].to_numpy(dtype=float)
    vwap = day["session_vwap"].to_numpy(dtype=float)
    atr = float(day["atr14_prev"].iloc[0])
    if not math.isfinite(atr) or atr <= 0:
        return []

    ib_mask = [idx for idx, value in enumerate(times) if "09:30" <= value < "10:00"]
    ib_mid_30 = float("nan")
    if ib_mask:
        ib_mid_30 = (float(np.max(highs[ib_mask])) + float(np.min(lows[ib_mask]))) / 2.0

    trades: list[dict[str, Any]] = []
    idx = max(config.consolidation_bars, 1)
    while idx < len(day) - 1 and len(trades) < config.max_trades_per_day:
        bar_time = times[idx]
        if bar_time < ENTRY_START or bar_time > ENTRY_END:
            idx += 1
            continue

        mean = _mean_level(config.mean_mode, idx, opens, highs, lows, vwap, times, ib_mid_30)
        if mean is None:
            idx += 1
            continue

        cons_slice = slice(idx - config.consolidation_bars, idx)
        cons_high = float(np.max(highs[cons_slice]))
        cons_low = float(np.min(lows[cons_slice]))
        cons_range = cons_high - cons_low
        if cons_range > config.consolidation_atr_pct * atr:
            idx += 1
            continue

        extension = config.extension_atr_pct * atr
        stop_buffer = config.stop_buffer_atr_pct * atr

        long_extended = mean - cons_low >= extension and cons_high < mean
        short_extended = cons_high - mean >= extension and cons_low > mean
        direction = 0
        if long_extended and lows[idx] < cons_low and closes[idx] > cons_low and closes[idx] < mean:
            direction = 1
            entry_idx = idx + 1
            entry = float(opens[entry_idx])
            stop = float(lows[idx] - stop_buffer)
            target = float(mean)
            risk = entry - stop
            reward = target - entry
        elif short_extended and highs[idx] > cons_high and closes[idx] < cons_high and closes[idx] > mean:
            direction = -1
            entry_idx = idx + 1
            entry = float(opens[entry_idx])
            stop = float(highs[idx] + stop_buffer)
            target = float(mean)
            risk = stop - entry
            reward = entry - target
        else:
            idx += 1
            continue

        if risk <= 0 or reward <= 0 or reward / risk < config.min_rr_to_mean:
            idx += 1
            continue

        exit_idx = len(day) - 1
        exit_price = float(closes[-1])
        exit_type = "eod"
        for scan_idx in range(entry_idx, len(day)):
            if times[scan_idx] > FLAT_TIME:
                exit_idx = scan_idx - 1 if scan_idx > entry_idx else scan_idx
                exit_price = float(closes[exit_idx])
                exit_type = "eod"
                break
            if direction == 1:
                stop_hit = lows[scan_idx] <= stop
                target_hit = highs[scan_idx] >= target
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
                stop_hit = highs[scan_idx] >= stop
                target_hit = lows[scan_idx] <= target
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
        trades.append(
            {
                "date": str(day["date"].iloc[0]),
                "direction": "long" if direction == 1 else "short",
                "mean_mode": config.mean_mode,
                "signal_ts": timestamps[idx].isoformat(),
                "entry_ts": timestamps[entry_idx].isoformat(),
                "exit_ts": timestamps[exit_idx].isoformat(),
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "exit_price": round(exit_price, 2),
                "exit_type": exit_type,
                "risk_points": round(risk, 2),
                "reward_points": round(reward, 2),
                "rr_to_mean": round(reward / risk, 4),
                "r_multiple": round(r_multiple, 4),
                "atr14_prev": round(atr, 2),
            }
        )
        idx = exit_idx + config.cooldown_bars

    return trades


def _max_drawdown(values: list[float]) -> float:
    equity = np.cumsum(np.array(values, dtype=float))
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    return float(dd.min())


def _score_trades(trades: list[dict[str, Any]], trading_days: int, config: LevelReversionConfig) -> dict[str, Any]:
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
    frequency_penalty = abs(avg_trades_per_day - 1.5) * 20.0 + max(0.0, 0.75 - pct_days_with_trade) * 80.0
    rank_score = total_r + 20.0 * min(profit_factor, 3.0) + 75.0 * pct_days_1_to_3 - frequency_penalty + max_dd
    exits = pd.Series([row["exit_type"] for row in trades]).value_counts().to_dict() if trades else {}
    return {
        **asdict(config),
        "variant_id": (
            f"{config.mean_mode}_ext{config.extension_atr_pct:g}_"
            f"cons{config.consolidation_bars}x{config.consolidation_atr_pct:g}_"
            f"buf{config.stop_buffer_atr_pct:g}_minrr{config.min_rr_to_mean:g}"
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
        "deployability": "research_only",
        "live_support_notes": (
            "Prototype level-reversion strategy is implemented only in this research script; "
            "no live execution or exact replay parity exists."
        ),
        "exact_replay_required": "yes",
    }


def _make_grid() -> list[LevelReversionConfig]:
    configs: list[LevelReversionConfig] = []
    for mean_mode in ("vwap", "ny_open", "ib_mid30", "day_mid"):
        for extension_atr_pct in (0.025, 0.05, 0.075, 0.10, 0.15):
            for consolidation_bars in (3, 4, 6):
                for consolidation_atr_pct in (0.05, 0.10, 0.15, 0.20):
                    for stop_buffer_atr_pct in (0.005, 0.01, 0.02):
                        for min_rr_to_mean in (0.20, 0.40, 0.60):
                            configs.append(
                                LevelReversionConfig(
                                    mean_mode=mean_mode,
                                    extension_atr_pct=extension_atr_pct,
                                    consolidation_bars=consolidation_bars,
                                    consolidation_atr_pct=consolidation_atr_pct,
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
    rth = _prepare_rth(df)
    days = [(date, day.copy()) for date, day in rth.groupby("date", sort=True)]
    trading_days = len(days)
    print(f"Prepared {trading_days} RTH days; first={days[0][0]} last={days[-1][0]}")

    configs = _make_grid()
    print(f"Running {len(configs)} configs...")
    rows: list[dict[str, Any]] = []
    best_trades: list[dict[str, Any]] = []
    best_score = -1e18
    for idx, config in enumerate(configs, start=1):
        trades: list[dict[str, Any]] = []
        for _, day in days:
            trades.extend(_simulate_day(day, config))
        row = _score_trades(trades, trading_days, config)
        rows.append(row)
        if row["rank_score"] > best_score:
            best_score = float(row["rank_score"])
            best_trades = trades
        if idx % 100 == 0:
            print(f"  completed {idx}/{len(configs)}; best={best_score:.2f}")

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
    freq_fit = ranked[
        (ranked["avg_trades_per_day"] >= 1.0)
        & (ranked["avg_trades_per_day"] <= 3.0)
        & (ranked["pct_days_with_trade"] >= 0.60)
    ].copy()

    ranked_path = RESULT_DIR / "ranked_candidates.csv"
    trades_path = RESULT_DIR / "top_candidate_trades.csv"
    summary_path = RESULT_DIR / "summary.json"
    ranked.to_csv(ranked_path, index=False)
    pd.DataFrame(best_trades).to_csv(trades_path, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "phase": "prototype_frequency_screen",
        "data_start": DATA_START,
        "data_end_exclusive": DATA_END_EXCLUSIVE,
        "available_last_day": days[-1][0] if days else None,
        "trading_days": trading_days,
        "raw_configs": len(configs),
        "frequency_fit_configs": int(len(freq_fit)),
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
    ]
    report_lines = [
        "# NQ NY Level Mean-Reversion Recent 5-Year Prototype",
        "",
        f"- Run slug: `{RUN_SLUG}`",
        f"- Data: `{DATA_START}` to `<{DATA_END_EXCLUSIVE}` using available NQ 5m bars",
        f"- Trading days: `{trading_days}`",
        "- Pattern: extension from mean -> tight consolidation -> sweep/reclaim of consolidation edge -> target fixed mean level",
        "- Mean modes tested: `vwap`, `ny_open`, `ib_mid30`, `day_mid`",
        f"- Entry window: `{ENTRY_START}` to `{ENTRY_END}`; flat by `{FLAT_TIME}`",
        "- Intrabar path assumption: conservative 5m bar path; stop wins if stop and target touch the same bar",
        f"- Raw configs: `{len(configs)}`",
        f"- Configs averaging 1-3 trades/day with at least 60% trade-day coverage: `{len(freq_fit)}`",
        "",
        "## Top Rows By Frequency-Aware Score",
        "",
        ranked.head(15)[report_cols].to_markdown(index=False),
        "",
        "## Top Rows Meeting 1-3 Trades/Day Frequency Filter",
        "",
        (freq_fit.head(15)[report_cols].to_markdown(index=False) if not freq_fit.empty else "_None in first pass._"),
        "",
        "## Read",
        "",
        "- This is a prototype screen, not a promotion packet. It uses 5m conservative exit sequencing and has no live/exact replay support.",
        "- The frequency objective is explicit: prefer average `1-3` trades/day and high percent of days with at least one trade.",
        "- Any promising row needs a second pass with 1m/1s magnifier, train/validation split, and prop-firm risk analysis before being taken seriously.",
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
