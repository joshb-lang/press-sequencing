"""Domain types for press sequencing.

Nothing in this module is specific to a press queue app, a portal or a
dispatcher. These are the facts a sequence is computed from.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

Attributes = dict[str, str]


@dataclass(frozen=True)
class ProductClass:
    """A named attribute combination, e.g. 16pt + matte lamination.

    A class matches a batch when every attribute it names is present on the
    batch with the same value. Classes are therefore allowed to overlap; the
    rule that references a class decides what that means for ordering.
    """

    name: str
    attributes: Attributes

    def matches(self, batch: Batch) -> bool:
        return all(batch.attributes.get(k) == v for k, v in self.attributes.items())


@dataclass(frozen=True)
class Batch:
    """A batch of work.

    `batch_id` is a first-class field. It is never derived from a filename:
    prefix and extension inconsistencies across WorkerBee, HP and Snowflake
    have broken joins before. This package provides no filename parsing, by
    design.
    """

    batch_id: str
    attributes: Attributes
    sheets: int
    quoted_ship_date: date
    qc_rejected: bool = False

    def __post_init__(self) -> None:
        if not self.batch_id or not self.batch_id.strip():
            raise ValueError("batch_id is required and must be non-empty")
        if self.sheets <= 0:
            raise ValueError(f"batch {self.batch_id}: sheets must be positive")


@dataclass(frozen=True)
class Press:
    press_id: str
    name: str
    sheets_per_hour: int
    lanes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.sheets_per_hour <= 0:
            raise ValueError(f"press {self.press_id}: sheets_per_hour must be positive")


@dataclass(frozen=True)
class PressAvailability:
    """What a supervisor states is actually available at shift start.

    Capacity is an input, not an assumption. A press with no operator has
    `operators=0` and contributes no time, which is different from a press
    that is absent from the shift entirely.
    """

    press_id: str
    hours: float
    operators: int = 1

    @property
    def minutes(self) -> float:
        return 0.0 if self.operators < 1 else self.hours * 60.0


@dataclass(frozen=True)
class ShiftCapacity:
    shift_date: date
    availability: tuple[PressAvailability, ...]

    def for_press(self, press_id: str) -> PressAvailability | None:
        for a in self.availability:
            if a.press_id == press_id:
                return a
        return None


@dataclass(frozen=True)
class PlacedBatch:
    """A batch placed on a press, with the position it holds in that run."""

    batch: Batch
    press_id: str
    position: int
    cycle: int
    run_minutes: float
    makeready_minutes: float

    @property
    def total_minutes(self) -> float:
        return self.run_minutes + self.makeready_minutes


@dataclass
class PressRun:
    press_id: str
    placed: list[PlacedBatch] = field(default_factory=list)

    @property
    def minutes_used(self) -> float:
        return sum(p.total_minutes for p in self.placed)

    @property
    def batch_ids(self) -> list[str]:
        return [p.batch.batch_id for p in self.placed]
