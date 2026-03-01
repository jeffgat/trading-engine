"""Conditional statistics for trade sequence analysis.

Analyzes trade dependencies: conditional win probabilities, streak analysis,
drawdown-conditioned performance, and tests whether win/loss outcomes are
independent of prior outcomes.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
from scipy.stats import chi2_contingency

from ..engine.simulator import TradeResult, EXIT_NO_FILL
from .autocorrelation import compute_acf


@dataclass
class ConditionalStats:
    """Conditional statistics for trade sequence analysis."""
    n_trades: int
    win_rate: float

    # Conditional probabilities
    p_win_after_win: float            # P(win | prev was win)
    p_win_after_loss: float           # P(win | prev was loss)
    p_win_in_drawdown: float          # P(win | equity below peak)
    p_win_after_n_losses: dict[int, float] = field(default_factory=dict)

    # Streak analysis
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    expected_max_consecutive_losses: float = 0.0
    streak_z_score: float = 0.0

    # Performance in drawdown bands
    performance_in_drawdown: dict[str, dict] = field(default_factory=dict)

    # Autocorrelation of R-series (lags 1-5)
    r_autocorrelations: list[float] = field(default_factory=list)

    # Chi-squared independence test on win/loss transitions
    chi2_stat: float = 0.0
    chi2_p_value: float = 1.0
    outcomes_independent: bool = True


def compute_conditional_stats(
    trades: list[TradeResult],
    drawdown_thresholds: list[float] | None = None,
    consecutive_loss_counts: list[int] | None = None,
) -> ConditionalStats:
    """Compute conditional statistics on a trade sequence.

    Analyzes trade dependencies including conditional win probabilities,
    streak lengths vs. i.i.d. expectations, and drawdown-conditioned
    performance.

    Args:
        trades: List of TradeResult (no-fills are filtered internally).
        drawdown_thresholds: R-multiple drawdown levels to analyze.
            Default: [2.0, 4.0, 6.0, 8.0].
        consecutive_loss_counts: N values for P(win | N consecutive losses).
            Default: [2, 3, 4, 5].

    Returns:
        ConditionalStats with all conditional probabilities and diagnostics.
    """
    if drawdown_thresholds is None:
        drawdown_thresholds = [2.0, 4.0, 6.0, 8.0]
    if consecutive_loss_counts is None:
        consecutive_loss_counts = [2, 3, 4, 5]

    filled = [t for t in trades if t.exit_type != EXIT_NO_FILL]
    n = len(filled)

    if n < 3:
        return ConditionalStats(n_trades=n, win_rate=0.0, p_win_after_win=0.0,
                                p_win_after_loss=0.0, p_win_in_drawdown=0.0)

    # Binary win/loss classification
    wins = np.array([t.r_multiple > 0 for t in filled])
    r_vals = np.array([t.r_multiple for t in filled])
    win_rate = float(np.mean(wins))

    # --- Conditional win probabilities ---
    # P(win | prev win) and P(win | prev loss)
    win_after_win_count, win_after_win_total = 0, 0
    win_after_loss_count, win_after_loss_total = 0, 0

    for i in range(1, n):
        if wins[i - 1]:
            win_after_win_total += 1
            if wins[i]:
                win_after_win_count += 1
        else:
            win_after_loss_total += 1
            if wins[i]:
                win_after_loss_count += 1

    p_win_after_win = win_after_win_count / win_after_win_total if win_after_win_total else 0.0
    p_win_after_loss = win_after_loss_count / win_after_loss_total if win_after_loss_total else 0.0

    # --- P(win | in drawdown) ---
    equity = np.cumsum(r_vals)
    peak = np.maximum.accumulate(equity)
    drawdown = equity - peak  # negative when in drawdown
    in_dd = drawdown < 0
    if np.any(in_dd):
        p_win_in_dd = float(np.mean(wins[in_dd]))
    else:
        p_win_in_dd = win_rate  # no drawdown observed

    # --- P(win | N consecutive losses) ---
    p_win_after_n = {}
    for target_n in consecutive_loss_counts:
        count, total = 0, 0
        streak = 0
        for i in range(n):
            if not wins[i]:
                streak += 1
            else:
                if streak >= target_n:
                    total += 1
                    count += 1  # this trade IS a win (ends the streak)
                streak = 0
            # Check if streak just reached target_n and there's a next trade
            if streak == target_n and i + 1 < n:
                total += 1
                if wins[i + 1]:
                    count += 1
        # Deduplicate: we want P(win | at trade right after N losses)
        # Recompute cleanly
        count, total = _count_wins_after_streak(wins, target_n)
        p_win_after_n[target_n] = count / total if total else 0.0

    # --- Streak analysis ---
    max_wins = _max_run(wins)
    max_losses = _max_run(~wins)

    # Expected max consecutive losses under i.i.d. Bernoulli
    q = 1.0 - win_rate  # loss probability
    if 0 < q < 1 and n > 1:
        # E[max_run] ≈ log(n * (1-q)) / log(1/q)  (Erdős–Rényi)
        log_inv_q = math.log(1.0 / q)
        expected_max = math.log(n * (1 - q)) / log_inv_q if log_inv_q > 0 else 0.0
        # Approximate std dev: σ ≈ π / (sqrt(6) * log(1/q))
        std_max = math.pi / (math.sqrt(6) * log_inv_q) if log_inv_q > 0 else 1.0
        z_score = (max_losses - expected_max) / std_max if std_max > 0 else 0.0
    else:
        expected_max = 0.0
        z_score = 0.0

    # --- Performance in drawdown bands ---
    perf_in_dd = {}
    for threshold in drawdown_thresholds:
        mask = drawdown < -threshold
        if np.any(mask):
            dd_trades = r_vals[mask]
            dd_wins = wins[mask]
            perf_in_dd[f"{threshold}R"] = {
                "n_trades": int(np.sum(mask)),
                "win_rate": round(float(np.mean(dd_wins)), 4),
                "avg_r": round(float(np.mean(dd_trades)), 4),
            }
        else:
            perf_in_dd[f"{threshold}R"] = {
                "n_trades": 0,
                "win_rate": 0.0,
                "avg_r": 0.0,
            }

    # --- R-series autocorrelation (lags 1-5) ---
    acf_lags = min(5, n - 2)
    if acf_lags > 0:
        r_acf = compute_acf(r_vals, acf_lags)
        r_autocorrelations = [round(float(v), 6) for v in r_acf]
    else:
        r_autocorrelations = []

    # --- Chi-squared independence test on win/loss transitions ---
    # 2x2 transition matrix: rows = prev outcome, cols = current outcome
    # [[loss→loss, loss→win], [win→loss, win→win]]
    transition = np.zeros((2, 2), dtype=int)
    for i in range(1, n):
        prev = int(wins[i - 1])
        curr = int(wins[i])
        transition[prev, curr] += 1

    if transition.min() >= 0 and transition.sum() > 0:
        # Need at least some counts in each row/column for valid test
        row_sums = transition.sum(axis=1)
        col_sums = transition.sum(axis=0)
        if np.all(row_sums > 0) and np.all(col_sums > 0):
            chi2_val, p_val, _, _ = chi2_contingency(transition, correction=True)
            chi2_stat = round(float(chi2_val), 4)
            chi2_p = round(float(p_val), 6)
        else:
            chi2_stat, chi2_p = 0.0, 1.0
    else:
        chi2_stat, chi2_p = 0.0, 1.0

    return ConditionalStats(
        n_trades=n,
        win_rate=round(win_rate, 4),
        p_win_after_win=round(p_win_after_win, 4),
        p_win_after_loss=round(p_win_after_loss, 4),
        p_win_in_drawdown=round(p_win_in_dd, 4),
        p_win_after_n_losses={k: round(v, 4) for k, v in p_win_after_n.items()},
        max_consecutive_wins=max_wins,
        max_consecutive_losses=max_losses,
        expected_max_consecutive_losses=round(expected_max, 2),
        streak_z_score=round(z_score, 2),
        performance_in_drawdown=perf_in_dd,
        r_autocorrelations=r_autocorrelations,
        chi2_stat=chi2_stat,
        chi2_p_value=chi2_p,
        outcomes_independent=chi2_p >= 0.05,
    )


def _max_run(mask: np.ndarray) -> int:
    """Longest consecutive run of True values."""
    max_run = 0
    current = 0
    for v in mask:
        if v:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _count_wins_after_streak(wins: np.ndarray, streak_len: int) -> tuple[int, int]:
    """Count wins at the trade immediately following N consecutive losses.

    Returns:
        (win_count, total_opportunities)
    """
    n = len(wins)
    count, total = 0, 0
    i = 0
    while i < n:
        # Count consecutive losses starting at i
        run_start = i
        while i < n and not wins[i]:
            i += 1
        run_len = i - run_start

        # If we had a run of >= streak_len losses and there's a next trade
        if run_len >= streak_len and i < n:
            total += 1
            if wins[i]:
                count += 1
        # If current position is a win, advance past it
        if i < n:
            i += 1
    return count, total


def conditional_stats_to_dict(result: ConditionalStats) -> dict:
    """Convert ConditionalStats to a JSON-serializable dict."""
    return {
        "n_trades": result.n_trades,
        "win_rate": result.win_rate,
        "p_win_after_win": result.p_win_after_win,
        "p_win_after_loss": result.p_win_after_loss,
        "p_win_in_drawdown": result.p_win_in_drawdown,
        "p_win_after_n_losses": {str(k): v for k, v in result.p_win_after_n_losses.items()},
        "max_consecutive_wins": result.max_consecutive_wins,
        "max_consecutive_losses": result.max_consecutive_losses,
        "expected_max_consecutive_losses": result.expected_max_consecutive_losses,
        "streak_z_score": result.streak_z_score,
        "performance_in_drawdown": result.performance_in_drawdown,
        "r_autocorrelations": result.r_autocorrelations,
        "chi2_stat": result.chi2_stat,
        "chi2_p_value": result.chi2_p_value,
        "outcomes_independent": result.outcomes_independent,
    }
