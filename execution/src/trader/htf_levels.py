"""Incremental HTF level publication for the live HTF-LSI engine.

Builds regular ET clock bars (30m / 60m / 90m) from the incoming 5m bar stream,
then publishes the latest unswept HTF high and low only after ``n_left`` later
HTF bars have completed. This mirrors the research-side HTF-LSI structure:

- the HTF bar itself must be complete
- ``n_left`` later HTF bars must have printed
- the candidate high/low must remain unswept until publication

After publication, the live engine owns level consumption/reuse semantics.
"""

from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any


@dataclass
class PendingHtfBar:
    """A completed HTF bar waiting to become publishable."""

    start_time: str
    high: float
    low: float
    publish_time: str = ""
    high_swept_before_publish: bool = False
    low_swept_before_publish: bool = False


@dataclass
class PublishedHtfLevel:
    """The latest published HTF level for one side."""

    instance_id: int
    price: float
    level_time: str
    publish_time: str


def _floor_bucket_start(ts: datetime, tf_minutes: int) -> datetime:
    total_minutes = ts.hour * 60 + ts.minute
    bucket_minutes = (total_minutes // tf_minutes) * tf_minutes
    return ts.replace(
        hour=bucket_minutes // 60,
        minute=bucket_minutes % 60,
        second=0,
        microsecond=0,
    )


class HtfLevelTracker:
    """Incrementally publish the latest valid unswept HTF high/low."""

    def __init__(
        self,
        *,
        tf_minutes: int = 60,
        n_left: int = 5,
        base_bar_minutes: int = 5,
    ) -> None:
        if tf_minutes not in {30, 60, 90}:
            raise ValueError(f"tf_minutes must be one of 30, 60, 90 (got {tf_minutes!r})")
        if n_left < 1:
            raise ValueError(f"n_left must be >= 1 (got {n_left!r})")
        if base_bar_minutes <= 0:
            raise ValueError(f"base_bar_minutes must be > 0 (got {base_bar_minutes!r})")

        self.tf_minutes = tf_minutes
        self.n_left = n_left
        self.base_bar_minutes = base_bar_minutes
        self._base_delta = timedelta(minutes=base_bar_minutes)

        self._current_bucket_start: datetime | None = None
        self._current_bucket_high: float = float("-inf")
        self._current_bucket_low: float = float("inf")

        self._pending: deque[PendingHtfBar] = deque()
        self._latest_high: PublishedHtfLevel | None = None
        self._latest_low: PublishedHtfLevel | None = None
        self._next_high_instance_id: int = 0
        self._next_low_instance_id: int = 0

    def _bucket_end(self, bucket_start: datetime) -> datetime:
        return bucket_start + timedelta(minutes=self.tf_minutes)

    def _scheduled_publish_time(self, bucket_start: datetime) -> datetime:
        return bucket_start + timedelta(minutes=(self.n_left + 1) * self.tf_minutes)

    def _pending_publish_dt(self, candidate: PendingHtfBar) -> datetime:
        if candidate.publish_time:
            return datetime.fromisoformat(candidate.publish_time)
        return self._scheduled_publish_time(datetime.fromisoformat(candidate.start_time))

    @property
    def latest_high(self) -> PublishedHtfLevel | None:
        return self._latest_high

    @property
    def latest_low(self) -> PublishedHtfLevel | None:
        return self._latest_low

    def on_bar(self, bar: Any) -> None:
        """Process a completed 5m bar and update HTF publication state."""
        bucket_start = _floor_bucket_start(bar.timestamp, self.tf_minutes)
        if self._current_bucket_start is None:
            self._current_bucket_start = bucket_start

        if bucket_start != self._current_bucket_start:
            # Sparse 1m/5m streams can jump past the clock-close of the current
            # HTF bucket. Mirror the research path by closing the stale bucket
            # at its true bucket end instead of the timestamp of the next trade.
            self._finalize_bucket(publish_time=self._bucket_end(self._current_bucket_start).isoformat())
            self._current_bucket_start = bucket_start
            self._current_bucket_high = float("-inf")
            self._current_bucket_low = float("inf")

        # Publish any candidates whose fixed clock-time publish boundary has
        # already passed before letting the current bar invalidate unpublished
        # levels. This matches the research alignment on sparse raw 1m data.
        self._publish_ready(current_time=bar.timestamp)

        # Any already-completed unpublished HTF bar can be invalidated by this
        # newly completed base bar only while it is still pending publication.
        current_bar_ts = bar.timestamp
        for pending in self._pending:
            if self._pending_publish_dt(pending) <= current_bar_ts:
                continue
            if float(bar.high) > pending.high:
                pending.high_swept_before_publish = True
            if float(bar.low) < pending.low:
                pending.low_swept_before_publish = True

        self._current_bucket_high = max(self._current_bucket_high, float(bar.high))
        self._current_bucket_low = min(self._current_bucket_low, float(bar.low))

        bar_end = bar.timestamp + self._base_delta
        bucket_end = self._bucket_end(self._current_bucket_start)
        if bar_end >= bucket_end:
            self._finalize_bucket(publish_time=bar_end.isoformat())
            self._current_bucket_start = None
            self._current_bucket_high = float("-inf")
            self._current_bucket_low = float("inf")

    def reset(self) -> None:
        self._current_bucket_start = None
        self._current_bucket_high = float("-inf")
        self._current_bucket_low = float("inf")
        self._pending.clear()
        self._latest_high = None
        self._latest_low = None
        self._next_high_instance_id = 0
        self._next_low_instance_id = 0

    def _finalize_bucket(self, *, publish_time: str) -> None:
        if self._current_bucket_start is None:
            return
        if self._current_bucket_high == float("-inf") or self._current_bucket_low == float("inf"):
            return

        self._pending.append(
            PendingHtfBar(
                start_time=self._current_bucket_start.isoformat(),
                high=float(self._current_bucket_high),
                low=float(self._current_bucket_low),
                publish_time=self._scheduled_publish_time(self._current_bucket_start).isoformat(),
            )
        )
        self._publish_ready(current_time=datetime.fromisoformat(publish_time))

    def _publish_ready(self, *, current_time: datetime) -> None:
        while self._pending:
            next_publish = self._pending_publish_dt(self._pending[0])
            if next_publish > current_time:
                break
            candidate = self._pending.popleft()
            if not candidate.high_swept_before_publish:
                self._latest_high = PublishedHtfLevel(
                    instance_id=self._next_high_instance_id,
                    price=candidate.high,
                    level_time=candidate.start_time,
                    publish_time=next_publish.isoformat(),
                )
                self._next_high_instance_id += 1
            if not candidate.low_swept_before_publish:
                self._latest_low = PublishedHtfLevel(
                    instance_id=self._next_low_instance_id,
                    price=candidate.low,
                    level_time=candidate.start_time,
                    publish_time=next_publish.isoformat(),
                )
                self._next_low_instance_id += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "tf_minutes": self.tf_minutes,
            "n_left": self.n_left,
            "base_bar_minutes": self.base_bar_minutes,
            "current_bucket_start": (
                self._current_bucket_start.isoformat() if self._current_bucket_start else None
            ),
            "current_bucket_high": (
                None if self._current_bucket_high == float("-inf") else self._current_bucket_high
            ),
            "current_bucket_low": (
                None if self._current_bucket_low == float("inf") else self._current_bucket_low
            ),
            "pending": [asdict(item) for item in self._pending],
            "latest_high": asdict(self._latest_high) if self._latest_high else None,
            "latest_low": asdict(self._latest_low) if self._latest_low else None,
            "next_high_instance_id": self._next_high_instance_id,
            "next_low_instance_id": self._next_low_instance_id,
        }

    def restore(self, data: dict[str, Any]) -> None:
        self.tf_minutes = int(data.get("tf_minutes", self.tf_minutes))
        self.n_left = int(data.get("n_left", self.n_left))
        self.base_bar_minutes = int(data.get("base_bar_minutes", self.base_bar_minutes))
        self._base_delta = timedelta(minutes=self.base_bar_minutes)

        current_bucket_start = data.get("current_bucket_start")
        self._current_bucket_start = (
            datetime.fromisoformat(current_bucket_start) if current_bucket_start else None
        )
        current_bucket_high = data.get("current_bucket_high")
        current_bucket_low = data.get("current_bucket_low")
        self._current_bucket_high = (
            float(current_bucket_high) if current_bucket_high is not None else float("-inf")
        )
        self._current_bucket_low = (
            float(current_bucket_low) if current_bucket_low is not None else float("inf")
        )

        self._pending.clear()
        for item in data.get("pending", []):
            self._pending.append(PendingHtfBar(**item))

        latest_high = data.get("latest_high")
        latest_low = data.get("latest_low")
        self._latest_high = PublishedHtfLevel(**latest_high) if latest_high else None
        self._latest_low = PublishedHtfLevel(**latest_low) if latest_low else None
        self._next_high_instance_id = int(data.get("next_high_instance_id", 0))
        self._next_low_instance_id = int(data.get("next_low_instance_id", 0))
