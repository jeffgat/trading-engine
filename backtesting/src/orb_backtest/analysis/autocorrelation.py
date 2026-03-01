"""Autocorrelation analysis and Ljung-Box test for R-multiple series.

Tests whether trade R-multiples are serially correlated, which determines
whether standard i.i.d. bootstrap Monte Carlo is valid or whether block
bootstrap should be used instead.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.stats import chi2

from ..engine.simulator import TradeResult, EXIT_NO_FILL


@dataclass
class AutocorrelationResult:
    """Results of autocorrelation analysis on R-multiples."""
    n_trades: int
    max_lag: int
    acf_values: list[float]           # ACF at lags 1..max_lag
    ljung_box_stat: float             # Q statistic
    ljung_box_p_value: float          # p-value from chi-squared distribution
    significant_lags: list[int]       # Lags where |ACF| > 2/sqrt(n)
    has_autocorrelation: bool         # True if p_value < alpha
    recommendation: str               # "iid_bootstrap" or "block_bootstrap"


def compute_acf(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Compute sample autocorrelation function at lags 1..max_lag.

    Uses the standard biased estimator (divides by n, not n-k) which is
    consistent with Box-Jenkins convention and ensures the ACF matrix is
    positive semi-definite.

    Args:
        x: Time series (1-D array).
        max_lag: Maximum lag to compute.

    Returns:
        Array of ACF values at lags 1 through max_lag.
    """
    n = len(x)
    x_centered = x - np.mean(x)
    c0 = np.dot(x_centered, x_centered) / n  # lag-0 autocovariance

    if c0 == 0:
        return np.zeros(max_lag)

    acf = np.empty(max_lag)
    for k in range(1, max_lag + 1):
        acf[k - 1] = np.dot(x_centered[:n - k], x_centered[k:]) / (n * c0)

    return acf


def test_autocorrelation(
    r_multiples: np.ndarray,
    max_lag: int = 10,
    alpha: float = 0.05,
) -> AutocorrelationResult:
    """Test R-multiple series for serial autocorrelation.

    Computes the ACF at lags 1..max_lag and runs the Ljung-Box Q test.
    The Q statistic follows a chi-squared distribution with max_lag degrees
    of freedom under the null hypothesis of no autocorrelation.

    Formula: Q = n(n+2) * sum_{k=1}^{h} (rho_k^2 / (n-k))

    Args:
        r_multiples: Array of trade R-multiples (filled trades only).
        max_lag: Maximum lag to test (default 10).
        alpha: Significance level (default 0.05).

    Returns:
        AutocorrelationResult with test statistics and recommendation.
    """
    n = len(r_multiples)
    if n < max_lag + 2:
        # Not enough data for meaningful autocorrelation test
        return AutocorrelationResult(
            n_trades=n,
            max_lag=max_lag,
            acf_values=[0.0] * max_lag,
            ljung_box_stat=0.0,
            ljung_box_p_value=1.0,
            significant_lags=[],
            has_autocorrelation=False,
            recommendation="iid_bootstrap",
        )

    # Compute ACF
    acf = compute_acf(r_multiples, max_lag)

    # Ljung-Box Q statistic
    k_range = np.arange(1, max_lag + 1)
    q_stat = float(n * (n + 2) * np.sum(acf**2 / (n - k_range)))

    # p-value from chi-squared distribution with max_lag degrees of freedom
    p_value = float(chi2.sf(q_stat, df=max_lag))

    # Individual significance: |ACF| > 2/sqrt(n) (approximate 95% CI)
    threshold = 2.0 / np.sqrt(n)
    significant = [int(k) for k in range(1, max_lag + 1) if abs(acf[k - 1]) > threshold]

    has_ac = p_value < alpha
    recommendation = "block_bootstrap" if has_ac else "iid_bootstrap"

    return AutocorrelationResult(
        n_trades=n,
        max_lag=max_lag,
        acf_values=[round(float(v), 6) for v in acf],
        ljung_box_stat=round(q_stat, 4),
        ljung_box_p_value=round(p_value, 6),
        significant_lags=significant,
        has_autocorrelation=has_ac,
        recommendation=recommendation,
    )


def check_mc_assumptions(
    trades: list[TradeResult],
    max_lag: int = 10,
    alpha: float = 0.05,
) -> AutocorrelationResult:
    """Convenience wrapper: extract R-multiples from trades and test.

    Filters out no-fill trades, extracts R-multiples, and runs the
    autocorrelation test.

    Args:
        trades: List of TradeResult from a backtest.
        max_lag: Maximum lag for Ljung-Box test.
        alpha: Significance level.

    Returns:
        AutocorrelationResult with recommendation for MC method.
    """
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    if not filled:
        return AutocorrelationResult(
            n_trades=0,
            max_lag=max_lag,
            acf_values=[0.0] * max_lag,
            ljung_box_stat=0.0,
            ljung_box_p_value=1.0,
            significant_lags=[],
            has_autocorrelation=False,
            recommendation="iid_bootstrap",
        )

    r_multiples = np.array([t.r_multiple for t in filled])
    return test_autocorrelation(r_multiples, max_lag=max_lag, alpha=alpha)


def autocorrelation_result_to_dict(result: AutocorrelationResult) -> dict:
    """Convert AutocorrelationResult to a JSON-serializable dict."""
    return {
        "n_trades": result.n_trades,
        "max_lag": result.max_lag,
        "acf_values": result.acf_values,
        "ljung_box_stat": result.ljung_box_stat,
        "ljung_box_p_value": result.ljung_box_p_value,
        "significant_lags": result.significant_lags,
        "has_autocorrelation": result.has_autocorrelation,
        "recommendation": result.recommendation,
    }
