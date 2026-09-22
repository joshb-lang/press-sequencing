"""Press time budgets and makeready.

Each work type gets a time window derived from press speed and anticipated
volume. Overflow truncates the list unless another bucket has room to absorb
it, in which case buckets readjust.

The three numbers this model needs — where time went on missed-SLA batches,
how many were reprints or double prints, and how press hours split between
changeover, idle and unstaffed — are not yet measured. The makeready figures
below are configuration precisely so they can be replaced with measured ones
without touching code. Until then, treat any output that depends on them as
indicative.
"""

from __future__ import annotations

from dataclasses import dataclass

from .eligibility import Condition
from .model import Batch, Press


@dataclass(frozen=True)
class Makeready:
    """Changeover cost model.

    `changeover_attributes` names the attributes whose change between
    consecutive batches costs a changeover — stock and lamination, typically.
    A deliberately crude model: if the Aug-Sep measurement shows changeover is
    a thin slice of press hours, the ceiling on all of this is low and the
    model should not be elaborated before that is known.
    """

    default_minutes: float = 0.0
    changeover_minutes: float = 0.0
    changeover_attributes: tuple[str, ...] = ()

    def minutes_for(self, batch: Batch, previous: Batch | None) -> float:
        if previous is None:
            return self.changeover_minutes + self.default_minutes
        changed = any(
            batch.attributes.get(a) != previous.attributes.get(a)
            for a in self.changeover_attributes
        )
        return self.default_minutes + (self.changeover_minutes if changed else 0.0)


def run_minutes(batch: Batch, press: Press) -> float:
    return batch.sheets / press.sheets_per_hour * 60.0


@dataclass(frozen=True)
class Bucket:
    """A work-type time window."""

    bucket_id: str
    when: Condition
    share: float | None = None
    minutes: float | None = None

    def __post_init__(self) -> None:
        if (self.share is None) == (self.minutes is None):
            raise ValueError(f"{self.bucket_id}: set exactly one of share or minutes")
        if self.share is not None and not 0 < self.share <= 1:
            raise ValueError(f"{self.bucket_id}: share must be in (0, 1]")
        if self.minutes is not None and self.minutes <= 0:
            raise ValueError(f"{self.bucket_id}: minutes must be positive")

    def matches(self, batch: Batch) -> bool:
        return self.when.matches(batch)


@dataclass(frozen=True)
class TimeBudget:
    buckets: tuple[Bucket, ...] = ()
    allow_reallocation: bool = True

    def bucket_for(self, batch: Batch) -> Bucket | None:
        for b in self.buckets:
            if b.matches(batch):
                return b
        return None

    def windows(self, available_minutes: float) -> dict[str, float]:
        """Time window per bucket for a press with `available_minutes` on shift."""
        return {
            b.bucket_id: (b.minutes if b.minutes is not None else b.share * available_minutes)
            for b in self.buckets
        }


class BudgetLedger:
    """Tracks bucket consumption on one press and decides what still fits.

    Reallocation is the "buckets readjust" behaviour: a bucket that overflows
    may borrow unused time from buckets that have headroom, so a quiet work
    type does not hold minutes a busy one needs. With reallocation off, a
    bucket is a hard cap and overflow truncates.
    """

    def __init__(self, budget: TimeBudget, available_minutes: float) -> None:
        self._budget = budget
        self._available = available_minutes
        self._windows = budget.windows(available_minutes)
        self._used: dict[str, float] = {k: 0.0 for k in self._windows}
        self._unbucketed_used = 0.0

    @property
    def total_used(self) -> float:
        return sum(self._used.values()) + self._unbucketed_used

    @property
    def remaining(self) -> float:
        return self._available - self.total_used

    def headroom(self, bucket_id: str) -> float:
        return self._windows[bucket_id] - self._used[bucket_id]

    def fits(self, batch: Batch, minutes: float) -> bool:
        if minutes > self.remaining:
            return False
        bucket = self._budget.bucket_for(batch)
        if bucket is None:
            # Work no bucket claims is capped only by the press's own time.
            return True
        if minutes <= self.headroom(bucket.bucket_id):
            return True
        if not self._budget.allow_reallocation:
            return False
        # Borrow from buckets with spare time; the press total still applies.
        spare = sum(
            max(0.0, self.headroom(b)) for b in self._windows if b != bucket.bucket_id
        )
        return minutes <= self.headroom(bucket.bucket_id) + spare

    def charge(self, batch: Batch, minutes: float) -> None:
        bucket = self._budget.bucket_for(batch)
        if bucket is None:
            self._unbucketed_used += minutes
        else:
            self._used[bucket.bucket_id] += minutes
