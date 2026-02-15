"""Structured errors with machine-readable codes and actionable fix suggestions."""

from __future__ import annotations


class BacktestError(Exception):
    """Structured error that serializes to {code, reason, fix} for agents."""

    def __init__(self, code: str, reason: str, fix: str, status_code: int = 400):
        self.code = code
        self.reason = reason
        self.fix = fix
        self.status_code = status_code
        super().__init__(reason)

    def to_dict(self) -> dict:
        return {"code": self.code, "reason": self.reason, "fix": self.fix}


# ── Error catalog ────────────────────────────────────────────────────

def unknown_instrument(symbol: str) -> BacktestError:
    return BacktestError(
        code="UNKNOWN_INSTRUMENT",
        reason=f"Instrument '{symbol}' not found",
        fix="Use GET /api/instruments for available symbols",
    )


def unknown_session(name: str) -> BacktestError:
    return BacktestError(
        code="UNKNOWN_SESSION",
        reason=f"Session '{name}' not found",
        fix="Use GET /api/sessions for available sessions",
    )


def data_not_found(detail: str) -> BacktestError:
    return BacktestError(
        code="DATA_NOT_FOUND",
        reason=detail,
        fix="Run sync_data.py download to fetch data",
        status_code=404,
    )


def invalid_sweep_spec(param: str, spec: str) -> BacktestError:
    return BacktestError(
        code="INVALID_SWEEP_SPEC",
        reason=f"Cannot parse sweep spec for '{param}': '{spec}'",
        fix="Use 'start:stop:step' or 'v1,v2,v3' format",
    )


def no_sweep_params() -> BacktestError:
    return BacktestError(
        code="NO_SWEEP_PARAMS",
        reason="No parameters to sweep",
        fix="Add at least one entry to the sweeps dict",
    )


def backtest_not_found(result_id: str) -> BacktestError:
    return BacktestError(
        code="BACKTEST_NOT_FOUND",
        reason=f"Backtest '{result_id}' not found",
        fix="Use GET /api/backtests to list available results",
        status_code=404,
    )


def optimization_not_found(result_id: str) -> BacktestError:
    return BacktestError(
        code="OPTIMIZATION_NOT_FOUND",
        reason=f"Optimization '{result_id}' not found",
        fix="Use GET /api/optimizations to list available results",
        status_code=404,
    )


def experiment_not_found(run_id: int) -> BacktestError:
    return BacktestError(
        code="EXPERIMENT_NOT_FOUND",
        reason=f"Experiment run {run_id} not found",
        fix="Use GET /api/experiments to list available runs",
        status_code=404,
    )


def invalid_experiment_ids() -> BacktestError:
    return BacktestError(
        code="INVALID_EXPERIMENT_IDS",
        reason="ids must be comma-separated integers",
        fix="Example: /api/experiments/compare?ids=1,2,3",
    )
