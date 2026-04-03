"""Tests for PSR and DSR validation module."""

from __future__ import annotations

import numpy as np
import pytest

from orb_backtest.validate.deflated_sharpe import (
    annotate_trades,
    compute_dsr,
    compute_psr,
    estimate_effective_trials,
    _expected_max_sharpe,
)


class TestPSR:
    """Tests for Probabilistic Sharpe Ratio."""

    def test_strong_positive_edge(self):
        """Strategy with clear positive edge should have high PSR."""
        rng = np.random.default_rng(42)
        # Mean +0.15, std 1.0 → SR ~ 0.15 per trade, 500 trades
        r = rng.normal(0.15, 1.0, 500)
        result = compute_psr(r)
        assert result.psr > 0.90
        assert result.n_trades == 500
        assert result.observed_sharpe > 0  # annualized

    def test_zero_edge(self):
        """Strategy with no edge should have PSR < strong threshold."""
        rng = np.random.default_rng(123)  # seed that produces near-zero mean
        r = rng.normal(0.0, 1.0, 1000)
        result = compute_psr(r)
        # With zero true edge, PSR should not be confidently positive
        assert result.psr < 0.95

    def test_negative_edge(self):
        """Strategy with negative edge should have low PSR."""
        rng = np.random.default_rng(42)
        r = rng.normal(-0.1, 1.0, 500)
        result = compute_psr(r)
        assert result.psr < 0.3

    def test_small_sample(self):
        """Very few trades should return PSR=0.5 (uninformative)."""
        r = np.array([1.0, -0.5])
        result = compute_psr(r)
        assert result.psr == 0.5
        assert result.n_trades == 2

    def test_benchmark_sharpe(self):
        """PSR against a positive benchmark should be lower than against zero."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 300)
        psr_zero = compute_psr(r, benchmark_sharpe=0.0)
        psr_high = compute_psr(r, benchmark_sharpe=1.0)
        assert psr_zero.psr > psr_high.psr

    def test_skewness_kurtosis_reported(self):
        """PSR should report distribution statistics."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 200)
        result = compute_psr(r)
        assert isinstance(result.skewness, float)
        assert isinstance(result.kurtosis, float)
        assert result.kurtosis > 0  # raw kurtosis, not excess


class TestEffectiveTrials:
    """Tests for trade-overlap clustering."""

    def test_identical_sets(self):
        """All configs with same trades = 1 effective trial."""
        dates = {"2024-01-01", "2024-01-02", "2024-01-03"}
        sets = [dates, dates, dates, dates]
        assert estimate_effective_trials(sets) == 1

    def test_disjoint_sets(self):
        """Completely different trade sets = N effective trials."""
        sets = [
            {"2024-01-01", "2024-01-02"},
            {"2024-02-01", "2024-02-02"},
            {"2024-03-01", "2024-03-02"},
        ]
        assert estimate_effective_trials(sets) == 3

    def test_partial_overlap(self):
        """Configs with partial overlap should cluster."""
        base = {f"2024-01-{i:02d}" for i in range(1, 21)}
        # 80% overlap with base
        variant1 = base - {"2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"} | {"2024-02-01", "2024-02-02", "2024-02-03", "2024-02-04"}
        # Completely different
        other = {f"2024-06-{i:02d}" for i in range(1, 21)}

        sets = [base, variant1, other]
        n_eff = estimate_effective_trials(sets)
        assert n_eff == 2  # base+variant1 cluster, other is separate

    def test_empty_input(self):
        assert estimate_effective_trials([]) == 1

    def test_single_config(self):
        assert estimate_effective_trials([{"2024-01-01"}]) == 1


class TestDSR:
    """Tests for Deflated Sharpe Ratio."""

    def test_strong_edge_few_trials(self):
        """Strong edge with few trials should have high DSR."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.2, 1.0, 500)
        result = compute_dsr(r, n_trials_raw=10, n_trials_effective=10)
        assert result.dsr > 0.80
        assert result.n_trials_effective == 10

    def test_more_trials_lowers_dsr(self):
        """More trials = higher expected max Sharpe = lower DSR."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 300)
        dsr_few = compute_dsr(r, n_trials_raw=10)
        dsr_many = compute_dsr(r, n_trials_raw=1000)
        assert dsr_few.dsr > dsr_many.dsr

    def test_effective_trials_matters(self):
        """Effective trials < raw trials should produce higher DSR."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 300)
        dsr_raw = compute_dsr(r, n_trials_raw=1000, n_trials_effective=1000)
        dsr_eff = compute_dsr(r, n_trials_raw=1000, n_trials_effective=50)
        assert dsr_eff.dsr > dsr_raw.dsr

    def test_expected_max_sharpe_increases_with_trials(self):
        """E[max(SR)] should increase with more trials."""
        e10 = _expected_max_sharpe(10, 500)
        e100 = _expected_max_sharpe(100, 500)
        e1000 = _expected_max_sharpe(1000, 500)
        assert e10 < e100 < e1000

    def test_small_sample(self):
        r = np.array([1.0, -0.5])
        result = compute_dsr(r, n_trials_raw=100)
        assert result.dsr == 0.5

    def test_psr_included(self):
        """DSR result should include PSR for comparison."""
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 200)
        result = compute_dsr(r, n_trials_raw=50)
        assert 0 <= result.psr <= 1
        # PSR (vs zero) should be >= DSR (vs expected max)
        assert result.psr >= result.dsr


class TestAnnotate:
    """Tests for the convenience annotation function."""

    def test_returns_expected_keys(self):
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 200)
        result = annotate_trades(r, n_trials_raw=100)
        assert "psr" in result
        assert "dsr" in result
        assert "value" in result["psr"]
        assert "interpretation" in result["psr"]
        assert "value" in result["dsr"]
        assert "n_trials_effective" in result["dsr"]

    def test_with_trade_date_sets(self):
        rng = np.random.default_rng(42)
        r = rng.normal(0.1, 1.0, 200)
        # Mostly overlapping trade sets → few effective trials
        base_dates = {f"2024-01-{i:02d}" for i in range(1, 21)}
        sets = [base_dates] * 50  # 50 identical configs
        result = annotate_trades(r, n_trials_raw=50, trade_date_sets=sets)
        assert result["dsr"]["n_trials_effective"] == 1
        # DSR should be high because effective trials = 1
        assert result["dsr"]["value"] > result["psr"]["value"] or result["dsr"]["value"] > 0.5
