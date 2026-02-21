"""Parameter stability analysis across walk-forward folds."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .walkforward import WalkForwardResult


@dataclass
class ParamStability:
    """Stability metrics for a single parameter across WF folds."""
    name: str
    values: list[float]
    mode: float
    mode_frequency: int
    stability_score: float  # fraction of folds within ±1 step of mode
    unique_values: int
    value_range: tuple[float, float]


@dataclass
class StabilityResult:
    """Aggregate stability across all swept parameters."""
    params: list[ParamStability]
    overall_score: float  # mean of per-param stability scores
    n_folds: int
    interpretation: str  # "high" / "moderate" / "low"


def analyze_parameter_stability(
    wf_result: WalkForwardResult,
    param_ranges: dict[str, list] | None = None,
) -> StabilityResult:
    """Analyze how consistently walk-forward folds select the same parameters.

    Args:
        wf_result: Completed walk-forward result with per-fold best_params.
        param_ranges: Optional dict mapping param names to their swept value lists.
            When provided, stability is scored with ±1 step fuzzy matching.
            Without it, only exact mode matches count.

    Returns:
        StabilityResult with per-param scores and overall interpretation.
    """
    folds = wf_result.folds
    n_folds = len(folds)

    if n_folds == 0:
        return StabilityResult(
            params=[], overall_score=0.0, n_folds=0, interpretation="low",
        )

    # Collect all param names from first fold
    param_names = list(folds[0].best_params.keys())

    param_stabilities: list[ParamStability] = []

    for name in param_names:
        values = [f.best_params.get(name, 0.0) for f in folds]

        # Mode via Counter
        counter = Counter(values)
        mode_val, mode_freq = counter.most_common(1)[0]

        # Compute step size from param_ranges if available
        step = None
        if param_ranges and name in param_ranges:
            sorted_vals = sorted(set(param_ranges[name]))
            if len(sorted_vals) >= 2:
                diffs = [sorted_vals[i+1] - sorted_vals[i] for i in range(len(sorted_vals) - 1)]
                step = min(diffs)

        # Score: fraction of folds within ±1 step of mode
        if step is not None and step > 0:
            within = sum(1 for v in values if abs(v - mode_val) <= step * 1.01)
        else:
            # No range info — exact match only
            within = mode_freq

        score = within / n_folds if n_folds > 0 else 0.0

        param_stabilities.append(ParamStability(
            name=name,
            values=values,
            mode=mode_val,
            mode_frequency=mode_freq,
            stability_score=round(score, 4),
            unique_values=len(set(values)),
            value_range=(min(values), max(values)),
        ))

    overall = (
        sum(p.stability_score for p in param_stabilities) / len(param_stabilities)
        if param_stabilities
        else 0.0
    )

    if overall >= 0.7:
        interpretation = "high"
    elif overall >= 0.4:
        interpretation = "moderate"
    else:
        interpretation = "low"

    return StabilityResult(
        params=param_stabilities,
        overall_score=round(overall, 4),
        n_folds=n_folds,
        interpretation=interpretation,
    )
