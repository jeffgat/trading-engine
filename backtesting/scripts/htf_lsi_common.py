#!/usr/bin/env python3
"""Shared helpers for NQ NY HTF-LSI research scripts."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Callable

import pandas as pd

from orb_backtest.analysis.regime_research import build_extended_regime_calendar, _regime_lookup
from orb_backtest.config import SessionConfig, StrategyConfig
from orb_backtest.data.instruments import NQ
from orb_backtest.data.loader import DATA_DIR, load_5m_data, load_1m_for_5m, load_1s_for_5m
from orb_backtest.results.metrics import compute_metrics


ROOT = Path(__file__).resolve().parent.parent
RESULTS_ROOT = ROOT / "data" / "results"
REPORT_PATH = ROOT / "learnings" / "reports" / "NQ_NY_HTF_LSI_DISCOVERY.md"

DISCOVERY_START = "2016-01-01"
DISCOVERY_END = "2022-12-31"
VALIDATION_START = "2023-01-01"
VALIDATION_END = "2025-03-31"
HOLDOUT_START = "2025-04-01"
PRE_HOLDOUT_END = "2025-03-31"

AVOID_BUCKETS = {"bull_medium_vol", "sideways_medium_vol"}

CURRENT_NQ_NY_HTF_LSI_LAG24 = {
    "timeframe": "5m",
    "direction_filter": "long",
    "entry_mode": "fvg_limit",
    "entry_start": "08:30",
    "entry_end": "13:30",
    "rr": 3.5,
    "tp1_ratio": 0.4,
    "min_gap_atr_pct": 3.0,
    "atr_length": 14,
    "htf_level_tf_minutes": 60,
    "htf_n_left": 3,
    "htf_trade_max_per_session": 2,
    "lsi_fvg_window_left": 20,
    "lsi_fvg_window_right": 2,
    "max_fvg_to_inversion_bars": 24,
}


def _data_exists(stem: str) -> bool:
    path = DATA_DIR / stem
    return path.with_suffix(".parquet").exists() or path.with_suffix(".csv").exists()


def ensure_required_data() -> None:
    missing = [stem for stem in ("NQ_5m", "NQ_1m") if not _data_exists(stem)]
    if missing:
        raise FileNotFoundError(
            "Missing required raw files in backtesting/data/raw: "
            + ", ".join(f"{stem}.parquet|csv" for stem in missing)
        )


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    out = df.resample(rule, label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    return out.dropna(subset=["open", "high", "low", "close"]).astype(float)


def load_timeframe_data(timeframe: str) -> tuple[pd.DataFrame, pd.DataFrame | None, pd.DataFrame | None, pd.DataFrame]:
    ensure_required_data()
    df_1s = load_1s_for_5m("NQ_5m.parquet")
    if timeframe == "5m":
        df_base = load_5m_data("NQ_5m.parquet")
        df_1m = load_1m_for_5m("NQ_5m.parquet")
        return df_base, df_1m, df_1s, df_1m

    signal_df_1m = load_5m_data("NQ_1m.parquet")
    if timeframe == "3m":
        df_base = resample_ohlcv(signal_df_1m, "3min")
    elif timeframe == "2m":
        df_base = resample_ohlcv(signal_df_1m, "2min")
    elif timeframe == "1m":
        df_base = signal_df_1m
    else:
        raise ValueError(f"Unsupported timeframe {timeframe!r}")
    return df_base, signal_df_1m, df_1s, signal_df_1m


def build_session(
    *,
    entry_start: str = "08:30",
    entry_end: str = "15:00",
    min_gap_atr_pct: float = 3.0,
) -> SessionConfig:
    return SessionConfig(
        name="NY",
        rth_start="08:30",
        sweep_start="08:30",
        sweep_end="15:00",
        entry_start=entry_start,
        entry_end=entry_end,
        flat_start="15:50",
        flat_end="16:00",
        min_gap_atr_pct=min_gap_atr_pct,
    )


def build_config(
    *,
    timeframe: str = "5m",
    direction_filter: str = "both",
    entry_mode: str = "fvg_limit",
    entry_start: str = "08:30",
    entry_end: str = "15:00",
    rr: float = 2.0,
    tp1_ratio: float = 0.5,
    min_gap_atr_pct: float = 3.0,
    atr_length: int = 14,
    htf_level_tf_minutes: int = 60,
    htf_n_left: int = 5,
    htf_trade_max_per_session: int = 1,
    htf_lsi_include_htf_levels: bool = True,
    htf_lsi_reference_levels: tuple[str, ...] = (),
    data_sweep_min_daily_atr_pct: float = 15.0,
    lsi_fvg_window_left: int = 20,
    lsi_fvg_window_right: int = 5,
    max_fvg_to_inversion_bars: int = 0,
    entry_context_gate: str = "",
    entry_context_min_atr: float = 0.0,
    entry_context_max_atr: float = 0.0,
    name: str = "",
) -> StrategyConfig:
    session = build_session(entry_start=entry_start, entry_end=entry_end, min_gap_atr_pct=min_gap_atr_pct)
    if not name:
        name = (
            f"NQ NY HTF_LSI {timeframe} "
            f"htf{htf_level_tf_minutes} n{htf_n_left} "
            f"{direction_filter} {entry_mode} "
            f"{entry_start}-{entry_end} cap{htf_trade_max_per_session}"
        )
    return StrategyConfig(
        instrument=NQ,
        sessions=(session,),
        strategy="htf_lsi",
        use_bar_magnifier=True,
        risk_usd=5000.0,
        min_qty=1.0,
        qty_step=1.0,
        direction_filter=direction_filter,
        rr=rr,
        tp1_ratio=tp1_ratio,
        atr_length=atr_length,
        lsi_fvg_window_left=lsi_fvg_window_left,
        lsi_fvg_window_right=lsi_fvg_window_right,
        lsi_stop_mode="absolute",
        lsi_entry_mode=entry_mode,
        htf_level_tf_minutes=htf_level_tf_minutes,
        htf_n_left=htf_n_left,
        htf_trade_max_per_session=htf_trade_max_per_session,
        htf_lsi_include_htf_levels=htf_lsi_include_htf_levels,
        htf_lsi_reference_levels=htf_lsi_reference_levels,
        data_sweep_min_daily_atr_pct=data_sweep_min_daily_atr_pct,
        max_fvg_to_inversion_bars=max_fvg_to_inversion_bars,
        entry_context_gate=entry_context_gate,
        entry_context_min_atr=entry_context_min_atr,
        entry_context_max_atr=entry_context_max_atr,
        name=name,
    )


def build_current_nq_ny_htf_lsi_lag24_config(
    *,
    name: str = "NQ NY HTF_LSI 5m lag24 lead",
    **overrides,
) -> StrategyConfig:
    params = {**CURRENT_NQ_NY_HTF_LSI_LAG24, **overrides}
    return build_config(name=name, **params)


def slice_trades(trades, start: str | None = None, end: str | None = None):
    return [
        t for t in trades
        if (start is None or t.date >= start) and (end is None or t.date < end)
    ]


def summarize_periods(trades) -> dict[str, dict]:
    return {
        "pre_holdout": compute_metrics(slice_trades(trades, DISCOVERY_START, HOLDOUT_START)),
        "discovery": compute_metrics(slice_trades(trades, DISCOVERY_START, VALIDATION_START)),
        "validation": compute_metrics(slice_trades(trades, VALIDATION_START, HOLDOUT_START)),
    }


def result_row(label: str, config: StrategyConfig, trades, *, gate_label: str = "ungated") -> dict:
    summary = summarize_periods(trades)
    session = config.sessions[0]
    return {
        "label": label,
        "gate": gate_label,
        "strategy": config.strategy,
        "timeframe": "1m" if session.entry_start == "" else "",
        "direction_filter": config.direction_filter,
        "entry_mode": config.lsi_entry_mode,
        "entry_start": session.entry_start,
        "entry_end": session.entry_end,
        "rr": config.rr,
        "tp1_ratio": config.tp1_ratio,
        "min_gap_atr_pct": session.min_gap_atr_pct,
        "atr_length": config.atr_length,
        "htf_level_tf_minutes": config.htf_level_tf_minutes,
        "htf_n_left": config.htf_n_left,
        "htf_trade_max_per_session": config.htf_trade_max_per_session,
        "htf_lsi_include_htf_levels": config.htf_lsi_include_htf_levels,
        "htf_lsi_reference_levels": ",".join(config.htf_lsi_reference_levels),
        "data_sweep_min_daily_atr_pct": config.data_sweep_min_daily_atr_pct,
        "lsi_fvg_window_left": config.lsi_fvg_window_left,
        "lsi_fvg_window_right": config.lsi_fvg_window_right,
        "max_fvg_to_inversion_bars": config.max_fvg_to_inversion_bars,
        "entry_context_gate": config.entry_context_gate,
        "entry_context_min_atr": config.entry_context_min_atr,
        "entry_context_max_atr": config.entry_context_max_atr,
        "pre_holdout_trades": int(summary["pre_holdout"]["total_trades"]),
        "pre_holdout_pf": float(summary["pre_holdout"]["profit_factor"]),
        "pre_holdout_calmar": float(summary["pre_holdout"]["calmar_ratio"]),
        "discovery_trades": int(summary["discovery"]["total_trades"]),
        "discovery_pf": float(summary["discovery"]["profit_factor"]),
        "discovery_avg_r": float(summary["discovery"]["avg_r"]),
        "discovery_calmar": float(summary["discovery"]["calmar_ratio"]),
        "discovery_total_r": float(summary["discovery"]["total_r"]),
        "validation_trades": int(summary["validation"]["total_trades"]),
        "validation_pf": float(summary["validation"]["profit_factor"]),
        "validation_avg_r": float(summary["validation"]["avg_r"]),
        "validation_calmar": float(summary["validation"]["calmar_ratio"]),
        "validation_total_r": float(summary["validation"]["total_r"]),
        "validation_max_dd_r": float(summary["validation"]["max_drawdown_r"]),
    }


def make_regime_gate(df_base: pd.DataFrame) -> Callable[[list], list]:
    lookup = _regime_lookup(build_extended_regime_calendar(df_base), "combined_regime")

    def gate(trades):
        return [
            trade for trade in trades
            if trade.exit_type == 0 or lookup.get(trade.date) not in AVOID_BUCKETS
        ]

    return gate


def apply_gate(trades, gate_fn: Callable[[list], list] | None):
    return gate_fn(trades) if gate_fn is not None else trades


def save_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str))


def write_markdown_report(path: Path, title: str, sections: list[tuple[str, list[dict]]]) -> None:
    lines = [f"# {title}", ""]
    for section_title, rows in sections:
        lines.append(f"## {section_title}")
        lines.append("")
        if not rows:
            lines.append("No rows.")
            lines.append("")
            continue
        lines.append("| Label | Gate | Disc PF | Disc Avg R | Val PF | Val Avg R | Val Calmar | Trades |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in rows:
            lines.append(
                f"| {row['label']} | {row['gate']} | "
                f"{row['discovery_pf']:.3f} | {row['discovery_avg_r']:.3f} | "
                f"{row['validation_pf']:.3f} | {row['validation_avg_r']:.3f} | "
                f"{row['validation_calmar']:.3f} | {row['validation_trades']} |"
            )
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def load_shortlist_config(path: Path | None) -> StrategyConfig:
    if path is None or not path.exists():
        return build_config()
    payload = json.loads(path.read_text())
    if isinstance(payload, list):
        row = payload[0]
    else:
        row = payload
    raw_htf_ref_levels = row.get("htf_lsi_reference_levels", ())
    if isinstance(raw_htf_ref_levels, str):
        htf_ref_levels = tuple(level for level in raw_htf_ref_levels.split(",") if level)
    else:
        htf_ref_levels = tuple(raw_htf_ref_levels)
    raw_include_htf = row.get("htf_lsi_include_htf_levels", True)
    if isinstance(raw_include_htf, str):
        include_htf_levels = raw_include_htf.strip().lower() not in {"", "0", "false", "no"}
    else:
        include_htf_levels = bool(raw_include_htf)
    return build_config(
        direction_filter=row.get("direction_filter", "both"),
        entry_mode=row.get("entry_mode", "fvg_limit"),
        entry_start=row.get("entry_start", "08:30"),
        entry_end=row.get("entry_end", "15:00"),
        rr=float(row.get("rr", 2.0)),
        tp1_ratio=float(row.get("tp1_ratio", 0.5)),
        min_gap_atr_pct=float(row.get("min_gap_atr_pct", 3.0)),
        atr_length=int(row.get("atr_length", 14)),
        htf_level_tf_minutes=int(row.get("htf_level_tf_minutes", 60)),
        htf_n_left=int(row.get("htf_n_left", 5)),
        htf_trade_max_per_session=int(row.get("htf_trade_max_per_session", 1)),
        htf_lsi_include_htf_levels=include_htf_levels,
        htf_lsi_reference_levels=htf_ref_levels,
        lsi_fvg_window_left=int(row.get("lsi_fvg_window_left", 20)),
        lsi_fvg_window_right=int(row.get("lsi_fvg_window_right", 5)),
        max_fvg_to_inversion_bars=int(row.get("max_fvg_to_inversion_bars", 0)),
        entry_context_gate=row.get("entry_context_gate", ""),
        entry_context_min_atr=float(row.get("entry_context_min_atr", 0.0)),
        entry_context_max_atr=float(row.get("entry_context_max_atr", 0.0)),
        name=row.get("label", "NQ NY HTF_LSI Loaded"),
    )


def config_to_dict(config: StrategyConfig) -> dict:
    return dataclasses.asdict(config)
