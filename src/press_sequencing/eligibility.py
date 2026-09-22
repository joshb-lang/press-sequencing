"""Press eligibility: where work may run at all.

This is not a fourth rule type. Ordering, alternation and grouping decide the
sequence of work that is already allowed on a press. Eligibility decides
what is allowed there in the first place. Conflating the two is what turns a
closed rule vocabulary into a constraint solver.

Several of these constraints are currently held as operator knowledge and are
routinely violated. Each carries a `status`: `verified` means someone on the
floor has confirmed the exact semantics encoded here, `unverified` means the
constraint is real but this encoding of it is a first pass and needs
confirming before it is trusted. See docs/open-questions.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Attributes, Batch, Press


@dataclass(frozen=True)
class Condition:
    """Matches a batch on attributes and, optionally, QC state."""

    attributes: Attributes
    qc_rejected: bool | None = None

    def matches(self, batch: Batch) -> bool:
        if self.qc_rejected is not None and batch.qc_rejected != self.qc_rejected:
            return False
        return all(batch.attributes.get(k) == v for k, v in self.attributes.items())


@dataclass(frozen=True)
class EligibilityConstraint:
    constraint_id: str
    when: Condition
    exclude_presses: tuple[str, ...] = ()
    allow_only_presses: tuple[str, ...] = ()
    status: str = "unverified"
    note: str = ""

    def __post_init__(self) -> None:
        if not self.exclude_presses and not self.allow_only_presses:
            raise ValueError(
                f"{self.constraint_id}: needs exclude_presses or allow_only_presses"
            )
        if self.status not in ("verified", "unverified"):
            raise ValueError(f"{self.constraint_id}: status must be verified or unverified")

    def permits(self, batch: Batch, press: Press) -> bool:
        if not self.when.matches(batch):
            return True
        if press.press_id in self.exclude_presses:
            return False
        if self.allow_only_presses and press.press_id not in self.allow_only_presses:
            return False
        return True


def eligible_presses(
    batch: Batch, presses: list[Press], constraints: list[EligibilityConstraint]
) -> list[Press]:
    return [p for p in presses if all(c.permits(batch, p) for c in constraints)]


def blocking_constraints(
    batch: Batch, press: Press, constraints: list[EligibilityConstraint]
) -> list[EligibilityConstraint]:
    """Why a batch may not run on a press. Used to explain an empty option set
    rather than silently stranding the work."""
    return [c for c in constraints if not c.permits(batch, press)]
