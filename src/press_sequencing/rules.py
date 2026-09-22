"""The rule vocabulary: a closed set of three sequencing primitives.

Ordering, alternation and grouping. Anything an operator or planner asks for
is expressed as a template built from these, not as a new rule type. Adding
open-ended rules turns this into a constraint solver, which is a different
and much larger project.

Press eligibility is deliberately NOT a rule primitive. "Holiday cards
excluded from Press 5" does not order, alternate or group anything; it says
where work may run at all. It lives in `eligibility.py`.

Each rule takes a list of batches already filtered to one press and one
cycle, and returns a reordered list. Rules are total functions on that list:
they never drop or duplicate a batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .model import Batch, Press, ProductClass


@dataclass(frozen=True)
class RuleScope:
    """Where a rule applies.

    Empty means everywhere. `lanes` matches when the press carries any of the
    named lanes, which is how the corner-alternation rules on lanes 2.1, 2.2
    and 3.1 are expressed without naming presses directly.
    """

    presses: tuple[str, ...] = ()
    lanes: tuple[str, ...] = ()

    def applies_to(self, press: Press) -> bool:
        if self.presses and press.press_id not in self.presses:
            return False
        if self.lanes and not set(self.lanes) & set(press.lanes):
            return False
        return True


class Rule(Protocol):
    rule_id: str
    scope: RuleScope

    def apply(self, batches: list[Batch], classes: dict[str, ProductClass]) -> list[Batch]:
        ...


def _class_of(batch: Batch, class_names: list[str], classes: dict[str, ProductClass]) -> str | None:
    """First named class that matches the batch, or None.

    First match wins so that overlapping classes stay predictable: the order
    a rule lists its classes in is the order they are tested in.
    """
    for name in class_names:
        pc = classes.get(name)
        if pc is not None and pc.matches(batch):
            return name
    return None


@dataclass(frozen=True)
class OrderingRule:
    """Within a class, run A, then B, then C.

    Stable: batches whose class is not named keep their relative position at
    the end of the list, rather than being reordered arbitrarily.
    """

    rule_id: str
    class_order: tuple[str, ...]
    scope: RuleScope = RuleScope()

    def apply(self, batches: list[Batch], classes: dict[str, ProductClass]) -> list[Batch]:
        order = {name: i for i, name in enumerate(self.class_order)}
        unranked = len(order)

        def key(item: tuple[int, Batch]) -> tuple[int, int]:
            i, batch = item
            name = _class_of(batch, list(self.class_order), classes)
            return (order.get(name, unranked) if name else unranked, i)

        return [b for _, b in sorted(enumerate(batches), key=key)]


@dataclass(frozen=True)
class GroupingRule:
    """Group by size or another attribute within a block.

    Groups appear in the order their first member appears in the input, so a
    grouping rule never silently reprioritises work — it only makes like sit
    with like.
    """

    rule_id: str
    attribute: str
    scope: RuleScope = RuleScope()

    def apply(self, batches: list[Batch], classes: dict[str, ProductClass]) -> list[Batch]:
        seen: dict[str, int] = {}
        for b in batches:
            value = b.attributes.get(self.attribute, "")
            seen.setdefault(value, len(seen))

        def key(item: tuple[int, Batch]) -> tuple[int, int]:
            i, batch = item
            return (seen[batch.attributes.get(self.attribute, "")], i)

        return [b for _, b in sorted(enumerate(batches), key=key)]


@dataclass(frozen=True)
class AlternationRule:
    """Alternate two product styles by a fixed count of batches or sheets.

    Covers corner alternation (four rounded / four square on lanes 2.1, 2.2
    and 3.1) and gloss/matte alternation for delivery stacking.

    `unit` is "batches" or "sheets". The sheets unit exists because the
    planned move from four batches to 204 sheets needs small batches to stop
    consuming a whole slot; it is expressible here and switched on in config,
    not in code.

    Batches matching neither class are appended after the alternated stream,
    in their original relative order. When one side runs out the other side
    continues rather than stalling the press.

    UNCONFIRMED SEMANTICS. A block is filled up to `count` without overshooting
    it: the next batch is left for the following block if taking it would put
    the block over budget. A single batch larger than the whole block is still
    taken, since batches are not split. The other reading - fill until the
    block reaches or exceeds `count` - gives different sequences, and which one
    204 sheets is meant to express has not been confirmed with the floor. See
    docs/open-questions.md.
    """

    rule_id: str
    class_a: str
    class_b: str
    count: int
    unit: str = "batches"
    scope: RuleScope = RuleScope()

    def __post_init__(self) -> None:
        if self.unit not in ("batches", "sheets"):
            raise ValueError(
                f"{self.rule_id}: unit must be 'batches' or 'sheets', got {self.unit!r}"
            )
        if self.count <= 0:
            raise ValueError(f"{self.rule_id}: count must be positive")

    def _weight(self, batch: Batch) -> int:
        return 1 if self.unit == "batches" else batch.sheets

    def apply(self, batches: list[Batch], classes: dict[str, ProductClass]) -> list[Batch]:
        names = [self.class_a, self.class_b]
        lanes: dict[str, list[Batch]] = {self.class_a: [], self.class_b: []}
        passthrough: list[Batch] = []

        for b in batches:
            name = _class_of(b, names, classes)
            if name is None:
                passthrough.append(b)
            else:
                lanes[name].append(b)

        result: list[Batch] = []
        current = self.class_a if lanes[self.class_a] else self.class_b
        accrued = 0

        while lanes[self.class_a] or lanes[self.class_b]:
            other = self.class_b if current == self.class_a else self.class_a
            if not lanes[current]:
                current, accrued = other, 0
                continue
            batch = lanes[current].pop(0)
            result.append(batch)
            accrued += self._weight(batch)

            # Switch when the block is full, or when the next batch on this
            # side would push it over budget. Taking at least one batch first
            # means an oversized batch fills a block on its own rather than
            # deadlocking.
            nxt = lanes[current][0] if lanes[current] else None
            overshoots = nxt is not None and accrued + self._weight(nxt) > self.count
            if accrued >= self.count or overshoots:
                current, accrued = other, 0

        return result + passthrough
