"""Pre-trade gate helpers for execution engines.

These gates intentionally mirror the backtesting research logic closely:
- Daily bull/no-low-confidence regime routing for the bull specialist.
- Frozen combined-regime medium-vol avoidance gates.
- 15m HH/HL + VWAP context confirmation on the signal bar.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

DailyHistoryProvider = Callable[[str], list[tuple[date, float, float, float, float]]]
RegimeGateCheck = Callable[[str], bool]
CompiledRegimeGate = tuple[str, RegimeGateCheck]

_daily_history_provider: DailyHistoryProvider | None = None

# Frozen pre-holdout tercile thresholds from regime research.
_LOW_VOL_UPPER = 0.1252
_MEDIUM_VOL_UPPER = 0.2040


@dataclass(frozen=True)
class RegimeGateEvaluation:
    gate: str
    date_key: str
    allowed: bool
    reason: str | None = None
    regime: str | None = None
    vol_regime: str | None = None
    combined_regime: str | None = None
    low_confidence: bool | None = None
    warmup_ok: bool | None = None

    def to_status_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "gate": self.gate,
            "date": self.date_key,
            "allowed": self.allowed,
        }
        if self.reason:
            result["reason"] = self.reason
        if self.regime is not None:
            result["regime"] = self.regime
        if self.vol_regime is not None:
            result["vol_regime"] = self.vol_regime
        if self.combined_regime is not None:
            result["combined_regime"] = self.combined_regime
        if self.low_confidence is not None:
            result["low_confidence"] = self.low_confidence
        if self.warmup_ok is not None:
            result["warmup_ok"] = self.warmup_ok
        return result


def _bars_to_frame(bars) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open": [bar.open for bar in bars],
            "high": [bar.high for bar in bars],
            "low": [bar.low for bar in bars],
            "close": [bar.close for bar in bars],
            "volume": [bar.volume for bar in bars],
        },
        index=pd.DatetimeIndex([bar.timestamp for bar in bars]),
    )


def _daily_bars_to_frame(
    daily_bars: list[tuple[date, float, float, float, float]],
) -> pd.DataFrame:
    if not daily_bars:
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    df = pd.DataFrame(
        daily_bars,
        columns=["date", "open", "high", "low", "close"],
    )
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def _append_placeholder_day_if_needed(df: pd.DataFrame, date_key: str) -> pd.DataFrame:
    if df.empty:
        return df

    requested = pd.Timestamp(datetime.strptime(date_key, "%Y%m%d").date())
    if requested in df.index:
        return df

    last_date = df.index[-1]
    if requested != last_date + timedelta(days=1):
        return df

    last_row = df.iloc[-1]
    placeholder = pd.DataFrame(
        {
            "open": [last_row["close"]],
            "high": [last_row["close"]],
            "low": [last_row["close"]],
            "close": [last_row["close"]],
        },
        index=pd.DatetimeIndex([requested]),
    )
    return pd.concat([df, placeholder])


def _build_nq_ny_regime_calendar(daily: pd.DataFrame) -> pd.DataFrame:
    if daily.empty:
        return pd.DataFrame(columns=["date", "low_confidence", "regime"])

    close = daily["close"]
    log_returns = np.log(close / close.shift(1))
    realized_vol_21d = log_returns.rolling(21, min_periods=21).std() * np.sqrt(252)
    close_vs_sma20 = close / close.rolling(20, min_periods=20).mean() - 1.0
    ret_5d = close.pct_change(5)

    calendar = pd.DataFrame(
        {
            "date": daily.index.normalize(),
            "close_vs_sma20": close_vs_sma20.shift(1),
            "ret_5d": ret_5d.shift(1),
            "realized_vol_21d": realized_vol_21d.shift(1),
        }
    )
    calendar["warmup_ok"] = calendar[["close_vs_sma20", "ret_5d", "realized_vol_21d"]].notna().all(axis=1)
    calendar["low_confidence"] = calendar["warmup_ok"] & (
        (calendar["close_vs_sma20"].abs() < 0.0025) | (calendar["ret_5d"].abs() < 0.005)
    )

    bull_mask = calendar["warmup_ok"] & (calendar["close_vs_sma20"] >= 0.005) & (calendar["ret_5d"] > 0.0)
    bear_mask = calendar["warmup_ok"] & (calendar["close_vs_sma20"] <= -0.005) & (calendar["ret_5d"] < 0.0)

    calendar["regime"] = "sideways"
    calendar.loc[bull_mask, "regime"] = "bull"
    calendar.loc[bear_mask, "regime"] = "bear"
    calendar.loc[~calendar["warmup_ok"], "regime"] = "warmup"
    return calendar.reset_index(drop=True)


def _classify_vol(vol_value: float) -> str:
    if pd.isna(vol_value):
        return "unknown"
    if vol_value <= _LOW_VOL_UPPER:
        return "low_vol"
    if vol_value <= _MEDIUM_VOL_UPPER:
        return "medium_vol"
    return "high_vol"


def _build_nq_ny_extended_regime_calendar(daily: pd.DataFrame) -> pd.DataFrame:
    calendar = _build_nq_ny_regime_calendar(daily)
    if calendar.empty:
        return pd.DataFrame(columns=["date", "low_confidence", "regime", "vol_regime", "combined_regime"])

    calendar["vol_regime"] = calendar["realized_vol_21d"].apply(_classify_vol)
    calendar.loc[~calendar["warmup_ok"], "vol_regime"] = "unknown"
    calendar["combined_regime"] = calendar.apply(
        lambda row: "warmup" if str(row["regime"]) == "warmup" else f"{row['regime']}_{row['vol_regime']}",
        axis=1,
    )
    return calendar


def _session_vwap(df: pd.DataFrame) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    cum_vol = df["volume"].cumsum().replace(0, np.nan)
    return (typical * df["volume"]).cumsum() / cum_vol


def _hh_hl_2_bull(session_bars) -> bool:
    if len(session_bars) < 9:
        return False

    current_idx = len(session_bars) - 1
    current_group = current_idx // 3
    pos_in_group = current_idx % 3
    last_complete_group = current_group if pos_in_group == 2 else current_group - 1
    if last_complete_group < 2:
        return False

    highs: list[float] = []
    lows: list[float] = []
    for group in range(last_complete_group + 1):
        start = group * 3
        chunk = session_bars[start : start + 3]
        if len(chunk) < 3:
            break
        highs.append(max(bar.high for bar in chunk))
        lows.append(min(bar.low for bar in chunk))

    if len(highs) <= last_complete_group:
        return False

    k = last_complete_group
    return (
        highs[k] > highs[k - 1]
        and lows[k] > lows[k - 1]
        and highs[k - 1] > highs[k - 2]
        and lows[k - 1] > lows[k - 2]
    )


def set_daily_history_provider(provider: DailyHistoryProvider | None) -> None:
    global _daily_history_provider
    _daily_history_provider = provider


def normalize_regime_gates(
    legacy_gate: str | None,
    configured_gates: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    normalized: list[str] = []
    seen: set[str] = set()

    def _append(name: str | None) -> None:
        if not name:
            return
        trimmed = str(name).strip()
        if not trimmed or trimmed == "none" or trimmed in seen:
            return
        normalized.append(trimmed)
        seen.add(trimmed)

    _append(legacy_gate)
    for name in configured_gates or ():
        _append(name)
    return tuple(normalized)


def _load_nq_daily_history(name: str, date_key: str) -> pd.DataFrame | None:
    if _daily_history_provider is None:
        logger.warning(
            "Regime gate '%s' has no daily history provider — blocking date=%s",
            name,
            date_key,
        )
        return None

    daily_bars = _daily_history_provider("NQ.FUT")
    if not daily_bars:
        logger.warning(
            "Regime gate '%s' has no NQ daily history — blocking date=%s",
            name,
            date_key,
        )
        return None

    daily = _daily_bars_to_frame(daily_bars)
    daily = _append_placeholder_day_if_needed(daily, date_key)
    if daily.empty:
        logger.warning(
            "Regime gate '%s' could not build a daily frame from NQ history — blocking date=%s",
            name,
            date_key,
        )
        return None
    return daily


def _calendar_row_for_date(
    calendar: pd.DataFrame,
    *,
    name: str,
    date_key: str,
    daily: pd.DataFrame,
) -> pd.Series | None:
    if calendar.empty:
        logger.warning(
            "Regime gate '%s' could not build a calendar from NQ daily history — blocking date=%s",
            name,
            date_key,
        )
        return None

    row_df = calendar.loc[pd.to_datetime(calendar["date"]).dt.strftime("%Y%m%d") == date_key]
    if row_df.empty:
        logger.warning(
            "Regime gate '%s' has no calendar row for date=%s (history_end=%s) — blocking",
            name,
            date_key,
            daily.index[-1].strftime("%Y%m%d") if not daily.empty else "-",
        )
        return None
    if len(row_df) > 1:
        logger.warning(
            "Regime gate '%s' found %d calendar rows for date=%s — using last",
            name,
            len(row_df),
            date_key,
        )
    return row_df.iloc[-1]


def _optional_bool(value) -> bool | None:
    if pd.isna(value):
        return None
    return bool(value)


def _optional_str(value) -> str | None:
    if pd.isna(value):
        return None
    text = str(value)
    return text if text else None


def _missing_gate_evaluation(name: str, date_key: str, reason: str) -> RegimeGateEvaluation:
    return RegimeGateEvaluation(
        gate=name,
        date_key=date_key,
        allowed=False,
        reason=reason,
    )


def _evaluate_bull_no_low_confidence_gate(name: str, date_key: str) -> RegimeGateEvaluation:
    daily = _load_nq_daily_history(name, date_key)
    if daily is None:
        return _missing_gate_evaluation(name, date_key, "missing_daily_history")

    calendar = _build_nq_ny_regime_calendar(daily)
    row = _calendar_row_for_date(calendar, name=name, date_key=date_key, daily=daily)
    if row is None:
        return _missing_gate_evaluation(name, date_key, "missing_calendar_row")

    regime = _optional_str(row.get("regime"))
    low_confidence = _optional_bool(row.get("low_confidence"))
    warmup_ok = _optional_bool(row.get("warmup_ok"))
    allowed = regime == "bull" and not bool(low_confidence)
    return RegimeGateEvaluation(
        gate=name,
        date_key=date_key,
        allowed=allowed,
        regime=regime,
        low_confidence=low_confidence,
        warmup_ok=warmup_ok,
    )


def _evaluate_combined_regime_block_gate(
    name: str,
    date_key: str,
    blocked_buckets: frozenset[str],
) -> RegimeGateEvaluation:
    daily = _load_nq_daily_history(name, date_key)
    if daily is None:
        return _missing_gate_evaluation(name, date_key, "missing_daily_history")

    calendar = _build_nq_ny_extended_regime_calendar(daily)
    row = _calendar_row_for_date(calendar, name=name, date_key=date_key, daily=daily)
    if row is None:
        return _missing_gate_evaluation(name, date_key, "missing_calendar_row")

    combined_regime = _optional_str(row.get("combined_regime"))
    return RegimeGateEvaluation(
        gate=name,
        date_key=date_key,
        allowed=combined_regime not in blocked_buckets,
        regime=_optional_str(row.get("regime")),
        vol_regime=_optional_str(row.get("vol_regime")),
        combined_regime=combined_regime,
        low_confidence=_optional_bool(row.get("low_confidence")),
        warmup_ok=_optional_bool(row.get("warmup_ok")),
    )


def _build_bull_no_low_confidence_gate(name: str) -> RegimeGateCheck:
    def _gate(date_key: str) -> bool:
        return _evaluate_bull_no_low_confidence_gate(name, date_key).allowed

    return _gate


def _build_combined_regime_block_gate(
    name: str,
    blocked_buckets: frozenset[str],
) -> RegimeGateCheck:
    def _gate(date_key: str) -> bool:
        return _evaluate_combined_regime_block_gate(name, date_key, blocked_buckets).allowed

    return _gate


_REGIME_GATE_BUILDERS: dict[str, Callable[[str], RegimeGateCheck]] = {
    "bull_no_low_confidence": _build_bull_no_low_confidence_gate,
    "block_bull_low_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"bull_low_vol"})),
    "block_bull_medium_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"bull_medium_vol"})),
    "block_bull_high_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"bull_high_vol"})),
    "block_bear_medium_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"bear_medium_vol"})),
    "block_bear_high_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"bear_high_vol"})),
    "block_sideways_medium_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"sideways_medium_vol"})),
    "block_sideways_high_vol": lambda name: _build_combined_regime_block_gate(name, frozenset({"sideways_high_vol"})),
    "block_full_medium_vol": lambda name: _build_combined_regime_block_gate(
        name,
        frozenset({"bull_medium_vol", "sideways_medium_vol"}),
    ),
    "block_full_high_vol": lambda name: _build_combined_regime_block_gate(
        name,
        frozenset({"bull_high_vol", "bear_high_vol", "sideways_high_vol"}),
    ),
}

_REGIME_GATE_EVALUATORS: dict[str, Callable[[str, str], RegimeGateEvaluation]] = {
    "bull_no_low_confidence": _evaluate_bull_no_low_confidence_gate,
    "block_bull_low_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bull_low_vol"}),
    ),
    "block_bull_medium_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bull_medium_vol"}),
    ),
    "block_bull_high_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bull_high_vol"}),
    ),
    "block_bear_medium_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bear_medium_vol"}),
    ),
    "block_bear_high_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bear_high_vol"}),
    ),
    "block_sideways_medium_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"sideways_medium_vol"}),
    ),
    "block_sideways_high_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"sideways_high_vol"}),
    ),
    "block_full_medium_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bull_medium_vol", "sideways_medium_vol"}),
    ),
    "block_full_high_vol": lambda name, date_key: _evaluate_combined_regime_block_gate(
        name,
        date_key,
        frozenset({"bull_high_vol", "bear_high_vol", "sideways_high_vol"}),
    ),
}


def required_daily_history_symbols_for_regime_gates(
    names: list[str] | tuple[str, ...] | None,
) -> tuple[str, ...]:
    """Return extra daily-history symbols required to evaluate *names*.

    All current execution regime gates are derived from the NQ daily regime
    calendar, even when the traded session is a different instrument.
    """
    if not normalize_regime_gates(None, names):
        return ()
    return ("NQ.FUT",)


def build_regime_gates(
    names: list[str] | tuple[str, ...] | None,
) -> tuple[CompiledRegimeGate, ...]:
    compiled: list[CompiledRegimeGate] = []
    for name in normalize_regime_gates(None, names):
        builder = _REGIME_GATE_BUILDERS.get(name)
        if builder is None:
            raise ValueError(f"Unknown regime gate: {name}")
        compiled.append((name, builder(name)))
    return tuple(compiled)


def build_regime_gate(name: str | None) -> RegimeGateCheck | None:
    if not name or name == "none":
        return None
    compiled = build_regime_gates((name,))
    return compiled[0][1] if compiled else None


def evaluate_regime_gate(name: str, date_key: str) -> RegimeGateEvaluation:
    evaluator = _REGIME_GATE_EVALUATORS.get(name)
    if evaluator is None:
        raise ValueError(f"Unknown regime gate: {name}")
    return evaluator(name, date_key)


def evaluate_regime_gates(
    names: list[str] | tuple[str, ...] | None,
    date_key: str,
) -> tuple[RegimeGateEvaluation, ...]:
    return tuple(
        evaluate_regime_gate(name, date_key)
        for name in normalize_regime_gates(None, names)
    )


def format_regime_gate_detail(evaluation: RegimeGateEvaluation) -> str:
    parts = [
        f"gate={evaluation.gate}",
        f"date={evaluation.date_key}",
    ]
    if evaluation.reason:
        parts.append(f"reason={evaluation.reason}")
    if evaluation.regime is not None:
        parts.append(f"regime={evaluation.regime}")
    if evaluation.vol_regime is not None:
        parts.append(f"vol_regime={evaluation.vol_regime}")
    if evaluation.combined_regime is not None:
        parts.append(f"combined_regime={evaluation.combined_regime}")
    if evaluation.low_confidence is not None:
        parts.append(f"low_confidence={str(evaluation.low_confidence).lower()}")
    if evaluation.warmup_ok is not None:
        parts.append(f"warmup_ok={str(evaluation.warmup_ok).lower()}")
    return " ".join(parts)


def normalize_regime_gate_fields(
    regime_gate: str | None,
    regime_gates: tuple[str, ...] | list[str],
    regime_gate_check: RegimeGateCheck | None,
    regime_gate_checks: tuple[CompiledRegimeGate, ...] | list[CompiledRegimeGate],
) -> tuple[str | None, tuple[str, ...], RegimeGateCheck | None, tuple[CompiledRegimeGate, ...]]:
    """Normalize and cross-link the four regime-gate fields.

    Returns (regime_gate, regime_gates, regime_gate_check, regime_gate_checks)
    with consistent values.  Used by both ORBEngine and LSIEngine at init time.
    """
    gates_t: tuple[str, ...] = tuple(regime_gates)
    checks_t: tuple[CompiledRegimeGate, ...] = tuple(regime_gate_checks)

    if checks_t:
        gates_t = tuple(name for name, _check in checks_t)
        if len(checks_t) == 1:
            regime_gate = regime_gate or checks_t[0][0]
            regime_gate_check = regime_gate_check or checks_t[0][1]
        elif regime_gate not in gates_t:
            regime_gate = None
    elif regime_gate_check is not None:
        gate_name = regime_gate or "custom"
        gates_t = (gate_name,)
        checks_t = ((gate_name, regime_gate_check),)
        regime_gate = gate_name
    elif gates_t:
        if len(gates_t) != 1 or regime_gate not in gates_t:
            regime_gate = gates_t[0] if len(gates_t) == 1 else None

    return regime_gate, gates_t, regime_gate_check, checks_t


def blocking_regime_gate_name(
    regime_gate_checks: tuple[CompiledRegimeGate, ...],
    date_key: str,
) -> str | None:
    """Return the name of the first regime gate that blocks *date_key*, or None."""
    for gate_name, gate_check in regime_gate_checks:
        if not gate_check(date_key):
            return gate_name
    return None


def build_structure_gate(name: str | None):
    if not name or name == "none":
        return None
    if name != "hh_hl_2_vwap":
        raise ValueError(f"Unknown structure gate: {name}")

    def _gate(engine, _bar) -> bool:
        session_bars = getattr(engine, "_session_bars", [])
        if len(session_bars) < 3:
            return False

        df = _bars_to_frame(session_bars)
        vwap_value = float(_session_vwap(df).iloc[-1])
        close_value = float(df["close"].iloc[-1])
        if np.isnan(vwap_value):
            return False

        return _hh_hl_2_bull(session_bars) and close_value > vwap_value

    return _gate
