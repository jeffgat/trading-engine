"""Structured errors with machine-readable codes and actionable fix suggestions."""

from __future__ import annotations


class IFVGError(Exception):
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

def unknown_instrument(symbol: str) -> IFVGError:
    return IFVGError(
        code="UNKNOWN_INSTRUMENT",
        reason=f"Instrument '{symbol}' not found",
        fix="Use GET /ifvg/instruments for available symbols",
    )


def data_not_found(detail: str) -> IFVGError:
    return IFVGError(
        code="DATA_NOT_FOUND",
        reason=detail,
        fix="Run sync_data.py download to fetch data",
        status_code=404,
    )


def invalid_sweep_spec(param: str, spec: str) -> IFVGError:
    return IFVGError(
        code="INVALID_SWEEP_SPEC",
        reason=f"Cannot parse sweep spec for '{param}': '{spec}'",
        fix="Use 'start:stop:step' or 'v1,v2,v3' format",
    )


def no_sweep_params() -> IFVGError:
    return IFVGError(
        code="NO_SWEEP_PARAMS",
        reason="No parameters to sweep",
        fix="Add at least one entry to the param ranges",
    )


def backtest_not_found(result_id: str) -> IFVGError:
    return IFVGError(
        code="BACKTEST_NOT_FOUND",
        reason=f"Backtest '{result_id}' not found",
        fix="Use GET /ifvg/backtests to list available results",
        status_code=404,
    )


def optimization_not_found(result_id: str) -> IFVGError:
    return IFVGError(
        code="OPTIMIZATION_NOT_FOUND",
        reason=f"Optimization '{result_id}' not found",
        fix="Use GET /ifvg/optimizations to list available results",
        status_code=404,
    )


def experiment_not_found(run_id: int) -> IFVGError:
    return IFVGError(
        code="EXPERIMENT_NOT_FOUND",
        reason=f"Experiment run {run_id} not found",
        fix="Use GET /ifvg/experiments to list available runs",
        status_code=404,
    )


def invalid_experiment_ids() -> IFVGError:
    return IFVGError(
        code="INVALID_EXPERIMENT_IDS",
        reason="ids must be comma-separated integers",
        fix="Example: /ifvg/experiments/compare?ids=1,2,3",
    )


def testing_plan_item_not_found(item_id: int) -> IFVGError:
    return IFVGError(
        code="TESTING_PLAN_ITEM_NOT_FOUND",
        reason=f"Testing plan item {item_id} not found",
        fix="Use GET /ifvg/testing-plan to list available items",
        status_code=404,
    )
