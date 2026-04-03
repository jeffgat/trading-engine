"""Deflated Sharpe Ratio (DSR) and Probabilistic Sharpe Ratio (PSR).

Implements Bailey & Lopez de Prado (2014) multiple-testing corrections
for strategy selection from parameter sweeps.

References:
  - Bailey, D.H. & Lopez de Prado, M. (2014). "The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting, and Non-Normality."
    Journal of Portfolio Management.
  - Bailey, D.H. & Lopez de Prado, M. (2012). "The Sharpe Ratio Efficient
    Frontier." Journal of Risk.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats


# ---------------------------------------------------------------------------
# PSR — Probabilistic Sharpe Ratio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PSRResult:
    """Result of Probabilistic Sharpe Ratio computation."""

    observed_sharpe: float
    benchmark_sharpe: float
    n_trades: int
    skewness: float
    kurtosis: float
    psr: float  # probability that true Sharpe > benchmark, range [0, 1]


def compute_psr(
    r_multiples: np.ndarray,
    benchmark_sharpe: float = 0.0,
) -> PSRResult:
    """Compute the Probabilistic Sharpe Ratio.

    PSR estimates the probability that the true (population) Sharpe ratio
    exceeds a given benchmark, accounting for sample size, skewness, and
    kurtosis of the return distribution.

    Formula (Bailey & Lopez de Prado 2012):
        PSR = Phi( (SR - SR*) / SE(SR) )
    where:
        SE(SR) = sqrt( (1 - skew*SR + (kurt-3)/4 * SR^2) / (n-1) )

    Args:
        r_multiples: Array of per-trade R-multiples.
        benchmark_sharpe: Sharpe ratio to test against (default 0 = positive edge).

    Returns:
        PSRResult with the probability and distribution statistics.
    """
    n = len(r_multiples)
    if n < 3:
        return PSRResult(
            observed_sharpe=0.0, benchmark_sharpe=benchmark_sharpe,
            n_trades=n, skewness=0.0, kurtosis=3.0, psr=0.5,
        )

    mean_r = float(np.mean(r_multiples))
    std_r = float(np.std(r_multiples, ddof=1))
    if std_r <= 0:
        return PSRResult(
            observed_sharpe=0.0, benchmark_sharpe=benchmark_sharpe,
            n_trades=n, skewness=0.0, kurtosis=3.0,
            psr=1.0 if mean_r > 0 else 0.0,
        )

    sr = mean_r / std_r  # non-annualized Sharpe (per-trade)
    sr_star = benchmark_sharpe / np.sqrt(252) if benchmark_sharpe != 0 else 0.0

    skew = float(stats.skew(r_multiples, bias=False))
    kurt = float(stats.kurtosis(r_multiples, bias=False, fisher=False))  # excess=False → raw kurtosis

    # Standard error of the Sharpe ratio
    se_num = 1.0 - skew * sr + (kurt - 3.0) / 4.0 * sr ** 2
    se_num = max(se_num, 1e-10)  # numerical safety
    se_sr = np.sqrt(se_num / (n - 1))

    if se_sr <= 0:
        psr_val = 1.0 if sr > sr_star else 0.0
    else:
        z = (sr - sr_star) / se_sr
        psr_val = float(stats.norm.cdf(z))

    return PSRResult(
        observed_sharpe=round(sr * np.sqrt(252), 4),  # annualized for display
        benchmark_sharpe=benchmark_sharpe,
        n_trades=n,
        skewness=round(skew, 4),
        kurtosis=round(kurt, 4),
        psr=round(psr_val, 4),
    )


# ---------------------------------------------------------------------------
# Effective independent trials via trade-overlap clustering
# ---------------------------------------------------------------------------


def estimate_effective_trials(
    trade_date_sets: list[set[str]],
    method: str = "jaccard",
) -> int:
    """Estimate the number of effectively independent strategy trials.

    Correlated configs (sharing most of the same trades) should not each
    count as a full independent trial for DSR. This clusters configs by
    trade-date overlap and returns the number of clusters.

    Args:
        trade_date_sets: List of sets, where each set contains the trade dates
            (YYYY-MM-DD strings) for one config.
        method: Clustering method. ``"jaccard"`` uses average-linkage
            clustering with Jaccard distance threshold of 0.5.

    Returns:
        Estimated number of independent trials (>= 1).
    """
    n = len(trade_date_sets)
    if n <= 1:
        return max(n, 1)

    # Compute pairwise Jaccard distances
    # Jaccard distance = 1 - |A ∩ B| / |A ∪ B|
    # Two configs with >50% trade overlap are "the same trial"
    threshold = 0.5

    # Simple greedy clustering: assign each config to first cluster
    # where average Jaccard similarity > threshold
    clusters: list[list[int]] = []

    for i in range(n):
        assigned = False
        for cluster in clusters:
            # Check average similarity to cluster members
            sims = []
            for j in cluster:
                intersection = len(trade_date_sets[i] & trade_date_sets[j])
                union = len(trade_date_sets[i] | trade_date_sets[j])
                sim = intersection / union if union > 0 else 0.0
                sims.append(sim)
            avg_sim = np.mean(sims)
            if avg_sim > threshold:
                cluster.append(i)
                assigned = True
                break
        if not assigned:
            clusters.append([i])

    return max(len(clusters), 1)


# ---------------------------------------------------------------------------
# DSR — Deflated Sharpe Ratio
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DSRResult:
    """Result of Deflated Sharpe Ratio computation."""

    observed_sharpe: float
    expected_max_sharpe: float  # E[max(SR)] under null
    n_trades: int
    n_trials_raw: int
    n_trials_effective: int
    skewness: float
    kurtosis: float
    dsr: float  # probability that true Sharpe > E[max(SR)] under null
    psr: float  # PSR against zero benchmark (for comparison)


def _expected_max_sharpe(n_trials: int, n_trades: int) -> float:
    """Expected maximum Sharpe ratio under the null (all strategies have zero edge).

    E[max(SR)] ≈ SR_std * ( (1 - gamma) * Phi^{-1}(1 - 1/N) + gamma * Phi^{-1}(1 - 1/(N*e)) )

    where gamma ≈ 0.5772 (Euler-Mascheroni), N = n_trials, and SR_std = 1/sqrt(n_trades-1).

    Simplified approximation from Bailey & Lopez de Prado (2014) eq. 9.
    """
    if n_trials <= 1 or n_trades <= 1:
        return 0.0

    gamma = 0.5772156649  # Euler-Mascheroni constant
    sr_std = 1.0 / np.sqrt(n_trades - 1)

    # Avoid numerical issues with very large N
    n = max(n_trials, 2)
    z1 = stats.norm.ppf(1.0 - 1.0 / n)
    z2 = stats.norm.ppf(1.0 - 1.0 / (n * np.e))

    e_max_sr = sr_std * ((1.0 - gamma) * z1 + gamma * z2)
    return float(e_max_sr)


def compute_dsr(
    r_multiples: np.ndarray,
    n_trials_raw: int,
    n_trials_effective: int | None = None,
    benchmark_sharpe: float | None = None,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio.

    DSR adjusts the observed Sharpe for multiple testing by comparing it
    against the expected maximum Sharpe under the null hypothesis (no strategy
    has a real edge). If DSR > 0.95, the observed Sharpe is unlikely to be
    explained by selection bias alone.

    Args:
        r_multiples: Array of per-trade R-multiples for the selected strategy.
        n_trials_raw: Total number of configs/strategies tested in the search.
        n_trials_effective: Effective independent trials after clustering.
            If None, uses ``n_trials_raw``.
        benchmark_sharpe: Override the benchmark. If None, uses the expected
            max Sharpe under null (the standard DSR formulation).

    Returns:
        DSRResult with deflated probability and supporting statistics.
    """
    n = len(r_multiples)
    n_eff = n_trials_effective if n_trials_effective is not None else n_trials_raw

    if n < 3:
        return DSRResult(
            observed_sharpe=0.0, expected_max_sharpe=0.0,
            n_trades=n, n_trials_raw=n_trials_raw, n_trials_effective=n_eff,
            skewness=0.0, kurtosis=3.0, dsr=0.5, psr=0.5,
        )

    mean_r = float(np.mean(r_multiples))
    std_r = float(np.std(r_multiples, ddof=1))
    if std_r <= 0:
        return DSRResult(
            observed_sharpe=0.0, expected_max_sharpe=0.0,
            n_trades=n, n_trials_raw=n_trials_raw, n_trials_effective=n_eff,
            skewness=0.0, kurtosis=3.0,
            dsr=1.0 if mean_r > 0 else 0.0,
            psr=1.0 if mean_r > 0 else 0.0,
        )

    sr = mean_r / std_r  # non-annualized per-trade Sharpe

    # Expected max Sharpe under null
    e_max_sr = _expected_max_sharpe(n_eff, n)
    sr_benchmark = benchmark_sharpe / np.sqrt(252) if benchmark_sharpe is not None else e_max_sr

    skew = float(stats.skew(r_multiples, bias=False))
    kurt = float(stats.kurtosis(r_multiples, bias=False, fisher=False))

    # PSR against the deflated benchmark
    se_num = 1.0 - skew * sr + (kurt - 3.0) / 4.0 * sr ** 2
    se_num = max(se_num, 1e-10)
    se_sr = np.sqrt(se_num / (n - 1))

    if se_sr <= 0:
        dsr_val = 1.0 if sr > sr_benchmark else 0.0
    else:
        z = (sr - sr_benchmark) / se_sr
        dsr_val = float(stats.norm.cdf(z))

    # Also compute standard PSR (against zero) for comparison
    psr_result = compute_psr(r_multiples, benchmark_sharpe=0.0)

    return DSRResult(
        observed_sharpe=round(sr * np.sqrt(252), 4),
        expected_max_sharpe=round(e_max_sr * np.sqrt(252), 4),
        n_trades=n,
        n_trials_raw=n_trials_raw,
        n_trials_effective=n_eff,
        skewness=round(skew, 4),
        kurtosis=round(kurt, 4),
        dsr=round(dsr_val, 4),
        psr=psr_result.psr,
    )


# ---------------------------------------------------------------------------
# Convenience: annotate a list of trade results
# ---------------------------------------------------------------------------


def annotate_trades(
    r_multiples: np.ndarray,
    n_trials_raw: int,
    trade_date_sets: list[set[str]] | None = None,
) -> dict:
    """Compute PSR + DSR annotations for a single promoted config.

    Args:
        r_multiples: Per-trade R-multiples for the config.
        n_trials_raw: Total configs tested in the search that produced this config.
        trade_date_sets: Optional list of trade-date sets for all configs
            in the search (for effective trial estimation). If None, uses raw count.

    Returns:
        Dict with PSR and DSR results, ready for JSON serialization.
    """
    n_eff = n_trials_raw
    if trade_date_sets is not None:
        n_eff = estimate_effective_trials(trade_date_sets)

    psr = compute_psr(r_multiples)
    dsr = compute_dsr(r_multiples, n_trials_raw, n_eff)

    return {
        "psr": {
            "value": psr.psr,
            "observed_sharpe": psr.observed_sharpe,
            "n_trades": psr.n_trades,
            "skewness": psr.skewness,
            "kurtosis": psr.kurtosis,
            "interpretation": (
                "strong" if psr.psr >= 0.95
                else "moderate" if psr.psr >= 0.85
                else "weak" if psr.psr >= 0.50
                else "negative"
            ),
        },
        "dsr": {
            "value": dsr.dsr,
            "observed_sharpe": dsr.observed_sharpe,
            "expected_max_sharpe_null": dsr.expected_max_sharpe,
            "n_trials_raw": dsr.n_trials_raw,
            "n_trials_effective": dsr.n_trials_effective,
            "n_trades": dsr.n_trades,
            "interpretation": (
                "survives deflation" if dsr.dsr >= 0.95
                else "marginal" if dsr.dsr >= 0.80
                else "likely overfit" if dsr.dsr >= 0.50
                else "overfit"
            ),
        },
    }
