"""Walk-forward optimization using the qualifying-move engine."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

import pandas as pd

from ..config import StrategyConfig, with_overrides
from ..engine.qualifying_move import run_backtest_qm
from ..engine.simulator import TradeResult, build_maps, build_signal_cache
from ..results.metrics import compute_metrics
from .grid import generate_param_grid
from .objectives import OBJECTIVE_MAP, get_objective_value
from .parallel import _load_or_build_signal_cache
from .parallel_qm import run_sweep_qm
from .walkforward import (
    WARMUP_DAYS,
    WalkForwardWindow,
    WalkForwardFold,
    WalkForwardResult,
    generate_windows,
    recency_analysis,
    _extract_swept_params,
)


def run_walkforward_qm(
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
    df_1m: pd.DataFrame | None = None,
    max_dd_r: float | None = None,
) -> WalkForwardResult:
    """Run walk-forward optimization using the qualifying-move engine.

    Same interface as walkforward.run_walkforward but routes through
    run_backtest_qm and run_sweep_qm.
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

    # Pre-build full-range maps and signal cache once — reused across all folds.
    # This avoids rebuilding maps (expensive) and recomputing signals (slow) on
    # every IS sweep and OOS evaluation.
    print("[wf_qm] Pre-building full-range signal cache and maps...")
    full_maps = build_maps(df, df_1m, None, None)
    full_signal_cache = _load_or_build_signal_cache(df, configs)

    for fold_idx, window in enumerate(windows):
        if progress_fn:
            progress_fn(fold_idx, len(windows), "optimizing IS")

        # 1. Slice df to IS window with warmup
        warmup_start = (
            datetime.strptime(window.is_start, "%Y-%m-%d")
            - pd.Timedelta(days=WARMUP_DAYS)
        ).strftime("%Y-%m-%d")
        is_df = df.loc[warmup_start:window.is_end]

        # 2. Run grid sweep on IS data.
        is_df_1m = df_1m.loc[warmup_start:window.is_end] if df_1m is not None else None
        if gate_factory is not None:
            # gate_factory creates a function that indexes into the DataFrame by
            # signal_bar position. If we pass the full df to run_sweep, signal_bar
            # values correspond to full-df positions, not is_df positions — the gate
            # would look up the wrong rows. Fall back to IS-sliced sweep for safety.
            is_results = run_sweep_qm(
                is_df, configs, n_workers=n_workers,
                start_date=window.is_start,
                df_1m=is_df_1m,
            )
        else:
            # No gate_factory — safe to pass full df with pre-built caches.
            # IS-window filtering uses start_date + end_date to pre-filter candidates.
            is_results = run_sweep_qm(
                df, configs, n_workers=n_workers,
                start_date=window.is_start, end_date=window.is_end,
                df_1m=df_1m,
                _prebuilt_maps=full_maps,
                _prebuilt_signal_cache=full_signal_cache,
            )

        # Build per-fold gate
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
            is_trades = [
                t for t in trades
                if window.is_start <= t.date < window.is_end
            ]
            if is_gate is not None:
                is_trades = is_gate(is_trades)

            m = compute_metrics(is_trades)
            if max_dd_r is not None and m.get("max_drawdown_r", 0) < max_dd_r:
                continue
            val = get_objective_value(m, objective, base_config.risk_usd)
            if val > best_is_val and m["total_trades"] > 0:
                best_is_val = val
                best_config = config
                best_is_metrics = m

        if best_config is None:
            best_config = base_config
            best_is_val = 0.0

        # 5. Test best config on OOS period
        if progress_fn:
            progress_fn(fold_idx, len(windows), "testing OOS")

        if gate_factory is None:
            # Reuse full-range caches — no index-dependent gate, so full df
            # with start_date + end_date bounds is safe and avoids rebuilding
            # maps/signal_cache per fold.
            oos_trades_all = run_backtest_qm(
                df, best_config,
                start_date=window.oos_start, end_date=window.oos_end,
                df_1m=df_1m,
                _maps=full_maps, _signal_cache=full_signal_cache,
            )
        else:
            # gate_factory depends on df-relative indices — must build
            # OOS-scoped maps and signal cache from the sliced DataFrame.
            oos_warmup_start = (
                datetime.strptime(window.oos_start, "%Y-%m-%d")
                - pd.Timedelta(days=WARMUP_DAYS)
            ).strftime("%Y-%m-%d")
            oos_df = df.loc[oos_warmup_start:window.oos_end]

            oos_df_1m = df_1m.loc[oos_warmup_start:window.oos_end] if df_1m is not None else None
            oos_maps = build_maps(oos_df, oos_df_1m, None, None)
            oos_sig = build_signal_cache(oos_df, [best_config])
            oos_trades_all = run_backtest_qm(
                oos_df, best_config, start_date=window.oos_start, df_1m=oos_df_1m,
                _maps=oos_maps, _signal_cache=oos_sig,
            )

        oos_trades = [
            t for t in oos_trades_all
            if window.oos_start <= t.date < window.oos_end
        ]

        # 6. Apply gate to OOS trades
        oos_gate = None
        if gate_factory is not None:
            oos_gate = gate_factory(oos_df)
        elif gate_fn is not None:
            oos_gate = gate_fn
        if oos_gate is not None:
            oos_trades = oos_gate(oos_trades)

        oos_metrics = compute_metrics(oos_trades)
        oos_val = get_objective_value(oos_metrics, objective, base_config.risk_usd)

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

    # Walk-forward efficiency
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
