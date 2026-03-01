"""Prop firm constraint evaluation for R-based trade sequences."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from ..engine.simulator import EXIT_NO_FILL


@dataclass(frozen=True)
class PropFirmConstraints:
    """Threshold parameters for prop firm account survival.

    All values are in R (risk units).
    """
    max_drawdown_r: float = 10.0
    min_annual_r: float = 24.0
    max_monthly_loss_r: float = 5.0
    min_positive_expectancy: bool = True


@dataclass
class ConstraintResult:
    """Detailed result of constraint evaluation against a trade sequence."""
    passed: bool

    # Per-constraint results
    max_drawdown_r: float
    max_drawdown_passed: bool

    annual_r_values: dict[str, float]
    annual_r_passed: bool  # all full years meet threshold

    monthly_r_values: dict[str, float]
    worst_month_r: float
    monthly_loss_passed: bool

    expectancy: float
    expectancy_passed: bool

    # Supporting stats
    total_r: float
    total_trades: int
    win_rate: float
    avg_win_r: float
    avg_loss_r: float
    max_consecutive_losses: int


def evaluate_constraints(
    trades,
    constraints: PropFirmConstraints | None = None,
) -> ConstraintResult:
    """Evaluate prop firm constraints against a trade sequence.

    Args:
        trades: List of TradeResult NamedTuples or plain dicts. Duck-typed —
            requires ``exit_type``, ``r_multiple``, and ``date`` attributes/keys.
        constraints: Thresholds to evaluate. Defaults to PropFirmConstraints().

    Returns:
        ConstraintResult with per-constraint pass/fail and supporting stats.
    """
    if constraints is None:
        constraints = PropFirmConstraints()

    # Duck-type accessor: NamedTuple attrs or dict keys
    def _get(t, key):
        try:
            return getattr(t, key)
        except AttributeError:
            return t[key]

    # Filter out no-fills
    filled = []
    for t in trades:
        et = _get(t, "exit_type")
        # EXIT_NO_FILL == 0 for NamedTuples, "no_fill" for dicts
        if et == EXIT_NO_FILL or et == "no_fill":
            continue
        filled.append(t)

    if not filled:
        return ConstraintResult(
            passed=False,
            max_drawdown_r=0.0,
            max_drawdown_passed=True,
            annual_r_values={},
            annual_r_passed=False,
            monthly_r_values={},
            worst_month_r=0.0,
            monthly_loss_passed=True,
            expectancy=0.0,
            expectancy_passed=False,
            total_r=0.0,
            total_trades=0,
            win_rate=0.0,
            avg_win_r=0.0,
            avg_loss_r=0.0,
            max_consecutive_losses=0,
        )

    # Build R sequence
    r_values = np.array([float(_get(t, "r_multiple")) for t in filled])
    dates = [str(_get(t, "date")) for t in filled]

    # R equity curve and max drawdown
    r_equity = np.cumsum(r_values)
    r_peak = np.maximum.accumulate(r_equity)
    r_dd = r_equity - r_peak
    max_dd_r = float(np.min(r_dd))  # negative
    total_r = float(r_equity[-1])

    # Group R by month and year
    monthly_r: dict[str, float] = defaultdict(float)
    annual_r: dict[str, float] = defaultdict(float)
    months_per_year: dict[str, set[str]] = defaultdict(set)

    for date_str, r in zip(dates, r_values):
        month_key = date_str[:7]  # YYYY-MM
        year_key = date_str[:4]   # YYYY
        monthly_r[month_key] += float(r)
        annual_r[year_key] += float(r)
        months_per_year[year_key].add(month_key)

    monthly_r = dict(sorted(monthly_r.items()))
    annual_r = dict(sorted(annual_r.items()))

    # Win/loss stats
    wins = r_values > 0
    losses = r_values < 0
    win_rate = float(np.mean(wins)) if len(r_values) > 0 else 0.0
    avg_win_r = float(np.mean(r_values[wins])) if wins.any() else 0.0
    avg_loss_r = float(np.mean(r_values[losses])) if losses.any() else 0.0
    expectancy = float(np.mean(r_values))

    # Max consecutive losses
    max_consec = 0
    current = 0
    for r in r_values:
        if r < 0:
            current += 1
            max_consec = max(max_consec, current)
        else:
            current = 0

    # --- Constraint checks ---

    # 1. Max drawdown (compare absolute value)
    dd_passed = abs(max_dd_r) <= constraints.max_drawdown_r

    # 2. Annual R: only gate on full calendar years (≥10 months of data)
    # Uses the average across full years so that one weak year doesn't veto
    # an otherwise strong strategy. Partial years are informational only.
    full_years = {
        y: r for y, r in annual_r.items()
        if len(months_per_year[y]) >= 10
    }
    if full_years:
        avg_annual_r = sum(full_years.values()) / len(full_years)
        annual_passed = avg_annual_r >= constraints.min_annual_r
    else:
        annual_passed = True

    # 3. Monthly loss: worst single month must not exceed threshold
    worst_month = min(monthly_r.values()) if monthly_r else 0.0
    monthly_passed = abs(worst_month) <= constraints.max_monthly_loss_r if worst_month < 0 else True

    # 4. Expectancy
    expectancy_passed = expectancy > 0 if constraints.min_positive_expectancy else True

    # Overall pass is conjunction
    passed = dd_passed and annual_passed and monthly_passed and expectancy_passed

    return ConstraintResult(
        passed=passed,
        max_drawdown_r=max_dd_r,
        max_drawdown_passed=dd_passed,
        annual_r_values=annual_r,
        annual_r_passed=annual_passed,
        monthly_r_values=monthly_r,
        worst_month_r=worst_month,
        monthly_loss_passed=monthly_passed,
        expectancy=expectancy,
        expectancy_passed=expectancy_passed,
        total_r=total_r,
        total_trades=len(filled),
        win_rate=win_rate,
        avg_win_r=avg_win_r,
        avg_loss_r=avg_loss_r,
        max_consecutive_losses=max_consec,
    )


def evaluate_constraints_mc(
    mc_result,
    constraints: PropFirmConstraints | None = None,
    trade_dates: list[str] | None = None,
) -> dict:
    """Evaluate prop constraints across Monte Carlo simulated equity curves.

    Args:
        mc_result: A MonteCarloResult with ``equity_curves`` (n_sims × n_trades).
        constraints: Thresholds. Defaults to PropFirmConstraints().
        trade_dates: Optional list of date strings (len == n_trades) for
            monthly/annual grouping. When omitted, only DD survival is computed.

    Returns:
        Dict with ``survival_rate``, DD percentiles, and per-constraint pass rates.
    """
    if constraints is None:
        constraints = PropFirmConstraints()

    curves = mc_result.equity_curves  # (n_sims, n_trades)
    n_sims = curves.shape[0]

    # Per-sim max drawdown
    peaks = np.maximum.accumulate(curves, axis=1)
    drawdowns = curves - peaks
    max_dds = np.min(drawdowns, axis=1)  # most negative per sim

    # Survival: sims where |max DD| <= threshold
    survived = np.abs(max_dds) <= constraints.max_drawdown_r
    survival_rate = float(np.mean(survived))

    # DD percentiles
    dd_abs = np.abs(max_dds)
    dd_percentiles = {
        "p5": round(float(np.percentile(dd_abs, 5)), 4),
        "p25": round(float(np.percentile(dd_abs, 25)), 4),
        "p50": round(float(np.percentile(dd_abs, 50)), 4),
        "p75": round(float(np.percentile(dd_abs, 75)), 4),
        "p95": round(float(np.percentile(dd_abs, 95)), 4),
    }

    result = {
        "survival_rate": round(survival_rate, 4),
        "dd_threshold": constraints.max_drawdown_r,
        "dd_percentiles": dd_percentiles,
        "n_sims": n_sims,
    }

    # If trade dates provided, compute annual/monthly pass rates per sim
    if trade_dates is not None and len(trade_dates) == curves.shape[1]:
        # Per-trade R values per sim: diff of cumulative curves
        per_trade_r = np.diff(curves, axis=1, prepend=0)

        # Build month/year index mapping
        month_indices: dict[str, list[int]] = defaultdict(list)
        year_indices: dict[str, list[int]] = defaultdict(list)
        months_per_year_set: dict[str, set[str]] = defaultdict(set)

        for i, d in enumerate(trade_dates):
            month_indices[d[:7]].append(i)
            year_indices[d[:4]].append(i)
            months_per_year_set[d[:4]].add(d[:7])

        # Monthly loss pass rate
        monthly_pass_count = 0
        for sim_idx in range(n_sims):
            sim_passed = True
            for month, indices in month_indices.items():
                month_r = float(np.sum(per_trade_r[sim_idx, indices]))
                if month_r < 0 and abs(month_r) > constraints.max_monthly_loss_r:
                    sim_passed = False
                    break
            if sim_passed:
                monthly_pass_count += 1
        result["monthly_loss_pass_rate"] = round(monthly_pass_count / n_sims, 4)

        # Annual R pass rate (full years only)
        full_years = [y for y, ms in months_per_year_set.items() if len(ms) >= 10]
        if full_years:
            annual_pass_count = 0
            for sim_idx in range(n_sims):
                sim_passed = True
                for year in full_years:
                    year_r = float(np.sum(per_trade_r[sim_idx, year_indices[year]]))
                    if year_r < constraints.min_annual_r:
                        sim_passed = False
                        break
                if sim_passed:
                    annual_pass_count += 1
            result["annual_r_pass_rate"] = round(annual_pass_count / n_sims, 4)

    return result
