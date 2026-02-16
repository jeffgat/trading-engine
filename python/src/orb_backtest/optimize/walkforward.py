"""Walk-forward optimization with rolling or anchored windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd
from dateutil.relativedelta import relativedelta

from ..config import StrategyConfig, with_overrides
from ..engine.simulator import run_backtest, TradeResult
from ..results.metrics import compute_metrics
from .grid import generate_param_grid
from .objectives import OBJECTIVE_MAP, get_objective_value
from .parallel import run_sweep


# Days of warmup data loaded before IS start for ATR initialization
WARMUP_DAYS = 30


@dataclass
class WalkForwardWindow:
    """A single walk-forward window definition."""
    is_start: str  # YYYY-MM-DD
    is_end: str
    oos_start: str
    oos_end: str


@dataclass
class WalkForwardFold:
    """Results for a single walk-forward fold."""
    fold_index: int
    is_start: str
    is_end: str
    oos_start: str
    oos_end: str
    best_params: dict[str, float]
    best_config: StrategyConfig
    is_metrics: dict
    is_objective_value: float
    oos_metrics: dict
    oos_objective_value: float
    oos_trades: list[TradeResult]


@dataclass
class WalkForwardResult:
    """Complete walk-forward analysis result."""
    folds: list[WalkForwardFold]
    combined_oos_trades: list[TradeResult]
    combined_oos_metrics: dict
    walk_forward_efficiency: float
    is_months: int
    oos_months: int
    step_months: int
    anchored: bool
    objective: str


def generate_windows(
    start: str,
    end: str,
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
    anchored: bool = False,
) -> list[WalkForwardWindow]:
    """Generate rolling or anchored walk-forward windows.

    Args:
        start: Data start date (YYYY-MM-DD).
        end: Data end date (YYYY-MM-DD).
        is_months: In-sample window length in months.
        oos_months: Out-of-sample window length in months.
        step_months: Step size for rolling forward.
        anchored: If True, IS window starts from 'start' and expands.

    Returns:
        List of WalkForwardWindow instances.
    """
    data_start = datetime.strptime(start, "%Y-%m-%d")
    data_end = datetime.strptime(end, "%Y-%m-%d")
    anchor_start = data_start

    windows = []
    is_start = data_start

    while True:
        if anchored:
            current_is_start = anchor_start
        else:
            current_is_start = is_start

        is_end_dt = is_start + relativedelta(months=is_months)
        oos_start_dt = is_end_dt
        oos_end_dt = oos_start_dt + relativedelta(months=oos_months)

        if oos_end_dt > data_end:
            break

        windows.append(WalkForwardWindow(
            is_start=current_is_start.strftime("%Y-%m-%d"),
            is_end=is_end_dt.strftime("%Y-%m-%d"),
            oos_start=oos_start_dt.strftime("%Y-%m-%d"),
            oos_end=oos_end_dt.strftime("%Y-%m-%d"),
        ))

        is_start += relativedelta(months=step_months)

    return windows


def run_walkforward(
    df: pd.DataFrame,
    base_config: StrategyConfig,
    param_ranges: dict[str, list],
    is_months: int = 12,
    oos_months: int = 3,
    step_months: int = 3,
    anchored: bool = False,
    objective: str = "sharpe",
    n_workers: int | None = None,
    start_date: str | None = None,
    progress_fn: Callable | None = None,
    gate_fn: Callable[[list[TradeResult]], list[TradeResult]] | None = None,
    gate_factory: Callable[[pd.DataFrame], Callable[[list[TradeResult]], list[TradeResult]]] | None = None,
) -> WalkForwardResult:
    """Run walk-forward optimization.

    For each fold:
    1. Slice df to IS window (with warmup before IS start)
    2. Run grid sweep on IS data
    3. Apply gate to each result's trades (if provided)
    4. Recompute metrics on gated trades, pick best by objective
    5. Run best config on OOS window
    6. Apply gate to OOS trades
    7. Store FoldResult

    After all folds: combine OOS trades chronologically, compute combined
    metrics, WF efficiency = avg(OOS obj) / avg(IS obj).

    Args:
        df: Full OHLCV DataFrame (should cover entire range + warmup).
        base_config: Base strategy configuration.
        param_ranges: Dict mapping param names to lists of values to sweep.
        is_months: In-sample window length.
        oos_months: Out-of-sample window length.
        step_months: Roll-forward step.
        anchored: Expanding IS window.
        objective: Optimization objective (one of VALID_OBJECTIVES).
        n_workers: Parallel workers for grid search within each fold.
        start_date: Data start for window generation.
        progress_fn: Optional callback(fold_idx, total_folds, status).
        gate_fn: Optional post-trade filter (for non-index-dependent gates).
            Signature: (trades: list[TradeResult]) -> list[TradeResult].
        gate_factory: Optional factory that creates a gate_fn from a DataFrame slice.
            Use this instead of gate_fn when the gate depends on signal_bar indices
            (e.g., SMA gate), since each fold uses a different df slice.
            Signature: (df: DataFrame) -> (trades: list[TradeResult]) -> list[TradeResult].

    Returns:
        WalkForwardResult with per-fold and combined OOS metrics.
    """
    obj_key = OBJECTIVE_MAP[objective]

    wf_start = start_date or df.index[0].strftime("%Y-%m-%d")
    data_end = df.index[-1].strftime("%Y-%m-%d")

    windows = generate_windows(
        wf_start, data_end, is_months, oos_months, step_months, anchored
    )

    if not windows:
        raise ValueError(
            f"No valid walk-forward folds for range {wf_start} to {data_end} "
            f"with IS={is_months}m, OOS={oos_months}m, step={step_months}m"
        )

    configs = generate_param_grid(base_config, param_ranges)
    folds: list[WalkForwardFold] = []
    all_oos_trades: list[TradeResult] = []

    for fold_idx, window in enumerate(windows):
        if progress_fn:
            progress_fn(fold_idx, len(windows), "optimizing IS")

        # 1. Slice df to IS window with warmup
        warmup_start = (
            datetime.strptime(window.is_start, "%Y-%m-%d")
            - pd.Timedelta(days=WARMUP_DAYS)
        ).strftime("%Y-%m-%d")
        is_df = df.loc[warmup_start:window.is_end]

        # 2. Run grid sweep on IS slice
        is_results = run_sweep(
            is_df, configs, n_workers=n_workers, start_date=window.is_start
        )

        # Build per-fold gate from factory (indices are relative to is_df)
        is_gate = None
        if gate_factory is not None:
            is_gate = gate_factory(is_df)
        elif gate_fn is not None:
            is_gate = gate_fn

        # 3-4. Apply gate, compute metrics, pick best
        best_config = None
        best_is_val = float("-inf")
        best_is_metrics = {}

        for config, trades in is_results:
            # Filter trades to IS window
            is_trades = [
                t for t in trades
                if window.is_start <= t.date < window.is_end
            ]
            # Apply gate if provided
            if is_gate is not None:
                is_trades = is_gate(is_trades)

            m = compute_metrics(is_trades)
            val = get_objective_value(m, objective, base_config.risk_usd)
            if val > best_is_val and m["total_trades"] > 0:
                best_is_val = val
                best_config = config
                best_is_metrics = m

        if best_config is None:
            # No trades in IS — use base config
            best_config = base_config
            best_is_val = 0.0

        # 5. Test best config on OOS period (with warmup)
        if progress_fn:
            progress_fn(fold_idx, len(windows), "testing OOS")

        oos_warmup_start = (
            datetime.strptime(window.oos_start, "%Y-%m-%d")
            - pd.Timedelta(days=WARMUP_DAYS)
        ).strftime("%Y-%m-%d")
        oos_df = df.loc[oos_warmup_start:window.oos_end]

        oos_trades_all = run_backtest(oos_df, best_config, start_date=window.oos_start)
        oos_trades = [
            t for t in oos_trades_all
            if window.oos_start <= t.date < window.oos_end
        ]

        # 6. Apply gate to OOS trades (built from oos_df for correct indices)
        oos_gate = None
        if gate_factory is not None:
            oos_gate = gate_factory(oos_df)
        elif gate_fn is not None:
            oos_gate = gate_fn
        if oos_gate is not None:
            oos_trades = oos_gate(oos_trades)

        oos_metrics = compute_metrics(oos_trades)
        oos_val = get_objective_value(oos_metrics, objective, base_config.risk_usd)

        # Extract best params
        best_params = _extract_swept_params(best_config, param_ranges.keys())

        fold = WalkForwardFold(
            fold_index=fold_idx,
            is_start=window.is_start,
            is_end=window.is_end,
            oos_start=window.oos_start,
            oos_end=window.oos_end,
            best_params=best_params,
            best_config=best_config,
            is_metrics=best_is_metrics,
            is_objective_value=best_is_val,
            oos_metrics=oos_metrics,
            oos_objective_value=oos_val,
            oos_trades=oos_trades,
        )
        folds.append(fold)
        all_oos_trades.extend(oos_trades)

        if progress_fn:
            progress_fn(fold_idx, len(windows), "done")

    # Sort all OOS trades by date
    all_oos_trades.sort(key=lambda t: t.date)
    combined_metrics = compute_metrics(all_oos_trades)

    # Walk-forward efficiency: avg OOS objective / avg IS objective
    avg_is = sum(f.is_objective_value for f in folds) / len(folds) if folds else 0
    avg_oos = sum(f.oos_objective_value for f in folds) / len(folds) if folds else 0
    wf_efficiency = avg_oos / avg_is if avg_is != 0 else 0.0

    return WalkForwardResult(
        folds=folds,
        combined_oos_trades=all_oos_trades,
        combined_oos_metrics=combined_metrics,
        walk_forward_efficiency=wf_efficiency,
        is_months=is_months,
        oos_months=oos_months,
        step_months=step_months,
        anchored=anchored,
        objective=objective,
    )


def _extract_swept_params(config: StrategyConfig, param_names) -> dict[str, float]:
    """Extract swept parameter values from a config."""
    params = {}
    for name in param_names:
        # Check session-prefixed params
        for sess_prefix in ("ny_", "asia_", "ldn_"):
            if name.startswith(sess_prefix):
                attr = name[len(sess_prefix):]
                sess_name = sess_prefix.rstrip("_").upper()
                for s in config.sessions:
                    if s.name.upper() == sess_name:
                        params[name] = getattr(s, attr, 0.0)
                break
        else:
            params[name] = getattr(config, name, 0.0)
    return params
