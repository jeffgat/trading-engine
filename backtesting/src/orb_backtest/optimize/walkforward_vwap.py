"""Walk-forward optimization for VWAP Reversion strategies.

Mirrors walkforward.py but uses:
- VWAPStrategyConfig / with_vwap_overrides instead of StrategyConfig / with_overrides
- run_vwap_backtest / build_vwap_signal_cache instead of run_backtest / build_signal_cache
- run_vwap_sweep / _load_or_build_vwap_signal_cache instead of run_sweep / _load_or_build_signal_cache
"""

from __future__ import annotations

from datetime import datetime
from itertools import product
from typing import Callable

import pandas as pd

from ..vwap_config import VWAPStrategyConfig, with_vwap_overrides
from ..engine.vwap_simulator import run_vwap_backtest, build_vwap_signal_cache
from ..engine.simulator import TradeResult, build_maps
from ..results.metrics import compute_metrics
from .objectives import OBJECTIVE_MAP, get_objective_value
from .parallel_vwap import run_vwap_sweep, _load_or_build_vwap_signal_cache

# Shared types and utilities from the ORB walk-forward module
from .walkforward import (
    WalkForwardWindow,
    WalkForwardFold,
    WalkForwardResult,
    generate_windows,
    recency_analysis,
    WARMUP_DAYS,
)


def _generate_vwap_param_grid(
    base_config: VWAPStrategyConfig,
    param_ranges: dict[str, list],
) -> list[VWAPStrategyConfig]:
    """Generate all combinations of parameter overrides for VWAP configs.

    Mirrors generate_param_grid() from grid.py but uses with_vwap_overrides
    instead of with_overrides.

    Args:
        base_config: Base VWAP strategy configuration.
        param_ranges: Dict mapping param names to lists of values.
            Supports session-prefixed params (e.g., 'ny_deviation_atr_pct').

    Returns:
        List of VWAPStrategyConfig instances, one per combination.
    """
    if not param_ranges:
        return [base_config]

    keys = list(param_ranges.keys())
    value_lists = [param_ranges[k] for k in keys]

    configs = []
    for values in product(*value_lists):
        overrides = dict(zip(keys, values))
        configs.append(with_vwap_overrides(base_config, **overrides))

    return configs


def run_walkforward_vwap(
    df: pd.DataFrame,
    df_1m: pd.DataFrame | None,
    base_config: VWAPStrategyConfig,
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
    max_dd_r: float | None = None,
) -> WalkForwardResult:
    """Run walk-forward optimization for a VWAP Reversion strategy.

    For each fold:
    1. Slice df to IS window (with warmup before IS start)
    2. Run VWAP grid sweep on IS data
    3. Apply gate to each result's trades (if provided)
    4. Recompute metrics on gated trades, pick best by objective
    5. Run best config on OOS window
    6. Apply gate to OOS trades
    7. Store FoldResult

    After all folds: combine OOS trades chronologically, compute combined
    metrics, WF efficiency = avg(OOS obj) / avg(IS obj).

    Args:
        df: Full 5-minute OHLCV DataFrame (should cover entire range + warmup).
        df_1m: Optional 1-minute OHLCV DataFrame for bar magnifier.
            VWAP strategies benefit from 1m resolution for fill/exit simulation.
        base_config: Base VWAP strategy configuration.
        param_ranges: Dict mapping param names to lists of values to sweep.
            Supports session-prefixed params (e.g., 'ny_deviation_atr_pct').
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
        max_dd_r: Maximum allowed drawdown in R-multiples for IS config selection.
            Configs with max_drawdown_r worse (more negative) than this threshold
            are rejected before comparing objectives. E.g., -10.0 rejects any
            IS config with drawdown exceeding 10R.

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

    configs = _generate_vwap_param_grid(base_config, param_ranges)
    folds: list[WalkForwardFold] = []
    all_oos_trades: list[TradeResult] = []

    # Pre-build full-range signal cache and maps once -- reused across all folds.
    # Key invariant: we use the FULL df (not sliced), with start_date filtering
    # handled inside the engine. This avoids index-alignment issues per fold.
    # Saves ~120s x N_folds of redundant signal computation.
    print("[wf-vwap] Pre-building full-range VWAP signal cache and maps...")
    full_maps = build_maps(df, df_1m)
    full_signal_cache = _load_or_build_vwap_signal_cache(df, configs)

    for fold_idx, window in enumerate(windows):
        if progress_fn:
            progress_fn(fold_idx, len(windows), "optimizing IS")

        # 1. Slice df to IS window with warmup
        warmup_start = (
            datetime.strptime(window.is_start, "%Y-%m-%d")
            - pd.Timedelta(days=WARMUP_DAYS)
        ).strftime("%Y-%m-%d")
        is_df = df.loc[warmup_start:window.is_end]

        # 2. Run VWAP grid sweep on IS data.
        is_df_1m = df_1m.loc[warmup_start:window.is_end] if df_1m is not None else None
        if gate_factory is not None:
            # gate_factory creates a function that indexes into the DataFrame by
            # signal_bar position. If we pass the full df to run_vwap_sweep,
            # signal_bar values correspond to full-df positions, not is_df
            # positions -- the gate would look up the wrong rows. Fall back to
            # IS-sliced sweep for safety.
            is_results = run_vwap_sweep(
                is_df, configs, n_workers=n_workers, start_date=window.is_start,
                df_1m=is_df_1m,
            )
        else:
            # No gate_factory -- safe to pass full df with pre-built caches.
            # IS-window filtering uses start_date + end_date to pre-filter candidates.
            is_results = run_vwap_sweep(
                df, configs, n_workers=n_workers,
                start_date=window.is_start, end_date=window.is_end,
                df_1m=df_1m,
                _prebuilt_signal_cache=full_signal_cache, _prebuilt_maps=full_maps,
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
            # DD hard gate: reject configs exceeding max drawdown threshold
            if max_dd_r is not None and m.get("max_drawdown_r", 0) < max_dd_r:
                continue
            val = get_objective_value(m, objective, base_config.risk_usd)
            if val > best_is_val and m["total_trades"] > 0:
                best_is_val = val
                best_config = config
                best_is_metrics = m

        if best_config is None:
            # No trades in IS -- use base config
            best_config = base_config
            best_is_val = 0.0

        # 5. Test best config on OOS period (with warmup)
        if progress_fn:
            progress_fn(fold_idx, len(windows), "testing OOS")

        if gate_factory is None:
            # Reuse full-range caches -- no index-dependent gate, so full df
            # with start_date + end_date bounds is safe and avoids rebuilding
            # maps/signal_cache per fold.
            oos_trades_all = run_vwap_backtest(
                df, best_config,
                start_date=window.oos_start, end_date=window.oos_end,
                df_1m=df_1m,
                _maps=full_maps, _signal_cache=full_signal_cache,
            )
        else:
            # gate_factory depends on df-relative indices -- must build
            # OOS-scoped maps and signal cache from the sliced DataFrame.
            oos_warmup_start = (
                datetime.strptime(window.oos_start, "%Y-%m-%d")
                - pd.Timedelta(days=WARMUP_DAYS)
            ).strftime("%Y-%m-%d")
            oos_df = df.loc[oos_warmup_start:window.oos_end]

            oos_df_1m = df_1m.loc[oos_warmup_start:window.oos_end] if df_1m is not None else None
            oos_maps = build_maps(oos_df, oos_df_1m)
            oos_sig = build_vwap_signal_cache(oos_df, [best_config])
            oos_trades_all = run_vwap_backtest(
                oos_df, best_config, start_date=window.oos_start,
                df_1m=oos_df_1m,
                _maps=oos_maps, _signal_cache=oos_sig,
            )

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
        best_params = _extract_swept_params_vwap(best_config, param_ranges.keys())

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


def _extract_swept_params_vwap(
    config: VWAPStrategyConfig,
    param_names,
) -> dict[str, float]:
    """Extract swept parameter values from a VWAP config.

    Handles both top-level VWAPStrategyConfig fields (rr, tp1_ratio,
    atr_length, tp2_mode, direction_filter, etc.) and session-prefixed
    params (ny_deviation_atr_pct, asia_stop_atr_pct, ldn_rejection_mode, etc.).

    Session prefixes supported: ny_, asia_, ldn_.
    """
    params = {}
    for name in param_names:
        # Check session-prefixed params (e.g., ny_deviation_atr_pct)
        for sess_prefix in ("ny_", "asia_", "ldn_"):
            if name.startswith(sess_prefix):
                attr = name[len(sess_prefix):]
                sess_name = sess_prefix.rstrip("_").upper()
                for s in config.sessions:
                    if s.name.upper() == sess_name:
                        params[name] = getattr(s, attr, 0.0)
                break
        else:
            # Top-level VWAPStrategyConfig attribute
            params[name] = getattr(config, name, 0.0)
    return params
