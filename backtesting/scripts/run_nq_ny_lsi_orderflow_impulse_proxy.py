#!/usr/bin/env python3
"""Diagnostic 1s impulse proxy for short-timeframe NQ NY LSI candidates.

This is deliberately *not* true order-book OFI. Historical NQ data currently
available to the research engine is OHLCV, so this pass uses a causal 1-second
proxy for the discretionary idea of "violent reversal momentum":

- directional price burst inside the setup confirmation bar
- directional volume proxy from 1s close/open movement
- abnormality versus earlier same-day 1s movement/volume

The goal is to see whether this intuition has enough signal to justify a
proper DataBento MBP/MBO order-flow feature later.
"""

from __future__ import annotations

import dataclasses
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow.dataset as ds

import htf_lsi_common as htf
import run_nq_ny_lsi_cisd_candidate_validation as val
import run_nq_ny_lsi_cisd_restricted_finalists as restricted
import run_nq_ny_lsi_cisd_sequence as seq

sys.path.insert(0, str(seq.ROOT / "src"))

from orb_backtest.engine.simulator import (  # noqa: E402
    EXIT_NO_FILL,
    build_maps,
    build_signal_cache,
    run_backtest,
)


RUN_SLUG = "nq_ny_lsi_orderflow_impulse_proxy_20260513"
OUTPUT_DIR = seq.ROOT / "data" / "results" / RUN_SLUG
REPORT_PATH = seq.ROOT / "learnings" / "reports" / "NQ_NY_LSI_ORDERFLOW_IMPULSE_PROXY_20260513.md"

ANALYSIS_START = "2023-01-01"
VALIDATION_START = val.PERIODS["validation"][0]
VALIDATION_END = val.PERIODS["validation"][1]
HOLDOUT_START = val.PERIODS["holdout"][0]
ONE_SECOND_PATH = seq.ROOT / "data" / "raw" / "NQ_1s.parquet"
TICK_SIZE = 0.25


@dataclasses.dataclass(frozen=True)
class CandidateRun:
    key: str
    label: str
    timeframe: str
    config: Any


@dataclasses.dataclass
class RollingWindowStats:
    start_ns: np.ndarray
    end_ns: np.ndarray
    move_ticks: np.ndarray
    volume: np.ndarray
    signed_volume: np.ndarray


@dataclasses.dataclass
class DayStats:
    frame: pd.DataFrame
    timestamp_ns: np.ndarray
    sign_volume: np.ndarray
    rolling: dict[int, RollingWindowStats]


class ImpulseScorer:
    def __init__(self, df_1s: pd.DataFrame, *, tick_size: float) -> None:
        self.df_1s = df_1s
        self.tick_size = tick_size
        self._days: dict[str, DayStats] = {}

    def _day_stats(self, day: str) -> DayStats | None:
        cached = self._days.get(day)
        if cached is not None:
            return cached

        start = pd.Timestamp(day)
        end = start + pd.Timedelta(days=1)
        frame = self.df_1s.loc[(self.df_1s.index >= start) & (self.df_1s.index < end)]
        if frame.empty:
            return None

        open_arr = frame["open"].to_numpy(dtype=np.float64, copy=False)
        close_arr = frame["close"].to_numpy(dtype=np.float64, copy=False)
        volume_arr = frame["volume"].to_numpy(dtype=np.float64, copy=False)
        delta = close_arr - open_arr
        prev_delta = np.empty_like(delta)
        prev_delta[0] = delta[0]
        if len(delta) > 1:
            prev_delta[1:] = close_arr[1:] - close_arr[:-1]
        signed_direction = np.where(delta != 0.0, np.sign(delta), np.sign(prev_delta))
        sign_volume = signed_direction * volume_arr

        stats = DayStats(
            frame=frame,
            timestamp_ns=frame.index.view("int64"),
            sign_volume=sign_volume,
            rolling={},
        )
        self._days[day] = stats
        return stats

    def _rolling(self, stats: DayStats, window_seconds: int) -> RollingWindowStats | None:
        window_seconds = int(max(1, window_seconds))
        cached = stats.rolling.get(window_seconds)
        if cached is not None:
            return cached

        frame = stats.frame
        n = len(frame)
        if n < window_seconds:
            return None

        open_arr = frame["open"].to_numpy(dtype=np.float64, copy=False)
        close_arr = frame["close"].to_numpy(dtype=np.float64, copy=False)
        volume_arr = frame["volume"].to_numpy(dtype=np.float64, copy=False)
        csum_vol = np.concatenate(([0.0], np.cumsum(volume_arr)))
        csum_signed = np.concatenate(([0.0], np.cumsum(stats.sign_volume)))
        start_idx = np.arange(0, n - window_seconds + 1)
        end_idx = start_idx + window_seconds - 1

        rolling = RollingWindowStats(
            start_ns=stats.timestamp_ns[start_idx],
            end_ns=stats.timestamp_ns[end_idx],
            move_ticks=(close_arr[end_idx] - open_arr[start_idx]) / self.tick_size,
            volume=csum_vol[start_idx + window_seconds] - csum_vol[start_idx],
            signed_volume=csum_signed[start_idx + window_seconds] - csum_signed[start_idx],
        )
        stats.rolling[window_seconds] = rolling
        return rolling

    def _baseline(
        self,
        stats: DayStats,
        *,
        before_ns: int,
        window_seconds: int,
    ) -> tuple[float, float]:
        rolling = self._rolling(stats, window_seconds)
        if rolling is None:
            return 1.0, 1.0
        prior_mask = rolling.end_ns < before_ns
        if int(prior_mask.sum()) < 50:
            prior_mask = rolling.end_ns < before_ns
        if not bool(prior_mask.any()):
            return 1.0, 1.0

        abs_move = np.abs(rolling.move_ticks[prior_mask])
        volume = rolling.volume[prior_mask]
        move_p75 = float(np.nanpercentile(abs_move, 75)) if len(abs_move) else 1.0
        volume_p75 = float(np.nanpercentile(volume, 75)) if len(volume) else 1.0
        return max(move_p75, 1.0), max(volume_p75, 1.0)

    def score_window(
        self,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        direction: int,
        window_seconds: int,
    ) -> dict[str, float]:
        day = start.strftime("%Y-%m-%d")
        stats = self._day_stats(day)
        if stats is None or end <= start:
            return self._empty(window_seconds)

        start_ns = int(start.value)
        end_ns = int(end.value)
        rolling = self._rolling(stats, window_seconds)
        if rolling is None:
            return self._empty(window_seconds)

        event_mask = (rolling.start_ns >= start_ns) & (rolling.end_ns < end_ns)
        if not bool(event_mask.any()):
            return self._empty(window_seconds)

        move_p75, volume_p75 = self._baseline(stats, before_ns=start_ns, window_seconds=window_seconds)
        dir_move = direction * rolling.move_ticks[event_mask]
        volume = rolling.volume[event_mask]
        signed_volume = direction * rolling.signed_volume[event_mask]
        flow_imbalance = np.divide(
            signed_volume,
            volume,
            out=np.zeros_like(signed_volume, dtype=np.float64),
            where=volume > 0,
        )
        price_ratio = dir_move / move_p75
        volume_ratio = volume / volume_p75
        score = np.maximum(price_ratio, 0.0) * np.sqrt(np.maximum(volume_ratio, 0.0)) * np.maximum(flow_imbalance, 0.0)
        idx = int(np.nanargmax(score))

        return {
            f"score_{window_seconds}s": float(score[idx]),
            f"dir_move_ticks_{window_seconds}s": float(dir_move[idx]),
            f"volume_ratio_{window_seconds}s": float(volume_ratio[idx]),
            f"flow_imbalance_{window_seconds}s": float(flow_imbalance[idx]),
            f"price_ratio_{window_seconds}s": float(price_ratio[idx]),
        }

    def score_full_bar(
        self,
        *,
        start: pd.Timestamp,
        end: pd.Timestamp,
        direction: int,
    ) -> dict[str, float]:
        day = start.strftime("%Y-%m-%d")
        stats = self._day_stats(day)
        if stats is None or end <= start:
            return self._empty_full()

        frame = stats.frame.loc[(stats.frame.index >= start) & (stats.frame.index < end)]
        if frame.empty:
            return self._empty_full()

        window_seconds = max(1, int(math.ceil((end - start).total_seconds())))
        move_p75, volume_p75 = self._baseline(stats, before_ns=int(start.value), window_seconds=window_seconds)
        open_price = float(frame["open"].iloc[0])
        close_price = float(frame["close"].iloc[-1])
        volume = float(frame["volume"].sum())
        signed_volume = float(direction * stats.sign_volume[stats.frame.index.get_indexer(frame.index)].sum())
        dir_move = float(direction * (close_price - open_price) / self.tick_size)
        flow_imbalance = signed_volume / volume if volume > 0 else 0.0
        price_ratio = dir_move / move_p75
        volume_ratio = volume / volume_p75
        score = max(price_ratio, 0.0) * math.sqrt(max(volume_ratio, 0.0)) * max(flow_imbalance, 0.0)
        return {
            "score_full": float(score),
            "dir_move_ticks_full": float(dir_move),
            "volume_ratio_full": float(volume_ratio),
            "flow_imbalance_full": float(flow_imbalance),
            "price_ratio_full": float(price_ratio),
        }

    @staticmethod
    def _empty(window_seconds: int) -> dict[str, float]:
        return {
            f"score_{window_seconds}s": float("nan"),
            f"dir_move_ticks_{window_seconds}s": float("nan"),
            f"volume_ratio_{window_seconds}s": float("nan"),
            f"flow_imbalance_{window_seconds}s": float("nan"),
            f"price_ratio_{window_seconds}s": float("nan"),
        }

    @staticmethod
    def _empty_full() -> dict[str, float]:
        return {
            "score_full": float("nan"),
            "dir_move_ticks_full": float("nan"),
            "volume_ratio_full": float("nan"),
            "flow_imbalance_full": float("nan"),
            "price_ratio_full": float("nan"),
        }


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def load_one_second_slice(start: str, end: str | None = None) -> pd.DataFrame:
    t0 = time.time()
    dataset = ds.dataset(ONE_SECOND_PATH, format="parquet")
    flt = ds.field("datetime") >= pd.Timestamp(start).to_datetime64()
    if end is not None:
        flt = flt & (ds.field("datetime") < pd.Timestamp(end).to_datetime64())
    table = dataset.to_table(
        columns=["datetime", "open", "high", "low", "close", "volume"],
        filter=flt,
    )
    frame = table.to_pandas()
    frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop("datetime")))
    frame = frame.sort_index()
    for col in ("open", "high", "low", "close"):
        frame[col] = frame[col].astype("float32")
    frame["volume"] = frame["volume"].astype("float32")
    print(f"Loaded {len(frame):,} 1s bars from {start} in {time.time() - t0:.1f}s", flush=True)
    return frame


def build_candidate_runs() -> list[CandidateRun]:
    variants = {variant.key: variant for variant in restricted.build_variants()}
    selected_keys = (
        "add_1m_classic_atr10_b3_a7p5__both__allDOW__cut1530",
        "add_1m_classic_atr10_b3_a7p5__both__noThu__cut1530",
        "pure_1m_classic_atr15_b2_a7p5__long__allDOW__cut1200",
    )
    runs = [
        CandidateRun(
            key=key,
            label=variants[key].label,
            timeframe="1m",
            config=variants[key].config,
        )
        for key in selected_keys
    ]
    runs.append(
        CandidateRun(
            key="add_3m_hourly_atr12p5_b3_a7p5",
            label="3m additive hourly HTF LSI/CISD finalist",
            timeframe="3m",
            config=val.cfg_for(val.CANDIDATES[2]),
        )
    )
    runs.append(
        CandidateRun(
            key="htf_lsi_2m_anchor",
            label="2m HTF-LSI secondary anchor",
            timeframe="2m",
            config=htf.build_config(
                timeframe="2m",
                direction_filter="long",
                entry_mode="fvg_limit",
                entry_start="08:30",
                entry_end="15:00",
                rr=3.0,
                tp1_ratio=0.6,
                min_gap_atr_pct=3.0,
                atr_length=14,
                htf_level_tf_minutes=60,
                htf_n_left=3,
                htf_trade_max_per_session=1,
                lsi_fvg_window_left=50,
                lsi_fvg_window_right=5,
                max_fvg_to_inversion_bars=0,
                name="NQ NY HTF_LSI 2m impulse proxy anchor",
            ),
        )
    )
    return runs


def load_signal_data() -> dict[str, pd.DataFrame]:
    data = seq.load_timeframes()
    path_2m = seq.CACHE_DIR / "NQ_2m.parquet"
    if path_2m.exists():
        data["2m"] = pd.read_parquet(path_2m)
    else:
        data["2m"] = seq.resample_ohlcv(data["1m"], "2min")
        data["2m"].to_parquet(path_2m)
    return data


def run_candidate(candidate: CandidateRun, data: dict[str, pd.DataFrame]) -> list[Any]:
    df = data[candidate.timeframe]
    df_1m = data["1m"] if candidate.timeframe != "1m" else None
    maps = build_maps(df, df_1m=df_1m)
    cache = build_signal_cache(df, [candidate.config], signal_df_1m=data["1m"])
    t0 = time.time()
    trades = run_backtest(
        df,
        candidate.config,
        start_date=ANALYSIS_START,
        df_1m=df_1m,
        signal_df_1m=data["1m"],
        _maps=maps,
        _signal_cache=cache,
    )
    fills = [trade for trade in trades if trade.exit_type != EXIT_NO_FILL]
    print(
        f"  {candidate.key:<58} {len(fills):>4} fills "
        f"[{time.time() - t0:.1f}s]",
        flush=True,
    )
    return trades


def timeframe_delta(timeframe: str) -> pd.Timedelta:
    return pd.Timedelta(minutes=int(timeframe.removesuffix("m")))


def annotate_trades(
    *,
    candidate: CandidateRun,
    trades: list[Any],
    data: dict[str, pd.DataFrame],
    scorer: ImpulseScorer,
) -> list[dict[str, Any]]:
    df = data[candidate.timeframe]
    delta = timeframe_delta(candidate.timeframe)
    rows: list[dict[str, Any]] = []

    for trade in trades:
        if trade.exit_type == EXIT_NO_FILL or trade.signal_bar < 0 or trade.signal_bar >= len(df):
            continue
        signal_start = pd.Timestamp(df.index[trade.signal_bar])
        signal_end = signal_start + delta
        row = {
            "candidate": candidate.key,
            "label": candidate.label,
            "timeframe": candidate.timeframe,
            "date": trade.date,
            "direction": int(trade.direction),
            "confirmation": trade.lsi_confirmation_type,
            "r_multiple": float(trade.r_multiple),
            "signal_time": signal_start.isoformat(),
            "fill_time": trade.fill_time,
            "lsi_sweep_time": trade.lsi_sweep_time,
            "lsi_fvg_time": trade.lsi_fvg_time,
            "lsi_cisd_time": trade.lsi_cisd_time,
            "entry_price": float(trade.entry_price),
            "risk_points": float(trade.risk_points),
        }
        row.update(
            scorer.score_window(
                start=signal_start,
                end=signal_end,
                direction=int(trade.direction),
                window_seconds=5,
            )
        )
        row.update(
            scorer.score_window(
                start=signal_start,
                end=signal_end,
                direction=int(trade.direction),
                window_seconds=15,
            )
        )
        row.update(
            scorer.score_full_bar(
                start=signal_start,
                end=signal_end,
                direction=int(trade.direction),
            )
        )
        rows.append(row)
    return rows


def in_period(row: pd.Series, start: str | None, end: str | None) -> bool:
    return (start is None or row["date"] >= start) and (end is None or row["date"] < end)


def metric_row(candidate: str, period: str, gate: str, subset: pd.DataFrame, threshold: float | None = None) -> dict[str, Any]:
    metrics = val.r_metrics(subset["r_multiple"].to_numpy(dtype=float) if not subset.empty else [])
    out = {
        "candidate": candidate,
        "period": period,
        "gate": gate,
        "threshold": threshold,
    }
    out.update(metrics)
    if not subset.empty:
        out["cisd_trades"] = int((subset["confirmation"] == "cisd").sum())
        out["inversion_trades"] = int((subset["confirmation"] == "inversion").sum())
        out["long_trades"] = int((subset["direction"] == 1).sum())
        out["short_trades"] = int((subset["direction"] == -1).sum())
    else:
        out.update({"cisd_trades": 0, "inversion_trades": 0, "long_trades": 0, "short_trades": 0})
    return out


def build_gate_summary(trade_df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    periods = {
        "validation": (VALIDATION_START, VALIDATION_END),
        "holdout": (HOLDOUT_START, None),
        "post_2023": (VALIDATION_START, None),
    }
    score_columns = ("score_5s", "score_15s", "score_full")

    for candidate, candidate_df in trade_df.groupby("candidate"):
        validation = candidate_df[(candidate_df["date"] >= VALIDATION_START) & (candidate_df["date"] < VALIDATION_END)]
        thresholds: list[tuple[str, str, float]] = []
        for column in score_columns:
            values = validation[column].replace([np.inf, -np.inf], np.nan).dropna()
            if values.empty:
                continue
            for quantile in (0.50, 0.60, 0.70, 0.80):
                thresholds.append((column, f"{column}_val_q{int(quantile * 100)}", float(values.quantile(quantile))))
            for absolute in (1.0, 1.5, 2.0, 3.0):
                thresholds.append((column, f"{column}_abs_ge_{str(absolute).replace('.', 'p')}", absolute))

        for period, (start, end) in periods.items():
            period_df = candidate_df[(candidate_df["date"] >= start) & ((candidate_df["date"] < end) if end else True)]
            rows.append(metric_row(candidate, period, "baseline", period_df))
            for column, gate, threshold in thresholds:
                gated = period_df[period_df[column] >= threshold]
                rows.append(metric_row(candidate, period, gate, gated, threshold))

    return pd.DataFrame(rows)


def write_report(gate_df: pd.DataFrame, trade_df: pd.DataFrame) -> None:
    lines = [
        "# NQ NY LSI Order-Flow Impulse Proxy",
        "",
        "- Objective: test whether a causal 1s OHLCV impulse proxy improves shorter-timeframe LSI/CISD candidates.",
        "- Important limitation: this is **not** true order book momentum. The current historical file has only `open/high/low/close/volume` at 1-second resolution, so signed flow is inferred from 1s price direction.",
        f"- Analysis window: `{ANALYSIS_START}` through latest available NQ 1s data.",
        "- Score: best directional 5s/15s burst inside the setup confirmation bar, scaled by earlier same-day movement and volume.",
        "",
        "## Best Holdout Gates",
        "",
        "| Candidate | Gate | Threshold | Trades | PF | Avg R | Total R | DD | Calmar |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    holdout = gate_df[(gate_df["period"] == "holdout") & (gate_df["gate"] != "baseline")].copy()
    holdout = holdout[holdout["trades"] >= 15]
    holdout = holdout.sort_values(["candidate", "calmar", "profit_factor", "total_r"], ascending=[True, False, False, False])
    for candidate, group in holdout.groupby("candidate"):
        row = group.iloc[0]
        lines.append(
            f"| `{candidate}` | `{row['gate']}` | {row['threshold']:.3f} | "
            f"{int(row['trades'])} | {row['profit_factor']:.3f} | {row['avg_r']:.3f} | "
            f"{row['total_r']:.2f} | {row['max_dd_r']:.2f} | {row['calmar']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Baselines",
            "",
            "| Candidate | Period | Trades | PF | Avg R | Total R | DD | Calmar |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    baseline = gate_df[gate_df["gate"] == "baseline"].sort_values(["candidate", "period"])
    for _, row in baseline.iterrows():
        lines.append(
            f"| `{row['candidate']}` | {row['period']} | {int(row['trades'])} | "
            f"{row['profit_factor']:.3f} | {row['avg_r']:.3f} | {row['total_r']:.2f} | "
            f"{row['max_dd_r']:.2f} | {row['calmar']:.2f} |"
        )

    lines.extend(
        [
            "",
            "## Score Distribution",
            "",
            "| Candidate | Trades | 5s p50 | 5s p75 | 15s p50 | 15s p75 | Full p50 | Full p75 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for candidate, group in trade_df.groupby("candidate"):
        lines.append(
            f"| `{candidate}` | {len(group)} | "
            f"{group['score_5s'].median():.3f} | {group['score_5s'].quantile(0.75):.3f} | "
            f"{group['score_15s'].median():.3f} | {group['score_15s'].quantile(0.75):.3f} | "
            f"{group['score_full'].median():.3f} | {group['score_full'].quantile(0.75):.3f} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation Guardrails",
            "",
            "- Treat any improvement here as a clue, not a production rule. True order-book testing needs bid/ask-side trades or MBP/MBO-derived OFI.",
            "- Gates are diagnostic because holdout has already been opened for these branches.",
            "- A useful next step is to promote only gates that improve validation and holdout together without collapsing trade count.",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines))


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("NQ NY LSI 1s impulse proxy diagnostic", flush=True)
    data = load_signal_data()
    candidates = build_candidate_runs()

    trades_by_candidate: dict[str, list[Any]] = {}
    for candidate in candidates:
        trades_by_candidate[candidate.key] = run_candidate(candidate, data)

    df_1s = load_one_second_slice(ANALYSIS_START)
    scorer = ImpulseScorer(df_1s, tick_size=TICK_SIZE)

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        t0 = time.time()
        candidate_rows = annotate_trades(
            candidate=candidate,
            trades=trades_by_candidate[candidate.key],
            data=data,
            scorer=scorer,
        )
        rows.extend(candidate_rows)
        print(
            f"  annotated {candidate.key:<58} {len(candidate_rows):>4} fills "
            f"[{time.time() - t0:.1f}s]",
            flush=True,
        )

    trade_df = pd.DataFrame(rows)
    gate_df = build_gate_summary(trade_df)

    trade_path = OUTPUT_DIR / "trade_impulse.csv"
    gate_path = OUTPUT_DIR / "gate_summary.csv"
    trade_df.to_csv(trade_path, index=False)
    gate_df.to_csv(gate_path, index=False)

    summary = {
        "run_slug": RUN_SLUG,
        "analysis_start": ANALYSIS_START,
        "data_limitations": "1s OHLCV proxy only; no historical L2/order-book depth or aggressor flags used.",
        "candidates": [
            {
                "key": candidate.key,
                "label": candidate.label,
                "timeframe": candidate.timeframe,
                "config_name": candidate.config.name,
            }
            for candidate in candidates
        ],
        "outputs": {
            "trade_impulse_csv": str(trade_path),
            "gate_summary_csv": str(gate_path),
            "report": str(REPORT_PATH),
        },
    }
    save_json(OUTPUT_DIR / "summary.json", summary)
    write_report(gate_df, trade_df)

    print(f"Wrote {trade_path}", flush=True)
    print(f"Wrote {gate_path}", flush=True)
    print(f"Wrote {REPORT_PATH}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
