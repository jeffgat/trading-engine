"""Parameter grid generation for IFVG strategy sweeps."""

from __future__ import annotations

import itertools

from ..config import IFVGConfig, with_overrides


def linspace_range(start: float, stop: float, step: float) -> list[float]:
    """Generate float range [start, stop] with step, including endpoints."""
    values = []
    v = start
    while v <= stop + step * 0.01:
        values.append(round(v, 6))
        v += step
    return values


def generate_param_grid(
    base_config: IFVGConfig,
    param_ranges: dict[str, list],
) -> list[IFVGConfig]:
    """Generate all parameter combinations via cartesian product.

    Args:
        base_config: Base IFVG configuration.
        param_ranges: Dict mapping param names to lists of values.
            Supports dot-notation for killzone params:
                asia_use_high_sweeps=[True, False]

    Returns:
        List of IFVGConfig, one per combination.

    Example::

        generate_param_grid(base, {
            'rr': [1.5, 2.0, 2.5],
            'min_gap_atr_pct': [1.5, 2.25, 3.0],
        })
        → 3 * 3 = 9 configs
    """
    param_names = list(param_ranges.keys())
    param_values = list(param_ranges.values())

    configs = []
    for combo in itertools.product(*param_values):
        overrides = dict(zip(param_names, combo))
        configs.append(with_overrides(base_config, **overrides))

    return configs
