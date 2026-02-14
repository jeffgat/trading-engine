"""Parameter grid generation for sweep optimization."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from typing import Any

import numpy as np

from ..config import StrategyConfig, SessionConfig, with_overrides


def generate_param_grid(
    base_config: StrategyConfig,
    param_ranges: dict[str, list],
) -> list[StrategyConfig]:
    """Generate all combinations of parameter overrides.

    Args:
        base_config: Base strategy configuration.
        param_ranges: Dict mapping param names to lists of values.
            Supports session-prefixed params (e.g., 'ny_stop_atr_pct').

    Returns:
        List of StrategyConfig instances, one per combination.

    Example:
        configs = generate_param_grid(base, {
            'rr': [2.0, 2.5, 3.0],
            'ny_stop_atr_pct': [10, 12, 15, 18, 20],
            'ny_min_gap_atr_pct': [1.0, 1.5, 1.75, 2.0],
        })
        # Produces 3 * 5 * 4 = 60 configs
    """
    if not param_ranges:
        return [base_config]

    keys = list(param_ranges.keys())
    value_lists = [param_ranges[k] for k in keys]

    configs = []
    for values in product(*value_lists):
        overrides = dict(zip(keys, values))
        configs.append(with_overrides(base_config, **overrides))

    return configs


def linspace_range(start: float, stop: float, step: float) -> list[float]:
    """Generate a range of float values [start, stop] with given step.

    Unlike numpy.arange, this includes the stop value if it aligns with the step.
    Values are rounded to avoid floating-point artifacts.
    """
    n_steps = int(round((stop - start) / step)) + 1
    return [round(start + i * step, 10) for i in range(n_steps)]


def describe_grid(param_ranges: dict[str, list]) -> str:
    """Human-readable description of a parameter grid."""
    lines = []
    total = 1
    for key, values in param_ranges.items():
        n = len(values)
        total *= n
        if len(values) <= 6:
            vals_str = ", ".join(str(v) for v in values)
        else:
            vals_str = f"{values[0]} to {values[-1]} ({n} values)"
        lines.append(f"  {key}: [{vals_str}]")

    header = f"Grid: {total:,} combinations"
    return header + "\n" + "\n".join(lines)
