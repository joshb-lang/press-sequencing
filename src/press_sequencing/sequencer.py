"""The reference sequencer.

Deliberately shape-neutral on the plan-vs-dispatch question, which is not
settled. `sequence_shift` produces a whole-shift plan; `next_for_press`
answers "what next?" for one press from current state. Both run the same
rules over the same configuration, so choosing one shape later does not mean
rewriting the rule layer — which is the part worth building now.

The sequence is built in three phases:

1. Assignment. Each batch goes to an eligible press with room, earliest
   quoted ship date first. Time is reserved at worst-case makeready.
2. Sequencing. Each press's batches are ordered by the configured rule
   pipeline, cycle 1 before cycle 2.
3. Charging. The ordered sequence is walked with real makeready costs.
   Anything that no longer fits is truncated from the tail.

Because cycle 1 is laid down before cycle 2, overflow eats into work that is
not yet due before it touches work that ships today. It can still reach
due-dated work, and when it does the plan says so rather than quietly
shortening the list — see `sla.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .budget import BudgetLedger, run_minutes
from .config import ConfigError, SequencingConfig
from .eligibility import blocking_constraints, eligible_presses
from .model import Batch, PlacedBatch, Press, PressRun, ShiftCapacity

NO_ELIGIBLE_PRESS = "no_eligible_press"
NO_CAPACITY = "no_capacity"
TIME_BUDGET = "time_budget"


@dataclass(frozen=True)
class Stranded:
    """Work the plan could not place, and why."""

    batch: Batch
    reason: str
    detail: str = ""


@dataclass
class ShiftPlan:
    shift_date: date
    runs: dict[str, PressRun] = field(default_factory=dict)
    stranded: list[Stranded] = field(default_factory=list)

    def sequence_for(self, press_id: str) -> list[Batch]:
        run = self.runs.get(press_id)
        return [p.batch for p in run.placed] if run else []

    @property
    def placed_count(self) -> int:
        return sum(len(r.placed) for r in self.runs.values())


def cycle_of(batch: Batch, shift_date: date) -> int:
    """Cycle 1 is a batch with earliest quoted ship date today or earlier;
    cycle 2 is the remainder."""
    return 1 if batch.quoted_ship_date <= shift_date else 2


def _presses_on_shift(config: SequencingConfig, capacity: ShiftCapacity) -> list[Press]:
    unknown = [
        a.press_id for a in capacity.availability if config.press(a.press_id) is None
    ]
    if unknown:
        raise ConfigError([f"capacity names unknown press {p!r}" for p in unknown])
    return [
        press
        for a in capacity.availability
        if a.minutes > 0 and (press := config.press(a.press_id)) is not None
    ]


def sequence_shift(
    batches: list[Batch], capacity: ShiftCapacity, config: SequencingConfig
) -> ShiftPlan:
    presses = _presses_on_shift(config, capacity)
    plan = ShiftPlan(shift_date=capacity.shift_date)

    if not presses:
        plan.stranded = [
            Stranded(b, NO_CAPACITY, "no press has staffed hours on this shift")
            for b in batches
        ]
        return plan

    ledgers = {
        p.press_id: BudgetLedger(
            config.budget, capacity.for_press(p.press_id).minutes  # type: ignore[union-attr]
        )
        for p in presses
    }
    assigned: dict[str, dict[int, list[Batch]]] = {
        p.press_id: {1: [], 2: []} for p in presses
    }

    # Phase 1 - assignment.
    ordered = sorted(batches, key=lambda b: (b.quoted_ship_date, b.batch_id))
    for batch in ordered:
        options = eligible_presses(batch, presses, config.eligibility)
        if not options:
            plan.stranded.append(
                Stranded(batch, NO_ELIGIBLE_PRESS, _why_ineligible(batch, presses, config))
            )
            continue

        # Placeholder assignment policy: least loaded eligible press. It is
        # deliberately changeover-blind. Whether changeover is worth optimising
        # for is one of the numbers the Aug-Sep analysis is meant to answer.
        candidates = []
        for press in options:
            minutes = run_minutes(batch, press) + config.makeready.minutes_for(batch, None)
            if ledgers[press.press_id].fits(batch, minutes):
                candidates.append((ledgers[press.press_id].remaining, press, minutes))
        if not candidates:
            plan.stranded.append(
                Stranded(
                    batch,
                    NO_CAPACITY,
                    "eligible presses ("
                    + ", ".join(p.press_id for p in options)
                    + ") have no time left in the relevant budget",
                )
            )
            continue

        _, press, minutes = max(candidates, key=lambda c: (c[0], c[1].press_id))
        ledgers[press.press_id].charge(batch, minutes)
        assigned[press.press_id][cycle_of(batch, capacity.shift_date)].append(batch)

    # Phase 2 - sequencing, and phase 3 - charging with real makeready.
    for press in presses:
        run = PressRun(press_id=press.press_id)
        ledger = BudgetLedger(
            config.budget, capacity.for_press(press.press_id).minutes  # type: ignore[union-attr]
        )
        previous: Batch | None = None
        position = 0

        for cycle in (1, 2):
            sequenced = _apply_pipeline(assigned[press.press_id][cycle], press, config)
            for batch in sequenced:
                run_mins = run_minutes(batch, press)
                mk = config.makeready.minutes_for(batch, previous)
                if not ledger.fits(batch, run_mins + mk):
                    plan.stranded.append(
                        Stranded(
                            batch,
                            TIME_BUDGET,
                            f"truncated from {press.press_id}: sequence overran the "
                            "time window once makeready was applied",
                        )
                    )
                    continue
                ledger.charge(batch, run_mins + mk)
                run.placed.append(
                    PlacedBatch(
                        batch=batch,
                        press_id=press.press_id,
                        position=position,
                        cycle=cycle,
                        run_minutes=run_mins,
                        makeready_minutes=mk,
                    )
                )
                previous = batch
                position += 1

        plan.runs[press.press_id] = run

    return plan


def _apply_pipeline(
    batches: list[Batch], press: Press, config: SequencingConfig
) -> list[Batch]:
    """Run the configured rules, in configured order, over one press's batches.

    Later rules see the output of earlier ones, so pipeline order is part of
    the configuration and not an implementation detail.
    """
    result = list(batches)
    for rule in config.pipeline:
        if rule.scope.applies_to(press):
            result = rule.apply(result, config.classes)
    return result


def _why_ineligible(batch: Batch, presses: list[Press], config: SequencingConfig) -> str:
    reasons: list[str] = []
    for press in presses:
        blocking = blocking_constraints(batch, press, list(config.eligibility))
        if blocking:
            reasons.append(f"{press.press_id}: {', '.join(c.constraint_id for c in blocking)}")
    return "; ".join(reasons) if reasons else "no press on shift accepts this batch"


def next_for_press(
    press_id: str,
    batches: list[Batch],
    capacity: ShiftCapacity,
    config: SequencingConfig,
    printed: set[str] | None = None,
) -> Batch | None:
    """What should this press run next, given what has already printed.

    Dispatch is the same computation as planning, taken one batch at a time:
    recompute from current state and return the head of the press's sequence.
    Recomputing rather than reading from a frozen plan is what lets a press
    self-heal after an abandoned run, and it is why a plan made at 06:00
    going stale by mid-morning is not fatal here.
    """
    printed = printed or set()
    open_batches = [b for b in batches if b.batch_id not in printed]
    plan = sequence_shift(open_batches, capacity, config)
    sequence = plan.sequence_for(press_id)
    return sequence[0] if sequence else None
