"""Latin Hypercube Sampling for parameter-space Monte Carlo."""

from __future__ import annotations

from scipy.stats import qmc
import numpy as np

from ..config import StrategyConfig, with_overrides
from .bayesian import BayesianParam


def generate_lhs_configs(
    base_config: StrategyConfig,
    params: list[BayesianParam],
    n_samples: int = 200,
    seed: int | None = None,
) -> list[StrategyConfig]:
    """Generate LHS-sampled configurations for parameter sensitivity analysis.

    Args:
        base_config: Base strategy configuration.
        params: Parameter definitions with bounds.
        n_samples: Number of LHS samples to generate.
        seed: Random seed.

    Returns:
        List of StrategyConfig instances.
    """
    sampler = qmc.LatinHypercube(d=len(params), seed=seed)
    sample = sampler.random(n=n_samples)

    # Scale to parameter bounds
    lower = [p.low for p in params]
    upper = [p.high for p in params]
    scaled = qmc.scale(sample, lower, upper)

    configs = []
    for row in scaled:
        overrides = {}
        for j, p in enumerate(params):
            val = float(row[j])
            if p.step is not None:
                # Snap to nearest step
                val = round(round((val - p.low) / p.step) * p.step + p.low, 10)
                val = max(p.low, min(p.high, val))
            overrides[p.name] = val
        configs.append(with_overrides(base_config, **overrides))

    return configs
