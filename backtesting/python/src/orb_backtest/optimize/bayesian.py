"""Bayesian optimization using Optuna (TPE or GP sampler)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from ..config import StrategyConfig, with_overrides
from ..engine.simulator import run_backtest, build_maps
from ..results.metrics import compute_metrics
from .objectives import OBJECTIVE_MAP
from .parallel import _load_or_build_signal_cache


@dataclass
class BayesianParam:
    """Definition of a single parameter to optimize."""
    name: str
    low: float
    high: float
    step: float | None = None


@dataclass
class BayesianTrial:
    """Result of a single Bayesian trial."""
    trial_number: int
    params: dict[str, float]
    config: StrategyConfig
    metrics: dict
    objective_value: float


@dataclass
class BayesianResult:
    """Complete Bayesian optimization result."""
    trials: list[BayesianTrial]
    best_trial: BayesianTrial
    param_definitions: list[BayesianParam]
    n_trials: int
    sampler: str
    objective: str


def parse_bayesian_param(spec: str) -> BayesianParam:
    """Parse parameter spec like 'rr=1.5:4.0' or 'rr=1.5:4.0:0.5'."""
    name, range_str = spec.split("=", 1)
    parts = range_str.split(":")
    if len(parts) == 2:
        return BayesianParam(name=name, low=float(parts[0]), high=float(parts[1]))
    elif len(parts) == 3:
        return BayesianParam(
            name=name, low=float(parts[0]), high=float(parts[1]), step=float(parts[2])
        )
    else:
        raise ValueError(f"Invalid param spec: {spec}. Use name=low:high or name=low:high:step")


def run_bayesian(
    df: pd.DataFrame,
    base_config: StrategyConfig,
    params: list[BayesianParam],
    n_trials: int = 100,
    objective: str = "sharpe",
    sampler: str = "tpe",
    start_date: str | None = None,
    seed: int | None = None,
    progress_fn: Callable | None = None,
    df_1m: pd.DataFrame | None = None,
) -> BayesianResult:
    """Run Bayesian optimization over parameter space.

    Args:
        df: OHLCV DataFrame.
        base_config: Base strategy configuration.
        params: Parameter definitions to optimize.
        n_trials: Number of trials.
        objective: Optimization objective (sharpe, pnl, profit_factor, calmar, avg_r).
        sampler: Sampler type (tpe or gp).
        start_date: Only count trades on/after this date.
        seed: Random seed for reproducibility.
        progress_fn: Optional callback(trial_num, total, best_val, trial_params).
        df_1m: Optional 1-minute DataFrame for bar magnifier fill simulation.

    Returns:
        BayesianResult with all trials and best trial.
    """
    import optuna

    optuna.logging.set_verbosity(optuna.logging.WARNING)

    obj_key = OBJECTIVE_MAP[objective]
    trials_list: list[BayesianTrial] = []
    best_value = float("-inf")

    # Pre-build maps and signal cache once — reused across all Optuna trials.
    # For 300 trials × ~650ms signal overhead = ~3.25 min saved.
    _maps = build_maps(df, df_1m, None, None)
    _signal_cache = _load_or_build_signal_cache(df, [base_config])

    def optuna_objective(trial: optuna.Trial) -> float:
        nonlocal best_value

        overrides = {}
        for p in params:
            if p.step is not None:
                val = trial.suggest_float(p.name, p.low, p.high, step=p.step)
            else:
                val = trial.suggest_float(p.name, p.low, p.high)
            overrides[p.name] = val

        config = with_overrides(base_config, **overrides)
        trades = run_backtest(df, config, start_date=start_date, df_1m=df_1m,
                              _maps=_maps, _signal_cache=_signal_cache)
        metrics = compute_metrics(trades)

        obj_val = metrics.get(obj_key, 0.0)

        bt = BayesianTrial(
            trial_number=trial.number + 1,
            params=overrides,
            config=config,
            metrics=metrics,
            objective_value=obj_val,
        )
        trials_list.append(bt)

        if obj_val > best_value:
            best_value = obj_val

        if progress_fn:
            progress_fn(trial.number + 1, n_trials, best_value, overrides)

        return obj_val

    # Create sampler
    if sampler == "gp":
        optuna_sampler = optuna.samplers.GPSampler(seed=seed)
    else:
        optuna_sampler = optuna.samplers.TPESampler(seed=seed)

    study = optuna.create_study(direction="maximize", sampler=optuna_sampler)
    study.optimize(optuna_objective, n_trials=n_trials)

    # Sort trials by number
    trials_list.sort(key=lambda t: t.trial_number)

    best_trial = max(trials_list, key=lambda t: t.objective_value)

    return BayesianResult(
        trials=trials_list,
        best_trial=best_trial,
        param_definitions=params,
        n_trials=n_trials,
        sampler=sampler,
        objective=objective,
    )
