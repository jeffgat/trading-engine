"""CUSUM regime-change detection for R-multiple series.

Detects structural breaks in strategy performance using the Cumulative Sum
(CUSUM) test. When a break is detected, it indicates the strategy's
return-generating process has changed — a formal alternative to the heuristic
"recent Calmar < 50% of historical" comparison.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..engine.simulator import TradeResult, EXIT_NO_FILL


# Brownian bridge critical values for CUSUM test (sup of |B(t)|/sqrt(n))
# From Brown, Durbin, Evans (1975) / Kolmogorov-Smirnov tables
CRITICAL_VALUES = {
    0.10: 1.224,
    0.05: 1.358,
    0.025: 1.480,
    0.01: 1.628,
}


@dataclass
class RegimeChangeResult:
    """Result of CUSUM regime change detection on R-multiples."""
    n_trades: int
    break_detected: bool
    break_index: int | None           # Trade index where break occurred
    break_date: str | None            # Date of trade at break point
    confidence_level: float           # 1 - p_value of the break
    cusum_stat: float                 # max |S_k| / (sigma * sqrt(n))
    critical_value: float             # Threshold for given alpha

    # Before/after break metrics
    before_metrics: dict | None = None
    after_metrics: dict | None = None

    # Full CUSUM path for visualization
    cusum_path: list[float] = field(default_factory=list)


def detect_regime_change(
    trades: list[TradeResult],
    alpha: float = 0.05,
    min_segment: int = 20,
) -> RegimeChangeResult:
    """Detect structural breaks in R-multiple series using CUSUM test.

    The CUSUM (Cumulative Sum) test:
    1. Centers the R-series by subtracting the mean
    2. Computes cumulative sum S_k = sum(r_i - r_bar) for k=1..n
    3. Normalizes: D = max|S_k| / (sigma * sqrt(n))
    4. Compares D against Brownian bridge critical values
    5. If significant, reports the break point and before/after metrics

    Args:
        trades: Filled TradeResult list.
        alpha: Significance level (default 0.05).
        min_segment: Minimum trades in each segment for a valid break.

    Returns:
        RegimeChangeResult with break point and before/after comparison.
    """
    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    n = len(filled)

    # Need enough trades for meaningful test
    if n < 2 * min_segment:
        return RegimeChangeResult(
            n_trades=n,
            break_detected=False,
            break_index=None,
            break_date=None,
            confidence_level=0.0,
            cusum_stat=0.0,
            critical_value=_get_critical_value(alpha),
        )

    r = np.array([t.r_multiple for t in filled])
    sigma = float(np.std(r, ddof=1))

    if sigma == 0:
        return RegimeChangeResult(
            n_trades=n,
            break_detected=False,
            break_index=None,
            break_date=None,
            confidence_level=0.0,
            cusum_stat=0.0,
            critical_value=_get_critical_value(alpha),
        )

    # Compute centered cumulative sum
    r_centered = r - np.mean(r)
    S = np.cumsum(r_centered)

    # Normalize by sigma * sqrt(n)
    S_normalized = S / (sigma * np.sqrt(n))

    # Find candidate break point (max |S_normalized|)
    abs_S = np.abs(S_normalized)
    k_star = int(np.argmax(abs_S))
    D = float(abs_S[k_star])

    # Enforce minimum segment sizes
    if k_star < min_segment - 1 or k_star > n - min_segment - 1:
        # Break point too close to edges; search for next best within bounds
        valid_range = abs_S[min_segment - 1: n - min_segment]
        if len(valid_range) == 0:
            return RegimeChangeResult(
                n_trades=n,
                break_detected=False,
                break_index=None,
                break_date=None,
                confidence_level=0.0,
                cusum_stat=round(D, 4),
                critical_value=_get_critical_value(alpha),
                cusum_path=[round(float(v), 4) for v in S_normalized],
            )
        k_star = int(np.argmax(valid_range)) + min_segment - 1
        D = float(abs_S[k_star])

    # Get critical value
    cv = _get_critical_value(alpha)

    # Compute approximate p-value from Kolmogorov distribution
    # P(sup|B(t)| > x) ≈ 2 * sum_{k=1}^inf (-1)^{k+1} * exp(-2*k^2*x^2)
    p_value = _kolmogorov_p_value(D)
    confidence = 1.0 - p_value

    break_detected = D > cv

    # Compute before/after metrics if break detected
    before_metrics = None
    after_metrics = None
    break_date = None

    if break_detected:
        # Split at k_star+1 (k_star is the index where cumsum peaks)
        split = k_star + 1
        before = filled[:split]
        after = filled[split:]
        break_date = filled[split].date if split < len(filled) else None

        before_metrics = _segment_metrics(before)
        after_metrics = _segment_metrics(after)

    return RegimeChangeResult(
        n_trades=n,
        break_detected=break_detected,
        break_index=k_star + 1 if break_detected else None,
        break_date=break_date,
        confidence_level=round(confidence, 4),
        cusum_stat=round(D, 4),
        critical_value=cv,
        before_metrics=before_metrics,
        after_metrics=after_metrics,
        cusum_path=[round(float(v), 4) for v in S_normalized],
    )


def _get_critical_value(alpha: float) -> float:
    """Get Brownian bridge critical value for given significance level."""
    if alpha in CRITICAL_VALUES:
        return CRITICAL_VALUES[alpha]
    # Interpolate or use nearest
    alphas = sorted(CRITICAL_VALUES.keys())
    for a in alphas:
        if alpha >= a:
            return CRITICAL_VALUES[a]
    return CRITICAL_VALUES[alphas[-1]]


def _kolmogorov_p_value(D: float) -> float:
    """Approximate p-value from Kolmogorov distribution.

    P(K > D) = 2 * sum_{k=1}^{inf} (-1)^{k+1} * exp(-2*k^2*D^2)

    Converges very rapidly; 100 terms is more than sufficient.
    """
    if D <= 0:
        return 1.0
    total = 0.0
    for k in range(1, 101):
        term = ((-1) ** (k + 1)) * math.exp(-2.0 * k * k * D * D)
        total += term
        if abs(term) < 1e-15:
            break
    p = 2.0 * total
    return max(0.0, min(1.0, p))


def _segment_metrics(trades: list[TradeResult]) -> dict:
    """Compute summary metrics for a segment of trades."""
    n = len(trades)
    if n == 0:
        return {"n_trades": 0, "avg_r": 0.0, "win_rate": 0.0, "sharpe": 0.0, "calmar": 0.0}

    r = np.array([t.r_multiple for t in trades])
    wins = np.sum(r > 0)
    avg_r = float(np.mean(r))
    std_r = float(np.std(r, ddof=1)) if n > 1 else 1.0

    # Sharpe (annualized)
    sharpe = (avg_r / std_r * np.sqrt(252)) if std_r > 0 else 0.0

    # Max drawdown for Calmar
    equity = np.cumsum(r)
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    max_dd = float(np.min(dd))

    # Calmar: total R / |max DD|
    total_r = float(np.sum(r))
    calmar = total_r / abs(max_dd) if max_dd < 0 else 0.0

    return {
        "n_trades": n,
        "avg_r": round(avg_r, 4),
        "win_rate": round(float(wins / n), 4),
        "sharpe": round(float(sharpe), 4),
        "calmar": round(calmar, 4),
    }


def regime_change_to_dict(result: RegimeChangeResult) -> dict:
    """Convert RegimeChangeResult to a JSON-serializable dict."""
    return {
        "n_trades": result.n_trades,
        "break_detected": result.break_detected,
        "break_index": result.break_index,
        "break_date": result.break_date,
        "confidence_level": result.confidence_level,
        "cusum_stat": result.cusum_stat,
        "critical_value": result.critical_value,
        "before_metrics": result.before_metrics,
        "after_metrics": result.after_metrics,
        "cusum_path_length": len(result.cusum_path),
    }
