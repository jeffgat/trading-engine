"""Order-book feature helpers for dynamic LSI sizing.

This module is intentionally feed-agnostic. Live DataBento MBP-10 streaming can
push top-of-book samples into ``OrderbookFeatureCache`` later, while research or
exact-replay paths can validate the same tiering logic from scored CSV values.
"""

from __future__ import annotations

import math
import csv
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable


CONFIRM_LAST_10S_MID_VELOCITY = "confirm_last_10s_mid_velocity_ticks_per_second"


def _is_finite(value: float | None) -> bool:
    return value is not None and math.isfinite(float(value))


@dataclass(frozen=True)
class TopOfBookSample:
    """Minimal top-of-book state needed for midpoint velocity features."""

    symbol: str
    timestamp: datetime
    bid: float
    ask: float
    instrument_id: int | None = None
    raw_symbol: str = ""

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2.0

    @property
    def is_valid(self) -> bool:
        return (
            _is_finite(self.bid)
            and _is_finite(self.ask)
            and self.bid > 0.0
            and self.ask > 0.0
            and self.ask >= self.bid
        )


@dataclass(frozen=True)
class DynamicSizingContext:
    """Causal context available at the entry-sizing decision point."""

    symbol: str
    direction: int
    signal_start: datetime | None = None
    signal_end: datetime | None = None
    feature: str = CONFIRM_LAST_10S_MID_VELOCITY
    config_name: str = ""
    session: str = ""
    entry_price: float | None = None


@dataclass(frozen=True)
class OrderbookDynamicSizingConfig:
    """Frozen thresholds and weights for order-book risk tiering."""

    feature: str = CONFIRM_LAST_10S_MID_VELOCITY
    window_seconds: float = 10.0
    min_coverage: float = 0.8
    fallback_weight: float = 1.0
    low_threshold: float = -0.322
    high_threshold: float = 0.912
    low_weight: float = 0.5
    mid_weight: float = 1.0
    high_weight: float = 1.5
    directions: tuple[int, ...] = (1,)
    min_tick: float = 0.25

    def __post_init__(self) -> None:
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be > 0")
        if not 0.0 <= self.min_coverage <= 1.0:
            raise ValueError("min_coverage must be between 0 and 1")
        if self.low_threshold >= self.high_threshold:
            raise ValueError("low_threshold must be < high_threshold")
        if self.min_tick <= 0:
            raise ValueError("min_tick must be > 0")
        for name, value in (
            ("fallback_weight", self.fallback_weight),
            ("low_weight", self.low_weight),
            ("mid_weight", self.mid_weight),
            ("high_weight", self.high_weight),
        ):
            if value < 0:
                raise ValueError(f"{name} must be >= 0")
        invalid = [direction for direction in self.directions if direction not in (-1, 1)]
        if invalid:
            raise ValueError("directions must contain only -1 and/or 1")


@dataclass(frozen=True)
class DynamicSizingDecision:
    """Result of converting an order-book feature into a risk weight."""

    feature: str
    risk_weight: float
    tier: str = "fallback"
    feature_value: float | None = None
    coverage: float = 0.0
    sample_count: int = 0
    active: bool = False
    reason: str = ""

    def as_metadata(self) -> dict[str, object]:
        return {
            "feature": self.feature,
            "feature_value": self.feature_value,
            "tier": self.tier,
            "risk_weight": self.risk_weight,
            "coverage": self.coverage,
            "sample_count": self.sample_count,
            "active": self.active,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class VelocityWindowResult:
    feature_value: float | None
    coverage: float
    sample_count: int
    reason: str


class OrderbookFeatureCache:
    """Rolling top-of-book sample cache keyed by parent symbol."""

    def __init__(self, retention_seconds: float = 90.0) -> None:
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be > 0")
        self.retention = timedelta(seconds=retention_seconds)
        self._samples: dict[str, deque[TopOfBookSample]] = defaultdict(deque)

    def add_sample(self, sample: TopOfBookSample) -> None:
        if not sample.is_valid:
            return
        bucket = self._samples[sample.symbol]
        bucket.append(sample)
        self._prune_symbol(sample.symbol, sample.timestamp)

    def add_top_of_book(
        self,
        *,
        symbol: str,
        timestamp: datetime,
        bid: float,
        ask: float,
        instrument_id: int | None = None,
        raw_symbol: str = "",
    ) -> None:
        self.add_sample(
            TopOfBookSample(
                symbol=symbol,
                timestamp=timestamp,
                bid=float(bid),
                ask=float(ask),
                instrument_id=instrument_id,
                raw_symbol=raw_symbol,
            )
        )

    def samples(self, symbol: str, *, start: datetime, end: datetime) -> list[TopOfBookSample]:
        if end <= start:
            return []
        return [
            sample
            for sample in self._samples.get(symbol, ())
            if start <= sample.timestamp < end and sample.is_valid
        ]

    def midpoint_velocity(
        self,
        *,
        symbol: str,
        direction: int,
        start: datetime,
        end: datetime,
        min_tick: float,
    ) -> VelocityWindowResult:
        if direction not in (-1, 1):
            return VelocityWindowResult(None, 0.0, 0, "invalid_direction")
        if min_tick <= 0:
            return VelocityWindowResult(None, 0.0, 0, "invalid_min_tick")
        if end <= start:
            return VelocityWindowResult(None, 0.0, 0, "invalid_window")

        coverage = self.coverage(symbol, start=start, end=end)
        window = self.samples(symbol, start=start, end=end)
        if len(window) < 2:
            return VelocityWindowResult(None, coverage, len(window), "insufficient_samples")

        seconds = max((end - start).total_seconds(), 1.0)
        move_ticks = direction * ((window[-1].mid - window[0].mid) / min_tick)
        return VelocityWindowResult(
            float(move_ticks / seconds),
            coverage,
            len(window),
            "ok",
        )

    def coverage(self, symbol: str, *, start: datetime, end: datetime) -> float:
        if end <= start:
            return 0.0
        bucket = self._samples.get(symbol)
        if not bucket:
            return 0.0
        earliest = bucket[0].timestamp
        latest = bucket[-1].timestamp
        covered_start = max(start, earliest)
        covered_end = min(end, latest)
        covered_seconds = max((covered_end - covered_start).total_seconds(), 0.0)
        desired_seconds = max((end - start).total_seconds(), 1.0)
        return min(covered_seconds / desired_seconds, 1.0)

    def status(self) -> dict[str, object]:
        symbols: dict[str, dict[str, object]] = {}
        total_samples = 0
        latest: datetime | None = None
        for symbol, bucket in self._samples.items():
            count = len(bucket)
            total_samples += count
            last = bucket[-1] if bucket else None
            if last is not None and (latest is None or last.timestamp > latest):
                latest = last.timestamp
            symbols[symbol] = {
                "sample_count": count,
                "last_sample_time": last.timestamp.isoformat() if last else None,
                "last_bid": last.bid if last else None,
                "last_ask": last.ask if last else None,
                "last_mid": last.mid if last else None,
                "raw_symbol": last.raw_symbol if last else "",
                "instrument_id": last.instrument_id if last else None,
            }
        return {
            "symbols": symbols,
            "total_samples": total_samples,
            "last_sample_time": latest.isoformat() if latest else None,
            "retention_seconds": self.retention.total_seconds(),
        }

    def _prune_symbol(self, symbol: str, now: datetime) -> None:
        cutoff = now - self.retention
        bucket = self._samples[symbol]
        while bucket and bucket[0].timestamp < cutoff:
            bucket.popleft()


class OrderbookVelocityTierSizer:
    """Convert midpoint velocity into frozen dynamic-sizing decisions."""

    def __init__(self, config: OrderbookDynamicSizingConfig | None = None) -> None:
        self.config = config or OrderbookDynamicSizingConfig()

    def tier_for_value(self, value: float) -> str:
        if value < self.config.low_threshold:
            return "low"
        if value < self.config.high_threshold:
            return "mid"
        return "high"

    def weight_for_tier(self, tier: str) -> float:
        if tier == "low":
            return self.config.low_weight
        if tier == "mid":
            return self.config.mid_weight
        if tier == "high":
            return self.config.high_weight
        return self.config.fallback_weight

    def decision_from_feature_value(
        self,
        value: float | None,
        *,
        direction: int = 1,
        coverage: float = 1.0,
        sample_count: int = 0,
        reason: str = "scored_feature",
    ) -> DynamicSizingDecision:
        if direction not in self.config.directions:
            return self._fallback(coverage=coverage, sample_count=sample_count, reason="direction_disabled")
        if not _is_finite(value):
            return self._fallback(coverage=coverage, sample_count=sample_count, reason="invalid_feature_value")
        if coverage < self.config.min_coverage:
            return self.fallback_decision(
                coverage=coverage,
                sample_count=sample_count,
                reason="insufficient_coverage",
            )

        clean_value = float(value)
        tier = self.tier_for_value(clean_value)
        return DynamicSizingDecision(
            feature=self.config.feature,
            feature_value=clean_value,
            tier=tier,
            risk_weight=self.weight_for_tier(tier),
            coverage=float(coverage),
            sample_count=int(sample_count),
            active=True,
            reason=reason,
        )

    def decision_from_cache(
        self,
        context: DynamicSizingContext,
        cache: OrderbookFeatureCache,
    ) -> DynamicSizingDecision:
        if context.feature != self.config.feature:
            return self._fallback(reason="feature_not_supported")
        signal_end = context.signal_end
        if signal_end is None:
            return self._fallback(reason="missing_signal_end")
        start = signal_end - timedelta(seconds=self.config.window_seconds)
        result = cache.midpoint_velocity(
            symbol=context.symbol,
            direction=context.direction,
            start=start,
            end=signal_end,
            min_tick=self.config.min_tick,
        )
        return self.decision_from_feature_value(
            result.feature_value,
            direction=context.direction,
            coverage=result.coverage,
            sample_count=result.sample_count,
            reason=result.reason,
        )

    def _fallback(
        self,
        *,
        coverage: float = 0.0,
        sample_count: int = 0,
        reason: str = "",
    ) -> DynamicSizingDecision:
        return self.fallback_decision(coverage=coverage, sample_count=sample_count, reason=reason)

    def fallback_decision(
        self,
        *,
        coverage: float = 0.0,
        sample_count: int = 0,
        reason: str = "",
    ) -> DynamicSizingDecision:
        return DynamicSizingDecision(
            feature=self.config.feature,
            risk_weight=self.config.fallback_weight,
            tier="fallback",
            feature_value=None,
            coverage=float(coverage),
            sample_count=int(sample_count),
            active=False,
            reason=reason,
        )


def _parse_replay_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _timestamp_key(value: datetime | None) -> str:
    if value is None:
        return ""
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.isoformat(timespec="seconds")


class ScoredFeatureLookupProvider:
    """Replay existing scored feature rows through the live sizing interface."""

    def __init__(
        self,
        scores: dict[tuple[str, str, int], DynamicSizingDecision],
        *,
        sizer: OrderbookVelocityTierSizer | None = None,
    ) -> None:
        self._scores = scores
        self.sizer = sizer or OrderbookVelocityTierSizer()

    @classmethod
    def from_csv(
        cls,
        path: str | Path,
        *,
        overlay: str = "",
        candidate: str = "",
        feature: str = CONFIRM_LAST_10S_MID_VELOCITY,
        profile: str = "",
        sizer: OrderbookVelocityTierSizer | None = None,
    ) -> "ScoredFeatureLookupProvider":
        scorer = sizer or OrderbookVelocityTierSizer()
        scores: dict[tuple[str, str, int], DynamicSizingDecision] = {}
        with Path(path).open(newline="") as handle:
            for row in csv.DictReader(handle):
                row_overlay = row.get("overlay")
                if overlay and row_overlay and row_overlay != overlay:
                    continue

                row_candidate = row.get("candidate") or _candidate_from_trade_uid(row.get("trade_uid"))
                if candidate and row_candidate != candidate:
                    continue

                row_feature = row.get("feature") or feature
                if feature and row_feature != feature:
                    continue

                row_profile = row.get("profile") or row.get("weight_profile")
                if profile and row_profile and row_profile != profile:
                    continue

                signal_start = _parse_replay_timestamp(
                    row.get("signal_start")
                    or row.get("entry_timestamp")
                    or row.get("timestamp")
                )
                if signal_start is None:
                    continue
                try:
                    direction = int(float(row.get("direction") or 0))
                except (TypeError, ValueError):
                    continue
                if direction not in (-1, 1):
                    continue

                value: float | None
                try:
                    value = float(
                        row.get("feature_value")
                        or row.get("actual_feature_value")
                        or row.get("expected_feature_value")
                        or row.get("value")
                        or "nan"
                    )
                except (TypeError, ValueError):
                    value = None
                coverage = _float_or_default(row.get("coverage"), 1.0)
                sample_count = int(_float_or_default(row.get("sample_count"), 0.0))
                decision = scorer.decision_from_feature_value(
                    value,
                    direction=direction,
                    coverage=coverage,
                    sample_count=sample_count,
                    reason=str(row.get("reason") or "scored_feature_csv"),
                )
                key = (signal_start.date().isoformat(), _timestamp_key(signal_start), direction)
                scores[key] = decision
        return cls(scores, sizer=scorer)

    def __call__(self, context: DynamicSizingContext) -> DynamicSizingDecision:
        signal_start = context.signal_start or context.signal_end
        if signal_start is None:
            return self.sizer.fallback_decision(reason="missing_signal_start")
        key = (signal_start.date().isoformat(), _timestamp_key(signal_start), int(context.direction))
        decision = self._scores.get(key)
        if decision is None:
            return self.sizer.fallback_decision(reason="scored_feature_missing")
        return decision


def _float_or_default(value: object, default: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _candidate_from_trade_uid(value: object) -> str:
    text = str(value or "")
    if "|" not in text:
        return ""
    return text.split("|", maxsplit=1)[0]


def unique_trade_dates(rows: Iterable[dict[str, object]], *, date_key: str = "date") -> set[str]:
    """Return unique YYYY-MM-DD dates from replay rows."""

    return {str(row[date_key]) for row in rows if row.get(date_key)}
