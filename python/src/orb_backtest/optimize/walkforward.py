"""Walk-forward optimization with rolling or anchored windows."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import pandas as pd
from dateutil.relativedelta import relativedelta

from ..config import StrategyConfig, with_overrides
from ..engine.simulator import run_backtest, build_maps, build_signal_cache, TradeResult
from ..results.metrics import compute_metrics
from .grid import generate_param_grid
from .objectives import OBJECTIVE_MAP, get_objective_value
from .parallel import run_sweep, _load_or_build_signal_cache


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
    df_1m: pd.DataFrame | None = None,
    df_30s: pd.DataFrame | None = None,
    df_1s: pd.DataFrame | None = None,
    max_dd_r: float | None = None,
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

    configs = generate_param_grid(base_config, param_ranges)
    folds: list[WalkForwardFold] = []
    all_oos_trades: list[TradeResult] = []

    # Pre-build full-range signal cache and maps once — reused across all IS folds.
    # Key invariant: we use the FULL df (not sliced), with start_date filtering
    # handled inside the engine. This avoids index-alignment issues per fold.
    # Saves ~120s x N_folds of redundant signal computation.
    print("[wf] Pre-building full-range signal cache and maps...")
    full_maps = build_maps(df, df_1m, df_30s, df_1s)
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
        is_df_30s = df_30s.loc[warmup_start:window.is_end] if df_30s is not None else None
        is_df_1s = df_1s.loc[warmup_start:window.is_end] if df_1s is not None else None
        if gate_factory is not None:
            # gate_factory creates a function that indexes into the DataFrame by
            # signal_bar position. If we pass the full df to run_sweep, signal_bar
            # values correspond to full-df positions, not is_df positions — the gate
            # would look up the wrong rows. Fall back to IS-sliced sweep for safety.
            is_results = run_sweep(
                is_df, configs, n_workers=n_workers, start_date=window.is_start,
                df_1m=is_df_1m, df_30s=is_df_30s, df_1s=is_df_1s,
            )
        else:
            # No gate_factory — safe to pass full df with pre-built caches.
            # IS-window filtering is done post-sweep by date string comparison.
            is_results = run_sweep(
                df, configs, n_workers=n_workers, start_date=window.is_start,
                df_1m=df_1m, df_30s=df_30s, df_1s=df_1s,
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

        oos_df_1m = df_1m.loc[oos_warmup_start:window.oos_end] if df_1m is not None else None
        oos_df_30s = df_30s.loc[oos_warmup_start:window.oos_end] if df_30s is not None else None
        oos_df_1s = df_1s.loc[oos_warmup_start:window.oos_end] if df_1s is not None else None
        oos_maps = build_maps(oos_df, oos_df_1m, oos_df_30s, oos_df_1s)
        oos_sig = build_signal_cache(oos_df, [best_config])
        oos_trades_all = run_backtest(
            oos_df, best_config, start_date=window.oos_start,
            df_1m=oos_df_1m, df_30s=oos_df_30s, df_1s=oos_df_1s,
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


def recency_analysis(
    wf_result: WalkForwardResult,
    recent_folds: int = 8,
) -> dict:
    """Compare recent OOS performance vs historical average.

    Splits the WF folds into recent (last N) and historical (everything else),
    computes metrics on each subset, and checks for param stability and
    performance degradation.

    Args:
        wf_result: Completed walk-forward result.
        recent_folds: Number of most-recent folds to treat as "recent".

    Returns:
        Dict with:
        - recent_metrics: compute_metrics() on recent OOS trades
        - historical_metrics: compute_metrics() on older OOS trades
        - param_stability: std dev of each swept param across recent folds
        - degradation_flag: True if recent Calmar < 50% of historical
        - recent_folds_used: actual number of recent folds used
        - historical_folds_used: actual number of historical folds used
    """
    import numpy as np

    folds = wf_result.folds
    n = min(recent_folds, len(folds))

    historical = folds[:-n] if n < len(folds) else []
    recent = folds[-n:]

    # Collect OOS trades for each group
    recent_trades = []
    for f in recent:
        recent_trades.extend(f.oos_trades)
    recent_trades.sort(key=lambda t: t.date)

    historical_trades = []
    for f in historical:
        historical_trades.extend(f.oos_trades)
    historical_trades.sort(key=lambda t: t.date)

    recent_m = compute_metrics(recent_trades)
    historical_m = compute_metrics(historical_trades) if historical_trades else None

    # Param stability across recent folds
    param_stability = {}
    if recent:
        param_names = list(recent[0].best_params.keys())
        for p in param_names:
            vals = [f.best_params.get(p, 0.0) for f in recent]
            param_stability[p] = float(np.std(vals, ddof=1)) if len(vals) > 1 else 0.0

    # Degradation flag: recent Calmar < 50% of historical
    degradation_flag = False
    if historical_m and historical_m.get("calmar_ratio", 0) > 0:
        recent_calmar = recent_m.get("calmar_ratio", 0)
        hist_calmar = historical_m["calmar_ratio"]
        degradation_flag = recent_calmar < hist_calmar * 0.5

    return {
        "recent_metrics": recent_m,
        "historical_metrics": historical_m,
        "param_stability": param_stability,
        "degradation_flag": degradation_flag,
        "recent_folds_used": len(recent),
        "historical_folds_used": len(historical),
    }


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
